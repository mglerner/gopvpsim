#!/usr/bin/env python3
"""Retrofit column-header tooltips onto the Slayer IVs "of yours" table.

The Top IVs table already carries ``title=`` hover text on its three
mirror-adjacent columns (Top-Mirror CMP %, Matchups Kept, Mirror Slayer
CMP %) via the per-column ``help`` field on ``_summaryColumns()``. The
Slayer IVs "of yours" table, rendered via ``renderSection`` with an
``extras`` array, had no equivalent -- the two matching columns there
were missing the same hover text.

This patcher does four deterministic edits to a shipped dive HTML:

  1. Declare three ``HELP_*`` constants once near the top of the inline
     JS block. The same strings were previously inlined three times in
     ``_summaryColumns()``; the declaration makes the source
     single-origin. The emitted ``title=`` text on each column header is
     still a full copy (browsers need it there) but the JS source no
     longer carries duplicate literals that would drift.
  2. Replace the three inline help-string literals in
     ``_summaryColumns()`` with references to the new constants.
  3. Teach the ``renderSection`` extras header loop to emit ``title=``
     when the extras entry declares a ``help`` field.
  4. Add ``help: HELP_TOP_MIRROR_CMP`` / ``help: HELP_MATCHUPS_KEPT``
     to the two Slayer IVs extras columns.

Idempotent via the fingerprint ``/* SLAYER_HELP_v1 */`` on the HELP_*
declaration block -- re-running a patched file is a no-op. A file that
has been patched but shows any of the four OLD patterns missing is
reported as ``[partial-match]``; this should not happen in practice
since all four edits are emitted by the same commit, but it keeps the
patcher honest about state it doesn't understand.

Usage:
    python scripts/patch_dive_slayer_help.py PATH [PATH ...]
    python scripts/patch_dive_slayer_help.py --dry-run PATH
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


FINGERPRINT = '/* SLAYER_HELP_v1 */'

# Edit 1: insert the HELP_* declaration block right after the nIvs/nS/nO
# line at the top of the IIFE. Anchors on the full line so accidental
# partial matches elsewhere don't trigger.
ANCHOR_VAR_NIVS = (
    'var nIvs = DATA.nIvs, nS = DATA.nScenarios, nO = DATA.nOpponents;\n'
)
HELP_DECLS = (
    ANCHOR_VAR_NIVS
    + '\n'
    '// Column-header tooltip strings for the three mirror-adjacent metrics.\n'
    '// ' + FINGERPRINT + ' Declared once so Top IVs and Slayer IVs tables\n'
    '// share a single source of truth; the emitted title= still inlines the\n'
    '// text, but the JS source no longer carries duplicate literals that\n'
    '// would drift as copy evolves.\n'
    "var HELP_MIRROR_SLAYER_CMP = '% of the Nash-converged slayer cohort whose attack you at least tie. Niche; often collapses to all-0 or all-100.';\n"
    "var HELP_TOP_MIRROR_CMP = '% of the top-50 same-species IVs in this dive whose attack you at least tie. Ladder-realistic mirror cohort.';\n"
    "var HELP_MATCHUPS_KEPT = 'Expected non-mirror matchups won, sampling scenarios uniformly: per opponent, (scenarios won / nSel) summed over opponents. Integer when a single scenario is selected; fractional when averaging. Denominator excludes the mirror entry.';\n"
)

# Edit 2a: Top-Mirror CMP inline help -> reference the constant.
OLD_TOP_MIRROR_INLINE = (
    "      help: '% of the top-50 same-species IVs in this dive whose attack "
    "you at least tie. Ladder-realistic mirror cohort.' },"
)
NEW_TOP_MIRROR_INLINE = "      help: HELP_TOP_MIRROR_CMP },"

# Edit 2b: Matchups Kept inline help.
OLD_MATCHUPS_INLINE = (
    "      help: 'Expected non-mirror matchups won, sampling scenarios "
    "uniformly: per opponent, (scenarios won / nSel) summed over opponents. "
    "Integer when a single scenario is selected; fractional when averaging. "
    "Denominator excludes the mirror entry.' },"
)
NEW_MATCHUPS_INLINE = "      help: HELP_MATCHUPS_KEPT },"

# Edit 2c: Mirror Slayer CMP inline help.
OLD_MIRROR_SLAYER_INLINE = (
    "                help: '% of the Nash-converged slayer cohort whose "
    "attack you at least tie. Niche; often collapses to all-0 or all-100.' });"
)
NEW_MIRROR_SLAYER_INLINE = "                help: HELP_MIRROR_SLAYER_CMP });"

# Edit 3: renderSection extras header loop picks up `help` -> title=.
OLD_EXTRAS_HDR_LOOP = (
    "      for (var xh = 0; xh < extras.length; xh++) {\n"
    "        var _xhCls = extras[xh].cls ? (' class=\"' + extras[xh].cls + '\"') : '';\n"
    "        h += '<th' + _xhCls + '>' + escapeHtml(extras[xh].header) + '</th>';\n"
    "      }"
)
NEW_EXTRAS_HDR_LOOP = (
    "      for (var xh = 0; xh < extras.length; xh++) {\n"
    "        var _xhCls = extras[xh].cls ? (' class=\"' + extras[xh].cls + '\"') : '';\n"
    "        var _xhTitle = extras[xh].help ? (' title=\"' + extras[xh].help.replace(/\"/g, '&quot;') + '\"') : '';\n"
    "        h += '<th' + _xhCls + _xhTitle + '>' + escapeHtml(extras[xh].header) + '</th>';\n"
    "      }"
)

# Edit 4: Slayer IVs extras -- add help on the two new columns.
OLD_SLAYER_EXTRAS = (
    "      { header: 'Top-Mirror CMP %', cell: _cellTopMirror },\n"
    "      { header: 'Matchups Kept',    cell: _cellMatchupsKept }"
)
NEW_SLAYER_EXTRAS = (
    "      { header: 'Top-Mirror CMP %', cell: _cellTopMirror,    help: HELP_TOP_MIRROR_CMP },\n"
    "      { header: 'Matchups Kept',    cell: _cellMatchupsKept, help: HELP_MATCHUPS_KEPT }"
)

EDITS = [
    ('HELP_* declarations',   ANCHOR_VAR_NIVS,           HELP_DECLS),
    ('Top-Mirror inline',     OLD_TOP_MIRROR_INLINE,     NEW_TOP_MIRROR_INLINE),
    ('Matchups Kept inline',  OLD_MATCHUPS_INLINE,       NEW_MATCHUPS_INLINE),
    ('Mirror Slayer inline',  OLD_MIRROR_SLAYER_INLINE,  NEW_MIRROR_SLAYER_INLINE),
    ('extras header loop',    OLD_EXTRAS_HDR_LOOP,       NEW_EXTRAS_HDR_LOOP),
    ('Slayer IVs extras',     OLD_SLAYER_EXTRAS,         NEW_SLAYER_EXTRAS),
]


def patch_html(content: str) -> tuple[str, bool, list[str]]:
    """Return (patched_content, changed, missing_edits).

    Idempotent: if FINGERPRINT already present, returns (content, False, []).
    If any edit's OLD pattern is missing, appends its label to
    missing_edits and skips that edit; the caller decides whether to
    abort or report partial state.
    """
    if FINGERPRINT in content:
        return content, False, []
    missing: list[str] = []
    # Check each OLD pattern exists exactly once before mutating, so we
    # never produce a half-patched file if a later edit would fail.
    for label, old, _new in EDITS:
        count = content.count(old)
        if count == 0:
            missing.append(f'{label} (not found)')
        elif count > 1 and label != 'HELP_* declarations':
            # The nIvs anchor is also the key for edit 1; we match-count
            # on the full text which should appear once. Any other edit
            # that appears multiple times signals an unknown HTML shape.
            missing.append(f'{label} (ambiguous: {count} matches)')
    if missing:
        return content, False, missing
    new_content = content
    for _label, old, new in EDITS:
        new_content = new_content.replace(old, new, 1)
    return new_content, True, []


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
                        help='HTML files or directories to patch in place.')
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
    n_partial = 0
    for f in files:
        try:
            content = f.read_text()
        except Exception as e:
            print(f'[skip] {f}: read failed: {e}', file=sys.stderr)
            continue
        if FINGERPRINT in content:
            print(f'[already-patched] {f}')
            n_skipped += 1
            continue
        new_content, changed, missing = patch_html(content)
        if missing:
            print(f'[partial-match] {f}: {", ".join(missing)}',
                  file=sys.stderr)
            n_partial += 1
            continue
        if not changed:
            # Belt-and-suspenders: patch_html returns False here only if
            # FINGERPRINT was already present, which we handled above.
            continue
        if args.dry_run:
            print(f'[would-patch] {f}')
        else:
            f.write_text(new_content)
            print(f'patched {f}')
        n_patched += 1

    tag = '(dry-run) ' if args.dry_run else ''
    print(f'\n{tag}patched {n_patched} file(s), '
          f'skipped {n_skipped} already-patched, '
          f'{n_partial} partial/unknown shape.')
    return 0 if n_partial == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
