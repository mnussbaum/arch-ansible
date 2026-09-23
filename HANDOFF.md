# Handoff — Type #2 install validation (arch-ansible)

Repo: `/home/mnussbaum/Projects/arch-ansible`  ·  Branch: `mkosi`  ·  Updated: 2026-09-23

## Mission

We replaced the OS installer. The old path (`systemd-sysinstall`) created Boot
Loader Spec **Type #1** entries that `systemd-sysupdate` (which is Type #2) can
never garbage-collect, so stale/unbootable menu entries pile up over the machine's
life. The new path is a **pure Type #2 install**: one `systemd-repart` run that
reproduces the mkosi medium's own Type #2 layout onto the target. Install and
update then share one convention. Reference: systemd/particleos#166.

## Validation framework — the 3 questions

1. **Does the installer write the disk correctly?**
   → **CONFIRMED** (re-run headless 2026-08-19 on image `20260727160716`).
2. **Does an installed machine boot into a clean, working system?**
   → **CONFIRMED, no caveats.** Re-validated 2026-08-19 from a rebuilt image
   (`20260819002736`) carrying the `mnt-shared.mount` fix: a fresh install's
   FIRST boot reports `systemctl is-system-running` = **`running`** with
   `systemctl --failed` **empty** — no masking, no workaround. The Installer
   medium itself is now clean too (was `degraded`).
3. **Can that installed machine still receive A/B updates cleanly afterward?**
   → **CONFIRMED** (2026-08-19, image `20260819015333`). It failed first — the A/B
   slots had no headroom — and passes after the repart sizing fix below. The
   update applies to the inactive slot, the ESP holds both UKIs, `loader/entries`
   stays empty (zero Type #1 leftovers — the whole point of the rewrite), the
   updated slot boots clean, and boot counting blesses it.

## Q4 — newer-over-older A/B update: **CONFIRMED** (2026-09-21)

The last open validation gap is closed. Previously the A/B update had only been
exercised older-over-newer, which forced an explicit `--entry`; the natural
direction — where sd-boot picks the new slot itself — is now proven.

Run with two consecutive builds, V1 `20260918140158` → V2 `20260921222244`:

1. `vm install` of V1: pure Type #2 (only the V1 UKI in `EFI/Linux`,
   `loader/entries` = 0, usr-B slots `_empty` at 16G). 72s.
2. V1 first boot: `is-system-running` = **running**, 0 failed units, `/usr`
   erofs on dm-verity, root unsealed by the TPM2 token with no passphrase.
3. V2's four split artifacts hardlinked into `~/.cache/mkosi/vm-test-src-<V2>/`
   and handed to the guest over virtiofs, then updated **on the target**:
   `/usr/lib/systemd/systemd-sysupdate --transfer-source=/mnt/vmtest update <V2>`
   → installed into the inactive B slot (parts 5/6/7) + UKI as `+3-0`; both UKIs
   in `EFI/Linux`; `loader/entries` still **0**.
4. **The test: reboot with NO `--entry`.** Result:
   `IMAGE_VERSION="20260921222244"` — sd-boot chose the new slot by itself —
   `is-system-running` = **running**, 0 failed units, `/usr` erofs, and the UKI
   renamed to `image_20260921222244_x86-64.efi` (counter gone = **blessed**).

The 16 GiB slot sizing still holds with room to spare, but `/usr` keeps growing:
8.07 GiB (Aug) → 9.64 GiB (V1) → **10.68 GiB (V2)**. Worth watching — at this
rate the 16 GiB slot is maybe a year out, and changing it needs a reinstall.

## Session 2026-09-18 — what changed

* **Retention policy** in `bin/build-image` (`c91855a`): keeps the newest N
  image versions (`--keep N|all`, default 3) after a successful build. Deletes
  each version by an explicit `find -maxdepth 1 -name "image_<ver>_*" -delete`,
  never an rm on a variable-built glob, and never the version just built.
* **yay PGP fix** (`61d6736`): the build failed in `cli-tools` because
  `aws-cli-bin` 2.36.48 needed a rebuild and yay's `gpg --recv-keys` failed.
  Root cause: on the current Arch set (gnupg 2.4.9-3 / gnutls 3.8.13) **dirmngr's
  hkps transport fails against every keyserver**, while plain `hkp://…:80` works
  and curl fetches the key over HTTPS fine. yay v13 imports `validpgpkeys`
  unconditionally (**its `pgpfetch` setting is parsed but never read**, so
  turning it off does nothing; tried and reverted). Fix: `"gpgflags":
  "--keyserver hkp://keyserver.ubuntu.com:80"` in the yay config written by
  `roles/packaging/tasks/setup-aur.yml`. Safe because makepkg pins the full
  fingerprint. Worth revisiting (and maybe reverting to the default keyserver)
  once gnupg/gnutls fix hkps.
* **Build-time analysis** (answering "would a sysext speed this up?" — no; a
  sysext layer still has to run the same Ansible, and on rolling Arch it needs a
  rebuild against every new base anyway). On
  the warm build of V1 (899s total): base packages from mkosi's incremental cache
  took ~40s, **Ansible took 9m19s**, and presets+erofs+verity+signing took the
  rest. About 400s of the Ansible time is **38 separate `Install packages`
  tasks**, each its own yay/pacman transaction that re-runs the image's 31 alpm
  hooks (and probably a yay AUR RPC round-trip). A sysext layer would still have
  to run that same Ansible, and on rolling Arch it would need rebuilding against
  every new base anyway. Candidate speedups, not yet measured: (a) move
  Ansible's official-repo package lists into mkosi `Packages=` so they land in
  the incremental cache; (b) lighter, collapse the 38 installs into one
  transaction. Measure how the ~400s splits (hooks vs extraction vs yay RPC)
  before picking.

