#!/usr/bin/env python
"""Build a cross-species matchup-web page for a league opponent pool.

Answers "who beats X / who does X beat?" for the Great League meta:
sims every ORDERED pair in the pool (battle ratings are asymmetric per
side) across all 9 shield scenarios, then renders a self-contained
sortable HTML matrix with a scenario dropdown and a per-species
best-wins / worst-losses panel.

Resolution mirrors the dive opponent side:
  - pool parsing via deep_dive._parse_opponent_pool_line (shadow forms
    and inline `| fast= | charged=` overrides supported),
  - movesets via gopvpsim.data.get_default_moveset unless overridden,
  - IVs via gopvpsim.pokemon.pvpoke_default_ivs (PvPoke UI defaults),
  - sims via gopvpsim.battle.simulate with the pvpoke_dp policy, the
    same invocation the scripts/battle.py CLI uses.

Standalone by design: NOT wired into build_website_index.py or the
publish scripts (that's a later human decision).

Usage:
    python scripts/build_matchup_web.py                  # full GL pool
    python scripts/build_matchup_web.py --limit 10       # quick subset
    python scripts/build_matchup_web.py --pool FILE --out PATH
"""
import argparse
import json
import os
import sys
import time
from datetime import date
from html import escape

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

from gopvpsim.battle import simulate, pvpoke_dp
from gopvpsim.data import get_default_moveset
from gopvpsim.attribution import PVPOKE_ATTRIBUTION_SHORT, support_footer_html
from gopvpsim.pokemon import pvpoke_default_ivs
from gopvpsim.theme import (
    theme_css,
    theme_head_script,
    theme_picker_html,
)
from deep_dive import make_battle_pokemon, _parse_opponent_pool_line

LEAGUE = 'great'
SHIELD_SCENARIOS = [(a, b) for a in (0, 1, 2) for b in (0, 1, 2)]
DEFAULT_POOL = os.path.join(os.path.dirname(__file__), '..',
                            'opponent_pools', 'gl_top50_plus_cs.txt')
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), '..',
                           'userdata', 'website', 'matchups', 'index.html')


