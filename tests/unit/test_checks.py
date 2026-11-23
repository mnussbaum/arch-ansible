import json

from arch_ansible_vm.checks import (
    EspLayout,
    Partition,
    parse_esp_listing,
    parse_partition_table,
)


def listing(*lines):
    """`find -printf '%y %P\\n'` output, one entry per argument."""
    return "\n".join(lines)


def test_esp_listing_finds_ukis_entries_image_dir_and_loaders():
    entries = listing(
        "d EFI",
        "d EFI/BOOT",
        "f EFI/BOOT/BOOTX64.EFI",
        "d EFI/systemd",
        "f EFI/systemd/systemd-bootx64.efi",
        "d EFI/Linux",
        "f EFI/Linux/image_20261123103753_x86-64.efi",
        "d loader",
        "f loader/loader.conf",
        "d loader/entries",
        "f loader/entries/image.conf",
        "d image",
    )

    assert parse_esp_listing(entries) == EspLayout(
        ukis=("EFI/Linux/image_20261123103753_x86-64.efi",),
        loader_entries=("loader/entries/image.conf",),
        has_image_dir=True,
        has_systemd_boot=True,
        has_fallback_loader=True,
    )


def test_an_empty_esp_has_nothing():
    assert parse_esp_listing("") == EspLayout(
        ukis=(),
        loader_entries=(),
        has_image_dir=False,
        has_systemd_boot=False,
        has_fallback_loader=False,
    )


def test_missing_directories_and_non_conf_entries_are_not_counted():
    entries = listing(
        "d EFI/Linux",
        "f EFI/Linux/readme.txt",
        "d loader/entries",
        "f loader/entries/notes.txt",
    )

    layout = parse_esp_listing(entries)

    assert layout.ukis == ()
    assert layout.loader_entries == ()
    assert not layout.has_image_dir


def sfdisk(*partitions):
    return json.dumps(
        {"partitiontable": {"label": "gpt", "partitions": list(partitions)}}
    )


def test_partition_table_names_known_types_in_order():
    table = sfdisk(
        {"type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B", "name": "esp"},
        {"type": "8484680C-9521-48C6-9C11-B0720656F69E", "name": "image_1"},
        {"type": "77FF5F63-E7B6-4633-ACF4-1565B864C0E6", "name": "image_1_verity"},
        {"type": "E7BB33FB-06CF-4E81-8273-E543B413E2E2", "name": "image_1_verity_sig"},
    )

    assert [p.type_name for p in parse_partition_table(table)] == [
        "esp",
        "usr",
        "usr-verity",
        "usr-verity-sig",
    ]


def test_partition_table_reports_unknown_types_rather_than_dropping_them():
    table = sfdisk({"type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4", "name": "data"})

    assert parse_partition_table(table) == (
        Partition(
            type_name="unknown",
            type_guid="0fc63daf848347728e793d69d8477de4",
            label="data",
        ),
    )


def test_an_empty_partition_table_has_no_partitions():
    assert parse_partition_table(json.dumps({"partitiontable": {"label": "gpt"}})) == ()
