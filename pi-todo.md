### Guides

- Official installation guide - https://archlinuxarm.org/platforms/armv8/broadcom/raspberry-pi-3
- General and SD card formatting - https://gist.github.com/theramiyer/cb3b406128e54faa12c37e1a01f7ae15
- Get further on setup on desktop builder machine via QEMU - https://wiki.polaire.nl/doku.php?id=archlinux-raspberry-encrypted
- Encrypted disk - https://gist.github.com/gea0/4fc2be0cb7a74d0e7cc4322aed710d38
- https://gist.github.com/pezz/5310082

### Todo

* Test cleanup and open tags
* Rename desired_partitions to partitions
* Need to test all changes against qemu still
  * Make sure to test the rebuild-boot-partition tag too
* Upgrade to the pi 3 image
* Enable remote management
  * Root volume unlock via SSH
  * Enable normal SSH
  * Wireguard for WAN networking
  * Remote targeting of ansible
  * Remote sync
