# shellcheck shell=bash
# Resolve ARCH_ANSIBLE_CACHE: the base directory for every build cache and all
# mkosi scratch (workspace, incremental cache, package cache, build dir, output,
# the sccache/cargo/pacman caches, the AUR repo and build chroot, and the homed
# credstore).
#
# Defaults to /var/cache/arch-ansible on the encrypted root btrfs. Keeps the
# build off the small homed /home partition (a full build's transient footprint
# — e.g. systemd-repart's ~5G /usr copy to size the erofs slot — overflows it)
# and makes the whole local-rebuild pipeline root-resident, alongside the update
# staging dir /var/lib/arch-ansible/updates. See docs/bootstrapping.md
# "Partition layout" and "Updates".
#
# mkosi expands ${ARCH_ANSIBLE_CACHE} in mkosi/mkosi.conf from the process environment,
# so every script that invokes mkosi sources this and the export carries through.
# Finalize scripts don't inherit the process env, so build paths that mkosi/mkosi.finalize
# writes back to are passed in explicitly via `mkosi --environment=`.
#
# Override by exporting ARCH_ANSIBLE_CACHE before invoking.

: "${ARCH_ANSIBLE_CACHE:=/var/cache/arch-ansible}"
export ARCH_ANSIBLE_CACHE

# mkosi's output dir, derived from the base. Both build-image (writes it) and
# update-system (reads the staged artifacts back out) need the same value.
export ARCH_ANSIBLE_OUTPUT_DIR="$ARCH_ANSIBLE_CACHE/mkosi/images/image"

# A tracked-files-only copy of the repo for ExtraTrees to ship into
# /usr/share/arch-ansible. mkosi has no exclude for ExtraTrees, so copying the
# repo directly would sweep gitignored content (secrets/, .qemu-host-shared/,
# the signing key) into the plaintext /usr.
export ARCH_ANSIBLE_SRCTREE="$ARCH_ANSIBLE_CACHE/mkosi-srctree"

# The password-store the build reads and the image ships at
# /usr/share/password-store (mkosi/mkosi.conf): the user's own, so new entries
# reach the next image. A live medium boots a fresh tmpfs $HOME with none, so it
# falls back to the one the running image ships.
if [[ -z "${ARCH_ANSIBLE_PASSWORD_STORE:-}" ]]; then
  ARCH_ANSIBLE_PASSWORD_STORE="${PASSWORD_STORE_DIR:-$HOME/.local/share/password-store}"
  [[ -d "$ARCH_ANSIBLE_PASSWORD_STORE" ]] || ARCH_ANSIBLE_PASSWORD_STORE=/usr/share/password-store
fi
export ARCH_ANSIBLE_PASSWORD_STORE

# Ensure the base exists and is writable by the build user. /var/cache is
# root-owned, so escalate once to create a user-owned subtree; an override the
# user can already write to needs no sudo.
arch_ansible_ensure_cache() {
  [[ -d "$ARCH_ANSIBLE_CACHE" && -w "$ARCH_ANSIBLE_CACHE" ]] && return 0
  if [[ -w "$(dirname "$ARCH_ANSIBLE_CACHE")" ]]; then
    mkdir -p "$ARCH_ANSIBLE_CACHE"
  else
    sudo install -d -o "$USER" "$ARCH_ANSIBLE_CACHE"
  fi
}

# Rebuild ARCH_ANSIBLE_SRCTREE from the current git-tracked files (working-tree
# content, ignored/untracked files excluded), then bolt on a shallow .git so the
# shipped /usr/share/arch-ansible is a cloneable repo. ansible/roles/user/tasks/
# first-login.yml clones it offline into the VM home and repoints origin at
# GitHub. Only committed objects land in .git — gitignored secrets (secrets/,
# the signing key, .qemu-host-shared/) are never committed, so they stay out of
# the plaintext /usr; the working tree still ships tracked files only. Shallow
# (--depth=1) keeps the history out of /usr. Run from the repo root.
arch_ansible_stage_srctree() {
  rm -rf "$ARCH_ANSIBLE_SRCTREE"
  mkdir -p "$ARCH_ANSIBLE_SRCTREE"
  git ls-files -z | rsync --from0 --files-from=- -a ./ "$ARCH_ANSIBLE_SRCTREE/"

  local branch tmp
  branch="$(git rev-parse --abbrev-ref HEAD)"
  tmp="$(mktemp -d)"
  # file:// (not a plain path) so --depth=1 is honored instead of a hardlink
  # clone that drags in the full object store.
  git clone --quiet --bare --depth=1 --branch "$branch" "file://$PWD" "$tmp/git"
  mv "$tmp/git" "$ARCH_ANSIBLE_SRCTREE/.git"
  rm -rf "$tmp"
  # Turn the bare clone into a normal checkout over the rsynced working tree:
  # core.bare=false gives it a worktree (its parent dir), and `reset` loads the
  # index from HEAD without touching the files (so `git status` shows only real
  # uncommitted drift, clean when built from the branch tip).
  git -C "$ARCH_ANSIBLE_SRCTREE" config core.bare false
  git -C "$ARCH_ANSIBLE_SRCTREE" reset --quiet
}
