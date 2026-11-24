"""Logging in at greetd and reading the graphical session back over serial.

The login goes through the real path: gtkgreet on the VGA console, typed with
QEMU's `sendkey`, so PAM, pam_systemd_home and the session's own startup (sway,
its terminal, the first-login playbook in that terminal's login shell) all run
as they do on hardware. Everything is then read from the root shell on serial.
"""

import base64
import json
import re
import shlex
import string
import time
from dataclasses import dataclass

# --- typing at the VGA console ----------------------------------------------

# QEMU key names for the characters that aren't their own name, on a US layout.
_UNSHIFTED = {
    " ": "spc",
    "-": "minus",
    "=": "equal",
    "[": "bracket_left",
    "]": "bracket_right",
    "\\": "backslash",
    ";": "semicolon",
    "'": "apostrophe",
    "`": "grave_accent",
    ",": "comma",
    ".": "dot",
    "/": "slash",
}
_SHIFTED = {
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "minus",
    "+": "equal",
    "{": "bracket_left",
    "}": "bracket_right",
    "|": "backslash",
    ":": "semicolon",
    '"': "apostrophe",
    "~": "grave_accent",
    "<": "comma",
    ">": "dot",
    "?": "slash",
}


def sendkeys_for(text):
    """The `sendkey` arguments that type `text` on a US layout."""
    keys = []
    for char in text:
        if char in string.ascii_lowercase or char in string.digits:
            keys.append(char)
        elif char in string.ascii_uppercase:
            keys.append(f"shift-{char.lower()}")
        elif char in _UNSHIFTED:
            keys.append(_UNSHIFTED[char])
        elif char in _SHIFTED:
            keys.append(f"shift-{_SHIFTED[char]}")
        else:
            raise ValueError(f"no key types {char!r}")

    return tuple(keys)


def type_text(vm, text):
    for key in sendkeys_for(text):
        vm.monitor.sendkey(key)


# --- guest files -------------------------------------------------------------

# Under the tty's 4096-byte line limit, with room for the command around it.
_CHUNK = 2048


def write_guest_file(shell, path, data, mode="0644"):
    """Write `data` (str or bytes) to `path` in the guest, through the shell."""
    raw = data.encode() if isinstance(data, str) else data
    encoded = base64.b64encode(raw).decode()
    staging = f"{path}.b64"
    shell.run(f": > {shlex.quote(staging)}", check=True, quiet=True)
    for start in range(0, len(encoded), _CHUNK):
        chunk = encoded[start : start + _CHUNK]
        shell.run(
            f"printf %s {chunk} >> {shlex.quote(staging)}", check=True, quiet=True
        )
    shell.run(
        f"base64 -d {shlex.quote(staging)} > {shlex.quote(path)}"
        f" && rm {shlex.quote(staging)} && chmod {mode} {shlex.quote(path)}",
        check=True,
    )


# --- the software token ------------------------------------------------------

# The key and cert sit at id 03, PIV slot 9D's, which first-login.yml looks for.
_SEED_TOKEN = r"""
set -o errexit
set -o nounset
set -o pipefail

pin=$1
so_pin=$2
mkdir -p /etc/softhsm /var/lib/softhsm/tokens
if [[ ! -e /etc/softhsm/softhsm2.conf ]]; then
  printf '%s\n' 'directories.tokendir = /var/lib/softhsm/tokens/' \
    'objectstore.backend = file' > /etc/softhsm/softhsm2.conf
fi
softhsm2-util --init-token --free --label ci --pin "$pin" --so-pin "$so_pin"

work=$(mktemp -d)
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj /CN=arch-ansible-ci-token \
  -keyout "$work/key.pem" -out "$work/cert.pem" 2>/dev/null
softhsm2-util --import "$work/key.pem" --token ci --label homed --id 03 --pin "$pin"
GNUTLS_PIN=$pin p11tool --batch --login --write --load-certificate "$work/cert.pem" \
  --label homed --id 03 'pkcs11:token=ci'
rm -rf "$work"

# Read by the user's p11tool at first login and by homed as root.
chmod -R a+rwX /var/lib/softhsm/tokens
"""


