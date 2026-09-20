"""Tests for scripts/deep_dive_builds.py -- the ported BUILDS computation.

The module is a render-time port of two analysis scripts that live outside
the repo, under ``userdata/analysis/``:

- ``2026-09-15_spread_sets/spread_sets.py`` (the five set generators)
- ``2026-09-16_builds/builds_lattice.py`` (the intersection lattice and the
  2-3 builds selected from it)

Those two are the REFERENCE IMPLEMENTATION, and their per-blob JSON output is
the oracle here: a parity test reads ``*_builds.json`` and compares the
port's default-preset numbers against it field by field. That is an oracle
comparison (the numbers come from a separate program, run before this module
existed), not a tautology against arrays this code just built.

Three further kinds of test:

- Preset behaviour. The reference re-counts a selected build's guaranteed
  cells under two shield priors and asks whether the LEADING build changes
  (``summarize_builds.py``'s ``prior_flip``); that post-hoc computation is
  reproduced here over the port's own default-preset builds and pinned to the
  answers the reference JSONs give. The port goes further -- it RE-SELECTS
  under each preset -- so a second test pins that the re-selection really
  moves the primary where the re-count said the lead moves.
- A synthetic win cube where the preset MUST flip the primary. No blob, so it
  runs in the fast tier and fails on a weight vector that is being ignored.
- Determinism: two computations of one arm produce byte-identical payload
  JSON (the section embeds it, and two renders of one blob must be
  byte-identical).

Blob- and reference-reading tests are marked ``local_artifacts`` and skip
when the analysis store is not on the machine.
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
SABLEYE_SHADOW = '20260911_005150_Sableye_great_shadow'
SABLEYE_PLAIN = '20260911_051621_Sableye_great'
MEDICHAM = '20260911_071541_Medicham_great'
MELMETAL = '20260910_190103_Melmetal_great'

sys.path.insert(0, str(REPO_ROOT / 'tests'))
from test_deep_dive_brief import B, require_blob  # noqa: E402


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


D = _load('deep_dive_builds')

# The reference implementation's own output, written by builds_lattice.py.
_REF_DIRS = [REPO_ROOT / 'userdata' / 'analysis' / '2026-09-16_builds',
             REPO_ROOT.parent / 'gopvpsim' / 'userdata' / 'analysis'
             / '2026-09-16_builds']


def require_reference(slug):
    for d in _REF_DIRS:
        p = d / f'{slug}_builds.json'
        if p.exists():
            return json.loads(p.read_text())
    pytest.skip(f"{slug}_builds.json (reference output) is not on this machine")


def _arm(slug, arm=0):
    path = require_blob(f'{slug}.replay.pkl.gz')
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, arm, str(path))
    return D.compute_builds(state, arm, facts=facts)


# ---------------------------------------------------------------------------
# 1. Parity with the reference implementation (default preset)
# ---------------------------------------------------------------------------

def _assert_reference_parity(slug, arm=0):
    ref = require_reference(slug)['arms'][arm]
    res = _arm(slug, arm)
    flat = res['presets'][D.PRESET_FLAT]
    assert res['n_decision_cells'] == ref['n_decision_cells']
    assert res['n_material_cells'] == ref['n_material_cells']
    assert ([(s['key'], s['name'], s['size'], s['n_guaranteed'],
              s['n_guaranteed_material']) for s in flat['lattice_sets']]
            == [(s['key'], s['name'], s['size'], s['n_guaranteed'],
                 s['n_guaranteed_material']) for s in ref['lattice_sets']])
    assert len(flat['builds']) == len(ref['builds'])
    for got, want in zip(flat['builds'], ref['builds']):
        assert got['role'] == want['role']
        assert got['combo'] == want['combo']
        assert got['size'] == want['size']
        assert got['n_guaranteed'] == want['n_guaranteed']
        assert got['n_guaranteed_material'] == want['n_guaranteed_material']
        assert got['rank1_in'] == want['rank1_in']
        assert got['most_winning_member']['iv'] == want['most_winning_member']['iv']
        assert got['most_winning_member']['wins'] == want['most_winning_member']['wins']
        assert got['description_shape'] == want['description_shape']
        if want['description'] is None:
            assert got['description'] is None
        else:
            assert got['description']['rule'] == want['description']['rule']
        # Under the default preset every weight is 1, so the weighted count
        # IS the plain one. A weighted count that drifted from it here would
        # mean the default preset stopped being the reference behaviour.
        assert got['n_guaranteed_weighted'] == want['n_guaranteed']
    return res, ref


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_reference_parity_shadow_sableye():
    """Shadow Sableye GL arm 0: 87 decision cells, best single set 42 cells,
    primary DEF = 61 spreads / 55 cells, fork = the 114-spread rectangle
    ``def >= 101.4 and HP >= 125`` (41 cells) holding stat-product rank-1."""
    res, ref = _assert_reference_parity(SABLEYE_SHADOW)
    flat = res['presets'][D.PRESET_FLAT]
    assert res['n_decision_cells'] == 87
    assert max(s['n_guaranteed'] for s in flat['lattice_sets']) == 42
    primary, fork = flat['builds'][0], flat['builds'][1]
    assert (primary['role'], primary['size'], primary['n_guaranteed']) == (
        'primary', 61, 55)
    assert (fork['role'], fork['size'], fork['n_guaranteed']) == ('fork', 114, 41)
    assert fork['description']['rule'] == 'def >= 101.4 and HP >= 125'
    assert fork['rank1_in'] and not primary['rank1_in']
    obj = flat['objectives']
    assert obj['rank1_iv'] == '0/15/15@49.5'
    # The grid's most-winning spread is in NEITHER build -- the fact the
    # section prints as the honest caveat under the builds table.
    assert obj['global_most_winning']['iv'] == '7/2/14@49.5'
    assert obj['global_most_winning']['wins'] == 382
    assert obj['global_most_winning_in'] == []


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_reference_parity_plain_sableye():
    """Plain Sableye GL arm 0: primary AD = 318 spreads / 43 cells under
    ``atk >= 125 and Def + 1.9*HP >= 345.067``; fork = the 170-spread box
    ``def >= 120 and HP >= 125``, holding rank-1 and the most-winning
    0/13/15@50 (362 matchups)."""
    res, ref = _assert_reference_parity(SABLEYE_PLAIN)
    flat = res['presets'][D.PRESET_FLAT]
    primary, fork = flat['builds'][0], flat['builds'][1]
    assert (primary['size'], primary['n_guaranteed']) == (318, 43)
    assert primary['description']['rule'] == 'atk >= 125 and Def + 1.9*HP >= 345.067'
    assert (fork['size'], fork['n_guaranteed']) == (170, 31)
    assert fork['description']['rule'] == 'def >= 120 and HP >= 125'
    assert fork['rank1_in']
    assert fork['most_winning_member']['iv'] == '0/13/15@50'
    assert fork['most_winning_member']['wins'] == 362


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_reference_parity_melmetal_every_arm():
    """Every arm of a four-moveset blob, not just the one the page opens on."""
    ref = require_reference(MELMETAL)
    assert len(ref['arms']) >= 4
    for arm in range(len(ref['arms'])):
        _assert_reference_parity(MELMETAL, arm)


# ---------------------------------------------------------------------------
# 2. The presets
# ---------------------------------------------------------------------------

def _lead(builds, keep):
    """``summarize_builds.py``'s ``lead``: the build guaranteeing the most
    cells once the scenarios outside ``keep`` are dropped from the count."""
    best, bi = -1, None
    for b in builds:
        v = sum(len(v) for k, v in b['guaranteed_by_scenario'].items()
                if keep is None or k in keep)
        if v > best:
            best, bi = v, b['combo']
    return bi


@pytest.mark.parametrize('slug,arm,flips_even,flips_one', [
    # Read off the reference JSONs with summarize_builds.py's own lead():
    # plain Sableye arm 0 flips under 1v1 only; Melmetal arm 1 flips under
    # both; Medicham's two arms flip under neither.
    (SABLEYE_PLAIN, 0, False, True),
    (MELMETAL, 1, True, True),
    (MEDICHAM, 0, False, False),
    (MEDICHAM, 1, False, False),
])
@pytest.mark.slow
@pytest.mark.local_artifacts
def test_reference_lead_flips_reproduce(slug, arm, flips_even, flips_one):
    """Re-counting the DEFAULT preset's builds under each prior gives the
    reference's own flip answers."""
    require_reference(slug)
    builds = _arm(slug, arm)['presets'][D.PRESET_FLAT]['builds']
    flat = _lead(builds, None)
    assert (_lead(builds, {'0v0', '1v1', '2v2'}) != flat) is flips_even
    assert (_lead(builds, {'1v1'}) != flat) is flips_one


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_preset_reselects_the_primary_where_the_recount_flips():
    """Plain Sableye arm 0: the 1v1 preset does not merely re-rank the
    default preset's two builds, it selects a DIFFERENT region as primary.

    The reference only re-counts; this module re-runs the whole lattice under
    the preset's weights, so the test pins the stronger property. A preset
    whose weight vector was ignored would return the same region here.
    """
    res = _arm(SABLEYE_PLAIN, 0)
    flat = res['presets'][D.PRESET_FLAT]['builds'][0]
    one = res['presets'][D.PRESET_ONE]['builds'][0]
    assert not np.array_equal(flat['_mask'], one['_mask'])
    assert one['n_guaranteed_weighted'] <= flat['n_guaranteed']
    # Under its own preset the selected primary leads on the weighted count.
    for b in res['presets'][D.PRESET_ONE]['builds'][1:]:
        assert one['n_guaranteed_weighted'] >= b['n_guaranteed_weighted']


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_every_preset_selects_builds_and_weights_only_its_scenarios():
    res = _arm(SABLEYE_SHADOW, 0)
    assert set(res['presets']) == set(D.PRESET_KEYS)
    labels = res['ctx']['scen_labels']
    for key, block in res['presets'].items():
        assert block['builds'], f"{key} selected no build"
        live = {labels[i] for i, w in enumerate(block['weights']) if w > 0}
        want = D.PRESET_SCENS[key]
        assert live == (set(labels) if want is None else set(want) & set(labels))
        for b in block['builds']:
            # A weighted count can never exceed the unweighted one: every
            # weight is 0 or 1.
            assert b['n_guaranteed_weighted'] <= b['n_guaranteed']


