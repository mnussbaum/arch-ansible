# Plan: Dynamic light/dark colorscheme on the immutable image

References:
- darkman — <https://gitlab.com/WhyNotHugo/darkman> (sunrise/sunset trigger +
  `{light,dark}-mode.d/` hook runner; also a `org.freedesktop.impl.portal.Settings`
  backend, but see note below on why that's secondary for us)
- Pywalfox — <https://github.com/Frewacom/pywalfox> (Firefox/Thunderbird live
  theming via the WebExtension Theme API + a native-messaging host)
- base16 sources we already use: `github.com/mnussbaum/base16-schemes-source`,
  `github.com/mnussbaum/base16-templates-source`

Goal: keep our two-scheme light/dark colorscheme switching working after the move
from mutatively-applied Ansible to immutable image swaps. The old mechanism (a
user timer re-running `ansible --tags base16` to rewrite configs in `/etc` +
`/usr`, then reloading apps) is dead twice over: Ansible isn't in the runtime
path anymore, and it wrote to locations that are now read-only verity `/usr`.

Naming: we adopt darkman's vocabulary. **light = daytime = `gruvbox-dark-hard`**,
**dark = night = `unikitty-dark`**. These are darkman's sun-position modes
(`light-mode.d/` runs when the sun is up, `dark-mode.d/` after sunset).

## Core design decision

**Render every scheme into the image at build time; flip a pointer at runtime.**

- Build time: `base16_builder` renders each app's color fragment **once per
  scheme** into read-only `/usr`. No runtime rendering at all — fully faithful to
  the immutable model. Reuses the existing builder + every existing `.j2`; no
  port to a new templating tool (tinty was considered and rejected for exactly
  this reason — it renders at runtime into `$HOME`).
- Runtime: `darkman` is the light/dark trigger and hook runner. Its hook relinks a
  stable `$HOME` path to the active scheme's fragment and sends each app its
  reload signal. The only writable-runtime touch is a handful of symlinks + a
  mode file.

### Why darkman is only the *scheduler* here, not the central switch

Both our schemes are *dark palettes* (`gruvbox-dark-hard` and `unikitty-dark`) —
the light/dark labels track the sun, not the palette brightness. The freedesktop
portal's `color-scheme` axis is only light-vs-dark, so a portal-following app
told "light mode" at daytime would render *bright* — wrong, because our daytime
palette is a dark gruvbox. So **portal-following gets us nothing** and almost
every app uses the pre-rendered-file-swap path instead. darkman's portal-backend
feature is therefore largely moot; we use darkman purely for sunrise/sunset
computation + running our hook. (This also finally replaces the dead clight
dependency in `day-or-night`.)

## Decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Rendering time | **Build time, into `/usr`** | Read-only verity `/usr` can't be written at runtime; baking both schemes keeps all generated config immutable |
| Templating tool | **Keep `base16_builder` + existing `.j2`s** | Zero template porting; same upstream scheme/template sources we already reference |
| Runtime selection | **Stable `$HOME` symlink → `/usr/.../themes/{light,dark}/...` + reload signal** | App configs stay scheme-agnostic; flip = relink + reload |
| Light/dark trigger | **darkman user service** | Built-in sunrise/sunset (replaces dead clight `day-or-night`); `{light,dark}-mode.d/` hook framework |
| Fresh-launched procs (shells) | **Env var from a mode file darkman writes** | zsh/CLI tools read `$BASE16_THEME` at launch; no running-process reload needed |
| Firefox live palette | **Pywalfox (off-the-shelf)** | Live `theme.update()`, no restart, no custom extension/native-host to maintain; CLI `pywalfox update` is built for system theming hooks |
| Scheme count/source | **Two schemes baked from upstream base16 repos** | Single source of truth; no scheme color data duplicated in this repo |

Trade-off accepted: the image carries N copies of each color fragment
(negligible size), and **changing/adding a scheme requires an image rebuild** —
fine for a stable light/dark pair.

## Required refactor: split colors out of each config

Today each `.j2` interpolates colors *inline* into the main config (e.g.
`/etc/sway/config`), one scheme at a time. To bake both schemes, split the
**color-bearing block into an `include`-able fragment** so the main config is
scheme-agnostic and just includes a stable path:

```
/usr/share/arch-ansible/themes/light/<app>    (gruvbox-dark-hard)
/usr/share/arch-ansible/themes/dark/<app>      (unikitty-dark)

~/.config/<app>/colors  ->  symlink into the active themes/{light,dark}/<app>
```

The main config `include`s `~/.config/<app>/colors`. This split is the bulk of
the work and is required regardless of tool choice.

## Per-app plan

Apps currently themed via the `base16` tag / `base16_builder`:
`cli-tools, firefox, greeter, launcher, neovim, pdf, qt, secrets, sway,
terminals (ghostty), waybar, zsh` (+ `set-appearance-facts` which only computed
the active-scheme facts and goes away).

