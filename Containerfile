FROM archlinux:latest

RUN pacman -Syu --noconfirm \
 && pacman -S --noconfirm \
      mkosi \
      ansible \
      python \
      python-pefile \
      python-pystache \
      python-yaml \
 && pacman -Scc --noconfirm

WORKDIR /work/src

# Bind-mount the repo (including secrets/vault-password) at /work/src:
#   podman build -t arch-ansible-builder .
#   podman run --privileged -v .:/work/src arch-ansible-builder [output]
ENTRYPOINT ["/bin/bash"]
CMD ["bin/build-live-image"]
