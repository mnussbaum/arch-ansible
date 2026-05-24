# Bootstrapping

This document describes the complete lifecycle of images in this repository:
how they are built, signed, installed, what they do on first boot, how they
handle kernel updates, and how to use the USI for recovery.

---

## Image types

### Persistent images

A **persistent image** is a fully provisioned Arch Linux installation for a
specific physical host. Each host has its own `mkosi.images/<hostname>/`
directory containing a `mkosi.conf` with host-specific kernel command line and
partition UUIDs, a `mkosi.repart/` directory defining its partition layout, and
a `host_vars/<hostname>.yml` with Ansible variables.

Persistent images are written directly to the target disk and become the
machine's permanent operating system.

### USI (Unified System Image)

The **USI** is a bootable live environment written to a USB drive. It is built
from `mkosi.images/usi/` and serves two purposes:

1. **Installation**: build and write a persistent image to a target machine's disk
2. **Recovery**: mount an encrypted disk from an unbootable machine, chroot, and repair

The USI is a complete Arch Linux system with sway, Wi-Fi, and all the tools
needed for both roles. It carries Wi-Fi credentials for known networks so it
can reach the internet without configuration after booting. The arch-ansible
repository is baked into the USI at build time so no network access is required
to initiate an installation.

---

## Security model

Every image is built around the following chain of trust:

```
UEFI firmware (Secure Boot, custom keys)
  └── systemd-boot (signed with db key)
        └── UKI: kernel + initrd + cmdline (signed with db key)
              └── LUKS2 encrypted root (TPM2 PCR 7 auto-unlock, YubiKey fallback)
                    └── root filesystem
```

### Secure Boot

Custom Secure Boot keys are generated per-machine at image build time by
`ukify genkey`. The private key and certificate live at
`/etc/kernel/secure-boot-private-key.pem` and
`/etc/kernel/secure-boot-certificate.pem`.

`bootctl install --secure-boot-auto-enroll=yes` writes `PK.auth`, `KEK.auth`,
and `db.auth` to the ESP. A single signing key is enrolled at all three levels
(PK, KEK, db) — no separate platform or exchange keys. On first boot,
`secure-boot-enroll force` in `loader.conf` causes systemd-boot to pull these
files into firmware automatically without requiring a UEFI Setup Mode visit.

The bootloader binary at `/usr/lib/systemd/boot/efi/systemd-bootx64.efi` is
pre-signed at build time with `systemd-sbsign` so future `bootctl update`
invocations (triggered by systemd package updates) always copy the signed
`.efi.signed` version to the ESP rather than the unsigned one.

Microsoft certificates are **not** enrolled. All hardware used here has been
confirmed to not require them for firmware validation of option ROMs.

### Unified Kernel Images

All bootable content is packaged as UKIs: EFI binaries that embed the kernel,
initrd, and kernel command line in a single signed artifact. There is no
separate kernel or initrd on the ESP — only UKIs. This ensures:

- The kernel command line cannot be tampered with even with physical access
- systemd-boot discovers UKIs automatically from `/efi/EFI/Linux/`; no boot
  entries to maintain
- Signatures cover the complete boot artifact, not individual parts

UKIs are assembled by `ukify` via `kernel-install` using
`/etc/kernel/uki.conf`, which points at the per-machine signing keys. Every
UKI built by `kernel-install` is automatically signed.

### LUKS2 full disk encryption

The root partition is encrypted with LUKS2. Three unlock mechanisms are
enrolled:

| Slot | Type     | Unlock condition                                      |
| ---- | -------- | ----------------------------------------------------- |
| 0    | TPM2     | Boot chain intact (PCR 7 sealed to Secure Boot state) |
| 1    | FIDO2    | YubiKey — touch required                              |
| 2    | Recovery | Printed key, stored with GPG paper backup             |

No passphrase keyslot. The recovery key serves the "last resort" role without
being brute-forceable.

**TPM2 (slot 0)** unlocks automatically on every normal boot with no user
interaction. It is sealed to PCR 7, which reflects the Secure Boot state
(enrolled keys + enabled). Any change to Secure Boot keys invalidates this
slot; the disk falls back to YubiKey unlock, after which the slot is wiped and
a new one is enrolled.

