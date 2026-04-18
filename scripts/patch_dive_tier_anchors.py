#!/usr/bin/env python3
"""One-off patcher: add ``id="tier-card-<slug>"`` to existing dive HTML.

The dive renderer used to emit the tier-card slug only on a hidden
``<span id="tier-card-yours-<slug>" style="display:none">`` placeholder
inside the card's ``<h4>``. Browsers cannot scroll to a display:none
element, so external deep-links (e.g. from the CD article's IV
Recommendations cards) resolve the href but don't move the viewport.

The permanent fix is in ``deep_dive_rendering.py``: the card's
``<div class="dd-rec-card">`` now carries the id directly. This script
applies the same transformation to existing HTML files in place so
links work without a re-dive.

Usage:
    python scripts/patch_dive_tier_anchors.py [--dry-run] PATH [PATH ...]

PATH can be a single .html file or a directory (walks recursively for
*.html). By default modifies files in place; --dry-run prints what
would change without writing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Match a card whose <h4> header contains the yours-placeholder span,
# capture the slug, and rewrite the opening <div> to add the id.
_CARD_RE = re.compile(
    r'<div class="dd-rec-card">'
    r'(\s*<h4>(?:(?!</h4>).)*?'
    r'<span id="tier-card-yours-([^"]+)")',
    re.DOTALL,
)


def patch_html(html: str) -> tuple[str, int]:
    """Return (patched_html, n_cards_rewritten). Idempotent: cards that
    already have an ``id="tier-card-..."`` attribute are skipped.
    """
    count = 0

    def _repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        slug = m.group(2)
        prefix = m.group(1)
        return f'<div class="dd-rec-card" id="tier-card-{slug}">{prefix}'

    new_html = _CARD_RE.sub(_repl, html)
    return new_html, count


def _iter_html_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix == '.html' else []
    return sorted(path.rglob('*.html'))


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Backfill tier-card anchor ids on existing dive HTML.')
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would change without writing.')
    args = parser.parse_args()

    total_files = 0
    total_cards = 0
    for root in args.paths:
        for path in _iter_html_files(root):
            html = path.read_text()
            new_html, n = patch_html(html)
            if n == 0:
                continue
            if new_html == html:
                # All matches were already patched.
                continue
            total_files += 1
            total_cards += n
            if args.dry_run:
                print(f'would patch {path}: {n} card(s)')
            else:
                path.write_text(new_html)
                print(f'patched {path}: {n} card(s)')
    verb = 'would patch' if args.dry_run else 'patched'
    print(f'\n{verb} {total_cards} card(s) across {total_files} file(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
