"""Stage 3: the medium's Installer profile writes an installable disk."""

import pytest

pytestmark = pytest.mark.install


def test_installer_boots_to_the_guided_installer_without_the_graphical_login(installer):
    assert installer.system.failed_units == ()
    # The Installer profile's systemd.unit= overrides the default target.
    assert installer.multi_user_target == "active"
    assert installer.graphical_target != "active"
    assert installer.installer_unit == "active"
    assert installer.greetd != "active"


def test_install_system_succeeds(installer):
    assert installer.install_rc == 0, installer.install_output


def test_esp_holds_one_bare_uki_and_systemd_boot(installer):
    esp = installer.esp

    assert esp is not None, "the install failed, so there's no ESP to read"
    assert len(esp.ukis) == 1, esp.ukis
    assert esp.loader_entries == ()
    assert not esp.has_image_dir
    assert esp.has_systemd_boot
    assert esp.has_fallback_loader


def test_target_holds_the_esp_and_both_usr_slots_but_not_root_home_or_swap(installer):
    usr_types = ("usr", "usr-verity", "usr-verity-sig")

    assert sorted(p.type_name for p in installer.partitions) == sorted(
        ["esp", *usr_types, *usr_types]
    )
    # Slot B is written empty; root, home and swap wait for first boot.
    empty = sorted(p.type_name for p in installer.partitions if p.label == "_empty")
    assert empty == sorted(usr_types)
