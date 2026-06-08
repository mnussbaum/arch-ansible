# shellcheck shell=bash
# Resolve ARCH_ANSIBLE_CACHE: the base directory for every build cache and all
# mkosi scratch (workspace, incremental cache, package cache, build dir, output,
# the sccache/cargo/yay/pacman caches, and the homed credstore).
#
# Keyed off ARCH_ANSIBLE_TARGET, the same transitional switch that selects
# mkosi.conf.d/10-sources-{host,device}.conf:
#
#   host   (transitional builder): ~/.cache — the interactive user's cache,
#          optionally a dedicated 60G btrfs volume (bin/setup-mkosi-cache-volume).
#   device (in-image, the steady state): /var/cache/arch-ansible on the encrypted
#          root btrfs. Keeps the build off the small homed /home partition (a full
#          build's transient footprint — e.g. systemd-repart's ~5G /usr copy to
#          size the erofs slot — overflows it) and makes the whole local-rebuild
#          pipeline root-resident, alongside the update staging dir
#          /var/lib/arch-ansible/updates. See plan-usr-hermetic.md "Target
#          partition layout" + Stage D.
#
# mkosi expands ${ARCH_ANSIBLE_CACHE} in mkosi.conf from the process environment,
# so every script that invokes mkosi sources this and the export carries through.
# Finalize scripts don't inherit the process env, so build paths that mkosi.finalize
# writes back to are passed in explicitly via `mkosi --environment=`.
#
# Override by exporting ARCH_ANSIBLE_CACHE before invoking.

if [[ -z "${ARCH_ANSIBLE_CACHE:-}" ]]; then
  if [[ "${ARCH_ANSIBLE_TARGET:-host}" == device ]]; then
    ARCH_ANSIBLE_CACHE=/var/cache/arch-ansible
  else
    ARCH_ANSIBLE_CACHE="$HOME/.cache"
  fi
fi
export ARCH_ANSIBLE_CACHE

# mkosi's output dir, derived from the base. Both build-image (writes it) and
# update-system (reads the staged artifacts back out) need the same value.
export ARCH_ANSIBLE_OUTPUT_DIR="$ARCH_ANSIBLE_CACHE/mkosi/images/image"

# A tracked-files-only copy of the repo for ExtraTrees to ship into
# /usr/share/arch-ansible. mkosi has no exclude for ExtraTrees, so copying the
# repo directly would sweep gitignored content (secrets/, .qemu-host-shared/,
# the signing key) into the plaintext /usr.
export ARCH_ANSIBLE_SRCTREE="$ARCH_ANSIBLE_CACHE/mkosi-srctree"

# Ensure the base exists and is writable by the build user. On a device
# /var/cache is root-owned, so escalate once to create a user-owned subtree;
# on the host ~/.cache is already ours and no sudo is needed.
arch_ansible_ensure_cache() {
  [[ -d "$ARCH_ANSIBLE_CACHE" && -w "$ARCH_ANSIBLE_CACHE" ]] && return 0
  if [[ -w "$(dirname "$ARCH_ANSIBLE_CACHE")" ]]; then
    mkdir -p "$ARCH_ANSIBLE_CACHE"
  else
    sudo install -d -o "$USER" "$ARCH_ANSIBLE_CACHE"
  fi
}

# Rebuild ARCH_ANSIBLE_SRCTREE from the current git-tracked files (working-tree
# content, ignored/untracked files excluded). Run from the repo root.
arch_ansible_stage_srctree() {
  rm -rf "$ARCH_ANSIBLE_SRCTREE"
  mkdir -p "$ARCH_ANSIBLE_SRCTREE"
  git ls-files -z | rsync --from0 --files-from=- -a ./ "$ARCH_ANSIBLE_SRCTREE/"
}
