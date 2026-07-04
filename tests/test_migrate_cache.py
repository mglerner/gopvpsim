"""Tests for scripts/migrate_cache.py — selective sweep-cache invalidation.

Pins the bug-#1 shadow_xor predicate (2026-06-27): after a localized engine
fix, a column is AFFECTED iff exactly one side is shadow; both-shadow and
both-non-shadow columns are provably unchanged and get blessed (re-stamped)
so the re-dive serves them warm, while shadow-XOR columns are deleted to
re-sim cold.
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sweep_cache = sys.modules.get("sweep_cache") or _load("sweep_cache")
migrate_cache = sys.modules.get("migrate_cache") or _load("migrate_cache")


def _focal_fields(shadow):
    return sweep_cache.focal_key_fields(
        species='Azumarill', league='great', shadow=shadow,
        fast_id='BUBBLE', charged_ids=['ICE_BEAM'],
        iv_floor=None, shield_scenarios=[(0, 0)], bait_mode='bait')


def _col_fields(opp_shadow):
    return sweep_cache.column_key_fields(
        opp_species='Medicham', opp_shadow=opp_shadow, opp_ivs=(15, 15, 15),
        opp_level=50.0, opp_fast_id='COUNTER', opp_charged_ids=['PSYCHIC'])


def _put(focal_shadow, opp_shadow):
    """Write a 1x1 column for (focal_shadow, opp_shadow) and return its
    sidecar path."""
    cache = sweep_cache.SweepCache(_focal_fields(focal_shadow))
    cf = _col_fields(opp_shadow)
    cache.put_column(cf, {'score': np.zeros((1, 1)), 'energy': np.zeros((1, 1))})
    return cache._col_path(cf).with_suffix('.json')


def _stamp(json_path):
    return sweep_cache.SweepCache.read_stamp(json_path)


def test_shadow_xor_predicate():
    p = migrate_cache.PREDICATES['shadow_xor']
    assert p({'shadow': False}, {'shadow': False}) is False  # both non-shadow
    assert p({'shadow': True}, {'shadow': True}) is False    # both shadow
    assert p({'shadow': True}, {'shadow': False}) is True    # XOR
    assert p({'shadow': False}, {'shadow': True}) is True    # XOR


def test_self_debuff_either_side_predicate():
    """bandaid[910]: a column is affected iff EITHER side owns a self-debuff
    charged move (both-sided). Uses the engine's real selfDebuffing flag."""
    p = migrate_cache.PREDICATES['self_debuff_either_side']
    # Real moves: CLOSE_COMBAT/SUPER_POWER/BRAVE_BIRD self-debuff; BODY_SLAM/
    # POWER_WHIP/NIGHT_SLASH/ICE_BEAM do not (verified via moves.get_moves()).
    lick = {'species': 'Lickitung', 'fast': 'LICK',
            'charged': ['BODY_SLAM', 'POWER_WHIP']}           # no self-debuff CM
    pang = {'species': 'Pangoro', 'fast': 'KARATE_CHOP',
            'charged': ['CLOSE_COMBAT', 'NIGHT_SLASH']}       # CLOSE_COMBAT = SD
    azu = {'species': 'Azumarill', 'fast': 'BUBBLE',
           'charged': ['ICE_BEAM', 'PLAY_ROUGH']}             # no self-debuff CM

    # Neither side owns a self-debuff CM -> provably unchanged -> BLESS.
    assert p(lick, azu) is False
    assert p(azu, lick) is False
    # BOTH-SIDED: an opponent-side self-debuff holder DOES change a non-SD
    # focal's column (the focal-only complement would wrongly bless this —
    # Lickitung focal vs Pangoro 92->284 in the feasibility A/B).
    assert p(lick, pang) is True     # opponent owns CLOSE_COMBAT
    assert p(pang, lick) is True     # focal owns CLOSE_COMBAT
    assert p(pang, pang) is True

    # Morpeko form-swap soundness: AURA_WHEEL_ELECTRIC<->DARK is a battle-time
    # CHARGED-move swap, and NEITHER variant is self-debuffing, so a Morpeko with
    # no stored self-debuff CM is correctly blessed.
    morp = {'species': 'Morpeko (Full Belly)', 'fast': 'THUNDER_SHOCK',
            'charged': ['AURA_WHEEL_ELECTRIC', 'PSYCHIC_FANGS']}
    assert p(morp, azu) is False
    assert p(azu, morp) is False

    # KNOWN-INCOMPLETE (F2, measured harmless): battle.py dynamically marks
    # FOCUS_BLAST selfDebuffing when paired with ZAP_CANNON, so this static-flag
    # predicate blesses such a column even though the [910] gate can reach it.
    # Harmless in practice (the mutation only shifts KO turn, not cached planes;
    # see the predicate docstring), but the static read is why FB+ZC blesses:
    regi = {'species': 'Registeel', 'fast': 'LOCK_ON',
            'charged': ['FOCUS_BLAST', 'ZAP_CANNON']}   # neither statically SD
    assert p(regi, azu) is False   # blessed on static flags (measured harmless)

    # FAIL-SAFE: missing/empty/None moveset -> AFFECTED (never bless blind).
    assert p(lick, None) is True
    assert p(None, lick) is True
    assert p(lick, {'species': 'X'}) is True            # col lacks 'charged'
    assert p({'species': 'X', 'charged': []}, azu) is True  # empty charged