def seed_software_token(shell, pin, so_pin):
    """Create the SoftHSM token that stands in for the YubiKey's PIV applet."""
    write_guest_file(shell, "/var/tmp/ci-seed-token", _SEED_TOKEN, mode="0700")
    shell.run(
        f"bash /var/tmp/ci-seed-token {shlex.quote(pin)} {shlex.quote(so_pin)}",
        check=True,
    )


# --- greetd ------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Session:
    id: str
    type: str
    active: bool
    seat: str


def home_user(shell):
    """The one homed user, created at first boot."""
    _, out = shell.run("homectl list --json=short", check=True)

    return json.loads(out)[0]["name"]


def home_state(shell, user):
    _, out = shell.run("homectl list --json=short", check=True)

    return next(row["state"] for row in json.loads(out) if row["name"] == user)


def user_session(shell, user):
    """`user`'s session on seat0, if they have one."""
    _, out = shell.run("loginctl list-sessions --json=short", check=True)
    ids = [
        row["session"]
        for row in json.loads(out)
        if row.get("user") == user and row.get("seat") == "seat0"
    ]
    if not ids:
        return None

    _, props = shell.run(
        f"loginctl show-session {shlex.quote(ids[0])} -p Type -p Active -p Seat",
        check=True,
    )
    values = dict(line.split("=", 1) for line in props.splitlines() if "=" in line)

    return Session(
        id=ids[0],
        type=values.get("Type", ""),
        active=values.get("Active") == "yes",
        seat=values.get("Seat", ""),
    )


def wait_for_greeter(shell, timeout=300):
    """Wait for gtkgreet to be up and drawn."""
    deadline = time.monotonic() + timeout
    while shell.run("pgrep -u greeter -x gtkgreet", quiet=True)[0] != 0:
        if time.monotonic() > deadline:
            raise TimeoutError(f"no gtkgreet after {timeout}s")
        time.sleep(2)
    # Running is not yet mapped and focused.
    time.sleep(5)


def log_in(vm, user, secret, attempts=3, settle=20):
    """Log in at gtkgreet; returns the new Session, or None if none started.

    The secret answers each prompt PAM shows after the user name. A token-only
    home can ask more than once (a password first, then the token's PIN), so
    it's typed up to `attempts` times, stopping as soon as a session exists so
    nothing spills into the session itself.
    """
    sh = vm.shell
    wait_for_greeter(sh)
    vm.log(f"==> logging in as {user} at greetd")
    type_text(vm, user)
    time.sleep(1)
    vm.screenshot("greeter-user")
    vm.monitor.sendkey("ret")
    time.sleep(3)
    for attempt in range(1, attempts + 1):
        type_text(vm, secret)
        time.sleep(1)
        vm.screenshot(f"greeter-secret-{attempt}")
        vm.monitor.sendkey("ret")
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline:
            if session := user_session(sh, user):
                return session
            time.sleep(2)

    return None


_KEYBOARD_EVENT = (
    "awk '/AT Translated/ {found = 1} found && /^H:/"
    " {match($0, /event[0-9]+/); print substr($0, RSTART, RLENGTH); exit}'"
    " /proc/bus/input/devices"
)


def keyboard_probe(vm):
    """Bytes the guest kernel's keyboard device delivered while QEMU typed."""
    sh = vm.shell
    _, event = sh.run(_KEYBOARD_EVENT, quiet=True)
    if not event.strip():
        return "no AT keyboard event device"

    sh.run(
        f"(timeout 6 cat /dev/input/{event.strip()} > /var/tmp/ci-kbd.bin &)",
        quiet=True,
    )
    time.sleep(1)
    type_text(vm, "abc")
    time.sleep(6)
    _, size = sh.run("stat -c %s /var/tmp/ci-kbd.bin", quiet=True)

    return f"/dev/input/{event.strip()} delivered {size.strip()} bytes for 3 keys"


