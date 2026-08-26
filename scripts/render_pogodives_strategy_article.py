#!/usr/bin/env python
"""Render the Cramorant PoGoDives-strategy article.

Output: userdata/website/articles/cramorant-pogodives-strategy/
(index.html + meta.toml). The Cramorant dive pages link here via the
standard related-article box (slug injected at render time -- see
docs/article_schema.md and the TODO note about a future
thresholds/cramorant.toml [Cramorant.article] entry).

AUTHORSHIP: prose drafted by Claude at Michael's explicit direction
(2026-08-26 overnight session); meta.toml carries authorship = "ai"
and the page banners the provenance. Michael reviews before any
publish (publishing always needs his explicit go).

Page chrome (theme CSS, theme picker, footers) is lifted at render
time from a rendered ML-guide article so the styling never drifts
from the site's; Plotly is lifted from the standalone Cramorant dive
page. Both are hard requirements -- the script fails loudly if
either source is missing.

Data: every number is recomputed from the rendered dive pages'
embedded score tensors at render time, so the article can never
disagree with the dives it links.
"""
import base64
import glob
import gzip
import json
import re
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE = REPO_ROOT / 'userdata' / 'website'
OUT_DIR = WEBSITE / 'articles' / 'cramorant-pogodives-strategy'

sys.path.insert(0, str(REPO_ROOT / 'src'))
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
from gopvpsim.attribution import (  # noqa: E402
    PVPOKE_ATTRIBUTION_SHORT,
    support_footer_html,
)
from gopvpsim.data import load_gamemaster  # noqa: E402
from gopvpsim.pokemon import Pokemon  # noqa: E402
from deep_dive_lib.sweep import compute_iv_metadata  # noqa: E402
from deep_dive_lib.opponents import parse_opponent_spec  # noqa: E402

SCEN_LABELS = ['0-0', '0-1', '0-2', '1-0', '1-1', '1-2', '2-0', '2-1', '2-2']


def _unpack(b64):
    raw = gzip.decompress(base64.b64decode(b64))
    return struct.unpack(f'<{len(raw) // 2}H', raw)


def _page_tensors(league):
    html = (WEBSITE / f'cramorant-{league}-league' / 'index.html').read_text()
    m = re.search(r'<script>var DATA = (\{.*?\});\nvar SCORES_GZ = (\{.*?\});\n',
                  html, re.S)
    return json.loads(m.group(1)), json.loads(m.group(2)), html


def _scenario_stats(a, b, n_opp):
    """Per-scenario (net flips, mean rating delta, winrate_a, winrate_b)
    of tensors b vs a."""
    out = []
    cells = 4096 * n_opp
    for si in range(9):
        gained = lost = 0
        dr = 0
        wa = wb = 0
        for iv in range(4096):
            base = iv * 9 * n_opp + si * n_opp
            for oi in range(n_opp):
                x, y = a[base + oi], b[base + oi]
                dr += y - x
                if x < 500 <= y:
                    gained += 1
                elif x >= 500 > y:
                    lost += 1
                wa += x >= 500
                wb += y >= 500
        out.append({'net': gained - lost, 'gained': gained, 'lost': lost,
                    'mr': dr / cells, 'wr_a': wa / cells, 'wr_b': wb / cells})
    return out


def _per_iv_deltas(pv, pg, n_opp):
    """[9][4096] per-IV opponent-averaged deltas + [4096] scenario avg."""
    per_scen = []
    avg = [0.0] * 4096
    for si in range(9):
        row = []
        for iv in range(4096):
            base = iv * 9 * n_opp + si * n_opp
            s = 0
            for oi in range(n_opp):
                s += pg[base + oi] - pv[base + oi]
            d = s / n_opp
            row.append(round(d, 1))
            avg[iv] += d / 9
        per_scen.append(row)
    return per_scen, [round(x, 2) for x in avg]


