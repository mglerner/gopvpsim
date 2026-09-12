"""Tests for scripts/deep_dive_brief.py -- the auto-derived build brief.

Three kinds of test live here:

1. Oracle pins on the worked Shadow Sableye Great League case from
   ``docs/expert_verdict_plan.md`` section 3. Those numbers were recomputed
   for that document from the 2026-09-11 blob by a different codebase, so
   ``==`` against them is an oracle comparison, not a tautology against our
   own arrays (the "counts are floors" rule in CLAUDE.md exists to stop a
   test re-deriving a number from the data the code just used; these come
   from outside).
2. Guard positive controls: each build-breaking guard gets an input that
   must make it raise, so a guard that silently stops guarding fails here.
3. Pre-fix records. Four behaviour bugs were fixed while this module was
   written; each test below records the value the old code produced, so a
   regression is recognisable and not just "a number changed".

Blob-reading tests are marked ``local_artifacts`` and skip when the replay
store is not on the machine.
"""
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
SABLEYE_SHADOW = '20260911_005150_Sableye_great_shadow.replay.pkl.gz'
SABLEYE_PLAIN = '20260911_051621_Sableye_great.replay.pkl.gz'
DEOXYS = '20260910_225044_Deoxys_Defense_great.replay.pkl.gz'


def _load_brief():
    """Load scripts/deep_dive_brief.py by path (it is a script, not a module)."""
    if 'deep_dive_brief' in sys.modules:
        return sys.modules['deep_dive_brief']
    sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        'deep_dive_brief', SCRIPTS_DIR / 'deep_dive_brief.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['deep_dive_brief'] = mod
    spec.loader.exec_module(mod)
    return mod


B = _load_brief()


def _replay_dirs():
    """Where replay blobs may live: this clone, then a sibling checkout.

    A working clone of this repo shares the machine's blob store with the
    main checkout rather than duplicating 9 GB of pickles.
    """
    return [REPO_ROOT / 'userdata' / 'replay',
            REPO_ROOT.parent / 'gopvpsim' / 'userdata' / 'replay']


def find_blob(name):
    for d in _replay_dirs():
        p = d / name
        if p.exists():
            return p
    return None


def require_blob(name):
    p = find_blob(name)
    if p is None:
        pytest.skip(f"{name} is not on this machine")
    return p


@pytest.fixture(scope='module')
def sableye_shadow_facts():
    path = require_blob(SABLEYE_SHADOW)
    state = B.load_blob(str(path))
    return state, B.compute_brief(state, 0, str(path)), str(path)


# ---------------------------------------------------------------------------
# The win predicate contract
# ---------------------------------------------------------------------------

def test_win_cube_is_the_is_win_predicate():
    """win_cube must agree with gopvpsim.battle.is_win spread by spread."""
    from gopvpsim.battle import is_win, WIN_RATING
    scores = np.array([[[0, 499, WIN_RATING, WIN_RATING + 1, 1000]]],
                      dtype=np.int32)
    got = B.win_cube(scores)
    want = np.array([[[is_win(int(s)) for s in scores[0][0]]]])
    assert got.tolist() == want.tolist()
    assert not is_win(WIN_RATING), "500 is a tie, not a win"


# ---------------------------------------------------------------------------
# Percentages (pre-fix record: 4095/4096 rendered as "100.0%")
# ---------------------------------------------------------------------------

def test_pct_never_renders_a_false_exact():
    assert B.pct(4095 / 4096) != '100.0%'      # pre-fix value
    assert float(B.pct(4095 / 4096)[:-1]) < 100.0
    assert B.pct(1 / 4096) != '0.0%'           # pre-fix value
    assert float(B.pct(1 / 4096)[:-1]) > 0.0
    assert B.pct(1.0) == '100.0%'              # a real 100 still prints plainly
    assert B.pct(0.0) == '0.0%'


# ---------------------------------------------------------------------------
# Print precision (pre-fix record: rounding 149.689078 to "149.69")
# ---------------------------------------------------------------------------

