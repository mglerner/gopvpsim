"""Phase-6 regression: the ML IV-envelope path runs on the shared iv_sweep
engine (build_quadrant_grids) instead of its own per-call sim loop.

Pins (a) the grid structure won_set/score_set/result_metrics read, and (b)
that a grid cell matches a direct from_pokemon + simulate of the same matchup
(engine ground truth) — gamemaster-robust, recomputed from current data.
"""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# deep_dive must be importable under its own name (iv_envelope_analysis does
# `from deep_dive import ...`, and iv_sweep pickles its worker by module name).
if "deep_dive" not in sys.modules:
    _dd = importlib.util.spec_from_file_location(
        "deep_dive", REPO_ROOT / "scripts" / "deep_dive.py")
    _m = importlib.util.module_from_spec(_dd)
    sys.modules["deep_dive"] = _m
    _dd.loader.exec_module(_m)

import iv_envelope_analysis as iva  # noqa: E402

from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS  # noqa: E402
from gopvpsim.moves import get_moves  # noqa: E402
from gopvpsim.battle import simulate, pvpoke_dp, BattlePokemon  # noqa: E402
from gopvpsim.data import get_default_moveset  # noqa: E402
from gopvpsim.breakpoints import _get_types  # noqa: E402

FOCAL = 'Metagross'
OPP = 'Kyogre'
SHIELD = (1, 1)


def _opponents():
    f, c = get_default_moveset(OPP, league='master')
    return [{'display': OPP, 'base': OPP, 'shadow': False,
             'fast': f, 'charged': list(c)}]


def _build_grids(monkeypatch):
    monkeypatch.setattr(iva, 'FOCAL_SHADOW', False)
    monkeypatch.setattr(iva, 'SHIELDS', [SHIELD])  # one shield -> fast
    ff, fc = get_default_moveset(FOCAL, league='master')
    grids = iva.build_quadrant_grids(FOCAL, ff, list(fc), _opponents(),
                                     iv_floor=14, use_cache=False)
    return grids, ff, list(fc)


def test_grid_structure(monkeypatch):
    grids, _ff, _fc = _build_grids(monkeypatch)
    # One grid per quadrant.
    assert set(grids) == set(iva.QUADRANTS.values())
    g = grids[(51.0, 51.0)]
    # iv_floor=14 -> IVs {14,15} per stat -> 8 combos.
    assert len(g) == 8
    assert (15, 15, 15) in g
    cell = g[(15, 15, 15)][(OPP, SHIELD)]
    assert set(cell) == {'score', 'won', 'energy', 'hp', 'max_hp', 'shields'}
    assert isinstance(cell['won'], bool)
    assert 0 <= cell['energy'] <= 100
    assert 0 <= cell['hp'] <= cell['max_hp']
    assert 0 <= cell['shields'] <= 2


def test_grid_cell_matches_direct_sim(monkeypatch):
    grids, ff, fc = _build_grids(monkeypatch)
    cell = grids[(51.0, 51.0)][(15, 15, 15)][(OPP, SHIELD)]

    # Direct engine oracle: hundo focal vs hundo opp, both at L51 (wbb_vs_bb).
    fast_db, charged_db = get_moves()
    of, oc = get_default_moveset(OPP, league='master')
    p0 = Pokemon.at_best_level(FOCAL, 15, 15, 15, league='master', max_level=51.0)
    p1 = Pokemon.at_best_level(OPP, 15, 15, 15, league='master', max_level=51.0)
    bp0 = BattlePokemon.from_pokemon(
        p0, dict(fast_db[ff]), [dict(charged_db[c]) for c in fc],
        shields=SHIELD[0], league_cp=LEAGUE_CAPS['master'])
    bp1 = BattlePokemon.from_pokemon(
        p1, dict(fast_db[of]), [dict(charged_db[c]) for c in oc],
        shields=SHIELD[1], league_cp=LEAGUE_CAPS['master'])
    r = simulate(bp0, bp1, charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp)

    assert int(cell['score']) == int(r.pvpoke_score(0))
    assert cell['won'] == (r.pvpoke_score(0) > r.pvpoke_score(1))
    assert cell['hp'] == max(0, r.hp_remaining[0])
    assert cell['max_hp'] == r.max_hp[0]
    assert cell['shields'] == r.shields_remaining[0]
    assert cell['energy'] == r.energy_remaining[0]
