#!/usr/bin/env python
"""Render an IV-envelope JSON (from iv_envelope_analysis.py) into a
XehrFelrose-style ML IV guide article, matching the pogo-dives website
article house style. Re-run freely to tweak presentation without re-simulating.

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
QUAD_ORDER = ['nobb_vs_nonbb', 'nobb_vs_bb', 'wbb_vs_nonbb', 'wbb_vs_bb']
STAT_LABEL = {'atk': 'Attack', 'def': 'Defense', 'hp': 'HP'}


def esc(s):
    return html.escape(str(s))


def joinm(lst):
    return ", ".join(esc(x) for x in lst) if lst else "-"


def style():
    return """
  body { max-width: 980px; margin: 24px auto; padding: 0 16px;
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         line-height: 1.5; color: #1a1a24; }
  h1 { margin-bottom: 0.15em; }
  h2 { margin-top: 1.8em; border-bottom: 2px solid #e3e3dc; padding-bottom: .15em; }
  h3 { margin-top: 1.3em; color: #333; }
  h4 { margin: 1em 0 .3em; color: #555; font-size: 1em; }
  code { background: #f3f3f3; padding: 1px 4px; border-radius: 3px; }
  ul li { margin-bottom: 0.35em; }
  table { border-collapse: collapse; width: 100%; margin: .6em 0 1.2em; font-size: 0.9em; }
  th, td { border: 1px solid #ddd; padding: 4px 8px; text-align: left; vertical-align: top; }
  th { background: #f4f6fb; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .banner { background: #fff3cd; border: 2px solid #ffc107; padding: 12px 16px; margin: 16px 0; border-radius: 4px; }
  .twocol { display: flex; gap: 2em; flex-wrap: wrap; }
  .twocol > div { flex: 1; min-width: 240px; }
  .terms dt { font-weight: 600; margin-top: .5em; }
  .terms dd { margin: 0 0 .2em 1.2em; color: #444; }
  .none { color: #888; }
  .sub { color: #666; font-size: .92em; }
  caption { text-align: left; font-weight: 600; color: #555; padding: .3em 0; }
"""


def build_card(d):
    b = d['build']
    bs = d['base_stats']
    return (f'<h2>The build</h2>\n<p class="sub">This guide assumes '
            f'<b>{esc(d["species"])}</b> with its signature move. Base stats '
            f'atk {bs["atk"]} / def {bs["def"]} / hp {bs["hp"]}.</p>\n'
            f'<ul><li>Fast: <code>{esc(b["fast"])}</code></li>'
            f'<li>Charged: {", ".join("<code>"+esc(c)+"</code>" for c in b["charged"])}</li></ul>\n')


def terms():
    return """<h2>Terms to know</h2>
<dl class="terms">
<dt>Breakpoint</dt><dd>An attack-stat threshold where your fast move deals 1 more damage to a specific opponent. Most impactful on fast moves that fire every turn.</dd>
<dt>Bulkpoint</dt><dd>A defense-stat threshold where a specific opponent's fast move deals 1 less damage to you.</dd>
<dt>CMP (charge-move priority)</dt><dd>When both Pokemon throw a charged move on the same turn, the one with the higher attack stat goes first. "CMP lost" means a lower attack IV drops you below an opponent's attack, so you would lose that simultaneous-throw.</dd>
<dt>0s / 1s / 2s</dt><dd>Even-shield scenarios: 0-0, 1-1, and 2-2 shields. This guide uses even shields and even energy, standard movesets.</dd>
<dt>BB (best buddy)</dt><dd>Best-buddy boost adds one level (L50 to L51). In Master League there is no CP cap, so that level fully applies.</dd>
<dt>Premium vs Thrifty IVs</dt><dd>Defined here mechanically, not as a gameplay call: a <b>Premium</b> spread drops no matchups versus a perfect (hundo) IV spread in the stated case; a <b>Thrifty</b> spread drops only the matchups listed next to it. Whether those matchups matter is your call.</dd>
</dl>
"""


def key_winloss(d):
    out = ['<h2>Versus the Master League meta</h2>']
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
    out = ['<h2>What best buddy changes (at a perfect IV)</h2>',
           '<p class="sub">Matchups best buddy (L51) gains over not best-buddying (L50), holding the meta\'s best-buddy status fixed. Even shields, perfect IV.</p>']
    for meta_key, meta_label, wbb, nobb in [
            ('nonbb', 'a non-best-buddy meta', 'wbb_vs_nonbb', 'nobb_vs_nonbb'),
            ('bb', 'a best-buddy meta', 'wbb_vs_bb', 'nobb_vs_bb')]:
        gained = sorted(hw[wbb] - hw[nobb])
        lost = sorted(hw[nobb] - hw[wbb])
        out.append(f'<h4>Vs {meta_label}</h4>')
        out.append(f'<ul><li><b>Gains:</b> {joinm(gained)}</li>')
        if lost:
            out.append(f'<li><b>Gives up:</b> {joinm(lost)}</li>')
        out.append('</ul>')
    return "\n".join(out) + "\n"


def stat_section(d, stat):
    sv = d['stat_values']
    out = [f'<h2>{STAT_LABEL[stat]} IVs</h2>']
    out.append(f'<p class="sub">{STAT_LABEL[stat]} at a perfect IV: '
               f'<b>{sv["bb"][stat]["15"]}</b> at L51 (best buddy), '
               f'<b>{sv["nobb"][stat]["15"]}</b> at L50. '
               f'Each row drops only that one stat (the other two stay 15); '
               f'matchups shown are those given up versus a perfect IV.</p>')
    for q in QUAD_ORDER:
        qd = d['quadrants'][q][stat]
        out.append(f'<h3>{esc(QUAD_LABEL[q])}</h3>')
        # header
        if stat == 'atk':
            cols = ['IV', STAT_LABEL[stat], 'CMP lost', 'Breakpoint lost',
                    '0s drops', '1s drops', '2s drops']
        elif stat == 'def':
            cols = ['IV', STAT_LABEL[stat], 'Bulkpoint lost',
                    '0s drops', '1s drops', '2s drops']
        else:
            cols = ['IV', STAT_LABEL[stat], '0s drops', '1s drops', '2s drops']
        out.append('<table><tr>'
                   + "".join(f'<th class="num">{c}</th>' if i <= 1 else f'<th>{c}</th>'
                             for i, c in enumerate(cols)) + '</tr>')
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
        out.append('</table>')
    return "\n".join(out) + "\n"


def rec_table(d, lvkey, meta_quad, title, note):
    rows = d['recommended']
    out = [f'<h3>{esc(title)}</h3>', f'<p class="sub">{esc(note)}</p>']
    out.append('<table><tr>'
               '<th class="num">CP</th><th class="num">IVs (A/D/S)</th>'
               '<th class="num">IV %</th><th class="num">Atk</th>'
               '<th class="num">Def</th><th class="num">HP</th>'
               '<th>Drops vs a perfect IV</th></tr>')
    # sort: fewest drops first, then highest IV %
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
    out.append('</table>')
    return "\n".join(out) + "\n"


def verdict(d):
    out = ['<h2>Recommended IVs</h2>',
           '<p class="sub">Every spread with all three IVs from 12 to 15 (the '
           'practical range above the 10/10/10 legendary catch floor), sorted '
           'so the spreads that drop nothing come first. "Premium" drops no '
           'matchups versus a perfect IV in the stated case; everything else '
           'lists exactly what it gives up. The realistic meta is best-buddied, '
           'so both tables compare against a best-buddy meta.</p>']
    out.append(rec_table(
        d, 'bb', 'wbb_vs_bb',
        'If you best buddy (L51), vs a best-buddy meta',
        'CP and stats at L51; drops measured in the best-buddy vs best-buddy case.'))
    out.append(rec_table(
        d, 'nobb', 'nobb_vs_bb',
        'If you do not best buddy (L50), vs a best-buddy meta',
        'CP and stats at L50; drops measured in the no-best-buddy vs best-buddy case.'))
    return "\n".join(out) + "\n"


def render(d):
    sp = esc(d['species'])
    parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{sp} Master League IV Guide</title>
<style>{style()}</style>
</head>
<body>
<h1>{sp}: Master League IV Guide</h1>
<p class="sub">How far your IVs can slip before this Master League attacker
gives up specific matchups, with the move on it. Breakpoints, bulkpoints, CMP,
and named matchups across the full best-buddy grid.</p>

<div class="banner"><strong>First-draft, auto-generated article.</strong> Every
number is from the simulator; the structure follows XehrFelrose's IV-deep-dive
format. No gameplay or teambuilding judgment is made here, only the mechanics
and matchups. Review and rewrite before shipping.</div>

<h2>What this covers</h2>
<ul>
<li>{sp} against the Master League meta (PvPoke top-{d['n_opponents']}).</li>
<li>Attack, Defense, and HP IVs from 15 down to 12, compared to a perfect IV.</li>
<li>The full grid of best-buddy / no-best-buddy, for you and for the meta.</li>
<li>The minimum recommended IV spreads, and exactly what each gives up.</li>
</ul>
"""]
    parts.append(terms())
    parts.append(build_card(d))
    parts.append(key_winloss(d))
    parts.append(bb_differences(d))
    for stat in ('atk', 'def', 'hp'):
        parts.append(stat_section(d, stat))
    parts.append(verdict(d))
    parts.append(f"""<h2>Method and caveats</h2>
<ul>
<li>Simulator: this project's PvPoke-style 1v1 engine. A win is a higher 1v1 battle rating than the opponent.</li>
<li>Opponents: <code>{esc(d['pool'])}</code>, all modeled at a perfect IV. {esc(d['shield_convention'])}.</li>
<li>Master League has no CP cap, so L50 (regular) and L51 (best buddy) are pure level steps on both sides.</li>
<li>Breakpoints/bulkpoints are for the fast move ({esc(d['build']['fast'])}); CMP uses the attack stat.</li>
<li>{sp} assumed to know its signature move. Data: <code>scripts/iv_envelope_analysis.py</code>; rendered by <code>scripts/render_iv_envelope_article.py</code>.</li>
</ul>
</body>
</html>
""")
    return "\n".join(parts)


def main():
    json_path = sys.argv[1]
    d = json.load(open(json_path))
    slug = (d['species'].lower().replace(' ', '-')
            .replace('(', '').replace(')', ''))
    outdir = f"userdata/website/articles/{slug}-ml-iv-guide"
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, 'index.html'), 'w') as f:
        f.write(render(d))
    meta = (f'title       = "{d["species"]} Master League IV Guide"\n'
            f'description = "First-draft auto-generated XehrFelrose-style IV deep dive for '
            f'{d["species"]} in Master League (with the signature move): breakpoints, '
            f'bulkpoints, CMP, and named matchups given up at each IV from 15 to 12, across '
            f'the full best-buddy grid, plus recommended IV spreads. Needs expert review before ship."\n'
            f'authorship  = "auto"\n'
            f'landing     = "index.html"\n')
    with open(os.path.join(outdir, 'meta.toml'), 'w') as f:
        f.write(meta)
    print(f"Wrote {outdir}/index.html and meta.toml")


if __name__ == '__main__':
    main()
