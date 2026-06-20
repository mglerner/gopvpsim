#!/usr/bin/env python
"""Render an IV-envelope JSON (from iv_envelope_analysis.py) into a
XehrFelrose-style ML IV guide article, matching the pogo-dives website
dark article house style with a sticky sidebar nav. Re-run freely to tweak
presentation without re-simulating.

Usage: python scripts/render_iv_envelope_article.py userdata/dives/<slug>_iv_envelope.json

Writes userdata/website/articles/<slug>-ml-iv-guide/{index.html,meta.toml}.
No gameplay/teambuilding judgment is rendered -- only the simulated mechanics
and matchups. The reader decides what matters.
"""
import sys, os, json, html

QUAD_LABEL = {
    'nobb_vs_nonbb': 'No best buddy, vs a non-best-buddy meta',
    'nobb_vs_bb':    'No best buddy, vs a best-buddy meta',
    'wbb_vs_nonbb':  'Best buddy, vs a non-best-buddy meta',
    'wbb_vs_bb':     'Best buddy, vs a best-buddy meta',
}
# Attribution. The format, structure, and much of the terminology of this
# article are adapted from XehrFelrose's Master League IV deep dives. Credit
# is rendered prominently (top credit box, Terms note, and footer). The numbers
# are independently re-simulated with this project's engine.
CREDIT_NAME = 'XehrFelrose'
CREDIT_URL = 'https://www.youtube.com/watch?v=6N3lXp39qtQ'

QUAD_ORDER = ['nobb_vs_nonbb', 'nobb_vs_bb', 'wbb_vs_nonbb', 'wbb_vs_bb']
QUAD_SHORT = {
    'nobb_vs_nonbb': 'No BB vs non-BB',
    'nobb_vs_bb':    'No BB vs BB',
    'wbb_vs_nonbb':  'BB vs non-BB',
    'wbb_vs_bb':     'BB vs BB',
}
STAT_LABEL = {'atk': 'Attack', 'def': 'Defense', 'hp': 'HP'}

# Sidebar nav: (anchor id, label, [(sub id, sub label), ...]).
NAV = [
    ('covers', 'What this covers', []),
    ('terms', 'Terms to know', []),
    ('build', 'The build', []),
    ('meta', 'Vs the meta', []),
    ('bestbuddy', 'What best buddy changes', []),
    ('attack', 'Attack IVs', [(f'atk-{q}', QUAD_SHORT[q]) for q in QUAD_ORDER]),
    ('defense', 'Defense IVs', [(f'def-{q}', QUAD_SHORT[q]) for q in QUAD_ORDER]),
    ('hp', 'HP IVs', [(f'hp-{q}', QUAD_SHORT[q]) for q in QUAD_ORDER]),
    ('recommended', 'Recommended IVs', [
        ('rec-bb', 'Best buddy (L51) table'),
        ('rec-nobb', 'No best buddy (L50) table'),
    ]),
    ('method', 'Method & caveats', []),
]


def esc(s):
    return html.escape(str(s))


def joinm(lst):
    return ", ".join(esc(x) for x in lst) if lst else '<span class="none">-</span>'


