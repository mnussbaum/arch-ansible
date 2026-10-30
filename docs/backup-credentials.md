# Add a machine's backup credentials

`restic-backup` (the `backup` role) looks up its Backblaze key in `pass` by
hostname: `host_secrets/<hostname>/restic_backblaze_key{,_id}`. A new machine
needs its own key before it can back up or restore.

The image ships a read-only copy of the builder's password store, so a machine
sees credentials that were in that store when its image was built. Add Backblaze
host credentials before building the recovery USB, and a new machine can restore
right after its first login.

On a computer that isn't ours, set up as in
[set-up-recovery-computer.md](set-up-recovery-computer.md), first point gpg,
pass and SSH at the YubiKey. Insert it, and from the repo run:

```bash
gpg --import ansible/roles/gpg/files/gpg-pubkey.asc
gpg --card-status
echo enable-ssh-support >> ~/.gnupg/gpg-agent.conf
gpgconf --kill gpg-agent
export SSH_AUTH_SOCK=$(gpgconf --list-dirs agent-ssh-socket)
export PASSWORD_STORE_DIR=~/.local/share/password-store
export PASSWORD_STORE_GPG_OPTS="--trust-model always"
[ -d "$PASSWORD_STORE_DIR" ] || git clone git@gitlab.com:mnussbaum/password-store.git "$PASSWORD_STORE_DIR"
git -C "$PASSWORD_STORE_DIR" pull
```

1. Pick the machine's name. It's typed at the hostname prompt on the machine's
   first boot ([install-machine.md](install-machine.md)); for a machine that's
   already installed, use `hostname`.
2. Log in to Backblaze with `pass show backblaze.com`. The TOTP code comes
   from the YubiKey: `ykman oath accounts code Backblaze`.
3. Create an application key for that machine with read, list and write access
   to the `mnussbaum-machine-backups` bucket. Don't limit it to a file prefix:
   every machine shares one restic repo, and a restore needs to read other
   machines' snapshots.

Add the key to the password store and push:

```bash
pass insert host_secrets/<name>/restic_backblaze_key_id
pass insert host_secrets/<name>/restic_backblaze_key
pass git push
```

For a machine that's already installed, roll a new image with
`bin/update-system` and reboot into it.
