"""Updating an installed disk to a newer image from the running system, and
reading back which version and boot entry it came up on."""

import json
import re
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from arch_ansible_vm.qemu import SHARE_MNT, SHARE_TAG

# Where update-system --no-build looks for a build under $ARCH_ANSIBLE_CACHE.
SHARED_BUILD = "mkosi/images/image"
# Where the checkout's bin/ goes in the share, so the update runs this
# checkout's update-system, as a person runs their own, not the old image's.
SHARED_CHECKOUT = "checkout"

# Required by boot-complete.target and always failing, so a boot with it never
# counts as good and its entry is never blessed.
NEVER_COMPLETE_UNIT = "ci-never-complete.service"

_NEVER_COMPLETE = """[Unit]
Description=Keeps this boot from counting as good (CI)
Before=boot-complete.target

[Service]
Type=oneshot
ExecStart=/usr/bin/false
"""


@dataclass(frozen=True, kw_only=True)
class BootEntry:
    # The UKI's file name without the boot counter, as sd-boot reports it.
    id: str
    selected: bool
    # None once the entry is blessed, or for an entry that was never counted.
    tries_left: int | None
    tries_done: int | None


def version_of(name):
    """The version in an image file name, image_<version>_<arch>…"""
    match = re.match(r"image_(\d+)_", Path(name).name)
    if not match:
        raise ValueError(f"no image version in {name!r}")

    return match[1]


def shared_build_version(share):
    """The version of the UKI shared for the update, the newest if several."""
    ukis = sorted((Path(share) / SHARED_BUILD).glob("image_*_*.efi"))
    if not ukis:
        raise FileNotFoundError(f"no UKI under {Path(share) / SHARED_BUILD}")

    return version_of(ukis[-1].name)


def uki_id(version):
    return f"image_{version}_x86-64.efi"


def share_checkout(share, repo):
    """Copy `repo`'s bin/ into the share, where apply_update runs it from."""
    shutil.copytree(
        Path(repo) / "bin", Path(share) / SHARED_CHECKOUT / "bin", dirs_exist_ok=True
    )


def apply_update(shell, timeout=3600):
    """Run the shared checkout's update-system against the build shared at
    SHARE_MNT; returns its (exit code, output)."""
    shell.run(
        f"mkdir -p {SHARE_MNT} && mount -t virtiofs {SHARE_TAG} {SHARE_MNT}",
        check=True,
    )

    return shell.run(
        f"ARCH_ANSIBLE_CACHE={SHARE_MNT}"
        f" {SHARE_MNT}/{SHARED_CHECKOUT}/bin/update-system --no-build",
        timeout=timeout,
    )


def os_release_version(shell):
    _, out = shell.run(
        '. /usr/lib/os-release && echo "$IMAGE_VERSION"', check=True, quiet=True
    )

    return out.strip()


def usr_partition_labels(shell):
    """The partition labels of the data and hash devices behind /usr."""
    _, out = shell.run(
        'dm=$(basename "$(readlink -f /dev/mapper/usr)");'
        ' for slave in /sys/block/"$dm"/slaves/*; do'
        ' lsblk -no PARTLABEL "/dev/${slave##*/}"; done',
        check=True,
    )

    return tuple(line.strip() for line in out.splitlines() if line.strip())


def uki_of(entry_id):
    """The UKI file name an entry ID names, without its @profile suffix."""
    return entry_id.split("@", 1)[0]


def parse_boot_entries(bootctl_json):
    """One entry per UKI on the ESP.

    bootctl lists each UKI once per profile (id@profile), with its boot
    counter, and again as the loader reported it (plain id), which is the only
    listing that says whether it was selected.
    """
    raw = json.loads(bootctl_json)
    selected = {uki_of(e["id"]) for e in raw if e.get("isSelected")}

    entries = {}
    for entry in raw:
        if entry.get("type") != "type2":
            continue

        uki = uki_of(entry["id"])
        entries.setdefault(
            uki,
            BootEntry(
                id=uki,
                selected=uki in selected,
                tries_left=entry.get("triesLeft"),
                tries_done=entry.get("triesDone"),
            ),
        )

    return tuple(entries.values())


def boot_entries(shell):
    _, out = shell.run("bootctl list --json=short", check=True)

    return parse_boot_entries(out)


def selected_entry(entries):
    return next((e.id for e in entries if e.selected), "")


def install_unbootable_copy(shell, version, newer):
    """Copy `version`'s UKI as `newer` with three tries, and stop every boot
    from completing, so booting the copy never blesses it."""
    copy = f"image_{newer}_x86-64+3.efi"
    shell.run(
        'linux="$(bootctl --print-esp-path)/EFI/Linux";'
        f' cp "$(ls "$linux"/image_{version}_x86-64*.efi | head -1)"'
        f' "$linux/{copy}"',
        check=True,
    )
    unit = f"/etc/systemd/system/{NEVER_COMPLETE_UNIT}"
    shell.run(
        f"printf %s {shlex.quote(_NEVER_COMPLETE)} > {unit}"
        " && mkdir -p /etc/systemd/system/boot-complete.target.requires"
        f" && ln -sf {unit} /etc/systemd/system/boot-complete.target.requires/",
        check=True,
    )


def remove_never_complete_unit(shell):
    shell.run(
        "rm -f /etc/systemd/system/boot-complete.target.requires/"
        f"{NEVER_COMPLETE_UNIT} /etc/systemd/system/{NEVER_COMPLETE_UNIT}",
        check=True,
    )