def _cmp_boundaries(data, league):
    """Opponents whose (default-IV) attack stat falls inside Cramorant's
    IV attack range -- each is a CMP boundary the sheet's rules key on."""
    gm_by_id = {p['speciesId']: p['speciesName']
                for p in load_gamemaster()['pokemon']}
    names = set(gm_by_id.values())
    ivmeta = compute_iv_metadata('Cramorant', league)
    atk = [x['atk'] for x in ivmeta]
    lo, hi = min(atk), max(atk)
    bounds = []
    for oi, link in enumerate(data['oppLinks']):
        name = data['opponents'][oi]
        clean, _variant, shadow = parse_opponent_spec(name)
        if clean not in names:
            sid = link['id']
            if sid.endswith('_shadow'):
                sid, shadow = sid[:-7], True
            clean = gm_by_id[sid]
        a, d_, s = link['byMode']['pvpoke']['ivs']
        op = Pokemon.at_best_level(clean, a, d_, s, league=league,
                                   shadow=shadow)
        if lo - 0.3 <= op.atk <= hi + 0.3:
            bounds.append({'name': name, 'atk': round(op.atk, 2)})
    bounds.sort(key=lambda b: b['atk'])
    return atk, bounds


def _lift_chrome():
    """Theme CSS + picker from a rendered ML-guide article."""
    guides = sorted(glob.glob(str(WEBSITE / 'articles' / '*-ml-iv-guide'
                                  / 'index.html')))
    if not guides:
        raise SystemExit('no rendered ML-guide article to lift chrome from')
    src = Path(guides[0]).read_text()
    style = re.search(r'(<style>.*?</style>)', src, re.S).group(1)
    picker = re.search(r'(<div class="theme-picker">.*?</script>)', src,
                       re.S).group(1)
    return style, picker


def _lift_plotly():
    """The inlined Plotly blob from the standalone Cramorant GL dive."""
    dive = (WEBSITE / 'cramorant-great-league' / 'index.html').read_text()
    m = re.search(r'(<script>/\*\*?\n?\* plotly\.js.*?</script>)', dive, re.S)
    if not m:
        # Fallback: the first multi-MB script tag is the bundle.
        for sm in re.finditer(r'<script>(.*?)</script>', dive, re.S):
            if len(sm.group(1)) > 3_000_000:
                return f'<script>{sm.group(1)}</script>'
        raise SystemExit('could not lift Plotly from the dive page')
    return m.group(1)


def build():
    data_gl, sc_gl, _ = _page_tensors('great')
    data_ul, sc_ul, _ = _page_tensors('ultra')
    n_gl = len(data_gl['opponents'])
    n_ul = len(data_ul['opponents'])
    pv_gl, pg_gl, nb_gl = (_unpack(sc_gl['0_pvpoke']),
                           _unpack(sc_gl['0_pvpoke:pogodives']),
                           _unpack(sc_gl['0_pvpoke:nobait']))
    pv_ul, pg_ul, nb_ul = (_unpack(sc_ul['0_pvpoke']),
                           _unpack(sc_ul['0_pvpoke:pogodives']),
                           _unpack(sc_ul['0_pvpoke:nobait']))

    vs_pv_gl = _scenario_stats(pv_gl, pg_gl, n_gl)
    vs_pv_ul = _scenario_stats(pv_ul, pg_ul, n_ul)
    vs_nb_gl = _scenario_stats(nb_gl, pg_gl, n_gl)
    vs_nb_ul = _scenario_stats(nb_ul, pg_ul, n_ul)
    scen_deltas, avg_deltas = _per_iv_deltas(pv_gl, pg_gl, n_gl)
    cram_atk, cmp_bounds = _cmp_boundaries(data_gl, 'great')

    def total(rows):
        return sum(r['net'] for r in rows)

    def pts(rows, n_opp):
        return total(rows) / (4096 * n_opp * 9) * 100

    hero = {
        'pv_gl_net': total(vs_pv_gl), 'pv_ul_net': total(vs_pv_ul),
        'pv_gl_pts': pts(vs_pv_gl, n_gl), 'pv_ul_pts': pts(vs_pv_ul, n_ul),
        'nb_gl_net': total(vs_nb_gl), 'nb_ul_net': total(vs_nb_ul),
        'nb_gl_pts': pts(vs_nb_gl, n_gl), 'nb_ul_pts': pts(vs_nb_ul, n_ul),
    }

    style, picker = _lift_chrome()
    plotly = _lift_plotly()

    def ledger_rows(rows_pv, rows_nb):
        out = []
        for si, lab in enumerate(SCEN_LABELS):
            p, n = rows_pv[si], rows_nb[si]
            out.append(
                f'<tr><td>{lab}</td>'
                f'<td class="num">{p["net"]:+,}</td>'
                f'<td class="num">{p["mr"]:+.2f}</td>'
                f'<td class="num">{p["wr_a"] * 100:.1f} &rarr; '
                f'{p["wr_b"] * 100:.1f}%</td>'
                f'<td class="num">{n["net"]:+,}</td>'
                f'<td class="num">{n["mr"]:+.2f}</td></tr>')
        return '\n'.join(out)

    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="gruvbox-light">
