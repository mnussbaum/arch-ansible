# Add a machine's backup credentials

`restic-backup` (the `backup` role) looks up its Backblaze key in `pass` by
hostname: `host_secrets/<hostname>/restic_backblaze_key{,_id}`. The repo
password (`restic_backup_password`) is shared. A new machine needs its own key
before it can back up or restore.

The password store ships read-only in the image (`/usr/share/password-store`),
so a machine sees credentials added before its image was built. Add them before
building the recovery USB that installs it, and it can restore right after its
first login.

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
