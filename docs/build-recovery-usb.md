# Build a recovery USB on any Linux or macOS computer

When no machine of ours can build the image, any Linux or macOS computer with
podman or docker can. `bin/dr-build` runs the whole build in an Arch container,
and `bin/dr-burn` writes the result to a USB drive, making a provisioned
recovery USB ("recovery USB" below). It holds the same image `bin/build-image`
makes: installer, Live System and installed system in one
([bootstrapping.md](bootstrapping.md)).

There are two kinds of build:

- **Real key**, `bin/dr-build`. It needs a YubiKey, which decrypts the Secure
  Boot key and the home recovery secret from `pass` and authenticates the clone
  of the password store from GitLab. The recovery USB boots under our machines'
  Secure Boot, installs machines, and carries the password store.
- **Throwaway key**, `bin/dr-build --ephemeral-key`. It needs nothing but the
  container runtime, and is a stopgap for when every YubiKey is lost: its Live
  System is where the GPG key is restored from paper
  ([gpg-paper-recovery.md](gpg-paper-recovery.md)). It signs with a throwaway
  Secure Boot key that is in no machine's firmware, so boot it with Secure Boot
  disabled. It asks for a password for the Live System's user in place of the
  recovery secret in `pass`, and ships no password store. It can't update a
  machine installed from a real-key image.

## What you need

- A USB drive of 32G or more.
- About 150G of free disk and 8G+ of memory for the container runtime, and a
  few hours. A cold build downloads every package and compiles the AUR
  packages; on Apple Silicon everything runs under x86 emulation, which is
  several times slower. A rebuild reuses the caches and is much faster.
- For a real-key build, a YubiKey and its PIN.

## 1. Set up the container runtime

**Linux.** Rootful podman or docker: `dr-build` uses `sudo` when needed. The
YubiKey is passed into the container, which runs its own pcscd, so stop the
host's first if it has one: `sudo systemctl stop pcscd.socket pcscd.service`.

**macOS.** Containers run in a Linux VM that can't reach USB devices, so the
YubiKey is used from macOS instead, and the recovery USB is written from macOS
too.

```sh
xcode-select --install          # git
brew install gnupg podman
podman machine init --rootful --cpus 8 --memory 16384 --disk-size 150
podman machine start
```

Docker Desktop or OrbStack work in place of podman: give them the same memory
and disk, and on Apple Silicon enable Rosetta for x86/amd64 emulation (Docker
Desktop: Settings → General). podman machine uses Rosetta automatically.

## 2. Build

Only committed changes are built: the container clones the checkout. Clone the
repo, or `git pull` an existing clone to pick up what was pushed since:

```sh
git clone https://github.com/mnussbaum/arch-ansible.git
cd arch-ansible
```

For a real-key build, run the following, then insert the YubiKey when asked and
enter its PIN:

```sh
bin/dr-build
```

The YubiKey authenticates the password-store clone over SSH and then decrypts
the secrets. On macOS gnupg does this before the container starts and the
decrypted secrets sit in `~/.dr-secrets.*` until the build ends; on Linux
they're decrypted into the container's `/dev/shm`. Either way the build copies
the Secure Boot key into the cache volume while it runs, and deletes it when
the build ends, even a failed one. If the container is killed instead, remove
the volume.

For a throwaway-key build, run the following and give it a password for the
Live System's user:

```sh
bin/dr-build --ephemeral-key
```

The throwaway key is minted once and kept in the cache volume.

Options worth knowing:

- `--password-store DIR` uses an existing copy of the store (e.g. from a backup)
  instead of cloning it.
- `--password-store-url URL` clones from elsewhere, e.g. over HTTPS with a GitLab
  access token when SSH is unavailable.
- Anything after `--` goes to `bin/build-image`, e.g. `-- --skip-postinst`.

## 3. Write the recovery USB

The image lands in `dr-out/`. Find the USB drive and write it:

```sh
lsblk                                   # Linux: e.g. /dev/sdb
diskutil list external physical         # macOS: e.g. /dev/disk4
bin/dr-burn dr-out/image_*_x86-64.raw /dev/sdb
```

`dr-burn` refuses partitions, mounted devices (Linux) and internal disks
(macOS), and asks you to type the device path before erasing it.

The image is not secret-free: like every build, it carries the initial home
secret readable in its `/usr` (see `bin/_credstore_common.sh`). Installed homes
drop it at first login, but a home that hasn't had one yet opens with it. Delete
`dr-out/` after writing it.

Build caches persist in the `arch-ansible-dr-cache` volume. When you're done
with the computer, reclaim the space with `podman volume rm
arch-ansible-dr-cache` (or `docker volume rm`).
