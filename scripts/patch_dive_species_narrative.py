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
import auto_gen_narrative  # type: ignore[import-not-found]
from generate_article import _load_dive_data  # type: ignore[import-not-found]
from gopvpsim.data import get_default_moveset, load_gamemaster  # type: ignore[import-not-found]


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
.dd-expert-zone { --sidebar-color: var(--callout-expert);
  padding: 10px 0 10px 20px; margin: 16px 0; }
.dd-narrative-zone { --sidebar-color: var(--zone-narrative);
  padding: 12px 0 12px 20px; margin: 20px 0; }
.dd-sim-zone { --sidebar-color: var(--callout-auto);
  padding: 10px 0 10px 20px; margin: 16px 0; }
.dd-callout { --sidebar-color: var(--callout-auto); --sidebar-width: 3px;
  padding: 8px 12px 8px 16px; margin: 10px 0; }
.dd-threshold-list li { --sidebar-color: var(--border); --sidebar-width: 2px;
  padding: 4px 0 4px 14px; margin: 4px 0; }
.dd-threshold-list .dd-loss-item { --sidebar-color: var(--loss); }
.dd-species-narrative-details > summary {
  cursor: pointer;
  color: var(--notable);
  font-weight: 600;
  font-size: 1.0rem;
  padding: 6px 0 6px 20px;
  list-style: none;
}
.dd-species-narrative-details > summary::-webkit-details-marker { display: none; }
.dd-species-narrative-details > summary::before {
  content: "▸ ";
  display: inline-block;
}
.dd-species-narrative-details[open] > summary::before {
  content: "▾ ";
}
.dd-species-narrative-details > summary:hover { color: var(--notable); }
.dd-species-narrative .dd-narrative-block {
  --sidebar-color: var(--callout-expert);
  padding: 10px 0 10px 20px;
  margin: 8px 0;
}
.dd-species-narrative .dd-narrative-block.authored-ai {
  --sidebar-color: var(--callout-ai);
}
.dd-species-narrative .dd-narrative-block.authored-auto {
  --sidebar-color: var(--callout-auto);
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
  background: var(--sidebar-color, var(--text-muted));
}

.dd-species-narrative p { margin: 8px 0; }
.dd-species-narrative .narrative-attribution { color: var(--text-muted);
  font-size: 0.82rem; margin: 6px 0 0 0; font-style: italic; }
