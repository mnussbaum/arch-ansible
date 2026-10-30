set -o errexit
set -o nounset
set -o pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "Error: bash 4 or newer is needed (macOS: brew install bash)." >&2
  exit 1
fi

# Requires FINGERPRINT, SUBKEY_BACKUP, and GNUPGHOME to be set by the caller.
#
# GPG_BATCH: use for all key operations in the temp GNUPGHOME. Uses loopback
# pinentry with an empty passphrase — security for the ephemeral key comes from
# the LUKS-encrypted USB, not the GPG key passphrase.
GPG_BATCH=(gpg --batch --pinentry-mode loopback --passphrase "")

# PIV slot loaded for systemd-homed PKCS#11 login (the "key management" slot, as
# in `man homectl`'s example). Every YubiKey is loaded with the SAME imported
# RSA key + self-signed cert, so a single homed enrollment (the volume key is
# wrapped to that one public key) is unlocked by ANY of the cards — mirroring how
# program_yubikey writes the same GPG subkeys to every card. The shared private
# key lives only on the LUKS-encrypted root GPG key USB and on the cards
# themselves.
HOMED_PIV_SLOT="9d"
# Factory PIV management key / PIN / PUK after `ykman piv reset` (pre-5.7 TDES
# default; ykman auto-detects the algorithm). Adjust if your YubiKeys ship a
# different factory management key.
PIV_DEFAULT_MGMT_KEY="010203040506070801020304050607080102030405060708"
PIV_DEFAULT_PIN="123456"
PIV_DEFAULT_PUK="12345678"

USB_MAPPER="gpg-offline-usb"
USB_MOUNT=""

PASSWORD_STORE_URL="git@gitlab.com:mnussbaum/password-store.git"
GITLAB_HOST_KEY="gitlab.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAfuCHKVTjquxvt6CM6tdG4SLp1Btn/nOeHHE5UOzRdf"

