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
  # Write mkosi.key + mkosi.crt to the repo root from pass. If the pass
  # entries are absent, generate a fresh ECC P-256 keypair and store it. Run
  # from the repo root (writes mkosi.{key,crt} relative to CWD).
  : "${PASSWORD_STORE_DIR:=$HOME/.local/share/password-store}"
  export PASSWORD_STORE_DIR PASSWORD_STORE_GPG_OPTS="--trust-model always"

  if pass show "$SECUREBOOT_PASS_KEY" >/dev/null 2>&1; then
    (umask 077; pass show "$SECUREBOOT_PASS_KEY"  > mkosi.key)
    pass show "$SECUREBOOT_PASS_CERT" > mkosi.crt
    return
  fi

  echo "==> Generating SecureBoot RSA-2048 key + cert, storing in pass..." >&2
  (umask 077; openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out mkosi.key)
  openssl req -new -x509 -key mkosi.key -out mkosi.crt -days 36500 \
    -subj "/CN=arch-ansible SecureBoot"
  pass insert -m -f "$SECUREBOOT_PASS_KEY"  < mkosi.key
  pass insert -m -f "$SECUREBOOT_PASS_CERT" < mkosi.crt
}
