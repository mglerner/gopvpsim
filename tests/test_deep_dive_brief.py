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
import re
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


def _names_stub(**over):
    """Minimal facts dict gate_names accepts, with field 13 satisfiable."""
    facts = {
        'rungs_above': [], 'rungs_below': [], 'alternative': None,
        'rungs_above_tail': None,
        'not_claimed': {'n': 0, 'of': 5, 'rows': [], 'n_no_rule': 0,
                        'n_excluded_by_caveat': 0},
        'floor': None,
    }
    facts.update(over)
    return facts


def _rung_stub(names, omitted, n_cells):
    return {'names': names, 'omitted': omitted, 'n_cells': n_cells,
            'ranks': [None] * len(names),
            'mechs': [{'kind': 'unattributed', 'line': None}] * len(names)}


def test_gate_names_rejects_a_dropped_name():
    facts = _names_stub(rungs_above=[_rung_stub(['a', 'b', 'c'], 1, 4)])
    B.gate_names(facts, CTX)                       # 3 + 1 == 4: fine
    facts['rungs_above'][0]['names'] = ['a', 'b']  # drop one, keep "+1 more"
    with pytest.raises(B.GuardError) as exc:
        B.gate_names(facts, CTX)
    assert 'G-names' in str(exc.value)


def test_gate_names_rejects_a_rank_list_that_does_not_match_the_names():
    """D3 prints the rank inline, positionally, so the lists must line up."""
    row = _rung_stub(['a', 'b'], 0, 2)
    row['ranks'] = [12]                            # one rank, two names
    with pytest.raises(B.GuardError) as exc:
        B.gate_names(_names_stub(rungs_above=[row]), CTX)
    assert 'ranks' in str(exc.value)


def test_gate_names_rejects_a_mechanism_list_that_does_not_match_the_names():
    """One mechanism PER CELL: cells sharing a rung need not share a cause."""
    row = _rung_stub(['a', 'b'], 0, 2)
    row['mechs'] = row['mechs'][:1]
    with pytest.raises(B.GuardError) as exc:
        B.gate_names(_names_stub(rungs_above=[row]), CTX)
    assert 'mechanisms' in str(exc.value)


def test_gate_names_rejects_a_miscounted_alternative_list():
    facts = _names_stub(alternative={'guaranteed': ['x', 'y'],
                                     'n_guaranteed': 2,
                                     'given_up': ['z'], 'n_given_up': 9,
                                     'exclusive': [], 'n_exclusive': 0})
    with pytest.raises(B.GuardError):
        B.gate_names(facts, CTX)


# ---------------------------------------------------------------------------
# G-caveat as an exclusion, not only a floor gate
# ---------------------------------------------------------------------------

def test_gate_caveat_rejects_a_bare_caveat_species_mention():
    """Field 10 excludes Aegislash cells; every other field must say so too.

    Pre-fix, field 12's table led with 'Atk >= 147.56 | 1v1 Aegislash
    (Shield) | rank 72 | 625 -> 924' with no marker, on the same page whose
    field 10 says that cell carries an open engine divergence.
    """
    B.gate_caveat(["1v1 Aegislash (Shield)" + B.CAVEAT_MARK], CTX)
    with pytest.raises(B.GuardError) as exc:
        B.gate_caveat(["Atk >= 147.56 | 1v1 Aegislash (Shield) | 625 -> 924"],
                      CTX)
    assert 'G-caveat' in str(exc.value)
    assert 'Aegislash' in str(exc.value)


def test_caveat_mark_carries_the_word_the_gate_looks_for():
    """Positive control: the marker and the gate can never drift apart."""
    assert 'divergence' in B.CAVEAT_MARK
    assert B.CAVEAT_SPECIES, "an empty caveat list would disable the gate"


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
    # G-owner is over EVERY cell at this value AFTER dedup, not only the
    # eligible ones: the Close Combat + Rage Fist pool entry is the same
    # column as plain Annihilape, so it collapses; the Shadow entry does not
    # collapse but is the same base species.
    assert fl['single_owner'] and fl['owners'] == ['Annihilape']
    assert (fl['modes_ok'], fl['modes_total']) == (4, 4)
    assert (fl['arms_ok'], fl['arms_total']) == (4, 4)
    # Direction and cleanliness are separate counts; here they agree.
    assert (fl['modes_clean'], fl['arms_clean']) == (4, 4)


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
    # V2: the negative opens in plain English -- what is not there, what to
    # build instead, and the closest rule in its own numbers. Round 3's
    # wording is the pre-fix value for each of these.
    assert 'nothing on this arm is a build line to hunt for' not in joined
    assert joined.startswith('No single stat threshold decides a matchup')
    assert 'build for stat product' in joined
    assert 'The closest thing to a line is 100.65 attack in the 0v0 against '\
           'Araquanid (Shadow), rank 44: nothing below it wins, and 2284 of '\
           'the 2301 spreads at or above it do.' in joined
    assert 'is a one-sided gate' not in joined      # round-3 wording, G-voice
    assert 'ATK >= 100.65' not in joined            # round-3 wording
    # Pre-fix wording: the headline said "no attack, Def or HP value is a
    # build line" and then, in the same sentence, that 24 clean cuts exist --
    # with the clean-cut-versus-floor distinction that reconciles them never
    # stated. It is stated in field 2 now, and the gate tally in the evidence.
    assert 'no attack, Def or HP value is a build line' not in joined
    assert 'G-direction' not in joined and 'G-material' not in joined
    # The exact-cut census moved OUT of the headline and INTO field 2.
    assert '18 on attack' not in joined
    f2 = ' '.join(B._f2_floor(facts)['lines'])
    assert '24 single-stat values do separate a cell exactly (18 on attack, '\
           '5 on Def, 1 on HP' in f2
    assert facts['dirty_thresholds'], "a negative must carry its evidence"
    for d in facts['dirty_thresholds']:
        assert d['rate_above'] > d['rate_below'], "a split must separate"
        assert 0 < d['n_above'] < facts['header']['n_iv']
    html = B.render_facts(state, 0, str(path), facts)
    assert html.isascii()
    assert 'there is no floor on this arm' in html


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


# ---------------------------------------------------------------------------
# Round-2 fixes: each test below fails against the first build.
# ---------------------------------------------------------------------------

MELMETAL = '20260910_190103_Melmetal_great.replay.pkl.gz'
FURRET = '20260910_210146_Furret_great.replay.pkl.gz'
ALTARIA = '20260910_185430_Altaria_great.replay.pkl.gz'


@pytest.mark.local_artifacts
def test_plain_sableye_floor_is_clean_in_two_of_four_not_four():
    """"Clean in N of M" counted SEPARABILITY, not the printed line.

    Round 1 printed "Holds: clean in 4 of 4 opponent-IV settings" over a
    floor whose per-setting table said "rank1 no clean cut (71.7% win)" two
    lines below. Round 2 split direction from "cleanliness" but measured the
    second at each view's OWN cut, so the count still did not describe the
    printed line: this floor separates in all four settings, at 123.41 in
    two of them and at 122.29 in the other two, and the printed line
    partitions only the two.
    """
    path = require_blob(SABLEYE_PLAIN)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    fl = facts['floor']
    assert fl['modes_ok'] == 4                    # pre-fix value, direction
    assert fl['modes_clean'] == 4                 # separability, any value
    clean_from_table = sum(1 for v in fl['per_mode_cuts'].values() if v['clean'])
    assert fl['modes_clean'] == clean_from_table
    # The two rank-1 settings separate at 122.29, not at the printed line.
    assert {m for m, v in fl['per_mode_cuts'].items()
            if v['printed'] != pytest.approx(123.41)} == {'rank1',
                                                          'rank1:nobait'}
    # Round 3: the headline stopped printing SEPARABILITY (each view's own
    # cut, at whatever value it sits) beside DIRECTION, because the two are
    # measured at different thresholds and the strict-looking one can exceed
    # the weak one. What it prints now is the partition of the SAME line.
    assert fl['modes_partition'] == 2
    assert fl['modes_partition'] <= fl['modes_ok']
    # V2: the partition count is a field-2 measurement, not a headline one
    # (G-voice bars the word from the verdict). Round 3's headline sentence,
    # "partitions the cell exactly in 2 of those settings", is the pre-fix
    # value; the same claim is made in full in field 2.
    text = ' '.join(B.build_headline(facts))
    assert 'partitions the cell exactly in 2 of those settings' not in text
    assert 'partition' not in text
    f2 = ' '.join(B._f2_floor(facts)['lines'])
    assert 'in 2 of 4 settings' in f2
    assert 'exactly clean in 2 of them' not in f2      # round-2 wording
    assert 'clean in 4 of 4' not in f2                 # round-1 wording


