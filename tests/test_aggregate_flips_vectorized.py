"""Parity pin for the 2026-09-25 vectorisation of aggregate_flips_by_anchor.

The aggregator was ~2 s per call on a 2,424-anchor UL dive and ran 8 times
per render pass (docs/perf/2026-09-25 bake attribution, R2). The rewrite
builds the win matrix once, counts pass-side wins with one mask @ matrix
product per anchor, and does the HP co-condition search as one reversed
cumulative sum over the HP-sorted passing IVs instead of a masked sum per
floor. It is a perf refactor: the records must be IDENTICAL.

``_reference`` below is the pre-vectorisation implementation, copied
verbatim from scripts/deep_dive_analysis.py at 3db37f0 (only its docstring
dropped and three non-ASCII comment glyphs spelled out). It lives here, not
in production, because nothing but this test may call it. The comparison
is exact: same record count and order, the SAME anchor object, and every
other field (scenarios, hp_threshold, passing_ivs, key order) equal, plus
equal debug_stats.

The known hazards are pinned by construction in the synthetic fixture: HP
floors that clean, then stay clean, then stop (the descending scan's
"relax until unclean" break), strict thresholds sitting exactly on an IV's
stat (``>`` vs ``>=``), exact-500 ties (not wins), duplicate HP values,
unknown / blank / lower-cased opponent names, and a data_obj with no ivHp
(the anchor-clear overlay's stub, deep_dive.py). The real-blob test runs
both implementations on moveset 0 of a production replay blob.
"""
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from tests.conftest import load_deep_dive

