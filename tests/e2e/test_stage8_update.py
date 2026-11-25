"""Stage 8: update-system takes the previous image to this run's from the
running system, and a newer entry that never completes a boot is abandoned
after its tries for the previous one."""

import pytest

pytestmark = pytest.mark.update


def test_update_system_installs_this_runs_version(update):
    assert update.update_rc == 0, update.update_output
    assert f"image_{update.new_version}" in {p.label for p in update.partitions}


def test_the_new_version_boots_from_the_other_usr_slot(update):
    assert update.os_release_version == update.new_version
    assert f"image_{update.new_version}" in update.usr_labels
    assert f"image_{update.old_version}" not in update.usr_labels


def test_root_and_swap_still_unlock_without_a_prompt(update):
    assert update.password_prompts == ()
    assert update.swap_unlock == "active"


def test_the_new_entry_is_blessed_and_selected(update):
    selected = [e for e in update.entries if e.selected]

    assert [e.id for e in selected] == [f"image_{update.new_version}_x86-64.efi"]
    assert (selected[0].tries_left, selected[0].tries_done) == (None, None)


def test_no_units_fail_after_the_update(update):
    assert update.system.failed_units == (), update.failed_unit_journals
    assert update.system.state == "running"


def test_the_old_version_stays_as_the_fallback(update):
    assert f"image_{update.old_version}" in {p.label for p in update.partitions}
    assert any(e.id.startswith(f"image_{update.old_version}_") for e in update.entries)


def test_the_recovery_key_still_logs_in(update):
    assert update.login is not None
    assert update.login.type == "wayland"


def test_an_entry_that_never_completes_a_boot_falls_back_after_three_tries(rollback):
    newer = next(e for e in rollback.entries if e.id == rollback.newer_id)

    assert rollback.selected == (rollback.newer_id,) * 3 + (rollback.new_id,)
    assert (newer.tries_left, newer.tries_done) == (0, 3)
