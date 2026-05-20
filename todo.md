## Nice to improve

1. Host groups to reduce host var duplication
1. Repartition windows partition
1. Specify partitions as sizes
1. Make it easier to add a new host, vars, hosts.yml
1. Host specific secret structure in pass

### Live image

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
1. Replace vault with pass
   - Need to figure out yubikey in qemu and bootstrapping story

## Bugs

1. machinectl depends on disutils which was removed in python 3.12
1. During boostrapping, after reboot, caps lock isn't remapped to escape until sway is available
1. yubikey isn't making it into qemu VMs

## Tasks

- Back up primary key
- Test full gpg creation script
- Rebuild install media with final state
- Prepare physical recovery packages
- Label physical media
- Test accessing yubikey from live ISO on physical machine
- Test ISO perms changes
- Remove 2fa backups from pass
