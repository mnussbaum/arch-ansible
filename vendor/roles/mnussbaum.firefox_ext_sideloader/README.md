# firefox_ext_sideloader

"Sideload" install Firefox extensions from XPI files using Ansible. Follows the
process described at
https://cryptonomic.net/sideload-extensions-in-firefox.html. This is useful if
for example your system package manager installs Firefox extensions globally
but they aren't being properly registered in your per-user Firefox profile.


## Example usages

```yaml
---
roles:
  - mnussbaum.firefox_ext_sideloader

tasks:
  - firefox_ext_sideloader:
      path: /usr/lib/firefox/browser/extensions/uBlock0@raymondhill.net.xpi

```

## Options

```yaml
path:
  description:
    - Path to the extensions XPI file
    - Many Arch Linux Firefox extension packages place XPI files at /usr/lib/firefox/browser/extensions
  required: true
  type: string
user:
  description:
    - Name of the system user to install the extension for
  required: false
  type: string
  default: Current user
profile:
  description:
    - Name of the Firefox profile to install the extension into
    - Profile names should match The `Name` field of the profiles listed in
      ~/.mozilla/firefox/profiles.ini
  required: false
  type: string
  default: Install into all available profiles
```

## Dependencies

- Python 3.5 or greater, 2.7 will likely work, but is untested
- Ansible
- [mozlz4](https://github.com/jusw85/mozlz4) used to de/compress Mozilla's
  non-standard LZ4 format used with some config files. If you're on Arch Linux
  you can install this via the [mozlz4 AUR package](https://aur.archlinux.org/packages/mozlz4/)

## Installation

You can install this role with
[`ansible-galaxy`](https://galaxy.ansible.com/intro). Check out the
`ansible-galaxy` docs for all the different ways you can install roles, but the
simplest is just:

    $ ansible-galaxy install mnussbaum.firefox_ext_sideloader


If you don't want to, or can't, use `ansible-galaxy`, then you can clone this
repo and drop it directly into your [Ansible roles path](https://docs.ansible.com/ansible/latest/playbooks_reuse_roles.html#role-search-path).

Be sure to install dependency [mozlz4](https://github.com/jusw85/mozlz4) and
make it available on your `$PATH` as well.

## Developing

This project uses [Poetry](https://python-poetry.org/) to install dependencies.

```bash
pip install --user poetry
poetry install --no-root
```

## License

[MIT](LICENSE)
