TODO:

- hostname isn't persisted correctly, not being set in /etc/hostname
- Move all bootstrapping into ansible?
- Remove hardcoding of vgcrypt and vgcrypt-root in boot tasks and grub config
  - Ideally pull partition info from disk too
- Make install console font bigger
- Review qemu args and optimize
- Installing vim plugins always seems to hang at first and then succeed?
