#!/usr/bin/env python
"""Cheap screen: does a species' matchup picture change with an energy lead?

Safe-switch / closer mons (Sableye, Quagsire, Drapion, ...) often enter
battle with 1-2 fast moves of carried-over energy, but the dive sims
everything at energy 0. Before plumbing an energy-lead axis through a
full deep dive, run this probe: it sims a handful of representative IV
spreads x the opponent pool x 9 shield scenarios x {0, 1, 2} fast moves
of starting energy (focal side only) and reports which matchup cells
flip, plus an aggregate SENSITIVE / MARGINAL / INSENSITIVE verdict.

Generalizes the one-off scripts/check_sableye_energy_lead.py (2026-06-03
precedent; see TODO.md "Energy-lead axis"). Calibration target from that
work: Shadow Sableye should come out SENSITIVE, and the bulk-corner rep
must gain MORE cells from energy lead than the atk-corner rep does --
if atk gains more on a Sableye-class species, that's a probe bug, not a
finding (TODO.md "Counter-intuitive cross-check").

Usage:
    python scripts/energy_probe.py Sableye --shadow
    python scripts/energy_probe.py Talonflame --pool opponent_pools/gl_top50_plus_cs.txt
    python scripts/energy_probe.py Quagsire --moveset MUD_SHOT,AQUA_TAIL,STONE_EDGE --json /tmp/quag.json

Single process by design (overnight dive batches may own the cores).
Read-only against the gamemaster/rankings caches.
"""
import argparse
import json
import sys, os
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

from gopvpsim.battle import simulate, pvpoke_dp
from gopvpsim.data import get_default_moveset
from gopvpsim.moves import get_moves
from gopvpsim.pokemon import iv_rank, pvpoke_default_ivs
from deep_dive import make_battle_pokemon, _parse_opponent_pool_line


# --- Verdict thresholds ------------------------------------------------------
#
# A "cell" is one (rep IV, opponent, shield scenario) matchup; it "flips"
# when its win-state (focal pvpoke score > 500) is not identical across
# the three energy levels. 2% flip-fraction sits well below Shadow
# Sableye's observed rate (~14%; the 2026-06-03 one-off saw ~50 of 594
# per-(IV,moveset) cells reshape, ~8%, on a smaller pool with 0/15/15
# opponents) while staying above sim-noise territory; 5 distinct
# opponents catches species whose flips concentrate on a few reps but
# span a real chunk of the meta (a dive's "Matchup-Flipping Boundaries"
# section would gain >= 5 lines, which is worth a dive axis).
#
# CALIBRATION NOTE (2026-06-12, gl_top50_plus_cs pool, 71 opponents):
# every species probed cleared the SENSITIVE bar -- Altaria 4.0%,
# Aegislash (Shield) 9.5%, Shadow Sableye 13.6%, Aegislash (Blade)
# 14.0%, Talonflame 23.8%. A free 1-2 fast moves of energy moves the
# needle for everything; even the intended "fast-KO glass cannon"
# control (Talonflame) is genuinely energy-hungry because the axis is
# denominated in FAST MOVES, so Incinerate banks 40 raw energy (~a full
# Fly) while Dragon Breath banks 8. The binary verdict is therefore a
# floor-filter, not the headline: when ranking species for the
# energy-lead dive axis, sort by flip_fraction (in the JSON summary)
# and re-quantile these constants once the full-meta scan exists.
SENSITIVE_FLIP_FRAC = 0.02   # >= 2% of all cells flip -> SENSITIVE
SENSITIVE_MIN_OPPS = 5       # or >= 5 distinct opponents involved
MARGINAL_FLIP_FRAC = 0.005   # >= 0.5% of cells (else INSENSITIVE)
MARGINAL_MIN_OPPS = 2        # or >= 2 distinct opponents

SHIELDS = [(a, d) for a in (0, 1, 2) for d in (0, 1, 2)]
ENERGY_MULTS = (0, 1, 2)     # fast moves of carried-over energy

DEFAULT_POOL = 'opponent_pools/gl_top50_plus_cs.txt'
DEFAULT_REPS = 7


