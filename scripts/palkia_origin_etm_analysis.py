#!/usr/bin/env python
"""One-off: Palkia (Origin) Master League ETM / IV / best-buddy deep dive.

Companion to scripts/dialga_origin_etm_analysis.py. Michael did not supply
specific Palkia (Origin) candidate IVs, so this report uses hundo plus the
generic single-/double-point drops to answer the same GoFest questions for
Palkia as the Dialga script does for Dialga.

Background (recommendation conversation 2026-06-19):
  - GoFest lets Michael ETM the signature move (Spacial Rend) onto a
    Palkia (Origin). This report supports the same decisions as the Dialga
    one: best-buddy (L51) vs regular (L50) on BOTH sides; what each single
    stat point costs; and whether the ETM (Spacial Rend) is worth it over
    the best no-ETM build.
  - Meta = PvPoke Master top-60 (snapshot in opponent_pools/master_top60.txt),
    all opponents assumed hundo (15/15/15). In Master the 10000 CP cap never
    binds, so regular = L50.0 and best-buddy = L51.0 are pure level steps.

Spacial Rend (95 power / 55 energy, no debuff) is Palkia (Origin)'s cheap
no-debuff nuke. The no-ETM alternative nukes are Draco Meteor (150/65 but
self-debuffs -2 atk) and Hydro Pump (130/75). Aqua Tail (55/35) is the
cheap spam/bait charge in every viable build. Section 4 surfaces which
matchups the Spacial Rend ETM actually flips.

Output: a markdown report at userdata/dives/palkia_origin_etm_analysis.md
with four sections, each laid out so L50 (regular) vs L51 (best-buddy)
reads side by side. Throwaway one-off; no CLI, edit constants below.
Do not import.
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


# --- Configuration -----------------------------------------------------------

FOCAL_SPECIES = 'Palkia (Origin)'
LEAGUE        = 'master'
POOL_FILE     = 'opponent_pools/master_top60.txt'
OUT_MD        = 'userdata/dives/palkia_origin_etm_analysis.md'

# Curated focal IV set. No specific Palkia candidate IVs were supplied, so
# this is hundo plus the generic single-/double-point drops. 15/14/15
# (-1 def) and 15/15/14 (-1 hp) double as representative "trade 1 def for
# 1 hp" spreads for the head-to-head (sec 3). 0/15/15 is a deliberately bad
# atk spread for scale.
HUNDO = (15, 15, 15)
FOCAL_IVS = [
    (15, 15, 15),   # hundo reference
    (14, 15, 15),   # -1 atk
    (13, 15, 15),   # -2 atk
    (15, 14, 15),   # -1 def  (representative def-for-hp swap, sec 3)
    (15, 13, 15),   # -2 def
    (15, 15, 14),   # -1 hp   (representative def-for-hp swap, sec 3)
    (15, 15, 13),   # -2 hp
    (0, 15, 15),    # bad atk, scale anchor
]
# Representative spreads (and hundo) used in the best-buddy matrix (sec 1)
# and the def-for-hp head-to-head (sec 3). Named ROT/ETM for parity with
# the Dialga script; here they are just the -1 def and -1 hp spreads.
REAL_ROT = (15, 14, 15)   # -1 def representative
REAL_ETM = (15, 15, 14)   # -1 hp representative

# Single-point sensitivity rows (sec 2): label -> IV.
SENS_ROWS = [
    ('-1 atk', (14, 15, 15)),
    ('-2 atk', (13, 15, 15)),
    ('-1 def', (15, 14, 15)),
    ('-2 def', (15, 13, 15)),
    ('-1 hp',  (15, 15, 14)),
    ('-2 hp',  (15, 15, 13)),
]

# Four movesets, all Dragon Breath. Two Spacial Rend builds ("with ETM")
# and two no-ETM builds. Aqua Tail is the cheap spam/bait charge; the
# second slot is the nuke.
MOVESETS = [
    ('AT/SR',    'DRAGON_BREATH', ['AQUA_TAIL', 'SPACIAL_REND']),
    ('Hydro/SR', 'DRAGON_BREATH', ['SPACIAL_REND', 'HYDRO_PUMP']),
    ('AT/Draco', 'DRAGON_BREATH', ['AQUA_TAIL', 'DRACO_METEOR']),
    ('AT/Hydro', 'DRAGON_BREATH', ['AQUA_TAIL', 'HYDRO_PUMP']),
]
PRIMARY_MS = 'AT/SR'   # the build sec 1-3 analyze

# Best-buddy 2x2: (my level, opponent level). 51 = best-buddy, 50 = regular.
LEVELS = [50.0, 51.0]
LEVEL_BLOCKS = [(f, o) for f in LEVELS for o in LEVELS]

# All 9 shield scenarios.
SHIELDS = [(a, d) for a in (0, 1, 2) for d in (0, 1, 2)]


# --- Build helpers -----------------------------------------------------------

_FAST_DB, _CHARGED_DB = get_moves()


def build_mon(species, fast_id, charged_ids, a, d, s, shields, level,
              shadow=False):
    """BattlePokemon at an EXPLICIT level (max_level=level). Mirrors
    deep_dive.make_battle_pokemon but pins the level rather than using the
    league default, so L50 (regular) and L51 (best-buddy) are separable."""
    p = Pokemon.at_best_level(species, a, d, s, league=LEAGUE,
                              max_level=level, shadow=shadow)
    fm = dict(_FAST_DB[fast_id])
    cms = [dict(_CHARGED_DB[cid]) for cid in charged_ids]
    return BattlePokemon.from_pokemon(p, fm, cms, shields=shields,
                                      league_cp=LEAGUE_CAPS[LEAGUE])


def load_opponents():
    """Parse the pool, returning (display, base, is_shadow, fast, [charged])."""
    opps = []
    with open(POOL_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            display, base, is_shadow, fast_ov, charged_ov = (
                _parse_opponent_pool_line(line))
            # All top-60 use default movesets (no overrides in this pool),
            # but honor overrides if a future edit adds them.
            base_clean, _variant, sh = parse_opponent_spec(display)
            if fast_ov is None or charged_ov is None:
                d_fast, d_charged = get_default_moveset(
                    base_clean, league=LEAGUE, shadow=sh)
            fast_id = fast_ov if fast_ov is not None else d_fast
            charged_ids = (list(charged_ov) if charged_ov is not None
                           else list(d_charged))
            opps.append((display, base_clean, sh, fast_id, charged_ids))
    return opps


def winner(s0, s1):
    return 1 if s0 > s1 else (-1 if s0 < s1 else 0)


# --- Sweep -------------------------------------------------------------------

def run_sweep(opponents):
    """results[iv][ms][block] = list of (opp_display, shields, s0, s1, w).

    block is the (my_level, opp_level) tuple. Opponents are hundo (15/15/15),
    built at opp_level; focal built at my_level.
    """
    results = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    n_sims = (len(FOCAL_IVS) * len(MOVESETS) * len(opponents)
              * len(SHIELDS) * len(LEVEL_BLOCKS))
    print(f"Pool: {len(opponents)} opponents (all hundo 15/15/15)")
    print(f"Focal IVs: {len(FOCAL_IVS)}  Movesets: {[m[0] for m in MOVESETS]}")
    print(f"Level blocks (my,opp): {LEVEL_BLOCKS}")
    print(f"Total sims: {n_sims:,}\n")

    progress = 0
    for iv in FOCAL_IVS:
        a, d, s = iv
        for ms_label, fast_id, charged_ids in MOVESETS:
            for my_lvl, opp_lvl in LEVEL_BLOCKS:
                for disp, base, sh, opp_fast, opp_charged in opponents:
                    for shf, sho in SHIELDS:
                        bp0 = build_mon(FOCAL_SPECIES, fast_id, charged_ids,
                                        a, d, s, shf, my_lvl)
                        bp1 = build_mon(base, opp_fast, opp_charged,
                                        15, 15, 15, sho, opp_lvl, shadow=sh)
                        r = simulate(bp0, bp1, charged_policy_0=pvpoke_dp,
                                     charged_policy_1=pvpoke_dp)
                        s0, s1 = r.pvpoke_score(0), r.pvpoke_score(1)
                        results[iv][ms_label][(my_lvl, opp_lvl)].append(
                            (disp, (shf, sho), s0, s1, winner(s0, s1)))
                        progress += 1
            print(f"  done IV {a}/{d}/{s} {ms_label}: "
                  f"{progress:,}/{n_sims:,}")
    return results


def wins_in(results, iv, ms, block):
    return sum(1 for r in results[iv][ms][block] if r[4] == 1)


def outcome_map(results, iv, ms, block):
    """(opp_display, shields) -> win flag, for flip comparisons."""
    return {(r[0], r[1]): r[4] for r in results[iv][ms][block]}


# --- Report ------------------------------------------------------------------

def blk(b):
    """Pretty (my_level, opp_level) block label."""
    f, o = b
    return f"me L{int(f)} / opp L{int(o)}"


def fmt_sh(sh):
    return f"{sh[0]}-{sh[1]}"


def section1(results, total):
    """Best-buddy 2x2 win matrix per real-candidate IV (primary moveset)."""
    out = ["## 1. Best-buddy 2x2 win matrix\n",
           f"Total wins out of **{total}** ({len(SHIELDS)} shields x 60 "
           f"opponents) for the **{PRIMARY_MS}** build, in each (my level, "
           f"opponent level) block. Rows = my Palkia-O level (L50 regular, "
           f"L51 best-buddy); columns = opponent level.\n"]
    for iv in [HUNDO, REAL_ROT, REAL_ETM]:
        a, d, s = iv
        tag = {HUNDO: 'hundo', REAL_ROT: '-1 def representative',
               REAL_ETM: '-1 hp representative'}[iv]
        out.append(f"\n**{a}/{d}/{s}** ({tag})\n")
        out.append("| my level \\ opp | opp L50 | opp L51 |")
        out.append("| --- | --- | --- |")
        for mf in LEVELS:
            cells = [f"my L{int(mf)}"]
            for mo in LEVELS:
                cells.append(str(wins_in(results, iv, PRIMARY_MS, (mf, mo))))
            out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def section2(results, total):
    """Per-stat-point sensitivity from hundo, in the two symmetric
    (regular vs best-buddy) diagonal blocks."""
    diag = [(50.0, 50.0), (51.0, 51.0)]
    out = ["## 2. Per-stat-point sensitivity\n",
           f"Win count for the **{PRIMARY_MS}** build vs the {total}-matchup "
           f"pool, and the cost of each single-/double-point drop from hundo. "
           f"Shown in the two symmetric blocks: **both L50** (regular mirror) "
           f"and **both L51** (best-buddy mirror).\n",
           "| spread | drop | wins (both L50) | d vs hundo | "
           "wins (both L51) | d vs hundo |",
           "| --- | --- | --- | --- | --- | --- |"]
    base = {b: wins_in(results, HUNDO, PRIMARY_MS, b) for b in diag}
    out.append(f"| 15/15/15 | hundo | {base[diag[0]]} | - | "
               f"{base[diag[1]]} | - |")
    for label, iv in SENS_ROWS:
        a, d, s = iv
        w50 = wins_in(results, iv, PRIMARY_MS, diag[0])
        w51 = wins_in(results, iv, PRIMARY_MS, diag[1])
        out.append(f"| {a}/{d}/{s} | {label} | {w50} | "
                   f"{w50 - base[diag[0]]:+d} | {w51} | "
                   f"{w51 - base[diag[1]]:+d} |")
    out.append("\nNote: the 15/14/15 (-1 def) and 15/15/14 (-1 hp) rows here "
               "equal the matching representative totals in section 1.")
    return "\n".join(out) + "\n"


def section3(results):
    """15/14/15 vs 15/15/14 head-to-head: named matchups where they diverge,
    per level block (primary moveset)."""
    out = ["## 3. 15/14/15 vs 15/15/14 head-to-head (def-for-hp swap)\n",
           f"The exact (opponent, shields) matchups where trading 1 def for "
           f"1 hp reaches a DIFFERENT outcome under the **{PRIMARY_MS}** build, "
           f"per level block. These two spreads differ only by 1 def <-> 1 hp; "
           f"this shows whether that swap matters for Palkia (Origin).\n"]
    any_div = False
    for b in LEVEL_BLOCKS:
        m_rot = outcome_map(results, REAL_ROT, PRIMARY_MS, b)
        m_etm = outcome_map(results, REAL_ETM, PRIMARY_MS, b)
        divs = sorted(k for k in m_rot if m_rot[k] != m_etm[k])
        if not divs:
            out.append(f"\n**{blk(b)}**: identical outcomes in all "
                       f"{len(m_rot)} matchups.")
            continue
        any_div = True
        out.append(f"\n**{blk(b)}**: {len(divs)} divergent matchup(s):\n")
        out.append("| opponent | shields | 15/14/15 | 15/15/14 |")
        out.append("| --- | --- | --- | --- |")
        for opp, sh in divs:
            w = {1: 'win', 0: 'tie', -1: 'loss'}
            out.append(f"| {opp} | {fmt_sh(sh)} | {w[m_rot[(opp, sh)]]} | "
                       f"{w[m_etm[(opp, sh)]]} |")
    if not any_div:
        out.append("\n**Conclusion: the def-for-hp swap is functionally "
                    "identical across every block** - it flips no matchups. "
                    "Build whichever you have; the ETM decision (section 4) "
                    "dominates.")
    return "\n".join(out) + "\n"


def flip_block(results, ms_with, ms_without, b):
    """Named matchups ms_with wins that ms_without does not (and vice versa),
    at hundo IVs, in block b."""
    m_w = outcome_map(results, HUNDO, ms_with, b)
    m_o = outcome_map(results, HUNDO, ms_without, b)
    gained = sorted(k for k in m_w if m_w[k] == 1 and m_o[k] != 1)
    lost = sorted(k for k in m_w if m_w[k] != 1 and m_o[k] == 1)
    return gained, lost


def section4(results, total):
    """ETM value: with-move (Spacial Rend) vs no-ETM builds, win deltas and
    named flips. Plus the Aqua Tail vs Hydro Pump second-charge contrast."""
    out = ["## 4. ETM value: Spacial Rend vs no-ETM builds\n",
           f"All at hundo (15/15/15) vs the {total}-matchup pool. The ETM "
           f"swaps the no-ETM nuke (Draco Meteor or Hydro Pump) for Spacial "
           f"Rend, holding Aqua Tail as the cheap charge. The value is in "
           f"*which* matchups flip as much as the win totals.\n"]

    # Win-count comparison across all four movesets, per block.
    out.append("### Aggregate wins per moveset and block\n")
    out.append("| moveset | " +
               " | ".join(blk(b) for b in LEVEL_BLOCKS) + " |")
    out.append("| --- | " + " | ".join("---" for _ in LEVEL_BLOCKS) + " |")
    for ms_label, _, _ in MOVESETS:
        cells = [str(wins_in(results, HUNDO, ms_label, b))
                 for b in LEVEL_BLOCKS]
        out.append(f"| {ms_label} | " + " | ".join(cells) + " |")

    # Named flips: Spacial Rend vs the no-ETM nuke, Aqua Tail common in both.
    for ms_with, ms_without, desc in [
            ('AT/SR', 'AT/Draco', 'Spacial Rend vs Draco Meteor (Aqua Tail '
             'as the other charge in both)'),
            ('AT/SR', 'AT/Hydro', 'Spacial Rend vs Hydro Pump (Aqua Tail as '
             'the other charge in both)')]:
        out.append(f"\n### {ms_with} vs {ms_without}\n")
        out.append(f"_{desc}._\n")
        for b in LEVEL_BLOCKS:
            gained, lost = flip_block(results, ms_with, ms_without, b)
            if not gained and not lost:
                out.append(f"\n**{blk(b)}**: no matchups flip.")
                continue
            out.append(f"\n**{blk(b)}**: +{len(gained)} gained, "
                       f"-{len(lost)} lost by taking {ms_with}:\n")
            if gained:
                out.append("- GAINED (" + ms_with + " wins, " + ms_without +
                           " does not): " +
                           ", ".join(f"{o} {fmt_sh(s)}" for o, s in gained))
            if lost:
                out.append("- LOST (" + ms_without + " wins, " + ms_with +
                           " does not): " +
                           ", ".join(f"{o} {fmt_sh(s)}" for o, s in lost))

    # Second charge: cheap Aqua Tail bait vs a second Hydro Pump nuke, SR fixed.
    out.append("\n### Second charge move: Aqua Tail vs Hydro Pump (SR fixed)\n")
    out.append("_Which opponents the cheap Aqua Tail bait slot turns relative "
               "to running Hydro Pump as a second nuke, with Spacial Rend the "
               "primary nuke in both._\n")
    for b in LEVEL_BLOCKS:
        gained, lost = flip_block(results, 'AT/SR', 'Hydro/SR', b)
        if not gained and not lost:
            out.append(f"\n**{blk(b)}**: no matchups flip.")
            continue
        out.append(f"\n**{blk(b)}**: Aqua Tail vs Hydro Pump: "
                   f"+{len(gained)} / -{len(lost)}:\n")
        if gained:
            out.append("- Aqua Tail GAINS: " +
                       ", ".join(f"{o} {fmt_sh(s)}" for o, s in gained))
        if lost:
            out.append("- Aqua Tail LOSES (Hydro Pump holds): " +
                       ", ".join(f"{o} {fmt_sh(s)}" for o, s in lost))
    return "\n".join(out) + "\n"


def main():
    opponents = load_opponents()
    results = run_sweep(opponents)
    total = len(opponents) * len(SHIELDS)

    header = (
        "# Palkia (Origin) Master League: ETM / IV / best-buddy deep dive\n\n"
        f"Focal: **{FOCAL_SPECIES}** vs the PvPoke Master top-60 "
        f"(`{POOL_FILE}`), all opponents hundo (15/15/15). Scores are "
        "pvpoke 1v1 battle ratings; a win is score > opponent score. In "
        "Master the CP cap never binds, so **regular = L50.0** and "
        "**best-buddy = L51.0** are pure level steps on either side.\n\n"
        "Generated by `scripts/palkia_origin_etm_analysis.py`.\n")

    body = "\n".join([
        header,
        section1(results, total),
        section2(results, total),
        section3(results),
        section4(results, total),
    ])

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, 'w') as f:
        f.write(body)
    print(f"\nWrote {OUT_MD}")


if __name__ == '__main__':
    main()