def test_printed_cut_floors_and_stays_a_valid_selector():
    """A printed '>=' line must select exactly the set the cut selects.

    The Sableye 1v1 Hippowdon rung is 149.689078 and 19 spreads sit exactly
    on it. Rounding to nearest prints 149.69, which excludes those 19: the
    rung holds 1538 spreads and the printed line would select 1519.
    """
    attained = np.array([149.5, 149.622718, 149.689078, 149.8, 150.0])
    printed, dp = B.printed_cut(149.689078, attained, field='test')
    assert printed == pytest.approx(149.68)                 # not 149.69
    assert dp == 2
    assert (attained >= printed).sum() == (attained >= 149.689078).sum()
    assert (attained >= 149.69).sum() < (attained >= 149.689078).sum()


def test_printed_cut_escalates_past_three_places_when_it_has_to():
    """Def values pack closer than a thousandth; the line must still select."""
    T = 102.37156897499999
    attained = np.array([102.3715, 102.37156, T, 102.372, 103.0])
    printed, dp = B.printed_cut(T, attained, field='test')
    assert dp > 3
    assert (attained >= printed).sum() == (attained >= T).sum()


def test_stage7_aborts_for_a_floor_it_cannot_print_in_three_places():
    """The floor keeps the plan's strict rule: 2 dp, 3 dp, then raise."""
    T = 102.37156897499999
    attained = np.array([102.3715, 102.37156, T, 102.372])
    with pytest.raises(B.GuardError) as exc:
        B.stage7_print_precision(T, attained, field='Floor',
                                 ctx={'cell': '2v2 Lapras'})
    assert 'G-print' in str(exc.value)
    assert 'field=Floor' in str(exc.value)


# ---------------------------------------------------------------------------
# Clean cuts
# ---------------------------------------------------------------------------

def test_clean_cut_is_exact_in_both_directions():
    stat = np.array([1.0, 2.0, 3.0, 4.0])
    assert B.clean_cut(stat, np.array([False, False, True, True]))[:2] == (3.0, 2)
    # one winner below the minimum winner's value would still pass a
    # one-sided test; a loser ABOVE it must not.
    assert B.clean_cut(stat, np.array([False, True, False, True])) is None
    assert B.clean_cut(stat, np.array([True, True, True, True])) is None
    assert B.clean_cut(stat, np.array([False, False, False, False])) is None


# ---------------------------------------------------------------------------
# Types (pre-fix record: every species read as ['normal'])
# ---------------------------------------------------------------------------

def test_species_types_come_from_the_full_gamemaster_entry():
    """get_species returns baseStats only, which has no 'types' key.

    parse_types then fell back to ['normal'] for every species, which gave
    stage 4b the wrong STAB and the wrong effectiveness on every breakpoint
    test it ran.
    """
    from gopvpsim.moves import parse_types
    from gopvpsim.pokemon import get_species
    assert parse_types(get_species('Sableye')) == ['normal']    # pre-fix value
    assert B._species_types('Sableye') == ('dark', 'ghost')
    assert B._species_types('Annihilape') == ('fighting', 'ghost')


def test_breakpoint_label_finds_the_mirror_step_at_plus_one_defense():
    """Sableye's Foul Play into a +1 Def mirror steps 58 -> 59 at the cut."""
    from gopvpsim.moves import get_moves
    _fast, charged = get_moves()
    build = B.opponent_build('Sableye (Shadow)', 'great', 'pvpoke')
    assert build is not None
    types = B._species_types('Sableye')
    cut = {'T': 148.5539982, 'axis': 'atk'}
    got = B.breakpoint_label(cut, 148.457638212, types, build, types,
                             'SHADOW_CLAW / DRAIN_PUNCH, FOUL_PLAY',
                             [charged['FOUL_PLAY'], charged['DRAIN_PUNCH']])
    assert got is not None
    assert got['move'] == 'FOUL_PLAY'
    assert (got['from'], got['to']) == (58, 59)
    assert got['def_stage'] == 1

    # Positive control for the types fix: with the pre-fix type list the
    # step is invisible (Foul Play reads 61 -> 61 at stage 0, 49 -> 49 at +1).
    pre_fix = B.breakpoint_label(cut, 148.457638212, ('normal',), build,
                                 ('normal',),
                                 'SHADOW_CLAW / DRAIN_PUNCH, FOUL_PLAY',
                                 [charged['FOUL_PLAY'], charged['DRAIN_PUNCH']])
    assert pre_fix is None

    # Stage 0 alone must not label it either (the buff stage is the point).
    stage0_only = B.breakpoint_label(cut, 148.457638212, types, build, types,
                                     'SHADOW_CLAW / DRAIN_PUNCH, FOUL_PLAY', [])
    assert stage0_only is None


