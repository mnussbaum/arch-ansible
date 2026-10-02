# Plan: Migrate to systemd-boot + LUKS2 (no LVM)

## Goals

- Replace GRUB with systemd-boot
- Drop the separate GRUB boot partition (EFI partition alone is sufficient)
- Replace LUKS+LVM with LUKS2 directly on the root partition (no LVM layer)
- Produce UKIs (Unified Kernel Images) — prerequisite for Secure Boot
- Enable Secure Boot with custom keys via `sbctl`
- TPM2-based automatic disk unlock sealed to PCR 7 (Secure Boot state) — survives kernel updates without re-enrollment
- YubiKey FIDO2 as fallback unlock; recovery key as last resort (no passphrase keyslot)
- Keep hibernation (swapfile resume)
- Keep QEMU and physical machines on the same partition layout

---

## Current layout (3 partitions)

```
/dev/sdX1  vfat    EFI           /boot/efi
/dev/sdX2  ext4    GRUB boot     /boot
/dev/sdX3  LUKS → LVM (vgcrypt) → ext4    /
```

## Target layout (2 partitions)

```
/dev/sdX1  vfat    EFI + UKIs    /efi
/dev/sdX2  LUKS2 → ext4          /
```

The EFI partition grows to 1GB to hold UKI images (each is ~100MB, want room for
current + previous + fallback). The boot partition disappears entirely — systemd-boot
and UKIs live on the ESP.

---

## Changes

### 1. New role: `systemd-boot` (replaces `grub` + `grub-theme`)

Tasks:

- Install `bootctl` (part of `systemd`, already present) and `sbctl`
- `bootctl install` during bootstrap only (when `bootstrap == "true"`)
- Write `/efi/loader/loader.conf`:
  ```
  default @saved
  timeout 5
  console-mode auto
  editor no
  ```
- Write `/etc/kernel/cmdline` — the UKI embeds this at build time:
  ```
  rd.luks.name=<root-partition-UUID>=cryptroot root=/dev/mapper/cryptroot rw quiet
  resume=/dev/mapper/cryptroot resume_offset={{ swapfile_offset.stdout }}
  ```
  Template this from host vars (UUID, NVMe `pcie_aspm=force` flag). Skip
  `resume=` and `resume_offset=` when `ansible_facts["virtualization_role"] == "guest"`
  — same conditional as the current `grub.j2`.
- Set up Secure Boot signing (see section 8 below)

Remove: `grub`, `grub-bios`, `os-prober` packages. `os-prober` is not needed —
the Windows partitions on physical hosts are vestigial and unused. Keep
`intel-ucode` (embedded in UKI via the `microcode` mkinitcpio hook).

### 2. `mkinitcpio` role changes

Switch from udev-based to systemd-based hooks. Affects `mkinitcpio.conf.j2`:

```
# Before
HOOKS=(base udev autodetect microcode modconf block consolefont keymap keyboard encrypt resume lvm2 filesystems fsck)

# After
HOOKS=(base systemd autodetect microcode modconf sd-vconsole keyboard block sd-encrypt filesystems fsck)
```

Key changes:

- `udev` → `systemd` (systemd-based initrd, required for sd-encrypt)
- `encrypt` → `sd-encrypt` (reads `rd.luks.name=` from cmdline, not `cryptdevice=`)
- `lvm2` removed (no LVM)
- `resume` removed (systemd initrd handles resume automatically via `resume=` cmdline)
- `consolefont` → `sd-vconsole`

Add a mkinitcpio preset for UKI output alongside the standard initramfs.
Create `/etc/mkinitcpio.d/<hostname>.preset` (or use the default `linux.preset`):

```
ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-linux"
PRESETS=('default' 'fallback')
default_uki="/efi/EFI/Linux/arch-linux.efi"
default_options=""
fallback_uki="/efi/EFI/Linux/arch-linux-fallback.efi"
fallback_options="-S autodetect"
```

Both UKIs are written directly to the ESP so systemd-boot auto-discovers them
and sbctl's pacman hook re-signs both after every kernel update. The fallback
preset skips the `autodetect` hook — it includes a wider driver set, making it
useful when the default UKI fails to boot. The fallback entry only appears in
the boot menu (5 second timeout) so it adds no friction to normal boots.