**FIDO2/YubiKey (slot 1)** is used when TPM2 is unavailable: USI recovery
sessions, boots with Secure Boot disabled, or after Secure Boot key changes.
Each physical YubiKey gets its own independent keyslot. `bin/enroll-yubikeys`
handles enrollment.

**Recovery key (slot 2)** is generated at enrollment time, printed, and stored
with the machine's GPG paper backup. It is never stored digitally.

---

## Disk layout

All images use a two-partition layout:

```
Partition 1   vfat (FAT32)   ESP — systemd-boot + UKIs         1 GiB   /efi
Partition 2   LUKS2 → ext4   encrypted root filesystem          rest    /
```

The ESP is 1 GiB to accommodate multiple UKI versions (~100 MiB each: current
and previous).

Partition UUIDs are fixed per host in `host_vars/<hostname>.yml` and in
`mkosi.repart/`. The LUKS container is always opened as `cryptroot` via
`/etc/crypttab.initramfs`.

---

## Build chain from scratch

This is the full sequence for setting up a new machine when no existing
provisioned system is available.

### Step 1 — Build environment

All image building runs inside a Podman container defined by `Containerfile`.
The container includes mkosi, Ansible, and their Python dependencies.

```bash
podman build -t arch-ansible-builder .
```

The container requires `--privileged` because mkosi uses loop devices and
`systemd-nspawn` internally.

### Step 2 — Build the USI

```bash
podman run --privileged -v .:/work/src arch-ansible-builder bin/build-usi
```

This runs `mkosi --directory mkosi.images/usi`, which:

1. Installs Arch Linux packages into a disk image rootfs (kernel, systemd-boot,
   systemd-ukify, and all packages declared in `mkosi.common/mkosi.conf`)
2. Copies the arch-ansible repository into the image via `BuildSources=../`
3. Runs `mkosi.build` inside `systemd-nspawn`, which invokes `build-playbook.yml`
   via `bin/ansible` — configuring sway, networking, Wi-Fi credentials, fonts,
   and all user-facing software
4. During the Ansible run:
   - `ukify genkey` generates Secure Boot signing keys into the image
   - The bootloader binary is pre-signed with `systemd-sbsign`
   - `bootctl install --secure-boot-auto-enroll=yes` installs the bootloader
     and writes the `.auth` key enrollment files to the ESP
   - `kernel-install add` builds the initial signed UKIs
5. mkosi finalizes the disk image

With `Bootable=yes`, mkosi mounts the ESP inside the nspawn during the build
script phase, so steps 4 and 5 always run at build time. The resulting image
ships with a fully configured bootloader, signed UKIs, and key enrollment files
ready for firmware import on first boot.

Output is `$XDG_DATA_HOME/arch-images/usi.raw`.

### Step 3 — Write USI to USB

```bash
bin/build-usi /dev/sdX
```

`mkosi burn` writes the image and expands partitions to fill the device.
Alternatively build to file first:

```bash
bin/build-usi
dd if=$XDG_DATA_HOME/arch-images/usi.raw of=/dev/sdX bs=4M status=progress conv=fsync
```

### Step 4 — Boot USI and install persistent image

Boot the target machine from the USI USB. The USI connects to Wi-Fi
automatically. The arch-ansible repository is already present in the USI at
`~/src/arch-ansible`. From the USI environment, build and write the persistent
image for the target host:

```bash
cd ~/src/arch-ansible
bin/build-persistent-image <hostname> /dev/nvme0n1
```

`bin/build-persistent-image` runs `mkosi --directory mkosi.images/<hostname>`
and then `mkosi burn /dev/nvme0n1`, following the same build process as the
USI but targeting the host's specific configuration. The persistent image
includes the arch-ansible repository and has its own Secure Boot signing keys
generated at build time.

---

## First boot sequence

On first boot of a freshly written persistent image:

### 1. Secure Boot key enrollment

systemd-boot reads `loader.conf` and finds `secure-boot-enroll force`. It
reads `PK.auth`, `KEK.auth`, and `db.auth` from `/efi/loader/keys/auto/` and
writes them into the UEFI Secure Boot key databases before loading any OS. On
the next boot, Secure Boot is enforced with the machine's custom keys.

