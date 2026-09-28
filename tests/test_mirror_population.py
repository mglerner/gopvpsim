"""The mirror POPULATION (TODO.md "NEXT BAKE: mirror population").

``deep_dive_lib/mirror_population.py`` chooses the mirrors a reader will
meet -- PvPoke's top-20 IV rank list for the focal plus the page's own
builds' most-winning members and SP1 (stat-product rank 1) -- and sweeps
every moveset against them as extra opponent columns. The page's "Which one
to build?" mirror paragraph then reads counts off the stored
per-(spread, scenario, member) scores
(``deep_dive_builds.population_facts``) instead of the mirror-slayer cohort.

Pinned here, all without a blob:

- the schema survives the replay blob round trip;
- the guards: every swept arm carries SP1 and the rank list's #1, and a
  population missing either raises;
- the per-build numbers REPRODUCE from the stored scores by an independent
  recount (plain loops, ``battle.is_win``, pre-shadow attack from
  ``Pokemon.at_best_level``), on a surface where they are not trivial;
- the rendered sentences' numbers, on a synthetic facts dict;
- a blob WITHOUT the key renders the cohort paragraph unchanged;
- ``iv_sweep(opp_ivs=...)`` puts the explicit IVs on the opponent.
"""
import multiprocessing
import sys
from pathlib import Path

import numpy as np
import pytest

from tests.conftest import load_deep_dive

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'src'))
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

deep_dive = load_deep_dive()

import deep_dive_builds as D  # noqa: E402
import deep_dive_which_build as W  # noqa: E402
from deep_dive_lib import mirror_population as MP  # noqa: E402
from deep_dive_lib.sweep import compute_iv_metadata  # noqa: E402
from gopvpsim.battle import is_win  # noqa: E402
from gopvpsim.data import get_default_moveset  # noqa: E402
from gopvpsim.pokemon import Pokemon, iv_rank  # noqa: E402

SPECIES, LEAGUE = 'Melmetal', 'great'
SCENS = [(a, b) for a in range(3) for b in range(3)]
SCEN_LABELS = [f'{a}v{b}' for a, b in SCENS]


def _meta():
    return np.array([(m['atk_iv'], m['def_iv'], m['sta_iv'], m['level'],
                      m['cp'], m['atk'], m['def_'], m['hp'])
                     for m in compute_iv_metadata(SPECIES, LEAGUE)],
                    dtype=float)


META = _meta()
N_IV = len(META)


def _state(pool=('Melmetal', 'Altaria')):
    # Plain-form movesets for every entry: Shadow Melmetal is unranked, and
    # the moveset is not what these tests are about.
    ms = [tuple(get_default_moveset(n.replace(' (Shadow)', ''), LEAGUE))
          for n in pool]
    return {'species': SPECIES, 'league': LEAGUE, 'shadow': False,
            'cup': None, 'opponent_names': list(pool),
            'opp_movesets': ms, 'shield_scenarios': SCENS,
            'moveset_data': [{'meta': [tuple(r) for r in META]}]}


def _sp1():
    sp = META[:, 5] * META[:, 6] * META[:, 7]
    return int(np.argmax(sp))


def _grid_idx(ivs):
    a, d, s = ivs
    hit = np.flatnonzero((META[:, 0] == a) & (META[:, 1] == d)
                         & (META[:, 2] == s))
    return int(hit[0])


# Two builds in the grid: an attack-heavy region and a bulk region. Their
# most-winning members are two spreads OUTSIDE the rank list's top 20, so
# the population carries them as extra members.
ATK_BUILD = META[:, 5] >= np.quantile(META[:, 5], 0.9)
BULK_BUILD = (META[:, 6] >= np.quantile(META[:, 6], 0.8)) & ~ATK_BUILD
MW_ATK = int(np.flatnonzero(ATK_BUILD)[0])
MW_BULK = int(np.flatnonzero(BULK_BUILD)[-1])
ARM_BUILDS = [{'sp1': _sp1(),
               'builds': {'flat': {'primary': MW_ATK, 'fork': MW_BULK}}}]


