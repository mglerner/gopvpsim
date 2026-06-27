"""Sweep disk cache + replay state tests (arc S4, 2026-06-10).

The sweep cache (scripts/sweep_cache.py) stores per-opponent score
columns keyed by (focal moveset/league/scenarios/bait/engine/gamemaster)
x (opponent species/shadow/resolved IVs/moveset). These tests pin:

- SweepCache put/get roundtrip, shape validation, and key separation.
- iv_sweep end-to-end: a second identical run is all-hits (0 sims) and
  bit-identical; a pool edit sims only the new column; cached results
  match a no-cache run exactly.
- dump_replay_state / load_replay_state roundtrip.
"""
import importlib.util
import multiprocessing
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Load deep_dive.py as a module (it's a script, not a package); this
# puts scripts/ on sys.path so `import sweep_cache` resolves to the
# same module object iv_sweep imports lazily. Registering in
# sys.modules BEFORE exec is required here (unlike the other dive
# tests): iv_sweep's pool pickles _sweep_worker by module name, and
# pickle must find this exact module object under "deep_dive".
# Get-or-create (shared contract with test_energy_lead.py): a second
# exec would rebind the name and break worker pickling for whichever
# test file bound it first.
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

from gopvpsim.data import get_default_moveset  # noqa: E402

LEAGUE = 'great'
SCENARIOS = [(0, 0), (1, 1)]
IV_FLOOR = (14, 14, 14)  # 8 IVs — keeps the pool sweeps fast
# Leave only 2 worker processes; the sweeps here are a handful of sims
# and pool spawn time dominates otherwise.
RESERVE = max(0, multiprocessing.cpu_count() - 2)


def _focal_fields(**overrides):
    fields = dict(species='Azumarill', league=LEAGUE, shadow=False,
                  fast_id='BUBBLE', charged_ids=['ICE_BEAM', 'PLAY_ROUGH'],
                  iv_floor=IV_FLOOR, shield_scenarios=SCENARIOS,
                  bait_mode='bait')
    fields.update(overrides)
    return sweep_cache.focal_key_fields(**fields)


def _col_fields(**overrides):
    fields = dict(opp_species='Medicham', opp_shadow=False,
                  opp_ivs=(7, 15, 14), opp_level=49.0,
                  opp_fast_id='COUNTER',
                  opp_charged_ids=['ICE_PUNCH', 'PSYCHIC'])
    fields.update(overrides)
    return sweep_cache.column_key_fields(**fields)


def test_column_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    cache = sweep_cache.SweepCache(_focal_fields())
    col_key = _col_fields()
    assert cache.get_column(col_key, 8, 2) is None  # cold miss

    score = np.arange(16, dtype=np.float64).reshape(8, 2) + 0.25
    energy = (np.arange(16, dtype=np.float64).reshape(8, 2) % 101)
    cache.put_column(col_key, {'score': score, 'energy': energy})

    # A fresh instance with the same focal fields reads both planes back exactly.
    cache2 = sweep_cache.SweepCache(_focal_fields())
    got = cache2.get_column(col_key, 8, 2)
    assert got is not None
    assert np.array_equal(got['score'], score)
    assert np.array_equal(got['energy'], energy)  # uint8 round-trip of 0..100
    # Human-readable sidecars exist for debugging.
    assert (cache2.dir / 'meta.json').exists()


def test_energy_out_of_range_is_no_store(tmp_path, monkeypatch):
    # Energy must be a bounded battle output (0..100); an out-of-range plane
    # fails the store assert (best-effort -> no-store), so the next get misses
    # rather than silently wrapping into uint8.
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    cache = sweep_cache.SweepCache(_focal_fields())
    col_key = _col_fields()
    cache.put_column(col_key, {'score': np.zeros((8, 2)),
                               'energy': np.full((8, 2), 200.0)})
    assert cache.get_column(col_key, 8, 2) is None


def test_stale_engine_stamp_is_miss(tmp_path, monkeypatch):
    # v6: a column stamped with a different engine hash must miss (and not
    # even load the .npz), so a stale-engine column is never served.
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'engine_aaaa')
    cache = sweep_cache.SweepCache(_focal_fields())
    col_key = _col_fields()
    cache.put_column(col_key, {'score': np.zeros((8, 2)),
                               'energy': np.zeros((8, 2))})
    # Same engine -> hit.
    assert cache.get_column(col_key, 8, 2) is not None
    # Engine changes -> the existing column is now stale -> miss.
    monkeypatch.setattr(sweep_cache, '_ENGINE_HASH', 'engine_bbbb')
    assert sweep_cache.SweepCache(_focal_fields()).get_column(col_key, 8, 2) is None


