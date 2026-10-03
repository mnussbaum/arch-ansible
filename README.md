# arch-ansible

Image-based provisioning for personal Arch Linux workstations. mkosi builds one
signed image, configured by Ansible at build time, that is the installer, the
live/recovery system and the installed system. Machines update by swapping A/B
`/usr` slots with images built from this repo. A QEMU wrapper tests images before
they reach hardware. See `docs/bootstrapping.md` for the full design.

## Stack

**OS & boot:** Arch Linux built with mkosi, UEFI, systemd-boot, Unified Kernel Images
(UKIs) with boot-menu profiles, Secure Boot with our own key (auto-enrolled on first
boot), read-only erofs `/usr` with dm-verity and A/B slots via systemd-sysupdate,
LUKS2 btrfs root and swap sealed to the TPM2, systemd-homed home unlocked by YubiKey.

**Desktop:** Sway (Wayland compositor), Waybar, Mako notifications, greetd with
gtkgreet, Swaylock, Ghostty, Thunar.

**Theming:** Base16 color schemes with day and night variants.

**Networking:** iwd for WiFi, systemd-networkd, systemd-resolved with Cloudflare/Google
DNS.

**Auth:** GPG primary key stored offline on a LUKS-encrypted USB, Ed25519 subkeys
(sign/encrypt/authenticate) programmed onto YubiKeys. GPG agent provides SSH via the
auth subkey. A shared PIV key on every YubiKey unlocks LUKS and homed.

**Backups:** restic to Backblaze B2.

## Repo layout

```
bin/                        Human-run scripts: build, VM, burn, update, key ceremonies
ansible/                    Everything Ansible (bin/ansible runs from here)
  postinst-playbook.yml     Image build playbook (run by mkosi's postinst)
  user-first-login-playbook.yml  Per-user setup on first login
  hosts.yml                 Inventory (the `build` identity)
  roles/                    One role per subsystem (tasks/, files/, templates/)
  group_vars/               Shared variables (user, fonts, theming)
  filter_plugins/           Custom Jinja filters
  vendor/roles/             External roles (requirements.yml)
  assets/                   Wallpapers
mkosi/                      Image build (bin/* run `mkosi --directory=mkosi`)
  mkosi.conf, mkosi.conf.d/ Base config and package lists
  mkosi.extra/              Files copied verbatim into the image (installed
                            commands live in mkosi.extra/usr/bin/)
  mkosi.postinst.chroot     Runs the Ansible postinst inside the image
  mkosi.repart/, mkosi.sysupdate/, mkosi.uki-profiles/, mkosi.initrd.conf/
container/                  Disaster-recovery build container (run by bin/dr-build)
docs/                       Design (bootstrapping.md), procedures (disaster-recovery.md
                            indexes them), the recovery guide, plans, todos
secrets/                    Generated recovery guide (gitignored)
dr-out/                     bin/dr-build output (gitignored)
```

## GPG keys and YubiKeys

One GPG key is the root of trust: its primary key stays offline on an encrypted
USB drive and on paper, and every YubiKey carries its subkeys (password store and
SSH), a shared PIV key that unlocks disks and homes, and the TOTP seeds for 2FA.
Creating and backing up the key, provisioning and renewing YubiKeys, 2FA codes
and printing the recovery guide are in `docs/gpg-and-yubikeys.md`.

## Password store

Passwords are managed with `pass` in a GPG-encrypted git repo, cloned into the home
directory at first login. The store is encrypted with the GPG key, so the YubiKey
(or primary GPG USB) is required to decrypt entries.

`bin/build-image` reads the Secure Boot key and other build secrets from the password
store, so the YubiKey must be present for a build.

## Provisioning

One signed image is the installer, the live/recovery system and the installed
system, picked from the boot menu. `docs/bootstrapping.md` ("One image, three
roles") explains the design.

### Build a new install/recovery USB

`bin/build-image` and `bin/burn-image` on an Arch machine
(`docs/bootstrapping.md`, "Building the image"), or `bin/dr-build` and
`bin/dr-burn` on any Linux or macOS computer (`docs/build-recovery-usb.md`).

### Provision a new physical machine

Add the machine's backup credentials (`docs/backup-credentials.md`), build a USB,
install (`docs/install-machine.md`) and restore the home
(`docs/restore-home.md`). `docs/disaster-recovery.md` covers what to do after
losing a machine, YubiKey or key; `docs/bootstrapping.md` ("System recovery")
covers the **Live System (Recovery)** profile.

### QEMU workflows

`bin/vm` is the only VM command. What you boot is an argument, not a different
command, and `--gui` opens a window instead of running headless:

```
bin/vm run                   # the built medium (installer / live system)
bin/vm run DISK.raw          # an installed disk, attached ALONE
bin/vm install TARGET.raw    # install the medium onto TARGET, then check the layout
```

Build the image first, then run it (emulates an installed machine — boots the
default profile, which self-provisions on first boot):

```
bin/build-image
bin/vm run
```

Add `--ephemeral` to boot a throwaway snapshot, leaving the built image
untouched.

Attach a second disk with `--device=<disk.raw>` and pick **Live System (Recovery)**
at the boot menu to repair it, or **Installer** to install onto it.

```
bin/vm run --device="$HOME/.cache/mkosi/images/image/<disk>.raw"
```

#### Scripted runs

`install`, and `run` with a disk, are headless and exit non-zero if the run
misses its checkpoint, so they compose into a validation pass. Naming a disk
attaches it **alone**, which a target's first boot requires: with the medium
also attached, first-boot `systemd-repart` provisions the wrong disk.

```
bin/vm install ~/.cache/mkosi/test-target.raw   # fresh install
bin/vm run     ~/.cache/mkosi/test-target.raw   # first boot + health checks
bin/vm run DISK --run 'CMD'                     # run CMD in the booted guest
bin/vm run DISK --share DIR                     # hand the guest files at /mnt/vmtest
bin/vm run DISK --entry VERSION                 # pick an sd-boot entry
bin/vm run DISK --gui                           # a window instead of the checks
```

## Maintenance

### Update a machine

`/usr` is read-only, so OS-level changes are made in this repo and rolled out as a
new image. On the machine itself:

```
bin/update-system            # build a new image, install it to the inactive /usr slot
bin/update-system --reboot   # ...and reboot into it
```

Failed boots fall back to the previous slot automatically. `--image=DISK` updates
another machine's disk from the live USB instead.

### Iterate on Ansible

Ansible runs inside the image build (`mkosi/mkosi.postinst.chroot` calls
`bin/ansible` with `postinst-playbook.yml`) and once per user at first login
(`user-first-login-playbook.yml`). To iterate on part of it:

```
bin/build-image --ansible-tags sway,waybar   # rebuild running only these roles
bin/build-image --skip-postinst              # rebuild without Ansible at all
bin/rerun-postinst                           # re-run the postinst on the cached image
```

`bin/update-system` forwards the same options to `bin/build-image`. Tags are the
role names in `ansible/postinst-playbook.yml`; `min-user-session` covers the roles
a usable desktop needs.

### Iteration cycle

When developing new configuration:

1. Make changes directly on a machine (or in `bin/vm run --ephemeral`) to verify
   they work.
2. Encode the changes in the relevant role under `ansible/roles/`.
3. Build the image and boot it with `bin/vm run` to confirm the configuration
   applies.
4. Roll it out with `bin/update-system`.
