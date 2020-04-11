TODO:

- Fix grub.j2 partition handling
  - Remove parted lookup in boot.yml
  - Pull partition definitions into host vars
  - Use partition info from host var in grub.j2
  - Remove parted install from pacstrap after this is done
- Move all bootstrapping into ansible
  - Write networking configuration into chroot
  - Unify pi boostrapping and qemu/xps bootstrapping
- Make partitioning idempotent
  - It's the "use 100% space" causing the issue
  - Might be able to use ansible partition facts to work around
- Document (or script) creation of luks-keyfile
- fix font in qemu
- Make install console font bigger
- Review qemu args and optimize
- Installing vim plugins always seems to hang at first and then succeed?
- Install zsh in the console, make default shell
- Enable vim mode in the console
