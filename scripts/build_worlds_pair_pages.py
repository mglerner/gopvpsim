#!/usr/bin/env python
"""Worlds 2026 per-pair detail pages (plan product 4: amber pairs only).

One root-level page per unordered amber pair WITH baked Tier-2 grids:
``worlds-pair-<a>--<b>.html``. Each direction section shows, per
IV-decided scenario, the full-grid counts + an SVG robustness curve
(fraction of the opponent's top-512 cohort beaten, by focal SP rank),
and a closed-form reach-or-deny strip (worlds_tier0). Pairs whose
grids are deferred get no page -- the hub prints the deferred list --
and links are only emitted where the target exists (ship-gate rule).

Honesty rules:

* The reach-or-deny strip is DAMAGE-PLAN arithmetic (energy-legal
  n_fast x fast + n_charged x charged >= HP), labeled as such -- it is
  not a full-battle guarantee; the grids above it are the battle truth.
* guarantee (cohort-max) vs per-spread (rank-1 anchor) quantities are
  printed as separate columns, never conflated (the session-2 review's
  PROP): DragapultSim's 110.21-style number is the guarantee column.
* Every printed cutoff is boundary-confirmed AT RENDER TIME against the
  engine's damage function (total damage crosses HP exactly at the
  cutoff, and falls short one float below) -- a failed confirmation
  aborts the build rather than shipping an unverified threshold.
* Stage-movable pairs carry the stage-0 flag (worlds_tier0
  movable_stage_axes); form-change pairs (Aegislash) get the
  closed-form exclusion footnote instead of a strip.
* Charts follow the site chart conventions: single series (bait mode),
  theme tokens only, native <title> tooltips, and the counts table as
  the text/table view.
"""
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from gopvpsim.pokemon import iv_rank
from gopvpsim.moves import get_moves, parse_types
from gopvpsim.pokemon import find_pokemon_entry

from build_website_index import _page_shell, WEBSITE_DIR  # noqa: E402
from build_worlds_pages import (  # noqa: E402
    esc, sheet_filename, WORLDS_CSS, SCEN_LABELS, provenance_html,
)
import worlds_planes as wp  # noqa: E402
import worlds_render_data as wrd  # noqa: E402
import worlds_tier2 as t2  # noqa: E402
import worlds_tier0 as t0  # noqa: E402

PAIR_CSS = WORLDS_CSS + """
  .curve { display: block; max-width: 100%; }
  .counts { color: var(--text-muted); font-size: 13px; margin: 4px 0 10px; }
  .counts strong { color: var(--text); }
  table.reach { border-collapse: collapse; font-size: 13px; width: 100%; }
  table.reach th, table.reach td { border-bottom: 1px solid var(--border);
        padding: 4px 8px; text-align: right;
        font-variant-numeric: tabular-nums; }
  table.reach th:first-child, table.reach td:first-child {
        text-align: left; }
  .stageflag { color: var(--flip); font-size: 12px; }
  .confirmed { color: var(--win); font-size: 12px; }
"""


def pair_page_filename(a, b):
    a, b = sorted((a, b))
    return f'worlds-pair-{a}--{b}.html'


# ---------------------------------------------------------------------------
# Reach-or-deny (closed-form, boundary-confirmed)
# ---------------------------------------------------------------------------

def _min_legal_fast(cm_energy, fm_gain, n_charged):
    """Minimal fast-move count funding ``n_charged`` charged moves from
    zero energy."""
    return math.ceil(n_charged * cm_energy / fm_gain)


