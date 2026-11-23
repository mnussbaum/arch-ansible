"""Where builds and test disks live: the cache layout, picking a built medium,
and retention of the installed test disks `vm install` makes."""

import json
import os
import re
import shutil
import sys
from pathlib import Path

# --- QEMU --------------------------------------------------------------------


def cache_dir():
    if v := os.environ.get("ARCH_ANSIBLE_CACHE"):
        return Path(v)
    return Path("/var/cache/arch-ansible")


def output_dir():
    return cache_dir() / "mkosi/images/image"


def selected_organizations(organizations):
    """`organizations` (from --organization), else $ARCH_ANSIBLE_ORGANIZATIONS, as
    bin/_images_common.sh normalizes them: sorted, deduplicated, comma-separated."""
    orgs = organizations or os.environ.get("ARCH_ANSIBLE_ORGANIZATIONS", "").split(",")
    return ",".join(sorted({o for o in orgs if o}))


def newest_medium(orgs):
    """The newest built mkosi medium (image_<version>_<arch>.raw) whose
    organizations, recorded by bin/build-image in image_<version>_organizations,
    are exactly `orgs`. An image without the record has none."""
    cands = []
    for p in output_dir().glob("image_*.raw"):
        # Skip the per-partition artifacts mkosi drops alongside the disk image.
        m = re.fullmatch(r"image_(\d+)_[a-z0-9-]+\.raw", p.name)
        if not m:
            continue
        record = output_dir() / f"image_{m[1]}_organizations"
        if (record.read_text().strip() if record.is_file() else "") == orgs:
            cands.append((int(m[1]), p))
    if not cands:
        flags = "".join(f" --organization {o}" for o in orgs.split(",") if o)
        sys.exit(
            f"error: no image built for organizations '{orgs or 'none'}' in "
            f"{output_dir()}; run bin/build-image{flags}"
        )
    return max(cands)[1]


def medium_version(medium):
    return re.fullmatch(r"image_(\d+)_.*", medium.name)[1]


def medium_organizations(medium):
    record = medium.parent / f"image_{medium_version(medium)}_organizations"
    return record.read_text().strip() if record.is_file() else ""


# --- test-disk retention -----------------------------------------------------


def disk_registry():
    return cache_dir() / "mkosi/vm-disks.json"


def load_disks():
    try:
        return json.loads(disk_registry().read_text())
    except FileNotFoundError:
        return {}


def disk_files(disk):
    return [
        p
        for p in (Path(disk), Path(f"{disk}.ovmf_vars.fd"), Path(f"{disk}.tpm"))
        if p.exists()
    ]


def disk_in_use(disk):
    """Whether any process (a VM still running elsewhere) has DISK open."""
    disk = os.path.realpath(disk)
    for fd_dir in Path("/proc").glob("[0-9]*/fd"):
        try:
            if any(os.readlink(fd) == disk for fd in fd_dir.iterdir()):
                return True
        except OSError:
            continue
    return False


def use_disk(disk, log, now, orgs=None):
    """Mark DISK used at `now` (registering it when `orgs` is given), then delete
    all but the most recently used registered disk per organization set."""
    disks = load_disks()
    key = str(disk)
    if orgs is not None:
        disks[key] = {"organizations": orgs}
    if key in disks:
        disks[key]["last_used"] = now

    newest = {}
    for path, d in sorted(disks.items(), key=lambda kv: -kv[1]["last_used"]):
        if not Path(path).exists():
            del disks[path]
        elif d["organizations"] not in newest:
            newest[d["organizations"]] = path
        elif path != key and not disk_in_use(path):
            log(
                f"==> removing older test disk {path} "
                f"(organizations: {d['organizations'] or 'none'})"
            )
            for f in disk_files(path):
                shutil.rmtree(f) if f.is_dir() else f.unlink()
            del disks[path]

    disk_registry().parent.mkdir(parents=True, exist_ok=True)
    tmp = disk_registry().with_suffix(".tmp")
    tmp.write_text(json.dumps(disks, indent=2) + "\n")
    tmp.replace(disk_registry())
