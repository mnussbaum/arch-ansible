"""Stage 4: the installed disk provisions itself on first boot, and unlocks
from the TPM with no prompt on the next."""

import pytest

from arch_ansible_vm.checks import NETWORK_CHECKS

pytestmark = pytest.mark.first_boot


def test_first_boot_reaches_running_with_no_failed_units(first_boot):
    assert first_boot.system.failed_units == (), first_boot.failed_unit_journals
    assert first_boot.system.state == "running"


def test_first_boot_starts_the_graphical_login(first_boot):
    assert first_boot.system.default_target == "graphical.target"
    assert first_boot.graphical_target == "active"
    assert first_boot.greetd == "active"


def test_first_boot_asks_for_no_password(first_boot):
    assert first_boot.password_prompts == ()


@pytest.mark.parametrize("check", NETWORK_CHECKS)
def test_first_boot_reaches_the_network(first_boot, check):
    assert first_boot.network[check] == 0


def test_second_boot_unlocks_without_a_prompt(second_boot):
    assert second_boot.password_prompts == ()
    assert second_boot.system.failed_units == (), second_boot.failed_unit_journals
    assert second_boot.system.state == "running"


def test_root_is_sealed_to_pcrlock_and_the_initrd_signed_pcr11_policy(second_boot):
    assert len(second_boot.root_bindings) == 1, second_boot.root_bindings
    root = second_boot.root_bindings[0]

    assert root.pcrlock
    assert 7 not in root.pcrs
    assert root.pubkey_pcrs == (11,)
    assert root.pubkey_ref == "initrd"


def test_swap_is_also_sealed_to_roots_pcr15(second_boot):
    assert len(second_boot.swap_bindings) == 1, second_boot.swap_bindings
    swap = second_boot.swap_bindings[0]

    assert swap.pcrlock
    assert 15 in swap.pcrs
    assert swap.pubkey_pcrs == (11,)
    assert swap.pubkey_ref == "initrd"
