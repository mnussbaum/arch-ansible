# Restore the GPG key from paper

Use this when every YubiKey and both primary-key USBs are lost. It rebuilds the
primary GPG key from the printed [recovery guide](recovery-guide.md), then
writes a new primary-key USB and programs new YubiKeys.

You need: the printed recovery guide, a recovery USB to boot
([build-recovery-usb.md](build-recovery-usb.md)), a blank USB drive for the new
primary-key backup, and blank YubiKeys.

## Step 1 — Boot the Live System

Steps 2–5 run in the Live System of a recovery USB, which has every tool they
need. A recovery USB built with a throwaway key boots only with Secure Boot
disabled, so disable it in the firmware unless the machine already trusts the
recovery USB's key. Boot the recovery USB and pick **Live System (Recovery)**.

Log in as `mnussbaum` (`user.name` in `ansible/group_vars/all/vars.yml`). On a
recovery USB built with `--ephemeral-key`, the password is the one given to
`dr-build`. On any other recovery USB it is the image's baked home secret:
switch to a console (Ctrl+Alt+F2), which logs in as root, and read it with

```
cat /usr/lib/credstore/home.new-password
```

If no known Wi-Fi network is in range, connect with

```
iwctl station wlan0 connect <SSID>
```

## Step 2 — Reconstruct the GPG private key

The public key is already imported from the repo; check with `gpg --list-keys`.
If it is missing, type in the ASCII armor from [Public key](recovery-guide.md#public-key)
in the guide's appendix and import it:

```
cat > pubkey.asc        # type, then Ctrl-D
gpg --import pubkey.asc
```

Type the numbered lines from [Private key](recovery-guide.md#private-key) in the
guide's appendix into a file, and nothing else: a blank or comment line breaks
the checksum.

```
cat > secrets.txt       # type, then Ctrl-D
```

Paperkey holds only the secret bytes. Join them with the public key to rebuild
the full private key, then check that the key and all subkeys are present. Each
line ends in a checksum, so on a typo paperkey names the line to fix
(`CRC on line 5 does not match`):

```
gpg --export > pubkey.gpg
paperkey --pubring pubkey.gpg --secrets secrets.txt | gpg --import
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

## Step 4 — Update the password store and the repo

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

## Step 5 — Create a new primary-key USB and program new YubiKeys

Type the `otpauth://` URIs from [Critical TOTP accounts](recovery-guide.md#critical-totp-accounts)
in the guide's appendix into a file, one per line:

```
cat > ~/totp.txt        # type, then Ctrl-D
```

Find the blank USB drive for the primary-key backup (not the recovery USB) with
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
