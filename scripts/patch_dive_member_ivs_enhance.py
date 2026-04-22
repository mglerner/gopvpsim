#!/usr/bin/env python3
"""Retrofit the 20e7bd1 Member IVs enhancements into shipped dive HTMLs.

The 20e7bd1 renderer change added two pieces to the Member IVs table
inside each Threshold Tier card:

1. **Full-list tooltips** on the Net flips column — drops the old
   ``+N more`` cap so mirror-specific matchups (``Tinkaton 1v1`` /
   ``Tinkaton 2v2`` / etc.) land visibly, unblocking role-specific
   IV picking.
2. **Three per-shield Score Δ columns** (0v0 Δ, 1v1 Δ, 2v2 Δ) vs
   the rank-1-by-stat-product IV, so a reader can see the role
   split without opening separate per-scenario views.

Both changes live in ``scripts/deep_dive_rendering.py::render_threshold_tier_cards``
and apply to *future* dives at render time. For already-shipped
dives we retrofit by injecting a ``<script>`` block that:

* waits for the existing ``_scoresReady`` promise (the same decoder
  the rest of the page uses to inflate ``SCORES_GZ``),
* walks every ``<table>`` inside a ``.dd-flip-detail`` block,
* adds 3 column headers + 3 cells per row,
* rewrites each row's Net flips ``title=""`` attribute with the
  full gained/lost list re-derived from the IV's scores vs the
  pvpoke-reference IV.

All inputs (SCORES_GZ, DATA.rank1RefIvIdx, DATA.pvpokeRefIvIdx,
DATA.opponents, DATA.scenarios, DATA.ivA/D/S) are already embedded
in every shipped dive HTML, so no re-dive is needed.

Idempotent via the fingerprint comment
``<!-- MEMBER_IVS_ENHANCE_v1 -->``: re-running the patcher on an
already-enhanced HTML is a no-op.

Usage:
    python scripts/patch_dive_member_ivs_enhance.py PATH [PATH ...]
    python scripts/patch_dive_member_ivs_enhance.py --dry-run PATH

PATH can be a single .html file or a directory (walks for index*.html).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


FINGERPRINT = '<!-- MEMBER_IVS_ENHANCE_v1 -->'


JS_BLOCK = r"""<script>
// MEMBER_IVS_ENHANCE_v1 — retrofit tooltip un-truncation + per-shield
// Score Δ columns onto already-shipped dive HTMLs. Runs once at page
// load after SCORES decompression; idempotent via the fingerprint
// comment above this block.
(function() {
  if (window.__memberIvsEnhanceRan) return;
  window.__memberIvsEnhanceRan = true;
  if (typeof _scoresReady === 'undefined') return;
  _scoresReady.then(function() {
    try { enhanceMemberIvsTables(); } catch (e) {
      console.warn('member-ivs-enhance failed:', e);
    }
  });

  function enhanceMemberIvsTables() {
    if (typeof DATA === 'undefined' || typeof SCORES === 'undefined') return;
    var scores = SCORES['0_pvpoke'];
    if (!scores) return;
    var nIvs = DATA.nIvs, nS = DATA.nScenarios, nO = DATA.nOpponents;
    var rank1 = DATA.rank1RefIvIdx;
    var pvpoke = DATA.pvpokeRefIvIdx;
    if (rank1 == null || pvpoke == null) return;

    // Target scenarios (0v0, 1v1, 2v2) → indices in DATA.scenarios.
    var targetLabels = ['0v0', '1v1', '2v2'];
    var targetIdx = [[0,0],[1,1],[2,2]].map(function(p) {
      for (var i = 0; i < (DATA.scenarios || []).length; i++) {
        if (DATA.scenarios[i][0] === p[0] && DATA.scenarios[i][1] === p[1]) {
          return i;
        }
      }
      return -1;
    });

    function scenAvg(iv, si) {
      if (si < 0) return null;
      var sum = 0, base = iv * nS * nO + si * nO;
      for (var oi = 0; oi < nO; oi++) sum += scores[base + oi];
      return sum / nO;
    }
    var r1Avgs = targetIdx.map(function(si) {
      return si >= 0 ? scenAvg(rank1, si) : null;
    });

    // Build reverse lookup: "atk/def/hp" → IV index. This matches
    // the first cell of each Member IVs row.
    var labelToIdx = {};
    for (var iv = 0; iv < nIvs; iv++) {
      var key = DATA.ivA[iv] + '/' + DATA.ivD[iv] + '/' + DATA.ivS[iv];
      labelToIdx[key] = iv;
    }

    // Compute full gained/lost list for one IV vs the pvpoke-reference.
    // Matches what render_threshold_tier_cards does server-side, but
    // client-side so the shipped HTML doesn't need new server data.
    function flipDetail(iv, ref) {
      var gains = [], losses = [];
      for (var si = 0; si < nS; si++) {
        var s0 = DATA.scenarios[si][0], s1 = DATA.scenarios[si][1];
        var scenLabel = s0 + 'v' + s1;
        for (var oi = 0; oi < nO; oi++) {
          var ivScore = scores[iv * nS * nO + si * nO + oi];
          var refScore = scores[ref * nS * nO + si * nO + oi];
          var ivWin = ivScore >= 500;
          var refWin = refScore >= 500;
          if (ivWin && !refWin) {
            gains.push(DATA.opponents[oi] + ' ' + scenLabel);
          } else if (!ivWin && refWin) {
            losses.push(DATA.opponents[oi] + ' ' + scenLabel);
          }
        }
      }
      return {gains: gains, losses: losses};
    }

    // Walk every Member IVs table inside a .dd-flip-detail block.
    var tables = document.querySelectorAll(
        '.dd-flip-detail table.dd-table.dd-narrow');
    tables.forEach(function(table) {
      var rows = table.querySelectorAll('tr');
      if (!rows.length) return;
      var header = rows[0];
      // Already enhanced? Guard against re-runs (e.g. if the JS is
      // ever included twice by a future build mistake).
      if (header.cells.length >= 9) return;
      // Expected shape: 6 header cells (IV / Atk / Def / HP / Avg rank /
      // Net flips). Bail if shape differs.
      if (header.cells.length !== 6) return;

      // Append 3 column headers.
      targetLabels.forEach(function(lbl) {
        var th = document.createElement('th');
        th.textContent = lbl + ' Δ';
        th.title = 'Avg score minus the rank-1-by-stat-product IV\'s' +
                   ' avg score, both at the ' + lbl + ' shield scenario.' +
                   ' Positive = this IV outscores rank-1 in ' + lbl + '.';
        header.appendChild(th);
      });

      // Enhance each data row.
      for (var i = 1; i < rows.length; i++) {
        var row = rows[i];
        // Handle the "… N more not rendered" footer row: widen its
        // colspan so the visual layout stays clean.
        if (row.cells.length === 1 && row.cells[0].colSpan > 1) {
          row.cells[0].colSpan = 9;
          continue;
        }
        if (row.cells.length !== 6) continue;
        var ivTriple = row.cells[0].textContent.trim();
        var iv = labelToIdx[ivTriple];
        // Append 3 Score Δ cells.
        targetIdx.forEach(function(si, k) {
          var td = document.createElement('td');
          if (si < 0 || r1Avgs[k] === null || iv === undefined) {
            td.className = 'dd-small';
            td.textContent = '—';
          } else {
            var avg = scenAvg(iv, si);
            var d = avg - r1Avgs[k];
            if (d > 0.05) td.className = 'dd-gain';
            else if (d < -0.05) td.className = 'dd-loss';
            td.textContent = (d >= 0 ? '+' : '') + d.toFixed(1);
          }
          row.appendChild(td);
        });
        // Rewrite the Net flips tooltip (column index 5) with the
        // full gained/lost list.
        if (iv !== undefined && iv !== pvpoke) {
          var flipCell = row.cells[5];
          var fd = flipDetail(iv, pvpoke);
          var lines = [];
          if (fd.gains.length) lines.push('Gained: ' + fd.gains.join(', '));
          if (fd.losses.length) lines.push('Lost: ' + fd.losses.join(', '));
          if (lines.length) flipCell.title = lines.join('\n');
        }
      }
    });
  }
})();
</script>
"""


def patch_html(content: str) -> tuple[str, bool]:
    """Return (patched_content, changed). Idempotent."""
    if FINGERPRINT in content:
        return content, False
    injection = FINGERPRINT + '\n' + JS_BLOCK
    # Inject right before </body>. Every shipped dive HTML has exactly
    # one </body> at the end of the interactive shell.
    if '</body>' in content:
        new_content = content.replace('</body>', injection + '</body>', 1)
    else:
        new_content = content + injection
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
    for f in files:
        try:
            content = f.read_text()
        except Exception as e:
            print(f'[skip] {f}: read failed: {e}', file=sys.stderr)
            continue
        new_content, changed = patch_html(content)
        if not changed:
            print(f'[already-patched] {f}')
            n_skipped += 1
            continue
        if args.dry_run:
            print(f'[would-patch] {f}')
        else:
            f.write_text(new_content)
            print(f'patched {f}')
        n_patched += 1

    tag = '(dry-run) ' if args.dry_run else ''
    print(f'\n{tag}patched {n_patched} file(s), '
          f'skipped {n_skipped} already-patched file(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
