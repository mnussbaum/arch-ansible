# Install a machine from a recovery USB

These steps install the repo's built image onto a machine's internal disk from
a recovery USB built with the real key
([build-recovery-usb.md](build-recovery-usb.md)).

To restore the machine's home from backup right after its first login, add its
backup credentials before building the recovery USB
([backup-credentials.md](backup-credentials.md)).

## 1. Prepare the firmware

The first boot enrolls our Secure Boot key, which the firmware only accepts in
Secure Boot setup mode. On a machine that hasn't run this repo's image before,
enter the firmware setup, clear the Secure Boot keys (often "Reset to Setup
Mode" or "Delete all Secure Boot keys"), and turn Secure Boot on. A machine
that already has our key needs nothing.

## 2. Install

Start the machine from the recovery USB through its firmware's boot menu:

1. Plug in the recovery USB and turn the machine off.
2. Turn it on and, before any logo or loading screen goes away, press the boot
   menu key repeatedly. It's usually shown briefly on the first screen. It's
   normally the F12, F9 or F8 key.
3. In the menu that appears, pick the USB drive. It's usually listed by its
   brand, sometimes with "UEFI" in front.

If the machine starts normally instead, the key was too late or wrong: shut
down and try again. Failing that, enter the firmware setup (usually F2 or Del
before the logo shows) and move the USB drive to the top of the boot order.

From the recovery USB's start-up menu, pick the **Installer** profile. It
starts a guided installer on the console: it lists the eligible disks (every
whole disk except the recovery USB), you pick one and confirm, and it installs.
Its menu can also drop to a shell, and the other consoles log in as root, where
the installer also runs directly:

```bash
install-system /dev/nvme0n1            # ERASES /dev/nvme0n1 and installs onto it
install-system --reboot /dev/nvme0n1   # ...and reboots into it when done
```

## 3. First boot

Remove the recovery USB and reboot into the installed disk. Its first boot:

1. **Enrolls the Secure Boot key** from the ESP. If enrolling the PK fails with
   "Security Violation", enroll it from firmware setup: in the Secure Boot key
   management (e.g. Expert Key Management with Custom Mode enabled), replace
   the PK from file with `loader/keys/auto/PK.auth` on the internal disk's ESP,
   then reboot.
2. **Provisions the disk**: the `usr` slots, swap, root and home, with root and
   swap sealed to the TPM2.
3. **Asks for locale, timezone, hostname and root password.** The hostname
   prompt preselects a generated name like `arch-92a9-061c`. Accept it or type
   one; a machine whose backup credentials were added ahead of time needs the
   name used there.
4. **Waits for a YubiKey** to enroll on root and swap: insert it, enter its PIV
   PIN when prompted, and touch it when it flashes.
5. **Creates the encrypted home.**

## 4. First login

Log in as `mnussbaum`. The password is the image's baked home secret. If you
don't know the password, you can access its default value by switching to a
console by pressing Ctrl+Alt+F2, log in as root with the password you just set
at first boot, and read it with:

```
cat /usr/lib/credstore/home.new-password
```

It is also available with `pass linux_users/mnussbaum/recovery-key` wherever
pass works.

First login runs `user-first-login-playbook.yml`. It enrolls the YubiKey to
unlock user login, and drops the baked in default password, so from then on the
home unlocks only with the YubiKey. It sets up Wi-Fi from `pass`, clones this
repo to `~/Projects/arch-ansible`, and clones the password store into the home.

## 5. Firefox

To optionally load Firefox settings, start Firefox, and it will Sync settings
on first launch. Sign into your Firefox account, using browserpass to fill the
credentials from `pass`. Let the first sync finish, then in about:addons →
PersistentPin → Preferences turn on syncing and restart Firefox; it pins the
account's sites at startup.
