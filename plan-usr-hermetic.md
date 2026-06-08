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
| `/usr` integrity | **dm-verity, anchored by the SecureBoot-signed UKI.** Image policy is `usr=signed` and boots. Verity-sig partition (PKCS#7, RSA-2048) is built and shipped. | Particleos pattern. **Confirmed by `dmsetup table usr`:** the table is hash-only (no `root_hash_sig_key_desc`) — the kernel does *not* enforce the verity signature at boot. Trust comes from `usrhash=` being embedded in the SecureBoot-signed UKI (verity root digest == `usrhash`), which short-circuits to hash-pinned verity. Our signing cert sits in `.platform` (UEFI db); dm-verity only consults `.builtin`/`.secondary`/`.machine`, so kernel-level sig enforcement is impossible without MOK-enrolling into `.machine`. The verity-sig partition only becomes load-bearing for runtime image attachment / sysupdate that dissects *without* a matching `usrhash` on the cmdline. For the A/B-UKI model this is the intended, sufficient mechanism. |
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
- A/B sysupdate flow — **blocked: the on-device update path isn't wired up yet.**
  Verified in a running VM (`diag-update-*.out`): the partition scaffold is
  correct (A slots `image_a_*`, B slots `_empty`+`NoAuto`, `repart --dry-run` =
  "No changes"), but `systemd-sysupdate` isn't installed, `/usr/lib/sysupdate.d/`
  doesn't exist, the ESP isn't mounted, and the installed UKI name doesn't match
  the transfer pattern. See **Stage D** for the full gap analysis and wiring plan.
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

## C — LUKS recovery factor *(pending)*

`Encrypt=tpm2` enrolls **only** a TPM2 keyslot on root (and swap), with no
passphrase fallback. Any change to the TPM or its PCR state locks the user out
with zero recovery: a cleared/replaced TPM, a firmware update that shifts PCR
values, moving the disk to another machine, or (in VM testing) a fresh
emulated TPM. This already bit us in QEMU — a second boot failed with "TPM key
integrity check failed. Key enrolled in superblock most likely does not belong
to this TPM." particleos has the same gap on its TODO ("luks recovery key
firstboot prompt").

We need a second, TPM-independent unlock factor on the root (and swap) LUKS
volumes. Options, roughly in order of preference:

1. **Recovery key enrolled at first boot, surfaced once.** A first-boot oneshot
   (after repart has created the volume) runs
   `systemd-cryptenroll --recovery-key` on the root device, then displays the
   generated recovery key (QR + text) on the console / writes it to a
   credential the user captures. The recovery key is a high-entropy
   systemd-format secret; store it with the GPG paper backup / in pass. This
   mirrors how the homed user already gets a recovery secret.
2. **Recovery key pre-seeded via credential**, like the homed
   `home.create`/`home.new-password` credstore pattern: generate the recovery
   secret at build time into pass, bake it as a systemd credential, and have a
   first-boot service enroll it with `systemd-cryptenroll --unlock-key-file`
   + a new `--recovery-key`-style slot. Keeps the secret stable and known
   ahead of time (recoverable from pass), at the cost of the secret existing
   before first boot.
3. **YubiKey FIDO2 slot** (`systemd-cryptenroll --fido2-device=auto`) as a
   second factor, enrolled at first login alongside the homed PIV enrollment.
   Good as an *additional* factor but not sufficient alone (a lost YubiKey
   then needs the recovery key anyway), so this complements rather than
   replaces 1/2.

Open questions:
- **When to enroll.** repart creates the LUKS volume in the initrd on first
  boot; enrollment needs the volume unlocked (TPM2) and the policy settled.
  A `ConditionFirstBoot=` oneshot ordered after `systemd-cryptsetup@root` is
  the natural hook — but it must run before anything depends on a stable
  keyslot set.
- **Where the recovery key lives.** Pure first-boot generation (option 1) is
  most secure (secret never exists pre-install) but requires the user to
  capture it interactively; pre-seeding (option 2) is recoverable from pass
  but the secret pre-exists. Given the homed user already uses a
  pass-stored recovery secret, option 2 is the consistent choice; option 1 is
  the stricter one.
- **Swap.** Swap is also `Encrypt=tpm2`; decide whether it needs a recovery
  factor (probably yes, or mark it for re-creation on TPM loss since it holds
  no persistent data — a `FactoryReset`/re-key on mismatch is acceptable for
  swap).
- **VM testing** is unblocked separately by persistent swtpm in
  `bin/run-image` (so the emulated TPM survives reboots); the recovery factor
  is about real-hardware resilience.

---

## D — On-device A/B self-update (sysupdate) *(in progress)*

**Decided model (ParticleOS *default*, driven via `updatectl`):** on-device
self-update by **local rebuild**, **no timer**, **no update server**. The device
rebuilds the image from this repo, stages the fresh split artifacts in a local
dir, and `updatectl` applies them to the inactive A/B slot. This mirrors
ParticleOS's local update flow but uses `updatectl`/`systemd-sysupdated` instead
of the raw `mkosi sysupdate` verb, so the device has a persistent, queryable
update target (`updatectl`, `updatectl check`, `updatectl update`).

- **In-image** `mkosi.extra/usr/lib/sysupdate.d/*.transfer` — `[Source]
  Type=regular-file Path=/var/lib/arch-ansible/updates` (a local staging dir, not
  a URL). This is the on-device target `updatectl` drives. ParticleOS's
  `obs-sysupdate` profile has the same *structure* but a `Type=url-file` OBS
  source; we use a local source because we self-build. (The OBS/url-file path
  with a signed remote is the only thing the in-image transfers would need a
  `SHA256SUMS`/keyring for — not applicable to a local source.)
- **Host-side** `mkosi.sysupdate/*.transfer` (`[Source] Path=/
  PathRelativeTo=explicit`) — kept for offline `mkosi sysupdate` testing against
  a built disk image; not the device path.
- Staging dir `/var/lib/arch-ansible/updates` is created by a tmpfiles.d entry;
  `bin/update-system` clears it and drops the new build's `*.usr-*.raw` + `.efi`
  there before calling `updatectl`, so the source advertises exactly one (newer)
  version.
- Versioning: `ImageVersion` is unset in `mkosi.conf`; mkosi reads the version
  from the `mkosi.version` file. `build-image` writes it from the `mkosi.bump`
  script (a `date +%Y%m%d%H%M%S` timestamp) before each build (the official path
  is the `mkosi bump` verb / `-B`, which also runs `mkosi.bump`; we write the
  file directly to keep build output clean). Monotonic timestamps mean every
  build is newer than the running slot, so sysupdate installs to the inactive
  slot; `InstancesMax=2` keeps the A/B pair and prunes older versions.
- Caveat (also open in ParticleOS's own `TODO`): boot-counting and http
  sysupdate are still maturing upstream; treat the rollback path as unproven
  until the verification below passes.

### Verified state (running VM, `diag-update-*.out`)

Good: A slots `image_a_usr`/`image_a_verity`/`image_a_verity_sig`, B slots
`_empty`+`NoAuto`, `systemd-repart --dry-run` = "No changes", `image_filter`
selects A and ignores B, systemd-boot 260.2 with Boot-counting + Measured-UKI +
SecureBoot(user) + TPM2 all supported.

### Wired this session

- **ESP now mounts:** added `esp=unprotected:xbootldr=unprotected+unused+absent:`
  to the `mkosi.conf` `image_policy` (was dropped by the trailing `:=ignore`,
  leaving `/efi` unmounted and `bootctl`/UKI-install dead).
- **UKI naming:** `UnifiedKernelImageFormat=%i_%v_%a` (was the kernel-install
  default `image-<kver>-<usrhash>.efi`, matching nothing).
- **Coherent labels/splits:** `Output=%i_%v_%a`; usr label `%M_%A` (was
  `%M_%A_usr`); all three usr partitions `SplitName=%t.%U`; runtime A-slot repart
  relabeled `%M_%A`/`_verity`/`_verity_sig` (were dead literal `usr`/… that
  repart ignored on adopt); `image_filter` broadened to usr+verity+verity-sig.
- **Host-side transfers rewritten** to ParticleOS patterns and renamed
  `*.conf`→`*.transfer` (the `.conf` ones were inert — systemd-sysupdate only
  reads `.transfer`). UKI target carries boot-count variants
  (`%M_@v_%a+@l-@d.efi`/…), `TriesLeft=3`, `InstancesMax=2`.
- **In-image transfers + staging (the updatectl target):**
  `mkosi.extra/usr/lib/sysupdate.d/{10,11,12,20}.transfer` with `[Source]
  Type=regular-file Path=/var/lib/arch-ansible/updates`; tmpfiles.d creates the
  staging dir. These give `systemd-sysupdated`/`updatectl` a persistent local
  target. (`systemd-sysupdate`/`updatectl` ship with the base `systemd` package —
  the worker is `/usr/lib/systemd/systemd-sysupdate`, not in PATH; the earlier
  "command not found" was a PATH artifact, not a missing tool.)
- **Versioning:** `mkosi.bump` (timestamp), `ImageVersion` removed,
  `mkosi.version` gitignored, `build-image` writes `mkosi.version` from
  `mkosi.bump` before building.
- **`bin/update-system`** (replaces `build-new-root-partition`): guards it's on a
  hermetic device (`/usr` == `/dev/mapper/usr`), runs `build-image` (keys from
  pass, fresh `mkosi.version`), clears+stages the new `*.usr-*.raw`+`.efi` into the staging
  dir, then `updatectl check` / `updatectl update` (+ `systemctl reboot` on
  `--reboot`).

### Validated after rebuild (`diag-update-20260530-080648.out`)

The structural wiring is confirmed end-to-end:

- **ESP mounts** at `/boot` (gpt-auto, via the `esp=`/`xbootldr=` policy); full
  `bootctl status`/`list` work; System Token set.
- **Labels** are the `%M_%A` timestamp scheme: A = `image_20260530003441` /
  `_verity` / `_verity_sig`, B = `_empty`+`NoAuto`; `repart --dry-run` = "No
  changes".
- **UKI** is `image_20260530003441_x86-64.efi` (multi-profile: main/default/
  emergency/factory-reset/factory-reset-with-tpm-clear); current cmdline
  `usrhash` matches the A verity digest.
- **sysupdate tool + target:** `/usr/lib/systemd/systemd-sysupdate` + `updatectl`
  ship with base `systemd`; the four `.transfer` files are installed under
  `/usr/lib/sysupdate.d/`; `systemd-sysupdate list` and `updatectl` both report
  target `host` at version `20260530003441` (installed/current). (`--component=`
  finds nothing — the transfers are a single flat target, not components; that
  flag was a diag artifact, since removed.)

**Still pending (expected):** the build-installed UKI has **no `+tries` counter**
and `systemd-bless-boot` is inert — boot-counting only activates once *sysupdate*
installs a counted UKI. That's the next test.

### Verification still to do (Tier-2/3 from the update review)

On-device `bin/update-system` build is now reaching the build/sign step in the
VM (proves the device can self-build and sign with the pass/YubiKey key). The
ordered VM test plan, priority `1 → 2 → 4` as the core:

1. **Apply (inspect before reboot).** `update-system` (no `--reboot`) →
   `diag-update.sh`: a `_empty` B slot becomes `image_<newts>` (+`_verity`/
   `_verity_sig`), a second counted UKI `…+3-0.efi` appears, the running slot is
   untouched (`ProtectVersion=%A`), `updatectl` lists two versions.
2. **Reboot into the new slot.** `bootctl`/`/proc/cmdline` `usrhash` flip to the
   new version; `/usr` backed by the former B partition; homed login still works
   (home is on the persistent partition).
3. **Bless contract.** On a good boot `systemd-bless-boot` fires and drops the
   `+tries` counter (was inert pre-sysupdate; if it never blesses, healthy boots
   count down toward a false rollback).
4. **Rollback / fallback (the safety net).** Force the new slot to fail (e.g.
   hard-reset 3× before bless) → boot-count exhausts → systemd-boot falls back to
   the prior good slot; `bootctl list` shows the bad entry failed.
5. **`/etc` tracks the new `/usr`.** A seeded symlink (`ls -l /etc/sway/config`)
   resolves into the new `/usr/share/factory`.
6. **A/B ping-pong + pruning.** A second `update-system` writes the *other* slot;
   `InstancesMax=2` prunes so it never exceeds two; `updatectl`/`bootctl` stay
   consistent — proves the cycle is sustainable, not one-shot.
- **Security:** tamper a staged `usr` artifact → must fail safe (usrhash mismatch
  at boot); wrong-key UKI → firmware rejects. `Verify=`/`SHA256SUMS` is moot for
  the local-rebuild model (no untrusted transport); revisit only if we ever add
  the OBS-style `url-file` path.

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
4. **No LUKS recovery factor.** TPM2 is the only keyslot on root/swap, so any
   TPM/PCR change is an unrecoverable lockout. Tracked as **Stage C** above.
   Until that lands, recovery is manual and only possible while the volume is
   still unlockable (`systemd-cryptenroll --recovery-key <dev>`).
5. **systemd-tmpfiles ordering for L lines.** L-lines run in
   `systemd-tmpfiles-setup.service`. With Encrypt=tpm2 there's no
   `/etc/cryptsetup-keys.d/` dependency, so no ordering issue.
6. **`/var` as subvolume vs partition** changes what we backup. The `backup`
   role's restic includes/excludes may need updating.
7. **Image filter strings.** `systemd.image_filter=usr=image_*:usr-verity=image_*:usr-verity-sig=image_*`
   requires the partition labels to match. Confirmed labels of the form
   `image_<version>`, `image_<version>_verity`, `image_<version>_verity_sig`
   (version is a `mkosi.bump` timestamp, e.g. `image_20260530003441`) in the
   dissect output.
8. **pacman keyring runtime service.** When we remove firstboot Ansible (B),
   the pacman-key init has to move to a stock systemd service.
9. **VM disk size.** `bin/run-image` grows the disk to 90G via
   `--runtime-size=90G`. For real hardware, `bin/burn-image` writes the
   compact image to a real disk and first-boot repart fills the available
   space.

---

## Security posture — integrity beyond `/usr`

Verified from a running VM (`diag-verity.out`): `dmsetup table usr` is hash-only,
root digest == `usrhash=` from the SecureBoot-signed UKI. So `/usr` integrity is
real and anchored, but **only `/usr` is integrity-protected.** This section
records the residual risk and the options to close it.

### FINDING (FIXED 2026-06-08) — the signing key was shipped in `/usr`

**Fixed.** The keypair now materializes to `${ARCH_ANSIBLE_CACHE}/mkosi-secureboot/`
(outside the repo; `bin/_secureboot_common.sh`), and `ExtraTrees` ships a
tracked-files-only staged copy (`${ARCH_ANSIBLE_CACHE}/mkosi-srctree`, built by
`arch_ansible_stage_srctree`) instead of `.`, so neither the key nor `secrets/`/
`.qemu-host-shared/` reach `/usr`. Original analysis below.

`ExtraTrees=.:/usr/share/arch-ansible` copies the entire working tree into the
image, including the gitignored **`mkosi.key`** that `build-image` materializes at
the repo root. So the plaintext Secure Boot / verity / PCR signing key lands at
`/usr/share/arch-ansible/mkosi.key` inside the image — and `/usr` is plaintext
erofs (integrity-protected, *not* encrypted). It is therefore readable straight
off the raw disk with **no decryption**: steal the disk → mount the usr partition
→ read the key → sign UKIs the firmware trusts → Secure Boot defeated. This is the
exact inverse of the `/usr` design principle below (`/usr` is the one place a
secret must never live), and it bypasses the "GPG/YubiKey is the only root of
trust" model. The on-device `update-system` flow re-bakes it every rebuild.

**Fix:** materialize `mkosi.key`/`mkosi.crt` to a path *outside* the repo (e.g.
`~/.cache/mkosi-secureboot/`) and pass those to mkosi, so the `ExtraTree` never
sweeps the key in; also scope that `ExtraTree` to tracked files only (it currently
also ships `.qemu-host-shared/`, any `secrets/`, etc.). Note the device *does*
legitimately need to sign updates, but it should materialize the key from pass
(YubiKey-gated) at update time into a transient path, never carry it in `/usr`.

### What each region actually gets

| Region | Secret? | Mutable? | Protection | Gap |
| --- | --- | --- | --- | --- |
| `/usr` | no | no | dm-verity (integrity), plaintext | — |
| `/etc`, `/var` | yes | yes | LUKS/TPM2 (encryption) | no integrity; dm-crypt is unauthenticated |
| `/home` | yes | yes | homed LUKS (encryption) | no integrity; user-level persistence trivial |
| ESP (UKIs) | no | yes | per-UKI SecureBoot signature | no rollback protection |

Verity + encryption are complementary: `/usr` is public-but-immutable (verify,
don't encrypt); state is private-but-mutable (encrypt, can't easily verify). The
**offline** threat is therefore mostly covered already — stolen disk can't read
or make *chosen* edits to encrypted state. Residual offline gap: dm-crypt gives
confidentiality, not authentication, so raw-disk bit-flips yield *garbled*
plaintext (corruption/DoS primitive, not clean injection). Low practical risk.

### The real exposure: post-compromise persistence

Unlike Android/ChromeOS, a verified `/usr` here does **not** give "malware can't
survive reboot." An attacker who reaches **root once at runtime** owns every
future boot entirely from outside `/usr`:

1. **`/etc` unit drop-ins override verified `/usr` units.** A
   `/etc/systemd/system/<svc>.service.d/*.conf` or a `*.target.wants/` symlink is
   executed by PID 1 at boot. Clean root persistence, no `/usr` tampering.
2. **Pure-seed `/etc` symlinks are defaults, not integrity.** `/etc` is a
   writable dir; root can `rm` a factory symlink and drop a real malicious file
   (e.g. `/etc/pam.d/system-auth` with `pam_exec.so`). Pointing into verified
   `/usr` does not make `/etc` immutable.
3. **`/var` is fully unverified, and the user is in the `docker` group**
   (root-equivalent; `/var/lib/docker` content unverified) — a root-equivalent
   unverified surface by default.
4. **`/home` (encrypted, but the attacker is already the user):**
   `~/.config/systemd/user/`, `~/.config/sway/`, `~/.zshrc`,
   `~/.config/environment.d` (PATH hijack to shadow `/usr` binaries).

Net: verity defends offline tampering and OS re-flashing; it does **near nothing**
for runtime persistence. It is not a whole-system runtime-integrity guarantee.

### Mitigations, ranked by value/cost (workstation threat model)

1. **TPM2 PCR binding of the LUKS unseal (highest value; TPM already in use).**
   Bind root LUKS to PCRs covering the boot path (already leaning on PCR 7); add
   `/usr`/UKI measurement so a tampered boot chain **fails to unseal** —
   integrity violation becomes fail-safe "won't decrypt" instead of silent
   compromise. Cheap, hardware already present.
2. **Minimal `/etc` + boot-time drift detection.** Assert every seeded `/etc`
   entry is still a symlink into `/usr/share/factory` (not replaced by a real
   file). Makes drop-in / symlink-swap persistence **tamper-evident**. Cheap.
3. **Shrink root-equivalent surface: drop `docker` group → rootless podman.**
   Removes a large unverified, root-equivalent surface verity silently ignores.
4. **dm-integrity under LUKS (authenticated encryption) for root.** Closes the
   offline bit-flip gap. Real perf cost; only if offline tamper is in scope.
5. **IMA/EVM with a signed policy.** The "correct" answer for verifying mutable
   `/etc`/exec content, but heavy to operate on Arch. Likely overkill here.
6. **Bootloader rollback protection.** Prevent booting an older validly-signed
   UKI with a known-vuln `/usr`. Matters once A/B updates have history.

**Recommendation:** land **1 + 2 + 3** — they convert "one root exploit = forever"
into tamper-evident + fail-safe at low cost and stay consistent with ParticleOS.
**4–6** are diminishing returns for a single-user workstation.

---

## Out of scope

- systemd-sysext for optional components.
- systemd-portabled for system daemons.
- flatpak for desktop apps.
- TPM2 PCR-signature unlocking (PCR-hash is current; signature is mkosi
  `SignExpectedPcr=yes` + `--measure=`).
- Automatic sysupdate timers (separate small change; can land any time).
- Kernel-enforced verity *signatures* (vs. the current hash-pinned-via-signed-UKI
  anchor). `usr=signed` is already the live policy and boots, but `dmsetup table
  usr` shows hash-only verity — trust rests on `usrhash=` inside the SecureBoot-
  signed UKI, not on the verity-sig partition. Real kernel sig enforcement would
  need `mkosi.crt` MOK-enrolled into `.machine` (cert is currently only in
  `.platform`, which dm-verity ignores). Only needed if we attach `/usr` at
  runtime without a per-image signed UKI.
