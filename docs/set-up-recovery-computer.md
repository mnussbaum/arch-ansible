# Set up a Linux or macOS computer for recovery

Any Linux or macOS computer can stand in for machines based on this repo in a
recovery: it
rebuilds the GPG key from a paper ([gpg-paper-recovery.md](gpg-paper-recovery.md))
copy, programs YubiKeys, and builds a recovery USB in a container
([build-recovery-usb.md](build-recovery-usb.md)). This installs what those
need: the container runtime, and the GPG and YubiKey tools that run on the
computer itself.

It needs about 80G of free disk and 8G+ of memory for the container runtime.

## If you're on a Mac

Install Homebrew first if it's missing (see brew.sh), then open a new terminal,
so its newer bash comes first on the `PATH`:

```sh
xcode-select --install          # git
brew install bash gnupg ykman pass paperkey podman
podman machine init --rootful --cpus 8 --memory 16384 --disk-size 100
podman machine start
```

Homebrew's podman needs a Mac with an Apple chip. On an Intel Mac, install
podman from podman.io instead, and drop it from the `brew install` line.

## If you're on Linux

Install rootful podman or docker (the scripts use `sudo` when needed), gnupg
with its smart card daemon, ykman, pass, paperkey and cryptsetup, and start
pcscd. On Debian or Ubuntu:

```sh
sudo apt install podman git gnupg scdaemon yubikey-manager pass paperkey pcscd cryptsetup
```

On Fedora:

```sh
sudo dnf install podman git gnupg2 gnupg2-scdaemon yubikey-manager pass paperkey pcsc-lite cryptsetup
sudo systemctl enable --now pcscd.socket
```

Plug in the YubiKey after installing these, or unplug it and plug it back in:
the smart card daemon can't read a YubiKey that was plugged in before it was
installed.

## Clone the repo

```sh
git clone https://github.com/mnussbaum/arch-ansible.git
cd arch-ansible
```

Run the repo's commands from there
