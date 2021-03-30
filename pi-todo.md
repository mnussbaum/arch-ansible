### Guides

- Official installation guide - https://archlinuxarm.org/platforms/armv8/broadcom/raspberry-pi-3
- General and SD card formatting - https://gist.github.com/theramiyer/cb3b406128e54faa12c37e1a01f7ae15
- Get further on setup on desktop builder machine via QEMU - https://wiki.polaire.nl/doku.php?id=archlinux-raspberry-encrypted
- Encrypted disk - https://gist.github.com/gea0/4fc2be0cb7a74d0e7cc4322aed710d38
- https://gist.github.com/pezz/5310082

### Todo

* Consolidate input data with standard bootstrapping playbook
  * Migrated desired_partitions to a map
  * Need to test this in qemu and pi still
  * Also changed how connections are configured, putting it in ansible.cfg
* All references to arch-pi should become references to panamint
* Probably don't want to use alarm user for pi
* Merge like half of bootstrap-pre-chroot
  * Probably need to sort shared tasks into an included file or set of included files
* I think then run boostrap tasks from playbook.yml in container and bootstrap-post-chroot.yml
* Run rest of bootstrapping playbook in live image
* Upgrade to the pi 3 image
* Allow root volume unlock via SSH for remote management
