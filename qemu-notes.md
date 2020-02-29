- cp /usr/share/ovmf/x64/OVMF_VARS.fd my_uefi_vars.bin

```bash
  qemu-system-x86_64 \
    -drive file=/home/mnussbaum/.local/share/qemu-arch-image.qcow2,format=qcow2 \
    -drive if=pflash,format=raw,readonly,file=/usr/share/ovmf/x64/OVMF_CODE.fd \
    -drive if=pflash,format=raw,file=my_uefi_vars.bin \
    -m 2048 -enable-kvm -M q35 -cpu host -smp 4,sockets=1,cores=4,threads=1 \
    -bios /usr/share/qemu/bios.bin \
    -boot menu=on \
    -cdrom /home/mnussbaum/.local/share/qemu-arch-usb.iso
```

TODO:

- Add scripting to build boot image and boot disk
- Script partitioning
- Run qemu headlessly?
- Everything into ansible?

- Still not working, can't reboot after successful provisioning
- Upon booting into ISO I can't mount vgcrypt-root due to "unknown filesystem type 'LVM2_member'"
- Tried to get past that with https://www.svennd.be/mount-unknown-filesystem-type-lvm2_member/, got error where mount can't read superblock on vgcrypt-root