@pytest.mark.local_artifacts
def test_gate_recompute_catches_a_corrupted_clean_count():
    """Positive control for the clean-versus-direction split."""
    import copy
    path = require_blob(SABLEYE_PLAIN)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    B.gate_recompute(state, 0, str(path), 'pvpoke', 'l50', facts, CTX)
    bad = copy.deepcopy(facts)
    bad['floor']['modes_clean'] = 1               # the table says 4
    with pytest.raises(B.GuardError) as exc:
        B.gate_recompute(state, 0, str(path), 'pvpoke', 'l50', bad, CTX)
    assert 'G-recompute' in str(exc.value) and 'field=Floor' in str(exc.value)


@pytest.mark.local_artifacts
def test_rank1_membership_of_the_alternative_is_set_without_a_floor():
    """Deoxys' rank-1 IS inside the printed rectangle; the page said it was not.

    The pre-fix no-floor branch never assigned ``in_alternative``, so
    ``r1.get(...)`` returned None and field 4 printed the negative sentence
    unconditionally on all 14 no-floor arms.
    """
    path = require_blob(DEOXYS)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    assert facts['floor'] is None
    assert 'in_alternative' in facts['rank1']
    alt = facts['alternative']
    mask = ((facts_meta(state)[:, 6] >= alt['def_cut'])
            & (facts_meta(state)[:, 7] >= alt['hp_cut']))
    assert facts['rank1']['in_alternative'] is bool(mask[facts['rank1']['i']])
    assert facts['rank1']['in_alternative'] is True
    html = B.render_facts(state, 0, str(path), facts)
    assert 'It is a member of the Alternative target below.' in html
    assert 'It is not a member of the Alternative target below.' not in html


def facts_meta(state, arm=0, mode='pvpoke'):
    _scores, meta = B.arm_view(state, arm, mode)
    return meta


@pytest.mark.local_artifacts
def test_dirty_thresholds_must_beat_the_constant_rule_and_be_material():
    """A row worse than "nobody wins this" is worse than printing nothing.

    Pre-fix, Melmetal's headline named 2v2 Jellicent at HP >= 149.00 as
    "misclassifies 7 of 4096" on a cell won by exactly 1 spread -- where the
    constant rule gets 1 wrong -- and Deoxys named 2v2 Fearow at HP >= 90.00
    (4 wrong against a constant rule's 2), both on splits far outside the
    [10%, 90%] band the clean-cut ladder enforces.
    """
    for name in (MELMETAL, DEOXYS):
        path = require_blob(name)
        state = B.load_blob(str(path))
        facts = B.compute_brief(state, 0, str(path))
        rows = facts['dirty_thresholds']
        assert rows, "a negative must still carry evidence"
        for d in rows:
            assert d['n_wrong'] < d['constant_wrong']
            share = d['n_above'] / facts['header']['n_iv']
            assert B.MATERIAL_LO <= share <= B.MATERIAL_HI
            assert d['gain'] == d['constant_wrong'] - d['n_wrong']
        gains = [d['gain'] for d in rows]
        assert gains == sorted(gains, reverse=True), "ranked by what it rescues"
        text = ' '.join(B.build_headline(facts))
        assert 'Jellicent at HP >= 149.00' not in text     # pre-fix row
        assert 'Fearow at HP >= 90.00' not in text         # pre-fix row


@pytest.mark.local_artifacts
@pytest.mark.parametrize('path_to_corrupt,new_value', [
    (('coverage', 'rows', 1, 'strict'), 0.99),
    (('coverage', 'rows', 1, 'ties'), 9),
    (('floor', 'mech', 'line'), 99.0),
    (('not_claimed', 'n'), 999),
    (('score_only', 1, 'above'), 12345),
    (('l51', 'n_pass'), 1),
    (('catch', 0, 'n'), 9),
    (('rank1', 'ivs'), (9, 9, 9)),
    (('rank1', 'contested_won'), 1),
    (('bulk', 'cells_won_range'), [1, 2]),
    (('alternative', 'cells_won'), [1, 2]),
    (('alternative', 'n_exclusive'), 3),
])
def test_gate_recompute_now_covers_the_fields_it_used_to_miss(
        sableye_shadow_facts, path_to_corrupt, new_value):
    """Every one of these rendered with NO guard failure in the first build.

    A probe that corrupted one fact at a time and re-rendered found the
    coverage ladder's strict share (the column field 14 calls the real
    robustness measure), the floor's own mechanism arithmetic, the
    not-claimed total, field 12's score pair, the L51 count, the catch counts
    and rank-1's IVs all reaching the page unchecked.
    """
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
    assert str(exc.value).startswith(('G-recompute:', 'G-tie:'))


@pytest.mark.local_artifacts
def test_gate_tie_fires_at_render_time_not_only_at_compute_time(
        sableye_shadow_facts):
    """G-tie lived inside stage 5, so a render-layer defect could not hit it."""
    import copy
    state, facts, path = sableye_shadow_facts
    bad = copy.deepcopy(facts)
    bad['coverage']['rows'][-1]['strict'] = 1.0     # ties still 25
    with pytest.raises(B.GuardError) as exc:
        B.gate_recompute(state, 0, path, 'pvpoke', 'l50', bad, CTX)
    assert 'G-tie' in str(exc.value) or 'G-recompute' in str(exc.value)


@pytest.mark.local_artifacts
def test_tail_sentence_thresholds_are_valid_selectors(sableye_shadow_facts):
    """Pre-fix the tail printed 156.30 and 150.61 with round-to-nearest.

    "Atk >= 156.30" selects 6 spreads where that rung holds 9; "Atk >= 150.61"
    selects 1132 where its rung holds 1156. The same 150.607 value also
    rendered as "150.60" in another arm's tail, so one document said it two
    ways.
    """
    state, facts, path = sableye_shadow_facts
    _scores, meta = B.arm_view(state, 0, 'pvpoke')
    atk = meta[:, 5]
    t = facts['rungs_above_tail']
    assert t['n_rungs'] > 0
    assert t['max_printed'] == pytest.approx(156.29)        # not 156.30
    assert t['max_pool_printed'] == pytest.approx(150.60)   # not 150.61
    assert int((atk >= t['max_printed']).sum()) == t['max_n_pass']
    assert int((atk >= t['max_pool_printed']).sum()) == t['max_pool_n_pass']
    assert int((atk >= 156.30).sum()) < t['max_n_pass']     # pre-fix value
    assert int((atk >= 150.61).sum()) < t['max_pool_n_pass']


@pytest.mark.local_artifacts
def test_coverage_lines_and_sensitivity_are_valid_selectors(
        sableye_shadow_facts):
    """The coverage 'line' column is a selector: its focal count is its sum."""
    state, facts, path = sableye_shadow_facts
    _scores, meta = B.arm_view(state, 0, 'pvpoke')
    atk = meta[:, 5]
    for row in facts['coverage']['rows']:
        assert int((atk >= row['printed']).sum()) == row['focal']
    for row in facts['sensitivity']:
        if row['T'] is None:
            continue
        assert int((atk >= row['printed']).sum()) == int((atk >= row['T']).sum())


@pytest.mark.local_artifacts
def test_furret_aegislash_rung_is_excluded_and_the_caveat_is_printed():
    """G-caveat is an exclusion, not only a floor gate.

    Pre-fix, field 6 printed "Atk >= 120.83 | 0v0 Aegislash (Shield), 0v2
    Aegislash (Shield)" as an ordinary rung, and because those cells were
    CLAIMED they never reached field 13 either, so the caveat text appeared
    nowhere on the page.
    """
    path = require_blob(FURRET)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    named = [n for row in facts['rungs_above'] + facts['rungs_below']
             for n in row['names']]
    assert named, "this arm does have material rungs"
    assert not any('Aegislash' in n for n in named)     # pre-fix: present
    assert facts['not_claimed']['n_excluded_by_caveat'] >= 1
    html = B.render_facts(state, 0, str(path), facts)
    assert 'engine divergence' in html
    assert 'Atk &gt;= 120.83' not in html               # pre-fix string