Also add `sbctl sign -s /efi/EFI/Linux/arch-linux-fallback.efi` to the Secure
Boot signing tasks in section 8 so the fallback UKI is in sbctl's database from
the start.

### 3. `swap` role changes

No structural change. The `resume_offset` calculation stays the same.
The offset value is consumed by the `systemd-boot` role (written into
`/etc/kernel/cmdline`) instead of the `grub` role.

The `swap` role must run before the `systemd-boot` role so the offset is
available when the cmdline template renders.

### 4. `host_vars` changes (all x86 hosts)

Remove the `boot` partition entry entirely.

Root partition: remove `volume_group_name`, `logical_volume_name`. Update
`logical_device` to `/dev/mapper/cryptroot` (consistent name across all hosts,
derived from `rd.luks.name=<UUID>=cryptroot`). Add a `luks_uuid` field — needed
to write `rd.luks.name=` into `/etc/kernel/cmdline`.

EFI partition: change `mount_point` from `/mnt/boot/efi` to `/mnt/efi`
(and on running systems `/efi`). Grow `end` to cover 1GiB.

Example diff for `host_vars/qemu.yml`:

```yaml
# Remove entirely:
#   boot: { ... }

partitions:
  efi:
    end: 1025MiB # was 261MiB
    mount_point: /mnt/efi # was /mnt/boot/efi
    # rest unchanged
  root:
    partition_device: /dev/sda2 # was sda3
    logical_device: /dev/mapper/cryptroot # was /dev/mapper/vgcrypt-root
    luks_uuid: "<uuid>" # new field
    # remove: volume_group_name, logical_volume_name
```

Physical hosts (bodie, tecopa, pahrump) keep their existing partition numbers
since earlier slots are occupied by legacy Windows partitions (vestigial — not
used). Only the Arch-managed partitions change.

### 5. Bootstrapping changes

**`create-partitions.yml`**: remove the `boot` partition from the loop (it
will no longer appear in `host_vars`).

**`luks-format-and-open.yml`**: LUKS2 is already the default in modern
`cryptsetup`, so `luks_device` module requires no format change. Update the
opened device name from `{{ item.volume_group_name }}` to `cryptroot`
(or derive from a new host var). Remove the low-memory `pbkdf` override for
x86 hosts (keep it for Pi). Capture the LUKS UUID after format for use in
`/etc/kernel/cmdline`.

**`setup-lvm.yml`**: delete this file. Remove its inclusion from the
bootstrap flow.

**`mount-partitions.yml`**: now mounts 2 partitions instead of 3. Sort
order stays the same (root first, then ESP). Update EFI mount point to `/efi`.

**`bootstrap.yml`**: remove the `efivars` bind mount step — `bootctl install`
reads efivars directly and does not need it bind-mounted.

### 6. `playbook.yml` changes

- Replace `import_role: grub` + `import_role: grub-theme` with `import_role: systemd-boot`
- Remove `when: grub` guards (or invert to `when: systemd_boot` if GRUB support
  needs to remain for any host — currently only QEMU and physical hosts use it,
  the live ISO already skips it)
- The `swap` import must precede `systemd-boot` (already the case since swap
  comes before grub currently)

### 7. Existing machine migration

The partition layout change is destructive: the GRUB boot partition must be
deleted and the root partition recreated without LVM. **No in-place migration.**

For each physical machine:

1. Back up data (already handled by `backup` role + Backblaze)
2. Boot live USB
3. Wipe and reinstall with new bootstrap flow

QEMU image is clean-slate — no migration concern.

### 8. Secure Boot setup (in `systemd-boot` role)

Secure Boot signing happens in two phases: automated Ansible steps and one
manual UEFI step per machine that requires physical interaction.

**Automated (Ansible):**

- Install `sbctl`
- `sbctl create-keys` — generates Platform Key, KEK, and DB keypair under
  `/usr/share/secureboot/`. Idempotent (no-op if keys exist).
