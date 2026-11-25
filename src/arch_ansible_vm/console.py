"""The guest's serial console, a root shell driven over it, and QEMU's HMP monitor."""

import re
import socket
import sys
import threading
import time

# --- terminal-output handling ------------------------------------------------
#
# sd-boot draws its menu with CSI cursor/colour sequences and agetty/bash echo
# more of the same. We keep the raw byte stream in the log file (so a failed run
# can be inspected exactly as the guest emitted it) but match against an
# escape-stripped copy.
_ANSI = re.compile(
    rb"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC ... BEL/ST
    rb"|\x1b\[[0-9;?]*[ -/]*[@-~]"  # CSI
    rb"|\x1b[@-Z\\-_78=>]"  # two-byte escapes, incl. DECSC/DECRC
)
# A read can split an escape sequence; hold the tail back until it completes
# rather than letting its bytes leak into the match text as literal garbage.
# An OSC can be cut between the two bytes of its ESC-\ terminator, so allow a
# trailing ESC after its body.
_PARTIAL = re.compile(rb"\x1b(?:\[[0-9;?]*[ -/]*|\][^\x07\x1b]*\x1b?)?$")


class Console:
    """The guest's serial port: a byte log plus an expect-style match buffer."""

    def __init__(self, path, log_path, echo=False):
        self.sock = _connect(path)
        # Held open for the console's lifetime: the reader thread writes to it.
        self.log = open(log_path, "wb")  # noqa: SIM115
        self.echo = echo
        self._pending = b""
        self._lock = threading.Lock()
        self.text = ""
        self.raw = bytearray()
        self.pos = 0
        self.eof = False
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        while True:
            try:
                data = self.sock.recv(65536)
            except OSError:
                break
            if not data:
                break
            self.log.write(data)
            self.log.flush()
            with self._lock:
                self.raw += data
                buf = self._pending + data
                m = _PARTIAL.search(buf)
                if m:
                    self._pending, buf = buf[m.start() :], buf[: m.start()]
                else:
                    self._pending = b""
                clean = _ANSI.sub(b"", buf).replace(b"\r", b"").replace(b"\x00", b"")
                chunk = clean.decode("utf-8", "replace")
                self.text += chunk
            if self.echo and chunk:
                sys.stdout.write(chunk)
                sys.stdout.flush()
        self.eof = True

    def expect(self, pattern, timeout=120, consume=True):
        """Wait for `pattern` after the last consumed match. Returns the Match."""
        rx = re.compile(pattern, re.MULTILINE) if isinstance(pattern, str) else pattern
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                m = rx.search(self.text, self.pos)
                if m:
                    if consume:
                        self.pos = m.end()
                    return m
                tail = self.text[-2000:]
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"timed out after {timeout}s waiting for {rx.pattern!r}.\n"
                    f"--- last serial output ---\n{tail}\n--- end ---"
                )
            if self.eof:
                raise EOFError(
                    f"serial closed (guest exited?) while waiting for "
                    f"{rx.pattern!r}.\n--- last serial output ---\n{tail}\n--- end ---"
                )
            time.sleep(0.05)

    def send(self, data):
        self.sock.sendall(data.encode())

    def snapshot(self):
        with self._lock:
            return self.text

    def raw_snapshot(self):
        with self._lock:
            return bytes(self.raw)


class Monitor:
    """QEMU's HMP monitor: keys, clicks and screendumps, which need no display."""

    def __init__(self, path):
        self.sock = _connect(path)
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self):
        while True:
            try:
                if not self.sock.recv(65536):
                    break
            except OSError:
                break

    def cmd(self, line):
        self.sock.sendall((line + "\n").encode())
        # HMP has no completion signal we care about; a small gap keeps a burst
        # of sendkeys from outrunning the guest's key queue.
        time.sleep(0.03)

    def sendkey(self, key, times=1):
        for _ in range(times):
            self.cmd(f"sendkey {key}")

    def click(self, x, y):
        """Left-click at pixel (x, y) through the absolute virtio-tablet."""
        self.cmd(f"mouse_move {x} {y}")
        self.cmd("mouse_button 1")
        self.cmd("mouse_button 0")

    def screendump(self, path):
        self.cmd(f"screendump {path}")


def _connect(path, timeout=30):
    deadline = time.monotonic() + timeout
    while True:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(str(path))
            return s
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)


# --- guest shell -------------------------------------------------------------

READY = "__VM_READY__"
BEGIN_RE = r"^__VM_BEGIN__$"
RC_RE = r"__RC_(\d+)__END__"


class Shell:
    """A root shell on the serial console, driven with sentinel markers.

    Every command is bracketed by two markers, each written so that the tty's
    echo of the command line cannot be mistaken for the marker itself: bash
    concatenates `"__VM_BEG""IN__"` into the output we look for, while the
    echoed line still reads `__VM_BEG""IN__`. Bracketing (rather than splitting
    on the echoed command) is what makes this robust — agetty wraps long
    command lines, so the echo is not reliably one line, let alone the exact
    bytes we sent.
    """

    def __init__(self, console, log):
        self.c = console
        self.log = log

    def wait_ready(self, timeout=600):
        """Poke the console until a shell answers."""
        deadline = time.monotonic() + timeout
        while True:
            self.c.send("\n")
            # Split so the command echo can't match the marker we look for.
            self.c.send('echo "__VM""_READY__"\n')
            try:
                self.c.expect(rf"^{READY}$", timeout=5)
                # Serial is a tty, so systemctl/journalctl page any output
                # longer than zero lines and the command never returns.
                self.c.send("export SYSTEMD_PAGER= PAGER=cat\n")
                return
            except TimeoutError:
                if time.monotonic() > deadline:
                    raise TimeoutError("no root shell on the serial console")
            except EOFError:
                raise

    def run(self, cmd, timeout=120, check=False, quiet=False):
        """Run `cmd`, return (rc, output). Output excludes the command echo."""
        self.c.send('echo "__VM_BEG""IN__"; ' + cmd + '; echo "__RC_$?__END__"\n')
        begin = self.c.expect(BEGIN_RE, timeout=timeout)
        m = self.c.expect(RC_RE, timeout=timeout)
        rc = int(m.group(1))
        out = self.c.text[begin.end() : m.start()].strip("\n")
        if not quiet:
            self.log(f"$ {cmd}")
            if out:
                self.log(out)
            self.log(f"[rc={rc}]")
        if check and rc != 0:
            raise RuntimeError(f"guest command failed (rc={rc}): {cmd}\n{out}")
        return rc, out
