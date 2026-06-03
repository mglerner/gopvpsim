#!/usr/bin/env python
"""One-off: does an energy lead (0 / 1-fast / 2-fast Shadow Claws of carry-
over) flip any matchups for Michael's 4 Shadow Sableye build candidates?

Background:
  - Recommendation conversation 2026-06-03. 4 candidate IVs:
    (2,11,13), (2,14,12), (5,13,15), (6,15,15) all "premium bulk" at
    GL cap, no atk-breakpoint differentiation in the dive's surfaced
    tiers (all need atk≥155+, all 4 candidates max at ~144 atk).
  - RyanSwag historical bias: a little atk often matters more than
    pure stat product, since Sableye's Shadow Claw chip race accumulates
    over many fast moves.
  - Sableye is often deployed as a safe switch or closer, where it
    enters battle with 1-2 fast moves of accumulated energy from
    pre-swap fast moves. Real PvP value differs from the dive's
    energy-0 default sim.
  - Energy-lead-as-a-sim-axis is logged as a future feature (TODO.md
    'Features to add'). This script is a one-off proxy that constructs
    BattlePokemon with non-zero energy by mutating bp.energy
    post-construction (BattlePokemon.initial_energy already exists,
    just not surfaced through scripts/run_website_dives.py yet).

Output: per (IV, moveset, energy_lead), aggregate wins across the
68-opponent GL pool and 9 shield scenarios; per-matchup flip list
when energy is non-zero.

Run AS-IS only with the 4 candidate IVs. No CLI; edit constants
below to adjust. Throwaway — do not import.
"""
import sys, os
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

from gopvpsim.battle import simulate
from gopvpsim.battle import pvpoke_dp
from gopvpsim.data import get_default_moveset, load_gamemaster
from deep_dive import make_battle_pokemon, _parse_opponent_pool_line


# --- Configuration -----------------------------------------------------------

FOCAL_SPECIES = 'Sableye'
FOCAL_SHADOW  = True
LEAGUE        = 'great'

# The 4 build candidates from Michael's collection.
CANDIDATES = [
    (2, 11, 13),
    (2, 14, 12),
    (5, 13, 15),
    (6, 15, 15),
]

# 4 movesets being compared in the recent dive. Stored as (label, fast,
# [c1, c2]). Order doesn't matter for the sim; alphabetical here to
# match the dive's canonical order.
MOVESETS = [
    ('DG+FP', 'SHADOW_CLAW', ['DAZZLING_GLEAM', 'FOUL_PLAY']),
    ('DP+FP', 'SHADOW_CLAW', ['DRAIN_PUNCH',    'FOUL_PLAY']),
    ('PG+FP', 'SHADOW_CLAW', ['FOUL_PLAY',      'POWER_GEM']),
    ('SS+FP', 'SHADOW_CLAW', ['FOUL_PLAY',      'SHADOW_SNEAK']),
]

# Energy lead values: 0 baseline, 8 = 1 Shadow Claw, 16 = 2 Shadow
# Claws. Shadow Claw is 8 energy per fast move.
ENERGY_LEADS = [0, 8, 16]

# All 9 shield scenarios.
SHIELDS = [(a, d) for a in (0, 1, 2) for d in (0, 1, 2)]

POOL_FILE = 'opponent_pools/gl_top50_plus_cs.txt'


# --- Load opponents (same path scripts/deep_dive.py uses) --------------------