@pytest.mark.local_artifacts
def test_rung_rows_print_the_opponent_rank_inline():
    """D3: lower-ranked rungs still print, with the rank inline."""
    path = require_blob(ALTARIA)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    rows = facts['rungs_below']
    assert rows
    ranked = [r for r in rows if any(x is not None for x in r['ranks'])]
    assert ranked
    html = B.render_facts(state, 0, str(path), facts)
    for r in ranked[:3]:
        rank = next(x for x in r['ranks'] if x is not None)
        assert f"(rank {int(rank)})" in html


@pytest.mark.local_artifacts
def test_plain_sableye_annihilape_rung_keeps_its_priority_mechanism():
    """One mechanism per CELL, not one per rung, and now it IS the floor.

    The 123.41 value owns 0v0 Marowak (a Foul Play breakpoint) and 0v1
    Annihilape (the 1.0 x 123.3776 priority line that the Shadow Sableye page
    prints as its own floor, on the same 2220 spreads). Labelling a whole row
    from cells[0] made the two pages tell different stories about one line.

    Round 3's rung merge (E3) promotes this value to the floor: the round-2
    floor sat 21 spreads lower at 123.34 for a single rank-35 Electrode cell,
    so the two Sableye pages headlined different opponents for what is one
    physical priority line.
    """
    path = require_blob(SABLEYE_PLAIN)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    fl = facts['floor']
    assert fl['cell'] == '0v1 Annihilape'        # round-2: 2v2 Electrode (H.)
    assert fl['n_pass'] == 2220                  # the shadow page's 2220
    assert fl['mech']['kind'] == 'cmp'
    assert fl['mech']['opp_cmp_atk'] == pytest.approx(123.3775648)
    assert fl['mech']['line'] == pytest.approx(1.0 * 123.3775648)
    assert fl['merged_from'][0]['n_pass'] == 2241
    assert fl['merged_from'][0]['n_below_floor_win'] == 21
    # The floor's SIBLINGS at the same value keep their own causes: 0v0
    # Marowak turns over at 123.42 by a FOUL_PLAY damage step, not by the
    # Annihilape priority line, and the page names each.
    sibs = {s['label']: s['mech'] for s in fl['siblings_at_T']}
    assert '0v0 Marowak' in sibs
    assert sibs['0v0 Marowak']['kind'] == 'breakpoint'   # pre-fix: 'cmp'
    assert sibs['0v0 Marowak']['move'] == 'FOUL_PLAY'
    assert sibs['0v1 Annihilape (Shadow)']['kind'] == 'cmp'
    html = B.render_facts(state, 0, str(path), facts)
    assert 'charge-move priority against Annihilape' in html
    assert 'FOUL_PLAY damage steps' in html


@pytest.mark.local_artifacts
def test_bulk_fork_is_stated_as_a_trade_when_it_is_not_exclusive(
        sableye_shadow_facts):
    """The headline sold a guarantee field 8 then retracted.

    Measured against the whole grid rather than against the floor's clearers,
    0 of the rectangle's 9 cells are exclusive to it -- on every floor arm in
    the corpus.
    """
    _state, facts, _path = sableye_shadow_facts
    alt = facts['alternative']
    assert (alt['n_guaranteed'], alt['n_exclusive']) == (9, 0)
    # V2: the headline states the trade as two counts in one sentence; the
    # exclusive-versus-grid retraction that round 3 put in the headline
    # ("is not exclusive") is field 8's wording now.
    text = ' '.join(B.build_headline(facts))
    assert 'gives up 7 matchups the line holds and picks up 9 it gives away' \
        in text
    assert 'is not exclusive' not in text                                # pre-fix
    assert 'It guarantees 9 contested cells the line cannot' not in text  # pre-fix
    f8 = ' '.join(B._f8_alternative(facts)['lines'])
    assert '0 of them' in f8 or 'not exclusive' in f8 or '9' in f8


@pytest.mark.local_artifacts
def test_melmetal_catch_line_does_not_claim_a_wild_catch():
    """Melmetal has no wild spawn; the pre-fix page said "Wild catches"."""
    path = require_blob(MELMETAL)
    state = B.load_blob(str(path))
    arm = next(i for i in range(len(state['moveset_data']))
               if B.compute_brief(state, i, str(path))['floor'] is not None)
    facts = B.compute_brief(state, arm, str(path))
    assert facts['acquisition'] == 'none'
    html = B.render_facts(state, arm, str(path), facts)
    assert 'Wild catches' not in html               # pre-fix string
    assert 'this species has no wild spawn' in html
    assert '10/10/10 IV floor' in html


def test_acquisition_class_is_driven_by_the_species_not_only_by_shadow():
    assert B.acquisition_class('Sableye', True) == 'grunt'
    assert B.acquisition_class('Sableye', False) == 'wild'
    assert B.acquisition_class('Melmetal', False) == 'none'
    assert B.acquisition_class('Deoxys (Defense)', False) == 'none'
    # Every class names its model and caveats it; pre-fix only shadow did.
    for cls in ('grunt', 'none', 'wild'):
        s = B._catch_sentence(cls, [{'target': 0.5, 'n': 2}], 'clear this line')
        assert 'Model:' in s and 'uniform-random IVs' in s


@pytest.mark.local_artifacts
def test_no_floor_alternative_is_rank_gated_and_reframed_when_wide():
    """Deoxys' rectangle was selected by two rank-110 Wartortle cells.

    On a no-floor arm the rectangle is the whole positive content of the
    brief, so only a top-50 opponent in a non-degenerate scenario may select
    it; and a rectangle covering more than 40% of the grid is re-framed
    rather than printed as a target.
    """
    path = require_blob(DEOXYS)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    alt = facts['alternative']
    assert alt is not None
    assert not any('Wartortle' in c for c in alt['exclusive'])   # pre-fix cells
    for cell in alt['exclusive']:
        rank = int(cell.rsplit('rank ', 1)[1].rstrip(')').split(';')[0])
        assert rank <= B.RANK_GATE
    path2 = require_blob(ALTARIA)
    state2 = B.load_blob(str(path2))
    facts2 = B.compute_brief(state2, 0, str(path2))
    assert facts2['alternative']['too_wide'] is True
    text = ' '.join(B.build_headline(facts2))
    assert 'Bulk does not separate either' in text
    assert 'is already 75.1% of the grid' in text
    assert 'already satisfy' not in text             # round-3 wording


@pytest.mark.local_artifacts
def test_melmetal_breakpoint_floor_does_not_say_the_mechanism_is_unattributed():
    path = require_blob(MELMETAL)
    state = B.load_blob(str(path))
    arm = next(i for i in range(len(state['moveset_data']))
               if B.compute_brief(state, i, str(path))['floor'] is not None)
    facts = B.compute_brief(state, arm, str(path))
    assert facts['floor']['mech']['kind'] == 'breakpoint'
    html = B.render_facts(state, arm, str(path), facts)
    assert 'mechanism unattributed; no coverage ladder' not in html  # pre-fix
    assert 'this floor is a damage breakpoint' in html


@pytest.mark.local_artifacts
def test_not_claimed_discloses_its_remainder(sableye_shadow_facts):
    """The only capped list in the document that did not."""
    state, facts, path = sableye_shadow_facts
    field = B._f13_not_claimed(facts)
    assert len(field['rows']) == field['n_listed']
    assert field['n_listable'] >= field['n_listed']
    joined = ' '.join(field['lines'])
    if field['n_listable'] > field['n_listed']:
        assert 'are listed' in joined and 'more are not' in joined


@pytest.mark.local_artifacts
def test_example_rows_keep_their_contested_cell_count_in_the_json(tmp_path):
    """json_safe drops the key 'cells'; the example field is renamed."""
    import json
    path = require_blob(SABLEYE_SHADOW)
    B.run_blob(str(path), str(tmp_path), arms='0')
    slug = B.blob_slug(str(path))
    data = json.loads((tmp_path / f'{slug}_brief.json').read_text())
    ex = data['arms'][0]['examples'][0]
    assert 'contested_cells' in ex                  # pre-fix: absent
    assert isinstance(ex['contested_cells'], int)


@pytest.mark.local_artifacts
def test_page_lead_block_names_the_arm_that_carries_the_line(tmp_path):
    """Melmetal's page opened on a no-line arm with no cross-arm sentence."""
    path = require_blob(MELMETAL)
    html_path, _json_path, all_facts = B.run_blob(str(path), str(tmp_path))
    page = Path(html_path).read_text()
    assert 'Arms on this page' in page
    with_floor = [f for f in all_facts if f['floor'] is not None]
    assert len(with_floor) == 1
    arm_no = with_floor[0]['header']['arm'] + 1
    assert f'carry a build line: arm {arm_no} at Atk &gt;=' in page


