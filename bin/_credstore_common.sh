# shellcheck shell=bash
# Build the systemd credential store baked into the image.
#
# Delivers home.create.<user>, the JSON user record that
# systemd-homed-firstboot.service consumes (ImportCredential=home.*) to create
# the user's per-user LUKS home UNATTENDED on first boot. The home is
# bootstrapped with a recovery secret kept in pass (encrypted to the GPG key, not
# the vault). The YubiKey PKCS#11 token is enrolled later, at first login, by the
# user-firstboot playbook; the recovery secret then remains the fallback factor
# for a lost/broken token, which homed best practice recommends having anyway.
#
# A hardware token cannot be enrolled unattended (it requires user presence), so
# this two-phase split - recovery secret at boot, token at first login - is the
# supported pattern for token-backed homed users.
#
# The baked credential is root-only and lives on the LUKS-encrypted root, the
# same posture as the LUKS bootstrap key in _luks_common.sh. It can't be
# TPM-bound on a generic, multi-machine image.
#
# It is built outside the repo (under ~/.cache): the repo is ExtraTrees'd to
# /usr/local/share/arch-ansible and remounted in the mkosi sandbox, so a secret
# written inside the repo would leak into the image. mkosi.conf references this
# same ~/.cache path.
: "${PASSWORD_STORE_DIR:=$HOME/.local/share/password-store}"
export PASSWORD_STORE_DIR

credstore_user=$(python3 -c \
  "import yaml;print(yaml.safe_load(open('group_vars/all/vars.yml'))['user']['name'])")
credstore_shell=$(python3 -c \
  "import yaml;print(yaml.safe_load(open('group_vars/all/vars.yml'))['user']['shell'])")
credstore_recovery="linux_users/$credstore_user/recovery-key"

# Generate the recovery secret once and keep it in pass, so it is stable across
# rebuilds and usable as the user's fallback credential.
if ! pass show "$credstore_recovery" >/dev/null 2>&1; then
  echo "==> Generating home recovery secret in pass ($credstore_recovery)..."
  openssl rand -base64 24 | pass insert -m -f "$credstore_recovery" >/dev/null
fi

credstore_dir="$HOME/.cache/mkosi-credstore"
# Preserve _luks_common.sh's cleanup (luks_keyfile is set there when sourced first).
trap 'rm -rf "$credstore_dir"; rm -f "${luks_keyfile:-}"' EXIT
rm -rf "$credstore_dir"
mkdir -p "$credstore_dir"
chmod 700 "$credstore_dir"

echo "==> Building home.create.$credstore_user + home.new-password credentials..."
# systemd-homed-firstboot ignores any "secret" field embedded in the user record;
# the password comes from a SEPARATE credential, home.new-password (read via the
# ask-password .credential = "home.new-password" path in homectl's
# acquire_new_password()). systemd-homed-firstboot.service ImportCredential=home.*
# imports both.
(umask 077; pass show "$credstore_recovery" \
  | CREDSTORE_USER="$credstore_user" CREDSTORE_SHELL="$credstore_shell" \
    CREDSTORE_DIR="$credstore_dir" python3 -c '
import json, os, sys
pw = sys.stdin.read().strip()
user = os.environ["CREDSTORE_USER"]
d = os.environ["CREDSTORE_DIR"]
record = {
    "userName": user,
    "memberOf": ["wheel", "input", "pcscd", "docker"],
    "shell": os.environ["CREDSTORE_SHELL"],
    "storage": "luks",
}
with open(f"{d}/home.create.{user}", "w") as f:
    json.dump(record, f)
with open(f"{d}/home.new-password", "w") as f:
    f.write(pw)
')
