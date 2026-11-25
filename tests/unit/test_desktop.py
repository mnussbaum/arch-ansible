import pytest

from arch_ansible_vm.desktop import sendkeys_for


def test_lowercase_letters_and_digits_are_their_own_keys():
    assert sendkeys_for("ab12") == ("a", "b", "1", "2")


def test_uppercase_and_shifted_symbols_hold_shift():
    assert sendkeys_for("A_!") == ("shift-a", "shift-minus", "shift-1")


def test_unshifted_symbols_use_their_key_names():
    assert sendkeys_for("-/= .") == ("minus", "slash", "equal", "spc", "dot")


def test_a_character_with_no_key_is_refused():
    with pytest.raises(ValueError, match="no key types"):
        sendkeys_for("é")
