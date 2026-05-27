- Document that we implement https://uapi-group.org/specifications/specs/discoverable_partitions_specification/
- Ask it to diff against the plan in https://0pointer.net/blog/fitting-everything-together.html
- I think we move package installs back into ansible
- Is `Install pacman database files` still needed?
- Clean up network_install_root
- Stuff copied from the host that needs to be in containerfile
  - yay-bin
  - password-store repo
  - arch-ansible repo
  - nvim packages
  - mirrorlist - ideally reflectored
  - Cargo registry
  - Sccache
- Host needs ~/.cargo/registry ~/.cache/sccache
- How are we going to mount in nvim data dir in container? Probably need to handle its absence
- In image build need to mount from new system locations once I have a provisioned machine
- Ask it if there's other things that need network access going on that we can avoid
- Get offline
  - Remove pacman keyring stuff if truly offline
  - Base16 configs reach internet still
  - delta theme file download

- Make sure this is followed up on:

```
  The UnifiedKernelImages=yes (mkosi/ukify) approach: mkosi drives the UKI assembly via ukify directly, giving better integration with Secure Boot signing and TPM2 PCR measurements. But then linux.preset needs to switch from default_uki= to default_image= (plain initrd path), and post-boot kernel updates need a separate hook (kernel-install
  plugin or pacman hook calling ukify) instead of mkinitcpio handling it.
```

- Revaluate bootstrap and rebuild-boot-partition tags
- Investigate restic/btrfs best practice setup
  - How can we restore a restic backup automatically?
- Document cache mounting pattern perf optimization
- Can we move ansible into the build step? Might allow better caching
- Make sure secrets aren't exposed in system ansible repo. Or replace with pass access
- Test the partition swap in qemu
- Fix colorscheme changer for the new world. Needs a whole new strategy
- Test different USI usages
- Add eeek tasks back in
- New scripts
  - build-image --usi=<false|true> [--refresh-cache] [--dev] [--skip-postinst] [--ansible-tags TAGS] [output-device]
  - run-image --hostname=<required_hostname> [--runtime=<qemu|whatever else mkosi supports>] <more optional arg to attach another image emulating a recovery drive attached to a workstation>
  - burn-image --hostname=<required_hostname> [--image file] <output device>
- Organize project top level better. Playbooks in one dir, mkosi stuff in another
