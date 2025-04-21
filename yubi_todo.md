# TODO

- Separate primary key generation into its own script
- Add script for provisioning new computer
- Add script for provisioning new yubikey
- Install CCID and run SCCID daemon on install media
- Set up yubikey on Android via https://github.com/drduh/YubiKey-Guide/issues/368#issuecomment-1414562947
- Set up yubikey for disk decryption
- Set up yubikey for user login

## New yubikey

- Require touch:

```
ykman openpgp keys set-touch att on --force --admin-pin 12345678
ykman openpgp keys set-touch aut on --force --admin-pin 12345678
ykman openpgp keys set-touch dec on --force --admin-pin 12345678
ykman openpgp keys set-touch sig on --force --admin-pin 12345678
```

- Set up yubikey for SSH via FIDO
- Update GPG pin/pw/puk setting:

```
gpg2 --card-edit <email><<-EOF
...
<<EOF
```

- Generate a subkey:

```
FINGERPRINT=$(gpg2 --list-key $EMAIL | grep -oE '[A-Z0-9]{40}')

# Subkeys
echo "$PASSPHRASE" | gpg2 --pinentry-mode loopback \
  --batch --no-tty --yes --passphrase-fd 0 --quick-add-key $FINGERPRINT \
  cv25519 encrypt 0
echo "$PASSPHRASE" | gpg2 --pinentry-mode loopback \
  --batch --no-tty --yes --passphrase-fd 0 --quick-add-key $FINGERPRINT \
  ed25519 sign 0
echo "$PASSPHRASE" | gpg2 --pinentry-mode loopback \
  --batch --no-tty --yes --passphrase-fd 0 --quick-add-key $FINGERPRINT \
  ed25519 auth 0
```

- Move subkey private files into yubikey:

```
gpg --edit-key <email><<-EOF
...
EOF
```

- Import public keys on all managed computers
- Add new key to password store?
- Register FIDO SSH key with github, gitlab(s), other computers?

## New computer

- Give primary key ultimate trust:

```
cat <<EOF >> ~/.gnupg/gpg.conf
trusted-key <primary key ID>
EOF
```

- Import public keys with `echo <public key> | gpg2 –quiet –import`
