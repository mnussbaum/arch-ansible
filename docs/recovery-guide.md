# Recovery guide

How to get from nothing to a working laptop with its home restored from backup,
after losing every machine, YubiKey and primary-key USB. You need:

- this guide, printed
- the laptop to set up
- a borrowed Linux or macOS computer with internet, about 150G of free disk and
  8G+ of memory, to build images on
- a USB drive of 32G or more for the recovery USB, and another for the new
  primary-key backup (a third for a second backup is better)
- new YubiKeys

`bin/generate-gpg-recovery-guide` prints this document with every doc it links
below embedded, and fills the appendix with the key material from the
primary-key USB. In the repo the appendix shows only what each item is. Keep the
printed guide in a physically separate place from the USB drives and YubiKeys,
and reprint it when the primary GPG key is replaced, the critical TOTP accounts
change, or any of these docs change.

## Overview

1. On the borrowed computer, build a recovery USB with a throwaway key.
2. On the laptop, boot that USB's Live System, rebuild the GPG key from this
   guide, write a new primary-key USB and program the new YubiKeys.
3. Still in the Live System, add the laptop's backup credentials.
4. On the borrowed computer, build the real recovery USB with a new YubiKey.
5. Install the laptop from it.
6. Restore the laptop's home from backup.

## Part 1 — Build a throwaway-key recovery USB

On the borrowed computer, set up the container runtime, then build with
`--ephemeral-key` and write the result to the 32G USB drive.

[Build a recovery USB](build-recovery-usb.md "embedded in the printed guide")

## Part 2 — Restore the GPG key from paper

On the laptop, booted from the Part 1 recovery USB.

[Restore the GPG key from paper](gpg-paper-recovery.md "embedded in the printed guide")

## Part 3 — Add the laptop's backup credentials

Still in the Live System, which has Firefox for the Backblaze website. Pick the
laptop's name now, and give it at the hostname prompt in Part 5.

[Add a machine's backup credentials](backup-credentials.md "embedded in the printed guide")

## Part 4 — Build the real recovery USB

On the borrowed computer, with a new YubiKey, follow [Part 1](#part-1--build-a-throwaway-key-recovery-usb)
again from "Build", without `--ephemeral-key`. The build reuses Part 1's caches,
and can overwrite the Part 1 recovery USB. `git pull` first: the build needs the
public key pushed in Part 2.

## Part 5 — Install the laptop

[Install a machine from a recovery USB](install-machine.md "embedded in the printed guide")

## Part 6 — Restore the home

[Restore a home from backup](restore-home.md "embedded in the printed guide")

## Afterwards

- Make a second primary-key USB and store it apart from the first:
  `bin/backup-gpg-key <primary-key-usb> <blank-usb>`.
- Print a new copy of this guide: `bin/generate-gpg-recovery-guide <primary-key-usb>`.
- The lost YubiKeys still hold the GPG subkeys and the shared PIV key, protected
  by their PINs. To revoke them, rotate the PIV key
  ([gpg-and-yubikeys.md](gpg-and-yubikeys.md), "Lost or blocked YubiKeys").
- On the borrowed computer, delete `dr-out/` and the `arch-ansible-dr-cache`
  volume.

## Appendix — Key material

The values appear only in the printed guide.

### Identity

<!-- secret: identity -->

### Primary key fingerprint

<!-- secret: fingerprint -->

### Public key

The primary key's ASCII-armored public key, also as a QR code. The repo has the
current copy at `ansible/roles/gpg/files/gpg-pubkey.asc`.

<!-- secret: public-key -->

### Private key

The primary key and its subkeys in paperkey's text format: only the secret
bytes, with a checksum per line. Rebuilding the key also needs the public key.

<!-- secret: private-key -->

### Critical TOTP accounts

A curated subset of the 2FA accounts on the primary-key USB (`CRITICAL_TOTPS` in
`bin/_recovery_guide.py`). Each QR code holds the `otpauth://` URI printed
beneath it.

<!-- secret: totp -->
