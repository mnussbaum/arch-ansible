# Restore the GPG key from paper

Use this when all root GPG key USBs are lost. It rebuilds the primary GPG key
from the printed [recovery guide](recovery-guide.md) and writes it to a new
root GPG key USB. Program YubiKeys from that USB afterwards
([gpg-and-yubikeys.md](gpg-and-yubikeys.md), "Provision new YubiKeys").

You need the printed recovery guide and a blank USB drive for the new root GPG
key. First get a terminal in the repo, in whichever of these ways fits.

## On a borrowed computer

Set it up as in [set-up-recovery-computer.md](set-up-recovery-computer.md),
open a terminal in the repo it cloned, then skip to "Rebuild the key" below.

## On a machine based on this repo that you can log in to

Open a terminal in `~/Projects/arch-ansible`, then skip to "Rebuild the key" below.

## From the recovery option

For a machine based on this repo that you can't log in to, or a borrowed
computer with a recovery USB:

1. Start the computer with the recovery USB plugged in, and boot into it from
   the BIOS. If it won't start from the USB, turn off Secure Boot in its
   firmware setup.
2. Pick the recovery option from its start-up menu.
3. Log in as `mnussbaum` (`user.name` in `ansible/group_vars/all/vars.yml`).
   The password is the image's baked home secret: switch to a console
   (Ctrl+Alt+F2), which logs in as root, and read it with `cat
/usr/lib/credstore/home.new-password`.
4. Connect to the internet. An ethernet cable works immediately. Or for Wi-Fi,
   open a terminal and run `iwctl`. In it, `device list` shows the Wi-Fi
   device's name (e.g. `wlan0`); then run `station wlan0 connect "<network
name>"` with that name, enter the network's password, and type `exit`.

## Rebuild the key

Find the blank USB drive for the root GPG key with `lsblk` (Linux) or
`diskutil list external physical` (macOS), and run the restore with it from the
repo:

```
bin/restore-primary-gpg-from-paper /dev/sdX
```

It asks you to type in, from the guide's appendix:

1. The numbered lines from the [Private
   key](recovery-guide.md#private-key) section. Type each line exactly
   as written, with its line number, the spaces between the pairs of
   characters, and its final six-character checksum; the indentation
   and upper or lower case don't matter. After the last line, press
   Enter, then Ctrl-D to finish. On a typo, paperkey names the line to
   fix (e.g. `CRC on line 5 does not match`) and the restore prints
   the file holding what you typed: open it with `nano <file>`, fix
   that line, save, and press Enter to try again.
2. The `otpauth://` URIs from [Critical TOTP
   accounts](recovery-guide.md#critical-totp-accounts), one per line.
   After the last one, press Enter, then Ctrl-D to finish; with none
   to enter, press Ctrl-D alone.

It then rebuilds the key and writes the new root GPG key USB, asking for a new
passphrase for it, then for the device path again before overwriting the USB
with the GPG data.
