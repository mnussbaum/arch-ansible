"""Render the printable recovery guide as HTML on stdout.

docs/recovery-guide.md is the skeleton. A line holding only a link titled
"embedded in the printed guide" is replaced by the linked doc, and each
<!-- secret: NAME --> placeholder by key material. Links to embedded docs become
"(Part N)" references, since paper has no links.

Run by bin/generate-gpg-recovery-guide; --preview prints placeholders in place
of key material.
"""

import argparse
import base64
import html
import pathlib
import re
import subprocess
import sys
import urllib.parse

import markdown

# A curated subset of oath-accounts.txt, printed so they survive losing the USB.
CRITICAL_TOTPS = {
    "Backblaze:michaelnussbaum08@gmail.com",
    "GitHub:mnussbaum",
    "GitLab:gitlab.com:gitlab.com_michaelnussbaum08@gmail.com",
    "Google:michaelnussbaum08@gmail.com",
    "Yahoo:michaelnussbaum08@yahoo.com",
    "Ubiquiti SSO:michael.nussbaum",
}

INCLUDE = re.compile(r'^\[[^\]]+\]\(([^)\s]+)\s+"embedded in the printed guide"\)\s*$', re.M)
SECRET = re.compile(r"^<!-- secret: ([a-z-]+) -->\s*$", re.M)
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.M | re.S)

CSS = """
body { font-family: Georgia, serif; max-width: 740px; margin: 40px auto; padding: 0 24px; color: #000; font-size: 13px; line-height: 1.6; }
h1 { font-size: 1.5em; border-bottom: 2px solid #000; padding-bottom: 6px; margin-bottom: 4px; }
h2 { font-size: 1.25em; margin-top: 2em; border-bottom: 1px solid #999; padding-bottom: 3px; page-break-after: avoid; }
h3 { font-size: 1.08em; margin-top: 1.6em; margin-bottom: 6px; page-break-after: avoid; }
h4 { font-size: 1em; margin-top: 1.3em; margin-bottom: 4px; page-break-after: avoid; }
.generated { color: #555; font-size: 0.85em; margin-bottom: 1.5em; font-family: monospace; }
.uid { font-family: monospace; font-size: 1.05em; background: #f5f5f5; padding: 8px 12px; border: 1px solid #ccc; }
.fingerprint { font-family: monospace; font-size: 1.05em; letter-spacing: 0.12em; background: #f5f5f5; padding: 12px; border: 1px solid #ccc; white-space: pre; }
.mono { font-family: monospace; white-space: pre-wrap; font-size: 0.8em; background: #f5f5f5; padding: 10px; border: 1px solid #ccc; word-break: break-all; }
.qr { margin: 12px 0; }
.qr img { display: block; image-rendering: pixelated; border: 1px solid #ccc; }
.totps { display: flex; flex-wrap: wrap; gap: 14px; margin: 12px 0; }
.totp { width: 130px; text-align: center; page-break-inside: avoid; }
.totp img { width: 120px; display: block; border: 1px solid #ccc; }
.totp .label { font-size: 0.68em; margin-top: 3px; word-break: break-all; }
.totp .uri { font-family: monospace; font-size: 0.62em; margin-top: 2px; word-break: break-all; color: #333; }
code { font-family: monospace; background: #f0f0f0; padding: 1px 5px; border: 1px solid #ddd; font-size: 0.95em; }
pre { background: #f0f0f0; border: 1px solid #ddd; padding: 8px 10px; white-space: pre-wrap; word-break: break-all; page-break-inside: avoid; }
pre code { background: none; border: none; padding: 0; }
ol li, ul li { margin-bottom: 6px; }
"""


def qr_png_b64(data: str, size: int, level: str) -> str:
    # On stdin: armored data starts with "-----", which qrencode reads as options.
    png = subprocess.run(
        ["qrencode", "-t", "PNG", "-s", str(size), "-l", level, "-o", "-"],
        input=data.encode(), capture_output=True, check=True,
    ).stdout
    return base64.b64encode(png).decode()