def _population(pool=('Melmetal', 'Altaria'), seed=7):
    state = _state(pool)
    pop = MP.select_population(state, ARM_BUILDS)
    rng = np.random.default_rng(seed)
    a = pop['arms'][0]
    m = len(a['members'])
    # Scores correlated with focal attack minus member attack, so the counts
    # differ from build to build (a flat random surface would make every
    # build's median the same number and the test vacuous).
    atk = META[:, 5][:, None, None]
    opp = np.array([pop['members'][j]['atk'] for j in a['members']])
    base = 500 + 40 * (atk - opp[None, None, :])
    noise = rng.integers(-120, 121, size=(N_IV, len(SCENS), m))
    a['scores'] = {'bait': np.clip(base + noise, 0, 1000).astype(np.int16),
                   'nobait': np.clip(base - 60 + noise, 0, 1000)
                   .astype(np.int16)}
    pop['bait_modes'] = {'bait': 'pvpoke', 'nobait': 'pvpoke:nobait'}
    state['mirror_population'] = pop
    return state, pop


def _block():
    return {'builds': [
        {'role': 'primary', '_mask': ATK_BUILD,
         'most_winning_member': {'idx': MW_ATK}},
        {'role': 'fork', '_mask': BULK_BUILD,
         'most_winning_member': {'idx': MW_BULK}}]}


def _ctx(state, mode='pvpoke'):
    return {'state': state, 'arm': 0, 'mode': mode, 'n_iv': N_IV,
            'n_sc': len(SCENS), 'meta': META, 'atk': META[:, 5].copy(),
            'scen_labels': SCEN_LABELS}


# ---------------------------------------------------------------------------
# selection + guards
# ---------------------------------------------------------------------------

def test_population_carries_rank_list_sp1_and_the_builds():
    _state_, pop = _population()
    a = pop['arms'][0]
    mem = pop['members']
    top = iv_rank(SPECIES, league=LEAGUE)[:MP.N_RANK]
    rank_ivs = [(e['atk_iv'], e['def_iv'], e['sta_iv']) for e in top]
    tagged_rank = [tuple(mem[m]['ivs']) for m, t in zip(a['members'],
                                                          a['tags'])
                   if 'pvpoke_rank' in t]
    assert tagged_rank == rank_ivs
    # The two anchors the decision record names.
    assert mem[a['rank1']]['rank'] == 1
    assert tuple(mem[a['rank1']]['ivs']) == rank_ivs[0]
    sp1_ivs = tuple(int(v) for v in META[_sp1(), :3])
    assert tuple(mem[a['sp1']]['ivs']) == sp1_ivs
    assert 'sp1' in a['tags'][a['members'].index(a['sp1'])]
    # The build members, tagged with their role, at explicit IVs.
    for role, idx in (('primary', MW_ATK), ('fork', MW_BULK)):
        mi = a['builds']['flat'][role]
        assert tuple(mem[mi]['ivs']) == tuple(int(v) for v in META[idx, :3])
        assert f'build:{role}' in a['tags'][a['members'].index(mi)]
    # Deduplicated: SP1 is rank #1 on an unfloored grid, ONE member.
    assert a['sp1'] == a['rank1']
    assert len(a['members']) == len(set(a['members'])) == MP.N_RANK + 2
    # Stats are the member's own, at its best level under the cap.
    p = Pokemon.at_best_level(SPECIES, *rank_ivs[0], league=LEAGUE)
    assert mem[a['rank1']]['level'] == p.level
    assert mem[a['rank1']]['raw_atk'] == p.raw_atk


def test_other_shadow_form_joins_only_when_in_the_pool():
    _s, pop = _population()
    assert not any(m['shadow'] for m in pop['members'])
    _s, pop2 = _population(pool=('Melmetal', 'Melmetal (Shadow)', 'Altaria'))
    sh = [m for m in pop2['members'] if m['shadow']]
    assert len(sh) == MP.N_RANK
    assert all(m['name'] == 'Melmetal (Shadow)' for m in sh)
    assert sorted(m['rank'] for m in sh) == list(range(1, MP.N_RANK + 1))


def test_guard_raises_without_sp1_or_rank1():
    """Pre-guard, a population missing either anchor would have rendered
    numbers "against the common builds" with the headline spread absent."""
    _s, pop = _population()
    MP.check_guards(pop)                          # the real one passes
    for what in ('sp1', 'rank1'):
        _s, bad = _population()
        a = bad['arms'][0]
        j = a['members'].index(a[what])
        del a['members'][j]
        del a['tags'][j]
        with pytest.raises(MP.PopulationGuardError):
            MP.check_guards(bad)


