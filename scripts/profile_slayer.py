"""
Small representative slayer-style driver for profiling.

Single-process so cProfile output is meaningful. Simulates Annihilape mirror
matchups across a small set of focal profiles x opponent profiles x 9
shield scenarios.

Usage:
    # Plain wall-time
    python scripts/profile_slayer.py

    # cProfile, top 30 by cumulative time
    python scripts/profile_slayer.py --profile

    # cProfile sorted by total time in function (excluding callees)
    python scripts/profile_slayer.py --profile --sort tottime

    # py-spy (needs sudo on macOS — use only for final validation against
    # the real multi-process slayer round, not the iteration loop)
    sudo py-spy record -o flame.svg -- python scripts/profile_slayer.py
"""
import argparse
import cProfile
import os
import pstats
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gopvpsim.battle import simulate, pvpoke_dp
from gopvpsim.data import load_gamemaster, parse_types
from gopvpsim.moves import get_moves
from gopvpsim.pokemon import LEAGUE_CAPS

# The benchmark builds its pair through the SAME core the real workers use
# (D10), so a mon-construction change (form-change wiring, shadow flags,
# energy lead) can't quietly stop being measured here.
from deep_dive_lib.sweep import BattleSide, build_battle_pair, compute_iv_metadata


SPECIES = 'Annihilape'
LEAGUE = 'great'
FAST_ID = 'COUNTER'
CHARGED_IDS = ['RAGE_FIST', 'CLOSE_COMBAT']
SHIELD_SCENARIOS = [(s0, s1) for s0 in (0, 1, 2) for s1 in (0, 1, 2)]


def build_inputs(n_focal_profiles, n_opp_profiles):
    iv_meta = compute_iv_metadata(SPECIES, LEAGUE, shadow=False)

    # Profiles carry the IVs + level too: build_battle_pair needs them for
    # attach_form_change (a no-op for Annihilape, but the real workers pass
    # them, and the benchmark must build what they build).
    seen = {}
    for m in iv_meta:
        k = (round(m['atk'], 4), round(m['def_'], 4), int(m['hp']))
        if k not in seen:
            seen[k] = (m['atk'], m['def_'], m['hp'],
                       (m['atk_iv'], m['def_iv'], m['sta_iv']), m['level'])
    profiles = list(seen.values())

    focal = profiles[:n_focal_profiles]
    step = max(1, len(profiles) // n_opp_profiles)
    opps = profiles[::step][:n_opp_profiles]

    fast_db, charged_db = get_moves()
    fm_template = dict(fast_db[FAST_ID])
    cms_template = [dict(charged_db[cid]) for cid in CHARGED_IDS]

    gm = load_gamemaster()
    mon = next(m for m in gm['pokemon'] if m['speciesName'] == SPECIES)
    types = parse_types(mon)

    return focal, opps, fm_template, cms_template, types, mon


def _side(profile, types, fm_template, cms_template, mon):
    atk, def_, hp, ivs, level = profile
    return BattleSide(SPECIES, types, atk, def_, hp, False,
                      fm_template, cms_template, mon, ivs, level)


def run_sims(focal, opps, fm_template, cms_template, types, mon,
             mechanics='legacy'):
    # Mirrors slayer_iter_worker: one BattlePokemon pair per (focal, opp)
    # from the shared build_battle_pair, reset_for_battle between shield
    # scenarios (keeps caches warm). ``mechanics`` is forwarded so the
    # benchmark measures the turn model the run actually asked for -- it
    # used to always measure 'legacy' regardless.
    n = 0
    for f_prof in focal:
        for o_prof in opps:
            bp0, bp1 = build_battle_pair(
                _side(f_prof, types, fm_template, cms_template, mon),
                _side(o_prof, types, fm_template, cms_template, mon),
                LEAGUE_CAPS[LEAGUE])
            for s0, s1 in SHIELD_SCENARIOS:
                bp0.reset_for_battle(s0, opponent=bp1)
                bp1.reset_for_battle(s1, opponent=bp0)
                simulate(bp0, bp1,
                         charged_policy_0=pvpoke_dp,
                         charged_policy_1=pvpoke_dp,
                         mechanics=mechanics)
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n-focal', type=int, default=40)
    ap.add_argument('--n-opp', type=int, default=20)
    ap.add_argument('--profile', action='store_true',
                    help='Run under cProfile and print top stats')
    ap.add_argument('--top', type=int, default=30,
                    help='Number of profiler rows to print')
    ap.add_argument('--sort', default='cumulative',
                    choices=['cumulative', 'tottime', 'ncalls'])
    ap.add_argument('--mechanics', default='legacy',
                    choices=['legacy', 'new'],
                    help='Turn-mechanics model to measure (default legacy, '
                         'matching the dive default)')
    args = ap.parse_args()

    n_total = args.n_focal * args.n_opp * len(SHIELD_SCENARIOS)
    print(f"Building inputs: {args.n_focal} focal x {args.n_opp} opp x "
          f"{len(SHIELD_SCENARIOS)} scenarios = {n_total:,} sims "
          f"[{args.mechanics} mechanics]",
          flush=True)
    inputs = build_inputs(args.n_focal, args.n_opp)

    if args.profile:
        profiler = cProfile.Profile()
        t0 = time.time()
        profiler.enable()
        n = run_sims(*inputs, mechanics=args.mechanics)
        profiler.disable()
        elapsed = time.time() - t0
        print(f"  {n:,} sims in {elapsed:.2f}s "
              f"({n / elapsed:,.0f} sims/s) [profiled, ~2-5x slower than real]\n")
        stats = pstats.Stats(profiler).sort_stats(args.sort)
        stats.print_stats(args.top)
    else:
        t0 = time.time()
        n = run_sims(*inputs, mechanics=args.mechanics)
        elapsed = time.time() - t0
        print(f"  {n:,} sims in {elapsed:.2f}s "
              f"({n / elapsed:,.0f} sims/s)")


if __name__ == '__main__':
    main()