def test_shape_mismatch_is_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    cache = sweep_cache.SweepCache(_focal_fields())
    col_key = _col_fields()
    cache.put_column(col_key, {'score': np.zeros((8, 2)),
                               'energy': np.zeros((8, 2))})
    # Requesting a different scenario count or IV count must miss.
    assert cache.get_column(col_key, 8, 9) is None
    assert cache.get_column(col_key, 4096, 2) is None


def test_key_separation(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    base = sweep_cache.SweepCache(_focal_fields())
    # Any focal-side field change lands in a different directory.
    for other in (_focal_fields(bait_mode='nobait'),
                  _focal_fields(shadow=True),
                  _focal_fields(charged_ids=['ICE_BEAM']),
                  _focal_fields(shield_scenarios=[(1, 1)]),
                  _focal_fields(iv_floor=None),
                  _focal_fields(focal_max_level=51.0)):  # best-buddy L51 != default L50
        assert sweep_cache.SweepCache(other).dir != base.dir
    # Any column-side field change lands in a different file.
    base_path = base._col_path(_col_fields())
    for other in (_col_fields(opp_ivs=(0, 15, 15)),
                  _col_fields(opp_shadow=True),
                  _col_fields(opp_charged_ids=['ICE_PUNCH']),
                  _col_fields(opp_level=48.5)):
        assert base._col_path(other) != base_path


def _run_sweep(opponents, opp_movesets, use_cache):
    return deep_dive.iv_sweep(
        'Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], LEAGUE, False,
        opponents, opp_movesets, SCENARIOS,
        iv_floor=IV_FLOOR, reserve_cpus=RESERVE,
        use_sweep_cache=use_cache,
    )[:4]


def test_iv_sweep_cache_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    med_moveset = get_default_moveset('Medicham', LEAGUE)
    azu_moveset = get_default_moveset('Azumarill', LEAGUE)
    opponents = ['Medicham']
    opp_movesets = [med_moveset]

    # Ground truth: no cache involved at all.
    res_ref, n_ref, cs_ref, cm_ref = _run_sweep(opponents, opp_movesets,
                                                use_cache=False)
    assert n_ref > 0

    # Cold cached run sims everything and matches the no-cache run.
    res1, n1, cs1, cm1 = _run_sweep(opponents, opp_movesets, use_cache=True)
    assert n1 == n_ref
    assert cs1 == cs_ref
    assert cm1 == cm_ref
    assert [r['avg_score'] for r in res1] == [r['avg_score'] for r in res_ref]

    # Identical re-run: all columns hit, zero sims, bit-identical output.
    res2, n2, cs2, cm2 = _run_sweep(opponents, opp_movesets, use_cache=True)
    assert n2 == 0
    assert cs2 == cs1
    assert cm2 == cm1
    assert [r['avg_score'] for r in res2] == [r['avg_score'] for r in res1]
    raw1 = [(r['atk_iv'], r['def_iv'], r['sta_iv'],
             sorted(r['per_opp'].items())) for r in res1]
    raw2 = [(r['atk_iv'], r['def_iv'], r['sta_iv'],
             sorted(r['per_opp'].items())) for r in res2]
    assert raw1 == raw2

    # Pool edit: adding an opponent sims ONLY the new column, and the
    # combined result matches a fresh no-cache run of the bigger pool.
    opponents2 = ['Medicham', 'Azumarill']
    opp_movesets2 = [med_moveset, azu_moveset]
    res3, n3, cs3, cm3 = _run_sweep(opponents2, opp_movesets2,
                                    use_cache=True)
    assert n3 > 0
    ref3 = _run_sweep(opponents2, opp_movesets2, use_cache=False)
    assert cs3 == ref3[2]
    # The incremental run skipped exactly the cached Medicham column.
    assert ref3[1] - n3 == n_ref


def _run_sweep_energy(opponents, opp_movesets, use_cache):
    """5-tuple sweep with energy captured (returns canonical_scores +
    canonical_energy at indices 2 and 4)."""
    return deep_dive.iv_sweep(
        'Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], LEAGUE, False,
        opponents, opp_movesets, SCENARIOS,
        iv_floor=IV_FLOOR, reserve_cpus=RESERVE,
        use_sweep_cache=use_cache, capture_energy=True,
    )


def test_iv_sweep_energy_warm_cold_bit_identical(tmp_path, monkeypatch):
    # The v5 cache stores an energy plane, so a --compare-energy dive serves
    # warm (previously it force-disabled the cache). Warm energy must be
    # bit-identical to cold, and to a no-cache run.
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    med_moveset = get_default_moveset('Medicham', LEAGUE)
    opponents = ['Medicham']
    opp_movesets = [med_moveset]

    # No-cache ground truth (energy captured).
    _, n_ref, cs_ref, _, ce_ref = _run_sweep_energy(opponents, opp_movesets,
                                                     use_cache=False)
    assert n_ref > 0
    assert ce_ref is not None and len(ce_ref) == len(cs_ref)
    assert all(0 <= e <= 100 for e in ce_ref)

    # Cold cached run: sims everything, stores both planes, matches no-cache.
    _, n1, cs1, _, ce1 = _run_sweep_energy(opponents, opp_movesets,
                                           use_cache=True)
    assert n1 == n_ref
    assert cs1 == cs_ref
    assert ce1 == ce_ref

    # Warm run: cache hit (0 sims), energy bit-identical to cold.
    _, n2, cs2, _, ce2 = _run_sweep_energy(opponents, opp_movesets,
                                           use_cache=True)
    assert n2 == 0
    assert cs2 == cs1
    assert ce2 == ce1


def _run_sweep_metrics(opponents, opp_movesets, use_cache):
    """Sweep with the full ML metric capture (won/hp/max_hp/shields) on."""
    return deep_dive.iv_sweep(
        'Azumarill', 'BUBBLE', ['ICE_BEAM', 'PLAY_ROUGH'], LEAGUE, False,
        opponents, opp_movesets, SCENARIOS,
        iv_floor=IV_FLOOR, reserve_cpus=RESERVE,
        use_sweep_cache=use_cache, capture_energy=True, capture_metrics=True)


def _metric_grid(results):
    """{(a,d,s): {(metric, si, oi): value}} for stable cold/warm comparison."""
    out = {}
    for r in results:
        cell = {}
        for m in ('won', 'hp', 'max_hp', 'shields'):
            for k, v in r['per_opp_' + m].items():
                cell[(m, *k)] = v
        out[(r['atk_iv'], r['def_iv'], r['sta_iv'])] = cell
    return out


def test_iv_sweep_metrics_warm_cold_bit_identical(tmp_path, monkeypatch):
    # The ML guide path caches won/hp/max_hp/shields planes so its warm
    # re-bake re-sims nothing. Warm metrics must be bit-identical to cold and
    # to a no-cache run.
    monkeypatch.setattr(sweep_cache, 'CACHE_DIR', tmp_path)
    med_moveset = get_default_moveset('Medicham', LEAGUE)
    opponents = ['Medicham']
    opp_movesets = [med_moveset]

    res_ref = _run_sweep_metrics(opponents, opp_movesets, use_cache=False)[0]
    g_ref = _metric_grid(res_ref)
    # Sanity on the captured fields.
    for cell in g_ref.values():
        for (m, _si, _oi), v in cell.items():
            if m == 'won':
                assert v in (True, False)
            elif m == 'shields':
                assert 0 <= int(v) <= 2
            elif m in ('hp', 'max_hp'):
                assert int(v) >= 0
    for (a, d, s), cell in g_ref.items():
        for si in range(len(SCENARIOS)):
            assert cell[('hp', si, 0)] <= cell[('max_hp', si, 0)]

    res_cold, n_cold = _run_sweep_metrics(opponents, opp_movesets,
                                          use_cache=True)[:2]
    assert _metric_grid(res_cold) == g_ref

    res_warm, n_warm = _run_sweep_metrics(opponents, opp_movesets,
                                          use_cache=True)[:2]
    assert n_warm == 0  # all columns hit (metric planes present)
    assert _metric_grid(res_warm) == g_ref


def test_replay_state_roundtrip(tmp_path):
    state = {
        'species': 'Azumarill', 'league': LEAGUE, 'shadow': False,
        'html_path': '/tmp/x.html', 'split_movesets': False,
        'moveset_data': [{'label': 'BUBBLE / ICE_BEAM',
                          'scores': {'pvpoke': [500, 250]},
                          'meta': [(0, 15, 15, 22.5, 1497,
                                    90.0, 120.0, 140)]}],
        'reference_idx': -1,
    }
    path = str(tmp_path / 'roundtrip.replay.pkl.gz')
    written = deep_dive.dump_replay_state(state, path)
    assert written == path
    loaded = deep_dive.load_replay_state(path)
    assert loaded == state


def test_replay_dump_default_path_is_userdata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = {'species': 'Aegislash (Shield)', 'league': 'great',
             'shadow': True, 'x': 1}
    path = deep_dive.dump_replay_state(state)
    assert path is not None
    assert path.startswith('userdata/replay/')
    assert path.endswith('_Aegislash_Shield_great_shadow.replay.pkl.gz')
    assert deep_dive.load_replay_state(path) == state