deep_dive = load_deep_dive()                      # puts scripts/ on sys.path
import deep_dive_analysis as analysis             # noqa: E402
from gopvpsim.battle import WIN_RATING            # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _reference(scores_flat, nIvs, nS, nO,
               resolved_anchors, data_obj, scenarios, opponents,
               win_threshold=WIN_RATING,
               pass_winrate_min=0.75, fail_winrate_max=0.25,
               debug_stats=None):
    # Build case-insensitive opponent index lookup so TOML and opponent-list
    # naming differences (Annihilape vs annihilape) don't silently drop hits.
    opp_idx_by_name = {}
    for oi, name in enumerate(opponents):
        opp_idx_by_name[name] = oi
        opp_idx_by_name[name.lower()] = oi

    # Counters so callers can diagnose why an anchor list produced few bullets.
    stats = {
        'considered': 0, 'no_opponent': 0, 'unknown_opponent': 0,
        'trivial_partition': 0, 'no_clean_scenario': 0, 'emitted': 0,
    }

    # Vectorise: reshape scores once, evaluate each anchor's partition via
    # boolean masks over the IV dim, collapse win counts over scenarios.
    # Without this the HP co-condition search dominates narrative compute
    # (see S8a profile 2026-04-17: 236s / 86% of narrative on a 1-moveset
    # Oinkologne dive was concentrated in the per-anchor HP sweep).
    scores_np = np.asarray(scores_flat).reshape(nIvs, nS, nO)
    iv_atk_np = np.asarray(data_obj['ivAtk'])
    iv_def_np = np.asarray(data_obj['ivDef'])
    hp_raw = data_obj.get('ivHp') or []
    iv_hp_np = np.asarray(hp_raw) if len(hp_raw) else None

    records = []
    for anchor in resolved_anchors:
        stats['considered'] += 1
        if not anchor.opponent:
            stats['no_opponent'] += 1
            continue
        oi = opp_idx_by_name.get(anchor.opponent)
        if oi is None:
            oi = opp_idx_by_name.get(anchor.opponent.lower())
        if oi is None:
            stats['unknown_opponent'] += 1
            continue

        stat_vals = iv_atk_np if anchor.target_stat == 'atk' else iv_def_np
        if anchor.strict:
            passing_mask = stat_vals > anchor.threshold_value
        else:
            passing_mask = stat_vals >= anchor.threshold_value
        n_pass = int(passing_mask.sum())
        n_fail = nIvs - n_pass
        if n_pass == 0 or n_fail == 0:
            stats['trivial_partition'] += 1
            continue

        wins_for_opp = scores_np[:, :, oi] > win_threshold  # (nIvs, nS); 500 = tie
        pw = wins_for_opp[passing_mask].sum(axis=0) / n_pass
        fw = wins_for_opp[~passing_mask].sum(axis=0) / n_fail
        clean = (pw >= pass_winrate_min) & (fw <= fail_winrate_max)

        if clean.any():
            flipped_scenarios = [scenarios[si] for si in np.where(clean)[0]]
            stats['emitted'] += 1
            records.append({
                'anchor': anchor,
                'opponent': anchor.opponent,
                'scenarios': flipped_scenarios,
                'direction': 'gain',
                'hp_threshold': None,
                # Canonical IV indices that pass this anchor. Used by
                # the interactive scatter plot's anchor-clear overlay
                # to highlight which spreads actually clear an emitted
                # anchor (separate from the bullet text rendering).
                'passing_ivs': np.where(passing_mask)[0].tolist(),
            })
            continue

        # -- HP co-condition search for def-side anchors --
        # When a def partition alone isn't clean, try adding an HP floor
        # to tighten the passing set. Iterate unique HPs within the
        # passing set from highest to lowest -- first clean scenario gives
        # the tightest useful floor; keep relaxing until clean disappears
        # to find the minimum HP.
        if (anchor.target_stat == 'def' and n_pass > 1
                and iv_hp_np is not None):
            pass_hps = sorted(set(iv_hp_np[passing_mask].tolist()))
            best_hp = None
            best_scenarios = []
            for hp_floor in reversed(pass_hps):
                sub_pass_mask = passing_mask & (iv_hp_np >= hp_floor)
                n_sp = int(sub_pass_mask.sum())
                n_sf = nIvs - n_sp
                if n_sp == 0 or n_sf == 0:
                    continue
                # sub_fail = failing OR (passing AND hp_low), which is
                # ~sub_pass_mask because sub_pass_mask = passing AND hp_ok,
                # so ~sub_pass_mask = failing OR (passing AND hp_low).
                # Equivalent to the original.
                spw = wins_for_opp[sub_pass_mask].sum(axis=0) / n_sp
                sfw = wins_for_opp[~sub_pass_mask].sum(axis=0) / n_sf
                hp_clean = (spw >= pass_winrate_min) & (sfw <= fail_winrate_max)
                if hp_clean.any():
                    best_hp = hp_floor
                    best_scenarios = [scenarios[si]
                                      for si in np.where(hp_clean)[0]]
                else:
                    if best_hp is not None:
                        break
            if best_hp is not None and best_scenarios:
                stats['emitted'] += 1
                pass_and_hp_mask = passing_mask & (iv_hp_np >= best_hp)
                records.append({
                    'anchor': anchor,
                    'opponent': anchor.opponent,
                    'scenarios': best_scenarios,
                    'direction': 'gain',
                    'hp_threshold': best_hp,
                    'passing_ivs': np.where(pass_and_hp_mask)[0].tolist(),
                })
                continue
        stats['no_clean_scenario'] += 1

    if debug_stats is not None:
        debug_stats.update(stats)
    return records


def _assert_identical(want, got):
    assert len(got) == len(want)
    for w, g in zip(want, got):
        assert g['anchor'] is w['anchor']
        assert list(g) == list(w)                          # key order
        for k in w:
            if k != 'anchor':
                assert g[k] == w[k], (k, w['anchor'], w[k], g[k])
                assert type(g[k]) is type(w[k]), k


def _run_both(*args):
    ws, gs = {}, {}
    want = _reference(*args, debug_stats=ws)
    got = analysis.aggregate_flips_by_anchor(*args, debug_stats=gs)
    _assert_identical(want, got)
    assert gs == ws
    return want, ws


@dataclass(eq=False)                       # identity, like ResolvedAnchor
class _Anchor:
    name: str
    opponent: str
    target_stat: str
    threshold_value: float
    strict: bool = False


