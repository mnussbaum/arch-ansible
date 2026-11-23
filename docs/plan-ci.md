# Plan: Testing and CI

References:
- `bin/vm` — the existing headless QEMU harness (serial root shell, sd-boot
  menu driving, screendumps, persistent varstore and swtpm)
- `bin/build-image --container --ephemeral-key` — the existing YubiKey-free
  build ([build-recovery-usb.md](build-recovery-usb.md))
- GitHub Actions hosted runners (free for public repos):
  <https://docs.github.com/en/actions/reference/runners/github-hosted-runners>;
  4 vCPU, 16G RAM, `/dev/kvm`, 6h per job, 20 concurrent jobs. Measured
  (see "Measured on a hosted runner"): one 145G disk with 88G free, 119G after
  deleting the preinstalled toolchains; no separate `/mnt`
- Actions cache: 10G per repo, LRU-evicted, 7-day retention at no cost
  (<https://github.blog/changelog/2025-11-20-github-actions-cache-size-can-now-exceed-10-gb-per-repository/>)

Goal: each item under "CI" in [todo.md](todo.md) runs as an automated check
with nobody at the keyboard and no YubiKey, leaving logs, serial output and
screenshots behind when it fails:

| todo item | Covered by |
|---|---|
| Container build | Stage 2 |
| Non container image build | Stage 6 |
| Install | Stage 3 |
| First boot | Stage 4 |
| Graphical boot with no failing units | Stage 4 |
| Network connectivity | Stage 4 |
| First login | Stage 5 |
| Pass access | Stage 5 |
| Firefox runs | Stage 5 |
| Terminal runs | Stage 5 |
| Nvim runs | Stage 5 |
| Recovery guide execution | Stage 7 |
| A/B update (added) | Stage 8 |
| update-system from a running system | Stage 8 |
| Restic data back-up | Stage 9 |
| Restore data from restic back-up | Stage 9 |

## What blocks it today

| Step | What blocks it |
|---|---|
| Build | The Secure Boot key and home recovery secret come from `pass`, which needs the YubiKey. The password store is cloned from private GitLab |
| Container build | `container_build` runs with `--tty`, and `--ephemeral-key` asks for the home password interactively |
| Native build | mkosi runs with `ToolsTree=/`, so it only works on a host running this image |
| Install / first boot | Already scripted by `bin/vm install` and `bin/vm run DISK` (firstboot credentials, autologin root on serial). `luks-enroll-pkcs11` already does nothing in a VM without `--yubikey` |
| First login | `first-login.yml` fails when there's no PIV cert (`failed_when: piv_uri.stdout \| length == 0`), and the homed login factor becomes the YubiKey |
| Pass access | Every store entry is encrypted to the real GPG key |
| Graphical session | Login goes through greetd on the VGA console, which serial can't see |
| Recovery guide | Parts 2 and 3 need the root GPG key USB, the paper key and YubiKeys; Part 7 restores from Backblaze |
| Resources | One version is ~23G of output (13G disk plus 10G of split artifacts), mkosi's incremental cache 13G, the package cache 2.6G, the mkosi workspace up to ~17G, an installed test disk ~15G; a cold build compiles Rust and AUR packages. A cold build peaked at ~50G of a runner's 119G |
| Host OS | Hosted runners are Ubuntu; `bin/vm` and the build expect Arch paths (`/usr/share/edk2/x64/…`) and tools |

## 1. Static checks and unit tests

Fast, no VM, on every push and pull request on a GitHub-hosted runner:

- `shellcheck` over `bin/`, `mkosi/mkosi.extra/usr/bin/`, `mkosi/mkosi.*`
  scripts and `container/`.
- `ansible-playbook --syntax-check` on both playbooks; `ansible-lint` once
  its findings are triaged (likely noisy at first).
- `systemd-analyze verify` on the units under `mkosi/mkosi.extra` and the
  roles' `files/`.
- `pytest` unit tests for the pure code: `bin/vm`'s `render_screen`,
  `menu_entries`, `build_qemu_args`, `build_live_cmd`, the `Shell` marker
  parsing against canned serial captures; `bin/_recovery_guide.py`; the
  filter plugins.
- `bin/generate-gpg-recovery-guide --preview` renders without error, so a doc
  edit can't break the printed guide.

Unit tests go through each module's public functions only, with fixed
inputs. The test list gets reviewed before any are written.

## 2. A CI identity and the container build

A build mode that needs nothing from `pass`, generated fresh per run and never
committed:

- a throwaway Secure Boot key (what `--ephemeral-key` mints today);
- a fixed home recovery secret;
- a throwaway GPG key with no passphrase, and a small password store
  encrypted to it, holding a canary entry and the entries first login reads
  (wifi, `host_secrets/<hostname>/pgpass`);
- the GPG key's secret half handed to the test VM at runtime (SMBIOS
  credential or the virtiofs share), never baked into `/usr`.

