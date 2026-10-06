# shellcheck shell=bash
# Which organizations (bin/build-image --organization) each built image has.
#
# build-image records them in $ARCH_ANSIBLE_OUTPUT_DIR/image_<version>_organizations,
# beside mkosi's own artifacts, whose names systemd-sysupdate matches and so
# can't carry them. An image without the record (built before it existed) has
# none. Sets compare sorted, so `--organization a --organization b` and
# `--organization b --organization a` are the same image.

# Normalize a comma-separated organization list: sorted, deduplicated.
arch_ansible_normalize_organizations() {
  tr ',' '\n' <<< "$1" | sed '/^$/d' | sort -u | paste -sd,
}

# The organizations recorded for an image version.
arch_ansible_image_organizations() {
  local record="$ARCH_ANSIBLE_OUTPUT_DIR/image_${1}_organizations"
  [[ -f "$record" ]] && cat "$record"
  return 0
}

# Every built image version, newest first.
arch_ansible_image_versions() {
  find "$ARCH_ANSIBLE_OUTPUT_DIR" -maxdepth 1 -name 'image_*' -printf '%f\n' 2>/dev/null \
    | sed -n 's/^image_\([0-9]\{1,\}\)_.*/\1/p' \
    | sort -rnu
}

# The newest image version built for exactly these organizations ("" for none).
arch_ansible_latest_image_version() {
  local want version
  want=$(arch_ansible_normalize_organizations "$1")
  while read -r version; do
    # Only versions whose disk image survived (not just a stray record).
    compgen -G "$ARCH_ANSIBLE_OUTPUT_DIR/image_${version}_*.raw" >/dev/null || continue
    if [[ "$(arch_ansible_image_organizations "$version")" == "$want" ]]; then
      echo "$version"
      return 0
    fi
  done < <(arch_ansible_image_versions)
  echo "error: no image built for organizations '${want:-none}' in $ARCH_ANSIBLE_OUTPUT_DIR;" \
    "run bin/build-image${want:+ --organization ${want//,/ --organization }}" >&2
  return 1
}