def reach_rows(focal_entry, opp_entry, focal_ranked, opp_cohort):
    """Reach-or-deny rows for one direction, or None when closed-form
    excluded. Each row is boundary-confirmed against the engine damage
    function; a failure raises (never ship an unverified cutoff)."""
    if (t0.closed_form_excluded(focal_entry['species'])
            or t0.closed_form_excluded(opp_entry['species'])):
        return None
    fast_db, charged_db = get_moves()
    fm = dict(fast_db[focal_entry['fast_move_id']])
    focal_mon = find_pokemon_entry(focal_entry['species'])
    opp_mon = find_pokemon_entry(opp_entry['species'])
    ftypes, otypes = parse_types(focal_mon), parse_types(opp_mon)
    id2name = dict(zip(focal_entry['charged_move_ids'],
                       focal_entry['charged_moves']))
    (f_atk_mov, f_def_mov), (o_atk_mov, o_def_mov) = t0.movable_stage_axes(
        (fm, [dict(charged_db[c]) for c in focal_entry['charged_move_ids']]),
        (dict(fast_db[opp_entry['fast_move_id']]),
         [dict(charged_db[c]) for c in opp_entry['charged_move_ids']]))
    stage_flag = f_atk_mov or o_def_mov
    anchor = opp_cohort[0]              # opponent rank-1 SP spread
    atk4096 = np.asarray([r['atk'] for r in focal_ranked])
    atk512 = atk4096[:512]
    rows = []
    for cid in focal_entry['charged_move_ids']:
        cm = dict(charged_db[cid])
        if not cm.get('power', 0) > 0:
            continue
        for n_charged in (1, 2):
            n_fast = _min_legal_fast(cm['energy'], fm['energyGain'],
                                     n_charged)
            try:
                guar, binding = t0.guarantee_cutoff(
                    fm, cm, n_fast, n_charged, ftypes, otypes, opp_cohort)
                per = t0.ko_cutoff(fm, cm, n_fast, n_charged, anchor['hp'],
                                   ftypes, otypes, anchor['def_'])
            except t0.ClosedFormError:
                continue
            # Boundary confirmation at render time: the plan's total
            # damage crosses the binding HP exactly at the cutoff and
            # falls short one representable float below it.
            for cutoff, tgt in ((guar, binding), (per, anchor)):
                tot = (n_fast * t0.staged_damage(fm, cutoff, tgt['def_'],
                                                 ftypes, otypes)
                       + n_charged * t0.staged_damage(cm, cutoff,
                                                      tgt['def_'],
                                                      ftypes, otypes))
                below = math.nextafter(cutoff, -math.inf)
                tot_b = (n_fast * t0.staged_damage(fm, below, tgt['def_'],
                                                   ftypes, otypes)
                         + n_charged * t0.staged_damage(cm, below,
                                                        tgt['def_'],
                                                        ftypes, otypes))
                if not (tot >= tgt['hp'] and tot_b < tgt['hp']):
                    raise RuntimeError(
                        f'boundary confirmation FAILED for '
                        f'{focal_entry["species_id"]} {cid} x{n_charged}: '
                        f'cutoff {cutoff} vs hp {tgt["hp"]}')
            rows.append({
                'move': id2name.get(cid, cid),
                'n_fast': n_fast, 'n_charged': n_charged,
                'guarantee': guar,
                'binding': binding,
                'per_spread': per,
                'reach4096': int((atk4096 >= guar).sum()),
                'reach512': int((atk512 >= guar).sum()),
                'reach_anchor512': int((atk512 >= per).sum()),
            })
    return {'rows': rows, 'stage_flag': stage_flag,
            'fast_name': focal_entry['fast_move'],
            'anchor': anchor}


def reach_table_html(reach, focal_name, opp_name):
    if reach is None:
        return ('<p class="section-intro">Closed-form reach/deny is '
                'footnoted OUT for this pair: a form-change side '
                '(Aegislash) makes "atk >= cutoff" cards wrong in sign, '
                'not just imprecise (Blade attack is non-monotone in the '
                'Shield attack IV). The grids above are the only honest '
                'surface.</p>')
    if not reach['rows']:
        return '<p class="section-intro">No closed-form plan applies.</p>'
    a = reach['anchor']
    rows_html = ''.join(
        f'<tr><td>{r["n_charged"]}x {esc(r["move"])} + {r["n_fast"]}x '
        f'{esc(reach["fast_name"])}</td>'
        f'<td>{r["guarantee"]:.2f}</td>'
        f'<td>{r["per_spread"]:.2f}</td>'
        f'<td>{r["reach512"]}/512 <span class="mband">('
        f'{r["reach4096"]}/4096)</span></td>'
        f'<td>{r["reach_anchor512"]}/512</td></tr>'
        for r in reach['rows'])
    flag = ('<p class="stageflag">Stage-0 numbers: this pair carries a '
            'stat-stage-moving move, so in-battle stages can shift these '
            'cutoffs (deny cutoffs shift optimistically). Grids above '
            'include all stage effects.</p>' if reach['stage_flag'] else '')
    return f"""
<div class="table-scroll"><table class="reach">
<tr><th>damage plan (energy-legal)</th>
<th>guarantee atk (beats every top-512 {esc(opp_name)})</th>
<th>atk vs rank-1 ({a['atk_iv']}/{a['def_iv']}/{a['sta_iv']})</th>
<th>{esc(focal_name)} top-512 spreads reaching guarantee</th>
<th>reaching rank-1 cutoff</th></tr>
{rows_html}
</table></div>
<p class="confirmed">Every cutoff above is boundary-confirmed against
the engine damage function at render time (crosses at the printed
value, falls short one float below).</p>
<p class="section-intro">These are DAMAGE-PLAN thresholds (minimal
energy-legal plan from zero energy), not full-battle guarantees --
shields, energy timing and bulk live in the grids above. Guarantee vs
rank-1 columns are different quantities on purpose.</p>
{flag}"""