def load_opponents():
    """Parse opponent pool, returning list of (display, fast_id, [charged])."""
    opps = []
    with open(POOL_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            display, base, is_shadow, fast_ov, charged_ov = (
                _parse_opponent_pool_line(line))
            if fast_ov is None or charged_ov is None:
                try:
                    d_fast, d_charged = get_default_moveset(
                        base, league=LEAGUE, shadow=is_shadow)
                except (KeyError, ValueError):
                    continue
            else:
                d_fast, d_charged = None, None
            fast_id = fast_ov if fast_ov is not None else d_fast
            charged_ids = (list(charged_ov) if charged_ov is not None
                          else list(d_charged))
            opps.append((display, base, is_shadow, fast_id, charged_ids))
    return opps


# --- Single matchup ----------------------------------------------------------

def run_matchup(iv, fast_id, charged_ids, opp_base, opp_shadow, opp_fast,
                opp_charged, shields_focal, shields_opp, energy_lead):
    """Return (focal_score, opp_score) from a single sim with the given
    starting energy on the focal side. Opponent always starts at energy 0
    (modeling: focal is the safe-switch/closer; opponent is the just-out
    counterpart entering fresh)."""
    a, d, s = iv
    bp0 = make_battle_pokemon(FOCAL_SPECIES, fast_id, charged_ids, LEAGUE,
                              shields_focal, a, d, s, shadow=FOCAL_SHADOW)
    # Mutate the energy post-__post_init__ to simulate carry-over.
    bp0.energy = energy_lead
    bp0.initial_energy = energy_lead  # keep consistent for any internal reset

    bp1 = make_battle_pokemon(opp_base, opp_fast, opp_charged, LEAGUE,
                              shields_opp, 0, 15, 15, shadow=opp_shadow)
    # Opponent uses generic rank-1ish IVs (0/15/15 = generic bulk). The
    # dive itself runs multiple opp-IV modes; here we pick one to keep
    # the matrix tractable. Caveat noted in the output.

    result = simulate(bp0, bp1,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp)
    return result.pvpoke_score(0), result.pvpoke_score(1)


# --- Aggregate sweep ---------------------------------------------------------

def winner(s0, s1):
    """Return 1 if focal wins, 0 if tie, -1 if focal loses."""
    if s0 > s1: return 1
    if s0 < s1: return -1
    return 0


def main():
    opponents = load_opponents()
    print(f"Pool: {len(opponents)} opponents")
    print(f"Candidates: {CANDIDATES}")
    print(f"Movesets: {[m[0] for m in MOVESETS]}")
    print(f"Energy leads: {ENERGY_LEADS}")
    print(f"Shield scenarios: {len(SHIELDS)} (all 9)")
    n_sims = (len(CANDIDATES) * len(MOVESETS) * len(opponents)
              * len(SHIELDS) * len(ENERGY_LEADS))
    print(f"Total sims: {n_sims:,}")
    print()

    # Results: results[iv][moveset_label][energy_lead] = list of
    #   (opp_display, shields, focal_score, opp_score, won_flag)
    results = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    progress = 0
    for iv in CANDIDATES:
        for ms_label, fast_id, charged_ids in MOVESETS:
            for opp_display, opp_base, opp_shadow, opp_fast, opp_charged in opponents:
                for shields_focal, shields_opp in SHIELDS:
                    for e_lead in ENERGY_LEADS:
                        s0, s1 = run_matchup(
                            iv, fast_id, charged_ids,
                            opp_base, opp_shadow, opp_fast, opp_charged,
                            shields_focal, shields_opp, e_lead)
                        w = winner(s0, s1)
                        results[iv][ms_label][e_lead].append(
                            (opp_display, (shields_focal, shields_opp),
                             s0, s1, w))
                        progress += 1
            print(f"  done {iv} {ms_label}: progress {progress:,} / {n_sims:,}")

    print()
    print("=" * 78)
    print("AGGREGATE WIN COUNTS (out of {} matchups per cell)".format(
        len(opponents) * len(SHIELDS)))
    print("=" * 78)
    print()
    hdr = f"{'IV':>10}  {'Moveset':>6}"
    for e in ENERGY_LEADS:
        hdr += f"  {'wins@' + str(e):>9}  {'losses@' + str(e):>11}"
    print(hdr)
    print("-" * len(hdr))
    for iv in CANDIDATES:
        iv_str = f"{iv[0]}/{iv[1]}/{iv[2]}"
        for ms_label, _, _ in MOVESETS:
            row = f"{iv_str:>10}  {ms_label:>6}"
            for e in ENERGY_LEADS:
                rs = results[iv][ms_label][e]
                wins = sum(1 for r in rs if r[4] == 1)
                losses = sum(1 for r in rs if r[4] == -1)
                row += f"  {wins:>9}  {losses:>11}"
            print(row)

    print()
    print("=" * 78)
    print("MATCHUP FLIPS (matchups where energy lead changes the outcome)")
    print("=" * 78)
    print()
    for iv in CANDIDATES:
        iv_str = f"{iv[0]}/{iv[1]}/{iv[2]}"
        for ms_label, _, _ in MOVESETS:
            base = {(r[0], r[1]): r[4] for r in results[iv][ms_label][0]}
            for e in ENERGY_LEADS[1:]:
                lifted = {(r[0], r[1]): r[4] for r in results[iv][ms_label][e]}
                flips_to_win = sorted([k for k in base
                                       if base[k] != 1 and lifted[k] == 1])
                flips_to_loss = sorted([k for k in base
                                        if base[k] == 1 and lifted[k] == -1])
                if flips_to_win or flips_to_loss:
                    print(f"  {iv_str} {ms_label} @ energy={e}:")
                    if flips_to_win:
                        print(f"    GAINED ({len(flips_to_win)}):")
                        for opp, sh in flips_to_win:
                            print(f"      {opp} {sh}")
                    if flips_to_loss:
                        print(f"    LOST ({len(flips_to_loss)}):")
                        for opp, sh in flips_to_loss:
                            print(f"      {opp} {sh}")

    print()
    print("=" * 78)
    print("HEAD-TO-HEAD: which IV gains the most from energy lead?")
    print("=" * 78)
    print()
    print(f"{'IV':>10}  {'Moveset':>6}  {'wins@0':>8}  {'wins@8':>8}  "
          f"{'wins@16':>8}  {'Δ8':>5}  {'Δ16':>5}")
    print("-" * 64)
    for iv in CANDIDATES:
        iv_str = f"{iv[0]}/{iv[1]}/{iv[2]}"
        for ms_label, _, _ in MOVESETS:
            w0 = sum(1 for r in results[iv][ms_label][0] if r[4] == 1)
            w8 = sum(1 for r in results[iv][ms_label][8] if r[4] == 1)
            w16 = sum(1 for r in results[iv][ms_label][16] if r[4] == 1)
            print(f"{iv_str:>10}  {ms_label:>6}  {w0:>8}  {w8:>8}  {w16:>8}"
                  f"  {w8-w0:>+5}  {w16-w0:>+5}")

    # Cross-IV comparison: which IV consistently wins more at any energy level?
    print()
    print("=" * 78)
    print("CROSS-IV: total wins summed across all 4 movesets, per energy lead")
    print("=" * 78)
    print()
    print(f"{'IV':>10}  {'wins@0':>8}  {'wins@8':>8}  {'wins@16':>8}")
    print("-" * 42)
    for iv in CANDIDATES:
        iv_str = f"{iv[0]}/{iv[1]}/{iv[2]}"
        totals = {e: 0 for e in ENERGY_LEADS}
        for ms_label, _, _ in MOVESETS:
            for e in ENERGY_LEADS:
                totals[e] += sum(1 for r in results[iv][ms_label][e]
                                  if r[4] == 1)
        print(f"{iv_str:>10}  {totals[0]:>8}  {totals[8]:>8}  {totals[16]:>8}")


if __name__ == '__main__':
    main()
