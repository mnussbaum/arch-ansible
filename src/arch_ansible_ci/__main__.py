"""CI tasks for this repo's image; see `bin/ci --help`."""

import argparse
import json
import sys
from dataclasses import asdict

from arch_ansible_ci.identity import ensure_identity


def cmd_identity(args):
    manifest = ensure_identity(args.dir)
    print(json.dumps(asdict(manifest), indent=2))

    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="ci", description="CI tasks for this repo's image."
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser(
        "identity",
        help="create the throwaway CI identity in DIR, or print the one already there",
    )
    i.add_argument("dir")
    i.set_defaults(func=cmd_identity)
    args = p.parse_args(argv)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