@pytest.mark.local_artifacts
def test_scenario_headers_come_from_the_blob(sableye_shadow_facts):
    state, facts, _path = sableye_shadow_facts
    want = [f"{a}v{b}" for a, b in state['shield_scenarios']]
    assert facts['header']['scenarios'] == want
    field = B._f9_examples(facts)
    assert field['extra_head'] == ['spread'] + want + ['total']
    for row in field['extra_rows']:
        assert len(row) == len(field['extra_head'])


@pytest.mark.local_artifacts
def test_rank1_win_counts_print_with_a_denominator(sableye_shadow_facts):
    """"wins 367 cells" gives the reader no scale; 684 is the denominator."""
    state, facts, path = sableye_shadow_facts
    r1 = facts['rank1']
    assert r1['total_won'] == 367
    assert r1['total_cells'] == 684
    assert 0 < r1['contested_won'] <= r1['n_contested'] == 161
    html = B.render_facts(state, 0, path, facts)
    assert '367 of 684 cells' in html


def test_settings_column_shows_a_range_when_cells_disagree():
    """A rung's MAX must not stand for a weaker cell sharing the value."""
    row = {'modes_ok': 4, 'modes_ok_min': 2, 'modes_total': 4}
    assert B._settings_col(row) == '2-4 of 4'
    assert B._settings_col({'modes_ok': 4, 'modes_ok_min': 4,
                            'modes_total': 4}) == '4/4'


def test_cmp_line_exactly_on_the_cut_is_tagged_as_a_tie():
    """1.2 x a default Shadow Sableye's 119.6685 IS the 143.60219826 cut."""
    build = B.opponent_build('Sableye (Shadow)', 'great', 'pvpoke')
    T = 1.2 * build['cmp_atk']
    cut = {'axis': 'atk', 'oi': 0, 'T': T, 'prev_attained': T - 0.2}
    state = {'shadow': True, 'opponent_names': ['Sableye (Shadow)']}
    mech = B.stage4_mechanism(cut, state, 'pvpoke', {0: build}, ('dark',),
                              'SHADOW_CLAW / FOUL_PLAY', {0: ('dark',)}, {0: []})
    assert mech['kind'] == 'cmp'
    assert mech['on_the_line'] is True
    text = B._mech_sentence(B._mech_facts(mech), True, 'Sableye (Shadow)')
    # Round 3 prints the equation at a precision where it closes under its
    # own digits; the round-2 text was "1.2 x 119.67 = 143.60 lands inside
    # the boundary", whose printed operands multiply to 143.604.
    assert '1.2 x 119.67 = 143.60' in text
    assert 'lands inside the boundary' not in text      # round-2 wording
    strictly_inside = dict(cut, T=T + 0.05)
    mech2 = B.stage4_mechanism(strictly_inside, state, 'pvpoke', {0: build},
                               ('dark',), 'SHADOW_CLAW / FOUL_PLAY',
                               {0: ('dark',)}, {0: []})
    assert mech2['on_the_line'] is False


def test_singular_plural_helper():
    assert B._noun(1, 'cell') == 'cell'
    assert B._noun(0, 'cell') == 'cells'
    assert B._noun(2, 'cell') == 'cells'


@pytest.mark.local_artifacts
def test_mirror_table_drops_the_dead_columns_without_a_floor():
    path = require_blob(DEOXYS)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    assert facts['floor'] is None
    field = B._f11_mirror(facts)
    if field['rows']:
        assert 'win rate below the floor' not in field['head']   # pre-fix col
        assert all(len(r) == len(field['head']) for r in field['rows'])
        assert not any('-' in r[1:] for r in field['rows'])


def test_cli_requires_an_output_directory():
    """--out defaulted to '.', so a forgotten flag wrote into the repo."""
    with pytest.raises(SystemExit):
        B.main(['some_blob.pkl.gz'])


@pytest.mark.local_artifacts
def test_field_12_marks_a_caveat_row_when_one_is_listed(sableye_shadow_facts,
                                                        monkeypatch):
    """Pre-fix, the 1v1 Aegislash step LED this table with no marker."""
    _state, facts, _path = sableye_shadow_facts
    rows = facts['score_only']
    assert rows[0]['caveat'] is False, "a caveat row never leads the table"
    assert any(r['caveat'] for r in rows), "the Aegislash step is still here"
    monkeypatch.setattr(B, 'SCORE_ROW_CAP', len(rows))
    field = B._f12_score_only(facts)
    marked = [r for r in field['rows'] if 'Aegislash' in r[1]]
    assert marked
    for r in marked:
        assert B.CAVEAT_MARK.strip() in r[1]
    B.gate_caveat(B.field_strings(field), CTX)     # the gate accepts it


@pytest.mark.local_artifacts
def test_a_priority_line_sitting_on_the_cut_is_tagged_on_the_page(
        sableye_shadow_facts):
    """The 1v0 mirror rung's line IS the cut, bit for bit.

    1.2 x a PvPoke-default Shadow Sableye's 119.6685 equals 143.60219826
    exactly, so a spread sitting on that cut ties rather than out-prioritises
    -- and the page's own Provenance says the engine seats an exact tie. The
    pre-fix row printed "lands inside the boundary" with no tag.
    """
    state, facts, path = sableye_shadow_facts
    rung = next(r for r in facts['rungs_below']
                if any(m['kind'] == 'cmp' and m['on_the_line']
                       for m in r['mechs']))
    assert rung['printed'] == pytest.approx(143.60)
    assert any('Sableye (Shadow)' in n for n in rung['names'])
    text = B._rung_mech_text(rung, True)
    assert 'falls exactly ON the cut' in text
    html = B.render_facts(state, 0, path, facts)
    assert 'falls exactly ON the cut' in html
    # Every other CMP rung on this dive is strictly interior and carries no tag.
    strict = [r for r in facts['rungs_below'] + facts['rungs_above']
              for m in r['mechs']
              if m['kind'] == 'cmp' and not m['on_the_line']]
    assert strict


# ---------------------------------------------------------------------------
# Round-3 fixes. Each test below fails against the round-2 build
# (commit f6cf5f5); the pre-fix value is recorded in the test or its docstring.
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
def test_melmetal_partition_count_can_never_exceed_the_direction_count():
    """The round-2 page printed a STRICTER test passing on MORE arms.

    Melmetal's SUPER_POWER arm carries the floor Atk >= 122.36. Round 2
    printed "Direction: ... 2 of 4 moveset arms" and, two lines below,
    "the partition is exact in 4 of 4 settings and 3 of 4 arms" -- 3 > 2 is
    impossible for two tests of one threshold. The 3 counted arms whose OWN
    cut exists (117.97 / 123.97 / 122.37), not arms the printed line
    partitions.
    """
    path = require_blob(MELMETAL)
    state = B.load_blob(str(path))
    arm = next(i for i in range(len(state['moveset_data']))
               if B.compute_brief(state, i, str(path))['floor'] is not None)
    facts = B.compute_brief(state, arm, str(path))
    fl = facts['floor']
    assert (fl['arms_ok'], fl['arms_clean']) == (2, 3)    # the pre-fix pair
    assert fl['arms_partition'] == 1                      # the honest number
    assert fl['arms_partition'] <= fl['arms_ok']
    assert fl['modes_partition'] <= fl['modes_ok']
    # V2: both counts live in field 2; the headline says only that the line
    # points the same way, in words. "1 of those arms" is the pre-fix
    # headline string.
    text = ' '.join(B.build_headline(facts))
    assert '1 of those arms' not in text
    assert 'points the same way' in text
    f2 = ' '.join(B._f2_floor(facts)['lines'])
    assert '1 of 4 arms' in f2
    assert 'exactly clean in 4 of them and 3 of 4 moveset arms' not in f2


@pytest.mark.local_artifacts
def test_separability_is_printed_with_the_values_it_counted():
    """E4: a bare count reads as corroboration; the values say what it is."""
    path = require_blob(MELMETAL)
    state = B.load_blob(str(path))
    arm = next(i for i in range(len(state['moveset_data']))
               if B.compute_brief(state, i, str(path))['floor'] is not None)
    facts = B.compute_brief(state, arm, str(path))
    html = B.render_facts(state, arm, str(path), facts)
    assert 'THIRD and non-comparable measurement' in html
    # The Dynamic Punch arm wins this cell with 4095 of 4096 spreads, so its
    # clean cut is not corroboration of anything.
    assert 'not a contested cell there' in html