### 2. LUKS2 unlock — bootstrap keyslot

On the first boot, no TPM2 or YubiKey keyslots are enrolled yet. The LUKS2
container is opened using a key file embedded by mkosi's `Encrypt=key-file`
setting during image construction. This bootstrap keyslot is temporary and is
wiped after LUKS enrollment completes.

### 3. Firstboot service

On first login, a `firstboot.service` systemd oneshot unit runs `playbook.yml`
automatically. This configures all software, verifies that the Secure Boot
signing keys and bootloader are present (erroring if anything expected from the
build step is missing), rebuilds UKIs to incorporate any pending changes, and
marks itself complete so it does not run again.

### 4. LUKS2 key enrollment

LUKS enrollment cannot happen in the same boot as Secure Boot key enrollment:
PCR 7 only reaches its final stable value after Secure Boot is active with the
custom keys, which requires a reboot after step 1. The `luks-enroll.service`
oneshot unit handles this automatically — on the second boot (with Secure Boot
now active), it:

1. Enrolls a TPM2 keyslot sealed to PCR 7:
   ```bash
   systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 /dev/<root-partition>
   ```
2. Generates a recovery key and displays it on the console:
   ```bash
   systemd-cryptenroll --recovery-key /dev/<root-partition>
   ```
   **Print and store this with the machine's GPG paper backup.**
3. Wipes the bootstrap key-file slot written by mkosi:
   ```bash
   systemd-cryptenroll --wipe-slot=0 /dev/<root-partition>
   ```
4. Creates `/var/lib/luks-enrolled` so the service does not run again.

### 5. YubiKey enrollment

Run once per YubiKey (primary + backup). The YubiKey must be physically present:

```bash
bin/enroll-yubikeys
```

Each invocation enrolls one FIDO2 device into its own LUKS2 keyslot using
`systemd-cryptenroll --fido2-device=auto`.

### Final keyslot state

| Slot | Type     | Enrolled by                          |
| ---- | -------- | ------------------------------------ |
| 0    | TPM2     | `luks-enroll.service` (automatic)    |
| 1    | FIDO2    | `bin/enroll-yubikeys` (user-invoked) |
| 2    | Recovery | `luks-enroll.service` (printed)      |

---

## Kernel updates

Kernel updates are fully automatic. When `pacman -Syu` installs a new `linux`
package:

1. The `linux` package's `kernel-install` pacman hook fires
2. `kernel-install add <version> /boot/vmlinuz-linux` runs:
   - The mkinitcpio plugin regenerates the initrd
   - ukify assembles a new UKI from the kernel, initrd, and `/etc/kernel/cmdline`
   - ukify reads `/etc/kernel/uki.conf` and signs the UKI with the machine's
     `/etc/kernel/secure-boot-private-key.pem`
   - The signed UKI is placed in `/efi/EFI/Linux/`
3. On reboot, TPM2 auto-unlocks — PCR 7 is unchanged because the Secure Boot
   state (same enrolled keys, Secure Boot still enabled) has not changed

No manual steps. No re-enrollment required after kernel updates.

**systemd package updates** trigger `bootctl update` via
`systemd-boot-update.service` on reboot. `bootctl update` detects the
pre-signed `systemd-bootx64.efi.signed` in `/usr/lib/` and copies it to the
ESP rather than the unsigned binary.

**mkinitcpio configuration changes** from Ansible trigger the `Regenerate
mkinitcpio ramdisk` handler, which runs `mkinitcpio -p linux`. The updated
initrd is incorporated the next time `kernel-install add` runs (next kernel
update or manual invocation). A reboot is required.

---

## System recovery with USI

Boot the target machine from the USI USB. The TPM2 keyslot will not open the
target machine's disk (different boot session → different PCR 7 value). Use a
YubiKey or the recovery key.

### Open the encrypted disk and chroot

`bin/recovery-mount` automates disk discovery, unlocking, mounting, and
chrooting. Run it from the USI:

```bash
bin/recovery-mount
```

It attempts FIDO2 unlock first (prompts for YubiKey touch), then falls back to
prompting for the recovery key if no token succeeds. TPM2 fails silently in
this session since PCR 7 differs from the installed system's enrolled value.

To perform these steps manually:

