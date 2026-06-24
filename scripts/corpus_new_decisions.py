#!/usr/bin/env python
"""Corpus harness for the test-grounded new-mechanics decision layer (rescoped
Phase 1, 2026-06-24). Throwaway / investigation tool.

For a focal vs the GL pool, all 9 shields, under mechanics='new', reports two
things per matchup:

  1. NON-REGRESSION GATE: score(new-resolution + CURRENT new decisions) vs
     score(new-resolution + forced-legacy decisions). The current new decision
     layer must never score BELOW the legacy-decisions baseline. Any
     'REGRESS' row is a hard failure.

  2. IMPROVEMENT CANDIDATES: matchups where the focal LOSES under new while
     ending with >= its cheapest charged move's energy unspent -- i.e. it died
     holding a chargeable move it never committed. Under the new charged-
     survives-death rule, committing that charge before death could improve the
     focal's score. These 'CAND' rows are where a grounded decisive-lethal-
     commit change should help.

Prints a JSON_SUMMARY line for machine parsing.

Usage:
  python scripts/corpus_new_decisions.py --focal "Aegislash (Blade)" [--shadow]
      [--start N --count M] [--quiet]
"""
import sys, os, json, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS
from gopvpsim.battle import (BattlePokemon, simulate, pvpoke_dp,
                             pvpoke_simulate_shield)
from gopvpsim.data import get_default_moveset
from gopvpsim.moves import get_moves

SHIELDS = [(s0, s1) for s0 in (0, 1, 2) for s1 in (0, 1, 2)]


def parse_species(line):
    line = line.strip()
    shadow = line.endswith('(Shadow)')
    return (line[:-len(' (Shadow)')].strip() if shadow else line), shadow


def load_pool(path):
    out = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith('#'):
                out.append(parse_species(ln))
    return out


def build(species, shadow, sh):
    fast_moves, charged_moves = get_moves()
    fid, cids = get_default_moveset(species, league='great', shadow=shadow)
    p = Pokemon.at_best_level(species, 15, 15, 15, league='great', shadow=shadow)
    return (BattlePokemon.from_pokemon(p, dict(fast_moves[fid]),
                                       [dict(charged_moves[c]) for c in cids],
                                       shields=sh, league_cp=LEAGUE_CAPS['great']))


# Policies that IGNORE the passed mechanics -> force LEGACY decisions, so we can
# isolate the new-resolution/legacy-decisions baseline (the non-regression floor).
def _cp_leg(a, d, mechanics='legacy'):
    return pvpoke_dp(a, d, mechanics='legacy')


def _sp_leg(a, d, m, mechanics='legacy'):
    return pvpoke_simulate_shield(a, d, m, mechanics='legacy')


def run_one(focal, f_sh, opp, o_sh, s0, s1, force_legacy):
    f = build(focal, f_sh, s0)
    o = build(opp, o_sh, s1)
    cheapest = min(m['energy'] for m in f.charged_moves)
    if force_legacy:
        res = simulate(f, o, mechanics='new',
                       charged_policy_0=_cp_leg, charged_policy_1=_cp_leg,
                       shield_policy_0=_sp_leg, shield_policy_1=_sp_leg)
    else:
        res = simulate(f, o, mechanics='new',
                       charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp)
    return {
        'score': res.pvpoke_score(0),
        'focal_lost': res.hp_remaining[0] <= 0,
        'focal_end_energy': res.energy_remaining[0],
        'cheapest_cm': cheapest,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--focal', required=True)
    ap.add_argument('--shadow', action='store_true')
    ap.add_argument('--pool', default='opponent_pools/gl_top50_plus_cs.txt')
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--count', type=int, default=999)
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    pool = load_pool(args.pool)[args.start:args.start + args.count]
    regress, cands = [], []
    n_cells = 0
    for opp, o_sh in pool:
        if (opp, o_sh) == (args.focal, args.shadow):
            continue
        for (s0, s1) in SHIELDS:
            try:
                cur = run_one(args.focal, args.shadow, opp, o_sh, s0, s1, False)
                base = run_one(args.focal, args.shadow, opp, o_sh, s0, s1, True)
            except Exception as e:
                if not args.quiet:
                    print(f"  SKIP {opp} [{s0},{s1}]: {type(e).__name__}: {e}")
                break
            n_cells += 1
            label = f"{opp}{' (S)' if o_sh else ''} [{s0},{s1}]"
            if cur['score'] < base['score']:
                regress.append({'m': label, 'cur': cur['score'], 'base': base['score'],
                                'delta': cur['score'] - base['score']})
            # Improvement candidate: focal lost holding a chargeable move (baseline view)
            if (base['focal_lost']
                    and base['focal_end_energy'] >= base['cheapest_cm']):
                cands.append({'m': label, 'score': base['score'],
                              'end_energy': base['focal_end_energy'],
                              'cheapest_cm': base['cheapest_cm']})

    flabel = f"{args.focal}{' (Shadow)' if args.shadow else ''}"
    if not args.quiet:
        print(f"\n=== {flabel} :: new-decisions corpus ({n_cells} cells) ===")
        print(f"REGRESSIONS (new/new < new/legacy-decisions): {len(regress)}")
        for r in sorted(regress, key=lambda x: x['delta'])[:15]:
            print(f"  REGRESS {r['m']:34s} {r['base']} -> {r['cur']}  (Δ{r['delta']})")
        print(f"IMPROVEMENT CANDIDATES (lost holding chargeable energy): {len(cands)}")
        for c in sorted(cands, key=lambda x: x['score'])[:15]:
            print(f"  CAND    {c['m']:34s} score={c['score']} "
                  f"end_energy={c['end_energy']} cheapest_cm={c['cheapest_cm']}")
    print("\nJSON_SUMMARY " + json.dumps({
        'focal': flabel, 'n_cells': n_cells,
        'n_regressions': len(regress), 'regressions': regress[:20],
        'n_candidates': len(cands), 'candidates': cands[:20],
    }))


if __name__ == '__main__':
    main()
