# Issue: `bin/update-system` fails in the QEMU VM — out of disk during build

Status: **fix implemented 2026-06-01, pending on-device VM verification.**
Captured 2026-05-31 from the VM run logged in `.qemu-host-shared/noroom`.

## Symptom

`bin/update-system` failed. The error is **not** in the update/`updatectl` step —
it's earlier, in the build step it calls (`bin/update-system:70` →
`bin/build-image` → `mkosi`). `systemd-repart` died while sizing the `usr`
partition:

```
‣  Generating disk image
Pre-populating erofs filesystem of partition 12-usr.conf to calculate minimal partition size
Preparing to populate erofs filesystem.
Failed to copy '/buildroot/usr' to '/var/tmp/.#repartb9c7aeba9ea42690/': No space left on device
‣ "systemd-repart … --root=/buildroot … /work/home/mnussbaum/.cache/mkosi/mkosi-workspace-sk25ffnv/staging/image_20260531175923_x86-64.raw …" returned non-zero exit code 1.
```

(The `updatectl` "Could not parse JSON job object" noise seen earlier is a red
herring — the build never produced artifacts, so there was nothing to install.)

## Root cause

`mkosi.repart/12-usr.conf` builds the `usr` partition with `Format=erofs`,
`Minimize=yes`, `CopyFiles=/usr:/`. To compute the minimized size, repart first
copies the **entire ~5.4G `/usr`** into a temp dir under `/var/tmp`. That copy
ran out of space.

Everything mkosi does is pinned to `~/.cache/mkosi`:

- `mkosi.conf:30-32` — `CacheDirectory`, `PackageCacheDirectory`,
  `BuildDirectory` all under `~/.cache/mkosi`
- `bin/build-image:43,57` — output dir `~/.cache/mkosi/images/image`
- mkosi's **workspace** is there too (see the path in the repart command:
  `…/.cache/mkosi/mkosi-workspace-…/staging/…`). Inside mkosi's sandbox,
  `/var/tmp` — where repart staged the 5.4G copy — is backed by that workspace.

So `/var/tmp` resolves onto `~/.cache/mkosi`, which sits on the home partition.
`df` from the failing VM:

```
/dev/mapper/home-mnussbaum   17G   17G  563M  97%  /home/mnussbaum   ← 563M free
/dev/mapper/root             22G   53M   21G   1%  /                 ← 21G free, unused
/dev/mapper/usr             5.4G  5.4G     0  100% /usr
```

`~/.cache/mkosi` is a **plain directory on `/home`** (563M free), not its own
mount. A 5.4G copy can't fit → ENOSPC.

## Why the intended escape hatch didn't help

`bin/setup-mkosi-cache-volume` is supposed to mount a dedicated **60G btrfs
loopback** at `~/.cache/mkosi` (`:7-9`) to give the build room (and reflink/COW).
In this VM it was never set up (`df` shows no separate mount there), so mkosi
silently fell back to building on the nearly-full 17G home partition.

And it **can't** work as written here: the loopback image lives at
`~/.cache/mkosi.img` on `/home`, but `/home` is only 17G total — a 60G image
can't fit. Meanwhile the 21G-free root fs sits unused (and looks ephemeral —
53M used, factory-reset shape — which is presumably why the cache was parked
under `/home` originally).

## Bottom line

On-device builds write all transient data (workspace, sandbox `/var/tmp`, cache,
output) into `~/.cache/mkosi` on the 17G home partition, which had 563M free —
far short of the ~5.4G+ that repart's erofs-sizing copy alone needs. The
intended fix (a 60G cache volume) wasn't mounted and wouldn't fit on `/home`
anyway.

## Fix options (not yet decided / implemented)

1. Point mkosi's workspace + `TMPDIR` at the 21G-free root fs (if root is
   persistent enough for a build's lifetime) so the 5.4G copy has room.
2. Resize the on-device home partition, or shrink the cache-volume image so it
   fits, then run `bin/setup-mkosi-cache-volume`.