@pytest.mark.local_artifacts
def test_gate_recompute_rejects_a_partition_count_above_the_direction_count():
    """Positive control for the ordering the round-2 page violated."""
    import copy
    path = require_blob(MELMETAL)
    state = B.load_blob(str(path))
    arm = next(i for i in range(len(state['moveset_data']))
               if B.compute_brief(state, i, str(path))['floor'] is not None)
    facts = B.compute_brief(state, arm, str(path))
    B.gate_recompute(state, arm, str(path), 'pvpoke', 'l50', facts, CTX)
    bad = copy.deepcopy(facts)
    bad['floor']['arms_partition'] = bad['floor']['arms_ok'] + 1
    with pytest.raises(B.GuardError) as exc:
        B.gate_recompute(state, arm, str(path), 'pvpoke', 'l50', bad, CTX)
    assert 'G-recompute' in str(exc.value)


def test_cmp_equation_closes_under_its_own_printed_digits():
    """Round 2 rounded operand and product independently, so it did not.

    "1.2 x 123.38 = 148.05" is false of its own printed numbers (the product
    is 148.056, which renders 148.06), and the apparent rounding direction
    flipped from line to line across the corpus.
    """
    for mult, cmp_atk in ((1.2, 123.3775648), (1.0, 123.29), (1.2, 123.88),
                          (1.2, 125.19), (1.2, 120.07), (1.2, 119.6684986)):
        line = mult * cmp_atk
        dp, operand, product = B.cmp_equation(mult, cmp_atk, line)
        assert f"{mult * float(operand):.{dp}f}" == product, (mult, cmp_atk)
        assert f"{line:.{dp}f}" == product
    # The round-2 rendering of the worked case, as a pre-fix value.
    assert B.cmp_equation(1.2, 123.3775648, 1.2 * 123.3775648)[1:] == (
        '123.3776', '148.0531')
    assert f"{1.2 * 123.38:.2f}" == '148.06'    # what round 2 printed as 148.05


def test_cmp_gap_clause_keeps_the_line_strictly_inside_the_printed_interval():
    mech = {'line': 1.2 * 123.3775648, 'gap_lo': 148.010638212,
            'gap_hi': 148.1039982}
    text = B.cmp_gap_clause(mech, 4)
    assert 'falls in the gap (148.0106, 148.1040]' in text
    lo, hi = text.split('(')[1].split(']')[0].split(', ')
    assert float(lo) < mech['line'] <= float(hi)
    assert B.cmp_gap_clause({'line': 1.0, 'gap_lo': float('-inf'),
                             'gap_hi': 2.0}, 2) == ''


def test_reachable_mask_restricts_only_the_iv_floored_classes():
    meta = np.zeros((4, 8))
    meta[:, :3] = [[10, 10, 10], [9, 15, 15], [15, 15, 15], [0, 0, 0]]
    for cls in ('wild', 'grunt'):
        m, restricted = B.reachable_mask(meta, cls)
        assert restricted is False and m.all()
    m, restricted = B.reachable_mask(meta, 'none')
    assert restricted is True
    assert list(m) == [True, False, True, False]


@pytest.mark.local_artifacts
def test_deoxys_bulk_rectangle_is_unreachable_and_says_so():
    """FATAL in round 2: the only actionable number on the page was a target
    no encounter can produce, printed as "10 for a 50% chance" under a caveat
    saying the 10/10/10 floor does NOT apply.

    Deoxys forms come from raids, research and trades, all of which floor
    every IV at 10. The rectangle Def >= 232.05 & HP >= 94 has 276 members
    and shares none of them with the 216 spreads that floor allows.
    """
    path = require_blob(DEOXYS)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    model = facts['alt_catch_model']
    assert model['restricted'] is True
    assert model['n_grid'] == 216
    assert model['n_reachable'] == 0                 # pre-fix: counted 276/4096
    assert model['share'] == 0.0
    html = B.render_facts(state, 0, str(path), facts)
    assert 'No spread that can land inside this rectangle is reachable' in html
    assert 'does NOT apply' not in html              # round-2 caveat wording
    # And the HEADLINE carries it, not only the acquisition line six fields
    # down, because the headline is the sentence a reader acts on.
    assert 'No spread inside it is reachable' in ' '.join(B.build_headline(facts))


@pytest.mark.local_artifacts
def test_melmetal_floor_catch_counts_over_the_reachable_grid():
    """The floor line takes the same restriction, in the other direction."""
    path = require_blob(MELMETAL)
    state = B.load_blob(str(path))
    arm = next(i for i in range(len(state['moveset_data']))
               if B.compute_brief(state, i, str(path))['floor'] is not None)
    facts = B.compute_brief(state, arm, str(path))
    cm = facts['catch_model']
    assert cm['restricted'] is True and cm['n_grid'] == 216
    assert 0 < cm['n_reachable'] < 216
    assert cm['share'] != facts['floor']['pool_share']   # pre-fix: equal
    assert facts['catch'][0]['n'] == B._encounters(cm['share'], 0.50)


@pytest.mark.local_artifacts
@pytest.mark.parametrize('path_to_corrupt,new_value', [
    (('rank1', 'n_cuts'), 41),
    (('rank1', 'n_cuts_cleared'), 3),
    (('rank1', 'shortfall'), 1.0),
    (('not_claimed', 'of'), 162),
    (('clean_counts',), {'atk': 39}),
    (('gate_tally', 'n_cuts'), 41),
    (('mirror', 'rows', 0, 'above'), 0.5),
    (('rungs_above_tail', 'max_n_pass'), 8),
    (('bulk', 'cogates', 0, 'rate_outside'), 0.5),
    (('examples', 0, 'contested_cells'), 3),
    (('examples', 0, 'sp_rank'), 3),
    (('level_reach', 'n_in_low'), 3),
    (('alternative', 'sp_share_lo'), 0.5),
    (('alternative', 'atk_lo'), 1.0),
    (('floor', 'energy', 'below'), [99]),
    (('cost', 'diff', 'caveat_excluded'), 99),
    (('grid_best', 'total'), 999),
    (('catch_model', 'n_reachable'), 99),
])
def test_gate_recompute_covers_the_round_2_probe_gaps(
        sableye_shadow_facts, path_to_corrupt, new_value):
    """25 reader-facing numbers rendered with no guard failure in round 2.

    A probe that corrupted one fact leaf at a time and re-rendered found
    three numbers in the HEADLINE verdict (rank-1's cut counts, its
    shortfall, the not-claimed denominator) and the whole of field 11 among
    them. Each is now a one-line re-derivation from arrays the guard already
    loads.
    """
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
    assert str(exc.value).startswith('G-recompute:')


@pytest.mark.local_artifacts
def test_sweep_arm_label_matches_the_page(sableye_shadow_facts):
    """Round 2 numbered arms 0-based in sweep.md and 1-based on the page."""
    _state, facts, _path = sableye_shadow_facts
    row = B.sweep_row(facts)
    assert row[1] == 'arm 1 of 4'                  # pre-fix: 'arm 0'
    fields = B.build_fields(facts)
    header = ' '.join(fields[0]['lines'])
    assert row[1] in header


@pytest.mark.local_artifacts
@pytest.mark.parametrize('blob', [SABLEYE_SHADOW, MELMETAL, FURRET, DEOXYS])
def test_hp_thresholds_print_as_integers_everywhere(blob):
    """Round 2 put "HP >= 142" and "HP >= 142.00" on one Melmetal page."""
    path = require_blob(blob)
    state = B.load_blob(str(path))
    out = []
    for arm in range(len(state['moveset_data'])):
        facts = B.compute_brief(state, arm, str(path))
        out.append(B.render_facts(state, arm, str(path), facts))
    text = '\n'.join(out)
    assert 'HP &gt;=' in text, "positive control: the page prints HP lines"
    assert not re.search(r'HP &gt;= \d+\.\d', text)


def test_stat_threshold_str_uses_the_integer_branch_for_hp():
    # It formats an ALREADY-FLOORED printed value (printed_cut does the
    # flooring), so the Def case is fed 101.40, not the 101.4055 cut.
    assert B.stat_threshold_str('hp', 142.0, 2) == 'HP >= 142'
    assert B.stat_threshold_str('def', 101.40, 2) == 'DEF >= 101.40'
    assert B.stat_threshold_str('atk', 148.103, 3) == 'ATK >= 148.103'


