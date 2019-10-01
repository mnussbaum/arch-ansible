1. Update existing scripting to use:
  * timedatectl
  * hostnamectl
  * localectl
  * a wpa passphrase file
2. Move existing scripting into ansible
3. Distill existing guides into ansible
  * Official installation guide - https://archlinuxarm.org/platforms/armv8/broadcom/raspberry-pi-3
  * General and SD card formatting - https://gist.github.com/theramiyer/cb2b406128e54faa12c37e1a01f7ae15
  * Get further on setup on desktop builder machine via QEMU - https://wiki.polaire.nl/doku.php?id=archlinux-raspberry-encrypted
  * Encrypted disk - https://gist.github.com/gea0/4fc2be0cb7a74d0e7cc4322aed710d38
4. Enable memory-only journald
5. Figure out multi-machine data schema for:
  * IP addresses
  * DNS
  * Directories to sync
6. Document bootstrapping
