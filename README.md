This repo sets up my Arch Linux based workstation. More info to come.

## Graphical session

This project runs both on a physical laptop and in VirtualBox. Unfortunately
sway doesn't run in VirtualBox so I switch between sway/Wayland and i3/Xorg.
sway and i3 share most of a config file that's [templated
here](templates/sway_and_i3_config.j2) so it could be worse.

In both cases the display server is run as a systemd user service. This makes
it easy to monitor for failures, find logs and switch between display servers.
I use a templated shell [`~/.profile`](templates/profile.j2) to import the
user's environment for all systemd user services and start one of the window
manager services either [i3.service][] or [sway.service][].

The i3 service depends on [xorg.service][] so Xorg starts whenever i3 does.
The xrdb service runs as part of
[graphical-session-pre.target](https://www.freedesktop.org/software/systemd/man/systemd.special.html#graphical-session-pre.target)
with both i3 and sway to configure Xorg and XWayland respectively. Xrdb retries
until the Xorg server is up and Xrdb succeeds. After xrdb completes
the graphical-session-pre target is reached.

Meanwhile the window manager has been starting up and it eventually executes
its config file, the last line of which starts thw window manager session, one
of [i3-session.target][] or [sway-session.target][]. The window manager session
binds to
[graphical-session.target](https://www.freedesktop.org/software/systemd/man/systemd.special.html#graphical-session.target)
, so both targets are reached at the same time. All remaining graphical
services are part of either the graphical-session target or a specific window
manager target. Some example graphical services like this are [feh.service][]
[swayidle.service][] and [waybar.service][].

[feh.service]: files/feh.service
[i3.service]: files/i3.service
[i3-session.target]: files/i3-session.target
[swayidle.service]: files/swayidle.service
[sway.service]: files/sway.service
[sway-session.target]: files/sway-session.target
[waybar.service]: files/waybar.service
[xorg.service]: templates/xorg.service.j2
[xrdb.service]: files/xrdb.service

## Bootstrapping

1. Create a `secrets/luks-keyfile` file containing a password for encrpyting
   the new disk
2. Create a `secrets/wifi-passphrase` file containing the wifi password
3. Build ISO - `./bin/build-<qemu-image|live-usb>`
4. Boot into ISO

- For XPS go into BIOS menu to boot from USB
- For QEMU this will happen automatically after the image is built

1. `cd arch-ansible`
1. `./bin/bootstrap-<qemu|xps>`
1. Reboot into the newly provisioned disk

- If XPS - `shutdown -r now`
- If QEMU - `shutdown now` - `./bin/run-qemu`

1. `cd ~/src/arch-ansible`
1. `gpg --import ~/gpg-keys/*`
1. `rm -rf ~/gpg-keys`
1. Run ansible to provision to the point of secret setups - `./bin/ansible`
1. Restart to bring up systemd services and GUI `shutdown -r now`
1. Add GPG key to the agent - `ssh-add`
1. `cd ~/src/arch-ansible`
1. Finish provisioning - `./bin/ansible`