# ---------------------------------------------------------------------------
# 3. Synthetic cube: the preset MUST flip the primary
# ---------------------------------------------------------------------------

def _synthetic_ctx():
    """A 256-spread, 3-scenario, 4-opponent grid with two disjoint regions.

    Region L (the low half) wins six cells, all of them in scenarios 0v0 and
    2v2. Region H (the high half) wins four cells, all in 1v1. So the flat
    preset must lead with L and the 1v1-only preset with H, and a build
    selector that ignored its weight vector would return L for both.
    """
    n, n_sc, n_opp = 256, 3, 4
    atk = np.arange(n, dtype=np.float64)
    dfn = np.full(n, 100.0)
    hp = np.full(n, 120.0)
    low = atk < 128
    win = np.zeros((n, n_sc, n_opp), bool)
    # every cell is contested (some winners, some losers) and sits inside the
    # 2%-98% band, so all twelve are decision cells
    for oi in range(3):
        win[low, 0, oi] = True
        win[low, 2, oi] = True
    for oi in range(4):
        win[~low, 1, oi] = True
    # a sprinkle so no column is all-win / all-lose at the extremes
    win[0, 1, 3] = True
    win[n - 1, 0, 0] = True
    win2 = win.reshape(n, n_sc * n_opp)
    cells = []
    scen_labels = ['0v0', '1v1', '2v2']
    for si in range(n_sc):
        for oi in range(n_opp):
            k = si * n_opp + oi
            cells.append({'k': k, 'si': si, 'oi': oi,
                          'label': f'{scen_labels[si]} Opp{oi}',
                          'scenario': scen_labels[si], 'rank': 1 + oi,
                          'contested': True, 'degenerate': False, 'rep': True,
                          'wr': float(win2[:, k].mean())})
    planes = {'atk': atk, 'def': dfn, 'hp': hp}
    sp = atk * dfn * hp
    order = np.argsort(-sp, kind='stable')
    sp_rank = np.empty(n, int)
    sp_rank[order] = np.arange(1, n + 1)
    meta = np.zeros((n, 8))
    meta[:, 0] = np.arange(n) % 16
    meta[:, 3] = 50.0
    # Stand-in for the real ctx's mean battle score (build_ctx reads it off
    # the blob's score cube). Only its ARGMAX is load-bearing here -- it is
    # the section's "highest battle score" standout -- so a monotone
    # stand-in built from the same win cube is enough, and keeping the key
    # present is what stops this fixture drifting out of sync with
    # build_ctx's contract.
    avg_score = 500.0 + 50.0 * win2.astype(np.float64).mean(axis=1)
    return dict(win=win, win2=win2, planes=planes, atk=atk, dfn=dfn, hp=hp,
                sp=sp, sp_rank=sp_rank, n_iv=n, n_sc=n_sc, n_opp=n_opp,
                cells=cells, scen_labels=scen_labels, meta=meta,
                avg_score=avg_score, best_score=int(np.argmax(avg_score)),
                other_modes={}, names=[f'Opp{i}' for i in range(n_opp)],
                sc=D.Scanner(planes))


