set -o errexit
set -o nounset

qemu_data_dir="$XDG_DATA_HOME/qemu-arch"
qemu_shared_dir="$qemu_data_dir/shared"

qemu_image_file="$qemu_data_dir/image.qcow2"
qemu_install_iso="$qemu_data_dir/live-usb.iso"
qemu_ovmf_vars_file="$qemu_data_dir/uefi-vars.bin"
qemu_gpg_usb_file="$qemu_data_dir/gpg-usb.img"

# YubiKey 5 OTP+U2F+CCID (1050:0407) — only passed through if plugged in.
# Requires an explicit EHCI controller; q35 usb=on only adds UHCI (USB 1.1).
yubikey_usb_args=()
if find /sys/bus/usb/devices -name 'idVendor' -exec grep -ql '1050' {} \; 2>/dev/null | grep -q .; then
  yubikey_usb_args=(
    "-device" "usb-ehci,id=ehci"
    "-device" "usb-host,bus=ehci.0,vendorid=0x1050,productid=0x0407"
  )
fi

# GPG USB image — only attached if the file exists
gpg_usb_args=()
if [[ -f "$qemu_gpg_usb_file" ]]; then
  gpg_usb_args=("-drive" "file=$qemu_gpg_usb_file,format=raw")
fi

mkdir -p "$qemu_shared_dir"

common_qemu_args=(
  "-virtfs" "local,path=$qemu_shared_dir,mount_tag=host_shared,security_model=mapped-xattr" \
  "-boot" "menu=on" \
  "-chardev" "socket,path=/tmp/qga.sock,server=on,wait=off,id=qga0" \
  "-cpu" "host" \
  "-enable-kvm" \
  "-device" "virtio-rng-pci" \
  "-device" "virtio-serial" \
  "-device" "virtserialport,chardev=qga0,name=org.qemu.guest_agent.0" \
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