| App | Selection mechanism | Reload on flip |
| --- | --- | --- |
| sway | `include ~/.config/sway/colors` → symlink | `swaymsg reload` |
| mako | symlinked config fragment | `makoctl reload` |
| waybar | symlinked CSS `@import` | `systemctl --user restart waybar` (current) or `SIGUSR2` |
| ghostty (terminals) | `config-file` include → symlink | `kill -USR2 $(pidof ghostty)` |
| neovim | reads mode file / `--remote-send` to running servers | autocmd or RPC |
| zsh, cli-tools | **env var** `BASE16_THEME` from darkman mode file | next shell (fresh launch) |
| launcher, pdf, qt | symlinked fragment | restart on next launch (acceptable) |
| secrets (GTK ask-pass) | symlinked GTK override | next agent launch |
| firefox | **Pywalfox** (see below) | live via Theme API |
| greeter | baked per-scheme; greeter is pre-session | n/a (build-time only) |

## Firefox (Pywalfox)

Split Firefox theming into two layers:

1. **Structure (color-agnostic)** stays in a static `userChrome.css`: hide close
   buttons, remove borders, fonts. The Theme API can't express these.
2. **Palette** is delivered live by Pywalfox via `browser.theme.update()`.

Integration seam: Pywalfox reads `~/.cache/wal/colors` (pywal's 16-hex-lines
format). base16 already has a canonical 16-color mapping (what our shell/terminal
template emits), so:

- Build time: render two pywal-format `colors` files from the base16 palettes
  (`light`, `dark`) into `/usr` via `base16_builder`.
- darkman hook: copy the active one to `~/.cache/wal/colors`, run `pywalfox update`.

Install in the image:
- Extension: sideload via existing `firefox_ext_sideloader` (or AMO).
- Native host: ship the `pywalfox` package; place the native-messaging manifest
  in `/usr/lib/mozilla/native-messaging-hosts/` (system-wide, read-only OK)
  rather than the per-user default.
- Ignore Pywalfox's own Dark/Light/Auto timer — both our schemes are dark
  palettes; we push palettes externally from darkman.

Caveat: Theme API covers only the chrome surfaces it exposes (frame, toolbar,
tabs, fields, sidebar, popups, newtab). Anything beyond that stays in the static
structural `userChrome.css`. Page-*content* recoloring is out of scope (would
need a CSS-injecting extension; our `userContent.css` only touches about:home).

## darkman wiring

One hook pair does everything (`~/.local/share/{light,dark}-mode.d/10-colorscheme`,
shipped from `/usr` skel or dotfiles):

```sh
# dark-mode.d/10-colorscheme  (light-mode.d/ uses mode=light, scheme=gruvbox-dark-hard)
scheme=unikitty-dark
mode=dark

for app in sway mako waybar ghostty launcher pdf qt secrets; do
  ln -sf "/usr/share/arch-ansible/themes/$mode/$app" "$HOME/.config/$app/colors"
done
echo "$scheme" > "$XDG_RUNTIME_DIR/base16-theme"        # fresh shells read this
cp "/usr/share/arch-ansible/themes/$mode/wal-colors" "$HOME/.cache/wal/colors"

swaymsg reload
makoctl reload
systemctl --user restart waybar
pkill -USR2 ghostty
pywalfox update
```

Other things can read `darkman get` / watch its D-Bus / read
`$XDG_RUNTIME_DIR/base16-theme` — the "signals exposed by darkman" surface.

## Build/image tasks

- Run `base16_builder` per app **twice** (light + dark) at image build, emitting
  fragments to `/usr/share/arch-ansible/themes/{light,dark}/`.
- Ship darkman (package + user service enabled) + the hook scripts.
- Ship Pywalfox (package + extension + system native-host manifest).
- Ship static, color-agnostic main configs containing `include` directives +
  the auto-following nvim plugin.
- Seed `~/.config/<app>/colors` symlinks + `~/.cache/wal/` via skel/tmpfiles so
  the first session has a defined default before darkman's first transition.

## Teardown (old mechanism)

Delete once the above lands:
- `roles/set-appearance-facts/` (active-scheme facts no longer needed)
- `roles/brightness/files/colorscheme-changer{,.service,.timer}` and its install
  tasks (the Ansible-invoking runtime loop)
- `day-or-night` clight logic (superseded by darkman)
- the `vendor/roles/mnussbaum.base16-builder-ansible` *runtime* use — keep only
  as a **build-time** renderer
- inline color interpolation in main configs, once split into fragments

## Open questions / to verify

- darkman: confirm it can drive sunrise/sunset from hardcoded coordinates without
  GeoClue (we want no location daemon).
- neovim: decide between a mode-file autocmd vs `--remote-send` to running
  servers vs `auto-dark-mode.nvim` (the last only does light/dark — likely
  insufficient since both schemes are dark palettes).
- ghostty: confirm `kill -USR2` live-reloads config-file includes in our version.
- Confirm the base16→pywal 16-color mapping matches what we want in Firefox
  chrome (reuse the existing terminal/shell base16 template's mapping).
- Decide where the hook scripts live: `/usr` skel vs dotfiles repo.
