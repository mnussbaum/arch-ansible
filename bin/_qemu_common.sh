set -o errexit
set -o nounset

images_dir="$XDG_DATA_HOME/arch-images"
qemu_shared_dir="$images_dir/shared"

usi_image_file="$images_dir/usi.raw"
qemu_image_file="$images_dir/qemu.raw"
qemu_gpg_usb_file="$images_dir/gpg-usb.img"

mkdir -p "$qemu_shared_dir"

# Forwards the host pcscd socket into the VM over vsock so the guest's
# scdaemon (and thus gpg-agent + SSH auth) can reach the YubiKey without
# USB passthrough. Requires the vhost_vsock kernel module on the host.
_pcscd_vsock_relay_pid=""

start_pcscd_vsock_relay() {
  local pcscd_sock=/run/pcscd/pcscd.comm
  if [[ -S "$pcscd_sock" ]]; then
    socat VSOCK-LISTEN:62001,fork,reuseaddr "UNIX-CONNECT:$pcscd_sock" &
    _pcscd_vsock_relay_pid=$!
  fi
}

stop_pcscd_vsock_relay() {
  if [[ -n "$_pcscd_vsock_relay_pid" ]]; then
    kill "$_pcscd_vsock_relay_pid" 2>/dev/null || true
    _pcscd_vsock_relay_pid=""
  fi
}
