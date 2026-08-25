"""Cramorant form change + Gulp Missile (ported from pvpoke 78c64048a).

Mechanics under test (pvpoke.com writeup, 2026-08-21 "Cramorant Sims and
Rankings" + the commit):

- After Dive/Surf, Cramorant takes prey: Gulping (Arrokuda) at >50% of max
  HP, Gorging (Pikachu) at <=50%. Can't change prey while holding one.
- An UNSHIELDED, non-instant charged attack against a prey-holding
  Cramorant triggers Gulp Missile: an instant, unshieldable charged
  action dealing flat floor(0.15 * target_max_hp) + 1 (no stats, types,
  STAB, shadow, or stage multipliers), debuffing the target -1 def
  (Arrokuda) or -2 atk (Pikachu), then reverting Cramorant to base form.
- Gulp Missile fires even if the triggering attack KO'd Cramorant
  (ignoresFaint) -- a lethal missile then produces a simultaneous-KO draw.
- Gulp Missile does not break Mimikyu's disguise and never triggers an
  opposing Gulp Missile.

FAILING-FIRST RECORD (testing policy): against the pre-port tree
(HEAD 6a7e534), every test in this file dies in collection-to-setup with
``KeyError: 'variable'`` from formchange.build_form_change_state:204 --
base Cramorant's gamemaster ``alternativeFormId: "variable"`` was
unresolvable, so no Cramorant BattlePokemon could be constructed at all.

Oracle fixtures below were generated 2026-08-24 and verified cell-exact
(score + winner + chargedLog) against PvPoke's own engine via
scripts/pvpoke_trace.js at pvpoke 78c64048a -- 45/45 cells.
"""
import pytest

from gopvpsim.battle import BattlePokemon, pvpoke_dp, simulate, use_first_available
from gopvpsim.data import get_default_moveset
from gopvpsim.formchange import FormData, form_change_swapped_moves
from gopvpsim.moves import get_moves

from .test_battle import _extract_battle_log, _make_battle_pokemon


def _cramorant(fast, charged, shields, league='great', ivs=(5, 15, 15)):
    return _make_battle_pokemon('Cramorant', fast, charged,
                                league, shields, *ivs)


# ---------------------------------------------------------------------------
# Construction / config unit tests
# ---------------------------------------------------------------------------

def test_cramorant_three_form_config():
    """The 'variable' form change builds a 3-form config in the pinned
    order (base, Gulping, Gorging) -- battle.py's HP-conditional target
    resolution indexes into that order."""
    bp = _cramorant('PECK', ['DIVE', 'FLY'], 1)
    fc = bp._form_change
    assert [fd.species_id for fd in fc.forms] == [
        'cramorant', 'cramorant_gulping', 'cramorant_gorging']
    base, gulping, gorging = fc.forms
    assert base.trigger == 'charged_move'
    assert base.move_ids == ('DIVE', 'SURF')
    assert base.target_idx is None            # 'variable' -> resolved by HP
    for prey, missile in ((gulping, 'GULP_MISSILE_ARROKUDA'),
                          (gorging, 'GULP_MISSILE_PIKACHU')):
        assert prey.trigger == 'charged_move'
        assert prey.move_id == missile        # exit move IS the missile
        assert prey.target_idx == 0           # revert to base
    # All three forms share stats (only name/species_id/trigger differ).
    assert base.atk == gulping.atk == gorging.atk
    assert base.def_ == gulping.def_ == gorging.def_
    # Extra-charged registry holds per-instance COPIES of both missiles.
    assert sorted(bp._extra_charged) == ['GULP_MISSILE_ARROKUDA',
                                         'GULP_MISSILE_PIKACHU']
    _, all_charged = get_moves()
    for mid, m in bp._extra_charged.items():
        assert m == all_charged[mid]
        assert m is not all_charged[mid], (
            'missile dict aliases the global gamemaster dict -- battle '
            'mutation would cross-contaminate (same hazard as '
            '_swap_charged_move)')
    other = _cramorant('PECK', ['DIVE', 'FLY'], 1)
    assert (other._extra_charged['GULP_MISSILE_ARROKUDA']
            is not bp._extra_charged['GULP_MISSILE_ARROKUDA'])


def test_matches_move_semantics():
    """FormData.matches_move: ANY wildcard, exact id, and plural moveIDs
    membership (the three arms of PvPoke Battle.js:1609-1610)."""
    fd = FormData(species='X', species_id='x', types=('normal',), atk=1.0,
                  def_=1.0, fast_move={}, charged_moves=(),
                  trigger='charged_move', move_id=None,
                  native_stat_buffs=None, move_ids=('DIVE', 'SURF'))
    assert fd.matches_move('DIVE') and fd.matches_move('SURF')
    assert not fd.matches_move('FLY')
    any_fd = FormData(species='X', species_id='x', types=('normal',),
                      atk=1.0, def_=1.0, fast_move={}, charged_moves=(),
                      trigger='charged_move', move_id='ANY',
                      native_stat_buffs=None)
    assert any_fd.matches_move('WHATEVER')


