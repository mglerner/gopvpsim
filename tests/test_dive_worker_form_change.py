"""Worker-equivalence tests for form-change plumbing (arc S1, 2026-06-10).

The deep-dive sweep/slayer workers construct BattlePokemon from raw
effective stats and historically never wired up form-change state, so
every Aegislash/Mimikyu/Morpeko dive simmed without form mechanics
(TODO "Deep-dive workers never wire up form changes"). These tests pin
the fix: worker-path sims of Aegislash (Shield) must produce the same
scores as direct BattlePokemon.from_pokemon sims of the identical
matchups (the oracle-verified path), on both the focal and opponent
side.
"""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Load deep_dive.py as a module (it's a script, not a package). This
# also imports deep_dive_slayer and applies the compute_iv_metadata
# injection (same pattern as test_slayer_smoke.py).
DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"
_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)

import deep_dive_slayer  # noqa: E402  (importable after deep_dive's sys.path insert)

from gopvpsim.battle import BattlePokemon, simulate, pvpoke_dp  # noqa: E402
from gopvpsim.data import load_gamemaster, parse_types  # noqa: E402
from gopvpsim.moves import get_moves  # noqa: E402
from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS  # noqa: E402


AEGI_SPECIES = 'Aegislash (Shield)'
AEGI_FAST = 'AEGISLASH_CHARGE_PSYCHO_CUT'
AEGI_CHARGED = ['SHADOW_BALL', 'GYRO_BALL']
AZU_MOVESET = ('BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'])
LEAGUE = 'great'
SCENARIOS = [(0, 0), (1, 1), (2, 2)]


def _reference_score(focal_ivs, shields_focal, shields_opp,
                     opp_species, opp_moveset, opp_ivs):
    """Direct from_pokemon sim — the oracle-verified reference path."""
    a, d, s = focal_ivs
    bp0 = deep_dive.make_battle_pokemon(
        AEGI_SPECIES, AEGI_FAST, AEGI_CHARGED, LEAGUE, shields_focal,
        a, d, s)
    oa, od, os_ = opp_ivs
    bp1 = deep_dive.make_battle_pokemon(
        opp_species, opp_moveset[0], opp_moveset[1], LEAGUE, shields_opp,
        oa, od, os_)
    result = simulate(bp0, bp1,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp)
    return result.pvpoke_score(0)


def _opp_cache_entry(species, fast_id, charged_ids, ivs):
    """Build an opp_cache dict the way iv_sweep does."""
    fast_db, charged_db = get_moves()
    gm = load_gamemaster()
    mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
    a, d, s = ivs
    pkm = Pokemon.at_best_level(species, a, d, s, league=LEAGUE)
    return {
        'species': species, 'types': parse_types(mon),
        'atk': pkm.atk, 'def_': pkm.def_, 'hp': pkm.hp,
        'fm': dict(fast_db[fast_id]),
        'cms': [dict(charged_db[c]) for c in charged_ids],
        'shadow': False,
        'mon': mon, 'ivs': ivs, 'level': pkm.level,
    }


def _focal_profile(ivs):
    """Build a sweep-worker profile tuple for one Aegislash IV spread."""
    a, d, s = ivs
    pkm = Pokemon.at_best_level(AEGI_SPECIES, a, d, s, league=LEAGUE)
    pk = (round(pkm.atk, 4), round(pkm.def_, 4), int(pkm.hp), a, d, s,
          pkm.level)
    return (pk, pkm.atk, pkm.def_, pkm.hp, a, d, s, pkm.level)


def _init_sweep_worker_state(opp_cache, scenarios):
    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon']
                     if m['speciesName'] == AEGI_SPECIES)
    fast_db, charged_db = get_moves()
    deep_dive._sweep_worker_init(
        AEGI_SPECIES, parse_types(focal_mon),
        dict(fast_db[AEGI_FAST]),
        [dict(charged_db[c]) for c in AEGI_CHARGED],
        opp_cache, scenarios,
        focal_mon=focal_mon, league_cp=LEAGUE_CAPS[LEAGUE],
        focal_shadow=False)


def test_sweep_worker_matches_from_pokemon():
    """Sweep-worker scores == direct from_pokemon scores for Aegislash
    (Shield) IVs vs Azumarill AND vs Aegislash (Shield) as opponent
    (covers focal-side and opponent-side form-change wiring)."""
    azu_ivs = (4, 15, 13)      # PvPoke GL default
    aegi_opp_ivs = (4, 14, 15)  # PvPoke GL default
    opp_cache = [
        _opp_cache_entry('Azumarill', AZU_MOVESET[0], AZU_MOVESET[1],
                         azu_ivs),
        _opp_cache_entry(AEGI_SPECIES, AEGI_FAST, AEGI_CHARGED,
                         aegi_opp_ivs),
    ]
    _init_sweep_worker_state(opp_cache, SCENARIOS)

    focal_iv_list = [(4, 14, 15), (0, 15, 15), (15, 15, 15)]
    chunk = [_focal_profile(ivs) for ivs in focal_iv_list]
    results, n_sims = deep_dive._sweep_worker(chunk)

    assert n_sims == len(focal_iv_list) * len(opp_cache) * len(SCENARIOS)

    opp_specs = [('Azumarill', AZU_MOVESET, azu_ivs),
                 (AEGI_SPECIES, (AEGI_FAST, AEGI_CHARGED), aegi_opp_ivs)]
    for ivs, prof in zip(focal_iv_list, chunk):
        per_opp = results[prof[0]]
        for oi, (opp_species, opp_moveset, opp_ivs) in enumerate(opp_specs):
            for si, (s_focal, s_opp) in enumerate(SCENARIOS):
                expected = _reference_score(ivs, s_focal, s_opp,
                                            opp_species, opp_moveset,
                                            opp_ivs)
                got = per_opp[(si, oi)]
                assert got == expected, (
                    f"IV {ivs} vs {opp_species} {s_focal}v{s_opp}: "
                    f"worker={got}, from_pokemon={expected}")


