"""
Regression tests for ``_find_losses_vs_general`` in
``scripts/deep_dive_narrative.py``. Vectorised with numpy in S8a;
this pins the observable output (``{opponent: {(s0,s1), ...}}``)
against a frozen pure-Python reference.
"""
from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# deep_dive_narrative imports sibling scripts by plain name, so add the
# scripts dir to sys.path before importing it.
sys.path.insert(0, str(SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location(
    "deep_dive_narrative", SCRIPTS_DIR / "deep_dive_narrative.py")
narrative = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(narrative)

_analysis_spec = importlib.util.spec_from_file_location(
    "deep_dive_analysis", SCRIPTS_DIR / "deep_dive_analysis.py")
analysis = importlib.util.module_from_spec(_analysis_spec)
assert _analysis_spec.loader is not None
_analysis_spec.loader.exec_module(analysis)


def _reference_find_losses(flavor, general, data_obj, score_arrays,
                           moveset_idx, scenarios, opponents):
    """Pre-S8a pure-Python implementation, frozen as the oracle."""
    nIvs = data_obj.get('nIvs', 0)
    nS = len(scenarios)
    nO = len(opponents)
    flavor_ivs = []
    general_only_ivs = []
    for iv in range(nIvs):
        meets_flavor = True
        meets_general = True
        if flavor['atk_cut'] > 0 and data_obj['ivAtk'][iv] < flavor['atk_cut']:
            meets_flavor = False
        if flavor['def_cut'] > 0 and data_obj['ivDef'][iv] < flavor['def_cut']:
            meets_flavor = False
        if flavor['hp_cut'] > 0 and data_obj['ivHp'][iv] < flavor['hp_cut']:
            meets_flavor = False
        if general['atk_cut'] > 0 and data_obj['ivAtk'][iv] < general['atk_cut']:
            meets_general = False
        if general['def_cut'] > 0 and data_obj['ivDef'][iv] < general['def_cut']:
            meets_general = False
        if general['hp_cut'] > 0 and data_obj['ivHp'][iv] < general['hp_cut']:
            meets_general = False
        if meets_flavor:
            flavor_ivs.append(iv)
        elif meets_general:
            general_only_ivs.append(iv)
    if not flavor_ivs or not general_only_ivs:
        return {}
    losses = {}
    all_modes = data_obj.get('oppIvModes', ['pvpoke'])
    for mode in all_modes:
        key = f'{moveset_idx}_{mode}'
        scores_flat = score_arrays.get(key, [])
        if not scores_flat:
            continue
        for si, scen in enumerate(scenarios):
            for oi, opp in enumerate(opponents):
                flavor_wr = sum(
                    1 for iv in flavor_ivs
                    if scores_flat[iv * nS * nO + si * nO + oi] > 500
                ) / len(flavor_ivs)
                general_wr = sum(
                    1 for iv in general_only_ivs
                    if scores_flat[iv * nS * nO + si * nO + oi] > 500
                ) / len(general_only_ivs)
                if general_wr >= 0.75 and flavor_wr <= 0.25:
                    losses.setdefault(opp, set()).add(tuple(scen))
    return losses


# Per-cell win rules: (stat, op, cut). An IV wins that (mode, scenario,
# opponent) cell iff its stat compares true against the cut. The function
# under test looks for cells the GENERAL-but-not-flavor IVs win while the
# flavor IVs lose, so the table has to contain rules that run AGAINST the
# flavor cutoffs ('lt' rules) — a table of only 'ge' rules rewards the
# flavor spread everywhere and the gate never fires. The 'ge' rules are
# kept as negative controls (they must NOT produce records).
_WIN_RULES = [
    ('def', 'lt', 145.0),
    ('atk', 'lt', 130.0),
    ('def', 'ge', 145.0),
    ('hp', 'lt', 140),
    ('atk', 'lt', 135.0),
    ('def', 'ge', 130.0),
    ('atk', 'ge', 135.0),
]


def _make_inputs(seed, nIvs=256, nS=9, nO=5, modes=('pvpoke', 'rank1')):
    """Random inputs whose SCORES are coupled to the IV stats being cut on.

    The pre-2026-08-09 version drew scores as i.i.d. ``randint(0, 1000)``,
    independent of ivAtk/ivDef/ivHp. Both winrates then sat at ~0.50 and
    the ``general_wr >= 0.75 and flavor_wr <= 0.25`` conjunction never
    fired: the oracle produced 0 records in 15/15 (seed x flavor) cases,
    so every comparison below was {} == {} and the file passed with the
    production function replaced by ``lambda *a, **k: {}``.

    Scores are now generated the way tests/test_matchup_boundaries.py does
    it (win is a function of the swept stat, plus ~6% noise), with a
    per-cell rule table that includes cells the flavor spread LOSES —
    which is the only shape this function can report.
    """
    rng = random.Random(seed)
    scenarios = [[s0, s1] for s0 in range(3) for s1 in range(3)][:nS]
    opponents = [f'OPP_{i}' for i in range(nO)]
    iv_atk = [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)]
    iv_def = [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)]
    iv_hp = [rng.randint(100, 200) for _ in range(nIvs)]
    data_obj = {
        'nIvs': nIvs,
        'ivAtk': iv_atk,
        'ivDef': iv_def,
        'ivHp': iv_hp,
        'oppIvModes': list(modes),
    }
    by_stat = {'atk': iv_atk, 'def': iv_def, 'hp': iv_hp}
    score_arrays = {}
    for mi, mode in enumerate(modes):
        flat = []
        for iv in range(nIvs):
            for si in range(nS):
                for oi in range(nO):
                    stat, op, cut = _WIN_RULES[
                        (si * nO + oi + mi) % len(_WIN_RULES)]
                    val = by_stat[stat][iv]
                    win = val < cut if op == 'lt' else val >= cut
                    if rng.random() < 0.06:   # ~6% noise, as in the sibling
                        win = not win         # boundaries fixture
                    flat.append(700 if win else 300)
        score_arrays[f'0_{mode}'] = flat
    return data_obj, score_arrays, scenarios, opponents


