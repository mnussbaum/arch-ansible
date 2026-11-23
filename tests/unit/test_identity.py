import os
import shutil
import subprocess

import pytest

from arch_ansible_ci.identity import ensure_identity


@pytest.fixture(scope="module")
def identity(tmp_path_factory):
    path = tmp_path_factory.mktemp("identity") / "ci"

    yield path, ensure_identity(path)

    subprocess.run(
        ["gpgconf", "--kill", "all"],
        check=False,
        env=dict(os.environ, GNUPGHOME=str(path / "gnupg")),
    )


def run(args, **env):
    return subprocess.run(
        args, check=True, capture_output=True, text=True, env=dict(os.environ, **env)
    ).stdout


def test_secureboot_key_matches_a_certificate_marked_throwaway(identity):
    path, _ = identity

    key_modulus = run(
        ["openssl", "rsa", "-noout", "-modulus", "-in", str(path / "secureboot.key")]
    )
    cert_modulus = run(
        ["openssl", "x509", "-noout", "-modulus", "-in", str(path / "secureboot.crt")]
    )
    subject = run(
        ["openssl", "x509", "-noout", "-subject", "-in", str(path / "secureboot.crt")]
    )

    assert key_modulus == cert_modulus
    assert "arch-ansible CI (throwaway)" in subject


def test_the_gpg_key_reads_the_canary_from_the_store(identity, tmp_path):
    path, manifest = identity
    fresh_home = tmp_path / "gnupg"
    fresh_home.mkdir(mode=0o700)
    secret_key = run(
        ["gpg", "--batch", "--armor", "--export-secret-keys", manifest.gpg_fingerprint],
        GNUPGHOME=str(path / "gnupg"),
    )
    subprocess.run(
        ["gpg", "--batch", "--import"],
        input=secret_key,
        check=True,
        capture_output=True,
        text=True,
        env=dict(os.environ, GNUPGHOME=str(fresh_home)),
    )

    canary = run(
        ["pass", "show", "ci/canary"],
        GNUPGHOME=str(fresh_home),
        PASSWORD_STORE_DIR=str(path / "password-store"),
    )

    subprocess.run(
        ["gpgconf", "--kill", "all"],
        check=False,
        env=dict(os.environ, GNUPGHOME=str(fresh_home)),
    )
    assert canary.strip() == manifest.canary


def test_the_store_is_a_git_repo_encrypted_to_the_ci_key(identity):
    path, manifest = identity
    store = path / "password-store"

    assert (store / ".git").is_dir()
    assert (store / ".gpg-id").read_text().strip() == manifest.gpg_fingerprint


def test_the_home_recovery_key_is_set(identity):
    path, _ = identity

    assert (path / "home-recovery-key").read_text()
    assert (path / "home-recovery-key").stat().st_mode & 0o777 == 0o600


def test_running_again_keeps_the_existing_identity(identity, tmp_path):
    path, manifest = identity
    copy = tmp_path / "ci"
    shutil.copytree(path, copy, ignore=shutil.ignore_patterns("S.*"))
    cert = (copy / "secureboot.crt").read_bytes()

    again = ensure_identity(copy)

    assert again == manifest
    assert (copy / "secureboot.crt").read_bytes() == cert
