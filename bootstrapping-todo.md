# Bootstrapping — Implementation Status

Sections of `bootstrapping.md` that are aspirational and not yet implemented.

---

## Build chain

- **Podman container** (`Containerfile`) — exists but untested end-to-end;
  `bin/build-image`, `bin/run-image`, and `bin/burn-image` have not been run inside it

## Recovery

- **`bin/recovery-mount`** — implemented; automates LUKS discovery, token/recovery-key
  unlock, root + ESP mount, and arch-chroot. Untested.

## Secure Boot and the USI

- **USI signed with machine db key (Option A)** — not implemented:
  - YubiKey PIV import of the machine db key is a manual step with no script
  - `bin/build-image usi` does not yet invoke `systemd-sbsign` with a PKCS#11 URI
  - Per-machine USI signing requires either a separate build per machine or a
    shared recovery key enrolled in all machines' db alongside the per-machine key
- Entire secure boot setup, not implemented

## Operational scripts

- **`bin/revoke-luks-yubikey`** — exists but verify it correctly handles slot
  discovery and re-enrollment

## End-to-end testing

- Physical hardware installation has not been tested with `mkosi burn`
- Secure Boot key auto-enrollment via `secure-boot-enroll force` has not been
  verified against real firmware
- TPM2 LUKS enrollment and PCR 7 sealing has not been tested

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
- Test the sysupdate scenarios
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
- Issues
  - Get a working update-system from in the image
- Change ansible to build mkosi structure instead of running on a host?
- Remove ARCH_ANSIBLE_SRCTREE copying used to avoid copying secrets dir with repo into image
- I wonder if we can run the user ansible in a seperate user home image build
  process. And then mount it in instead of running it on user first log in
