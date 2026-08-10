"""Differential test: the numba JIT DP kernels must agree with the pure-Python loops.

``src/gopvpsim/battle.py`` forks at two module-level globals read at call
time -- ``_NEAR_KO_DP_JIT`` (battle.py:1395) and ``_CALC_TTL_JIT``
(battle.py:451).  When numba imports cleanly they hold the compiled kernels
from ``_dp_jit.py``; when it does not, a bare ``except Exception`` sets both
to ``None`` and the engine runs equivalent pure-Python loops.  Nothing
compared the two halves, and ``sweep_cache.engine_hash()`` *cannot* see the
difference -- the source bytes are identical either way -- so a divergence
would silently mix JIT-computed and Python-computed columns into the same
warm cache (2026-08-09 test-suite review, blind-spots E1/E2).

Because both globals are read at call time, ``monkeypatch.setattr`` flips the
implementation in-process: no reimport, no subprocess, no uninstalling numba.

DELIBERATELY a pure differential: this file asserts ``jit == python`` and
NOTHING about the values themselves.  Expected scores and charged-move logs
live in ``tests/test_battle.py``'s oracle corpus; duplicating them here would
create a second fixture set to re-bless on every legitimate engine change.
"""
import pytest

from gopvpsim import battle
from gopvpsim.battle import BattlePokemon, pvpoke_dp, simulate


pytestmark = pytest.mark.skipif(
    battle._NEAR_KO_DP_JIT is None or battle._CALC_TTL_JIT is None,
    reason="numba not installed (the [perf] extra); with no JIT both branches "
           "are the same code, so JIT/Python parity is vacuous",
)


# (species, fast id, charged ids, shadow). Movesets are spelled out rather
# than pulled from get_default_moveset() on purpose: PvPoke's rankings drift
# upstream, and a fixture that silently re-aims itself would quietly change
# which kernel branches this differential covers.
SPECS = {
    'medicham':   ('Medicham',   'PSYCHO_CUT',     ['DYNAMIC_PUNCH', 'PSYCHIC'],       False),
    'azumarill':  ('Azumarill',  'BUBBLE',         ['ICE_BEAM', 'HYDRO_PUMP'],         False),
    'lucario':    ('Lucario',    'COUNTER',        ['POWER_UP_PUNCH', 'SHADOW_BALL'],  False),
    'registeel':  ('Registeel',  'LOCK_ON',        ['FOCUS_BLAST', 'FLASH_CANNON'],    False),
    'registeelZ': ('Registeel',  'LOCK_ON',        ['FOCUS_BLAST', 'ZAP_CANNON'],      False),
    'lurantis':   ('Lurantis',   'FURY_CUTTER',    ['LEAF_BLADE', 'SUPER_POWER'],      False),
    'skarmory':   ('Skarmory',   'AIR_SLASH',      ['SKY_ATTACK', 'BRAVE_BIRD'],       False),
    'nidoqueen':  ('Nidoqueen',  'POISON_JAB',     ['POISON_FANG', 'EARTH_POWER'],     False),
    'swampert':   ('Swampert',   'MUD_SHOT',       ['HYDRO_CANNON', 'EARTHQUAKE'],     False),
    'buzzwoleS':  ('Buzzwole',   'COUNTER',        ['FELL_STINGER', 'SUPER_POWER'],    True),
    'oinkologne': ('Oinkologne', 'TACKLE',         ['BODY_SLAM', 'DIG'],               False),
    'arcanine':   ('Arcanine',   'SNARL',          ['WILD_CHARGE', 'CRUNCH'],          False),
    'bastiodon':  ('Bastiodon',  'SMACK_DOWN',     ['STONE_EDGE', 'FLAMETHROWER'],     False),
    'venusaur':   ('Venusaur',   'VINE_WHIP',      ['FRENZY_PLANT', 'SLUDGE_BOMB'],    False),
    'annihilape': ('Annihilape', 'COUNTER',        ['RAGE_FIST', 'SHADOW_BALL'],       False),
    'skeledirge': ('Skeledirge', 'INCINERATE',     ['SHADOW_BALL', 'DISARMING_VOICE'], False),
    'talonflame': ('Talonflame', 'INCINERATE',     ['BRAVE_BIRD', 'FLAME_CHARGE'],     False),
    'lickitung':  ('Lickitung',  'LICK',           ['BODY_SLAM', 'POWER_WHIP'],        False),
    'gfisk':      ('Stunfisk (Galarian)', 'MUD_SHOT', ['ROCK_SLIDE', 'EARTHQUAKE'],    False),
    'mandibuzz':  ('Mandibuzz',  'SNARL',          ['AERIAL_ACE', 'FOUL_PLAY'],        False),
    'sableyeS':   ('Sableye',    'SHADOW_CLAW',    ['FOUL_PLAY', 'POWER_GEM'],         True),
    'corviknight':('Corviknight','SAND_ATTACK',    ['SKY_ATTACK', 'IRON_HEAD'],        False),
    'machamp':    ('Machamp',    'COUNTER',        ['CROSS_CHOP', 'ROCK_SLIDE'],       False),
    'gyarados':   ('Gyarados',   'DRAGON_BREATH',  ['AQUA_TAIL', 'CRUNCH'],            False),
    'clodsire':   ('Clodsire',   'MUD_SHOT',       ['STONE_EDGE', 'MEGAHORN'],         False),
    'toxapex':    ('Toxapex',    'POISON_JAB',     ['SLUDGE_WAVE', 'BRINE'],           False),
    'cresselia':  ('Cresselia',  'PSYCHO_CUT',     ['GRASS_KNOT', 'MOONBLAST'],        False),
    'charizard':  ('Charizard',  'FIRE_SPIN',      ['BLAST_BURN', 'DRAGON_CLAW'],      False),
}