## What changed 2026-08-19

### New: `bin/vm` — headless, scripted VM validation

The whole validation loop used to need a human at a QEMU GTK window. It doesn't
any more. `bin/vm` drives the same VMs with `-display none`, using two
properties of the image:

* OVMF mirrors the firmware console to the serial port, so sd-boot's menu is
  readable on serial and QEMU's HMP `sendkey` moves the selection;
* every profile has `console=ttyS0` plus an agetty autologin credential, so a
  root shell lands on a unix socket and commands round-trip over it.

```bash
bin/vm install ~/.cache/mkosi/test-target.raw   # Q1: fresh install
bin/vm run    ~/.cache/mkosi/test-target.raw   # Q2: boot + health checks
bin/vm run DISK --run 'CMD'                    # run CMD in the booted system
bin/vm run DISK --share DIR                    # virtiofs DIR at /mnt/vmtest
bin/vm run DISK --journal                      # + journal warnings
bin/vm install DISK --medium IMAGE.raw          # install a specific version
```

Both exit non-zero if the run misses its checkpoint, so they script. Notes:

* `install` **recreates the target file** (rm + truncate) by default — `truncate`
  alone on an existing same-size file is a no-op and the stale GPT auto-activates
  and breaks repart with EBUSY. `--no-fresh` opts out.
