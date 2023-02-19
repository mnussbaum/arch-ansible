## Document how to

1. Build ISO
1. Build/run QEMU VM ISO and VM
1. Recover the boot partition
1. Setup a new machine
1. What the different tag modes are
1. Build a fresh install media
1. Do ~/.netrc and GOPRIVATE setup, or automate it

## Verify

1. Managed partition changes properly boot partitions
1. Bootstrap secrets are installed properly
1. Wipe partitions and actually wipe data and try it all out

## Nice to improve

1. Repartition windows partition
1. Specify partitions as sizes
1. Make it easier to add a new host, vars, hosts.yml

## Bugs

1. Ansible files not owned by user post-install
1. Installing packages in pre-chroot fails due to missing pacman keys
