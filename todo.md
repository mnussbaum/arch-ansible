## Nice to improve

- Host groups to reduce host var duplication
- Repartition windows partition
- Specify partitions as sizes
- Make it easier to add a new host, vars, hosts.yml, generate mkosi partition UUID
- Structured secrets
  - Wifi secrets dir to replace vault
  - Document secret setup in new host adding docs
- Make container file capable of building live USB
  - Include it in recovery
- DRY up host YAMLs and connection type in hosts.yml

### Live image

1. Move to systemd-boot
1. Install more (or everything) during early bootstrapping and live USB

## Bugs

- machinectl depends on disutils which was removed in python 3.12
  - Maybe just remove pi support and machinectl altogether
- During boostrapping, after reboot, caps lock isn't remapped to escape until sway is available

## Tasks

- Rebuild install media with final state
- Label physical media
- Test offline iso build and install
- Prepare physical recovery packages
- Remove 2fa backups from pass
- Remove old 2fa app and data from phone
