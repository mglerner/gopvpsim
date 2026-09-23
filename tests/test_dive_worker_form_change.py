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
import sys
from pathlib import Path

from tests.conftest import load_deep_dive

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Loading deep_dive also imports deep_dive_slayer and applies the
# compute_iv_metadata injection (same pattern as test_slayer_smoke.py).
deep_dive = load_deep_dive()

import deep_dive_slayer  # noqa: E402  (importable after deep_dive's sys.path insert)

from gopvpsim.battle import BattlePokemon, simulate, pvpoke_dp  # noqa: E402
from gopvpsim.data import load_gamemaster  # noqa: E402
from gopvpsim.moves import parse_types  # noqa: E402
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
    profiles = [_focal_profile(ivs) for ivs in focal_iv_list]
    chunk = [(prof, oi) for prof in profiles
             for oi in range(len(opp_cache))]
    results, _energy, _metrics, n_sims = deep_dive._sweep_worker(chunk)

    assert n_sims == len(focal_iv_list) * len(opp_cache) * len(SCENARIOS)

    opp_specs = [('Azumarill', AZU_MOVESET, azu_ivs),
                 (AEGI_SPECIES, (AEGI_FAST, AEGI_CHARGED), aegi_opp_ivs)]
    for ivs, prof in zip(focal_iv_list, profiles):
        for oi, (opp_species, opp_moveset, opp_ivs) in enumerate(opp_specs):
            scores = results[(prof[0], oi)]
            for si, (s_focal, s_opp) in enumerate(SCENARIOS):
                expected = _reference_score(ivs, s_focal, s_opp,
                                            opp_species, opp_moveset,
                                            opp_ivs)
                got = scores[si]
                assert got == expected, (
                    f"IV {ivs} vs {opp_species} {s_focal}v{s_opp}: "
                    f"worker={got}, from_pokemon={expected}")


def test_sweep_worker_pins_pvpoke_oracle_score():
    """The sweep worker reproduces the PvPoke-harness-verified 0v0
    score (751 as of 2026-09-09; 773 under the retired legacy turn
    system) for Aegislash (Shield) 4/14/15 vs Azumarill 4/15/13 —
    the same cell test_aegislash_vs_azumarill_form_change pins on the
    from_pokemon path. A no-form-change construction (the pre-S1
    worker behavior) must NOT reproduce it, proving the wiring is what
    changed the dive results."""
    opp_cache = [_opp_cache_entry('Azumarill', AZU_MOVESET[0],
                                  AZU_MOVESET[1], (4, 15, 13))]
    _init_sweep_worker_state(opp_cache, [(0, 0)])

    prof = _focal_profile((4, 14, 15))
    results, _energy, _metrics, _ = deep_dive._sweep_worker([(prof, 0)])
    score = results[(prof[0], 0)][0]
    assert round(score) == 751

    # Pre-S1 behavior: same stats, no form-change state attached.
    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon']
                     if m['speciesName'] == AEGI_SPECIES)
    fast_db, charged_db = get_moves()
    _, atk, def_, hp, *_rest = prof
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
    assert round(result.pvpoke_score(0)) != 751


def test_slayer_worker_forwards_mechanics(monkeypatch):
    """slayer_iter_worker must forward the worker's ``mechanics`` setting
    into simulate(). Pins the --mechanics plumbing: with mechanics='new'
    in worker state, every simulate() call gets mechanics='new'. (A
    no-op default kwarg would leave this green only by accident, so we
    assert the captured value is 'new', not just present.)"""
    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon']
                     if m['speciesName'] == AEGI_SPECIES)
    fast_db, charged_db = get_moves()
    scenarios = [(1, 1), (0, 0)]
    deep_dive_slayer.slayer_worker_init(
        AEGI_SPECIES, parse_types(focal_mon),
        LEAGUE_CAPS[LEAGUE], False,
        dict(fast_db[AEGI_FAST]),
        [dict(charged_db[c]) for c in AEGI_CHARGED],
        scenarios, focal_mon=focal_mon, mechanics='new')

    seen = []

    class _FakeResult:
        def pvpoke_score(self, _i):
            return 500

    def _fake_simulate(p0, p1, **kwargs):
        seen.append(kwargs.get('mechanics'))
        return _FakeResult()

    monkeypatch.setattr(deep_dive_slayer, 'simulate', _fake_simulate)

    chunk = [_focal_profile((4, 14, 15))]
    opp_prof = _focal_profile((0, 15, 15))
    opponents = [(0, opp_prof[1:])]
    deep_dive_slayer.slayer_iter_worker((chunk, opponents))

    assert seen, "simulate was never called"
    assert all(m == 'new' for m in seen), (
        f"expected every simulate() call to get mechanics='new', got {seen}")


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