The container build gets `--tty` only when stdin is a terminal, so in CI the
`--ephemeral-key` home password is piped in, which `dr-entrypoint` already
reads from stdin:

```
printf '%s\n' "$home_password" \
  | bin/build-image --container --ephemeral-key --password-store <ci-store>
```

The VM firmware enrolls the throwaway cert in its varstore exactly as
`make_varstore` does with the real one, so Secure Boot, PCR 7 and the TPM
binding are exercised the same way as with the real key.

## 3. Install

`bin/vm install` already boots the Installer profile, runs `install-system
--yes /dev/vdb` and inspects the ESP. Its "validation question #1" checks
become assertions that fail the run: exactly one UKI in `EFI/Linux/`, no
`loader/entries/*.conf`, no `/image/`.

## 4. First boot, graphical target, network

`bin/vm run DISK` already exits non-zero unless `is-system-running` is
`running`. Added checks:

- `systemctl get-default` is `graphical.target` and it's active;
  `greetd.service` is active; `systemctl --failed` is empty.
- No pending `systemd-tty-ask-password-agent --list` entries; root, swap and
  home TPM2 slots carry the expected PCR/pcrlock binding (the check already
  prints these; it should assert on them).
- Network: `systemd-networkd-wait-online`, `resolvectl query archlinux.org`,
  `curl -fsS https://archlinux.org`. QEMU user networking stands in for
  wired; Wi-Fi isn't testable in a VM.
- A second boot of the same disk unlocks from the TPM with no prompt
  (the PCR 15 and pcrlock re-enrollment only takes effect then).

## 5. First login, pass, Firefox and terminal

