"""Proportional GTO fills + the sliver floor (guard ba557ad).

Pre-guard commit: e84d825. There, a mixed (IV-decided) cell rendered
FLAT amber in both surfaces -- the cheat-sheet strip emitted
``<span class="sc sc-amber" title=...>?</span>`` and the hub mini
sub-square emitted ``<i class="a"></i>``, with NO inline gradient
anywhere (observed pre-fix value: zero ``linear-gradient`` stops in
either helper's output, so a 93/7 cell and a 50/50 cell were
byte-identical).

ba557ad splits a mixed cell green/red at the win share and clamps each
side to a visible sliver: percentage stops in [5%, 95%] on the 20px
cheat-sheet box, pixel stops in [1px, 6px] on the 7px hub box. The
floor is the whole point -- a 99.9% cell must still read as mixed, not
as solid -- so the clamps are pinned here from both ends.

Synthetic ``CellSlice`` / matrix-row objects only; no baked npz.
"""
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import worlds_render_data as wrd  # noqa: E402
import build_worlds_pages as bwp  # noqa: E402

# Fractions probed, in increasing order. 0.0/1.0 are the settled ends
# (never gradient-filled); 0.001 and 0.999 are the floor/ceiling
# controls; 0.05/0.95 sit exactly on the sheet clamps; 0.5/0.93 are the
# proportional interior (0.93 is the commit message's "93/7 no longer
# looks like 50/50").
FRACS = [0.0, 0.001, 0.05, 0.07, 0.5, 0.93, 0.95, 0.999, 1.0]
AMBER_IDX = [i for i, f in enumerate(FRACS) if 0.0 < f < 1.0]

# Tolerant scanners: class attribute, then anything up to '>', so a new
# attribute (title, outline class, ...) between them cannot blind them.
SC_SPAN = re.compile(r'<span class="sc (?P<cls>[^"]*)"(?P<rest>[^>]*)>'
                     r'(?P<letter>[^<]*)</span>')
MINI_BOX = re.compile(r'<i class="(?P<cls>[^"]*)"(?P<rest>[^>]*)>')
# Colour is CAPTURED (not just matched) so the tests can pin that the
# green stop comes first -- a win/loss swap renders 93% RED for a 93%
# win share and must fail here (skeptic mutation M4/M9).
PCT_STOP = re.compile(r'var\(--(win|loss)\)\s*([0-9]+(?:\.[0-9]+)?)%')
PX_STOP = re.compile(r'var\(--(win|loss)\)\s*([0-9]+)px')


def _slice(fracs):
    """Smallest CellSlice the renderers accept."""
    frac = np.asarray(fracs, dtype=float)
    n = 1000
    return wrd.CellSlice(
        frac=frac,
        wins=np.round(frac * n).astype(int),
        n=n,
        margin_lo=np.full(len(frac), -40, dtype=int),
        margin_hi=np.full(len(frac), 60, dtype=int),
    )


def _row(fracs):
    """Smallest matrix_summary-shaped row the hub cell accepts."""
    sl = _slice(fracs)
    return {'missing': False, 'frac': [float(f) for f in sl.frac],
            'status': sl.status, 'amber': True, 'amber_scenarios': [],
            'n': sl.n}


def _sheet_stops(html):
    """{scenario index: (class, [colours], [percent stops])}."""
    out = {}
    for i, m in enumerate(SC_SPAN.finditer(html)):
        pairs = PCT_STOP.findall(m.group('rest'))
        out[i] = (m.group('cls'), [c for c, _ in pairs],
                  [float(x) for _, x in pairs])
    return out


def _hub_stops(html):
    """{sub-square index: (class, [colours], [pixel stops])}."""
    out = {}
    for i, m in enumerate(MINI_BOX.finditer(html)):
        pairs = PX_STOP.findall(m.group('rest'))
        out[i] = (m.group('cls'), [c for c, _ in pairs],
                  [int(x) for _, x in pairs])
    return out


def test_scanners_see_the_whole_grid():
    """Scanner self-test: nine cells per surface, seven of them mixed
    (a silently-empty scan is the default failure mode here)."""
    sheet = _sheet_stops(_grid_html())
    hub = _hub_stops(bwp._mini_cell(_row(FRACS), 'Alpha', 'Beta'))
    assert len(sheet) == 9, sheet
    assert len(hub) == 9, hub
    assert [i for i, (c, *_) in sheet.items() if 'sc-amber' in c] == AMBER_IDX
    assert [i for i, (c, *_) in hub.items() if c.split()[0] == 'a'] == AMBER_IDX
    assert len(AMBER_IDX) == 7


def _grid_html():
    return bwp._grid9(_slice(FRACS), 'Beta', 'bait')


def test_sheet_gradient_stops_stay_inside_the_5_95_band():
    """Every amber cheat-sheet stop is a real gradient inside [5%, 95%]
    (pre-guard: no stops at all)."""
    stops = _sheet_stops(_grid_html())
    seen = 0
    for i, (cls, colors, pcts) in stops.items():
        if 'sc-amber' not in cls:
            assert not pcts, (i, cls, pcts)   # settled cells stay flat
            continue
        assert colors == ['win', 'loss'], (i, colors)  # green first
        assert len(pcts) == 2, (i, pcts)      # green stop == red stop
        assert pcts[0] == pcts[1], (i, pcts)
        assert 5.0 <= pcts[0] <= 95.0, (i, pcts)
        seen += 1
    assert seen == len(AMBER_IDX)


