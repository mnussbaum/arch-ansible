# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "archlinux/archlinux"
  config.vm.hostname = "vagrant"

  config.vm.provider "virtualbox" do |vb|
    vb.memory = 10240
    vb.cpus = 4
  end
  config.disksize.size = "80GB"

  config.vm.provision "shell", inline: <<-EOF
pacman -Syu --noconfirm --needed wpa_supplicant ansible python python-passlib
mkdir -p ~/.ssh
mkdir -p ~/.gnupg
chmod 600 ~/.gnupg
EOF

  config.vm.provision :file, source: "~/.ssh/id_rsa", destination: "~/.ssh/id_rsa"
  config.vm.provision :file, source: "~/.ssh/id_rsa.pub", destination: "~/.ssh/id_rsa.pub"
  config.vm.provision :shell, inline: "chmod 600 ~/.ssh/id_rsa", privileged: false
  config.vm.provision :shell, inline: "chmod 600 ~/.ssh/id_rsa.pub", privileged: false

  # config.vm.provision "shell", inline: "cd /vagrant && ./provision-vagrant", privileged: true
end