def test_synthetic_preset_flips_the_primary():
    ctx = _synthetic_ctx()
    sets = [{'name': 'L', 'generator': 'T', 'mask': ctx['atk'] < 128,
             'provenance': {}, 'aliases': []},
            {'name': 'H', 'generator': 'T', 'mask': ctx['atk'] >= 128,
             'provenance': {}, 'aliases': []}]
    frame = D.cell_frame(ctx)
    # Ten of the twelve columns are contested and inside the band; the two
    # 'Opp3' columns outside 1v1 are all-lose and are not decision cells.
    assert len(frame['cells']) == 10
    picks = {}
    for key in D.PRESET_KEYS:
        w = D.preset_weights(key, ctx['scen_labels'])
        L = D.arm_lattice(ctx, sets, frame, w)
        kept, _r1, _fi = D.select_builds(ctx, L)
        picks[key] = kept[0][1]['sets'][0]
    assert picks[D.PRESET_FLAT] == 'L'
    assert picks[D.PRESET_ONE] == 'H'
    # The even preset keeps 0v0 and 2v2, so it still leads with L; the test
    # would pass trivially if every preset agreed, which the 1v1 line rules out.
    assert picks[D.PRESET_EVEN] == 'L'


def test_preset_weights_are_zero_one_over_the_baked_scenarios():
    labels = ['0v0', '0v1', '1v1', '2v2']
    assert list(D.preset_weights(D.PRESET_FLAT, labels)) == [1, 1, 1, 1]
    assert list(D.preset_weights(D.PRESET_EVEN, labels)) == [1, 0, 1, 1]
    assert list(D.preset_weights(D.PRESET_ONE, labels)) == [0, 0, 1, 0]
    # A dive that baked no 1v1 leaves that preset with nothing to weight, and
    # the section must drop it rather than silently weight everything.
    assert not D.preset_is_live(D.PRESET_ONE, ['0v0', '2v2'])
    assert D.preset_is_live(D.PRESET_EVEN, ['0v0', '2v2'])


