#!/usr/bin/env python3
"""Retrofit envelope-position tags onto Notable-IVs composite cards.

The S4/P3 envelope-position metric
(``deep_dive_rendering._render_envelope_tag``) injects a
``<p class="dd-env-tag ...">`` line onto each Notable-IVs composite
card at dive-render time, summarizing how the card's members sit vs
the anchor-IV band at matching stat-product rank. Dives rendered
before the envelope-tag renderer change (per §11.3 F6 / §12.4 item 1
of ``docs/jre_ryanswag_comparison.md``) shipped without the tags
even though the ``envelopePositions`` data is already embedded in the
main ``index.html``'s ``DATA`` object.

This patcher does two deterministic edits to a shipped dive HTML:

  1. Append the ``.dd-env-tag`` + 4 shape-specific CSS rules to the
     first ``<style>`` block, scoped by a fingerprint comment so the
     injection is idempotent.
  2. For each Notable-IVs composite card
     (``<div class="dd-rec-card ..." id="notable-...">`` whose ``<h4>``
     category name contains ``∩``), look up the card's envelope entry
     in ``data.envelopePositions["<featured_moveset>"]`` and inject
     the tag HTML from ``_render_envelope_tag`` immediately after the
     card's subtitle ``<p class="dd-small dd-prose">`` line.

Idempotent via the fingerprint ``/* ENVELOPE_TAGS_v1 */`` on the
injected CSS block. Split ``index_m*.html`` files carry no
``envelopePositions`` data (only the main dive's featured moveset is
populated at render time); they are reported as ``[skip] no envelope
data`` rather than treated as errors.

Usage::

    python scripts/patch_dive_envelope_tags.py PATH [PATH ...]
    python scripts/patch_dive_envelope_tags.py --dry-run PATH

Matches the ``patch_dive_slayer_help.py`` pattern: fingerprinted,
single-origin CSS (kept in sync with the ``dd-env-*`` block in
``scripts/deep_dive_rendering.py`` around line 317-327), regex
injection anchored on surgically-specific markup so unrelated
card-like structures elsewhere in the HTML can't match.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
sys.path.insert(0, str(REPO_ROOT / 'src'))

from deep_dive_rendering import _render_envelope_tag  # type: ignore[import-not-found]


FINGERPRINT = '/* ENVELOPE_TAGS_v1 */'

# CSS mirrors ``scripts/deep_dive_rendering.py`` lines 317-327. Keep
# in sync -- the renderer's inline CSS block is canonical; this copy
# backfills pre-F6 dives. Later-defined-wins CSS cascade means appending
# to the existing <style> is safe even if future renderer changes
# introduce new variants (the old ones stay covered).
_CSS_BLOCK = (
    '\n' + FINGERPRINT + '\n'
    '/* Envelope-position tag CSS injected by\n'
    '   scripts/patch_dive_envelope_tags.py. Kept in sync with the\n'
    '   dd-env-* block in scripts/deep_dive_rendering.py (~line 317). */\n'
    '.dd-env-tag { font-size:0.82rem; margin:2px 0 4px; padding:3px 8px;\n'
    '  border-radius:3px; border-left:3px solid transparent; cursor:help;\n'
    '  display:inline-block; }\n'
    '.dd-env-rider-top    { background:#132a1c; color:#9be89b; border-left-color:#3fb950; }\n'
    '.dd-env-elev-crosser { background:#162318; color:#7db87d; border-left-color:#2f8135; }\n'
    '.dd-env-dep-crosser  { background:#2a1e16; color:#d29922; border-left-color:#b07214; }\n'
    '.dd-env-rider-bottom { background:#2a181b; color:#e77173; border-left-color:#c04547; }\n'
)

# Notable-IVs card preamble: the ``id="notable-..."`` pin is what
# separates this from the other three dd-rec-card sites (tier cards,
# mirror-slayer cards, misc.) -- renderer line 1324 is the only place
# that emits the ``notable-`` id prefix.
_CARD_PATTERN = re.compile(
    r'(<div class="dd-rec-card[^"]*" id="notable-[^"]+">\s*'
    r'<h4>)([^<]+?)(\s*<span[^>]*>[^<]*</span></h4>\s*'
    r'<p class="dd-small dd-prose">[^<]*</p>)',
    re.DOTALL,
)

# var DATA = {...}; -- non-greedy ``.*?`` stops at the first ``});``.
# JSON has no ``});`` token so the non-greedy match is safe even on
# the 4MB+ DATA blob.
_DATA_PATTERN = re.compile(r'var DATA = (\{.*?\});', re.DOTALL)


def _extract_envelope_positions(html: str) -> dict | None:
    """Return the featured-moveset envelope dict from DATA, or None.

    Only the first key in ``envelopePositions`` is used. At dive-render
    time the renderer writes one entry per moveset_idx, but currently
    only the main featured moveset (``'0'``) is populated in shipped
    HTMLs; per-moveset split files don't carry envelope data at all.
    """
    m = _DATA_PATTERN.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    ep = data.get('envelopePositions')
    if not isinstance(ep, dict) or not ep:
        return None
    return ep[sorted(ep.keys())[0]]


def _inject_css(html: str) -> tuple[str, bool]:
    """Append the envelope-tag CSS to the first ``<style>`` block.

    No-op if the fingerprint is already present. Returns
    ``(patched, changed)``.
    """
    if FINGERPRINT in html:
        return html, False
    m = re.search(r'<style>(.*?)</style>', html, re.DOTALL)
    if not m:
        return html, False
    patched = html[:m.end(1)] + _CSS_BLOCK + html[m.end(1):]
    return patched, True


def _inject_tags(html: str, envelope_positions: dict) -> tuple[str, int, int]:
    """Insert envelope tags after eligible composite-card subtitles.

    Composite-only: matches the renderer's ``cat.kind != 'matchup'``
    gate via the ``∩`` marker (composites are the only IV category
    kind with that symbol in the name). Returns
    ``(patched, n_injected, n_composite_seen)``. ``n_composite_seen``
    counts composite cards in the HTML regardless of whether their
    envelope shape is renderable -- ``sparse`` shapes (too few
    members/anchors) render to ``''`` and are counted as seen but
    not injected.
    """
    n_inject = 0
    n_seen = 0

    def repl(m: re.Match) -> str:
        nonlocal n_inject, n_seen
        cat_name = m.group(2).strip()
        if '∩' not in cat_name:
            return m.group(0)
        n_seen += 1
        env_entry = envelope_positions.get(cat_name)
        if not env_entry:
            return m.group(0)
        tag_html = _render_envelope_tag(env_entry)
        if not tag_html:
            return m.group(0)
        n_inject += 1
        return m.group(0) + tag_html

    return _CARD_PATTERN.sub(repl, html), n_inject, n_seen


def patch_html(content: str) -> tuple[str, bool, str]:
    """Return ``(patched, changed, note)``.

    ``note`` is human-readable outcome text: ``'already-patched'``,
    ``'no envelope data in DATA object'``, ``'no <style> block found'``,
    ``'no composite cards matched'``, or ``'N cards tagged'``.
    """
    if FINGERPRINT in content:
        return content, False, 'already-patched'
    envelope = _extract_envelope_positions(content)
    if not envelope:
        return content, False, 'no envelope data in DATA object'
    css_patched, css_ok = _inject_css(content)
    if not css_ok:
        return content, False, 'no <style> block found'
    tagged, n_inject, n_seen = _inject_tags(css_patched, envelope)
    if n_inject == 0:
        # CSS-only injection without any tags is noise; revert to the
        # original. The ``sparse`` envelope shape is a legitimate
        # "nothing to say" signal (too few members/anchors to compute
        # a reliable metric); all-sparse is common for dives with
        # tiny composite cards (1-2 IV members).
        if n_seen == 0:
            return content, False, 'no composite cards in HTML'
        return content, False, (
            f'{n_seen} composite cards found, all sparse (no renderable '
            'envelope shape -- expected when members/anchors are too few)')
    return tagged, True, f'{n_inject} of {n_seen} composite cards tagged'


def gather_html_files(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix == '.html':
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(p.glob('index*.html')))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('paths', nargs='+', type=Path,
                        help='HTML files or dive directories to patch in place.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would be patched without writing.')
    args = parser.parse_args()

    files = gather_html_files(args.paths)
    if not files:
        print('error: no .html files found under the given paths',
              file=sys.stderr)
        return 1

    n_patched = 0
    n_skipped = 0
    for f in files:
        try:
            content = f.read_text()
        except Exception as e:
            print(f'[skip] {f}: read failed: {e}', file=sys.stderr)
            n_skipped += 1
            continue
        new_content, changed, note = patch_html(content)
        if not changed:
            print(f'[skip] {f}: {note}')
            n_skipped += 1
            continue
        if args.dry_run:
            print(f'[would-patch] {f}: {note}')
        else:
            f.write_text(new_content)
            print(f'patched {f}: {note}')
        n_patched += 1

    tag = '(dry-run) ' if args.dry_run else ''
    print(f'\n{tag}patched {n_patched} file(s), skipped {n_skipped}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
