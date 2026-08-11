"""CMP board: tie semantics, footnote, and threshold consistency.

The board's thresholds must agree with the engine's cmp_atk expression
(walked division for shadows) and never render an exact tie as a win.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import build_worlds_cmp as bwc  # noqa: E402

from gopvpsim.pokemon import SHADOW_ATK_BONUS  # noqa: E402


def test_cmp_of_matches_engine_expression():
    # Non-shadow: identity. Shadow: walked division, NOT algebraic
    # inversion -- for a value where fl(fl(x*1.2)/1.2) != x the two
    # differ, so pin the walked form.
    assert bwc.cmp_of(100.0, False) == 100.0
    raw = 107.3
    boosted = raw * SHADOW_ATK_BONUS
    assert bwc.cmp_of(boosted, True) == boosted / SHADOW_ATK_BONUS


@pytest.mark.slow
def test_board_page_contracts(tmp_path):
    import worlds_render_data as wrd
    import worlds_planes as wp
    meta = wrd.load_meta()
    manifest = wp.load_manifest()
    # manifest.json is TRACKED (the provenance record) -- a missing one
    # is a broken checkout, not a skip condition (testing policy:
    # tracked-file skips are hard asserts).
    assert manifest is not None, 'worlds/planes/manifest.json missing'
    html_text = bwc.render_cmp_board(meta, manifest)
    assert 'Shadow-tie footnote' in html_text
    assert 'no priority' in html_text        # tie = third state, never a win
    assert 'coin flip' in html_text
    # Conservative display + cohort honesty (verify catches 2026-08-11):
    assert 'rounded UP' in html_text
    assert 'best-SP-per-attack-IV band' in html_text
    assert 'settled regardless of IVs' not in html_text
    assert '../' not in html_text
    assert '—' not in html_text and '–' not in html_text
    # Non-trivial contested table: floors, not exact counts (testing
    # policy) -- the meta guarantees dozens of overlapping ranges.
    assert html_text.count('class="wtl"') >= 40
    data = bwc.entry_cmp_data(meta['entries'])
    pairs = bwc.contested_pairs(data)
    assert len(pairs) >= 20
    # Cohort regression (the hundo blind spot): sableye_shadow vs
    # wigglytuff was 'settled' under top-512-only ranges although a
    # hundo Wigglytuff (attack band) wins CMP -- the union cohort must
    # keep it contested.
    names = {(r['a']['entry']['species_id'], r['b']['entry']['species_id'])
             for r in pairs}
    assert (('sableye_shadow', 'wigglytuff') in names
            or ('wigglytuff', 'sableye_shadow') in names)
    # Threshold consistency: for each contested direction, a spread
    # counted W must sit at-or-above the win threshold and a spread
    # counted T must equal the anchor exactly (spot-check 5 pairs).
    for r in pairs[:5]:
        thr = r['ab']['thr']
        anchor = r['b']['rank1']
        vals = r['a']['vals']
        assert r['ab']['w'] == sum(1 for v in vals if v > anchor)
        assert r['ab']['t'] == sum(1 for v in vals if v == anchor)
        if thr['win_above'] is not None:
            # win_above is EFFECTIVE atk; compare in cmp space via the
            # same walked conversion the engine uses.
            thr_cmp = bwc.cmp_of(thr['win_above'],
                                 r['a']['entry']['shadow'])
            for v in vals:
                if v > anchor:
                    assert v >= thr_cmp
