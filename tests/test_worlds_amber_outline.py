"""Amber OUTLINE channel + flag origins (guard 6a7e534).

A cell can be settled in the displayed rank1/top512 slice and still be
IV-decided in a corner of the tested space (high-attack cohort,
max-attack probe, both at once, a probe-spread flip, or full-grid
Tier-2 evidence). 6a7e534 gave that its own channel:

* ``Cell.amber_origins()`` names WHICH corner flags each scenario.
* cheat-sheet "IVs decide" flags carry the nearest-corner annotation
  ("1-1 (max-atk probe)") whenever the scenario is not mixed in the
  displayed slice.
* the solid-but-flagged cells get a flip-colored inset ring: class
  ``sc-u`` on sheet grid cells, ``u`` on hub minis. A SEPARATE channel
  from the GTO fill (ba557ad) -- never a widened sliver, so the fill
  keeps meaning "share of THIS cohort beaten by THIS spread".

Pre-guard (ba557ad, which already carries the GTO fill) observed
values, i.e. what these tests pin against:

* ``Cell.amber_origins`` and ``build_worlds_pages._flag_label`` did not
  exist at all (AttributeError).
* the fixture's flag line read ``IVs decide: 0-2, 1-0, 1-1, 2-0, 2-2``
  -- no annotations, so a flag that disagreed with the strip could not
  explain itself.
* no ``sc-u`` grid cell and no ``<i class="g u">`` mini box was emitted
  anywhere (0 outlined cells).

Synthetic planes/meta throughout (portable; no real plane blobs), same
fixture style as test_build_worlds_pages.py.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import worlds_planes as wp  # noqa: E402
import worlds_render_data as wrd  # noqa: E402
import build_worlds_pages as bwp  # noqa: E402

SCEN = [(a, b) for a in range(3) for b in range(3)]

# Fixture meta: two entries, one ordered direction rendered per sheet.
META = {
    'format': 'open GL 1500 + Play! banned list',
    'mechanics': 'legacy (old system; Worlds-confirmed)',
    'usage_recent_cutoff': '2026-03',
    'usage_events_recent': 16,
    'usage_teams_recent': 1801,
    'badge_usage_top': 25,
    'badge_rank_top': 30,
    'moveset_modal_min_pct': 60.0,
    'reject_top_n': 55,
    'entries': [
        {'name': 'Alpha', 'species': 'Alpha', 'species_id': 'alpha',
         'shadow': False, 'badge': 'PLAYED', 'badge_rule': 'PLAYED',
         'current_rank': 2, 'usage_recent_pct': 30.0,
         'fast_move': 'Fast A', 'charged_moves': ['CM One', 'CM Two'],
         'fast_move_id': 'FAST_A', 'charged_move_ids': ['CM_ONE', 'CM_TWO'],
         'moveset_source': 'modal', 'moveset_modal_pct': 90.0,
         'moveset_n': 100, 'default_disagrees': False},
        {'name': 'Beta (Shadow)', 'species': 'Beta',
         'species_id': 'beta_shadow', 'shadow': True, 'badge': 'PLAYED',
         'badge_rule': 'PLAYED', 'current_rank': 9,
         'usage_recent_pct': 12.0, 'fast_move': 'Fast B',
         'charged_moves': ['CM Three'], 'fast_move_id': 'FAST_B',
         'charged_move_ids': ['CM_THREE'], 'moveset_source': 'modal',
         'moveset_modal_pct': 88.0, 'moveset_n': 50,
         'default_disagrees': False},
    ],
    'rejects': [],
}

MANIFEST = {'engine': 'eng123', 'gamemaster': 'gm456',
            'worlds_code': 'wc789',
            'entries': {'k': {'baked': '2026-08-10'}}}

# Opponent cohort rows 0,1,2 are the top-512 cohort; rows 3,4 are the
# high-attack (atkband) cohort. Disjoint on purpose so each corner of
# the tested space can be flipped independently.
TOP512 = [True, True, True, False, False]
ATKBAND = [False, False, False, True, True]

# Expected per-scenario story of the fixture (headline = rank1 probe
# spread vs the top-512 cohort):
#   0-0 green, settled everywhere                      -> no flag
#   0-1 red, settled everywhere                        -> no flag
#   0-2 MIXED in the headline slice                    -> flag, NO ring
#   1-0 red in the headline, mixed vs the atkband cohort   -> ring
#   1-1 green in the headline, mixed vs the atkband cohort -> ring
#   1-2 settled (differs by bait mode on the alpha sheet)  -> no flag
#   2-0 green in the headline, mixed under the maxatk probe -> ring
#   2-1 green, settled everywhere                      -> no flag
#   2-2 green in the headline, mixed only under maxatk+atkband -> ring
HEADLINE_MIXED = 2
OUTLINED = {3, 4, 6, 8}
EXPECTED_ORIGINS = {2: ['headline'], 3: ['atkband'], 4: ['atkband'],
                    6: ['maxatk'], 8: ['maxatk+atkband']}


def _won():
    """(2 probe spreads, 5 cohort rows, 9 scenarios) bool wins."""
    w = np.zeros((2, 5, 9), dtype=bool)
    w[:, :, 0] = True                       # 0-0 green everywhere
    # 0-2: headline mix (row 2 of the top-512 cohort loses); every OTHER
    # slice is clean, so its only origin is 'headline'
    w[:, (0, 1), 2] = True
    w[:, (3, 4), 2] = True
    w[1, 2, 2] = True
    # 1-0: headline all-loss; the rank1 probe splits the atkband cohort
    w[0, 3, 3] = True
    # 1-1: headline all-win; the rank1 probe splits the atkband cohort
    w[:, (0, 1, 2), 4] = True
    w[0, 3, 4] = True
    w[1, (3, 4), 4] = True
    # 2-0: headline all-win; the maxatk probe drops top-512 row 2
    w[:, :, 6] = True
    w[1, 2, 6] = False
    # 2-1: green everywhere
    w[:, :, 7] = True
    # 2-2: only maxatk-probe-vs-atkband is mixed
    w[:, :, 8] = True
    w[1, 4, 8] = False
    return w


@pytest.fixture
def cells(tmp_path):
    planes = tmp_path / 'planes'
    won = _won()
    # alpha->beta differs by bait mode (1-2 is a clean win with no
    # bait), so that sheet shows TWO grids -- the union_flags keyword
    # path. beta->alpha is bait-independent -> the collapsed single
    # grid, the positional path. Both must carry the ring.
    won_nb = won.copy()
    won_nb[:, :, 5] = True
    for f, o in (('alpha', 'beta_shadow'), ('beta_shadow', 'alpha')):
        for bait in (True, False):
            w = won_nb if (f == 'alpha' and not bait) else won
            score = np.where(w, 700, 300).astype(np.uint16)
            arrs = wp.plane_arrays(
                w, score, focal_ivs=[(0, 15, 15), (15, 15, 15)],
                focal_levels=[24.0, 25.5],
                opp_ivs=[(0, 15, 14), (1, 15, 11), (4, 1, 12),
                         (15, 15, 15), (15, 14, 15)],
                opp_levels=[24.0, 24.0, 25.0, 22.5, 22.5], scenarios=SCEN,
                top512_mask=TOP512, atkband_mask=ATKBAND)
            wp.write_plane(wp.plane_filename(f, o, bait), arrs, planes)
    return wrd.build_all_cells(META['entries'], planes)


def _grid_cells(html_text):
    """{(bait label, scenario label): (class attr, letter)} for every
    3x3 grid cell in a rendered sheet. Keyed off the tooltip so the
    parse never depends on span order."""
    out = {}
    for cls, tip, letter in re.findall(
            r'<span class="(sc [^"]*)"[^>]*title="([^"]*)"[^>]*>'
            r'([WL?])</span>', html_text):
        mode, _, rest = tip.partition(' ')
        label = rest.split(' ', 1)[0]
        out[(mode, label)] = (cls, letter)
    return out


def test_fixture_is_the_intended_shape(cells):
    """Positive control for everything below: the fixture really does
    carry solid-in-the-headline-but-corner-flagged scenarios AND a
    headline-mixed one. Without this the outline assertions could pass
    vacuously."""
    cell = cells[('alpha', 'beta_shadow')]
    assert cell.amber_scenarios() == sorted(OUTLINED | {HEADLINE_MIXED})
    status = cell.headline.status
    assert status[HEADLINE_MIXED] == 'amber'
    assert all(status[i] != 'amber' for i in OUTLINED)
    assert {'green', 'red'} <= {status[i] for i in OUTLINED}


def test_amber_origins_names_the_corner(cells):
    """Cell.amber_origins tags each flagged scenario with WHICH corner
    of the tested IV space flips it. Pre-guard: no such method."""
    cell = cells[('alpha', 'beta_shadow')]
    assert cell.amber_origins() == EXPECTED_ORIGINS


def test_amber_origins_keys_match_amber_scenarios():
    """Every flagged scenario gets an origin and nothing else does --
    pinned on a synthetic Cell that exercises all six documented tags
    (headline / atkband / maxatk / maxatk+atkband / spread-flip /
    grid), including the two that come from outside ``slices``."""
    def sl(mixed):
        frac = np.ones(9)
        for i, f in mixed.items():
            frac[i] = f
        return wrd.CellSlice(frac=frac, wins=(frac * 8).astype(np.int64),
                             n=8, margin_lo=np.full(9, -100, dtype=np.int32),
                             margin_hi=np.full(9, 100, dtype=np.int32))

    cell = wrd.Cell(
        focal_id='a', opp_id='b',
        slices={('rank1', 'top512', True): sl({0: 0.5}),
                ('rank1', 'atkband', True): sl({1: 0.5}),
                ('maxatk512', 'top512', True): sl({2: 0.5, 5: 0.0}),
                ('maxatk512', 'atkband', True): sl({3: 0.5})},
        grid_scenarios=[7])
    assert cell.spread_flip_scenarios() == [5]           # non-trivial
    origins = cell.amber_origins()
    assert sorted(origins) == cell.amber_scenarios() == [0, 1, 2, 3, 5, 7]
    assert origins == {0: ['headline'], 1: ['atkband'], 2: ['maxatk'],
                       3: ['maxatk+atkband'], 5: ['spread-flip'],
                       7: ['grid']}
    # Every tag the data layer can emit has a renderer label (except
    # 'headline', which renders bare by design).
    tags = {t for v in origins.values() for t in v}
    assert tags - {'headline'} <= set(bwp._ORIGIN_LABEL)
    assert set(bwp._ORIGIN_NEAREST) == set(bwp._ORIGIN_LABEL)


def test_flag_label_annotates_only_non_headline_scenarios():
    """_flag_label: bare label when the strip already shows the mix,
    nearest-corner annotation otherwise. Pre-guard: no _flag_label."""
    assert bwp._flag_label(4, {4: ['headline']}) == '1-1'
    # 'headline' wins even when a corner also flags it -- the strip
    # already shows the mix, so the annotation would be noise.
    assert bwp._flag_label(4, {4: ['atkband', 'headline']}) == '1-1'
    assert bwp._flag_label(4, {4: ['atkband']}) == '1-1 (high-atk opp)'
    assert bwp._flag_label(4, {4: ['maxatk']}) == '1-1 (max-atk probe)'
    assert (bwp._flag_label(8, {8: ['maxatk+atkband']})
            == '2-2 (max-atk probe vs high-atk opp)')
    assert (bwp._flag_label(0, {0: ['spread-flip']})
            == '0-0 (probe-spread flip)')
    assert bwp._flag_label(6, {6: ['grid']}) == '2-0 (full grid only)'
    # Nearest-first: fewest deviations from the headline slice wins.
    assert (bwp._flag_label(3, {3: ['grid', 'maxatk', 'atkband']})
            == '1-0 (high-atk opp)')
    assert bwp._flag_label(1, {}) == '0-1'               # no origin -> bare


def test_cheat_sheet_flags_carry_origin_annotations(cells):
    """Pre-guard the line read 'IVs decide: 0-2, 1-0, 1-1, 2-0, 2-2'."""
    html_text = bwp.render_cheat_sheet(META['entries'][0], META, cells,
                                       MANIFEST, slug_map={})
    assert ('IVs decide: 0-2, 1-0 (high-atk opp), 1-1 (high-atk opp), '
            '2-0 (max-atk probe), 2-2 (max-atk probe vs high-atk opp)'
            in html_text)
    assert '\u2014' not in html_text and '\u2013' not in html_text


def test_cheat_sheet_rings_solid_but_flagged_cells(cells):
    """Both bait grids on the two-grid sheet: the solid-but-flagged
    scenarios carry sc-u, the headline-mixed one never does (negative
    control), and the settled-everywhere ones never do."""
    html_text = bwp.render_cheat_sheet(META['entries'][0], META, cells,
                                       MANIFEST, slug_map={})
    grid = _grid_cells(html_text)
    modes = {m for m, _ in grid}
    assert modes == {'bait', 'no-bait'}, modes      # keyword-arg path
    for mode in modes:
        outlined = {bwp.SCEN_LABELS.index(lab)
                    for (m, lab), (cls, _l) in grid.items()
                    if m == mode and 'sc-u' in cls.split()}
        assert outlined == OUTLINED, (mode, sorted(outlined))
        # Negative control: a headline-mixed cell is amber, and amber
        # is NEVER outlined (the ring is a separate channel from the
        # fill -- outlining a mixed cell would double-encode it).
        cls, letter = grid[(mode, bwp.SCEN_LABELS[HEADLINE_MIXED])]
        assert 'sc-amber' in cls.split() and letter == '?'
        assert 'sc-u' not in cls
    assert not re.search(r'class="sc sc-amber[^"]*sc-u', html_text)
    # The ringed cells say why in their tooltip, and the letters still
    # carry the outcome (never color-alone).
    assert ('settled in this slice, IV-contested in another '
            '(the IVs-decide flags name the corner)' in html_text)
    assert {grid[('bait', bwp.SCEN_LABELS[i])][1] for i in OUTLINED} \
        == {'W', 'L'}


def test_bait_independent_sheet_also_rings(cells):
    """The collapsed single-grid path passes union_flags positionally;
    it must ring the same set."""
    html_text = bwp.render_cheat_sheet(META['entries'][1], META, cells,
                                       MANIFEST, slug_map={})
    grid = _grid_cells(html_text)
    assert {m for m, _ in grid} == {'bait-independent'}
    outlined = {bwp.SCEN_LABELS.index(lab)
                for (_m, lab), (cls, _l) in grid.items()
                if 'sc-u' in cls.split()}
    assert outlined == OUTLINED, sorted(outlined)
    assert 'sc-u' not in grid[('bait-independent',
                               bwp.SCEN_LABELS[HEADLINE_MIXED])][0]


def test_hub_mini_boxes_carry_the_outline_class(cells):
    """Hub minis: solid-but-union-flagged sub-squares get class 'u',
    amber (proportionally filled) ones never do, and the cell tooltip
    names the outlined scenarios. Pre-guard: zero 'u' boxes."""
    summary = wrd.matrix_summary(cells, META['entries'])
    row = summary[('alpha', 'beta_shadow')]
    td = bwp._mini_cell(row, 'Alpha', 'Beta (Shadow)')
    boxes = re.findall(r'<i class="([^"]*)"[^>]*>', td)
    assert len(boxes) == 9, boxes
    outlined = {i for i, c in enumerate(boxes) if 'u' in c.split()}
    # Derived from the same data the renderer used: union flags minus
    # the scenarios the headline slice already shows as mixed.
    expected = set(row['amber_scenarios']) - {
        i for i, s in enumerate(row['status']) if s == 'amber'}
    assert outlined == expected == OUTLINED
    assert 'u' not in boxes[HEADLINE_MIXED].split()
    assert '<i class="g u"></i>' in td and '<i class="r u"></i>' in td
    # The proportional fill is untouched by the ring channel (ba557ad
    # still owns the mixed box).
    assert '<i class="a" style="background:linear-gradient(90deg,' in td
    assert ('outlined 1-0, 1-1, 2-0, 2-2 = settled here, IV-contested in '
            'a corner slice (the cheat sheet names it)' in td)


def test_hub_renders_and_documents_the_channel(cells):
    """End to end: the outline reaches the hub page, and the shared
    legend explains the channel (a color-only affordance nobody can
    read is not shipped)."""
    hub = bwp.render_hub(META, cells, MANIFEST, slug_map={})
    assert '<i class="g u"></i>' in hub and '<i class="r u"></i>' in hub
    assert hub.count('<i class="g u"></i>') >= 2        # floor, both cells
    assert 'sc-green sc-u' in bwp.LEGEND                # legend swatch
    assert 'IV-contested in a corner of the tested space' in hub
    assert '.mini i.u {' in bwp.WORLDS_CSS
    assert '.g9 .sc.sc-u {' in bwp.WORLDS_CSS
    assert '\u2014' not in hub and '\u2013' not in hub