# ---------------------------------------------------------------------------
# Score-only steps (pre-fix record: 334 rows on the Sableye dive)
# ---------------------------------------------------------------------------

def _score_cube(columns):
    """(n_iv, 1, n_opp) score cube from per-opponent score lists."""
    arr = np.array(columns, dtype=np.int32).T
    return arr.reshape(arr.shape[0], 1, arr.shape[1])


def test_score_only_reports_only_clean_steps_in_either_direction():
    """A big swing is not a step: the two sides must not overlap.

    The pre-fix downward test compared min-above with max-below, which only
    says SOME spread above scores less than SOME spread below -- true on 334
    of the Sableye dive's cells and on almost any noisy column.
    """
    atk = np.array([100.0, 100.0, 101.0, 101.0])
    up = [600, 601, 700, 701]            # clean +99 step at 101.0
    noisy = [700, 601, 640, 620]         # overlapping: not a step either way
    down = [800, 801, 600, 601]          # clean -200 step at 101.0
    scores = _score_cube([up, noisy, down])
    state = {'shield_scenarios': [(0, 0)],
             'opponent_names': ['Up', 'Noisy', 'Down']}
    triage = {'all_win_mask': np.array([[True, True, True]]),
              'all_lose_mask': np.array([[False, False, False]])}
    rows = B.stage10_score_only(scores, atk, triage, state, [1, 2, 3])
    by_cell = {r['label']: r for r in rows}
    assert set(by_cell) == {'0v0 Up', '0v0 Down'}
    assert (by_cell['0v0 Up']['below'], by_cell['0v0 Up']['above']) == (601, 700)
    assert (by_cell['0v0 Down']['below'], by_cell['0v0 Down']['above']) == (800, 601)


# ---------------------------------------------------------------------------
# Degradation ladder, on synthetic cubes
# ---------------------------------------------------------------------------

def _triage_stub(contested):
    return {'n_contested': contested}


def test_degradation_rung_a_no_contested_cell():
    got = B.stage12_degradation(_triage_stub(0), [], [], None, 4, 4, 4096)
    assert got['rung'] == 'a'
    assert got['counts']['contested'] == 0
    assert 'No contested matchup' in got['sentence']


def test_degradation_rung_b_no_clean_cut_anywhere():
    got = B.stage12_degradation(_triage_stub(57), [], [], None, 4, 4, 4096)
    assert got['rung'] == 'b'
    assert '0 of 57' in got['sentence']
    assert 'stat product' in got['sentence']


def test_degradation_rung_c_cuts_exist_but_none_is_a_floor():
    cuts = [{'axis': 'atk'}] * 24
    rungs = [{'gates': {'G-direction': False, 'G-rank': True}}] * 3
    got = B.stage12_degradation(_triage_stub(115), cuts, rungs, None, 4, 5, 4096)
    assert got['rung'] == 'c'
    assert '24 clean cuts' in got['sentence']
    assert got['counts']['G-direction'] == 3


def test_degradation_rung_d_floor_too_rare_to_label():
    floor = {'T': 151.0, 'pool_share': 0.004, 'n_pass': 16}
    got = B.stage12_degradation(_triage_stub(40), [{'axis': 'atk'}], [floor],
                                floor, 4, 4, 4096)
    assert got['rung'] == 'd'
    assert '16 of 4096' in got['sentence']


def test_degradation_rung_e_is_a_caveat_not_a_ladder_stop():
    """(e) is orthogonal to (a)-(d): plain Sableye has a floor AND one arm."""
    assert B.stage12_caps(4, 4) is None
    caps = B.stage12_caps(4, 1)
    assert caps['rung'] == 'e'
    assert '1 moveset arm' in caps['sentence']
    floor = {'T': 148.0, 'pool_share': 0.5, 'n_pass': 2048}
    ladder = B.stage12_degradation(_triage_stub(140), [{'axis': 'atk'}],
                                   [floor], floor, 4, 1, 4096)
    assert ladder['rung'] == 'floor'      # the floor is not hidden by (e)


