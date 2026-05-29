# Plan: Hermetic /usr partition (Lennart "particle OS" model)

References:
- <https://0pointer.net/blog/fitting-everything-together.html>
- <https://github.com/systemd/particleos/> (canonical reference implementation; we
  follow its patterns where possible)

Goal: hermetic /usr as the unit of A/B atomic updates, dm-verity-protected and
PKCS#7-signed from day one. The writable root filesystem holds /etc (mostly as
symlinks back into /usr/share/factory/etc/) plus /var as a btrfs subvolume.
/home is a btrfs landing zone for systemd-homed per-user LUKS images. No
keyfile ships in the image — LUKS volumes are created TPM2-bound by repart on
first boot.

## Current state

**Stage A architecturally validated.** The image boots end-to-end in QEMU:
SecureBoot keys enrolled, UKI verified, `/usr` mounted `ro` via dm-verity on
erofs, runtime systemd-repart created the writable partitions on first boot,
LUKS volumes born TPM2-bound (no shipped passphrase), system reaches login.
Confirmed in-VM:

- `/dev/mapper/usr` mounted at `/usr` as `erofs`, `ro`, verity-mapped
- `touch /usr/foo` returns EROFS; `touch /etc/foo` succeeds
- `/dev/mapper/root` mounted at `/`, btrfs, TPM2-unlocked

**What's still pending for A.5 to be fully done:**

- Full postinst build (the validated boot used `--skip-postinst` — no Ansible
  ran, so factory-seed L-lines weren't generated, no homed user, no sway, no
  role tree). The complete Ansible run is the honest test of A.0–A.3.
- A/B sysupdate dry-run (trigger sysupdate, verify usr-b populates, reboot
  into B, verify boot, verify cleanup of A)
- Factory-reset UKI profile (boot the profile, verify root/swap/home wipe,
  verify /usr A/B preserved)
- erofs+verity corruption test (flip a byte in the usr partition, verify the
  kernel refuses to mount / reads return I/O error)

## Decisions (with revisions from what we learned)

| Decision | Choice | Why |
| --- | --- | --- |
| `/etc` seed mechanism | **L (symlink) lines, not C (copy) lines.** `/etc/<thing>` → symlink → `/usr/share/factory/etc/<thing>`. | Particleos pattern: `/etc` *tracks* `/usr` across A/B updates instead of freezing at first boot. |
| `/usr` filesystem | **erofs** | Particleos pattern. True read-only image format, ~half the size of btrfs, faster to verify under verity. |
| `/usr` integrity | **dm-verity + PKCS#7 signature from day one.** Signed verity working with software RSA-2048 keys. | Particleos pattern. Image policy currently `usr=verity` (hash-only) rather than `usr=signed` — a small downgrade from intent; revert after full validation. |
| SecureBoot + verity + PCR signing | **Software RSA-2048 keypair in pass.** *Not* YubiKey PKCS#11. | pkcs11-provider's signing primitives (the OpenSSL provider needed for systemd-sbsign and systemd-repart) fail with `provider signature failure` regardless of key algorithm (we tested both RSA and ECDSA). The verification path works (`systemd-keyutil validate` succeeds) but actual signing doesn't. Revisit when pkcs11-provider's signing path matures or when we switch to a tool that talks to PKCS#11 directly. |
| Key algorithm | **RSA-2048.** | UEFI Secure Boot's auto-enroll path in OVMF rejects ECDSA auth descriptors. RSA-2048 is the safe default and is universally accepted. |
| LUKS unlock | **`Encrypt=tpm2` in repart.d, born TPM-bound on first boot.** No keyfile shipped, no luks-enroll.service. | Particleos pattern. Eliminates the "image-as-shipped contains the unlock secret" window entirely. |
| Root partition | **Single btrfs partition with `/var` as a subvolume.** Holds /etc + /var. | Particleos pattern: no separate /var partition. Root's TPM2 LUKS covers /var transparently. |
| `/home` | **btrfs landing zone for systemd-homed LUKS images.** Not encrypted at partition level. | Per-user encryption keyed to YubiKey PIV + recovery secret. |
| Image scope | **Single image with UKI profiles.** | Particleos pattern. The "rescue twin" becomes a UKI profile of the same /usr. |
| Image structure | **mkosi.images/ collapsed to top-level.** Single mkosi.conf at the repo root; `ImageId=image`. | mkosi 26 disallows several settings (PassEnvironment, Distribution, etc.) in image-included configs. Going top-level only is cleaner anyway since there's only one image. |
| Factory reset | **`FactoryReset=yes` on root/swap/home + UKI profile cmdline `systemd.factory_reset=1`** | Particleos pattern. Declarative, no scripts. |
| `/usr` conversion approach | **Build-time finalize hook**, not per-role rewrites | ~110 `/etc` files across 40+ roles — a single finalize step that walks `$BUILDROOT/etc`, moves contents to `$BUILDROOT/usr/share/factory/etc/`, and emits L-lines captures ~65% for free |
| systemd-homed | **Keep as-is** — YubiKey PIV + recovery key (slot 9d) | Particleos ships only a hashed password; our richer enrollment is an addition. SecureBoot key originally went into slot 9c but is now removed from there. |

