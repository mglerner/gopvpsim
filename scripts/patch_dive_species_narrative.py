#!/usr/bin/env python3
"""Backfill the Species narrative zone into existing dive HTML.

The Shape 2 Species narrative renderer (``deep_dive_rendering.render_
species_narrative``) emits a gold-bordered ``<section class="dd-species-
narrative">`` block above the interactive dashboard. It fires only
when ``deep_dive.py`` detects populated ``[Species.intro]`` /
``[Species.meta_role]`` / ``[Species.verdict]`` blocks in the
threshold TOML.

Before the 2026-04-19 narrative-extraction fix, invoking deep_dive.py
with ``--no-thresholds`` (the standard pattern for stub threshold
files like Aegislash's) skipped the narrative extraction entirely,
so the rendered HTML had no narrative even when the TOML authored
one. This patcher applies the narrative in place without re-running
the 50+ minute dive.

Usage::

    # Patch every HTML in a dive dir (discovers species from the
    # dir basename, maps to thresholds/<species>.toml):
    python scripts/patch_dive_species_narrative.py \\
        userdata/website/aegislash-shield-great-league \\
        [userdata/website/aegislash-blade-great-league ...]

    # Explicit species + TOML override:
    python scripts/patch_dive_species_narrative.py PATH \\
        --species 'Aegislash (Shield)' \\
        --thresholds thresholds/aegislash_shield.toml

Idempotent: dive HTMLs that already carry a
``<section class="dd-species-narrative">`` are skipped.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
sys.path.insert(0, str(REPO_ROOT / 'src'))

from deep_dive_rendering import render_species_narrative  # type: ignore[import-not-found]


# Injection marker: the narrative renders immediately before the
# interactive controls div. Matches both the main index.html and the
# per-moveset split files, which share the controls-div shape.
_CONTROLS_MARKER = '<div class="controls">'
_ALREADY_PATCHED_MARKER = '<section class="dd-species-narrative">'

# CSS override shipped alongside the patched narrative. Fresh dive
# renders carry this via deep_dive_rendering's main stylesheet; patched
# HTMLs were generated under an older renderer, so we scope-override
# here. The rules below have the same selectors as the main sheet so
# later-defined-wins CSS cascade ensures these take effect.
# Keep in sync with scripts/deep_dive_rendering.py's
# ``.dd-species-narrative`` CSS block.
_NARRATIVE_CSS_OVERRIDE = """
<style>
/* Species-narrative CSS override injected by
   scripts/patch_dive_species_narrative.py (2026-04-19 refactor).
   Brings pre-refactor dive HTMLs onto the shared rounded-sidebar
   pattern so all dive zones (expert, narrative, sim, callout,
   threshold list, species narrative) render with the same
   rounded-cap pseudo-element bar. Safe no-op if the main stylesheet
   already has equivalent rules (later-defined-wins cascade). */

/* Zero the outer .dd-species-narrative's old hard border/padding. */
.dd-species-narrative {
  margin: 20px 0;
  border-left: none;
  padding: 0;
}

/* Per-zone colours + spacing. */
.dd-expert-zone { --sidebar-color: #d29922;
  padding: 10px 0 10px 20px; margin: 16px 0; }
.dd-narrative-zone { --sidebar-color: #9b59b6;
  padding: 12px 0 12px 20px; margin: 20px 0; }
.dd-sim-zone { --sidebar-color: #58a6ff;
  padding: 10px 0 10px 20px; margin: 16px 0; }
.dd-callout { --sidebar-color: #58a6ff; --sidebar-width: 3px;
  padding: 8px 12px 8px 16px; margin: 10px 0; }
.dd-threshold-list li { --sidebar-color: #0f3460; --sidebar-width: 2px;
  padding: 4px 0 4px 14px; margin: 4px 0; }
