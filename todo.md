## Document how to

1. Setup a new machine
1. What the different tag modes are

## Verify

1. Managed partition changes properly boot partitions
1. Bootstrap secrets are installed and cleaned properly
1. Arch-ansible (and subdirs) file and dir perms are right
1. Wipe partitions and actually wipe data and try it all out

## Nice to improve

1. Do an actual gpg import on private key during bootstrapping - https://blog.veloc1ty.de/2018/08/06/pgp-trust-key-non-interactive-with-ansible/
1. Repartition windows partition
1. Specify partitions as sizes
1. Make it easier to add a new host, vars, hosts.yml
1. Offline install from ISO
1. Offline ISO build
1. Fix yay installs prompting for pw when they shouldn't
   in qemu
1. Install more during bootstrapping
1. Install more on the live USB
1. Remap caps lock to escape in the console and live USB

## Bugs

1. Fix networking in qemu post restart- http://ayekat.ch/blog/qemu-networkd
   maybe
1. Regenerate boot script isn't reinstalling grub
1. Corrupted `/mnt/var/cache/pacman/pkg/*.tar.zst`
1. All the files in src/arch-ansible on the new disk had the wrong permissions
1. Treesitter errors on first nvim start
1. Slow grub/luks decryption
1. GPG keygrip is not consistent across devices, and maybe for that reason,
   maybe others, GPG/SSH setup is busted. Try replacing SSH agent with GPG
   agent entirely
1. Had to reinstall gcr to make pinentry work, otherwise missing object file
1. Need to explicitly gpg trust own public key
1. Missing eeek ssh keys
1. Needed to edit sudoers to allow yay installs without password or else
   ansible prompts with each package install
   https://github.com/kewlfft/ansible-aur#create-the-aur_builder-user
