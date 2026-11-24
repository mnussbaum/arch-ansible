"""Launching QEMU guests: firmware varstore, swtpm, virtiofs, and the QEMU and
`mkosi vm` command lines."""

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from arch_ansible_vm.console import Console, Monitor, Shell
from arch_ansible_vm.disks import cache_dir, medium_version, newest_medium

REPO = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True, kw_only=True)
class Drive:
    """A raw disk image attached as a virtio-blk device."""

    file: Path
    bootindex: int | None = None
    # Discard the guest's writes, leaving the file untouched.
    snapshot: bool = False


@dataclass(frozen=True, kw_only=True)
class LiveOptions:
    """How to boot the built medium through `mkosi vm`."""

    cpus: int
    memory: str
    # Normalized as selected_organizations returns them.
    organizations: str
    # A second disk, attached as /dev/vdb.
    device: str | None = None
    gui: bool = False
    yubikey: bool = False
    ephemeral: bool = False


def mkosi_env():
    """The environment `mkosi` needs to expand mkosi/mkosi.conf.

    mkosi/mkosi.conf refers to ${ARCH_ANSIBLE_CACHE}, ${ARCH_ANSIBLE_SRCTREE} and
    ${ARCH_ANSIBLE_PASSWORD_STORE} and expands them from the process environment
    (bin/_cache_common.sh exports them for the build scripts). Without them
    mkosi fails config validation before it boots anything:
    "${ARCH_ANSIBLE_CACHE}/cargo/registry does not exist". An already-exported
    value wins, matching _cache_common.sh.
    """
    env = dict(os.environ)
    cache = cache_dir()
    env.setdefault("ARCH_ANSIBLE_CACHE", str(cache))
    env.setdefault("ARCH_ANSIBLE_SRCTREE", str(cache / "mkosi-srctree"))
    store = Path(
        os.environ.get("PASSWORD_STORE_DIR")
        or Path.home() / ".local/share/password-store"
    )
    if not store.is_dir():
        store = Path("/usr/share/password-store")
    env.setdefault("ARCH_ANSIBLE_PASSWORD_STORE", str(store))
    return env


def secureboot_cert(recover=False):
    cert = cache_dir() / "mkosi-secureboot/mkosi.crt"
    if not cert.is_file() and recover:
        # Cache cleared but the image is still present: re-materialize the cert
        # from pass. The only path here that touches GPG, so it is opt-in — a
        # headless run can't answer a YubiKey prompt.
        out = subprocess.run(
            [
                "bash",
                "-c",
                (
                    "source bin/_cache_common.sh; source bin/_secureboot_common.sh; "
                    "trap forget_secureboot_key EXIT; "
                    'materialize_secureboot_keypair >&2; printf %s "$SECUREBOOT_CERT"'
                ),
            ],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            cert = Path(out.stdout.strip())
    if not cert.is_file():
        sys.exit(
            f"error: {cert} is missing. Run bin/build-image once to materialize "
            "the Secure Boot keypair (it may prompt for GPG/YubiKey, which a "
            "headless run can't answer)."
        )
    return cert


def make_varstore(dest, cert):
    """OVMF varstore with our Secure Boot cert enrolled (PK/KEK/db).

    Kept per-VM and persistent so PCR 7 is stable across boots — a TPM2-sealed
    LUKS keyslot enrolled on first boot can only be unsealed if the firmware
    comes up in the same Secure Boot state. (virt-fw-vars' --enroll-cert is
    broken in virt-firmware 26.x; the file-based options work — same approach as
    bin/vm run, with or without --gui.)
    """
    if dest.is_file() and dest.stat().st_mtime >= cert.stat().st_mtime:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "virt-fw-vars",
            "--input",
            "/usr/share/edk2/x64/OVMF_VARS.4m.fd",
            "--output",
            str(dest),
            "--set-pk",
            "OvmfEnrollDefaultKeys",
            str(cert),
            "--add-kek",
            "OvmfEnrollDefaultKeys",
            str(cert),
            "--add-db",
            "OvmfEnrollDefaultKeys",
            str(cert),
            "--secure-boot",
        ],
        check=True,
    )
    return dest


