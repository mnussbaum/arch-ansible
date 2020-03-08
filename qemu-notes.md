TODO:

- Script partitioning
- Run qemu headlessly?
- Everything into ansible?
- Remove hardcoding of vgcrypt and vgcrypt-root in boot tasks and grub config

- Still not working, can't reboot after successful provisioning
- Upon booting into ISO I can't mount vgcrypt-root due to "unknown filesystem type 'LVM2_member'"
- Tried to get past that with https://www.svennd.be/mount-unknown-filesystem-type-lvm2_member/, got error where mount can't read superblock on vgcrypt-root
