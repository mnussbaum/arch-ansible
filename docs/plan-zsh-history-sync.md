# Plan: Sync zsh history across laptops

References:
- zsh history options and `fc` — `man zshoptions` (History), `man zshbuiltins` (`fc`)
- Atuin sync v2 record store — <https://docs.atuin.sh/main/reference/store/>
  (the model we're copying: per-host append-only logs, merge on read)
- kitchen-sync — `~/Projects/kitchen-sync/docs/design.md` (the eventual sync
  transport; Syncthing works until then)

Goal: up-arrow and Ctrl-R on any laptop see commands run on every laptop, in
time order, without a server and without sync conflicts.

## Core design decision

**One history file per host, written only by that host. Merge on read.**

Shell history is a set of immutable timestamped events, so the correct merge is
"union of every host's entries, sorted by time". If each host writes only its
own file, the sync layer never sees concurrent edits to the same file and needs
no merge logic at all. This is Atuin's design expressed as plain files.

Rejected:
- One shared `.zsh_history` synced as text. The file isn't valid UTF-8 (zsh
  metafies non-ASCII bytes with `0x83`), zsh rewrites it wholesale on trim and
  dedupe, and zsh's own lock isn't visible to the sync tool. Any sync layer
  would either lose entries (LWW) or interleave rewrites (text merge).
- Atuin. Needs its own sync server, which breaks the bucket-only/serverless
  goal. Its SQLite DB must not be file-synced.

## Layout

```
~/Sync/zsh-history/
  <host>.hist        # written only by <host>
```

- `HISTFILE=~/Sync/zsh-history/$HOST.hist`. Hostnames are stable per machine
  across reimages, so a reimaged laptop keeps appending to its own file.
- Only `*.hist` is ever read as a peer history. zsh's `*.LOCK` and `*.new`
  (`HIST_SAVE_BY_COPY`) files and sync-tool temp files live alongside and must
  be ignored by both the merge script and the sync layer.
- Migration: on first run, if `$HOST.hist` doesn't exist and the old
  `$XDG_DATA_HOME/.zsh_history` does, copy it in as the seed.

## Merge script: `zsh-history-merge`

Installed at `mkosi/mkosi.extra/usr/bin/zsh-history-merge`.

```
zsh-history-merge [--limit N] DIR > merged
```

- Input: every `DIR/*.hist`.
- Parse `EXTENDED_HISTORY` entries: an entry starts with `: <start>:<elapsed>;`
  and continues across lines ending in a backslash.
- Byte-transparent: run with `LC_ALL=C`, never decode as UTF-8. Only the ASCII
  header is parsed; command bytes are copied verbatim.
- k-way merge by `<start>` (each file is already roughly time-ordered; fall back
  to a full sort if not). Stable on ties.
- Drop exact duplicates (same `<start>` and same command bytes). These appear
  when a host's own file absorbs imported entries (see below).
- Keep the newest `--limit` entries (default `$HISTSIZE`).
- Skip unparseable lines rather than failing, so one corrupt file can't break
  every shell.

Implementation: awk or a short Python script; whichever keeps byte-transparency
simplest.

## zsh config (`ansible/roles/zsh/files/zsh-configs/history.zsh`)

1. Set `HISTDIR`, `HISTFILE=$HISTDIR/$HOST.hist`, run the migration seed.
2. Startup: run `zsh-history-merge "$HISTDIR"` into a temp file and `fc -R` it,
   so the in-memory list is time-sorted across hosts.
3. Live: a `precmd` hook `zstat`s each peer `*.hist` (not our own; `SHARE_HISTORY`
   already handles that) and `fc -RI` any whose mtime changed since last
   prompt. `-I` only adds entries not already in memory; appending them at the
   end is correct because they're newly synced and thus recent.

Keep `EXTENDED_HISTORY`, `INC_APPEND_HISTORY`, `SHARE_HISTORY`. Raise
`HISTSIZE`/`SAVEHIST` (e.g. 100000) so zsh rewrites its file rarely.

## Known issues

- **Imported entries leak into the host's own file.** When zsh trims or
  rewrites `HISTFILE` it writes the whole in-memory list, including peers'
  entries. Harmless for correctness (the merge dedupes) but files grow toward
  `SAVEHIST`. The high `SAVEHIST` makes rewrites rare. Full fix would be
  writing our file ourselves from `zshaddhistory`, which means reimplementing
  zsh's metafied encoding; not worth it unless growth is a real problem.
- **Dedupe options rewrite history.** `HIST_IGNORE_ALL_DUPS` and
  `HIST_SAVE_NO_DUPS` drop older duplicates from the list and the saved file.
  Fine per host; just means a command run on two hosts shows once, at its
  latest time.
- **Not live across machines.** Peer commands appear after the sync layer pulls
  them, at the next prompt.

## Verify before implementing

- zsh reads `HISTFILE` itself after the startup files run. Check whether that
  re-appends our own entries as a block after the merged view and breaks
  ordering. If so, load the merged view from a one-shot first `precmd` hook
  (after zsh's own read), and check whether `HIST_IGNORE_ALL_DUPS` collapses the
  duplicate block during `fc -R`; otherwise use `fc -p` to start from an empty
  list.
- `fc -RI` semantics on peer files across zsh versions (dedupe against the
  in-memory list).
- How often zsh actually rewrites the file with `INC_APPEND_HISTORY` +
  `SHARE_HISTORY` at a large `SAVEHIST`.

## Sync transport

- Now: Syncthing. Add `zsh-history` under `~/Sync`; ignore `*.LOCK`, `*.new` via
  `.stignore`. Single-writer files mean no `.sync-conflict` files.
- Later: kitchen-sync. Requirements this adds are recorded in its
  `docs/design.md` (single-writer paths, upload debounce, ignores).

## Steps

1. Write `zsh-history-merge` + tests on fixture files (multi-line commands,
   metafied bytes, duplicates, corrupt lines).
2. Resolve the "verify" items in a throwaway shell.
3. Update `history.zsh`; ship the merge script in the image.
4. Seed this laptop's file, enable on a second laptop, confirm ordering.
