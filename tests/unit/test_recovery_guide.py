import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RENDERER = REPO / "bin/_recovery_guide.py"
FIXTURE_GUIDE = Path(__file__).parent / "fixtures/guide/guide.md"
FINGERPRINT = "0123456789ABCDEF0123456789ABCDEF01234567"
INCLUDE = re.compile(
    r'^\[[^\]]+\]\(([^)\s]+)\s+"embedded in the printed guide"\)\s*$', re.MULTILINE
)
# A line of plain prose, which reaches the HTML unchanged.
PLAIN_LINE = re.compile(r"^[A-Za-z][A-Za-z0-9 ,.'()-]{20,}$", re.MULTILINE)


def render(*args, check=True):
    return subprocess.run(
        [sys.executable, str(RENDERER), *args],
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.fixture
def key_material(tmp_path):
    pubkey = tmp_path / "pubkey.asc"
    pubkey.write_text(
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\ntest\n-----END PGP PUBLIC KEY BLOCK-----\n"
    )
    paperkey = tmp_path / "paperkey.txt"
    paperkey.write_text(
        "# Secret-key-only data, from paperkey\n  1: 00 11 22 AABBCC\n  2: 33 44 55 DDEEFF\n"
    )

    return [
        "--uid",
        "Test User <test@example.com>",
        "--fingerprint",
        FINGERPRINT,
        "--pubkey",
        str(pubkey),
        "--paperkey",
        str(paperkey),
    ]


def test_preview_inlines_every_embedded_doc_of_the_real_guide():
    guide = REPO / "docs/recovery-guide.md"

    html = render("--preview", str(guide)).stdout

    assert "embedded in the printed guide" not in html
    for doc in INCLUDE.findall(guide.read_text()):
        body = (guide.parent / doc).read_text().split("\n", 1)[1]
        line = PLAIN_LINE.search(body)
        assert line, f"{doc} has no plain line to look for"
        assert line.group(0) in html, f"{doc} was not inlined"


def test_links_are_rewritten_for_paper():
    html = render("--preview", str(FIXTURE_GUIDE)).stdout

    assert "the setup steps (Part 1)" in html
    assert "See the setup steps (Part 1), Part 1," in html
    assert "<code>docs/other.md</code>," in html
    assert "the other doc (<code>docs/other.md</code>)" in html
    assert "a wrapped label (<code>docs/other.md</code>)" in html
    assert "example (https://example.com)" in html
    assert "[left alone](other.md)" in html


def test_embedded_docs_lose_their_title_and_their_headings_drop_a_level():
    html = render("--preview", str(FIXTURE_GUIDE)).stdout

    assert "Setup title" not in html
    assert "<h3>Setup step</h3>" in html


def test_key_material_flags_are_required_without_preview():
    result = render(str(FIXTURE_GUIDE), check=False)

    assert result.returncode == 2
    assert (
        "--uid, --fingerprint, --pubkey and --paperkey are required without --preview"
        in result.stderr
    )


def test_fingerprint_is_grouped_and_only_numbered_paperkey_lines_are_kept(key_material):
    html = render(*key_material, str(FIXTURE_GUIDE)).stdout

    assert "0123 4567 89AB CDEF 0123\n4567 89AB CDEF 0123 4567" in html
    assert "1: 00 11 22 AABBCC\n  2: 33 44 55 DDEEFF" in html
    assert "Secret-key-only data" not in html


def test_only_critical_totp_accounts_are_printed(key_material, tmp_path):
    oath = tmp_path / "oath-accounts.txt"
    oath.write_text(
        "# exported accounts\n"
        "otpauth://totp/GitHub:mnussbaum?secret=AAAA\n"
        "otpauth://totp/Unlisted:someone?secret=BBBB\n"
    )

    html = render(*key_material, "--oath", str(oath), str(FIXTURE_GUIDE)).stdout

    assert '<div class="label">GitHub:mnussbaum</div>' in html
    assert "Unlisted" not in html


def test_a_missing_oath_file_is_noted(key_material):
    html = render(*key_material, str(FIXTURE_GUIDE)).stdout

    assert "(The root GPG key USB has no oath-accounts.txt.)" in html
