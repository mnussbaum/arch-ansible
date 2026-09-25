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
(`mkosi.extra/usr/lib/repart.d/{40-swap,50-root}.conf`, `Encrypt=tpm2`). The
keyslot is bound to **PCR 7 and a signed PCR 11 policy**: `TPM2PCRs=7` pins the
Secure Boot state, and repart adds the signed policy by default from mkosi's
`SignExpectedPcr=` key. A normal boot unlocks with no interaction.

Once first boot has created a policy, `pcrlock-enroll-luks.service` moves the
PCR 7 half onto a **systemd-pcrlock policy** (see "PCR 7 via pcrlock" below);
the signed PCR 11 half never changes.

Those two bindings behave very differently, and the difference matters for
recovery:

* **PCR 7** is stable within a boot, so the token can also authorize changes
  from the running system (`systemd-cryptenroll --unlock-tpm2-device=auto`).
* **Signed PCR 11** measures *this* UKI and its boot phases, so no other
  image — including a recovery medium — can ever satisfy it. That is the point:
  a different OS cannot unseal the disk. It also means `bin/recovery-mount`
  cannot use the TPM token and needs a second factor.

That second factor is enrolled on first boot, in the initrd, by systemd 262's
own `systemd-cryptenroll-firstboot.service`, which is authorized by the TPM2
token itself (`--unlock-headless`). It runs right after repart creates root and
shows a menu on the console: a recovery key, a passphrase, or one entry per
FIDO2 token plugged in — pick the **YubiKey**. It waits for an answer with no
timeout, and Enter skips it. Without a second factor a root is unrecoverable
once its measured boot legitimately changes — a firmware update, a re-enrolled
Secure Boot key, a cleared TPM or a replaced board. A skipped wizard leaves the volume TPM-only; a
factor can still be added later from any normal boot:

```
systemd-cryptenroll /dev/disk/by-designator/root-luks --unlock-tpm2-device=auto --fido2-device=auto
```

*The FIDO2 branch has not run on real hardware yet: QEMU has no FIDO2
passthrough (the vsock relay carries pcscd, not FIDO2 HID). `bin/vm run DISK`
exercises the recovery-key branch instead.*

#### PCR 7 via pcrlock

A literal PCR 7 value breaks on any Secure Boot variable change — a dbx
revocation update, a new KEK or db entry — and from then on only the recovery
factor opens the disk. So after first boot, root and swap are re-bound to a
`systemd-pcrlock` policy for PCR 7, which lives in a TPM NV index and can be
rewritten without touching the keyslot:

* `systemd-pcrlock-secureboot-policy` / `-secureboot-authority` describe the
  current Secure Boot state; `systemd-pcrlock-make-policy` (via
  `bin/pcrlock-make-policy`) turns it into a policy on **PCR 7 only**, with
  `--strict=yes` so it fails rather than silently dropping PCR 7. A copy goes to
  the ESP (`loader/credentials/pcrlock.<machine-id>.cred`) for the initrd.
* `pcrlock-enroll-luks.service` (`bin/pcrlock-enroll-luks`) then re-enrolls each
  TPM2 slot as signed PCR 11 + pcrlock, wiping the old slot only after the new
  one exists. If the policy was not made, the volumes keep the literal binding.
* The policy's recovery PIN is ours, kept root-only on the encrypted root
  (`/var/lib/arch-ansible/pcrlock-recovery-pin`), so the policy can always be
  rewritten once root is open.

**Before changing Secure Boot variables**, wrap the change:

```
sudo /usr/share/arch-ansible/bin/pcrlock-secureboot-change fwupdmgr update
```

It keeps the old variables as a second variant, runs the command, locks the new
ones, and rebuilds the policy covering both; the next boot drops the old one.
The TPM keeps unlocking across the change.

**After an unplanned change** (or a new db certificate, which cannot be
predicted), the TPM refuses. Unlock root with the recovery key once: that boot
re-predicts from the new state and rewrites the policy with the stored PIN, and
the next boot unlocks from the TPM again. Swap has no recovery slot, so it stays
locked for that one boot (the system comes up `degraded`).

*Validated in a VM (dbx appends signed with the KEK): the planned path unlocks
silently across the change; the unplanned path needs the recovery key once and
then heals. Not yet run on real firmware, whose PCR 7 event log may contain
events pcrlock does not recognize — `--strict` then fails the policy and the
volumes stay on literal PCR 7.*

`home` is a plain btrfs partition; per-user encryption is `systemd-homed` — one
LUKS volume per home directory — on top of it.

### YubiKey enrollment for homed

A home is created **unattended** on first boot, then gains its hardware token at
**first login**. A token cannot be enrolled unattended (it needs user presence),
hence the split:

1. **First boot.** `systemd-homed-firstboot.service` consumes the credentials
   baked by `bin/_credstore_common.sh` — `home.create.<user>` (the user record)
   and `home.new-password` (a recovery secret kept in `pass` under
   `linux_users/<user>/recovery-key`) — and creates the encrypted home with no
   prompting.
2. **First login.** `roles/user/tasks/first-login.yml` discovers the YubiKey's
   PIV URI and runs `homectl update --pkcs11-token-uri=…`, then **drops the
   password factor**, leaving the token as the login factor and the recovery
   secret as the fallback.

It pins PIV **slot 9D** (`id=%03`, "Key Management"). Slot 9C is the Secure Boot
signing key and must never be selected.

Things that will bite you:

* **It needs a physical touch.** Slot 9D is `PIN required: ONCE`,
  `Touch required: CACHED` (`ykman piv keys info 9d`). The decrypt blocks on a
  tap and, untouched, fails after ~37s as an opaque
  `Failed to execute operation: Input/output error`. The real reason is only in
  `journalctl -u systemd-homed`: `Failed to decrypt key on security token: No
  user has logged in`.
* **The password and the touch must land in the same attempt.** homed also wants
  the plaintext password to authorize the change; missing either makes it fail
  fast and re-prompt, which looks like an endless password loop.
* **`homectl authenticate <user>` tests the password alone** — no token, no
  touch. Use it to tell "wrong password" from "enrollment is failing".
* **Never run `homectl` under `SYSTEMD_LOG_LEVEL=debug`.** It dumps the record it
  sends, including `secret.tokenPin` in plaintext.
* In a VM the YubiKey arrives over the pcscd vsock relay (see *YubiKey relay in
  QEMU* below); `bin/vm run` with no disk wires it up.

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

### Discoverable partitions