# ---------------------------------------------------------------------------
# Render gates: positive controls
# ---------------------------------------------------------------------------

CTX = {'blob': 'test.pkl.gz', 'arm': 0, 'mode': 'pvpoke'}


def test_gate_words_passes_clean_text():
    B.gate_words(["Atk >= 148.10 owns 0v1 Annihilape in Great League.",
                  "Clean cuts that most builds should clear."], CTX)


@pytest.mark.parametrize('word', ['definitive', 'recommended', 'best',
                                  'strong', 'solid', 'reliable', 'consistent',
                                  'worth', 'good', 'bad'])
def test_gate_words_rejects_each_banned_word(word):
    with pytest.raises(B.GuardError) as exc:
        B.gate_words([f"This line is {word} evidence."], CTX)
    assert 'G-words' in str(exc.value)
    assert word in str(exc.value)


def test_gate_words_allows_league_names_but_not_bare_great():
    B.gate_words(["Great League, Ultra League, Master League."], CTX)
    with pytest.raises(B.GuardError):
        B.gate_words(["The cut is great."], CTX)


def test_gate_words_allows_the_fixed_should_phrase_exactly_once():
    B.gate_words(["Clean cuts that most builds should clear."], CTX)
    with pytest.raises(B.GuardError) as exc:
        B.gate_words(["most builds should clear", "most builds should clear"],
                     CTX)
    assert 'G-words' in str(exc.value)
    with pytest.raises(B.GuardError):
        B.gate_words(["You should build for attack."], CTX)


def test_gate_words_rejects_non_ascii():
    with pytest.raises(B.GuardError) as exc:
        B.gate_words(["The cut is 148.10 → 2220 spreads."], CTX)
    assert 'G-words' in str(exc.value)
    assert 'not ASCII' in str(exc.value)


@pytest.mark.parametrize('word', ['mean', 'means', 'average', 'averaged'])
def test_gate_means_rejects_cohort_language(word):
    with pytest.raises(B.GuardError) as exc:
        B.gate_words([f"The clearers {word} 101.2 Def."], CTX)
    assert 'G-means' in str(exc.value)


def test_gate_names_rejects_a_dropped_name():
    facts = {'rungs_above': [{'names': ['a', 'b', 'c'], 'omitted': 1,
                              'n_cells': 4}],
             'rungs_below': [], 'alternative': None, 'rungs_above_tail': None}
    B.gate_names(facts, CTX)                       # 3 + 1 == 4: fine
    facts['rungs_above'][0]['names'] = ['a', 'b']  # drop one, keep "+1 more"
    with pytest.raises(B.GuardError) as exc:
        B.gate_names(facts, CTX)
    assert 'G-names' in str(exc.value)


def test_gate_names_rejects_a_miscounted_alternative_list():
    facts = {'rungs_above': [], 'rungs_below': [], 'rungs_above_tail': None,
             'alternative': {'guaranteed': ['x', 'y'], 'n_guaranteed': 2,
                             'given_up': ['z'], 'n_given_up': 9}}
    with pytest.raises(B.GuardError):
        B.gate_names(facts, CTX)


# ---------------------------------------------------------------------------
# Oracle pins on the worked Shadow Sableye case
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
def test_sableye_shadow_triage_and_clean_cut_counts(sableye_shadow_facts):
    _state, facts, _path = sableye_shadow_facts
    assert (facts['triage']['all_win'], facts['triage']['all_lose'],
            facts['triage']['contested']) == (278, 245, 161)
    assert facts['clean_counts'] == {'atk': 40}          # 40 atk, 0 def, 0 hp
    assert facts['n_distinct_atk_cuts'] == 29


