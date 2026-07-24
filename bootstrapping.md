# Bootstrapping

This document describes the complete lifecycle of the image in this repository:
how it is built, signed, installed, what it does on first boot, how it is
updated, and how to boot it as a recovery medium.

Parts of the intended design are not yet implemented; those are called out inline
and tracked in `bootstrapping-todo.md`.

---

## One image, three roles

There is a single, generically-built image — no per-host config is baked in.
Following the model in [Fitting Everything
Together](https://0pointer.net/blog/fitting-everything-together.html), the same
signed image is the installer, the live/recovery environment, and the installed
system. It ships only the immutable verity `/usr` plus an ESP; the encrypted
root/home are provisioned on first boot by `systemd-repart`. Which role it plays
is just a boot-menu choice (a UKI profile under `mkosi.uki-profiles/`), not a
separate build:

- **Installed system** — written to a machine's internal disk; the default
  profile self-provisions root/home on first boot and becomes the permanent OS.
  Machine identity is applied later: the hostname at boot (see below) and
  per-machine traits (monitors, VM guest/host role, etc.) from hardware/facts at
  firstboot.
- **Installer / live USB** — the same image written to a USB drive, used to
  bootstrap a new machine.
- **Recovery** — booted from that USB into the **Live System (Recovery)** profile
  (`mkosi.uki-profiles/15-live.conf`): a volatile root that masks the first-boot
  self-install, so it can mount and repair an unbootable machine's encrypted disk
  without provisioning itself.

The image is a complete Arch Linux system with sway, Wi-Fi, and all the tools
needed for these roles. It carries Wi-Fi credentials for known networks so it can
reach the internet without configuration after booting, and the arch-ansible
repository is baked in at build time so no network access is required to initiate
an installation.

---

## Security model

The image is built around the following chain of trust:

```
UEFI firmware (Secure Boot, custom keys)
  └── systemd-boot (signed)
        └── UKI: kernel + initrd + cmdline (signed)
              └── /usr: erofs + dm-verity (root hash in the signed cmdline)
                    └── encrypted root/swap (LUKS2, TPM2 PCR 7 auto-unlock)
```

### Secure Boot

A single software RSA-2048 keypair signs everything: the UKIs (Secure Boot), the
expected-PCR measurements, and the verity root hash. It is **not** generated
per-machine. The keypair lives in `pass` (encrypted to the GPG key, so GPG stays
the only root of trust); `bin/_secureboot_common.sh` materializes it to
`${ARCH_ANSIBLE_CACHE}/mkosi-secureboot/mkosi.{key,crt}` on every build, outside
the repo so the `ExtraTrees` sweep can't carry it into the plaintext `/usr`.
`bin/build-image` passes it to mkosi via `--secure-boot-key/--secure-boot-certificate`,
`--sign-expected-pcr-key/-certificate`, and `--verity-key/-certificate`.

mkosi (`SecureBoot=yes`) installs systemd-boot and writes the `PK`/`KEK`/`db`
auto-enroll files to the ESP. A single key is enrolled at all three levels — no
separate platform or exchange keys. On first boot, `secure-boot-enroll force` in
`mkosi.extra/efi/loader/loader.conf` causes systemd-boot to pull these into
firmware automatically without a UEFI Setup Mode visit. Microsoft certificates
are **not** enrolled; the hardware used here does not require them for option-ROM
validation.

> The key currently lives on disk because pkcs11-provider's CMS/PE signing paths
> (needed by `systemd-sbsign` and `systemd-repart`) don't yet work; once they do
> it can move to a YubiKey PIV slot. Per-machine signing / db-key import is not
> implemented — see `bootstrapping-todo.md`.

### Unified Kernel Images

All bootable content is packaged as UKIs: EFI binaries embedding the kernel,
initrd, and kernel command line in a single signed artifact. There is no separate
kernel or initrd on the ESP. This means the kernel command line — including the
verity root hash — cannot be tampered with, and signatures cover the whole boot
artifact. A single UKI carries multiple **profiles** (`mkosi.uki-profiles/`):
`default`, `live` (recovery), `emergency`, `factory-reset`, and
`factory-reset-with-tpm-clear`, each a boot-menu entry with its own cmdline.

### Immutable /usr (dm-verity)

The OS lives in a read-only `/usr` (erofs, zstd-compressed) protected by
dm-verity. The verity root hash is embedded in the signed UKI cmdline
(`root=dissect`, `mount.usr=dissect`), so the kernel only mounts a `/usr` whose
contents match the signed hash. `/usr` is laid out as A/B slots for atomic
updates (see [Updates](#updates)). `/etc` is seeded from
`/usr/share/factory/etc` (via `mkosi.finalize.factory-seed`) so it tracks `/usr`
across updates instead of freezing at first boot; per-host state (machine-id, ssh
host keys, shadow) is written into the writable `/etc` on first boot.

### Disk encryption

The root and swap partitions are LUKS2, created and TPM2-enrolled by
`systemd-repart` when it provisions them on first boot
(`mkosi.extra/usr/lib/repart.d/{40-swap,50-root}.conf`, `Encrypt=tpm2`). The TPM2
keyslot is sealed to PCR 7 (Secure Boot state), so a normal boot unlocks with no
interaction. `home` is a plain btrfs partition; per-user encryption is handled by
`systemd-homed` (a LUKS volume per home directory) on top of it, with a recovery
secret seeded into the credstore by `bin/_credstore_common.sh`.

> **Planned, not yet implemented:** FIDO2/YubiKey and printed-recovery-key
> keyslots on the root volume. `roles/systemd-boot/files/80-systemd-boot.preset`
> enables `firstboot.service` and `luks-enroll.service`, but those units are not
> defined anywhere yet, and there is no key-file bootstrap slot. `bin/enroll-yubikeys`
> and `bin/revoke-luks-yubikey` exist but are untested. See `bootstrapping-todo.md`.

---

## Partition layout

The **built image** contains only what is needed to boot and self-provision:

```
ESP            vfat        systemd-boot + UKIs                 ≥ 2 GiB   /efi
usr-verity-sig                signature over the verity hash
usr-verity                    dm-verity hash tree for /usr
usr            erofs        read-only /usr (the OS)
```

On **first boot**, `systemd-repart` (driven by `/usr/lib/repart.d/`) grows the
ESP and adds:

```
usr (B slot)               inactive A/B update slot (NoAuto)
swap           LUKS2/tpm2  4 GiB
root           btrfs/tpm2  encrypted root, /var subvolume    weight 3
home           btrfs       homed mounts per-user LUKS here    weight 1
```

The ESP is ≥ 2 GiB to hold two ~460 MiB UKIs at once during an A/B swap.
Partition UUIDs are not fixed per host: repart derives them from its seed. There
are no per-host partition definitions.

---

## Build chain from scratch

This is the full sequence for setting up a new machine when no existing
provisioned system is available.

### Step 1 — Build environment

mkosi runs on the host directly (`ToolsTree=/`). A `Containerfile` is provided to
run the build in Podman, but it is not yet verified end-to-end
(`bootstrapping-todo.md`); it would need `--privileged` because mkosi uses loop
devices and `systemd-nspawn`.

```bash
# optional, untested:
podman build -t arch-ansible-builder .
```

### Step 2 — Build the image

```bash
bin/build-image
```

`bin/build-image` materializes the Secure Boot keypair from `pass`, bumps
`mkosi.version` (a fresh monotonic version so each build supersedes the running
slot for sysupdate), and runs `mkosi build`, which:

1. Installs the Arch packages declared in `mkosi.conf` into the rootfs.
2. Copies the arch-ansible repository in via `BuildSources`/`ExtraTrees` (a
   tracked-files-only staging copy, so gitignored secrets don't reach `/usr`).
3. Runs the post-install (Ansible against the `build` identity) inside
   `systemd-nspawn` — configuring sway, networking, Wi-Fi credentials, fonts, and
   user-facing software.
4. Signs the bootloader and UKIs and writes the Secure Boot auto-enroll files to
   the ESP.
5. Builds the erofs `/usr`, its dm-verity hash + signature, and emits the disk
   plus split artifacts (`SplitArtifacts=partitions,uki`).

Output is under `~/.cache/mkosi/images/image/` (the split `.usr-*.raw`, `.efi`,
and the full `.raw`).

### Step 3 — Write the image to a USB

```bash
bin/burn-image /dev/sdX
```

`mkosi burn` writes the built image and expands partitions to fill the device. The
image is generic; each machine names itself on first boot (see *Per-machine runtime
config* below).

### Step 4 — Boot the USB and install to the target disk

Boot the target machine from the USB. It connects to Wi-Fi automatically and the
arch-ansible repository is already present at `/usr/share/arch-ansible`. Write the
same image to the target's internal disk:

```bash
bin/burn-image /dev/nvme0n1
```

On first boot the default profile self-provisions the encrypted root/home.

---

## First boot sequence

On first boot of a freshly installed image:

### 1. Secure Boot key enrollment

systemd-boot reads `loader.conf`, finds `secure-boot-enroll force`, reads the
`PK`/`KEK`/`db` auto-enroll files from the ESP, and writes them into the UEFI key
databases before loading any OS. On subsequent boots, Secure Boot is enforced with
the custom key.

### 2. Self-provisioning (systemd-repart)

The initrd runs `systemd-repart` against `/usr/lib/repart.d/`. It creates the
inactive `/usr` B slot, the encrypted swap, the encrypted btrfs root (with the
`/var` subvolume), and the home partition, sizing them to the disk. Root and swap
are LUKS2 with a TPM2 keyslot sealed to PCR 7, enrolled at creation time.

### 3. Per-machine runtime config

Per-machine traits (VM guest/host role from facts, network runtime, etc.) are
applied at firstboot from hardware/facts. The hostname is self-assigned: mkosi's
`Hostname=arch-????-????` is baked into os-release as `DEFAULT_HOSTNAME`, and systemd
replaces each `?` with a hex character hashed deterministically from the machine-id,
so every machine gets a unique, stable name (e.g. `arch-92a9-061c`) with no
per-machine input — whether it self-installs or is provisioned via the Installer
profile. Override with `hostnamectl hostname <name>`.

> **Not yet implemented:** the `firstboot.service` / `luks-enroll.service` flow
> the preset enables (FIDO2 + printed-recovery-key enrollment, bootstrap-slot
> wipe). TPM2/PCR 7 sealing across the Secure Boot enrollment boot has also not
> been verified against real firmware — see `bootstrapping-todo.md`. (`bin/run-image`
> works around the PCR 7 instability in QEMU by persisting the OVMF varstore and
> the emulated TPM across runs.)

---

## Updates

The OS updates by swapping the read-only `/usr` A/B slots, not by mutating a
running system — there are no in-place `pacman -Syu` kernel/`/usr` updates.

`bin/update-system` is the on-device path (there is no update server): it rebuilds
a fresh image version from this repo, drops the split artifacts into the staging
dir `/var/lib/arch-ansible/updates`, and runs `systemd-sysupdate
--transfer-source=<staging>` to install them to the inactive slot via the in-image
transfers (`usr`, `usr-verity`, `usr-verity-sig`, `uki`). It drives
`systemd-sysupdate` directly rather than `updatectl`/`systemd-sysupdated`, because
the transfers use `PathRelativeTo=explicit` and the source must be supplied with
`--transfer-source`, which `updatectl` can't pass.

```bash
bin/update-system            # build + apply to the inactive slot
bin/update-system --reboot   # ...and reboot into it
```

To update a machine that is installed but can't boot far enough to update itself
(e.g. a broken laptop), boot it from the live USB and point `update-system` at its
disk with `--image`. This rebuilds as above, then applies to the target's inactive
`usr` slot via the **volatile-root** mechanism — *not* `systemd-sysupdate
--image`, which fails to parse our `Type=regular-file` transfers through systemd
v261. It symlinks `/run/systemd/volatile-root` at a target *partition* in a
private mount namespace (so systemd treats the target as the system disk) and runs
`systemd-sysupdate --definitions=mkosi.sysupdate --transfer-source=<build output>
--offline update`, with `SYSTEMD_ESP_PATH` pointing the new UKI at the target's
own ESP. Nothing is dissected, so the TPM2-sealed LUKS root/home/swap are never
unlocked or touched (user data survives) — only the inactive `usr` slot and the
ESP are written. The target disk is the second disk in the guest under
`bin/run-image --device=` (`/dev/vdb`), or the physical disk node otherwise.
(Mechanism validated read-only; end-to-end write-test pending.)

```bash
bin/update-system --image=/dev/vdb   # offline-update an attached target disk
```

Because `/usr` is a single signed, verity-protected artifact, the kernel, initrd,
and userspace always move together. Boot counting / auto-rollback is driven by the
UKI's `TriesLeft=` (set in the `uki` transfer), so a failed boot falls back to the
prior slot automatically.

---

## System recovery

Boot the target machine from the USB and select **Live System (Recovery)** at the
boot menu. This boots a volatile root (`root=tmpfs`) that masks the first-boot
self-install, so it behaves like a rescue medium rather than provisioning itself.
The TPM2 keyslot will not open the target machine's disk (different boot session →
different PCR 7 value), so use a YubiKey or the recovery key.

In QEMU, `bin/run-image --device=<disk.raw>` emulates this: it boots the image as
the medium and attaches the disk as `/dev/vdb`; pick **Live System (Recovery)** at
the menu to repair it (or **Installer** to install onto it).

### Open the encrypted disk and chroot

`bin/recovery-mount` automates disk discovery, unlocking, mounting, and
chrooting. Run it from the live/recovery system:

```bash
bin/recovery-mount
```

It attempts FIDO2 unlock first (prompts for YubiKey touch), then falls back to
prompting for the recovery key if no token succeeds. TPM2 fails silently in this
session since PCR 7 differs from the installed system's enrolled value.

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

**Reinstall the bootloader and re-enroll Secure Boot keys** (materialize the key
from `pass` first, then):

```bash
bootctl install --no-variables --esp-path=/efi --secure-boot-auto-enroll=yes \
  --certificate="$SECUREBOOT_CERT" --private-key="$SECUREBOOT_KEY"
```

**Re-enroll TPM2** (after a Secure Boot key change):

```bash
cryptsetup luksDump /dev/<root-partition>                  # find TPM2 slot number
systemd-cryptenroll --wipe-slot=<n> /dev/<root-partition>  # auth via YubiKey/recovery
systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 /dev/<root-partition>
```

**Revoke a lost YubiKey** (untested — see `bootstrapping-todo.md`):

```bash
cryptsetup luksDump /dev/<root-partition>                  # find FIDO2 slot number
systemd-cryptenroll --wipe-slot=<n> /dev/<root-partition>  # auth via remaining YubiKey
bin/enroll-yubikeys                                        # enroll replacement
```

### Secure Boot and the recovery USB

A recovery USB carries its own Secure Boot key, distinct from the one enrolled in a
target machine's firmware. To boot it on a machine with custom Secure Boot keys
active, either:

- **Sign the recovery USB with the machine's db key** (planned, not implemented):
  import the key into a YubiKey PIV slot and have the build sign the EFI binaries
  via `systemd-sbsign --private-key pkcs11:`, so it boots under the machine's keys
  with no firmware changes. See `bootstrapping-todo.md`.
- **Temporarily disable Secure Boot** in firmware, perform recovery, then
  re-enable it before rebooting into the installed system. The TPM2 slot survives
  as long as the enrolled keys are unchanged and Secure Boot is re-enabled before
  the next normal boot.

---

## YubiKey relay in QEMU

When running an image in QEMU with `bin/run-image`, the host's pcscd socket is
forwarded into the VM over vsock so that GPG agent and SSH authentication inside
the VM can reach the YubiKey without USB passthrough. The relay uses `socat` and
requires the `vhost_vsock` kernel module on the host:

```bash
modprobe vhost_vsock
```

This also allows testing YubiKey LUKS enrollment flows inside the VM before
deploying to physical hardware.

---

## Adding a new host

All machines share the same generic image; each names itself at firstboot
(machine-id-derived) and per-machine traits are detected at firstboot. To provision
a new machine, build the image and burn it:

```bash
bin/build-image
bin/burn-image /dev/sdX
```

Build-time configuration that can't be detected at runtime goes in `group_vars`
or behind a runtime condition in the roles.

---

## Day-to-day configuration changes

Because `/usr` is read-only, OS-level changes are made by editing this repo and
rolling a new image with `bin/update-system` (which rebuilds and swaps the
inactive `/usr` slot), then rebooting into it. Writable state — `/etc`, `/home`,
and user-level configuration applied by `playbook.yml` — can still be changed live
on the running machine.
