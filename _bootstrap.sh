#! /bin/bash

set -o errexit
set -o nounset

partition_for() {
  local name="$1"
  local disk="$2"

  number=$(parted "$disk" print | grep "$name" | tr -s " " | cut -d " " -f 2)
  if [[ "$disk" == *"nvme"* ]]; then
    echo "${disk}p${number}"
  else
    echo "${disk}${number}"
  fi
}

start_wpa_wifi() {
  local wireless_card="$1"
  local ssid="$2"
  local wifi_passphrase="$3"

  cat <<'WPA_SUPPLICANT' > "/etc/wpa_supplicant/$ssid.conf"
ctrl_interface=/run/wpa_supplicant
ctrl_interface_group=wheel
update_config=1
country=US
WPA_SUPPLICANT

  wpa_passphrase "$ssid" "$wifi_passphrase" >> "/etc/wpa_supplicant/$ssid.conf"
  chmod 600 "/etc/wpa_supplicant/$ssid.conf"

  ip link set dev "$wireless_card" up
  wpa_supplicant -B -i "$wireless_card" -c "/etc/wpa_supplicant/$ssid.conf"
  dhcpcd "$wireless_card"
}

network_down() {
  if ! curl --silent --fail --output /dev/null google.com ; then
    return 0
  fi

  return 1
}

setup_network() {
  local wireless_card="$1"
  local ssid="$2"

  if ! network_down ; then
    return
  fi

  read -s -p "WPA passphrase:" wifi_passphrase
  start_wpa_wifi "$wireless_card" "$ssid" "$wifi_passphrase"

  if network_down ; then
    >&2 echo "No internet. If over wifi probably use wpa_passphrase, wpa_supplicant and dhcpd"
    exit 1
  fi
}

format_and_mount_boot_partition() {
  local boot_device="$1"
  local efi_partition="$2"

  # TODO: Zero out the partition
  # dd if=/dev/zero of=$boot_device bs=16M

  mkfs.vfat -F32 "$efi_partition"
  mkfs.ext4 -O ^has_journal -L grub "$boot_device"
  mkdir -p /mnt/boot
  mount "$boot_device" /mnt/boot
  mkdir -p /mnt/boot/efi
  mount "$efi_partition" /mnt/boot/efi
}

create_and_mount_encrypted_root_volume() {
  local root_partition="$1"
  local encrypted_volume_group_name="vgcrypt"
  local root_logical_volume_name="root"
  local root_device="/dev/mapper/$encrypted_volume_group_name-$root_logical_volume_name"

  cryptsetup \
    --cipher aes-xts-plain64 \
    --hash sha512 \
    --key-size 512 \
    --verify-passphrase \
    --verbose \
    luksFormat "$root_partition"
  cryptsetup luksOpen "$root_partition" lvm

  # TODO: Zero out the partition
  # dd if=/dev/zero of=/dev/mapper/lvm bs=16M

  pvcreate /dev/mapper/lvm
  vgcreate $encrypted_volume_group_name /dev/mapper/lvm

  lvcreate --extents +100%FREE -n $root_logical_volume_name $encrypted_volume_group_name

  mkfs.ext4 -O ^has_journal -b 4096 -L $root_logical_volume_name "$root_device"
  mount "$root_device" /mnt
}

ansible_bootstrap() {
  local hostname="$1"
  local username="$2"

  cp -r . /mnt/root/arch-ansible

  arch-chroot /mnt /root/arch-ansible/initial-configure-xps "$hostname"
  arch-chroot /mnt sh -c "cd /root/arch-ansible && ./ansible \
    -e bootstrap='true' --tags bootstrap"

  cp -r . "/mnt/home/$username/src/arch-ansible"
  arch-chroot /mnt chown -R "$username":"$username" "/home/$username/src/arch-ansible"

  cp -r gpg-keys "/mnt/home/$username/gpg-keys"
  arch-chroot /mnt chown -R "$username":"$username" "/home/$username/gpg-keys"
  arch-chroot /mnt bash -c "chmod -R 0600 /home/$username/gpg-keys/*"

  arch-chroot /mnt mkdir "/home/$username/.ssh"
  cp -r ssh-keys/* "/mnt/home/$username/.ssh"
  arch-chroot /mnt chown -R "$username":"$username" "/home/$username/.ssh"
  arch-chroot /mnt bash -c "chmod -R 0600 /home/$username/.ssh/*"
}

bootstrap() {
  local hostname="$1"
  local username="$2"
  local disk="$3"
  local ssid="$4"
  local wireless_card="$5"

  local boot_partition=$(partition_for "Grub" $disk)
  local root_partition=$(partition_for "Arch Root" $disk)
  local efi_partition=$(partition_for "EFI" $disk)

  mkdir -p /mnt
  create_and_mount_encrypted_root_volume "$root_partition"
  format_and_mount_boot_partition "$boot_partition" "$efi_partition"

  setup_network "$wireless_card" "$ssid"
  if [[ -n "$ssid" ]] ; then
    cp -r /etc/wpa_supplicant/*.conf /mnt/etc/wpa_supplicant/
  fi

  cat <<'LIST' > /etc/pacman.d/mirrorlist
  Server = https://mirrors.kernel.org/archlinux/$repo/os/$arch
  Server = https://mirrors.ocf.berkeley.edu/archlinux/$repo/os/$arch
  Server = https://mirror.grig.io/archlinux/$repo/os/$arch
LIST

  pacman-key --refresh-keys
  pacstrap /mnt base linux linux-firmware linux-headers
  genfstab -U -p /mnt >> /mnt/etc/fstab
  ansible_bootstrap "$hostname" "$username"
}