# ---------------------------------------------------------------------------
# schema round trip
# ---------------------------------------------------------------------------

def test_population_survives_the_replay_blob_round_trip(tmp_path):
    state, pop = _population()
    state = dict(state, species=SPECIES, league=LEAGUE)
    path = deep_dive.dump_replay_state(state, str(tmp_path / 'b.pkl.gz'))
    assert path
    back = deep_dive.load_replay_state(path)['mirror_population']
    assert back['version'] == MP.SCHEMA_VERSION
    assert back['members'] == pop['members']
    a0, b0 = pop['arms'][0], back['arms'][0]
    for key in ('members', 'tags', 'builds', 'sp1', 'rank1'):
        assert b0[key] == a0[key]
    for tag in ('bait', 'nobait'):
        assert b0['scores'][tag].dtype == np.int16
        assert np.array_equal(b0['scores'][tag], a0['scores'][tag])


# ---------------------------------------------------------------------------
# the numbers reproduce from the stored scores
# ---------------------------------------------------------------------------

def _recount(state, block, cols_of, mode_tag):
    """Independent recount: loops, battle.is_win, Pokemon.raw_atk."""
    pop = state['mirror_population']
    a = pop['arms'][0]
    sc = a['scores'][mode_tag]
    out = []
    for b in block['builds']:
        idx = np.flatnonzero(b['_mask'])
        cols = cols_of
        per_scen = []
        for si in range(len(SCENS)):
            counts = sorted(sum(1 for j in cols if is_win(int(sc[i, si, j])))
                            for i in idx)
            per_scen.append([counts[(len(counts) - 1) // 2], counts[0]])
        opp_raw = [pop['members'][a['members'][j]]['raw_atk'] for j in cols]
        cmp_counts = []
        for i in idx:
            f = Pokemon.at_best_level(SPECIES, *(int(v) for v in META[i, :3]),
                                      league=LEAGUE)
            cmp_counts.append(sum(1 for r in opp_raw if f.raw_atk > r))
        cmp_counts.sort()
        out.append({'beat': per_scen,
                    'cmp': [cmp_counts[(len(cmp_counts) - 1) // 2],
                            cmp_counts[0]]})
    return out


@pytest.mark.parametrize('mode,tag', [('pvpoke', 'bait'),
                                      ('pvpoke:nobait', 'nobait')])
def test_population_numbers_reproduce_from_stored_scores(mode, tag):
    state, pop = _population()
    block = _block()
    pf = D.population_facts(_ctx(state, mode), block, 'flat')
    assert pf is not None and pf['page_ok']
    a = pop['arms'][0]
    groups = {g['key']: g for g in pf['groups']}
    assert set(groups) == {'rank', 'page'}
    rank_cols = [j for j, t in enumerate(a['tags']) if 'pvpoke_rank' in t]
    page_mids = sorted({a['builds']['flat']['primary'],
                        a['builds']['flat']['fork'], a['sp1']})
    page_cols = [a['members'].index(m) for m in page_mids]
    for key, cols in (('rank', rank_cols), ('page', page_cols)):
        want = _recount(state, block, cols, tag)
        got = groups[key]['builds']
        assert groups[key]['n'] == len(cols)
        for w, g in zip(want, got):
            assert g['beat'] == w['beat'], key
            assert g['cmp'] == w['cmp'], key
    # Non-trivial: the two builds land on different 1v1 counts, and the
    # counts are neither all-zero nor all-N (the "both empty" failure mode).
    r = groups['rank']['builds']
    si = pf['si']
    assert pf['scenario'] == '1v1'
    assert r[0]['beat'][si] != r[1]['beat'][si]
    flat = [v for b in r for pair in b['beat'] for v in pair]
    assert 0 < max(flat) and min(flat) < len(rank_cols)
    assert r[0]['cmp'][0] > r[1]['cmp'][0]


def test_page_group_is_dropped_when_the_builds_moved():
    """The bake tagged members for builds this render does not select: the
    page sentence must not call them "this page's own picks"."""
    state, _pop = _population()
    block = _block()
    block['builds'][1]['most_winning_member'] = {'idx': MW_BULK - 1}
    pf = D.population_facts(_ctx(state), block, 'flat')
    assert pf['page_ok'] is False
    assert [g['key'] for g in pf['groups']] == ['rank']


def test_no_population_no_facts():
    state = _state()
    assert D.population_arm(_ctx(state)) is None
    assert D.population_facts(_ctx(state), _block(), 'flat') is None
    state, _pop = _population()
    # L51 was not swept: the best-buddy section keeps the cohort paragraph.
    assert D.population_arm(_ctx(state), level='l51') is None


# ---------------------------------------------------------------------------
# the rendered sentences
# ---------------------------------------------------------------------------

def _pf():
    rank_rows = [{'role': 'primary', 'size': 400, 'n': 20,
                  'beat': [[0, 0]] * 4 + [[17, 12]] + [[0, 0]] * 4,
                  'cmp': [15, 9]},
                 {'role': 'fork', 'size': 300, 'n': 20,
                  'beat': [[0, 0]] * 4 + [[8, 8]] + [[0, 0]] * 4,
                  'cmp': [0, 0]}]
    page_rows = [{'role': 'primary', 'size': 400, 'n': 3,
                  'beat': [[0, 0]] * 4 + [[2, 1]] + [[0, 0]] * 4,
                  'cmp': [2, 1]},
                 {'role': 'fork', 'size': 300, 'n': 3,
                  'beat': [[0, 0]] * 4 + [[1, 1]] + [[0, 0]] * 4,
                  'cmp': [0, 0]}]
    cmp_rows = [{'q': 0.5, 'T': 119.39, 'line': 119.3913, 'line_printed': 119.39,
                 'line_dp': 2, 'n_beaten': 13, 'n_cohort': 20,
                 'n_grid_strict': 900, 'n_grid_ties': 950},
                {'q': 0.75, 'T': 119.91, 'line': 119.9142,
                 'line_printed': 119.91, 'line_dp': 2, 'n_beaten': 19,
                 'n_cohort': 20, 'n_grid_strict': 500, 'n_grid_ties': 520}]
    return {'species': 'Melmetal', 'shadow': False, 'scenario': '1v1',
            'si': 4, 'n_members': 22, 'page_ok': True,
            'groups': [{'key': 'rank', 'shadow': False, 'n': 20,
                        'atk_lo': 118.86, 'atk_hi': 120.76, 'cmp': cmp_rows,
                        'builds': rank_rows},
                       {'key': 'page', 'shadow': False, 'n': 3, 'cmp': None,
                        'builds': page_rows}]}


BL = {'builds': [{'role': 'primary'}, {'role': 'fork'}]}
FACTS = {'header': {'species': 'Melmetal', 'shadow': False}}


def test_population_sentences_print_the_counts():
    out = W.population_sentences(_pf(), BL, FACTS)
    assert out == [
        "Against the top 20 spreads on PvPoke's IV rank list for Melmetal, "
        "in the 1v1: Build 1 beats 85% (every member at least 60%) and wins "
        "charge-move priority against 75%; Build 2 beats 40% and wins "
        "charge-move priority against 0%.",
        "An attack of 119.39 and up wins charge-move priority against 13 of "
        "them, and 119.91 and up against 19.",
        "Against this page's own picks for Melmetal (3 spreads: each build's "
        "most-winning member and SP1), in the 1v1: Build 1 beats 2 of 3 "
        "(every member at least 1 of 3) and wins charge-move priority "
        "against 2 of 3; Build 2 beats 1 of 3 and wins charge-move priority "
        "against 0 of 3.",
    ]


def test_one_page_pick_is_one_spread():
    """Every build's most-winning member can BE SP1 (real: Melmetal GL arm
    1), and the first real render printed "(1 spreads: ...)"."""
    pf = _pf()
    page = pf['groups'][1]
    page['n'] = 1
    page['builds'] = [dict(r, n=1, beat=[[0, 0]] * 9, cmp=[1, 1])
                      for r in page['builds']]
    out = W.population_sentences(pf, BL, FACTS)[-1]
    assert '(1 spread: ' in out and '1 spreads' not in out


def test_population_replaces_the_cohort_and_old_blobs_keep_it(monkeypatch):
    monkeypatch.setattr(W, 'RENDER_MIRROR_POPULATION', True)
    mf = {'n_iv': 4096, 'atk_lo': 154.62, 'n_final': 31, 'tilt': 'bulk',
          'split': None,
          'cmp': _pf()['groups'][0]['cmp'],
          'builds': [{'role': 'primary', 'size': 400, 'n_clear': [0, 0],
                      'atk_max': 119.0},
                     {'role': 'fork', 'size': 300, 'n_clear': [0, 0],
                      'atk_max': 118.0}]}
    old = {'presets': {'flat': BL}, 'mirror': {'flat': mf}}
    html_old = W.mirror_block_html(FACTS, old)
    assert 'mirror-slayer protocol' in html_old
    assert "IV rank list" not in html_old
    # The exact pre-population rendering, so an old blob's page is unchanged.
    assert html_old == W._preset_blocks(
        old, lambda k: W._mirror_preset_html(mf, BL, FACTS))
    new = dict(old, population={'flat': _pf()})
    html_new = W.mirror_block_html(FACTS, new)
    assert "PvPoke&#x27;s IV rank list" in html_new or \
        "PvPoke's IV rank list" in html_new
    assert 'mirror-slayer protocol' not in html_new
    assert html_new.count('<p class="wb-mirror">') == 1


def test_render_gate_keeps_the_cohort_paragraph_until_reviewed():
    """The gate as shipped (2026-09-28): the population is baked and stored,
    but a blob that carries one still renders the COHORT paragraph, byte-
    identical to a blob without one, until RENDER_MIRROR_POPULATION is
    flipped (the self-mirror probe in deep_dive_which_build's gate comment).
    Fails the day the gate is opened, which is the point: opening it is a
    ship decision, and this test is where it gets recorded."""
    assert W.RENDER_MIRROR_POPULATION is False
    mf = {'n_iv': 4096, 'atk_lo': 154.62, 'n_final': 31, 'tilt': 'bulk',
          'split': None,
          'cmp': _pf()['groups'][0]['cmp'],
          'builds': [{'role': 'primary', 'size': 400, 'n_clear': [0, 0],
                      'atk_max': 119.0},
                     {'role': 'fork', 'size': 300, 'n_clear': [0, 0],
                      'atk_max': 118.0}]}
    old = {'presets': {'flat': BL}, 'mirror': {'flat': mf}}
    new = dict(old, population={'flat': _pf()})
    html_old = W.mirror_block_html(FACTS, old)
    assert 'mirror-slayer protocol' in html_old
    assert W.mirror_block_html(FACTS, new) == html_old


# ---------------------------------------------------------------------------
# the sweep plumbing
# ---------------------------------------------------------------------------

RESERVE = max(0, multiprocessing.cpu_count() - 2)


def test_iv_sweep_explicit_opp_ivs_reach_the_opponent():
    """Explicit rank-1 IVs score exactly like the 'rank1' opp-IV mode, and a
    far-off explicit spread (15/0/0) scores unlike the mode's own IVs -- so
    the explicit IVs are what was simmed, not the mode's resolution."""
    om = get_default_moveset('Azumarill', 'great')
    fm = get_default_moveset('Mimikyu', 'great')
    r1 = iv_rank('Azumarill', league='great')[0]
    r1_ivs = (r1['atk_iv'], r1['def_iv'], r1['sta_iv'])

    def sweep(mode, opp_ivs=None):
        return deep_dive.iv_sweep(
            'Mimikyu', fm[0], fm[1], 'great', False,
            ['Azumarill'], [om], [(1, 1), (0, 0)], opp_iv_mode=mode,
            iv_floor=(13, 13, 13), reserve_cpus=RESERVE,
            opp_ivs=opp_ivs)[2]
    by_mode = sweep('rank1')
    explicit = sweep('pvpoke', opp_ivs=[r1_ivs])
    assert explicit == by_mode
    assert sweep('rank1', opp_ivs=[(15, 0, 0)]) != by_mode
    with pytest.raises(ValueError):
        sweep('pvpoke', opp_ivs=[r1_ivs, r1_ivs])
