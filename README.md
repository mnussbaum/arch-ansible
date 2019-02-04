This repo sets up my Arch Linux based workstation. More info to come.

## Display stack

This project runs both on a phyiscal laptop and in VirtualBox. Unfortunately
Sway doesn't run in VirtualBox so I switch between Sway/Wayland and i3/Xorg.
Sway and i3 share most of a templated config file so it could be worse.

In both cases the display server is run as a systemd user service. This makes
it easy to monitor for failures, find logs and switch between display servers.
I use a templated shell [`~/.profile`](templates/profile.j2) to import the
user's environment for all systemd user services and start one of the display
sessions.

Xorg and Sway both have slightly different timing issues that make systemd
service dependencies tricky. Xorg's first issue is that it takes ~2sec after it
starts listening on its socket before it can actually handle requests. After
Xorg starts it should be configured with xrdb before any other applications
start.

Services that want to interact with Sway, on the other hand, need access to a
`SWAYSOCK` env var that is only set for processes started by Sway itself. To
make this env var available to services like Waybar and Redshift I use an
`exec` in my Sway config to import the env var for all systemd user services.

Both of the display servers's timing issues mean that dependent services will
start before they can succeed. For long running services that's fine, they can
just retry until they work. But oneshot type services that are supposed to run
to completion aren't restartable by systemd, so they will fail and never rerun
by default. To avoid this issue I include a [graphical-session-delay
service](files/graphical-session-delay.service) that sleeps for 2sec. It
depends on the display server service and blocks the rest of my display server
interacting services from starting until it's complete.

Here's the ordered list of systemd services across the two stacks:

| Purpose                                          | X11                                 | Wayland                             |
| ------------------------------------------------ | ----------------------------------- | ----------------------------------- |
| Invoked by systemd on graphical user login       | graphical-session.target            | graphical-session.target            |
| Group all display manager services               | [x11-session.target][]              | [wayland-session.target][]          |
| Run compositor                                   | [xorg.service][]                    | [sway.service][]                    |
| Import `SWAYSOCK` into systemd user services     |                                     | An `exec`d systemctl in sway config |
| Give compositor chance to be actually ready      | [graphical-session-delay.service][] | [graphical-session-delay.service][] |
| Configure Xorg                                   | [xrdb.service][]                    | [xrdb.service][]                    |
| Indicate we're ready to start graphical services | [graphical-session-ready.target][]  | [graphical-session-ready.target][]  |
| Start graphical services                         | [i3][], [feh][], [redshift][]...    | [waybar][], [redshift][]...         |

[feh]: files/wallpaper.service
[graphical-session-delay.service]: files/graphical-session-delay.service
[graphical-session-ready.target]: files/graphical-session-ready.target
[i3]: files/i3.service
[redshift]: files/redshift.service
[sway.service]: files/sway.service
[waybar]: files/waybar.service
[wayland-session.target]: files/wayland-session.target
[x11-session.target]: files/x11-session.target
[xorg.service]: templates/xorg.service.j2
[xrdb.service]: files/xrdb.service
