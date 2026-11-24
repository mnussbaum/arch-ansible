"""Facts read from a running guest over its serial root shell.

Each probe runs guest commands and returns a frozen record, so bin/vm can
print what it found and the end-to-end tests can assert on the same facts.
The parsers are separate from the probes so they can be tested on captured
output.
"""

import json
from dataclasses import dataclass

# Discoverable Partitions Specification type GUIDs, as `systemd-id128 show`
# lists them.
PARTITION_TYPES = {
    "c12a7328f81f11d2ba4b00a0c93ec93b": "esp",
    "8484680c952148c69c11b0720656f69e": "usr",
    "77ff5f63e7b64633acf41565b864c0e6": "usr-verity",
    "e7bb33fb06cf4e818273e543b413e2e2": "usr-verity-sig",
    "4f68bce3e8cd4db196e7fbcaf984b709": "root",
    "933ac7e12eb44f13b8440e14e2aef915": "home",
    "0657fd6da4ab43c484e50933c84b4f4f": "swap",
}

# Reaching the internet from a booted system: a link, DNS, then HTTPS.
NETWORK_CHECKS = (
    "/usr/lib/systemd/systemd-networkd-wait-online --any --timeout=60",
    "resolvectl query archlinux.org",
    "curl -fsS -o /dev/null --max-time 30 https://archlinux.org",
)


@dataclass(frozen=True, kw_only=True)
class SystemState:
    """systemd's view of the boot."""

    # is-system-running once boot has finished: running, degraded, ...
    state: str
    failed_units: tuple[str, ...]
    # The configured default, which a systemd.unit= on the cmdline overrides.
    default_target: str


@dataclass(frozen=True, kw_only=True)
class EspLayout:
    """What a written ESP holds."""

    ukis: tuple[str, ...]
    loader_entries: tuple[str, ...]
    has_image_dir: bool
    has_systemd_boot: bool
    has_fallback_loader: bool


@dataclass(frozen=True, kw_only=True)
class Partition:
    # A name from PARTITION_TYPES, or "unknown".
    type_name: str
    type_guid: str
    label: str


@dataclass(frozen=True, kw_only=True)
class Tpm2Binding:
    """How one systemd-tpm2 LUKS token is sealed."""

    pcrs: tuple[int, ...]
    pubkey_pcrs: tuple[int, ...]
    pubkey_ref: str | None
    pcrlock: bool


def last_line(text):
    lines = text.strip().splitlines()

    return lines[-1] if lines else ""


def system_state(shell, timeout=600):
    """Wait for boot to finish, then read its state."""
    _rc, state = shell.run("systemctl is-system-running --wait", timeout=timeout)
    _rc, failed = shell.run("systemctl --failed --no-legend --plain | awk '{print $1}'")
    # Without stderr: a systemd.unit= on the cmdline adds a note there, and
    # serial merges it into the output.
    _rc, default = shell.run("systemctl get-default 2>/dev/null")

    return SystemState(
        state=last_line(state),
        failed_units=tuple(failed.split()),
        default_target=last_line(default),
    )


def unit_state(shell, unit):
    _rc, out = shell.run(f"systemctl is-active {unit}")

    return last_line(out)


def failed_unit_journals(shell):
    """The tail of each failed unit's journal: the failed list names what
    broke, rarely why."""
    _rc, out = shell.run(
        "for u in $(systemctl --failed --no-legend --plain | awk '{print $1}'); "
        'do echo "--- $u"; journalctl -b --no-pager -o cat -u "$u" | tail -15; done'
    )

    return out


def pending_password_prompts(shell):
    """Outstanding ask-password requests. A boot that fell back to a prompt
    stalls on tty0, which serial can't see, so this is the only sign of it."""
    _rc, out = shell.run("systemd-tty-ask-password-agent --list 2>/dev/null")

    return tuple(line for line in out.splitlines() if line.strip())


def install_system(shell, device, timeout):
    """Run the one-shot installer onto `device`; returns (rc, output)."""
    # Stop the guided installer first so the two can't race for the target.
    # An explicit stop wins over Restart=always.
    shell.run("systemctl stop arch-install.service")

    return shell.run(f"/usr/bin/install-system --yes {device} 2>&1", timeout=timeout)


def parse_esp_listing(listing):
    """Parse `find <esp> -mindepth 1 -printf '%y %P\\n'` output."""
    ukis, entries = [], []
    has_image_dir = has_systemd_boot = has_fallback_loader = False
    for line in listing.splitlines():
        kind, _, path = line.partition(" ")
        lower = path.lower()
        if kind == "f" and lower.startswith("efi/linux/") and lower.endswith(".efi"):
            ukis.append(path)
        elif (
            kind == "f"
            and lower.startswith("loader/entries/")
            and lower.endswith(".conf")
        ):
            entries.append(path)
        elif kind == "f" and lower == "efi/systemd/systemd-bootx64.efi":
            has_systemd_boot = True
        elif kind == "f" and lower == "efi/boot/bootx64.efi":
            has_fallback_loader = True
        elif lower == "image":
            has_image_dir = True

    return EspLayout(
        ukis=tuple(sorted(ukis)),
        loader_entries=tuple(sorted(entries)),
        has_image_dir=has_image_dir,
        has_systemd_boot=has_systemd_boot,
        has_fallback_loader=has_fallback_loader,
    )


def esp_layout(shell, partition):
    shell.run("mkdir -p /mnt/esp", check=True)
    shell.run(f"mount {partition} /mnt/esp", check=True)
    _rc, listing = shell.run("find /mnt/esp -mindepth 1 -printf '%y %P\\n'")
    shell.run("umount /mnt/esp")

    return parse_esp_listing(listing)


def parse_partition_table(sfdisk_json):
    """Parse `sfdisk --json` output into the partitions' types, in order."""
    partitions = json.loads(sfdisk_json)["partitiontable"].get("partitions", [])
    out = []
    for p in partitions:
        guid = p["type"].lower().replace("-", "")
        out.append(
            Partition(
                type_name=PARTITION_TYPES.get(guid, "unknown"),
                type_guid=guid,
                label=p.get("name", ""),
            )
        )

    return tuple(out)


def partition_table(shell, disk):
    shell.run("udevadm settle")
    _rc, out = shell.run(f"sfdisk --json {disk}", check=True)

    return parse_partition_table(out)


def parse_tpm2_tokens(luks_json):
    """Parse `cryptsetup luksDump --dump-json-metadata` into its TPM2 tokens."""
    tokens = json.loads(luks_json)["tokens"].values()

    return tuple(
        Tpm2Binding(
            pcrs=tuple(t.get("tpm2-pcrs", [])),
            pubkey_pcrs=tuple(t.get("tpm2_pubkey_pcrs", [])),
            pubkey_ref=t.get("tpm2_pubkey_ref"),
            pcrlock=bool(t.get("tpm2_pcrlock", False)),
        )
        for t in tokens
        if t.get("type") == "systemd-tpm2"
    )


def tpm2_bindings(shell, designator):
    """The TPM2 tokens of the LUKS volume at /dev/disk/by-designator/<designator>."""
    _rc, out = shell.run(
        f"cryptsetup luksDump --dump-json-metadata /dev/disk/by-designator/{designator}",
        check=True,
    )

    return parse_tpm2_tokens(out)


def network_checks(shell):
    """The exit code of each of NETWORK_CHECKS."""
    return {cmd: shell.run(cmd, timeout=120)[0] for cmd in NETWORK_CHECKS}
