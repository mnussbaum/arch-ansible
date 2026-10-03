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
is just a boot-menu choice (a UKI profile under `mkosi/mkosi.uki-profiles/`), not a
separate build:

- **Installed system** — written to a machine's internal disk; the default
  profile self-provisions root/home on first boot and becomes the permanent OS.
  Machine identity is applied later: the hostname at boot (see below) and
  per-machine traits (monitors, VM guest/host role, etc.) from hardware/facts at
  firstboot.
- **Installer / live USB** — the same image written to a USB drive, used to
  bootstrap a new machine.
- **Recovery** — booted from that USB into the **Live System (Recovery)** profile
  (`mkosi/mkosi.uki-profiles/15-live.conf`): a volatile root that masks the first-boot
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
`mkosi/mkosi.extra/efi/loader/loader.conf` causes systemd-boot to pull these into
firmware automatically without a UEFI Setup Mode visit. Microsoft certificates
are **not** enrolled; the hardware used here does not require them for option-ROM
validation.

> The key currently lives on disk because pkcs11-provider's CMS/PE signing paths
> (needed by `systemd-sbsign` and `systemd-repart`) don't yet work; once they do
> it can move to a YubiKey PIV slot.

### Unified Kernel Images

All bootable content is packaged as UKIs: EFI binaries embedding the kernel,
initrd, and kernel command line in a single signed artifact. There is no separate
kernel or initrd on the ESP. This means the kernel command line — including the
verity root hash — cannot be tampered with, and signatures cover the whole boot
artifact. A single UKI carries multiple **profiles** (`mkosi/mkosi.uki-profiles/`):
`default`, `live` (recovery), `emergency`, `factory-reset`, and
`factory-reset-with-tpm-clear`, each a boot-menu entry with its own cmdline.

### Immutable /usr (dm-verity)

