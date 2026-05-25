- Document that we implement https://uapi-group.org/specifications/specs/discoverable_partitions_specification/
- Ask it to diff against the plan in https://0pointer.net/blog/fitting-everything-together.html
- Figure out user data story
- Figure out how we test changes to automation. Just QEMU?
- Figure out how we apply changes to automation. Reinstall?
- I think we move package installs back into ansible
- Use mkosi.prepare to install mnussbaum user
- Run xdg-user-dir to install user dirs
- Is `Install pacman database files` still needed?
- Clean up bootstrapping tags and playbooks
- Clean up network_install_root
- Clean up the variables for daemon refresh and service starting
- Stuff copied from the host that needs to be in containerfile
  - yay-bin
  - password-store repo
  - arch-ansible repo
  - nvim packages
- How are we going to mount in nvim data dir in container? Probably need to handle its absence
- In image build need to mount from new system locations once I have a provisioned machine
- Ask it if there's other things that need network access going on that we can avoid
- Get offline
  - Remove pacman keyring stuff if truly offline
  - Base16 configs reach internet still
  - delta theme file download

- `HOSTNAME=usi NO_ASK_BECOME_PASS=1 ANSIBLE_PLAYBOOK=postinst-playbook.yml ./bin/ansible --tags=greeter --tags=packaging`
- Make sure this is followed up on:

```
  The UnifiedKernelImages=yes (mkosi/ukify) approach: mkosi drives the UKI assembly via ukify directly, giving better integration with Secure Boot signing and TPM2 PCR measurements. But then linux.preset needs to switch from default_uki= to default_image= (plain initrd path), and post-boot kernel updates need a separate hook (kernel-install
  plugin or pacman hook calling ukify) instead of mkinitcpio handling it.
```

- Revaluate bootstrap and rebuild-boot-partition tags
- Investigate restic/btfs best practice setup
- Document cache mounting pattern perf optimization
- Need to make user login driven by yubikey due to unencrypted root:

```
 /etc/shadow breaks home encryption
 The biggest issue. If home directories are encrypted with keys derived from user passwords (e.g. systemd-homed LUKS homes), exposing /etc/shadow gives an attacker the
 hash to crack offline. A cracked password directly unlocks the home encryption — you've degraded home encryption to "as strong as your password against offline
 cracking.
```
