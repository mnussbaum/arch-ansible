"""Stage 5: first login at greetd with a software token in place of the
YubiKey, then pass, the desktop and nvim in the session it starts."""

import pytest

from arch_ansible_vm.desktop import FIREFOX, GHOSTTY, PAGE_TITLE

pytestmark = pytest.mark.session


def test_login_starts_a_wayland_session_on_seat0(session):
    assert session.login is not None
    assert (session.login.type, session.login.seat, session.login.active) == (
        "wayland",
        "seat0",
        True,
    )


def test_first_login_playbook_finishes_without_failures(session):
    recap = session.first_login_recap

    assert recap is not None, "no PLAY RECAP in the login terminal"
    assert (recap.get("failed"), recap.get("unreachable")) == (0, 0)


def test_home_is_unlocked_by_the_token_alone(session):
    home = session.home

    assert any("SoftHSM" in uri for uri in home.token_uris), home.token_uris
    assert not home.has_password
    assert home.keyslots == 1


def test_pass_decrypts_the_canary(session, manifest):
    assert session.canary == manifest.canary


def test_terminal_and_firefox_open_with_firefox_on_workspace_2(session):
    by_app = {w.app_id: w for w in session.windows}

    assert GHOSTTY in by_app, session.windows
    assert FIREFOX in by_app, session.windows
    assert by_app[FIREFOX].workspace == "2"


def test_firefox_loads_a_local_page(session):
    assert PAGE_TITLE in session.firefox_title


def test_no_user_units_failed(session):
    assert session.user_failed_units == ()


def test_nvim_starts_cleanly_with_every_plugin_active(session):
    nvim = session.nvim

    assert (nvim.errmsg, nvim.messages) == ("", "")
    assert nvim.plugins
    assert nvim.inactive_plugins == ()


def test_nvim_attaches_language_servers(session):
    clients = session.nvim.lsp_clients

    assert "ansiblels" in clients["ansible"]
    assert "pyright" in clients["python"]


def test_nvim_quotes_an_unquoted_variable_on_save(session):
    assert 'echo "$1"' in session.nvim.fixed_script


def test_the_home_password_no_longer_logs_in(relogin):
    assert relogin.with_home_password is None


def test_the_token_pin_logs_in(relogin):
    assert relogin.with_token_pin is not None