@pytest.mark.local_artifacts
def test_no_floor_arms_still_print_example_spreads():
    """Round 2 printed a silence sentence on exactly the pages that need it.

    "No floor on this arm, so there is no set of clearers to draw examples
    from" was field 9 on all 14 no-floor arms in the corpus, so the negative
    verdict never carried its positive half.
    """
    path = require_blob(DEOXYS)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    assert facts['floor'] is None
    assert len(facts['examples']) >= 2               # pre-fix: 0
    rules = [e['rule'] for e in facts['examples']]
    assert 'most cells won on the whole grid' in rules
    for e in facts['examples']:
        assert e['by_scenario'] and sum(e['by_scenario']) == e['total']
    html = B.render_facts(state, 0, str(path), facts)
    assert 'no set of clearers to draw examples from' not in html
    # V2 wording; "on this arm" is the pre-fix string (G-voice bars "arm").
    assert 'the whole IV decision here is' in html
    assert 'the whole IV decision on this arm is' not in html


@pytest.mark.local_artifacts
def test_grid_best_sizes_the_decision_against_rank_1():
    path = require_blob(DEOXYS)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    gb, r1 = facts['grid_best'], facts['rank1']
    assert gb['total'] >= r1['total_won']
    assert gb['n_tied'] >= 1
    text = B._grid_best_sentence(facts)
    # V2 says "matchups"; "cells wide" is the pre-fix string.
    assert f"{gb['total']}" in text and 'matchups wide' in text
    assert 'cells wide' not in text


def test_near_line_row_only_promotes_a_gate_or_a_near_miss():
    """The classifier, not the blob: a merely-accurate split is not a line."""
    assert B.near_line_row([]) is None
    gate = {'one_sided': True, 'near_exact': False}
    assert B.near_line_row([gate]) is gate
    near = {'one_sided': False, 'near_exact': True}
    assert B.near_line_row([near]) is near
    assert B.near_line_row([{'one_sided': False, 'near_exact': False}]) is None


@pytest.mark.local_artifacts
def test_furret_near_exact_rule_leads_its_headline():
    """A rule broken by ONE spread in 4096 is a verdict, not "nothing"."""
    path = require_blob(FURRET)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    d = facts['dirty_thresholds'][0]
    assert d['cell'] == '1v1 Lapras'
    assert d['n_wrong'] == 1 and d['near_exact'] is True
    # V2: one_sided covers BOTH clean-sided shapes, and this row is the
    # second one -- every spread at or above the line wins, and a single
    # spread below it wins too. Pre-fix this read False, because only the
    # "nothing below wins" shape counted, which is why Medicham's 108.39
    # (1978 of 1978 above, 56 of 2118 below) was printed as a plain dirty
    # split rather than as the gate it is.
    assert d['one_sided'] is True
    assert d['gate_side'] == 'sufficient'
    text = ' '.join(B.build_headline(facts))
    assert 'The closest thing to a line is 102.063 defense in the 1v1 '\
           'against Lapras (rank 37): every one of the 1614 spreads at or '\
           'above it wins, and 1 of the 2482 below it wins too.' in text
    assert 'nothing on this arm is a build line to hunt for' not in text


@pytest.mark.local_artifacts
def test_furret_clean_cut_denominators_reconcile():
    """Round 2 printed 28, 26 and 28 for one quantity, ten lines apart."""
    path = require_blob(FURRET)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    cc = facts['clean_counts']
    assert sum(cc.values()) == facts['gate_tally']['n_cuts']
    assert facts['clean_claimed'] + facts['clean_excluded'] == sum(cc.values())
    assert facts['clean_excluded'] == 2
    joined = ' '.join(B.build_headline(facts)) + ' ' + \
        facts['degradation']['sentence']
    assert 'excluded for an open engine divergence' in joined
    assert f"{facts['clean_claimed']} clean cuts" in joined


@pytest.mark.local_artifacts
def test_score_only_rows_are_ordered_by_distance_to_the_win_line(
        sableye_shadow_facts):
    """Round 2 sorted by step size, which leads with blowouts on both sides."""
    _state, facts, _path = sableye_shadow_facts
    rows = [r for r in facts['score_only'] if not r['caveat']]
    assert rows, "positive control: there are non-caveat score rows"
    dists = [r['to_win'] for r in rows]
    assert dists == sorted(dists)
    for r in rows:
        assert r['to_win'] == min(abs(r['below'] - B.WIN_RATING),
                                  abs(r['above'] - B.WIN_RATING))


@pytest.mark.local_artifacts
def test_not_claimed_names_the_coin_flips_one_per_species(
        sableye_shadow_facts):
    """Round 2 spent six slots on three opponents, four of them at 0% or 100%."""
    _state, facts, _path = sableye_shadow_facts
    field = B._f13_not_claimed(facts)
    cells = [row[0] for row in field['rows']]
    species = [c.split(' ', 1)[1].split(' (engine')[0] for c in cells]
    assert len(set(species)) == len(species), species
    rates = [float(row[2].rstrip('%')) for row in field['rows']]
    assert rates == sorted(rates, key=lambda v: abs(v - 50.0))
    assert abs(rates[0] - 50.0) <= abs(rates[-1] - 50.0)


@pytest.mark.local_artifacts
def test_alternative_target_prints_its_iv_envelope(sableye_shadow_facts):
    """E12: the step the genre ends on -- what the spreads actually look like."""
    _state, facts, _path = sableye_shadow_facts
    env = facts['alternative']['envelope']
    assert sum(c for _v, c in env['by_atk_iv']) == facts['alternative']['n']
    assert env['atk_iv'][0] <= env['atk_iv'][1]
    assert len(env['top_sp']) == 5
    html = B.render_facts(_state, 0, _path, facts)
    assert 'IV envelope of the members' in html


def test_field_order_is_the_reader_order_and_renumbers_from_one():
    assert sorted(B.FIELD_ORDER) == sorted(B.FIELD_DERIVATION_ORDER)
    assert len(B.FIELD_ORDER) == 15
    # Examples sits directly under Floor; Coverage moves back with the audit.
    assert B.FIELD_ORDER[:3] == ('_f1_header', '_f2_floor', '_f9_examples')
    assert B.FIELD_ORDER.index('_f3_coverage') > B.FIELD_ORDER.index('_f10_cost')


@pytest.mark.local_artifacts
def test_fields_render_in_the_reader_order(sableye_shadow_facts):
    _state, facts, _path = sableye_shadow_facts
    fields = B.build_fields(facts)
    assert [f['n'] for f in fields] == list(range(1, 16))
    titles = [f['title'] for f in fields]
    assert titles[:3] == ['Header', 'Floor', 'Example spreads']
    assert titles.index('Coverage') > titles.index('Cost')


@pytest.mark.local_artifacts
def test_coverage_column_prints_one_precision(sableye_shadow_facts):
    """Round 2 printed five rows at 2 dp and one at 3 in the same column."""
    _state, facts, _path = sableye_shadow_facts
    field = B._f3_coverage(facts)
    places = {len(row[1].split('.')[1]) for row in field['rows']}
    assert len(places) == 1, field['rows']
    assert max(r['dp'] for r in facts['coverage']['rows']) == places.pop()


@pytest.mark.local_artifacts
def test_dirty_table_prints_the_genre_precision_cost():
    """E8: the exact selector stays, with what one decimal place costs."""
    path = require_blob(FURRET)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    g = facts['dirty_thresholds'][0]['genre']
    assert g['printed'] == pytest.approx(102.0, abs=0.1)
    assert g['n_above'] >= facts['dirty_thresholds'][0]['n_above']
    html = B.render_facts(state, 0, str(path), facts)
    assert 'PvPoke and Poke Genie display' in html


@pytest.mark.local_artifacts
def test_both_sableye_pages_headline_the_same_priority_line():
    """E3: D1's literal "lowest eligible rung" made the verdict opponent flap.

    Round 2 headlined plain Sableye at 123.34 for ONE rank-35 Electrode cell
    while the value 21 spreads up owns four cells against three top-31
    opponents, and split the four Shadow Sableye arms between 148.01
    (Electrode) and 148.10 (Annihilape). Both are the same physical priority
    line against the same PvPoke-default Annihilape, 1.0x it on one page and
    1.2x it on the other, over the same 2220 spreads.
    """
    shadow_path = require_blob(SABLEYE_SHADOW)
    plain_path = require_blob(SABLEYE_PLAIN)
    sh_state = B.load_blob(str(shadow_path))
    pl_state = B.load_blob(str(plain_path))
    plain = B.compute_brief(pl_state, 0, str(plain_path))['floor']
    assert plain['cell'] == '0v1 Annihilape'
    assert plain['n_pass'] == 2220
    shadow_cells = set()
    for arm in range(len(sh_state['moveset_data'])):
        fl = B.compute_brief(sh_state, arm, str(shadow_path))['floor']
        assert fl is not None
        assert fl['n_pass'] == 2220                  # round-2: 2220 / 2239
        assert fl['printed'] == pytest.approx(148.10)
        shadow_cells.add(fl['cell'])
    assert shadow_cells == {'0v1 Annihilape'}        # round-2: two opponents
    assert (plain['mech']['opp_cmp_atk']
            == pytest.approx(B.compute_brief(sh_state, 0, str(shadow_path))
                             ['floor']['mech']['opp_cmp_atk']))


