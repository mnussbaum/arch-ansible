Document how to:

1. Build ISO
1. Build/run QEMU VM ISO and VM
1. Recover the boot partition
1. Setup a new machine
1. What the different tag modes are
1. Build a fresh install media

1. Test managed partition changes I made, both not breaking existing usages of
   `partitions` as well as properly mounting EFI partition
1. Fix the permissions on bin scripts in install media
1. Repartition windows partition
1. Specify partitions as sizes
1. Make it easier to add a new host, vars and bin scripts, hosts.yml
1. Networking package installs fail, even though packages are already installed
   due to `database file for 'core' does not exist (use '-Sy' to download)`
1. Setting timezone and hw clock to UTC fails with `tried to configure name using a file
/etc/sysconfig/clock" but could not write to it`. Replace with:

   ```
   ln -sf /usr/share/zoneinfo/Region/City /etc/localtime
   hwclock --systohc
   ```

1. timedatectl commands to set NTP fail with `System has not been booted with
systemd as the init system`. Also locale commands commands
1. `/boot/grub/grub.cfg` was missing after initial install
1. Network device during bootstrapping was wlan0, need to set it different in
   bootstrapping vs actual operation
1. Ansible files not owned by user
1. secrets dir and secrets/vault-password file not found in arch-ansible repo,
   all secrets missing
1. fakeroot was missing even though it should have been installed by
   base-devel, was when I installed that package manually
1. Document or automate ~/.netrc and GOPRIVATE setup
