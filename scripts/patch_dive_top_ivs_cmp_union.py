#!/usr/bin/env python3
"""Retrofit the Top IVs table's row-set union (sort ∪ Mirror CMP %) into
already-shipped dive HTMLs.

The f76a33e engine.js change widens the Top IVs table's row set from
"top N by the active sort" to "top N by the active sort ∪ top N by
Mirror CMP %" (deduplicated, re-sorted by the active column for
display). This surfaces IVs picked specifically for CMP coverage —
those lose the Y Rank ranking and are invisible under the default
"top 10 by battle score" cut. Future dives bake the new code at
dive-generation time.

Shipped dive HTMLs have the old engine.js inlined and would need
the new row-selection logic patched in. Rather than re-inject the
full ~100-line updateSummaryTable body, this patcher does a
surgical regex replacement of the single problem line:

    var top = indices.slice(0, N);

...with the new union-building block. The surrounding function is
untouched; all the referenced helpers (_computeMirrorCmpPct,
currentYIsSparse, summarySort, yValues, nIvs, cmp) are in scope
because they're defined earlier in the same inlined engine.js.

Idempotent via fingerprint comment ``/* TOP_IVS_CMP_UNION_v1 */``
inside the replacement block — re-running the patcher on an
already-patched HTML is a no-op.

Usage:
    python scripts/patch_dive_top_ivs_cmp_union.py PATH [PATH ...]
    python scripts/patch_dive_top_ivs_cmp_union.py --dry-run PATH
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


FINGERPRINT = '/* TOP_IVS_CMP_UNION_v2 */'
OLD_FINGERPRINT_V1 = '/* TOP_IVS_CMP_UNION_v1 */'

OLD_LINE = 'var top = indices.slice(0, N);'

# Matches the ENTIRE v1 block (from the v1 fingerprint comment through
# the closing ``var top = _unionList;``). Used to migrate v1-patched
# HTMLs to v2 in place. Both v1 and v2 blocks end at the same line, so
# the substitution is clean.
V1_BLOCK_RE = re.compile(
    re.escape(OLD_FINGERPRINT_V1) + r'.*?var top = _unionList;',
    re.DOTALL,
)

REPLACEMENT = FINGERPRINT + r"""
  // Row-set: union of top-N by the active sort column AND (when a
  // Mirror-CMP cohort is available AND the active sort isn't already
  // Mirror CMP %) top-N by Mirror CMP %. Surfaces IVs picked
  // specifically for CMP coverage. Re-sorted by active column for
  // display order.
  //
  // v2: drop IVs with CMP <= 0 from the CMP bucket. v1 sorted all
  // IVs by CMP desc with stable fallback, which meant that when MOST
  // IVs had CMP=0 (cohort atk range exceeds their atk), the "top N
  // by CMP" bucket filled with the first N by IV index (typically
  // 0/0/X junk). CMP=0 means "beats nothing in the cohort" = not a
  // tradeoff-frontier row.
  var _seen = {};
  var _unionList = [];
  function _addIfRoomCmp(iv) {
    if (_seen[iv]) return false;
    if (currentYIsSparse &&
        (summarySort.col === 'yrank' || summarySort.col === 'yval') &&
        !isFinite(yValues[iv])) return false;
    _seen[iv] = true;
    _unionList.push(iv);
    return true;
  }
  for (var _pi = 0, _added = 0; _pi < indices.length && _added < N; _pi++) {
    if (_addIfRoomCmp(indices[_pi])) _added++;
  }
  if (!!(DATA.mirrorCohortAtk && DATA.mirrorCohortAtk.length > 0) &&
      summarySort.col !== 'mirrorCmp') {
    var _cmpIdx = [];
    for (var _k3 = 0; _k3 < nIvs; _k3++) _cmpIdx.push(_k3);
    _cmpIdx.sort(function(a, b) {
      var va = _computeMirrorCmpPct(a), vb = _computeMirrorCmpPct(b);
      var na = isNaN(va), nb = isNaN(vb);
      if (na && nb) return 0;
      if (na) return 1;
      if (nb) return -1;
      return vb - va;
    });
    for (var _pi2 = 0, _added2 = 0;
         _pi2 < _cmpIdx.length && _added2 < N;
         _pi2++) {
      var _cmpVal = _computeMirrorCmpPct(_cmpIdx[_pi2]);
      if (!isFinite(_cmpVal) || _cmpVal <= 0) break;
      if (_addIfRoomCmp(_cmpIdx[_pi2])) _added2++;
    }
  }
  _unionList.sort(cmp);
  var top = _unionList;"""


def patch_html(content: str) -> tuple[str, bool]:
    """Return (patched_content, changed). Idempotent across v1 and v2.

    Three cases:

    * Already v2: return unchanged.
    * v1-patched: substitute the v1 block with the v2 block (both end
      at ``var top = _unionList;``, so the regex cleanly swaps them).
    * Unpatched: substitute the original ``var top = indices.slice(0,
      N);`` with the v2 block.
    """
    if FINGERPRINT in content:
        return content, False
    if OLD_FINGERPRINT_V1 in content:
        new_content, n = V1_BLOCK_RE.subn(REPLACEMENT.lstrip(), content,
                                          count=1)
        if n == 0:
            # v1 fingerprint present but block malformed; give up.
            return content, False
        return new_content, True
    if OLD_LINE not in content:
        return content, False  # not a dive HTML that embeds the engine
    new_content = content.replace(OLD_LINE, REPLACEMENT, 1)
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
        new_content, changed = patch_html(content)
        if FINGERPRINT in content:
            print(f'[already-patched] {f}')
            n_skipped += 1
            continue
        if not changed:
            print(f'[no-match] {f} (old row-select line not found)',
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
