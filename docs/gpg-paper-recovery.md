# Restore the GPG key from the paper recovery guide

Use this when every YubiKey and both primary GPG USBs are lost. The printed
recovery guide (`bin/generate-gpg-recovery-guide`, see README.md) holds the
primary key on paper and embeds these steps, so it can be followed without the
repo.

<!-- The recovery guide embeds everything below this line. -->

You need: the printed guide, a computer with internet, a USB drive of 32G or
more for this repo's image, a blank USB for the primary key backup, and blank
YubiKeys: building the image, unlocking disks and logging in all use one.

## Step 1 — Boot a Live System

Steps 2–5 run in the Live System of a provisioned recovery USB: a USB drive with
this repo's image written to it, called a recovery USB below. It has every tool
they need.

Use any existing recovery USB. Otherwise build one with a throwaway Secure Boot
key on any Linux or macOS machine with podman or docker. It takes a few hours,
and asks for a password for the Live System's user (`docs/disaster-recovery.md`,
"No YubiKey"):

```
git clone https://github.com/mnussbaum/arch-ansible.git && cd arch-ansible
bin/dr-build --ephemeral-key
bin/dr-burn dr-out/image_*_x86-64.raw /dev/sdX
```

Disable Secure Boot in the firmware, unless the machine already trusts the
recovery USB's key. Boot it and pick **Live System (Recovery)**.

Log in as your user. On a recovery USB built with `--ephemeral-key`, the
password is the one given to `dr-build`. On any other recovery USB it is the
image's baked home secret: switch to a console (Ctrl+Alt+F2), which logs in as
root, and read it with

```
cat /usr/lib/credstore/home.new-password
```

If no known Wi-Fi network is in range, connect with

```
iwctl station wlan0 connect <SSID>
```

## Step 2 — Reconstruct the GPG private key

The public key is already imported from the repo; check with `gpg --list-keys`.
If it is missing, type in the ASCII armor from the guide's "GPG Root Public Key"
section and import it:

```
cat > pubkey.asc        # paste, then Ctrl-D
gpg --import pubkey.asc
```

Type in the base64 from the guide's "GPG Root Private Key (paperkey format)"
section and decode it to raw bytes:

```
cat > secrets.b64       # paste, then Ctrl-D
base64 -d secrets.b64 > secrets.raw
```

Paperkey holds only the secret bytes. Join them with the public key to rebuild
the full private key, then check that the key and all subkeys are present:

```
gpg --export > pubkey.gpg
paperkey --pubring pubkey.gpg --secrets secrets.raw --input-type raw | gpg --import
gpg --list-secret-keys
```

## Step 3 — Set up SSH authentication via gpg-agent

gpg-agent already serves SSH. Register the authentication subkey with it, then
check GitHub and GitLab access:

```
gpg --with-keygrip --list-secret-keys \
  | awk '/\[A\]/{found=1} found && /Keygrip/{print $NF " 0"; exit}' >> ~/.gnupg/sshcontrol
ssh -T git@github.com
ssh -T git@gitlab.com
```

## Step 4 — Update the password store and Ansible repo

A recovery USB built with the real key carries both in your home; bring them up
to date:

```
git -C ~/.local/share/password-store pull
git -C ~/Projects/arch-ansible pull
```

A recovery USB built with `--ephemeral-key` has no password store; clone it:

```
git clone git@gitlab.com:mnussbaum/password-store.git ~/.local/share/password-store
```

Check that pass decrypts: `pass ls`, then `pass show` any entry.

## Step 5 — Create a new primary key USB and program new YubiKeys

Type the `otpauth://` URIs from the guide's "Critical 2FA / TOTP Accounts"
section into a file, one per line:

```
cat > ~/totp.txt        # type, then Ctrl-D
```

Find the blank USB for the primary key backup (not the recovery USB) with
`lsblk`, and run the restore script with it:

```
cd ~/Projects/arch-ansible
./bin/restore-primary-gpg-from-paper /dev/sdX ~/totp.txt
```

It renews the subkeys' expiry, backs up the key and TOTP seeds to the USB, and
programs any number of YubiKeys. With no YubiKey at hand, type `done` at the
first prompt to only create the USB backup, and program them later from that USB
with `./bin/enroll-yubikeys /dev/sdX`.

Commit and push the renewed public key, which the image build uses:

```
git commit -am 'Renew GPG subkeys' && git push
```

## Step 6 — Build the install medium and replace the machine

The build needs about 150G of disk, more than the Live System has. Run it on any
Linux or macOS machine with podman or docker, following
`docs/disaster-recovery.md`. With a YubiKey from Step 5 plugged in, build and
write the medium to the 32G USB drive, overwriting the Step 1 recovery USB if
you like (find it with `lsblk` or `diskutil list`):

```
git clone https://github.com/mnussbaum/arch-ansible.git && cd arch-ansible
bin/dr-build
bin/dr-burn dr-out/image_*_x86-64.raw /dev/sdX
```

Boot the target machine from it, pick **Installer**, and follow "Replacing a
lost or dead machine" in `docs/disaster-recovery.md`.
