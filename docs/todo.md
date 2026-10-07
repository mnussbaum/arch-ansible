## Bootstrapping

- Fix colorscheme changer for the new world. Needs a whole new strategy
- Remove old host directory setup once fully cut over to image based hosts
- Make firefox configs and preferences portable
- Remove ARCH_ANSIBLE_SRCTREE copying used to avoid copying secrets dir with repo into image
- Add testing and CI
- Check for a root-swap TPM bypass in `bin/vm`: retype the real root in the
  GPT, add an attacker LUKS root, boot the default profile, and try to unseal
  the real root's TPM token from the booted system. Signed PCR 11 covers the
  `sysinit`/`ready` phases and nothing checks root identity (PCR 15), so it
  may work. Fixes: sign only initrd phases, or verify PCR 15 before switch-root

## Sync

- Organize the Sync directory
- Move all photos into a photo management tool
- Holistic data sync strategy