- `sbctl sign -s /efi/EFI/systemd/systemd-bootx64.efi` — sign the bootloader
- `sbctl sign -s /efi/EFI/BOOT/BOOTX64.EFI` — sign the fallback EFI binary
- `sbctl sign -s /efi/EFI/Linux/arch-linux.efi` — sign the default UKI
- `sbctl sign -s /efi/EFI/Linux/arch-linux-fallback.efi` — sign the fallback UKI
  The `-s` flag adds each path to sbctl's database; the pacman hook
  `zz-sbctl.hook` (installed by the sbctl package) re-signs all database entries
  on every kernel update automatically.

**Manual (once per machine, post-install):**

1. Reboot into UEFI firmware, enable Setup Mode (clears existing PK)
2. Back in the running system: `sbctl enroll-keys --microsoft`
   The `--microsoft` flag includes Microsoft's UEFI CA alongside your own keys —
   required for firmware that validates option ROMs (GPU, NVMe controllers).
3. Reboot — Secure Boot is now enforced.

This step cannot be automated in Ansible because it requires the UEFI to be in
Setup Mode, which requires a physical firmware interaction. Document it as a
post-install checklist item.

**QEMU note:** OVMF supports Secure Boot. To test before doing it on physical
hardware, boot the QEMU VM, enter the OVMF setup menu (F2), enable Setup Mode
there, then run `sbctl enroll-keys --microsoft` inside the VM.

### 9. LUKS2 keyslot setup

Enrollment is split into two phases. TPM2 must be enrolled _after_ Secure Boot
is active with your keys — PCR 7's value changes when keys are enrolled and
Secure Boot is enabled, so enrolling against the wrong PCR 7 state means the
TPM will refuse every subsequent boot. The UEFI Setup Mode step is the wall
that cannot be automated.

**Phase 1 — Manual (once per machine):**

1. Boot the installed system (Secure Boot still disabled, GRUB → systemd-boot
   migration complete)
2. Enter UEFI firmware → enable Setup Mode (clears existing PK)
3. Back in the running system: `sbctl enroll-keys --microsoft`
4. Reboot — Secure Boot now active

**Phase 2 — Automatic (systemd oneshot service in `systemd-boot` role):**

The role deploys a oneshot service that runs on every boot until it succeeds,
gated by two conditions: Secure Boot must be active, and a marker file must not
yet exist.

```ini
# /etc/systemd/system/luks-enroll.service
[Unit]
Description=Enroll LUKS2 TPM2 and recovery key on first Secure Boot boot
ConditionPathExists=!/var/lib/luks-enrolled
After=local-fs.target systemd-cryptsetup@cryptroot.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/luks-enroll
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

```bash
# /usr/local/bin/luks-enroll
#!/bin/bash
set -euo pipefail

# Wait until Secure Boot is active — exit silently if not yet enrolled.
# Service will retry on next boot (marker file absent).
if ! bootctl status 2>/dev/null | grep -q "Secure Boot: enabled"; then
  echo "Secure Boot not active — skipping LUKS enrollment until next boot"
  exit 0
fi

DEVICE="{{ partitions.root.partition_device }}"  # templated by Ansible

echo "=== Enrolling TPM2 keyslot (PCR 7) ==="
systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 "$DEVICE"

echo "=== Enrolling recovery key ==="
RECOVERY_KEY_FILE=/root/luks-recovery-key.txt
systemd-cryptenroll --recovery-key "$DEVICE" | tee "$RECOVERY_KEY_FILE"
chmod 600 "$RECOVERY_KEY_FILE"
echo "Recovery key written to $RECOVERY_KEY_FILE — print and store with GPG paper backup, then delete"

echo "=== Removing bootstrap passphrase keyslot ==="
# Slot 0 is the passphrase set during cryptsetup luksFormat at bootstrap.
# TPM2 authenticates this wipe automatically.
systemd-cryptenroll --wipe-slot=0 "$DEVICE"

