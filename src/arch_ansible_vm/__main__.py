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

from arch_ansible_vm.checks import (
    esp_layout,
    failed_unit_journals,
    install_system,
    network_checks,
    partition_table,
    pending_password_prompts,
    system_state,
    tpm2_bindings,
    unit_state,
)
from arch_ansible_vm.disks import (
    medium_organizations,
    newest_medium,
    output_dir,
    selected_organizations,
    use_disk,
)
from arch_ansible_vm.qemu import (
    REPO,
    SHARE_MNT,
    SHARE_TAG,
    LiveOptions,
    build_live_cmd,
    make_varstore,
    mkosi_env,
    secureboot_cert,
    start_swtpm,
    stop_swtpm,
)
from arch_ansible_vm.sessions import (
    boot_to_shell,
    default_cpus,
    disk_vm,
    installer_vm,
    power_off,
    recreate_disk,
)

# --- subcommands -------------------------------------------------------------


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
        log(f"==> recreating {target} ({args.size}) from scratch")
        recreate_disk(target, args.size)
    elif not target.is_file():
        sys.exit(f"error: {target} does not exist (drop --no-fresh to create it)")
    use_disk(target, log, time.time(), orgs=medium_organizations(medium))

    log(f"==> medium: {medium.name}")
    with installer_vm(
        medium, target, log, args.memory, args.cpus, echo=args.verbose
    ) as vm:
        boot_to_shell(vm, args.boot_timeout, log, entry="Installer")
        sh = vm.shell

        # The guided installer is up on tty1 and the graphical login never
        # started (systemd.unit=multi-user.target in the Installer profile).
        log("\n===== Installer environment =====")
        state = system_state(sh)
        log(f"{state}")
        log(f"arch-install.service: {unit_state(sh, 'arch-install.service')}")
        log(f"greetd.service: {unit_state(sh, 'greetd.service')}")
        if state.failed_units:
            log(failed_unit_journals(sh))

        log("\n===== install-system --yes /dev/vdb =====")
        rc, _ = install_system(sh, "/dev/vdb", args.install_timeout)
        if rc != 0:
            log("==> INSTALL FAILED")
            sh.run("journalctl -b --no-pager -p warning | tail -60")
            return 1

        # A pure Type #2 layout: sd-boot plus a bare UKI in EFI/Linux/, no
        # /image/ dir and no loader/entries/*.conf.
        log("\n===== Written layout =====")
        for partition in partition_table(sh, "/dev/vdb"):
            log(f"{partition}")
        log(f"{esp_layout(sh, '/dev/vdb1')}")

        power_off(vm, timeout=120)

    log(f"\n==> CHECKPOINT A reached: {target} installed.")
    log(f"    Next: bin/vm run {target}")
    return 0


HEALTH_CHECKS = [
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

    with disk_vm(
        disk,
        log,
        args.memory,
        args.cpus,
        echo=args.verbose,
        share=args.share,
        gui=args.gui,
        yubikey=args.yubikey,
        tpm_state=args.tpm_state,
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

        # First boot does the whole provisioning run (repart creates root/home/
        # swap, TPM2-seals LUKS, homed/firstboot units), so allow plenty.
        boot_to_shell(vm, args.boot_timeout, log, entry=args.entry)
        sh = vm.shell

        log("\n===== Health checks =====")
        state = system_state(sh)
        log(f"{state}")
        for check in HEALTH_CHECKS:
            sh.run(check, timeout=120)
        log(f"network checks (exit codes): {network_checks(sh)}")

        # First boot seals to the TPM and later boots must unseal silently; a
        # pending ask-password request is the failure signal, and it would
        # otherwise be invisible on tty0.
        log("\n===== LUKS / TPM =====")
        log(f"pending password prompts: {pending_password_prompts(sh)}")
        sh.run(
            "journalctl -b --no-pager -o cat -u systemd-cryptsetup@root.service "
            "| tail -10"
        )
        # Born literal PCR 7 + initrd-only signed PCR 11, then moved onto the
        # pcrlock policy by pcrlock-enroll-luks.service.
        for unit in (
            "systemd-pcrlock-make-policy.service",
            "pcrlock-enroll-luks.service",
        ):
            log(f"{unit}: {unit_state(sh, unit)}")
        for designator in ("root-luks", "swap-luks"):
            log(f"{designator}: {tpm2_bindings(sh, designator)}")

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

        if state.state != "running":
            # Only on a bad run: the failed units alone rarely say why, and this
            # is the one chance to read the journal before the guest is gone.
            log("\n===== Failed units =====")
            log(failed_unit_journals(sh))
            log("\n===== Journal (warnings and worse) =====")
            sh.run("journalctl -b --no-pager -p warning | tail -80")

        power_off(vm)

    log(f"\n==> is-system-running = {state.state}")
    if state.state == "running":
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
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--memory", default="8G", help="guest RAM (default 8G)")
    common.add_argument(
        "--cpus",
        type=int,
        default=default_cpus(),
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
