import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


def run_vm(*args):
    env = dict(os.environ, PYTHONPATH=str(SRC))

    return subprocess.run(
        [sys.executable, "-m", "arch_ansible_vm", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (
            ["run", "disk.raw", "--device", "target.raw"],
            "error: --device applies to the medium",
        ),
        (
            ["run", "disk.raw", "--ephemeral"],
            "error: --ephemeral applies to the medium",
        ),
        (
            ["run", "disk.raw", "--organization", "a"],
            "error: --organization applies to the medium",
        ),
        (["run", "--run", "true"], "error: --run needs an installed DISK"),
        (["run", "--share", "/tmp"], "error: --share needs an installed DISK"),
        (["run", "--entry", "v1"], "error: --entry needs an installed DISK"),
    ],
)
def test_run_rejects_flags_for_the_other_kind_of_boot(args, error):
    result = run_vm(*args)

    assert result.returncode == 1
    assert error in result.stderr


@pytest.mark.parametrize("flag", [["--entry", "v1"], ["--run", "true"]])
def test_run_rejects_serial_driven_flags_with_gui(flag):
    result = run_vm("run", "disk.raw", "--gui", *flag)

    assert result.returncode == 1
    assert (
        "drives the guest over serial and can't be combined with --gui" in result.stderr
    )
