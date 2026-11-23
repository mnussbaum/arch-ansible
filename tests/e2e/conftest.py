"""Boots the built medium and an installed disk once per session, recording
what each boot found. The tests assert on these records, so a failure names
the fact that was wrong while the VMs' serial logs and screendumps sit in the
VM run directory for the details.

The medium is $ARCH_ANSIBLE_CI_MEDIUM, else the newest one built for
$ARCH_ANSIBLE_ORGANIZATIONS.
"""

import functools
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from arch_ansible_vm.checks import (
    EspLayout,
    Partition,
    SystemState,
    Tpm2Binding,
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
from arch_ansible_vm.disks import newest_medium, output_dir, selected_organizations
from arch_ansible_vm.sessions import (
    boot_to_shell,
    default_cpus,
    disk_vm,
    installer_vm,
    power_off,
    recreate_disk,
)

MEMORY = "8G"
TARGET_SIZE = "100G"
INSTALLER_BOOT_TIMEOUT = 600
INSTALL_TIMEOUT = 1800
# First boot provisions the whole disk: repart, LUKS, homed.
DISK_BOOT_TIMEOUT = 900


@dataclass(frozen=True, kw_only=True)
class InstallerFacts:
    system: SystemState
    installer_unit: str
    greetd: str
    install_rc: int
    install_output: str
    # Read only after a successful install.
    esp: EspLayout | None
    partitions: tuple[Partition, ...]


@dataclass(frozen=True, kw_only=True)
class BootFacts:
    system: SystemState
    graphical_target: str
    greetd: str
    password_prompts: tuple[str, ...]
    # Exit code of each of NETWORK_CHECKS.
    network: dict[str, int]
    root_bindings: tuple[Tpm2Binding, ...]
    swap_bindings: tuple[Tpm2Binding, ...]
    failed_unit_journals: str


def write_log_line(stream, msg):
    stream.write(str(msg).rstrip("\n") + "\n")
    stream.flush()


def collect_boot_facts(vm):
    sh = vm.shell
    system = system_state(sh)
    facts = BootFacts(
        system=system,
        graphical_target=unit_state(sh, "graphical.target"),
        greetd=unit_state(sh, "greetd.service"),
        password_prompts=pending_password_prompts(sh),
        network=network_checks(sh),
        root_bindings=tpm2_bindings(sh, "root-luks"),
        swap_bindings=tpm2_bindings(sh, "swap-luks"),
        failed_unit_journals=failed_unit_journals(sh) if system.failed_units else "",
    )
    power_off(vm)

    return facts


@pytest.fixture(scope="session")
def log():
    run_dir = output_dir() / "vm"
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "e2e.log").open("a") as stream:
        yield functools.partial(write_log_line, stream)


@pytest.fixture(scope="session")
def medium():
    if path := os.environ.get("ARCH_ANSIBLE_CI_MEDIUM"):
        return Path(path)

    return newest_medium(selected_organizations(None))


@pytest.fixture(scope="session")
def target():
    """A blank disk to install onto, with no firmware or TPM state left from
    an earlier run."""
    path = output_dir() / "vm" / "e2e-target.raw"
    recreate_disk(path, TARGET_SIZE)
    Path(f"{path}.ovmf_vars.fd").unlink(missing_ok=True)
    shutil.rmtree(f"{path}.tpm", ignore_errors=True)

    return path


@pytest.fixture(scope="session")
def installer(medium, target, log):
    log(f"==> installing {medium.name} onto {target}")
    with installer_vm(medium, target, log, MEMORY, default_cpus()) as vm:
        boot_to_shell(vm, INSTALLER_BOOT_TIMEOUT, log, entry="Installer")
        sh = vm.shell
        system = system_state(sh)
        installer_unit = unit_state(sh, "arch-install.service")
        greetd = unit_state(sh, "greetd.service")
        rc, out = install_system(sh, "/dev/vdb", INSTALL_TIMEOUT)
        installed = rc == 0
        facts = InstallerFacts(
            system=system,
            installer_unit=installer_unit,
            greetd=greetd,
            install_rc=rc,
            install_output=out,
            esp=esp_layout(sh, "/dev/vdb1") if installed else None,
            partitions=partition_table(sh, "/dev/vdb") if installed else (),
        )
        power_off(vm, timeout=120)

    return facts


@pytest.fixture(scope="session")
def first_boot(installer, target, log):
    if installer.install_rc != 0:
        pytest.fail(f"nothing to boot, the install failed:\n{installer.install_output}")

    log(f"==> first boot of {target}")
    with disk_vm(target, log, MEMORY, default_cpus()) as vm:
        boot_to_shell(vm, DISK_BOOT_TIMEOUT, log)

        return collect_boot_facts(vm)


@pytest.fixture(scope="session")
def second_boot(first_boot, target, log):
    log(f"==> second boot of {target}")
    with disk_vm(target, log, MEMORY, default_cpus()) as vm:
        boot_to_shell(vm, DISK_BOOT_TIMEOUT, log)

        return collect_boot_facts(vm)
