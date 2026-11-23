"""One command to run this project's VMs.

Running a VM here used to mean picking between three scripts (run-image,
boot-disk, vm-test) with three sets of flags, two of which built the same VM two
different ways, and then between two subcommands that differed in more than what
they booted. There are now two subcommands, and what you are booting is an
argument rather than a different program:

  run [DISK]  Boot a VM. With no DISK that is the built medium — the installer /
              live system, which also self-provisions into a normal system on
              first boot. With a DISK it is that installed disk, attached alone.
  install     Boot the medium's Installer profile with TARGET attached as
              /dev/vdb, run `install-system --yes /dev/vdb`, then inspect the
              layout it wrote. Recreates TARGET first: `truncate` on an existing
              same-size file is a no-op, and the stale partitions left behind
              auto-activate and make repart fail with EBUSY.

Each test disk costs 12G+ on the host, so `install` records the disk's
organizations and every `install` or `run DISK` deletes all but the most
recently used installed disk per organization set, along with its varstore and
TPM state. Disks `install` didn't make are never touched.

Booting a disk is headless and scripted by default — health checks, a non-zero
exit if the run misses its checkpoint — so it composes into a validation pass.
Two properties of the image make that possible:

  * OVMF's ConSplitter mirrors the firmware console onto the serial port, so
    sd-boot's menu is readable on serial and QEMU's HMP `sendkey` can move the
    selection — no display, no keyboard, no VT switching;
  * QEMU adds `console=ttyS0` to every UKI profile's cmdline (an SMBIOS
    kernel-cmdline-extra; the signed cmdline leaves it out, as hardware has no
    UART there) and passes an agetty autologin credential, so a root shell
    lands on the serial socket and commands and their output round-trip over
    it. (`console=tty0` still comes last, so /dev/console — and thus systemd's
    own boot output and any password prompt — still goes to the invisible VGA
    console. Read those back with `journalctl` over serial, or reach for the
    screendump this takes when a headless boot goes quiet.)

`--gui` opens a window instead and hands the VM over, for when you are sitting
at it. Without a keyboard grab Ctrl+Alt+F<n> lands on the HOST compositor, so
`grab-on-hover=on` is set; Ctrl+Alt+G toggles the grab by hand.

Under the hood the medium still boots through `mkosi vm` (which supplies the
vsock YubiKey relay, the /run/host/shared runtime tree and the 90G growth) while
a named disk is driven directly, because `mkosi vm` can only boot the output its
own config names. Firmware varstore and TPM state persist either way — per-disk
for a named disk — so Secure Boot PCR 7 and a TPM2-sealed LUKS keyslot stay
stable across runs, like real hardware.
"""

import argparse
import functools
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from arch_ansible_vm.disks import (
    medium_organizations,
    newest_medium,
    output_dir,
    selected_organizations,
    use_disk,
)
from arch_ansible_vm.qemu import (
    FIRSTBOOT_HOSTNAME,
    FIRSTBOOT_ROOT_PASSWORD,
    REPO,
    SHARE_MNT,
    SHARE_TAG,
    Drive,
    LiveOptions,
    Vm,
    build_live_cmd,
    make_varstore,
    mkosi_env,
    secureboot_cert,
    start_swtpm,
    stop_swtpm,
    yubikey_qemu_args,
)
from arch_ansible_vm.sdboot import select_boot_entry

# --- subcommands -------------------------------------------------------------


def wait_for_shell(vm, timeout, log):
    """Wait for the serial root shell, capturing the VGA console if it never comes.

    A boot that stalls on tty0 — a LUKS passphrase query, systemd-firstboot's
    prompt, an emergency shell — looks identical on serial to one that is simply
    slow: silence. The screendump is what tells the two apart.
    """
    interval = 60
    waited = 0
    while True:
        try:
            vm.shell.wait_ready(timeout=min(interval, timeout - waited))
            return
        except TimeoutError:
            waited += interval
            if waited >= timeout:
                shot = vm.screenshot("stalled")
                log(f"==> no root shell after {timeout}s; VGA console: {shot}")
                raise TimeoutError(
                    f"no root shell on serial after {timeout}s. The boot is "
                    f"stalled on something only /dev/console (tty0) shows — see "
                    f"the screendump at {shot}."
                )
            shot = vm.screenshot(f"waiting-{waited}s")
            log(f"==> still waiting ({waited}s); VGA console: {shot}")
        except EOFError:
            shot = vm.screenshot("died")
            log(f"==> guest exited; VGA console: {shot}")
            raise


