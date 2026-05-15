## Nice to improve

1. Host groups to reduce host var duplication
1. Repartition windows partition
1. Specify partitions as sizes
1. Make it easier to add a new host, vars, hosts.yml

### Live image

1. Offline install from ISO
1. Offline ISO build
1. Move to systemd-boot
1. Install more (or everything) during early bootstrapping and live USB:
   - Powerline font
   - Neovim + packages + plugins
   - Tmux configs
   - Base16 colors
   - Starship prompt
   - Bat
   - Eza
   - Full zsh configs
   - Git configs
   - fzf
   - ripgrep
   - pass
1. Put password store on ISO. Use it instead of vault. Verify it works with yubikey

## Bugs

1. In live image permissions are still screwed up, causing a git diff
   - Not everything in bin is supposed to be executable, but we're making it so
   - Some files/ are supposed to be executable, but they're not
   - Some library and vendor file executable bits are swapped too
1. machinectl depends on disutils which was removed in python 3.12
1. During boostrapping, after reboot, caps lock isn't remapped to escape until sway is available
1. During boostrapping Firefox setup fails until sway is available
1. yubikey isn't making it into qemu VMs

## Tasks

- Back up primary key
- Test full gpg creation script
- Rebuild install media with final state
- Prepare physical recovery packages
- Label physical media