# ---------------------------------------------------------------------------
# Robustness curve (SVG, single series, theme tokens, <title> tooltips)
# ---------------------------------------------------------------------------

def curve_svg(frac_by_rank, scen_label, opp_name, bin_size=16,
              width=680, height=120):
    """Step-area of fraction-of-cohort-beaten by focal SP rank (binned
    means). Single series; native tooltips; recessive grid."""
    n = len(frac_by_rank)
    nb = (n + bin_size - 1) // bin_size
    pad_l, pad_b, pad_t = 34, 16, 6
    pw, ph = width - pad_l - 4, height - pad_b - pad_t
    bins = [float(np.mean(frac_by_rank[i * bin_size:(i + 1) * bin_size]))
            for i in range(nb)]
    pts = []
    for i, f in enumerate(bins):
        x = pad_l + pw * i / max(nb - 1, 1)
        y = pad_t + ph * (1 - f)
        pts.append((x, y))
    line = ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
    area = (f'{pad_l:.1f},{pad_t + ph:.1f} ' + line
            + f' {pad_l + pw:.1f},{pad_t + ph:.1f}')
    hovers = ''.join(
        f'<rect x="{pad_l + pw * i / max(nb - 1, 1) - pw / nb / 2:.1f}" '
        f'y="{pad_t}" width="{pw / nb:.1f}" height="{ph}" fill="transparent">'
        f'<title>SP ranks {i * bin_size + 1}-{min((i + 1) * bin_size, n)}: '
        f'beats {100 * bins[i]:.1f}% of top-512 {esc(opp_name)}</title>'
        f'</rect>'
        for i in range(nb))
    gridlines = ''.join(
        f'<line x1="{pad_l}" y1="{pad_t + ph * (1 - g):.1f}" '
        f'x2="{pad_l + pw}" y2="{pad_t + ph * (1 - g):.1f}" '
        f'stroke="var(--border)" stroke-width="1"/>'
        f'<text x="{pad_l - 4}" y="{pad_t + ph * (1 - g) + 3:.1f}" '
        f'text-anchor="end" font-size="9" fill="var(--text-muted)">'
        f'{int(g * 100)}%</text>'
        for g in (0.0, 0.5, 1.0))
    xt = ''.join(
        f'<text x="{pad_l + pw * r / n:.1f}" y="{height - 3}" '
        f'text-anchor="middle" font-size="9" fill="var(--text-muted)">'
        f'{r if r else 1}</text>'
        for r in (0, 1024, 2048, 3072, n))
    return (f'<svg class="curve" viewBox="0 0 {width} {height}" '
            f'role="img" aria-label="fraction of {esc(opp_name)} top-512 '
            f'beaten, by {esc(scen_label)} scenario and focal SP rank">'
            f'{gridlines}'
            f'<polygon points="{area}" fill="var(--accent)" '
            f'fill-opacity="0.22"/>'
            f'<polyline points="{line}" fill="none" stroke="var(--accent)" '
            f'stroke-width="2"/>'
            f'{hovers}{xt}</svg>')


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def direction_section(focal_entry, opp_entry, cell, grid_bait, grid_nobait):
    fname, oname = focal_entry['name'], opp_entry['name']
    amber = cell.amber_scenarios()
    parts = [f'<h2>{esc(fname)} vs {esc(oname)}</h2>']
    if grid_bait is None:
        parts.append('<p class="section-intro">Tier-2 grid not baked for '
                     'this direction (deferred by the budget); Tier-1 '
                     'probe data is on the cheat sheet.</p>')
        return ''.join(parts)
    won = grid_bait['won']                      # (4096, n, 9)
    mask = grid_bait['top512_mask']
    nb_won = grid_nobait['won'] if grid_nobait is not None else None
    for si in amber:
        w = won[:, mask, si]                    # (4096, 512)
        frac = w.mean(axis=1)
        sweeps = int((frac == 1.0).sum())
        sweeps512 = int((frac[:512] == 1.0).sum())
        zero512 = int((frac[:512] == 0.0).sum())
        beats_r1 = int(w[:512, 0].sum())
        extra = ''
        if nb_won is not None:
            nbf = nb_won[:, mask, si].mean(axis=1)
            extra = (f' No-bait: <strong>{int((nbf[:512] == 1.0).sum())}'
                     '</strong> of your top-512 sweep.')
        parts.append(
            f'<h3>{SCEN_LABELS[si]} (IV-decided)</h3>'
            f'<p class="counts">Of your top-512 spreads (bait): '
            f'<strong>{sweeps512}</strong> beat every top-512 {esc(oname)}, '
            f'<strong>{zero512}</strong> beat none, '
            f'<strong>{beats_r1}</strong> beat its rank-1 spread. '
            f'Across all 4096 spreads, <strong>{sweeps}</strong> sweep.'
            f'{extra}</p>'
            + curve_svg(frac, SCEN_LABELS[si], oname))
    focal_ranked = iv_rank(focal_entry['species'], league='great',
                           shadow=focal_entry['shadow'])
    opp_ranked = iv_rank(opp_entry['species'], league='great',
                         shadow=opp_entry['shadow'])
    opp_cohort = opp_ranked[:512]
    parts.append('<h3>Reach or deny (closed form)</h3>')
    parts.append(reach_table_html(
        reach_rows(focal_entry, opp_entry, focal_ranked, opp_cohort),
        fname, oname))
    return ''.join(parts)


