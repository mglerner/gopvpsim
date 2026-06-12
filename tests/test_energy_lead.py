"""Energy-lead sim axis tests (TODO "Energy-lead axis", shipped 2026-06-12).

The axis rides the composite mode string as ':eN' where N counts FAST
MOVES of stored energy (not raw energy points) so mode keys stay uniform
across movesets whose fast moves generate different energy. iv_sweep
converts N x the moveset's energyGain to raw starting energy, capped at
(100 - cheapest charged cost). These tests pin:

- parse_mode / parse_energy / compose_mode roundtrip + e0 collapse.
- The sweep cache focal key separates energy_lead values.
- iv_sweep with an energy mode actually changes outcomes, the cap
  makes over-the-cap multiples equivalent, and the worker's applied
  energy matches a direct single-sim with initial_energy set.
"""
import importlib.util
import multiprocessing
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Same loading pattern as test_sweep_cache.py: register under
# "deep_dive" BEFORE exec so the pool can pickle _sweep_worker by
# module name. Get-or-create: if another test module already
# registered "deep_dive", REUSE its module object — a second exec
# would rebind sys.modules["deep_dive"] to a different object and
# break pickle's identity check on _sweep_worker for whichever file
# bound first (the pool pickles workers by qualified name).
if "deep_dive" in sys.modules:
    deep_dive = sys.modules["deep_dive"]
else:
    DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"
    _spec = importlib.util.spec_from_file_location("deep_dive",
                                                   DEEP_DIVE_PATH)
    deep_dive = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    sys.modules["deep_dive"] = deep_dive
    _spec.loader.exec_module(deep_dive)

import sweep_cache  # noqa: E402

from gopvpsim.battle import pvpoke_dp, simulate  # noqa: E402
from gopvpsim.data import get_default_moveset  # noqa: E402

LEAGUE = 'great'
SCENARIOS = [(0, 0), (1, 1)]
IV_FLOOR = (14, 14, 14)  # 8 IVs — keeps sweeps fast
RESERVE = max(0, multiprocessing.cpu_count() - 2)

FOCAL = dict(species='Azumarill', fast_id='BUBBLE',
             charged_ids=['ICE_BEAM', 'PLAY_ROUGH'])


# ---- mode-string layer ------------------------------------------------------

def test_compose_collapses_defaults():
    assert deep_dive.compose_mode('pvpoke') == 'pvpoke'
    assert deep_dive.compose_mode('pvpoke', 'bait', 0) == 'pvpoke'
    assert deep_dive.compose_mode('pvpoke', 'nobait') == 'pvpoke:nobait'
    assert deep_dive.compose_mode('rank1', 'bait', 1) == 'rank1:e1'
    assert deep_dive.compose_mode('rank1', 'nobait', 2) == 'rank1:nobait:e2'


def test_parse_mode_ignores_energy_tag():
    assert deep_dive.parse_mode('pvpoke:e2') == ('pvpoke', 'bait')
    assert deep_dive.parse_mode('pvpoke:nobait:e1') == ('pvpoke', 'nobait')
    assert deep_dive.parse_mode('rank1:nobait') == ('rank1', 'nobait')
    assert deep_dive.parse_mode('rank1') == ('rank1', 'bait')


def test_parse_energy():
    assert deep_dive.parse_energy('pvpoke') == 0
    assert deep_dive.parse_energy('pvpoke:nobait') == 0
    assert deep_dive.parse_energy('pvpoke:e1') == 1
    assert deep_dive.parse_energy('rank1:nobait:e2') == 2
    assert deep_dive.parse_energy('pvpoke:e0') == 0


def test_roundtrip():
    for base in ('pvpoke', 'rank1'):
        for bait in ('bait', 'nobait'):
            for el in (0, 1, 2):
                mode = deep_dive.compose_mode(base, bait, el)
                assert deep_dive.parse_mode(mode) == (base, bait)
                assert deep_dive.parse_energy(mode) == el


def test_pretty_label_energy():
    lbl1 = deep_dive.mode_pretty_label('pvpoke:e1')
    lbl2 = deep_dive.mode_pretty_label('rank1:nobait:e2')
    assert '+1 fast move energy' in lbl1
    assert '+2 fast moves energy' in lbl2
    assert 'no bait' in lbl2