The OS lives in a read-only `/usr` (erofs, zstd-compressed) protected by
dm-verity. The verity root hash is embedded in the signed UKI cmdline, so the
kernel only mounts a `/usr` whose contents match the signed hash. `/usr` is
laid out as A/B slots for atomic updates (see [Updates](#updates)). `/etc` is
seeded from `/usr/share/factory/etc` (via `mkosi/mkosi.finalize.factory-seed`)
so it tracks `/usr` across updates instead of freezing at first boot; per-host
state (machine-id, ssh host keys, shadow) is written into the writable `/etc`
on first boot.

### Disk encryption

The root and swap partitions are LUKS2, created and TPM2-enrolled by
`systemd-repart` when it provisions them on first boot
(`mkosi/mkosi.extra/usr/lib/repart.d/{40-swap,50-root}.conf`, `Encrypt=tpm2`). The
keyslot is bound to **PCR 7 and a signed PCR 11 policy**: `TPM2PCRs=7` pins the
Secure Boot state, and repart adds the signed policy by default from mkosi's
`SignExpectedPcr=` key. A normal boot unlocks with no interaction.

Once first boot has created a policy, `pcrlock-enroll-luks.service` moves the
PCR 7 half onto a **systemd-pcrlock policy** (see "PCR 7 via pcrlock" below);
the signed PCR 11 half never changes.

Those two bindings behave very differently, and the difference matters for
recovery:

- **PCR 7** is stable within a boot, so the token can also authorize changes
  from the running system (`systemd-cryptenroll --unlock-tpm2-device=auto`).
- **Signed PCR 11** measures _this_ UKI and its boot phases, so no other
  image — including a recovery medium — can ever satisfy it. That is the point:
  a different OS cannot unseal the disk. It also means `bin/recovery-mount`
  cannot use the TPM token and needs a second factor.

That second factor is the **YubiKey's shared PIV key**, enrolled on root and
swap as a PKCS#11 slot at first boot, before login, by
`luks-enroll-pkcs11.service` (`/usr/bin/luks-enroll-pkcs11`),
authorized by the TPM2 token. `bin/enroll-yubikeys` loads the same PIV key
(kept in pass, encrypted to the GPG root) onto every YubiKey, so any of them —
including ones provisioned later, or rebuilt from the root key on the offline
USB — unlocks every disk. Enrolling asks for the PIV PIN, no touch; unlocking
asks for the PIN and a touch. Without a second factor a root is unrecoverable
once its measured boot legitimately changes — a firmware update, a re-enrolled
Secure Boot key, a cleared TPM or a replaced board. So first boot waits on the
console until a YubiKey is enrolled or `skip` is typed; skipping, or any volume
left without the slot, fails the unit (system `degraded`) and is logged to the
journal (`journalctl -t luks-enroll-pkcs11`). Enroll later from any normal boot:

```
sudo /usr/bin/luks-enroll-pkcs11
```

The initrd carries pcscd and the PIV PKCS#11 module (`mkosi/mkosi.initrd.conf/`), so
a machine whose TPM path broke still boots, asking for the YubiKey at the LUKS
prompt. systemd 262's interactive `systemd-cryptenroll-firstboot.service` is
masked on the kernel command line in favour of this. In a VM the unit does
nothing unless a YubiKey is passed through (`bin/vm run --yubikey`).

#### PCR 7 via pcrlock

A literal PCR 7 value breaks on any Secure Boot variable change — a dbx
revocation update, a new KEK or db entry — and from then on only the recovery
factor opens the disk. So after first boot, root and swap are re-bound to a
`systemd-pcrlock` policy for PCR 7, which lives in a TPM NV index and can be
rewritten without touching the keyslot:

- `systemd-pcrlock-secureboot-policy` / `-secureboot-authority` describe the
  current Secure Boot state; `systemd-pcrlock-make-policy` (via
  `mkosi/mkosi.extra/usr/bin/pcrlock-make-policy`) turns it into a policy on **PCR 7 only**, with
  `--strict=yes` so it fails rather than silently dropping PCR 7. A copy goes to
  the ESP (`loader/credentials/pcrlock.<machine-id>.cred`) for the initrd.
- `pcrlock-enroll-luks.service` (`mkosi/mkosi.extra/usr/bin/pcrlock-enroll-luks`) then re-enrolls each
  TPM2 slot as signed PCR 11 + pcrlock, wiping the old slot only after the new
  one exists. If the policy was not made, the volumes keep the literal binding.
- The policy's recovery PIN is ours, kept root-only on the encrypted root
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
predicted), the TPM refuses. Unlock root with the YubiKey once (swap is
skipped for that boot): that boot re-predicts from the new state and rewrites
the policy with the stored PIN, and the next boot unlocks root and swap from
the TPM again.

pcrlock needs a TPM 2.0 rev ≥ 1.38 (PolicyAuthorizeNV). On older TPMs — the
XPS 13 9365's Intel PTT is one — `systemd-pcrlock-make-policy` is skipped and
root and swap stay on literal PCR 7 + signed PCR 11. Its PCR 7 event log was
fully recognized, so a newer TPM firmware would be enough.

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
2. **First login.** `ansible/roles/user/tasks/first-login.yml` discovers the YubiKey's
   PIV URI and runs `homectl update --pkcs11-token-uri=…`, then **drops the
   password factor**, leaving the token as the login factor.
3. **Baked secret removal.** The baked secret is readable from any image's
   unencrypted `/usr`, so first login then wipes its LUKS keyslot, leaving the
   YubiKey's as the home's only one. It refuses if no YubiKey slot exists
   beside it. There is no password fallback: a broken or lost YubiKey is
   fixed by re-provisioning one, which reloads the same PIV key ("Common
   recovery tasks"). Machines installed before this existed drop the secret
   when the first-login playbook is re-run:
   `cd ~/Projects/arch-ansible && ANSIBLE_PLAYBOOK=user-first-login-playbook.yml NO_ASK_BECOME_PASS=1 ./bin/ansible`.

It pins PIV **slot 9D** (`id=%03`, "Key Management"), the only key on the PIV
applet: provisioning resets PIV first. The Secure Boot key is a software key in
`pass`, not on the YubiKey.

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
swap           LUKS2/tpm2  4–16 GiB (weight 0.5, for hibernation)
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

| `Type=` in `repart.d`                 | what finds it at boot                                                                    |
| ------------------------------------- | ---------------------------------------------------------------------------------------- |
| `esp`                                 | `systemd-gpt-auto-generator` mounts it at `/efi`                                         |
| `usr`, `usr-verity`, `usr-verity-sig` | `mount.usr=dissect` — the verity triple is matched and `/usr` comes up integrity-checked |
| `root`                                | `root=dissect`, unlocked via its LUKS2 TPM2 token                                        |
| `home`, `swap`                        | auto-mounted / auto-enabled by type                                                      |

Two consequences worth knowing:

- **Paths are by role, not by device.** `/dev/disk/by-designator/root-luks` and
  `/dev/mapper/usr` are what scripts use; nothing references `/dev/sda2` or a UUID.
- **The same image boots any machine.** Since discovery is by type, there are no
  per-host partition definitions to generate — which is what makes one image
  serve every machine, and what makes the A/B slots interchangeable.

The A/B `usr` slots are the one place where type alone is ambiguous: both slots
carry `Type=usr`, so the inactive one is labelled `_empty` and the UKI's
`systemd.image_filter=usr=image_*` keeps `dissect` from picking it.

---

## Build caches

A build reuses six caches under `${ARCH_ANSIBLE_CACHE}` (`~/.cache` on a host,
`/var/cache/arch-ansible` on a device — `bin/_cache_common.sh`):

| cache              | what it saves                                                            |
| ------------------ | ------------------------------------------------------------------------ |
| `mkosi/pacman-pkg` | downloaded packages (mkosi's own `PackageCacheDirectory`)                |
| `aur-repo`         | **built** AUR packages; mkosi installs from it via `PackageDirectories=` |
| `aur-chroot`       | the devtools clean chroot AUR packages are built in                      |
| `nvim/site`        | ~130 MiB of plugins and compiled tree-sitter parsers                     |
| `cargo/registry`   | downloaded crates                                                        |
| `sccache`          | compiled Rust objects                                                    |

`aur-repo` and `aur-chroot` are maintained outside mkosi: before every build,
`bin/sync-aur` checks the AUR for newer versions of the image's AUR packages and
builds missing or outdated ones with `makechrootpkg` into `aur-repo`, keeping only
the newest version of each. Makedepends go into the chroot, so this works on a
device with a read-only `/usr`. A run that builds asks for sudo.

### The round-trip pattern

The postinst caches (`nvim/site`, `cargo/registry`, `sccache`) are each wired
into the build three times, and the reason is worth understanding before
changing any of it:

1. **`SkeletonTrees=`** seeds the cache into the image. This is _frozen into
   mkosi's incremental snapshot_, so it reflects the state when that snapshot
   was taken, not today.
2. **`BuildSources=`** mounts the same host directory live at `/work/src/…`, so
   the postinst sees whatever previous builds have written since the snapshot.
   `mkosi/mkosi.postinst.chroot` delta-seeds from there (`rsync --ignore-existing`).
3. **`mkosi/mkosi.finalize`** writes new files back out. It cannot touch the host
   cache from its sandbox, so it stages into the output directory
   (`cache-writeback/`) and `bin/build-image` rsyncs that into the real cache
   after mkosi exits.

The write-back is a **delta**, not a copy: finalize touches a marker before the
postinst runs and stages only files newer than it.

---

## Build chain from scratch

This is the full sequence for setting up a new machine when no existing
provisioned system is available.

### Step 1 — Build the image

On an Arch host with the builder packages (`mkosi/mkosi.conf.d/20-builder.conf`),
mkosi runs on the host directly (`ToolsTree=/`):

```bash
bin/build-image
```

Anywhere else (any Linux or macOS with podman or docker), `bin/dr-build` builds
`container/Containerfile` and runs `bin/build-image` inside it instead; its output
lands in `dr-out/` and is written with `bin/dr-burn` rather than `bin/burn-image`.
See `disaster-recovery.md`.

`bin/build-image` materializes the Secure Boot keypair from `pass`, bumps
`mkosi/mkosi.version` (a fresh monotonic version so each build supersedes the running
slot for sysupdate), and runs `mkosi build`, which:

1. Installs the Arch packages declared in `mkosi/mkosi.conf` into the rootfs.
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

### Step 2 — Write the image to a USB

```bash
bin/burn-image /dev/sdX
```

`mkosi burn` writes the built image and expands partitions to fill the device. The
image is generic; the hostname is chosen at install time.

### Step 3 — Boot the USB and install to the target disk

Boot the target machine from the USB and pick the **Installer** profile. It
auto-launches a guided installer on the console (`mkosi/mkosi.extra/usr/bin/install-system --guided`
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
cloned from the running `/usr`. `root`/`home`/`swap` and the inactive `usr-B`
slot are deferred to the target's own first boot (see _First boot sequence_).

This produces a pure **Boot Loader Spec Type #2** ESP — a bare UKI under
`EFI/Linux/`, no `loader/entries/*.conf` — the same convention
`systemd-sysupdate` uses for A/B updates, so install and update share one layout
and nothing accumulates stale boot entries. It replaces `systemd-sysinstall`,
whose `bootctl link` step is hardwired to Type #1 (a UKI under `/image/` plus
per-profile loader entries) that the Type #2 update path can never garbage
collect (mirrors [systemd/particleos#166](https://github.com/systemd/particleos/pull/166)).

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
applied at firstboot from hardware/facts. The hostname is provided from user
input at install time.

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
`usr` slot via the **volatile-root** mechanism — _not_ `systemd-sysupdate
--image`, which fails to parse our `Type=regular-file` transfers through systemd
v261. It symlinks `/run/systemd/volatile-root` at a target _partition_ in a
private mount namespace (so systemd treats the target as the system disk) and runs
`systemd-sysupdate --definitions=mkosi/mkosi.sysupdate --transfer-source=<build output>
--offline update`, with `SYSTEMD_ESP_PATH` pointing the new UKI at the target's
own ESP. Nothing is dissected, so the TPM2-sealed LUKS root/home/swap are never
unlocked or touched (user data survives) — only the inactive `usr` slot and the
ESP are written. The target disk is the second disk in the guest under
`bin/vm run --device=` (`/dev/vdb`), or the physical disk node otherwise.

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
The TPM2 keyslot will not open the target machine's disk (its signed PCR 11
policy only matches the installed UKI's own boot), so use the YubiKey.

In QEMU, `bin/vm run --device=<disk.raw>` emulates this: it boots the image as
the medium and attaches the disk as `/dev/vdb`; pick **Live System (Recovery)** at
the menu to repair it (or **Installer** to install onto it).

### Open the encrypted disk and chroot

`bin/recovery-mount` automates disk discovery, unlocking, mounting, and
chrooting. Run it from the live/recovery system:

```bash
bin/recovery-mount
```

It unlocks with the YubiKey (PIV; prompts for its PIN and a touch). To perform
these steps manually:

```bash
# Unlock with the YubiKey (PIV PIN and a touch). Not `cryptsetup open
# --token-only`: Arch's libcryptsetup has no token plugins.
/usr/lib/systemd/systemd-cryptsetup attach cryptroot /dev/<root-partition> - pkcs11-uri=auto

mount /dev/mapper/cryptroot /mnt
mount -o ro /dev/<usr-partition> /mnt/usr   # the target's erofs /usr; root has none
mount /dev/<esp-partition> /mnt/efi
arch-chroot /mnt
```

Pick the target's partitions, not the medium's: both disks carry the same
labels. `recovery-mount` also offers to open homed homes read-only.

### Common recovery tasks

**Repair the ESP** (lost or corrupted bootloader). The medium's ESP holds the same
signed systemd-boot and `loader/`, including the Secure Boot auto-enroll keys.
With the target's ESP at `/mnt/efi` and the medium's mounted elsewhere, copy
`EFI/systemd/`, `EFI/BOOT/` and `loader/` across. Don't copy the medium's UKI:
each UKI pins its own `/usr`'s verity hash. If the target's `EFI/Linux/` is
empty, `bin/update-system --image=<disk>` installs a fresh `/usr` and a matching
UKI (see "Updates"). _Untested._

**Firmware lost its Secure Boot keys** (a reset, a board swap). Put the firmware
in setup mode and boot the installed system: `secure-boot-enroll force`
re-enrolls the keys from the ESP's `loader/keys/`. PCR 7 changes, so that boot
asks for the YubiKey once and then heals ("PCR 7 via pcrlock").

**TPM stopped unlocking.** What to do depends on why:

- A Secure Boot variable change: planned, wrap it in `pcrlock-secureboot-change`;
  unplanned, unlock with the YubiKey once and the policy heals ("PCR 7 via
  pcrlock").
- A cleared or replaced TPM, or a binding that didn't heal: boot by typing the
  YubiKey PIN, then re-seal root and swap (PIV PIN and a touch per volume):

  ```bash
  sudo /usr/share/arch-ansible/bin/luks-reseal-tpm
  ```

  It binds literal PCR 7 + signed PCR 11, and `pcrlock-enroll-luks.service`
  moves PCR 7 onto the pcrlock policy on a later boot. Don't re-enroll by hand
  with `systemd-cryptenroll --tpm2-pcrs=7`: without `--tpm2-public-key-pcrs=11`
  the slot loses the signed PCR 11 policy.

  `systemd-cryptenroll` can't authorize with a PKCS#11 token and Arch's
  libcryptsetup has no token plugins, so the script decrypts the slot's key with
  `pkcs11-tool` the way systemd-cryptsetup does and passes it as
  `--unlock-key-file`.

**Lose a YubiKey:** every YubiKey carries the same PIV key, so one can't be
revoked alone; its PIV PIN (limited attempts) is what protects it. To revoke,
rotate the key: put a new PIV key in pass and re-provision the remaining
YubiKeys (`bin/enroll-yubikeys`), then on each machine, while its TPM works,
wipe the old PKCS#11 slot (`bin/revoke-luks-yubikey <slot>`) and re-enroll
(`sudo /usr/bin/luks-enroll-pkcs11`).

**Lose every YubiKey.** Machines whose TPM still unlocks keep booting, but you
can't log in: homes take only the token. Rebuild YubiKeys from the offline
primary-key USB with `bin/enroll-yubikeys <device>`. It loads the same PIV key
from pass, so the new keys unlock every disk and home with no re-enrollment. If
the USB is gone too, rebuild the key from the paper recovery guide and run
`bin/restore-primary-gpg-from-paper <device>` (README.md), which writes a new
USB and programs the YubiKeys the same way. Either way the password-store has to
be reachable first: with the primary key imported, gpg-agent's SSH support can
clone it.

**PIV PIN blocked** (too many wrong tries): unblock it with the PUK,

```bash
ykman piv access unblock-pin --puk <PUK> --new-pin <PIN>
```

If the PUK is blocked too, the PIV applet is lost; re-provision that YubiKey
with `bin/enroll-yubikeys`, which resets PIV and reloads the shared key. It also
resets the OpenPGP and OATH applets, as with any provisioning.

**Reach a home without a YubiKey.** You can't: after first login a home opens
only with the shared PIV key. Re-provision a YubiKey ("Lose every YubiKey",
above), or restore its data from restic.

### Secure Boot and the recovery USB

Every image, the medium included, is signed with the one Secure Boot key from
`pass`, the key every installed machine enrolled at first boot. So a stick built
by `bin/build-image` or `bin/dr-build` boots under any of our machines' Secure
Boot with no firmware changes.

The exception is a stopgap stick built after losing every YubiKey, when the
Secure Boot key in `pass` can't be decrypted: it's signed with a throwaway key
that is in no firmware. Boot it with Secure Boot disabled, or in setup mode to enroll that key
(`disaster-recovery.md`). Not every machine allows the first.

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

### Backup credentials

`restic-backup` (the `backup` role) looks up its Backblaze key in `pass` by
hostname: `host_secrets/$(hostname)/restic_backblaze_key{,_id}`. The repo password
(`restic_backup_password`) is shared. A new host needs its own key before it can
back up or restore:

1. Give the machine its permanent name
2. In Backblaze, create an application key for that host with read, list and
   write access to the `mnussbaum-machine-backups` bucket. Don't limit it to a
   file prefix: every host shares one restic repo, and a restore needs to read
   other hosts' snapshots.
3. Add it to the password store, then `pass git push`:
   ```bash
   pass insert host_secrets/<name>/restic_backblaze_key_id
   pass insert host_secrets/<name>/restic_backblaze_key
   ```
4. The password store ships read-only in the image (`/usr/share/password-store`),
   so roll a new image with `bin/update-system` and reboot into it.
5. Check with `restic-backup snapshots`.

### Restoring data from backup

Once the host's credentials are in place, seed its home from the latest snapshot:

```bash
restic-backup restore                    # every path in /etc/restic-backup/includes
restic-backup restore -d ~/Documents     # or specific paths
```

By default the restore only adds files that are missing. It never deletes or
overwrites anything, so it's safe to run on a home that already has work in it,
such as a repo you cloned during setup. Pass `--exact` to make each path match
the snapshot exactly, deleting files not in it and overwriting changed ones.

Restore before adding any Syncthing folders. If a folder is already being synced,
files deleted on other devices after the snapshot will come back and sync out to
them.

---

## Day-to-day configuration changes

Because `/usr` is read-only, OS-level changes are made by editing this repo and
rolling a new image with `bin/update-system` (which rebuilds and swaps the
inactive `/usr` slot), then rebooting into it. Writable state — `/etc`, `/home`,
and user-level configuration applied by `playbook.yml` — can still be changed live
on the running machine.
