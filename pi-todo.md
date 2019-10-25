1. Move existing scripting into ansible

- Bootstrapping XPS from live env only

  - partitioning
  - Make partitions come from host specific data
  - network setup
    - Make wireless device host specific
    - Make SSID come from data
  - Configure mirror list
  - pacman refresh keys
  - pacstrap the chroot
  - genfstab the chroot

- Shared across all runs of boot.yml

  - Copy network setup from host if not present
  - Set hostname
  - Set locale
  - Set system clock timezone
  - Set hwclock timezone to utc
  - Sync hwclock to match sysclock
    - Ideally only do this if they're some threshold out of sync
  - pacman refresh - on initial bootstrapping only
  - pacman install boostrapping packages

- Bootrapping module generizications
  - Make kernel modules in mkinitcpio host specific
  - Make kernel modules modprobe.d host specific
  - Make swap setup host specific
  - Make grub installation host specific
  - Copy into target wpa_supplicant config
  - Copy into target repo itself
  - Copy into target gpg keys - import them
  - Copy into target ssh keys - ssh-add them

2. Distill existing guides into ansible

- Official installation guide - https://archlinuxarm.org/platforms/armv8/broadcom/raspberry-pi-3
- General and SD card formatting - https://gist.github.com/theramiyer/cb3b406128e54faa12c37e1a01f7ae15
- Get further on setup on desktop builder machine via QEMU - https://wiki.polaire.nl/doku.php?id=archlinux-raspberry-encrypted
- Encrypted disk - https://gist.github.com/gea0/4fc2be0cb7a74d0e7cc4322aed710d38

3. Enable memory-only journald
4. Figure out multi-machine data schema for:

- IP addresses
- DNS
- Directories to sync
- Enable ssh

5. Document bootstrapping