First login assumes a YubiKey, so CI uses a software PKCS#11 token in its
place. A `ci` mkosi profile adds SoftHSM2 and registers it with p11-kit; the
test seeds a token with a key and cert at id 3 (PIV slot 9D's id).
`first-login.yml`'s `p11tool` discovery, `home-enroll-yubikey` and
`home-drop-baked-secret` then run unchanged, and the home ends up token-only,
as on hardware. Logins after that need the token PIN.

The token is seeded after first boot, from the serial shell, so
`luks-enroll-pkcs11` finds no token at first boot and behaves as it does in
any VM. Running `/usr/bin/luks-enroll-pkcs11` against the token afterwards
also tests LUKS PKCS#11 enrollment; unlocking with it in the initrd would need
SoftHSM there too, which is out of scope.

The `ci` profile is the only difference from the real image, and it only adds
packages. The image is built with no organizations.

Then, driven over serial and the QEMU monitor:

1. Log in on greetd by typing user and password/PIN with HMP `sendkey`, which
   is the real login path (PAM, `pam_systemd_home`, zlogin).
2. Wait for `~/.config/user-first-login-done`, or for the playbook's exit
   recorded in the journal; fail on any failed ansible task.
3. **Pass:** import the CI GPG key, `pass show ci/canary` matches. This tests
   the store clone, gpg config and pass, but not the card path.
4. **Sway, Firefox, terminal:** with `SWAYSOCK` from the user's runtime dir,
   `swaymsg exec` Firefox and Ghostty, then poll `swaymsg -t get_tree` for
   their `app_id`s; confirm Firefox loaded a local page (window title).
   `grim` inside and a QEMU `screendump` outside are saved as artifacts.
5. **Nvim:** as the user, `nvim --headless` starts with the image's config
   and exits cleanly with nothing in `:messages`; every plugin in the
   lockfile loads; opening a shell script, an Ansible tasks file and a
   Python file attaches the expected LSP clients and conform formatters;
   saving a script with an unquoted `$1` quotes it (the shellcheck fixer).
6. `systemctl --user --failed` is empty for the session.

## 6. Native build

A native build needs a host running this image, so it runs inside the VM:
boot the container-built medium (the live system is a supported build host,
`arch_ansible_select_build_target`), share the CI store and keys in, run
`bin/build-image` there, then install and first-boot *that* output through
stages 3 and 4. This also covers building from a live medium, which is the
recovery USB's job.

It's a second full build, inside a VM: ~50G of workspace, caches and output
in the guest on top of the 12G medium, which fits in a runner's 119G. It is
slower than the container build, with 4 nested vCPUs and at most ~12G of guest
RAM, so it runs weekly in its own job, seeded with the Actions caches through
the virtiofs share. If it ever outgrows the 6h limit, `--skip-postinst` still
covers what differs from the container build (`ToolsTree=/`, the live
medium's cache placement, `sync-aur` with a chroot).

## 7. Recovery guide

Run the guide's steps as written on a stock Ubuntu runner, which stands in for
the "borrowed computer":

| Part | In CI |
|---|---|
| 1. Set up the borrowed computer | Run the Debian/Ubuntu `apt` line from set-up-recovery-computer.md verbatim |
| 2. Rebuild GPG key from paper | Generate a test key and a test guide (`generate-gpg-recovery-guide` against a loop-device "USB"), then `restore-primary-gpg-from-paper --secrets --totp` onto another loop device and compare fingerprints |
| 3. Set up YubiKeys | Not testable without hardware; stays a manual check |
| 4. Backup access | A local restic repo (or MinIO) in place of B2 |
| 5. Make the recovery USB | Stage 2 |
| 6. Install | Stages 3–4 |
| 7. Restore files | Stage 9 |

The test keeps its own steps, one per part of the guide, and the docs stay
as they are. Each step cites the doc command it stands for:

```python
doc_command(
    "gpg-paper-recovery.md",
    "bin/restore-primary-gpg-from-paper /dev/sdX",
    replace={"/dev/sdX": loop_device},
    extra_args=["--secrets", secrets_file, "--totp", totp_file],
)
```

`doc_command` fails unless that exact text is in one of the doc's code
blocks, then substitutes the CI values and runs it. Changing a command in a
doc breaks CI until the test follows. Prompts are answered through the
scripts' existing flags or explicitly on stdin. Prose-only steps (the
Backblaze web UI, `iwctl`) stay untested.

## 8. A/B update

An update has to go to a newer version than the one installed, and a build
costs most of a runner. So instead of building twice, the update job installs
the **previous successful `main` run's** medium (fetched with
`actions/download-artifact` and that run's id) and updates it to this run's
image. That also tests the upgrade users actually take, from the last image to
the next. On the first run, with no previous medium, the stage is skipped with
a notice.

1. `bin/vm install` the previous medium, first boot it (stage 4 checks), then
   delete the medium to free its 12G.
2. Download this run's split artifacts (`usr`, `usr-verity`,
   `usr-verity-sig`, the UKI; ~10.5G), which the build job uploads beside the
   medium.
3. `bin/vm run DISK --share <artifacts> --run 'bin/update-system --no-build …'`
   applies them to the inactive slot, pointed at the share.
4. Boot again and check: `IMAGE_VERSION` in `/usr/lib/os-release` is the new
   one, `/usr` is the B slot, root and swap still unlock from the TPM with no
   prompt (the new UKI has to satisfy the signed PCR 11 policy), the entry is
   blessed (`bootctl list` shows no `+N-M` boot-counting suffix left), no failed
   units, and the home still opens with the token.
5. Rollback: install a UKI that can't reach `boot-complete.target` (e.g. one
   whose cmdline adds `systemd.unit=emergency.target`) as a newer version,
   boot it three times, and check sd-boot falls back to the previous entry.

Peak disk is about 15G for the installed disk plus 12G for the medium plus
10.5G of split artifacts.

## 9. Restic back-up and restore

`restic-backup --device` already backs up to a restic repo on a local block
device instead of B2, so CI attaches a blank disk to the VM as that device.
Only the B2 transport goes untested.