def test_form_change_swapped_moves_includes_gulp_missiles():
    """Cache-migration contract: a moveset with Dive/Surf makes the battle
    read the Gulp Missile move entries (fired from the extra registry,
    never stored in the moveset)."""
    both = {'GULP_MISSILE_ARROKUDA', 'GULP_MISSILE_PIKACHU'}
    assert form_change_swapped_moves(['DIVE']) >= both
    assert form_change_swapped_moves(['SURF']) >= both
    # GENERATOR input: migrate_cache (the only production consumer) passes
    # one; the function iterates twice, so an unmaterialized argument made
    # the missile union silently dead (2026-08-24 review finding).
    assert form_change_swapped_moves(m for m in ['DIVE']) >= both
    assert form_change_swapped_moves(['ICE_BEAM']) == set()
    # Positive control: the pre-existing swap table still works.
    assert 'AURA_WHEEL_DARK' in form_change_swapped_moves(
        ['AURA_WHEEL_ELECTRIC'])


def test_default_moveset_and_none_padding():
    """Cramorant's PvPoke GL default is Peck / Dive + Fly. And the
    'none' second-charged-move padding pvpoke 78c64048a introduced in
    regenerated rankings (Unown is the only species today) is treated as
    absent, not as a move id."""
    assert get_default_moveset('Cramorant', 'great') == ('PECK', ['DIVE', 'FLY'])
    fast, charged = get_default_moveset('Unown', 'great')
    assert 'none' not in charged
    assert charged == ['STRUGGLE']


# ---------------------------------------------------------------------------
# Prey-pick HP boundary (strictly > 50% of max HP -> Gulping)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hp_at_dive,expected_form", [
    (64, 'cramorant_gulping'),   # 64/126 > 0.5 -> Arrokuda
    (63, 'cramorant_gorging'),   # exactly 50% is NOT >0.5 -> Pikachu
])
def test_prey_pick_hp_boundary(hp_at_dive, expected_form):
    """PvPoke Battle.js:1615: `hp / stats.hp > 0.5` is STRICT -- exactly
    half HP takes the Gorging (Pikachu) prey."""
    bp = _cramorant('PECK', ['DIVE', 'FLY'], 0)
    assert bp.max_hp == 126, 'IV/level drift broke the exact-half setup'
    # One-turn battle: Dive KOs a 1-HP dummy, the post-attack form change
    # still runs (PvPoke changes form regardless of the defender's faint),
    # then the faint check ends the fight with the prey form observable.
    dummy = BattlePokemon(
        species='Dummy', types=['normal'], atk=100.0, def_=100.0, max_hp=1,
        fast_move=dict(get_moves()[0]['COUNTER']),
        charged_moves=[dict(get_moves()[1]['ICE_BEAM'])], shields=0)
    bp.hp = hp_at_dive
    bp.energy = 40
    result = simulate(bp, dummy,
                      charged_policy_0=use_first_available,
                      charged_policy_1=lambda *a, **k: None)
    assert result.winner == 0
    assert bp._form_change.forms[bp._form_idx].species_id == expected_form


# ---------------------------------------------------------------------------
# Gulp Missile mechanics (crafted battles)
# ---------------------------------------------------------------------------

def test_gulp_missile_flat_damage_value():
    """floor(0.15 * target max HP) + 1, no multipliers: Registeel's
    Flying/Water-resisted, high-defense profile can't reduce it. Parsed
    from the live battle timeline of the oracle matchup below."""
    bp = _cramorant('PECK', ['DIVE', 'HYDRO_PUMP'], 0)
    reg = _make_battle_pokemon('Registeel', 'LOCK_ON',
                               ['FLASH_CANNON', 'FOCUS_BLAST'],
                               'great', 0, 15, 15, 15)
    result = simulate(bp, reg, charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp, log=True)
    expected = int(0.15 * reg.max_hp) + 1
    missile_lines = [ln for ln in result.timeline
                     if 'Gulp Missile' in ln and 'dmg' in ln]
    assert missile_lines, 'missile never fired in the fixture battle'
    assert f'→ {expected} dmg' in missile_lines[0], (
        f'expected flat {expected} = floor(0.15*{reg.max_hp})+1, '
        f'got: {missile_lines[0]}')


def test_gulp_missile_does_not_break_mimikyu_disguise():
    """'Gulp Missile can't be blocked (including by Mimikyu's disguise)':
    the instant tag skips the protect branch -- full flat damage through
    the disguise, and the disguise survives for the next real charged
    attack."""
    bp = _cramorant('PECK', ['DIVE', 'FLY'], 0)
    mimi = _make_battle_pokemon('Mimikyu', 'SHADOW_CLAW',
                                ['SHADOW_SNEAK', 'PLAY_ROUGH'],
                                'great', 0, 5, 13, 15)
    bp.change_form(mimi, 1)         # holding prey (Gulping)
    assert mimi._form_disguise_active
    result = simulate(bp, mimi,
                      charged_policy_0=lambda *a, **k: None,  # fast only
                      charged_policy_1=pvpoke_dp, log=True)
    missile_idx = next(i for i, ln in enumerate(result.timeline)
                       if 'Gulp Missile' in ln)
    expected = int(0.15 * mimi.max_hp) + 1
    assert f'→ {expected} dmg' in result.timeline[missile_idx], (
        'missile was reduced -- the disguise protect branch fired on an '
        'instant move')
    assert not any('disguise busted' in ln
                   for ln in result.timeline[:missile_idx + 1]), (
        'the missile busted the disguise; PvPoke Battle.js:1335 exempts '
        'instant moves')
    # Cramorant never throws a real charged move here (fast-only policy),
    # so the disguise must SURVIVE the whole battle -- the missile neither
    # busts nor consumes it.
    assert mimi._form_disguise_active is True


