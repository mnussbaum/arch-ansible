## Nice to improve

1. Host groups to reduce host var duplication
1. Repartition windows partition
1. Specify partitions as sizes
1. Make it easier to add a new host, vars, hosts.yml

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
1. Machine name is hardcoded in restic backup script
1. In live image git diff from wrong perms. bin/\_gpg_common.sh old 644, new 755, files/toggle-bluetooth, other executable files/, library/yay, vendor/roles/\* old 755, new 644.

## Tasks

- Back up primary key
- Test full gpg creation script
- Rebuild install media with final state
- Prepare physical recovery packages
- Label physical media