def login_diagnostics(vm):
    """What a failed greetd login leaves behind: whether typed keys reach the
    guest's kernel and the greeter's sway, and the recent journal of greetd,
    PAM and homed."""
    sh = vm.shell
    _, inputs = sh.run("grep -h '^N: Name=' /proc/bus/input/devices", quiet=True)
    probe = keyboard_probe(vm)
    greeter_sway = "SWAYSOCK=$(ls /run/user/$(id -u greeter)/sway-ipc.*.sock | head -1)"
    _, sway_inputs = sh.run(
        f"{greeter_sway} swaymsg -t get_inputs -r"
        " | python3 -c 'import json, sys;"
        ' [print(i["type"], i["identifier"]) for i in json.load(sys.stdin)]\'',
        quiet=True,
    )
    _, sway_seats = sh.run(f"{greeter_sway} swaymsg -t get_seats", quiet=True)
    _, journal = sh.run(
        "journalctl -b --no-pager -o short-monotonic --since -10min"
        " | grep -iE 'greetd|gtkgreet|pam|homed|homework|sway|softhsm|pkcs' | tail -150",
        timeout=60,
        quiet=True,
    )

    return (
        f"input devices:\n{inputs}\n\nkeyboard probe: {probe}\n\n"
        f"greeter sway inputs:\n{sway_inputs}\n\ngreeter sway seats:\n{sway_seats}"
        f"\n\njournal:\n{journal}"
    )


def log_out(shell, user, timeout=120):
    """End `user`'s sessions, wait for homed to lock the home, then restart
    greetd for a fresh greeter."""
    shell.run(f"loginctl terminate-user {shlex.quote(user)}", check=True)
    deadline = time.monotonic() + timeout
    while home_state(shell, user) != "inactive":
        if time.monotonic() > deadline:
            raise TimeoutError(f"the home of {user} still active after {timeout}s")
        time.sleep(2)
    restart_greeter(shell)


def restart_greeter(shell):
    shell.run("systemctl restart greetd", check=True)


# --- the session -------------------------------------------------------------

GHOSTTY = "com.mitchellh.ghostty"
FIREFOX = "firefox"
PAGE_TITLE = "arch-ansible CI page"


def user_uid(shell, user):
    _, out = shell.run(f"id -u {shlex.quote(user)}", check=True)

    return int(out.strip())


def sway_socket(shell, uid, timeout=180):
    deadline = time.monotonic() + timeout
    while True:
        rc, out = shell.run(
            f"ls /run/user/{uid}/sway-ipc.*.sock 2>/dev/null | head -1", quiet=True
        )
        if rc == 0 and out.strip():
            return out.strip()
        if time.monotonic() > deadline:
            raise TimeoutError(f"no sway IPC socket after {timeout}s")
        time.sleep(2)


def swaymsg(shell, sock, args):
    return shell.run(f"SWAYSOCK={shlex.quote(sock)} swaymsg {args}", quiet=True)


@dataclass(frozen=True, kw_only=True)
class Window:
    app_id: str
    title: str
    workspace: str


def parse_sway_tree(tree):
    """Every application window in `swaymsg -t get_tree -r` output."""
    windows = []
    stack = [(json.loads(tree), "")]
    while stack:
        node, workspace = stack.pop()
        if node.get("type") == "workspace":
            workspace = node.get("name", "")
        if node.get("type") in ("con", "floating_con") and node.get("pid"):
            windows.append(
                Window(
                    app_id=node.get("app_id") or "",
                    title=node.get("name") or "",
                    workspace=workspace,
                )
            )
        stack.extend(
            (child, workspace)
            for child in node.get("nodes", []) + node.get("floating_nodes", [])
        )

    return tuple(windows)


def sway_windows(shell, sock):
    rc, out = swaymsg(shell, sock, "-t get_tree -r")

    return parse_sway_tree(out) if rc == 0 else ()


