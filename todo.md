## Document how to

1. Recover the boot partition
1. Setup a new machine
1. What the different tag modes are

## Verify

1. Managed partition changes properly boot partitions
1. Bootstrap secrets are installed and cleaned properly
1. Arch-ansible (and subdirs) file and dir perms are right
1. Wipe partitions and actually wipe data and try it all out

## Nice to improve

1. Automate installing secret and config files:
   - /etc/wireguard/eeek-wg0.conf
   - ~/.aws/config
   - ~/.kube/config
1. Move eeek-wg0 VPN name into configuration
1. Do an actual gpg import on private key during bootstrapping - https://blog.veloc1ty.de/2018/08/06/pgp-trust-key-non-interactive-with-ansible/
1. Configure GOPRIVATE
1. Repartition windows partition
1. Specify partitions as sizes
1. Make it easier to add a new host, vars, hosts.yml
1. Offline install from ISO
1. Offline ISO build
1. Fix yay installs prompting for pw when they shouldn't
   in qemy

## Bugs

1. Fix networking in qemu post restart- http://ayekat.ch/blog/qemu-networkd maybe