touch /var/lib/luks-enrolled
echo "=== LUKS enrollment complete. Run enroll-yubikey to add YubiKey fallback slots. ==="
```

The script is templated by Ansible so `DEVICE` resolves to the correct
partition path per host.

**YubiKey enrollment — user-invoked script:**

YubiKey enrollment is left as an explicit user step because it requires the key
to be physically plugged in and touched. The role installs a helper:

```bash
# /usr/local/bin/enroll-yubikey  (installed by systemd-boot role, mode 0755)
#!/bin/bash
set -euo pipefail
DEVICE="{{ partitions.root.partition_device }}"
echo "Plug in YubiKey and press enter..."
read -r
systemd-cryptenroll --fido2-device=auto "$DEVICE"
echo "Done. Run again for each additional YubiKey."
```

Run once per YubiKey. Each gets its own independent LUKS2 keyslot.

**Revoking a lost YubiKey:**

```bash
cryptsetup luksDump /dev/nvme0n1p2   # identify the slot number
systemd-cryptenroll --wipe-slot=<n> /dev/nvme0n1p2  # TPM2 authenticates
enroll-yubikey  # enroll replacement
```

**Final keyslot layout:**

| Slot | Type         | Unlock condition                              |
| ---- | ------------ | --------------------------------------------- |
| 0    | TPM2 (PCR 7) | Boot chain intact — automatic, no interaction |
| 1    | FIDO2        | YubiKey primary — touch required              |
| 2    | FIDO2        | YubiKey backup — touch required               |
| 3    | Recovery key | Printed, stored with GPG paper backup         |

No passphrase keyslot. The recovery key fills the same "last resort" role
without being brute-forceable or coercible.

**Required packages:** `tpm2-tss` (TPM2 support in initrd), `libfido2` (FIDO2
support in initrd). Add both to the `systemd-boot` role's package list so
`systemd-cryptsetup` can attempt those keyslots during boot.

### 10. Day-to-day operations

**Package updates (`pacman -Syu`):** fully transparent. Three pacman hooks fire
automatically on kernel updates:

1. mkinitcpio rebuilds both UKIs (default + fallback)
2. `zz-sbctl.hook` re-signs both
3. On reboot: TPM2 unlocks automatically (PCR 7 unchanged — Secure Boot state
   did not change)

Non-kernel and `systemd` package updates follow the same pattern via their own
hooks. No manual steps at any point.

**Ansible configuration changes:** only changes that affect UKI contents require
a rebuild and reboot. The `mkinitcpio` role handler already triggers a rebuild;
it needs an explicit `sbctl sign` step added for non-kernel-triggered rebuilds
(where the pacman hook does not fire). Everything else applies live as today.

| Change                             | Rebuild needed                                 | Reboot needed |
| ---------------------------------- | ---------------------------------------------- | ------------- |
| `/etc/kernel/cmdline`              | Yes — handler triggers mkinitcpio + sbctl sign | Yes           |
| `mkinitcpio.conf` (hooks, modules) | Yes — handler triggers mkinitcpio + sbctl sign | Yes           |
| All other roles                    | No                                             | Same as today |

**Re-enrolling Secure Boot keys (rare):** changes PCR 7, invalidates the TPM2
keyslot. The disk falls back to YubiKey on next boot. After re-enrollment:

```bash
systemd-cryptenroll --wipe-slot=<tpm2-slot> /dev/nvme0n1p2  # YubiKey authenticates
systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 /dev/nvme0n1p2
```

### 11. Live USB Secure Boot signing (`build-live-iso.yml`)

The custom live USB must boot under your enrolled Secure Boot keys so it can be
used for repair without temporarily disabling Secure Boot — which would change
PCR 7 and invalidate the TPM2 keyslot, requiring re-enrollment afterward.

**Problem 1:** The EFI binaries in the ISO are finalized by `mkarchiso` after
`customize_airootfs.sh` completes. They cannot be signed inside the chroot
because they don't exist at that point in the build.

**Problem 2:** The live USB may need to be built on a borrowed machine that
does not have the sbctl DB key in `/usr/share/secureboot/`.

**Solution:** Store the Secure Boot DB signing key in the YubiKey's PIV slot.
`sbsign` supports PKCS#11 tokens, so the key is available on any machine with
your YubiKey and `opensc` installed, without the private key ever leaving the
hardware. `build-live-iso.yml` detects which signing method is available and
uses accordingly.

**One-time setup — import DB key into YubiKey PIV:**

```bash
# Import the sbctl DB key into PIV slot 9c (Digital Signature slot)
ykman piv keys import 9c /usr/share/secureboot/keys/db/db.key
ykman piv certificates import 9c /usr/share/secureboot/keys/db/db.crt
```

After import, the private key in `/usr/share/secureboot/keys/db/db.key` can be
deleted from disk — the YubiKey is now the sole holder. `sbctl` operations on
your own machines continue to work because sbctl can be configured to use
PKCS#11, or the local key file is kept as a convenience copy only (lower risk
since the machine is itself encrypted).

**Post-build signing step in `build-live-iso.yml`:**

Add after the `Build ISO` task:

```yaml
- name: Live USB | Sign EFI binaries in ISO
  become: true
  script: bin/sign-live-iso "{{ item.path }}" "{{ iso_build_dir }}/signed.iso"
  loop: "{{ built_images.files }}"

