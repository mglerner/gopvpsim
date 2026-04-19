#!/usr/bin/env python3
"""One-off patcher: add external-link anchor ids to existing dive HTML.

Three card types get stable-slug ids on the outer ``<div class="dd-rec-
card">`` so external pages (CD article IV Recommendations, cross-
species comparisons) can deep-link directly to a card:

* **Threshold tier cards** → ``id="tier-card-<slug>"``. Original P2
  pattern (shipped 2026-04-18). Slug reads from a hidden
  ``<span id="tier-card-yours-<slug>">`` placeholder already present
  in the card's ``<h4>``.
* **Notable IVs cards** → ``id="notable-<slug>"``. Slug derived from
  the category name (first text node of the card's ``<h4>``).
  Replaces the earlier ``id="dd-notable-card-<uid>"`` counter-based
  id, which wasn't stable across re-renders.
* **Mirror Slayer cards** → ``id="mirror-<slug>"``. Slug derived from
  the category name (Atk Slayer / Bulk Slayer / CMP Slayer).

The permanent fix is in ``deep_dive_rendering.py``: the renderer now
emits each id natively. This script applies the same transformation
to existing HTML files in place so links work without a re-dive.

Usage:
    python scripts/patch_dive_tier_anchors.py [--dry-run] PATH [PATH ...]

PATH can be a single .html file or a directory (walks recursively for
*.html). By default modifies files in place; --dry-run prints what
would change without writing.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

# Threshold-tier card: read slug from the yours-placeholder span
# already present in the card's <h4>, rewrite the opening <div> to add
# the id.
_TIER_CARD_RE = re.compile(
    r'<div class="dd-rec-card">'
    r'(\s*<h4>(?:(?!</h4>).)*?'
    r'<span id="tier-card-yours-([^"]+)")',
    re.DOTALL,
)

# Notable IVs card: already has an unstable counter-based id
# (``dd-notable-card-<N>``); rewrite to a stable name-slug id. Name is
# the first text node of the <h4>, stopping at the first inner <span>
# (which is the member-count annotation).
_NOTABLE_CARD_RE = re.compile(
    r'<div class="dd-rec-card (dd-notable|dd-not-notable)"'
    r' id="dd-notable-card-\d+">'
    r'(\s*<h4>)([^<]+?)(\s*<span\b[^>]*>\()',
    re.DOTALL,
)

# Mirror Slayer card: ``<div class="dd-rec-card">`` with an <h4> whose
# leading text is one of Atk Slayer / Bulk Slayer / CMP Slayer (then a
# ``(N survivors)`` span). No pre-existing id, so match only when the
# rec-card lives inside the mirror section (checked via whitespace-
# tolerant lookahead on the <h4> text).
_MIRROR_CARD_RE = re.compile(
    r'<div class="dd-rec-card">'
    r'(\s*<h4>)(Atk Slayer|Bulk Slayer|CMP Slayer)'
    r'(\s*<span\b[^>]*>\()',
    re.DOTALL,
)


def _slugify(name: str) -> str:
    return re.sub(r'^-|-$', '',
                  re.sub(r'[^a-z0-9]+', '-', name.lower()))


def patch_html(source: str) -> tuple[str, dict[str, int]]:
    """Return (patched_html, counts_per_card_type). Idempotent: cards
    that already carry the target id are skipped.
    """
    counts = {'tier': 0, 'notable': 0, 'mirror': 0}

    def _tier_repl(m: re.Match) -> str:
        counts['tier'] += 1
        slug = m.group(2)
        prefix = m.group(1)
        return f'<div class="dd-rec-card" id="tier-card-{slug}">{prefix}'

    def _notable_repl(m: re.Match) -> str:
        counts['notable'] += 1
        notable_cls = m.group(1)
        open_h4 = m.group(2)
        raw_name = html.unescape(m.group(3)).strip()
        tail = m.group(4)
        slug = _slugify(raw_name) or 'cat'
        return (f'<div class="dd-rec-card {notable_cls}" '
                f'id="notable-{slug}">{open_h4}{m.group(3)}{tail}')

    def _mirror_repl(m: re.Match) -> str:
        counts['mirror'] += 1
        open_h4 = m.group(1)
        cat_name = m.group(2)
        tail = m.group(3)
        slug = _slugify(cat_name)
        return (f'<div class="dd-rec-card" id="mirror-{slug}">'
                f'{open_h4}{cat_name}{tail}')

    new_source = _TIER_CARD_RE.sub(_tier_repl, source)
    new_source = _NOTABLE_CARD_RE.sub(_notable_repl, new_source)
    new_source = _MIRROR_CARD_RE.sub(_mirror_repl, new_source)
    return new_source, counts


def _iter_html_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix == '.html' else []
    return sorted(path.rglob('*.html'))


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Backfill tier-, notable-, and mirror-card anchor ids '
                    'on existing dive HTML.')
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would change without writing.')
    args = parser.parse_args()

    total_files = 0
    total = {'tier': 0, 'notable': 0, 'mirror': 0}
    for root in args.paths:
        for path in _iter_html_files(root):
            source = path.read_text()
            new_source, counts = patch_html(source)
            n = sum(counts.values())
            if n == 0 or new_source == source:
                continue
            total_files += 1
            for k, v in counts.items():
                total[k] += v
            summary = ', '.join(
                f'{v} {k}' for k, v in counts.items() if v
            )
            if args.dry_run:
                print(f'would patch {path}: {summary}')
            else:
                path.write_text(new_source)
                print(f'patched {path}: {summary}')
    verb = 'would patch' if args.dry_run else 'patched'
    total_cards = sum(total.values())
    print(f'\n{verb} {total_cards} card(s) across {total_files} file(s) '
          f'({total["tier"]} tier, {total["notable"]} notable, '
          f'{total["mirror"]} mirror).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