def test_stage6_merges_only_rungs_whose_clearer_sets_nearly_agree():
    """The merge rule itself, on hand-built rungs: no blob, no thresholds."""
    def rung(T, n, label):
        return {'T': T, 'n_pass': n, 'pool_share': n / 4096.0,
                'eligible': True, 'cells': [{'label': label}]}
    near = [rung(100.0, 2241, 'a'), rung(100.1, 2220, 'b')]
    got = B.stage6_select(near, n_iv=4096)
    assert got['T'] == 100.1                       # the HIGHER value
    assert [m['T'] for m in got['merged_from']] == [100.0]
    far = [rung(100.0, 2241, 'a'), rung(100.1, 2000, 'b')]
    got = B.stage6_select(far, n_iv=4096)
    assert got['T'] == 100.0                       # 241 apart: no merge
    assert 'merged_from' not in got
    # A merge may not walk the floor out of the decision band.
    out = [rung(100.0, 2241, 'a'), rung(100.1, 900, 'b')]
    assert B.stage6_select(out, n_iv=4096)['T'] == 100.0
    # Three in a row merge transitively while each step stays inside tol.
    chain = [rung(100.0, 2241, 'a'), rung(100.1, 2220, 'b'),
             rung(100.2, 2200, 'c')]
    got = B.stage6_select(chain, n_iv=4096)
    assert got['T'] == 100.2 and len(got['merged_from']) == 2


@pytest.mark.local_artifacts
def test_merged_cells_are_stated_as_bought_and_not_as_partitioned():
    """The merged-in cell turns over BELOW the line, so it is a weaker claim."""
    path = require_blob(SABLEYE_PLAIN)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    fl = facts['floor']
    m = fl['merged_from'][0]
    assert m['cells'][0]['label'] == '2v2 Electrode (Hisuian)'
    assert m['n_below_floor_win'] == 21
    # V2: the headline names the second matchup and says the claim is
    # weaker, in words; the "bought, not partitioned" pair of sentences is
    # field 2's, which is where the full claim is made. Those two strings are
    # the pre-fix headline values.
    text = ' '.join(B.build_headline(facts))
    assert 'The same line also takes the 2v2 against Electrode (Hisuian), '\
           'rank 35, though up to 21 of the 1876 builds below it win it too.'\
           in text
    assert 'bought, not partitioned' not in text
    assert 'up to 21 of the 1876 spreads under it win it as well' not in text
    f2 = ' '.join(B._f2_floor(facts)['lines'])
    assert 'Also buys: 2v2 Electrode (Hisuian) (rank 35)' in f2
    assert '21 spreads below the printed line win it too' in f2


@pytest.mark.local_artifacts
def test_gate_recompute_rejects_a_merge_outside_the_tolerance():
    """Positive control: a merged rung that is not actually close."""
    import copy
    path = require_blob(SABLEYE_PLAIN)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    B.gate_recompute(state, 0, str(path), 'pvpoke', 'l50', facts, CTX)
    bad = copy.deepcopy(facts)
    bad['floor']['merged_from'][0]['n_pass'] = 4000
    with pytest.raises(B.GuardError) as exc:
        B.gate_recompute(state, 0, str(path), 'pvpoke', 'l50', bad, CTX)
    assert 'Floor merge' in str(exc.value)


# ---------------------------------------------------------------------------
# V2: the two inexact floor primitives, their bars, and their badges
# ---------------------------------------------------------------------------

MEDICHAM = '20260911_071541_Medicham_great.replay.pkl.gz'
LAPRAS = '20260911_015923_Lapras_great.replay.pkl.gz'


def _one_cell_cube(wins):
    """A 1-cell win cube and an attack plane of 0..n-1, for the primitives.

    Synthetic on purpose: the eligibility bars are arithmetic over one
    column, and a blob would make the test a re-derivation of the same
    arrays the code just read.
    """
    wins = np.asarray(wins, dtype=bool)
    return wins, np.arange(wins.size, dtype=float)


def test_gate_primitive_takes_three_percent_dirt_and_refuses_four():
    """E2's bar: >= 97% of the dirty side has to point the right way."""
    n = 4096
    half = n // 2
    # NECESSARY shape: nothing below the line wins; 3% of the spreads above
    # it lose. That is a line. 4% is not.
    for dirt, want in ((int(0.03 * half), True), (int(0.04 * half), False)):
        wins = np.zeros(n, dtype=bool)
        wins[half:] = True
        # The losers have to sit at the TOP of the above side, not at its
        # bottom edge: contiguous dirt against the boundary just moves the
        # boundary, and the cell comes out exact.
        wins[n - dirt:] = False
        _w, stat = _one_cell_cube(wins)
        cands = [c for c in B.gate_cuts(stat, wins) if c['kind'] == 'gate']
        assert cands, "the gate value itself must always be found"
        c = next(c for c in cands if c['gate_side'] == 'necessary')
        assert c['n_win_below'] == 0
        assert B.primitive_ok(c, n) is want, (dirt, c['rate_above'])


def test_sufficient_gate_takes_three_percent_dirt_and_refuses_four():
    """The other clean-sided shape: Medicham's 1v1 Snorlax, as arithmetic."""
    n = 4096
    half = n // 2
    for dirt, want in ((int(0.03 * half), True), (int(0.04 * half), False)):
        wins = np.zeros(n, dtype=bool)
        wins[half:] = True                       # everything above wins
        wins[:dirt] = True                       # winners BELOW the line
        _w, stat = _one_cell_cube(wins)
        c = next(c for c in B.gate_cuts(stat, wins)
                 if c['kind'] == 'gate' and c['gate_side'] == 'sufficient')
        assert c['n_win_above'] == c['n_above']
        assert B.primitive_ok(c, n) is want, (dirt, c['rate_below_loss'])


def test_near_exact_takes_point_four_percent_and_refuses_point_six():
    """E2's other bar: at most 0.5% of the GRID on the wrong side in total."""
    n = 4096
    half = n // 2
    assert B.near_exact_limit(n) == 20           # 0.5% of 4096, rounded
    for share, want in ((0.004, True), (0.006, False)):
        wrong = int(round(share * n))
        lo = wrong // 2
        hi = wrong - lo
        wins = np.zeros(n, dtype=bool)
        wins[half:] = True
        # Dirt on BOTH sides, and away from the boundary on both, so the row
        # is near-exact rather than one of the two clean-sided shapes.
        wins[:lo] = True                         # winners at the very bottom
        wins[n - hi:] = False                    # losers at the very top
        _w, stat = _one_cell_cube(wins)
        T, n_wrong = B.best_split(stat, wins)
        c = B.cut_counts(stat, wins, T)
        assert c['kind'] == 'near_exact'
        assert c['n_wrong'] == n_wrong == wrong
        assert B.primitive_ok(c, n) is want, (wrong, c['n_wrong'])


def test_exact_cut_outranks_a_gate_within_half_an_attack_point():
    """The tie-break, on hand-built rungs: no blob, no thresholds."""
    def rung(T, n, label, kind):
        return {'T': T, 'n_pass': n, 'pool_share': n / 4096.0, 'kind': kind,
                'eligible': True, 'cells': [{'label': label}]}
    close = [rung(100.0, 2000, 'a', 'gate'), rung(100.4, 1990, 'b', 'exact')]
    assert B.stage6_select(close, n_iv=4096)['T'] == 100.4      # exact wins
    far = [rung(100.0, 2000, 'a', 'gate'), rung(100.6, 1990, 'b', 'exact')]
    assert B.stage6_select(far, n_iv=4096)['T'] == 100.0        # D1 wins
    # Restricting the pool to one primitive is what the evidence block audits.
    assert B.stage6_select(close, n_iv=4096, kinds=('exact',))['T'] == 100.4
    assert B.stage6_select(close, n_iv=4096, kinds=('gate',))['T'] == 100.0
    assert B.stage6_select(close, n_iv=4096, kinds=('near_exact',)) is None
    # A non-exact pick never merges: the merged-in claim needs an exact
    # partition to prove it, and a gate cannot supply one.
    merge = [rung(100.0, 2241, 'a', 'gate'), rung(100.05, 2220, 'b', 'gate')]
    assert 'merged_from' not in B.stage6_select(merge, n_iv=4096)


