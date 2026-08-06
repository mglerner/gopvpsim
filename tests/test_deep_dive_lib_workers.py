"""Spawn-mode worker resolution after the entry-12 deep_dive.py split.

The dive's process pool pickles its entry points BY QUALIFIED NAME (June
review section G, invariant 22).  The split moved them from ``deep_dive``
into ``deep_dive_lib.sweep``, which CHANGES that name: a module-attribute
re-export on ``deep_dive`` is enough for callers, but it does not make the
old qualified name resolve in a child process.  That cannot be settled by
reasoning, so these tests run a REAL spawn pool and compare its output with
an in-process call of the same worker.

Also pins the two things the child depends on: ``deep_dive_lib.sweep`` must
import WITHOUT ``deep_dive`` (the child never loads the by-path script), and
``deep_dive_slayer``'s parent-side ``compute_iv_metadata`` injection must
still land on the moved function.
"""
import multiprocessing
import pickle
import subprocess
import sys
from pathlib import Path

from tests.conftest import load_deep_dive

REPO_ROOT = Path(__file__).resolve().parents[1]

deep_dive = load_deep_dive()

import deep_dive_slayer  # noqa: E402  (importable after deep_dive's sys.path insert)
from deep_dive_lib import sweep as sweep_mod  # noqa: E402

from gopvpsim.data import load_gamemaster, parse_types  # noqa: E402
from gopvpsim.moves import get_moves  # noqa: E402
from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS  # noqa: E402

LEAGUE = 'great'
SPECIES = 'Azumarill'
FAST = 'BUBBLE'
CHARGED = ['ICE_BEAM', 'PLAY_ROUGH']
FOCAL_IVS = (0, 15, 15)
OPP_SPECIES = 'Medicham'
OPP_FAST = 'COUNTER'
OPP_CHARGED = ['ICE_PUNCH', 'PSYCHIC']
OPP_IVS = (0, 15, 15)
SCENARIOS = [(1, 1)]


def _mon(species):
    gm = load_gamemaster()
    return next(m for m in gm['pokemon'] if m['speciesName'] == species)


def _opp_cache():
    fast_db, charged_db = get_moves()
    mon = _mon(OPP_SPECIES)
    a, d, s = OPP_IVS
    pkm = Pokemon.at_best_level(OPP_SPECIES, a, d, s, league=LEAGUE)
    return [{
        'species': OPP_SPECIES, 'types': parse_types(mon),
        'atk': pkm.atk, 'def_': pkm.def_, 'hp': pkm.hp,
        'fm': dict(fast_db[OPP_FAST]),
        'cms': [dict(charged_db[c]) for c in OPP_CHARGED],
        'shadow': False,
        'mon': mon, 'ivs': OPP_IVS, 'level': pkm.level,
    }]


def _initargs(opp_cache):
    """Exactly the initargs tuple iv_sweep hands multiprocessing.Pool."""
    fast_db, charged_db = get_moves()
    focal_mon = _mon(SPECIES)
    return (SPECIES, parse_types(focal_mon),
            dict(fast_db[FAST]),
            [dict(charged_db[c]) for c in CHARGED],
            opp_cache, SCENARIOS, True,        # focal_bait
            None, False,                       # log_path, verbose
            focal_mon, LEAGUE_CAPS[LEAGUE], False,   # focal_mon, league_cp, shadow
            0, 'legacy', False)                # energy, mechanics, capture_metrics


def _chunk():
    a, d, s = FOCAL_IVS
    pkm = Pokemon.at_best_level(SPECIES, a, d, s, league=LEAGUE)
    pk = (round(pkm.atk, 4), round(pkm.def_, 4), int(pkm.hp), a, d, s,
          pkm.level)
    prof = (pk, pkm.atk, pkm.def_, pkm.hp, a, d, s, pkm.level)
    return [(prof, 0)]


def test_worker_qualified_names_moved_with_the_code():
    """The re-export is the SAME object; the qualified name is the lib one."""
    for name in ('_sweep_worker', '_sweep_worker_init'):
        shim = getattr(deep_dive, name)
        assert shim is getattr(sweep_mod, name)
        assert shim.__module__ == 'deep_dive_lib.sweep'
    assert pickle.loads(pickle.dumps(deep_dive._sweep_worker)) is \
        sweep_mod._sweep_worker


def test_sweep_worker_round_trips_through_a_real_spawn_pool():
    """A spawn child resolves deep_dive_lib.sweep._sweep_worker and returns
    the same scores as the in-process call."""
    opp_cache = _opp_cache()
    chunk = _chunk()

    deep_dive._sweep_worker_init(*_initargs(opp_cache))
    local_scores, local_energy, _metrics, local_sims = \
        deep_dive._sweep_worker(chunk)

    ctx = multiprocessing.get_context('spawn')
    with ctx.Pool(1, initializer=deep_dive._sweep_worker_init,
                  initargs=_initargs(opp_cache)) as pool:
        child_scores, child_energy, _child_metrics, child_sims = \
            pool.apply(deep_dive._sweep_worker, (chunk,))

    assert child_sims == local_sims == len(SCENARIOS)
    assert child_scores == local_scores
    assert child_energy == local_energy


def test_sweep_module_imports_without_deep_dive():
    """The child imports the LIB module, never the by-path deep_dive script.

    Run in a clean interpreter so an already-imported deep_dive in this
    process cannot mask a back-reference.
    """
    code = ('import sys; import deep_dive_lib.sweep as s; '
            'assert "deep_dive" not in sys.modules, sorted(sys.modules); '
            'print(s._sweep_worker.__module__)')
    out = subprocess.run(
        [sys.executable, '-c', code], capture_output=True, text=True,
        cwd=str(REPO_ROOT / 'scripts'))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == 'deep_dive_lib.sweep'


def test_slayer_worker_name_is_unchanged_and_injection_still_lands():
    """The slayer worker did NOT move (it already lived in
    deep_dive_slayer), but its parent-side compute_iv_metadata injection
    now has to reach the moved function."""
    assert deep_dive_slayer.slayer_iter_worker.__module__ == 'deep_dive_slayer'
    assert deep_dive_slayer.slayer_worker_init.__module__ == 'deep_dive_slayer'
    assert deep_dive_slayer.compute_iv_metadata is sweep_mod.compute_iv_metadata
