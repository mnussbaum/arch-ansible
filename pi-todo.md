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
  * ruby-rexml missing across the board atm, in community testing
  * thermald doesn't compile
  * greetd-gtkgreet - Should be fixed in versions > 0.7, using git version for not
  * spotify
  * qemu-arm-static
  * firefox-nightly
  * Need to set `LIBGL_ALWAYS_SOFTWARE=1` for alacritty to run
    * Might be able to use zink?
  * nerd-fonts-complete completely fills the disk :rimshot:
* Fix alacritty
* Wifi not working in pi
  * Worked when I manually setup 2.4 network, try that
* Fix boot error complaining about no resume something
* Upgrade to the pi 3 image
* Enable remote management
  * Root volume unlock via SSH
  * Enable normal SSH
  * Wireguard for WAN networking
  * Remote targeting of ansible
  * Remote sync