- name: Live USB | Replace unsigned ISO with signed ISO
  become: true
  command: mv "{{ iso_build_dir }}/signed.iso" "{{ item.path }}"
  loop: "{{ built_images.files }}"
```

**`bin/sign-live-iso` script:**

```bash
#!/bin/bash
# Signs EFI binaries in an archiso ISO using either the local sbctl DB key
# or the YubiKey PIV slot (PKCS#11), whichever is available.
set -euo pipefail

UNSIGNED_ISO=$1
SIGNED_ISO=$2

WORK=$(mktemp -d)
trap "rm -rf $WORK" EXIT

LOCAL_KEY=/usr/share/secureboot/keys/db/db.key
LOCAL_CRT=/usr/share/secureboot/keys/db/db.crt
PKCS11_URI="pkcs11:manufacturer=piv_II;id=%02"  # PIV slot 9c

# Determine signing method
if [[ -f "$LOCAL_KEY" ]]; then
  sign() { sbsign --key "$LOCAL_KEY" --cert "$LOCAL_CRT" --output "$1" "$1"; }
  echo "Signing with local sbctl DB key"
elif ykman piv info &>/dev/null 2>&1; then
  sign() { sbsign --engine pkcs11 --key "$PKCS11_URI" --cert "$LOCAL_CRT" --output "$1" "$1"; }
  echo "Signing with YubiKey PIV slot (touch may be required)"
else
  echo "ERROR: no signing key available. Need either local sbctl DB key or YubiKey." >&2
  exit 1
fi

# Extract ISO, sign EFI binaries, repack
xorriso -indev "$UNSIGNED_ISO" -osirrox on -extract / "$WORK/extracted" 2>/dev/null
find "$WORK/extracted/EFI" -name "*.efi" | while read -r efi; do
  sign "$efi"
done
xorriso -indev "$UNSIGNED_ISO" \
        -outdev "$SIGNED_ISO" \
        -boot_image any replay \
        -map "$WORK/extracted/EFI" /EFI
```

**Required packages on the build machine:** `xorriso`, `sbsigntool` (`sbsign`),
`opensc` (for PKCS#11/YubiKey path), `ykman` (for PIV detection). Add to the
`archiso` role's package list so they are present on any provisioned machine.
A borrowed machine running a standard distro will need them installed manually,
but that is a one-line `apt`/`pacman` invocation.

**Accessing the encrypted root from the live USB:**

Even with the live USB booting under Secure Boot, PCR 7 differs from the
installed system's enrolled value (different boot session). The TPM2 keyslot
will refuse. Unlock with a FIDO2 YubiKey or the recovery key:

```bash
# Try enrolled tokens — TPM2 fails silently, FIDO2 prompts for YubiKey touch
cryptsetup open --token-only /dev/nvme0n1p2 cryptroot

