#!/usr/bin/env python
"""Shared driver for testing candidate new-mechanics DECISION changes as
pluggable policies (no battle.py edits, no worktrees). Throwaway / investigation.

A candidate decision change is expressed as a focal-side charged policy (and/or
shield policy) that wraps the legacy pvpoke_dp / pvpoke_simulate_shield and
applies a mechanics-gated override. `compare()` sweeps a focal vs the GL pool x
9 shields under mechanics='new' and contrasts the candidate against the
NON-REGRESSION BASELINE (focal uses forced-legacy decisions on the new clock).
The OPPONENT uses forced-legacy decisions in BOTH runs, so only the focal's
decision varies (avoids the side-confound the prior workflow hit).

Returns per-cell regressions (candidate < baseline -- HARD-FLOOR violations) and
gains (candidate > baseline). Usage from a scratchpad script (cwd = repo root):

    import sys; sys.path.insert(0, 'scripts')
    from corpus_policy_driver import compare, build, cp_leg
    from gopvpsim.battle import pvpoke_dp
    def candidate(a, d, mechanics='legacy'):
        base = pvpoke_dp(a, d, mechanics='legacy')        # legacy choice
        if mechanics == 'new' and <grounded condition>:
            return <override move index>
        return base
    r = compare('Aegislash (Shield)', False, candidate)
    print(r['n_cells'], len(r['regress']), len(r['gains']))
    print('REGRESS', r['regress'][:10]); print('GAINS', r['gains'][:10])
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS
from gopvpsim.battle import (BattlePokemon, simulate, pvpoke_dp,
                             pvpoke_simulate_shield)
from gopvpsim.data import get_default_moveset
from gopvpsim.moves import get_moves

SHIELDS = [(s0, s1) for s0 in (0, 1, 2) for s1 in (0, 1, 2)]
_FAST, _CHARGED = get_moves()


def _parse(line):
    line = line.strip()
    shadow = line.endswith('(Shadow)')
    return (line[:-len(' (Shadow)')].strip() if shadow else line), shadow


def load_pool(path='opponent_pools/gl_top50_plus_cs.txt'):
    out = []
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith('#'):
                out.append(_parse(ln))
    return out


def build(species, shadow, sh):
    fid, cids = get_default_moveset(species, league='great', shadow=shadow)
    p = Pokemon.at_best_level(species, 15, 15, 15, league='great', shadow=shadow)
    return BattlePokemon.from_pokemon(p, dict(_FAST[fid]),
                                      [dict(_CHARGED[c]) for c in cids],
                                      shields=sh, league_cp=LEAGUE_CAPS['great'])


def cp_leg(a, d, mechanics='legacy'):
    """Forced-legacy charged decision (the baseline / opponent policy)."""
    return pvpoke_dp(a, d, mechanics='legacy')


def sp_leg(a, d, m, mechanics='legacy'):
    """Forced-legacy shield decision (the baseline / opponent policy)."""
    return pvpoke_simulate_shield(a, d, m, mechanics='legacy')


def compare(focal, shadow, focal_cp, focal_sp=None,
            pool='opponent_pools/gl_top50_plus_cs.txt', start=0, count=999):
    """Sweep focal vs pool x 9 shields, mechanics='new'. focal_cp/focal_sp are
    the CANDIDATE focal policies; opponent uses forced-legacy in both runs."""
    fsp = focal_sp or sp_leg
    regress, gains = [], []
    n = 0
    for opp, osh in load_pool(pool)[start:start + count]:
        if (opp, osh) == (focal, shadow):
            continue
        for (s0, s1) in SHIELDS:
            try:
                f = build(focal, shadow, s0); o = build(opp, osh, s1)
                base = simulate(f, o, mechanics='new',
                                charged_policy_0=cp_leg, charged_policy_1=cp_leg,
                                shield_policy_0=sp_leg, shield_policy_1=sp_leg
                                ).pvpoke_score(0)
                f = build(focal, shadow, s0); o = build(opp, osh, s1)
                cand = simulate(f, o, mechanics='new',
                                charged_policy_0=focal_cp, charged_policy_1=cp_leg,
                                shield_policy_0=fsp, shield_policy_1=sp_leg
                                ).pvpoke_score(0)
            except Exception:
                break
            n += 1
            lbl = f"{opp}{' (S)' if osh else ''} [{s0},{s1}]"
            if cand < base:
                regress.append((lbl, base, cand))
            elif cand > base:
                gains.append((lbl, base, cand))
    return {'n_cells': n, 'regress': regress, 'gains': gains,
            'net': sum(c - b for _, b, c in gains) + sum(c - b for _, b, c in regress)}


if __name__ == '__main__':
    # Self-test: candidate == legacy must give 0 regressions and 0 gains.
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--focal', default='Aegislash (Shield)')
    ap.add_argument('--shadow', action='store_true')
    ap.add_argument('--count', type=int, default=8)
    a = ap.parse_args()
    r = compare(a.focal, a.shadow, cp_leg, count=a.count)
    print(f"self-test {a.focal}: cells={r['n_cells']} "
          f"regress={len(r['regress'])} gains={len(r['gains'])} (both must be 0)")
