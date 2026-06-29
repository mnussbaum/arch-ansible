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
- **Hostname is set via an install-time credential.** `systemd-sysinstall` only
  propagates locale/keymap/timezone on its own (no `--copy-hostname`), so a mandatory
  drop-in (`systemd-sysinstall.service.d/10-firstboot-hostname.conf`) imports a
  `firstboot.hostname` credential supplied to the installer and forwards it to the
  target with `--load-credential` (install fails if absent). The credential is
  supplied explicitly — `run-image --hostname` via `mkosi --credential`, or a
  `firstboot.hostname.cred` in the medium's ESP `loader/credentials/` written by
  `burn-image` — never derived from the installer's own running hostname. On the
  target's first boot, the enabled `systemd-firstboot.service`
  (`ImportCredential=firstboot.*`) writes the static `/etc/hostname`. This is the
  single naming mechanism for both routes (self-install and installer); the old
  `system.hostname` transient cred has been dropped. `firstboot.hostname` is new in
  systemd 261. Untested end-to-end; verify the name actually lands on a fresh install.
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

1. [ ] **Build an image** — `bin/build-image`. Pass: signed UKI + split
       usr/verity/verity-sig artifacts land in `~/.cache/mkosi/images/image`, version
       bumped (`mkosi.version`).
2. [ ] **Boot the image** — `bin/run-image --hostname=qemu`, normal (default)
       boot. First boot runs repart (device A/B `usr` + root/home/swap layout),
       TPM2-seals the LUKS root/swap, and self-provisions. Pass: reaches a provisioned
       login, the hostname credential landed, `/usr` is the dm-verity image.
3. [ ] **On-device A/B update (sysupdate in the booted image)** — in the booted
       system, `bin/update-system` (no `--image`; add `--reboot` to switch slots).
       Pass: the new version fills the inactive `usr` slot, a new UKI is dropped with
       `TriesLeft=`, and a reboot lands on the new slot with boot-counting /
       auto-rollback intact.
4. [ ] **Fresh install from a live USB → blank host** — boot the **Installer**
       profile (`mkosi.uki-profiles/25-install.conf` → `systemd-sysinstall.service`)
       against a blank disk, or boot **Live System** and run `systemd-sysinstall` by
       hand. Pass: disk partitioned, `/usr` copied, ESP populated via `bootctl
install`/`link`, the `firstboot.hostname` credential forwarded, and the
       target's first boot provisions + TPM2-seals. (See "Install from the live
       medium" above for the hostname-credential and PCR-7 caveats.)
5. [ ] **Offline update from a live USB → existing host** — boot **Live System
       (Recovery)**, then `bin/update-system --image=/dev/vdb` against an
       already-installed target (use the step-4 host as the target). Pass: the new
       version fills the _inactive_ `usr` slot, the new UKI lands on the _target's_
       ESP, the prior slot is retained, and root/home/swap are untouched (homed user
       data survives). Mechanism + design: see `offline-update-handoff.md`.

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