def _delta_gm(**move_powers):
    """Minimal gamemaster for the form-change-swap delta test. Overriding a move
    power lets a caller build an old/new pair differing in exactly one move.
    Aegislash (Shield/Blade) + Morpeko (Full Belly/Hangry) carry the formChange
    links the delta expands through; only speciesId/speciesName/formChange and
    moveId/power are read by build_gamemaster_delta."""
    powers = {'PSYCHO_CUT': 30, 'AEGISLASH_CHARGE_PSYCHO_CUT': 0,
              'SHADOW_BALL': 100, 'AURA_WHEEL_ELECTRIC': 45,
              'AURA_WHEEL_DARK': 45, 'PSYCHIC_FANGS': 40,
              'THUNDER_SHOCK': 3, 'BUBBLE': 7, 'ICE_BEAM': 90}
    powers.update(move_powers)
    return {
        'pokemon': [
            {'speciesId': 'aegislash_shield', 'speciesName': 'Aegislash (Shield)',
             'formChange': {'alternativeFormId': 'aegislash_blade'}},
            {'speciesId': 'aegislash_blade', 'speciesName': 'Aegislash (Blade)',
             'formChange': {'alternativeFormId': 'aegislash_shield'}},
            {'speciesId': 'morpeko_full_belly', 'speciesName': 'Morpeko (Full Belly)',
             'formChange': {'alternativeFormId': 'morpeko_hangry'}},
            {'speciesId': 'morpeko_hangry', 'speciesName': 'Morpeko (Hangry)'},
            {'speciesId': 'azumarill', 'speciesName': 'Azumarill'},
            {'speciesId': 'medicham', 'speciesName': 'Medicham'},
        ],
        'moves': [{'moveId': mid, 'power': p} for mid, p in powers.items()],
    }


