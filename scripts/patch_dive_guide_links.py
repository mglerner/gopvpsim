#!/usr/bin/env python3
"""Inject Reader's Guide footer links into already-shipped HTML.

Applies the same textual changes as the source-side edits landed in
scripts/generate_article.py (CD article footer + IV Recommendations
intro), scripts/deep_dive.py (dive-page guide-pointer line above
About & Credits), and scripts/deep_dive_rendering.py (Threshold
Tiers intro sentence), without re-diving.

Idempotent: each inserted snippet has a stable sentinel string. A
file already carrying the sentinel is skipped with a "skip" line so
re-runs are safe.

Two file shapes are handled:

  article: the CD article (articles/<slug>/index.html). Patches the
           <footer> and every <p class="iv-rec-intro">.

  dive:    the dive landing or a split-moveset sibling
           (<species>-<league>/index.html,
           <species>-<league>/index_m*.html). Patches the
           Threshold-Tiers intro paragraph and inserts a one-line
           <p> guide-pointer before the <details>About & Credits
           block.

File kind is auto-detected by structure (<footer> tag + iv-rec-intro
=> article; About & Credits details block => dive). A file that
matches neither prints a warning and is left alone.

Usage:
    python scripts/patch_dive_guide_links.py PATH [PATH ...]
    python scripts/patch_dive_guide_links.py --ship
    python scripts/patch_dive_guide_links.py --dry-run --ship
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'

# Stable sentinel substrings (any of these on a line => already patched).
ART_FOOTER_SENTINEL = '../../guides/">Reader\'s Guide</a>'
ART_INTRO_SENTINEL = '../../guides/threshold-tiers/'
DIVE_POINTER_SENTINEL = 'New here? The <a href="../guides/">'
DIVE_INTRO_SENTINEL = '../guides/threshold-tiers/'


# -------------------------- article --------------------------------

ART_FOOTER_NEEDLE = (
    '<a href="https://github.com/pvpoke/pvpoke">PvPoke</a> game data.'
)
ART_FOOTER_REPLACEMENT = (
    '<a href="https://github.com/pvpoke/pvpoke">PvPoke</a> game data. |\n'
    '  <a href="../../guides/">Reader\'s Guide</a>'
)

# The IV Recommendations intro comes in two variants (per-form render
# vs single-form render). Both end the visible-prose sentence with
# "Threshold Tiers section</a>." or "Threshold Tiers section.". We
# patch by appending one link-carrying sentence *before* the closing
# </p>. Use a regex so we can cover both variants in one pass.
import re as _re

# Match the full <p class="iv-rec-intro">...</p> block (non-greedy,
# allowing inline tags). We append the guide-link sentence before
# </p>. Using re because the intro carries embedded anchor tags and a
# plain string replace would bias to one variant.
ART_INTRO_PATTERN = _re.compile(
    r'(<p class="iv-rec-intro">.*?)(</p>)',
    flags=_re.DOTALL,
)
ART_INTRO_INSERT = (
    ' New to tier cards? The '
    '<a href="../../guides/threshold-tiers/">Threshold Tiers guide</a> '
    'walks through what the stat cutoffs and member counts mean.'
)


def _patch_article(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []

    # Footer
    if ART_FOOTER_SENTINEL in text:
        notes.append('footer already patched')
    elif ART_FOOTER_NEEDLE in text:
        text = text.replace(ART_FOOTER_NEEDLE, ART_FOOTER_REPLACEMENT, 1)
        notes.append('footer patched')
    else:
        notes.append('footer needle not found')

    # Intro paragraph(s)
    if ART_INTRO_SENTINEL in text:
        notes.append('intro already patched')
    else:
        new_text, n = ART_INTRO_PATTERN.subn(
            lambda m: m.group(1) + ART_INTRO_INSERT + m.group(2),
            text, count=0,
        )
        if n:
            text = new_text
            notes.append(f'intro patched ({n} occurrence(s))')
        else:
            notes.append('intro pattern not found')

    return text, notes


# ---------------------------- dive ---------------------------------

# Threshold-Tiers intro: existing source ends the prose "anchor list:"
# then continues with a <ul>. We patch by inserting the guide-link
# sentence right before the "A tier's anchors come from two passes"
# phrase that leads into the bullet list, matching the source edit.
DIVE_INTRO_NEEDLE = (
    "A tier's anchors come from two passes over the anchor list:"
)
DIVE_INTRO_REPLACEMENT = (
    'New to tier cards? The '
    '<a href="../guides/threshold-tiers/">Threshold Tiers guide</a> '
    'walks through what the stat cutoffs and member counts mean. '
    + DIVE_INTRO_NEEDLE
)

# The one-line pointer is inserted immediately before the About &
# Credits details block. Match on the existing markup so we only
# insert once per file.
DIVE_POINTER_ANCHOR = (
    '<details class="meta" style="margin-top:30px;'
    'border-top:1px solid #0f3460;padding-top:10px">'
    '<summary>About &amp; Credits</summary>'
)
DIVE_POINTER_REPLACEMENT = (
    '<p style="margin-top:30px;color:#888;font-size:12px">'
    'New here? The <a href="../guides/">Reader\'s Guide</a> '
    'explains tier cards, envelope shapes, and the IV flavor guide '
    'in plain language.</p>\n'
    '<details class="meta" style="margin-top:10px;'
    'border-top:1px solid #0f3460;padding-top:10px">'
    '<summary>About &amp; Credits</summary>'
)


def _patch_dive(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []

    # Threshold-Tiers intro
    if DIVE_INTRO_SENTINEL in text:
        notes.append('tt-intro already patched')
    elif DIVE_INTRO_NEEDLE in text:
        text = text.replace(DIVE_INTRO_NEEDLE, DIVE_INTRO_REPLACEMENT, 1)
        notes.append('tt-intro patched')
    else:
        notes.append('tt-intro needle not found')

    # Guide-pointer line above About & Credits
    if DIVE_POINTER_SENTINEL in text:
        notes.append('pointer already patched')
    elif DIVE_POINTER_ANCHOR in text:
        text = text.replace(DIVE_POINTER_ANCHOR, DIVE_POINTER_REPLACEMENT, 1)
        notes.append('pointer patched')
    else:
        notes.append('pointer anchor not found')

    return text, notes


# ------------------------- dispatch --------------------------------

def _classify(text: str) -> str:
    has_article_footer = (
        '<footer>' in text and 'scripts/generate_article.py' in text
    )
    has_iv_rec_intro = '<p class="iv-rec-intro">' in text
    has_about_credits = 'About &amp; Credits' in text
    has_tt_intro = 'dd-threshold-tiers' in text
    if has_article_footer or has_iv_rec_intro:
        return 'article'
    if has_about_credits or has_tt_intro:
        return 'dive'
    return 'unknown'


def _find_ship_surfaces() -> list[Path]:
    article = (WEBSITE_DIR / 'articles'
               / 'oinkologne-cd-2026-05' / 'index.html')
    site_index = WEBSITE_DIR / 'index.html'
    surfaces = [article, site_index]
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
    kind = _classify(text)
    if kind == 'article':
        new_text, notes = _patch_article(text)
    elif kind == 'dive':
        new_text, notes = _patch_dive(text)
    else:
        print(f'{path}: skip (not article or dive)')
        return True

    if new_text == text:
        print(f'{path}: no-op [{kind}: {"; ".join(notes)}]')
        return True

    if dry_run:
        print(f'{path}: would patch [{kind}: {"; ".join(notes)}]')
    else:
        path.write_text(new_text)
        print(f'{path}: patched [{kind}: {"; ".join(notes)}]')
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('paths', nargs='*', type=Path)
    parser.add_argument('--ship', action='store_true',
                        help='Patch the Oinkologne pre-ship surface set.')
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