def test_gulp_missile_is_never_shielded_and_reverts_form():
    """Across a full shields-up fight: no Gulp Missile entry is ever
    shielded, and each missile is thrown from a prey form (the revert to
    base happens after the throw, so the log name carries the prey
    form)."""
    bp = _cramorant('PECK', ['DIVE', 'HYDRO_PUMP'], 2)
    reg = _make_battle_pokemon('Registeel', 'LOCK_ON',
                               ['FLASH_CANNON', 'FOCUS_BLAST'],
                               'great', 2, 15, 15, 15)
    result = simulate(bp, reg, charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp, log=True)
    log = _extract_battle_log(result)
    missiles = [e for e in log if 'Gulp Missile' in e]
    assert missiles, 'no missile fired in the 2v2 fixture'
    for entry in missiles:
        assert '(shielded)' not in entry
        assert entry.startswith(('Cramorant (Gulping):',
                                 'Cramorant (Gorging):'))


# ---------------------------------------------------------------------------
# Oracle fixtures -- cell-exact vs pvpoke_trace.js @ 78c64048a (2026-08-24)
# ---------------------------------------------------------------------------

_ORACLE_MATCHUPS = {
    # Gulping cycle + re-prey after revert (Gorging on the second Dive).
    'registeel': dict(
        p1=('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'], (5, 15, 15)),
        p2=('Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST'], (15, 15, 15))),
    # Gorging branch + ignoresFaint: Wild Charge KOs Cramorant, the
    # missile still fires from the grave (0v0/0v1/0v2 logs).
    'raichu_alolan': dict(
        p1=('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'], (5, 15, 15)),
        p2=('Raichu (Alolan)', 'VOLT_SWITCH', ['WILD_CHARGE', 'PSYCHIC'], (15, 15, 15))),
    # Mirror: usePriority forced true (equal atk), missile never triggers
    # a counter-missile, prey lock visible ('Cramorant (Gulping): Dive').
    'mirror': dict(
        p1=('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'], (5, 15, 15)),
        p2=('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'], (5, 15, 15))),
    # Dive-ASAP negative control: Fly's dpe/Dive's dpe >= 1.5 vs
    # Azumarill, so Cramorant correctly just spams Fly -- plus the 1v2
    # simultaneous-KO DRAW cell (lethal missile + lethal Ice Beam).
    'azumarill': dict(
        p1=('Cramorant', 'PECK', ['DIVE', 'FLY'], (5, 15, 15)),
        p2=('Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], (4, 15, 13))),
    # Surf build: exercises the replicated moveID typo semantics
    # (nonGulpMove degenerates to Surf itself; rule fires ~unconditionally).
    'surf_registeel': dict(
        p1=('Cramorant', 'WATER_GUN', ['SURF', 'FLY'], (5, 15, 15)),
        p2=('Registeel', 'LOCK_ON', ['FLASH_CANNON', 'FOCUS_BLAST'], (15, 15, 15))),
    # Mimikyu interplay: Dive busts the disguise normally (0v0), while the
    # missile fires THROUGH an intact disguise without busting it -- in 1v2
    # Mimikyu's post-missile Shadow Sneak still logs unbusted 'Mimikyu'.
    # Also carries a 1v0 simultaneous-KO draw.
    'mimikyu': dict(
        p1=('Cramorant', 'PECK', ['DIVE', 'HYDRO_PUMP'], (5, 15, 15)),
        p2=('Mimikyu', 'SHADOW_CLAW', ['SHADOW_SNEAK', 'PLAY_ROUGH'], (5, 13, 15))),
}

_ORACLE_CELLS = [
    # (matchup, s1, s2, p1_score, winner, chargedLog)
    ('registeel', 0, 0, 507, 0, ['Cramorant: Dive', 'Registeel: Focus Blast', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Registeel: Flash Cannon', 'Cramorant: Hydro Pump']),
    ('registeel', 0, 1, 332, 1, ['Cramorant: Dive', 'Registeel: Focus Blast', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Hydro Pump (shielded)', 'Registeel: Focus Blast']),
    ('registeel', 0, 2, 332, 1, ['Cramorant: Dive', 'Registeel: Focus Blast', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Hydro Pump (shielded)', 'Registeel: Focus Blast']),
    ('registeel', 1, 0, 702, 0, ['Cramorant: Dive', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Registeel: Flash Cannon (shielded)', 'Cramorant: Hydro Pump']),
    ('registeel', 1, 1, 674, 0, ['Cramorant: Dive', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Registeel: Flash Cannon (shielded)', 'Cramorant: Dive (shielded)', 'Cramorant (Gorging): Dive']),
    ('registeel', 1, 2, 464, 1, ['Cramorant: Dive', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Registeel: Flash Cannon (shielded)', 'Cramorant: Dive (shielded)', 'Cramorant (Gorging): Dive (shielded)', 'Registeel: Flash Cannon', 'Cramorant (Gorging): Gulp Missile (Pikachu)']),
    ('registeel', 2, 0, 702, 0, ['Cramorant: Dive', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Registeel: Flash Cannon (shielded)', 'Cramorant: Hydro Pump']),
    ('registeel', 2, 1, 674, 0, ['Cramorant: Dive', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Registeel: Flash Cannon (shielded)', 'Cramorant: Dive (shielded)', 'Cramorant (Gorging): Dive']),
    ('registeel', 2, 2, 654, 0, ['Cramorant: Dive', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Registeel: Flash Cannon (shielded)', 'Cramorant: Dive (shielded)', 'Registeel: Flash Cannon (shielded)', 'Cramorant (Gorging): Dive (shielded)', 'Cramorant (Gorging): Dive']),
    ('raichu_alolan', 0, 0, 378, 1, ['Cramorant: Dive', 'Raichu (Alolan): Wild Charge', 'Cramorant (Gorging): Gulp Missile (Pikachu)']),
    ('raichu_alolan', 0, 1, 177, 1, ['Cramorant: Dive (shielded)', 'Raichu (Alolan): Wild Charge', 'Cramorant (Gorging): Gulp Missile (Pikachu)']),
    ('raichu_alolan', 0, 2, 177, 1, ['Cramorant: Dive (shielded)', 'Raichu (Alolan): Wild Charge', 'Cramorant (Gorging): Gulp Missile (Pikachu)']),
    ('raichu_alolan', 1, 0, 336, 1, ['Cramorant: Dive']),
    ('raichu_alolan', 1, 1, 135, 1, ['Cramorant: Dive (shielded)']),
    ('raichu_alolan', 1, 2, 135, 1, ['Cramorant: Dive (shielded)']),
    ('raichu_alolan', 2, 0, 336, 1, ['Cramorant: Dive']),
    ('raichu_alolan', 2, 1, 135, 1, ['Cramorant: Dive (shielded)']),
    ('raichu_alolan', 2, 2, 135, 1, ['Cramorant: Dive (shielded)']),
    ('mirror', 0, 0, 626, 0, ['Cramorant: Dive', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
    ('mirror', 0, 1, 523, 0, ['Cramorant: Dive', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant (Gulping): Dive']),
    ('mirror', 0, 2, 523, 0, ['Cramorant: Dive', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant (Gulping): Dive']),
    ('mirror', 1, 0, 626, 0, ['Cramorant: Dive', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
    ('mirror', 1, 1, 619, 0, ['Cramorant: Dive', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant (Gulping): Dive (shielded)']),
    ('mirror', 1, 2, 619, 0, ['Cramorant: Dive', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant (Gulping): Dive (shielded)']),
    ('mirror', 2, 0, 626, 0, ['Cramorant: Dive', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
    ('mirror', 2, 1, 619, 0, ['Cramorant: Dive', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant (Gulping): Dive (shielded)']),
    ('mirror', 2, 2, 619, 0, ['Cramorant: Dive', 'Cramorant: Dive', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant (Gulping): Dive (shielded)']),
    ('azumarill', 0, 0, 489, 1, ['Cramorant: Fly', 'Azumarill: Ice Beam', 'Cramorant: Fly', 'Azumarill: Ice Beam']),
    ('azumarill', 0, 1, 345, 1, ['Cramorant: Fly (shielded)', 'Azumarill: Ice Beam', 'Cramorant: Fly', 'Azumarill: Ice Beam']),
    ('azumarill', 0, 2, 201, 1, ['Cramorant: Fly (shielded)', 'Azumarill: Ice Beam', 'Cramorant: Fly (shielded)', 'Azumarill: Ice Beam']),
    ('azumarill', 1, 0, 654, 0, ['Cramorant: Fly', 'Azumarill: Ice Beam (shielded)', 'Cramorant: Fly', 'Azumarill: Ice Beam']),
    ('azumarill', 1, 1, 638, 0, ['Cramorant: Fly (shielded)', 'Azumarill: Ice Beam (shielded)', 'Cramorant: Fly', 'Azumarill: Ice Beam', 'Cramorant: Fly']),
    ('azumarill', 1, 2, 500, None, ['Cramorant: Fly (shielded)', 'Azumarill: Ice Beam (shielded)', 'Cramorant: Fly (shielded)', 'Azumarill: Ice Beam', 'Cramorant: Fly', 'Cramorant: Dive', 'Azumarill: Ice Beam', 'Cramorant (Gorging): Gulp Missile (Pikachu)']),
    ('azumarill', 2, 0, 833, 0, ['Cramorant: Fly', 'Azumarill: Ice Beam (shielded)', 'Cramorant: Fly', 'Azumarill: Ice Beam (shielded)']),
    ('azumarill', 2, 1, 817, 0, ['Cramorant: Fly (shielded)', 'Azumarill: Ice Beam (shielded)', 'Cramorant: Fly', 'Azumarill: Play Rough (shielded)', 'Cramorant: Fly']),
    ('azumarill', 2, 2, 571, 0, ['Cramorant: Fly (shielded)', 'Azumarill: Ice Beam (shielded)', 'Cramorant: Fly (shielded)', 'Cramorant: Fly', 'Azumarill: Ice Beam (shielded)', 'Azumarill: Ice Beam', 'Cramorant: Dive']),
    ('surf_registeel', 0, 0, 507, 0, ['Cramorant: Surf', 'Registeel: Focus Blast', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Registeel: Flash Cannon', 'Cramorant: Surf']),
    ('surf_registeel', 0, 1, 507, 0, ['Cramorant: Surf (shielded)', 'Registeel: Focus Blast', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Registeel: Flash Cannon', 'Cramorant: Surf']),
    ('surf_registeel', 0, 2, 400, 1, ['Cramorant: Surf (shielded)', 'Registeel: Focus Blast', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Surf (shielded)', 'Registeel: Focus Blast', 'Cramorant (Gorging): Gulp Missile (Pikachu)']),
    ('surf_registeel', 1, 0, 702, 0, ['Registeel: Flash Cannon (shielded)', 'Cramorant: Surf', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Surf']),
    ('surf_registeel', 1, 1, 702, 0, ['Registeel: Flash Cannon (shielded)', 'Cramorant: Surf (shielded)', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Surf']),
    ('surf_registeel', 1, 2, 480, 1, ['Registeel: Flash Cannon (shielded)', 'Cramorant: Surf (shielded)', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Surf (shielded)', 'Registeel: Flash Cannon', 'Cramorant (Gorging): Gulp Missile (Pikachu)']),
    ('surf_registeel', 2, 0, 702, 0, ['Registeel: Flash Cannon (shielded)', 'Cramorant: Surf', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Surf']),
    ('surf_registeel', 2, 1, 702, 0, ['Registeel: Flash Cannon (shielded)', 'Cramorant: Surf (shielded)', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Surf']),
    ('surf_registeel', 2, 2, 638, 0, ['Registeel: Flash Cannon (shielded)', 'Cramorant: Surf (shielded)', 'Registeel: Flash Cannon', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Surf (shielded)', 'Registeel: Flash Cannon (shielded)', 'Cramorant (Gorging): Surf']),
    ('mimikyu', 0, 0, 515, 0, ['Cramorant: Dive', 'Mimikyu (Busted): Play Rough', 'Cramorant (Gulping): Gulp Missile (Arrokuda)', 'Cramorant: Dive']),
    ('mimikyu', 0, 1, 196, 1, ['Mimikyu: Play Rough', 'Cramorant: Dive (shielded)', 'Cramorant (Gorging): Dive']),
    ('mimikyu', 0, 2, 196, 1, ['Mimikyu: Play Rough', 'Cramorant: Dive (shielded)', 'Cramorant (Gorging): Dive (shielded)']),
    ('mimikyu', 1, 0, 500, None, ['Cramorant: Dive', 'Cramorant (Gulping): Dive', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Mimikyu (Busted): Shadow Sneak', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
    ('mimikyu', 1, 1, 322, 1, ['Mimikyu: Shadow Sneak (shielded)', 'Cramorant: Dive (shielded)', 'Cramorant (Gulping): Dive', 'Mimikyu (Busted): Shadow Sneak', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
    ('mimikyu', 1, 2, 313, 1, ['Mimikyu: Shadow Sneak (shielded)', 'Cramorant: Dive (shielded)', 'Cramorant (Gulping): Dive (shielded)', 'Mimikyu: Shadow Sneak', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
    ('mimikyu', 2, 0, 714, 0, ['Cramorant: Dive', 'Cramorant (Gulping): Dive', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Mimikyu (Busted): Shadow Sneak (shielded)']),
    ('mimikyu', 2, 1, 678, 0, ['Mimikyu: Shadow Sneak (shielded)', 'Cramorant: Dive (shielded)', 'Cramorant (Gulping): Dive', 'Cramorant (Gulping): Dive']),
    ('mimikyu', 2, 2, 443, 1, ['Mimikyu: Shadow Sneak (shielded)', 'Cramorant: Dive (shielded)', 'Cramorant (Gulping): Dive (shielded)', 'Cramorant (Gulping): Dive', 'Mimikyu (Busted): Shadow Sneak (shielded)', 'Mimikyu (Busted): Shadow Sneak', 'Cramorant (Gulping): Gulp Missile (Arrokuda)']),
]


@pytest.mark.integration
@pytest.mark.parametrize("matchup,s1,s2,p1_score,winner,expected_log",
                         _ORACLE_CELLS,
                         ids=[f"{m}-{a}v{b}" for m, a, b, *_ in _ORACLE_CELLS])
def test_cramorant_oracle(matchup, s1, s2, p1_score, winner, expected_log):
    spec = _ORACLE_MATCHUPS[matchup]
    sp1, f1, c1, iv1 = spec['p1']
    sp2, f2, c2, iv2 = spec['p2']
    bp1 = _make_battle_pokemon(sp1, f1, c1, 'great', s1, *iv1)
    bp2 = _make_battle_pokemon(sp2, f2, c2, 'great', s2, *iv2)
    result = simulate(bp1, bp2, charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp, log=True)
    score = round(result.pvpoke_score(0))
    assert score == p1_score, (
        f"{matchup} {s1}v{s2}: expected p1 score {p1_score}, got {score}")
    assert result.winner == winner
    assert _extract_battle_log(result) == expected_log
    if winner is None:
        # The simultaneous-KO draw: a lethal Gulp Missile against the
        # charged move that KO'd Cramorant scores 500/500 on both sides.
        assert round(result.pvpoke_score(1)) == 500
        assert result.hp_remaining == [0, 0]


# ---------------------------------------------------------------------------
# 2026-08-24 port-review additions (adversarial-review confirmed gaps)
# ---------------------------------------------------------------------------

def test_base_species_id_is_form_invariant():
    """_base_species_id mirrors PvPoke's speciesId, which changeForm never
    rewrites: it must stay 'cramorant' in every prey form, or the
    vs-Cramorant shield rules would silently stop applying once prey is
    held (review finding: this invariance was unpinned)."""
    from gopvpsim.battle import _base_species_id, _holding_prey
    bp = _cramorant('PECK', ['DIVE', 'FLY'], 0)
    opp = _make_battle_pokemon('Azumarill', 'BUBBLE',
                               ['ICE_BEAM', 'PLAY_ROUGH'], 'great', 0, 4, 15, 13)
    assert _base_species_id(bp) == 'cramorant'
    assert not _holding_prey(bp)
    bp.change_form(opp, 1)                     # Gulping
    assert _base_species_id(bp) == 'cramorant'
    assert _holding_prey(bp)
    bp.change_form(opp, 2)                     # Gorging (test-only jump)
    assert _base_species_id(bp) == 'cramorant'
    assert _holding_prey(bp)
    bp.change_form(opp, 0)                     # back to base
    assert not _holding_prey(bp)


def test_triggered_moves_table_matches_gamemaster_moveids():
    """Drift guard for the hardcoded _FORM_CHANGE_TRIGGERED_MOVES table:
    every trigger move the gamemaster declares for Cramorant (formChange
    moveIDs) must be a key, and each maps to both missiles."""
    from gopvpsim.formchange import _FORM_CHANGE_TRIGGERED_MOVES
    from gopvpsim.pokemon import get_pokemon_entry
    fc = get_pokemon_entry('Cramorant')['formChange']
    for mid in fc['moveIDs']:
        assert set(_FORM_CHANGE_TRIGGERED_MOVES[mid]) == {
            'GULP_MISSILE_ARROKUDA', 'GULP_MISSILE_PIKACHU'}, mid


def test_gulp_missile_intra_turn_insertion_position():
    """The missile is INSERTED at the current action index, so it resolves
    between the triggering charged move and any later same-turn action
    (PvPoke's actionIndex splice) -- NOT appended after the turn's actions.
    Observable: when both sides throw charged on one turn and the faster
    side's move triggers the missile, the slower side's (= Cramorant's own)
    charged move lands AFTER the missile has already debuffed the striker
    to -1 def, so its damage is the -1-def value. (Review finding: the
    insertion position, the reason the loop became index-driven, was
    unpinned.)"""
    from gopvpsim.moves import get_moves
    fm, cm = get_moves()
    striker = BattlePokemon(
        species='Striker', types=['normal'], atk=150.0, def_=110.0,
        max_hp=200, fast_move=dict(fm['COUNTER']),
        charged_moves=[dict(cm['ICE_BEAM'])], shields=0, initial_energy=90)
    cram = _cramorant('PECK', ['DIVE', 'HYDRO_PUMP'], 0)
    opp_for_setup = striker
    cram.change_form(opp_for_setup, 1)         # Gulping (holding prey)
    cram.energy = 40                           # Dive ready
    assert striker.cmp_atk > cram.cmp_atk      # striker's charged resolves first

    # Expected Dive damage at striker def stage 0 vs -1 (must differ, or
    # the test cannot discriminate insertion position).
    dive = cram.charged_moves[0]
    d0 = cram.charged_move_damage(dive, striker)
    striker.def_stage = -1
    d1 = cram.charged_move_damage(dive, striker)
    striker.def_stage = 0
    assert d1 > d0, 'pick different stats: stage step must move the floor'

    result = simulate(cram, striker,
                      charged_policy_0=use_first_available,
                      charged_policy_1=use_first_available, log=True)
    uses = [ln for ln in result.timeline if 'uses' in ln and '→' in ln]
    i_ice = next(i for i, ln in enumerate(uses) if 'Ice Beam' in ln)
    i_missile = next(i for i, ln in enumerate(uses) if 'Gulp Missile' in ln)
    i_dive = next(i for i, ln in enumerate(uses) if 'uses Dive' in ln)
    assert i_ice < i_missile < i_dive, (
        f'missile must resolve between the trigger and the remaining '
        f'same-turn action; got order {uses}')
    assert f'→ {d1} dmg' in uses[i_dive], (
        f'Dive damage must reflect the missile debuff (-1 def -> {d1}, '
        f'stage-0 would be {d0}): {uses[i_dive]}')
    assert striker.def_stage == -1


def test_gulp_missile_fires_at_a_corpse():
    """PvPoke has no dead-defender guard on charged actions: when an
    exact-CMP-tie dead-throw (the simultaneous-charged exception) triggers
    the missile, the missile still fires at the corpse -- score-neutral,
    but the log line keeps oracle parity. (Review finding 13; our generic
    dead-defender skip now carves out instant moves.)"""
    from gopvpsim.moves import get_moves
    fm, cm = get_moves()
    cram = _cramorant('PECK', ['DIVE', 'HYDRO_PUMP'], 0)
    # Equal cmp_atk -> no priority -> the dead thrower's charged still
    # resolves via the opponent_also_charged exception.
    striker = BattlePokemon(
        species='Striker', types=['normal'], atk=cram.atk, def_=110.0,
        max_hp=60, fast_move=dict(fm['COUNTER']),
        charged_moves=[dict(cm['ICE_BEAM'])], shields=0, initial_energy=90)
    cram.change_form(striker, 1)               # Gulping
    cram.energy = 100                          # Hydro Pump (lethal) ready
    assert striker.cmp_atk == cram.cmp_atk
    hp_dmg = cram.charged_move_damage(cram.charged_moves[1], striker)
    assert hp_dmg >= striker.max_hp, 'setup: Hydro Pump must KO the striker'

    result = simulate(cram, striker,
                      charged_policy_0=lambda a, d, mechanics='legacy': 1,
                      charged_policy_1=use_first_available, log=True)
    # p0 (cram) throws first in the stable no-priority order, KOs striker;
    # striker's dead-throw Ice Beam still hits prey-holding cram
    # (unshielded) -> the missile fires at the corpse.
    uses = [ln for ln in result.timeline if 'uses' in ln and '→' in ln]
    assert any('Ice Beam' in ln for ln in uses), (
        f'setup drift: the dead-throw never happened: {uses}')
    assert any('Gulp Missile' in ln for ln in uses), (
        f'missile must fire at the corpse (PvPoke parity): {uses}')
    assert result.winner == 0


# ---------------------------------------------------------------------------
# would_shield tail rules + [918] widening (review: these were dead to the
# suite as direct units; each case pins a discriminating scenario probed
# empirically -- setup preconditions asserted so drift fails loudly)
# ---------------------------------------------------------------------------

def test_would_shield_aegislash_rule_flips_to_false():
    """Tail rule 1 (upstream-new in 78c64048a): an aegislash_shield
    defender with incoming damage*2 < hp does not shield -- proven by an
    identity clone with the same numbers that DOES shield."""
    from gopvpsim.battle import would_shield
    from .test_battle import make_bp
    _, cm = get_moves()
    med = _make_battle_pokemon('Medicham', 'COUNTER',
                               ['DYNAMIC_PUNCH', 'ICE_PUNCH'],
                               'great', 0, 7, 15, 14)
    aeg = _make_battle_pokemon('Aegislash (Shield)',
                               'AEGISLASH_CHARGE_PSYCHO_CUT',
                               ['SHADOW_BALL', 'GYRO_BALL'],
                               'great', 2, 0, 15, 15)
    aeg.hp = 50
    clone = make_bp(types=list(aeg.types), def_=aeg.def_, hp=aeg.max_hp,
                    shields=2, charged=[dict(cm['SHADOW_BALL'])])
    clone.hp = 50
    dp = med.charged_moves[0]
    dmg = med.charged_move_damage(dp, aeg)
    assert dmg * 2 < aeg.hp, 'setup: the rule predicate must hold'
    assert would_shield(med, clone, dp) is True, 'setup: clone must shield'
    assert would_shield(med, aeg, dp) is False


def test_would_shield_prey_holder_tanks_weak_hits():
    """Tail rule 2: a prey-holding Cramorant tanks charged hits smaller
    than hp/2.2 (so the missile fires sooner); its own base form with the
    same numbers shields."""
    from gopvpsim.battle import would_shield
    from .test_battle import make_bp, make_charged, make_fast
    cram = _cramorant('PECK', ['DIVE', 'HYDRO_PUMP'], 2)
    striker = make_bp(atk=110.0, fast=make_fast(power=10, energy_gain=5),
                      charged=[make_charged(power=45, energy=45)])
    mv = striker.charged_moves[0]
    dmg = striker.charged_move_damage(mv, cram)
    assert dmg * 2.2 < cram.hp, 'setup: the rule predicate must hold'
    assert would_shield(striker, cram, mv) is True, 'setup: base form shields'
    cram.change_form(striker, 1)               # Gulping
    assert would_shield(striker, cram, mv) is False


def test_would_shield_vs_cramorant_weak_move_save():
    """Tail rule 3: opponents don't shield a sub-33% Cramorant charged
    move (saving shields for after the Gulp Missile debuff) -- proven by
    a non-Cramorant clone with identical stats and moves that DOES
    shield the same Dive."""
    from gopvpsim.battle import would_shield
    from .test_battle import make_bp
    fm, cm = get_moves()
    med = _make_battle_pokemon('Medicham', 'COUNTER',
                               ['DYNAMIC_PUNCH', 'ICE_PUNCH'],
                               'great', 2, 7, 15, 14)
    cram = _cramorant('PECK', ['DIVE', 'HYDRO_PUMP'], 0)
    clone = make_bp(atk=cram.atk, def_=cram.def_, hp=cram.max_hp,
                    types=list(cram.types), fast=dict(fm['PECK']),
                    charged=[dict(cm['DIVE']), dict(cm['HYDRO_PUMP'])])
    dive = cram.charged_moves[0]
    dmg = cram.charged_move_damage(dive, med)
    assert dmg / med.hp < 0.33, 'setup: the rule predicate must hold'
    assert would_shield(clone, med, clone.charged_moves[0]) is True, (
        'setup: the identity-free clone must shield')
    assert would_shield(cram, med, dive) is False


def test_would_shield_lethal_dive_typo_semantics():
    """Tail rule 4 as SHIPPED upstream (ActionLogic.js:1239 with the
    move.moveID typo): a LETHAL Cramorant Dive is never shielded, while a
    lethal Surf -- the typo's dead branch -- is shielded normally. If
    PvPoke ever fixes the typo (or the inverted intent), this pin fails
    and the divergence decision must be revisited."""
    from gopvpsim.battle import would_shield
    for mv_id, expected in (('DIVE', False), ('SURF', True)):
        cram = _make_battle_pokemon('Cramorant', 'WATER_GUN', [mv_id, 'FLY'],
                                    'great', 0, 5, 15, 15)
        frail = _make_battle_pokemon('Medicham', 'COUNTER',
                                     ['DYNAMIC_PUNCH', 'ICE_PUNCH'],
                                     'great', 1, 7, 15, 14)
        frail.hp = 5
        move = cram.charged_moves[0]
        assert cram.charged_move_damage(move, frail) > frail.hp, 'setup: lethal'
        assert would_shield(cram, frail, move) is expected, mv_id


def test_918_stacking_fires_against_prey_holder():
    """The [918] stack-energy gate (pvpoke 78c64048a ActionLogic.js:959)
    fires for a NON-self-debuffing moveset against a prey-holding
    Cramorant: Lickitung at 50/70 toward double-Body-Slam energy WAITS
    when Cramorant holds prey and THROWS against base-form Cramorant in
    the identical near-KO state."""
    def decide(prey: bool):
        lick = _make_battle_pokemon('Lickitung', 'LICK', ['BODY_SLAM'],
                                    'great', 1, 8, 15, 14)
        cram = _cramorant('PECK', ['DIVE', 'HYDRO_PUMP'], 1)
        if prey:
            cram.change_form(lick, 1)
        lick.energy = 50          # < targetEnergy 70 = (100//35)*35
        cram.cooldown = 1         # mid-fast: past the OMT opponent-idle delay
        cram.hp = 60              # near-KO region so the [918] block is reached
        return pvpoke_dp(lick, cram)

    assert decide(prey=False) == 0     # throws Body Slam
    assert decide(prey=True) is None   # stacks toward 70 first


def test_policy_lab_knob_defaults_are_pvpoke(monkeypatch):
    """The policy-lab knobs default to PvPoke's shipped literals (the
    engine is byte-identical unless a lab process overrides them), and
    each knob is actually LIVE -- overriding it changes the decision the
    matching rule produces."""
    import gopvpsim.battle as B
    assert B._CRAM_DIVE_GATE_DPE == 1.5
    assert B._CRAM_DIVE_GATE_HP == 1.3
    assert B._CRAM_TANK_MULT == 2.2
    assert B._CRAM_DELAY_GORGING is False
    assert B._CRAM_LETHAL_DIVE_SHIELD_FIX is False

    # Tank knob is live: the prey-holder tank scenario flips back to
    # shielding when the threshold is squeezed to nothing.
    from .test_battle import make_bp, make_charged, make_fast
    cram = _cramorant('PECK', ['DIVE', 'HYDRO_PUMP'], 2)
    striker = make_bp(atk=110.0, fast=make_fast(power=10, energy_gain=5),
                      charged=[make_charged(power=45, energy=45)])
    mv = striker.charged_moves[0]
    cram.change_form(striker, 1)
    assert B.would_shield(striker, cram, mv) is False        # default 2.2
    monkeypatch.setattr(B, '_CRAM_TANK_MULT', 1000.0)
    assert B.would_shield(striker, cram, mv) is True

    # Lethal-Dive fix knob is live: the shipped never-shield pin inverts.
    monkeypatch.setattr(B, '_CRAM_LETHAL_DIVE_SHIELD_FIX', True)
    cram2 = _make_battle_pokemon('Cramorant', 'WATER_GUN', ['DIVE', 'FLY'],
                                 'great', 0, 5, 15, 15)
    frail = _make_battle_pokemon('Medicham', 'COUNTER',
                                 ['DYNAMIC_PUNCH', 'ICE_PUNCH'],
                                 'great', 1, 7, 15, 14)
    frail.hp = 5
    assert B.would_shield(cram2, frail, cram2.charged_moves[0]) is True

    # Dive-gate DPE knob is live: vs Azumarill the default gate blocks
    # the dive (Fly's dpe ratio >= 1.5); widening it makes the ASAP rule
    # fire.
    azu = _make_battle_pokemon('Azumarill', 'BUBBLE',
                               ['ICE_BEAM', 'PLAY_ROUGH'], 'great', 1, 4, 15, 13)
    cram3 = _cramorant('PECK', ['DIVE', 'FLY'], 1)
    cram3.energy = 40
    azu.cooldown = 1
    dive_idx = next(i for i, m in enumerate(cram3.charged_moves)
                    if m['moveId'] == 'DIVE')
    assert pvpoke_dp(cram3, azu) != dive_idx   # default: never dives here
    monkeypatch.setattr(B, '_CRAM_DIVE_GATE_DPE', 100.0)
    assert pvpoke_dp(cram3, azu) == dive_idx   # widened gate: dives ASAP