def load_pool(pool_path, limit=None):
    """Parse the opponents-file into resolved sim entries.

    Returns (entries, skipped) where each entry is a dict with display,
    base, shadow, fast, charged, ivs; skipped is [(display, reason)].
    """
    entries, skipped = [], []
    with open(pool_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            display, base, is_shadow, fast_ov, charged_ov = (
                _parse_opponent_pool_line(line))
            try:
                if fast_ov is None or charged_ov is None:
                    d_fast, d_charged = get_default_moveset(
                        base, league=LEAGUE, shadow=is_shadow)
                else:
                    d_fast, d_charged = None, None
                fast_id = fast_ov if fast_ov is not None else d_fast
                charged_ids = (list(charged_ov) if charged_ov is not None
                               else list(d_charged))
                # Same IV resolution as the dive opponent side's default
                # ('pvpoke') mode: gamemaster defaultIVs, shadow-agnostic.
                _lv, a_iv, d_iv, s_iv = pvpoke_default_ivs(base, league=LEAGUE)
            except (KeyError, ValueError) as exc:
                skipped.append((display, str(exc)))
                continue
            entries.append({
                'display': display, 'base': base, 'shadow': is_shadow,
                'fast': fast_id, 'charged': charged_ids,
                'ivs': (a_iv, d_iv, s_iv),
            })
            if limit is not None and len(entries) >= limit:
                break
    return entries, skipped


def run_matrix(entries):
    """Sim all ordered pairs x 9 shield scenarios.

    Returns (scores, n_sims, elapsed) where scores['a-b'][i][j] is the
    rounded PvPoke battle rating for row entry i vs column entry j with
    i holding a shields and j holding b shields (None on the diagonal).
    """
    n = len(entries)
    scores = {f'{a}-{b}': [[None] * n for _ in range(n)]
              for a, b in SHIELD_SCENARIOS}
    total = n * (n - 1) * len(SHIELD_SCENARIOS)
    # Build each BattlePokemon once and reuse it via reset_for_battle()
    # (the sweep-worker pattern) — from_pokemon is ~20x the cost of a
    # single sim, so per-sim reconstruction dominates the runtime.
    bps = [make_battle_pokemon(e['base'], e['fast'], e['charged'], LEAGUE,
                               1, *e['ivs'], shadow=e['shadow'])
           for e in entries]
    t0 = time.time()
    sims = 0
    for i, ei in enumerate(entries):
        bp0 = bps[i]
        for j in range(n):
            if i == j:
                continue
            bp1 = bps[j]
            for a, b in SHIELD_SCENARIOS:
                bp0.reset_for_battle(a, opponent=bp1)
                bp1.reset_for_battle(b, opponent=bp0)
                result = simulate(bp0, bp1,
                                  charged_policy_0=pvpoke_dp,
                                  charged_policy_1=pvpoke_dp)
                scores[f'{a}-{b}'][i][j] = round(result.pvpoke_score(0))
                sims += 1
        elapsed = time.time() - t0
        print(f'  [{i + 1}/{n}] {ei["display"]}: {sims:,}/{total:,} sims, '
              f'{sims / elapsed:,.0f} sims/s', flush=True)
    return scores, sims, time.time() - t0


def render_html(entries, scores, pool_name, n_sims, elapsed):
    names = [e['display'] for e in entries]
    movesets = [
        '{} / {}'.format(e['fast'], ' + '.join(e['charged']))
        for e in entries
    ]
    ivs = ['{}/{}/{}'.format(*e['ivs']) for e in entries]
    gen_date = date.today().isoformat()
    n = len(entries)
    scenario_options = ''.join(
        '<option value="{a}-{b}"{sel}>{a}s vs {b}s{tag}</option>'.format(
            a=a, b=b, sel=' selected' if (a, b) == (1, 1) else '',
            tag=' (even)' if a == b else '')
        for a, b in SHIELD_SCENARIOS)

    return """<!DOCTYPE html>
<html data-theme="gruvbox-light">
<head>
<meta charset="utf-8">
{THEME_HEAD}
<title>Great League matchup web</title>
<style>
{THEME_CSS}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
         sans-serif; margin: 30px auto; padding: 0 20px; max-width: none;
         background: var(--bg); color: var(--text); line-height: 1.5; }}
  h1 {{ color: var(--title); margin-bottom: 4px; }}
  p.subtitle {{ color: var(--text-muted); font-size: 14px; margin-top: 0; }}
  .controls {{ margin: 14px 0; font-size: 14px; }}
  .controls select {{ background: var(--surface); color: var(--text);
        border: 1px solid var(--border); border-radius: 2px; padding: 4px 8px;
        font-size: 13px; }}
  .hint {{ color: var(--text-muted); font-size: 12.5px; margin: 6px 0 14px 0; }}
  .matrix-wrap {{ overflow: auto; max-height: 82vh;
        border: 1px solid var(--border); border-radius: 2px; }}
  table.matrix {{ border-collapse: separate; border-spacing: 0;
        font-size: 11px; }}
  table.matrix th, table.matrix td {{ border-bottom: 1px solid var(--border);
        border-right: 1px solid var(--border); padding: 2px 4px; }}
  table.matrix thead th {{ position: sticky; top: 0; z-index: 2;
        background: var(--surface); color: var(--heading); vertical-align: bottom;
        cursor: pointer; }}
  table.matrix thead th:hover {{ background: var(--border-2); }}
  table.matrix thead th .vert {{ writing-mode: vertical-rl;
        transform: rotate(180deg); max-height: 150px; min-height: 110px;
        font-weight: 500; white-space: nowrap; margin: 0 auto; }}
  table.matrix tbody th {{ position: sticky; left: 0; z-index: 1;
        background: var(--surface-2); color: var(--text); font-weight: 500;
        text-align: left; white-space: nowrap; cursor: pointer;
        padding: 2px 8px; }}
  table.matrix tbody th:hover {{ background: var(--border-2); }}
  table.matrix thead th.corner {{ left: 0; z-index: 3; }}
  table.matrix td {{ text-align: center; min-width: 30px; }}
  table.matrix td.diag {{ background: var(--surface-2); color: var(--text-muted); }}
  table.matrix tbody th.pinned {{ background: var(--border-2); color: var(--flip); }}
  table.matrix thead th.pinned {{ background: var(--border-2); color: var(--flip); }}
  table.matrix tr.pinned td {{ outline: 1px solid var(--flip);
        outline-offset: -1px; }}
  table.matrix th.sortkey {{ color: var(--flip); }}
  table.matrix thead th .sortglyph {{ display: block; text-align: center;
        color: var(--text-muted); font-size: 11px; padding-top: 2px;
        filter: grayscale(1) opacity(0.45); }}
  table.matrix thead th .sortglyph:hover {{ filter: none; }}
  table.matrix thead th .sortglyph.pinnedglyph {{ filter: none; }}
  #panel {{ background: var(--surface); border-radius: 2px; padding: 12px 16px;
        margin: 16px 0; display: none; }}
  #panel h2 {{ color: var(--heading); margin: 0 0 4px 0; font-size: 1.1em; }}
  #panel .meta {{ color: var(--text-muted); font-size: 12.5px; margin-bottom: 8px; }}
  #panel .cols {{ display: flex; gap: 40px; flex-wrap: wrap; }}
  #panel h3 {{ font-size: 13px; margin: 6px 0 4px 0; }}
  #panel h3.wins {{ color: var(--win); }}
  #panel h3.losses {{ color: var(--loss); }}
  #panel ol {{ margin: 0; padding-left: 22px; font-size: 13px; }}
  #panel li {{ margin: 2px 0; }}
  #panel .score {{ color: var(--text-muted); font-variant-numeric: tabular-nums; }}
  footer {{ color: var(--text-muted); font-size: 13px; margin-top: 24px;
        border-top: 1px solid var(--border); padding-top: 10px; }}
</style>
</head>
<body>
{THEME_PICKER}
<h1>Great League matchup web</h1>
<p class="subtitle">Generated {gen_date} &middot; pool:
<code>{pool_name}</code> &middot; {n} species &middot; {n_sims:,} sims
({elapsed:.0f}s) &middot; PvPoke-default movesets &amp; IVs</p>

<div class="controls">
  Shield scenario (row vs column):
  <select id="scenario" onchange="setScenario(this.value)">
    {scenario_options}
  </select>
</div>
<p class="hint">Cells are PvPoke-style battle ratings from the
<b>row</b> species' perspective: &gt;500 (green) = row wins, &lt;500
(red) = row loses. <b>Click</b> a row name to pin that row to the top
(click again to unpin); pinned rows float above the sort. Click a
<b>column header</b> to sort rows by that matchup (avg header = row
average, corner = alphabetical); the <b>&#128204;</b> glyph under a
column name pins that column to the left. <b>Hover</b> a row name or
column header for that species' best wins / worst losses.</p>

<div id="panel"></div>

<div class="matrix-wrap">
  <table class="matrix" id="matrix"></table>
</div>

<footer><p>Matchup web &middot; gopvpsim &middot; even-shields (1v1) data
drives the per-species panel regardless of the dropdown.</p>
<p>{PVPOKE_ATTRIBUTION_SHORT}</p></footer>
{SUPPORT_FOOTER}

<script>
const SPECIES = {species_json};
const MOVESETS = {movesets_json};
const IVS = {ivs_json};
const DATA = {data_json};
const N = SPECIES.length;

let scenario = "1-1";
let sortMode = "avg";   // "avg" | "alpha" | column index
let sortDir = -1;       // -1 = descending (high / Z-A first), 1 = ascending
let pinnedRows = [];    // species indices in pin order (render at top)
let pinnedCols = [];    // species indices in pin order (render at left)
let panelIndex = null;  // species shown in the side panel (null = hidden)

function rowAvg(mat, i) {{
  let s = 0, c = 0;
  for (let j = 0; j < N; j++) {{
    if (mat[i][j] !== null) {{ s += mat[i][j]; c++; }}
  }}
  return c ? s / c : 0;
}}

function rowOrder() {{
  const mat = DATA[scenario];
  const idx = Array.from({{length: N}}, (_, i) => i);
  if (sortMode === "alpha") {{
    idx.sort((x, y) => SPECIES[x].localeCompare(SPECIES[y]) * sortDir);
  }} else if (sortMode === "avg") {{
    idx.sort((x, y) => (rowAvg(mat, x) - rowAvg(mat, y)) * sortDir);
  }} else {{
    const c = sortMode;
    idx.sort((x, y) => {{
      const a = mat[x][c], b = mat[y][c];
      if (a === null && b === null) return 0;
      if (a === null) return 1;   // empty cells always sort last
      if (b === null) return -1;
      return (a - b) * sortDir;
    }});
  }}
  // Pinned rows float to the top in pin order; the rest keep sortMode order.
  const rest = idx.filter(i => !pinnedRows.includes(i));
  return pinnedRows.concat(rest);
}}

function colOrder() {{
  const idx = Array.from({{length: N}}, (_, j) => j);
  const rest = idx.filter(j => !pinnedCols.includes(j));
  return pinnedCols.concat(rest);
}}

function cellStyle(s) {{
  if (s === null) return "";
  const t = Math.min(Math.abs(s - 500) / 350, 1);
  // Margin gradient: ramp the fill's alpha 12%->67% with the margin, over
  // the themed fill color (the strong-vs-marginal contrast lives here).
  const pct = (12 + 55 * t).toFixed(0);
  if (s > 500) {{
    return "background: color-mix(in srgb, var(--matrix-win-bg) " + pct +
           "%, transparent); color: var(--matrix-win-fg);";
  }} else if (s < 500) {{
    return "background: color-mix(in srgb, var(--matrix-loss-bg) " + pct +
           "%, transparent); color: var(--matrix-loss-fg);";
  }}
  return "background: var(--matrix-tie-bg); color: var(--matrix-tie-fg);";
}}

function sortArrow(m) {{
  // Direction glyph for the active sort header (down = descending, up = ascending).
  return m === sortMode ? (sortDir < 0 ? " &#9662;" : " &#9652;") : "";
}}

function render() {{
  const mat = DATA[scenario];
  const order = rowOrder();
  const cols = colOrder();
  let h = "<thead><tr>";
  h += '<th class="corner' + (sortMode === "alpha" ? " sortkey" : "") +
       '" onclick="setSort(\\'alpha\\')" title="Sort alphabetically">' +
       "Species" + sortArrow("alpha") + "</th>";
  h += '<th class="' + (sortMode === "avg" ? "sortkey" : "") +
       '" onclick="setSort(\\'avg\\')" title="Sort by row average">' +
       '<div class="vert">avg</div></th>';
  for (const j of cols) {{
    const pinned = pinnedCols.includes(j);
    h += '<th class="' + (sortMode === j ? "sortkey" : "") +
         (pinned ? " pinned" : "") +
         '" onclick="setSort(' + j + ')"' +
         ' onmouseenter="showPanel(' + j + ')"' +
         ' title="Sort rows by score vs ' + escAttr(SPECIES[j]) + '">' +
         '<div class="vert">' + (pinned ? "&#128204; " : "") +
         esc(SPECIES[j]) + "</div>" +
         '<span class="sortglyph' + (pinned ? " pinnedglyph" : "") + '" ' +
         'onclick="event.stopPropagation(); togglePinCol(' + j + ')" ' +
         'title="' + (pinned ? "Unpin column" :
                      "Pin column to the left") +
         '">&#128204;</span></th>';
  }}
  h += "</tr></thead><tbody>";
  for (const i of order) {{
    const rowPinned = pinnedRows.includes(i);
    h += '<tr data-i="' + i + '"' +
         (rowPinned ? ' class="pinned"' : "") + ">";
    h += '<th' + (rowPinned ? ' class="pinned"' : "") +
         ' onclick="togglePinRow(' + i + ')"' +
         ' onmouseenter="showPanel(' + i + ')" title="' +
         escAttr((rowPinned ? "Unpin | " : "Pin row to the top | ") +
                 MOVESETS[i] + " | IVs " + IVS[i]) + '">' +
         (rowPinned ? "&#128204; " : "") + esc(SPECIES[i]) + "</th>";
    h += '<td style="color:var(--text-muted)">' + rowAvg(mat, i).toFixed(0) + "</td>";
    for (const j of cols) {{
      const s = mat[i][j];
      if (s === null) {{
        h += '<td class="diag">-</td>';
      }} else {{
        h += '<td style="' + cellStyle(s) + '" title="' +
             escAttr(SPECIES[i] + " vs " + SPECIES[j] + ": " + s) + '">' +
             s + "</td>";
      }}
    }}
    h += "</tr>";
  }}
  h += "</tbody>";
  document.getElementById("matrix").innerHTML = h;
}}

function setScenario(v) {{
  scenario = v;
  render();
  if (panelIndex !== null) showPanel(panelIndex);  // keep an open panel in sync
}}
function setSort(m) {{
  if (m === sortMode) {{
    sortDir = -sortDir;                  // same header again: flip direction
  }} else {{
    sortMode = m;
    sortDir = (m === "alpha") ? 1 : -1;  // new header: names A-Z, scores high-first
  }}
  render();
}}

function togglePinRow(i) {{
  const k = pinnedRows.indexOf(i);
  if (k >= 0) pinnedRows.splice(k, 1); else pinnedRows.push(i);
  render();
}}

function togglePinCol(j) {{
  const k = pinnedCols.indexOf(j);
  if (k >= 0) pinnedCols.splice(k, 1); else pinnedCols.push(j);
  render();
}}

function showPanel(i) {{
  panelIndex = i;
  const panel = document.getElementById("panel");
  const mat = DATA[scenario];
  const scLabel = scenario.replace("-", "v");  // "1-1" -> "1v1", "0-2" -> "0v2"
  const rows = [];
  let w = 0, l = 0, t = 0;
  for (let j = 0; j < N; j++) {{
    const s = mat[i][j];
    if (s === null) continue;
    rows.push([j, s]);
    if (s > 500) w++; else if (s < 500) l++; else t++;
  }}
  rows.sort((a, b) => b[1] - a[1]);
  const wins = rows.filter(r => r[1] > 500).slice(0, 5);
  const losses = rows.filter(r => r[1] < 500).slice(-5).reverse();
  const li = r => "<li>" + esc(SPECIES[r[0]]) +
        ' <span class="score">(' + r[1] + ")</span></li>";
  panel.innerHTML =
    "<h2>" + esc(SPECIES[i]) + "</h2>" +
    '<div class="meta">' + esc(MOVESETS[i]) + " &middot; IVs " + IVS[i] +
    " &middot; " + scLabel + " shields: " + w + "W-" + l + "L" +
    (t ? "-" + t + "T" : "") + "</div>" +
    '<div class="cols"><div><h3 class="wins">Top 5 best wins (' + scLabel + ')</h3>' +
    "<ol>" + (wins.map(li).join("") || "<li>none</li>") + "</ol></div>" +
    '<div><h3 class="losses">Top 5 worst losses (' + scLabel + ')</h3><ol>' +
    (losses.map(li).join("") || "<li>none</li>") + "</ol></div></div>";
  panel.style.display = "block";
}}

function esc(s) {{
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}}
function escAttr(s) {{ return esc(s).replace(/"/g, "&quot;"); }}

render();
</script>
</body>
</html>
""".format(
        gen_date=gen_date, pool_name=escape(pool_name), n=n,
        n_sims=n_sims, elapsed=elapsed,
        scenario_options=scenario_options,
        species_json=json.dumps(names),
        movesets_json=json.dumps(movesets),
        ivs_json=json.dumps(ivs),
        data_json=json.dumps(scores, separators=(',', ':')),
        PVPOKE_ATTRIBUTION_SHORT=PVPOKE_ATTRIBUTION_SHORT,
        # matchups/index.html -> root is one up
        SUPPORT_FOOTER=support_footer_html('../'),
        # Theme outputs injected as kwargs (not pasted into the template):
        # their CSS/JS braces would otherwise break .format(). The Gruvbox
        # credit is already emitted by support_footer_html (SUPPORT_FOOTER).
        THEME_CSS=theme_css(),
        THEME_HEAD=theme_head_script(),
        THEME_PICKER=theme_picker_html(),
    )


def main():
    parser = argparse.ArgumentParser(
        description='Build the cross-species matchup-web HTML page.')
    parser.add_argument('--pool', default=DEFAULT_POOL,
                        help='opponents-file (default: gl_top50_plus_cs.txt)')
    parser.add_argument('--out', default=DEFAULT_OUT,
                        help='output HTML path '
                             '(default: userdata/website/matchups/index.html)')
    parser.add_argument('--limit', type=int, default=None,
                        help='only use the first N resolvable pool entries '
                             '(quick correctness/timing check)')
    args = parser.parse_args()

    entries, skipped = load_pool(args.pool, limit=args.limit)
    pool_name = os.path.basename(args.pool)
    print(f'Pool {pool_name}: {len(entries)} species resolved'
          + (f' (limit {args.limit})' if args.limit else ''), flush=True)
    for display, reason in skipped:
        print(f'  WARNING: skipped {display}: {reason}', file=sys.stderr,
              flush=True)
    if len(entries) < 2:
        print('Need at least 2 resolvable species; aborting.',
              file=sys.stderr)
        return 1

    scores, n_sims, elapsed = run_matrix(entries)
    print(f'Done: {n_sims:,} sims in {elapsed:.1f}s '
          f'({n_sims / elapsed:,.0f} sims/s)', flush=True)

    html_text = render_html(entries, scores, pool_name, n_sims, elapsed)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as f:
        f.write(html_text)
    print(f'Wrote {args.out}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
