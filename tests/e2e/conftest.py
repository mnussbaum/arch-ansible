"""Boots the built medium and an installed disk once per session, recording
what each boot found. The tests assert on these records, so a failure names
the fact that was wrong while the VMs' serial logs and screendumps sit in the
VM run directory for the details.

The medium is $ARCH_ANSIBLE_CI_MEDIUM, else the newest one built for
$ARCH_ANSIBLE_ORGANIZATIONS. The session stage logs in with the identity it
was built with (bin/ci identity), at $ARCH_ANSIBLE_CI_IDENTITY, and needs a
medium built with --test-token.
"""

import functools
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from arch_ansible_ci.identity import Manifest, export_gpg_secret_key, load_identity
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
from arch_ansible_vm.desktop import (
    FIREFOX,
    GHOSTTY,
    Home,
    Session,
    Window,
    home_facts,
    home_user,
    log_in,
    log_out,
    login_diagnostics,
    open_local_page,
    restart_greeter,
    seed_software_token,
    sway_socket,
    user_uid,
    wait_for_play_recap,
    wait_for_windows,
    write_guest_file,
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
FIRST_LOGIN_TIMEOUT = 1800
# The software token's, standing in for the YubiKey's PIV PINs.
TOKEN_PIN = "123456"
TOKEN_SO_PIN = "12345678"
NVIM_DIR = "/var/tmp/ci-nvim"


@dataclass(frozen=True, kw_only=True)
class InstallerFacts:
    system: SystemState
    multi_user_target: str
    graphical_target: str
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


@dataclass(frozen=True, kw_only=True)
class NvimFacts:
    errmsg: str
    messages: str
    plugins: tuple[str, ...]
    inactive_plugins: tuple[str, ...]
    # Language server names attached to each sample file, by its kind.
    lsp_clients: dict[str, tuple[str, ...]]
    fixed_script: str


@dataclass(frozen=True, kw_only=True)
class SessionFacts:
    login: Session | None
    # The first-login playbook's PLAY RECAP counts, None if it never finished.
    first_login_recap: dict[str, int] | None
    home: Home
    canary: str
    windows: tuple[Window, ...]
    firefox_title: str
    user_failed_units: tuple[str, ...]
    nvim: NvimFacts


@dataclass(frozen=True, kw_only=True)
class ReloginFacts:
    with_home_password: Session | None
    with_token_pin: Session | None


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
        multi_user_target = unit_state(sh, "multi-user.target")
        graphical_target = unit_state(sh, "graphical.target")
        installer_unit = unit_state(sh, "arch-install.service")
        greetd = unit_state(sh, "greetd.service")
        rc, out = install_system(sh, "/dev/vdb", INSTALL_TIMEOUT)
        installed = rc == 0
        facts = InstallerFacts(
            system=system,
            multi_user_target=multi_user_target,
            graphical_target=graphical_target,
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


@pytest.fixture(scope="session")
def identity():
    path = os.environ.get("ARCH_ANSIBLE_CI_IDENTITY")
    if not path:
        pytest.fail(
            "set ARCH_ANSIBLE_CI_IDENTITY to the identity the medium was built with"
        )

    return Path(path)


@pytest.fixture(scope="session")
def manifest(identity) -> Manifest:
    return load_identity(identity)


def read_pass_canary(vm, user, identity):
    sh = vm.shell
    write_guest_file(sh, "/var/tmp/ci-gpg-key.asc", export_gpg_secret_key(identity))
    sh.run(f"chown {user} /var/tmp/ci-gpg-key.asc", check=True)
    sh.run(
        f"runuser -u {user} -- gpg --batch --import /var/tmp/ci-gpg-key.asc", check=True
    )
    sh.run("rm /var/tmp/ci-gpg-key.asc", check=True)
    _, canary = sh.run(f"runuser -u {user} -- pass show ci/canary")

    return canary.strip()


def user_failed_units(vm, user):
    _, out = vm.shell.run(
        f"systemctl --user --machine={user}@ list-units --state=failed --plain"
        " --no-legend",
        check=True,
    )

    return tuple(line.split()[0] for line in out.splitlines() if line.strip())


def check_nvim(vm, user):
    sh = vm.shell
    files = {
        "ansible.cfg": "[defaults]\n",
        "roles/demo/tasks/main.yml": (
            "# vim:ft=yaml.ansible:\n---\n- name: Say hello\n"
            "  ansible.builtin.debug:\n    msg: hello\n"
        ),
        "pyproject.toml": '[project]\nname = "demo"\nversion = "0"\n',
        "demo.py": 'print("hello")\n',
        "fix.sh": "#!/bin/bash\necho $1\n",
        "check.lua": (Path(__file__).parent / "nvim_check.lua").read_text(),
    }
    sh.run(f"rm -rf {NVIM_DIR} && mkdir -p {NVIM_DIR}/roles/demo/tasks", check=True)
    for name, content in files.items():
        write_guest_file(sh, f"{NVIM_DIR}/{name}", content)
    sh.run(f"chown -R {user} {NVIM_DIR}", check=True)
    sh.run(
        f"cd {NVIM_DIR} && timeout 300 runuser -u {user} -- env"
        f" NVIM_CHECK_DIR={NVIM_DIR} NVIM_CHECK_OUT={NVIM_DIR}/result.json"
        f" nvim --headless -c 'luafile {NVIM_DIR}/check.lua' </dev/null >/dev/null 2>&1",
        timeout=360,
    )
    rc, out = sh.run(f"cat {NVIM_DIR}/result.json")
    if rc != 0:
        pytest.fail("nvim wrote no results; it failed to start or hung")

    found = json.loads(out)

    return NvimFacts(
        errmsg=found["errmsg"],
        messages=found["messages"],
        plugins=tuple(found["plugins"] or ()),
        inactive_plugins=tuple(found["inactive_plugins"] or ()),
        lsp_clients={
            kind: tuple(attached["clients"] or ())
            for kind, attached in found["lsp"].items()
        },
        fixed_script=found["fixed_script"],
    )


@pytest.fixture(scope="session")
def logged_in(second_boot, target, identity, log):
    """A third boot of the installed disk: seed the software token, then log
    in at greetd with the home's first password and let first login run.
    Yields the running VM for the re-login checks, then powers it off."""
    password = (identity / "home-recovery-key").read_text().strip()
    log(f"==> third boot of {target}: first login")
    with disk_vm(target, log, MEMORY, default_cpus()) as vm:
        boot_to_shell(vm, DISK_BOOT_TIMEOUT, log)
        sh = vm.shell
        user = home_user(sh)
        seed_software_token(sh, TOKEN_PIN, TOKEN_SO_PIN)

        login = log_in(vm, user, password)
        vm.screenshot("session-login")
        if login is None:
            diagnostics = login_diagnostics(vm)
            log(diagnostics)
            pytest.fail(
                f"no session for {user} after logging in at greetd\n{diagnostics}"
            )

        uid = user_uid(sh, user)
        sock = sway_socket(sh, uid)
        recap, pane = wait_for_play_recap(sh, uid, FIRST_LOGIN_TIMEOUT)
        (vm.run_dir / "session-first-login-pane.txt").write_text(pane)
        windows = wait_for_windows(sh, sock, (GHOSTTY, FIREFOX))
        firefox_title = open_local_page(sh, sock)
        vm.screenshot("session-desktop")
        facts = SessionFacts(
            login=login,
            first_login_recap=recap,
            home=home_facts(sh, user),
            canary=read_pass_canary(vm, user, identity),
            windows=windows,
            firefox_title=firefox_title,
            user_failed_units=user_failed_units(vm, user),
            nvim=check_nvim(vm, user),
        )

        yield vm, user, facts

        power_off(vm)


@pytest.fixture(scope="session")
def session(logged_in):
    return logged_in[2]


@pytest.fixture(scope="session")
def relogin(logged_in, identity, log):
    """Log out, then try the home's first password, then the token's PIN."""
    vm, user, _ = logged_in
    password = (identity / "home-recovery-key").read_text().strip()
    log(f"==> logging {user} out and in again")
    log_out(vm.shell, user)
    with_home_password = log_in(vm, user, password, attempts=1)
    vm.screenshot("relogin-home-password")

    with_token_pin = None
    if with_home_password is None:
        restart_greeter(vm.shell)
        with_token_pin = log_in(vm, user, TOKEN_PIN)
        vm.screenshot("relogin-token-pin")

    return ReloginFacts(
        with_home_password=with_home_password, with_token_pin=with_token_pin
    )