def write_line(stream, msg):
    stream.write(str(msg).rstrip("\n") + "\n")
    stream.flush()


def run_medium(args, log):
    """`vm run` with no disk: boot the built medium through `mkosi vm`."""
    output = output_dir()
    output.mkdir(parents=True, exist_ok=True)
    # mkosi maps the host user to root in the guest, so the runtime-tree share
    # is only writable by root there. World-writable on the host lets the
    # unprivileged guest user write back through virtiofs too.
    shared = REPO / ".qemu-host-shared"
    shared.mkdir(parents=True, exist_ok=True)
    shared.chmod(0o777)

    varstore = make_varstore(output / "ovmf_vars.fd", secureboot_cert(recover=True))
    tpm_sock, pidfile = start_swtpm(
        Path(args.tpm_state) if args.tpm_state else output / "tpm"
    )
    options = LiveOptions(
        cpus=args.cpus,
        memory=args.memory,
        organizations=selected_organizations(args.organization),
        device=args.device,
        gui=args.gui,
        yubikey=args.yubikey,
        ephemeral=args.ephemeral,
    )
    cmd = build_live_cmd(
        options, output, shared, varstore, tpm_sock, passt=bool(shutil.which("passt"))
    )
    if args.device:
        log(
            f"==> Attached {args.device} as /dev/vdb. At the boot menu, pick "
            "'Live System (Recovery)' to repair it, or 'Installer' to install onto it."
        )
    try:
        return subprocess.run(cmd, cwd=REPO, env=mkosi_env(), check=False).returncode
    finally:
        stop_swtpm(pidfile)


def validate_run_flags(args):
    """Reject `vm run` flags that don't apply to what's being booted."""
    medium_only = {
        "--device": args.device,
        "--ephemeral": args.ephemeral,
        "--organization": args.organization,
    }
    disk_only = {"--run": args.run, "--share": args.share, "--entry": args.entry}
    if args.disk:
        for flag, val in medium_only.items():
            if val:
                sys.exit(
                    f"error: {flag} applies to the medium; drop the DISK "
                    "argument to boot it"
                )
    else:
        for flag, val in disk_only.items():
            if val:
                sys.exit(
                    f"error: {flag} needs an installed DISK to act on "
                    "(`vm run DISK ...`)"
                )

    if args.gui:
        for flag in ("entry", "run"):
            if getattr(args, flag):
                sys.exit(
                    f"error: --{flag} drives the guest over serial and can't "
                    "be combined with --gui"
                )


def cmd_run(args):
    """One entry point: no disk boots the medium, a disk boots that disk alone."""
    log = functools.partial(write_line, sys.stdout)
    if args.disk:
        return run_disk(args, log)

    return run_medium(args, log)