# (league, p0 key, p1 key). Chosen to reach the branches where the two
# implementations could most easily drift apart:
#   * SUPER_POWER / WILD_CHARGE / BRAVE_BIRD / RAGE_FIST are self-DEBUFFERS,
#     exercising the has_debuf tiebreak field the kernel threads back out and
#     the phase-1 dedup that compares it;
#   * POWER_UP_PUNCH / POISON_FANG are chance-1 self-buff / opponent-debuff
#     moves, so the DP's 9-row per-atk-stage damage tables (_dp_jit.py:191-196)
#     get indexed off rows other than the root stage 4;
#   * two shadow pairs stack the shadow atk/def multipliers on top of that;
#   * LOCK_ON / SAND_ATTACK give 1-turn fast moves and huge charged moves, the
#     regime where the DP's fast-move-farming arm dominates.
#
# MEASURED COVERAGE, because "reaches" is not "discriminates" and the
# difference matters when someone leans on this file. Over these 135 cells the
# kernel is entered 2,430 times, with cm_buff_delta nonzero on 371 and
# root_atk_stage != 0 on 51 -- the stage inputs genuinely arrive. But only
# FOUR of the eight fields the kernel threads back out are observable through
# simulate(): found, first, max_idx and has_debuf. Perturbing any of the other
# four (debuf_count, f_turn, f_hp, f_sh) leaves all 135 cells identical, and
# so does making the kernel ignore the per-atk-stage rows outright
# (`cm_dmgs_stage[stage_row_idx, n]` -> `[root_atk_stage + 4, n]`, verified
# 2026-08-09). The stage-table indexing is EXECUTED here but NOT
# differentially covered: no matchup in this grid has a DP plan whose chosen
# answer depends on a mid-plan stage change. Closing that needs a pair whose
# two charged moves differ in damage ORDER across a stage boundary; it is a
# known gap, not a covered case. What this file does discriminate sharply --
# proven by mutation on both halves of the fork -- is near-KO energy
# accounting, shield chip, the pure-Python DP iteration cap, the TTL kernel's
# KO threshold, and the overflow-sentinel reset.
PAIRS = [
    ('great', 'medicham',   'azumarill'),
    ('great', 'lucario',    'registeel'),
    ('great', 'lurantis',   'skarmory'),
    ('great', 'nidoqueen',  'swampert'),
    ('great', 'buzzwoleS',  'oinkologne'),
    ('great', 'bastiodon',  'venusaur'),
    ('great', 'annihilape', 'skeledirge'),
    ('great', 'talonflame', 'medicham'),
    ('great', 'lickitung',  'gfisk'),
    ('great', 'mandibuzz',  'sableyeS'),
    ('great', 'corviknight', 'clodsire'),
    ('great', 'toxapex',    'machamp'),
    ('great', 'gyarados',   'cresselia'),
    ('ultra', 'arcanine',   'registeelZ'),
    ('ultra', 'charizard',  'swampert'),
]

MATCHUPS = [(f'{p0}-vs-{p1}', league, SPECS[p0], SPECS[p1])
            for league, p0, p1 in PAIRS]

SHIELD_CELLS = [(a, b) for a in (0, 1, 2) for b in (0, 1, 2)]


def _build(spec, league, shields):
    """Build a FRESH BattlePokemon from the real gamemaster.

    Freshness is load-bearing: ``_dp_cache`` (battle.py:2304) and
    ``_cached_charged_dmgs_np`` (battle.py:2150) are per-instance, so a
    reused object would carry a cache built under the other code path.
    """
    from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS
    from gopvpsim.moves import get_moves

    species, fast_id, charged_ids, shadow = spec
    pk = Pokemon.at_best_level(species, 15, 15, 15, league=league, shadow=shadow)
    fast_moves, charged_moves = get_moves()
    fm = dict(fast_moves[fast_id])
    cms = [dict(charged_moves[cid]) for cid in charged_ids]
    return BattlePokemon.from_pokemon(pk, fm, cms, shields=shields,
                                      league_cp=LEAGUE_CAPS[league])