@pytest.mark.local_artifacts
def test_medicham_now_carries_a_gate_floor_and_badges_it():
    """Michael's round-4 re-check, and what the other gates do with it.

    The 1v1 Snorlax value he named, 108.3987 (1978 of 1978 above win, 56 of
    2118 below win), IS a sufficient gate and is now in the floor pool -- and
    it fails G-direction, holding in 3 of the 4 baked opponent-IV settings.
    The line the page prints is the next one up that holds in all four.
    """
    path = require_blob(MEDICHAM)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    fl = facts['floor']
    assert fl is not None                        # pre-fix: None, rung c
    assert fl['kind'] == 'gate' and fl['gate_side'] == 'sufficient'
    assert fl['badge'] == 'one-sided gate'
    assert fl['cell'] == '0v1 Snorlax (Shadow)'
    assert (fl['n_win_above'], fl['n_above']) == (1455, 1455)
    assert fl['n_win_below'] == 55
    assert fl['modes_ok'] == fl['modes_total'] == 4
    html = B.render_facts(state, 0, str(path), facts)
    assert 'Primitive: ONE-SIDED GATE (sufficient)' in html
    # The negative-page wording must not survive anywhere on a page that now
    # carries a line. ("no floor clearer" is field 8's rule text and is about
    # the rectangle, not about this arm.)
    for dead in ('no floor on this arm', 'No floor on this arm',
                 'no attack floor on this arm',
                 'nothing on this arm is a build line',
                 'No single stat threshold decides',
                 'and none is a floor'):
        assert dead not in html, dead


@pytest.mark.local_artifacts
def test_a_gate_floors_page_never_claims_an_exact_partition():
    """A badge is a claim about the wrong side, so it gates the sentences."""
    path = require_blob(LAPRAS)
    state = B.load_blob(str(path))
    facts = B.compute_brief(state, 0, str(path))
    fl = facts['floor']
    assert fl['kind'] == 'gate' and fl['n_win_below'] == 56
    f2 = ' '.join(B._f2_floor(facts)['lines'])
    assert 'Primitive: ONE-SIDED GATE' in f2
    assert 'Decides: 2v2 Jellicent' in f2         # not "Owns:"
    assert 'Owns:' not in f2
    # The v1 template printed "At or above: N of N win" unconditionally.
    assert f"At or above: {fl['n_win_above']} of {fl['n_above']} win" in f2


@pytest.mark.local_artifacts
def test_gate_recompute_rejects_a_wrong_primitive_badge(sableye_shadow_facts):
    """Positive control for G-primitive."""
    import copy
    state, facts, path = sableye_shadow_facts
    B.gate_recompute(state, 0, path, 'pvpoke', 'l50', facts, CTX)
    for key, bad_value in (('kind', 'gate'), ('n_wrong', 7),
                           ('n_win_below', 3)):
        bad = copy.deepcopy(facts)
        bad['floor'][key] = bad_value
        with pytest.raises(B.GuardError) as exc:
            B.gate_recompute(state, 0, path, 'pvpoke', 'l50', bad, CTX)
        assert 'Floor primitive' in str(exc.value)


# ---------------------------------------------------------------------------
# V2: G-voice -- the headline is written for a reader, not for the audit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('word', ['partition', 'partitions', 'one-sided gate',
                                  'constant rule', 'separability', 'gap (',
                                  'carry a floor label', 'arm', 'arms',
                                  'cell', 'cells', 'clearers'])
def test_gate_voice_rejects_every_barred_headline_word(word):
    with pytest.raises(B.GuardError) as exc:
        B.gate_voice([f"The line is 148.10 attack and the {word} is here."],
                     CTX)
    assert 'G-voice' in str(exc.value)


def test_gate_voice_passes_the_voice_it_is_there_to_protect():
    """Positive control: the sentence Michael wrote as the target."""
    B.gate_voice(["Most Annihilape should have at least 148.10 attack; that "
                  "is the priority line against a typical Annihilape and it "
                  "decides the 0v1 outright; rank-1 misses it by 6.35."], CTX)


def test_gate_voice_does_not_fire_on_a_move_name_containing_arm():
    """CHARM is a fast move; \\barm\\b must not match inside it."""
    B.gate_voice(["Most Clefable running CHARM / MOONBLAST should have at "
                  "least 100.00 attack."], CTX)


@pytest.mark.local_artifacts
def test_render_rejects_an_audit_word_injected_into_the_headline(
        sableye_shadow_facts, monkeypatch):
    """Positive control at render time, not only on the gate in isolation."""
    state, facts, path = sableye_shadow_facts
    real = B.build_headline
    monkeypatch.setattr(
        B, 'build_headline',
        lambda f: [real(f)[0] + ' It partitions the cell exactly.']
                  + real(f)[1:])
    with pytest.raises(B.GuardError) as exc:
        B.render_facts(state, 0, path, facts)
    assert 'G-voice' in str(exc.value)


@pytest.mark.local_artifacts
def test_every_rendered_headline_in_the_corpus_passes_the_voice_gate():
    """The gate is only worth having if it runs on the real pages."""
    seen = 0
    for name in (SABLEYE_SHADOW, SABLEYE_PLAIN, DEOXYS, MELMETAL, FURRET,
                 ALTARIA, MEDICHAM, LAPRAS):
        path = find_blob(name)
        if path is None:
            continue
        state = B.load_blob(str(path))
        for arm in range(len(state['moveset_data'])):
            facts = B.compute_brief(state, arm, str(path))
            head = B.build_headline(facts)
            assert len(head) == 2
            B.gate_voice(head, CTX)
            strip = B.build_strip(facts)
            assert len(strip) == 5
            B.gate_voice([f"{k}: {v}" for k, v in strip], CTX)
            seen += 1
    if seen == 0:
        pytest.skip('no replay blob on this machine')
    assert seen >= 8


# ---------------------------------------------------------------------------
# V2: the at-a-glance strip
# ---------------------------------------------------------------------------

@pytest.mark.local_artifacts
def test_strip_labels_switch_with_the_result(sableye_shadow_facts):
    _state, facts, _path = sableye_shadow_facts
    assert [k for k, _v in B.build_strip(facts)] == list(B.STRIP_LABELS_FLOOR)
    path = require_blob(DEOXYS)
    state = B.load_blob(str(path))
    none = B.compute_brief(state, 0, str(path))
    strip = B.build_strip(none)
    assert [k for k, _v in strip] == list(B.STRIP_LABELS_NONE)
    assert dict(strip)['Line'] == 'none'
    assert dict(strip)['Decision width'] == '6 matchups'


@pytest.mark.local_artifacts
def test_strip_line_carries_the_headline_precision(sableye_shadow_facts):
    """Item 5: the exact selector shows only where the guard forced 3 dp."""
    _state, facts, _path = sableye_shadow_facts
    assert dict(B.build_strip(facts))['Line'].startswith(
        'Atk >= 148.10 [exact]')
    assert B.headline_value(148.10, 2) == '148.10'
    path = require_blob(SABLEYE_PLAIN)
    state = B.load_blob(str(path))
    plain = B.compute_brief(state, 0, str(path))
    assert plain['floor']['dp'] == 3
    assert B.headline_value(plain['floor']['printed'], 3) == '123.42 (123.419)'
    assert '123.42 (123.419)' in dict(B.build_strip(plain))['Line']


@pytest.mark.local_artifacts
def test_the_evidence_block_audits_each_primitive(sableye_shadow_facts):
    """E2: the page shows what each primitive alone would have chosen."""
    _state, facts, _path = sableye_shadow_facts
    picks = facts['primitive_picks']
    assert set(picks) == {'exact', 'gate', 'near_exact'}
    assert picks['exact']['cell'] == '0v1 Annihilape'
    text = ' '.join(B.build_evidence(facts)['lines'])
    assert 'Floor pool by primitive' in text
    assert 'exact -> Atk >= 148.10' in text
    assert 'Selected: the exact at Atk >= 148.10' in text