</style>
"""


def _infer_species_league_from_slug(slug: str) -> tuple[str, str] | None:
    """Reverse of deep_dive.py's slug convention.

    'aegislash-shield-great-league' -> ('Aegislash (Shield)', 'great')
    'oinkologne-female-great-league' -> ('Oinkologne (Female)', 'great')
    'oinkologne-great-league' -> ('Oinkologne', 'great')
    'tinkaton-ultra-league' -> ('Tinkaton', 'ultra')

    Returns None when the slug shape can't be parsed cleanly.
    """
    parts = slug.split('-')
    if len(parts) >= 2 and parts[-1] == 'league':
        parts = parts[:-1]
    league = 'great'
    if parts and parts[-1] in ('great', 'ultra', 'master'):
        league = parts[-1]
        parts = parts[:-1]
    if not parts:
        return None

    form_tokens = {
        'shield', 'blade', 'female', 'male',
        'busted', 'hangry', 'disguised',
        'origin', 'altered', 'rapid', 'single',
    }
    if parts[-1].lower() in form_tokens:
        form = parts[-1].capitalize()
        base = ' '.join(p.capitalize() for p in parts[:-1])
        if not base:
            return None
        return (f'{base} ({form})', league)
    return (' '.join(p.capitalize() for p in parts), league)


def _infer_species_from_slug(slug: str) -> str | None:
    """Backwards-compat wrapper returning just the species name."""
    result = _infer_species_league_from_slug(slug)
    return result[0] if result else None


def _load_narrative_and_cd_prep(toml_path: Path, species: str) -> tuple[dict, dict]:
    """Load the narrative + cd_prep blocks from a threshold TOML.

    Returns ``(narrative, cd_prep)`` dicts. ``cd_prep`` is empty when
    the species TOML has no ``[Species.cd_prep]`` block, which is the
    expected state for non-CD species (templates then skip auto-gen).
    """
    with open(toml_path, 'rb') as f:
        raw = tomllib.load(f)
    sp = raw.get(species, {})
    narrative: dict = {}
    for key in ('intro', 'meta_role', 'verdict'):
        if key in sp and isinstance(sp[key], dict):
            narrative[key] = sp[key]
    cd_prep = sp.get('cd_prep') or {}
    if not isinstance(cd_prep, dict):
        cd_prep = {}
    return narrative, cd_prep


def _load_narrative(toml_path: Path, species: str) -> dict:
    """Backwards-compat wrapper returning just the narrative dict."""
    narrative, _ = _load_narrative_and_cd_prep(toml_path, species)
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

    # Gamemaster is expensive to load; keep one handle across roots.
    gm = None

    for root in args.paths:
        # Resolve species + league + thresholds path.
        species = args.species
        league = 'great'
        if species is None:
            slug = root.name if root.is_dir() else root.parent.name
            parsed = _infer_species_league_from_slug(slug)
            if parsed is None:
                print(f'[skip] {root}: could not infer species from slug',
                      file=sys.stderr)
                continue
            species, league = parsed
        else:
            slug = root.name if root.is_dir() else root.parent.name
            parsed = _infer_species_league_from_slug(slug)
            if parsed is not None:
                league = parsed[1]

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

        narrative, cd_prep = _load_narrative_and_cd_prep(toml_path, species)

        # Auto-generate A-field prose from the dive's embedded score
        # data. Templates in auto_gen_narrative.py are data-driven and
        # deterministic; they fill only empty TOML fields (human
        # overrides always win). Two modes:
        #
        # * **CD mode** fires when cd_prep declares a CD fast move AND
        #   a distinct PvPoke-default exists to compare against — the
        #   templates narrate the CD-vs-baseline delta (Oinkologne,
        #   Tinkaton, etc.).
        # * **Standalone mode** fires otherwise (non-CD species like
        #   Aegislash, or species whose CD move matches the default).
        #   Templates narrate the species' top-scoring moveset by
        #   absolute win rate, skipping delta prose.
        #
        # The gate is now "does the dive have data" rather than "is
        # this a CD species" — see docs/jre_ryanswag_comparison.md §10
        # G5-B for the design motivation.
        cd_fast_moves = cd_prep.get('fast_moves') or []
        cd_fast = cd_fast_moves[0] if cd_fast_moves else None
        if root.is_dir():
            try:
                baseline_fast, _ = get_default_moveset(species, league)
            except (KeyError, Exception) as exc:
                baseline_fast = None
                print(f'[warn] {root}: no default moveset for '
                      f'{species!r} in {league}: {exc}',
                      file=sys.stderr)
            try:
                dive_data = _load_dive_data(root)
            except SystemExit as exc:
                dive_data = None
                print(f'[warn] {root}: dive data load failed: {exc}',
                      file=sys.stderr)
            if dive_data is not None:
                if gm is None:
                    gm = load_gamemaster()
                # In standalone mode (no cd_fast, or cd_fast equals
                # baseline_fast), pass None for both so the templates'
                # internal logic picks the top-scoring moveset.
                effective_cd = cd_fast if (cd_fast and cd_fast != baseline_fast) else None
                effective_base = baseline_fast if effective_cd else None
                auto_gen_narrative.fill_narrative_a_fields(
                    narrative, dive_data,
                    species=species,
                    cd_move_fast=effective_cd,
                    baseline_move_fast=effective_base,
                    league=league,
                    gm=gm,
                )

        if not narrative:
            print(f'[skip] {root}: TOML {toml_path.name} has no narrative '
                  f'blocks and no auto-gen content',
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
