## Nice to improve

1. Host groups to reduce host var duplication
1. Repartition windows partition
1. Specify partitions as sizes
1. Make it easier to add a new host, vars, hosts.yml
1. Structured secrets
   1. Wifi secrets dir to replace vault
   1. Document secret setup in new host adding docs

### Live image

1. Move to systemd-boot
1. Install more (or everything) during early bootstrapping and live USB

## Bugs

- machinectl depends on disutils which was removed in python 3.12
  - Maybe just remove pi support and machinectl altogether
- During boostrapping, after reboot, caps lock isn't remapped to escape until sway is available

## Tasks

- Back up primary key
- Test full gpg creation script
- Remove 2fa backups from pass
- Rebuild install media with final state
- Label physical media
- Test offline iso build and install
- Prepare physical recovery packages

## In the middle

- Of building fancy QEMU ISO
