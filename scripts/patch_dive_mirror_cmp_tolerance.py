#!/usr/bin/env python3
"""Retrofit the Mirror CMP % tolerance fix into shipped dive HTMLs.

The shipped _computeMirrorCmpPct compares cohort atk values against a
per-IV atk with a strict ``<``, inheriting sub-0.01 float drift from the
cohort's full-precision atk computation. On Tinkaton UL the cohort
collapses to a single value of 142.8509983 while the max display-precision
IV atk is 142.85, so every IV reports 0% even though several IVs tie the
slayer benchmark at 2dp.

This patcher swaps the body of ``function _computeMirrorCmpPct(iv)`` with
a version that rounds both sides to 2dp and counts ties as beats. The
surrounding JS (``function`` keyword, the sort comparators that call
``_computeMirrorCmpPct``) is untouched.

Idempotent via the fingerprint comment ``/* MIRROR_CMP_TOLERANCE_v1 */``
inside the replacement block -- re-running is a no-op.

Usage:
    python scripts/patch_dive_mirror_cmp_tolerance.py PATH [PATH ...]
    python scripts/patch_dive_mirror_cmp_tolerance.py --dry-run PATH
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


FINGERPRINT = '/* MIRROR_CMP_TOLERANCE_v1 */'

# Matches the v1 body exactly as shipped by deep_dive_engine.js pre-fix.
# The body starts with ``{`` right after ``function _computeMirrorCmpPct(iv)``
# and ends at the matching closing ``}``. We anchor on the function header
# and the distinctive ``else break;  // sorted ascending; stop at first
# non-match`` line so we don't accidentally rewrite similar-shaped code.
OLD_BODY_RE = re.compile(
    r'function _computeMirrorCmpPct\(iv\) \{\s*'
    r'var cohort = DATA\.mirrorCohortAtk;\s*'
    r'if \(!cohort \|\| cohort\.length === 0\) return NaN;\s*'
    r'var myAtk = DATA\.ivAtk\[iv\];\s*'
    r'if \(!isFinite\(myAtk\)\) return NaN;\s*'
    r'var beaten = 0;\s*'
    r'for \(var i = 0; i < cohort\.length; i\+\+\) \{\s*'
    r'if \(cohort\[i\] < myAtk\) beaten\+\+;\s*'
    r'else break;[^\n]*\n\s*'
    r'\}\s*'
    r'return \(beaten / cohort\.length\) \* 100;\s*'
    r'\}',
    re.DOTALL,
)

NEW_BODY = (
    'function _computeMirrorCmpPct(iv) {  ' + FINGERPRINT + '\n'
    '  var cohort = DATA.mirrorCohortAtk;\n'
    '  if (!cohort || cohort.length === 0) return NaN;\n'
    '  var myAtk = DATA.ivAtk[iv];\n'
    '  if (!isFinite(myAtk)) return NaN;\n'
    '  // Round to 2dp so float drift in cohort atk (e.g. Tink UL 142.8509983\n'
    '  // vs display 142.85) stops lying. Ties count as beat since PvP CMP at\n'
    '  // equal atk resolves on priority or coin-flip, not a guaranteed loss.\n'
    '  var myAtkR = Math.round(myAtk * 100) / 100;\n'
    '  var beaten = 0;\n'
    '  for (var i = 0; i < cohort.length; i++) {\n'
    '    var cR = Math.round(cohort[i] * 100) / 100;\n'
    '    if (cR <= myAtkR) beaten++;\n'
    '    else break;\n'
    '  }\n'
    '  return (beaten / cohort.length) * 100;\n'
    '}'
)


def patch_html(content: str) -> tuple[str, bool]:
    """Return (patched_content, changed). Idempotent."""
    if FINGERPRINT in content:
        return content, False
    new_content, n = OLD_BODY_RE.subn(NEW_BODY, content, count=1)
    if n == 0:
        return content, False
    return new_content, True


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
    n_no_match = 0
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
        new_content, changed = patch_html(content)
        if not changed:
            print(f'[no-match] {f} (old _computeMirrorCmpPct body not found)',
                  file=sys.stderr)
            n_no_match += 1
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
          f'{n_no_match} without old pattern.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
