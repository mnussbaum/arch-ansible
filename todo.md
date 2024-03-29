## Document how to

1. Setup a new machine
1. What the different tag modes are

## Verify

1. Regenerate boot script reinstalls grub
1. TTY and live USB caps lock remapped to escape
1. Ansible repo file perms correct after fresh bootstrapping

## Nice to improve

1. Host groups to reduce host var duplication
1. Do an actual gpg import on private key during bootstrapping - https://blog.veloc1ty.de/2018/08/06/pgp-trust-key-non-interactive-with-ansible/
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

1. Fix networking in qemu post restart- http://ayekat.ch/blog/qemu-networkd
   maybe
1. Corrupted `/mnt/var/cache/pacman/pkg/*.tar.zst`
1. Treesitter errors on first nvim start
1. GPG keygrip is not consistent across devices, and maybe for that reason,
   maybe others, GPG/SSH setup is busted. Try replacing SSH agent with GPG
   agent entirely
1. Had to reinstall gcr to make pinentry work, otherwise missing object file
1. Need to explicitly gpg trust own public key
1. Missing eeek ssh keys
1. Needed to edit sudoers to allow yay installs without password or else
   ansible prompts with each package install
   https://github.com/kewlfft/ansible-aur#create-the-aur_builder-user
1. In live image permissions are still screwed up, causing a git diff
   - Not everything in bin is supposed to be executable, but we're making it so
   - Some files/ are supposed to be executable, but they're not
   - Some library and vendor file executable bits are swapped too
