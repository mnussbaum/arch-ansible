# Disaster recovery

Where to start, by what was lost:

- **A machine** (lost, dead or wiped): add the replacement's backup credentials
  ([backup-credentials.md](backup-credentials.md)), build a recovery USB
  (`bin/build-image`, or [build-recovery-usb.md](build-recovery-usb.md) when no
  machine of ours can build one), install
  ([install-machine.md](install-machine.md)) and restore the home
  ([restore-home.md](restore-home.md)). A machine that won't boot can often be
  repaired from the recovery USB's Live System instead
  ([bootstrapping.md](bootstrapping.md), "System recovery").
- **A YubiKey, or every YubiKey**: [gpg-and-yubikeys.md](gpg-and-yubikeys.md),
  "Lost or blocked YubiKeys".
- **Every YubiKey and the primary-key USBs**: rebuild the key from the printed
  recovery guide ([gpg-paper-recovery.md](gpg-paper-recovery.md)).
- **Everything**: the printed recovery guide ([recovery-guide.md](recovery-guide.md))
  runs from nothing to a working laptop with its home restored.

## How `dr-build` works

- `container/Containerfile` is an Arch container holding the packages listed in
  `mkosi/mkosi.conf.d/20-builder.conf`, the same ones the image carries to
  rebuild itself; add build tools there, not to the Containerfile.
  It is x86_64 only, like the image; mkosi's `Architecture=` and pacman's are
  pinned, so emulation on an arm64 host can't change what gets built.
- `container/dr-unlock` imports the public key from
  `ansible/roles/gpg/files/gpg-pubkey.asc` into a throwaway GNUPGHOME, clones the
  password-store and decrypts the three build secrets. It runs in the container
  on Linux and on the host on macOS, so it sticks to bash 3.2.
- `container/dr-entrypoint` clones the mounted checkout, collects the secrets,
  and runs `bin/build-image` with `ARCH_ANSIBLE_SECRETS_DIR`, which makes it
  read them from there instead of from `pass`. With `ARCH_ANSIBLE_AUR_CHROOT=no`,
  `bin/sync-aur` builds AUR packages with plain `makepkg` in the throwaway
  container instead of an nspawn chroot, which is fragile inside a container.
- `bin/dr-burn` is a plain `dd`. `mkosi burn` adds only a backup GPT at the end
  of the USB drive, and systemd-repart puts one there on the medium's first boot.