def test_sheet_fill_is_proportional_between_the_clamps():
    """Interior fractions render at their own win share, so 93/7 does
    not look like 50/50 (the point of ba557ad)."""
    stops = _sheet_stops(_grid_html())
    for i in AMBER_IDX:
        f = FRACS[i]
        if 0.05 < f < 0.95:
            assert stops[i][2][0] == round(100 * f, 1), (i, f, stops[i])
    # and the interior really does separate the two headline cases
    assert stops[FRACS.index(0.93)][2][0] != stops[FRACS.index(0.5)][2][0]


def test_sheet_floor_and_ceiling_never_pass_as_solid():
    """Positive control for the absence pin: 0.999 must not fill the
    box (no 100% stop) and 0.001 must still show a sliver -- with the
    canonical clamped stops asserted present, so this test fails if the
    gradient channel disappears rather than silently passing."""
    stops = _sheet_stops(_grid_html())
    hi_cls, hi_colors, hi = stops[FRACS.index(0.999)]
    lo_cls, lo_colors, lo = stops[FRACS.index(0.001)]
    # still classified IV-decided, letter still carried (never colour-alone)
    assert 'sc-amber' in hi_cls and 'sc-amber' in lo_cls
    assert hi_colors == lo_colors == ['win', 'loss']
    assert hi == [95.0, 95.0], stops[FRACS.index(0.999)]
    assert lo == [5.0, 5.0], stops[FRACS.index(0.001)]
    html = _grid_html()
    assert 'var(--win) 100.0%' not in html
    assert 'var(--win) 0.0%' not in html


def test_hub_pixel_stops_stay_inside_the_1_6_band():
    """Every amber hub sub-square is a gradient with a 1..6 px stop on
    the 7px box (pre-guard: plain <i class="a"></i>, no stops)."""
    stops = _hub_stops(bwp._mini_cell(_row(FRACS), 'Alpha', 'Beta'))
    seen = 0
    for i, (cls, colors, pxs) in stops.items():
        if cls.split()[0] != 'a':
            assert not pxs, (i, cls, pxs)
            continue
        assert colors == ['win', 'loss'], (i, colors)  # green first
        assert len(pxs) == 2 and pxs[0] == pxs[1], (i, pxs)
        assert 1 <= pxs[0] <= 6, (i, pxs)
        seen += 1
    assert seen == len(AMBER_IDX)


def test_hub_fill_is_monotone_in_the_win_share():
    """More cohort spreads beaten never renders as a narrower green."""
    stops = _hub_stops(bwp._mini_cell(_row(FRACS), 'Alpha', 'Beta'))
    widths = [stops[i][2][0] for i in AMBER_IDX]
    assert widths == sorted(widths), widths
    assert widths[0] < widths[-1], widths     # non-degenerate


def test_hub_floor_and_ceiling_never_pass_as_solid():
    """Positive control, hub side: 0.999 clamps to 6px (never the full
    7px box) and 0.001 keeps 1px."""
    html = bwp._mini_cell(_row(FRACS), 'Alpha', 'Beta')
    stops = _hub_stops(html)
    hi_cls, hi_colors, hi = stops[FRACS.index(0.999)]
    lo_cls, lo_colors, lo = stops[FRACS.index(0.001)]
    assert hi_cls.split()[0] == 'a' and lo_cls.split()[0] == 'a'
    assert hi_colors == lo_colors == ['win', 'loss']
    assert hi == [6, 6], stops[FRACS.index(0.999)]
    assert lo == [1, 1], stops[FRACS.index(0.001)]
    assert 'var(--win) 7px' not in html
    assert 'var(--win) 0px' not in html


def test_class_fallbacks_survive_the_inline_fill():
    """The no-inline-style fallbacks (sc-amber / class "a") and the
    W/L/? letters are the scanner anchors ba557ad promised to keep."""
    sheet = _grid_html()
    hub = bwp._mini_cell(_row(FRACS), 'Alpha', 'Beta')
    assert sheet.count('class="sc sc-amber') >= len(AMBER_IDX)
    assert re.findall(r'<i class="a[ "]', hub)
    letters = [m.group('letter') for m in SC_SPAN.finditer(sheet)]
    assert letters == ['L'] + ['?'] * 7 + ['W'], letters


def test_legend_documents_the_denominator_and_the_floor():
    """The legend must explain the fill it now ships (tolerant match)
    and keep the sc-amber anchor as its positive control."""
    legend = bwp.LEGEND
    assert 'sc-amber' in legend
    assert re.search(r'linear-gradient\([^)]*var\(--win\)', legend)
    assert re.search(r'green width is the share', legend)
    assert re.search(r'sliver', legend)
    assert re.search(r'uniform over the tested cohort', legend)
