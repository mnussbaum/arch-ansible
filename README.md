Sets up an Arch Linux based workstation

## Bootstrapping

1. Create a `./secrets/vault-password` file containing the password to unlock
   Ansible Vault secrets
2. Build ISO - `./bin/build-<qemu-image|live-usb>`
3. Boot into ISO

- For XPS go into BIOS menu to boot from USB
- For QEMU this will happen automatically after the image is built

1. `cd arch-ansible`
1. `chmod +x bin/*`
1. `./bin/bootstrap-<qemu|xps>`
1. Reboot into the newly provisioned disk

- If XPS - `shutdown -r now`
- If QEMU - `shutdown now` - `./bin/run-qemu`

1. `cd ~/src/arch-ansible`
1. `gpg --import ~/gpg-keys/*`
1. `rm -rf ~/gpg-keys`
1. Run ansible to provision to the point of secret setups - `./bin/ansible`
1. Restart to bring up systemd services and GUI `shutdown -r now`
1. Add GPG key to the agent - `ssh-add`
1. `cd ~/src/arch-ansible`
1. Finish provisioning - `./bin/ansible`

## Adding secrets

```bash
ansible-vault edit group_vars/all/secrets.yml
```