def style():
    return """
  :root { --bg:#1a1a2e; --fg:#e0e0e0; --red:#e94560; --pur:#c8a2d0;
          --grn:#9be89b; --panel:#16213e; --cell:#0f162a; --rule:#0f3460;
          --sub:#8ea1bd; --blue:#5b8dd9; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         background:var(--bg); color:var(--fg); line-height:1.6; margin:0; }
  a { color:var(--grn); text-decoration:none; }
  a:hover { text-decoration:underline; }
  .topbar { max-width:1180px; margin:0 auto; padding:32px 16px 0; }
  h1 { color:var(--red); margin:0 0 6px; }
  h2 { color:var(--pur); border-bottom:1px solid var(--rule);
       padding-bottom:6px; margin-top:34px; scroll-margin-top:14px; }
  h3 { color:var(--pur); margin-top:20px; font-size:1.05em; }
  h4 { color:var(--sub); margin:12px 0 4px; font-size:.95em; }
  code { background:var(--panel); padding:2px 5px; border-radius:3px; font-size:.9em; }
  p { margin:10px 0; }
  .sub { color:var(--sub); font-size:.92em; }
  .none { color:#6b7a93; }
  table { border-collapse:collapse; width:100%; margin:.6em 0 1.3em; font-size:.88em; }
  th, td { border:1px solid var(--rule); padding:5px 9px; text-align:left; vertical-align:top; }
  thead th { background:var(--panel); color:var(--pur); }
  tbody td { background:var(--cell); color:var(--fg); }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  caption { text-align:left; font-weight:600; color:var(--pur); padding:.3em 0; }
  /* orange = AI-drafted prose, not yet human-reviewed (authored-ai tier) */
  .banner { background:#2e241a; color:#e8d4bb; border-radius:6px;
            padding:10px 16px 10px 20px; margin:16px 0; font-size:14px;
            position:relative; }
  .banner::before { content:""; position:absolute; left:0; top:4px; bottom:4px;
            width:4px; border-radius:2px; background:#e8903a; }
  /* gold = source attribution (matches the site's expert/source tier) */
  .credit { background:#2e2a1a; color:#e8dfcf; border-radius:6px;
            padding:10px 16px 10px 20px; margin:16px 0; font-size:14px;
            position:relative; }
  .credit::before { content:""; position:absolute; left:0; top:4px; bottom:4px;
            width:4px; border-radius:2px; background:#d29922; }
  .credit a { color:#f0d98b; }
  .twocol { display:flex; gap:2em; flex-wrap:wrap; }
  .twocol > div { flex:1; min-width:240px; }
  .terms dt { font-weight:600; margin-top:.5em; color:var(--pur); }
  .terms dd { margin:0 0 .2em 1.2em; color:var(--fg); }
  .panel { background:var(--panel); border-radius:6px; padding:10px 14px 10px 18px;
           margin:12px 0; position:relative; }
  .panel::before { content:""; position:absolute; left:0; top:4px; bottom:4px;
           width:3px; border-radius:2px; background:var(--blue); }
  footer { color:#667; font-size:13px; margin-top:40px;
           border-top:1px solid var(--rule); padding-top:12px; }
  /* layout + sidebar */
  .layout { display:flex; gap:28px; max-width:1180px; margin:8px auto 0;
            padding:0 16px 40px; align-items:flex-start; }
  nav.toc { position:sticky; top:14px; flex:0 0 190px; font-size:13px;
            background:var(--panel); border-radius:6px; padding:12px 14px; }
  nav.toc strong { color:var(--pur); display:block; margin-bottom:6px;
            font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  nav.toc a { display:block; color:var(--grn); padding:3px 0; }
  nav.toc a.sub { padding:2px 0 2px 14px; font-size:12px; color:var(--sub); }
  nav.toc a.sub:hover { color:var(--grn); }
  main { flex:1; min-width:0; }
  main h2:first-child { margin-top:6px; }
  @media (max-width:820px) {
    .layout { flex-direction:column; }
    nav.toc { position:static; flex:none; width:auto; }
  }
"""


def nav_html():
    parts = []
    for i, l, subs in NAV:
        parts.append(f'<a href="#{i}">{esc(l)}</a>')
        for sid, sl in subs:
            parts.append(f'<a class="sub" href="#{sid}">{esc(sl)}</a>')
    return f'<nav class="toc"><strong>On this page</strong>{"".join(parts)}</nav>'


def build_card(d):
    b = d['build']
    bs = d['base_stats']
    return (f'<h2 id="build">The build</h2>\n<p class="sub">This guide assumes '
            f'<b>{esc(d["species"])}</b> with its signature move. Base stats '
            f'atk {bs["atk"]} / def {bs["def"]} / hp {bs["hp"]}.</p>\n'
            f'<ul><li>Fast: <code>{esc(b["fast"])}</code></li>'
            f'<li>Charged: {", ".join("<code>"+esc(c)+"</code>" for c in b["charged"])}</li></ul>\n')