# Or explicitly with recovery key
cryptsetup open /dev/nvme0n1p2 cryptroot
```

Then `arch-chroot /mnt` as normal.

---

## Future: image-based installs with systemd-homed + Restic

Not in scope for the current plan but the natural next step if pursuing mkosi
image-based installs. Captured here to record the intended design.

### Why Syncthing is a poor fit for machine restore

Syncthing is a good ongoing cross-machine sync tool but a poor restore mechanism
because it requires another machine to be online and reachable. On a fresh
install with no other machine available — borrowing a friend's laptop, setting
up a new primary machine before decommissioning the old one — there is nothing
to sync from. A durable, pull-based backup store (Restic on Backblaze or a
local drive) has no such dependency.

### The design

**systemd-homed** manages the user's home directory as a portable LUKS2-encrypted
image file (`/var/lib/systemd/home/mnussbaum.home`). The home is only decrypted
and mounted when the user actively logs in — unlocked with the FIDO2 YubiKey
(same key, separate homed keyslot). This adds a meaningful security property
beyond whole-disk LUKS2: even on a running unattended machine where the disk has
been TPM-unlocked, the home directory remains encrypted until the user
authenticates.

**Restic** backs up the _contents_ of the mounted home (not the `.home` image
blob). Backing up the raw image blob would defeat Restic's deduplication and
produce large undiffable snapshots. Backing up file contents works normally —
Restic sees the home as a regular directory once mounted.

**Partition layout** gains a dedicated data partition:

```
/dev/sdX1  vfat       EFI + UKIs          /efi      (1GB)
/dev/sdX2  LUKS2      OS root             /         (remainder minus data)
/dev/sdX3  LUKS2      homed data store    /var/lib/systemd/home
```

The data partition has its own LUKS2 keyslot enrolled to the YubiKey (not TPM2
— it should only decrypt when the user is present, which is the same condition
under which homed unlocks the home image inside it). The OS root continues to
use TPM2 for automatic unlock.

### Restore flow on a fresh machine

1. Deploy OS image (mkosi-built or fresh bootstrap) — TPM2 enrolled, Secure
   Boot active
2. Format and mount the data partition, or attach an existing one from the old
   machine
3. If restoring from Backblaze (no existing data partition):
   ```bash
   homectl create mnussbaum --fido2-device=auto   # creates empty home, enrolls YubiKey
   login                                           # mounts home via YubiKey touch
   restic restore latest --target ~/               # populates home from Backblaze
   ```
4. If migrating the data partition from old machine:
   ```bash
   # Attach existing data partition, homed discovers the .home file automatically
   homectl activate mnussbaum   # prompts for YubiKey touch
   login                        # home is fully populated, no restore needed
   ```

Scenario 3 (Backblaze restore) works with no other machine present. Scenario 4
is a fast path when swapping hardware — plug in the old data drive and go.

### Ansible changes required

- **`user` role**: replace `ansible.builtin.user` tasks with `homectl create`
  and `homectl update`. homed stores user metadata (UID, GID, shell, authorized
  keys) inside the `.home` image, so `/etc/passwd` is managed by homed rather
  than directly.
- **`backup` role**: ensure Restic runs after login (home must be mounted).
  The existing timer-based approach works; add a dependency on the homed mount
  unit (`home-mnussbaum.mount` or equivalent).
- **`syncthing` role**: Syncthing remains useful for ongoing cross-machine
  sync of specific directories (e.g. `~/Sync`), but is no longer the restore
  mechanism. Its role narrows to convenience sync, not recovery.
- **Partition layout**: `host_vars` gains a `data` partition entry; bootstrapping
  gains a LUKS2 format + homed registration step for the data partition.

---

## Resolved questions

- **Windows dual-boot**: Windows partitions on physical hosts are vestigial and
  unused. `os-prober` is removed entirely. No Windows loader entries needed in
  systemd-boot.

- **LUKS passphrase / vconsole**: `sd-vconsole` reads `/etc/vconsole.conf` and
  the standard keymap paths — identical to the old `consolefont` + `keymap`
  hooks. The custom `us-custom.map.gz` (CapsLock→Escape) is already installed
  to the path `sd-vconsole` expects. No change needed.

- **`resume_offset` in QEMU**: carry the existing
  `when: ansible_facts["virtualization_role"] != "guest"` conditional from
  `grub.j2` into the `/etc/kernel/cmdline` template. Already accounted for
  in section 1.

- **Secure Boot scope**: key generation and UEFI enrollment are included in
  this plan (section 8). The manual UEFI Setup Mode step is documented as a
  post-install checklist item rather than an Ansible task.

- Goal is to comply with
  https://uapi-group.org/specifications/specs/discoverable_partitions_specification/
  and https://0pointer.net/blog/fitting-everything-together.html
