# Bootstrapping — Implementation Status

Sections of `bootstrapping.md` that are aspirational and not yet implemented.

---

## Build chain

- **Podman container** (`Containerfile`) — exists but untested end-to-end;
  `bin/build-image`, `bin/vm live`, and `bin/burn-image` have not been run inside it

## Recovery

- **`bin/recovery-mount`** — implemented; automates LUKS discovery, token/recovery-key
  unlock, root + /usr + ESP + home mount, and arch-chroot. Untested.

## Install from the live medium

- **`bin/install-system` (`mkosi.uki-profiles/25-install.conf`)** — VALIDATED
  2026-08-19. `systemd-sysinstall` is RETIRED (it was hardwired to Boot Loader Spec
  Type #1; see the Type #2 follow-up below). The `install` UKI profile now boots to
  `multi-user.target` and auto-runs `arch-install.service` → `bin/install-system
--guided` on tty1. The whole install is one `systemd-repart` run:
  `systemd-repart --dry-run=no --empty=force --defer-partitions=swap,root,home DISK`
  — the ESP is populated by `CopyFiles=/boot:/` in the shipped
  `mkosi.extra/usr/lib/repart.d/10-esp.conf`, usr-A is cloned by `CopyBlocks=auto`,
  and root/home/swap are deferred to the target's own first boot. No `bootctl`, no
  Type #1 entries. A one-shot mode (`install-system --yes DISK`) exists for scripted
  runs and is what `bin/vm install` drives.
  The profile also sets `systemd.unit=multi-user.target`, without which the baked
  graphical login (greetd/sway) takes over the console before the guided installer
  can run. Verified: `arch-install.service` active, `greetd.service` inactive.
- **Hostname and root password are PROMPTED at the target's first boot.** The
  earlier "self-assigned from machine-id, no install-time input" design is only the
  _fallback_: `mkosi.conf` still sets `Hostname=arch-????-????` (baked into
  os-release as `DEFAULT_HOSTNAME`, `?` → hex hashed from the machine-id), but
  `mkosi.extra/usr/lib/systemd/system/systemd-firstboot.service.d/10-prompt-hostname.conf`
  adds `--prompt-hostname` to the upstream ExecStart, which already carries
  `--prompt-root-password`. So a fresh install asks TWO questions on first boot.
  Both prompts go to `/dev/console`, which the cmdline pins to tty0
  (`console=ttyS0 console=tty0`, last wins) — so a headless first boot BLOCKS
  FOREVER with nothing on serial to explain why. Supply
  `firstboot.hostname` + `passwd.plaintext-password.root` as credentials to skip
  them (`bin/vm boot` passes both over SMBIOS). Skipping the hostname prompt
  leaves `/etc/hostname` absent and keeps the `DEFAULT_HOSTNAME`. Override
  post-install with `hostnamectl hostname`.
- Open issue: TPM2 LUKS enrollment happens at repart time (`Encrypt=tpm2`). Under
  the Type #2 installer root/swap are DEFERRED to the target's own first boot, so
  sealing now happens on the target under its own firmware — the installer's TPM is
  no longer involved. Confirmed working in QEMU (seal on first boot, silent unseal
  on the second). PCR 7 stability against REAL firmware is still unverified.

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
  namespace + `SYSTEMD_ESP_PATH` for the UKI. Guest write-test PASSED 2026-07-07
  (E2E step 5). Watch for the partition-not-whole-disk gotcha and the live-build
  signing-key handling. Note it needs host root (`losetup`, `unshare`, and mounting
  the target ESP), so it can't be driven unattended where sudo wants a password —
  `bin/vm boot --share` sidesteps that by running sysupdate ON the target
  instead (see "Driving the tests headlessly").
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
host installed in step 4 is the target updated in step 5).

**Steps 4 and 5 are now fully automated and need no human at a VM window** — see
"Driving the tests headlessly" immediately below. Steps 2, 3 and anything needing an
in-guest rebuild still go through `bin/vm live` with a YubiKey in the guest for
signing/unlock.

### Driving the tests headlessly (`bin/vm`)

