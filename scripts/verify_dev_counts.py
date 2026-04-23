#!/usr/bin/env python
"""Cross-check DEVELOPER_NOTES.md dev-count sentinels against live code.

DEVELOPER_NOTES.md carries five machine-readable scalars wrapped in
HTML-comment sentinels of the form ``<!-- sync:KEY -->VALUE<!-- /sync -->``
(see ``build_guides.py._load_verification_counts``). This script:

  - parses every sentinel pair out of the prose,
  - for each *derivable* key, computes the live value from code and
    asserts the sentinel matches,
  - for non-derivable keys (the PvPoke cross-check counts), sanity-
    checks the sentinel is a plausible positive integer,
  - exits 1 on any mismatch so pre-commit can block drift.

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
``pvpoke_bugs_documented``
    These depend on manual cross-reference against PvPoke and can't be
    recomputed from code alone. We trust the sentinel but reject values
    that are clearly wrong (non-int, <= 0).

Usage
-----

    python scripts/verify_dev_counts.py
    python scripts/verify_dev_counts.py --quiet   # only emit mismatches

Exit code is 0 on full agreement, 1 on any mismatch or missing sentinel.
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
}
ALL_KEYS = DERIVABLE_KEYS | PLAUSIBILITY_KEYS


def _parse_sentinels(text: str) -> dict[str, int]:
    """Extract sentinel keys from DEVELOPER_NOTES.md as ints.

    Non-integer values are rejected (returned as ``None`` slot) so the
    verifier can flag them.
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


def _derive_test_count() -> int:
    """Run pytest --collect-only and parse the tests-collected total."""
    result = subprocess.run(
        ['python', '-m', 'pytest', '--collect-only', '-q',
         str(REPO_ROOT / 'tests')],
        cwd=REPO_ROOT,
        capture_output=True, text=True, check=False,
    )
    # The final non-empty stdout line is ``"N tests collected in Xs"``.
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError(
            f'pytest --collect-only produced no output; '
            f'stderr={result.stderr!r}')
    tail = lines[-1]
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
    args = parser.parse_args()

    if not DEV_NOTES_PATH.is_file():
        print(f'error: {DEV_NOTES_PATH} missing', file=sys.stderr)
        return 1

    sentinels = _parse_sentinels(DEV_NOTES_PATH.read_text())

    problems: list[str] = []

    # 1. Every expected key must exist.
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

    # 3. Derivable keys: recompute and compare.
    if 'test_count' in sentinels:
        val = sentinels['test_count']
        try:
            live = _derive_test_count()
        except Exception as exc:  # pragma: no cover - environmental
            problems.append(f'test_count: derivation failed ({exc})')
        else:
            if val != live:
                problems.append(
                    f'test_count: sentinel {val} != live {live} '
                    f'(update DEVELOPER_NOTES.md)')
            elif not args.quiet:
                print(f'  test_count: {val} (matches live)')

    if 'type_chart_cells_verified' in sentinels:
        val = sentinels['type_chart_cells_verified']
        try:
            live = _derive_type_chart_cells()
        except Exception as exc:  # pragma: no cover - environmental
            problems.append(
                f'type_chart_cells_verified: derivation failed ({exc})')
        else:
            if val != live:
                problems.append(
                    f'type_chart_cells_verified: sentinel {val} != '
                    f'live {live} (update DEVELOPER_NOTES.md)')
            elif not args.quiet:
                print(f'  type_chart_cells_verified: {val} (matches live)')

    # 4. Unknown sentinel keys are informational - print but don't fail.
    unknown = sentinels.keys() - ALL_KEYS
    if unknown and not args.quiet:
        for key in sorted(unknown):
            print(f'  {key}: {sentinels[key]} (unknown key, not verified)')

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
        return 1

    if not args.quiet:
        print('\nAll dev-count sentinels verified.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