def test_cell_jaccard_is_unweighted_and_empty_safe():
    a = np.array([True, False, True])
    b = np.array([True, True, False])
    assert D.cell_jac(a, b) == pytest.approx(1 / 3)
    assert D.cell_jac(np.zeros(3, bool), np.zeros(3, bool)) == 0.0


# ---------------------------------------------------------------------------
# 4. Packing + payload
# ---------------------------------------------------------------------------

def test_pack_mask_is_lsb_first():
    import base64
    packed = D.pack_mask([True, False, True] + [False] * 5 + [True])
    assert base64.b64decode(packed) == bytes([0b00000101, 0b00000001])
    assert D.pack_mask([]) == ''


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_payload_is_deterministic_and_within_budget():
    res = _arm(SABLEYE_SHADOW, 0)
    blob = json.dumps(D.builds_payload(res, 0), sort_keys=True,
                      separators=(',', ':'))
    again = _arm(SABLEYE_SHADOW, 0)
    blob2 = json.dumps(D.builds_payload(again, 0), sort_keys=True,
                       separators=(',', ':'))
    assert blob == blob2
    # The render-time budget for this section, all three presets included.
    assert len(blob) < 60 * 1024, f"{len(blob)} bytes"


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_payload_regions_are_keyed_by_the_spreads_they_hold():
    """Two presets whose lattice letters mean different sets must not share a
    region entry, and a region two presets really do agree on must not be
    stored twice."""
    res = _arm(SABLEYE_SHADOW, 0)
    pay = D.builds_payload(res, 0)
    combos = {}
    for key in pay['presetKeys']:
        for col in pay['presets'][key]['cols']:
            combos.setdefault(col['combo'], set()).add(col['r'])
    # at least one combo string is reused across presets for DIFFERENT regions
    assert any(len(v) > 1 for v in combos.values()), (
        "no combo letter is reused across presets; the collision this keying "
        "exists to prevent cannot be observed on this blob")
    for key in pay['presetKeys']:
        for b in pay['presets'][key]['builds']:
            assert pay['regions'][b['region']]['mask'], (
                "a selected build's region carries no membership mask")
            assert pay['regions'][b['region']]['size'] == b['size']


