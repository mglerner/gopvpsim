#!/usr/bin/env python
"""Cross-check DEVELOPER_NOTES.md dev-count sentinels against live code.

DEVELOPER_NOTES.md carries six machine-readable scalars wrapped in
HTML-comment sentinels of the form ``<!-- sync:KEY -->VALUE<!-- /sync -->``
(see ``build_guides.py._load_verification_counts``). This script:

  - parses every sentinel pair out of the prose,
  - for each *derivable* key, computes the live value from code and
    asserts the sentinel matches,
  - for non-derivable keys (the PvPoke cross-check counts), sanity-
    checks the sentinel is a plausible positive integer,
  - exits 3 (``DRIFT_EXIT``) on any mismatch so pre-commit can block
    drift, and 1 when a live value could not be derived at all.

Derivable keys
--------------

``test_count``
    Run ``pytest --collect-only -q tests/`` and count the tests. The
    last line of the output is of the form ``"N tests collected in Xs"``;
    we parse N. Kept fast (a few seconds) so pre-commit stays cheap.

``type_chart_cells_verified``
    Import ``gopvpsim.moves.EFFECTIVENESS`` and sum the per-attacker
    inner-dict sizes. For an 18x18 type chart that's 324 cells.

Non-derivable keys (plausibility-checked only)
----------------------------------------------

``pvpoke_matchups_verified``, ``pvpoke_cells_verified``,
``pvpoke_cells_exact``, ``pvpoke_bugs_documented``
    These depend on manual cross-reference against PvPoke and can't be
    recomputed from code alone. We trust the sentinel but reject values
    that are clearly wrong (non-int, <= 0).

Usage
-----

    python scripts/verify_dev_counts.py
    python scripts/verify_dev_counts.py --quiet   # only emit mismatches
    python scripts/verify_dev_counts.py --update  # rewrite derivable sentinels
    python scripts/verify_dev_counts.py --notes PATH  # check that copy of the
        # notes (the hook passes its index export; live counts still come from
        # the working tree, and the every-key-present check is left to the
        # hook's index-consistent step 3)

Exit codes: 0 on full agreement; 3 (``DRIFT_EXIT``) on a mismatch, a
missing or implausible sentinel, or a sentinel ``--update`` could not
rewrite; 1 when the notes file is missing or a live value could not be
derived (no pytest in the venv, a test module that fails to import);
2 is argparse's usage error.

``--update`` (opt-in) turns the derivable-key check from a gate into a
fix: each derivable sentinel whose value disagrees with the live
derivation is rewritten in place in DEVELOPER_NOTES.md (old -> new is
printed) instead of being reported as drift.  Non-derivable keys are
never rewritten, and missing/implausible sentinels still fail.  Without
``--update`` behavior is unchanged: nothing is written and any drift
exits 3.

The flag exists because ``test_count`` is a serialization point --
parallel work lanes that each add tests otherwise race to hand-edit the
same sentinel line.  One explicit ``--update`` at the end of a batch
replaces N conflicting hand edits.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_NOTES_PATH = REPO_ROOT / 'DEVELOPER_NOTES.md'

_SENTINEL_RE = re.compile(
    r'<!--\s*sync:([A-Za-z_][A-Za-z0-9_]*)\s*-->(.+?)<!--\s*/sync\s*-->',
    flags=re.DOTALL,
)

DERIVABLE_KEYS = {'test_count', 'type_chart_cells_verified'}
PLAUSIBILITY_KEYS = {
    'pvpoke_matchups_verified',
    'pvpoke_cells_verified',
    'pvpoke_bugs_documented',
    # Renders publicly via guides/how-this-works {{dev:pvpoke_cells_exact}}.
    # Not derivable here (needs the full oracle-harness run, minutes);
    # re-derive with scripts/audit_oracle_harness.py when it drifts.
    # Registered 2026-08-06 after it sat as an unknown key while the
    # published guide showed a 2-cell-stale value (170 vs 172).
    'pvpoke_cells_exact',
}
ALL_KEYS = DERIVABLE_KEYS | PLAUSIBILITY_KEYS

# Exit code for drift. Distinct from 1 (a Python traceback, or a derivation
# that could not run: no pytest/certifi) and 2 (an argparse usage error) so
# the pre-commit hook can tell drift from a crash.
DRIFT_EXIT = 3


def _parse_sentinels(text: str) -> dict[str, int]:
    """Extract sentinel keys from DEVELOPER_NOTES.md as ints.

    A non-integer value is kept as its raw string so the verifier can
    flag it as implausible.
    """
    out: dict[str, int] = {}
    for m in _SENTINEL_RE.finditer(text):
        key = m.group(1)
        raw = m.group(2).strip()
        try:
            out[key] = int(raw)
        except ValueError:
            out[key] = raw  # type: ignore[assignment]
    return out


def _rewrite_sentinel(text: str, key: str, value: int) -> tuple[str, int]:
    """Return ``(new_text, n_rewritten)`` with ``sync:key``'s value replaced.

    Only the text *between* the sentinel comments changes; the comment
    markers and any whitespace padding around the value are preserved
    verbatim, so the result still matches ``_parse_sentinels``.

    The value group is ``[^<]*?`` rather than ``.+?``: a match must never
    be able to cross a ``<!--``.  If a closing ``<!-- /sync -->`` is ever
    lost to a hand-edit, a ``.+?`` match would run on to the *next* key's
    closing marker and the rewrite would silently delete the intervening
    prose and that whole sentinel.  With ``[^<]*?`` a malformed span
    simply doesn't match, so nothing is rewritten and the caller reports
    it.
    """
    pattern = re.compile(
        r'(<!--\s*sync:' + re.escape(key) + r'\s*-->)'
        r'([^<]*?)(<!--\s*/sync\s*-->)'
    )

    def _sub(m: re.Match) -> str:
        inner = m.group(2)
        if inner.strip():
            lead = inner[:len(inner) - len(inner.lstrip())]
            trail = inner[len(inner.rstrip()):]
        else:
            # All-whitespace body: lstrip() and rstrip() would each claim
            # the whole run, doubling the padding.
            lead, trail = inner, ''
        return f'{m.group(1)}{lead}{value}{trail}{m.group(3)}'

    return pattern.subn(_sub, text)


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def _derive_test_count() -> int:
    """Run pytest --collect-only and parse the tests-collected total."""
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '--collect-only', '-q',
         str(REPO_ROOT / 'tests')],
        cwd=REPO_ROOT,
        capture_output=True, text=True, check=False,
    )
    # The final non-empty stdout line is ``"N tests collected in Xs"``.
    # pytest colorizes it under color-forcing environments (FORCE_COLOR,
    # some terminals), which broke the match twice on 2026-08-16/17 --
    # strip ANSI SGR sequences before parsing.
    stdout = _ANSI_RE.sub('', result.stdout)
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError(
            f'pytest --collect-only produced no output; '
            f'stderr={result.stderr!r}')
    tail = lines[-1]
    # A module that fails to import still yields a tail -- "N tests
    # collected, 1 error in Xs", exit 2 -- and N is the PARTIAL count. Until
    # 2026-10-25 that read as drift (or passed, or was written by --update).
    if result.returncode != 0 or re.search(r'\d+\s+errors?\b', tail):
        raise RuntimeError(
            f'pytest --collect-only exited {result.returncode}: {tail!r}')
    m = re.match(r'^(\d+)\s+tests?\s+collected\b', tail)
    if not m:
        raise RuntimeError(
            f"couldn't parse pytest collect-only tail: {tail!r}")
    return int(m.group(1))


def _derive_type_chart_cells() -> int:
    """Sum per-attacker inner-dict sizes in EFFECTIVENESS."""
    sys.path.insert(0, str(REPO_ROOT / 'src'))
    from gopvpsim.moves import EFFECTIVENESS  # type: ignore[import-not-found]
    return sum(len(v) for v in EFFECTIVENESS.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--quiet', action='store_true',
                        help='Only print mismatches; stay silent on agreement.')
    parser.add_argument('--update', action='store_true',
                        help='Rewrite drifted DERIVABLE sentinels in '
                             'DEVELOPER_NOTES.md instead of failing on them. '
                             'Non-derivable keys are never touched.')
    parser.add_argument('--notes', type=Path, default=None,
                        help='DEVELOPER_NOTES.md to check (the pre-commit hook '
                             'passes its index export). Live counts always come '
                             'from the working tree; the every-key-present check '
                             'is skipped (see below).')
    args = parser.parse_args()
    if args.update and args.notes is not None:
        # --update would rewrite the COPY and report success while the real
        # notes stay stale (the hook's export is deleted on exit).
        parser.error('--update rewrites only the default DEVELOPER_NOTES.md; drop --notes')
    notes_path = args.notes if args.notes is not None else DEV_NOTES_PATH

    if not notes_path.is_file():
        print(f'error: {notes_path} missing', file=sys.stderr)
        return 1

    text = notes_path.read_text()
    sentinels = _parse_sentinels(text)

    problems: list[str] = []

    # 1. Every expected key must exist. Skipped under --notes: ALL_KEYS is
    # this WORKING-TREE script's, so an unstaged new key would block every
    # unrelated commit; the hook's step 3 pins presence index-against-index.
    if args.notes is None:
        missing = ALL_KEYS - sentinels.keys()
        for key in sorted(missing):
            problems.append(f'missing sentinel: sync:{key}')

    # 2. Non-derivable keys: plausibility only.
    for key in sorted(PLAUSIBILITY_KEYS & sentinels.keys()):
        val = sentinels[key]
        if not isinstance(val, int) or val <= 0:
            problems.append(
                f'{key}: implausible sentinel value {val!r} '
                f'(expected positive int)')
        elif not args.quiet:
            print(f'  {key}: {val} (trusted)')

    # 3. Derivable keys: recompute and compare (and rewrite under --update).
    # Names are resolved here rather than at import time so tests can
    # monkeypatch the derivations.
    derivers = (
        ('test_count', _derive_test_count),
        ('type_chart_cells_verified', _derive_type_chart_cells),
    )
    dirty = False
    derive_failures: list[str] = []
    for key, derive in derivers:
        if key not in sentinels:
            continue
        val = sentinels[key]
        try:
            live = derive()
        except Exception as exc:  # noqa: BLE001 - environmental (no pytest, no certifi)
            derive_failures.append(f'{key}: derivation failed ({exc})')
            continue
        if val == live:
            if not args.quiet:
                print(f'  {key}: {val} (matches live)')
        elif args.update:
            text, n = _rewrite_sentinel(text, key, live)
            if n:
                dirty = True
                print(f'  {key}: {val} -> {live} (updated DEVELOPER_NOTES.md)')
            else:
                # Reachable when the sentinel pair is malformed (e.g. a
                # lost closing marker): the narrow rewrite pattern refuses
                # to match, so we fail loudly instead of eating prose.
                problems.append(f'{key}: could not rewrite sentinel')
        else:
            problems.append(
                f'{key}: sentinel {val} != live {live} '
                f'(update DEVELOPER_NOTES.md)')

    if dirty:
        notes_path.write_text(text)

    # 4. Unknown sentinel keys are informational - print but don't fail.
    unknown = sentinels.keys() - ALL_KEYS
    if unknown and not args.quiet:
        for key in sorted(unknown):
            print(f'  {key}: {sentinels[key]} (unknown key, not verified)')

    if derive_failures:
        # Not drift: the live value could not be computed at all (missing
        # pytest/certifi, a collection error). Exit 1 so the pre-commit hook
        # reports an environment problem rather than a stale sentinel. Any
        # drift found alongside is still printed so one run shows everything.
        print('\nERROR: dev-count derivation failed (environment, not drift):',
              file=sys.stderr)
        for d in derive_failures:
            print(f'  - {d}', file=sys.stderr)
        for p in problems:
            print(f'  - (also) {p}', file=sys.stderr)
        return 1

    if problems:
        print('\nERROR: dev-count drift detected:', file=sys.stderr)
        for p in problems:
            print(f'  - {p}', file=sys.stderr)
        print(
            '\nFix by updating the relevant '
            '<!-- sync:KEY -->VALUE<!-- /sync --> pair in DEVELOPER_NOTES.md, '
            'or adjust the derivation in scripts/verify_dev_counts.py '
            "if the metric's definition has changed.",
            file=sys.stderr)
        return DRIFT_EXIT

    if not args.quiet:
        print('\nAll dev-count sentinels verified.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
