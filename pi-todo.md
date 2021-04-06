### Guides

- Official installation guide - https://archlinuxarm.org/platforms/armv8/broadcom/raspberry-pi-3
- General and SD card formatting - https://gist.github.com/theramiyer/cb3b406128e54faa12c37e1a01f7ae15
- Get further on setup on desktop builder machine via QEMU - https://wiki.polaire.nl/doku.php?id=archlinux-raspberry-encrypted
- Encrypted disk - https://gist.github.com/gea0/4fc2be0cb7a74d0e7cc4322aed710d38
- https://gist.github.com/pezz/5310082

### Todo

* Missing packages
  * hwinfo
  * vscode-languageserver-bin
  * vscode-json-languageserver-bin
  * ruby-rexml missing across the board atm, in community testing
  * thermald has a missing upower-glib dependency
  * starship prompt doesn't work - need to update https://github.com/starship/starship/pull/2137/files for arm with glibc
* Wifi not working in pi
  * Worked when I manually setup 2.4 network, try that
* Copy arch-ansible dir to user home instead of alarm home
  * Should get rid of all references to alarm home
* Fix boot error complaining about no resume something
* Test cleanup and open tags
* Rename desired_partitions to partitions
* Upgrade to the pi 3 image
* Enable remote management
  * Root volume unlock via SSH
  * Enable normal SSH
  * Wireguard for WAN networking
  * Remote targeting of ansible
  * Remote sync
