"""Stage 3: the medium's Installer profile writes an installable disk."""

import pytest

pytestmark = pytest.mark.install


def test_installer_boots_to_the_guided_installer_without_the_graphical_login(installer):
    assert installer.system.failed_units == ()
    assert installer.system.default_target == "multi-user.target"
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


def test_target_holds_only_the_esp_and_usr_partitions(installer):
    assert sorted(p.type_name for p in installer.partitions) == [
        "esp",
        "usr",
        "usr-verity",
        "usr-verity-sig",
    ]