@pytest.mark.local_artifacts
def test_sableye_shadow_floor_is_the_annihilape_cmp_line(sableye_shadow_facts):
    _state, facts, _path = sableye_shadow_facts
    fl = facts['floor']
    assert fl['T'] == pytest.approx(148.1039982)
    assert fl['printed'] == pytest.approx(148.10)
    assert fl['dp'] == 2
    assert fl['n_pass'] == 2220
    assert fl['cell'] == '0v1 Annihilape'
    assert fl['rank'] == 30
    assert fl['n_below'] == 1876
    assert fl['n_below_win'] == 0
    assert fl['score_below'] == [396, 396]
    assert fl['mech']['kind'] == 'cmp'
    assert fl['mech']['opp_ivs'] == (4, 13, 13)
    assert fl['mech']['opp_level'] == pytest.approx(17.0)
    assert fl['mech']['opp_cmp_atk'] == pytest.approx(123.3775648)
    assert fl['mech']['line'] == pytest.approx(1.2 * 123.3775648)
    assert fl['single_owner'] and fl['owners'] == ['Annihilape']
    assert (fl['modes_ok'], fl['modes_total']) == (4, 4)
    assert (fl['arms_ok'], fl['arms_total']) == (4, 4)


@pytest.mark.local_artifacts
def test_sableye_shadow_coverage_ladder_is_strict(sableye_shadow_facts):
    """The seven ladder rows, strict share / ties / focal clearers."""
    _state, facts, _path = sableye_shadow_facts
    rows = facts['coverage']['rows']
    got = [(round(100 * r['strict'], 1), r['ties'], r['focal']) for r in rows]
    assert got == [(3.6, 88, 2657), (14.6, 132, 2220), (43.1, 122, 1511),
                   (50.0, 57, 1405), (58.3, 79, 1109), (66.7, 154, 983),
                   (99.4, 25, 43)]
    assert 'ties the max-attack' in rows[-1]['label']
    assert rows[-1]['strict'] < 1.0, "a tie is not a win"


@pytest.mark.local_artifacts
def test_sableye_shadow_alternative_target(sableye_shadow_facts):
    _state, facts, _path = sableye_shadow_facts
    alt = facts['alternative']
    assert alt['def_cut'] == pytest.approx(101.4055, abs=1e-3)
    assert alt['def_printed'] == pytest.approx(101.40)   # floor, not 101.41
    assert alt['hp_cut'] == 125
    assert alt['n'] == 114
    assert alt['n_guaranteed'] == 9
    assert alt['n_given_up'] == 7
    assert facts['rank1']['in_alternative'] is True


@pytest.mark.local_artifacts
def test_sableye_shadow_rank1_and_not_claimed(sableye_shadow_facts):
    _state, facts, _path = sableye_shadow_facts
    r1 = facts['rank1']
    assert r1['ivs'] == (0, 15, 15)
    assert r1['level'] == pytest.approx(49.5)
    assert r1['clears_floor'] is False
    assert r1['n_cuts_cleared'] == 0
    assert r1['n_cuts'] == 40
    assert r1['total_won'] == 367
    assert r1['lowest_missed']['printed'] == pytest.approx(143.60)
    assert (facts['not_claimed']['n'], facts['not_claimed']['of']) == (121, 161)


@pytest.mark.local_artifacts
def test_sableye_shadow_level_51_view_prints_its_own_cut(sableye_shadow_facts):
    """D8: the two level views may never be quoted with one number."""
    _state, facts, _path = sableye_shadow_facts
    l51 = facts['l51']
    assert l51['clean'] is True
    assert l51['T'] == pytest.approx(148.096558, abs=1e-5)
    assert l51['printed'] == pytest.approx(148.09)
    assert l51['n_pass'] == 2345
    assert l51['n_selected_by_l50_literal'] == 2220


@pytest.mark.local_artifacts
def test_sableye_shadow_cost_diff_excludes_the_caveat_species(
        sableye_shadow_facts):
    _state, facts, _path = sableye_shadow_facts
    d = facts['cost']['diff']
    assert facts['cost']['reverse_cuts'] == 0
    assert (d['n_gained'], d['n_lost']) == (38, 24)
    assert (d['n_gained_with_caveat'], d['n_lost_with_caveat']) == (40, 25)
    assert d['caveat_excluded'] == 3