`bin/vm` runs the install/boot/update loop with `-display none` — no GTK
window, no keyboard, no VT switching (which historically leaked keystrokes to the
HOST compositor). Two properties of the image make it work:

- OVMF mirrors the firmware console to the serial port, so sd-boot's menu is
  readable on serial and QEMU's HMP `sendkey` moves the selection. The menu is
  drawn with absolute cursor addressing, not lines, so bin/vm replays it onto a
  screen model to read the entry list;
- every UKI profile carries `console=ttyS0` plus an agetty autologin credential, so
  a root shell lands on a unix socket and commands round-trip over it.

```bash
# Q1 — fresh install (recreates the target file first; see the truncate gotcha)
bin/vm install ~/.cache/mkosi/test-target.raw
bin/vm install DISK --medium IMAGE.raw     # install a specific version

# Q2 — boot the installed target ALONE + health checks
bin/vm boot ~/.cache/mkosi/test-target.raw
bin/vm boot DISK --journal                 # + journal warnings

# Q3 — A/B update, driven ON the target (no host privilege needed)
bin/vm boot DISK --share ~/.cache/mkosi/vm-test-src \
  --run '/usr/lib/systemd/systemd-sysupdate --transfer-source=/mnt/vmtest update <VERSION>'
bin/vm boot DISK --entry '<VERSION>'       # boot a specific sd-boot entry
```

Both subcommands exit non-zero if the run misses its checkpoint, so they script.
Things worth knowing:

- **`--share DIR`** exports DIR over virtiofs (tag `vmtest-share`, at
  `/mnt/vmtest`) via an unprivileged `virtiofsd`. This is what makes an offline A/B
  update possible without host root: hand the guest the build artifacts and run
  `systemd-sysupdate` **on the target itself**, where `/dev/vda` is already a block
  device — no `losetup`, no `unshare`, no `sudo`. (The `update-system --image` path
  needs all three.) The tag is deliberately NOT mkosi's `/run/host/shared`, so
  `mnt-shared.mount` stays inert and the two don't interfere.
- **On a stalled boot it screendumps the VGA console to a PNG.** `/dev/console` is
  tty0, so systemd's output and every firstboot/LUKS prompt are invisible on
  serial; a blocked boot looks exactly like a slow one. The screendump is the only
  way to tell them apart and is what diagnosed the first-boot hang.
- `install` **recreates the target file** (rm + truncate) by default — `truncate`
  on an existing same-size file is a no-op, and the stale GPT auto-activates and
  fails repart with EBUSY. `--no-fresh` opts out.
- `boot` attaches the target **alone**. With the medium also attached, first-boot
  repart sees two mkosi-layout disks and provisions the wrong one.

Drive it as ONE QEMU session. Steps 2–3 exercise the **booted image itself** (no
second disk); steps 4–5 act on a **separate target disk** (`/dev/vdb`) — and step 4
produces the very disk step 5 updates. In-guest `bin/*` come from the booted image's
read-only `/usr/share/arch-ansible`, so a script fix needs a host rebuild (step 1) +
reboot before it's live in the guest. Steps 3 and 5 rebuild the image _inside_ the
guest, so the guest needs the primed caches + `/usr/share/password-store` + a
reachable YubiKey, or the in-guest build falls back to the network.

1. [x] **Build an image** — `bin/build-image` (add `--caching force` to stay offline
       on a primed cache). Pass: signed UKI + split usr/verity/verity-sig artifacts
       land in `~/.cache/mkosi/images/image`, version bumped (`mkosi.version`).
       VERIFIED 2026-06-29 for `image_20260629164917_x86-64`: `sbverify --cert
   ~/.cache/mkosi-secureboot/mkosi.crt <uki>.efi` → "Signature verification OK";
       verity-sig `certificateFingerprint` == the `CN=arch-ansible SecureBoot` cert
       (`B2:DA:95…97:83`) and its `rootHash` matches the `usr` partition's hash. Same
       cert is pre-enrolled into the OVMF varstore by `bin/vm live`, so the firmware
       trusts the chain at boot. Re-run + re-verify after any image change.