* `boot` attaches the target **alone** (gotcha #1 below) and passes first boot's
  answers as SMBIOS credentials: `agetty.autologin`, `firstboot.hostname`,
  `passwd.plaintext-password.root`.
* On a stalled boot it **screendumps the VGA console** to a PNG. This is the only
  window into `/dev/console` (= tty0) in a headless run and it is what cracked the
  first-boot hang; reach for it first when a boot goes silent.
* `--share DIR` exports DIR over virtiofs (tag `vmtest-share`, mounted at
  `/mnt/vmtest`), run by an unprivileged `virtiofsd`. This is how an A/B update is
  driven without any host privilege: hand the guest the build artifacts and run
  `systemd-sysupdate` **on the target itself**, where `/dev/vda` is already a real
  block device — no `losetup`, no `unshare`, no host `sudo`. (The offline
  `update-system --image` path needs all three, and sudo here wants a password.)
  The tag is deliberately NOT mkosi's `/run/host/shared`, so `mnt-shared.mount`
  stays inert and the two mechanisms don't interfere.

### Fixed: `mkosi.extra/usr/lib/systemd/system/mnt-shared.mount`

Added `ConditionCredential=fstab.extra`. `ConditionVirtualization=vm` alone is
true in *every* VM, but the virtiofs tag only exists when the VM was launched by
`mkosi vm` with a runtime tree. Under `bin/vm run` (either display mode) the mount
failed, and that one failed unit pinned `is-system-running` at `degraded` for the
entire boot — which is precisely the signal Q2 depends on. mkosi writes an
`fstab.extra` system credential naming that tag and nothing else does, so the
unit is now inert exactly when the share is absent.

## Results (2026-08-19, image `20260727160716`)

**Q1 — installed layout, read back from the installer:**
partitions `esp` + usr-A (verity-sig / verity / erofs) + three `_empty` usr-B
slots; root/home/swap correctly **deferred**. ESP holds `EFI/systemd/`,
`EFI/Linux/image_20260727160716_x86-64.efi`, `EFI/BOOT/`, `loader/`.
`loader/entries` → **0 files**. `/image/` → **absent**. Pure Type #2.

**Q1b — the greetd fix works.** In the Installer profile: `arch-install.service`
active, `greetd.service` inactive, `systemd.unit=multi-user.target` overriding the
`graphical.target` default. (Verified baked into the UKI by dumping its `.profile`
/`.cmdline` PE sections.)

**Q2 — first boot** (`arch-vmtest`): all partitions provisioned —
`/` = `/dev/mapper/root` btrfs on LUKS, `/usr` = `/dev/mapper/usr` erofs on
dm-verity, `/home` btrfs, LUKS swap active, `/boot` the ESP. Secure Boot
`enabled (user)`, `Measured UKI: yes`, systemd-boot 261-1-arch.

**Q2 — second boot, TPM2 unseal:**
`Automatically discovered security TPM2 token unlocks volume.`
`systemd-tty-ask-password-agent --list` empty → **no passphrase was ever
requested**. `cryptsetup luksDump` shows `Tokens: 0: systemd-tpm2`.

**Q2 — clean boot:** on image `20260727160716` this needed `mnt-shared.mount`
masked at runtime (which is how the unit was identified as the sole blocker).
Re-run on the rebuilt `20260819002736`, which carries the fix, it is clean with
no intervention: `systemctl is-system-running` = **`running`**,
`systemctl --failed` **empty**, on the target's very first boot — and the
Installer medium reports `running` too.

## FIXED: A/B slot sizing (found and fixed 2026-08-19)

`systemd-sysupdate` streams the new `/usr` into the inactive slot and dies at 98%:

```
File too large
Failed to decode and write: Argument list too long
(sd-import-raw) failed with exit status 1: Argument list too long
```

Measured, from `sfdisk -J` on the target and `stat` on the artifacts:

| | bytes | note |
|---|---|---|
| usr-B slot | 8,589,934,592 | exactly 8 GiB — the `SizeMinBytes=8G` floor |
| usr-A slot | 8,660,631,552 | `CopyBlocks=auto` sized it to the **old** `/usr` |
| new `/usr` | 8,661,143,552 | |

It overshoots **usr-B by 67.9 MiB and usr-A by 500 KiB** — it fits in *neither*.

Cause (`mkosi.extra/usr/lib/repart.d/{22-usr-a,32-usr-b}.conf`, both
`SizeMinBytes=8G` / `SizeMaxBytes=10G`):

* usr-A has `CopyBlocks=auto`, so repart sizes it to the source `/usr` **exactly** —
  zero headroom for a future image;
* usr-B has no `CopyBlocks`, so it gets the 8 GiB **floor** — which `/usr` has now
  outgrown.

Both files' comments still say the slot "holds a fixed ~5G dm-verity erofs". That
is stale: `/usr` is now 8.07 GiB. The 8 GiB floor was already too small and the
`CopyBlocks=auto` sizing means **any** growth in `/usr` breaks the next update.

Proposed fix — give both slots the same fixed size with real headroom, e.g.
`SizeMinBytes=10G` + `SizeMaxBytes=10G` on both, so A and B are interchangeable
and hold today's 8.07 GiB with ~1.9 GiB spare. A partition larger than its erofs
is fine: dm-verity takes the data size from the verity metadata, not the
partition. NOTE THE TRADE-OFF, which is why this wasn't just applied: usr A+B go
from ~16.1 GiB to 20 GiB, and that ~3.9 GiB comes out of root (17.7 GiB → ~13.8
GiB on the 60 GiB test disk). 22-usr-a.conf's comment says root needs that space
for the on-device build's transient scratch. Sizing is a judgement call about the
real machine's disk — decide before changing it. Changing it needs a rebuild AND
a reinstall (partition geometry is laid down at install).

The bigger half of the problem, found while measuring: partitions with **no
`SizeMaxBytes`** are growable at the default `Weight=1000`, so repart hands them a
share of ALL free space. `esp` and `usr-a-verity` had no max, so they took **5.9
GiB each** on the 60G test disk against ~280 MiB and 68 MiB of real content — and
that scales with the disk, so on a 1 TB NVMe it would be a **~160 GB ESP and a
~160 GB verity-hash partition**. `50-root.conf`'s old comment predicted "root
~50G, home ~17G on a 90G disk" by counting only root and home; the measured layout
never matched, for exactly this reason.

### The fix (applied)

Every partition now has an explicit fixed size except root and home, which are
the deliberate 3:1 pair that absorbs the remainder. That makes the layout correct
at any disk size.

| file | before | after |
|---|---|---|
| `22-usr-a.conf` | 8–10G, sized by `CopyBlocks=auto` | `SizeMin=SizeMax=16G` |
| `32-usr-b.conf` | 8–10G → took the 8G floor | `SizeMin=SizeMax=16G` |
| `21-usr-a-verity.conf` | **unbounded** → 5.9G | `SizeMin=SizeMax=512M` |
| `31-usr-b-verity.conf` | 400M | `512M` (matches A) |
| `10-esp.conf` | 2G min, **unbounded** → 5.9G | `SizeMin=SizeMax=2G` |
| `bin/vm` | target default 60G | 100G (fixed parts total ~49G) |

`CopyBlocks=auto` stays on usr-a for *content*; it just no longer decides size.
`mkosi.repart/` is untouched — the medium is sized by mkosi with `Minimize=yes`,
so it has no free space to over-claim.

### Validated end to end (image `20260819015333`)

Geometry as designed, and A/B now byte-identical: esp 2.00 GiB, usr-A 16.00 GiB,
usr-A-verity 0.50 GiB, usr-B 16.00 GiB, usr-B-verity 0.50 GiB; root 45.7 GiB and
home 15.2 GiB on the 100 GiB target.

The A/B update — the exact 8.66 GB slot copy that failed before:

```
Successfully installed '…usr-x86-64.…raw' (regular-file) as '…3p7' (partition).
Successfully installed '…efi' as '/boot/EFI/Linux/image_20260819002736_x86-64+3-0.efi'.
✓ Successfully installed update '20260819002736'.
```

* both UKIs present in `/boot/EFI/Linux/`, new one with `+3-0` (TriesLeft=3);
* **`loader/entries` = 0** — no Type #1 leftovers;
* booting the updated slot (`vm run DISK --entry 20260819002736`) comes up on
  `IMAGE_VERSION=20260819002736`, `/usr` = `/dev/mapper/usr` erofs,
  `is-system-running` = **`running`**, zero failed units;
* after that successful boot the UKI is renamed to
  `image_20260819002736_x86-64.efi` — the counter is gone, i.e. sd-boot
  **blessed** the entry. Boot counting / auto-rollback works.

This also settles an assumption flagged earlier: usr-A is a 16 GiB partition
holding an 8.5 GiB erofs and it mounts and boots fine, so **a partition larger
than its erofs is confirmed OK** (dm-verity takes the data size from the verity
metadata).

### On real hardware

The geometry is written at install time, so adopting this needs a **reinstall**,
not just an update — do it before the machine is in daily use, or plan a `/home`
backup (homed volumes live in the home partition). There is no in-place fix:
growing usr-b would need free space immediately after it, and root/home sit there.

Headroom rationale: `/usr` went from the "~5G" the old comments assumed to 8.5 GiB
in about two months. 16G is ~2x today and costs 32G for A+B — ~3% of a 1 TB disk.
Under-sizing costs a reinstall, so err high.

## Build-artifact loss (2026-08-19) — READ THIS

The mkosi output dir had grown to **353 GB across 23 image versions** and filled
the disk (97%), which failed a build with `No space left on device` while
systemd-repart pre-populated the erofs in `/var/tmp`. Cleanup was approved for 21
stale versions, keeping the two newest.

**The cleanup script deleted all 23.** It used bash's `mapfile`, which does not
exist in zsh, so the array was empty and `for v in "${OLD[@]}"` expanded to a
single empty string — turning the loop body into `rm -f -- *`. Every version is
gone, including the two that were meant to be kept. Old versions are NOT
reproducible (their Arch package sets have moved on).

Salvaged by luck: `~/.cache/mkosi/vm-test-src/` held **hardlinks** to
`20260819002736`'s four split artifacts (UKI, usr erofs, verity, verity-sig), so
that data survived and served as the A/B update source above. Its bootable medium
`.raw` did not survive.

Lessons for next time: **never `rm` with an unguarded glob built from a variable**,
and don't assume bash builtins in this zsh environment. Prefer
`find … -maxdepth 1 -name 'image_<ver>_*' -delete` per explicit version.

**FIXED (2026-09-18):** `bin/build-image` had **no retention policy**, which is how
353 GB accumulated. It now prunes the output dir to the newest N versions (default
3, `--keep N|all`) after a successful build, deleting each version by an explicit
`find -maxdepth 1 -name "image_<ver>_*" -delete` — never a glob built from a
variable — and refusing to prune the version it just built.

## What's left

1. ~~Validate the `mnt-shared.mount` fix from a rebuilt image.~~ **DONE** — see
   Q2 above. (That rebuild also pulled in the uncommitted `mkosi.finalize` /
   `mkosi.postinst.chroot` cargo/sccache work and ~3 weeks of Arch updates; the
   build succeeded and the resulting image installs and boots clean.)
2. ~~Q3: fix the slot sizing, then re-run the A/B update.~~ **DONE** — see the
   A/B slot sizing section above.
3. ~~`bootstrapping-todo.md` needs updating.~~ **DONE** (`6652888`).
4. ~~Add a retention policy to `bin/build-image`.~~ **DONE** (2026-09-18) — see
   the artifact-loss note. Logic tested in a sandbox against a synthetic output
   dir (keep=N / keep=all / current-version protection / unversioned files left
   alone). The 2026-09-18 build ran it for real against 2 versions (a correct
   no-op), but **the deletion path has never fired against real mkosi output**.
   It will on the first build that makes a 4th version, which will delete
   `20260819015333` (not reproducible; the image carrying the sizing fix).
   Pass `--keep all` on that build if that version should survive. (The
   2026-09-21 build made only a 3rd version, so it was again a no-op.)
5. **Real hardware needs a reinstall** to pick up the new partition geometry.
6. **Only one A/B direction was exercised.** The update applied an *older* version
   (`20260819002736`, the salvaged artifacts) onto a newer install, so the
   updated slot had to be selected explicitly with `--entry`. A natural
   newer-over-older run — where sd-boot picks the new slot as the default — is
   now **CONFIRMED** (2026-09-21); see the Q4 section at the top.
7. Non-blocking warnings seen in the first-boot journal, none of which failed a
   unit: `systemd-tpm2-setup: TPM key integrity check failed` (fresh vTPM, SRK
   regenerated); `systemd-growfs: crypt_resize() of /dev/vda9 failed: Operation
   not permitted`; polkit `/etc/polkit-1/rules.d` read-only; wireplumber writing
   to `/.local/state` as root. Worth a look eventually.
8. **Build speed**: see the build-time analysis in the 2026-09-18 section.
   Still unmeasured: how the ~400s of package-install time splits between alpm
   hooks, extraction, and yay's AUR RPC.
   (Warm build times for reference: V1 899s, V2 1321s — the latter shared the
   host with a running VM.)
9. **Push decision** still pending: 22 commits ahead of `origin/mkosi`.
10. **Exercise the root FIDO2 enrollment on real hardware** — the branch a VM
    cannot reach (no FIDO2 passthrough). Until then every installed root is
    TPM-only and unrecoverable from a recovery medium.
11. **Make the first-login YubiKey enrollment survivable**: tell the user a tap
    is required, and retry instead of failing after 37s. See the 2026-09-22
    section above; it will bite again on the real-hardware install.
12. **Rotate the PIV PIN** (`ykman piv access change-pin`) — a
    `SYSTEMD_LOG_LEVEL=debug homectl` run printed it in plaintext on 2026-09-22.
13. **`bootstrapping-todo.md` still lists the A/B direction as an open item**
    (added by `6652888`). It now has uncommitted edits of the user's, so it was
    deliberately left untouched — fold the Q4 result in alongside those.

## The medium must satisfy its own baked repart minimums (fixed 2026-09-22)

`bin/vm run` (the medium booting its DEFAULT profile, i.e. self-provisioning
into a normal system) died in the initrd:

```
Failed to start Repartition Root Disk.
Timed out waiting for device /dev/disk/by-designator/root.  →  Emergency Mode
Can't fit requested partitions into available free space (71.9G), refusing.
```

Cause: `6a36902` gave `mkosi.extra/usr/lib/repart.d/21-usr-a-verity.conf` a
`SizeMinBytes=512M` (it previously had no size constraints at all). Those baked
definitions are what the medium runs against ITS OWN layout on first boot, and
the medium's verity partition was ~86M, packed between `verity_sig` and `usr`
with no free space on either side. repart cannot grow a partition boxed in like
that, so the whole run fails — note it fails ENTIRELY, it does not skip the one
partition, so root is never created.

Measured with `systemd-repart --dry-run` on the host (fast, no boot needed):
the threshold is exactly the existing size — 86M floor plans fine, 87M and above
fail. `usr-a`'s 16G floor is harmless because it is the LAST partition and all
the free space follows it.

Fix: `mkosi.repart/11-usr-verity.conf` now carries `SizeMinBytes=512M` so the
medium ships the same verity slot size the installed system demands
(`Minimize=yes` stays; the floor wins). Medium grew 12.7G → 13.3G. Verified on
image `20260922004002`: repart is `active (exited)`, `is-system-running` =
`running`, zero failed units, and the layout comes up esp 2G / verity 512M /
usr 16G / empty B slots / swap 4G / root 41G.

**The rule this leaves behind:** any floor added to `mkosi.extra/usr/lib/repart.d/`
must be matched in `mkosi.repart/` (or be satisfiable by growing into free space
at the END of the medium), or the medium's own default-profile boot breaks. Only
that path is affected — installed targets create partitions fresh, and the Live
and Installer profiles mask repart, which is why every test since `6a36902`
passed.

Debugging shortcut worth keeping: `systemd-repart --dry-run=yes
--definitions=mkosi.extra/usr/lib/repart.d IMAGE.raw` reproduces the failure on
the host in seconds. On a medium copy, `truncate -s 90G` then `sgdisk -e` first,
so the GPT describes the grown disk the way the guest sees it.

## First login: YubiKey PIV enrollment needs a TOUCH (2026-09-22)

`user-first-login-playbook.yml` failed on a fresh medium boot at
`roles/user/tasks/first-login.yml` → **Enroll YubiKey PIV**:

```
sudo -n homectl update mnussbaum --pkcs11-token-uri=pkcs11:…;id=%03
Successfully logged into security token 'arch-ansible SecureBoot'.
Operation on home mnussbaum failed: Failed to execute operation: Input/output error
```

homed's own journal is where the reason lives (`journalctl -u systemd-homed`),
not the Ansible output:

```
Successfully logged into security token … with PIN.
Failed to decrypt key on security token: No user has logged in
```

**Cause: PIV slot 9D is `PIN required: ONCE` + `Touch required: CACHED`**
(`ykman piv keys info 9d`). The decrypt blocks on a physical tap; nothing in the
task says so, and the failure takes ~37s, which reads like a hang.

Once touched, the token half works, but the operation ALSO needs the plaintext
password in the same attempt — the record's only other factor — and homed fails
fast (1–3s) and retries when it does not get one, which looks like an endless
password prompt. It succeeds when the dialog is answered AND the key is tapped
within the same attempt.

Narrowing this, for next time:
* `homectl authenticate <user>` tests the password ALONE — no token, no touch.
  It passing proves the password and the ask-password path are fine.
* `homectl update <user> --real-name="$(current value)"` is a harmless
  metadata-only update; it needs no prompt at all, so it separates "updates are
  broken" from "this particular update is".
* The password homed wants here is the recovery secret in pass
  (`linux_users/<user>/recovery-key`), the same value baked into the image as
  `/usr/lib/credstore/home.new-password`. Comparing the two by sha256 (stripped
  of the trailing newline) confirms the image and pass agree.
* Verify a candidate against the record's yescrypt hash without typing it:
  `crypt(3)` via ctypes on `privileged.hashedPassword` from
  `homectl inspect <user> --json=short` (root sees the privileged section).

**NEVER run `homectl` with `SYSTEMD_LOG_LEVEL=debug`.** It dumps the whole user
record it sends, INCLUDING `secret.tokenPin` in plaintext (and the hashed
passwords). Doing that during this debug leaked the PIV PIN into a session
transcript; rotate with `ykman piv access change-pin` if it happens.

Worth fixing in the playbook: the enrollment task should say a tap is required
and retry, rather than failing opaquely after 37s.

## Root needs a recovery factor: FIDO2 at first boot (2026-09-23)

An installed root had ONE keyslot, bound to the TPM2 token repart enrolls — and
that token is a **signed PCR 11 policy** (`tpm2-pcrs=[]`,
`tpm2_pubkey_pcrs=[11]`), not PCR 7. PCR 11 is extended at every boot phase and
the signatures cover only the initrd of a normal signed UKI boot, so it cannot
unlock from a recovery medium or any booted system — by design, so a running OS
cannot unseal the disk. Consequences: such a root is unrecoverable once its
measured boot stops matching (TPM cleared, board swapped), and
`bin/recovery-mount` can never open it. Nothing enrolled a second factor;
`bin/revoke-luks-yubikey` had always assumed a FIDO2 slot nothing created.

Now: `50-root.conf` uses `Encrypt=key-file+tpm2`, which with no `--key-file`
adds a zero-length-key slot beside the TPM2 one (systemd-repart's documented
hook for first-boot setup). `luks-enroll-fido2.service` runs
`bin/enroll-root-fido2` on first boot, before login: it authorizes with that
empty key, enrolls a FIDO2 token and wipes the empty slot in ONE
`systemd-cryptenroll` call. If no key turns up within 120s it wipes the empty
slot anyway and warns — root stays TPM-only, but the disk is never left openable
with an empty password. Blocking the boot instead would brick a machine whose
YubiKey is elsewhere.

**Still unverified: the FIDO2 enrollment itself.** QEMU here has no FIDO2
passthrough — the vsock relay carries pcscd (PIV/smartcard), not FIDO2 HID — so
that branch first runs on real hardware. What a VM exercises, and what was
verified on image `20260922233147`, is the no-key fallback.

**Correction (2026-09-23, same day):** the first version of this used an
empty-key bootstrap slot (`Encrypt=key-file+tpm2`) because the TPM2 token was
believed unusable post-boot. That was wrong, and the belief came from
over-generalising a RECOVERY boot, where a different UKI means PCR 11 can never
match. On the volume's own booted system `systemd-cryptenroll
--unlock-tpm2-device=auto` works — measured, and what AstrOS uses to enroll its
recovery key at first boot. So the bootstrap slot is gone, along with the window
in which an empty password opened root, and a factor can be added later from any
normal boot:

```
systemd-cryptenroll /dev/disk/by-designator/root-luks --unlock-tpm2-device=auto --fido2-device=auto
systemd-cryptenroll /dev/disk/by-designator/root-luks --unlock-tpm2-device=auto --recovery-key
```

### PCR 7 + 11 (2026-09-23)

`TPM2PCRs=7` on root and swap (`repart.d`, systemd >= 259) adds a literal PCR 7
binding next to the signed PCR 11 policy repart takes by default from mkosi's
`SignExpectedPcr=` key. Verified on a fresh install: `tpm2-pcrs: [7]`,
`tpm2_pubkey_pcrs: [11]` — `TPM2PCRs=` ADDS to the signed policy rather than
replacing it.

Mirrors the two reference images, which differ: **ParticleOS** sets no
`TPM2PCRs=` and so binds signed PCR 11 only; **AstrOS** sets `TPM2PCRs=7` and
advertises "sealed against PCR11+7". PCR 7 alone is brittle across firmware and
Secure Boot changes; signed PCR 11 alone leaves the seal indifferent to Secure
Boot being switched off.

STILL OPEN, and the reason the FIDO2 factor matters: on real hardware the seal
must be taken when PCR 7 is FINAL. If the target's first boot is also the boot
where sd-boot auto-enrols the keys from `/loader/keys/auto`, it may seal against
the setup-mode value and fail on every later boot. VMs hide this — `bin/vm`
hands QEMU a varstore with the cert already enrolled, so PCR 7 is stable from
the start. Order on hardware: enrol keys, reboot with Secure Boot on, then
provision.

## When systemd 262 lands in Arch (surveyed 2026-09-23)

v262 was released 2026-09-22; Arch core is still 261.3, so none of this is
actionable yet. Several items land squarely on work done in this branch.

**Adopt, roughly in this order:**

1. **`systemd-cryptenroll-firstboot.service` replaces our enrollment service.**
   Upstream now ships a first-boot wizard for "enrolling additional unlock
   mechanisms … in TPM-enabled scenarios which default to unattended TPM-based
   disk encryption, but where enrollment of additional mechanisms to decrypt the
   disks for recovery purposes shall be suggested to the user" — i.e. exactly
   `luks-enroll-fido2.service` + `bin/enroll-root-fido2`. Swapping to it deletes
   ~90 lines of ours. Check first how it picks the device and whether it can be
   pointed at a YubiKey unattended.
2. **`systemd-cryptenroll --unlock-headless`** = `--unlock-tpm2` when a TPM
   exists, else `--unlock-empty`. That is our authorization logic, including the
   TPM-less case we do not handle.
3. **pcrlock, for the PCR 7 brittleness we knowingly accepted.** v262 adds
   Varlink methods to relax policy before an fwupd-prepared firmware update,
   `--strict=` so a requested PCR cannot be silently dropped from a policy, and
   policy re-prediction after an update via
   `systemd-sysupdate-notify-pcrlock.socket`. We use no pcrlock today; this is
   the principled fix, with the FIDO2 factor as the fallback rather than the
   plan.
4. **`systemd-sysupdate cleanup` + its new persistent file database**: files it
   installed that no current match pattern claims are now removed. This branch
   exists because stale boot entries accumulated, so it is on-theme.

**The trap — do not adopt without deciding:** signed-policy references
(`systemd-measure --policyref=`, `--tpm2-public-key-policyref=` in cryptenroll
and repart, `ukify --sign-initrd-pcrs`). Today the UKI signs expected PCR 11
values for the LATER boot phases too, which is precisely why post-boot
`systemd-cryptenroll --unlock-tpm2-device=auto` works and why the bootstrap
keyslot could be dropped (see the PCR 7 + 11 section). An initrd-only signed
policy is stronger — a running OS then cannot unseal the disk — but it BREAKS
that enrollment path, ours and AstrOS's. Adopting it means moving enrollment
into the initrd or authorizing it with a different factor.

**Explicitly NOT for us:** `bootctl link-auto` and
`systemd-sysupdate-notify-bootctl.socket`. `bootctl link` writes Boot Loader
Spec **Type #1** entries — the thing this whole branch retired.

**Housekeeping on the 262 rebuild:**

* `systemd-sysupdate.service`/`.timer` are renamed to `…-update.service`/
  `.timer` (compat symlinks exist). We reference neither.
* `systemd-sysupdated` is deprecated in favour of Varlink straight to
  `systemd-sysupdate`; we already drive the binary directly, for the
  `--transfer-source` reason recorded in `bin/update-system`.
* **NvPCR anchoring changed** and is the most likely surprise: definitions must
  ship in the UKI, which must embed an initrd-bound signed policy
  (`ukify --sign-initrd-pcrs`). Existing NvPCRs auto-upgrade, and the old anchor
  secret in /var/lib and the ESP is removed. We do extend the `cryptsetup`
  NvPCR at boot, so watch the first 262 build for it.
* TPM2 PIN enrollment can now be hardened with Argon2id (`--tpm2-with-pin=yes`),
  if a PIN is ever added.

## CRITICAL test-harness gotchas (these cost hours — do not relearn)

1. **First-boot testing needs the target attached ALONE** — `bin/vm run`
   (headless or `--gui`), never `vm run DISK`. The medium is also a
   mkosi-layout disk, so first-boot repart provisions the WRONG one and the boot
   hangs on `/dev/disk/by-designator/root`.
2. **`truncate -s 60G` on an existing 60G file is a NO-OP.** `vm install`
   now does the `rm -f` for you.
3. **The post-install auto-reboot into the target CANNOT be validated in QEMU.**
   `install-system` writes an efibootmgr entry + BootNext, but OVMF re-derives
   boot order from qemu's `bootindex` every boot and prunes the manual NVRAM
   entry. VM-only artifact; don't chase it.
4. **Console split:** the cmdline ends `console=ttyS0 console=tty0`, so last wins
   and `/dev/console` = tty0. Kernel messages go to *both*, but **userspace
   prompts go only to tty0** — invisible on serial. A headless boot that hits one
   just goes silent. `bin/vm`'s screendump is how you see it.
5. **First boot asks TWO questions on tty0**, not one: `systemd-firstboot`
   `--prompt-hostname` *and* `--prompt-root-password` (see
   `mkosi.extra/…/systemd-firstboot.service.d/10-prompt-hostname.conf`). Both need
   credentials in an unattended boot; `vm run DISK` supplies both.
6. **Host kernel/module mismatch breaks mkosi.** After a host `pacman -Syu` that
   upgrades `linux`, the running kernel's modules are gone until you reboot.
   mkosi's sandbox then fails to mount overlayfs with `OSError: [Errno 19] No
   such device: 'newroot/buildroot'`. Check `uname -r` against
   `ls /usr/lib/modules`, then reboot the host.
7. **Don't `pgrep -af mkosi` (or `ps` its full cmdline).** `build-image` passes
   `ANSIBLE_WIFI_NETWORKS` as base64 on mkosi's command line, so that prints
   every wifi PSK. Use `pgrep -f` with no `-a`, or match by PID.
8. **Wrap long runs with `run_in_background` directly**, not `nohup … &` inside
   one; otherwise the completion notice reports the wrapper's exit code, not the
   build's (a failed build once reported "exit 0" this way). Also note `ls` is
   aliased to `eza` with icons in this shell, so `ls | grep '^name'` silently
   matches nothing; use `find -printf` in scripts.
9. **The guest's root shell has aliases**: `cat` is `bat` and `ls` is `eza`, so
   a `--run` command gets bat's error text and icon-prefixed listings. Also
   **`/etc/os-release` does not exist** in this image — read `/usr/lib/os-release`
   (e.g. `grep ^IMAGE_VERSION= /usr/lib/os-release`) to identify the booted slot.
10. **Only ONE medium VM at a time.** `vm run` (no disk) hardcodes
    `--vsock-cid=3`, so a second one dies instantly with "VSock connection ID 3
    is already in use by another virtual machine". mkosi suggests
    `VsockConnectionId=auto`; worth adopting. A `vm run DISK` guest uses no
    vsock and is unaffected.
11. **`vm run` MUTATES the built medium** unless `--ephemeral` is passed: mkosi
    grows it to `--runtime-size=90G` and the default profile self-provisions
    into it. Use `--ephemeral` for throwaway boots, or work on a
    `cp --sparse=always` copy (12G real for a 90G apparent file).
12. **Anything new under `bin/` must be `git add`ed before it ships.**
    `arch_ansible_stage_srctree()` copies `git ls-files`, so an untracked script
    never reaches `/usr/share/arch-ansible` — while a new unit under
    `mkosi.extra/` DOES ship, straight from the working tree. That asymmetry
    once produced an image whose service was installed and enabled but skipped
    itself on `ConditionPathExists`.
13. **`cryptsetup open --test-passphrase --key-file=X` LIES on the volume's own
    running system**: it succeeds whatever key you pass, because the volume key
    is already in the kernel (a deliberately wrong key also reported "Key slot 1
    unlocked"). To ask what a LUKS header really holds, read it offline — find
    the partition offset with `sfdisk -J IMAGE`, then parse the LUKS2 JSON at
    `offset+4096` (NUL-terminated) in Python. That needs no root, no loop device
    and no VM, and it is how the empty-slot wipe was actually confirmed.
14. **Do NOT press Ctrl+Alt+F<n> in the QEMU GTK window** — without the keyboard
   grab it hits the HOST compositor. `bin/vm --gui` sets `grab-on-hover=on`,
   and Ctrl+Alt+G toggles the grab by hand; the default runs are headless anyway.

## VM interaction channels

`bin/vm` is the single entry point. `bin/run-image` and `bin/boot-disk` are gone
(2026-09-21), and `vm live`/`vm boot` became one `vm run [DISK]` (2026-09-22):
what you boot is the argument, not the command.

- `bin/vm run DISK` / `bin/vm install TARGET` — headless serial + HMP monitor +
  screendump, scripted health checks, non-zero exit on a missed checkpoint. The
  journal dump is automatic when a run does NOT reach `running`.
- `bin/vm run DISK --gui` — a window instead of the scripted checks; serial
  captured to the run dir's `<disk>-serial.log`. Autologin is always on, and the
  first-boot hostname/root-password answers are fixed test credentials
  (`arch-vmtest` / `root`) rather than flags.
- `bin/vm run` (no disk) — boots the medium through `mkosi vm`, and mounts host
  `.qemu-host-shared/` ↔ guest `/mnt/shared` (virtiofs). Note the guest path is
  `/mnt/shared`, not `/run/host/shared`. `--device DISK` attaches a second disk
  to install onto or repair; `--ephemeral` boots a throwaway snapshot.
- `--share DIR` (disk runs) is a separate virtiofs mount at `/mnt/vmtest`, tag
  `vmtest-share`, deliberately NOT mkosi's `/run/host/shared`.
- `--tpm-state DIR` overrides the TPM state dir on BOTH modes. The default is
  per-VM (`DISK.tpm` for a disk, `<output>/tpm` for the medium), so a medium
  booted to RECOVER a target cannot unseal that target's TPM2-bound LUKS root —
  point both at one dir to share a TPM, as install and first boot do on real
  hardware. (Dropped in the 2026-09-22 consolidation as "not necessary" and
  restored the same day when recovery testing needed exactly it.) The path must
  be short: swtpm's control socket lives in it and AF_UNIX caps at ~108 bytes.
- Flags that no longer exist, deliberately: `--boot-device` (`vm run DISK` is the
  safe version — see gotcha #1), `--runtime`, `--journal`, `--hostname`,
  `--root-password`, and `ARCH_ANSIBLE_VM_CPUS`/`_RAM` (`--memory`/`--cpus`
  cover both modes now).
- Sizing: one default for both modes, host CPUs − 2 and 8G. Measured cost on a
  scripted disk boot is ~6s versus 4 CPUs (18s → 24s); an earlier 114s outlier
  was host contention, not the defaults.
- **qemu-ga IS running in the guest** (this note previously said it was not —
  corrected 2026-09-22). `vm run` with no disk wires its socket at
  `/tmp/qemu-guest-agent.sock`, which gives ROOT COMMAND EXECUTION in a live VM
  from the host — including one a human is sitting in front of, without touching
  their session. It is how the first-login failure below was diagnosed. Talk to
  it with `guest-exec` + `guest-exec-status` (capture-output, base64 out-data)
  and `guest-file-open/write/close`; `guest-ping` checks it is alive. Only the
  medium path wires it up; a `vm run DISK` guest has no agent (use `--run`).
- QEMU's unix monitor accepts **one** client; `bin/vm` holds it while running.

## Git state

HEAD `19abeb1` on branch `mkosi`. **22 commits ahead of `origin/mkosi` — NOT
pushed** (push decision still pending). Working tree clean.

Since 2026-09-21: `c91855a` (retention), `61d6736` (yay over hkp), `521dd5e` +
`ffba894` + `021f6a5` (docs), `e1e0652` (bin/vm consolidation), `a19b2b2` (docs
sweep), `1c7452d` (`vm run [DISK]` merge), `60fec37` (mkosi cache env vars),
`19abeb1` (medium verity floor).

Scope discipline has held all along: the nvim/AUR/build-cache changes are separate
and must be committed apart from the installer work. Use `git add -p` for mixed
files.

## Key files

- `bin/install-system` — the installer (`--guided` menu + one-shot `--yes DISK`).
- `bin/vm` — the one VM command: `live`, `install`, `boot` (+ `--gui`).
- `mkosi.uki-profiles/25-install.conf` — Installer UKI profile cmdline.
- `mkosi.extra/usr/lib/systemd/system/arch-install.service` — auto-runs the guided
  installer on tty1, gated on `arch.install`.
- `mkosi.extra/usr/lib/repart.d/*` — baked device layout; `10-esp.conf` has
  `CopyFiles=/boot:/`; root/swap `Encrypt=tpm2`; root/home/swap created at the
  target's FIRST BOOT, not at install.
- `bin/build-image` — builds the image; `bin/vm` — the single VM entry point
  (`live` / `install` / `boot`, `--gui` for a window).
- `bootstrapping-todo.md` — the E2E checklist; Type #2 item ~line 328.