1. In the stage 5 VM, after first login, seed known files in the home and
   run a backup through the real path: `restic-backup.service`, with its
   password from `pass-credential@restic_backup_password` (a CI store entry),
   pointed at the attached disk. Check `restic-backup snapshots` lists it.
2. Attach the same disk to a freshly installed VM, log in, run
   `restic-backup restore --device …` (the restore-home.md command, cited
   through `doc_command`), and diff the restored files against the seeded
   ones. Then check that a second restore without `--overwrite` leaves a
   locally edited file alone.

This also serves as Part 7 of the recovery guide (stage 7).

## Runners and triggers

Everything runs on GitHub-hosted runners. Other free services don't fit:
GitLab.com's free tier is 400 minutes a month, less than one cold build.
Because the CI identity holds no real secrets, no job needs repository
secrets, so pull requests from forks are safe to run too.

| Tier | What | When |
|---|---|---|
| Fast | Stage 1 | Every push and PR |
| Image | Stages 2–5 and 7–9 | Push to `main`, nightly, manual, and PRs labelled `ci:image` |
| Slow | Stage 6 (native build in a VM) | Weekly and manual |

### Measured on a hosted runner

One cold `--ephemeral-key` container build with no caches, `--incremental=no`
and no split artifacts, on a standard `ubuntu-latest` runner:

| | |
|---|---|
| Total | 42 min: AUR packages ~24 (wluma 5, calibre-bin 5, pwvucontrol 3.5, claude-code 2.5), mkosi package install ~4, ansible postinst ~3 (287 tasks), finalize, erofs, signing and disk image ~9; the builder container under 1 |
| Disk | One 145G disk: 88G free, 119G after cleanup; peak use ~50G |
| Memory | 3.2G peak of 16G |
| Medium | 12G apparent, 9.3G allocated, 7.7G with `zstd -T0` (49s) |

With the AUR packages cached, a build should take ~18 min. Disk and time both
leave room, so jobs are split for parallelism, not to fit.

### Job layout

```
builder-container ──► build ──┬──► vm: install, first boot, first login,
     (weekly)                 │        back-up (stages 3–5, 9)
                              ├──► ab-update (stage 8, from the previous
                              │        run's medium)
                              └──► recovery-guide (stage 7, with the restore
                                       half of stage 9)
```

- **Builder container.** `container/Containerfile` plus the VM tools
  (`qemu-base`, `edk2-ovmf`, `swtpm`, `virt-firmware`, `virtiofsd`), pushed to
  GHCR (free for public packages) and rebuilt weekly or when its inputs
  change. Every job runs inside it with `--device /dev/kvm --privileged`, so
  `bin/vm` finds the same paths as on Arch, and no job installs packages
  on Ubuntu.
- **Disk.** Each job starts by deleting the runner's preinstalled toolchains
  (Android, .NET, GHC, CodeQL, Docker images; ≈30G).
- **Build job.** `--incremental=no`: mkosi's 13G incremental cache doesn't
  fit the 10G Actions cache. Split artifacts stay on (~10G more disk), so
  the A/B update stage can use them as built.
- **Actions cache** (≈4G total, within the 10G quota): the pacman package
  cache keyed on a hash of the package lists, `aur-repo` keyed on the AUR
  package versions (so `sync-aur` only compiles what changed), sccache, the
  cargo registry and nvim's site directory.
