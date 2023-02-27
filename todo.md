## Document how to

1. Build ISO
1. Build/run QEMU VM ISO and VM
1. Recover the boot partition
1. Setup a new machine
1. What the different tag modes are
1. Build a fresh install media

## Verify

1. Managed partition changes properly boot partitions
1. Bootstrap secrets are installed properly
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

## Bugs

1. Ansible files not owned by user post-install