def terms():
    return """<h2 id="terms">Terms to know</h2>
<dl class="terms">
<dt>Breakpoint</dt><dd>An attack-stat threshold where your fast move deals 1 more damage to a specific opponent. Most impactful on fast moves that fire every turn.</dd>
<dt>Bulkpoint</dt><dd>A defense-stat threshold where a specific opponent's fast move deals 1 less damage to you.</dd>
<dt>CMP (charge-move priority)</dt><dd>When both Pokemon throw a charged move on the same turn, the one with the higher attack stat goes first. "CMP lost" means a lower attack IV drops you below an opponent's attack, so you would lose that simultaneous-throw.</dd>
<dt>0s / 1s / 2s</dt><dd>Even-shield scenarios: 0-0, 1-1, and 2-2 shields. This guide uses even shields and even energy, standard movesets.</dd>
<dt>BB (best buddy)</dt><dd>Best-buddy boost adds one level (L50 to L51). In Master League there is no CP cap, so that level fully applies.</dd>
<dt>Premium vs Thrifty IVs</dt><dd>Terminology from {credit_name} (<a href="{credit_url}">video</a>). Defined here mechanically, not as a gameplay call: a <b>Premium</b> spread drops no matchups versus a perfect (hundo) IV spread in the stated case; a <b>Thrifty</b> spread drops only the matchups listed next to it. Whether those matchups matter is your call.</dd>
</dl>
<p class="sub">These terms and the breakdown that follows are adapted from {credit_name}'s Master League IV deep dives.</p>
""".replace("{credit_name}", esc(CREDIT_NAME)).replace("{credit_url}", esc(CREDIT_URL))


def key_winloss(d):
    out = ['<h2 id="meta">Versus the Master League meta</h2>']
    q = d['headline_quadrant']
    ml, ol = d['quadrant_levels'][q]
    out.append(f'<p class="sub">Consistent results (all even shields) at a perfect IV, '
               f'in the <b>{esc(QUAD_LABEL[q].lower())}</b> case '
               f'(you L{int(ml)} vs opponents L{int(ol)}), vs the '
               f'{d["n_opponents"]}-strong Master top-60.</p>')
    out.append('<div class="twocol">')
    out.append('<div><h3>Key wins</h3><ul>'
               + "".join(f"<li>{esc(x)}</li>" for x in d['key_wins']) + '</ul></div>')
    out.append('<div><h3>Key losses</h3><ul>'
               + "".join(f"<li>{esc(x)}</li>" for x in d['key_losses']) + '</ul></div>')
    out.append('</div>')
    if d['key_split']:
        out.append('<p class="sub"><b>Shield-dependent (split):</b> '
                   + joinm(d['key_split']) + '.</p>')
    return "\n".join(out) + "\n"


def bb_differences(d):
    hw = {q: set(v) for q, v in d['hundo_won'].items()}
    out = ['<h2 id="bestbuddy">What best buddy changes (at a perfect IV)</h2>',
           '<p class="sub">Matchups best buddy (L51) gains over not best-buddying (L50), holding the meta\'s best-buddy status fixed. Even shields, perfect IV.</p>',
           '<div class="panel">']
    for meta_label, wbb, nobb in [
            ('a non-best-buddy meta', 'wbb_vs_nonbb', 'nobb_vs_nonbb'),
            ('a best-buddy meta', 'wbb_vs_bb', 'nobb_vs_bb')]:
        gained = sorted(hw[wbb] - hw[nobb])
        lost = sorted(hw[nobb] - hw[wbb])
        out.append(f'<h4>Vs {meta_label}</h4>')
        out.append(f'<div><b>Gains:</b> {joinm(gained)}</div>')
        if lost:
            out.append(f'<div><b>Gives up:</b> {joinm(lost)}</div>')
    out.append('</div>')
    return "\n".join(out) + "\n"


def stat_section(d, stat):
    sv = d['stat_values']
    out = [f'<h2 id="{stat if stat!="atk" else "attack"}">{STAT_LABEL[stat]} IVs</h2>'
           if stat == 'atk' else
           f'<h2 id="{"defense" if stat=="def" else "hp"}">{STAT_LABEL[stat]} IVs</h2>']
    out.append(f'<p class="sub">{STAT_LABEL[stat]} at a perfect IV: '
               f'<b>{sv["bb"][stat]["15"]}</b> at L51 (best buddy), '
               f'<b>{sv["nobb"][stat]["15"]}</b> at L50. '
               f'Each row drops only that one stat (the other two stay 15); '
               f'matchups shown are those given up versus a perfect IV.</p>')
    for q in QUAD_ORDER:
        qd = d['quadrants'][q][stat]
        out.append(f'<h3 id="{stat}-{q}">{esc(QUAD_LABEL[q])}</h3>')
        if stat == 'atk':
            cols = ['IV', STAT_LABEL[stat], 'CMP lost', 'Breakpoint lost',
                    '0s drops', '1s drops', '2s drops']
        elif stat == 'def':
            cols = ['IV', STAT_LABEL[stat], 'Bulkpoint lost',
                    '0s drops', '1s drops', '2s drops']
        else:
            cols = ['IV', STAT_LABEL[stat], '0s drops', '1s drops', '2s drops']
        out.append('<table><thead><tr>'
                   + "".join(f'<th class="num">{c}</th>' if i <= 1 else f'<th>{c}</th>'
                             for i, c in enumerate(cols)) + '</tr></thead><tbody>')
        for iv in [iv for iv in d['iv_range'] if iv != 15]:
            e = qd[str(iv)]
            drp = e['dropped']
            cells = [f'<td class="num">{iv}</td>',
                     f'<td class="num">{e["pvp_stat"]}</td>']
            if stat == 'atk':
                cells.append(f'<td>{joinm(e.get("cmp_lost", []))}</td>')
                cells.append(f'<td>{joinm(e.get("breakpoints_lost", []))}</td>')
            elif stat == 'def':
                cells.append(f'<td>{joinm(e.get("bulkpoints_lost", []))}</td>')
            cells.append(f'<td>{joinm(drp.get("0-0", []))}</td>')
            cells.append(f'<td>{joinm(drp.get("1-1", []))}</td>')
            cells.append(f'<td>{joinm(drp.get("2-2", []))}</td>')
            out.append('<tr>' + "".join(cells) + '</tr>')
        out.append('</tbody></table>')
    return "\n".join(out) + "\n"


