# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "/Users/mnussbaum/src/atlas-archlinux/packer_outdir/packed/archlinux-virtualbox.box"
  # config.vm.synced_folder "../data", "/vagrant_data"

  config.vm.provider "virtualbox" do |vb|
    # vb.gui = true

    vb.memory = "4096"
  end

  config.vm.provision "shell", inline: "rm /dev/random"
  config.vm.provision "shell", inline: "ln -s /dev/urandom /dev/random"

  config.vm.provision "shell", inline: "sed -i '1iServer = https://mirrors.ocf.berkeley.edu/archlinux/$repo/os/$arch' /etc/pacman.d/mirrorlist"

  config.vm.provision "shell", inline: "rm -R /etc/pacman.d/gnupg || /bin/true"
  config.vm.provision "shell", inline: "rm -R /root/.gnupg/ || /bin/true"
  config.vm.provision "shell", inline: "mkdir /root/.gnupg/"
  config.vm.provision "shell", inline: "touch /root/.gnupg/dirmngr_ldapservers.conf"
  config.vm.provision "shell", inline: "dirmngr </dev/null"
  config.vm.provision "shell", inline: "pacman-key --init"
  config.vm.provision "shell", inline: "pacman-key --populate archlinux"
  config.vm.provision "shell", inline: "pacman-key --refresh-keys"

  config.vm.provision "shell", inline: "rm -f /var/lib/pacman/db.lck || /bin/true"

  config.vm.provision "shell", inline: "pacman -Scc --noconfirm"
  config.vm.provision "shell", inline: "pacman -Syyu --noconfirm"
  config.vm.provision "shell", inline: "pacman -Syu --noconfirm ansible python"

  config.vm.provision "ansible" do |ansible|
    ansible.raw_arguments  = [
      "-e ssd_drive=/dev/sda2",
    ]
    ansible.verbose = "v"
    ansible.playbook = "playbook.yml"
  end
end