# Builds a root GPG key USB image: a LUKS volume holding the given files. Runs
# as root, natively on Linux and in a container on macOS, which has no LUKS.
# Arguments: the image file to create and the directory of files to copy.
KEY_USB_SCRIPT='
set -o errexit
set -o nounset
set -o pipefail
img=$1
files=$2
mapper=gpg-offline-usb-image
mount=$(mktemp -d)
truncate -s 64M "$img"
cryptsetup luksFormat "$img"
cryptsetup open "$img" "$mapper"
mkfs.ext4 -q "/dev/mapper/$mapper"
mount "/dev/mapper/$mapper" "$mount"
cp "$files"/* "$mount/"
umount "$mount"
cryptsetup close "$mapper"
rmdir "$mount"
'

OLD_USB_MAPPER="gpg-offline-usb-old"
OLD_USB_MOUNT=""

setup_gnupghome() {
  local gnupghome="$1"
  chmod 700 "$gnupghome"
  cp ansible/roles/gpg/files/scdaemon.conf "$gnupghome/scdaemon.conf"

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

# A directory for staging a root GPG key USB. On macOS it is under $HOME, which
# every macOS container runtime shares into its VM.
key_usb_stage_dir() {
  if [[ $(uname -s) == Darwin ]]; then
    mktemp -d "$HOME/.key-usb.XXXXXX"
  else
    mktemp -d
  fi
}

# Writes <stage>/files to <device> as a new LUKS-encrypted root GPG key USB,
# through an image built in <stage>.
write_key_usb() {
  local device="$1" stage="$2"

  echo "==> Encrypting the new root GPG key USB (choose its passphrase)..."
  if [[ $(uname -s) == Darwin ]]; then
    printf '%s' "$KEY_USB_SCRIPT" > "$stage/key-usb.sh"
    source bin/_container_common.sh
    container_runtime
    "${CONTAINER_RT[@]}" run --rm --interactive --tty --privileged --platform linux/amd64 \
      --volume "$stage:/stage" docker.io/library/archlinux:latest bash -c \
      'pacman -Sy --noconfirm --needed cryptsetup e2fsprogs >/dev/null
       bash /stage/key-usb.sh /stage/key-usb.img /stage/files'
  else
    sudo bash -c "$KEY_USB_SCRIPT" _ "$stage/key-usb.img" "$stage/files"
  fi

  bin/burn-image "$stage/key-usb.img" "$device"
}

# Mounts the root GPG key USB at USB_MOUNT. macOS has no LUKS, so there it copies
# the whole drive into a file, opens that in a container and leaves copies of
# its files in USB_MOUNT. Writes to those would be lost, so callers on macOS
# must pass --read-only.
open_usb() {
  local device="$1" mode="${2:-}"

  if [[ $(uname -s) == Darwin ]]; then
    if [[ $mode != --read-only ]]; then
      echo "Error: on macOS the root GPG key USB can only be read; use Linux to change it." >&2
      exit 1
    fi
    USB_MOUNT=$(mktemp -d "$HOME/.key-usb.XXXXXX")
    echo "==> Copying encrypted USB $device (the whole drive, which takes a few minutes)..."
    diskutil unmountDisk "$device"
    sudo dd if="/dev/r${device#/dev/}" of="$USB_MOUNT/usb.img" bs=4m
    sudo chown "$(id -u)" "$USB_MOUNT/usb.img"
    echo "==> Opening it (enter the USB's passphrase)..."
    source bin/_container_common.sh
    container_runtime
    "${CONTAINER_RT[@]}" run --rm --interactive --tty --privileged --platform linux/amd64 \
      --volume "$USB_MOUNT:/usb" docker.io/library/archlinux:latest bash -c \
      'set -o errexit
       pacman -Sy --noconfirm --needed cryptsetup >/dev/null
       cryptsetup open --readonly /usb/usb.img key-usb
       mkdir /m
       mount -o ro /dev/mapper/key-usb /m
       cp /m/* /usb/
       chmod 644 /usb/*
       umount /m
       cryptsetup close key-usb'
    rm "$USB_MOUNT/usb.img"
    return
  fi

  USB_MOUNT=$(mktemp -d)
  echo "==> Opening encrypted USB $device..."
  sudo cryptsetup open "$device" "$USB_MAPPER"
  sudo mount "/dev/mapper/$USB_MAPPER" "$USB_MOUNT"
  sudo chown "$(id -u):$(id -g)" "$USB_MOUNT"
}

close_usb() {
  if [[ $(uname -s) == Darwin ]]; then
    if [[ -n "$USB_MOUNT" ]]; then rm -rf "$USB_MOUNT"; fi
    USB_MOUNT=""
    return
  fi

  if [[ -n "$USB_MOUNT" ]]; then
    sudo umount "$USB_MOUNT" 2>/dev/null || true
    rmdir "$USB_MOUNT" 2>/dev/null || true
    USB_MOUNT=""
  fi
  sudo cryptsetup close "$USB_MAPPER" 2>/dev/null || true
}

# Extends the subkeys of the key in GNUPGHOME by a year when any expires within
# 30 days, and exports the changed public key to the repo. Sets RENEWED then.
# Rebuilding or importing a key changes nothing, so otherwise the public key
# stays as it is.
renew_expiring_subkeys() {
  local renew_by expiring
  renew_by=$(( $(date +%s) + 30 * 24 * 60 * 60 ))
  expiring=$(gpg --list-keys --with-colons "$FINGERPRINT" \
    | awk -F: -v by="$renew_by" '$1 == "sub" && $7 != "" && $7 < by')
  RENEWED=""
  if [[ -z "$expiring" ]]; then
    return
  fi

  echo "==> Subkeys expire within 30 days; extending them by 1 year..."
  "${GPG_BATCH[@]}" --yes --quick-set-expire "$FINGERPRINT" 1y "*"
  gpg --armor --export "$FINGERPRINT" > ansible/roles/gpg/files/gpg-pubkey.asc
  RENEWED=1
}

# Clones the password store into PASSWORD_STORE_DIR, or pulls it, over SSH with
# the authentication subkey of the key in GNUPGHOME.
fetch_password_store() {
  : "${PASSWORD_STORE_DIR:=$HOME/.local/share/password-store}"
  export PASSWORD_STORE_DIR

  echo "==> Getting the password store over SSH..."
  echo enable-ssh-support >> "$GNUPGHOME/gpg-agent.conf"
  gpg --with-keygrip --list-keys "$FINGERPRINT" \
    | awk '/\[A\]/ { auth = 1 } auth && /Keygrip/ { print $NF " 0"; exit }' \
    > "$GNUPGHOME/sshcontrol"
  echo "$GITLAB_HOST_KEY" > "$GNUPGHOME/known_hosts"
  gpgconf --kill gpg-agent
  gpgconf --launch gpg-agent

  local git_env=(SSH_AUTH_SOCK="$(gpgconf --list-dirs agent-ssh-socket)"
    GIT_SSH_COMMAND="ssh -o UserKnownHostsFile=$GNUPGHOME/known_hosts")
  if [[ -d "$PASSWORD_STORE_DIR/.git" ]]; then
    env "${git_env[@]}" git -C "$PASSWORD_STORE_DIR" pull --quiet \
      || echo "    Warning: couldn't pull the password store; using it as it is."
  else
    mkdir -p "$(dirname "$PASSWORD_STORE_DIR")"
    env "${git_env[@]}" git clone --quiet "$PASSWORD_STORE_URL" "$PASSWORD_STORE_DIR"
  fi
}

open_old_usb() {
  local device="$1"
  OLD_USB_MOUNT=$(mktemp -d)
  echo "==> Opening existing root GPG key USB $device..."
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
  local user_pin2 admin_pin2 piv_pin2 piv_puk2
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
  echo "    PIV PIN + PUK (6-8 chars each; the PIN unlocks the home via systemd-homed):"
  while true; do
    read -r -s -p "  New PIV PIN (6-8 chars): " YUBIKEY_PIV_PIN; echo
    read -r -s -p "  Confirm PIV PIN: " piv_pin2; echo
    [[ "$YUBIKEY_PIV_PIN" != "$piv_pin2" ]] && { echo "  PINs do not match, try again."; continue; }
    [[ "${#YUBIKEY_PIV_PIN}" -ge 6 && "${#YUBIKEY_PIV_PIN}" -le 8 ]] && break
    echo "  PIV PIN must be 6-8 characters."
  done
  while true; do
    read -r -s -p "  New PIV PUK (6-8 chars): " YUBIKEY_PIV_PUK; echo
    read -r -s -p "  Confirm PIV PUK: " piv_puk2; echo
    [[ "$YUBIKEY_PIV_PUK" != "$piv_puk2" ]] && { echo "  PUKs do not match, try again."; continue; }
    [[ "${#YUBIKEY_PIV_PUK}" -ge 6 && "${#YUBIKEY_PIV_PUK}" -le 8 ]] && break
    echo "  PIV PUK must be 6-8 characters."
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
  local oath_file="${OATH_FILE:-$USB_MOUNT/oath-accounts.txt}"
  if [[ ! -f "$oath_file" ]]; then
    echo "==> No OATH seed backup found, skipping."
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

load_homed_piv_keypair() {
  # Materialize the shared homed PIV key + cert into temp files (inside the
  # ephemeral $GNUPGHOME, so they are wiped along with it) for import onto each
  # card. RSA2048 because systemd-homed wraps the home's LUKS volume key with the
  # certificate's public key at user creation (see `man homectl`, the
  # --pkcs11-token-uri example).
  #
  # The keypair lives in pass, encrypted to the GPG key, so GPG stays the only
  # root of trust and ONE key serves the user on every machine and every YubiKey.
  # It is read/written through the offline subkeys already imported into
  # $GNUPGHOME (no card needed); --trust-model always lets the first-run insert
  # encrypt to the freshly-imported, not-yet-trusted key.
  : "${PASSWORD_STORE_DIR:=$HOME/.local/share/password-store}"
  export PASSWORD_STORE_DIR PASSWORD_STORE_GPG_OPTS="--trust-model always"

  local user pass_key pass_cert
  user=$(awk '/^user:/ { u = 1; next } u && /^[^ ]/ { u = 0 } u && $1 == "name:" { print $2; exit }' \
    ansible/group_vars/all/vars.yml)
  pass_key="linux_users/$user/piv-key"
  pass_cert="linux_users/$user/piv-cert"

  HOMED_PIV_KEY="$GNUPGHOME/homed-piv-key.pem"
  HOMED_PIV_CERT="$GNUPGHOME/homed-piv-cert.pem"

  if [[ ! -f "$PASSWORD_STORE_DIR/.gpg-id" ]]; then
    echo "Error: no password-store at PASSWORD_STORE_DIR=$PASSWORD_STORE_DIR" >&2
    exit 1
  fi

  if [[ -f "$PASSWORD_STORE_DIR/$pass_key.gpg" ]]; then
    echo "==> Loading homed PIV key + cert from pass ($pass_key)..."
    (umask 077; pass show "$pass_key"  >"$HOMED_PIV_KEY")
    (umask 077; pass show "$pass_cert" >"$HOMED_PIV_CERT")
    return
  fi

  # A new key locks out every home enrolled with the old one, so only
  # create-gpg-key may mint it.
  if [[ -z "${HOMED_PIV_ALLOW_NEW:-}" ]]; then
    echo "Error: $pass_key is missing from $PASSWORD_STORE_DIR" >&2
    exit 1
  fi

  echo "==> Generating shared homed PIV RSA2048 key + cert, storing in pass..."
  (umask 077; openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
    -out "$HOMED_PIV_KEY")
  openssl req -new -x509 -key "$HOMED_PIV_KEY" -out "$HOMED_PIV_CERT" -days 36500 \
    -subj "/CN=systemd-homed $user"
  pass insert -m -f "$pass_key"  <"$HOMED_PIV_KEY"
  pass insert -m -f "$pass_cert" <"$HOMED_PIV_CERT"
}

provision_yubikey_piv() {
  # Load the shared homed key + cert into this card's PIV slot so systemd-homed
  # can unlock the user with it. Resets PIV first so the slot is the only
  # cert/key pair on the applet (--pkcs11-token-uri=auto requires exactly one).
  # pin-policy=once: PIN entered once per session. touch-policy=cached: a tap is
  # required but stays valid ~15s, so login/sudo/unlock bursts need a single tap.
  echo "==> Resetting PIV applet..."
  ykman piv reset --force
  echo "==> Setting PIV PIN/PUK..."
  ykman piv access change-pin --pin "$PIV_DEFAULT_PIN" --new-pin "$YUBIKEY_PIV_PIN"
  ykman piv access change-puk --puk "$PIV_DEFAULT_PUK" --new-puk "$YUBIKEY_PIV_PUK"
  echo "==> Protecting PIV management key with the PIN..."
  ykman piv access change-management-key \
    --management-key "$PIV_DEFAULT_MGMT_KEY" --pin "$YUBIKEY_PIV_PIN" \
    --protect --force
  echo "==> Importing homed key + cert into PIV slot $HOMED_PIV_SLOT..."
  ykman piv keys import \
    --pin "$YUBIKEY_PIV_PIN" --pin-policy once --touch-policy cached \
    "$HOMED_PIV_SLOT" "$HOMED_PIV_KEY"
  ykman piv certificates import \
    --pin "$YUBIKEY_PIV_PIN" "$HOMED_PIV_SLOT" "$HOMED_PIV_CERT"
}

program_all_yubikeys() {
  _collect_new_pin_config
  load_homed_piv_keypair
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
    provision_yubikey_piv

    (( key_number++ ))
  done

  echo ""
  echo "==> $((key_number - 1)) YubiKey(s) programmed."
}
