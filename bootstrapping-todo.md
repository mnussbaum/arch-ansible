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

- Document yubikey enrollment for homectl
- Document cache mounting pattern perf optimization
- Document that we implement https://uapi-group.org/specifications/specs/discoverable_partitions_specification/
- Implement verity, encryption and layout from https://0pointer.net/blog/fitting-everything-together.html
- Move most package installs back into ansible, only leave enough to run ansible
- Can remove network_install_root var?
- Stuff copied from the host that needs to be in containerfile, handle missing files gracefully
  - yay-bin
  - password-store repo
  - arch-ansible repo
  - nvim packages
  - mirrorlist - ideally reflectored
  - Cargo registry
  - Sccache
- Create ~/.cargo/registry ~/.cache/sccache in the user home dir in skel
- In image build configs need to mount from new system locations once I have a provisioned machine
- Get offline
  - Base16 configs reach internet still
  - delta theme file download
  - Others?
  - `WithNetwork=false`?

- Make sure this is followed up on:

```
  The UnifiedKernelImages=yes (mkosi/ukify) approach: mkosi drives the UKI assembly via ukify directly, giving better integration with Secure Boot signing and TPM2 PCR measurements. But then linux.preset needs to switch from default_uki= to default_image= (plain initrd path), and post-boot kernel updates need a separate hook (kernel-install
  plugin or pacman hook calling ukify) instead of mkinitcpio handling it.
```

- Verify restic backup/restore scripts
- Consider automating restic restore in a new workstation
- Can we move ansible into the build step? Might allow better caching
- Test the partition swap in qemu
- Fix colorscheme changer for the new world. Needs a whole new strategy
- Test different USI usages
- Organize project top level better. Playbooks in one dir, mkosi stuff in another
- Do I need runtime systemd unit to grow swap partition?
- Make it able to handle new hosts without new configs
- Add eeek tasks back in once fully done
