# Bootstrapping — Implementation Status

Sections of `bootstrapping.md` that are aspirational and not yet implemented.

---

## Build chain

- **Podman container** (`Containerfile`) — exists but untested end-to-end;
  `bin/build-image`, `bin/run-image`, and `bin/burn-image` have not been run inside it
- **ESP mount during nspawn** — needs verification that mkosi mounts the ESP
  inside the build script nspawn with `Bootable=yes`; the `systemd-boot` role's
  `mountpoint /efi` guard exists as a fallback if it does not
- **arch-ansible repo in USI** — `BuildSources=../` copies the repo into the
  nspawn build environment; verify it is accessible at `~/src/arch-ansible` in
  the booted USI (may need a `mkosi.extra` or post-build step to place it at
  the right path for the user)

## First boot sequence

- **`firstboot.service`** — implemented; `ConditionFirstBoot=yes` gates the oneshot
  service that runs `bin/ansible` from the baked-in repo. Untested.
- **Runtime playbook error-on-missing** — implemented; `systemd-boot` role uses
  `ansible_env.SRCDIR` to distinguish build (generate artifacts) from runtime
  (fail with clear message if artifacts missing). Untested.
- **`luks-enroll.service`** — implemented; `roles/systemd-boot/files/luks-enroll`,
  `luks-enroll.service`, and install tasks added to the systemd-boot role. Untested.

## Recovery

- **`bin/recovery-mount`** — implemented; automates LUKS discovery, token/recovery-key
  unlock, root + ESP mount, and arch-chroot. Untested.

## Secure Boot and the USI

- **USI signed with machine db key (Option A)** — not implemented:
  - YubiKey PIV import of the machine db key is a manual step with no script
  - `bin/build-image usi` does not yet invoke `systemd-sbsign` with a PKCS#11 URI
  - Per-machine USI signing requires either a separate build per machine or a
    shared recovery key enrolled in all machines' db alongside the per-machine key

## Operational scripts

- **`bin/revoke-luks-yubikey`** — exists but verify it correctly handles slot
  discovery and re-enrollment

## End-to-end testing

- Full build pipeline has not been run to completion
- QEMU image boot has not been verified with the new systemd-boot + UKI setup
- Physical hardware installation has not been tested with `mkosi burn`
- Secure Boot key auto-enrollment via `secure-boot-enroll force` has not been
  verified against real firmware
- TPM2 LUKS enrollment and PCR 7 sealing has not been tested