def test_matches_reference_random_inputs():
    for seed in range(5):
        data_obj, score_arrays, scenarios, opponents = _make_inputs(seed)
        analysis._invalidate_np_caches()
        general = {'atk_cut': 0.0, 'def_cut': 140.0, 'hp_cut': 130}
        # The third spec used to be def_cut=150.0, above the fixture's IV
        # ceiling — it partitioned to an empty flavor group and returned {}
        # before reaching a single winrate gate. The no-passers path has
        # its own test below (test_empty_when_flavor_cut_excludes_everyone);
        # here every spec must be reachable. This one is atk-only so the
        # atk leg of the cut logic is exercised too.
        flavor_specs = [
            {'atk_cut': 0.0, 'def_cut': 145.0, 'hp_cut': 140},
            {'atk_cut': 130.0, 'def_cut': 140.0, 'hp_cut': 135},
            {'atk_cut': 135.0, 'def_cut': 0.0, 'hp_cut': 0},
        ]
        for flavor in flavor_specs:
            ref = _reference_find_losses(
                flavor, general, data_obj, score_arrays, 0,
                scenarios, opponents)
            # Anti-vacuity: {} == {} proves nothing. Measured floor over
            # seeds 0..19 x these 3 flavors is 4 opponents / 6 scenario
            # entries (typical 5 opponents / 13-26 entries).
            assert ref, (
                f'oracle produced no losses for seed={seed} flavor={flavor} '
                f'— fixture no longer exercises the winrate gate, so the '
                f'parity check below is vacuous')
            got = narrative._find_losses_vs_general(
                flavor, general, data_obj, score_arrays, 0,
                scenarios, opponents)
            assert ref == got, (
                f'seed={seed} flavor={flavor} ref={ref} got={got}')


def _reachable_flavor_control(data_obj, score_arrays, scenarios, opponents):
    """The same fixture DOES report losses for a reachable flavor cut.

    Without this, `got == {}` below is satisfied by any function that
    always returns {} — which is exactly how this file used to pass with
    the production implementation gutted.
    """
    analysis._invalidate_np_caches()
    control = narrative._find_losses_vs_general(
        {'atk_cut': 0.0, 'def_cut': 145.0, 'hp_cut': 140},
        {'atk_cut': 0.0, 'def_cut': 140.0, 'hp_cut': 130},
        data_obj, score_arrays, 0, scenarios, opponents)
    assert control, 'control flavor produced no losses — fixture is dead'


def test_empty_when_flavor_cut_catches_all_ivs():
    data_obj, score_arrays, scenarios, opponents = _make_inputs(0)
    _reachable_flavor_control(data_obj, score_arrays, scenarios, opponents)
    analysis._invalidate_np_caches()
    # Flavor cut = general cut, so general_only is empty
    general = {'atk_cut': 0.0, 'def_cut': 140.0, 'hp_cut': 130}
    flavor = dict(general)
    got = narrative._find_losses_vs_general(
        flavor, general, data_obj, score_arrays, 0, scenarios, opponents)
    assert got == {}


def test_empty_when_flavor_cut_excludes_everyone():
    data_obj, score_arrays, scenarios, opponents = _make_inputs(0)
    _reachable_flavor_control(data_obj, score_arrays, scenarios, opponents)
    analysis._invalidate_np_caches()
    general = {'atk_cut': 0.0, 'def_cut': 100.0, 'hp_cut': 100}
    flavor = {'atk_cut': 0.0, 'def_cut': 999.0, 'hp_cut': 0}  # no passers
    got = narrative._find_losses_vs_general(
        flavor, general, data_obj, score_arrays, 0, scenarios, opponents)
    assert got == {}


def test_missing_mode_scores_skip_but_dont_crash():
    data_obj, score_arrays, scenarios, opponents = _make_inputs(0)
    del score_arrays['0_rank1']
    analysis._invalidate_np_caches()
    general = {'atk_cut': 0.0, 'def_cut': 140.0, 'hp_cut': 130}
    flavor = {'atk_cut': 0.0, 'def_cut': 145.0, 'hp_cut': 140}
    ref = _reference_find_losses(
        flavor, general, data_obj, score_arrays, 0, scenarios, opponents)
    assert ref, 'oracle produced no losses — comparison would be vacuous'
    got = narrative._find_losses_vs_general(
        flavor, general, data_obj, score_arrays, 0, scenarios, opponents)
    # No crash, and the surviving mode still contributes: the result
    # derives only from 0_pvpoke scores and matches the oracle.
    assert isinstance(got, dict)
    assert got == ref
