"""worlds_shortlist ranking semantics: COMBINED usage, not max.

The shortlist deliberately ranks by usage sum (the most-played MATCHUP)
where worlds_tier2.amber_worklist ranks by max-then-sum (the bake wanted
the most-played MON's pairs first). This pins the difference so neither
quietly adopts the other's key.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import worlds_render_data as wrd  # noqa: E402
import worlds_shortlist as ws  # noqa: E402


def _entry(sid, usage):
    return {'species_id': sid, 'name': sid.title(), 'badge': 'PLAYED',
            'usage_recent_pct': usage}


def _slice(fracs):
    f = np.asarray(fracs, dtype=float)
    n = 512
    return wrd.CellSlice(frac=f, wins=(f * n).astype(int), n=n,
                         margin_lo=np.zeros(9, int),
                         margin_hi=np.zeros(9, int))


def _cell(focal, opp, fracs):
    cell = wrd.Cell(focal_id=focal, opp_id=opp)
    cell.scenarios = [(i % 3, i // 3) for i in range(9)]
    cell.slices[('rank1', 'top512', True)] = _slice(fracs)
    return cell


def _pair_cells(a, b, amber_fracs):
    """Both directions; forward direction carries the amber scenario."""
    return {(a, b): _cell(a, b, amber_fracs),
            (b, a): _cell(b, a, [1.0] * 9)}


def test_ranking_is_combined_usage_not_max():
    entries = [_entry('a', 10.0), _entry('b', 10.0),
               _entry('c', 15.0), _entry('d', 2.0)]
    amber = [0.5] + [1.0] * 8
    cells = {}
    cells.update(_pair_cells('a', 'b', amber))   # combined 20
    cells.update(_pair_cells('c', 'd', amber))   # combined 17, max 15
    # green pair, must not appear at all
    cells.update(_pair_cells('a', 'c', [1.0] * 9))
    rows = ws.shortlist_rows(entries, cells)
    assert [r['pair'] for r in rows] == [('a', 'b'), ('c', 'd')]
    # max-usage ordering (worlds_tier2's key) would put ('c','d') first;
    # positive control that the two keys actually disagree on this data.
    assert max(10.0, 10.0) < max(15.0, 2.0)
    assert rows[0]['combined'] == 20.0
    assert rows[0]['amber_dirs'] == (True, False)
    assert rows[0]['amber_scen'] == (1, 0)
    assert rows[0]['closest_split'] == 0.5


def test_manifest_amber_pairs_excludes_clean_sample():
    manifest = {'entries': {
        'a|b|bait': {'clean_sample': False},
        'a|b|nobait': {'clean_sample': False},
        'b|a|bait': {'clean_sample': False},
        'c|d|bait': {'clean_sample': True},
        'c|d|nobait': {'clean_sample': True},
    }}
    assert ws.manifest_amber_pairs(manifest) == {('a', 'b')}


def test_missing_from_manifest_flags_row():
    entries = [_entry('a', 10.0), _entry('b', 10.0)]
    cells = _pair_cells('a', 'b', [0.5] + [1.0] * 8)
    rows = ws.shortlist_rows(entries, cells, manifest_pairs=set())
    assert len(rows) == 1 and rows[0]['in_tier2'] is False
    rows = ws.shortlist_rows(entries, cells, manifest_pairs={('a', 'b')})
    assert rows[0]['in_tier2'] is True