def rec_table(d, lvkey, meta_quad, title, note, anchor):
    rows = d['recommended']
    out = [f'<h3 id="{anchor}">{esc(title)}</h3>', f'<p class="sub">{esc(note)}</p>']
    out.append('<table><thead><tr>'
               '<th class="num">CP</th><th class="num">IVs (A/D/HP)</th>'
               '<th class="num">IV %</th><th class="num">Atk</th>'
               '<th class="num">Def</th><th class="num">HP</th>'
               '<th>Drops vs a perfect IV</th></tr></thead><tbody>')
    srt = sorted(rows, key=lambda r: (len(r['drops'][meta_quad]),
                                      -r[f'perfect_{lvkey}']))
    for r in srt:
        a, dd, s = r['ivs']
        pa, pd, ph = r[f'pvp_{lvkey}']
        drops = r['drops'][meta_quad]
        dcell = ('<span class="none">drops nothing (Premium)</span>'
                 if not drops else joinm(drops))
        out.append('<tr>'
                   f'<td class="num">{r[f"cp_{lvkey}"]}</td>'
                   f'<td class="num">{a}/{dd}/{s}</td>'
                   f'<td class="num">{r[f"perfect_{lvkey}"]:.2f}%</td>'
                   f'<td class="num">{pa}</td><td class="num">{pd}</td>'
                   f'<td class="num">{ph}</td>'
                   f'<td>{dcell}</td></tr>')
    out.append('</tbody></table>')
    return "\n".join(out) + "\n"


def verdict(d):
    out = ['<h2 id="recommended">Recommended IVs</h2>',
           '<p class="sub">Every spread with all three IVs from 12 to 15 (the '
           'practical range above the 10/10/10 legendary catch floor), sorted '
           'so the spreads that drop nothing come first. "Premium" drops no '
           'matchups versus a perfect IV in the stated case; everything else '
           'lists exactly what it gives up. The realistic meta is best-buddied, '
           'so both tables compare against a best-buddy meta.</p>']
    out.append(rec_table(
        d, 'bb', 'wbb_vs_bb',
        'If you best buddy (L51), vs a best-buddy meta',
        'CP and stats at L51; drops measured in the best-buddy vs best-buddy case.',
        'rec-bb'))
    out.append(rec_table(
        d, 'nobb', 'nobb_vs_bb',
        'If you do not best buddy (L50), vs a best-buddy meta',
        'CP and stats at L50; drops measured in the no-best-buddy vs best-buddy case.',
        'rec-nobb'))
    return "\n".join(out) + "\n"


