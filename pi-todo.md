### Guides

- Official installation guide - https://archlinuxarm.org/platforms/armv8/broadcom/raspberry-pi-3
- General and SD card formatting - https://gist.github.com/theramiyer/cb3b406128e54faa12c37e1a01f7ae15
- Get further on setup on desktop builder machine via QEMU - https://wiki.polaire.nl/doku.php?id=archlinux-raspberry-encrypted
- Encrypted disk - https://gist.github.com/gea0/4fc2be0cb7a74d0e7cc4322aed710d38
- https://gist.github.com/pezz/5310082

### Todo

* Missing packages
  * hwinfo
  * vscode-{html|css}-languageserver-bin - I forgot which one
  * vscode-json-languageserver-bin
  * thermald doesn't compile
  * greetd-gtkgreet - Should be fixed in versions >= 0.8, using git version for not
  * spotify
* Fix cleanup failing, why are there files in boot that don't seem to be from the mount?
* Fix ownership of files in homedir, arch-ansible repo
* Upgrade to the pi 3 image
  * This should let me remove references to linux-raspberrypi-headers in build-pi-container.yml
* Enable remote management
  * Root volume unlock via SSH
  * Enable normal SSH
  * Wireguard for WAN networking
  * Remote targeting of ansible
  * Remote sync