def cmd_install(args):
    log = functools.partial(write_line, sys.stdout)
    medium = (
        Path(args.medium)
        if args.medium
        else newest_medium(selected_organizations(args.organization))
    )
    target = Path(args.target).resolve()

    if args.fresh:
        # `truncate -s N` on an existing N-byte file is a no-op: it sets the
        # size and leaves every byte alone. The stale GPT then auto-activates
        # when the medium boots and repart fails with "Device or resource busy".
        # Removing the file first is the only way to get a genuinely blank disk.
        log(f"==> recreating {target} ({args.size}) from scratch")
        target.unlink(missing_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["truncate", "-s", args.size, str(target)], check=True)
    elif not target.is_file():
        sys.exit(f"error: {target} does not exist (drop --no-fresh to create it)")
    use_disk(target, log, time.time(), orgs=medium_organizations(medium))

    cert = secureboot_cert()
    run_dir = output_dir() / "vm"
    varstore = make_varstore(run_dir / "installer-vars.fd", cert)

    log(f"==> medium: {medium.name}")
    with Vm(
        name="installer",
        drives=[
            # snapshot=on: the installer only reads the medium (root=tmpfs), and
            # discarding writes keeps the built artifact byte-identical.
            Drive(file=medium, bootindex=0, snapshot=True),
            Drive(file=target),
        ],
        varstore=varstore,
        tpm_state=run_dir / "installer-tpm",
        run_dir=run_dir,
        log=log,
        memory=args.memory,
        cpus=args.cpus,
        echo=args.verbose,
    ) as vm:
        select_boot_entry(vm, "Installer")

        log("==> waiting for a root shell on ttyS0 …")
        wait_for_shell(vm, args.boot_timeout, log)
        sh = vm.shell

        # The greetd fix (systemd.unit=multi-user.target in the Installer
        # profile) is exactly this pair of facts: the guided installer is up on
        # tty1 and the graphical login never started.
        log("\n===== Installer environment =====")
        sh.run("systemctl is-system-running || true")
        sh.run("systemctl is-active arch-install.service || true")
        sh.run("systemctl is-active greetd.service || true")
        sh.run("systemctl get-default")
        sh.run("systemctl --failed --no-legend --plain || true")
        # The failed units name what broke but rarely why.
        sh.run(
            "for u in $(systemctl --failed --no-legend --plain | awk '{print $1}'); "
            'do echo "--- $u"; journalctl -b --no-pager -o cat -u "$u" | tail -15; done'
        )

        # Stop the guided installer before driving the one-shot path, so the two
        # can't race for the target. An explicit stop wins over Restart=always.
        sh.run("systemctl stop arch-install.service || true")

        log("\n===== install-system --yes /dev/vdb =====")
        rc, _ = sh.run(
            "/usr/bin/install-system --yes /dev/vdb 2>&1",
            timeout=args.install_timeout,
        )
        if rc != 0:
            log("==> INSTALL FAILED")
            sh.run("journalctl -b --no-pager -p warning | tail -60 || true")
            return 1

        # Validation question #1: a pure Type #2 layout — sd-boot plus a bare UKI
        # in EFI/Linux/, no /image/ dir and no loader/entries/*.conf.
        log("\n===== Written layout (validation question #1) =====")
        sh.run("udevadm settle; lsblk -o NAME,SIZE,TYPE,PARTLABEL,FSTYPE /dev/vdb")
        sh.run("mkdir -p /mnt/esp && mount /dev/vdb1 /mnt/esp")
        sh.run("find /mnt/esp -maxdepth 3 | sort")
        sh.run("ls -A /mnt/esp/loader/entries 2>/dev/null | wc -l")
        sh.run("ls -A /mnt/esp/image 2>/dev/null | wc -l")
        sh.run("umount /mnt/esp")

        log("\n==> powering off")
        sh.c.send("systemctl poweroff\n")
        vm.wait(timeout=120)

    log(f"\n==> CHECKPOINT A reached: {target} installed.")
    log(f"    Next: bin/vm run {target}")
    return 0


HEALTH_CHECKS = [
    "systemctl is-system-running",
    "systemctl --failed --no-legend --plain",
    "hostnamectl",
    # One target per call: findmnt prints nothing for a multi-target invocation.
    "findmnt -no SOURCE,FSTYPE /",
    "findmnt -no SOURCE,FSTYPE /usr",
    "lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS",
    "bootctl status 2>&1 | head -30",
    "systemd-analyze blame 2>/dev/null | head -10",
]


