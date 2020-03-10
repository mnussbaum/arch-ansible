TODO:

- hostname isn't persisted correctly
- Script partitioning
- Run qemu headlessly?
- DRY up qemu invocations across scripts
  - Make scripts build missing disk or iso as necessary
  - Move qemu setup into ansible?
- Move all bootstrapping into ansible?
- Remove hardcoding of vgcrypt and vgcrypt-root in boot tasks and grub config
  - Ideally pull partition info from disk too
- Fix failed install of ruby-solargraph due to ruby-ruby-progressbar ruby-progressbar conflicts
