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
docs/                       Design (bootstrapping.md), disaster recovery, plans, todos
secrets/                    Generated recovery guide (gitignored)
dr-out/                     bin/dr-build output (gitignored)
```

## Auth

### Build a new primary GPG USB

The primary GPG USB is a LUKS-encrypted drive containing the primary (cert-only) GPG key
and revocation certificate. It is only plugged in during key ceremonies and must be kept
offline otherwise.

```
./bin/create-gpg-key <device> <existing-key-device>   # replacing a primary key
./bin/create-gpg-key <device> <totp-file>             # starting fresh
```

`<device>` is wiped. The second argument supplies the TOTP seeds: a previous primary
GPG USB (whose key also re-encrypts the password store) or a file of `otpauth://`
URIs.

This will:

1. Format and LUKS-encrypt `<device>`
2. Generate a new Ed25519 primary key (cert-only, no expiry)
3. Add three subkeys (sign, encrypt, auth), each expiring in 1 year
4. Generate a revocation certificate and store it on the USB
5. Back up the primary key to the USB
6. Export the public key to `ansible/roles/gpg/files/gpg-pubkey.asc`
7. Re-encrypt the password store to the new key and copy the TOTP seeds to the USB
8. Program all connected YubiKeys with the subkeys, the TOTP seeds and the shared
   homed PIV key (minted into pass on first run)

After running, commit the public key:

```
git add ansible/roles/gpg/files/gpg-pubkey.asc
git commit -m 'Add GPG public key'
```

Also add the SSH public key to GitHub/GitLab:

```
gpg --export-ssh-key <fingerprint>
```

### Provision new YubiKeys

YubiKeys are programmed as part of `create-gpg-key` or `enroll-yubikeys`. The scripts
loop interactively, prompting to insert each YubiKey in turn. Each YubiKey receives the
same three subkeys (sign, encrypt, auth), its TOTP seeds, and the shared PIV key from
`pass` that unlocks LUKS and homed, so a replacement YubiKey works on every machine
with no per-machine re-enrollment.

To program additional YubiKeys against an existing primary GPG USB:

```
./bin/enroll-yubikeys <device>
```

When prompted, insert YubiKeys one at a time and follow the prompts.

### Use YubiKeys

The YubiKey's GPG auth subkey is used for SSH via the GPG agent. Once Ansible has
provisioned the machine, the agent is configured automatically.

To verify the YubiKey is working:

```
gpg --card-status          # shows card info and subkey fingerprints
ssh-add -L                 # should show the auth subkey's SSH public key
```

If the agent is not picking up the card, restart it:

```
gpgconf --kill gpg-agent
gpg --card-status
```

### Renew YubiKeys

Subkeys expire annually. Run the renewal ceremony with the primary GPG USB plugged in:

```
./bin/enroll-yubikeys <device>   # e.g. /dev/sda1
```

This extends all subkey expiry by one year, exports the updated public key to
`ansible/roles/gpg/files/gpg-pubkey.asc`, and reprograms all YubiKeys. After running:

```
git add ansible/roles/gpg/files/gpg-pubkey.asc && git commit -m 'Renew GPG subkeys'
```

### 2FA codes

TOTP codes are stored in the YubiKey OATH applet, separate from the password
store. This preserves genuine two-factor separation: compromising the password
store doesn't expose TOTP seeds. The OATH applet is password-protected; the
password is set during YubiKey provisioning.

Seeds are backed up as `otpauth://` URIs in `oath-accounts.txt` on the primary
GPG USB. They are automatically loaded onto each YubiKey during
`create-gpg-key` and `enroll-yubikeys`. The recovery guide PDF includes QR codes
and `otpauth://` URIs for a curated set of critical accounts (defined in
`CRITICAL_TOTPS` in `bin/generate-gpg-recovery-guide`), so those accounts can
be restored from paper alone without the USB.

**Import from Aegis**

Export from Aegis: Menu → Export → Plain text backup (unencrypted JSON), then:

```
./bin/import-aegis-export <device> <aegis-export.json>
```

Converts the Aegis JSON to `otpauth://` URIs, backs them up to the USB, and
loads them onto the YubiKey. Delete the export file from your phone after
running.

**Add a single account**

```
./bin/add-oath-account <device>
./bin/add-oath-account <device> --qr <screenshot.png>   # decode from a QR image
```

Backs up the seed to USB and adds it to the currently connected YubiKey.

**Generate codes**

```
ykman oath accounts code           # list all accounts with current codes
ykman oath accounts code <name>    # code for a specific account
```

### Back up the GPG USB

Keep a second encrypted copy of the primary GPG USB in a separate physical location:

```
./bin/backup-gpg-key <source-device> <dest-device>
```

The destination device is formatted and LUKS-encrypted, then the key files are copied.

### Generate a recovery guide

The recovery guide is a printable PDF containing everything needed to reconstruct the
GPG key from scratch: the public key (as a QR code and ASCII armor), the private key
encoded via paperkey, and step-by-step instructions for
restoring SSH access, cloning the password store and Ansible repo, programming new
YubiKeys, and bootstrapping a new machine.

```
./bin/generate-gpg-recovery-guide <primary-key-usb-device> [output.pdf]
```

Output defaults to `secrets/gpg-recovery-guide.pdf`. Store a printed copy in a
physically separate location from the USB drives and YubiKeys.

Regenerate the guide whenever the primary GPG key is replaced or `CRITICAL_TOTPS`
changes.

### Restore from the recovery guide

If every YubiKey and both primary GPG USBs are lost, follow
`docs/gpg-paper-recovery.md`, which the guide also prints. From the Live System
of a provisioned recovery USB, it rebuilds the key from paper, then runs

```
./bin/restore-primary-gpg-from-paper <device> [<totp-file>]
```

which renews the subkeys' expiry, writes a new primary GPG USB (with the TOTP seeds
typed from the guide) and programs new YubiKeys. Then build a medium with
`bin/dr-build` (`docs/disaster-recovery.md`).

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

```
bin/build-image
bin/burn-image /dev/sda
```

With no working Arch machine, `bin/dr-build` runs the same build in a container on
any Linux or macOS machine, and `bin/dr-burn` writes it (`docs/disaster-recovery.md`).

### Provision a new physical machine

Boot the target machine from the USB, pick the **Installer** profile, and follow
the prompts. `docs/bootstrapping.md` ("Build chain from scratch") walks through
the install, first boot, first login and restoring the home from backup; "System
recovery" covers the **Live System (Recovery)** profile.

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
