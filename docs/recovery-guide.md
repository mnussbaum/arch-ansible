# Recovery guide

How to get from nothing to a working computer with all its files restored from
backup, even after losing every computer, YubiKey and root GPG key USB. If any
of these survived, you can skip steps and need less:

- a **root GPG key USB**: the encrypted USB drive holding the GPG key
- a **working YubiKey**: one already set up with our keys
- a **working recovery USB**: a USB drive that starts a computer into a system
  based on this repo and installs it
- a **working computer**: a machine based on this repo, with its files still on
  it

**With a working computer**, only the keys need rebuilding: follow
Part 2 and Part 3 on the computer itself, skipping them as the steps below say.
You need this printed guide, a USB drive for a new root GPG key, and new
YubiKeys.

Otherwise if you need to build a computer you need:

- this printed guide
- the computer to set up
- a borrowed Mac or Linux computer with internet, at least 80GB of free disk
  space and 8GB of memory, unless you already have a working recovery USB
- a USB drive of at least 32GB to become the recovery USB
- A USB drive to store the root GPG key
- A YubiKey

Regenerate this guide when the keys change, the important two-factor accounts
change, or these instructions change.

## Steps

1. **Set up the borrowed computer**:
   [Part 1](#part-1--set-up-the-borrowed-computer). Skip if you have a working
   computer or a working recovery USB.
2. **Rebuild the GPG key from this paper** onto a new root GPG key USB:
   [Part 2](#part-2--rebuild-the-gpg-key-from-paper). Skip if you have a root GPG
   key USB.
3. **Set up new YubiKeys** from the root GPG key USB:
   [Part 3](#part-3--set-up-new-yubikeys). Skip if you have a working YubiKey.

The remaining steps are only needed if you're setting up a new computer:

4. **Set up the computer's backup access**:
   [Part 4](#part-4--set-up-the-computers-backup-access).
5. **Make the recovery USB**: [Part 5](#part-5--make-the-recovery-usb). Skip if
   you have a working recovery USB.
6. **Install the computer** from that USB:
   [Part 6](#part-6--install-the-computer).
7. **Restore the computer's files** from backup:
   [Part 7](#part-7--restore-the-computers-files).

## Part 1 — Set up the borrowed computer

[Set up a computer for recovery](set-up-recovery-computer.md "embedded in the printed guide")

## Part 2 — Rebuild the GPG key from paper copy

Run this on either the borrowed computer or your working device.

[Restore the GPG key from paper](gpg-paper-recovery.md "embedded in the printed guide")

## Part 3 — Set up new YubiKeys

Still on the borrowed computer or the working device, with the root GPG key USB
and the new YubiKeys. Find the root GPG key USB with `lsblk` (Linux) or
`diskutil list external physical` (macOS) and run, from the repo:

```sh
bin/enroll-yubikeys /dev/sdX
```

It asks for the root GPG key's USB passphrase, then for the YubiKeys' new PINs,
then for each YubiKey to be plugged and provisioned in turn; type `done` after
the last one. On a Mac it first copies the whole root GPG key USB, which takes
a few minutes. If it renewed the subkeys, commit and push the public key as it
says.

On a working computer, the new YubiKeys now unlock its files, and you're done.

## Part 4 — Set up the computer's backup access

On the borrowed computer or the computer started from the recovery USB, with a
YubiKey plugged in. Choose the computer's name now; you type it in when
installing in Part 6.

[Add a machine's backup credentials](backup-credentials.md "embedded in the printed guide")

## Part 5 — Make the recovery USB

On the borrowed computer, with a YubiKey. Make a real-key build, with the
password store from Part 4:

```sh
bin/build-image --container --password-store ~/.local/share/password-store
```

[Build a recovery USB](build-recovery-usb.md "embedded in the printed guide")

## Part 6 — Install the computer

[Install a machine from a recovery USB](install-machine.md "embedded in the printed guide")

## Part 7 — Restore the computer's files

If you skipped Part 5 and installed from an older recovery USB, its system
doesn't have the backup access from Part 4 yet. Its copies of this repo and the
password store are as old as the USB, so get the latest of both, then update
the computer; it builds a new system, which can take a while, then restarts:

```sh
cd ~/Projects/arch-ansible
git pull
pass git pull
bin/update-system --reboot
```

[Restore user data from backup](restore-home.md "embedded in the printed guide")

## Afterwards

- On the borrowed computer, delete the `dr-out/` folder and the build cache:
  `podman volume rm arch-ansible-dr-cache` (or `docker volume rm`).
- Store the root GPG key USB and this guide in a safe place.

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

A curated subset of the 2FA accounts on the root GPG key USB. Each QR code holds
the `otpauth://` URI printed beneath it.

<!-- secret: totp -->