# ---------------------------------------------------------------------------
# 5. The preset's own scale (2026-09-16 review)
#
# Everything the page prints about a build under a narrow preset has TWO
# possible denominators -- the scenarios the preset counts, and all nine --
# and the ranking used the first. The round-1 implementation picked the
# most-winning member on the second while plotting it on the first, and
# printed the second in the table with the first in the sentence under it.
# ---------------------------------------------------------------------------

def _synthetic_sets(ctx):
    return [{'name': 'L', 'generator': 'T', 'mask': ctx['atk'] < 128,
             'provenance': {}, 'aliases': []},
            {'name': 'H', 'generator': 'T', 'mask': ctx['atk'] >= 128,
             'provenance': {}, 'aliases': []}]


def synthetic_res():
    """A ``compute_builds``-shaped result over the synthetic cube.

    Blob-free, so the payload's field contract can be pinned in the fast
    tier and by tests/test_js_wire_contract.py, which reads the same shape
    the browser dereferences.
    """
    ctx = _synthetic_ctx()
    sets = _synthetic_sets(ctx)
    frame = D.cell_frame(ctx)
    presets = {k: D.run_preset(ctx, sets, frame, k) for k in D.PRESET_KEYS}
    sigs = {tuple((b['role'], b['_mask'].tobytes()) for b in p['builds'])
            for p in presets.values()}
    return dict(ctx=ctx, sets=sets, frame=frame, presets=presets,
                presets_identical=(len(sigs) == 1),
                n_decision_cells=len(frame['cells']),
                n_material_cells=int(frame['mat'].sum()),
                label='synthetic', arm=0)


def test_the_payload_carries_the_preset_scale_fields():
    """Named here against the BUILDER's output, not grepped out of the JS.

    tests/test_js_wire_contract.py scans the engine for the same names; a
    rename on either side then fails on one of the two.
    """
    pay = D.builds_payload(synthetic_res(), 0)
    assert set(pay['presetKeys']) == set(D.PRESET_KEYS)
    for key in pay['presetKeys']:
        block = pay['presets'][key]
        for field in ('nDecW', 'nDecWMat', 'tie', 'weights', 'scens',
                      'builds', 'cols', 'lattice', 'objectives'):
            assert field in block, (key, field)
        assert block['nDecW'] <= pay['nDecision']
        for b in block['builds']:
            for field in ('nG', 'nGw', 'nGmat', 'mostWinning', 'region',
                          'desc', 'rank1In'):
                assert field in b, (key, field)
            for field in ('iv', 'idx', 'wins', 'winsAll', 'den', 'spRank'):
                assert field in b['mostWinning'], (key, field)
            assert b['nGw'] <= b['nG']
        if block['objectives']:
            for field in ('winGap', 'winDen', 'cellGap', 'cellGapAll'):
                assert field in block['objectives'], (key, field)
    for col in pay['presets'][D.PRESET_ONE]['cols']:
        assert col['nGw'] <= col['nG']


def test_the_weighted_denominator_is_the_presets_own_cell_count():
    res = synthetic_res()
    labels = res['ctx']['scen_labels']
    for key, block in res['presets'].items():
        live = {labels[i] for i, w in enumerate(block['weights']) if w > 0}
        want = sum(1 for c in res['frame']['cells'] if c['scenario'] in live)
        assert block['n_decision_weighted'] == want, key
    # the 1v1 preset counts strictly fewer cells than the flat one, so the
    # two denominators are genuinely different numbers on this cube
    assert (res['presets'][D.PRESET_ONE]['n_decision_weighted']
            < res['presets'][D.PRESET_FLAT]['n_decision_weighted'])