def render_pair_page(a_entry, b_entry, meta, cells, manifest, t2_manifest,
                    tier2_dir=t2.TIER2_DIR):
    def grids(focal_id, opp_id):
        out = {}
        for bait in (True, False):
            key = wp.pair_key(focal_id, opp_id, bait)
            ent = (t2_manifest or {}).get('entries', {}).get(key)
            out[bait] = (t2.read_grid(ent['file'], tier2_dir)
                         if ent else None)
        return out
    a, b = a_entry['species_id'], b_entry['species_id']
    ga, gb = grids(a, b), grids(b, a)
    body = (direction_section(a_entry, b_entry, cells[(a, b)],
                              ga[True], ga[False])
            + direction_section(b_entry, a_entry, cells[(b, a)],
                                gb[True], gb[False])
            + '<p><a href="worlds.html">Back to the Worlds 2026 hub</a> | '
            + f'<a href="{sheet_filename(a)}">{esc(a_entry["name"])} cheat '
            + 'sheet</a> | '
            + f'<a href="{sheet_filename(b)}">{esc(b_entry["name"])} cheat '
            + 'sheet</a></p>')
    return _page_shell(
        title=f'{a_entry["name"]} vs {b_entry["name"]} - Worlds 2026',
        heading=f'{a_entry["name"]} vs {b_entry["name"]}: the IVs decide',
        intro_html=('<p>Full-grid view of an IV-decided pair: every focal '
                    'IV spread (all 4096, stat-product order) against the '
                    'opponent\'s top-512 spreads, per shield scenario, '
                    'plus closed-form reach/deny cutoffs.</p>'
                    + provenance_html(meta, manifest)),
        body_html=body,
        extra_css=PAIR_CSS)


def build(website_dir=WEBSITE_DIR):
    meta = wrd.load_meta()
    entries = {e['species_id']: e for e in meta['entries']}
    manifest = wp.load_manifest()
    t2_manifest = t2.load_manifest()
    if manifest is None or t2_manifest is None:
        sys.exit('ABORT: need both Tier-1 and Tier-2 manifests')
    if wp.stamp_mismatches(manifest) or t2.stamp_mismatches(t2_manifest):
        sys.exit('ABORT: stamp mismatch -- refuse mixed-vintage pages')
    cells = wrd.build_all_cells(meta['entries'])
    # Pages only for amber pairs whose 4 grids are ALL baked (a partial
    # pair renders half-empty and reads as done; the hub's deferred list
    # covers the rest).
    baked_pairs = []
    for pair in sorted({tuple(sorted(k)) for k, c in cells.items()
                        if not c.missing and c.amber}):
        keys = [wp.pair_key(f, o, bait)
                for f, o in (pair, pair[::-1]) for bait in (True, False)]
        if all(k in t2_manifest.get('entries', {}) for k in keys):
            baked_pairs.append(pair)
    website_dir = Path(website_dir)
    for a, b in baked_pairs:
        html_text = render_pair_page(entries[a], entries[b], meta, cells,
                                     manifest, t2_manifest)
        (website_dir / pair_page_filename(a, b)).write_text(html_text)
    print(f'Wrote {len(baked_pairs)} pair pages '
          f'({len(t2_manifest.get("deferred", []))} pairs deferred).')
    return 0


if __name__ == '__main__':
    sys.exit(build())
