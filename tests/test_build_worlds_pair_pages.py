"""build_worlds_pair_pages: reach-or-deny + curve + page contracts.

The reach strip is validated against the session-2 DragapultSim
reproduction (Tinkaton vs Mantine: guarantee 110.18 under the minimal
energy-legal 14-fast + 2-Gigaton plan) -- a real external oracle, not a
self-referential pin. Boundary confirmation is exercised both ways
(passes on real cutoffs; a corrupted cutoff raises).
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import build_worlds_pair_pages as bpp  # noqa: E402
import worlds_bake as wb  # noqa: E402

from gopvpsim.pokemon import iv_rank  # noqa: E402


@pytest.fixture(scope='module')
def tinkaton_mantine_reach():
    entries = {e['species_id']: e for e in wb.load_meta()}
    focal_ranked = iv_rank('Tinkaton', league='great', shadow=False)
    opp_cohort = iv_rank('Mantine', league='great', shadow=False)[:512]
    return bpp.reach_rows(entries['tinkaton'], entries['mantine'],
                          focal_ranked, opp_cohort), entries


def test_reach_reproduces_dragapultsim_guarantee(tinkaton_mantine_reach):
    reach, _ = tinkaton_mantine_reach
    rows = {(r['move'], r['n_charged']): r for r in reach['rows']}
    gh2 = rows[('Gigaton Hammer', 2)]
    # Session-2 oracle: guarantee 110.18 (DragapultSim's 110.21; residual
    # is cross-implementation stat rounding), minimal legal plan 14 fast.
    assert gh2['n_fast'] == 14
    assert gh2['guarantee'] == pytest.approx(110.18, abs=0.05)
    # Guarantee and per-spread (rank-1 anchor) are distinct quantities.
    assert gh2['per_spread'] < gh2['guarantee']
    # Coverage counts: the guarantee-reaching spreads are off-SP -- none
    # in top-512, some in the full 4096 (the breakpoint-chaser story).
    assert gh2['reach512'] == 0 and gh2['reach4096'] > 0
    # Bulldoze carries an opponent-def debuff -> stage flag on.
    assert reach['stage_flag'] is True
    # Unreachable-plan collapse (Michael 2026-08-11): the Bulldoze rows
    # (double-resisted; cutoff ~757 vs an attainable ceiling ~113.55)
    # and 1x Gigaton leave the table for the footnote; the live 2x
    # Gigaton row stays.
    html_text = bpp.reach_table_html(reach, 'Tinkaton', 'Mantine')
    assert 'NO attainable spread can complete' in html_text
    assert 'tops out at 113.55' in html_text
    assert 'Bulldoze + 5x Fairy Wind (needs 757.57)' in html_text
    assert html_text.count('<tr><td>') == 1          # only 2x Gigaton
    assert '2x Gigaton Hammer' in html_text


def test_boundary_confirmation_rejects_corrupt_cutoff(tinkaton_mantine_reach):
    """The render-time confirmation must actually discriminate: rerunning
    with a poisoned ko_cutoff raises instead of shipping the number."""
    import worlds_tier0 as t0
    _, entries = tinkaton_mantine_reach
    focal_ranked = iv_rank('Tinkaton', league='great', shadow=False)
    opp_cohort = iv_rank('Mantine', league='great', shadow=False)[:64]
    real = t0.ko_cutoff
    def poisoned(*a, **k):
        return real(*a, **k) + 0.5      # off-boundary by half a stat point
    t0.ko_cutoff = poisoned
    try:
        with pytest.raises(RuntimeError, match='boundary confirmation'):
            bpp.reach_rows(entries['tinkaton'], entries['mantine'],
                           focal_ranked, opp_cohort)
    finally:
        t0.ko_cutoff = real


def test_reach_excluded_for_aegislash(tinkaton_mantine_reach):
    _, entries = tinkaton_mantine_reach
    aegi = entries['aegislash_shield']
    focal_ranked = iv_rank('Tinkaton', league='great', shadow=False)
    opp_cohort = iv_rank(aegi['species'], league='great', shadow=False)[:8]
    assert bpp.reach_rows(entries['tinkaton'], aegi,
                          focal_ranked, opp_cohort) is None
    html_text = bpp.reach_table_html(None, 'Tinkaton', 'Aegislash (Shield)')
    assert 'footnoted OUT' in html_text


def test_curve_svg_shape_and_tooltips():
    # Constant blocks make the bin means exact: top half sweeps, bottom
    # half loses everything.
    frac = np.concatenate([np.ones(2048), np.zeros(2048)])
    svg = bpp.curve_svg(frac, '0-0', 'Mantine')
    assert svg.count('<title>') == 256      # 4096 / bin 16
    assert 'SP ranks 1-16' in svg and 'SP ranks 4081-4096' in svg
    assert 'var(--accent)' in svg           # theme token, no literal hex
    assert 'beats 100.0%' in svg and 'beats 0.0%' in svg


def test_pair_page_filename_sorted():
    assert (bpp.pair_page_filename('mantine', 'tinkaton')
            == bpp.pair_page_filename('tinkaton', 'mantine')
            == 'worlds-pair-mantine--tinkaton.html')


def test_worlds_fn_grid_decided():
    import worlds_fn
    won = np.ones((600, 5, 9), dtype=bool)
    grid = {'won': won, 'top512_mask': np.array([True] * 4 + [False])}
    assert worlds_fn.grid_decided(grid) == (False, 0.0, 0.0)  # constant
    won2 = won.copy()
    won2[3, 1, 4] = False                    # one losing cell in-block
    d, wc, wi = worlds_fn.grid_decided({'won': won2,
                                        'top512_mask': grid['top512_mask']})
    assert d is True and wc == pytest.approx(1 / (512 * 4))
    # spread impact: exactly one of the 512 focal rows is mixed
    assert wi == pytest.approx(1 / 512)
    # Winning-minority case: all rows lose to opp col 1 but beat the
    # rest -- cell minority is the LOSING side here (512/2048), while
    # every row is mixed (impact 100%). The two metrics must diverge.
    won4 = won.copy()
    won4[:512, 1, 4] = False
    d4, wc4, wi4 = worlds_fn.grid_decided(
        {'won': won4, 'top512_mask': grid['top512_mask']})
    assert d4 and wc4 == pytest.approx(512 / 2048) and wi4 == 1.0
    # A flip OUTSIDE the top512 block (masked col or focal rank > 512)
    # must not count.
    won3 = won.copy()
    won3[3, 4, 4] = False                    # masked-out cohort column
    won3[555, 1, 4] = False                  # focal rank beyond 512
    assert worlds_fn.grid_decided({'won': won3,
                                   'top512_mask': grid['top512_mask']}) \
        == (False, 0.0, 0.0)
    assert worlds_fn.grid_decided(None) == (False, 0.0, 0.0)


def test_deny_moot_annotation(tinkaton_mantine_reach):
    """A 512/512 deny count is trivially true whenever the focal rank-1
    misses the plan against every build; it must carry the moot marker
    (Michael 2026-08-14 -- pre-fix, Azumarill vs Jellicent rendered a
    bare 512/512 that read as per-build signal). A strictly-between
    count stays unannotated: that is the informative case."""
    reach, _ = tinkaton_mantine_reach
    live = next(r for r in reach['rows']
                if r['reach4096'] > 0 or r['reach_anchor4096'] > 0)
    fake = dict(reach, rows=[dict(live, deny512=512),
                             dict(live, deny512=137)])
    html_text = bpp.reach_table_html(fake, 'A', 'B')
    assert '(moot: rank-1 never reaches)' in html_text
    assert html_text.count('moot: rank-1 never reaches') == 1
    assert f'{reach["r1_atk"]:.2f}' in html_text     # hover tip cites atk
    assert '>137/512</td>' in html_text              # informative: bare


def test_rank_pack_roundtrip():
    """The 8-hex-per-rank pack must decode (at the JS substr offsets:
    0/1/2 IV nibbles, 3-4 level*2, 5-7 CP) back to iv_rank's spreads."""
    ranked = iv_rank('Azumarill', league='great', shadow=False)
    pack = bpp.rank_pack(ranked)
    assert len(pack) == 8 * len(ranked) == 8 * 4096
    for idx in (0, 1, 2500, 4095):
        s = pack[idx * 8:(idx + 1) * 8]
        r = ranked[idx]
        assert (int(s[0], 16), int(s[1], 16), int(s[2], 16)) == \
            (r['atk_iv'], r['def_iv'], r['sta_iv'])
        assert int(s[3:5], 16) / 2 == r['level']
        assert int(s[5:8], 16) == r['cp']


def test_curve_svg_pack_attrs():
    """pack_id wires the data-* attributes PAIR_JS inverts; the geometry
    attrs must equal the python layout constants (padl/pw/w), and the
    no-pack call shape stays attribute-free (old call sites)."""
    frac = np.linspace(0.0, 1.0, 4096)
    svg = bpp.curve_svg(frac, '0-0', 'Mantine', pack_id='azumarill')
    assert 'data-pack="azumarill"' in svg
    assert 'data-n="4096"' in svg and 'data-bin="16"' in svg
    assert 'data-w="680"' in svg and 'data-padl="34"' in svg \
        and 'data-pw="642"' in svg
    bins = svg.split('data-bins="')[1].split('"')[0].split(',')
    assert len(bins) == 256                          # 4096 / bin 16
    assert 'data-pack' not in bpp.curve_svg(frac, '0-0', 'Mantine')
