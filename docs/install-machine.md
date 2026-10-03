# Install a machine from a recovery USB

Installs the image onto a machine's internal disk from a recovery USB built with
the real key ([build-recovery-usb.md](build-recovery-usb.md)). The image is
generic: each machine is named on its first boot, and per-machine traits are
detected from the hardware, so nothing needs adding to the repo first. How the
install and first boot work is in [bootstrapping.md](bootstrapping.md).

To restore the machine's home from backup right after its first login, add its
backup credentials before building the recovery USB
([backup-credentials.md](backup-credentials.md)).

## 1. Prepare the firmware

The first boot enrolls our Secure Boot key, which the firmware only accepts in
Secure Boot setup mode. On a machine that hasn't run our image before, enter the
firmware setup, clear the Secure Boot keys (often "Reset to Setup Mode" or
"Delete all Secure Boot keys"), and turn Secure Boot on. A machine that already
has our key needs nothing.

## 2. Install

Boot the recovery USB (usually through the firmware's boot menu key) and pick
the **Installer** profile. It starts a guided installer on the console: it lists
the eligible disks (every whole disk except the recovery USB), you pick one and
confirm, and it installs. Its menu can also drop to a shell, and the other
consoles log in as root, where the installer also runs directly:

```bash
install-system /dev/nvme0n1            # ERASES /dev/nvme0n1 and installs onto it
install-system --reboot /dev/nvme0n1   # ...and reboots into it when done
```

## 3. First boot

Remove the recovery USB and reboot into the installed disk. Its first boot:

1. **Enrolls the Secure Boot key** from the ESP.
2. **Provisions the disk**: the inactive `usr` slot, swap, root and home, with
   root and swap sealed to the TPM2.
3. **Asks for locale, timezone, hostname and root password.** The hostname
   prompt preselects a generated name like `arch-92a9-061c`. Accept it or type
   one; a machine whose backup credentials were added ahead of time needs the
   name used there. Rename later with `hostnamectl hostname <name>`.
4. **Waits for a YubiKey** to enroll on root and swap: insert it, enter its PIV
   PIN and touch it.
5. **Creates the encrypted home.**

## 4. First login

Log in as `mnussbaum`. The password is the image's baked home secret: switch to a
console (Ctrl+Alt+F2), log in as root with the password set at first boot, and
read it with

```
cat /usr/lib/credstore/home.new-password
```

It is also `pass linux_users/mnussbaum/recovery-key` wherever pass works.

First login runs `user-first-login-playbook.yml`. It enrolls the YubiKey on the
home (PIN and touch) and drops the password, so from then on the home unlocks
only with the YubiKey. It also sets up Wi-Fi from `pass` and clones this repo to
`~/Projects/arch-ansible` and the password store into the home.
