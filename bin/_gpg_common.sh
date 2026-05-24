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

OLD_USB_MAPPER="gpg-offline-usb-old"
OLD_USB_MOUNT=""

setup_gnupghome() {
  local gnupghome="$1"
  chmod 700 "$gnupghome"
  cp roles/gpg/files/scdaemon.conf "$gnupghome/scdaemon.conf"

  # Pinentry script that supplies the card admin PIN without prompting.
  # _write_card_admin_pin() must be called before any card operations.
  local pin_file="$gnupghome/card-admin-pin"
  local pinentry="$gnupghome/pinentry.sh"
  cat > "$pinentry" << PINENTRY_EOF
#!/bin/bash
echo "OK Pleased to meet you"
while IFS= read -r line; do
    case "\$line" in
        GETPIN) printf 'D %s\nOK\n' "\$(cat '$pin_file')" ;;
        BYE)    echo "OK"; exit 0 ;;
        *)      echo "OK" ;;
    esac
done
PINENTRY_EOF
  chmod +x "$pinentry"
  printf 'pinentry-program %s\n' "$pinentry" > "$gnupghome/gpg-agent.conf"
}

_write_card_admin_pin() {
  printf '%s' "$YUBIKEY_CURRENT_ADMIN_PIN" > "$GNUPGHOME/card-admin-pin"
  chmod 600 "$GNUPGHOME/card-admin-pin"
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

open_old_usb() {
  local device="$1"
  OLD_USB_MOUNT=$(mktemp -d)
  echo "==> Opening existing root key USB $device..."
  sudo cryptsetup open "$device" "$OLD_USB_MAPPER"
  sudo mount "/dev/mapper/$OLD_USB_MAPPER" "$OLD_USB_MOUNT"
}

close_old_usb() {
  if [[ -n "$OLD_USB_MOUNT" ]]; then
    sudo umount "$OLD_USB_MOUNT" 2>/dev/null || true
    rmdir "$OLD_USB_MOUNT" 2>/dev/null || true
    OLD_USB_MOUNT=""
  fi
  sudo cryptsetup close "$OLD_USB_MAPPER" 2>/dev/null || true
}

program_yubikey() {
  # Set all three card slots to Curve25519 variants before moving keys.
  # Slots default to rsa2048 and must be changed to accept ed25519/cv25519.
  # This clears any existing keys in those slots, so all three are re-programmed.
  printf '%s\n' \
    'admin' \
    'key-attr' \
    '2' '1' \
    '2' '1' \
    '2' '1' \
    'quit' | \
    gpg --no-tty --command-fd 0 --card-edit

  # Move all three subkeys in one session. Subkey order: 1=[S], 2=[E], 3=[A].
  # The auto-PIN pinentry (set up in setup_gnupghome) satisfies admin PIN
  # requests without prompting, so the PIN is available for each keytocard call.
  printf '%s\n' \
    'key 1' 'keytocard' '1' \
    'key 1' 'key 2' 'keytocard' '2' \
    'key 2' 'key 3' 'keytocard' '3' \
    'save' | \
    gpg --yes --no-tty --command-fd 0 --edit-key "$FINGERPRINT"
}

restore_subkeys() {
  # Remove stub files without killing the agent. Killing the agent would clear
  # the passphrase cache; keytocard would then call the pinentry which returns
  # the card admin PIN instead of the empty key passphrase, causing it to fail.
  # gpg-agent reads key material from disk on each operation so removing the
  # stub files and importing fresh material is sufficient.
  rm -f "$GNUPGHOME/private-keys-v1.d"/*.key
  "${GPG_BATCH[@]}" --import "$SUBKEY_BACKUP"
}

_collect_new_pin_config() {
  # Sets target PIN/password globals applied to every YubiKey. Called once before the loop.
  echo "==> New PIN configuration (will be applied to all YubiKeys)"
  local user_pin2 admin_pin2
  while true; do
    read -r -s -p "  New user PIN (min 6 chars): " YUBIKEY_NEW_USER_PIN; echo
    read -r -s -p "  Confirm new user PIN: " user_pin2; echo
    [[ "$YUBIKEY_NEW_USER_PIN" == "$user_pin2" ]] && break
    echo "  PINs do not match, try again."
  done
  while true; do
    read -r -s -p "  New admin PIN (min 8 chars): " YUBIKEY_NEW_ADMIN_PIN; echo
    read -r -s -p "  Confirm new admin PIN: " admin_pin2; echo
    [[ "$YUBIKEY_NEW_ADMIN_PIN" == "$admin_pin2" ]] && break
    echo "  PINs do not match, try again."
  done
  echo "    OATH password (required by Yubico Authenticator to access 2FA codes):"
  local oath_pw2
  while true; do
    read -r -s -p "  New OATH password: " YUBIKEY_OATH_PASSWORD; echo
    read -r -s -p "  Confirm OATH password: " oath_pw2; echo
    [[ "$YUBIKEY_OATH_PASSWORD" == "$oath_pw2" ]] && break
    echo "  Passwords do not match, try again."
  done
}

change_yubikey_pins() {
  echo "==> Setting YubiKey PINs..."
  ykman openpgp access change-pin \
    --pin "$YUBIKEY_CURRENT_USER_PIN" \
    --new-pin "$YUBIKEY_NEW_USER_PIN"
  ykman openpgp access change-admin-pin \
    --admin-pin "$YUBIKEY_CURRENT_ADMIN_PIN" \
    --new-admin-pin "$YUBIKEY_NEW_ADMIN_PIN"
}

load_oath_accounts() {
  local oath_file="$USB_MOUNT/oath-accounts.txt"
  if [[ ! -f "$oath_file" ]]; then
    echo "==> No OATH seed backup found on USB, skipping."
    return
  fi
  echo "==> Loading OATH accounts onto YubiKey..."
  local count=0
  while IFS= read -r uri || [[ -n "$uri" ]]; do
    [[ -z "$uri" || "$uri" == \#* ]] && continue
    ykman oath accounts uri --touch --force "$uri"
    count=$(( count + 1 ))
  done < "$oath_file"
  echo "    Loaded $count OATH account(s)."
}

reset_oath_applet() {
  echo "==> Resetting OATH applet..."
  ykman oath reset --force
}

set_oath_password() {
  echo "==> Setting OATH application password..."
  ykman oath access change --new-password "$YUBIKEY_OATH_PASSWORD"
}

enroll_luks_fido2() {
  local device
  device=$(cryptsetup status cryptroot 2>/dev/null | awk '/device:/{print $2}') || true
  if [[ -z "$device" ]]; then
    echo "==> cryptroot not active — skipping LUKS FIDO2 enrollment."
    return
  fi
  echo "==> Enrolling FIDO2 keyslot on $device (touch YubiKey when prompted)..."
  systemd-cryptenroll --fido2-device=auto "$device"
  echo "    FIDO2 keyslot enrolled."
}

program_all_yubikeys() {
  _collect_new_pin_config
  local key_number=1
  while true; do
    gpgconf --kill scdaemon
    echo ""
    echo "Plug in YubiKey $key_number and press Enter, or type 'done' to finish..."
    read -r response
    [[ "$response" == "done" ]] && break

    until gpg --card-status > /dev/null 2>&1; do
      echo "    Card not detected — re-insert the YubiKey and press Enter to retry..."
      read -r _ignored
    done

    echo "==> Resetting OpenPGP applet..."
    ykman openpgp reset --force
    gpgconf --kill scdaemon
    until gpg --card-status > /dev/null 2>&1; do
      sleep 1
    done
    YUBIKEY_CURRENT_USER_PIN="123456"
    YUBIKEY_CURRENT_ADMIN_PIN="12345678"
    _write_card_admin_pin

    if [[ $key_number -gt 1 ]]; then
      echo "==> Restoring subkeys from backup for YubiKey $key_number..."
      restore_subkeys
    fi

    echo "==> Programming YubiKey $key_number..."
    program_yubikey
    change_yubikey_pins
    reset_oath_applet
    load_oath_accounts
    set_oath_password
    enroll_luks_fido2

    (( key_number++ ))
  done

  echo ""
  echo "==> $((key_number - 1)) YubiKey(s) programmed."
}