# --- Representative IV spreads ----------------------------------------------

def pick_rep_ivs(species, league, shadow, n_reps):
    """Return [(label, (a, d, s)), ...] spanning the IV envelope.

    Always includes: rank-1 stat product, PvPoke default, max-attack
    corner (best SP with atk_iv=15), max-bulk corner (atk_iv=0, best
    def*hp). Remaining slots (n_reps - 4) are mid-envelope picks: best
    SP at evenly spaced atk_iv values between the corners. Deduped by
    IV triple, so the returned list can be shorter than n_reps.
    """
    ranked = iv_rank(species, league=league, shadow=shadow)
    if not ranked:
        raise ValueError(f"no legal IV spreads for {species} in {league}")

    def ivs(e):
        return (e['atk_iv'], e['def_iv'], e['sta_iv'])

    picks = []  # (label, ivs) in priority order

    picks.append(('rank1-sp', ivs(ranked[0])))

    try:
        _lv, pa, pd, ps = pvpoke_default_ivs(species, league=league)
        picks.append(('pvpoke-dflt', (pa, pd, ps)))
    except (ValueError, KeyError):
        pass  # no defaultIVs entry; envelope corners still cover the span

    # Max-attack corner: best stat product among atk_iv == 15 spreads
    # (ranked is SP-descending, so first hit wins).
    atk_corner = next((e for e in ranked if e['atk_iv'] == 15), None)
    if atk_corner is not None:
        picks.append(('atk-corner', ivs(atk_corner)))

    # Max-bulk corner: atk_iv == 0, maximize def * hp (the 0/15/15-style
    # build; tie-break by stat product).
    bulk_pool = [e for e in ranked if e['atk_iv'] == 0]
    if bulk_pool:
        bulk_corner = max(bulk_pool,
                          key=lambda e: (e['def_'] * e['hp'],
                                         e['stat_product']))
        picks.append(('bulk-corner', ivs(bulk_corner)))

    # Mid-envelope: best SP at evenly spaced atk_iv values in (0, 15).
    n_mid = max(0, n_reps - len(picks))
    for i in range(n_mid):
        target_atk = round(15 * (i + 1) / (n_mid + 1))
        mid = next((e for e in ranked if e['atk_iv'] == target_atk), None)
        if mid is not None:
            picks.append((f'mid-a{target_atk}', ivs(mid)))

    # Dedup by IV triple, keeping first (highest-priority) label.
    seen, reps = set(), []
    for label, triple in picks:
        if triple not in seen:
            seen.add(triple)
            reps.append((label, triple))
    return reps


# --- Opponent pool ------------------------------------------------------------