def _signature(matchup, cell):
    """Run one cell on freshly-built mons; return a comparable result tuple."""
    _label, league, spec0, spec1 = matchup
    s0, s1 = cell
    p0 = _build(spec0, league, s0)
    p1 = _build(spec1, league, s1)
    # pvpoke_dp on BOTH sides: that is what the sweep worker runs
    # (scripts/deep_dive_lib/sweep.py:88-92) and it is the ONLY policy that
    # reaches the near-KO DP kernel. simulate()'s default bait_with_cheapest
    # never enters it, which would make this differential vacuous.
    r = simulate(p0, p1, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp,
                 log=True)
    return (
        r.winner,
        r.pvpoke_score(0),
        r.pvpoke_score(1),
        r.turns,
        tuple(r.hp_remaining),
        tuple(r.energy_remaining),
        tuple(r.shields_remaining),
        tuple(r.timeline),
    )


def _all_signatures():
    return {(m[0], cell): _signature(m, cell)
            for m in MATCHUPS for cell in SHIELD_CELLS}


def test_jit_and_pure_python_agree_on_every_cell(monkeypatch):
    """135 cells (15 matchups x 9 shield combos), JIT vs pure-Python fallback.

    Includes the anti-vacuity guards the differential needs: a cell-count
    floor, plus counting shims proving BOTH kernels were actually entered on
    the JIT pass.  Without those, a refactor that stopped calling the JIT --
    or a trimmed MATCHUPS list -- would leave this file green and
    meaningless.  Floors are set far BELOW today's counts (measured 2,430
    near-KO DP and 6,821 TTL invocations over these 135 cells) so ordinary
    engine work does not churn them.
    """
    calls = {'dp': 0, 'ttl': 0}
    real_dp, real_ttl = battle._NEAR_KO_DP_JIT, battle._CALC_TTL_JIT

    def dp_shim(*a):
        calls['dp'] += 1
        return real_dp(*a)

    def ttl_shim(*a):
        calls['ttl'] += 1
        return real_ttl(*a)

    monkeypatch.setattr(battle, '_NEAR_KO_DP_JIT', dp_shim)
    monkeypatch.setattr(battle, '_CALC_TTL_JIT', ttl_shim)
    jit = _all_signatures()

    assert len(jit) == len(MATCHUPS) * len(SHIELD_CELLS) >= 100, len(jit)
    assert calls['dp'] >= 200, \
        f"the near-KO DP kernel ran only {calls['dp']} times (was 2,430) -- " \
        "this differential is going vacuous"
    assert calls['ttl'] >= 500, \
        f"the turns-to-live kernel ran only {calls['ttl']} times (was 6,821) " \
        "-- this differential is going vacuous"

    # None on both globals is exactly the state the bare `except Exception`
    # at battle.py:32-40 leaves behind when numba is unavailable.
    monkeypatch.setattr(battle, '_NEAR_KO_DP_JIT', None)
    monkeypatch.setattr(battle, '_CALC_TTL_JIT', None)
    pure = _all_signatures()

    assert set(jit) == set(pure)
    mismatched = sorted(k for k in jit if jit[k] != pure[k])
    assert not mismatched, (
        f"{len(mismatched)}/{len(jit)} cells diverge between the numba kernels "
        f"and the pure-Python loops; first: {mismatched[0]}\n"
        f"  jit:    {jit[mismatched[0]]}\n"
        f"  python: {pure[mismatched[0]]}"
    )


def test_near_ko_dp_overflow_sentinel_falls_back_cleanly(monkeypatch):
    """The queue-overflow backstop (battle.py:1420-1432) must be a no-op path.

    ``_near_ko_dp_jit`` returns ``iters = -1`` when its bounded state queue
    overflows and non-dominated states were dropped; battle.py then resets
    ``found``/``final_state``/``iters`` and re-runs the unbounded Python loop.
    The comment there calls that branch what makes JIT/Python parity
    "structural rather than probabilistic" -- and at QUEUE_CAP=1024 against a
    ~50-state steady state it never fires in practice, so it is dead-branch
    rot bait: the hand-wired reset could be dropped by a refactor with nothing
    failing.  Forcing the sentinel here keeps it exercised.

    ``_CALC_TTL_JIT`` stays LIVE so this isolates the near-KO DP fallback.
    """
    baseline = _all_signatures()

    # The iters=-1 sentinel, in the 9-tuple shape battle.py:1400-1418 unpacks.
    # found=True plus a plausible-looking state is deliberate: the payload has
    # to be GARBAGE-but-well-typed so that dropping the reset at :1424-1427
    # actually changes the answer.  A found=False sentinel would sail through
    # a broken reset unnoticed.
    monkeypatch.setattr(battle, '_NEAR_KO_DP_JIT',
                        lambda *a: (True, 0, 0, 1, 0, 1, 0.0, 0, -1))
    fell_back = _all_signatures()

    mismatched = sorted(k for k in baseline if baseline[k] != fell_back[k])
    assert not mismatched, (
        f"{len(mismatched)}/{len(baseline)} cells diverge when the near-KO DP "
        f"kernel signals queue overflow; first: {mismatched[0]}\n"
        f"  jit:      {baseline[mismatched[0]]}\n"
        f"  fallback: {fell_back[mismatched[0]]}"
    )
