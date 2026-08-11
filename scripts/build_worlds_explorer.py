#!/usr/bin/env python
"""Worlds 2026 IV-explorer page (plan product 5): worlds-explorer.html.

Assembly follows the deep_dive.py shape (the only repo pattern where
the same JS is browser-shipped AND node-tested): the two .js modules
are inlined verbatim, DATA arrives as its own <script> block, and a
small UI script wires the DOM. All math lives in the parity-tested
modules (tests/test_worlds_explorer_js.py); the UI script only formats.

Honesty surfaces on the page:
* cutoffs are vs each opponent's RANK-1 anchor (labeled; the pair pages
  carry full-cohort guarantees);
* stage-0 flag per pair; effective-stat unit note;
* Aegislash renders its closed-form exclusion, never a ladder;
* out-of-range / over-cap builds get explicit banners, never silently
  clamped read-outs.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from build_website_index import _page_shell, WEBSITE_DIR  # noqa: E402
from build_worlds_pages import WORLDS_CSS, provenance_html  # noqa: E402
import worlds_planes as wp  # noqa: E402
import worlds_render_data as wrd  # noqa: E402
import worlds_explorer_data as wed  # noqa: E402

EXPLORER_CSS = WORLDS_CSS + """
  .ctl { display: flex; flex-wrap: wrap; gap: 10px; align-items: end;
         margin: 14px 0; }
  .ctl label { display: block; font-size: 12px;
               color: var(--text-muted); }
  .ctl select { padding: 4px 6px; background: var(--surface);
                color: var(--text); border: 1px solid var(--border-2);
                border-radius: 4px; }
  #wx-stats { font-variant-numeric: tabular-nums; font-size: 14px;
              margin: 8px 0; }
  .banner { border-left: 3px solid var(--flip); padding: 4px 10px;
            color: var(--flip); font-size: 13px; margin: 8px 0; }
  table.wx { border-collapse: collapse; width: 100%; font-size: 13px; }
  table.wx th, table.wx td { border-bottom: 1px solid var(--border);
        padding: 5px 8px; text-align: left; vertical-align: top; }
  .mv { white-space: nowrap; }
  .gap { color: var(--text-muted); }
  .reach { color: var(--win); font-weight: 600; }
  .stageflag { color: var(--flip); font-size: 12px; }
"""

UI_JS = r"""
(function () {
  'use strict';
  WorldsIV.init(WX_DATA, POGOCollection);
  var $ = function (id) { return document.getElementById(id); };
  var entries = Object.keys(WX_DATA.entries).map(function (k) {
    return [k, WX_DATA.entries[k].name];
  }).sort(function (a, b) { return a[1] < b[1] ? -1 : 1; });

  var sp = $('wx-species');
  entries.forEach(function (e) {
    var o = document.createElement('option');
    o.value = e[0]; o.textContent = e[1]; sp.appendChild(o);
  });
  ['wx-a', 'wx-d', 'wx-s'].forEach(function (id) {
    var sel = $(id);
    for (var i = 0; i <= 15; i++) {
      var o = document.createElement('option');
      o.value = i; o.textContent = i; sel.appendChild(o);
    }
  });
  var lv = $('wx-level');
  var auto = document.createElement('option');
  auto.value = ''; auto.textContent = 'best (auto)'; lv.appendChild(auto);
  for (var l = 1; l <= WX_DATA.maxLevel; l += 0.5) {
    var o = document.createElement('option');
    o.value = l; o.textContent = l; lv.appendChild(o);
  }
  sp.value = 'tinkaton'; $('wx-a').value = 1; $('wx-d').value = 14;
  $('wx-s').value = 14;

  function mvName(sid, mid) {
    return WX_DATA.entries[sid].moveNames[mid] || mid;
  }

  function fmt(x, dp) { return Number(x).toFixed(dp == null ? 2 : dp); }
  /* Conservative cutoff display: CEIL to 2dp for BOTH cutoff kinds --
   * each is a 'meet or exceed the printed number' condition (reach:
   * atk >= X; shed: def > X), so ceiling makes the printed number
   * always sufficient. Plain toFixed rounded 90 atk / 127 def cutoffs
   * BELOW their true value, and rendered unreached cutoffs as '+0.00'
   * on 22.6% of builds (adversarial-verify catch, 2026-08-11). Gaps
   * under 0.01 print as '<0.01' -- at a CP-capped best level such a
   * gap is NOT closeable by powering up, only by a different spread. */
  function fmtAtkCut(x) { return (Math.ceil(x * 100) / 100).toFixed(2); }
  function fmtGap(g) {
    return g < 0.01 ? '<0.01' : '+' + fmt(g);
  }

  function render() {
    var mine = sp.value;
    var a = +$('wx-a').value, d = +$('wx-d').value, s = +$('wx-s').value;
    var level = lv.value === '' ? null : +lv.value;
    var r = WorldsIV.evaluate(mine, a, d, s, level);
    if (!r) { $('wx-stats').textContent = 'No legal level.'; return; }
    $('wx-stats').innerHTML =
      'Level <strong>' + r.level + '</strong>, CP <strong>' + r.cp +
      '</strong>, effective atk <strong>' + fmt(r.attack) +
      '</strong>, def <strong>' + fmt(r.defense) +
      '</strong>, HP <strong>' + r.stamina + '</strong>.';
    var banners = [];
    if (r.overCap) banners.push(
      'Over the ' + WX_DATA.leagueCap + ' CP cap - not GL-legal '
      + '(read-outs below are mathematically valid for these stats, '
      + 'but the build cannot be entered).');
    if (r.atkOutOfRange) banners.push(
      'Attack is outside the analyzed (best-level) range - breakpoint '
      + 'read-outs are hidden rather than clamped.');
    if (r.defOutOfRange) banners.push(
      'Defense is outside the analyzed (best-level) range - bulkpoint '
      + 'read-outs are hidden rather than clamped.');
    $('wx-banners').innerHTML = banners.map(function (b) {
      return '<div class="banner">' + b + '</div>';
    }).join('');
    var rows = entries.filter(function (e) { return e[0] !== mine; })
      .map(function (e) {
        var oid = e[0];
        var v = r.opponents[oid];
        if (v.excluded) {
          return '<tr><td>' + e[1] + '</td><td colspan="3">closed-form '
            + 'excluded (form change; see its cheat sheet)</td></tr>';
        }
        var bp = v.bp === null ? '<span class="gap">out of range</span>'
          : v.bp.map(function (m) {
              var t = '<span class="mv">' + mvName(mine, m.move)
                + ':</span> <span class="reach">' + m.tier + '</span>';
              if (m.nextTier !== null) {
                t += ' <span class="gap">(' + m.nextTier + ' at atk '
                  + fmtAtkCut(m.nextAtk) + ', '
                  + fmtGap(m.nextAtk - r.attack) + ')</span>';
              }
              return t;
            }).join('<br>');
        var bulk = v.bulk === null
          ? '<span class="gap">out of range</span>'
          : v.bulk.map(function (m) {
              var t = '<span class="mv">' + mvName(oid, m.move)
                + ':</span> takes ' + m.taken;
              if (m.shedAbove !== null) {
                t += ' <span class="gap">(shed at def > '
                  + fmtAtkCut(m.shedAbove) + ', '
                  + fmtGap(m.shedAbove - r.defense) + ')</span>';
              }
              return t;
            }).join('<br>');
        var flag = v.stage_flag
          ? '<span class="stageflag">stage-moving moves</span>' : '';
        return '<tr><td><a href="worlds-' + oid + '.html">' + e[1]
          + '</a></td><td>' + bp + '</td><td>' + bulk + '</td><td>'
          + flag + '</td></tr>';
      });
    $('wx-out').innerHTML =
      '<table class="wx"><tr><th>opponent (rank-1 anchor)</th>'
      + '<th>your damage tiers (per hit)</th>'
      + '<th>damage you take (per hit)</th><th></th></tr>'
      + rows.join('') + '</table>';
  }
  ['wx-species', 'wx-a', 'wx-d', 'wx-s', 'wx-level']
    .forEach(function (id) { $(id).addEventListener('change', render); });
  render();
})();
"""


def render_explorer(meta, manifest):
    data = wed.build_data()
    blob = json.dumps(data, separators=(',', ':'))
    pogo_js = (REPO / 'scripts' / 'deep_dive_user_collection.js').read_text()
    wx_js = (REPO / 'scripts' / 'worlds_iv_explorer.js').read_text()
    body = f"""
