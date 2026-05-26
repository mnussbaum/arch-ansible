set -o errexit
set -o nounset

qemu_image_dir=mkosi.images/qemu
qemu_shared_dir="$qemu_image_dir/shared"
qemu_output_dir=~/.cache/mkosi/images/qemu

mkdir -p "$qemu_shared_dir"