- **Handing the image on.** Two workflow artifacts with a few days'
  retention (artifacts on public repos don't count against a quota): the
  medium, `zstd`-compressed to ~7.7G and decompressed with `--sparse`
  downstream, and the split artifacts (~10.5G; the erofs `/usr` is already
  compressed).
- **Memory.** 16G total, so test VMs get 8G and the container's build
  leaves room for them by running in a separate job.

The heavy stages still run through one entry point, `bin/ci [stage...]`,
so a failing CI stage can be reproduced locally with the same command. It
writes everything (build log, serial logs, screendumps, journal excerpts)
under one output directory, which each job uploads as an artifact whether it
passed or failed.

## Code layout

`bin/vm` is 1369 lines with the reusable parts (Console, Shell, Vm,
`select_boot_entry`) inside a script. The e2e checks want those as a library:

```
pyproject.toml, uv.lock     uv project at the repo root; pytest as a dev
                            dependency, no runtime dependencies
src/arch_ansible_vm/
  console.py                serial console and the root shell over it
  qemu.py                   QEMU command line, swtpm, OVMF varstore
  sdboot.py                 sd-boot menu parsing and selection
  disks.py                  test-disk retention
  __main__.py               the `vm run` / `vm install` CLI
bin/vm                      PYTHONPATH=<repo>/src exec python3 -m arch_ansible_vm "$@"
bin/ci                      exec uv run --project <repo> pytest tests/e2e -m <stage>...
tests/unit/                 stage 1's unit tests
tests/e2e/                  one module per stage, a pytest marker each, and
                            the CI-only support code: the throwaway identity,
                            doc_command, shared VM fixtures
```

- `bin/vm` keeps its flags and behaviour; only where the code lives changes.
  It runs the package with plain `python3` rather than `uv run`, which would
  create a `.venv` in the image's read-only copy of the repo; the harness
  needs only the standard library.
- The library holds the VM harness only. CI-only pieces stay in `tests/e2e/`,
  since nothing else uses them.
- `uv` already ships in the image (`90-packages.conf`); the CI builder
  container adds it.
- `bin/_recovery_guide.py` stays a standalone script, because it runs on
  borrowed computers without uv.
- The extraction follows the Python rules: absolute imports, no nested
  functions (`log_to`'s closure becomes a passed-in callable), frozen
  keyword-only dataclasses for drive and VM settings.

## Order of work

1. Done: stage 1 plus the GitHub workflow, and the `bin/vm` library
   extraction with its unit tests.
2. Done: a spike measuring one cold build on a hosted runner (see "Measured
   on a hosted runner").
3. CI identity, the builder container on GHCR and the build job (stage 2),
   with the Actions caches.
4. Turn `bin/vm`'s printed checks into assertions (stages 3–4) and add
   `bin/ci`.
5. First login, pass and the graphical session (stage 5).
6. A/B update and rollback (stage 8).
7. Restic back-up and restore (stage 9).
8. Recovery guide (stage 7).
9. Native build in a VM (stage 6).

## Decisions

- Everything runs on GitHub-hosted runners; no self-hosted hardware.
- One CI identity (throwaway Secure Boot key, GPG key and store) per run;
  real secrets never reach CI, so no job uses repository secrets.
- Jobs run inside the Arch builder container, published to GHCR.
- The image tier is split into jobs joined by the compressed medium and the
  split artifacts, for parallelism; a cold build measured 42 min and ~50G.
- The heavy stages run through `bin/ci`, so CI and local runs are identical.
- Hardware-only steps (YubiKey provisioning, Wi-Fi, real Secure Boot
  firmware) stay on a manual checklist.
- First login uses a SoftHSM2 token from a `ci` mkosi profile in place of
  the YubiKey.
- Only the image with no organizations is tested; full disk encryption and
  subvolume homes go untested.
- No AGENTS.md repo-rules lint.
- The recovery-guide test keeps its own steps, each citing the exact doc
  command it runs; the docs aren't restructured.
- A/B updates and rollback are tested, from the previous `main` run's image.
- Build caches live only in the Actions cache; nightly runs keep them from
  being evicted. A cold build measured 42 min, so a lost cache costs time,
  not the run.
- Stage 1's checks are defined once in `.pre-commit-config.yaml`
  (`language: system` hooks), run by prek as a git pre-commit
  hook and by CI with `prek run --all-files`. Tool settings live in the
  tools' own config files (`.shellcheckrc`, `.ansible-lint`, ruff in
  `pyproject.toml`), which nvim reads too.
- nvim applies the fixable checks on save, globally: conform's `shellcheck`
  and `ansible-lint` fixers, with ansible-lint replacing prettier on
  `yaml.ansible`. nvim-lint shows shellcheck and `systemd-analyze verify`
  diagnostics; `ansiblels` keeps showing ansible-lint and syntax-check ones.
- CI also runs `ruff format --check` and `ruff check`.
- The VM harness moves to a uv package, `src/arch_ansible_vm/`, with
  `bin/vm` and `bin/ci` as thin wrappers; tests live in `tests/unit/` and
  `tests/e2e/`, with one pytest marker per stage.