## Target partition layout

**Build-time** (shipped in the image, ~3.5G):

```
ESP                 vfat        /efi        1 GiB
usr-verity-sig      verity-sig              ~auto (minimized)
usr-verity          verity-hash             ~auto (minimized)
usr                 erofs ro    /usr        ~2.5G  (verity-protected, Minimize=yes)
```

**Runtime** (created by systemd-repart on first boot, declared in
`/usr/lib/repart.d/`):

```
usr-a               erofs ro    /usr        copies build-time slot
usr-a-verity        verity-hash
usr-a-verity-sig    verity-sig
usr-b               erofs ro    -           empty   (A/B slot B, NoAuto=1)
usr-b-verity        verity-hash             empty
usr-b-verity-sig    verity-sig              empty
swap                swap                    4 GiB   (Encrypt=tpm2, FactoryReset=yes)
root                btrfs       /           ~auto   (Encrypt=tpm2, FactoryReset=yes, Subvolumes=/var)
home                btrfs       /home       ~auto   (NOT encrypted, FactoryReset=yes)
```

VM testing: `bin/run-image` passes `--runtime-size=90G` to mkosi so first-boot
repart has space (matches the pre-refactor partition allocation).

---

## Stage A — Hermetic /usr image, verity from day one

### A.0 — Finalize-to-factory mechanism *(done)*

`mkosi.postinst.factory-seed.chroot` runs after the Ansible postinst-playbook,
walks `$BUILDROOT/etc`, moves contents to
`$BUILDROOT/usr/share/factory/etc/<same path>`, and emits a
`/usr/lib/tmpfiles.d/00-factory-etc.conf` with one **L-line** per top-level
entry. `L` with `-` as target makes tmpfiles compute the default
`/usr/share/factory/etc/<basename>` target — so `/etc/sway/config` becomes a
symlink that resolves through to /usr, tracking A/B updates.

Allowlist: empty post-revision (Encrypt=tpm2 eliminated the LUKS keyfile that
was the only entry).

Droplist:
- `kernel/secure-boot-private-key.pem` — build-time-only, must not ship
- `pacman.d/gnupg` — regenerated by `pacman-key --init` on first boot
- `makepkg.conf` — build-chroot mutations must not persist

### A.1 — Move misplaced /usr/lib content out of /etc *(done)*

Roles converted: power, qemu-guest, qemu-host, secrets, reflector,
systemd-boot, libinput, polkit, sway, waybar, backup, brightness, syncthing,
network_configuration, media, devops. Systemd unit files, modprobe.d,
sysctl.d, udev rules, polkit rules moved from `/etc/...` to `/usr/lib/...`.

### A.2 — Vendor file mutations *(done)*

- `/etc/bluetooth/main.conf`: minimal full file in factory
- `/etc/nsswitch.conf`: full homed-aware file in factory
- `/etc/profile.d/freetype2.sh`: own `freetype2-overrides.sh` instead of
  mutating the package's file
- `/etc/makepkg.conf`: dropped from image (A.0 droplist)
- `/etc/pacman.d/gnupg`: regenerated at first boot via `init-keyring` task
  added to firstboot-playbook.yml