def render(d):
    sp = esc(d['species'])
    credit_name = esc(CREDIT_NAME)
    credit_url = esc(CREDIT_URL)
    main_parts = [f"""<h2 id="covers">What this covers</h2>
<ul>
<li>{sp} against the Master League meta (PvPoke top-{d['n_opponents']}).</li>
<li>Attack, Defense, and HP IVs from 15 down to 12, compared to a perfect IV.</li>
<li>The full grid of best-buddy / no-best-buddy, for you and for the meta.</li>
<li>The minimum recommended IV spreads, and exactly what each gives up.</li>
</ul>
"""]
    main_parts.append(terms())
    main_parts.append(build_card(d))
    main_parts.append(key_winloss(d))
    main_parts.append(bb_differences(d))
    for stat in ('atk', 'def', 'hp'):
        main_parts.append(stat_section(d, stat))
    main_parts.append(verdict(d))
    main_parts.append(f"""<h2 id="method">Method and caveats</h2>
<ul>
<li>Simulator: this project's PvPoke-style 1v1 engine. A win is a higher 1v1 battle rating than the opponent.</li>
<li>Opponents: <code>{esc(d['pool'])}</code>, all modeled at a perfect IV. {esc(d['shield_convention'])}.</li>
<li>Master League has no CP cap, so L50 (regular) and L51 (best buddy) are pure level steps on both sides.</li>
<li>Breakpoints/bulkpoints are for the fast move ({esc(d['build']['fast'])}); CMP uses the attack stat.</li>
<li>{sp} assumed to know its signature move. Data: <code>scripts/iv_envelope_analysis.py</code>; rendered by <code>scripts/render_iv_envelope_article.py</code>.</li>
<li>Format, structure, and terminology adapted from <a href="{credit_url}">{credit_name}'s Master League IV deep dives</a>. The numbers are independently re-simulated, not lifted from the video.</li>
</ul>
""")
    main_html = "\n".join(main_parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{sp} Master League IV Guide</title>
<style>{style()}</style>
</head>
<body>
<div class="topbar">
<h1>{sp}: Master League IV Guide</h1>
<p class="sub">How far your IVs can slip before this Master League attacker
gives up specific matchups, with the move on it. Breakpoints, bulkpoints, CMP,
and named matchups across the full best-buddy grid.</p>
<div class="credit"><strong>Format credit:</strong> the structure, terminology,
and presentation of this guide are adapted from
<a href="{credit_url}">{credit_name}'s Master League IV deep dives</a>. In
particular the "Terms to know" vocabulary (including the "Premium" vs "Thrifty"
IV framing), and the per-stat by best-buddy by shield breakdown, follow
{credit_name}'s work. The numbers here are independently re-simulated with this
project's own engine, not taken from the video.</div>
<div class="banner"><strong>AI-drafted, not yet human-reviewed.</strong> The
data tables are auto-generated from this project's simulator; the explanatory
prose is Claude-drafted, restating {credit_name}'s framing in our own words. No
gameplay or teambuilding judgment is made here, only the mechanics and matchups.
A human should review the prose (and confirm the attribution is fair) before
this ships.</div>
</div>
<div class="layout">
{nav_html()}
<main>
{main_html}
<footer>Format adapted from <a href="{credit_url}">{credit_name}'s Master League
IV deep dives</a>; numbers independently simulated. Generated by
<code>scripts/iv_envelope_analysis.py</code> +
<code>scripts/render_iv_envelope_article.py</code>.</footer>
</main>
</div>
</body>
</html>
"""


def main():
    json_path = sys.argv[1]
    d = json.load(open(json_path))
    slug = (d['species'].lower().replace(' ', '-')
            .replace('(', '').replace(')', ''))
    outdir = f"userdata/website/articles/{slug}-ml-iv-guide"
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, 'index.html'), 'w') as f:
        f.write(render(d))
    # authorship = "ai": data tables are auto-generated, but the explanatory
    # prose is Claude-drafted (the orange "ai" tier), so the whole article is
    # AI-drafted-pending-review until a human edits the prose. Kept out of
    # ship-tracked articles/*.toml so the pre-commit policy isn't bypassed.
    meta = (f'title       = "{d["species"]} Master League IV Guide"\n'
            f'description = "AI-drafted (auto data tables + Claude-drafted prose), not yet '
            f'human-reviewed. XehrFelrose-style IV deep dive for {d["species"]} in Master '
            f'League (with the signature move): breakpoints, bulkpoints, CMP, and named '
            f'matchups given up at each IV from 15 to 12, across the full best-buddy grid, '
            f'plus recommended IV spreads. Format/terminology adapted from {CREDIT_NAME} '
            f'({CREDIT_URL}); numbers independently simulated. Human review of the prose '
            f'needed before ship."\n'
            f'authorship  = "ai"\n'
            f'landing     = "index.html"\n')
    with open(os.path.join(outdir, 'meta.toml'), 'w') as f:
        f.write(meta)
    print(f"Wrote {outdir}/index.html and meta.toml")


if __name__ == '__main__':
    main()
