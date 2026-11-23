# shellcheck shell=bash
set -o errexit
set -o nounset
set -o pipefail

# Building the image in a container, on any Linux or macOS computer with podman
# or docker: bin/build-image --container. See docs/build-recovery-usb.md.

DR_IMAGE=arch-ansible-dr
DR_VOLUME=arch-ansible-dr-cache

# Sets CONTAINER_RT to the container runtime command. Rootful: mkosi and
# cryptsetup need a real --privileged.
container_runtime() {
  if command -v podman >/dev/null; then
    CONTAINER_RT=(podman)
    if [[ $(uname -s) == Darwin ]]; then
      local rootful
      rootful=$(podman machine inspect --format '{{.Rootful}}' 2>/dev/null | head -1) || {
        echo "Error: no podman machine; see docs/set-up-recovery-computer.md" >&2
        exit 1
      }
      if [[ $rootful != true ]]; then
        echo "Error: the podman machine must be rootful:" >&2
        echo "  podman machine stop; podman machine set --rootful; podman machine start" >&2
        exit 1
      fi
    elif [[ $(id -u) -ne 0 ]]; then
      CONTAINER_RT=(sudo podman)
    fi
  elif command -v docker >/dev/null; then
    CONTAINER_RT=(docker)
    if [[ $(uname -s) == Linux ]] && ! docker info >/dev/null 2>&1; then
      CONTAINER_RT=(sudo docker)
    fi
  else
    echo "Error: install podman or docker first; see docs/set-up-recovery-computer.md" >&2
    exit 1
  fi

  if ! "${CONTAINER_RT[@]}" info >/dev/null 2>&1; then
    echo "Error: '${CONTAINER_RT[*]} info' fails; is the runtime (or its VM) running?" >&2
    exit 1
  fi
}

container_build_usage() {
  echo "Usage: bin/build-image --container [--ephemeral-key]" >&2
  echo "          [--password-store DIR | --password-store-url URL] [--out DIR]" >&2
  echo "          [-- build-image options...]" >&2
  echo "  --ephemeral-key       No YubiKey: sign with a throwaway key and ask for a new" >&2
  echo "                        home password. Boot it with Secure Boot off." >&2
  echo "  --password-store      Use this password-store instead of cloning it." >&2
  echo "  --password-store-url  Clone it from here (default: GitLab over SSH via the YubiKey;" >&2
  echo "                        with --ephemeral-key, no password-store unless given)." >&2
  echo "  --out                 Where the image lands, replacing older ones there" >&2
  echo "                        (default: dr-out/ in the checkout)." >&2
  echo "  Builds the committed state of this checkout. Caches persist in the" >&2
  echo "  '$DR_VOLUME' volume; remove it to reclaim the space." >&2
}

# Builds the image in container/Containerfile and leaves it in --out. The
# YubiKey decrypts the build secrets here, on the host, so the container needs
# no USB access (which macOS runtimes can't give it).
container_build() {
  local ephemeral="" store_dir="" store_url="" out=""
  local build_args=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --ephemeral-key) ephemeral=1 ;;
      --password-store) store_dir=$2; shift ;;
      --password-store-url) store_url=$2; shift ;;
      --out) out=$2; shift ;;
      -h|--help) container_build_usage; exit ;;
      --) shift; build_args=("$@"); break ;;
      *) echo "Unexpected argument: $1" >&2; container_build_usage; exit 1 ;;
    esac
    shift
  done

  # Paths given relative to where it was run, then everything from the checkout.
  if [[ -n $out ]]; then mkdir -p "$out"; out=$(cd "$out" && pwd); fi
  if [[ -n $store_dir ]]; then store_dir=$(cd "$store_dir" && pwd); fi
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  local repo=$PWD
  if [[ -z $out ]]; then out=$repo/dr-out; mkdir -p "$out"; fi

  container_runtime

  local mem
  if [[ ${CONTAINER_RT[0]} == docker || ${CONTAINER_RT[1]:-} == docker ]]; then
    mem=$("${CONTAINER_RT[@]}" info --format '{{.MemTotal}}')
  else
    mem=$("${CONTAINER_RT[@]}" info --format '{{.Host.MemTotal}}')
  fi
  if [[ ${mem:-0} -lt 8000000000 ]]; then
    echo "Warning: the runtime has $((mem / 1000000000))G of memory; give it 8G+" >&2
  fi

  local run=("${CONTAINER_RT[@]}" run --rm --interactive --tty --privileged --platform linux/amd64
    --shm-size 2g
    --volume "$repo:/host-repo:ro"
    --volume "$DR_VOLUME:/home/builder/.cache"
    --volume "$out:/out")
  if [[ -n $store_dir ]]; then run+=(--volume "$store_dir:/host-password-store:ro"); fi
  if [[ -n $store_url ]]; then run+=(--env "DR_PASSWORD_STORE_URL=$store_url"); fi

  if [[ -n $ephemeral ]]; then
    run+=(--env DR_MODE=ephemeral)
  else
    # gpg reaches the YubiKey through pcscd (scdaemon.conf: disable-ccid).
    if [[ $(uname -s) == Linux ]] && ! pgrep -x pcscd >/dev/null \
        && ! systemctl is-active --quiet pcscd.socket 2>/dev/null; then
      echo "Error: pcscd isn't running; start it with:" >&2
      echo "  sudo systemctl enable --now pcscd.socket" >&2
      exit 1
    fi
    # Under $HOME, which every macOS runtime shares into its VM; deleted on exit.
    DR_SECRETS=$(mktemp -d "$HOME/.dr-secrets.XXXXXX")
    trap 'rm -rf "$DR_SECRETS"' EXIT
    local unlock_args=(--repo "$repo" --out "$DR_SECRETS")
    if [[ -n $store_dir ]]; then unlock_args+=(--password-store "$store_dir"); fi
    if [[ -n $store_url ]]; then unlock_args+=(--password-store-url "$store_url"); fi
    container/dr-unlock "${unlock_args[@]}"
    run+=(--env DR_MODE=provided --volume "$DR_SECRETS:/host-secrets:ro")
  fi

  echo "==> Building the builder container" >&2
  "${CONTAINER_RT[@]}" build --platform linux/amd64 --tag "$DR_IMAGE" \
    --file container/Containerfile .

  echo "==> Building the image (a cold build can take a while)" >&2
  "${run[@]}" "$DR_IMAGE" ${build_args[@]+"${build_args[@]}"}

  echo "Built:" >&2
  # shellcheck disable=SC2012 # image names are plain image_<version>_<arch>.raw
  ls -1t "$out"/image_*.raw | head -1 >&2
  echo "Write it to a USB drive with: bin/burn-image <image> <device>" >&2
}
