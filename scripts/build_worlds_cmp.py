#!/usr/bin/env python
"""Worlds 2026 CMP board (plan product 6): meta-wide charge-move-
priority order with per-pair IV thresholds for the contested pairs.

CMP (charge-move priority) decides who throws first when both sides'
charged moves fire on the same turn: higher ``cmp_atk`` wins, where
``cmp_atk`` is the EFFECTIVE attack with the shadow x1.2 divided back
out (battle.py cmp_atk -- priority compares unboosted attack; the
division is WALKED, never algebraically inverted). An exact tie is a
THIRD state: the engine applies no priority at all and resolves in
player-index order (PROP-1); in-game it is effectively a coin flip.
The board must never render a tie as a win.

Root-level ``worlds-cmp.html`` via the shared shell; renderer-only
consumer (outside every producer hash). Data: iv_rank top-512 per
entry + worlds_tier0.cmp_threshold for exact flip thresholds.

REQUIRED footnote (TODO.md decided item 2, session-2 float audit): our
walked divide-by-1.2 breaks 30 of PvPoke's 227 exact shadow-twin CMP
ties by 1 ULP. The board and the baked planes are engine-consistent by
construction; the engine-side fix is deferred post-Worlds.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from gopvpsim.pokemon import iv_rank, SHADOW_ATK_BONUS

from build_website_index import _page_shell, WEBSITE_DIR  # noqa: E402
from build_worlds_pages import (  # noqa: E402
    esc, badge_html, sheet_filename, WORLDS_CSS, provenance_html,
)
import worlds_planes as wp  # noqa: E402
import worlds_render_data as wrd  # noqa: E402
import worlds_tier0 as t0  # noqa: E402

CMP_CSS = WORLDS_CSS + """
  table.cmp { border-collapse: collapse; width: 100%; font-size: 14px; }
  table.cmp th, table.cmp td { border-bottom: 1px solid var(--border);
        padding: 5px 8px; text-align: left; }
  .rangebar { position: relative; height: 12px; background:
        var(--bar-track); border-radius: 3px; min-width: 220px; }
  .rangebar .span { position: absolute; top: 0; height: 12px;
        background: var(--accent); border-radius: 3px; opacity: .75; }
  .rangebar .r1 { position: absolute; top: -2px; width: 2px;
        height: 16px; background: var(--text); }
  .wtl { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .wtl .w { color: var(--win); } .wtl .l { color: var(--loss); }
  .wtl .t { color: var(--tie); }
"""


def cmp_of(atk, shadow):
    """battle.py's cmp_atk expression: effective atk with the shadow
    boost divided back out (walked division -- fl(fl(x*1.2)/1.2) != x
    for ~1/3 of spreads, so never 'simplify' this algebraically)."""
    return atk / SHADOW_ATK_BONUS if shadow else atk


def entry_cmp_data(entries):
    """Per entry: rank-1 / min / max cmp_atk over the site's STANDARD
    plausible-spread cohort -- top-512 SP UNION best-SP-per-attack-IV
    (worlds_bake.cohort_indices), the same cohort every other Worlds
    surface sweeps. The first board used top-512 only, which excludes
    exactly the high-attack spreads that win CMP: a hundo Wigglytuff
    (SP rank 2137, in the attack band) beats Sableye (Shadow)'s rank-1
    while every top-512 Wigglytuff loses -- so 124 pairs the top-512
    ranges called 'settled' were IV-decided (adversarial-verify catch,
    2026-08-11)."""
    import worlds_bake as wb
    out = []
    for e in entries:
        rk = iv_rank(e['species'], league='great', shadow=e['shadow'])
        union, _t, _a = wb.cohort_indices(e['species'], e['shadow'])
        vals = [cmp_of(rk[i]['atk'], e['shadow']) for i in union]
        out.append({'entry': e, 'rank1': cmp_of(rk[0]['atk'], e['shadow']),
                    'lo': min(vals), 'hi': max(vals), 'vals': vals,
                    'n': len(vals)})
    out.sort(key=lambda d: -d['rank1'])
    return out


def contested_pairs(data):
    """Pairs whose cohort cmp_atk ranges overlap -- the IV-decided CMP
    set (within the cohort universe the range test is exact: any
    win+loss mix implies overlapping ranges). For each direction: W/T/L
    counts of the focal's cohort spreads vs the OPPONENT'S RANK-1
    spread, plus the exact win threshold (tier0.cmp_threshold)."""
    rows = []
    for i, a in enumerate(data):
        for b in data[i + 1:]:
            if a['hi'] >= b['lo'] and b['hi'] >= a['lo']:
                rows.append((a, b))
    out = []
    for a, b in rows:
        def side(f, o):
            thr = t0.cmp_threshold(o['rank1'], f['entry']['shadow'])
            # Counts against the anchor: strict win / exact tie / loss.
            w = sum(1 for v in f['vals'] if v > o['rank1'])
            t = sum(1 for v in f['vals'] if v == o['rank1'])
            return {'thr': thr, 'w': w, 't': t, 'l': f['n'] - w - t,
                    'n': f['n']}
        out.append({'a': a, 'b': b, 'ab': side(a, b), 'ba': side(b, a)})
    # Contested pairs ranked by combined usage, like the Tier-2 worklist.
    out.sort(key=lambda r: -(r['a']['entry']['usage_recent_pct']
                             + r['b']['entry']['usage_recent_pct']))
    return out


def render_cmp_board(meta, manifest):
    data = entry_cmp_data(meta['entries'])
    pairs = contested_pairs(data)
    glo = min(d['lo'] for d in data)
    ghi = max(d['hi'] for d in data)
    span = ghi - glo

    def bar(d):
        left = 100 * (d['lo'] - glo) / span
        width = max(100 * (d['hi'] - d['lo']) / span, 0.6)
        r1 = 100 * (d['rank1'] - glo) / span
        return (f'<div class="rangebar"><div class="span" '
                f'style="left:{left:.1f}%;width:{width:.1f}%"></div>'
                f'<div class="r1" style="left:{r1:.1f}%" '
                f'title="rank-1: {d["rank1"]:.2f}"></div></div>')

    order_rows = ''.join(
        f'<tr><td><a href="{sheet_filename(d["entry"]["species_id"])}">'
        f'{esc(d["entry"]["name"])}</a>{badge_html(d["entry"])}</td>'
        f'<td class="num">{d["rank1"]:.2f}</td>'
        f'<td class="num">{d["lo"]:.2f}..{d["hi"]:.2f}</td>'
        f'<td>{bar(d)}</td></tr>'
        for d in data)

    def wtl(s):
        return (f'<span class="wtl"><span class="w">{s["w"]}W</span>/'
                f'<span class="t">{s["t"]}T</span>/'
                f'<span class="l">{s["l"]}L</span></span>')

    import math as _math

    def thr_eff(side_data, entry):
        # cmp_threshold bisects over EFFECTIVE atk already (its cmp_of
        # divides the shadow boost out) -- print win_above without any
        # re-scaling (re-multiplying by 1.2 printed shadow thresholds
        # 1.2x too high; caught by the threshold-consistency test,
        # 2026-08-11). Displayed value is CEILED to 2dp: the truncated
        # form read exact-tie spreads as winners at display precision
        # (adversarial-verify catch). eff_atk >= the printed value
        # implies a true CMP win; spreads between the true and printed
        # threshold read conservatively as not-winning.
        return _math.ceil(side_data['thr']['win_above'] * 100) / 100

    pair_rows = []
    for r in pairs:
        an, bn = r['a']['entry']['name'], r['b']['entry']['name']
        pair_rows.append(
            f'<tr><td>{esc(an)} vs {esc(bn)}</td>'
            f'<td>{wtl(r["ab"])}</td><td>{wtl(r["ba"])}</td>'
            f'<td class="num">{thr_eff(r["ab"], r["a"]["entry"]):.2f}</td>'
            f'<td class="num">{thr_eff(r["ba"], r["b"]["entry"]):.2f}</td>'
            '</tr>')

    body = f"""
<h2>Priority order (rank-1 spreads, plausible-spread ranges)</h2>
<p class="section-intro">Sorted by the rank-1 spread's cmp_atk; the bar
is the range over the standard plausible-spread cohort (top-512 by
stat product PLUS the best-SP-per-attack-IV band, so high-attack
builds like hundos are inside the bars -- the same cohort every other
Worlds page sweeps). Non-overlapping bars: CMP is settled across that
cohort (a spread outside it could still differ). Overlapping bars are
contested below. Entries printing the same rank-1 value are exact
rank-1 ties.</p>
<div class="table-scroll"><table class="cmp">
<tr><th>entry</th><th class="num">rank-1 cmp_atk</th>
<th class="num">cohort range</th><th>range</th></tr>
{order_rows}
</table></div>
<h2>Contested pairs ({len(pairs)} of 465, usage-ranked)</h2>
<p class="section-intro">For each direction: how many of the first
species' cohort spreads Win / exactly Tie / Lose CMP against the
SECOND species' rank-1 spread. The two threshold columns give A's and
B's minimum EFFECTIVE attack (the shadow-boosted scale the
<a href="worlds-explorer.html">IV explorer</a> reports -- NOT the
cmp_atk scale of the table above, which divides the shadow boost back
out) that wins CMP against the other side's rank-1 anchor. Printed
thresholds are rounded UP: reaching the printed value guarantees the
win; an exact tie is never a win (the engine applies no priority and
resolves in player-index order -- in-game, effectively a coin flip).
</p>
<div class="table-scroll"><table class="cmp">
<tr><th>pair (A vs B)</th><th>A vs B rank-1</th><th>B vs A rank-1</th>
<th class="num">A's win-CMP eff. atk</th>
<th class="num">B's win-CMP eff. atk</th></tr>
{''.join(pair_rows)}
</table></div>
<p class="section-intro"><strong>Shadow-tie footnote:</strong> our
engine computes a shadow's cmp_atk by dividing the boosted attack back
by 1.2; that float division breaks 30 of PvPoke's 227 exact
shadow-vs-twin CMP ties by one ULP (they tie in PvPoke, resolve by
priority here). This board and every baked Worlds plane use the SAME
arithmetic, so nothing on these pages can contradict the sims; the
engine-side fix is deferred until after Worlds.</p>
{NOT_BUILT_LINK}
<p><a href="worlds.html">Back to the Worlds 2026 hub</a></p>
"""
    return _page_shell(
        title='Worlds 2026 - CMP board',
        heading='Worlds 2026: charge-move priority (CMP)',
        intro_html=('<p>Who throws first when both charged moves fire on '
                    'the same turn: higher cmp_atk (effective attack with '
                    'the shadow boost divided back out) wins priority. '
                    'IVs move cmp_atk, so near-ties flip on spreads.</p>'
                    + provenance_html(meta, manifest)),
        body_html=body,
        extra_css=CMP_CSS)


NOT_BUILT_LINK = ('<div class="notbuilt"><p><strong>Deliberately not '
                  'built:</strong> when to actually align charged throws, '
                  'or CMP-based switch plays -- this is arithmetic on who '
                  'wins priority, not strategy advice.</p></div>')


def build(website_dir=WEBSITE_DIR):
    meta = wrd.load_meta()
    manifest = wp.load_manifest()
    if manifest is None or wp.stamp_mismatches(manifest):
        sys.exit('ABORT: Tier-1 manifest missing or stale')
    (Path(website_dir) / 'worlds-cmp.html').write_text(
        render_cmp_board(meta, manifest))
    print('Wrote worlds-cmp.html')
    return 0


if __name__ == '__main__':
    sys.exit(build())