def secret_blocks(args) -> dict[str, str]:
    if args.preview:
        placeholder = '<div class="mono">(printed only in the real guide)</div>'
        return {name: placeholder for name in
                ("identity", "fingerprint", "public-key", "private-key", "totp")}

    fpr = args.fingerprint
    groups = [fpr[i:i + 4] for i in range(0, len(fpr), 4)]
    pubkey = pathlib.Path(args.pubkey).read_text()
    # Only the numbered lines get typed back in; paperkey's comments explain its format.
    paperkey = "\n".join(line for line in pathlib.Path(args.paperkey).read_text().splitlines()
                         if re.match(r"\s*\d+:", line))
    blocks = {
        "identity": f'<div class="uid">{html.escape(args.uid)}</div>',
        "fingerprint": '<div class="fingerprint">'
                       f'{" ".join(groups[:5])}\n{" ".join(groups[5:])}</div>',
        "public-key": f'<div class="qr"><img width="230" height="230" '
                      f'src="data:image/png;base64,{qr_png_b64(pubkey, 5, "L")}"></div>'
                      f'<div class="mono">{html.escape(pubkey)}</div>',
        "private-key": f'<div class="mono">{html.escape(paperkey)}</div>',
    }

    totps = []
    if args.oath:
        for line in pathlib.Path(args.oath).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            label = urllib.parse.unquote(urllib.parse.urlparse(line).path.lstrip("/"))
            if label in CRITICAL_TOTPS:
                totps.append(
                    '<div class="totp">'
                    f'<img src="data:image/png;base64,{qr_png_b64(line, 3, "M")}">'
                    f'<div class="label">{html.escape(label)}</div>'
                    f'<div class="uri">{html.escape(line)}</div></div>')
    blocks["totp"] = (f'<div class="totps">{"".join(totps)}</div>' if totps
                      else "<p>(The primary key USB has no oath-accounts.txt.)</p>")
    return blocks


def demote(text: str) -> str:
    """Drop the doc's title and push its headings one level down."""
    text = re.sub(r"\A# .*\n", "", text.lstrip())
    return re.sub(r"^(#{2,5}) ", r"#\1 ", text, flags=re.M)


def unlink(text: str, parts: dict[str, str]) -> str:
    """Rewrite links for paper, leaving fenced code alone."""
    def replace(m: re.Match) -> str:
        label, target = m.group(1), m.group(2)
        if target.startswith(("http://", "https://")):
            return label if label == target else f"{label} ({target})"
        name = target.split("#", 1)[0]
        if not name or name == "recovery-guide.md":
            return label
        if name in parts:
            return parts[name] if label == name else f"{label} ({parts[name]})"
        if label == name:
            return f"`docs/{name}`"
        return f"{label} (`docs/{name}`)"

    out, pos = [], 0
    for fence in FENCE.finditer(text):
        out.append(LINK.sub(replace, text[pos:fence.start()]))
        out.append(fence.group(0))
        pos = fence.end()
    out.append(LINK.sub(replace, text[pos:]))
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("guide")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--uid")
    ap.add_argument("--fingerprint")
    ap.add_argument("--pubkey")
    ap.add_argument("--paperkey")
    ap.add_argument("--oath")
    ap.add_argument("--generated", default="")
    args = ap.parse_args()
    if not args.preview and not all((args.uid, args.fingerprint, args.pubkey, args.paperkey)):
        ap.error("--uid, --fingerprint, --pubkey and --paperkey are required without --preview")

    guide_path = pathlib.Path(args.guide)
    text = guide_path.read_text()
    title, text = text.split("\n", 1)
    title = title.removeprefix("# ")

    # Each embedded doc is referred to by the "Part N" heading it sits under.
    parts = {}
    for m in INCLUDE.finditer(text):
        heading = re.findall(r"^## (.*)$", text[:m.start()], re.M)[-1]
        parts[m.group(1)] = heading.split(" — ", 1)[0]

    text = INCLUDE.sub(
        lambda m: demote((guide_path.parent / m.group(1)).read_text()), text)
    text = unlink(text, parts)

    blocks = secret_blocks(args)
    tokens = {}
    def stash(m: re.Match) -> str:
        token = f"SECRETBLOCK{len(tokens)}"
        tokens[token] = blocks[m.group(1)]
        return token
    text = SECRET.sub(stash, text)

    body = markdown.markdown(text, extensions=["fenced_code"])
    for token, block in tokens.items():
        body = body.replace(f"<p>{token}</p>", block)

    generated = html.escape(args.generated or "preview")
    if args.uid:
        generated += f" &nbsp;|&nbsp; {html.escape(args.uid)}"
    sys.stdout.write(
        f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
        f"<title>{html.escape(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f"<h1>{html.escape(title)}</h1>\n"
        f'<div class="generated">Generated: {generated}</div>\n'
        f"{body}\n</body>\n</html>\n")


if __name__ == "__main__":
    main()
