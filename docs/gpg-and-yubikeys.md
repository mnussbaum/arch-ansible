# GPG keys and YubiKeys

One GPG key is the root of trust. Its primary key (cert-only, no expiry) lives
offline on a LUKS-encrypted USB drive, the primary GPG USB, which is plugged in
only for key ceremonies. Its three subkeys (sign, encrypt, auth) live on every
YubiKey: encrypt decrypts the password store, and auth is the SSH key. Every
YubiKey also carries the same PIV key, kept in `pass`, which unlocks LUKS and
the homed home on every machine, and the TOTP seeds for 2FA codes.

Losing a YubiKey is covered under [Lost or blocked YubiKeys](#lost-or-blocked-yubikeys),
and losing more in [disaster-recovery.md](disaster-recovery.md).

## Primary GPG USB

### Create a new primary key

```
./bin/create-gpg-key <device> <existing-key-device>   # replacing a primary key
./bin/create-gpg-key <device> <totp-file>             # starting fresh
```

`<device>` is wiped. The second argument supplies the TOTP seeds: a previous primary
GPG USB (whose key also re-encrypts the password store) or a file of `otpauth://`
URIs.

This will:

1. Format and LUKS-encrypt `<device>`
2. Generate a new Ed25519 primary key (cert-only, no expiry)
3. Add three subkeys (sign, encrypt, auth), each expiring in 1 year
4. Generate a revocation certificate and store it on the USB
5. Back up the primary key to the USB
6. Export the public key to `ansible/roles/gpg/files/gpg-pubkey.asc`
7. Re-encrypt the password store to the new key and copy the TOTP seeds to the USB
8. Program all connected YubiKeys with the subkeys, the TOTP seeds and the shared
   homed PIV key (minted into pass on first run)

After running, commit the public key:

```
git add ansible/roles/gpg/files/gpg-pubkey.asc
git commit -m 'Add GPG public key'
```

Also add the SSH public key to GitHub/GitLab:

```
gpg --export-ssh-key <fingerprint>
```

### Back up the primary GPG USB

Keep a second encrypted copy of the primary GPG USB in a separate physical location:

```
./bin/backup-gpg-key <source-device> <dest-device>
```

The destination device is formatted and LUKS-encrypted, then the key files are copied.

### Print the recovery guide

The printed recovery guide holds the primary key on paper, with everything needed
to get from nothing to a working laptop with its home restored. Its text is
[recovery-guide.md](recovery-guide.md) and the docs it embeds; see that doc for
when to reprint.

```
./bin/generate-gpg-recovery-guide <primary-key-usb-device> [output.pdf]
./bin/generate-gpg-recovery-guide --preview [output.pdf]   # placeholders, no USB
```

Output defaults to `secrets/gpg-recovery-guide.pdf`.

## YubiKeys

### Provision new YubiKeys

YubiKeys are programmed as part of `create-gpg-key` or `enroll-yubikeys`. The scripts
loop interactively, prompting to insert each YubiKey in turn. Each YubiKey receives the
same three subkeys (sign, encrypt, auth), its TOTP seeds, and the shared PIV key from
`pass` that unlocks LUKS and homed, so a replacement YubiKey works on every machine
with no per-machine re-enrollment.

To program additional YubiKeys against an existing primary GPG USB:

```
./bin/enroll-yubikeys <device>
```

When prompted, insert YubiKeys one at a time and follow the prompts.

### Use YubiKeys

The YubiKey's GPG auth subkey is used for SSH via the GPG agent. Once Ansible has
provisioned the machine, the agent is configured automatically.

To verify the YubiKey is working:

```
gpg --card-status          # shows card info and subkey fingerprints
ssh-add -L                 # should show the auth subkey's SSH public key
```

If the agent is not picking up the card, restart it:

```
gpgconf --kill gpg-agent
gpg --card-status
```

### Renew YubiKeys

Subkeys expire annually. Run the renewal ceremony with the primary GPG USB plugged in:

```
./bin/enroll-yubikeys <device>   # e.g. /dev/sda1
```

This extends all subkey expiry by one year, exports the updated public key to
`ansible/roles/gpg/files/gpg-pubkey.asc`, and reprograms all YubiKeys. After running:

```
git add ansible/roles/gpg/files/gpg-pubkey.asc && git commit -m 'Renew GPG subkeys'
```

### Lost or blocked YubiKeys

**Lose a YubiKey.** Every YubiKey carries the same PIV key, so one can't be
revoked alone; its PIV PIN (limited attempts) is what protects it. To revoke,
rotate the key: put a new PIV key in pass and re-provision the remaining
YubiKeys (`bin/enroll-yubikeys`), then on each machine, while its TPM works,
wipe the old PKCS#11 slot (`bin/revoke-luks-yubikey <slot>`) and re-enroll
(`sudo /usr/bin/luks-enroll-pkcs11`).

**Lose every YubiKey.** Machines whose TPM still unlocks keep booting, but you
can't log in: homes take only the token. Rebuild YubiKeys from the offline
primary-key USB with `bin/enroll-yubikeys <device>`. It loads the same PIV key
from pass, so the new keys unlock every disk and home with no re-enrollment. If
the USB is gone too, rebuild the key from the paper recovery guide
([gpg-paper-recovery.md](gpg-paper-recovery.md)), which writes a new USB and
programs the YubiKeys the same way. Either way the password-store has to
be reachable first: with the primary key imported, gpg-agent's SSH support can
clone it.

**PIV PIN blocked** (too many wrong tries): unblock it with the PUK,

```bash
ykman piv access unblock-pin --puk <PUK> --new-pin <PIN>
```

If the PUK is blocked too, the PIV applet is lost; re-provision that YubiKey
with `bin/enroll-yubikeys`, which resets PIV and reloads the shared key. It also
resets the OpenPGP and OATH applets, as with any provisioning.

**Reach a home without a YubiKey.** You can't: after first login a home opens
only with the shared PIV key. Re-provision a YubiKey ("Lose every YubiKey",
above), or restore its data from restic.

## 2FA codes

TOTP codes are stored in the YubiKey OATH applet, separate from the password
store. This preserves genuine two-factor separation: compromising the password
store doesn't expose TOTP seeds. The OATH applet is password-protected; the
password is set during YubiKey provisioning.

Seeds are backed up as `otpauth://` URIs in `oath-accounts.txt` on the primary
GPG USB. They are automatically loaded onto each YubiKey during
`create-gpg-key` and `enroll-yubikeys`. The recovery guide includes QR codes
and `otpauth://` URIs for a curated set of critical accounts (defined in
`CRITICAL_TOTPS` in `bin/_recovery_guide.py`), so those accounts can
be restored from paper alone without the USB.

**Add a single account**

```
./bin/add-oath-account <device>
./bin/add-oath-account <device> --qr <screenshot.png>   # decode from a QR image
```

Backs up the seed to USB and adds it to the currently connected YubiKey.

**Generate codes**

```
ykman oath accounts code           # list all accounts with current codes
ykman oath accounts code <name>    # code for a specific account
```