def test_a_ruleless_build_carries_an_iv_envelope_that_holds_its_members():
    """The envelope is printed instead of a bare "list of N spreads"; it must
    contain every member and own up to what else is inside it."""
    res = synthetic_res()
    seen = 0
    for block in res['presets'].values():
        for b in block['builds']:
            if b['description'] is not None:
                assert b['iv_envelope'] is None
                continue
            seen += 1
            env = b['iv_envelope']
            assert env and env['n_box'] >= b['size']
            assert env['n_outside'] == env['n_box'] - b['size']
            for ax, col in (('atk', 0), ('def', 1), ('hp', 2)):
                v = res['ctx']['meta'][b['_mask'], col]
                assert env[ax][0] == int(v.min())
                assert env[ax][1] == int(v.max())
    # positive control: this cube does produce at least one describable build
    assert any(b['description'] is not None
               for block in res['presets'].values() for b in block['builds'])


def test_display_rule_spells_one_stat_one_way_and_never_truncates():
    """Page spelling only -- the `rule` field itself stays byte-identical to
    the reference implementation's, which the parity tests compare."""
    assert (D.display_rule('atk >= 125 and Def + 1.9*HP >= 345.067')
            == 'Atk >= 125.00 and Def + 1.9*HP >= 345.067')
    assert (D.display_rule('def >= 101.4 and HP >= 125')
            == 'Def >= 101.40 and HP >= 125')
    # a threshold that needs three places keeps them: print_thr chose the
    # shortest decimal that selects exactly the same spreads
    assert D.display_rule('atk >= 148.125') == 'Atk >= 148.125'
    # HP is an integer stat and the fact strip has always printed it as one
    assert D.display_rule('hp >= 143') == 'HP >= 143'
    # the step count is not a threshold
    assert (D.display_rule('atk >= 150.24 and Def >= d(HP) [4 steps]')
            == 'Atk >= 150.24 and Def >= d(HP) [4 steps]')


def test_the_cluster_set_label_uses_the_clusters_sections_own_name():
    """The Matchup clusters section names its clusters C0..C(K-1); an
    off-by-one relabelling pointed the UpSet row "matchup cluster 5" at what
    that section calls C4 (2026-09-16 review)."""
    assert D.set_short_label('S1 1v0 cluster 4') == 'matchup cluster C4 (1v0)'
    assert D.set_short_label('S1 1v0 cluster 0') == 'matchup cluster C0 (1v0)'


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_the_most_winning_member_is_the_highest_point_of_its_own_build():
    """Picked on the PRESET-weighted win count -- the section plot's y axis.

    Pre-fix the member was the all-nine argmax while the plot drew the
    weighted count, so Shadow Sableye's 1v1 primary marked 8/7/5@50 at 38
    weighted wins while 11/4/4@49.5 of the same build reached 39, and the
    legend asserted something the plot contradicted.
    """
    res = _arm(SABLEYE_SHADOW, 0)
    ctx = res['ctx']
    for key, block in res['presets'].items():
        w = D.preset_weights(key, ctx['scen_labels'])
        wsum = D.weighted_wins(ctx, w)
        den = int(w.sum()) * ctx['n_opp']
        for b in block['builds']:
            mw = b['most_winning_member']
            assert mw['wins'] == int(wsum[b['_mask']].max()), (key, b['role'])
            assert int(wsum[mw['idx']]) == mw['wins']
            assert mw['denominator'] == den
    one = res['presets'][D.PRESET_ONE]['builds'][0]['most_winning_member']
    assert (one['iv'], one['wins'], one['denominator']) == ('11/4/4@49.5', 39, 76)
    # the all-nine choice this replaced is still carried, and is a DIFFERENT
    # spread here -- so the test would pass trivially if they coincided
    assert one['wins_all'] != res['presets'][D.PRESET_FLAT]['builds'][0][
        'most_winning_member']['wins']


@pytest.mark.slow
@pytest.mark.local_artifacts
def test_a_shared_lead_is_reported_as_a_tie():
    """Under a narrow preset the primary is usually a tie-break, not a
    dominant region, and a page printing only the winner reads as though one
    region dominated."""
    res = _arm(SABLEYE_SHADOW, 0)
    assert res['presets'][D.PRESET_ONE]['top_tie'] == {
        'n': 9, 'weighted': 13, 'by': 'size', 'size': 292}
    assert res['presets'][D.PRESET_EVEN]['top_tie']['weighted'] == 29
    # recomputed independently from the lattice each preset ran
    for key, block in res['presets'].items():
        tie, top = block['top_tie'], block['inters'][0]
        n = sum(1 for d in block['inters'] if d['wg'] == top['wg'])
        assert (tie['n'] if tie else 1) == n, key
        if tie:
            assert tie['weighted'] == int(round(top['wg']))
