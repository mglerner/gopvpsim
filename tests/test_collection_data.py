"""Strong pin for the IV scanner's league-capped level ceiling.

`DATA.collection.maxLevel` is what the in-page IV scanner feeds into
`ivsToStatsAtCap` / `matchMons` (`deep_dive_engine.js`), so a re-hardcode
to a bare 51.0 silently shows GL/UL owned mons one level too high -- the
bug fixed by `9f55e38` and never pinned since. Design:
`docs/reviews/2026-06-28_iv_scanner_maxlevel_strong_pin_design.md`
(Option 1: `build_collection_data()` extracted from
`generate_interactive_html` so this is a fast unit test, not a render).

Also pins the two traps that make the extraction safe:

* the emitted dict's LITERAL key order (replay-vs-original HTML diffing
  is byte-for-byte, and `json.dumps` preserves insertion order), and
* that `LEAGUE_MAX_LEVEL` is read at CALL time -- `main()` mutates it in
  place for `--max-level`.
"""
import sys
from pathlib import Path

from tests.conftest import load_deep_dive

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

deep_dive = load_deep_dive()

from gopvpsim.pokemon import LEAGUE_MAX_LEVEL, LEAGUES  # noqa: E402

SPECIES = 'Azumarill'


def _build(league, **kw):
    return deep_dive.build_collection_data(
        SPECIES, league, kw.pop('shadow', False),
        kw.pop('tier_info', []), kw.pop('best_buddy', None))


def test_collection_maxlevel_is_league_capped_all_leagues():
    """maxLevel == the league's ceiling for EVERY league, not a constant.

    Great/Ultra cap at 50.0 and Little/Master at 51.0, so a re-hardcode to
    51.0 (the pre-`9f55e38` value) fails the great/ultra legs, and a
    hardcode to 50.0 fails the little/master legs.
    """
    # The pin is only as strong as the table's spread: assert up front that
    # the four leagues really do disagree, so this can't degrade into four
    # copies of the same assertion if LEAGUES is ever flattened.
    assert set(LEAGUE_MAX_LEVEL) == set(LEAGUES) == {
        'little', 'great', 'ultra', 'master'}
    assert len(set(LEAGUE_MAX_LEVEL.values())) > 1
    assert LEAGUE_MAX_LEVEL['great'] == LEAGUE_MAX_LEVEL['ultra'] == 50.0
    assert LEAGUE_MAX_LEVEL['little'] == LEAGUE_MAX_LEVEL['master'] == 51.0

    for league in ('great', 'ultra', 'master', 'little'):
        cd = _build(league)
        assert cd is not None, f'{SPECIES} missing from the pokemon index'
        assert cd['maxLevel'] == LEAGUE_MAX_LEVEL[league], (
            f'{league}: collection.maxLevel {cd["maxLevel"]} != league '
            f'ceiling {LEAGUE_MAX_LEVEL[league]}')


def test_collection_maxlevel_reads_league_table_at_call_time():
    """`main()` mutates LEAGUE_MAX_LEVEL in place for --max-level.

    The helper must therefore look the ceiling up when it runs -- a
    module-import-time snapshot (or a default argument) would silently
    ignore the override.
    """
    original = LEAGUE_MAX_LEVEL['great']
    assert original == 50.0
    try:
        LEAGUE_MAX_LEVEL['great'] = 42.0
        assert _build('great')['maxLevel'] == 42.0
    finally:
        LEAGUE_MAX_LEVEL['great'] = original
    assert _build('great')['maxLevel'] == 50.0


def test_collection_data_key_order_is_stable():
    """The emitted key order is part of the rendered bytes -- pin it.

    `data_obj['collection']` is json.dumps'd straight into `var DATA = ...`,
    and replay-vs-original dive HTML is compared byte-for-byte, so
    reordering these keys is a rendered-output change even though it is
    semantically a no-op.
    """
    expected = [
        'speciesKey', 'isShadow', 'leagueLabel', 'leagueCap', 'maxLevel',
        'shadowAtkBonus', 'shadowDefMult', 'cpm', 'pokemonIndex',
        'preToFinals', 'rankLookup', 'thresholds', 'tierNames',
        'requireGender',
    ]
    assert list(_build('great')) == expected
    # rankLookupAlt is appended last, only for an active non-no-op
    # best-buddy toggle (the L51 twin's off-grid rank table).
    bb = {'active': True, 'alt_cap': 51.0, 'noop': False}
    assert list(_build('great', best_buddy=bb)) == expected + ['rankLookupAlt']


def test_collection_rank_lookup_uses_the_same_league_ceiling():
    """The baked rank table is ranked at the same cap the scanner reports.

    Both come from `LEAGUE_MAX_LEVEL.get(league, MAX_CPM_LEVEL)`; if they
    ever diverge, an owned mon's displayed rank is computed at a different
    level than its displayed stats.
    """
    from gopvpsim.user_collection import compute_rank_lookup

    cd = _build('great')
    expected = compute_rank_lookup(
        SPECIES, league='great', max_level=cd['maxLevel'], shadow=False)
    baked = cd['rankLookup'][SPECIES]['normal']
    assert baked, 'rank table is empty -- the comparison would be vacuous'
    assert baked == {f'{a},{d},{s}': r for (a, d, s), r in expected.items()}