def _synthetic(seed, nIvs=300, nS=9, nO=6):
    """Scores coupled to def (with an HP co-condition on some opponents)
    or atk, ~6% noise, exact-500 ties on odd opponents, and a random pool of
    anchors spanning the stat range -- including thresholds that sit exactly
    on an IV's stat, so ``strict`` is observable."""
    rng = random.Random(seed)
    scen = [(a, b) for a in range(3) for b in range(3)][:nS]
    opps = [f'Opp_{i}' for i in range(nO)]
    atk = [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)]
    dfn = [round(100 + 50 * rng.random(), 2) for _ in range(nIvs)]
    hp = [rng.randint(120, 160) for _ in range(nIvs)]      # many duplicates
    rules = []
    for oi in range(nO):
        stat = 'def' if oi % 3 else 'atk'
        cut = rng.uniform(115, 140)
        hp_floor = rng.randint(130, 150) if oi % 3 == 2 else None
        rules.append((stat, cut, hp_floor))
    scores = []
    for iv in range(nIvs):
        for si in range(nS):
            for oi in range(nO):
                stat, cut, hp_floor = rules[oi]
                v = atk[iv] if stat == 'atk' else dfn[iv]
                win = v >= cut and (hp_floor is None or si % 3 == 0
                                    or hp[iv] >= hp_floor)
                if rng.random() < 0.06:
                    win = not win
                scores.append(700 if win else (500 if oi % 2 else 300))
    anchors = []
    for k in range(80):
        oi = rng.randrange(nO)
        stat = rng.choice(['atk', 'def', 'def'])
        vals = atk if stat == 'atk' else dfn
        thr = (vals[rng.randrange(nIvs)] if k % 4 == 0
               else round(rng.uniform(95, 155), 2))
        name = opps[oi].lower() if k % 7 == 0 else opps[oi]
        anchors.append(_Anchor(f'a{k}', name, stat, thr, strict=k % 3 == 0))
    anchors += [_Anchor('blank', '', 'def', 120.0),
                _Anchor('ghost', 'Opp_99', 'def', 120.0),
                _Anchor('all', opps[1], 'def', 0.0),
                _Anchor('none', opps[1], 'def', 999.0)]
    data_obj = {'ivAtk': atk, 'ivDef': dfn, 'ivHp': hp}
    return scores, nIvs, nS, nO, anchors, data_obj, scen, opps


def test_matches_reference_on_synthetic_fixtures():
    n_rec = n_hp = 0
    for seed in range(6):
        want, stats = _run_both(*_synthetic(seed))
        n_rec += len(want)
        n_hp += sum(1 for r in want if r['hp_threshold'] is not None)
        assert stats['considered'] == 84
        assert stats['no_opponent'] == 1 and stats['unknown_opponent'] == 1
        assert stats['trivial_partition'] >= 2
    # Anti-vacuity: both phases must actually emit across the seeds.
    assert n_rec >= 30, n_rec
    assert n_hp >= 5, n_hp


def test_matches_reference_without_hp():
    """The anchor-clear overlay's stub data_obj carries no ivHp: the HP
    search must be skipped by both implementations alike."""
    scores, nIvs, nS, nO, anchors, data_obj, scen, opps = _synthetic(3)
    stub = {'ivAtk': data_obj['ivAtk'], 'ivDef': data_obj['ivDef']}
    want, _ = _run_both(scores, nIvs, nS, nO, anchors, stub, scen, opps)
    assert want and all(r['hp_threshold'] is None for r in want)
    want_hp, _ = _run_both(scores, nIvs, nS, nO, anchors, data_obj, scen, opps)
    assert len(want_hp) > len(want)        # the HP phase is what differs


def test_hp_scan_stops_at_first_unclean_floor_after_a_clean_one():
    """Direct pin of the descending scan. Passing IVs (def >= 130), by HP:
    110 x30 all win, 109 x12 all lose, 108 x30 all win, 100 x60 all lose;
    the 100 failing IVs all lose. Phase 1 is unclean (60/132 wins). Floor
    110 is clean (30/30 pass, 30/202 fail wins), floor 109 is not (30/42 <
    0.75) -> the scan stops and returns 110. Floor 108 is clean again
    (60/72, 0/160), so a scan that did not stop at 109 returns 108."""
    nS, nO = 1, 1
    dfn, hp, win = [], [], []
    for h, n, w in ((110, 30, True), (109, 12, False), (108, 30, True),
                    (100, 60, False)):
        dfn += [140.0] * n
        hp += [h] * n
        win += [w] * n
    dfn += [120.0] * 100
    hp += [150] * 100
    win += [False] * 100
    nIvs = len(dfn)
    scores = [700 if w else 300 for w in win]
    data_obj = {'ivAtk': [100.0] * nIvs, 'ivDef': dfn, 'ivHp': hp}
    anchors = [_Anchor('d', 'OPP', 'def', 130.0)]
    want, _ = _run_both(scores, nIvs, nS, nO, anchors, data_obj,
                        [(1, 1)], ['OPP'])
    assert [r['hp_threshold'] for r in want] == [110]