def run_disk(args, log):
    """`vm run DISK`: boot an installed disk alone, headless or in a window."""
    disk = Path(args.disk).resolve()
    if not disk.is_file():
        sys.exit(f"error: {disk} is not a file")
    use_disk(disk, log, time.time())

    cert = secureboot_cert()
    run_dir = output_dir() / "vm"
    # Varstore and TPM live next to the disk (as bin/boot-disk did), so the
    # LUKS keyslot sealed on first boot can be unsealed on every later boot.
    varstore = make_varstore(Path(f"{disk}.ovmf_vars.fd"), cert)

    # Answers for everything the installed system's first boot asks the user, all
    # delivered as SMBIOS type 11 credentials. This matters more than it looks:
    # systemd-firstboot prompts on /dev/console, which the image pins to tty0
    # (`console=tty0` comes last on the cmdline), so a headless boot that hits a
    # prompt just goes silent forever with nothing on serial to say why.
    creds = [
        # Testing convenience only: a root shell on every getty, so the system's
        # health can be read back over serial without a password and without
        # switching VTs. Never use this for a real install.
        "agetty.autologin=root",
        # First prompt: systemd-firstboot --prompt-hostname (added by
        # mkosi/mkosi.extra/…/systemd-firstboot.service.d/10-prompt-hostname.conf).
        f"firstboot.hostname={FIRSTBOOT_HOSTNAME}",
        # Second prompt: --prompt-root-password, from the same ExecStart. Test
        # credential only — a real install is meant to be answered by the human
        # sitting at the console.
        f"passwd.plaintext-password.root={FIRSTBOOT_ROOT_PASSWORD}",
    ]
    if args.yubikey:
        # Run the guest's own pcscd for the passed-through key instead of the
        # vsock relay (ansible/roles/qemu-guest/files/pcscd-novm-condition.conf).
        creds.append("pcscd.local=1")

    with Vm(
        name=disk.stem,
        drives=[Drive(file=disk, bootindex=0)],
        varstore=varstore,
        tpm_state=Path(args.tpm_state) if args.tpm_state else Path(f"{disk}.tpm"),
        run_dir=run_dir,
        log=log,
        memory=args.memory,
        cpus=args.cpus,
        credentials=creds,
        echo=args.verbose,
        share=args.share,
        gui=args.gui,
        extra_args=yubikey_qemu_args() if args.yubikey else (),
    ) as vm:
        if args.gui:
            # Nothing is scripted here: the window is the interface. Wait for
            # the user to shut the guest down (or close the window).
            log(
                "==> GUI run: pick the entry yourself; close the window or run "
                "`systemctl poweroff` in the guest when done."
            )
            vm.proc.wait()
            return 0

        if args.entry:
            select_boot_entry(vm, args.entry)

        log("==> waiting for a root shell on ttyS0 …")
        # First boot does the whole provisioning run (repart creates root/home/
        # swap, TPM2-seals LUKS, homed/firstboot units), so allow plenty.
        wait_for_shell(vm, args.boot_timeout, log)
        sh = vm.shell

        log("\n===== Health checks (validation question #2) =====")
        state = None
        for check in HEALTH_CHECKS:
            _rc, out = sh.run(check + " || true", timeout=120)
            if check.startswith("systemctl is-system-running"):
                state = out.strip().splitlines()[-1] if out.strip() else "?"

        # Did anything ask for a passphrase? First boot seals to the TPM, later
        # boots must unseal silently; a pending ask-password request (or a
        # cryptsetup unit that fell back to a prompt) is the failure signal, and
        # it would otherwise be invisible on tty0.
        log("\n===== LUKS / TPM =====")
        sh.run("systemd-tty-ask-password-agent --list 2>&1 | head || true")
        sh.run(
            "journalctl -b --no-pager -o cat -u systemd-cryptsetup@root.service "
            "2>&1 | tail -10 || true"
        )
        sh.run(
            "cryptsetup luksDump /dev/disk/by-designator/root-luks 2>/dev/null "
            "| grep -i -A2 'tokens\\|systemd-tpm2' | head -20 || true"
        )
        sh.run("systemd-cryptenroll /dev/disk/by-designator/root-luks || true")
        # How each TPM2 slot is bound: born literal PCR 7 + initrd-only signed
        # PCR 11 (tpm2_pubkey_ref), then moved onto the pcrlock policy by
        # pcrlock-enroll-luks.service.
        sh.run(
            "systemctl is-active systemd-pcrlock-make-policy.service "
            "pcrlock-enroll-luks.service || true"
        )
        sh.run(
            "for d in root-luks swap-luks home-luks; do printf '%s: ' $d; "
            "cryptsetup luksDump --dump-json-metadata /dev/disk/by-designator/$d "
            "| python3 -c 'import json,sys; print([{k: t.get(k) for k in "
            '("keyslots", "tpm2-pcrs", "tpm2_pubkey_pcrs", "tpm2_pubkey_ref", '
            '"tpm2_pcrlock")} '
            'for t in json.load(sys.stdin)["tokens"].values() '
            'if t["type"] == "systemd-tpm2"])\'; done || true'
        )

        if args.share:
            sh.run(
                f"mkdir -p {SHARE_MNT} && mount -t virtiofs {SHARE_TAG} "
                f"{SHARE_MNT} && ls {SHARE_MNT} | head -5",
                check=True,
            )

        if args.run:
            log("\n===== --run =====")
            for cmd in args.run:
                sh.run(cmd, timeout=args.run_timeout)

        if state != "running":
            # Only on a bad run: the failed units alone rarely say why, and this
            # is the one chance to read the journal before the guest is gone.
            log("\n===== Journal (warnings and worse) =====")
            sh.run("journalctl -b --no-pager -p warning | tail -80 || true")

        log("\n==> powering off")
        sh.c.send("systemctl poweroff\n")
        vm.wait(timeout=180)

    log(f"\n==> is-system-running = {state}")
    if state == "running":
        log("==> CHECKPOINT B: clean boot.")
        return 0
    log("==> NOT a clean boot — see the failed units above.")
    return 1


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="vm",
        description="Run this project's VMs: `run` boots one, `install` makes one.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # On the subcommands, not the top level: `vm run DISK --cpus 4` is what
    # anyone types, and a top-level-only option silently fails there.
    nproc = os.cpu_count() or 4
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--memory", default="8G", help="guest RAM (default 8G)")
    common.add_argument(
        "--cpus",
        type=int,
        default=nproc - 2 if nproc > 4 else nproc,
        help="vCPUs (default: host CPUs minus 2, leaving the host "
        "room; in-guest rebuilds scale with this)",
    )
    common.add_argument(
        "--organization",
        action="append",
        metavar="NAME",
        help="use the newest medium built with exactly these "
        "organizations (repeatable; default "
        "$ARCH_ANSIBLE_ORGANIZATIONS, else none)",
    )
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="mirror the raw serial stream to stdout as it arrives",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser(
        "run", parents=[common], help="boot the medium, or an installed disk"
    )
    r.add_argument(
        "disk",
        nargs="?",
        help="installed disk to boot. Omit it to boot the built medium instead.",
    )
    r.add_argument(
        "--gui",
        action="store_true",
        help="open a window and hand the VM over, instead of running "
        "headless with scripted health checks",
    )
    r.add_argument(
        "--device",
        metavar="DISK",
        help="medium only: attach DISK as a second disk (/dev/vdb) to "
        "install onto or repair",
    )
    r.add_argument(
        "--ephemeral",
        action="store_true",
        help="medium only: boot a throwaway snapshot, leaving the "
        "built image untouched",
    )
    r.add_argument(
        "--entry",
        metavar="VERSION",
        help="disk only: sd-boot entry to select (default: the default entry)",
    )
    r.add_argument(
        "--yubikey",
        action="store_true",
        help="pass the host's YubiKey through to the guest over USB "
        "(PIV/PKCS#11 and FIDO2), e.g. to test LUKS unlock with "
        "it. The host can't use it while the VM runs",
    )
    r.add_argument(
        "--run",
        action="append",
        metavar="CMD",
        help="disk only: run CMD in the booted system after the health "
        "checks (repeatable). Root's /etc is writable, so changes "
        "made here persist into the disk's next boot.",
    )
    r.add_argument(
        "--share",
        metavar="DIR",
        help=f"disk only: export DIR to the guest over virtiofs at "
        f"{SHARE_MNT}, to hand it build artifacts (e.g. for an "
        f"A/B update)",
    )
    r.add_argument(
        "--tpm-state",
        metavar="DIR",
        help="persistent swtpm state dir. Defaults to DISK.tpm for a "
        "disk and <output>/tpm for the medium, so each VM gets "
        "its own TPM — which means a medium booted to recover a "
        "target CANNOT unseal that target's TPM2-bound LUKS "
        "root. Point both at one dir to share a TPM, the way "
        "install and first boot share one on real hardware.",
    )
    r.add_argument("--boot-timeout", type=int, default=900)
    r.add_argument(
        "--run-timeout",
        type=int,
        default=1800,
        help="per---run-command timeout (default 1800s; an A/B update copies ~10G)",
    )
    r.set_defaults(func=cmd_run)

    i = sub.add_parser(
        "install", parents=[common], help="install the built medium onto TARGET"
    )
    i.add_argument("target", help="target disk image (recreated unless --no-fresh)")
    i.add_argument(
        "--medium",
        help="medium to boot (default: newest image built for --organization)",
    )
    i.add_argument(
        "--size",
        default="100G",
        help="target size when created (default 100G: the fixed\n"
        "partitions total ~49G, so a 60G disk leaves too little\n"
        "root for the on-device build scratch)",
    )
    i.add_argument(
        "--no-fresh",
        dest="fresh",
        action="store_false",
        help="reuse the existing target file instead of recreating it",
    )
    i.add_argument("--boot-timeout", type=int, default=600)
    i.add_argument("--install-timeout", type=int, default=1800)
    i.set_defaults(func=cmd_install)

    args = p.parse_args(argv)
    if args.cmd == "run":
        validate_run_flags(args)

    os.chdir(REPO)
    needed = ["swtpm", "virt-fw-vars"]
    # Booting the medium goes through mkosi; everything else execs QEMU itself.
    booting_medium = args.cmd == "run" and not args.disk
    needed.append("mkosi" if booting_medium else "qemu-system-x86_64")
    for tool in needed:
        if not shutil.which(tool):
            sys.exit(f"error: {tool} not found in PATH")
    try:
        return args.func(args)
    except (TimeoutError, EOFError, RuntimeError) as e:
        print(f"\nerror: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
