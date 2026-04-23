#!/usr/bin/env python
"""Retrofit shipped dive HTML so tier-card badges show the flavor name.

The 2026-04-23 tier-name unify (see scripts/deep_dive.py ``_rename_plotly_tiers``
and the session plan) makes tier-card badges and the Plotly legend both
display the flavor-matched name (e.g. "Lapras Slayer" instead of
"Lapras Atk"). Dives emitted BEFORE that change render the auto-derived
name on the card and the flavor name only in the legend; this patcher
brings shipped HTML in line without a re-dive.

What it does
------------

- Parse the dive's ``var DATA = {...}`` JS blob to extract ``tiers``,
  where each renamed entry carries both ``name`` (the flavor name) and
  ``original_name`` (the pre-rename auto-derived label).
- For every tier whose ``original_name`` differs from ``name``, rewrite
  the visible badge text in the tier-card HTML from ``original_name``
  to ``name``. The outer ``id="tier-card-<slug>"`` anchor is SLUGGED
  FROM ``original_name``, so deep-link hrefs from the article side keep
  resolving without any anchor renaming.
- Deep-link consumers on the article side already slug from
  ``original_name`` (see generate_article.py ``_tier_card_href``), so
  this patcher does not need to touch article files. Only dive HTML.
- Plotly legend text is rendered client-side from ``DATA.tiers[*].name``,
  which already holds the flavor name in shipped HTML (the rename ran
  after render, server-side). No legend change needed.

Idempotency
-----------

Each rewrite matches a specific ``id="tier-card-<slug>">`` anchor and
looks for the exact ``original_name`` in the badge. A second run finds
no matches (badge text is now the flavor name) and is a clean no-op.

Usage
-----

    python scripts/patch_dive_tier_name_unify.py PATH [PATH ...]
    python scripts/patch_dive_tier_name_unify.py --ship
    python scripts/patch_dive_tier_name_unify.py --dry-run --ship
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'


def _slugify(name: str) -> str:
    return re.sub(r'^-|-$', '',
                  re.sub(r'[^a-z0-9]+', '-', name.lower()))


def _extract_data_tiers(text: str) -> list[dict]:
    """Pull DATA.tiers out of the inline script. Empty list on failure.

    DATA is a single JSON blob assigned via ``var DATA = {...};``. We
    parse the whole thing and return the tiers list; callers handle the
    empty-list case as a no-op.
    """
    m = re.search(r'var DATA = (\{.*?\});\n', text, flags=re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    tiers = data.get('tiers')
    if isinstance(tiers, list):
        return tiers
    return []


def _patch_tier(text: str, tier: dict) -> tuple[str, bool]:
    """Rewrite one tier's badge text from original_name to name.

    Returns (new_text, changed). Silent no-op when the tier already
    reads as the flavor name (idempotent) or when the anchor is missing
    (older or differently-shaped dive file).
    """
    original_name = (tier.get('original_name') or '').strip()
    flavor_name = (tier.get('name') or '').strip()
    if not original_name or not flavor_name or original_name == flavor_name:
        return text, False
    slug = _slugify(original_name)
    if not slug:
        return text, False

    # Match the specific card's badge text. The HTML shape is produced
    # by deep_dive_rendering.py::render_threshold_tier_cards:
    #
    #   <div class="dd-rec-card" id="tier-card-{slug}">
    #   <h4><span class="dd-badge" style="...">{name}</span> ...
    #
    # We anchor on the tier-card id so the rewrite targets only this
    # tier's badge. Non-greedy over whitespace/attributes to stay
    # robust to minor emit-shape drift.
    card_anchor = (
        r'(<div class="dd-rec-card" id="tier-card-' + re.escape(slug) + r'">\s*'
        r'<h4>(?:<a[^>]*>\s*)?'
        r'<span class="dd-badge"[^>]*>)'
        r'(' + re.escape(original_name) + r')'
        r'(</span>)'
    )
    pattern = re.compile(card_anchor)
    new_text, n = pattern.subn(
        lambda m: m.group(1) + flavor_name + m.group(3), text, count=1)
    return new_text, (n > 0)


def _patch_dive(text: str) -> tuple[str, list[str]]:
    """Apply every applicable tier rewrite. Returns (new_text, notes)."""
    tiers = _extract_data_tiers(text)
    if not tiers:
        return text, ['no DATA.tiers found']
    notes: list[str] = []
    renamed = [t for t in tiers
               if (t.get('original_name') or '').strip()
               and t.get('name') != t.get('original_name')]
    if not renamed:
        return text, ['no renamed tiers (all names equal original_name)']
    patched_count = 0
    skipped_names: list[str] = []
    for tier in renamed:
        text, changed = _patch_tier(text, tier)
        if changed:
            patched_count += 1
        else:
            skipped_names.append(
                f'{tier.get("original_name")}->{tier.get("name")}')
    if patched_count:
        notes.append(f'{patched_count} tier badge(s) retargeted')
    if skipped_names:
        notes.append(f'skipped (already unified or anchor missing): '
                     f'{", ".join(skipped_names)}')
    return text, notes


# ------------------------- dispatch --------------------------------


def _find_ship_surfaces() -> list[Path]:
    """Same ship-surface set as patch_dive_guide_links.py, minus the
    article (no tier badges live there - the article renders its own
    tier cards via generate_article._render_tier_card, which reads
    ``tier.get('name')`` from dive data and so already picks up the
    flavor name)."""
    surfaces: list[Path] = []
    for dive_slug in ('oinkologne-great-league',
                      'oinkologne-female-great-league'):
        dive_dir = WEBSITE_DIR / dive_slug
        if not dive_dir.is_dir():
            continue
        if (dive_dir / 'index.html').exists():
            surfaces.append(dive_dir / 'index.html')
        for p in sorted(dive_dir.glob('index_m*.html')):
            surfaces.append(p)
    return surfaces


def _process(path: Path, *, dry_run: bool) -> bool:
    text = path.read_text()
    new_text, notes = _patch_dive(text)
    note_str = '; '.join(notes) if notes else 'no-op'
    if new_text == text:
        print(f'{path}: no-op [{note_str}]')
        return True
    if dry_run:
        print(f'{path}: would patch [{note_str}]')
    else:
        path.write_text(new_text)
        print(f'{path}: patched [{note_str}]')
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
