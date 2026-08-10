"""One battle-pair construction for both dive workers (D10).

DRY review 2026-08-05 entry 12 / June review D10: ``_sweep_worker`` and
``deep_dive_slayer.slayer_iter_worker`` carried near-clone ~20-line blocks
that built the (focal, opponent) BattlePokemon pair -- kept in sync only by
parallel editing, which is exactly how the pre-S1 "workers never wired up
form changes" bug survived. They now share
``deep_dive_lib.sweep.build_battle_pair``; the workers themselves stay
separate (they iterate different grids -- the review's do-not-merge list).

These tests pin what the shared core must preserve:

* the pair is built the way the OLD inline code built it (same stats, same
  shadow flag, same form-change state, same private move dicts),
* the focal energy-lead reaches the mon and the opponent side stays at 0,
* move dicts are PRIVATE per BattlePokemon (review section G, invariant 1),
* ``scripts/profile_slayer.py`` runs on the same core and forwards
  ``mechanics`` (its benchmark used to measure 'legacy' regardless).
"""
import sys
from pathlib import Path

from tests.conftest import load_deep_dive

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'src'))

deep_dive = load_deep_dive()

import profile_slayer  # noqa: E402  (scripts/ is on sys.path after the load)
from deep_dive_lib.sweep import BattleSide, build_battle_pair  # noqa: E402

from gopvpsim.battle import BattlePokemon  # noqa: E402
from gopvpsim.data import load_gamemaster  # noqa: E402
from gopvpsim.moves import parse_types  # noqa: E402
from gopvpsim.formchange import attach_form_change  # noqa: E402
from gopvpsim.moves import get_moves  # noqa: E402
from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS  # noqa: E402

LEAGUE = 'great'
LEAGUE_CP = LEAGUE_CAPS[LEAGUE]
# A form-change species on BOTH sides: the alt-form state is the part the
# duplicated blocks were most likely to drift on.
FOCAL = 'Aegislash (Shield)'
FOCAL_FAST = 'AEGISLASH_CHARGE_PSYCHO_CUT'
FOCAL_CHARGED = ['SHADOW_BALL', 'GYRO_BALL']
OPP = 'Azumarill'
OPP_FAST = 'BUBBLE'
OPP_CHARGED = ['ICE_BEAM', 'PLAY_ROUGH']


def _mon(species):
    gm = load_gamemaster()
    return next(m for m in gm['pokemon'] if m['speciesName'] == species)


def _side(species, fast_id, charged_ids, ivs, shadow=False,
          initial_energy=0):
    fast_db, charged_db = get_moves()
    mon = _mon(species)
    a, d, s = ivs
    pkm = Pokemon.at_best_level(species, a, d, s, league=LEAGUE,
                                shadow=shadow)
    return BattleSide(species, parse_types(mon), pkm.atk, pkm.def_, pkm.hp,
                      shadow, dict(fast_db[fast_id]),
                      [dict(charged_db[c]) for c in charged_ids],
                      mon, ivs, pkm.level, initial_energy)


def _legacy_build(side):
    """The construction the workers open-coded before D10, verbatim."""
    bp = BattlePokemon(
        species=side.species, types=side.types,
        atk=side.atk, def_=side.def_, max_hp=side.hp,
        shadow=side.shadow,
        fast_move=dict(side.fm_template),
        charged_moves=[dict(cm) for cm in side.cms_template],
    )
    bp.initial_energy = side.initial_energy
    attach_form_change(bp, side.mon, *side.ivs, side.level,
                       LEAGUE_CP, side.shadow)
    return bp


def _snapshot(bp):
    fc = getattr(bp, '_form_change', None)
    return {
        'species': bp.species, 'types': bp.types,
        'atk': bp.atk, 'def_': bp.def_, 'max_hp': bp.max_hp,
        'shadow': bp.shadow,
        'initial_energy': bp.initial_energy,
        'fast_move': bp.fast_move,
        'charged_moves': bp.charged_moves,
        'has_form_change': fc is not None,
        'form_effect': getattr(fc, 'effect', None),
        'disguise': getattr(bp, '_form_disguise_active', False),
        'initial_atk_stage': bp.initial_atk_stage,
        'initial_def_stage': bp.initial_def_stage,
    }


def test_pair_matches_the_old_inline_construction():
    focal = _side(FOCAL, FOCAL_FAST, FOCAL_CHARGED, (4, 14, 15))
    opp = _side(OPP, OPP_FAST, OPP_CHARGED, (4, 15, 13))

    bp0, bp1 = build_battle_pair(focal, opp, LEAGUE_CP)

    assert _snapshot(bp0) == _snapshot(_legacy_build(focal))
    assert _snapshot(bp1) == _snapshot(_legacy_build(opp))
    # The focal really is a form-change mon, so the assertion above is
    # comparing something (a no-form species would pass it vacuously).
    assert _snapshot(bp0)['has_form_change'] is True


def test_shadow_flag_and_energy_lead_land_on_the_right_side():
    focal = _side(FOCAL, FOCAL_FAST, FOCAL_CHARGED, (0, 15, 15),
                  initial_energy=17)
    opp = _side(OPP, OPP_FAST, OPP_CHARGED, (0, 15, 15), shadow=True)

    bp0, bp1 = build_battle_pair(focal, opp, LEAGUE_CP)

    assert bp0.initial_energy == 17
    assert bp1.initial_energy == 0     # opponent always starts at 0
    assert bp0.shadow is False
    assert bp1.shadow is True


def test_move_dicts_are_private_per_mon():
    """Invariant 1: each BattlePokemon owns its move dicts. Sharing them
    would let one mon's derived flags/turn counts leak into the other."""
    focal = _side(FOCAL, FOCAL_FAST, FOCAL_CHARGED, (4, 14, 15))
    # Same templates on both sides -- the mirror case the slayer worker runs.
    bp0, bp1 = build_battle_pair(focal, focal, LEAGUE_CP)

    assert bp0.fast_move is not focal.fm_template
    assert bp1.fast_move is not focal.fm_template
    assert bp0.fast_move is not bp1.fast_move
    for cm0, cm1, tmpl in zip(bp0.charged_moves, bp1.charged_moves,
                              focal.cms_template):
        assert cm0 is not tmpl and cm1 is not tmpl and cm0 is not cm1


def test_profile_slayer_runs_on_the_shared_core_and_forwards_mechanics(
        monkeypatch):
    """The benchmark used to call simulate() with no ``mechanics=``, so it
    measured 'legacy' whatever was asked for."""
    seen = []

    class _FakeResult:
        pass

    def _fake_simulate(p0, p1, **kwargs):
        assert isinstance(p0, BattlePokemon) and isinstance(p1, BattlePokemon)
        seen.append(kwargs.get('mechanics'))
        return _FakeResult()

    monkeypatch.setattr(profile_slayer, 'simulate', _fake_simulate)

    inputs = profile_slayer.build_inputs(2, 2)
    n = profile_slayer.run_sims(*inputs, mechanics='new')

    assert n == len(seen) > 0
    assert all(m == 'new' for m in seen), seen
