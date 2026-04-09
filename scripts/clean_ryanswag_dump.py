#!/usr/bin/env python
"""
Convert a RyanSwag GamePress deep-dive HTML-to-text dump into clean markdown.

The dumps under ``docs/reference_deep_dives/ryanswag/*.txt`` are mostly
intact prose with markdown-ish headers, but they have three classes of
formatting damage left over from the HTML scrape:

1. Hundreds of whitespace-only lines (single spaces, leftover ``&nbsp;``).
2. **Orphan bullets**: a bare ``-`` line, followed by zero-or-more blank
   or whitespace-only lines, followed by the content line. Markdown needs
   ``- content`` on a single line; the orphan form renders as an empty
   list item plus a stray paragraph.
3. The leading ``# Source: ...`` line is intended as a comment but renders
   as an H1 because it starts with ``#``.

This script fixes (1), (2), and (3) and writes the result to a sibling
``.md`` file. The original ``.txt`` is left in place so you can diff /
verify the conversion before deleting.

Usage::

    python scripts/clean_ryanswag_dump.py docs/reference_deep_dives/ryanswag/annihilape.txt

The output is then run through ``scripts/format_md.py`` (collapse blank
lines, pad tables, strip trailing whitespace) so it lands as final-form
markdown.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMAT_MD = REPO_ROOT / "scripts" / "format_md.py"


def _is_blankish(line: str) -> bool:
    """A line is 'blankish' if it's empty or contains only whitespace."""
    return line.strip() == ""


def fix_orphan_bullets(lines: list[str]) -> list[str]:
    """Join bare ``-`` bullet markers with their orphaned content lines.

    Pattern matched (where '~' = blankish line):

        -                       ->   - <content>
        ~
        ~
        <content>

    Detection rule: a line that, after stripping, equals exactly ``-`` (or
    ``*`` or ``+``, the other markdown bullet markers). The next non-blank
    line is consumed as that bullet's content, regardless of how many
    blankish lines lie between them.

    Bullets that already have content on the same line (``- foo``) are
    left alone.
    """
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped in ("-", "*", "+"):
            # Walk forward to find the next non-blank line.
            j = i + 1
            while j < n and _is_blankish(lines[j]):
                j += 1
            if j < n:
                content = lines[j].strip()
                # If the content line is itself another bullet marker or
                # header, don't join — that would corrupt structure. Treat
                # this orphan as a real (empty) bullet and move on.
                if content.startswith(("- ", "* ", "+ ", "#")) or content in ("-", "*", "+"):
                    out.append(f"{stripped} ")
                    i += 1
                    continue
                out.append(f"{stripped} {content}")
                i = j + 1
                continue
        out.append(line)
        i += 1
    return out


def fix_source_header(lines: list[str]) -> list[str]:
    """Convert a leading ``# Source: ...`` line into a blockquote.

    The dumps prepend two ``#``-prefixed lines:

        # Title
        # Source: web.archive.org/...

    The second line is meant as a comment but renders as an H1. Convert
    it to a blockquote so the title H1 stays unique. Only acts on the
    very first occurrence near the top of the file.
    """
    out: list[str] = []
    fixed = False
    for line in lines:
        if not fixed and line.startswith("# Source:"):
            url = line[len("# Source:"):].strip()
            out.append(f"> Source: {url}")
            fixed = True
            continue
        out.append(line)
    return out


def strip_whitespace_only_lines(lines: list[str]) -> list[str]:
    """Replace any whitespace-only line with a truly empty line.

    The HTML scrape produced thousands of single-space lines. Markdown
    treats them as blank either way, but truly empty lines collapse
    cleanly under ``format_md.py``'s ``collapse_blank_lines`` pass.
    """
    return ["" if _is_blankish(line) else line for line in lines]


def clean(text: str) -> str:
    lines = text.splitlines()
    lines = strip_whitespace_only_lines(lines)
    lines = fix_orphan_bullets(lines)
    lines = fix_source_header(lines)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: clean_ryanswag_dump.py <file.txt>", file=sys.stderr)
        return 2
    src = Path(argv[1])
    if not src.exists() or src.suffix != ".txt":
        print(f"expected an existing .txt file, got: {src}", file=sys.stderr)
        return 2
    dst = src.with_suffix(".md")
    cleaned = clean(src.read_text())
    dst.write_text(cleaned)
    print(f"wrote: {dst}")

    # Run format_md.py on the result to handle final whitespace + table padding.
    result = subprocess.run(
        [sys.executable, str(FORMAT_MD), str(dst)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"format_md.py failed: {result.stderr}", file=sys.stderr)
        return result.returncode
    print(result.stdout, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