# ---------------------------------------------------------------------------
# The slayer's turn-mechanics default (2026-09-20 pre-dive grid, L6 item 3)
# ---------------------------------------------------------------------------

REGI_SPECIES = 'Registeel'
REGI_FAST = 'LOCK_ON'
REGI_CHARGED = ['FLASH_CANNON', 'FOCUS_BLAST']


def _registeel_mirror_scores(mechanics=None):
    """One slayer round, 0/15/15 vs 15/15/15 Registeel mirror, 3 scenarios."""
    gm = load_gamemaster()
    mon = next(m for m in gm['pokemon'] if m['speciesName'] == REGI_SPECIES)
    fast_db, charged_db = get_moves()
    kw = {} if mechanics is None else {'mechanics': mechanics}
    deep_dive_slayer.slayer_worker_init(
        REGI_SPECIES, parse_types(mon), LEAGUE_CAPS[LEAGUE], False,
        dict(fast_db[REGI_FAST]),
        [dict(charged_db[c]) for c in REGI_CHARGED],
        SCENARIOS, focal_mon=mon, **kw)

    def prof(ivs):
        a, d, s = ivs
        p = Pokemon.at_best_level(REGI_SPECIES, a, d, s, league=LEAGUE)
        pk = (round(p.atk, 4), round(p.def_, 4), int(p.hp), a, d, s, p.level)
        return (pk, p.atk, p.def_, p.hp, a, d, s, p.level)

    focal, opp = prof((0, 15, 15)), prof((15, 15, 15))
    out = deep_dive_slayer.slayer_iter_worker(([focal], [(0, opp[1:])]))
    return out[(focal[0], 0)]


def test_the_slayer_default_mechanics_tracks_the_engine():
    """The slayer's fallback clock is battle.simulate's own default.

    PRE-FIX all three slayer defaults read ``'legacy'`` --
    ``slayer_worker_init``'s kwarg, ``slayer_iter_worker``'s
    ``ws.get('mechanics', ...)`` and ``iterative_slayer_discovery``'s kwarg
    -- while ``simulate``'s default had been ``'new'`` since 2026-09-09
    (7e6a82b). Both product call sites pass ``args.mechanics``, so no
    shipped page ran on the wrong clock; a caller that omitted it did.
    """
    import inspect
    engine_default = simulate.__kwdefaults__['mechanics']
    assert engine_default == 'new'                      # positive control
    assert deep_dive_slayer.SLAYER_DEFAULT_MECHANICS == engine_default
    for fn in (deep_dive_slayer.slayer_worker_init,
               deep_dive_slayer.iterative_slayer_discovery):
        got = inspect.signature(fn).parameters['mechanics'].default
        assert got == engine_default, (fn.__name__, got)  # pre-fix: 'legacy'


def test_a_slayer_round_runs_on_the_clock_it_is_given(allow_legacy_mechanics):
    """The flag reaches simulate() and moves the scores it produces.

    Registeel mirror, LOCK_ON / Flash Cannon + Focus Blast, focal 0/15/15
    against opponent 15/15/15. The 2v2 cell is where the two turn systems
    part: legacy 825, new 723. PRE-FIX a caller that named no mechanics got
    the legacy triple ``(428, 492, 825)``; it now gets the new one.
    """
    legacy = _registeel_mirror_scores('legacy')
    new = _registeel_mirror_scores('new')
    assert legacy == (428, 492, 825), legacy
    assert new == (428, 492, 723), new
    assert legacy != new, "this pair no longer discriminates the two clocks"
    assert _registeel_mirror_scores() == new          # pre-fix: == legacy


def test_deep_dive_hands_its_mechanics_to_every_slayer_call():
    """--mechanics must reach BOTH --mirror-slayer sites, not just the first.

    Scanned with ast rather than a regex so a call spanning lines, or one
    added later, cannot slip past. The second site is the best-buddy L51
    re-convergence, which is exactly the kind of call a reader forgets.
    """
    import ast
    src = (REPO_ROOT / 'scripts' / 'deep_dive.py').read_text()
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)
             and n.func.id == 'iterative_slayer_discovery']
    assert len(calls) >= 2, f"expected both slayer call sites, found {len(calls)}"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        assert 'mechanics' in kw, f"line {call.lineno} passes no mechanics"
        val = kw['mechanics']
        assert (isinstance(val, ast.Attribute) and val.attr == 'mechanics'
                and isinstance(val.value, ast.Name) and val.value.id == 'args'), \
            f"line {call.lineno} does not pass args.mechanics"
