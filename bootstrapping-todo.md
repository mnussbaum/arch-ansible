# Bootstrapping — Implementation Status

Sections of `bootstrapping.md` that are aspirational and not yet implemented.

---

## Build chain

- **Podman container** (`Containerfile`) — exists but untested end-to-end;
  `bin/build-image`, `bin/run-image`, and `bin/burn-image` have not been run inside it

## Recovery

- **`bin/recovery-mount`** — implemented; automates LUKS discovery, token/recovery-key
  unlock, root + /usr + ESP + home mount, and arch-chroot. Untested.

## Install from the live medium

- **`systemd-sysinstall` (`mkosi.uki-profiles/25-install.conf`)** — the `install`
  UKI profile boots straight into the upstream `systemd-sysinstall.service`
  (`systemd-sysinstall --variables=yes --reboot=yes --mute-console=yes`). That tool
  does the `systemd-repart` `/usr` copy, `bootctl link`/`bootctl install` ESP
  population, and credential setup itself. It defaults its repart definitions to
  `/usr/lib/repart.d/` when `/usr/lib/repart.sysinstall.d/` is absent (which it is),
  so no extra definitions dir is needed. The old stopgap (`bin/install-to-disk` +
  `system-install.{target,service}`) is gone. Still untested end-to-end.
- **Hostname is self-assigned from the machine-id (no install-time input).**
  `mkosi.conf` sets `Hostname=arch-????-????`, baked into os-release as
  `DEFAULT_HOSTNAME`. systemd replaces each `?` with a hex char hashed
  deterministically from the machine-id, so every install gets a unique, stable name
  (e.g. `arch-92a9-061c`) — one image, many uniquely-named machines, with no
  credential and no `systemd-sysinstall` involvement. This replaced an earlier
  `firstboot.hostname` credential forwarded through `systemd-sysinstall`, which
  TPM-sealed the (non-secret) name to the installer's TPM and broke on
  imaging/transplant/TPM-clear (see step-4 notes). Removed with it: the
  `systemd-sysinstall.service.d` drop-in, `run-image`/`burn-image` `--hostname`.
  Untested end-to-end; verify the name lands and is stable across reboots on a fresh
  install. Override a chosen name post-install with `hostnamectl hostname`.
- Open issue: TPM2 LUKS enrollment happens at repart time (`Encrypt=tpm2`), so
  PCR 7 sealing during the installer boot may not match the installed system's
  first normal boot — verify against real firmware.

## Secure Boot and the recovery medium

- **Recovery USB signed with machine db key (Option A)** — not implemented:
  - YubiKey PIV import of the machine db key is a manual step with no script
  - `bin/build-image` does not yet invoke `systemd-sbsign` with a PKCS#11 URI
  - Per-machine signing requires either a separate build per machine or a
    shared recovery key enrolled in all machines' db alongside the per-machine key
- Entire secure boot setup, not implemented

## Operational scripts

- **`bin/update-system --image=DISK`** — offline A/B update of an
  installed-but-not-running target disk from the live USB. REWORKED off the broken
  `systemd-sysupdate --image` (which still fails to parse our `Type=regular-file`
  transfers through systemd v261) to the **volatile-root** mechanism: symlink
  `/run/systemd/volatile-root` at a target _partition_ in a private mount
  namespace + `SYSTEMD_ESP_PATH` for the UKI. Mechanism validated read-only on the
  host; guest write-test pending (E2E step 5). Full design, the
  partition-not-whole-disk gotcha, and the live-build signing-key handling: see
  `offline-update-handoff.md`.
