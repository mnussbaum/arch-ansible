Sets up an Arch Linux based workstation

## GPG key setup

SSH authentication uses a GPG auth subkey stored on a YubiKey. The primary key
lives only on an offline LUKS-encrypted USB drive and is never imported into the
main keyring.

### Create a new key (first time)

```bash
bin/create-gpg-key /dev/sdX
```

Formats `/dev/sdX` with LUKS encryption, creates a primary [C] key plus [S],
[E], [A] subkeys (1-year expiry), backs up the primary key to the USB, exports
`files/gpg-pubkey.asc`, and programs any number of YubiKeys. Each YubiKey will
have its PINs changed from the defaults during programming.

After running:

1. Add the SSH public key to GitHub/GitLab: `gpg --export-ssh-key <fingerprint>`
2. Commit: `git add files/gpg-pubkey.asc group_vars/all/gpg_auth_keygrips.yml && git commit`

### Back up the key to a second USB

```bash
bin/backup-gpg-key /dev/sdX /dev/sdY
```

Copies `primary-key.asc` and `revocation-cert.asc` from the source USB to a
newly LUKS-formatted destination USB. Store the two drives in separate physical
locations.

### Program an additional or replacement YubiKey

Reset the card first if it has an unknown PIN:

```bash
ykman openpgp reset
```

Then reprogram from the USB backup:

```bash
bin/renew-gpg-subkeys /dev/sdX
```

This also extends subkey expiry by 1 year, which is harmless outside the annual
renewal window.

### Annual renewal

```bash
bin/renew-gpg-subkeys /dev/sdX
```

Opens the existing encrypted USB, extends all subkey expiry by 1 year, updates
`files/gpg-pubkey.asc`, and reprograms any number of YubiKeys. Commit the
updated public key afterward:

```bash
git add files/gpg-pubkey.asc && git commit -m 'Renew GPG subkeys'
```

---

## Bootstrapping a new machine

1. Create a `./secrets/vault-password` file containing the password to unlock
   Ansible Vault secrets
2. Build ISO: `./bin/build-<qemu-image|live-usb>`
3. Boot into ISO
   - XPS: enter BIOS menu to select USB boot
   - QEMU: happens automatically after image is built
4. `cd arch-ansible`
5. `chmod +x bin/*`
6. `./bin/bootstrap-<qemu|xps>`
7. Reboot into the newly provisioned disk
   - XPS: `shutdown -r now`
   - QEMU: `shutdown now` then `./bin/run-qemu`
8. `cd ~/src/arch-ansible`
9. Plug in a YubiKey — SSH auth is now available via gpg-agent
10. Run Ansible to provision to the point of secret setup: `./bin/ansible`
11. Restart to bring up systemd services and GUI: `shutdown -r now`
12. `cd ~/src/arch-ansible`
13. Finish provisioning: `./bin/ansible`

## Adding secrets

```bash
ansible-vault edit group_vars/all/secrets.yml
```
