"""A throwaway identity that stands in for the real secrets in CI.

Its layout is the one `bin/build-image --container --secrets` reads, the same
set dr-unlock decrypts from pass with the YubiKey: a Secure Boot keypair, the
home recovery secret and a password store, plus the GPG key the store is
encrypted to. Nothing here is trusted outside CI: only CI VMs enroll the
certificate, and the store holds only test entries.
"""

import hashlib
import json
import os
import secrets
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

SECUREBOOT_SUBJECT = "/CN=arch-ansible CI (throwaway)"
GPG_UID = "arch-ansible CI (throwaway) <ci@invalid>"
CANARY_ENTRY = "ci/canary"
MANIFEST = "manifest.json"


@dataclass(frozen=True, kw_only=True)
class Manifest:
    """What an identity holds, for jobs that need to check or use it."""

    secureboot_cert_sha256: str
    gpg_fingerprint: str
    canary: str


def ensure_identity(path):
    """Create the identity in `path`, or return the one already there."""
    path = Path(path)
    manifest_file = path / MANIFEST
    if manifest_file.is_file():
        return Manifest(**json.loads(manifest_file.read_text()))

    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    make_secureboot_keypair(path)
    fingerprint = make_gpg_key(path / "gnupg")
    canary = secrets.token_hex(16)
    make_password_store(path, fingerprint, canary)
    stop_gpg_agent(path / "gnupg")
    write_secret(path / "home-recovery-key", secrets.token_urlsafe(24))
    manifest = Manifest(
        secureboot_cert_sha256=hashlib.sha256(
            (path / "secureboot.crt").read_bytes()
        ).hexdigest(),
        gpg_fingerprint=fingerprint,
        canary=canary,
    )
    # Written last: its presence marks a complete identity.
    manifest_file.write_text(json.dumps(asdict(manifest), indent=2) + "\n")

    return manifest


def write_secret(path, value):
    path.touch(mode=0o600)
    path.write_text(value)


def make_secureboot_keypair(path):
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "36500",
            "-subj",
            SECUREBOOT_SUBJECT,
            "-keyout",
            str(path / "secureboot.key"),
            "-out",
            str(path / "secureboot.crt"),
        ],
        check=True,
        capture_output=True,
    )
    (path / "secureboot.key").chmod(0o600)


def gpg_env(gnupghome):
    return dict(os.environ, GNUPGHOME=str(gnupghome))


def make_gpg_key(gnupghome):
    """A passphrase-less key with an encryption subkey; returns its fingerprint."""
    gnupghome.mkdir(mode=0o700)
    env = gpg_env(gnupghome)
    subprocess.run(
        [
            "gpg",
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            "--quick-generate-key",
            GPG_UID,
            "default",
            "default",
            "never",
        ],
        check=True,
        capture_output=True,
        env=env,
    )
    listing = subprocess.run(
        ["gpg", "--batch", "--with-colons", "--list-secret-keys", GPG_UID],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout

    return next(
        line.split(":")[9] for line in listing.splitlines() if line.startswith("fpr:")
    )


def stop_gpg_agent(gnupghome):
    """gpg leaves an agent running per GNUPGHOME; nothing here needs it again."""
    subprocess.run(
        ["gpgconf", "--kill", "all"],
        check=False,
        capture_output=True,
        env=gpg_env(gnupghome),
    )


def pass_env(path):
    return dict(
        gpg_env(path / "gnupg"),
        PASSWORD_STORE_DIR=str(path / "password-store"),
        GIT_AUTHOR_NAME="arch-ansible CI",
        GIT_AUTHOR_EMAIL="ci@invalid",
        GIT_COMMITTER_NAME="arch-ansible CI",
        GIT_COMMITTER_EMAIL="ci@invalid",
    )


def make_password_store(path, fingerprint, canary):
    """A git password store, which first login needs to clone it, holding the
    canary that CI reads back to check pass works."""
    env = pass_env(path)
    for args, stdin in (
        (["init", fingerprint], None),
        (["git", "init"], None),
        (["insert", "--multiline", CANARY_ENTRY], canary),
    ):
        subprocess.run(
            ["pass", *args],
            input=stdin,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