@pytest.mark.local_artifacts
def test_sableye_shadow_examples(sableye_shadow_facts):
    _state, facts, _path = sableye_shadow_facts
    got = {e['ivs']: e['total'] for e in facts['examples']}
    assert got == {(6, 9, 7): 371, (7, 2, 14): 382, (10, 13, 11): 371}


@pytest.mark.local_artifacts
def test_sableye_shadow_score_only_has_the_annihilape_step(
        sableye_shadow_facts):
    _state, facts, _path = sableye_shadow_facts
    rows = {(r['cell'], r['below'], r['above']) for r in facts['score_only']}
    assert ('0v0 Annihilape (Shadow)', 661, 888) in rows
    assert ('2v2 Lapras', 677, 843) in rows
    # pre-fix the same stage emitted 334 rows, almost all of them overlapping
    # swings rather than steps.
    assert len(facts['score_only']) < 60


@pytest.mark.local_artifacts
def test_plain_sableye_cmp_line_drops_the_shadow_multiplier():
    """The same fight, a plain focal: the line is 1.0x, the count is the same.

    Shadow Sableye flips 0v1 Annihilape at 148.10 with 2220 spreads clearing;
    plain Sableye flips it at 123.42 with the same 2220, because the whole
    attack axis is the shadow axis divided by 1.2.
    """
    path = require_blob(SABLEYE_PLAIN)
    state = B.load_blob(str(path))
    scores, meta = B.arm_view(state, 0, 'pvpoke')
    win = B.win_cube(scores)
    oi = state['opponent_names'].index('Annihilape')
    si = [i for i, p in enumerate(state['shield_scenarios'])
          if p == (0, 1)][0]
    T, n_pass, _prev, n_below = B.clean_cut(meta[:, 5], win[:, si, oi])
    assert T == pytest.approx(123.4199985)
    assert n_pass == 2220
    # The cut renders as 123.41, not the 123.42 a round-to-nearest gives:
    # 19 spreads sit at exactly 123.4199985 and "Atk >= 123.42" drops them,
    # selecting 2201 where the cut holds 2220.
    printed, dp = B.printed_cut(T, meta[:, 5], field='test')
    assert (printed, dp) == (123.41, 2)
    assert int((meta[:, 5] >= printed).sum()) == n_pass
    assert int((meta[:, 5] >= 123.42).sum()) == 2201
    assert n_below == 68        # not the 171 an earlier proposal quoted
    build = B.opponent_build('Annihilape', 'great', 'pvpoke')
    assert B.cmp_line(build, focal_shadow=False) == pytest.approx(123.3775648)
    assert B.cmp_line(build, focal_shadow=True) == pytest.approx(148.0530777)


# ---------------------------------------------------------------------------
# G-recompute: corrupt a fact, the render must refuse it
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
@pytest.mark.parametrize('path_to_corrupt,new_value', [
    (('floor', 'n_pass'), 2221),
    (('floor', 'pool_share'), 0.9),
    (('rank1', 'total_won'), 999),
    (('alternative', 'n'), 115),
])
def test_gate_recompute_catches_a_corrupted_number(sableye_shadow_facts,
                                                   path_to_corrupt, new_value):
    import copy
    state, facts, path = sableye_shadow_facts
    B.gate_recompute(state, 0, path, 'pvpoke', 'l50', facts, CTX)   # clean
    bad = copy.deepcopy(facts)
    node = bad
    for key in path_to_corrupt[:-1]:
        node = node[key]
    node[path_to_corrupt[-1]] = new_value
    with pytest.raises(B.GuardError) as exc:
        B.gate_recompute(state, 0, path, 'pvpoke', 'l50', bad, CTX)
    msg = str(exc.value)
    assert msg.startswith('G-recompute:')
    for token in ('field=', 'cell=', 'printed=', 'recomputed=', 'blob=',
                  'arm=', 'mode='):
        assert token in msg


@pytest.mark.local_artifacts
def test_gate_recompute_catches_a_corrupted_frontier_stat(
        sableye_shadow_facts):
    import copy
    state, facts, path = sableye_shadow_facts
    bad = copy.deepcopy(facts)
    bad['bulk']['frontier'][0]['max_def'] += 1.0
    with pytest.raises(B.GuardError) as exc:
        B.gate_recompute(state, 0, path, 'pvpoke', 'l50', bad, CTX)
    assert 'field=Bulk' in str(exc.value)


