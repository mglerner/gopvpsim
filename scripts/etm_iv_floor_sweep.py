#!/usr/bin/env python
"""One-off: "minimum IVs to build" floor sweep for ML Dialga-O / Palkia-O.

Companion to dialga_origin_etm_analysis.py / palkia_origin_etm_analysis.py.
Those answered the ETM and per-single-point questions; this one sweeps IVs
DEEP (each stat down to 0, plus diagonals and realistic raid spreads) to
answer the general player question: how low can your IVs go before an ML
Origin-forme legendary stops being worth building, ASSUMING it has the
signature move? Both the regular (both L50) and best-buddy (both L51) cases.

Each focal mon uses its default ML "with the move" build:
  - Dialga (Origin): Dragon Breath / Roar of Time + Iron Head
  - Palkia (Origin): Dragon Breath / Aqua Tail + Spacial Rend
vs the PvPoke Master top-60 (all opponents hundo). Wins are out of 540
(9 shields x 60 opponents). Master has no CP cap, so L50 vs L51 is a pure
level step on both sides; we report the two symmetric blocks (both L50,
both L51). Throwaway one-off; edit constants below. Do not import.

Output: userdata/dives/etm_iv_floor_sweep.md
"""
import sys, os
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS
from gopvpsim.moves import get_moves
from gopvpsim.battle import simulate, pvpoke_dp, BattlePokemon
from gopvpsim.data import get_default_moveset
from deep_dive import _parse_opponent_pool_line, parse_opponent_spec

LEAGUE    = 'master'
POOL_FILE = 'opponent_pools/master_top60.txt'
OUT_MD    = 'userdata/dives/etm_iv_floor_sweep.md'

# Focal mons with their default "you have the move" ML build.
FOCALS = [
    ('Dialga (Origin)', 'DRAGON_BREATH', ['ROAR_OF_TIME', 'IRON_HEAD']),
    ('Palkia (Origin)', 'DRAGON_BREATH', ['AQUA_TAIL', 'SPACIAL_REND']),
]

# IV spreads to sweep, grouped so the report reads as a floor story.
# Legendary raid/research/GBL catches are floored at 10/10/10, so nothing
# below 10 on any stat is buildable in practice -- the sweep stops at 10.
# (label, (a, d, s))
IV_GROUPS = [
    ('Reference', [
        ('hundo', (15, 15, 15)),
    ]),
    ('Attack floor (def/hp = 15)', [
        ('14 atk', (14, 15, 15)),
        ('13 atk', (13, 15, 15)),
        ('12 atk', (12, 15, 15)),
        ('11 atk', (11, 15, 15)),
        ('10 atk', (10, 15, 15)),
    ]),
    ('Defense floor (atk/hp = 15)', [
        ('14 def', (15, 14, 15)),
        ('13 def', (15, 13, 15)),
        ('12 def', (15, 12, 15)),
        ('11 def', (15, 11, 15)),
        ('10 def', (15, 10, 15)),
    ]),
    ('HP floor (atk/def = 15)', [
        ('14 hp', (15, 15, 14)),
        ('13 hp', (15, 15, 13)),
        ('12 hp', (15, 15, 12)),
        ('11 hp', (15, 15, 11)),
        ('10 hp', (15, 15, 10)),
    ]),
    ('Flat spreads (all three equal)', [
        ('13/13/13', (13, 13, 13)),
        ('12/12/12', (12, 12, 12)),
        ('10/10/10', (10, 10, 10)),
    ]),
    ('Realistic raid catches (>=10)', [
        ('10/15/15', (10, 15, 15)),
        ('15/10/15', (15, 10, 15)),
        ('10/14/13', (10, 14, 13)),
        ('12/10/11', (12, 10, 11)),
    ]),
]

SHIELDS = [(a, d) for a in (0, 1, 2) for d in (0, 1, 2)]
BLOCKS = [(50.0, 50.0), (51.0, 51.0)]   # (my level, opp level): regular, best-buddy

_FAST_DB, _CHARGED_DB = get_moves()


def build_mon(species, fast_id, charged_ids, a, d, s, shields, level,
              shadow=False):
    p = Pokemon.at_best_level(species, a, d, s, league=LEAGUE,
                              max_level=level, shadow=shadow)
    fm = dict(_FAST_DB[fast_id])
    cms = [dict(_CHARGED_DB[cid]) for cid in charged_ids]
    return BattlePokemon.from_pokemon(p, fm, cms, shields=shields,
                                      league_cp=LEAGUE_CAPS[LEAGUE])