```bash
# Unlock with enrolled tokens (FIDO2 prompts for YubiKey touch):
cryptsetup open --token-only /dev/<root-partition> cryptroot

# Or with the recovery key:
cryptsetup open /dev/<root-partition> cryptroot

mount /dev/mapper/cryptroot /mnt
mount /dev/<esp-partition> /mnt/efi
arch-chroot /mnt
```

### Common recovery tasks

**Rebuild UKIs** (e.g. after a failed kernel update):

```bash
ls /usr/lib/modules/ | xargs -I{} kernel-install add {} /boot/vmlinuz-linux
```

**Reinstall bootloader**:

```bash
bootctl install \
  --no-variables \
  --esp-path=/efi \
  --secure-boot-auto-enroll=yes \
  --certificate=/etc/kernel/secure-boot-certificate.pem \
  --private-key=/etc/kernel/secure-boot-private-key.pem
```

**Re-enroll TPM2** (after Secure Boot key change):

```bash
cryptsetup luksDump /dev/<root-partition>           # find TPM2 slot number
systemd-cryptenroll --wipe-slot=<n> /dev/<root-partition>  # auth via YubiKey
systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 /dev/<root-partition>
```

**Revoke a lost YubiKey**:

```bash
cryptsetup luksDump /dev/<root-partition>           # find FIDO2 slot number
systemd-cryptenroll --wipe-slot=<n> /dev/<root-partition>  # auth via remaining YubiKey
bin/enroll-yubikeys                                  # enroll replacement
```

### Secure Boot and the USI

The USI carries its own Secure Boot keys, generated at USI build time and
distinct from those enrolled in the target machine's firmware. To boot the USI
on a machine with custom Secure Boot keys active, there are two options:

**Option A — Sign the USI with the machine's db key (recommended):** The
machine's Secure Boot private key can be imported into a YubiKey PIV slot
(`ykman piv keys import 9c /etc/kernel/secure-boot-private-key.pem`). When
building the USI, `bin/build-usi` signs the USI's EFI binaries using that PIV
slot via `systemd-sbsign --private-key pkcs11:`. The signed USI boots normally
under the machine's custom Secure Boot without any firmware changes. The
private key never leaves hardware.

**Option B — Temporarily disable Secure Boot:** Disable Secure Boot in the
firmware, perform recovery, then re-enable it before rebooting into the
installed system. The TPM2 slot survives this cycle as long as the enrolled
keys are unchanged and Secure Boot is re-enabled before the next normal boot.

---

## YubiKey relay in QEMU

When running the QEMU image with `bin/run-qemu`, the host's pcscd socket is
forwarded into the VM over vsock so that GPG agent and SSH authentication inside
the VM can reach the YubiKey without USB passthrough. The relay uses `socat`
and requires the `vhost_vsock` kernel module on the host:

```bash
modprobe vhost_vsock
```

This relay also allows testing YubiKey LUKS enrollment flows inside the QEMU
VM before deploying to physical hardware.

---

## Adding a new host

`bin/add-host` scaffolds the required files for a new host. Run it and follow
the prompts; it generates a UUID, creates the host_vars, mkosi.conf,
mkosi.repart, and crypttab.initramfs files. To do it manually:

1. Add the host to `hosts.yml`
2. Create `host_vars/<hostname>.yml` with `disk.partition_uuid` (generate with
   `uuidgen`), `networking`, and other host-specific variables
3. Create `mkosi.images/<hostname>/mkosi.conf` with `KernelCommandLine=` for
   the target hardware
4. Create `mkosi.images/<hostname>/mkosi.repart/` with ESP and root partition
   definitions; set `UUID=` in the root partition to match `disk.partition_uuid`
5. Create `mkosi.images/<hostname>/mkosi.extra/etc/crypttab.initramfs` with the
   correct `PARTUUID=`
6. Build and install from the USI: `bin/build-persistent-image <hostname> /dev/sdX`

---

## Day-to-day configuration changes

Run `playbook.yml` from the target machine or via SSH. Changes that modify
`mkinitcpio.conf` or `/etc/kernel/cmdline` trigger a UKI rebuild automatically
via the Ansible handler; a reboot is required for those changes to take effect.
All other role changes apply live without a reboot.
