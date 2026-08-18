#!/usr/bin/env python
"""Assemble reco.json for the Thievul vs Licki IV-robustness pages.

Synthesis layer: joins the baked 4096x4096 win grids (the authority on
fight outcomes), the dive-derived meta win counts, and the closed-form
breakpoint layer into auto-computed recommendation cards. Every number
in every card is computed here from the inputs -- no hand-authored
results. Works for either opponent:

    direnv exec . python scripts/thievul_licki_assemble.py                        # lickitung
    direnv exec . python scripts/thievul_licki_assemble.py --opponent lickilicky

Conventions (match DESIGN.md): both grid axes in iv_rank order; a win is
score > 500 strict (ties lose); scenario si = sf*3 + so.

Honesty rules baked in after the 2026-08-16 adversarial verification of
the first (Lickitung) page:
- Scenario classification is explicit and three-way, with the rule
  stated in the blob: saturated_win (every one of the 16.7M cells is a
  win), hopeless (no spread reaches >5% top-512 coverage -- IVs can't
  save you), sensitive (everything else). Computed PER GRID; the
  headline never generalizes across movesets.
- Every metric key carries its moveset+bait label; cards show both
  movesets side by side (the community claims may assume either build:
  PvPoke's recommended Thievul is SP/NS+IW, our dive landing build is
  SP/IW+PR).
- "Best" picks disclose the full tiebreak chain and the count tied on
  the primary metric.
- Scenario priority for picks is a FIXED, stated order (even-shield
  fights first, then common asymmetries), filtered to each grid's
  sensitive scenarios -- not a hidden optimization choice.
"""
import argparse
import decimal
import hashlib
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import worlds_planes as wp  # noqa: E402

from gopvpsim.pokemon import iv_rank  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
SCEN = ['0-0', '0-1', '0-2', '1-0', '1-1', '1-2', '2-0', '2-1', '2-2']
SI_11 = 4
# Stated pick-priority over scenarios (filtered to sensitive ones per
# grid): the even-shield fights people actually plan around, then the
# common asymmetries, then the rest.
SCEN_PRIORITY = ['1-1', '0-0', '2-2', '1-0', '2-1', '0-1', '1-2', '2-0',
                 '0-2']
HOPELESS_MAX_COV = 0.05  # top-512 coverage no spread exceeds -> hopeless

OPPONENTS = {
    'lickitung': {
        'data_dir': REPO / 'userdata' / 'thievul_licki',
        'primary_grid': 'iwpr_bait',
        'moveset_of': {'iwpr': 'SP/IW+PR', 'nsiw': 'SP/NS+IW'},
    },
    'lickilicky': {
        'data_dir': REPO / 'userdata' / 'thievul_lickilicky',
        'primary_grid': 'iwpr_bait',
        'moveset_of': {'iwpr': 'SP/IW+PR', 'nsiw': 'SP/NS+IW'},
    },
}


def pct1(v):
    """One decimal, rounded the way the page's JS rounds it.

    Python's format() rounds half-to-even and JS toFixed rounds half-up,
    which disagree on the 8 attainable coverage values that land exactly on
    x.x5 (6.25 -> "6.2" vs "6.3"). The page renders the same quantity from
    the raw counts, so this side must follow ITS rule or the two print
    different numbers for one value.
    """
    return str(decimal.Decimal(repr(float(v))).quantize(
        decimal.Decimal('0.1'), rounding=decimal.ROUND_HALF_UP))