- `/etc/pacman.conf`: factory-seeded
- `/etc/fonts/conf.d/*` symlinks + `10-hinting-slight.conf` removal: no code
  change (Ansible builds the chroot's /etc, A.0 captures via L)

### A.3 — Relocate /usr/local/bin scripts *(done)*

- 13 scripts: `/usr/local/bin/` → `/usr/lib/arch-ansible/bin/`
- Repo: `/usr/local/share/arch-ansible` → `/usr/share/arch-ansible`
- Password store: `/usr/local/share/password-store` → `/usr/share/password-store`
- Delta themes: `/usr/local/share/delta-themes.gitconfig` → `/usr/share/delta-themes.gitconfig`
- All systemd unit `ExecStart=`, gpg-agent `pinentry-program`,
  firstboot/zlogin/colorscheme-changer embedded paths, mkosi `ExtraTrees=` /
  `postinst.chroot` chmod paths updated
- `/etc/profile.d/arch-ansible-path.sh` extends PATH for short-name invocation
- `postinst-playbook.yml` pre_task creates `/usr/lib/arch-ansible/bin`

### A.4 — Partition layout + UKI profiles + SecureBoot via mkosi *(done)*

Done:
- /usr split + erofs + verity + verity-sig from day one
- /var as btrfs subvolume of root
- Encrypt=tpm2 (no shipped keyfile, no luks-enroll.service)
- mkosi SecureBoot=yes replaces sbctl
- USI image deleted; replaced by UKI profiles (`default`, `emergency`,
  `factory-reset`, `factory-reset-with-tpm-clear`) under `mkosi.uki-profiles/`
- Factory reset UKI profile with `systemd.factory_reset=1`
- mkosi.images/ structure collapsed to top-level config

Critical detail: `mkosi.repart/12-usr.conf` uses `CopyFiles=/usr:/` (the `:/`
matters — without it, the partition contents end up at `/usr/usr/*` and
nothing works at runtime).

### A.4.1 — SecureBoot keypair *(done — software, not YubiKey)*

Originally planned to live on YubiKey PIV slot 9c via pkcs11-provider. After
extensive testing pkcs11-provider's signing operations fail for both
systemd-sbsign (UKI signing) and systemd-repart (verity-sig CMS signing) with
`provider signature failure`, regardless of RSA vs ECDSA. Verification works
(`systemd-keyutil validate` passes), signing doesn't.

Fallback that's in place: software RSA-2048 keypair in pass at
`arch_ansible/secureboot-{key,cert}`. `bin/build-image` materializes both to
`mkosi.{key,crt}` (gitignored) on every run; `bin/_secureboot_common.sh`
generates fresh keys if pass is empty. The same keypair signs UKI, expected
PCR measurements, and verity root hash.

Revisit when:
- pkcs11-provider's CMS/PE signing path improves upstream, OR
- A wrapper signing tool that bypasses OpenSSL providers becomes available
  (e.g. using `ykman piv keys sign` and feeding pre-signed artifacts to
  mkosi via `--secure-boot-sign-tool`)

### A.5 — Validate Stage A end-to-end *(partial)*

**Validated:**
- Build succeeds (with `--skip-postinst`)
- VM boots: SecureBoot enrolled, UKI verified, /usr mounted via dm-verity,
  systemd-repart created runtime partitions, TPM2 unlocked root LUKS unattended
- Sanity checks confirmed: /usr is `ro,erofs,dm-verity`, `touch /usr/foo`
  fails with EROFS, `touch /etc/foo` works, root is `/dev/mapper/root` btrfs

**Pending:**
- Full postinst build (no `--skip-postinst`) — exercises factory-seed L-lines,
  every role in the tree, homed user creation. This is the honest test of
  A.0–A.3 against a real Ansible payload.
- L-line verification: `ls -la /etc/sway/config` should show symlink to
  `/usr/share/factory/etc/sway/config`
- A/B sysupdate flow: trigger sysupdate, verify usr-b + verity sibs populate,
  reboot into B, sysupdate cleans up A
- Factory-reset UKI profile: boot it, verify root/swap/home wipe, /usr A/B
  preserved
- erofs+verity integrity test: corrupt a byte in the usr partition, verify
  kernel refuses to mount

---

## B — Remove firstboot Ansible *(done)*

firstboot ran Ansible on the running system, which can't install packages into
a read-only /usr. The roles it called actually run fine at *build time* (the
postinst-playbook runs inside the mkosi chroot — that's how the image gets all
its packages), so the fix was to move them to build time, keep their `package:`
tasks, and drop the `service: state=started` calls (presets enable services
instead). What each firstboot task became:

- `packaging init-keyring` → **dropped.** Hermetic systems never run pacman at
  runtime; updates come via sysupdate of the whole /usr image.
- `network_configuration` runtime (resolv.conf symlink) → **already shipped**
  by `mkosi.extra/etc/resolv.conf` (symlink to the resolved stub). Runtime task
  deleted.
- `brightness` runtime (Dell kbd backlight timeout) → **udev rule**
  `99-dell-kbd-backlight-timeout.rules` shipped to `/usr/lib/udev/rules.d`,
  hardware-gated by the `KERNEL==dell::kbd_backlight` match.
- `qemu-guest` / `qemu-host` → moved into postinst (build time),
  **unconditionally shipped in every image**; services self-activate via
  `ConditionVirtualization=`. The two `pcscd-vsock-forward.service` files
  (guest connects, host listens) shared one name and would collide — renamed
  to `pcscd-vsock-guest.service` (already `ConditionVirtualization=kvm`) and
  `pcscd-vsock-host.service` (added `ConditionVirtualization=no`), each enabled
  by its role's preset.
- `qemu-guest-agent` role folded into `qemu-guest` (package + preset enable).
- Two guest-only tweaks that can't self-gate statically (coretemp blacklist,
  Sway Super-leader override) → **dropped** (minor VM cosmetic loss).