def test_gamemaster_delta_form_change_swapped_moves():
    """F1 regression: a gamemaster patch touching ONLY a form-change swapped-in
    move changes a column's scores though that move is not in the stored key
    (Aegislash's default fast move AEGISLASH_CHARGE_PSYCHO_CUT reverts to the
    plain PSYCHO_CUT; Morpeko's stored AURA_WHEEL_ELECTRIC toggles to
    AURA_WHEEL_DARK). affected() must mark such columns AFFECTED, not bless
    them. Pre-F1 the used-set held only stored moves, so all of these blessed."""
    azu = {'species': 'Azumarill', 'shadow': False,
           'fast': 'BUBBLE', 'charged': ['ICE_BEAM']}

    # Aegislash: only PSYCHO_CUT changes; Aegislash stores AEGISLASH_CHARGE_PSYCHO_CUT.
    affected, info = migrate_cache.build_gamemaster_delta(
        _delta_gm(PSYCHO_CUT=30), _delta_gm(PSYCHO_CUT=90))
    assert info['touched_moves'] == ['PSYCHO_CUT']
    assert info['touched_species'] == []
    aegis = {'species': 'Aegislash (Shield)', 'shadow': False,
             'fast': 'AEGISLASH_CHARGE_PSYCHO_CUT', 'charged': ['SHADOW_BALL']}
    assert affected(aegis, azu) is True   # focal reads PSYCHO_CUT after revert
    assert affected(azu, aegis) is True   # Aegislash as opponent column, same
    # Control: a column with no form-changer and no PSYCHO_CUT stays BLESSED.
    med = {'species': 'Medicham', 'shadow': False,
           'fast': 'COUNTER', 'charged': ['PSYCHIC']}
    assert affected(azu, med) is False

    # Morpeko: only AURA_WHEEL_DARK changes; Morpeko stores AURA_WHEEL_ELECTRIC.
    affected, info = migrate_cache.build_gamemaster_delta(
        _delta_gm(AURA_WHEEL_DARK=45), _delta_gm(AURA_WHEEL_DARK=20))
    assert info['touched_moves'] == ['AURA_WHEEL_DARK']
    morp = {'species': 'Morpeko (Full Belly)', 'shadow': False,
            'fast': 'THUNDER_SHOCK',
            'charged': ['AURA_WHEEL_ELECTRIC', 'PSYCHIC_FANGS']}
    assert affected(morp, azu) is True    # reads AURA_WHEEL_DARK after toggle
    assert affected(azu, morp) is True


def test_migrate_blesses_unaffected_deletes_affected(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'oldengine000')
    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_cur')

    # Four columns under two focal dirs, all stamped at the old engine and the
    # CURRENT gamemaster (engine-mode requires the gamemaster already current).
    unaff_nn = _put(focal_shadow=False, opp_shadow=False)  # both non-shadow
    unaff_ss = _put(focal_shadow=True, opp_shadow=True)    # both shadow
    aff_a = _put(focal_shadow=False, opp_shadow=True)      # XOR
    aff_b = _put(focal_shadow=True, opp_shadow=False)      # XOR
    for sc in (unaff_nn, unaff_ss, aff_a, aff_b):
        assert _stamp(sc) == 'oldengine000'

    # Engine changes (a localized shadow-only fix).
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'newengine111')

    # Dry-run touches nothing.
    migrate_cache.migrate_engine(tmp_path, 'oldengine000', 'shadow_xor',
                                 apply=False)
    assert _stamp(unaff_nn) == 'oldengine000'
    assert aff_a.exists()

    # Apply: unaffected re-stamped to the new engine (warm), affected deleted.
    migrate_cache.migrate_engine(tmp_path, 'oldengine000', 'shadow_xor',
                                 apply=True)
    assert _stamp(unaff_nn) == 'newengine111'
    assert _stamp(unaff_ss) == 'newengine111'
    assert sweep_cache.SweepCache.read_gm_stamp(unaff_nn) == 'gm_cur'  # kept
    assert unaff_nn.with_suffix('.npz').exists()  # .npz untouched by bless
    for aff in (aff_a, aff_b):
        assert not aff.exists()
        assert not aff.with_suffix('.npz').exists()


def test_engine_migrate_skips_other_gamemaster(tmp_path, monkeypatch):
    # v7: a column whose PER-COLUMN gamemaster stamp differs from the current
    # gamemaster must be left alone — the engine predicate models only the
    # engine delta, so the gamemaster must already be current.
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'oldengine000')
    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'oldgm')
    sc = _put(focal_shadow=False, opp_shadow=False)  # unaffected, but old GM

    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'newengine111')
    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'newgm')
    migrate_cache.migrate_engine(tmp_path, 'oldengine000', 'shadow_xor',
                                 apply=True)
    # Untouched: still old engine stamp (its gamemaster stamp isn't current).
    assert _stamp(sc) == 'oldengine000'


# ---- slayer engine migration (migrate_slayer_engine) ----

slayer_cache = sys.modules.get("slayer_cache") or _load("slayer_cache")


