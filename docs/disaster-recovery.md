# Disaster recovery: build a medium on someone else's machine

When no machine of ours can build the image, any Linux or macOS machine with
podman or docker can: `bin/dr-build` runs the whole build in an Arch container,
and `bin/dr-burn` writes the result to a USB stick. The medium is the same image
`bin/build-image` makes — installer, live/recovery system and installed system
in one (see `bootstrapping.md`).

## What to bring

- A YubiKey and its PIN. It decrypts the Secure Boot key and the homed recovery
  secret from `pass`, and authenticates the clone of the password-store from
  GitLab. Without one, see [No YubiKey](#no-yubikey).
- A USB stick of 32G or more.
- About 150G of free disk and 8G+ of memory for the container runtime, and a
  few hours. A cold build downloads every package and compiles the AUR
  packages; on Apple Silicon everything runs under x86 emulation, which is
  several times slower.

## 1. Set up the container runtime

**Linux.** Rootful podman or docker: `dr-build` uses `sudo` when needed. The
YubiKey is passed into the container, which runs its own pcscd, so stop the
host's first if it has one: `sudo systemctl stop pcscd.socket pcscd.service`.

**macOS.** Containers run in a Linux VM that can't reach USB devices, so the
YubiKey is used from macOS instead, and the stick is written from macOS too.

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

```sh
git clone https://github.com/mnussbaum/arch-ansible.git
cd arch-ansible
git checkout mkosi              # until mkosi is merged to master
bin/dr-build
```

Insert the YubiKey when asked and enter its PIN: it authenticates the
password-store clone over SSH and then decrypts the secrets. On macOS gnupg does this before the
container starts and the decrypted secrets sit in `~/.dr-secrets.*` until the
build ends; on Linux they're decrypted into the container's `/dev/shm`. Either
way the build copies the Secure Boot key into the cache volume while it runs,
and deletes it when the build ends, even a failed one. If the container is
killed instead, remove the volume.

The medium lands in `dr-out/`. Build caches persist in the `arch-ansible-dr-cache`
volume, so a rerun is much faster; `podman volume rm arch-ansible-dr-cache`
(or `docker volume rm`) reclaims the space afterwards.

The medium itself is not secret-free: like every build, it carries the
initial home secret readable in its `/usr` (see `bin/_credstore_common.sh`).
Installed homes drop it at first login, but a home that hasn't had one yet
opens with it. Delete `dr-out/` after burning.

Options worth knowing:

- `--password-store DIR` uses an existing copy of the store (e.g. from a backup)
  instead of cloning it.
- `--password-store-url URL` clones from elsewhere, e.g. over HTTPS with a GitLab
  access token when SSH is unavailable.
- Anything after `--` goes to `bin/build-image`, e.g. `-- --skip-postinst`.

Only committed changes are built: the container clones the checkout.

## 3. Write the stick

```sh
lsblk                                   # Linux: find the stick, e.g. /dev/sdb
diskutil list external physical         # macOS: e.g. /dev/disk4
bin/dr-burn dr-out/image_*_x86-64.raw /dev/sdb
```

It refuses partitions, mounted devices (Linux) and internal disks (macOS), and
asks you to type the device path before erasing it.

Then boot from the stick and carry on as in `bootstrapping.md`: install, or
**Live System (Recovery)** to reach an existing disk with `recovery-mount`.
The stick is signed with the same Secure Boot key as every installed machine,
so it boots under their Secure Boot as-is.

## Replacing a lost or dead machine

1. Build and burn a medium as above (or use an existing stick).
2. Boot it on the new machine, pick **Installer**, and install. The first boot
   enrolls Secure Boot, provisions the disk, asks for a hostname and root
   password, and waits for the YubiKey to enroll on root and swap
   (`bootstrapping.md`, "Disk encryption").
3. Log in with the home recovery secret (`pass linux_users/<user>/recovery-key`,
   or the password given to `--ephemeral-key`). First login enrolls the YubiKey
   on the home, drops the password and its keyslot, and runs the user
   playbook.
4. Give the machine Backblaze credentials and restore its home from restic
   (`bootstrapping.md`, "Backup credentials" and "Restoring data from backup").
   Restore before adding Syncthing folders.

## No YubiKey

`bin/dr-build --ephemeral-key` needs nothing but the container runtime. It
signs with a throwaway Secure Boot key (minted once and kept in the cache volume)
and asks for a password for the new home directory in place of the recovery
secret in `pass`. It ships no password-store unless given `--password-store` or
`--password-store-url`.

The result is a stopgap:

- Its key is in no machine's firmware. Boot it with Secure Boot disabled, or
  in setup mode so it enrolls its throwaway key.
- It can't update a machine installed from a real-key image.
- Once the YubiKey or the GPG key is back (`restore-primary-gpg-from-paper`),
  rebuild with the real key and re-enroll Secure Boot from setup mode.

## How it works

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
  of the stick, and systemd-repart puts one there on the medium's first boot.
