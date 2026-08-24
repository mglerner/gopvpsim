"""Signature-dedup soundness for Cramorant (2026-08-24 port review).

The review found the vs-Cramorant movable_axes widening had zero
coverage: a prey-holding Cramorant's Gulp Missile debuffs the OTHER
side's stat stages (-1 def from Arrokuda, -2 atk from Pikachu), so a
focal facing a Cramorant opponent must carry the FULL stage range for
both axes in its dedup signature. Without the widening, two focal IV
profiles that share stage-0 damages but differ post-debuff would be
MERGED and fight different battles under one representative sim.

FAILING-FIRST RECORD: with `_extra_charged_moves` returning [] (the
pre-fix state: missiles appeared in no form's move list), the
vs-Cramorant assertions below fail -- the axes stay unmovable.
"""
import sys
from pathlib import Path

from tests.conftest import load_deep_dive

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

deep_dive = load_deep_dive()

import deep_dive_signature as sig  # noqa: E402

from gopvpsim.moves import get_moves, parse_types  # noqa: E402
from gopvpsim.pokemon import Pokemon, get_pokemon_entry  # noqa: E402


def _opp_entry(species, fast_id, charged_ids, ivs=(5, 15, 15)):
    """Build the opp_cache-shaped dict build_opp_side consumes."""
    fm, cm = get_moves()
    p = Pokemon.at_best_level(species, *ivs, league='great')
    mon = get_pokemon_entry(species)
    return {
        'mon': mon,
        'types': tuple(parse_types(mon)),
        'fm': dict(fm[fast_id]),
        'cms': [dict(cm[c]) for c in charged_ids],
        'atk': p.atk,
        'def_': p.def_,
        'ivs': ivs,
        'level': p.level,
        'shadow': False,
    }


def _tinkaton_focal_side():
    """A plain no-buff focal side (Tinkaton stats, moves without buffs)."""
    fm, cm = get_moves()
    p = Pokemon.at_best_level('Tinkaton', 5, 15, 15, league='great')
    mon = get_pokemon_entry('Tinkaton')
    profile = [(None, p.atk, p.def_, p.hp, 5, 15, 15, p.level)]
    # THUNDER_SHOCK + FLASH_CANNON: no buffs on either, so any movability
    # must come from the OPPONENT side.
    return sig.build_focal_side(mon, tuple(parse_types(mon)),
                                dict(fm['THUNDER_SHOCK']),
                                [dict(cm['FLASH_CANNON'])],
                                profile, 1500, False)


def test_extra_charged_moves_registry():
    cram = get_pokemon_entry('Cramorant')
    ids = sorted(m['moveId'] for m in sig._extra_charged_moves(cram))
    assert ids == ['GULP_MISSILE_ARROKUDA', 'GULP_MISSILE_PIKACHU']
    assert sig._extra_charged_moves(get_pokemon_entry('Azumarill')) == []
    # Mewtwo-mega-style entries (extraChargedMoves but no formChange) stay
    # empty: their pools are inert in PvPoke too.
    fake = {'extraChargedMoves': ['GULP_MISSILE_ARROKUDA']}
    assert sig._extra_charged_moves(fake) == []


def test_vs_cramorant_marks_both_focal_axes_movable():
    """Arrokuda [0,-1] (opponent-target) moves the focal's DEF axis;
    Pikachu [-2,0] moves the focal's ATK axis. Both missiles ride in the
    Cramorant opponent's alt-form move lists, so movable_axes must widen
    both focal axes -- and must NOT widen them vs a plain opponent with
    the same moveset shape (positive control)."""
    focal = _tinkaton_focal_side()
    cram_side = sig.build_opp_side(
        _opp_entry('Cramorant', 'PECK', ['DIVE', 'FLY']), 1500)
    atk_mov, def_mov = sig.movable_axes(focal, cram_side)
    assert atk_mov is True and def_mov is True, (
        'vs-Cramorant focal axes must be movable (Gulp Missile debuffs)')
    # Positive control: same check vs a buff-free plain opponent.
    plain_side = sig.build_opp_side(
        _opp_entry('Lickitung', 'LICK', ['BODY_SLAM']), 1500)
    atk_mov, def_mov = sig.movable_axes(focal, plain_side)
    assert atk_mov is False and def_mov is False, (
        'control drifted: the plain opponent must not widen the axes '
        '(a buff crept into its moveset -- pick another control)')


def test_cramorant_opp_side_enumerates_all_prey_forms():
    """build_opp_side must emit a form dict for EVERY alt form (Gulping
    AND Gorging) -- the Pikachu missile with its -2 atk debuff rides only
    on the Gorging form, so dropping forms[2] silently loses the atk-axis
    widening."""
    cram_side = sig.build_opp_side(
        _opp_entry('Cramorant', 'PECK', ['DIVE', 'FLY']), 1500)
    missiles_per_form = [
        sorted(m['moveId'] for m in f['charged']
               if str(m.get('moveId', '')).startswith('GULP_MISSILE'))
        for f in cram_side['forms']]
    # forms[0] is the base scalar form (no extras appended there); every
    # alt form carries both registry missiles.
    assert len(cram_side['forms']) >= 3
    for got in missiles_per_form[1:]:
        assert got == ['GULP_MISSILE_ARROKUDA', 'GULP_MISSILE_PIKACHU']
