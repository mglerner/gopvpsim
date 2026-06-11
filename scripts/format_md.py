#!/usr/bin/env python
"""
Format markdown files for raw-text readability.

Current passes (run in order):

* **strip_trailing_whitespace** — removes trailing whitespace from prose
  lines while preserving markdown's two-space soft line break and leaving
  fenced code blocks untouched (where trailing whitespace may be
  meaningful column padding).
* **collapse_blank_lines** — collapses runs of 2+ consecutive blank lines
  outside code fences down to a single blank line, and strips trailing
  blank lines at end-of-file.
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
# Shared helpers
# ---------------------------------------------------------------------------


def _fence_mask(lines: list[str]) -> list[bool]:
    """For each line, return True iff it lies inside a fenced code block.

    Fence markers (the ``` or ~~~ lines themselves) count as outside the
    fence — passes that operate on prose can leave them alone since the
    marker text is itself markdown punctuation. Supports both ``` and ~~~
    fences and only treats a closing fence as one that uses the same
    marker as the opener (so ``` doesn't accidentally close ~~~).
    """
    mask = [False] * len(lines)
    in_fence = False
    fence_marker = ""
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            fence_marker = stripped[:3]
            mask[i] = False  # the opening fence line itself
            continue
        if in_fence and stripped.startswith(fence_marker):
            in_fence = False
            fence_marker = ""
            mask[i] = False  # the closing fence line itself
            continue
        mask[i] = in_fence
    return mask


# ---------------------------------------------------------------------------
# Pass: strip_trailing_whitespace
# ---------------------------------------------------------------------------


def strip_trailing_whitespace(lines: list[str]) -> list[str]:
    """Strip trailing whitespace from prose lines.

    Lines inside fenced code blocks are left untouched (the trailing
    whitespace may be meaningful column padding in tabular data dumps).

    Markdown's ``two-trailing-spaces`` soft line break is preserved: a
    line that ends in two-or-more spaces is normalized to exactly two
    trailing spaces (so the line break is preserved while any extra
    padding is cleaned up). Tabs at end-of-line are stripped — they have
    no markdown semantics.
    """
    in_fence = _fence_mask(lines)
    out: list[str] = []
    for i, line in enumerate(lines):
        if in_fence[i]:
            out.append(line)
            continue
        # Count trailing spaces (only spaces, not tabs).
        stripped = line.rstrip()
        n_trailing_spaces = len(line) - len(line.rstrip(" "))
        if n_trailing_spaces >= 2 and stripped:
            # Preserve the markdown soft break — but normalize to exactly
            # two spaces. (Empty-after-rstrip lines are just blank lines
            # with whitespace; collapse them to truly blank instead.)
            out.append(stripped + "  ")
        else:
            out.append(stripped)
    return out


# ---------------------------------------------------------------------------
# Pass: collapse_blank_lines
# ---------------------------------------------------------------------------


def collapse_blank_lines(lines: list[str]) -> list[str]:
    """Collapse runs of 2+ consecutive blank lines down to 1, outside fences.

    Multiple blank lines have no semantic effect in markdown. A single
    blank line is the canonical separator between block elements; runs of
    two or more are leftover noise. Inside fenced code blocks blank-line
    runs are preserved verbatim — they may be meaningful in code samples.

    Trailing blank lines at end-of-file are also collapsed away (the file
    will end with exactly one newline, handled by ``format_text``).
    """
    in_fence = _fence_mask(lines)
    out: list[str] = []
    prev_blank_outside_fence = False
    for i, line in enumerate(lines):
        if in_fence[i]:
            out.append(line)
            prev_blank_outside_fence = False
            continue
        if line == "":
            if prev_blank_outside_fence:
                continue  # drop the duplicate blank
            prev_blank_outside_fence = True
            out.append(line)
        else:
            prev_blank_outside_fence = False
            out.append(line)
    # Strip trailing blank lines outright. (format_text adds back exactly
    # one newline at end-of-file.)
    while out and out[-1] == "":
        out.pop()
    return out


# ---------------------------------------------------------------------------
# Pass: pad_tables
# ---------------------------------------------------------------------------


def _split_cells(s: str) -> list[str]:
    """Split on '|' EXCEPT escaped pipes (\\|) and pipes inside backtick
    code spans — both are cell content, and a naive split() shifted every
    subsequent column (2026-06-11 review finding W1)."""
    cells: list[str] = []
    buf: list[str] = []
    in_code = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "`":
            in_code = not in_code
            buf.append(ch)
        elif ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf.append("\\|")
            i += 1
        elif ch == "|" and not in_code:
            cells.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf))
    return cells


def _split_row(line: str) -> list[str]:
    """Split a markdown table row line into trimmed cell strings.

    Strips leading indent (the caller validates it's <= 3 spaces) and a
    single leading and trailing pipe if present (the convention in this
    repo). Cells are returned with surrounding whitespace stripped.
    Escaped pipes and pipes inside backtick code spans stay in their cell.
    """
    s = line.rstrip("\n").lstrip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in _split_cells(s)]


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

            # GFM: a table may be indented up to 3 spaces; 4+ is an
            # indented code block. Previously the indent leaked into the
            # first cell AND the re-emit dropped it (review finding W1).
            indents = [l[:len(l) - len(l.lstrip())] for l in block]
            if any(len(ind.expandtabs(4)) >= 4 for ind in indents):
                # Indented code block (or tab-indented content) — leave
                # every line byte-identical.
                out.extend(block)
                continue

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
            # Re-emit with the first line's indent (normalizing ragged
            # indents within the block, which is this tool's job anyway).
            indent = indents[0]
            out.extend(indent + rendered
                       for rendered in _render_table(rows, sep_index, aligns))
            continue

        out.append(line)
        i += 1

    return out


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

PASSES: list[Callable[[list[str]], list[str]]] = [
    strip_trailing_whitespace,
    collapse_blank_lines,
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