def test_sweep_worker_pins_pvpoke_oracle_score():
    """The sweep worker reproduces the PvPoke-harness-verified 0v0
    score (773) for Aegislash (Shield) 4/14/15 vs Azumarill 4/15/13 —
    the same cell test_aegislash_vs_azumarill_form_change pins on the
    from_pokemon path. A no-form-change construction (the pre-S1
    worker behavior) must NOT reproduce it, proving the wiring is what
    changed the dive results."""
    opp_cache = [_opp_cache_entry('Azumarill', AZU_MOVESET[0],
                                  AZU_MOVESET[1], (4, 15, 13))]
    _init_sweep_worker_state(opp_cache, [(0, 0)])

    chunk = [_focal_profile((4, 14, 15))]
    results, _ = deep_dive._sweep_worker(chunk)
    score = results[chunk[0][0]][(0, 0)]
    assert round(score) == 773

    # Pre-S1 behavior: same stats, no form-change state attached.
    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon']
                     if m['speciesName'] == AEGI_SPECIES)
    fast_db, charged_db = get_moves()
    _, atk, def_, hp, *_rest = chunk[0]
    bp0 = BattlePokemon(
        species=AEGI_SPECIES, types=parse_types(focal_mon),
        atk=atk, def_=def_, max_hp=hp,
        fast_move=dict(fast_db[AEGI_FAST]),
        charged_moves=[dict(charged_db[c]) for c in AEGI_CHARGED],
        shields=0,
    )
    opp = opp_cache[0]
    bp1 = BattlePokemon(
        species=opp['species'], types=opp['types'],
        atk=opp['atk'], def_=opp['def_'], max_hp=opp['hp'],
        fast_move=dict(opp['fm']),
        charged_moves=[dict(cm) for cm in opp['cms']],
        shields=0,
    )
    result = simulate(bp0, bp1,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp)
    assert round(result.pvpoke_score(0)) != 773


def test_slayer_worker_matches_from_pokemon_mirror():
    """Slayer-iteration worker (Aegislash mirror) scores == direct
    from_pokemon mirror sims."""
    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon']
                     if m['speciesName'] == AEGI_SPECIES)
    fast_db, charged_db = get_moves()
    scenarios = [(1, 1), (0, 0)]
    deep_dive_slayer.slayer_worker_init(
        AEGI_SPECIES, parse_types(focal_mon),
        focal_mon['baseStats']['atk'], focal_mon['baseStats']['def'],
        focal_mon['baseStats']['hp'],
        LEAGUE_CAPS[LEAGUE], False,
        dict(fast_db[AEGI_FAST]),
        [dict(charged_db[c]) for c in AEGI_CHARGED],
        scenarios, focal_mon=focal_mon)

    focal_ivs = [(4, 14, 15), (15, 15, 15)]
    opp_ivs = (0, 15, 15)
    chunk = [_focal_profile(ivs) for ivs in focal_ivs]
    opp_prof = _focal_profile(opp_ivs)
    # slayer opponents: (opp_iv_idx, (atk, def, hp, a, d, s, lv))
    opponents = [(0, opp_prof[1:])]

    results = deep_dive_slayer.slayer_iter_worker((chunk, opponents))

    for ivs, prof in zip(focal_ivs, chunk):
        scores = results[(prof[0], 0)]
        for si, (s_focal, s_opp) in enumerate(scenarios):
            a, d, s = ivs
            bp0 = deep_dive.make_battle_pokemon(
                AEGI_SPECIES, AEGI_FAST, AEGI_CHARGED, LEAGUE, s_focal,
                a, d, s)
            bp1 = deep_dive.make_battle_pokemon(
                AEGI_SPECIES, AEGI_FAST, AEGI_CHARGED, LEAGUE, s_opp,
                *opp_ivs)
            res = simulate(bp0, bp1,
                           charged_policy_0=pvpoke_dp,
                           charged_policy_1=pvpoke_dp)
            expected = round(res.pvpoke_score(0))
            assert scores[si] == expected, (
                f"mirror IV {ivs} vs {opp_ivs} {s_focal}v{s_opp}: "
                f"worker={scores[si]}, from_pokemon={expected}")
