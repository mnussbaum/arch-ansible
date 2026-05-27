# shellcheck shell=bash
# Generate an ephemeral per-build LUKS bootstrap keyfile.
#
# systemd-repart encrypts var/home (and the first-boot swap partition) with this
# key via mkosi's `[Validation] Passphrase=` setting. mkosi.common ExtraTrees
# bakes the same file into the image at /etc/cryptsetup-keys.d/luks.passphrase
# and /efi/loader/credentials/luks.passphrase so the disk auto-unlocks on first
# boot, before any TPM2/FIDO2 keyslot exists.
#
# It lives outside the repo: BuildSources=../ remounts the repo at /work inside
# the mkosi sandbox, so a keyfile in the repo isn't reachable at its host path
# when systemd-repart binds it. mkosi.conf references this same ~/.cache path.
#
# This is purely a bootstrap key: luks-enroll.service enrolls TPM2 + a recovery
# key (and bin/enroll-yubikeys adds FIDO2) and then wipes this keyslot. There is
# no passphrase keyslot. The key is random, generated fresh for every build, and
# never committed or stored anywhere outside the image it unlocks.
luks_keyfile="$HOME/.cache/mkosi-luks-bootstrap.passphrase"
trap 'rm -f "$luks_keyfile"' EXIT
mkdir -p "$(dirname "$luks_keyfile")"
(umask 077; head -c 512 /dev/urandom | base64 -w0 >"$luks_keyfile")