def start_swtpm(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    # swtpm puts its control socket inside the state dir, and AF_UNIX paths cap
    # at ~108 bytes. Past that swtpm dies with "Path for UnixIO socket is too
    # long", which otherwise surfaces as an opaque CalledProcessError traceback.
    sock_len = len(str(state_dir / "swtpm-sock").encode())
    if sock_len > 100:
        sys.exit(
            f"error: --tpm-state path is too long ({sock_len} bytes for its "
            f"control socket; the AF_UNIX limit is ~108). Use a shorter "
            f"directory, e.g. under {cache_dir()}/mkosi/."
        )
    if not (state_dir / "tpm2-00.permall").exists():
        subprocess.run(
            ["swtpm_setup", "--tpm2", "--tpmstate", str(state_dir), "--createek"],
            check=True,
        )
    sock = state_dir / "swtpm-sock"
    pidfile = state_dir / "swtpm.pid"
    subprocess.run(
        [
            "swtpm",
            "socket",
            "--tpm2",
            "--tpmstate",
            f"dir={state_dir}",
            "--ctrl",
            f"type=unixio,path={sock}",
            "--pid",
            f"file={pidfile}",
            "--daemon",
        ],
        check=True,
    )
    return sock, pidfile


def stop_swtpm(pidfile):
    try:
        os.kill(int(pidfile.read_text().strip()), signal.SIGTERM)
    except OSError, ValueError:
        pass


# Answers for the two questions an installed system asks on its first boot
# (systemd-firstboot --prompt-hostname and --prompt-root-password). Fixed rather
# than flags: these are test VMs, and a prompt nobody answers hangs the boot
# silently on tty0.
FIRSTBOOT_HOSTNAME = "arch-vmtest"
FIRSTBOOT_ROOT_PASSWORD = "root"

# Deliberately NOT mkosi's "/run/host/shared" tag: that one is claimed by
# mnt-shared.mount, which is gated on mkosi's fstab.extra credential. Using our
# own tag keeps the two mechanisms independent — this share is mounted explicitly
# by whoever asked for it, and mnt-shared.mount stays inert.
SHARE_TAG = "vmtest-share"
SHARE_MNT = "/mnt/vmtest"


def start_virtiofsd(share_dir, run_dir, name):
    """Export `share_dir` to the guest over virtiofs.

    Runs unprivileged (`--sandbox none`, no user namespace), which is enough to
    serve a directory the invoking user already owns — and, unlike the host-side
    sudo the offline `update-system --image` path needs, requires no privilege
    escalation at all.
    """
    share_dir = Path(share_dir).resolve()
    if not share_dir.is_dir():
        sys.exit(f"error: --share {share_dir} is not a directory")
    for exe in ("virtiofsd", "/usr/lib/virtiofsd", "/usr/libexec/virtiofsd"):
        path = shutil.which(exe) or (exe if Path(exe).is_file() else None)
        if path:
            break
    else:
        sys.exit("error: virtiofsd not found (pacman -S virtiofsd)")
    sock = run_dir / f"{name}-virtiofs.sock"
    sock.unlink(missing_ok=True)
    proc = subprocess.Popen(
        [
            path,
            "--socket-path",
            str(sock),
            "--shared-dir",
            str(share_dir),
            "--sandbox",
            "none",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        if sock.exists():
            break
        time.sleep(0.05)
    else:
        proc.terminate()
        sys.exit("error: virtiofsd never created its socket")
    return {"proc": proc, "sock": sock, "dir": share_dir}


def yubikey_qemu_args():
    """QEMU args passing the host's YubiKey through to the guest over USB.

    The guest then sees the real card (PIV via pcscd, FIDO2), so smartcard
    unlock and enrollment can be tested; the host can't use the key meanwhile.
    Opening the device needs no root: the desktop session's uaccess ACL grants
    the logged-in user read-write on it.
    """
    # A socket-activated host pcscd, woken by any host smartcard client (e.g.
    # gpg's scdaemon), takes the key back from QEMU mid-boot.
    active = subprocess.run(
        ["systemctl", "is-active", "--quiet", "pcscd.socket", "pcscd.service"],
        check=False,
    )
    if active.returncode == 0:
        sys.exit(
            "error: --yubikey: the host's pcscd would take the YubiKey back from "
            "the guest; stop it first: sudo systemctl stop pcscd.socket pcscd.service "
            "(start pcscd.socket again afterwards)"
        )
    for dev in sorted(Path("/sys/bus/usb/devices").iterdir()):
        vendor = dev / "idVendor"
        if vendor.exists() and vendor.read_text().strip() == "1050":
            bus = int((dev / "busnum").read_text())
            addr = int((dev / "devnum").read_text())
            return [
                "-device",
                "qemu-xhci,id=ykxhci",
                "-device",
                f"usb-host,bus=ykxhci.0,hostbus={bus},hostaddr={addr}",
            ]
    sys.exit("error: --yubikey: no YubiKey (USB vendor 1050) is plugged in")


def build_qemu_args(
    drives,
    varstore,
    tpm_sock,
    memory,
    cpus,
    credentials,
    serial,
    monitor_sock=None,
    share_sock=None,
    gui=False,
    extra=(),
):
    """Assemble the QEMU command line shared by every subcommand.

    Split out of Vm so it can be inspected (and tested) without launching
    anything. `serial` is either ("socket", path) — the headless case, where the
    console is driven over a unix socket — or ("file", path), which just logs the
    guest's serial output for a GUI run.
    """
    args = [
        "qemu-system-x86_64",
        "-machine",
        "type=q35,smm=on,hpet=off",
        "-smp",
        str(cpus),
        "-m",
        memory,
        "-cpu",
        "host",
        "-accel",
        "kvm",
        "-global",
        "ICH9-LPC.disable_s3=1",
        "-global",
        "driver=cfi.pflash01,property=secure,value=on",
        "-drive",
        (
            "if=pflash,format=raw,unit=0,readonly=on,"
            "file=/usr/share/edk2/x64/OVMF_CODE.secboot.4m.fd"
        ),
        "-drive",
        f"if=pflash,format=raw,unit=1,file={varstore}",
        "-object",
        "rng-random,filename=/dev/urandom,id=rng0",
        "-device",
        "virtio-rng-pci,rng=rng0",
        "-chardev",
        f"socket,id=chrtpm,path={tpm_sock}",
        "-tpmdev",
        "emulator,id=tpm0,chardev=chrtpm",
        "-device",
        "tpm-tis,tpmdev=tpm0",
        "-nic",
        "user,model=virtio-net-pci",
        # Keep the VGA adapter (so /dev/tty0 and thus /dev/console exist in
        # the guest exactly as they do under a GUI run) even when headless.
        "-device",
        "virtio-vga",
        # Guest RAM as a shareable memfd. Plain -m memory can't be mapped by
        # an external vhost-user process, so virtiofsd needs this even when
        # no share is configured for this run (harmless if unused).
        "-object",
        f"memory-backend-memfd,id=mem,size={memory},share=on",
        "-numa",
        "node,memdev=mem",
    ]
    if gui:
        # Only the GTK backend forwards window-resize ui_info to virtio-vga, so
        # the guest's output follows the host window instead of staying at
        # 1024x768; zoom-to-fit=off resizes the guest rather than scaling a
        # fixed framebuffer. grab-on-hover=on engages the Wayland
        # keyboard-shortcuts-inhibit protocol so the host compositor stops
        # eating $mod bindings (Ctrl+Alt+G toggles the grab by hand).
        args += ["-display", "gtk,gl=on,zoom-to-fit=off,grab-on-hover=on"]
        # Absolute pointing device: without it QEMU gives the guest a relative
        # PS/2 mouse, so the guest cursor drifts out of sync with the host
        # pointer and clicks land in the wrong place.
        args += ["-device", "virtio-tablet"]
    else:
        args += ["-display", "none"]

    kind, path = serial
    if kind == "socket":
        # wait=on: QEMU holds the machine reset until we attach, so none of
        # sd-boot's menu is lost to a connect race.
        args += [
            "-chardev",
            f"socket,id=serial0,path={path},server=on,wait=on",
            "-serial",
            "chardev:serial0",
        ]
    else:
        # Nothing is driving the console, so just capture it to a file the way
        # the old bin/boot-disk did; the window is the interactive surface.
        args += [
            "-chardev",
            f"file,id=serial0,path={path}",
            "-serial",
            "chardev:serial0",
        ]
    if monitor_sock:
        args += ["-monitor", f"unix:{monitor_sock},server,nowait"]

    for i, d in enumerate(drives):
        opts = f"if=none,id=drive{i},file={d.file},format=raw"
        if d.snapshot:
            opts += ",snapshot=on"
        args += ["-drive", opts]
        dev = f"virtio-blk-pci,drive=drive{i}"
        if d.bootindex is not None:
            dev += f",bootindex={d.bootindex}"
        args += ["-device", dev]
    # The kernel console on serial, for the root shell and the boot log. Not in
    # the image's signed cmdline, since hardware has no UART behind ttyS0;
    # systemd-stub appends this, even under Secure Boot. It lands after the
    # UKI's own console=tty0, and the last console= becomes /dev/console, so
    # tty0 is repeated to keep firstboot and LUKS prompts on the VGA console.
    args += [
        "-smbios",
        "type=11,value=io.systemd.stub.kernel-cmdline-extra=console=ttyS0 console=tty0",
    ]
    for cred in credentials:
        args += ["-smbios", f"type=11,value=io.systemd.credential:{cred}"]
    if share_sock:
        args += [
            "-chardev",
            f"socket,id=vfs0,path={share_sock}",
            "-device",
            f"vhost-user-fs-pci,queue-size=1024,chardev=vfs0,tag={SHARE_TAG}",
        ]
    args += list(extra)
    return args


class Vm:
    """A QEMU guest: headless with serial + monitor on unix sockets, or GUI."""

    def __init__(
        self,
        name,
        drives,
        varstore,
        tpm_state,
        run_dir,
        log,
        memory="4G",
        cpus=4,
        credentials=(),
        echo=False,
        share=None,
        gui=False,
        extra_args=(),
    ):
        self.name = name
        self.log = log
        self.run_dir = run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        self.gui = gui
        self.serial_sock = run_dir / f"{name}-serial.sock"
        self.monitor_sock = run_dir / f"{name}-monitor.sock"
        self.serial_log = run_dir / f"{name}-serial.log"
        # QEMU's own errors, e.g. why it refused to start the machine.
        self.qemu_log = run_dir / f"{name}-qemu.log"
        for p in (self.serial_sock, self.monitor_sock):
            p.unlink(missing_ok=True)

        tpm_sock, self.tpm_pidfile = start_swtpm(tpm_state)
        self.virtiofsd = None
        if share:
            self.virtiofsd = start_virtiofsd(share, run_dir, name)

        args = build_qemu_args(
            drives=drives,
            varstore=varstore,
            tpm_sock=tpm_sock,
            memory=memory,
            cpus=cpus,
            credentials=credentials,
            serial=("file", self.serial_log) if gui else ("socket", self.serial_sock),
            monitor_sock=self.monitor_sock,
            share_sock=self.virtiofsd["sock"] if self.virtiofsd else None,
            gui=gui,
            extra=extra_args,
        )

        how = "in a window" if gui else "headless"
        self.log(f"==> launching {name} {how} (serial log: {self.serial_log})")
        # Held open for QEMU's lifetime; closed in close().
        self._qemu_log_file = self.qemu_log.open("wb")
        self.proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=self._qemu_log_file
        )
        # Order matters when headless: the serial chardev is server=on,wait=on,
        # so QEMU holds the machine reset — and has not yet created the monitor
        # socket — until this client attaches. Connecting the monitor first just
        # times out. A GUI run has no serial client at all (the human drives the
        # window and serial goes to the log file), so the monitor is reachable
        # straight away.
        self.console = (
            None if gui else Console(self.serial_sock, self.serial_log, echo=echo)
        )
        self.shell = None if gui else Shell(self.console, self.log)
        self.monitor = Monitor(self.monitor_sock)

    def screenshot(self, tag="screen"):
        """Capture the VGA console to a PPM (converted to PNG when possible).

        The guest's cmdline ends with `console=tty0`, so /dev/console — and
        therefore systemd's status output, systemd-firstboot's prompts and any
        LUKS passphrase query — lands on the VGA console, not on serial. With no
        display attached, a screendump is the only way to see it, so this is the
        first thing to reach for when a headless boot goes quiet.
        """
        ppm = self.run_dir / f"{self.name}-{tag}.ppm"
        self.monitor.screendump(str(ppm))
        for _ in range(50):
            if ppm.exists() and ppm.stat().st_size:
                break
            time.sleep(0.1)
        if not ppm.exists():
            return None
        png = ppm.with_suffix(".png")
        if shutil.which("magick") or shutil.which("convert"):
            tool = shutil.which("magick") or shutil.which("convert")
            if subprocess.run([tool, str(ppm), str(png)], check=False).returncode == 0:
                ppm.unlink(missing_ok=True)
                return png
        return ppm

    def qemu_errors(self, lines=20):
        """The end of QEMU's stderr."""
        if not self.qemu_log.exists():
            return ""

        return "\n".join(
            self.qemu_log.read_text(errors="replace").splitlines()[-lines:]
        )

    def wait(self, timeout=300):
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._qemu_log_file.close()
        stop_swtpm(self.tpm_pidfile)
        if self.virtiofsd:
            self.virtiofsd["proc"].terminate()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def build_live_cmd(options, output, shared, varstore=None, tpm_sock=None, passt=False):
    """The `mkosi vm` command line for a live/medium run, plus its QEMU extras.

    Split out of run_medium so it can be inspected without starting anything.
    """
    vmm = [
        # The guest-agent socket the old run-image always wired up. qemu-ga is
        # not actually running in the guest, but the socket is harmless and
        # keeps the option available.
        "-chardev",
        "socket,path=/tmp/qemu-guest-agent.sock,server=on,wait=off,id=qga0",
        "-device",
        "virtio-serial",
        "-device",
        "virtserialport,chardev=qga0,name=org.qemu.guest_agent.0",
    ]
    if options.device:
        # A second disk as an ordinary internal drive (no bootindex, so the
        # medium stays the boot device). Which role it plays is a boot-menu
        # choice: "Live System (Recovery)" to mount/repair it, or "Installer"
        # to replicate the image onto it.
        vmm += [
            "-drive",
            f"if=none,id=device,file={options.device},format=raw",
            "-device",
            "virtio-blk-pci,drive=device",
        ]
    if options.gui:
        vmm += [
            "-display",
            "gtk,gl=on,zoom-to-fit=off,grab-on-hover=on",
            "-device",
            "virtio-tablet",
        ]
    if options.yubikey:
        vmm += yubikey_qemu_args()
        # Run the guest's own pcscd for the passed-through key instead of the
        # vsock relay (ansible/roles/qemu-guest/files/pcscd-novm-condition.conf).
        vmm += ["-smbios", "type=11,value=io.systemd.credential:pcscd.local=1"]
    vmm += [
        "-chardev",
        f"socket,id=chrtpm,path={tpm_sock}",
        "-tpmdev",
        "emulator,id=tpm0,chardev=chrtpm",
        "-device",
        "tpm-tis,tpmdev=tpm0",
    ]
    if passt:
        # mkosi defaults to QEMU SLIRP, whose single-threaded userspace TCP
        # stack collapses under parallel HTTPS — pacman's ParallelDownloads=5
        # stalls an in-guest rebuild to ~0 B/s. passt is the modern user-mode
        # replacement: same rootless, WiFi-friendly model (no bridge/tap, so it
        # works over the host's wlan0) but properly multi-threaded.
        # --runtime-network=none stops mkosi adding its own SLIRP nic.
        vmm += ["-netdev", "passt,id=net0", "-device", "virtio-net-pci,netdev=net0"]

    orgs = options.organizations
    cmd = [
        "mkosi",
        "--directory=mkosi",
        f"--output-directory={output}",
        f"--cpus={options.cpus}",
        f"--ram={options.memory}",
        "--vsock=yes",
        "--vsock-cid=3",
        # mkosi's --tpm state is ephemeral, so a TPM2-bound LUKS volume enrolled
        # on one boot can't be unsealed on the next. We run our own swtpm.
        "--tpm=no",
        "--runtime-size=90G",
        f"--runtime-tree={shared}:/run/host/shared",
        # Pre-enrolled varstore: mkosi's finalize_firmware_variables() copies
        # --firmware-variables to a throwaway temp file, so the image's runtime
        # auto-enroll would be discarded on exit and every launch would re-enter
        # setup mode, shifting PCR 7 out from under the TPM2-bound LUKS keyslot.
        "--firmware=uefi-secure-boot",
        f"--firmware-variables={varstore}",
        f"--profile={','.join(['build', *filter(None, orgs.split(','))])}",
        # mkosi would otherwise boot mkosi/mkosi.version, the newest build of
        # any organization set.
        f"--image-version={medium_version(newest_medium(orgs))}",
    ]
    if options.gui:
        cmd.append("--console=gui")
    if options.ephemeral:
        # Boot a throwaway snapshot so the built artifact is not mutated by a
        # self-provisioning first boot.
        cmd.append("--ephemeral=yes")
    cmd += ["vm", "--"] + vmm
    return cmd
