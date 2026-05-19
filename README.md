# arch-ansible

Ansible-based provisioning for personal Arch Linux workstations. Manages the full
machine lifecycle: live USB creation, bootstrapping (partitioning, encryption, OS
install), and ongoing configuration. Also supports a QEMU VM for testing changes before
applying them to physical hardware.

## Stack

**OS & boot:** Arch Linux, UEFI, GRUB 2 with custom theme, LUKS-encrypted root with LVM
inside, separate unencrypted EFI and `/boot` partitions, ext4 filesystems.

**Desktop:** Sway (Wayland compositor), Waybar, Mako notifications, Greetd greeter,
Swaylock, WezTerm, Thunar.

**Theming:** Base16 color schemes with day and night variants, regenerated across all
apps when switching.

**Networking:** iwd for WiFi, systemd-networkd, systemd-resolved with Cloudflare/Quad9
DNS.

**Auth:** GPG primary key stored offline on a LUKS-encrypted USB, Ed25519 subkeys
(sign/encrypt/authenticate) programmed onto YubiKeys. GPG agent provides SSH via the
auth subkey.

## Repo layout

```
bin/            Bootstrap and key ceremony scripts
tasks/          Ansible task files (one per subsystem)
tasks/bootstrapping/  Disk partition, LUKS, and filesystem tasks
host_vars/      Per-machine configuration (partitions, monitors, WiFi)
group_vars/     Shared variables (user, fonts, theming, packages)
files/          Static config files deployed by Ansible
templates/      Jinja2 templates for generated configs
secrets/        Ansible Vault password (secrets themselves are encrypted in group_vars/)
vendor/roles/   External Ansible roles
assets/         Wallpapers, fonts, GRUB theme assets
playbook.yml    Main configuration playbook
bootstrap.yml   Bootstrap orchestrator
```

## Auth

### Build a new primary GPG USB

The primary GPG USB is a LUKS-encrypted drive containing the primary (cert-only) GPG key
and revocation certificate. It is only plugged in during key ceremonies and must be kept
offline otherwise.

```
./bin/create-gpg-key <device>   # e.g. /dev/sda1
```

This will:

1. Format and LUKS-encrypt `<device>`
2. Generate a new Ed25519 primary key (cert-only, no expiry)
3. Add three subkeys (sign, encrypt, auth), each expiring in 1 year
4. Generate a revocation certificate and store it on the USB
5. Back up the primary key to the USB
6. Export the public key to `files/gpg-pubkey.asc`
7. Program all connected YubiKeys with the subkeys
8. Enroll the auth subkey keygrip in `group_vars/all/gpg_auth_keygrips.yml` (the keygrip
   is a stable identifier used to tell the GPG agent which key to expose over SSH)

After running, commit the public key and keygrips:

```
git add files/gpg-pubkey.asc group_vars/all/gpg_auth_keygrips.yml
git commit -m 'Add GPG public key'
```

Also add the SSH public key to GitHub/GitLab:

```
gpg --export-ssh-key <fingerprint>
```

### Provision new YubiKeys

YubiKeys are programmed as part of `create-gpg-key` or `renew-gpg-subkeys`. The scripts
loop interactively, prompting to insert each YubiKey in turn. Each YubiKey receives the
same three subkeys (sign, encrypt, auth).

To program additional YubiKeys against an existing primary GPG USB:

```
./bin/renew-gpg-subkeys <device>
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
./bin/renew-gpg-subkeys <device>   # e.g. /dev/sda1
```

This extends all subkey expiry by one year, exports the updated public key to
`files/gpg-pubkey.asc`, and reprograms all YubiKeys. After running:

```
git add files/gpg-pubkey.asc && git commit -m 'Renew GPG subkeys'
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
encoded via paperkey, the Ansible vault password, and step-by-step instructions for
restoring SSH access, cloning the password store and Ansible repo, programming new
YubiKeys, and bootstrapping a new machine.

```
./bin/generate-gpg-recovery-guide <primary-key-usb-device> [output.pdf]
```

Output defaults to `secrets/gpg-recovery-guide.pdf`. Store a printed copy in a
physically separate location from the USB drives and YubiKeys.

Regenerate the guide whenever the primary GPG key is replaced or the vault password
changes.

## Password store

Passwords are managed with `pass` and stored in a GPG-encrypted git repo cloned by
Ansible during provisioning. The store is encrypted with the GPG key, so the YubiKey
(or primary GPG USB) is required to decrypt entries.

Some Ansible tasks read credentials directly from the password store at run time. Those
tasks require the GPG agent to be running and the YubiKey to be present before
`./bin/ansible` is invoked.

## Provisioning

### Build a new install USB

The install USB is a bootable Arch Linux ISO with Ansible pre-loaded. It is used to
bootstrap new machines and repair broken ones.

Plug in a USB drive (will be written to `/dev/sda`) and run:

```
./bin/build-live-usb
```

### Provision a new physical machine

1. Build the install USB (see above) and boot the target machine from it.

2. From the live environment, set `$HOSTNAME` to the machine's hostname (must match an
   entry in `hosts.yml`) and run:

   ```
   HOSTNAME=<hostname> ./bin/bootstrap-physical
   ```

   This partitions the disk (GPT: EFI, `/boot`, LUKS-encrypted root with LVM), creates
   filesystems, runs `pacstrap`, sets the hostname, then runs the main playbook in a
   chroot.

3. Reboot and log back in. Run `./bin/ansible` to complete provisioning
   running desktop environment.

### Provision a new QEMU instance

1. Build the QEMU image and start the installer:

   ```
   ./bin/build-qemu-image
   ```

   This creates a 32 GB qcow2 disk, builds an install ISO, and boots into it.

2. From inside the QEMU guest, run:

   ```
   ./bin/bootstrap-qemu
   ```

3. After bootstrap completes, reboot the VM and start it normally:

   ```
   ./bin/run-qemu
   ```

4. Within the VM run `./bin/ansible` to complete provisioning

## Maintenance

### Run a normal Ansible run

```
./bin/ansible
```

Runs `playbook.yml` against the current `$HOSTNAME`, auto-detects day or night for the
appearance variable, and prompts for the sudo password.

To skip the sudo password prompt:

```
NO_ASK_BECOME_PASS=1 ./bin/ansible
```

To override the appearance:

```
./bin/ansible -e appearance=daytime
./bin/ansible -e appearance=nighttime
```

### Ansible tags

Tags limit which tasks run, useful for faster iteration on a specific subsystem.

| Tag                      | Tasks run                                                                                        |
| ------------------------ | ------------------------------------------------------------------------------------------------ |
| `bootstrap`              | Initial setup only: users, packages, networking, partitioning helpers                            |
| `rebuild-boot-partition` | Regenerate GRUB config and mkinitcpio initramfs; use to repair a broken boot partition or kernel |
| `base16`                 | Regenerate all color-scheme files across every app                                               |
| `nvim`                   | Neovim configuration and plugins                                                                 |
| `networking`             | Network configuration (iwd, systemd-networkd, resolved)                                          |

Example:

```
./bin/ansible --tags base16
./bin/ansible --tags nvim,base16
```

### Iteration cycle

When developing new configuration:

1. Make changes directly on the machine to verify they work.
2. Encode the changes in the relevant task file under `tasks/`.
3. Revert the direct changes (or use a fresh QEMU instance).
4. Run Ansible and confirm the configuration applies correctly.
5. Run Ansible a second time and confirm it is idempotent (no changes reported).