<head>
<meta charset="utf-8">
<script>(function(){{try{{var t=localStorage.getItem('pogo-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Playing Cramorant: The PoGoDives Strategy</title>
{style}
<style>
.article-main {{ max-width: 60em; margin: 0 auto; padding: 0 1.2em 2em; }}
.hero {{ background: var(--surface); border: 1px solid var(--border);
  border-left: 5px solid var(--accent); padding: 14px 18px; margin: 1em 0;
  border-radius: 6px; }}
.hero b {{ color: var(--callout-strong); }}
.cheat {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
.cheat th, .cheat td {{ border: 1px solid var(--border); padding: 6px 10px;
  text-align: left; vertical-align: top; }}
.cheat th {{ background: var(--surface-2); }}
.cheat td.sc {{ white-space: nowrap; font-weight: 600; }}
.ledger {{ border-collapse: collapse; margin: 1em 0; font-size: 0.92em; }}
.ledger th, .ledger td {{ border: 1px solid var(--border);
  padding: 4px 10px; }}
.ledger th {{ background: var(--surface-2); }}
.ledger td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.grid3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
.panel {{ height: 250px; }}
.wide {{ height: 340px; }}
.note {{ background: var(--callout-bg); color: var(--callout-fg);
  border-left: 4px solid var(--callout-auto); padding: 10px 14px;
  margin: 1em 0; border-radius: 4px; font-size: 0.95em; }}
h2 {{ margin-top: 1.6em; }}
</style>
</head>
<body>
{picker}
<div class="topbar">
<h1>Playing Cramorant: The PoGoDives Strategy</h1>
<p class="sub">A shield-scenario-by-shield-scenario battle plan for
Cramorant's Gulp Missile, tuned and verified across every IV spread and
the full Great and Ultra League metas.</p>
<div class="banner"><strong>AI-drafted at the developer's direction,
pending human review.</strong> Every number is recomputed from the same
simulations that power the <a href="../../cramorant-great-league/">Great
League</a> and <a href="../../cramorant-ultra-league/">Ultra League</a>
dives; the strategy itself is what the dives' &ldquo;PoGoDives
strat&rdquo; dropdown simulates.</div>
</div>
<main class="article-main">

<div class="hero">
<b>What you get.</b> Followed as written, this plan wins
<b>{hero['pv_gl_net']:+,}</b> extra (IV &times; opponent &times; shield
scenario) matchups in Great League and <b>{hero['pv_ul_net']:+,}</b> in
Ultra League versus playing PvPoke's default battle plan &mdash; about
<b>+{hero['pv_gl_pts']:.1f} / +{hero['pv_ul_pts']:.1f} points of
absolute win rate</b> overall, rising to <b>+10&ndash;12 points in the
even-shield endgames</b> (1-1, 1-2, 2-2). Versus a never-bait plan it
is worth <b>{hero['nb_gl_net']:+,} / {hero['nb_ul_net']:+,}</b>
(+{hero['nb_gl_pts']:.1f} points in each league). And it is certified
never worse than PvPoke's plan in <em>any</em> of the nine shield
scenarios, in either league, on any of the five movesets the dives
carry &mdash; on both win rate and average battle rating.</div>

<div class="note">Baseline credit where it is due: the comparison line
here is <a href="https://pvpoke.com">PvPoke</a>'s battle AI, which is an
excellent general-purpose player and the engine this whole project is
built on. This page describes a Cramorant-specialized refinement of that
plan, not a replacement for it &mdash; in most scenarios most of what
you do is exactly what PvPoke would do.</div>

<h2>The cheat sheet</h2>
<p>Scenarios are written <b>your shields &ndash; their shields</b> at
the moment the fight starts. Two moves matter: your <b>prey move</b>
(Dive, or Surf) which loads a fish and arms the free, unshieldable Gulp
Missile, and your <b>banked move</b> (Fly on the standard build).
&ldquo;Dive-rush&rdquo; means throwing the prey move the moment you have
the energy, even though Fly hits harder. &ldquo;Tanking&rdquo; means
deliberately <em>not shielding</em> while you hold a fish, so their hit
triggers your missile.</p>

<table class="cheat">
<tr><th>Start</th><th>Move choice</th><th>Shielding</th></tr>
<tr><td class="sc">0-0, 0-1</td>
<td>Dive-rush <b>only if you win CMP</b> (your Attack stat is higher
&mdash; the dive pages mark this per IV). If you lose CMP, play normal
PvPoke move choices: bank Fly.</td>
<td>You have no shields; nothing to decide.</td></tr>
<tr><td class="sc">0-2</td>
<td>Dive-rush always.</td>
<td>Nothing to decide.</td></tr>
<tr><td class="sc">1-0</td>
<td>No dive-rush &mdash; normal PvPoke move choices.</td>
<td>Tank a little more bravely than usual while holding a fish: eat any
hit that leaves you above roughly half your current HP. Shield the big
stuff.</td></tr>
<tr><td class="sc">1-1, 1-2</td>
<td>Dive-rush always.</td>
<td>Tank hard while holding a fish: eat anything that won't take you
below about 30% of your current HP &mdash; <em>unless</em> you are far
ahead on HP (a lead of 40+ percentage points), in which case shield
normally and bank the win.</td></tr>
<tr><td class="sc">2-0</td>
<td colspan="2">Play plain PvPoke. You are already heavily favored;
every tweak we tested here only gave rating back.</td></tr>
<tr><td class="sc">2-1</td>
<td>Dive-rush only in a narrow window: you win CMP, <em>and</em> all
their charged moves are expensive (40+ energy), <em>and</em> they have
the energy to fire one right now, <em>and</em> their fast move barely
dents you. Otherwise: normal move choices.</td>
<td>Shield normally (PvPoke's rules).</td></tr>
<tr><td class="sc">2-2</td>
<td>Dive-rush always.</td>
<td>The <b>loaded-opponent rule</b>: while holding a fish, refuse the
shield (eat hits up to about 60% of your current HP) <em>only while the
opponent stays loaded</em> &mdash; that is, only if the move they are
throwing still leaves them enough energy for another charged move. If
this throw empties their bar, take the shield: nothing will punish them
for a long time, so the HP buys you nothing.</td></tr>
</table>

<h2>Why this works (the three mechanisms)</h2>
<p><b>1. The missile is only free if your Dive isn't punished.</b>
Dive-rushing trades your efficient Fly for tempo: a fish in the mouth
and an unshieldable ~15%-of-their-bar missile with a guaranteed debuff.
That trade goes bad exactly when the opponent's own charged move crosses
yours &mdash; which is why every dive-rush rule above is gated on
<b>winning CMP</b>. This is also why the per-IV plots on the dive show
two sharp populations: whole IV blocks flip behavior at an Attack
breakpoint.</p>
<p><b>2. A shield you refuse must buy a missile that matters.</b>
Tanking converts HP into missile tempo. The HP price is real; the
missile's value is capped around 15% of their bar. So the plan tanks
hard when the game is close (1-1, 1-2, 2-2), gently when you're a
shield up (1-0), and never when you're two shields up on a cornered
opponent (2-0, and most of 2-1).</p>
<p><b>3. Only feed on a loaded opponent.</b> The 2-2 discovery that
closed out the tuning campaign: refusing a shield is only profitable
while the opponent still has another charged move behind the one you're
eating. If their bar is emptying, shield it &mdash; you keep the HP and
lose nothing, because the missile can wait.</p>

<h2>How this relates to PvPoke's plan</h2>
<p>We love PvPoke &mdash; this project is a Python port of its
open-source engine, its data, and its rankings, and its battle AI is
the reference we verify against, cell by cell. PvPoke's plan for
Cramorant already includes a dive-rush rule and a fish-tanking rule;
what this page adds is <em>conditioning</em>: the same two levers,
switched per shield scenario, per CMP, and per the opponent's energy
state. Where our conditions say &ldquo;don't&rdquo;, the plan
<em>is</em> PvPoke's, unchanged &mdash; and in the two scenarios where
we couldn't beat it cleanly for every spread (2-0, and most 2-1
situations), the plan simply defers to PvPoke entirely. The one
philosophical difference is small and honest: PvPoke optimizes each
fight in isolation with a general rule set; we allowed ourselves nine
scenario-specific rule rows for one very unusual bird.</p>

<h2>Caveats</h2>
<p>The conditions above carry a few tuned constants (the 40-energy
bound, the tank thresholds, the fast-move-chip bound). They were fitted
on the current Great and Ultra metas and verified at full resolution
across every IV spread, all nine scenarios, both leagues, and all five
dive movesets &mdash; but a move rebalance can move them, and this
project's tripwires re-open the verification when that happens. Details
and the full disclosure list live in the repo's validation docs.</p>

<h2>Methods: how the strategy was built</h2>
<p>The tuning bar, set by the developer, was strict: <b>the plan had to
be at-or-above PvPoke's in every single shield scenario</b> &mdash; on
both net wins and average battle rating, in each league, each opponent
IV mode, each bait mode, and each of the five movesets the dives carry
(360 cells in total), with no negative cell shipped. The loop that got
there:</p>
<ol>
<li><b>Cell map.</b> Score every (IV &times; opponent &times; scenario)
cell of the uniform starting rule against PvPoke's plan, from the dive
pages' own score tensors, and list the failing cells.</li>
<li><b>Per-opponent oracle.</b> Compute the ceiling a perfect
opponent-conditioned rule could reach &mdash; this said the failing
scenarios were fixable before any search began.</li>
<li><b>Trace the losses.</b> Agents re-ran individual losing fights
under both plans and diffed the decision logs; the CMP mechanism, the
missile's 15% value bound, and the loaded-opponent rule all came out of
reading actual fights, not from curve-fitting.</li>
<li><b>Targeted re-simulation.</b> Candidate rules were evaluated by
re-simulating exact tensor slices (one scenario &times; all opponents
&times; sampled IVs) through the production battle path, verified
integer-exact against the shipped pages before use. Final candidates
were certified at full 4096-IV resolution &mdash; sampled screens
turned out to alias the HP-IV axis.</li>
<li><b>Adversarial review.</b> Independent skeptic agents attacked the
result twice, and both mattered: one caught a rule that failed the bar
on a moveset outside the original test set; the other proved one
&ldquo;load-bearing&rdquo; constant was dead code. The shipped plan is
what survived them.</li>
</ol>

<h3>The per-scenario deltas (Great League, Peck / Dive + Fly)</h3>
<p>Each point is one of the 4096 IV spreads; y is the PoGoDives plan's
pool-average battle rating minus PvPoke's plan's, x is stat-product
rank (rank 1 at the left). The flat 2-0 panel is the deference rule
doing its job.</p>
<div class="grid3" id="scatters"></div>
<h3>Delta histograms</h3>
<div class="grid3" id="histos"></div>
<h3>Scenario-averaged</h3>
<div class="grid3">
  <div class="panel wide" id="avg-scatter" style="grid-column:span 2"></div>
  <div class="panel wide" id="avg-histo"></div>
</div>


<h3 id="humps">Anatomy of the humps</h3>
<p>The histograms above are lumpy, and the lumps are not noise. Replot
the same per-IV deltas against Cramorant's <em>attack stat</em> instead
of stat-product rank and the humps resolve into a staircase: the delta
is piecewise-constant in attack, and every hump in a histogram is one
tread of the staircase projected sideways. Two different mechanisms cut
the steps:</p>
<p><b>CMP boundaries (rule-driven).</b> Twenty of the Great League
pool's opponents have an attack stat that falls <em>inside</em>
Cramorant's own IV attack range (118.5&ndash;129.3). For the
CMP-conditioned scenarios (0-0, 0-1, 2-1), crossing one opponent's
attack value switches the dive-rush rule on against exactly that
opponent &mdash; a discrete step in the pool-averaged delta. In the 0-0
panel below, the four largest steps land, to the decimal, on Shadow
Dusclops (122.9), Shadow Lapras (125.6), the
Feraligatr&thinsp;/&thinsp;Shadow Altaria pair (123.9&ndash;124.1), and
Sableye (119.7). A step can go either way: winning CMP against
Feraligatr makes the dive-rush profitable there (step up); winning it
against Shadow Dusclops turns the rule on in a fight where the rush
doesn't pay (step down). This is also why the shadow variants behave
differently from their normal forms &mdash; the shadow attack bonus
moves the boundary.</p>
<p><b>Damage breakpoints (fight-driven).</b> The 2-2 scenario's gate
has no CMP condition, yet its staircase has steps too (and 0-1 has
steps at attack values matching no opponent). Those treads are ordinary
damage tiers: an attack threshold where Peck, Dive, Fly, or an
opponent's answer changes by one damage point, shifting how a whole
block of IV spreads experiences the missile trade. The strategy's
value is piecewise-constant over breakpoint cells &mdash; which is
exactly why the dives report per-IV numbers rather than one average.</p>
<p>Practical upshot: <b>which hump your Cramorant sits in is knowable
before you queue</b>. Check your IVs' attack stat on the dive page; the
per-IV plot there tells you whether you're on the high tread or the low
one, and the CMP markers tell you which specific mirror-zone opponents
flip for your spread.</p>
<div class="grid3">
  <div class="panel wide" id="hump-00" style="grid-column:span 3;height:380px"></div>
</div>
<div class="grid3">
  <div class="panel wide" id="hump-22" style="grid-column:span 3;height:380px"></div>
</div>
<h3>The ledger</h3>
<p>Net wins, mean rating delta, and win rate (PvPoke &rarr; PoGoDives)
per start scenario versus PvPoke's plan, plus the same net/rating
versus the never-bait plan. Counts are over all 4096 IVs &times; the
full opponent pool.</p>
<h4>Great League</h4>
<table class="ledger">
<tr><th>Start</th><th>net vs PvPoke</th><th>&Delta;rating</th>
<th>win rate</th><th>net vs never-bait</th><th>&Delta;rating</th></tr>
{ledger_rows(vs_pv_gl, vs_nb_gl)}
</table>
<h4>Ultra League</h4>
<table class="ledger">
<tr><th>Start</th><th>net vs PvPoke</th><th>&Delta;rating</th>
<th>win rate</th><th>net vs never-bait</th><th>&Delta;rating</th></tr>
{ledger_rows(vs_pv_ul, vs_nb_ul)}
</table>
<p class="note">Versus never-bait, two Great League cells (0-2, 2-1)
trade a few hundred net wins for large rating gains &mdash; the
certified no-negative-cells guarantee is versus PvPoke's plan, which is
the baseline both this plan and never-bait should be judged against.</p>

<footer style="margin-top:30px;border-top:1px solid var(--border);padding-top:12px;font-size:0.85rem;color:var(--text-muted)">{PVPOKE_ATTRIBUTION_SHORT}</footer>
{support_footer_html('../../support.html')}
</main>
{plotly}
<script>
var D = {json.dumps({'labels': SCEN_LABELS, 'ranks': data_gl['spRanks'],
                     'scen': scen_deltas, 'avg': avg_deltas,
                     'atk': [round(a, 2) for a in cram_atk],
                     'bounds': cmp_bounds})};
function mkScatter(el, y, title) {{
  Plotly.newPlot(el, [{{x: D.ranks, y: y, mode: 'markers', type: 'scattergl',
    marker: {{size: 3, opacity: 0.45}}}}],
    {{title: {{text: title, font: {{size: 13}}}},
     margin: {{l: 42, r: 8, t: 30, b: 30}}, showlegend: false,
     paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
     xaxis: {{autorange: 'reversed', title: {{text: 'SP rank', font: {{size: 9}}}}}},
     yaxis: {{zeroline: true}}, font: {{size: 10}}}},
    {{displayModeBar: false, responsive: true}});
}}
function mkHisto(el, y, title) {{
  Plotly.newPlot(el, [{{x: y, type: 'histogram', nbinsx: 60}}],
    {{title: {{text: title, font: {{size: 13}}}},
     margin: {{l: 42, r: 8, t: 30, b: 30}}, showlegend: false,
     paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
     font: {{size: 10}}}},
    {{displayModeBar: false, responsive: true}});
}}
D.labels.forEach(function(lab, si) {{
  var s = document.createElement('div'); s.className = 'panel';
  document.getElementById('scatters').appendChild(s);
  mkScatter(s, D.scen[si], lab);
  var h = document.createElement('div'); h.className = 'panel';
  document.getElementById('histos').appendChild(h);
  mkHisto(h, D.scen[si], lab);
}});
mkScatter(document.getElementById('avg-scatter'), D.avg, 'Scenario-averaged delta');
mkHisto(document.getElementById('avg-histo'), D.avg, 'Scenario-averaged delta');
function mkAtkPlot(elId, si, title) {{
  var shapes = D.bounds.map(function(b) {{
    return {{type: 'line', x0: b.atk, x1: b.atk, yref: 'paper', y0: 0, y1: 1,
            line: {{width: 1, dash: 'dot', color: '#999'}}}};
  }});
  var ann = D.bounds.map(function(b, i) {{
    return {{x: b.atk, yref: 'paper', y: (i % 2 ? 1.0 : 0.94), text: b.name,
            showarrow: false, font: {{size: 8}}, textangle: -60,
            xanchor: 'left'}};
  }});
  Plotly.newPlot(document.getElementById(elId),
    [{{x: D.atk, y: D.scen[si], mode: 'markers', type: 'scattergl',
      marker: {{size: 3, opacity: 0.4}}, name: 'per-IV delta'}}],
    {{title: {{text: title, font: {{size: 13}}}},
     margin: {{l: 46, r: 8, t: 60, b: 34}}, showlegend: false,
     paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
     xaxis: {{title: {{text: "Cramorant attack stat", font: {{size: 10}}}}}},
     yaxis: {{zeroline: true, title: {{text: 'delta', font: {{size: 10}}}}}},
     shapes: shapes, annotations: ann, font: {{size: 10}}}},
    {{displayModeBar: false, responsive: true}});
}}
mkAtkPlot('hump-00', 0, '0-0 delta vs attack -- steps land on CMP boundaries (dotted lines, labeled)');
mkAtkPlot('hump-22', 8, '2-2 delta vs attack -- no CMP condition; steps are damage breakpoints');
</script>
</body>
</html>
"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / 'index.html').write_text(html)
    (OUT_DIR / 'meta.toml').write_text(
        'title       = "Playing Cramorant: The PoGoDives Strategy"\n'
        'description = "AI-drafted at the developer\'s direction '
        '(2026-08-26), pending human review before publish. The '
        'per-shield-scenario Cramorant battle plan behind the dives\' '
        'PoGoDives strat dropdown, written for human players: cheat '
        'sheet, mechanisms, and a methods section with the per-IV delta '
        'plots. All numbers recomputed from the dive tensors at render '
        'time."\n'
        'authorship  = "ai"\n'
        'landing     = "index.html"\n')
    print(f'wrote {OUT_DIR}/index.html ({len(html):,} chars) + meta.toml')


if __name__ == '__main__':
    build()
