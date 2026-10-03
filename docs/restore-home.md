# Restore a home from backup

Seeds a machine's home from the latest restic snapshot in Backblaze. The machine
needs its own backup credentials first ([backup-credentials.md](backup-credentials.md)).
Check they work:

```bash
restic-backup snapshots
```

Then restore:

```bash
restic-backup restore                    # every path in /etc/restic-backup/includes
restic-backup restore -d ~/Documents     # or specific paths
```

By default the restore only adds files that are missing. It never deletes or
overwrites anything, so it's safe to run on a home that already has work in it,
such as a repo cloned during setup. Pass `--exact` to make each path match the
snapshot exactly, deleting files not in it and overwriting changed ones.

Restore before adding any Syncthing folders. If a folder is already being
synced, files deleted on other devices after the snapshot will come back and
sync out to them.