2. [x] **Boot the image** — normal (default) boot:
   ```
   bin/vm live --gui
   ```
   First boot runs repart (device A/B `usr` + root/home/swap layout), TPM2-seals
   the LUKS root/swap (swtpm state persists next to the image, so no reseal on
   later runs), and self-provisions. Pass: reaches a provisioned login;
   `hostnamectl` shows a self-assigned `arch-…` name; `findmnt /usr` is the
   dm-verity image.
   PASSED 2026-07-01 (`image_20260630170801`). Full device layout (esp 2G + usr-A
   - empty usr-B + LUKS swap + LUKS root btrfs `/` TPM2-unsealed + homed
     `home-mnussbaum`); `/usr` = `/dev/mapper/usr` erofs (dm-verity). Reached greetd
   - user session. NAMING (new prompt path) verified: firstboot prompted, typed
     `wee` → `/etc/hostname=wee` (clean, no `?`), `hostnamectl --static=wee`;
     DEFAULT_HOSTNAME retained for the skip case. ANSIBLE DECOUPLING verified: the
     user-first-login playbook actually RAN against localhost (created ~/.aws/config,
     ~/.pgpass, touched ~/.config/user-first-login-done) — no "no hosts matched", so
     the old silent no-op on a self-named host is fixed. KNOWN MINOR: first-boot
     `--transient` still shows the DEFAULT_HOSTNAME (`arch-bcca-9ede`) because the
     running hostname was set early, before firstboot wrote `/etc/hostname`; static
     is correct and transient converges to `wee` on reboot (harmless — nothing keys
     on the name anymore).
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
   bin/vm live --gui \
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
   needs a single-disk boot: `bin/vm live --boot-device` (bootindex=0) does NOT
   work — with two mkosi-layout disks present, `systemd-repart` provisioned the
   MEDIUM (vda) not the target, so the target hung on `root=dissect`. Wrote
   `bin/vm boot --gui DISK.raw` (direct QEMU, Secure Boot + persistent per-disk TPM,
   no medium) to boot the target alone. Result: target self-provisioned correctly
   — repart built the full device layout (root/home/swap + usr-B inactive slot),
   LUKS root/swap TPM2-sealed AND auto-unsealed (no passphrase), `/usr` dm-verity,
   homed user home decrypted. ONE GAP: hostname did NOT land (`hostnamectl`
   static unset; transient `archlinux`). Cause: `systemd-sysinstall` TPM-seals the
   firstboot credentials to the INSTALLER's TPM; the cred was delivered fine
   (`/run/credentials/firstboot.hostname` present) but `systemd-firstboot` failed
   to decrypt it — "TPM key integrity check failed … does not belong to this TPM"
   — because `boot-disk` (now `bin/vm boot --gui`) gave the target its own per-disk TPM, different from the
   installer's (`$output_dir/tpm`). On real hardware install + first boot share
   one TPM, so it would decrypt. To prove it: re-install, then
   `bin/vm boot --gui --tpm-state $output_dir/tpm` (added that flag) so both share the
   machine TPM. Design follow-up worth considering: the hostname isn't secret —
   TPM-sealing it makes naming fragile (breaks on TPM change / re-image); a
   host-key or unencrypted firstboot cred would be more robust.
   HOSTNAME CONFIRMED 2026-06-30 — re-ran the whole chain on ONE shared TPM
   (re-install via `bin/vm live` Installer, then `bin/vm boot --gui --tpm-state $output_dir/
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
   drop-in, `--hostname`/`--credential` from `bin/vm live`, and the ESP cred-writing
   from `burn-image`. Self-naming needs a quick re-verify on the next build
   (`bin/vm boot --gui` a fresh install → `hostnamectl` shows `arch-…`, stable across
   reboots). NOTE: the step-4 commands below/above still say `--hostname=…`; that
   flag is gone now — drop it (the disk names itself).
   RE-RUN AND PASSED 2026-08-19 on the **Type #2** installer (`bin/install-system`,
   no sysinstall), headless via `bin/vm install`. Verified by reading the
   target back from inside the installer: partitions `esp` + usr-A
   {verity_sig,verity,erofs} + three `_empty` usr-B slots, with root/home/swap
   correctly DEFERRED; ESP holds `EFI/systemd/`, `EFI/Linux/<uki>.efi`,
   `EFI/BOOT/`, `loader/`; **`loader/entries` = 0 files** and **no `/image/`** —
   a pure Type #2 layout. The target's first boot then provisioned everything
   (`/` = `/dev/mapper/root` btrfs on LUKS, `/usr` = `/dev/mapper/usr` erofs on
   dm-verity, `/home` btrfs, LUKS swap), Secure Boot `enabled (user)`,
   `Measured UKI: yes`, and reached `systemctl is-system-running` = **running**
   with zero failed units. Second boot unsealed silently
   ("Automatically discovered security TPM2 token unlocks volume";
   `systemd-tty-ask-password-agent --list` empty), so the TPM2 path works
   across reboots. TWO FIXES were needed to get a genuinely clean boot:
   (a) `mkosi.uki-profiles/25-install.conf` gained
   `systemd.unit=multi-user.target` — otherwise greetd grabs the console before
   the guided installer; (b) `mnt-shared.mount` gained
   `ConditionCredential=fstab.extra` — `ConditionVirtualization=vm` is true in
   EVERY VM but the virtiofs tag only exists under `mkosi vm --runtime-tree`, so
   the mount failed and that ONE failed unit pinned `is-system-running` at
   `degraded` for the whole boot, masking the very signal this step tests.
5. [x] **Offline update from a live USB → existing host** — reboot with the SAME
       step-4 disk still attached:

   ```
   bin/vm live --gui \
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
   `ProtectVersion` — eyeball it.
   PASSED 2026-07-07 (medium `20260706145110`, target `test-target.raw` from step
   4 at `20260630111640`). In-guest `update-system --image=/dev/vdb` built
   `20260707050812` and applied it offline to the target. Verified on `/dev/vdb`:
   the previously-`_empty` usr-B slot (vdb5/6/7) now holds
   `image_20260707050812_{verity_sig,verity,∅}` (16K / 400M DM_verity_hash / 8G
   erofs); usr-A (vdb2/3/4 `20260630111640`) retained; new UKI
   `EFI/Linux/image_20260707050812_x86-64+3-0.efi` on the TARGET ESP with
   boot-counting (TriesLeft=3, TriesDone=0); swap/root (crypto_LUKS) + home (btrfs)
   untouched, never unlocked. TWO BUGS FIXED to get here:
   (a) SCRATCH PROVISIONING (`provision_scratch`, committed `c58d41a`): the first
   cold run died with "scratch: can't find the medium disk". The disk resolution
   used `dmsetup deps -o devname | lsblk -no PKNAME | head` — name-resolution can be
   empty on the cold first-boot invocation, `-no PKNAME` grabbed the dm-child row
   (partition, not disk), and the pipe could SIGPIPE under `pipefail`. Rewrote to
   resolve via sysfs (`/sys/block/<dm>/slaves/*` + `lsblk -dno PKNAME`) and replaced
   the `sfdisk --append`/`partx`/`mkfs.btrfs` carve with `systemd-repart` (BLKPG
   in-place add + Format=btrfs, idempotent, discovery by partlabel).
   (b) IN-GUEST REBUILD NETWORK STALL: the rebuild downloads the package-version
   drift delta (baked pkg-cache is 2.1G but the fresh `-Sy` DB resolves to newer
   builds → cache miss), and QEMU's default SLIRP user-net collapses to <1 B/s under
   pacman's `ParallelDownloads=5` (a single stream is 239 KB/s). Fix: `bin/vm live`
   now uses **passt** (`--runtime-network=none` + a passt netdev) when installed —
   multi-threaded user-mode net that survives parallel HTTPS; `roles/qemu-host`
   installs `passt`. (Falls back to SLIRP if absent.)
   CAVEATS / FOLLOW-UPS: (1) NOT network-free — the rebuild still fetched the drift
   delta over passt (as designed: "works with wifi up"). True no-network
   (`--caching force` + a sync DB baked consistent with the pkg-cache) is still
   future work, overlapping the offline-AUR install path. (2) UKI ENTRY-TYPE
   MISMATCH (installer Type #1 vs sysupdate Type #2) — diagnosed; DECISION: go
   Type #2-only and retire `systemd-sysinstall`; plan below.

   RE-RUN AND PASSED 2026-08-19 against a Type #2 install, headless. Driven ON
   the target via `bin/vm boot --share` + `systemd-sysupdate` rather than
   `update-system --image` from a Live boot: the target's `/dev/vda` is already
   a block device there, so it needs no `losetup`/`unshare`/`sudo`, and the
   artifacts come in over virtiofs. This exercises the sysupdate transfers and
   slot rotation; it does NOT exercise `update-system`'s own build glue or
   `provision_scratch` (both already covered by the 2026-07-07 run).
   Verified on the target: the update landed in the inactive slot
   (`Successfully installed … as '…3p7' (partition)`), both UKIs present in
   `EFI/Linux/` with the new one boot-counted (`+3-0`), **`loader/entries` = 0 —
   zero Type #1 leftovers**, root/home/swap untouched. Booting the updated slot
   (`vm boot --entry <VERSION>`) came up on that `IMAGE_VERSION`, `/usr` =
   `/dev/mapper/usr` erofs, `is-system-running` = **running**, zero failed units —
   and afterwards the UKI had been renamed to drop the `+3-0` counter, i.e.
   sd-boot BLESSED the entry, so boot counting / auto-rollback works.
   FIRST ATTEMPT FAILED, and the bug was real: `systemd-sysupdate` aborted at 98%
   of the `/usr` copy with `File too large` / `Failed to decode and write:
   Argument list too long`. The A/B slots had NO headroom — usr-B was exactly
   8 GiB (its `SizeMinBytes` floor) and usr-A had been sized to the _previous_
   image by `CopyBlocks=auto`, so the new 8.66 GB `/usr` fit in NEITHER (over B
   by 67.9 MiB, over A by 500 KiB). Compounding it, `esp` and `usr-a-verity` had
   no `SizeMaxBytes` at all, so at the default `Weight=1000` repart handed each a
   ~1/6 share of ALL free space — 5.9 GiB apiece on a 60G disk, and it scales
   with the disk (a ~160 GB ESP on a 1 TB NVMe). FIXED in
   `mkosi.extra/usr/lib/repart.d/`: usr-a and usr-b are now both
   `SizeMin=SizeMax=16G` (identical, so the pair is interchangeable), the verity
   slots both `512M`, the ESP `SizeMin=SizeMax=2G`; root and home are the only
   growable partitions left, in their deliberate 3:1 split, which makes the
   layout correct at any disk size. `CopyBlocks=auto` stays on usr-a for CONTENT
   but no longer decides SIZE. Confirmed en route: a partition larger than its
   erofs is fine (16 GiB slot holding an 8.5 GiB erofs mounts and boots), because
   dm-verity takes the data size from the verity metadata.

Follow-ups (software; discovered during E2E, not yet done):

- [x] **Exercise the A/B update in the newer-over-older direction.** The 2026-08-19
      re-run applied an _older_ version onto a newer install (the only artifacts
      available at the time), so the updated slot had to be selected explicitly with
      `vm boot --entry`. The natural case — a newer version applied over an
      older install, where sd-boot picks the new slot as the default with no
      intervention — was unproven.
      **PASSED 2026-09-21** with two consecutive builds, V1 `20260918140158` → V2
      `20260921222244`. V1 installed pure Type #2 (only its UKI in `EFI/Linux`,
      `loader/entries` = 0, usr-B `_empty` at 16G) and first-booted clean
      (`running`, zero failed units, root unsealed by the TPM2 token). V2's four
      split artifacts were shared in over virtiofs and applied ON the target with
      `systemd-sysupdate --transfer-source=/mnt/vmtest update <V2>`: it landed in
      the inactive slot (parts 5/6/7), its UKI arrived boot-counted as `+3-0`,
      both UKIs were present and `loader/entries` stayed **0**. Rebooting with
      **no `--entry`** came up on `IMAGE_VERSION="20260921222244"` — sd-boot chose
      the new slot itself — with `is-system-running` = **running**, zero failed
      units, `/usr` = `/dev/mapper/usr` erofs, and the UKI renamed to drop the
      counter, i.e. sd-boot BLESSED it. Boot counting / auto-rollback works in
      this direction too.
      WATCH: `/usr` keeps growing — 8.07 GiB (Aug) → 9.64 GiB (V1) → 10.68 GiB
      (V2). The 16 GiB slot still has room, but resizing it needs a REINSTALL,
      so this is worth tracking rather than discovering late.

- [x] **Make install pure Type #2: retire `systemd-sysinstall`, install via a
      single `systemd-repart` run.** IMPLEMENTED 2026-07-24. **VALIDATED END TO END
      2026-08-19** — steps 4 and 5 both re-run headlessly on the new installer; a
      fresh install is pure Type #2 (`loader/entries` empty, no `/image/`), boots
      clean, and still A/B-updates with zero Type #1 leftovers. See the step 4/5
      notes above for the five fixes that were needed along the way.
      DIAGNOSED 2026-07-07. Two systemd
      kernel-management workflows were mixed across the lifecycle and never cleaned
      up after each other: - `systemd-sysinstall` (step 4, install) installs the kernel via `bootctl link`
      (`man systemd-sysinstall` step 7). `bootctl link` is **hardwired to Boot Loader
      Spec Type #1** (`man bootctl`: "Creates one or more Type #1 boot loader entries"
      — no Type #2 mode): it copies the UKI under the entry-token dir (`/image/`, token
      `image` = `ImageId`) and writes one `loader/entries/image-commit_N.<ver>[@profile]
      .conf` per UKI profile (the `@1..@6` seen on the target = profiles, not tries),
      each with `extra /image/firstboot.{hostname,locale,keymap}.cred` sidecars. - mkosi (the medium) and `mkosi.sysupdate/20-uki.transfer` use **Type #2**: the
      multi-profile UKI lives in `EFI/Linux/` and sd-boot auto-expands the profiles
      (`man sysupdate.d`: `Path=/EFI/Linux`, `EFI/Linux/foobarOS_@v.efi`). Boot
      counting via the `+tries-done` filename.
      Both are valid BLS and sd-boot reads both, so boot works — but sysupdate's
      transfer (`MatchPattern` on `EFI/Linux/*.efi`, `InstancesMax=2`) is blind to the
      installer's Type #1 set, so after a target is offline-updated the original
      install's `/image/` UKI + its 7 Type #1 entries **persist forever** (never GC'd).
      Impact isn't a wrong default (both share `sort-key=image`; the newer Type #2
      version always sorts above the frozen install version, so it stays the default),
      but the Type #1 entries pin the **install-time `usrhash`**; once A/B rotation
      recycles that usr slot (only 2 slots), they point at a `/usr` that no longer
      exists and become **unbootable menu traps** a user can still manually select.
      They also waste ~113 MB of ESP permanently (fine on our 2G ESP; would matter on
      particleOS's 1G). The `extra /image/firstboot.*.cred` are vestigial too (the
      TPM-sealed firstboot-credential path was removed; hostname self-assigns).

      DECISION: standardize on **Type #2 end-to-end** rather than install-Type-1-then-GC.
      The mkosi-built medium is *already* pure Type #2 (`EFI/Linux/<uki>.efi` + sd-boot,
      no `/image/`, no `loader/entries/`); a pure-Type-2 install just reproduces that
      layout onto the target, UKI-named the way sysupdate names it so A/B rotation
      continues seamlessly. Install and update then share one convention and one code
      path, and the whole seam (plus any `bootctl unlink` GC) ceases to exist.

      Why not the alternatives: (a) *first-boot `bootctl unlink` GC* — keeps `sysinstall`
      and papers over the seam; still emits Type #1, still has the rotate-away window,
      needs careful "only after a Type #2 UKI is booted" sequencing. Demoted to a
      one-time migration tool (below), not the strategy. (b) *make the installer emit
      Type #2* — not possible: `bootctl link` has no Type #2 mode and `systemd-sysinstall`
      hardcodes it, and there's no upstream issue/RFE to add it (tracker + PR #41877 +
      systemd `TODO.md` checked 2026-07-24).
      REFERENCE: ParticleOS itself reverted OFF `systemd-sysinstall` for exactly this
      reason ([systemd/particleos#166](https://github.com/systemd/particleos/pull/166),
      daandemeyer: "the boot entries installed by systemd-sysinstall are not removed
      when the system is updated by systemd-sysupdate … the boot menu becomes a total
      mess"). Its replacement is a single repart run — which we adopted.

      KEY CORRECTION to the earlier plan: install does NOT need to reimplement LUKS/TPM
      enrollment. `systemd-sysinstall` only ever laid down `esp + usr-A`;
      root/home/swap (+ their `Encrypt=tpm2` LUKS sealing) and the inactive `usr-B`
      slot are created by the INSTALLED system's own first-boot `systemd-repart`, from
      the baked `/usr/lib/repart.d/` — unchanged by any of this. No `bootctl install`,
      no `systemd-sysupdate`, no cred migration needed either (the firstboot
      hostname/locale/keymap creds were already dropped; hostname self-assigns).

      IMPLEMENTATION (mirrors particleos#166): the whole install is one command,
        `systemd-repart --dry-run=no --empty=force --defer-partitions=swap,root,home DISK`
      - `mkosi.extra/usr/lib/repart.d/10-esp.conf`: added `CopyFiles=/boot:/`. When
        repart CREATES the target ESP it copies the running medium's `/boot` (sd-boot +
        the bare Type #2 UKI in `EFI/Linux/` + `loader/`) straight onto it — no
        `bootctl` at all. Only fires on creation, so the installed system's first-boot
        ESP grow is untouched.
      - `usr-A` is cloned from the running `/usr` by the existing `CopyBlocks=auto`
        (22-usr-a.conf); `--defer-partitions` leaves root/home/swap for first boot.
      - `bin/install-system`: thin wrapper — one-shot `install-system DISK` (block dev
        or raw file; medium-disk guard; `--yes`/`--reboot`) or `install-system
        --guided` (enumerate eligible disks → pick → confirm → install), with a
        "drop to a shell" escape hatch.
      - `mkosi.extra/usr/lib/systemd/system/arch-install.service` (+ multi-user.target
        .wants symlink): auto-runs the guided installer on tty1, gated on the
        `arch.install` kernel-cmdline marker so it is inert outside the Installer
        profile (Conflicts=getty@tty1 only there).
      - `mkosi.uki-profiles/25-install.conf`: dropped `systemd.unit=systemd-sysinstall
        .service`; added the `arch.install` marker + autologin (second escape hatch);
        kept `systemd-repart.service` masked (the medium must not provision itself).
      - Docs: `bootstrapping.md` gained an Installation section; `bin/vm live`
        comment updated.

      Caveat still to carry: first-install rollback cliff — the copied base UKI is a
      single instance with no `+tries` suffix, so it's a permanent (non-boot-counted)
      entry; the first `update-system` adds the boot-counted Type #2 pair. Pre-existing
      posture, not new. (The old "reimplement LUKS/TPM enrollment" caveat was WRONG —
      see the correction above.)

      Migration for already-installed Type #1 targets: a one-time `bootctl unlink` of the
      `image-commit_*` entries (removes the entry + its now-unreferenced `/image/` UKI +
      `.cred` sidecars per `man bootctl`), run only once the target is already booted on
      a Type #2 UKI (it won't unlink the booted entry). `update-system --image` is a
      natural place to do this opportunistically after applying.

      Verify after: fresh install (no sysinstall) → `bootctl list` shows only Type #2
      entries, ESP has `EFI/Linux/` + sd-boot and **no** `/image/` or `loader/entries/`;
      then one update → A/B pair rotates, still zero Type #1 leftovers.

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
  - PCR 11 enablement?
  - Anything else?
- Move to sys-extensions flatpaks and distrobox
- Change ansible to build mkosi structure instead of running on a host?
- Remove ARCH_ANSIBLE_SRCTREE copying used to avoid copying secrets dir with repo into image
- I wonder if we can run the user ansible in a seperate user home image build
  process. And then mount it in instead of running it on user first log in
- Make firstboot user playbook live image aware. No need to enroll yubikey and such
- Do I still need the bsdtar wrapping for nspawn building?