<p class="section-intro">Pick your Pokemon, IVs and level; every number
updates instantly from baked closed-form cutoffs (no simulation in the
browser). Damage tiers are PER HIT vs each opponent's
<strong>rank-1 SP anchor spread</strong> -- other opponent spreads
shift cutoffs (the per-pair detail pages carry full-cohort
guarantees). All stats are EFFECTIVE (shadow multiplier applied).
Pairs marked with the stage flag carry stat-stage-moving moves:
stage-0 cutoffs shift once a buff/debuff lands. Tiers count damage per
use of the move; whether a tier wins the FIGHT is what the cheat
sheets and grids answer.</p>
<div class="ctl">
<div><label>Your Pokemon</label><select id="wx-species"></select></div>
<div><label>Atk IV</label><select id="wx-a"></select></div>
<div><label>Def IV</label><select id="wx-d"></select></div>
<div><label>Sta IV</label><select id="wx-s"></select></div>
<div><label>Level</label><select id="wx-level"></select></div>
</div>
<div id="wx-stats"></div>
<div id="wx-banners"></div>
<div class="table-scroll"><div id="wx-out"></div></div>
<p><a href="worlds.html">Back to the Worlds 2026 hub</a></p>
<script>{pogo_js}</script>
<script>const WX_DATA = {blob};</script>
<script>{wx_js}</script>
<script>{UI_JS}</script>
"""
    return _page_shell(
        title='Worlds 2026 - IV explorer',
        heading='Worlds 2026: IV explorer',
        intro_html=('<p>What do YOUR IVs reach and hold against the '
                    'Worlds meta? Breakpoints and bulkpoints vs the 30 '
                    'closed-form entries (Aegislash is form-change '
                    'excluded and shown as such), from exact cutoffs; '
                    'displayed cutoffs are rounded UP so reaching the '
                    'printed number always suffices.</p>'
                    + provenance_html(meta, manifest)),
        body_html=body,
        extra_css=EXPLORER_CSS)


def build(website_dir=WEBSITE_DIR):
    meta = wrd.load_meta()
    manifest = wp.load_manifest()
    if manifest is None or wp.stamp_mismatches(manifest):
        sys.exit('ABORT: Tier-1 manifest missing or stale')
    (Path(website_dir) / 'worlds-explorer.html').write_text(
        render_explorer(meta, manifest))
    print('Wrote worlds-explorer.html')
    return 0


if __name__ == '__main__':
    sys.exit(build())