def load_opponents():
    opps = []
    with open(POOL_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            display, base, is_shadow, fast_ov, charged_ov = (
                _parse_opponent_pool_line(line))
            base_clean, _variant, sh = parse_opponent_spec(display)
            if fast_ov is None or charged_ov is None:
                d_fast, d_charged = get_default_moveset(
                    base_clean, league=LEAGUE, shadow=sh)
            fast_id = fast_ov if fast_ov is not None else d_fast
            charged_ids = (list(charged_ov) if charged_ov is not None
                           else list(d_charged))
            opps.append((display, base_clean, sh, fast_id, charged_ids))
    return opps


def won_set(species, fast_id, charged_ids, iv, block, opponents):
    """Return the set of (opp_display, (shf, sho)) matchups this spread WINS,
    so callers can both count them and diff them against hundo by name."""
    a, d, s = iv
    my_lvl, opp_lvl = block
    won = set()
    for disp, base, sh, opp_fast, opp_charged in opponents:
        for shf, sho in SHIELDS:
            bp0 = build_mon(species, fast_id, charged_ids, a, d, s, shf, my_lvl)
            bp1 = build_mon(base, opp_fast, opp_charged, 15, 15, 15, sho,
                            opp_lvl, shadow=sh)
            r = simulate(bp0, bp1, charged_policy_0=pvpoke_dp,
                         charged_policy_1=pvpoke_dp)
            if r.pvpoke_score(0) > r.pvpoke_score(1):
                won.add((disp, (shf, sho)))
    return won


def fmt_flips(flips):
    """Render a set of (opp, (shf, sho)) as 'Opp 1-2, Opp2 0-0' sorted."""
    return ", ".join(f"{opp} {sh[0]}-{sh[1]}"
                     for opp, sh in sorted(flips)) or "(none)"


def main():
    opponents = load_opponents()
    total = len(opponents) * len(SHIELDS)
    all_ivs = [iv for _, rows in IV_GROUPS for _, iv in rows]
    n_sims = (len(FOCALS) * len(all_ivs) * len(opponents) * len(SHIELDS)
              * len(BLOCKS))
    print(f"Pool: {len(opponents)} opponents (hundo). Spreads: {len(all_ivs)}. "
          f"Total sims: {n_sims:,}\n")

    # results[species][iv][block] = set of won (opp, shields)
    results = defaultdict(lambda: defaultdict(dict))
    done = 0
    for species, fast_id, charged_ids in FOCALS:
        for _, rows in IV_GROUPS:
            for _, iv in rows:
                for block in BLOCKS:
                    results[species][iv][block] = won_set(
                        species, fast_id, charged_ids, iv, block, opponents)
                    done += len(opponents) * len(SHIELDS)
                print(f"  {species} {iv}: "
                      f"reg={len(results[species][iv][BLOCKS[0]])} "
                      f"bb={len(results[species][iv][BLOCKS[1]])} "
                      f"({done:,}/{n_sims:,})")

    lines = [
        "# ML Dialga-O / Palkia-O: minimum-IV floor sweep\n",
        f"For each focal mon's default **with-the-move** build, sweeping IVs "
        f"from hundo down to the 10/10/10 catch floor vs the Master top-60 "
        f"(all hundo). **reg** = both mons L50; **bb** = both mons L51. The "
        f"win count (out of {total}) is secondary; what matters for ML "
        f"teambuilding is **which specific matchups you give up** by running a "
        f"non-hundo spread, so each spread also lists the named matchups it "
        f"LOSES (and any it gains) relative to hundo. Matchups are "
        f"`Opponent shields` where shields is your-opp (e.g. `Dialga 1-2`).\n",
        "Builds: Dialga (Origin) Dragon Breath / Roar of Time + Iron Head; "
        "Palkia (Origin) Dragon Breath / Aqua Tail + Spacial Rend.\n",
        "Generated by `scripts/etm_iv_floor_sweep.py`.\n",
    ]
    for species, _, _ in FOCALS:
        hundo = {b: results[species][(15, 15, 15)][b] for b in BLOCKS}
        lines.append(f"\n## {species}\n")
        # Secondary: the aggregate count table.
        lines.append("### Win counts (secondary)\n")
        lines.append("| group | spread | IVs | wins reg | d | wins bb | d |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for group, rows in IV_GROUPS:
            for label, iv in rows:
                a, d, s = iv
                wr = len(results[species][iv][BLOCKS[0]])
                wb = len(results[species][iv][BLOCKS[1]])
                lines.append(
                    f"| {group} | {label} | {a}/{d}/{s} | {wr} | "
                    f"{wr - len(hundo[BLOCKS[0]]):+d} | {wb} | "
                    f"{wb - len(hundo[BLOCKS[1]]):+d} |")
        # Primary: named matchups lost vs hundo, per spread.
        lines.append("\n### Matchups given up vs hundo (the part that matters)\n")
        for group, rows in IV_GROUPS:
            for label, iv in rows:
                if iv == (15, 15, 15):
                    continue
                a, d, s = iv
                reg_lost = hundo[BLOCKS[0]] - results[species][iv][BLOCKS[0]]
                reg_gain = results[species][iv][BLOCKS[0]] - hundo[BLOCKS[0]]
                bb_lost = hundo[BLOCKS[1]] - results[species][iv][BLOCKS[1]]
                bb_gain = results[species][iv][BLOCKS[1]] - hundo[BLOCKS[1]]
                lines.append(f"\n**{a}/{d}/{s}** ({label})")
                lines.append(f"- regular (L50) loses: {fmt_flips(reg_lost)}"
                             + (f"  |  gains: {fmt_flips(reg_gain)}"
                                if reg_gain else ""))
                lines.append(f"- best-buddy (L51) loses: {fmt_flips(bb_lost)}"
                             + (f"  |  gains: {fmt_flips(bb_gain)}"
                                if bb_gain else ""))
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, 'w') as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_MD}")


if __name__ == '__main__':
    main()
