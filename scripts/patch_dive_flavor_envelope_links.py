#!/usr/bin/env python3
"""Inject IV Flavor Guide + Envelope Position guide pointers into
already-shipped dive HTML.

Mirrors the source edits in scripts/deep_dive_narrative.py (flavor
zone intro sentence) and scripts/auto_gen_narrative.py (envelope-shape
summary trailing pointer), applied to dive files without re-diving.

Idempotent: each inserted snippet has a stable sentinel substring.
A file already carrying the sentinel is skipped with a "skip" line so
re-runs are safe.

Only handles dive files (landing + split-moveset siblings). The CD
article doesn't carry either surface (include_supplement=False in
render_overview suppresses the envelope paragraph, and the IV Flavor
Guide zone is dive-only), so this patcher leaves articles alone.

Usage:
    python scripts/patch_dive_flavor_envelope_links.py PATH [PATH ...]
    python scripts/patch_dive_flavor_envelope_links.py --ship
    python scripts/patch_dive_flavor_envelope_links.py --dry-run --ship
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'

# Stable sentinels: any of these in the file => already patched.
FLAVOR_SENTINEL = '../guides/iv-flavor-guide/'
ENVELOPE_SENTINEL = '../guides/envelope-position/'


# -------- Flavor zone intro ----------------------------------------
#
# Source emits the intro as a single <p>; we append one sentence
# before the closing </p>. The closing half of the existing sentence
# is unambiguous enough to use as a plain-string needle.

FLAVOR_NEEDLE = (
    'Threshold Tiers answer different questions and may not line '
    'up 1:1.</p>'
)
FLAVOR_REPLACEMENT = (
    'Threshold Tiers answer different questions and may not line '
    'up 1:1. '
    'New to flavor cards? The '
    '<a href="../guides/iv-flavor-guide/" style="color:#a78bca">IV '
    'Flavor Guide</a> walks through the six name families and the '
    'trade-off layout.'
    '</p>'
)


# -------- Envelope-shape summary -----------------------------------
#
# The envelope paragraph is a single-line <p> of shape
#
#   <p><strong>Envelope shape.</strong> ... straddle.</p>
#
# but the trailing clauses vary (rider-top only, rider-only, etc.).
# Regex matches the whole paragraph and injects the pointer sentence
# before the closing </p>. Non-greedy .*? is safe because no </p>
# appears inside the paragraph.

ENVELOPE_PATTERN = re.compile(
    r'(<p><strong>Envelope shape\.</strong>.*?)(</p>)',
    flags=re.DOTALL,
)
ENVELOPE_INSERT = (
    ' See the <a href="../guides/envelope-position/">Envelope '
    'Position guide</a> for what &ldquo;ride above the band&rdquo; '
    'means.'
)


def _patch_dive(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []

    # Flavor-zone intro
    if FLAVOR_SENTINEL in text:
        notes.append('flavor-intro already patched')
    elif FLAVOR_NEEDLE in text:
        text = text.replace(FLAVOR_NEEDLE, FLAVOR_REPLACEMENT, 1)
        notes.append('flavor-intro patched')
    else:
        notes.append('flavor-intro needle not found')

    # Envelope-shape summary
    if ENVELOPE_SENTINEL in text:
        notes.append('envelope-summary already patched')
    else:
        new_text, n = ENVELOPE_PATTERN.subn(
            lambda m: m.group(1) + ENVELOPE_INSERT + m.group(2),
            text, count=0,
        )
        if n:
            text = new_text
            notes.append(f'envelope-summary patched ({n} occurrence(s))')
        else:
            notes.append('envelope-summary pattern not found')

    return text, notes


def _is_dive(text: str) -> bool:
    # Dive files carry the Threshold Tiers anchor id or the About
    # & Credits block. Articles lack both and emit neither surface
    # that this patcher targets.
    return 'dd-threshold-tiers' in text or 'About &amp; Credits' in text


def _find_ship_surfaces() -> list[Path]:
    """Oinkologne pre-ship dive set (landing + every split-moveset)."""
    surfaces: list[Path] = []
    for dive_slug in ('oinkologne-great-league',
                      'oinkologne-female-great-league'):
        dive_dir = WEBSITE_DIR / dive_slug
        if not dive_dir.is_dir():
            continue
        surfaces.append(dive_dir / 'index.html')
        for p in sorted(dive_dir.glob('index_m*.html')):
            surfaces.append(p)
    return [s for s in surfaces if s.exists()]


def _process(path: Path, *, dry_run: bool) -> bool:
    text = path.read_text()
    if not _is_dive(text):
        print(f'{path}: skip (not a dive)')
        return True
    new_text, notes = _patch_dive(text)
    if new_text == text:
        print(f'{path}: no-op [{"; ".join(notes)}]')
        return True
    if dry_run:
        print(f'{path}: would patch [{"; ".join(notes)}]')
    else:
        path.write_text(new_text)
        print(f'{path}: patched [{"; ".join(notes)}]')
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('paths', nargs='*', type=Path)
    parser.add_argument('--ship', action='store_true',
                        help='Patch the Oinkologne pre-ship dive set.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    paths: list[Path] = list(args.paths)
    if args.ship:
        paths = _find_ship_surfaces() + paths
    if not paths:
        parser.error('Provide paths, or pass --ship for the pre-ship set.')

    ok = True
    for p in paths:
        if not p.exists():
            print(f'{p}: skip (not found)')
            continue
        if not _process(p, dry_run=args.dry_run):
            ok = False
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