def wait_for_windows(shell, sock, app_ids, timeout=300):
    """The session's windows, once one of each of `app_ids` is open (or at the
    timeout, whatever is open then)."""
    deadline = time.monotonic() + timeout
    while True:
        windows = sway_windows(shell, sock)
        if set(app_ids) <= {w.app_id for w in windows}:
            return windows
        if time.monotonic() > deadline:
            return windows
        time.sleep(3)


def wait_for_title(shell, sock, app_id, title, timeout=120):
    """The title of `app_id`'s window, once it contains `title` (or at the
    timeout, whatever it is then)."""
    deadline = time.monotonic() + timeout
    while True:
        titles = [w.title for w in sway_windows(shell, sock) if w.app_id == app_id]
        if any(title in t for t in titles) or time.monotonic() > deadline:
            return next((t for t in titles if title in t), titles[0] if titles else "")
        time.sleep(2)


def open_local_page(shell, sock):
    """Open a local page in the running Firefox; returns the window's title
    once it shows the page's (or whatever it shows at the timeout)."""
    write_guest_file(
        shell,
        "/var/tmp/ci-page.html",
        f"<!doctype html><title>{PAGE_TITLE}</title><p>arch-ansible CI</p>\n",
    )
    swaymsg(shell, sock, shlex.quote("exec firefox file:///var/tmp/ci-page.html"))

    return wait_for_title(shell, sock, FIREFOX, PAGE_TITLE)


def tmux_pane(shell, uid):
    """The full history of the user's tmux pane: the terminal sway opens at
    login, where zlogin runs the first-login playbook."""
    _, sock = shell.run(
        f"find /tmp/tmux-{uid} /run/user/{uid} -maxdepth 2 -type s -name default"
        " 2>/dev/null | head -1",
        quiet=True,
    )
    if not sock.strip():
        return ""

    rc, out = shell.run(
        f"tmux -S {shlex.quote(sock.strip())} capture-pane -p -J -S -", quiet=True
    )

    return out if rc == 0 else ""


_RECAP_HOST = re.compile(r"^\S+\s+:\s+((?:\w+=\d+\s*)+)$", re.MULTILINE)


def play_recap(output):
    """The counts on the PLAY RECAP of ansible-playbook `output`, summed over
    hosts, or None if the play hasn't finished."""
    _, sep, recap = output.rpartition("PLAY RECAP")
    if not sep:
        return None

    totals = {}
    for m in _RECAP_HOST.finditer(recap):
        for field in m.group(1).split():
            name, value = field.split("=")
            totals[name] = totals.get(name, 0) + int(value)

    return totals or None


def wait_for_play_recap(shell, uid, timeout):
    """The first-login playbook's PLAY RECAP and the pane it ran in."""
    deadline = time.monotonic() + timeout
    while True:
        pane = tmux_pane(shell, uid)
        recap = play_recap(pane)
        if recap is not None or time.monotonic() > deadline:
            return recap, pane
        time.sleep(10)


# --- the home ----------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Home:
    token_uris: tuple[str, ...]
    has_password: bool
    keyslots: int


_KEYSLOTS = r"""
loop=$(losetup -nO NAME -j "/home/$1.home" | head -1)
part=$(lsblk -nrpo NAME,FSTYPE "$loop" | awk '$2 == "crypto_LUKS" {print $1; exit}')
cryptsetup luksDump --dump-json-metadata "$part" \
  | python3 -c 'import json, sys; print(len(json.load(sys.stdin)["keyslots"]))'
"""


def home_facts(shell, user):
    """How the active home of `user` is unlocked."""
    _, out = shell.run(f"homectl inspect {shlex.quote(user)} --json=short", check=True)
    record = json.loads(out)
    write_guest_file(shell, "/var/tmp/ci-keyslots", _KEYSLOTS, mode="0700")
    _, slots = shell.run(f"bash /var/tmp/ci-keyslots {shlex.quote(user)}", check=True)

    return Home(
        token_uris=tuple(record.get("pkcs11TokenUri", ())),
        has_password="hashedPassword" in record.get("privileged", {}),
        keyslots=int(slots.strip().splitlines()[-1]),
    )