- **`ProtectVersion=%A` — resolved (correct as-is).** `%A` = `IMAGE_VERSION`,
  which the image sets (verified `IMAGE_VERSION="…"` in the UKI's `.osrel`), so on
  a real device / live USB it protects the running version — the man-page
  recommended specifier. The "string is not valid, ignoring" warning only fires
  where os-release lacks `IMAGE_VERSION` (a bare build host, e.g. the read-only
  `list` test) and is benign. Kept (dropping it loses correct on-device
  active-slot protection).
- **`bin/revoke-luks-yubikey`** — exists but verify it correctly handles slot
  discovery and re-enrollment

## End-to-end testing

The full validation sequence — each step gates the next, and steps 4→5 chain (the
host installed in step 4 is the target updated in step 5). Drive these in QEMU via
`bin/run-image`; a YubiKey is available in the guest for signing/unlock.

Drive it as ONE QEMU session. Steps 2–3 exercise the **booted image itself** (no
second disk); steps 4–5 act on a **separate target disk** (`/dev/vdb`) — and step 4
produces the very disk step 5 updates. In-guest `bin/*` come from the booted image's
read-only `/usr/share/arch-ansible`, so a script fix needs a host rebuild (step 1) +
reboot before it's live in the guest. Steps 3 and 5 rebuild the image *inside* the
guest, so the guest needs the primed caches + `/usr/share/password-store` + a
reachable YubiKey, or the in-guest build falls back to the network.

1. [x] **Build an image** — `bin/build-image` (add `--caching force` to stay offline
       on a primed cache). Pass: signed UKI + split usr/verity/verity-sig artifacts
       land in `~/.cache/mkosi/images/image`, version bumped (`mkosi.version`).
       VERIFIED 2026-06-29 for `image_20260629164917_x86-64`: `sbverify --cert
       ~/.cache/mkosi-secureboot/mkosi.crt <uki>.efi` → "Signature verification OK";
       verity-sig `certificateFingerprint` == the `CN=arch-ansible SecureBoot` cert
       (`B2:DA:95…97:83`) and its `rootHash` matches the `usr` partition's hash. Same
       cert is pre-enrolled into the OVMF varstore by `run-image`, so the firmware
       trusts the chain at boot. Re-run + re-verify after any image change.
2. [ ] **Boot the image** — normal (default) boot:
       ```
       bin/run-image --console=gui
       ```
       First boot runs repart (device A/B `usr` + root/home/swap layout), TPM2-seals
       the LUKS root/swap (swtpm state persists next to the image, so no reseal on
       later runs), and self-provisions. Pass: reaches a provisioned login;
       `hostnamectl` shows a self-assigned `arch-…` name; `findmnt /usr` is the
       dm-verity image.
3. [x] **On-device A/B update (sysupdate in the booted image)** — in the guest:
       ```
       cd /usr/share/arch-ansible && gpg --card-status
       bin/update-system --reboot          # no --image = on-device; rebuilds + applies
       ```
       Pass: the new version fills the inactive `usr` slot, a new UKI is dropped with
       `TriesLeft=`, and the reboot lands on the new slot with boot-counting /
       auto-rollback intact (verify the active slot flipped via `bootctl list` /
       `IMAGE_VERSION`). NOTE: this is the unverified `updatectl`→direct-
       `systemd-sysupdate` switch — watch the apply output.
       FAILED 2026-06-30 (`image_20260629164917` guest). Silent no-op: the in-guest
       rebuild succeeded and staged all four artifacts for `20260630065151` into
       `/var/lib/arch-ansible/updates`, but `systemd-sysupdate --transfer-source=…
       --offline update` applied nothing — after `--reboot` the running version was
       still `20260629164917`, the inactive `usr` slot (vda5/6/7) was still labeled
       `_empty`, and no boot-counted UKI was dropped. `systemd-sysupdate … --offline
       list` confirms it discovers NO available instance from the staged source even
       though the files match the shipped `MatchPattern=%M_@v_%a.usr-%a.@u.raw`.
       ROOT CAUSE (confirmed by matrix): the **`--offline` flag** suppresses
       enumeration of the local `regular-file` source. Dropping `--offline` from the
       exact same `list` makes the staged version appear as an installable candidate
       (`↻ 20260630065151 … ✓ candidate`). The script's inline comment assumed
       `--offline` only "skips network metadata fetch"; in systemd 260/261 it instead
       skips local source discovery, so `update` becomes a silent no-op (exit 0).
       Two bugs: (a) **remove `--offline`** from both `systemd-sysupdate … update`
       calls in `bin/update-system` (on-device line ~225 AND the `--image`/offline
       branch line ~204 — the `--image` path has the identical latent bug, so step 5
       would also no-op); there are no url-file transfers, so no network is contacted
       regardless. (b) `update-system` reboots after a no-op apply — line ~226 runs
       `systemctl reboot` unconditionally; it should assert the active version
       actually changed before `--reboot`.
       FIX APPLIED 2026-06-30 (`bin/update-system`, uncommitted): dropped `--offline`
       from both `systemd-sysupdate … update` calls and now pass the explicit
       just-built version (`new_version=$(cat mkosi.version)`) → `update "$new_version"`.
       An undiscoverable version exits 1 (vs. bare `update`'s no-op exit 0), so
       `errexit` aborts before the reboot — covers both (a) and (b). Pending: host
       rebuild + reboot of the live image (in-guest `/usr/share/arch-ansible` is
       read-only), then re-run step 3.
       PASSED 2026-06-30 after the fix (rebuilt image booted as `20260630010706`,
       in-guest `update-system --reboot` built+applied `20260630082348`). Verified in
       guest: running `IMAGE_VERSION=20260630082348`; active `/usr` on slot B
       (vda6/vda7); prior slot A (`20260630010706`) retained — NO `_empty` partitions
       left; both UKIs on the ESP; boot counting active and `systemd-bless-boot`
       logged "Marked boot as 'good'" with no `+tries` UKI remaining (auto-rollback
       armed then resolved on first good boot).
4. [x] **Fresh install from a live USB → blank host** — make a blank target and
       attach it:
       ```
       truncate -s 90G ~/.cache/mkosi/test-target.raw
       bin/run-image --console=gui \
         --device="$HOME/.cache/mkosi/test-target.raw"
       ```
       At the boot menu pick **Installer** (`mkosi.uki-profiles/25-install.conf` →
       `systemd-sysinstall.service`), or pick **Live System** and run
       `systemd-sysinstall` by hand. Pass: `/dev/vdb` partitioned (A/B `usr` +
       root/home/swap, usr-b empty), `/usr` copied, ESP populated via `bootctl
       install`/`link`, and the target's first boot provisions + TPM2-seals and
       self-assigns a stable `arch-…` hostname. (See "Install from the live medium" above for
       the hostname-credential and PCR-7 caveats.)
       FINDING 2026-06-30 (benign): during install `systemd-sysinstall` logs "Failed
       to read timezone, skipping timezone propagation: Invalid argument" and
       continues. Cause: `mkosi.conf` sets `Timezone=US/Pacific`, which mkosi
       materializes as a RELATIVE symlink `/etc/localtime -> ../usr/share/zoneinfo/
       US/Pacific`; systemd's timezone read (`get_timezone`) only accepts an ABSOLUTE
       `/usr/share/zoneinfo/...` target, so the relative form returns -EINVAL and
       propagation is skipped (target timezone falls back to default/firstboot). Not a
       blocker for step 4. Fix later on the mkosi side (emit an absolute localtime
       symlink); confirm with `ls -l /etc/localtime` in the live/installer env.
       FAILED 2026-06-30 (`installtest` target, blank `/dev/vdb`). The installer hit
       `FailureAction=halt` (upstream `systemd-sysinstall.service`) — i.e.
       `systemd-sysinstall` exited non-zero, "Reached target System Halt", no reboot.
       Evidence on `test-target.raw`: a malformed/incomplete GPT — 4 partitions only
       (ESP **11.5G**, usr-verity-sig 16K, usr-verity **11.5G**, usr 10G), with NO
       root/home/swap and NO usr-B (A/B second slot). That 4-partition shape matches
       the `mkosi.repart/` BUILD layout, NOT the correct installed-system layout the
       image ships at `/usr/lib/repart.d/` (`mkosi.extra/usr/lib/repart.d/`: 10-esp +
       usr-A {20/21/22} + usr-B {30/31/32} + 40-swap + 50-root + 60-home). LEADING
       HYPOTHESIS: `systemd-sysinstall` used the wrong repart definitions (the build
       set / its own defaults) instead of the shipped device layout, producing a bad
       partitioning and then erroring. The todo claim above ("defaults to
       /usr/lib/repart.d/, no extra dir needed") is suspect — likely needs an explicit
       `/usr/lib/repart.sysinstall.d/` with the installed-system layout. UNCONFIRMED
       pending the console error from the halted installer (volatile, root=tmpfs — no
       persisted journal) and an inspection of the image's actual
       `/usr/lib/repart.d/` + `/usr/lib/repart.sysinstall.d/`.
       ROOT CAUSE CONFIRMED 2026-06-30 (re-ran `systemd-sysinstall` by hand in the
       Live profile, unmuted, then debug-mounted the target via the guest agent). The
       image ships the correct layout at `/usr/lib/repart.d/` (10-esp + usr-A/B +
       swap/root/home); `/usr/lib/repart.sysinstall.d/` is absent, so sysinstall uses
       the right dir. sysinstall wiped `/dev/vdb`, created esp + usr-A
       (verity-sig/verity/usr) via `CopyBlocks=auto` from the running medium's active
       usr (`/dev/vda5,6,7`, version 20260630082348), wrote the table — then FAILED at
       "Mounting partitions… Failed to mount image: Invalid argument" → non-zero exit
       → `FailureAction=halt`. THE REAL BUG (not the signature — that's a red herring):
       `SYSTEMD_LOG_LEVEL=debug systemd-dissect --mount /dev/vdb` shows the signed
       verity `/usr` activates fine ("Verity activation via kernel signature logic
       worked"); the EINVAL is from mounting the **ESP (vfat)** — `blkid /dev/vdb1`
       has only `PARTLABEL=esp`, NO `TYPE=vfat`: the ESP was never formatted. The
       device `mkosi.extra/usr/lib/repart.d/10-esp.conf` had no `Format=`, so a
       freshly-created ESP (blank-disk install) has no filesystem. Normal first boot
       works because it adopts the build image's already-vfat ESP and repart only
       grows it. PROVEN: `mkfs.vfat /dev/vdb1` then the same default-policy
       `systemd-dissect --mount` succeeds (efi + usr both mount). NOTE the earlier
       "ship the verity cert / verity.d" theory was WRONG — the cert IS already in
       `/usr/lib/verity.d/mkosi.crt` (verified) and verity validates via the kernel
       signature path; verity.d was never the issue. FIX APPLIED (uncommitted): added
       `Format=vfat` to `mkosi.extra/usr/lib/repart.d/10-esp.conf` (repart only formats
       partitions it newly creates, so the first-boot grow of the existing ESP is
       untouched). Secondary: sysinstall lays down only esp + usr-A (root/home/swap/
       usr-B come from the target's first-boot repart, by design) but esp/usr-verity
       came out oversized (11.5G each, ~57G unallocated) — worth a second look. Pending
       rebuild + re-run step 4.
       INSTALL VERIFIED 2026-06-30 after the `Format=vfat` fix (rebuilt
       `image_20260630111640`, booted Installer onto blank `/dev/vdb`). Installer ran
       to completion and rebooted (no halt). Target inspected from the Live profile:
       ESP `vdb1` now `TYPE=vfat`, populated with systemd-boot (`EFI/systemd`,
       `EFI/BOOT/BOOTX64.EFI`), the signed UKI, and `loader/` boot-counting entries;
       `/usr` erofs copied (slot A, signed verity intact); `firstboot.hostname.cred`
       (+ locale/keymap) staged on the ESP (TPM-encrypted, applied at target first
       boot). root/home/swap/usr-B absent by design (target first-boot repart).
       FIRST BOOT VERIFIED 2026-06-30 (mostly). Booting the target in isolation
       needs a single-disk boot: `run-image --boot-device` (bootindex=0) does NOT
       work — with two mkosi-layout disks present, `systemd-repart` provisioned the
       MEDIUM (vda) not the target, so the target hung on `root=dissect`. Wrote
       `bin/boot-disk DISK.raw` (direct QEMU, Secure Boot + persistent per-disk TPM,
       no medium) to boot the target alone. Result: target self-provisioned correctly
       — repart built the full device layout (root/home/swap + usr-B inactive slot),
       LUKS root/swap TPM2-sealed AND auto-unsealed (no passphrase), `/usr` dm-verity,
       homed user home decrypted. ONE GAP: hostname did NOT land (`hostnamectl`
       static unset; transient `archlinux`). Cause: `systemd-sysinstall` TPM-seals the
       firstboot credentials to the INSTALLER's TPM; the cred was delivered fine
       (`/run/credentials/firstboot.hostname` present) but `systemd-firstboot` failed
       to decrypt it — "TPM key integrity check failed … does not belong to this TPM"
       — because `boot-disk` gave the target its own per-disk TPM, different from the
       installer's (`$output_dir/tpm`). On real hardware install + first boot share
       one TPM, so it would decrypt. To prove it: re-install, then
       `boot-disk --tpm-state=$output_dir/tpm` (added that flag) so both share the
       machine TPM. Design follow-up worth considering: the hostname isn't secret —
       TPM-sealing it makes naming fragile (breaks on TPM change / re-image); a
       host-key or unencrypted firstboot cred would be more robust.
       HOSTNAME CONFIRMED 2026-06-30 — re-ran the whole chain on ONE shared TPM
       (re-install via run-image Installer, then `boot-disk --tpm-state=$output_dir/
       tpm`). `systemd-firstboot` decrypted the cred cleanly (no TPM error) and wrote
       `/etc/hostname=installtest` (`hostnamectl` static = installtest); provisioning
       healthy (root btrfs TPM2-unsealed, /usr dm-verity, homed user). Step 4 fully
       verified end-to-end. (Side note observed: post-install the polluted medium —
       dirtied by the earlier `--boot-device` accident — hangs on `by-designator/root`
       when it auto-boots its default profile; harmless to the install, but rebuild
       the medium before step 5 for a clean Live boot.)
       HOSTNAME APPROACH CHANGED 2026-06-30 — dropped the whole firstboot.hostname
       credential mechanism (per ParticleOS). The TPM-sealing fragility is now moot:
       there is no credential to seal. Instead `mkosi.conf` sets
       `Hostname=arch-????-????`, baked into os-release as `DEFAULT_HOSTNAME`; systemd
       replaces each `?` with a hex char hashed deterministically from the machine-id,
       so every install gets a unique, stable name (e.g. `arch-92a9-061c`) with no
       install-time input. Removed: the `systemd-sysinstall.service.d` hostname
       drop-in, `--hostname`/`--credential` from `run-image`, and the ESP cred-writing
       from `burn-image`. Self-naming needs a quick re-verify on the next build
       (`boot-disk` a fresh install → `hostnamectl` shows `arch-…`, stable across
       reboots). NOTE: the step-4 commands below/above still say `--hostname=…`; that
       flag is gone now — drop it (the disk names itself).
5. [ ] **Offline update from a live USB → existing host** — reboot with the SAME
       step-4 disk still attached:
       ```
       bin/run-image --console=gui \
         --device="$HOME/.cache/mkosi/test-target.raw"
       ```
       At the boot menu pick **Live System (Recovery)**, then in the guest:
       ```
       cd /usr/share/arch-ansible && gpg --card-status
       bin/update-system --image=/dev/vdb
       ```
       Pass: the new version fills the _inactive_ `usr` slot (the empty usr-b from
       step 4), the new UKI lands on the _target's_ ESP, the prior slot is retained,
       and root/home/swap are untouched (homed user data survives). Slot-safety note:
       offline `%A` = the live USB's version, not the target's active slot, so
       retention relies on `InstancesMax=2` + oldest-instance eviction, not
       `ProtectVersion` — eyeball it. Mechanism + design: see
       `offline-update-handoff.md`.

Orthogonal checks (fold into the steps above as real hardware becomes available):

- [ ] Physical-hardware install via `mkosi burn` (step 4 on real firmware).
- [ ] Secure Boot key auto-enrollment via `secure-boot-enroll force` against real
      firmware.
- [ ] TPM2 LUKS enrollment + PCR 7 sealing on real firmware (relates to the open
      sysinstall PCR-7 caveat under "Install from the live medium").

## Running todo notes

- Document
  - Yubikey enrollment for homectl
  - Cache mounting pattern perf optimization
  - That we implement https://uapi-group.org/specifications/specs/discoverable_partitions_specification/
- Code reorgs
  - Move most package installs back into ansible, only leave enough to run ansible
  - Can remove network_install_root var?
  - Can we move ansible into the build step? Might allow better caching
    - Organize project top level better. Playbooks in one dir, mkosi stuff in another
  - Make it able to handle new hosts without new configs
- Recovery mode boot strapping
  - Stuff copied from the host that needs to be in containerfile, handle missing files gracefully
    - yay-bin
    - password-store repo
    - arch-ansible repo
    - nvim packages
    - mirrorlist - ideally reflectored
    - Cargo registry
    - Sccache
- Test offline builds
  - Base16 configs reach internet still
  - delta theme file download
  - Others?
  - `WithNetwork=false`?
- Consider automating restic restore in a new workstation
- Recovery media
  - Test live image and recovery in qemu
  - Test live image and recovery on real device
- Fix colorscheme changer for the new world. Needs a whole new strategy
- Add eeek tasks back in once fully done
- Remove all luks scripting
- Remove old host directory setup once fully cut over to image based hosts
- Finish the hermetic plan
  - PCR 7 enablement
  - Anything else?
- Change ansible to build mkosi structure instead of running on a host?
- Remove ARCH_ANSIBLE_SRCTREE copying used to avoid copying secrets dir with repo into image
- I wonder if we can run the user ansible in a seperate user home image build
  process. And then mount it in instead of running it on user first log in
- Make firstboot user playbook live image aware. No need to enroll yubikey and such
- Do I still need the bsdtar wrapping for nspawn building?
