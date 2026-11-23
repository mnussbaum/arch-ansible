from pathlib import Path

from arch_ansible_vm.sdboot import menu_entries, render_screen

FIXTURES = Path(__file__).parent / "fixtures"


def test_menu_entries_reads_a_captured_menu_in_order():
    raw = (FIXTURES / "sdboot-menu.raw").read_bytes()

    assert menu_entries(raw) == [
        "Arch Linux",
        "Arch Linux (default)",
        "Arch Linux (Live System)",
        "Arch Linux (emergency)",
        "Arch Linux (Installer)",
        "Arch Linux (factory-reset)",
        "Arch Linux (factory-reset-with-tpm-clear)",
        "Reboot Into Firmware Interface",
    ]


def test_menu_entries_skips_rules_countdown_and_blank_rows():
    raw = (
        b"\x1b[2J"
        b"\x1b[3;10HEntry A"
        b"\x1b[4;10H\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80"
        b"\x1b[5;10HEntry B"
        b"\x1b[6;1H      "
        b"\x1b[20;1HBoot in 5 s."
    )

    assert menu_entries(raw) == ["Entry A", "Entry B"]


def test_menu_entries_drops_everything_before_the_last_clear():
    raw = b"\x1b[1;1HOld entry\x1b[2J\x1b[1;1HNew entry"

    assert menu_entries(raw) == ["New entry"]


def test_render_screen_places_text_at_the_cursor_and_repaints_over_it():
    raw = b"\x1b[2;5Habc\x1b[2;6HX"

    assert render_screen(raw) == {2: "    aXc"}


def test_render_screen_handles_line_endings_and_skips_stray_escapes():
    raw = b"one\r\ntwo\x1b[1mbold\r\nabc\rX\x1b"

    assert render_screen(raw) == {1: "one", 2: "twobold", 3: "Xbc"}
