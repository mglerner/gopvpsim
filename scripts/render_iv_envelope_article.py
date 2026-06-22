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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from gopvpsim.attribution import PVPOKE_ATTRIBUTION_SHORT  # noqa: E402
import pvpoke_links

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
    'nobb_vs_nonbb': 'non-BB vs non-BB',
    'nobb_vs_bb':    'non-BB vs BB',
    'wbb_vs_nonbb':  'BB vs non-BB',
    'wbb_vs_bb':     'BB vs BB',
}
STAT_LABEL = {'atk': 'Attack', 'def': 'Defense', 'hp': 'HP'}
CLOSE_CALL_KIND_LABEL = {
    'shield': 'shield spent',
    'neardeath': 'near-death win',
    'energy': 'energy banked',
}

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
        ('rec-bb', 'BB vs BB'),
        ('rec-nobb', 'non-BB vs BB'),
        ('rec-bb-nonbb', 'BB vs non-BB'),
        ('rec-nobb-nonbb', 'non-BB vs non-BB'),
    ]),
    ('method', 'Method & caveats', []),
]


def esc(s):
    return html.escape(str(s))


def _a(name, link=None, fsh=1, osh=1):
    """A matchup name, linked to its pvpoke.com battle when a linker is given.
    Best-effort: any failure to build the URL falls back to plain text, so a
    bad link can never break a render."""
    if link is None:
        return esc(name)
    try:
        url = link(name, fsh, osh)
    except Exception:
        url = None
    return (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(name)}</a>'
            if url else esc(name))


def _linker(d, ivs, my_level, opp_level):
    """Return f(opp_display, fsh, osh) -> pvpoke battle URL for this focal at
    these IVs/levels vs that opponent at the given shields."""
    b = d['build']
    def fn(opp_display, fsh, osh):
        return pvpoke_links.battle_url(
            d['species'], d.get('shadow', False), ivs, my_level,
            b['fast'], b['charged'], opp_display, opp_level, fsh, osh)
    return fn


def joinm(lst, link=None, fsh=1, osh=1):
    return (", ".join(_a(x, link, fsh, osh) for x in lst) if lst
            else '<span class="none">-</span>')


EVEN_LABELS = {'0-0', '1-1', '2-2'}


def _sh_class(lab):
    return 'sh-even' if lab in EVEN_LABELS else 'sh-uneven'


def tagged_lines(by_sh, shields, link=None):
    """One <div> per shield label with drops, tagged sh-even/sh-uneven so the
    shield-view toggle can hide the uneven ones client-side."""
    out = []
    for lab in shields:
        opps = by_sh.get(lab, [])
        if opps:
            fsh, osh = lab.split('-')
            out.append(f'<div class="sh-line {_sh_class(lab)}"><b>{esc(lab)}</b> '
                       + ", ".join(_a(o, link, fsh, osh) for o in opps) + '</div>')
    return out


def join_drops(drop_strings, link=None,
               empty='<span class="none">drops nothing (Premium)</span>'):
    """Inline 'Name shield, ...' for lists of 'Name s-s' strings, linking each
    name to its battle at the parsed shield count."""
    if not drop_strings:
        return empty
    parts = []
    for s in drop_strings:
        name, lab = s.rsplit(' ', 1)
        fsh, osh = lab.split('-')
        parts.append(f'{_a(name, link, fsh, osh)} {esc(lab)}')
    return ", ".join(parts)


def drop_cell(by_sh, shields, empty_text='-', link=None):
    """Compact 'matchups dropped' cell: tagged lines + a JS-managed empty
    marker (shown when no lines are visible in the current shield view)."""
    lines = tagged_lines(by_sh, shields, link)
    if not lines:
        # No drops at all (in any view) -> static marker, no toggle needed.
        return f'<span class="none">{empty_text}</span>'
    return (f'<div class="dropcell"><span class="empty-marker none hidden">{empty_text}</span>'
            + "".join(lines) + '</div>')


