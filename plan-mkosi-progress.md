# mkosi Migration: Progress & Remaining Work

## Done

### mkosi config

- **Standalone `--directory` builds**: all scripts use `mkosi --directory mkosi.images/<name>` instead of the subimage `--dependency` architecture; root `mkosi.conf` is now a `Format=none` stub
- **`mkosi.common/`**: shared config directory; `Distribution`, `WithNetwork`, `BuildSources` live here and are valid because each image is the main image when built standalone
- **`BuildSources=../` (no explicit target)**: fixed double-nesting bug — `BuildSources=../:/work/src` caused the source to mount at `/work/src/work/src` instead of `/work/src` (= `SRCDIR`)
- **Scope errors resolved**: removed `[Runtime]` sections from subimage configs (scope=main, only valid in main image context); runtime args are now CLI flags in `bin/run-qemu`
- **Setting names fixed**: `CPUs=`, `RAM=`, `VSock=`, `VSockCID=`

### Renamed live → usi

- `mkosi.images/live/` → `mkosi.images/usi/`
- `host_vars/live.yml` → `host_vars/usi.yml`
- `hosts.yml`: `live:` → `usi:`
- `bin/build-live-image` → `bin/build-usi`
- `live_image_file` → `usi_image_file`, `live.raw` → `usi.raw`

### Updated bin scripts

- **`bin/build-persistent-image`**: `--directory mkosi.images/<name>`; `mkosi burn <device>` for physical hosts (replaces dd)
- **`bin/build-usi`**: `--directory mkosi.images/usi`; `mkosi burn <device>` for device targets; no-arg builds to `$usi_image_file`
- **`bin/run-qemu`**: uses `mkosi vm` verb with `--cpus`, `--ram`, `--vsock`, `--vsock-cid`, `--runtime-trees`; `--live` mode renamed to `--usi`
- **`bin/_qemu_common.sh`**: removed `make_image_args`/`common_qemu_args`; renamed `live_image_file` → `usi_image_file`

### mkosi.build fixes

- `USER=root HOME=/root` before ansible: inside mkosi's user-namespace sandbox `$USER` inherits the host username, so ansible called sudo to escalate (which lacks setuid in user namespaces); setting `USER=root` lets ansible detect uid 0 and skip privilege escalation

---

## Remaining work

### Build correctness

- [x] Fix timezone role: `Timezone=US/Pacific` in `mkosi.common/mkosi.conf`; `time` role omitted from `build-playbook.yml` (timedatectl needs D-Bus)
- [x] Audit service start/daemon_reload tasks: `build-playbook.yml` sets `svc_start_state: "{{ omit }}"` and `svc_daemon_reload: false`; `playbook.yml` sets `svc_start_state: started` / `svc_daemon_reload: true`; affected roles (power, qemu-guest, trim, gpg, brightness, reflector, enable_network) updated
- [ ] Run the full build successfully (qemu image first, then usi)

### Verification

- [ ] Boot the qemu image: `mkosi --directory mkosi.images/qemu --output-directory $XDG_DATA_HOME/arch-images vm`
- [ ] Verify shared dir (`/run/host/shared`) and pcscd vsock relay work in USI and persistent flavors of QEMU
- [ ] Verify sway starts successfully in USI and persistent flavors of QEMU
- [ ] Test `build-persistent-image bodie /dev/sdX` on a physical device
- [ ] Test `build-usi /dev/sdX` on a physical device

### Deferred (next step)

- Remove ansible-vault; fetch `luks_passphrase` from `pass` using gpg/yubikey instead of `--vault-password-file secrets/vault-password`

### Larger plan

See `plan-systemd-boot.md` for the full systemd-boot + LUKS2 + Secure Boot + TPM2 design. The mkosi migration is the prerequisite — once the build pipeline works end-to-end, that plan picks up from here.

Use recommended systemd approach for all aspects of image building and runtime behavior

Goal is to comply with https://uapi-group.org/specifications/specs/discoverable_partitions_specification/ and https://0pointer.net/blog/fitting-everything-together.html