# ---------------------------------------------------------------------------
# Render: gates run, output is ASCII and deterministic
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
def test_render_is_ascii_and_carries_the_floor_line(sableye_shadow_facts):
    state, facts, path = sableye_shadow_facts
    html = B.render_facts(state, 0, path, facts)
    assert html.isascii()
    assert 'Atk &gt;= 148.10' in html
    assert '2220 of 4096 spreads' in html
    assert 'Annihilape' in html
    assert 'Auto-derived' in html


@pytest.mark.local_artifacts
def test_render_rejects_an_injected_banned_word(sableye_shadow_facts,
                                                monkeypatch):
    """Positive control for the render gate: the page must refuse to build."""
    state, facts, path = sableye_shadow_facts
    real = B.build_headline

    def poisoned(f):
        paras = real(f)
        return [paras[0] + ' This is the definitive line.'] + paras[1:]

    monkeypatch.setattr(B, 'build_headline', poisoned)
    with pytest.raises(B.GuardError) as exc:
        B.render_facts(state, 0, path, facts)
    assert 'G-words' in str(exc.value) and 'definitive' in str(exc.value)


@pytest.mark.local_artifacts
def test_render_rejects_injected_non_ascii(sableye_shadow_facts, monkeypatch):
    state, facts, path = sableye_shadow_facts
    real = B.build_headline
    monkeypatch.setattr(B, 'build_headline',
                        lambda f: [real(f)[0] + ' 148.10 → 2220'])
    with pytest.raises(B.GuardError) as exc:
        B.render_facts(state, 0, path, facts)
    assert 'not ASCII' in str(exc.value)


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_two_renders_are_byte_identical(tmp_path):
    """No render timestamp, no dict-ordering wobble: the page is a function
    of the blob plus the two stamped live reads."""
    path = require_blob(SABLEYE_SHADOW)
    a = tmp_path / 'a'
    b = tmp_path / 'b'
    B.run_blob(str(path), str(a), arms='0')
    B.run_blob(str(path), str(b), arms='0')
    slug = B.blob_slug(str(path))
    first = (a / f'{slug}_brief.html').read_bytes()
    second = (b / f'{slug}_brief.html').read_bytes()
    assert first == second
    assert (a / f'{slug}_brief.json').read_bytes() == \
           (b / f'{slug}_brief.json').read_bytes()


# ---------------------------------------------------------------------------
# The negative result is still a result (D12)
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
def test_deoxys_defense_has_no_floor_and_says_why():
    path = require_blob(DEOXYS)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    assert facts['floor'] is None
    assert facts['degradation']['rung'] == 'c'
    assert facts['clean_counts'].get('atk', 0) >= 1   # cuts exist ...
    assert facts['gate_tally']['n_eligible'] == 0     # ... none is eligible
    headline = B.build_headline(facts)
    assert len(headline) == 2
    joined = ' '.join(headline)
    assert 'no attack, Def or HP value is a build line' in joined
    assert 'contested matchups' in joined
    assert facts['dirty_thresholds'], "a negative must carry its evidence"
    for d in facts['dirty_thresholds']:
        assert d['rate_above'] > d['rate_below'], "a split must separate"
        assert 0 < d['n_above'] < facts['header']['n_iv']
    html = B.render_facts(state, 0, str(path), facts)
    assert html.isascii()
    assert 'Omitted: no floor; no coverage ladder.' in html


# ---------------------------------------------------------------------------
# The sweep table
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
def test_sweep_row_and_table(tmp_path, sableye_shadow_facts):
    _state, facts, _path = sableye_shadow_facts
    row = B.sweep_row(facts)
    assert len(row) == len(B.SWEEP_HEAD)
    assert row[0] == 'Sableye (Shadow) great'
    assert row[3].startswith('floor 148.10')
    assert row[4] == '40/0/0'
    out = B.write_sweep([row], str(tmp_path))
    text = Path(out).read_text()
    assert text.count('\n|') == 3          # header, rule, one row
    assert text.isascii()