def _put_slayer(slayer_dir, key, engine, gamemaster, charged):
    """Write a v5 slayer .pkl + .json sidecar for a mirror scenario."""
    import pickle
    slayer_dir.mkdir(parents=True, exist_ok=True)
    with open(slayer_dir / f'{key}.pkl', 'wb') as f:
        pickle.dump({(0, 0): (500,)}, f)
    (slayer_dir / f'{key}.json').write_text(json.dumps({
        'engine': engine, 'gamemaster': gamemaster,
        'scenario': {'species': key, 'league': 'great', 'shadow': False,
                     'fast': 'F', 'charged': charged}}))
    return slayer_dir / f'{key}.json'


def test_slayer_engine_migration_blesses_and_deletes(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'newengine111')
    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_cur')
    sd = tmp_path / 'slayer'
    # Pangoro mirror owns CLOSE_COMBAT (self-debuff) -> AFFECTED (mirror).
    aff = _put_slayer(sd, 'Pangoro', 'oldengine000', 'gm_cur',
                      ['CLOSE_COMBAT', 'NIGHT_SLASH'])
    # Azumarill mirror owns no self-debuff CM -> BLESSED.
    bless = _put_slayer(sd, 'Azumarill', 'oldengine000', 'gm_cur',
                        ['ICE_BEAM', 'PLAY_ROUGH'])

    migrate_cache.migrate_slayer_engine(sd, 'oldengine000',
                                        'self_debuff_either_side', apply=True)
    # Unaffected re-stamped to the new engine (warm); affected deleted.
    assert slayer_cache.read_stamp(bless)[0] == 'newengine111'
    assert bless.with_suffix('.pkl').exists()
    assert not aff.exists() and not aff.with_suffix('.pkl').exists()


def test_slayer_engine_migration_skips_other_gamemaster(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'newengine111')
    monkeypatch.setattr(sweep_cache, '_GAMEMASTER_HASH', 'gm_new')
    sd = tmp_path / 'slayer'
    j = _put_slayer(sd, 'Azumarill', 'oldengine000', 'gm_old',
                    ['ICE_BEAM'])  # unaffected but OLD gamemaster
    migrate_cache.migrate_slayer_engine(sd, 'oldengine000',
                                        'self_debuff_either_side', apply=True)
    assert slayer_cache.read_stamp(j)[0] == 'oldengine000'  # untouched


# ---- gamemaster-delta predicate (build_gamemaster_delta) ----

def _gm(pokemon, moves):
    return {'pokemon': pokemon, 'moves': moves}


def _mon(sid, name, atk=100, form_alt=None):
    e = {'speciesId': sid, 'speciesName': name,
         'baseStats': {'atk': atk, 'def': 100, 'hp': 100}}
    if form_alt:
        e['formChange'] = {'alternativeFormId': form_alt}
    return e


def _mv(mid, power=10):
    return {'moveId': mid, 'power': power, 'energy': 50}


def test_gm_delta_additive_only_blesses_all():
    # Adding a brand-new species (skarmory_mega scenario): touched sets empty
    # -> every existing column is unaffected regardless of what it references.
    old = _gm([_mon('azumarill', 'Azumarill')], [_mv('BUBBLE')])
    new = _gm([_mon('azumarill', 'Azumarill'), _mon('skarmory_mega', 'Skarmory (Mega)')],
              [_mv('BUBBLE')])
    affected, info = migrate_cache.build_gamemaster_delta(old, new)
    assert info['added_species'] == ['skarmory_mega']
    assert info['touched_species'] == [] and info['touched_moves'] == []
    f = {'species': 'Azumarill', 'shadow': False, 'fast': 'BUBBLE', 'charged': []}
    c = {'species': 'Azumarill', 'shadow': False, 'fast': 'BUBBLE', 'charged': []}
    assert affected(f, c) is False


def test_gm_delta_changed_base_stat_affects_referencing_columns():
    old = _gm([_mon('medicham', 'Medicham', atk=100),
               _mon('azumarill', 'Azumarill')], [_mv('COUNTER')])
    new = _gm([_mon('medicham', 'Medicham', atk=999),  # rebalanced
               _mon('azumarill', 'Azumarill')], [_mv('COUNTER')])
    affected, info = migrate_cache.build_gamemaster_delta(old, new)
    assert info['touched_species'] == ['medicham']
    azu = {'species': 'Azumarill', 'shadow': False, 'fast': 'X', 'charged': []}
    med = {'species': 'Medicham', 'shadow': False, 'fast': 'X', 'charged': []}
    # Column with Medicham on either side -> affected; neither -> not.
    assert affected(azu, med) is True   # opponent changed
    assert affected(med, azu) is True   # focal changed
    assert affected(azu, azu) is False


