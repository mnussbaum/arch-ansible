You're in an Ansible repo configuring an Arch Linux workstation and
provisioning tools.

The system implements an immutable, image based installation and upgrade strategy
that leans heavily on systemd tooling and mkosi. See docs/bootstrapping.md for details.

Repo `bin/` holds only scripts a person runs from the checkout. Commands
installed onto the system (called by units, sudoers, tasks, other scripts) go
in `/usr/bin`, shipped from `mkosi/mkosi.extra/usr/bin/` or copied there by a
role, never an arch-ansible-named directory.

This is a public repo (github.com/mnussbaum/arch-ansible, default branch
`main`); its own work is fine to push there, but never commit secrets or key
material. Sensitive, gitignored paths: `secrets/` (generated GPG recovery
guides), `mkosi.key`/`mkosi.crt` (image signing key). Secrets are managed in
pass (Password Store). Host secrets live under `host_secrets/<hostname>/` and
reach units through
`ansible/roles/secrets/files/pass-credential@.{socket,service}`.
