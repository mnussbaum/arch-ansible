set -o errexit
set -o nounset

qemu_data_dir="$XDG_DATA_HOME/qemu-arch"

qemu_image_file="$qemu_data_dir/image.qcow2"
qemu_install_iso="$qemu_data_dir/live-usb.iso"
qemu_ovmf_vars_file="$qemu_data_dir/uefi-vars.bin"

common_qemu_args=(
  "-bios" "/usr/share/qemu/bios.bin" \
  "-boot" "menu=on" \
  "-chardev" "socket,path=/tmp/qga.sock,server,nowait,id=qga0" \
  "-cpu" "host" \
  "-enable-kvm" \
  "-device" "virtio-rng-pci" \
  "-device" "virtio-serial" \
  "-device" "virtserialport,chardev=qga0,name=org.qemu.guest_agent.0" \
  "-display" "sdl,gl=on" \
  "-drive" "if=pflash,format=raw,readonly,file=/usr/share/ovmf/x64/OVMF_CODE.fd" \
  "-drive" "if=pflash,format=raw,file=$qemu_ovmf_vars_file" \
  "-global" "ICH9-LPC.disable_s3=1" \
  "-m" "4096" \
  "-machine" "type=q35,smm=on,accel=kvm,usb=on" \
  "-monitor" "none" \
  "-name" "archiso,process=archiso_0" \
  "-nic" "user,model=virtio-net-pci" \
  "-parallel" "none" \
  "-serial" "stdio" \
  "-smp" "4,sockets=1,cores=4,threads=1" \
  "-vga" "virtio"
)
