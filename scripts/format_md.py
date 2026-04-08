#!/usr/bin/env python
"""
Format markdown files for raw-text readability.

Currently runs one pass:

* **pad_tables** — pads pipe-table cells with spaces so columns line up
  in a plain text editor while remaining valid GitHub-flavored markdown.

The script is designed as a pipeline: future readability passes can be
added to the ``PASSES`` list. Each pass is a function ``list[str] -> list[str]``
that operates on the file's lines (without trailing newlines) and returns
the new lines. Passes must be idempotent: running ``format_md.py`` twice
in a row must be a no-op on the second run.

Usage::

    python scripts/format_md.py [FILE ...]
    python scripts/format_md.py --hook   # read Claude Code hook JSON from stdin

With no positional arguments, walks the current directory recursively for
``*.md`` files (skipping ``.git``, ``.pytest_cache``, ``.claude``,
``userdata``, ``node_modules``, ``__pycache__``).

In ``--hook`` mode, reads a Claude Code PostToolUse JSON payload from
stdin, extracts ``tool_input.file_path``, and formats it iff it ends in
``.md``. Non-markdown paths and missing files are silently ignored so the
hook can be wired to fire on every Edit/Write without filtering upstream.

Exit code is 0 whether or not anything was changed; the script prints
``updated:`` / ``unchanged:`` lines so a caller (or a hook) can see what
happened.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Pass: pad_tables
# ---------------------------------------------------------------------------


def _split_row(line: str) -> list[str]:
    """Split a markdown table row line into trimmed cell strings.

    Strips a single leading and trailing pipe if present (the convention
    in this repo). Cells are returned with surrounding whitespace stripped.
    """
    s = line.rstrip("\n")
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    """True iff every cell is a markdown table separator (---, :---, ---:, :---:)."""
    if not cells:
        return False
    for c in cells:
        if not c:
            return False
        if not set(c) <= {"-", ":"}:
            return False
        if "-" not in c:
            return False
    return True


def _alignment(separator_cell: str) -> str:
    """Return ``left`` / ``right`` / ``center`` for one separator cell."""
    left = separator_cell.startswith(":")
    right = separator_cell.endswith(":")
    if left and right:
        return "center"
    if right:
        return "right"
    return "left"


def _pad_cell(text: str, width: int, align: str) -> str:
    if align == "right":
        return text.rjust(width)
    if align == "center":
        slack = width - len(text)
        l = slack // 2
        r = slack - l
        return " " * l + text + " " * r
    return text.ljust(width)


def _render_table(rows: list[list[str]], sep_index: int, aligns: list[str]) -> list[str]:
    n_cols = max(len(r) for r in rows)
    rows = [r + [""] * (n_cols - len(r)) for r in rows]
    aligns = (aligns + ["left"] * (n_cols - len(aligns)))[:n_cols]

    # Column widths from data rows (skip separator).
    widths = [0] * n_cols
    for i, row in enumerate(rows):
        if i == sep_index:
            continue
        for j, cell in enumerate(row):
            if len(cell) > widths[j]:
                widths[j] = len(cell)

    # Minimum width so the separator fits its alignment markers.
    for j in range(n_cols):
        min_w = 3  # ---
        if aligns[j] == "right":
            min_w = 4  # ---:
        elif aligns[j] == "center":
            min_w = 5  # :---:
        if widths[j] < min_w:
            widths[j] = min_w

    out: list[str] = []
    for i, row in enumerate(rows):
        if i == sep_index:
            parts = []
            for j in range(n_cols):
                w = widths[j]
                a = aligns[j]
                if a == "center":
                    parts.append(":" + "-" * (w - 2) + ":")
                elif a == "right":
                    parts.append("-" * (w - 1) + ":")
                else:
                    parts.append("-" * w)
            out.append("| " + " | ".join(parts) + " |")
        else:
            parts = [_pad_cell(row[j], widths[j], aligns[j]) for j in range(n_cols)]
            out.append("| " + " | ".join(parts) + " |")
    return out


def pad_tables(lines: list[str]) -> list[str]:
    """Pad pipe-table cells so columns line up in raw text.

    Lines inside fenced code blocks (``` or ~~~) are left untouched —
    a `|` inside a code fence is just code, not a table. A table is a
    contiguous run of lines starting with `|` that contains a separator
    row (``|---|---|``).
    """
    out: list[str] = []
    i = 0
    in_fence = False
    fence_marker = ""

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        # Track fenced code blocks. We support ``` and ~~~ fences and
        # only treat a closing fence as one that uses the same marker.
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            fence_marker = stripped[:3]
            out.append(line)
            i += 1
            continue
        if in_fence:
            out.append(line)
            if stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            i += 1
            continue

        if stripped.startswith("|"):
            # Collect a contiguous run of pipe-prefixed lines.
            block: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1

            rows = [_split_row(l) for l in block]
            sep_index = -1
            for k, r in enumerate(rows):
                if _is_separator_row(r):
                    sep_index = k
                    break

            if sep_index == -1 or len(rows) < 2:
                # Not a real table — emit unchanged.
                out.extend(block)
                continue

            aligns = [_alignment(c) for c in rows[sep_index]]
            out.extend(_render_table(rows, sep_index, aligns))
            continue

        out.append(line)
        i += 1

    return out


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

PASSES: list[Callable[[list[str]], list[str]]] = [
    pad_tables,
]


def format_text(text: str) -> str:
    """Run all passes on a markdown document. Preserves trailing newline."""
    had_trailing_newline = text.endswith("\n")
    lines = text.splitlines()
    for pass_fn in PASSES:
        lines = pass_fn(lines)
    new_text = "\n".join(lines)
    if had_trailing_newline:
        new_text += "\n"
    return new_text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

SKIP_DIRS = {".git", ".pytest_cache", ".claude", "userdata", "node_modules", "__pycache__"}


def discover_markdown(root: Path) -> list[Path]:
    found: list[Path] = []
    for p in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        found.append(p)
    return sorted(found)


def process_file(path: Path) -> bool:
    """Format ``path`` in place. Returns True iff the file was modified."""
    original = path.read_text()
    new_text = format_text(original)
    if new_text != original:
        path.write_text(new_text)
        return True
    return False


def _hook_targets() -> list[Path]:
    """Read a Claude Code PostToolUse JSON payload from stdin and return
    the (possibly empty) list of paths to format."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return []
    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return []
    return [Path(file_path)]


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args == ["--hook"]:
        targets = _hook_targets()
    elif args:
        targets = [Path(a) for a in args]
    else:
        targets = discover_markdown(Path.cwd())

    for path in targets:
        if not path.exists():
            print(f"missing:   {path}", file=sys.stderr)
            continue
        if path.suffix.lower() != ".md":
            # The hook may pass non-markdown paths; just skip silently.
            continue
        if process_file(path):
            print(f"updated:   {path}")
        else:
            print(f"unchanged: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