def drops_to_by_sh(drop_strings):
    """Convert ['Opp Name 1-2', ...] -> {'1-2': ['Opp Name'], ...}."""
    by_sh = {}
    for s in drop_strings:
        opp, lab = s.rsplit(' ', 1)
        by_sh.setdefault(lab, []).append(opp)
    return by_sh


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
  nav.toc .nav-toggle { margin-bottom:10px; padding-bottom:9px;
                  border-bottom:1px solid var(--rule); }
  nav.toc .nav-toggle strong { display:block; color:var(--pur); font-size:12px;
                  text-transform:uppercase; letter-spacing:.04em; margin-bottom:5px; }
  nav.toc .nav-toggle label { display:inline-block; color:var(--fg);
                  margin-right:12px; padding:2px 0; cursor:pointer; font-size:12px; }
  nav.toc .nav-toggle input { margin-right:6px; vertical-align:middle; }
  .sh-line { line-height:1.4; }
  body.shields-even .sh-uneven { display:none; }
  .hidden { display:none; }
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
  nav.toc { position:sticky; top:14px; flex:0 0 260px; font-size:13px;
            background:var(--panel); border-radius:6px; padding:12px 14px;
            max-height:calc(100vh - 28px); overflow-y:auto; }
  nav.toc strong { color:var(--pur); display:block; margin-bottom:6px;
            font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  nav.toc a { display:block; color:var(--grn); padding:2px 0; }
  nav.toc .subnav { display:flex; flex-wrap:wrap; gap:1px 10px;
            padding:0 0 4px 12px; line-height:1.3; }
  nav.toc a.sub { padding:0; font-size:11.5px;
            color:var(--sub); white-space:nowrap; }
  nav.toc a.sub:hover { color:var(--grn); }
  main { flex:1; min-width:0; }
  main h2:first-child { margin-top:6px; }
  .close-calls ul { margin:4px 0 8px; padding-left:20px; }
  .close-calls > div { margin-top:6px; }
  .close-calls li { margin:2px 0; }
  .cc-tag { display:inline-block; font-size:.78em; padding:0 5px;
            border-radius:3px; vertical-align:middle; }
  .cc-shield { background:#1a2333; color:#8ab4f8; }
  .cc-energy { background:#2e2a1a; color:#e8dfcf; }
  .cc-neardeath { background:#2e1a1f; color:#e8b0b8; }
  @media (max-width:820px) {
    .layout { flex-direction:column; }
    nav.toc { position:static; flex:none; width:auto; }
  }
"""


def nav_html(compact=False):
    parts = []
    for i, l, subs in NAV:
        parts.append(f'<a href="#{i}">{esc(l)}</a>')
        if subs:
            # Flow the sub-links horizontally (wrapping) so the four
            # per-section jump links take ~one line instead of four.
            sub = "".join(f'<a class="sub" href="#{sid}">{esc(sl)}</a>'
                          for sid, sl in subs)
            parts.append(f'<div class="subnav">{sub}</div>')
    toggle = ("""<div class="nav-toggle"><strong>Shield view</strong>
<label><input type="radio" name="sv" value="all" checked> All 9 shields</label>
<label><input type="radio" name="sv" value="even"> Even only</label>
</div>""" if compact else "")
    return (f'<nav class="toc">{toggle}'
            f'<strong>On this page</strong>{"".join(parts)}</nav>')


def moveword(d):
    """Noun phrase for the build: signature-move override (BUILDS) vs the
    PvPoke default Master moveset. Used everywhere the prose names the build."""
    return ('its signature move' if d['build'].get('source') == 'signature'
            else 'its standard Master League moveset')


def build_card(d):
    b = d['build']
    bs = d['base_stats']
    return (f'<h2 id="build">The build</h2>\n<p class="sub">This guide assumes '
            f'<b>{esc(d["species"])}</b> with {moveword(d)}. Base stats '
            f'atk {bs["atk"]} / def {bs["def"]} / hp {bs["hp"]}.</p>\n'
            f'<ul><li>Fast: <code>{esc(b["fast"])}</code></li>'
            f'<li>Charged: {", ".join("<code>"+esc(c)+"</code>" for c in b["charged"])}</li></ul>\n')


def terms(d):
    shields = d['shields']
    if len(shields) > 3:
        shield_dd = ('Shield scenarios are written <b>you-opp</b> (your shields '
                     'first). This guide covers all ' + str(len(shields)) +
                     ' ordered scenarios (' + ", ".join(esc(s) for s in shields) +
                     '), so "you 2 / opp 1" (2-1) is distinct from "you 1 / opp 2" '
                     '(1-2). Even energy, standard movesets.')
    else:
        shield_dd = ('Even-shield scenarios, written you-opp: ' +
                     ", ".join(esc(s) for s in shields) +
                     '. Even energy, standard movesets.')
    return ("""<h2 id="terms">Terms to know</h2>
<dl class="terms">
<dt>Breakpoint</dt><dd>An attack-stat threshold where your fast move deals 1 more damage to a specific opponent. Most impactful on fast moves that fire every turn.</dd>
<dt>Bulkpoint</dt><dd>A defense-stat threshold where a specific opponent's fast move deals 1 less damage to you.</dd>
<dt>CMP (charge-move priority)</dt><dd>When both Pokemon throw a charged move on the same turn, the one with the higher attack stat goes first. "CMP lost" means a lower attack IV drops you below an opponent's attack, so you would lose that simultaneous-throw.</dd>
<dt>Shields (you-opp)</dt><dd>""" + shield_dd + """</dd>
<dt>BB (best buddy)</dt><dd>Best-buddy boost adds one level (L50 to L51). In Master League there is no CP cap, so that level fully applies.</dd>
<dt>Premium vs Thrifty IVs</dt><dd>Terminology from {credit_name} (<a href="{credit_url}">video</a>). Defined here mechanically, not as a gameplay call: a <b>Premium</b> spread drops no matchups versus a perfect (hundo) IV spread in the stated case; a <b>Thrifty</b> spread drops only the matchups listed next to it. Whether those matchups matter is your call.</dd>
</dl>
<p class="sub">These terms and the breakdown that follows are adapted from {credit_name}'s Master League IV deep dives.</p>
""").replace("{credit_name}", esc(CREDIT_NAME)).replace("{credit_url}", esc(CREDIT_URL))


def key_winloss(d):
    # Summarize wins/losses on the 3 EVEN shields (the high-level overview);
    # the full per-shield nuance lives in the per-stat tables below. Recomputed
    # from hundo_won so it is correct whether the JSON is even- or all-9-shield.
    out = ['<h2 id="meta">Versus the Master League meta</h2>']
    q = d['headline_quadrant']
    ml, ol = d['quadrant_levels'][q]
    evens = {'0-0', '1-1', '2-2'}
    all_opp = d['key_wins'] + d['key_losses'] + d['key_split']
    by_opp = {}
    for entry in d['hundo_won'][q]:
        opp, lab = entry.rsplit(' ', 1)
        by_opp.setdefault(opp, set()).add(lab)
    kw, kl, ks = [], [], []
    for o in all_opp:
        n = len(by_opp.get(o, set()) & evens)
        (kw if n == 3 else kl if n == 0 else ks).append(o)
    out.append(f'<p class="sub">Win/loss at a perfect IV on the 3 even shields '
               f'(0-0, 1-1, 2-2), in the <b>{esc(QUAD_LABEL[q].lower())}</b> case '
               f'(you L{int(ml)} vs opponents L{int(ol)}), vs the '
               f'{d["n_opponents"]}-strong Master top-60. The full per-shield '
               f'picture is in the stat tables below.</p>')
    # Perfect-IV summaries over the even shields; link to the headline quadrant
    # at a representative 1-1.
    link = _linker(d, (15, 15, 15), ml, ol)
    out.append('<div class="twocol">')
    out.append('<div><h3>Key wins</h3><ul>'
               + "".join(f"<li>{_a(x, link, 1, 1)}</li>" for x in kw) + '</ul></div>')
    out.append('<div><h3>Key losses</h3><ul>'
               + "".join(f"<li>{_a(x, link, 1, 1)}</li>" for x in kl) + '</ul></div>')
    out.append('</div>')
    if ks:
        out.append('<p class="sub"><b>Shield-dependent (split on even shields):</b> '
                   + joinm(ks, link, 1, 1) + '.</p>')
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
        # These are perfect-IV (15/15/15) matchups; link to the best-buddy
        # (L51) focal at this meta's level, with the entry's shields.
        my_lvl, opp_lvl = d['quadrant_levels'][wbb]
        link = _linker(d, (15, 15, 15), my_lvl, opp_lvl)
        out.append(f'<h4>Vs {meta_label}</h4>')
        out.append(f'<div><b>Gains:</b> '
                   f'{join_drops(gained, link, "<span class=\"none\">-</span>")}</div>')
        if lost:
            out.append(f'<div><b>Gives up:</b> {join_drops(lost, link)}</div>')
    out.append('</div>')
    return "\n".join(out) + "\n"


def close_calls_block(qd, iv_range, link_factory):
    """Compact 'Close calls' callout for one quadrant of a stat section: kept
    wins whose post-match margin moved enough to matter, per dropped IV. Renders
    nothing when no IV in this quadrant has any close call (keeps the article
    scannable). link_factory(iv) -> a matchup linker at that dropped IV."""
    rows = []
    for iv in [v for v in iv_range if v != 15]:
        calls = qd[str(iv)].get('close_calls') or []
        if not calls:
            continue
        link = link_factory(iv)
        items = []
        for c in calls:
            fsh, osh = c['shield'].split('-')
            tag = esc(CLOSE_CALL_KIND_LABEL.get(c['kind'], c['kind']))
            items.append(f'<li>{_a(c["opp"], link, fsh, osh)} '
                         f'<span class="sub">{esc(c["shield"])}</span> '
                         f'<span class="cc-tag cc-{esc(c["kind"])}">{tag}</span>: '
                         f'{esc(c["margin"])}</li>')
        rows.append(f'<div><b>IV {iv}:</b><ul>' + "".join(items) + '</ul></div>')
    if not rows:
        return ''
    return ('<div class="panel close-calls"><b>Close calls</b> '
            '<span class="sub">(still a win, but the post-match margin shifts '
            'enough to matter: a shield spent, a near-death survival, or roughly '
            'one fewer charged move of energy banked)</span>'
            + "".join(rows) + '</div>')


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
    shields = d['shields']
    compact = len(shields) > 3
    drop_cols = (['Matchups dropped (you-opp)'] if compact
                 else [f'{s.split("-")[0]}s drops' for s in shields])
    slot = {'atk': 0, 'def': 1, 'hp': 2}[stat]
    for q in QUAD_ORDER:
        qd = d['quadrants'][q][stat]
        my_lvl, opp_lvl = d['quadrant_levels'][q]
        out.append(f'<h3 id="{stat}-{q}">{esc(QUAD_LABEL[q])}</h3>')
        if stat == 'atk':
            cols = ['IV', STAT_LABEL[stat], 'CMP lost', 'Breakpoint lost'] + drop_cols
        elif stat == 'def':
            cols = ['IV', STAT_LABEL[stat], 'Bulkpoint lost'] + drop_cols
        else:
            cols = ['IV', STAT_LABEL[stat]] + drop_cols
        out.append('<table><thead><tr>'
                   + "".join(f'<th class="num">{c}</th>' if i <= 1 else f'<th>{c}</th>'
                             for i, c in enumerate(cols)) + '</tr></thead><tbody>')
        for iv in [iv for iv in d['iv_range'] if iv != 15]:
            e = qd[str(iv)]
            drp = e['dropped']
            fivs = [15, 15, 15]
            fivs[slot] = iv
            link = _linker(d, fivs, my_lvl, opp_lvl)
            cells = [f'<td class="num">{iv}</td>',
                     f'<td class="num">{e["pvp_stat"]}</td>']
            # CMP/breakpoint/bulkpoint are shield-independent; link them at 1-1.
            if stat == 'atk':
                cells.append(f'<td>{joinm(e.get("cmp_lost", []), link, 1, 1)}</td>')
                cells.append(f'<td>{joinm(e.get("breakpoints_lost", []), link, 1, 1)}</td>')
            elif stat == 'def':
                cells.append(f'<td>{joinm(e.get("bulkpoints_lost", []), link, 1, 1)}</td>')
            if compact:
                cells.append(f'<td>{drop_cell(drp, shields, link=link)}</td>')
            else:
                for s in shields:
                    fsh, osh = s.split('-')
                    cells.append(f'<td>{joinm(drp.get(s, []), link, fsh, osh)}</td>')
            out.append('<tr>' + "".join(cells) + '</tr>')
        out.append('</tbody></table>')
        cc_block = close_calls_block(
            qd, d['iv_range'],
            lambda iv, slot=slot, ml=my_lvl, ol=opp_lvl: _linker(
                d, [15 if j != slot else iv for j in range(3)], ml, ol))
        if cc_block:
            out.append(cc_block)
    return "\n".join(out) + "\n"


def rec_table(d, lvkey, meta_quad, title, note, anchor):
    rows = d['recommended']
    out = [f'<h3 id="{anchor}">{esc(title)}</h3>', f'<p class="sub">{esc(note)}</p>']
    out.append('<table><thead><tr>'
               '<th class="num">CP</th><th class="num">IVs (A/D/HP)</th>'
               '<th class="num">IV %</th><th class="num">Atk</th>'
               '<th class="num">Def</th><th class="num">HP</th>'
               '<th>Drops vs a perfect IV</th></tr></thead><tbody>')
    compact = len(d['shields']) > 3
    my_lvl, opp_lvl = d['quadrant_levels'][meta_quad]
    srt = sorted(rows, key=lambda r: (len(r['drops'][meta_quad]),
                                      -r[f'perfect_{lvkey}']))
    for r in srt:
        a, dd, s = r['ivs']
        pa, pd, ph = r[f'pvp_{lvkey}']
        drops = r['drops'][meta_quad]
        link = _linker(d, r['ivs'], my_lvl, opp_lvl)
        if compact:
            # grouped, shield-tagged lines so the toggle can hide uneven drops;
            # JS shows the Premium marker when no drops are visible in the view.
            dcell = drop_cell(drops_to_by_sh(drops), d['shields'],
                              'drops nothing (Premium)', link)
        else:
            dcell = join_drops(drops, link)
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
    # vs-non-best-buddy-meta tables are present only when the analysis simmed
    # all four REC_QUADRANTS; older 2-quadrant JSON still renders (BB-meta only).
    has_nonbb = 'wbb_vs_nonbb' in d['recommended'][0]['drops']
    meta_note = (
        'The first two tables compare against a best-buddied meta (the '
        'realistic, harder case); the last two against a non-best-buddied meta, '
        'which is strictly easier.' if has_nonbb else
        'The realistic meta is best-buddied, so both tables compare against a '
        'best-buddy meta.')
    out = ['<h2 id="recommended">Recommended IVs</h2>',
           '<p class="sub">Every spread with all three IVs from 12 to 15 (the '
           'practical range above the 10/10/10 legendary catch floor), sorted '
           'so the spreads that drop nothing come first. "Premium" drops no '
           'matchups versus a perfect IV in the stated case; everything else '
           f'lists exactly what it gives up. {meta_note}</p>']
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
    if has_nonbb:
        out.append(rec_table(
            d, 'bb', 'wbb_vs_nonbb',
            'If you best buddy (L51), vs a non-best-buddy meta',
            'CP and stats at L51; drops measured in the best-buddy vs '
            'no-best-buddy-meta case.',
            'rec-bb-nonbb'))
        out.append(rec_table(
            d, 'nobb', 'nobb_vs_nonbb',
            'If you do not best buddy (L50), vs a non-best-buddy meta',
            'CP and stats at L50; drops measured in the no-best-buddy vs '
            'no-best-buddy-meta case.',
            'rec-nobb-nonbb'))
    return "\n".join(out) + "\n"


def render(d):
    sp = esc(d['species'])
    credit_name = esc(CREDIT_NAME)
    credit_url = esc(CREDIT_URL)
    shieldconv = esc(d['shield_convention'])
    compact = len(d['shields']) > 3
    toggle_script = ("""
<script>
function updShields(){
  var even = document.querySelector('input[name="sv"]:checked').value === 'even';
  document.body.classList.toggle('shields-even', even);
  document.querySelectorAll('.dropcell').forEach(function(c){
    var anyVisible = Array.prototype.some.call(
      c.querySelectorAll('.sh-line'), function(l){ return l.offsetParent !== null; });
    var m = c.querySelector('.empty-marker');
    if (m) m.classList.toggle('hidden', anyVisible);
  });
}
Array.prototype.forEach.call(document.querySelectorAll('input[name="sv"]'),
  function(r){ r.addEventListener('change', updShields); });
updShields();
</script>""" if compact else "")
    main_parts = [f"""<h2 id="covers">What this covers</h2>
<ul>
<li>{sp} against the Master League meta (PvPoke top-{d['n_opponents']}).</li>
<li>Attack, Defense, and HP IVs from 15 down to 12, compared to a perfect IV.</li>
<li>The full grid of best-buddy / no-best-buddy, for you and for the meta.</li>
<li>The minimum recommended IV spreads, and exactly what each gives up.</li>
</ul>
"""]
    main_parts.append(terms(d))
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
<li>Each matchup name links to that exact battle on <a href="https://pvpoke.com">pvpoke.com</a>: this {sp} at the row's IVs and level on the left, the opponent at a perfect 15/15/15 on the right, with the stated shields. Links not tied to a single shield count -- CMP, breakpoint/bulkpoint, and the perfect-IV summary lists (key wins/losses and best-buddy changes) -- use 1-1. Opponent movesets are PvPoke's Master defaults. PvPoke's engine closely matches this project's but can differ in edge cases, so an outcome may occasionally not line up exactly.</li>
<li>{sp} modeled with {moveword(d)}. Data: <code>scripts/iv_envelope_analysis.py</code>; rendered by <code>scripts/render_iv_envelope_article.py</code>.</li>
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
gives up specific matchups, using {moveword(d)}. Breakpoints, bulkpoints, CMP,
and named matchups across the full best-buddy grid, over {shieldconv}.</p>
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
{nav_html(compact)}
<main>
{main_html}
<footer>Format adapted from <a href="{credit_url}">{credit_name}'s Master League
IV deep dives</a>; numbers independently simulated. Generated by
<code>scripts/iv_envelope_analysis.py</code> +
<code>scripts/render_iv_envelope_article.py</code>.
<br>{PVPOKE_ATTRIBUTION_SHORT}</footer>
</main>
</div>{toggle_script}
</body>
</html>
"""


def main():
    json_path = sys.argv[1]
    d = json.load(open(json_path))
    slug = (d['species'].lower().replace(' ', '-')
            .replace('(', '').replace(')', ''))
    # The all-9 guide is the canonical one (it has a built-in even-only toggle),
    # so it lives at the plain -ml-iv-guide path. A standalone even-only render
    # (if ever produced) gets a -even suffix so it won't clobber the canonical.
    variant_suffix = '-even' if d.get('variant') == 'even' else ''
    outdir = f"userdata/website/articles/{slug}-ml-iv-guide{variant_suffix}"
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
            f'League (with {moveword(d)}): breakpoints, bulkpoints, CMP, and named '
            f'matchups given up at each IV from 15 to 12, across the full best-buddy grid '
            f'over {d["shield_convention"]}, plus recommended IV spreads. '
            f'Format/terminology adapted from {CREDIT_NAME} '
            f'({CREDIT_URL}); numbers independently simulated. Human review of the prose '
            f'needed before ship."\n'
            f'authorship  = "ai"\n'
            f'landing     = "index.html"\n')
    with open(os.path.join(outdir, 'meta.toml'), 'w') as f:
        f.write(meta)
    print(f"Wrote {outdir}/index.html and meta.toml")


if __name__ == '__main__':
    main()