def test_gm_delta_shadow_resolves_to_base_entry():
    # A base-stat change to 'medicham' must affect a SHADOW Medicham column
    # (shadow stats derive from the base entry), even if no '_shadow' entry
    # exists / was regenerated.
    old = _gm([_mon('medicham', 'Medicham', atk=100)], [_mv('X')])
    new = _gm([_mon('medicham', 'Medicham', atk=999)], [_mv('X')])
    affected, _ = migrate_cache.build_gamemaster_delta(old, new)
    shadow_med = {'species': 'Medicham', 'shadow': True, 'fast': 'X', 'charged': []}
    other = {'species': 'Medicham', 'shadow': True, 'fast': 'X', 'charged': []}
    assert affected(shadow_med, other) is True


def test_gm_delta_form_change_alt_stats_affect_column():
    # Editing ONLY the alt form (aegislash_blade) must mark an Aegislash
    # (Shield) column affected — the battle transforms into Blade and reads
    # its baseStats.
    old = _gm([_mon('aegislash_shield', 'Aegislash (Shield)', form_alt='aegislash_blade'),
               _mon('aegislash_blade', 'Aegislash (Blade)', atk=100),
               _mon('azumarill', 'Azumarill')], [_mv('X')])
    new = _gm([_mon('aegislash_shield', 'Aegislash (Shield)', form_alt='aegislash_blade'),
               _mon('aegislash_blade', 'Aegislash (Blade)', atk=999),  # alt rebalanced
               _mon('azumarill', 'Azumarill')], [_mv('X')])
    affected, info = migrate_cache.build_gamemaster_delta(old, new)
    assert info['touched_species'] == ['aegislash_blade']
    shield = {'species': 'Aegislash (Shield)', 'shadow': False, 'fast': 'X', 'charged': []}
    azu = {'species': 'Azumarill', 'shadow': False, 'fast': 'X', 'charged': []}
    assert affected(shield, azu) is True   # focal transforms to changed Blade
    assert affected(azu, shield) is True   # opponent transforms to changed Blade


def test_gm_delta_changed_move_affects_users():
    old = _gm([_mon('a', 'A'), _mon('b', 'B')], [_mv('COUNTER', 10), _mv('ICE', 5)])
    new = _gm([_mon('a', 'A'), _mon('b', 'B')], [_mv('COUNTER', 99), _mv('ICE', 5)])
    affected, info = migrate_cache.build_gamemaster_delta(old, new)
    assert info['touched_moves'] == ['COUNTER']
    uses = {'species': 'A', 'shadow': False, 'fast': 'COUNTER', 'charged': []}
    not_uses = {'species': 'B', 'shadow': False, 'fast': 'ICE', 'charged': ['ICE']}
    assert affected(uses, not_uses) is True     # one side uses COUNTER
    assert affected(not_uses, not_uses) is False


def test_gm_delta_unresolvable_species_is_affected():
    # A removed/renamed species: the column's stored name no longer resolves
    # in EITHER gm -> can't prove unaffected -> re-sim.
    old = _gm([_mon('oldmon', 'OldMon'), _mon('a', 'A')], [_mv('X')])
    new = _gm([_mon('a', 'A')], [_mv('X')])  # OldMon removed
    affected, info = migrate_cache.build_gamemaster_delta(old, new)
    assert 'oldmon' in info['touched_species']
    # A column whose name is gone entirely from both gms:
    ghost = {'species': 'GhostName', 'shadow': False, 'fast': 'X', 'charged': []}
    a = {'species': 'A', 'shadow': False, 'fast': 'X', 'charged': []}
    assert affected(ghost, a) is True
    # And the removed species itself (still resolvable via the OLD index):
    oldmon = {'species': 'OldMon', 'shadow': False, 'fast': 'X', 'charged': []}
    assert affected(oldmon, a) is True
