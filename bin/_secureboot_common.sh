# shellcheck shell=bash
# SecureBoot signing keypair management.
#
# The same software RSA-2048 keypair signs UKIs (SecureBoot), expected PCR
# measurements, and the verity root hash. It lives in pass (encrypted to the
# GPG key, so GPG stays the only root of trust). bin/build-image materializes
# it to mkosi.key + mkosi.crt at the project root on every build; both files
# are gitignored. RSA-2048 (not ECC) because UEFI Secure Boot's auto-enroll
# path in OVMF/firmware historically rejects ECDSA auth descriptors.
#
# pkcs11-provider doesn't currently support the signing operations that
# systemd-sbsign and systemd-repart need, so the key has to live on disk
# rather than on a YubiKey. The cost is that the build host must keep the key
# protected at the filesystem layer (mode 0600 + LUKS-encrypted disk). When
# pkcs11-provider's CMS/PE signing paths land we can move the key back onto a
# YubiKey PIV slot.
SECUREBOOT_PASS_KEY="arch_ansible/secureboot-key"
SECUREBOOT_PASS_CERT="arch_ansible/secureboot-cert"

materialize_secureboot_keypair() {
  # Write mkosi.key + mkosi.crt to the repo root from pass. Run from the repo
  # root (writes mkosi.{key,crt} relative to CWD).
  #
  # The signing key is the root of Secure Boot trust, so retrieval failures must
  # NEVER fall through to minting a new key: overwriting it would invalidate
  # every already-signed image and brick Secure Boot until re-enrollment. We
  # therefore distinguish three cases by testing for the encrypted entry on disk
  # *before* trying to decrypt:
  #   - entry present + decrypts        → use it
  #   - entry present + decrypt fails   → hard error (YubiKey out? wrong store?)
  #   - entry absent                    → hard error, unless ARCH_ANSIBLE_SECUREBOOT_INIT=1
  # Only genuine first-time host setup (ARCH_ANSIBLE_SECUREBOOT_INIT=1) mints a key.
  : "${PASSWORD_STORE_DIR:=$HOME/.local/share/password-store}"
  export PASSWORD_STORE_DIR PASSWORD_STORE_GPG_OPTS="--trust-model always"

  if [[ -f "$PASSWORD_STORE_DIR/$SECUREBOOT_PASS_KEY.gpg" ]]; then
    if ! (umask 077; pass show "$SECUREBOOT_PASS_KEY" > mkosi.key); then
      rm -f mkosi.key
      echo "ERROR: $SECUREBOOT_PASS_KEY exists in pass but failed to decrypt." >&2
      echo "  Is the YubiKey inserted and the GPG agent unlocked?" >&2
      echo "  PASSWORD_STORE_DIR=$PASSWORD_STORE_DIR" >&2
      return 1
    fi
    # umask only governs newly created files; an already-present mkosi.key (e.g.
    # copied in with looser perms) keeps its mode through the redirect, and
    # systemd-sbsign/mkosi reject a group/world-readable private key. Force it.
    chmod 600 mkosi.key
    pass show "$SECUREBOOT_PASS_CERT" > mkosi.crt
    return
  fi

  if [[ "${ARCH_ANSIBLE_SECUREBOOT_INIT:-}" != 1 ]]; then
    echo "ERROR: $SECUREBOOT_PASS_KEY not found in pass." >&2
    echo "  PASSWORD_STORE_DIR=$PASSWORD_STORE_DIR" >&2
    echo "  Refusing to auto-generate a Secure Boot key (would break trust if the" >&2
    echo "  real one is just unreachable). For genuine first-time setup, re-run" >&2
    echo "  with ARCH_ANSIBLE_SECUREBOOT_INIT=1." >&2
    return 1
  fi

  echo "==> Generating SecureBoot RSA-2048 key + cert, storing in pass..." >&2
  (umask 077; openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out mkosi.key)
  chmod 600 mkosi.key
  openssl req -new -x509 -key mkosi.key -out mkosi.crt -days 36500 \
    -subj "/CN=arch-ansible SecureBoot"
  pass insert -m -f "$SECUREBOOT_PASS_KEY"  < mkosi.key
  pass insert -m -f "$SECUREBOOT_PASS_CERT" < mkosi.crt
}