def fmt_ivs(ivs):
    return f'{ivs[0]}/{ivs[1]}/{ivs[2]}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--opponent', choices=sorted(OPPONENTS),
                    default='lickitung')
    args = ap.parse_args()
    cfg = OPPONENTS[args.opponent]
    data = cfg['data_dir']

    manifest = json.loads((data / 'manifest.json').read_text())
    opp_name = manifest['opponent']
    bp = json.loads((data / 'breakpoints.json').read_text())
    # meta_wins is opponent-independent (Thievul vs the dive pool); the
    # canonical copy lives with the lickitung dataset.
    mw_path = data / 'meta_wins.npz'
    if not mw_path.exists():
        mw_path = OPPONENTS['lickitung']['data_dir'] / 'meta_wins.npz'
    mw = np.load(mw_path)
    ranked = iv_rank('Thievul', league='great')

    won = {}
    for label, ginfo in manifest['grids'].items():
        z = np.load(data / ginfo['file'])
        w = wp.unpack_won(z['won_packed'], tuple(z['won_shape']))
        assert w.shape == (4096, 4096, 9), (label, w.shape)
        won[label] = w

    def grid_pretty(label):
        ms = label.rsplit('_', 1)[0]
        bait = manifest['grids'][label]['bait']
        return (f'{cfg["moveset_of"].get(ms, ms)}, '
                f'{"baiting" if bait else "no bait"}')

    # Per-grid scenario classification (the rule is in the blob) -------
    per_grid = {}
    for label, w in won.items():
        cls = {'saturated_win': [], 'hopeless': [], 'sensitive': []}
        detail = {}
        for si in range(9):
            sl = w[:, :, si]
            c512 = sl[:, :512].mean(axis=1)
            detail[SCEN[si]] = {
                'win_frac_all': round(float(sl.mean()), 4),
                'cov512_min': round(float(c512.min()) * 100, 2),
                'cov512_max': round(float(c512.max()) * 100, 2),
                'n_spreads_full_cov512': int((c512 == 1.0).sum()),
            }
            if sl.all():
                cls['saturated_win'].append(SCEN[si])
            elif c512.max() <= HOPELESS_MAX_COV:
                cls['hopeless'].append(SCEN[si])
            else:
                cls['sensitive'].append(SCEN[si])
        per_grid[label] = {
            **cls, 'detail': detail, 'pretty': grid_pretty(label),
            'rule': ('saturated_win: every one of the 16,777,216 cells '
                     'is a Thievul win; hopeless: no Thievul spread '
                     f'beats more than {HOPELESS_MAX_COV:.0%} of the '
                     'top-512 cohort (IV choice cannot save the '
                     'scenario); sensitive: everything else'),
        }

    primary = cfg['primary_grid']
    w_pri = won[primary]
    sens = [s for s in SCEN_PRIORITY
            if s in per_grid[primary]['sensitive']]
    pick_scens = sens[:3] if sens else ['1-1']
    pick_sis = [SCEN.index(s) for s in pick_scens]

    cov512 = {label: {si: won[label][:, :512, si].mean(axis=1)
                      for si in range(9)} for label in won}
    meta = {}
    for ms in ('iwpr', 'nsiw'):
        key = f'wins__{ms}__pvpoke__bait__1-1'
        if key in mw:
            meta[ms] = mw[key].astype(int)
    pool_n = int(mw['pool_n']) if 'pool_n' in mw else 88
    meta_pri = meta['iwpr']
    sp_tier = np.array(
        bp['thievul_offense']['moves']['SUCKER_PUNCH']
          ['tier_vs_rank1_licki_by_spread'])

    def metrics(i):
        out = {'sp_tier_vs_rank1_licki': int(sp_tier[i]),
               'meta_wins_11': {ms: int(meta[ms][i]) for ms in meta}}
        # ALL nine scenarios per grid, not just the primary grid's pick
        # list: a card that states its own tiebreak chain (the NS+IW card
        # ranks on 1-1 first) must be able to show the number it ranked on.
        for label in won:
            # Rounded ONCE, at render time. Storing 2dp here and printing
            # 1dp downstream is a double round: 72.8515625 -> 72.85 ->
            # "72.8%", while the page's own 1dp render of the raw value is
            # "72.9%". 6dp is exact enough for the 1/512 and 1/4096 steps
            # to round identically on both sides.
            out[label] = {
                SCEN[si]: round(float(cov512[label][si][i]) * 100, 6)
                for si in range(len(SCEN))}
            out[label]['pretty'] = grid_pretty(label)
        return out

    def find(a, d, s):
        for i, r in enumerate(ranked):
            if (r['atk_iv'], r['def_iv'], r['sta_iv']) == (a, d, s):
                return i
        raise KeyError((a, d, s))

    def spread_row(i):
        r = ranked[i]
        return {'ivs': [r['atk_iv'], r['def_iv'], r['sta_iv']],
                'rank': i + 1, 'level': r['level'], 'cp': r['cp'],
                'atk': round(r['atk'], 4), 'def': round(r['def_'], 4),
                'hp': r['hp']}

    # Picks, with disclosed tiebreaks ---------------------------------
    pick_cols = [cov512[primary][si] for si in pick_sis]
    tiebreak = (' > '.join(f'{s} coverage' for s in pick_scens)
                + ' > meta wins (SP/IW+PR, 1-1) > stat-product rank')
    # np.lexsort: LAST key is primary, so list from weakest to strongest.
    keys = [np.arange(4096), -meta_pri] + [-c for c in reversed(pick_cols)]
    order = np.lexsort(tuple(keys))
    i_smash = int(order[0])
    n_tied_smash = int((pick_cols[0] >= pick_cols[0][i_smash] - 1e-12).sum())

    # Best meta among spreads with full top-512 coverage at every
    # sensitive pick scenario (primary grid).
    full_mask = np.ones(4096, dtype=bool)
    for c in pick_cols:
        full_mask &= (c == 1.0)
    if full_mask.any():
        cand = np.flatnonzero(full_mask)
        i_bal = int(cand[np.argmax(meta_pri[cand])])
        bal_note = (f'{len(cand)} spreads have 100% top-512 coverage at '
                    f'{", ".join(pick_scens)}; this is the best meta '
                    f'record among them '
                    f'({int((meta_pri[cand] == meta_pri[i_bal]).sum())} '
                    f'tied at that record)')
    else:
        i_bal, bal_note = i_smash, 'no spread is full-coverage at all pick scenarios'

    max_meta = int(meta_pri.max())
    at_max = np.flatnonzero(meta_pri == max_meta)
    i_meta_best = int(at_max[np.argmax(pick_cols[0][at_max])])

    # Best build under the OTHER moveset (NS+IW), judged on ITS OWN
    # sensitive scenarios -- readers running PvPoke's default moveset
    # deserve a pick computed for it, not IW+PR's leftovers.
    ns_card = None
    if 'nsiw_bait' in won:
        ns_sens = [s for s in SCEN_PRIORITY
                   if s in per_grid['nsiw_bait']['sensitive']]
        ns_scens = ns_sens[:3] if ns_sens else ['1-1']
        ns_cols = [cov512['nsiw_bait'][SCEN.index(s)] for s in ns_scens]
        meta_ns = meta.get('nsiw', meta_pri)
        ns_keys = [np.arange(4096), -meta_ns] + [-c for c in
                                                 reversed(ns_cols)]
        i_ns = int(np.lexsort(tuple(ns_keys))[0])
        n_tied_ns = int((ns_cols[0] >= ns_cols[0][i_ns] - 1e-12).sum())
        ns_tiebreak = (' > '.join(f'{s} coverage' for s in ns_scens)
                       + ' > meta wins (SP/NS+IW, 1-1) > stat-product rank')
        ns_card = ('Best build if you run NS+IW (PvPoke default)',
                   f'Computed on the SP/NS+IW grid\'s own sensitive '
                   f'scenarios ({", ".join(ns_scens)}); for readers '
                   f'following PvPoke\'s default moveset. Tiebreak: '
                   f'{ns_tiebreak}', i_ns,
                   [f'{n_tied_ns} spread{"" if n_tied_ns == 1 else "s"} '
                    f'tie on {ns_scens[0]} coverage under NS+IW'], [],
                   'nsiw_bait', ns_scens,
                   {'n_tied': n_tied_ns,
                    'metric': f'{ns_scens[0]} coverage under NS+IW',
                    'tiebreak': ns_tiebreak})

    named = [
        ('The Licki smasher', f'Best {", ".join(pick_scens)} record vs '
         f'{opp_name} ({grid_pretty(primary)}); tiebreak: {tiebreak}',
         i_smash,
         [f'{n_tied_smash} spread{"" if n_tied_smash == 1 else "s"} tie '
          f'on the primary metric '
          f'({pick_scens[0]} top-512 coverage); tiebreak chain: {tiebreak}'],
         ['Optimized purely for this matchup; check the meta line before '
          'committing dust.'], primary, pick_scens,
         {'n_tied': n_tied_smash,
          'metric': f'{pick_scens[0]} top-512 coverage',
          'tiebreak': tiebreak}),
        ('IV tech without meta cost', bal_note, i_bal, [], []),
        ('Max meta wins', f'Best overall-meta spread -- one of '
         f'{len(at_max)} tied at {max_meta}W (SP/IW+PR, 1-1); among the '
         f'tie, best {pick_scens[0]} coverage shown', i_meta_best, [], []),
    ]
    if ns_card:
        named.insert(3, ns_card)
    named += [
        ('What about the 6/15/5 spread?', 'The spread discussed in the '
         'community as the Sucker Punch breakpoint pick', find(6, 15, 5),
         [], []),
        ('What about 15 HP? (6/15/15)', 'The "do you not want 15 hp" '
         'question applied to 6/15/x', find(6, 15, 15), [], []),
        ('Shipped dive rank 1: 0/15/11', 'The published dive landing '
         'build', 0, [], []),
        ('PvPoke default IVs: 4/15/15', "The spread PvPoke's own matchup "
         'page simulates -- it misses the SP breakpoint, which is why '
         'PvPoke prefers Night Slash in this matchup', find(4, 15, 15),
         [], []),
        ('Hundo 15/15/15', 'For CD day: what the hundo actually does',
         find(15, 15, 15), [], []),
    ]

    # Byte-identical win grids, grouped (see the collapse in card()).
    grid_groups = []
    _seen = {}
    for label in sorted(won):
        key = hashlib.md5(np.ascontiguousarray(won[label])).hexdigest()
        if key in _seen:
            grid_groups[_seen[key]].append(label)
        else:
            _seen[key] = len(grid_groups)
            grid_groups.append([label])

    def card(title, subtitle, i, extra, caveats, scens=None, tie=None):
        # A card prints the SAME scenarios its own tiebreak chain ranked
        # on -- the NS+IW card is chosen on the NS+IW grid's sensitive
        # scenarios, so printing the primary grid's set underneath it
        # would be a different question than the one it answered.
        scens = list(scens or pick_scens)
        m = metrics(i)
        r = ranked[i]
        lines = [
            f'IVs {fmt_ivs(spread_row(i)["ivs"])} -- SP rank '
            f'#{i + 1}, L{r["level"]}, CP {r["cp"]}, atk {r["atk"]:.2f} / '
            f'def {r["def_"]:.2f} / hp {r["hp"]}',
        ]
        # BYTE-IDENTICAL grids collapse to one line naming both: two
        # lines of identical digits read as a rendering bug, and the
        # duplication is a property of the data (a bait grid can be
        # byte-identical to its no-bait twin), not a finding. Grids that
        # merely happen to agree at THESE scenarios still get their own
        # line -- "=" here means the whole 4096x4096x9 grid is the same.
        for group in grid_groups:
            # ONE decimal, matching the page's COV_DP: the band and the
            # verdict table render these same stored values, and the 2dp
            # repr here made one quantity print two ways.
            covs = ', '.join(f'{s}: {pct1(m[group[0]][s])}%' for s in scens)
            pretty = ' = '.join(m[la]['pretty'] for la in group)
            lines.append(f'[{pretty}] top-512 coverage -- {covs}')
        mw_line = ' / '.join(
            f'{cfg["moveset_of"][ms]} {m["meta_wins_11"][ms]}W'
            for ms in sorted(m['meta_wins_11']))
        lines.append(f'Meta at 1-1, of {pool_n} dive-pool matchups '
                     f'(baiting): {mw_line}')
        lines.append(f'Sucker Punch does {m["sp_tier_vs_rank1_licki"]} '
                     f'damage vs the rank-1 {opp_name} (7 = clears the '
                     f'breakpoint)')
        return {'title': title, 'subtitle': subtitle,
                'spread': spread_row(i), 'rank': i + 1,
                'lines': lines + extra, 'metrics': m,
                'scenarios': scens,
                # STRUCTURED tie facts. The page used to recover these by
                # regex from the prose line below, which broke the moment
                # the sentence was pluralised; the prose stays for the
                # card body, but the band reads these fields.
                'tie': tie,
                'caveats': caveats}

    def card_with_grid(spec):
        c = card(*spec[:5], scens=(spec[6] if len(spec) > 6 else None),
                 tie=(spec[7] if len(spec) > 7 else None))
        # Every card states the grid it was computed on, structurally --
        # the page no longer has to guess it from the subtitle.
        c['grid'] = spec[5] if len(spec) > 5 else primary
        c['basis_pretty'] = grid_pretty(c['grid'])
        return c

    cards = [card_with_grid(n) for n in named]

    # Two cards can select the SAME spread (on Lickilicky the smasher and
    # the no-meta-cost pick are both 5/9/7). Shipping them twice with
    # identical numbers reads as a rendering bug, so they are merged into
    # one card that states both roles.
    merged, by_rank = [], {}
    for c in cards:
        key = (c['rank'], c['grid'])
        if key in by_rank:
            first = by_rank[key]
            if c['title'] not in first['title']:
                first['title'] = f"{first['title']} (also: {c['title']})"
            for extra_line in c['lines']:
                if extra_line not in first['lines']:
                    first['lines'].append(extra_line)
            if c.get('subtitle') and c['subtitle'] not in first['subtitle']:
                first['subtitle'] = (first['subtitle'].rstrip('.')
                                     + '. Also the pick for: '
                                     + c['subtitle'])
            continue
        by_rank[key] = c
        merged.append(c)
    cards = merged

    # The PAGE defaults to the NS+IW grid, so the band must lead with the
    # card computed on it; leading with an IW+PR card made the first
    # numbers a reader sees belong to a moveset no panel below was showing.
    default_grid = 'nsiw_bait' if 'nsiw_bait' in won else primary
    cards.sort(key=lambda c: 0 if c.get('grid') == default_grid else 1)

    # Opponent-cohort level facts DERIVED from the baked npz (the first
    # version hardcoded Lickitung's "L44.5-50 XL" here; the independent
    # verification caught it rendered falsely on the Lickilicky page).
    opp_levels = np.load(
        data / manifest['grids'][primary]['file'])['opp_levels']
    lv_lo, lv_hi = float(opp_levels.min()), float(opp_levels.max())
    xl_note = (' -- XL-candy territory (above L40)' if lv_lo > 40.0
               else '')
    cohort_note = (
        f'Coverage cohort for cards is the top-512 {opp_name} spreads by '
        f'stat product; every {opp_name} spread in the 4096 denominator '
        f'is the CP-capped best build for its IVs, L{lv_lo:g}-L{lv_hi:g}'
        f'{xl_note}.')

    # Cross-moveset finding (computed, only for grids present) ---------
    notes = [
        'All cards are auto-computed from the baked grids, the dive '
        'replay extraction, and the closed-form breakpoint layer. '
        'Human-guided, AI-generated; no hand-authored numbers.',
        'A "win" is pvpoke score > 500 strict; ties count as losses.',
        cohort_note,
        'Meta wins are vs the shipped dive pool (88 matchups incl. '
        'counter-slayers and the mirror) with PvPoke opponent IVs, focal '
        'baiting, at 1-1 shields.',
        'ICY_WIND is the 2026-08-16 CD move, injected for the sim (the '
        'pinned gamemaster predates it; pvpoke upstream added it '
        '2026-08-14 as an elite move). Mechanics: legacy.',
    ]
    if 'nsiw_bait' in won and args.opponent == 'lickilicky':
        clears = sp_tier >= 7
        c_iw = cov512['iwpr_bait'][SI_11]
        c_ns = cov512['nsiw_bait'][SI_11]
        ns_better = c_ns > c_iw
        n_ns_better = int(ns_better.sum())
        n_ns_better_missing = int((ns_better & ~clears).sum())
        miss_word = ('all of them breakpoint-missing'
                     if n_ns_better_missing == n_ns_better else
                     f'{n_ns_better_missing} of them breakpoint-missing')
        notes.append(
            f'Moveset is IV-conditional at 1-1: for all '
            f'{int(clears.sum())} breakpoint-clearing spreads SP/IW+PR '
            f'is better-or-equal (mean {c_iw[clears].mean()*100:.1f}% vs '
            f'{c_ns[clears].mean()*100:.1f}% top-512 coverage); NS+IW is '
            f'better for only {n_ns_better} spreads, {miss_word} -- '
            f'PvPoke\'s default 4/15/15 is one of them, which is why its '
            f'matchup page prefers Night Slash.')

    reco = {
        'opponent': opp_name,
        'primary_grid': primary,
        'primary_grid_pretty': grid_pretty(primary),
        'pick_scenarios': pick_scens,
        'scenario_priority_rule': ('picks are ranked over the sensitive '
                                   'scenarios of the primary grid in the '
                                   'fixed order ' + ', '.join(SCEN_PRIORITY)),
        'per_grid_scenarios': per_grid,
        'pool_n': pool_n,
        'cards': cards,
        'pareto_axes': [f'meta wins at 1-1 ({grid_pretty(primary)})',
                        f'{pick_scens[0]} top-512 coverage pct '
                        f'({grid_pretty(primary)})'],
        'pareto': [],
        'notes': notes,
        'named_builds': [
            {'label': f'#{i + 1} {fmt_ivs(spread_row(i)["ivs"])} ({t})',
             'rank': i + 1}
            for t, i in ([('smasher', i_smash), ('no-meta-cost', i_bal),
                          ('max meta', i_meta_best)]
                         + ([('NS+IW pick', ns_card[2])] if ns_card else [])
                         + [('6/15/5', find(6, 15, 5)),
                            ('6/15/15', find(6, 15, 15)), ('rank1', 0),
                            ('pvpoke default', find(4, 15, 15)),
                            ('hundo', find(15, 15, 15))])],
    }

    # Pareto on (meta, primary pick-scenario coverage) -----------------
    pts = np.stack([meta_pri, pick_cols[0]], axis=1)
    for i in range(4096):
        dominated = ((pts[:, 0] >= pts[i, 0]) & (pts[:, 1] >= pts[i, 1]) &
                     ((pts[:, 0] > pts[i, 0]) | (pts[:, 1] > pts[i, 1])))
        if not dominated.any():
            reco['pareto'].append(
                {**spread_row(i), 'meta_wins_11': int(meta_pri[i]),
                 'primary_cov512': round(float(pick_cols[0][i]) * 100, 2)})
    reco['pareto'].sort(key=lambda e: -e['meta_wins_11'])

    out = data / 'reco.json'
    out.write_text(json.dumps(reco, indent=1))
    print(f'wrote {out} ({out.stat().st_size:,} bytes)')
    print(f'primary grid {primary}; pick scenarios {pick_scens}')
    for label, pg in per_grid.items():
        print(f'  {label}: saturated {pg["saturated_win"]} hopeless '
              f'{pg["hopeless"]} sensitive {pg["sensitive"]}')
    for c in cards:
        m = c['metrics']
        covs = ' '.join(f'{s}={m[primary][s]}' for s in pick_scens)
        print(f'-- {c["title"]}: #{c["rank"]} '
              f'{fmt_ivs(c["spread"]["ivs"])} {covs} '
              f'meta={m["meta_wins_11"]}')


if __name__ == '__main__':
    main()
