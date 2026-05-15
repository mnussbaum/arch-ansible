## Document how to

1. Setup a new machine
1. What the different tag modes are

## Nice to improve

1. Host groups to reduce host var duplication
1. Repartition windows partition
1. Specify partitions as sizes
1. Make it easier to add a new host, vars, hosts.yml
1. Offline install from ISO
1. Offline ISO build
1. Move to systemd-boot
1. Install more during early bootstrapping and live USB:
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

## Bugs

1. Missing eeek ssh keys
1. In live image permissions are still screwed up, causing a git diff
   - Not everything in bin is supposed to be executable, but we're making it so
   - Some files/ are supposed to be executable, but they're not
   - Some library and vendor file executable bits are swapped too
1. machinectl depends on disutils which was removed in python 3.12
1. TTY and live USB caps lock aren't remapped to escape
1. Caps lock isn't remapped to escape after bootstrapping reboot before sway is available
1. Firefox setup fails until sway is available
1. greeter background is missing