The layout is not described anywhere at runtime — there is **no `/etc/fstab`**
and no per-host disk config. Every partition is declared only by its GPT type
UUID, following the [Discoverable Partitions
Specification](https://uapi-group.org/specifications/specs/discoverable_partitions_specification/),
and the system finds its own storage from those types:

| `Type=` in `repart.d` | what finds it at boot |
|---|---|
| `esp` | `systemd-gpt-auto-generator` mounts it at `/efi` |
| `usr`, `usr-verity`, `usr-verity-sig` | `mount.usr=dissect` — the verity triple is matched and `/usr` comes up integrity-checked |
| `root` | `root=dissect`, unlocked via its LUKS2 TPM2 token |
| `home`, `swap` | auto-mounted / auto-enabled by type |

Two consequences worth knowing:

* **Paths are by role, not by device.** `/dev/disk/by-designator/root-luks` and
  `/dev/mapper/usr` are what scripts use (`bin/recovery-mount`,
  `bin/revoke-luks-yubikey`); nothing references
  `/dev/sda2` or a UUID.
* **The same image boots any machine.** Since discovery is by type, there are no
  per-host partition definitions to generate — which is what makes one image
  serve every machine, and what makes the A/B slots interchangeable.

The A/B `usr` slots are the one place where type alone is ambiguous: both slots
carry `Type=usr`, so the inactive one is labelled `_empty` and the UKI's
`systemd.image_filter=usr=image_*` keeps `dissect` from picking it.

---

## Build caches

A build reuses six caches under `${ARCH_ANSIBLE_CACHE}` (`~/.cache` on a host,
`/var/cache/arch-ansible` on a device — `bin/_cache_common.sh`):

| cache | what it saves |
|---|---|
| `mkosi/pacman-pkg` | downloaded packages (mkosi's own `PackageCacheDirectory`) |
| `aur-repo` | **built** AUR packages; mkosi installs from it via `PackageDirectories=` |
| `aur-chroot` | the devtools clean chroot AUR packages are built in |
| `nvim/site` | ~130 MiB of plugins and compiled tree-sitter parsers |
| `cargo/registry` | downloaded crates |
| `sccache` | compiled Rust objects |

`aur-repo` and `aur-chroot` are maintained outside mkosi: before every build,
`bin/sync-aur` checks the AUR for newer versions of the image's AUR packages and
builds missing or outdated ones with `makechrootpkg` into `aur-repo`, keeping only
the newest version of each. Makedepends go into the chroot, so this works on a
device with a read-only `/usr`. A run that builds asks for sudo.

### The round-trip pattern

The postinst caches (`nvim/site`, `cargo/registry`, `sccache`) are each wired
into the build three times, and the reason is worth understanding before
changing any of it:

1. **`SkeletonTrees=`** seeds the cache into the image. This is *frozen into
   mkosi's incremental snapshot*, so it reflects the state when that snapshot
   was taken, not today.
2. **`BuildSources=`** mounts the same host directory live at `/work/src/…`, so
   the postinst sees whatever previous builds have written since the snapshot.
   `mkosi.postinst.chroot` delta-seeds from there (`rsync --ignore-existing`).
3. **`mkosi.finalize`** writes new files back out. It cannot touch the host
   cache from its sandbox, so it stages into the output directory
   (`cache-writeback/`) and `bin/build-image` rsyncs that into the real cache
   after mkosi exits.

The write-back is a **delta**, not a copy: finalize touches a marker before the
postinst runs and stages only files newer than it. One wrinkle is recorded in
that script — cargo extracts crates into `registry/src/` preserving the
archive's *old* mtimes, so the delta misses them; only `cache/` and `index/`
round-trip and `src/` is re-extracted.

### What this costs

Caching is what makes a warm build ~10 minutes instead of an hour, but it is not
free. In a measured 574s build, **"Copying cached trees" was 88s (15%)** — and
that is a straight byte-for-byte copy because `~/.cache` is on **ext4**, which
has no reflink support. `mkosi.conf` sets `UseSubvolumes=auto`, which can do
nothing there. Moving the mkosi cache onto btrfs (or XFS with reflinks) would
turn that phase into a near-instant snapshot; `bin/setup-mkosi-cache-volume`
exists for making such a volume.

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

> **Not yet implemented:** the `firstboot.service` flow the preset enables.
> (LUKS second-factor enrollment is done: systemd 262's
> `systemd-cryptenroll-firstboot.service`, above.) TPM2/PCR 7 sealing across the Secure Boot enrollment boot has also not
> been verified against real firmware — see `bootstrapping-todo.md`. (`bin/vm run`
> works around the PCR 7 instability in QEMU by persisting the OVMF varstore and
> the emulated TPM across runs.)

---

## Installation

Boot a machine from the live USB and pick the **Installer** profile. It
auto-launches a guided installer on the console (`bin/install-system --guided`
via `arch-install.service`): it lists the eligible target disks (every whole disk
except the live medium), you pick one and confirm, and it installs. The menu also
offers dropping to a shell — where you can run `install-system DISK` directly — as
an escape hatch, and the other VTs autologin root as a second one.

```bash
install-system /dev/sda            # non-interactive: ERASES /dev/sda, installs onto it
install-system --reboot /dev/sda   # ...and reboot into it when done
```

The whole install is a single `systemd-repart` run against the target, driven by
the image's baked `/usr/lib/repart.d/`. It lays down only the ESP and the active
`usr` slot: the ESP def carries `CopyFiles=/boot:/`, so repart populates the
freshly-created target ESP with systemd-boot + the bare UKI + `loader/` copied
straight from the running medium's `/boot`, and `usr-A` (`CopyBlocks=auto`) is
cloned from the running `/usr`. `root`/`home`/`swap` are *deferred* to the
target's own first boot, where its `systemd-repart` creates them and TPM2-seals
the LUKS `root`/`swap`; the inactive `usr-B` slot is created there too.

This produces a pure **Boot Loader Spec Type #2** ESP — a bare UKI under
`EFI/Linux/`, no `loader/entries/*.conf` — the same convention
`systemd-sysupdate` uses for A/B updates, so install and update share one layout
and nothing accumulates stale boot entries. It replaces `systemd-sysinstall`,
whose `bootctl link` step is hardwired to Type #1 (a UKI under `/image/` plus
per-profile loader entries) that the Type #2 update path can never garbage
collect (mirrors [systemd/particleos#166](https://github.com/systemd/particleos/pull/166)).

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
`bin/vm run --device=` (`/dev/vdb`), or the physical disk node otherwise.
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

In QEMU, `bin/vm run --device=<disk.raw>` emulates this: it boots the image as
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

**Re-enroll TPM2** (after a Secure Boot key change). A fresh install gets its
TPM2 keyslot from `systemd-repart` (`Encrypt=tpm2` + `TPM2PCRs=7` in
`mkosi.extra/usr/lib/repart.d/50-root.conf`), bound to PCR 7 AND the signed
PCR 11 policy — so this is only needed when a Secure Boot change invalidates
PCR 7:

```bash
cryptsetup luksDump /dev/disk/by-designator/root-luks        # find the TPM2 slot
systemd-cryptenroll --wipe-slot=<n> /dev/disk/by-designator/root-luks
systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 \
  --tpm2-public-key=/usr/lib/systemd/tpm2-pcr-public-key.pem \
  /dev/disk/by-designator/root-luks
```

Without `--tpm2-public-key=` the new slot binds PCR 7 only and loses the signed
PCR 11 policy repart adds by default, so kernel updates keep working but the
seal no longer follows the measured boot. Authorize the wipe with the YubiKey's
FIDO2 slot (`--unlock-fido2-device=auto`) if PCR 7 already fails to unseal.

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

When running an image in QEMU with `bin/vm run`, the host's pcscd socket is
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