.dd-threshold-list .dd-loss-item { --sidebar-color: #f85149; }
.dd-species-narrative .dd-narrative-block {
  --sidebar-color: #d29922;
  padding: 10px 0 10px 20px;
  margin: 8px 0;
}
.dd-species-narrative .dd-narrative-block.authored-ai {
  --sidebar-color: #e8903a;
}
.dd-species-narrative .dd-narrative-block > h2,
.dd-species-narrative .dd-narrative-block > h3 {
  color: var(--sidebar-color);
  margin: 0 0 8px 0;
}
.dd-species-narrative .dd-narrative-block > h2 { font-size: 1.15rem; }
.dd-species-narrative .dd-narrative-block > h3 { font-size: 1.0rem; }

/* Shared pattern: rounded-cap pseudo-element sidebar. */
.dd-expert-zone,
.dd-narrative-zone,
.dd-sim-zone,
.dd-callout,
.dd-species-narrative .dd-narrative-block,
.dd-threshold-list li {
  position: relative;
  border-left: none;
}
.dd-expert-zone::before,
.dd-narrative-zone::before,
.dd-sim-zone::before,
.dd-callout::before,
.dd-species-narrative .dd-narrative-block::before,
.dd-threshold-list li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  width: var(--sidebar-width, 4px);
  border-radius: calc(var(--sidebar-width, 4px) / 2);
  background: var(--sidebar-color, #8b949e);
}

.dd-species-narrative p { margin: 8px 0; }
.dd-species-narrative .narrative-attribution { color: #8b949e;
  font-size: 0.82rem; margin: 6px 0 0 0; font-style: italic; }
</style>
"""


def _infer_species_from_slug(slug: str) -> str | None:
    """Reverse of deep_dive.py's slug convention.

    'aegislash-shield-great-league' -> 'Aegislash (Shield)'
    'oinkologne-female-great-league' -> 'Oinkologne (Female)'
    'oinkologne-great-league' -> 'Oinkologne'

    Returns None when the league suffix can't be stripped cleanly.
    """
    parts = slug.split('-')
    # Trim trailing league tokens
    if len(parts) >= 2 and parts[-1] == 'league':
        parts = parts[:-1]
    if parts and parts[-1] in ('great', 'ultra', 'master'):
        parts = parts[:-1]
    if not parts:
        return None

    # Known form suffixes land inside parens
    form_tokens = {
        'shield', 'blade', 'female', 'male',
        'busted', 'hangry', 'disguised',
        'origin', 'altered', 'rapid', 'single',
    }
    if parts[-1].lower() in form_tokens:
        form = parts[-1].capitalize()
        base = ' '.join(p.capitalize() for p in parts[:-1])
        return f'{base} ({form})' if base else None
    return ' '.join(p.capitalize() for p in parts)


def _load_narrative(toml_path: Path, species: str) -> dict:
    with open(toml_path, 'rb') as f:
        raw = tomllib.load(f)
    sp = raw.get(species, {})
    narrative: dict = {}
    for key in ('intro', 'meta_role', 'verdict'):
        if key in sp and isinstance(sp[key], dict):
            narrative[key] = sp[key]
    return narrative


def _patch_html(html: str, narrative_fragment: str,
                force: bool = False) -> tuple[str, bool]:
    """Inject narrative_fragment immediately before the first controls div.

    Returns (patched_html, changed). By default idempotent: returns
    unchanged when the file already has a
    ``<section class="dd-species-narrative">``. Pass ``force=True``
    to strip the existing narrative section first and re-inject —
    useful after a renderer change (e.g. new CSS classes) that the
    old injected markup doesn't reflect.
    """
    if _ALREADY_PATCHED_MARKER in html:
        if not force:
            return html, False
        # Strip the existing narrative section (and any CSS override we
        # previously injected alongside it) before re-injecting. Matches
        # are non-greedy DOTALL so the section / style tags can span
        # multiple lines; ``count=1`` on each so we don't accidentally
        # remove unrelated style tags elsewhere in the HTML.
        import re as _re
        # Strip any previously-injected CSS override <style> block,
        # identified by its fingerprint comment.
        html = _re.sub(
            r'<style>[^<]*?Species-narrative CSS override injected by.*?</style>\s*',
            '', html, count=1, flags=_re.DOTALL,
        )
        html = _re.sub(
            r'<section class="dd-species-narrative">.*?</section>\s*',
            '', html, count=1, flags=_re.DOTALL,
        )
    idx = html.find(_CONTROLS_MARKER)
    if idx < 0:
        return html, False
    patched = html[:idx] + _NARRATIVE_CSS_OVERRIDE + narrative_fragment + html[idx:]
    return patched, True


def _iter_html_files(path: Path):
    if path.is_file():
        return [path] if path.suffix == '.html' else []
    return sorted(path.rglob('*.html'))


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Backfill Species narrative into existing dive HTML.')
    parser.add_argument('paths', nargs='+', type=Path,
                        help='Dive directories or individual HTML files.')
    parser.add_argument('--species',
                        help='Override species name (inferred from dir slug '
                             'by default).')
    parser.add_argument('--thresholds', type=Path,
                        help='Override TOML path (default: thresholds/'
                             '<species_slug>.toml).')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true',
                        help='Strip any existing narrative section before '
                             're-injecting (useful after a renderer change '
                             'that needs the new markup).')
    args = parser.parse_args()

    total_files = 0
    total_patched = 0

    for root in args.paths:
        # Resolve species + thresholds path
        species = args.species
        if species is None:
            slug = root.name if root.is_dir() else root.parent.name
            species = _infer_species_from_slug(slug)
            if species is None:
                print(f'[skip] {root}: could not infer species from slug',
                      file=sys.stderr)
                continue

        toml_path = args.thresholds
        if toml_path is None:
            species_fname = (species.lower()
                             .replace(' ', '_')
                             .replace('(', '')
                             .replace(')', ''))
            toml_path = REPO_ROOT / 'thresholds' / f'{species_fname}.toml'
        if not toml_path.exists():
            print(f'[skip] {root}: threshold TOML not found at {toml_path}',
                  file=sys.stderr)
            continue

        narrative = _load_narrative(toml_path, species)
        if not narrative:
            print(f'[skip] {root}: TOML {toml_path.name} has no narrative blocks',
                  file=sys.stderr)
            continue

        fragment = render_species_narrative(narrative)
        if not fragment.strip():
            print(f'[skip] {root}: rendered narrative fragment was empty',
                  file=sys.stderr)
            continue

        for html_path in _iter_html_files(root):
            html = html_path.read_text()
            new_html, changed = _patch_html(html, fragment, force=args.force)
            if not changed:
                continue
            total_files += 1
            total_patched += 1
            if args.dry_run:
                print(f'would patch {html_path}')
            else:
                html_path.write_text(new_html)
                print(f'patched {html_path}')

    verb = 'would patch' if args.dry_run else 'patched'
    print(f'\n{verb} {total_patched} HTML file(s) across {len(args.paths)} input(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
