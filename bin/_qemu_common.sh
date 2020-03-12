set -o errexit
set -o nounset

qemu_data_dir="$XDG_DATA_HOME/qemu-arch"

qemu_image_file="$qemu_data_dir/image.qcow2"
qemu_install_iso="$qemu_data_dir/live-usb.iso"
qemu_ovmf_vars_file="$qemu_data_dir/uefi-vars.bin"

common_qemu_args=(
  "-drive" "if=pflash,format=raw,readonly,file=/usr/share/ovmf/x64/OVMF_CODE.fd" \
  "-drive" "if=pflash,format=raw,file=$qemu_ovmf_vars_file" \
  "-m" "4096" \
  "-enable-kvm" \
  "-M" "q35" \
  "-cpu" "host" \
  "-smp" "4,sockets=1,cores=4,threads=1" \
  "-bios" "/usr/share/qemu/bios.bin" \
  "-boot" "menu=on" \
)
