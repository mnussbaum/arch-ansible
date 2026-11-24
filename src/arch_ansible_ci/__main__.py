"""CI tasks for this repo's image; see `bin/ci --help`."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from arch_ansible_ci.identity import ensure_identity

REPO = Path(__file__).resolve().parent.parent.parent
STAGES = ("install", "first_boot", "session")


def cmd_identity(args):
    manifest = ensure_identity(args.dir)
    print(json.dumps(asdict(manifest), indent=2))

    return 0


def cmd_test(args):
    """Run end-to-end stages; a stage's earlier stages run first as fixtures."""
    os.chdir(REPO)
    os.execvp(
        "uv",
        [
            "uv",
            "run",
            "--project",
            str(REPO),
            "pytest",
            "tests/e2e",
            "-m",
            " or ".join(args.stages),
            "-v",
            "-rA",
            *args.pytest_args,
        ],
    )


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
    t = sub.add_parser("test", help="run end-to-end stages against the built medium")
    t.add_argument(
        "stages",
        nargs="+",
        choices=STAGES,
        metavar="STAGE",
        help=f"one or more of: {', '.join(STAGES)}",
    )
    t.add_argument(
        "pytest_args", nargs=argparse.REMAINDER, help="after --, arguments for pytest"
    )
    t.set_defaults(func=cmd_test)
    args = p.parse_args(argv)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
