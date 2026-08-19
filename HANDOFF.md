# Handoff — Type #2 install validation (arch-ansible)

Repo: `/home/mnussbaum/Projects/arch-ansible`  ·  Branch: `mkosi`  ·  Updated: 2026-08-19

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

## What changed this session

### New: `bin/vm-test` — headless, scripted VM validation

The whole validation loop used to need a human at a QEMU GTK window. It doesn't
any more. `bin/vm-test` drives the same VMs with `-display none`, using two
properties of the image:

* OVMF mirrors the firmware console to the serial port, so sd-boot's menu is
  readable on serial and QEMU's HMP `sendkey` moves the selection;
* every profile has `console=ttyS0` plus an agetty autologin credential, so a
  root shell lands on a unix socket and commands round-trip over it.

```bash
bin/vm-test install ~/.cache/mkosi/test-target.raw   # Q1: fresh install
bin/vm-test boot    ~/.cache/mkosi/test-target.raw   # Q2: boot + health checks
bin/vm-test boot DISK --run 'CMD'                    # run CMD in the booted system
bin/vm-test boot DISK --share DIR                    # virtiofs DIR at /mnt/vmtest
bin/vm-test boot DISK --journal                      # + journal warnings
bin/vm-test install DISK --medium IMAGE.raw          # install a specific version
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
`mkosi vm` with a runtime tree. Under `bin/boot-disk` / `bin/vm-test` the mount
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
| `bin/vm-test` | target default 60G | 100G (fixed parts total ~49G) |

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
* booting the updated slot (`vm-test boot --entry 20260819002736`) comes up on
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

Follow-up worth doing: `bin/build-image` has **no retention policy**, which is how
353 GB accumulated. Adding a "keep last N versions" prune at the end of a
successful build would prevent a repeat.

## What's left

1. ~~Validate the `mnt-shared.mount` fix from a rebuilt image.~~ **DONE** — see
   Q2 above. (That rebuild also pulled in the uncommitted `mkosi.finalize` /
   `mkosi.postinst.chroot` cargo/sccache work and ~3 weeks of Arch updates; the
   build succeeded and the resulting image installs and boots clean.)
2. ~~Q3: fix the slot sizing, then re-run the A/B update.~~ **DONE** — see the
   A/B slot sizing section above.
3. **`bootstrapping-todo.md` needs updating** with the results above (all three
   validation questions now pass; steps 4 and 5 are re-verified on the Type #2
   installer).
4. **Add a retention policy to `bin/build-image`** — see the artifact-loss note.
5. **Real hardware needs a reinstall** to pick up the new partition geometry.
6. **Only one A/B direction was exercised.** The update applied an *older* version
   (`20260819002736`, the salvaged artifacts) onto a newer install, so the
   updated slot had to be selected explicitly with `--entry`. A natural
   newer-over-older run — where sd-boot picks the new slot as the default — is
   still unproven. Two consecutive builds would close that gap.
7. Non-blocking warnings seen in the first-boot journal, none of which failed a
   unit: `systemd-tpm2-setup: TPM key integrity check failed` (fresh vTPM, SRK
   regenerated); `systemd-growfs: crypt_resize() of /dev/vda9 failed: Operation
   not permitted`; polkit `/etc/polkit-1/rules.d` read-only; wireplumber writing
   to `/.local/state` as root. Worth a look eventually.

## CRITICAL test-harness gotchas (these cost hours — do not relearn)

1. **First-boot testing needs the target attached ALONE** — `bin/vm-test boot` or
   `bin/boot-disk`, never `run-image --boot-device`. The medium is also a
   mkosi-layout disk, so first-boot repart provisions the WRONG one and the boot
   hangs on `/dev/disk/by-designator/root`.
2. **`truncate -s 60G` on an existing 60G file is a NO-OP.** `vm-test install`
   now does the `rm -f` for you.
3. **The post-install auto-reboot into the target CANNOT be validated in QEMU.**
   `install-system` writes an efibootmgr entry + BootNext, but OVMF re-derives
   boot order from qemu's `bootindex` every boot and prunes the manual NVRAM
   entry. VM-only artifact; don't chase it.
4. **Console split:** the cmdline ends `console=ttyS0 console=tty0`, so last wins
   and `/dev/console` = tty0. Kernel messages go to *both*, but **userspace
   prompts go only to tty0** — invisible on serial. A headless boot that hits one
   just goes silent. `vm-test`'s screendump is how you see it.
5. **First boot asks TWO questions on tty0**, not one: `systemd-firstboot`
   `--prompt-hostname` *and* `--prompt-root-password` (see
   `mkosi.extra/…/systemd-firstboot.service.d/10-prompt-hostname.conf`). Both need
   credentials in an unattended boot; `vm-test boot` supplies both.
6. **Do NOT press Ctrl+Alt+F<n> in the QEMU GTK window** — without the keyboard
   grab it hits the HOST compositor. Moot now that `vm-test` is headless.

## VM interaction channels

- `bin/vm-test` — headless serial + HMP monitor + screendump. Preferred.
- `run-image` mounts host `.qemu-host-shared/` ↔ guest `/mnt/shared` (virtiofs).
  Note the guest path is `/mnt/shared`, not `/run/host/shared`.
- `boot-disk` — GUI, `--autologin`, serial captured to `$disk.serial.log`.
- The qemu-guest-agent socket exists but qemu-ga is NOT running in the guest.
- QEMU's unix monitor accepts **one** client; `vm-test` holds it while running.

## Git state

HEAD `2d6a1c2` on branch `mkosi`. **6 commits ahead of `origin/mkosi` — NOT
pushed** (push decision still pending).

### Uncommitted — CATEGORIZE before committing
**Type #2 / validation work:**
- `bin/vm-test` (new) — the headless harness.
- `mkosi.extra/usr/lib/systemd/system/mnt-shared.mount` — `ConditionCredential`.
- `mkosi.uki-profiles/25-install.conf` — `systemd.unit=multi-user.target`
  (the greetd fix; now verified working end-to-end).
- `bin/boot-disk` — `--autologin` flag + `smbios_args`.

**Separate in-flight work — DO NOT commit with the above:**
- `mkosi.finalize`, `mkosi.postinst.chroot` — cargo/sccache registry round-trip
  fixes (the user's own work).

Scope discipline has held all along: the nvim/AUR/build-cache changes are separate
and must be committed apart from the installer work. Use `git add -p` for mixed
files.

## Key files

- `bin/install-system` — the installer (`--guided` menu + one-shot `--yes DISK`).
- `bin/vm-test` — headless validation harness (this session).
- `mkosi.uki-profiles/25-install.conf` — Installer UKI profile cmdline.
- `mkosi.extra/usr/lib/systemd/system/arch-install.service` — auto-runs the guided
  installer on tty1, gated on `arch.install`.
- `mkosi.extra/usr/lib/repart.d/*` — baked device layout; `10-esp.conf` has
  `CopyFiles=/boot:/`; root/swap `Encrypt=tpm2`; root/home/swap created at the
  target's FIRST BOOT, not at install.
- `bin/build-image`, `bin/run-image`, `bin/boot-disk` — build/test harness.
- `bootstrapping-todo.md` — the E2E checklist; Type #2 item ~line 328.
