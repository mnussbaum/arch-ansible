common_qemu_args=(
  "-drive" "if=pflash,format=raw,readonly,file=/usr/share/ovmf/x64/OVMF_CODE.fd" \
  "-drive" "if=pflash,format=raw,file=/tmp/qemu-arch-uefi-vars.bin" \
  "-m" "2048" \
  "-enable-kvm" \
  "-M" "q35" \
  "-cpu" "host" \
  "-smp" "4,sockets=1,cores=4,threads=1" \
  "-bios" "/usr/share/qemu/bios.bin" \
  "-boot" "menu=on" \
)
