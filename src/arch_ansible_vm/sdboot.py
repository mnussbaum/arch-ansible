"""Reading and driving the sd-boot menu over the serial console."""

import re
import time

# --- sd-boot menu ------------------------------------------------------------


def select_boot_entry(vm, title, timeout=120):
    """Pick the sd-boot menu entry whose title contains `title`.

    Any keypress cancels sd-boot's countdown (loader.conf sets `timeout 5`),
    so we tap `up` from the moment the VM starts until the menu shows up — that
    both stops the clock in time and parks the highlight on the first entry
    (sd-boot clamps at the ends rather than wrapping). From a known position the
    selection is a plain count of `down` presses, so we never have to work out
    which entry the firmware defaulted to.
    """
    deadline = time.monotonic() + timeout
    while True:
        vm.monitor.sendkey("up")
        if re.search(re.escape(title), vm.console.snapshot()):
            break
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"sd-boot menu never showed an entry matching {title!r}.\n"
                f"--- serial ---\n{vm.console.snapshot()[-3000:]}\n--- end ---"
            )
        time.sleep(0.25)

    # Give the menu a moment to finish drawing, then park firmly at the top.
    time.sleep(1.0)
    vm.monitor.sendkey("up", times=25)
    time.sleep(0.5)

    entries = menu_entries(vm.console.raw_snapshot())
    if not entries:
        raise RuntimeError(
            "could not parse the sd-boot menu.\n"
            f"--- serial ---\n{vm.console.snapshot()[-3000:]}\n--- end ---"
        )
    matches = [i for i, e in enumerate(entries) if title in e]
    if not matches:
        raise RuntimeError(f"no entry matching {title!r} in menu: {entries}")
    idx = matches[0]
    vm.log(f"==> sd-boot entries: {entries}")
    vm.log(f"==> selecting #{idx} ({entries[idx]!r})")
    vm.monitor.sendkey("down", times=idx)
    time.sleep(0.5)
    vm.monitor.sendkey("ret")
    return entries[idx]


# sd-boot doesn't emit its menu line by line: it centres each entry by absolute
# cursor address (CSI <row>;<col> H) and then repaints individual rows as the
# selection or the countdown changes. Stripping the escapes leaves one run-on
# line of padding, so the menu has to be reconstructed on a screen model.
_ESC_SEQ = re.compile(
    rb"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]"
)
_BOX_OR_BLANK = re.compile(r"^[─-╿\s]*$")
_COUNTDOWN = re.compile(r"^Boot in \d+\s*s\.?$")


def render_screen(raw):
    """Replay a raw terminal stream into {row: text}, honouring CSI ... H."""
    # Everything before the last full-screen erase belongs to a previous screen
    # (firmware chatter, an earlier repaint), so drop it.
    cut = raw.rfind(b"\x1b[2J")
    if cut >= 0:
        raw = raw[cut:]
    rows, row, col, i, n = {}, 1, 1, 0, len(raw)
    while i < n:
        if raw[i] == 0x1B:
            m = _ESC_SEQ.match(raw, i)
            if not m:
                i += 1
                continue
            seq = m.group(0)
            if seq.endswith(b"H") and seq.startswith(b"\x1b["):
                parts = seq[2:-1].split(b";")
                row = int(parts[0]) if parts[0] else 1
                col = int(parts[1]) if len(parts) > 1 and parts[1] else 1
            i = m.end()
            continue
        if raw[i] in (0x0A, 0x0D):
            if raw[i] == 0x0A:
                row += 1
            col = 1
            i += 1
            continue
        j = i
        while j < n and raw[j] != 0x1B and raw[j] not in (0x0A, 0x0D):
            j += 1
        text = raw[i:j].decode("utf-8", "replace")
        line = rows.setdefault(row, [])
        if len(line) < col - 1:
            line.extend(" " * (col - 1 - len(line)))
        for k, ch in enumerate(text):
            if col - 1 + k < len(line):
                line[col - 1 + k] = ch
            else:
                line.append(ch)
        col += len(text)
        i = j
    return {r: "".join(cs) for r, cs in rows.items()}


def menu_entries(raw):
    """Titles of the entries in the sd-boot menu currently on screen, in order."""
    screen = render_screen(raw)
    out = []
    for r in sorted(screen):
        title = screen[r].strip()
        # Skip the separator rule, the "Boot in Ns." status line, and any row
        # a repaint has since blanked.
        if _BOX_OR_BLANK.match(title) or _COUNTDOWN.match(title):
            continue
        out.append(title)
    return out
