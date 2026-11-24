"""Booting the installer and installed disks, shared by bin/vm and the
end-to-end tests."""

import os
import subprocess
from pathlib import Path

from arch_ansible_vm.disks import output_dir
from arch_ansible_vm.qemu import (
    FIRSTBOOT_HOSTNAME,
    FIRSTBOOT_ROOT_PASSWORD,
    Drive,
    Vm,
    make_varstore,
    secureboot_cert,
    yubikey_qemu_args,
)
from arch_ansible_vm.sdboot import select_boot_entry


def default_cpus():
    """Host CPUs minus 2, leaving the host room, on hosts with more than 4."""
    nproc = os.cpu_count() or 4

    return nproc - 2 if nproc > 4 else nproc


def recreate_disk(target, size):
    """Make `target` a blank sparse disk of `size`.

    `truncate -s N` on an existing N-byte file is a no-op: it sets the size and
    leaves every byte alone. The stale GPT then auto-activates when the medium
    boots and repart fails with "Device or resource busy". Removing the file
    first is the only way to get a genuinely blank disk.
    """
    target = Path(target)
    target.unlink(missing_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["truncate", "-s", size, str(target)], check=True)


def installer_vm(medium, target, log, memory, cpus, echo=False):
    """The medium with `target` attached as /dev/vdb, for its Installer profile."""
    run_dir = output_dir() / "vm"
    varstore = make_varstore(run_dir / "installer-vars.fd", secureboot_cert())

    return Vm(
        name="installer",
        drives=[
            # snapshot=on: the installer only reads the medium (root=tmpfs), and
            # discarding writes keeps the built artifact byte-identical.
            Drive(file=Path(medium), bootindex=0, snapshot=True),
            Drive(file=Path(target)),
        ],
        varstore=varstore,
        tpm_state=run_dir / "installer-tpm",
        run_dir=run_dir,
        log=log,
        memory=memory,
        cpus=cpus,
        echo=echo,
    )


def firstboot_credentials(yubikey=False):
    """Answers for everything an installed system's first boot asks, as SMBIOS
    type 11 credentials.

    This matters more than it looks: systemd-firstboot prompts on
    /dev/console, which the image pins to tty0 (`console=tty0` comes last on
    the cmdline), so a headless boot that hits a prompt just goes silent
    forever with nothing on serial to say why.
    """
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
    if yubikey:
        # Run the guest's own pcscd for the passed-through key instead of the
        # vsock relay (ansible/roles/qemu-guest/files/pcscd-novm-condition.conf).
        creds.append("pcscd.local=1")

    return creds


def disk_vm(
    disk,
    log,
    memory,
    cpus,
    echo=False,
    share=None,
    gui=False,
    yubikey=False,
    tpm_state=None,
):
    """An installed disk booted alone.

    Its varstore and TPM state live next to it, so the LUKS keyslots sealed on
    first boot unseal on every later boot, as on real hardware.
    """
    disk = Path(disk)
    varstore = make_varstore(Path(f"{disk}.ovmf_vars.fd"), secureboot_cert())

    return Vm(
        name=disk.stem,
        drives=[Drive(file=disk, bootindex=0)],
        varstore=varstore,
        tpm_state=Path(tpm_state) if tpm_state else Path(f"{disk}.tpm"),
        run_dir=output_dir() / "vm",
        log=log,
        memory=memory,
        cpus=cpus,
        credentials=firstboot_credentials(yubikey),
        echo=echo,
        share=share,
        gui=gui,
        extra_args=yubikey_qemu_args() if yubikey else (),
    )


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
                ) from None
            shot = vm.screenshot(f"waiting-{waited}s")
            log(f"==> still waiting ({waited}s); VGA console: {shot}")
        except EOFError:
            shot = vm.screenshot("died")
            log(f"==> guest exited; VGA console: {shot}")
            raise


def boot_to_shell(vm, timeout, log, entry=None):
    """Pick `entry` in the boot menu if given, then wait for the root shell.

    If QEMU exits instead, raises with its errors rather than the broken
    socket that reveals it.
    """
    try:
        if entry:
            select_boot_entry(vm, entry)

        log("==> waiting for a root shell on ttyS0 …")
        wait_for_shell(vm, timeout, log)
    except (BrokenPipeError, ConnectionResetError, EOFError) as e:
        rc = vm.wait(timeout=5)
        if rc is None:
            raise

        raise RuntimeError(f"QEMU exited with {rc}:\n{vm.qemu_errors()}") from e


def power_off(vm, timeout=180):
    vm.log("\n==> powering off")
    vm.shell.c.send("systemctl poweroff\n")
    vm.wait(timeout=timeout)
