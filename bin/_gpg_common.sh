set -o errexit
set -o nounset
set -o pipefail

# Requires FINGERPRINT, SUBKEY_BACKUP, and GNUPGHOME to be set by the caller.
#
# GPG_BATCH: use for all key operations in the temp GNUPGHOME. Uses loopback
# pinentry with an empty passphrase — security for the ephemeral key comes from
# the LUKS-encrypted USB, not the GPG key passphrase.
GPG_BATCH=(gpg --batch --pinentry-mode loopback --passphrase "")

USB_MAPPER="gpg-offline-usb"
USB_MOUNT=""

setup_gnupghome() {
  local gnupghome="$1"
  chmod 700 "$gnupghome"
  cp files/scdaemon.conf "$gnupghome/scdaemon.conf"
}

format_and_open_usb() {
  local device="$1"
  USB_MOUNT=$(mktemp -d)
  echo "==> Formatting $device with LUKS encryption..."
  sudo cryptsetup luksFormat "$device"
  sudo cryptsetup open "$device" "$USB_MAPPER"
  echo "==> Creating filesystem..."
  sudo mkfs.ext4 -F "/dev/mapper/$USB_MAPPER"
  sudo mount "/dev/mapper/$USB_MAPPER" "$USB_MOUNT"
  sudo chown "$(id -u):$(id -g)" "$USB_MOUNT"
}

open_usb() {
  local device="$1"
  USB_MOUNT=$(mktemp -d)
  echo "==> Opening encrypted USB $device..."
  sudo cryptsetup open "$device" "$USB_MAPPER"
  sudo mount "/dev/mapper/$USB_MAPPER" "$USB_MOUNT"
  sudo chown "$(id -u):$(id -g)" "$USB_MOUNT"
}

close_usb() {
  if [[ -n "$USB_MOUNT" ]]; then
    sudo umount "$USB_MOUNT" 2>/dev/null || true
    rmdir "$USB_MOUNT" 2>/dev/null || true
    USB_MOUNT=""
  fi
  sudo cryptsetup close "$USB_MAPPER" 2>/dev/null || true
}

program_yubikey() {
  # Subkey order: 1=[S], 2=[E], 3=[A]
  # [S] and [A] require slot selection (1 and 3); [E] has only one slot.
  # Does not use GPG_BATCH: the YubiKey PIN must go through normal pinentry,
  # not the loopback passphrase used for the ephemeral GPG key.
  printf '%s\n' \
    'key 1' 'keytocard' '1' 'key 1' \
    'key 2' 'keytocard' 'key 2' \
    'key 3' 'keytocard' '3' 'key 3' \
    'save' | \
    gpg --yes --no-tty --command-fd 0 --edit-key "$FINGERPRINT"
}

restore_subkeys() {
  "${GPG_BATCH[@]}" --yes --delete-secret-key "$FINGERPRINT"
  gpg --decrypt "$SUBKEY_BACKUP" | "${GPG_BATCH[@]}" --import
}

change_yubikey_pins() {
  # Prompts for new PINs (with confirmation); ykman prompts for the current
  # PINs interactively so this works regardless of whether the card is at
  # factory defaults or already has custom PINs.
  echo "==> Setting YubiKey PINs..."
  local user_pin user_pin2 admin_pin admin_pin2
  while true; do
    read -r -s -p "  New user PIN (min 6 chars): " user_pin; echo
    read -r -s -p "  Confirm user PIN: " user_pin2; echo
    [[ "$user_pin" == "$user_pin2" ]] && break
    echo "  PINs do not match, try again."
  done
  while true; do
    read -r -s -p "  New admin PIN (min 8 chars): " admin_pin; echo
    read -r -s -p "  Confirm admin PIN: " admin_pin2; echo
    [[ "$admin_pin" == "$admin_pin2" ]] && break
    echo "  PINs do not match, try again."
  done
  echo "  Enter the CURRENT user PIN when prompted (default: 123456):"
  ykman openpgp access change-pin --new-pin "$user_pin"
  echo "  Enter the CURRENT admin PIN when prompted (default: 12345678):"
  ykman openpgp access change-admin-pin --new-admin-pin "$admin_pin"
}

program_all_yubikeys() {
  local key_number=1
  while true; do
    echo ""
    echo "Plug in YubiKey $key_number and press Enter, or type 'done' to finish..."
    read -r response
    [[ "$response" == "done" ]] && break

    if [[ $key_number -gt 1 ]]; then
      echo "==> Restoring subkeys from backup for YubiKey $key_number..."
      restore_subkeys
    fi

    echo "==> Programming YubiKey $key_number..."
    program_yubikey
    change_yubikey_pins

    (( key_number++ ))
  done

  echo ""
  echo "==> $((key_number - 1)) YubiKey(s) programmed."
}