- Deleted `firstboot.service`, the `firstboot` script, `firstboot-playbook.yml`,
  the two `runtime.yml` task files, and the sway qemu-firstboot bits.
- `bin/ansible` default playbook changed from the deleted firstboot-playbook.yml
  to postinst-playbook.yml.

**Known follow-up (not B):** runtime `./bin/ansible` (base16 theme regen via
colorscheme-changer, manual maintenance) writes to `/etc/...` which now
symlinks into read-only `/usr/share/factory/etc/`. This is the L-line
writable-/etc problem (risk #3) and needs its own resolution before runtime
re-theming works again.

---

## Risks and open questions

1. **YubiKey-backed SecureBoot remains aspirational.** Currently software keys
   in pass. Security posture is that the build host's filesystem (LUKS-encrypted
   disk, mode 0600) is the only protection layer for the signing key. Compared
   to YubiKey-backed signing this is a step down. Track upstream
   pkcs11-provider for signing-path improvements.
2. **erofs build time.** erofs requires recompression every build (no
   reflinks for the compressed payload). First build took several minutes
   just for the cpio + compression steps. Iteration time is real.
3. **L lines + writable /etc semantics.** A user editing `/etc/sway/config`
   would write through the symlink into `/usr/share/factory/etc/sway/config`
   — which is in /usr and therefore read-only. Pattern needs to be: break
   the symlink first (`unlink /etc/sway/config` and copy from factory)
   before editing. Worth a helper script.
4. **Recovery passphrase.** With no shipped keyfile and no enrollment
   ceremony, there's no second factor on root LUKS by default. Document that
   recovery is manual: `cryptsetup luksAddKey --token-type systemd-tpm2`.
5. **systemd-tmpfiles ordering for L lines.** L-lines run in
   `systemd-tmpfiles-setup.service`. With Encrypt=tpm2 there's no
   `/etc/cryptsetup-keys.d/` dependency, so no ordering issue.
6. **`/var` as subvolume vs partition** changes what we backup. The `backup`
   role's restic includes/excludes may need updating.
7. **Image filter strings.** `systemd.image_filter=usr=image_*` requires the
   partition labels to match. Confirmed labels of the form `image_a_usr`,
   `image_a_verity`, `image_a_verity_sig` in the dissect output.
8. **pacman keyring runtime service.** When we remove firstboot Ansible (B),
   the pacman-key init has to move to a stock systemd service.
9. **VM disk size.** `bin/run-image` grows the disk to 90G via
   `--runtime-size=90G`. For real hardware, `bin/burn-image` writes the
   compact image to a real disk and first-boot repart fills the available
   space.

---

## Out of scope

- systemd-sysext for optional components.
- systemd-portabled for system daemons.
- flatpak for desktop apps.
- TPM2 PCR-signature unlocking (PCR-hash is current; signature is mkosi
  `SignExpectedPcr=yes` + `--measure=`).
- Automatic sysupdate timers (separate small change; can land any time).
- Image policy `usr=signed` (currently `usr=verity`; flip back after the
  full-postinst validation confirms the signing key paths are stable).