# ---- cache key --------------------------------------------------------------

def test_focal_key_separates_energy(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    fields = dict(species='Azumarill', league=LEAGUE, shadow=False,
                  fast_id='BUBBLE', charged_ids=['ICE_BEAM', 'PLAY_ROUGH'],
                  iv_floor=IV_FLOOR, shield_scenarios=SCENARIOS,
                  bait_mode='bait')
    base = sweep_cache.SweepCache(
        sweep_cache.focal_key_fields(**fields))
    lead = sweep_cache.SweepCache(
        sweep_cache.focal_key_fields(**fields, energy_lead=22))
    assert base.dir != lead.dir


# ---- sweep behavior ---------------------------------------------------------

def _run_sweep(mode):
    med_moveset = get_default_moveset('Medicham', LEAGUE)
    return deep_dive.iv_sweep(
        FOCAL['species'], FOCAL['fast_id'], FOCAL['charged_ids'],
        LEAGUE, False,
        ['Medicham'], [med_moveset], SCENARIOS,
        opp_iv_mode=mode,
        iv_floor=IV_FLOOR, reserve_cpus=RESERVE,
        use_sweep_cache=False,
    )


def _per_opp(results):
    return [(r['atk_iv'], r['def_iv'], r['sta_iv'],
             sorted(r['per_opp'].items())) for r in results]


def test_energy_axis_changes_scores_and_caps():
    fast_db, charged_db = deep_dive.get_moves()
    eg = fast_db['BUBBLE']['energyGain']
    cap = 100 - min(charged_db[c]['energy'] for c in FOCAL['charged_ids'])
    assert eg > 0 and cap > 0

    res_cold = _run_sweep('pvpoke')
    res_e0 = _run_sweep('pvpoke:e0')
    res_e2 = _run_sweep('pvpoke:e2')

    # e0 is the cold start, bit-identical.
    assert _per_opp(res_e0[0]) == _per_opp(res_cold[0])
    assert res_e0[2] == res_cold[2]

    # Two fast moves of lead must change at least one outcome.
    assert _per_opp(res_e2[0]) != _per_opp(res_cold[0])

    # Multiples past the reachable cap are equivalent: both resolve to
    # the capped raw energy. m_cap is the smallest multiple that
    # exceeds the cap; m_cap+4 is comfortably past it.
    m_cap = cap // eg + 1
    res_at_cap = _run_sweep(f'pvpoke:e{m_cap}')
    res_past_cap = _run_sweep(f'pvpoke:e{m_cap + 4}')
    assert _per_opp(res_at_cap[0]) == _per_opp(res_past_cap[0])
    assert res_at_cap[2] == res_past_cap[2]


def test_worker_energy_matches_direct_sim():
    """The pool worker's applied starting energy must match a direct
    simulate() with initial_energy set — catches plumbing breaks where
    the mode parses but the worker never applies it."""
    fast_db, _ = deep_dive.get_moves()
    eg = fast_db['BUBBLE']['energyGain']

    results, _, _, _ = deep_dive.iv_sweep(
        FOCAL['species'], FOCAL['fast_id'], FOCAL['charged_ids'],
        LEAGUE, False,
        ['Medicham'], [get_default_moveset('Medicham', LEAGUE)],
        [(1, 1)],
        opp_iv_mode='pvpoke:e2',
        iv_floor=(15, 15, 15), reserve_cpus=RESERVE,
        use_sweep_cache=False,
    )
    assert len(results) == 1
    sweep_score = results[0]['per_opp'][(0, 0)]

    oa, od, os_ = deep_dive.resolve_opp_ivs('Medicham', LEAGUE, False,
                                            'pvpoke')
    med_fast, med_charged = get_default_moveset('Medicham', LEAGUE)
    bp0 = deep_dive.make_battle_pokemon(
        FOCAL['species'], FOCAL['fast_id'], FOCAL['charged_ids'],
        LEAGUE, 1, 15, 15, 15)
    bp0.initial_energy = 2 * eg
    bp0.energy = 2 * eg
    bp1 = deep_dive.make_battle_pokemon(
        'Medicham', med_fast, list(med_charged), LEAGUE, 1, oa, od, os_)
    result = simulate(bp0, bp1,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp)
    assert result.pvpoke_score(0) == sweep_score
