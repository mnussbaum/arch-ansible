# shellcheck shell=bash
# The build context that bin/build-image (and bin/update-system through it)
# builds in and bin/burn-image burns from. Both must resolve it identically, or burn-image looks for images where
# update-system never put them.
#
# Source this BEFORE bin/_cache_common.sh: arch_ansible_select_build_target sets
# the ARCH_ANSIBLE_TARGET/ARCH_ANSIBLE_CACHE that _cache_common.sh derives the
# output dir from.

# Select the build target by what /usr is. Running from one of our images — a
# device or the live medium, whose /usr is the dissected verity image — means
# the device target (caches on /var/cache/arch-ansible, sources from
# /usr/share|lib); anything else is a conventional Arch install, the host target
# (~/.cache, ~/.local).
#
# A live medium's root is tmpfs (RAM), too small for a full rebuild, so the
# caches move to persistent scratch carved from the medium's free space (see
# arch_ansible_scratch). Pass --provision to create that scratch partition when
# it's missing (building); without it an existing one is only mounted
# (reading back a build), so burning never repartitions the medium. A
# provisioned device already has a real root fs, so it stays on /var/cache.
arch_ansible_select_build_target() {
  [[ "$(findmnt -no SOURCE /usr 2>/dev/null || true)" == /dev/mapper/usr ]] || return 0
  export ARCH_ANSIBLE_TARGET=device
  if [[ "$(findmnt -no FSTYPE / 2>/dev/null)" == tmpfs ]]; then
    arch_ansible_scratch "${1:-}"
  fi
}

# Persistent scratch for an offline rebuild on a live medium. Carve a partition
# from the medium's own unallocated space (vm run --runtime-size / burn-image
# grow the medium well past the ~10G image) and point ARCH_ANSIBLE_CACHE at it.
# Reused across runs (and reboots) via the arch-scratch partition label.
# systemd-repart adds the partition via BLKPG, leaving the in-use image
# partitions untouched (no full partition-table re-read). Without --provision a
# missing partition is left alone and the caches stay where they are.
arch_ansible_scratch() {
  local mnt=/run/arch-scratch dev disk part dm defs
  local -a slaves
  dev=/dev/disk/by-partlabel/arch-scratch
  if [[ ! -e "$dev" ]]; then
    [[ "${1:-}" == --provision ]] || return 0
    # Whole disk backing the running verity /usr = the live medium (not the
    # target). Resolve via sysfs: /sys/block/<dm>/slaves/* is populated by the
    # kernel at setup, so it works on the cold first-boot invocation where
    # `dmsetup -o devname` name-resolution can still be empty. -dno PKNAME
    # (--nodeps) reports the partition's own parent disk, not its dm child.
    dm=$(basename "$(readlink -f /dev/mapper/usr)")
    slaves=(/sys/block/"$dm"/slaves/*)
    [[ -e "${slaves[0]}" ]] || { echo "scratch: no backing devices for $dm" >&2; exit 1; }
    part=$(basename "${slaves[0]}")
    disk=$(lsblk -dno PKNAME "/dev/$part")
    [[ -n "$disk" ]] || { echo "scratch: can't find the medium disk" >&2; exit 1; }
    disk="/dev/$disk"
    # systemd-repart (in the image) adds one btrfs partition filling the free
    # space and formats it, updating the kernel partition table in place (BLKPG)
    # so the in-use image partitions aren't disturbed. An isolated ephemeral
    # definitions dir keeps the image's own repart.d out of it; --dry-run=no
    # applies (repart defaults to dry-run). It never deletes partitions, so
    # passing only this definition leaves the existing layout alone.
    defs=$(mktemp -d)
    cat >"$defs/70-arch-scratch.conf" <<'EOF'
[Partition]
Type=linux-generic
Label=arch-scratch
Format=btrfs
EOF
    sudo systemd-repart --definitions="$defs" --dry-run=no --seed=random "$disk" >/dev/null
    rm -rf "$defs"
    sudo udevadm settle
    [[ -e "$dev" ]] || { echo "scratch: partition not created on $disk" >&2; exit 1; }
  fi
  sudo mkdir -p "$mnt"
  mountpoint -q "$mnt" || sudo mount "$dev" "$mnt"
  sudo chown "$(id -u):$(id -g)" "$mnt"
  export ARCH_ANSIBLE_CACHE="$mnt/cache"
  mkdir -p "$ARCH_ANSIBLE_CACHE"
}

# Default ARCH_ANSIBLE_ORGANIZATIONS to the running image's organizations
# (recorded in os-release by the organizations role), unless the caller set it
# (even to empty, meaning none). On a live medium that is the medium's set, not
# necessarily an --image target's. Callers skip this when --organization was
# given.
arch_ansible_default_organizations() {
  [[ -z "${ARCH_ANSIBLE_ORGANIZATIONS+set}" ]] || return 0
  ARCH_ANSIBLE_ORGANIZATIONS=$(. /usr/lib/os-release; echo "${ARCH_ANSIBLE_ORGANIZATIONS:-}")
  export ARCH_ANSIBLE_ORGANIZATIONS
  echo "Organizations: ${ARCH_ANSIBLE_ORGANIZATIONS:-none}" >&2
}

# Prime a device build's caches from what the running image ships, so a rebuild
# runs offline. Call after bin/_cache_common.sh and arch_ansible_ensure_cache.
arch_ansible_seed_device_build() {
  # Seed the package cache baked into /usr (mkosi/mkosi.conf ExtraTree) so the rebuild
  # installs offline instead of re-downloading ~1G. cp -n leaves a primed cache
  # (reused scratch) alone.
  local pkg_dst="$ARCH_ANSIBLE_CACHE/mkosi/pacman-pkg/cache/pacman/pkg"
  if [[ -d /usr/lib/arch-ansible/pkg-cache ]]; then
    mkdir -p "$pkg_dst"
    cp -rn /usr/lib/arch-ansible/pkg-cache/. "$pkg_dst/" 2>/dev/null || true
  fi

  # Same for the local AUR repo baked into /usr (mkosi/mkosi.conf ExtraTree): seed it into
  # the build's aur-repo cache, which is what mkosi installs the AUR packages from
  # (PackageDirectories= in mkosi/mkosi.conf) — no rebuild or network needed for them. cp -n
  # leaves a primed cache (reused scratch) alone.
  local aur_dst="$ARCH_ANSIBLE_CACHE/aur-repo"
  if [[ -d /usr/lib/arch-ansible/aur-repo ]]; then
    mkdir -p "$aur_dst"
    cp -rn /usr/lib/arch-ansible/aur-repo/. "$aur_dst/" 2>/dev/null || true
  fi

  # The .chroot postinst's pacman needs a sync DB, and a device has no system one
  # (and /var doesn't persist). Seed a persistent copy that 10-sources-device.conf
  # feeds into the image. Only fetch it when missing; once primed, builds reuse it
  # offline. Root: pacman -Sy refuses to run unprivileged even with a custom
  # --dbpath. DBs are SigLevel DatabaseOptional, so this needs no keyring. No
  # `|| true`: if it's missing and the sync fails, the build can't proceed.
  local pacman_db="$ARCH_ANSIBLE_CACHE/arch-ansible/pacman-db"
  if [[ ! -f "$pacman_db/sync/core.db" ]]; then
    mkdir -p "$pacman_db"
    sudo pacman -Sy --dbpath "$pacman_db" --logfile /dev/null
  fi
}