def test_winrate_gates_are_inclusive_in_both_phases():
    """pw >= 0.75 and fw <= 0.25 are INCLUSIVE, in phase 1 and in the HP
    search alike. The random fixture never lands on a rate of exactly 3/4 or
    1/4, so without this a '>' / '<' slip in either phase passed.

    Phase 1: 8 passing IVs, 6 win (0.75); 8 failing IVs, 2 win (0.25).
    HP phase: passing HP 110 x4 (3 win) + HP 100 x4 (all lose) = 3/8, so
    phase 1 is unclean; floor 110 is exactly 3/4 pass and 2/8 fail."""
    atk = [100.0] * 16
    dfn = [140.0] * 8 + [120.0] * 8
    hp = [150] * 16
    win = [True] * 6 + [False] * 2 + [True] * 2 + [False] * 6
    scores = [700 if w else 300 for w in win]
    want, _ = _run_both(scores, 16, 1, 1, [_Anchor('d', 'OPP', 'def', 130.0)],
                        {'ivAtk': atk, 'ivDef': dfn, 'ivHp': hp},
                        [(1, 1)], ['OPP'])
    assert [r['hp_threshold'] for r in want] == [None]

    dfn = [140.0] * 8 + [120.0] * 4
    hp = [110] * 4 + [100] * 4 + [150] * 4
    win = [True] * 3 + [False] + [False] * 4 + [True] * 2 + [False] * 2
    scores = [700 if w else 300 for w in win]
    want, _ = _run_both(scores, 12, 1, 1, [_Anchor('d', 'OPP', 'def', 130.0)],
                        {'ivAtk': [100.0] * 12, 'ivDef': dfn, 'ivHp': hp},
                        [(1, 1)], ['OPP'])
    assert [r['hp_threshold'] for r in want] == [110]


def _blob_inputs(name):
    for d in (REPO_ROOT / 'userdata' / 'replay',
              REPO_ROOT.parent / 'gopvpsim' / 'userdata' / 'replay',
              Path('/Users/mglerner/coding/gopvpsim/userdata/replay')):
        if (d / name).exists():
            state = deep_dive.load_replay_state(str(d / name))
            break
    else:
        pytest.skip(f'{name} is not on this machine')
    ms = state['moveset_data'][0]
    meta = ms['meta']
    data_obj = {'ivAtk': [m[5] for m in meta], 'ivDef': [m[6] for m in meta],
                'ivHp': [m[7] for m in meta]}
    scen = [tuple(s) for s in state['shield_scenarios']]
    opps = state['opponent_names']
    anchors = state['slayer_iter_result']['resolved_anchors']
    return state, ms, data_obj, scen, opps, anchors


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_matches_reference_on_real_blob():
    """Tinkaton GL (2026-09-20 bake, one of the render-harness blobs):
    every opp-IV mode of moveset 0."""
    state, ms, data_obj, scen, opps, anchors = _blob_inputs(
        '20260920_180117_Tinkaton_great.replay.pkl.gz')
    nIvs, nS, nO = len(data_obj['ivAtk']), len(scen), len(opps)
    n_rec = n_hp = 0
    for mode in state['opp_iv_modes']:
        want, _ = _run_both(ms['scores'][mode], nIvs, nS, nO, anchors,
                            data_obj, scen, opps)
        n_rec += len(want)
        n_hp += sum(1 for r in want if r['hp_threshold'] is not None)
    assert n_rec >= 50 and n_hp >= 1, (n_rec, n_hp)