def load_opponents(pool_path, league):
    """Parse opponent pool file -> [(display, base, is_shadow, fast, [charged])].

    Same parse path as scripts/deep_dive.py; entries without a moveset
    override take get_default_moveset, and species missing from the
    rankings are skipped (matching check_sableye_energy_lead.py).
    """
    opps = []
    with open(pool_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            display, base, is_shadow, fast_ov, charged_ov = (
                _parse_opponent_pool_line(line))
            if fast_ov is None or charged_ov is None:
                try:
                    d_fast, d_charged = get_default_moveset(
                        base, league=league, shadow=is_shadow)
                except (KeyError, ValueError):
                    continue
            else:
                d_fast, d_charged = None, None
            fast_id = fast_ov if fast_ov is not None else d_fast
            charged_ids = (list(charged_ov) if charged_ov is not None
                           else list(d_charged))
            opps.append((display, base, is_shadow, fast_id, charged_ids))
    return opps


def opp_ivs(base, league, shadow):
    """Opponent IVs: PvPoke default (the dive convention), falling back
    to generic 0/15/15 bulk when the gamemaster has no defaultIVs entry."""
    try:
        _lv, a, d, s = pvpoke_default_ivs(base, league=league)
        return a, d, s
    except (ValueError, KeyError):
        return 0, 15, 15


# --- Energy axis --------------------------------------------------------------

def energy_values(fast_id, charged_ids):
    """Raw starting-energy values for {0, 1, 2} fast moves of lead.

    Mirrors deep_dive.iv_sweep's focal_energy block: N x the fast move's
    energyGain, capped at (100 - cheapest charged cost) since a higher
    lead is unreachable in play (the charged move would already have
    been thrown).
    """
    fast_db, charged_db = get_moves()
    eg = fast_db[fast_id].get('energyGain', 0)
    cap = max(0, 100 - min(charged_db[c]['energy'] for c in charged_ids))
    return [min(m * eg, cap) for m in ENERGY_MULTS]


# --- Probe --------------------------------------------------------------------

def run_probe(species, shadow, league, pool_path, moveset, n_reps):
    """Run the full probe; return a results dict (also used for --json)."""
    if moveset is None:
        fast_id, charged_ids = get_default_moveset(
            species, league=league, shadow=shadow)
        charged_ids = list(charged_ids)
    else:
        fast_id, charged_ids = moveset[0], list(moveset[1:])

    reps = pick_rep_ivs(species, league, shadow, n_reps)
    opponents = load_opponents(pool_path, league)
    e_vals = energy_values(fast_id, charged_ids)

    n_cells = len(reps) * len(opponents) * len(SHIELDS)
    print(f"Species: {species}{' (Shadow)' if shadow else ''}  "
          f"league={league}", flush=True)
    print(f"Moveset: {fast_id} + {'/'.join(charged_ids)}", flush=True)
    print(f"Energy axis (raw): {e_vals}  "
          f"(= {{0,1,2}} fast moves, capped at 100 - cheapest cost)",
          flush=True)
    print(f"Reps ({len(reps)}): " + ", ".join(
        f"{lbl}={a}/{d}/{s}" for lbl, (a, d, s) in reps), flush=True)
    print(f"Pool: {len(opponents)} opponents x {len(SHIELDS)} scenarios "
          f"x {len(e_vals)} energy = {n_cells * len(e_vals):,} sims",
          flush=True)

    # wins[rep_label][(opp_display, sf, so)] = [bool win at e0, e1, e2]
    wins = {lbl: {} for lbl, _ in reps}
    t0 = time.perf_counter()
    for ri, (lbl, (a, d, s)) in enumerate(reps):
        for opp_display, opp_base, opp_shadow, opp_fast, opp_charged in opponents:
            # Build the pair once per (rep, opponent); reset_for_battle
            # across the scenario x energy axes keeps the damage/DP
            # caches warm (same pattern as the deep_dive sweep worker).
            bp0 = make_battle_pokemon(species, fast_id, charged_ids,
                                      league, 2, a, d, s, shadow=shadow)
            oa, od, os_ = opp_ivs(opp_base, league, opp_shadow)
            bp1 = make_battle_pokemon(opp_base, opp_fast, opp_charged,
                                      league, 2, oa, od, os_,
                                      shadow=opp_shadow)
            for sf, so in SHIELDS:
                states = []
                for e in e_vals:
                    bp0.initial_energy = e  # reset re-applies it at T0
                    bp0.reset_for_battle(sf, opponent=bp1)
                    bp1.reset_for_battle(so, opponent=bp0)
                    result = simulate(bp0, bp1,
                                      charged_policy_0=pvpoke_dp,
                                      charged_policy_1=pvpoke_dp)
                    states.append(result.pvpoke_score(0) > 500)
                wins[lbl][(opp_display, sf, so)] = states
        print(f"  [{ri + 1}/{len(reps)}] {lbl} done "
              f"({time.perf_counter() - t0:.1f}s)", flush=True)
    runtime = time.perf_counter() - t0

    return {
        'species': species, 'shadow': shadow, 'league': league,
        'pool': pool_path, 'fast': fast_id, 'charged': charged_ids,
        'energy_values': e_vals,
        'reps': [{'label': lbl, 'ivs': list(t)} for lbl, t in reps],
        'wins': wins, 'n_opponents': len(opponents),
        'runtime_s': runtime,
    }


# --- Reporting ----------------------------------------------------------------

def summarize(probe):
    """Print the stdout report; return the JSON-ready summary dict."""
    wins = probe['wins']
    e_vals = probe['energy_values']
    rep_labels = [r['label'] for r in probe['reps']]
    rep_ivs = {r['label']: tuple(r['ivs']) for r in probe['reps']}
    n_cells_per_rep = probe['n_opponents'] * len(SHIELDS)
    total_cells = n_cells_per_rep * len(rep_labels)

    # Per-rep win counts + flips relative to e0.
    print(flush=True)
    print("=" * 72, flush=True)
    print(f"PER-REP WINS (out of {n_cells_per_rep} cells = "
          f"{probe['n_opponents']} opponents x 9 scenarios)", flush=True)
    print("=" * 72, flush=True)
    hdr = (f"{'rep':>12} {'IVs':>8}  {'w@e0':>5} {'w@e1':>5} {'w@e2':>5}"
           f"  {'Δe1':>4} {'Δe2':>4}  {'gain':>4} {'lose':>4}")
    print(hdr, flush=True)
    print("-" * len(hdr), flush=True)

    rep_summary = {}
    all_flip_cells = []  # (rep, opp, sf, so, states)
    for lbl in rep_labels:
        cells = wins[lbl]
        w = [sum(1 for st in cells.values() if st[i])
             for i in range(len(e_vals))]
        gained = sum(1 for st in cells.values() if not st[0] and st[-1])
        lost = sum(1 for st in cells.values() if st[0] and not st[-1])
        flips = [(opp, sf, so, st) for (opp, sf, so), st in cells.items()
                 if len(set(st)) > 1]
        all_flip_cells.extend((lbl, *f) for f in flips)
        a, d, s = rep_ivs[lbl]
        print(f"{lbl:>12} {f'{a}/{d}/{s}':>8}  "
              f"{w[0]:>5} {w[1]:>5} {w[2]:>5}  "
              f"{w[1] - w[0]:>+4} {w[2] - w[0]:>+4}  "
              f"{gained:>4} {lost:>4}", flush=True)
        rep_summary[lbl] = {'ivs': [a, d, s], 'wins': w,
                            'gained_e2': gained, 'lost_e2': lost,
                            'n_flip_cells': len(flips)}

    # Flip list, grouped per rep / direction.
    print(flush=True)
    print("=" * 72, flush=True)
    print("FLIP LIST (cells whose win-state crosses 500 between energy "
          "levels)", flush=True)
    print("=" * 72, flush=True)
    if not all_flip_cells:
        print("  (none)", flush=True)
    for lbl in rep_labels:
        rep_flips = [f for f in all_flip_cells if f[0] == lbl]
        if not rep_flips:
            continue
        print(f"  {lbl} ({rep_ivs[lbl][0]}/{rep_ivs[lbl][1]}/"
              f"{rep_ivs[lbl][2]}): {len(rep_flips)} cells", flush=True)
        for _, opp, sf, so, st in sorted(rep_flips, key=lambda f: f[1]):
            if not st[0] and st[-1]:
                direction = 'GAIN'
            elif st[0] and not st[-1]:
                direction = 'LOSE'
            else:
                direction = 'MIXED'  # e.g. wins only at e1
            marks = ''.join('W' if x else 'L' for x in st)
            print(f"    {direction:>5}  {opp:<32} ({sf},{so})  "
                  f"e0/e1/e2={marks}", flush=True)

    # Aggregate verdict.
    n_flips = len(all_flip_cells)
    flip_frac = n_flips / total_cells if total_cells else 0.0
    flip_opps = sorted({f[1] for f in all_flip_cells})
    if flip_frac >= SENSITIVE_FLIP_FRAC or len(flip_opps) >= SENSITIVE_MIN_OPPS:
        verdict = 'SENSITIVE'
    elif flip_frac >= MARGINAL_FLIP_FRAC or len(flip_opps) >= MARGINAL_MIN_OPPS:
        verdict = 'MARGINAL'
    else:
        verdict = 'INSENSITIVE'

    # Bulk-vs-atk gain comparison (the TODO.md cross-check shape: bulk
    # IVs should gain MORE from energy lead for chip-war species).
    # The explicit corner labels can dedup away (e.g. Sableye's
    # bulk-corner IS rank-1 SP at 0/15/15), so fall back to the reps
    # with the lowest / highest atk IV.
    bulk_atk = None
    if len(rep_summary) >= 2:
        bulk_lbl = ('bulk-corner' if 'bulk-corner' in rep_summary else
                    min(rep_summary, key=lambda l: rep_summary[l]['ivs'][0]))
        atk_lbl = ('atk-corner' if 'atk-corner' in rep_summary else
                   max(rep_summary, key=lambda l: rep_summary[l]['ivs'][0]))
        if bulk_lbl != atk_lbl:
            bg = rep_summary[bulk_lbl]['gained_e2']
            ag = rep_summary[atk_lbl]['gained_e2']
            bulk_atk = {'bulk_rep': bulk_lbl, 'atk_rep': atk_lbl,
                        'bulk_gained': bg, 'atk_gained': ag}
            cmp_word = ('MORE than' if bg > ag else
                        'FEWER than' if bg < ag else 'the SAME as')
            print(flush=True)
            print(f"Bulk-vs-atk: {bulk_lbl} "
                  f"(atk IV {rep_summary[bulk_lbl]['ivs'][0]}) gains {bg} "
                  f"cells (e0->e2), {cmp_word} {atk_lbl} "
                  f"(atk IV {rep_summary[atk_lbl]['ivs'][0]}) at {ag}.",
                  flush=True)

    print(flush=True)
    print(f"VERDICT: {verdict}  "
          f"({n_flips}/{total_cells} cells flip = {flip_frac:.1%}; "
          f"{len(flip_opps)} distinct opponents involved; "
          f"thresholds: SENSITIVE >= {SENSITIVE_FLIP_FRAC:.0%} or "
          f">= {SENSITIVE_MIN_OPPS} opps, MARGINAL >= "
          f"{MARGINAL_FLIP_FRAC:.1%} or >= {MARGINAL_MIN_OPPS} opps)",
          flush=True)
    print(f"Runtime: {probe['runtime_s']:.1f}s "
          f"({total_cells * len(e_vals):,} sims, single core)", flush=True)

    return {
        'verdict': verdict, 'flip_cells': n_flips,
        'total_cells': total_cells, 'flip_fraction': flip_frac,
        'flip_opponents': flip_opps, 'bulk_vs_atk': bulk_atk,
        'reps': rep_summary,
        'flips': [
            {'rep': lbl, 'opponent': opp, 'shields': [sf, so],
             'states': list(st)}
            for lbl, opp, sf, so, st in all_flip_cells
        ],
    }


def main():
    ap = argparse.ArgumentParser(
        description="Screen a species for energy-lead matchup sensitivity")
    ap.add_argument('species', help="PvPoke speciesName, e.g. Sableye")
    ap.add_argument('--shadow', action='store_true')
    ap.add_argument('--league', default='great')
    ap.add_argument('--pool', default=DEFAULT_POOL,
                    help=f"opponent pool file (default {DEFAULT_POOL})")
    ap.add_argument('--moveset', default=None, metavar='FAST,C1[,C2]',
                    help="move IDs, comma-separated "
                         "(default: get_default_moveset)")
    ap.add_argument('--reps', type=int, default=DEFAULT_REPS,
                    help=f"target number of representative IV spreads "
                         f"(default {DEFAULT_REPS}; actual count can be "
                         f"lower after dedup)")
    ap.add_argument('--json', default=None, metavar='OUT',
                    help="write machine-readable results to this path")
    args = ap.parse_args()

    moveset = args.moveset.split(',') if args.moveset else None
    if moveset is not None and len(moveset) < 2:
        ap.error("--moveset needs at least FAST,CHARGED1")

    probe = run_probe(args.species, args.shadow, args.league,
                      args.pool, moveset, args.reps)
    summary = summarize(probe)

    if args.json:
        out = {k: v for k, v in probe.items() if k != 'wins'}
        out['summary'] = summary
        with open(args.json, 'w') as f:
            json.dump(out, f, indent=2)
        print(f"JSON written to {args.json}", flush=True)


if __name__ == '__main__':
    main()
