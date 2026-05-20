set -o errexit
set -o nounset

qemu_data_dir="$XDG_DATA_HOME/qemu-arch"
qemu_shared_dir="$qemu_data_dir/shared"

qemu_image_file="$qemu_data_dir/image.qcow2"
qemu_install_iso="$qemu_data_dir/live-usb.iso"
qemu_ovmf_vars_file="$qemu_data_dir/uefi-vars.bin"
qemu_gpg_usb_file="$qemu_data_dir/gpg-usb.img"

# GPG USB image — only attached if the file exists
gpg_usb_args=()
if [[ -f "$qemu_gpg_usb_file" ]]; then
  gpg_usb_args=("-drive" "file=$qemu_gpg_usb_file,format=raw")
fi

system_disk_args=(
  "-device" "virtio-scsi-pci,id=scsi0"
  "-drive" "if=none,id=hd0,file=$qemu_image_file,format=qcow2"
  "-device" "scsi-hd,bus=scsi0.0,drive=hd0"
)

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

common_qemu_args=(
  "-virtfs" "local,path=$qemu_shared_dir,mount_tag=host_shared,security_model=mapped-xattr" \
  "-boot" "menu=on" \
  "-chardev" "socket,path=/tmp/qga.sock,server=on,wait=off,id=qga0" \
  "-cpu" "host" \
  "-enable-kvm" \
  "-device" "virtio-rng-pci" \
  "-device" "virtio-serial" \
  "-device" "virtserialport,chardev=qga0,name=org.qemu.guest_agent.0" \
  "-device" "vhost-vsock-pci,guest-cid=3" \
  "-nic" "user,model=virtio-net-pci" \
  "-display" "sdl,gl=on" \
  "-drive" "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd" \
  "-drive" "if=pflash,format=raw,file=$qemu_ovmf_vars_file" \
  "-global" "ICH9-LPC.disable_s3=1" \
  "-m" "4096" \
  "-machine" "type=q35,accel=kvm,usb=on" \
  "-monitor" "none" \
  "-name" "archiso,process=archiso_0" \
  "-parallel" "none" \
  "-serial" "stdio" \
  "-smp" "4,sockets=1,cores=4,threads=1" \
  "-vga" "virtio"
)
