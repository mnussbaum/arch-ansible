import itertools
from pathlib import Path

import pytest

from arch_ansible_vm.qemu import Drive, LiveOptions, build_live_cmd, build_qemu_args


def has_pair(args, flag, value):
    """Whether `flag` is immediately followed by `value` somewhere in `args`."""
    return any(a == flag and b == value for a, b in itertools.pairwise(args))


def qemu_args(**overrides):
    params = {
        "drives": [],
        "varstore": Path("/run/vars.fd"),
        "tpm_sock": Path("/run/tpm.sock"),
        "memory": "4G",
        "cpus": 2,
        "credentials": (),
        "serial": ("socket", "/run/serial.sock"),
        "monitor_sock": "/run/monitor.sock",
    }
    params.update(overrides)

    return build_qemu_args(**params)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """An empty ARCH_ANSIBLE_CACHE with the image output directory."""
    monkeypatch.setenv("ARCH_ANSIBLE_CACHE", str(tmp_path))
    output = tmp_path / "mkosi/images/image"
    output.mkdir(parents=True)

    return output


def add_medium(output, version, organizations):
    (output / f"image_{version}_x86-64.raw").touch()
    (output / f"image_{version}_organizations").write_text(organizations + "\n")


def live_cmd(output, **overrides):
    params = {"cpus": 4, "memory": "8G", "organizations": "a,b"}
    params.update(overrides)

    return build_live_cmd(
        LiveOptions(**params),
        output,
        Path("/repo/.qemu-host-shared"),
        Path("/run/vars.fd"),
        Path("/run/tpm.sock"),
        passt=True,
    )


def test_headless_args_wait_on_the_serial_socket_and_have_no_display():
    args = qemu_args()

    assert has_pair(args, "-display", "none")
    assert has_pair(
        args, "-chardev", "socket,id=serial0,path=/run/serial.sock,server=on,wait=on"
    )
    assert has_pair(args, "-monitor", "unix:/run/monitor.sock,server,nowait")


def test_gui_args_open_a_window_and_log_serial_to_a_file():
    args = qemu_args(serial=("file", "/run/serial.log"), gui=True)

    assert has_pair(args, "-display", "gtk,gl=on,zoom-to-fit=off,grab-on-hover=on")
    assert has_pair(args, "-device", "virtio-tablet")
    assert has_pair(args, "-chardev", "file,id=serial0,path=/run/serial.log")


def test_drives_get_snapshot_and_bootindex_only_when_set():
    args = qemu_args(
        drives=[
            Drive(file=Path("/disks/medium.raw"), bootindex=0, snapshot=True),
            Drive(file=Path("/disks/target.raw")),
        ]
    )

    assert has_pair(
        args,
        "-drive",
        "if=none,id=drive0,file=/disks/medium.raw,format=raw,snapshot=on",
    )
    assert has_pair(args, "-device", "virtio-blk-pci,drive=drive0,bootindex=0")
    assert has_pair(
        args, "-drive", "if=none,id=drive1,file=/disks/target.raw,format=raw"
    )
    assert has_pair(args, "-device", "virtio-blk-pci,drive=drive1")


def test_credentials_become_smbios_values_beside_the_console_cmdline():
    args = qemu_args(credentials=["firstboot.hostname=arch-vmtest"])

    assert has_pair(
        args,
        "-smbios",
        "type=11,value=io.systemd.credential:firstboot.hostname=arch-vmtest",
    )
    assert has_pair(
        args,
        "-smbios",
        "type=11,value=io.systemd.stub.kernel-cmdline-extra=console=ttyS0 console=tty0",
    )


def test_a_virtiofs_share_adds_the_vhost_user_device():
    args = qemu_args(share_sock=Path("/run/virtiofs.sock"))

    assert has_pair(args, "-chardev", "socket,id=vfs0,path=/run/virtiofs.sock")
    assert has_pair(
        args,
        "-device",
        "vhost-user-fs-pci,queue-size=1024,chardev=vfs0,tag=vmtest-share",
    )


def test_live_cmd_passes_the_medium_options_through(cache):
    add_medium(cache, "20261101000000", "a,b")

    cmd = live_cmd(cache, device="/disks/target.raw", ephemeral=True, gui=True)

    assert has_pair(
        cmd, "-drive", "if=none,id=device,file=/disks/target.raw,format=raw"
    )
    assert has_pair(cmd, "-netdev", "passt,id=net0")
    assert has_pair(cmd, "-display", "gtk,gl=on,zoom-to-fit=off,grab-on-hover=on")
    assert "--ephemeral=yes" in cmd
    assert "--console=gui" in cmd
    assert "--profile=build,a,b" in cmd
    assert "--cpus=4" in cmd
    assert "--ram=8G" in cmd


def test_live_cmd_pins_the_newest_medium_built_for_the_organizations(cache):
    add_medium(cache, "20261101000000", "a,b")
    add_medium(cache, "20261102000000", "a,b")
    add_medium(cache, "20261103000000", "other")

    cmd = live_cmd(cache)

    assert "--image-version=20261102000000" in cmd
