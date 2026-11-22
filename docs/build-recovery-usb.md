# Build a recovery USB on any Linux or macOS computer

When no machine based on this repo can build the image, any Linux or macOS
computer with podman or docker can. `bin/build-image --container` runs the
whole build in an Arch container, and `bin/burn-image` writes the result to a
USB drive, making a provisioned recovery USB.

There are two kinds of build:

- **Real key**, `bin/build-image --container`. It needs a YubiKey, which
  decrypts the Secure Boot key and the home recovery secret from `pass` and
  authenticates the clone of the password store from GitLab. The recovery USB
  can install this repo's image onto new machines, and repair existing ones.
- **Throwaway key**, `bin/build-image --container --ephemeral-key`. It needs no
  YubiKey. It's for when no YubiKey is at hand to unlock the real key, but you
  still need a USB that starts a computer with this repo's tools, e.g. to
  rebuild the GPG key from paper or repair a machine that won't boot. It signs
  with a throwaway Secure Boot key, so boot it with Secure Boot disabled. It
  asks for a password for the user it starts with in place of the recovery
  secret in `pass`, and ships no password store. It can't update a machine
  installed from a real-key image.

## What you need

- A computer set up as in
  [set-up-recovery-computer.md](set-up-recovery-computer.md).
- A USB drive of 32G or more.
- For a real-key build, a YubiKey and its PIN.
- Time. A cold build can take a while: it downloads every package and compiles
  the AUR packages.

## 1. Build

For a real-key build, run the following, then insert the YubiKey when asked and
enter its PIN:

```sh
bin/build-image --container
```

The YubiKey authenticates the password-store clone over SSH and then decrypts
the secrets, on the computer itself before the container starts. The decrypted
secrets sit in `~/.dr-secrets.*` until the build ends. The build copies the
Secure Boot key into the cache volume while it runs, and deletes it when the
build ends, even a failed one. If the container is killed instead, remove the
volume.

For a throwaway-key build, run the following and give it a password for the
user it starts with:

```sh
bin/build-image --container --ephemeral-key
```

The throwaway key is minted once and kept in the cache volume.

Options worth knowing:

- `--password-store DIR` uses an existing copy of the store (e.g.
  `~/.local/share/password-store`, or one from a backup) instead of cloning it.
- `--password-store-url URL` clones from elsewhere, e.g. over HTTPS with a GitLab
  access token when SSH is unavailable.

## 2. Write the recovery USB

The image lands in `dr-out/`. Next we need to write it to a USB drive. Writing
it erases the USB drive, so find the drive's device name carefully: list the
drives with the USB unplugged, plug it in, and list them again. The drive that
appeared is the USB.

```sh
# On Linux:
lsblk -o NAME,SIZE,TRAN,MODEL
# On macOS:
diskutil list external physical
```

Check that the new entry matches the drive:

- **Size:** close to the size printed on the drive. A 32GB drive shows as about
  29G on Linux, and about 31 GB on macOS.
- **Whole drive:** use the drive itself, not a partition on it: `/dev/sdb`, not
  `/dev/sdb1`, on Linux; `/dev/disk4`, not `/dev/disk4s1`, on macOS. On Linux,
  add `/dev/` to the `NAME` column.

Then write it, with your device name in place of `/dev/sdb`:

```sh
bin/burn-image dr-out/image_*_x86-64.raw /dev/sdb
```

Delete `dr-out/` after writing it. Build caches persist in the
`arch-ansible-dr-cache` volume. When you're done with the computer, reclaim the
space with `podman volume rm arch-ansible-dr-cache` (or `docker volume rm`).
