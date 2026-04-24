#!/usr/bin/env python3
"""Retrofit the Top IVs per-shield Score Δ split into shipped dive HTMLs.

The f9d36a5 renderer change (scripts/deep_dive_engine.js) replaces the
outer Top IVs table's single ``Δ vs #1`` reactive column with three
per-shield columns (``0v0 Δ``, ``1v1 Δ``, ``2v2 Δ``) frozen on the
Shields axis. The 2026-04-24 CSS follow-up fixes header wrapping for
half-width viewports.

``updateSummaryTable`` re-renders the Top IVs table on every dropdown
change, so a DOM-patch-after-load retrofit (like
``patch_dive_member_ivs_enhance.py`` does for the Member IVs inner
table) would be destroyed by the first dropdown event. Instead this
patcher modifies the inlined engine JS and CSS inside each shipped
HTML via targeted string replacements: seven specific ``(before,
after)`` pairs cover the CSS wrap fix, the help-constant addition,
the ``_computeScoreDelta`` → new-helpers swap, the ``_summaryColumns``
descriptor rewrite, the cell-render block, the hover-tooltip block,
and the About-this-metrics box copy update.

Idempotent via the fingerprint comment
``<!-- TOP_IVS_PER_SHIELD_V1 -->``: re-running on an already-patched
HTML is a no-op. Fails loudly (exits non-zero) if any expected
``before`` string is missing from the target so a drift between
source and patcher surfaces immediately instead of silently producing
a half-patched file.

Usage:
    python scripts/patch_dive_top_ivs_per_shield.py PATH [PATH ...]
    python scripts/patch_dive_top_ivs_per_shield.py --dry-run PATH

PATH can be a single .html file or a directory (walks for index*.html).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


FINGERPRINT = '<!-- TOP_IVS_PER_SHIELD_V1 -->'


# --------------------------------------------------------------------
# Replacement table: 7 ``(before, after)`` pairs.
# --------------------------------------------------------------------

# Pair 1 — CSS wrap fix. The pre-change rule forced ``white-space: nowrap``
# on both ``th`` and ``td`` inside ``.summary``, which kept the Top IVs
# table too wide to fit half-width viewports once the three Δ columns
# landed. Split the rule so numeric cells stay single-line but headers
# wrap normally.
CSS_BEFORE = """  .summary th, .summary td { text-align: left; padding: 3px 8px;
                               border-bottom: 1px solid #0f3460; white-space: nowrap; }
  .summary th { color: #e94560; }"""

CSS_AFTER = """  .summary th, .summary td { text-align: left; padding: 3px 8px;
                               border-bottom: 1px solid #0f3460; }
  .summary td { white-space: nowrap; }
  .summary th { color: #e94560; white-space: normal; vertical-align: bottom; }"""


# Pair 2 — new HELP constant. Append after HELP_MATCHUPS_KEPT.
HELP_BEFORE = (
    "var HELP_MATCHUPS_KEPT = 'Expected non-mirror matchups won, "
    "sampling scenarios uniformly: per opponent, (scenarios won / "
    "nSel) summed over opponents. Integer when a single scenario is "
    "selected; fractional when averaging. Denominator excludes the "
    "mirror entry.';"
)
HELP_AFTER = (
    HELP_BEFORE + "\n"
    "var HELP_PER_SHIELD_DELTA = 'Signed avg-score delta vs the best "
    "IV in this scenario: +ve beats the best IV here, 0 is the best "
    "IV, -ve trades score for something else (atk / HP / bulk). "
    "Frozen on the Shields axis so all three show regardless of "
    "dropdown; reacts to Opp-IVs + Bait.';"
)


# Pair 3 — _computeScoreDelta function → new per-shield helpers.
COMPUTE_BEFORE = """// Difference in avg battle score vs the current rank-1 (lowest yRank)
// IV, under the ACTIVE Shields/Opp-IVs/Bait combo. Positive = this IV
// scores better than rank-1; negative = worse. Rank-1 itself returns 0.
// Uses yValues so the delta reacts to dropdown changes automatically.
function _computeScoreDelta(iv) {
  var myScore = yValues[iv];
  if (!isFinite(myScore)) return NaN;
  // Find the rank-1 IV for the current Y-axis mode.
  var rank1Iv = -1;
  for (var k = 0; k < yRanks.length; k++) {
    if (yRanks[k] === 1) { rank1Iv = k; break; }
  }
  if (rank1Iv < 0) return NaN;
  var rank1Score = yValues[rank1Iv];
  if (!isFinite(rank1Score)) return NaN;
  return myScore - rank1Score;
}"""

COMPUTE_AFTER = """// Per-shield Score Δ helpers. Each IV gets one Δ per even-shield
// scenario (0v0 / 1v1 / 2v2); values are avg battle score across
// opponents at that specific scenario minus the rank-1 IV's avg at
// the same scenario. Unlike the former dropdown-reactive single Δ,
// these three columns always surface the per-scenario split so a
// reader can pick an IV for lead (~2v2-weighted), mid (~1v1) or
// closer (~0v0) role regardless of what the Shields dropdown is
// set to. Reacts to Opp-IVs + Bait (via scoreMode); frozen on the
// Shields axis.
//
// Cached per (movesetIdx, scoreMode) so dropdown shuffles don't
// rebuild the nIvs-length avg arrays on every sort.
var _perShieldCacheKey = null;
var _perShieldCache = {};  // shieldCount -> { avgByIv, rank1Score }
var _perShieldScenarioIdxCache = null;

function _perShieldScenarioIdx(shields) {
  // Find the scenarios index where scenarios[si] === [shields, shields].
  // Cache the full (0v0, 1v1, 2v2) mapping on first call.
  if (_perShieldScenarioIdxCache === null) {
    _perShieldScenarioIdxCache = { 0: -1, 1: -1, 2: -1 };
    var scs = DATA.scenarios || [];
    for (var si = 0; si < scs.length; si++) {
      var sc = scs[si];
      if (sc[0] === sc[1] && sc[0] >= 0 && sc[0] <= 2) {
        _perShieldScenarioIdxCache[sc[0]] = si;
      }
    }
  }
  var idx = _perShieldScenarioIdxCache[shields];
  return (idx === undefined) ? -1 : idx;
}

function _ensurePerShieldBaselines(mi) {
  // scoreMode tracks the y-axis mode / oppIvMode the same way
  // computeYValues does, so the Δ numbers match the "Score" column
  // semantically (avgScore vs winsPvpoke vs winsRank1 all key off
  // different score arrays).
  var mode = state.yAxisMode || 'avgScore';
  var scoreMode;
  if (mode === 'winsPvpoke') scoreMode = 'pvpoke';
  else if (mode === 'winsRank1') scoreMode = 'rank1';
  else scoreMode = state.oppIvMode;  // 'avgScore' follows the Opp-IV/Bait dropdown
  var key = mi + '|' + scoreMode;
  if (key === _perShieldCacheKey) return;
  _perShieldCacheKey = key;
  _perShieldCache = {};
  var scores = getScores(mi, scoreMode);
  if (!scores) return;
  var targets = [0, 1, 2];
  for (var t = 0; t < targets.length; t++) {
    var shields = targets[t];
    var si = _perShieldScenarioIdx(shields);
    if (si < 0) continue;
    var avgByIv = new Float64Array(nIvs);
    var bestScore = -Infinity;
    for (var iv = 0; iv < nIvs; iv++) {
      var base = iv * nS * nO + si * nO;
      var sum = 0;
      for (var oi = 0; oi < nO; oi++) sum += scores[base + oi];
      var a = sum / nO;
      avgByIv[iv] = a;
      if (a > bestScore) bestScore = a;
    }
    _perShieldCache[shields] = { avgByIv: avgByIv, rank1Score: bestScore };
  }
}

function _computePerShieldScoreDelta(iv, shields) {
  _ensurePerShieldBaselines(state.movesetIdx);
  var b = _perShieldCache[shields];
  if (!b) return NaN;
  var my = b.avgByIv[iv];
  if (!isFinite(my)) return NaN;
  return my - b.rank1Score;
}"""


# Pair 4 — _summaryColumns comment block + scoreDelta descriptor.
COLS_BEFORE = """// 'mirrorCmp' and 'scoreDelta' are the XL-candy-decision helpers
// (docs/todo.md "XL-candy-decision tool"). Both are optional:
// mirrorCmp is present only when --mirror-slayer produced a cohort
// (DATA.mirrorCohortAtk non-empty), scoreDelta is always available
// as long as yValues is populated.
function _summaryColumns() {
  var hasCohort = !!(DATA.mirrorCohortAtk && DATA.mirrorCohortAtk.length > 0);
  var cols = [
    { id: 'yrank', label: 'Y Rank',  defaultDir: 'asc',  value: function(iv){ return yRanks[iv]; } },
    { id: 'ivs',   label: 'IVs',     defaultDir: null,   value: null },
    { id: 'level', label: 'Level',   defaultDir: 'desc', value: function(iv){ return DATA.ivLv[iv]; } },
    { id: 'cp',    label: 'CP',      defaultDir: 'desc', value: function(iv){ return DATA.ivCp[iv]; } },
    { id: 'atk',   label: 'Atk',     defaultDir: 'desc', value: function(iv){ return DATA.ivAtk[iv]; } },
    { id: 'def',   label: 'Def',     defaultDir: 'desc', value: function(iv){ return DATA.ivDef[iv]; } },
    { id: 'hp',    label: 'HP',      defaultDir: 'desc', value: function(iv){ return DATA.ivHp[iv]; } },
    { id: 'sp',    label: 'SP Rank', defaultDir: 'asc',  value: function(iv){ return DATA.spRanks[iv]; } },
    { id: 'yval',  label: null,      defaultDir: 'desc', value: function(iv){ return yValues[iv]; } },
    { id: 'scoreDelta',    label: 'Δ vs #1',        defaultDir: 'desc', value: function(iv){ return _computeScoreDelta(iv); } },
    { id: 'topMirrorCmp',  label: 'Top-Mirror CMP %', defaultDir: 'desc', value: function(iv){ return _computeTopMirrorCmpPct(iv); },
      help: HELP_TOP_MIRROR_CMP },
    { id: 'matchupsKept',  label: 'Matchups Kept',    defaultDir: 'desc', value: function(iv){ return _computeMatchupsKept(iv); },
      help: HELP_MATCHUPS_KEPT },
  ];"""

COLS_AFTER = """// 'mirrorCmp' and the three per-shield Δ columns are the
// XL-candy-decision helpers (docs/todo.md "XL-candy-decision tool" +
// "Personal-collection decision tool follow-ups"). mirrorCmp is
// optional (cohort-gated); the three Δ columns are always present
// when score arrays exist and always surface per-scenario splits
// regardless of the Shields dropdown, so lead/mid/closer role
// picking doesn't collapse into one number.
function _summaryColumns() {
  var hasCohort = !!(DATA.mirrorCohortAtk && DATA.mirrorCohortAtk.length > 0);
  var cols = [
    { id: 'yrank', label: 'Y Rank',  defaultDir: 'asc',  value: function(iv){ return yRanks[iv]; } },
    { id: 'ivs',   label: 'IVs',     defaultDir: null,   value: null },
    { id: 'level', label: 'Level',   defaultDir: 'desc', value: function(iv){ return DATA.ivLv[iv]; } },
    { id: 'cp',    label: 'CP',      defaultDir: 'desc', value: function(iv){ return DATA.ivCp[iv]; } },
    { id: 'atk',   label: 'Atk',     defaultDir: 'desc', value: function(iv){ return DATA.ivAtk[iv]; } },
    { id: 'def',   label: 'Def',     defaultDir: 'desc', value: function(iv){ return DATA.ivDef[iv]; } },
    { id: 'hp',    label: 'HP',      defaultDir: 'desc', value: function(iv){ return DATA.ivHp[iv]; } },
    { id: 'sp',    label: 'SP Rank', defaultDir: 'asc',  value: function(iv){ return DATA.spRanks[iv]; } },
    { id: 'yval',  label: null,      defaultDir: 'desc', value: function(iv){ return yValues[iv]; } },
    { id: 'd0',    label: '0v0 Δ',   defaultDir: 'desc', value: function(iv){ return _computePerShieldScoreDelta(iv, 0); },
      help: HELP_PER_SHIELD_DELTA },
    { id: 'd1',    label: '1v1 Δ',   defaultDir: 'desc', value: function(iv){ return _computePerShieldScoreDelta(iv, 1); },
      help: HELP_PER_SHIELD_DELTA },
    { id: 'd2',    label: '2v2 Δ',   defaultDir: 'desc', value: function(iv){ return _computePerShieldScoreDelta(iv, 2); },
      help: HELP_PER_SHIELD_DELTA },
    { id: 'topMirrorCmp',  label: 'Top-Mirror CMP %', defaultDir: 'desc', value: function(iv){ return _computeTopMirrorCmpPct(iv); },
      help: HELP_TOP_MIRROR_CMP },
    { id: 'matchupsKept',  label: 'Matchups Kept',    defaultDir: 'desc', value: function(iv){ return _computeMatchupsKept(iv); },
      help: HELP_MATCHUPS_KEPT },
  ];"""


# Pair 5 — Δ cell rendering in updateSummaryTable.
CELL_BEFORE = """    // Score Δ: show signed delta vs rank-1 under the active Y-axis mode.
    // Green when positive (beats rank-1), red when negative (trades
    // score for something else — typically atk or HP), zero for the
    // rank-1 IV itself.
    var sd = _computeScoreDelta(iv);
    if (isFinite(sd)) {
      var sdStr = (sd > 0 ? '+' : '') + sd.toFixed(1);
      var sdColor = (sd > 0) ? '#9be89b' : (sd < 0 ? '#e89b9b' : '#c9d1d9');
      h += '<td style="color:' + sdColor + '">' + sdStr + '</td>';
    } else {
      h += '<td>-</td>';
    }"""

CELL_AFTER = """    // Per-shield Score Δ: one cell each for 0v0 / 1v1 / 2v2, value is
    // avg score across opponents at that scenario minus the best-IV's
    // avg at the same scenario. Frozen on the Shields axis so the
    // three cells show the full lead/mid/closer split regardless of
    // the Shields dropdown selection. Green positive / red negative /
    // neutral for exact zero (best IV at that shield).
    for (var _sh = 0; _sh < 3; _sh++) {
      var _d = _computePerShieldScoreDelta(iv, _sh);
      if (isFinite(_d)) {
        var _dStr = (_d > 0 ? '+' : '') + _d.toFixed(1);
        var _dColor = (_d > 0) ? '#9be89b' : (_d < 0 ? '#e89b9b' : '#c9d1d9');
        h += '<td style="color:' + _dColor + '">' + _dStr + '</td>';
      } else {
        h += '<td>-</td>';
      }
    }"""


# Pair 6 — buildHoverText Δ line.
HOVER_BEFORE = """  // XL-candy-decision helpers. Score Δ reacts to dropdowns; Mirror
  // CMP % is dropdown-independent (atk-based). Only surface when the
  // numbers are meaningful: Score Δ on rank-1 is 0 (skip; not new
  // info), Mirror CMP % needs a cohort to exist.
  var sd = _computeScoreDelta(iv);
  if (isFinite(sd) && yRanks[iv] !== 1) {
    lines.push('Δ vs #1: ' + (sd > 0 ? '+' : '') + sd.toFixed(1));
  }
  var cmp = _computeMirrorCmpPct(iv);"""

HOVER_AFTER = """  // XL-candy-decision helpers. Per-shield Δ columns are frozen on
  // the Shields axis so hover always shows the full lead/mid/closer
  // split regardless of dropdown state. Mirror CMP % is
  // dropdown-independent (atk-based) and cohort-gated.
  var _d0 = _computePerShieldScoreDelta(iv, 0);
  var _d1 = _computePerShieldScoreDelta(iv, 1);
  var _d2 = _computePerShieldScoreDelta(iv, 2);
  function _fmtD(d) { return (d > 0 ? '+' : '') + d.toFixed(1); }
  var _parts = [];
  if (isFinite(_d0)) _parts.push('0v0 ' + _fmtD(_d0));
  if (isFinite(_d1)) _parts.push('1v1 ' + _fmtD(_d1));
  if (isFinite(_d2)) _parts.push('2v2 ' + _fmtD(_d2));
  if (_parts.length > 0) lines.push('Δ vs best: ' + _parts.join(' | '));
  var cmp = _computeMirrorCmpPct(iv);"""


# Pair 7 — About-these-metrics summary line + intro paragraph.
ABOUT_BEFORE = """  // About-these-metrics box: explains the three mirror-adjacent columns
  // (Top-Mirror CMP %, Matchups Kept, Mirror Slayer CMP %). Collapsed
  // by default so regulars are not slowed down; sits above the table so
  // new readers see it adjacent to the headers.
  var h = '<details style="margin:0 0 8px 0;background:#1a1f2a;border:1px solid #2a3040;border-radius:4px;padding:6px 10px">'
    + '<summary style="cursor:pointer;color:#c9d1d9;font-weight:600">About these metrics (Top-Mirror CMP %, Matchups Kept, Mirror Slayer CMP %)</summary>'
    + '<div style="margin-top:8px;font-size:12px;line-height:1.5;color:#c9d1d9">'
    + '<p>These three columns all ask "how well does this IV compete in the mirror (same-species) matchup," but they answer it from different angles. Read them together, not individually.</p>'"""

ABOUT_AFTER = """  // About-these-metrics box: explains the per-shield Δ trio plus the
  // mirror-adjacent columns (Top-Mirror CMP %, Matchups Kept, Mirror
  // Slayer CMP %). Collapsed by default so regulars are not slowed
  // down; sits above the table so new readers see it adjacent to the
  // headers.
  var h = '<details style="margin:0 0 8px 0;background:#1a1f2a;border:1px solid #2a3040;border-radius:4px;padding:6px 10px">'
    + '<summary style="cursor:pointer;color:#c9d1d9;font-weight:600">About these metrics (0v0 / 1v1 / 2v2 Δ, Top-Mirror CMP %, Matchups Kept, Mirror Slayer CMP %)</summary>'
    + '<div style="margin-top:8px;font-size:12px;line-height:1.5;color:#c9d1d9">'
    + '<p><b>0v0 Δ / 1v1 Δ / 2v2 Δ.</b> Per-even-shield signed avg-score delta vs the best IV in that specific scenario. These three columns are <em>frozen on the Shields axis</em> so all three show regardless of what the Shields dropdown is set to; they do react to Opp-IVs + Bait. Useful for role-specific IV picking: leads weight 2v2 Δ, closers weight 0v0 Δ, mid picks weight 1v1 Δ. Positive = beats the best IV in that scenario (rare; the best IV has 0), negative = trades score for something else (usually atk or bulk).</p>'
    + '<p>The next three columns all ask "how well does this IV compete in the mirror (same-species) matchup," but they answer it from different angles. Read them together, not individually.</p>'"""


REPLACEMENTS = [
    ('CSS wrap fix',          CSS_BEFORE,     CSS_AFTER),
    ('HELP_PER_SHIELD_DELTA', HELP_BEFORE,    HELP_AFTER),
    ('_computeScoreDelta',    COMPUTE_BEFORE, COMPUTE_AFTER),
    ('_summaryColumns',       COLS_BEFORE,    COLS_AFTER),
    ('updateSummaryTable',    CELL_BEFORE,    CELL_AFTER),
    ('buildHoverText',        HOVER_BEFORE,   HOVER_AFTER),
    ('About-these-metrics',   ABOUT_BEFORE,   ABOUT_AFTER),
]


def patch_html(content: str, filename: str = '') -> tuple[str, bool, list[str]]:
    """Return ``(patched_content, changed, errors)``. Idempotent.

    Fails loudly by returning non-empty ``errors`` when any expected
    ``before`` string is missing from the content. The caller decides
    whether to skip or abort on drift.
    """
    if FINGERPRINT in content:
        return content, False, []
    errors: list[str] = []
    out = content
    for name, before, after in REPLACEMENTS:
        if before not in out:
            errors.append(f'  [{name}] expected pre-change snippet not found')
            continue
        # Every ``before`` should appear exactly once in the inlined JS /
        # CSS. More than one match means the anchors aren't unique enough
        # and we'd silently over-patch.
        count = out.count(before)
        if count > 1:
            errors.append(f'  [{name}] expected pre-change snippet found {count}x (ambiguous)')
            continue
        out = out.replace(before, after, 1)
    if errors:
        return content, False, errors
    # Insert fingerprint comment just before </body>. Guarantees every
    # patched file is identifiable and the patcher is idempotent.
    stamp = FINGERPRINT + '\n'
    if '</body>' in out:
        out = out.replace('</body>', stamp + '</body>', 1)
    else:
        out = out + stamp
    return out, True, []


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
    n_failed = 0
    for f in files:
        try:
            content = f.read_text()
        except Exception as e:
            print(f'[skip] {f}: read failed: {e}', file=sys.stderr)
            n_failed += 1
            continue
        new_content, changed, errors = patch_html(content, str(f))
        if errors:
            print(f'[error] {f}:', file=sys.stderr)
            for line in errors:
                print(line, file=sys.stderr)
            n_failed += 1
            continue
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
          f'skipped {n_skipped} already-patched, '
          f'{n_failed} failed.')
    return 1 if n_failed > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