3. Free space on `/home` (it's at 97%) as a stopgap.
4. Reconsider whether on-device builds are viable given the device's writable
   space layout (root appears ephemeral, home is small) — may need a dedicated
   build/scratch partition sized for a full image build.

Open question to resolve first: is `/dev/mapper/root` (`/`) persistent for the
duration of a build, or wiped? That determines whether option 1 is safe.

## Resolution (Option 1, implemented 2026-06-01)

**Open question answered: root is persistent.** `mkosi.extra/usr/lib/repart.d/50-root.conf`
declares root as btrfs with `Subvolumes=/var` and `FactoryReset=yes` —
`FactoryReset` only wipes on an *explicit* factory reset (`systemd.factory_reset=1`
/ GPT reset flag), never on a normal boot. So root (with `/var`, ~21G free,
TPM2-encrypted) is safe for build scratch, and a factory reset discarding a
regenerable cache is correct. This is consistent with the hermetic plan, which
designates root's `/var` as the home for mutable state (plan-usr-hermetic.md
Decision line 49, layout line 79) — the update staging dir
`/var/lib/arch-ansible/updates` already lives there.

**Root cause of the *exact* failure:** mkosi's `WorkspaceDirectory` defaults to
the *invoking user's* `~/.cache/mkosi` (`config.py:workspace_dir_or_default`),
**independent of `CacheDirectory`**. The workspace backs the sandbox's `/var/tmp`,
where `systemd-repart` stages its ~5G `/usr` copy to size the erofs slot. On a
device that path is the 17G/563M-free homed `/home` → ENOSPC.

**Fix:** all build caches + mkosi scratch now live under a single base,
`${ARCH_ANSIBLE_CACHE}` (`bin/_cache_common.sh`), keyed off `ARCH_ANSIBLE_TARGET`
(the same transitional switch as `mkosi.conf.d/10-sources-*.conf`):

- host: `~/.cache` (unchanged behavior, except the build's cargo registry moved
  from `~/.cargo/registry` to `~/.cache/cargo/registry`)
- device: `/var/cache/arch-ansible` (encrypted root btrfs)

Files changed:
- `bin/_cache_common.sh` (new) — resolves + exports `ARCH_ANSIBLE_CACHE` and
  `ARCH_ANSIBLE_OUTPUT_DIR`; `arch_ansible_ensure_cache` creates the base
  (sudo-chown to the user on a device, where `/var/cache` is root-owned).
- `mkosi.conf` — `CacheDirectory`/`PackageCacheDirectory`/`BuildDirectory` →
  `${ARCH_ANSIBLE_CACHE}/mkosi*`; **added `WorkspaceDirectory=${ARCH_ANSIBLE_CACHE}/mkosi`**
  (the load-bearing line); `BuildSources`/`SkeletonTrees`/`ExtraTrees` cargo/
  sccache/yay/pacman-pkg/credstore paths → the base.
- `mkosi.finalize` — write-back destinations → `$ARCH_ANSIBLE_CACHE/*`, passed in
  via `mkosi --environment=` (finalize scripts don't inherit the caller's env);
  guarded with `:?`.
- `bin/build-image` — sources the helper, ensures the base, derives `output_dir`,
  passes `--environment=ARCH_ANSIBLE_CACHE=…`, relocated its `mkdir -p` set.
- `bin/update-system`, `bin/run-image`, `bin/burn-image`, `bin/rerun-postinst`,
  `bin/_credstore_common.sh` — source the helper; output/cache/pacman-db/credstore
  paths derived from the base.
- `mkosi.conf.d/10-sources-{device,host}.conf` — pacman-db-sync / yay-bin paths →
  the base.

**Validated (without a full build):** `mkosi summary` (host) resolves
`Workspace Directory`/`Cache Directory`/sources to `~/.cache/...`; `mkosi cat-config`
(device) resolves them to `/var/cache/arch-ansible/...` (only the existence check
on device-only `/usr` + `/var` source paths fails on the host, as expected). All
edited scripts pass `bash -n`.

**Backups:** no change needed. `roles/backup/files/restic-backup.includes` is
scoped to specific `$HOME` subdirs (Projects, Documents, …) and never touches
`/var` or `~/.cache`, so relocating the cache to `/var/cache` doesn't affect
backups (resolves plan Risk #6's concern for this case).

**Still to verify on-device (the 40-min build can't run here):**
1. `bin/update-system` in the QEMU VM gets past the repart erofs-sizing step
   (the original ENOSPC) and completes the build.
2. `/var/cache/arch-ansible` is created user-writable and the caches/output land
   there (not on `/home`); `df` shows `/home` no longer filling during a build.
3. `mkosi.finalize` write-back succeeds to `/var/cache/arch-ansible/*` (confirms
   `--environment=ARCH_ANSIBLE_CACHE` reaches finalize and its sandbox can write
   that path).
4. A second build reuses the primed `/var` caches (fast/offline), then the
   `updatectl` apply path (Stage D test plan 1→2→4) finally gets exercised.
