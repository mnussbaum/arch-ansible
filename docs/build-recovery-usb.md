# Build a recovery USB on any Linux or macOS computer

When no machine of ours can build the image, any Linux or macOS computer with
podman or docker can. `bin/build-image --container` runs the whole build in an
Arch container, and `bin/burn-image` writes the result to a USB drive, making a
provisioned recovery USB ("recovery USB" below). It holds the same image
`bin/build-image` makes on our machines: installer, recovery system and
installed system in one ([bootstrapping.md](bootstrapping.md)).

There are two kinds of build:

- **Real key**, `bin/build-image --container`. It needs a YubiKey, which
  decrypts the Secure Boot key and the home recovery secret from `pass` and
  authenticates the clone of the password store from GitLab. The recovery USB
  boots under our machines' Secure Boot, installs machines, and carries the
  password store.
- **Throwaway key**, `bin/build-image --container --ephemeral-key`. It needs no
  YubiKey. It signs with a throwaway Secure Boot key that is in no machine's
  firmware, so boot it with Secure Boot disabled. It asks for a password for the
  user it starts with in place of the recovery secret in `pass`, and ships no
  password store. It can't update a machine installed from a real-key image.

## What you need

- A computer set up as in
  [set-up-recovery-computer.md](set-up-recovery-computer.md).
- A USB drive of 32G or more.
- For a real-key build, a YubiKey and its PIN.
- A few hours. A cold build downloads every package and compiles the AUR
  packages; on Apple Silicon everything runs under x86 emulation, which is
  several times slower. A rebuild reuses the caches and is much faster.

## 1. Build

Only committed changes are built: the container clones the checkout.

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
- Anything after `--` goes to `bin/build-image` in the container, e.g.
  `-- --skip-postinst`.

## 2. Write the recovery USB

The image lands in `dr-out/`. Find the USB drive and write it:

```sh
lsblk                                   # Linux: e.g. /dev/sdb
diskutil list external physical         # macOS: e.g. /dev/disk4
bin/burn-image dr-out/image_*_x86-64.raw /dev/sdb
```

`burn-image` refuses partitions, mounted devices (Linux) and internal disks
(macOS), and asks you to type the device path before erasing it.

The image is not secret-free: like every build, it carries the initial home
secret readable in its `/usr` (see `bin/_credstore_common.sh`). Installed homes
drop it at first login, but a home that hasn't had one yet opens with it. Delete
`dr-out/` after writing it.

Build caches persist in the `arch-ansible-dr-cache` volume. When you're done
with the computer, reclaim the space with `podman volume rm
arch-ansible-dr-cache` (or `docker volume rm`).
