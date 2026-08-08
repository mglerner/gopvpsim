"""The Plotly canvases read theme.py tokens, in every theme.

Plotly draws into its own SVG/WebGL canvas and cannot resolve CSS custom
properties, so the three dive canvases (main scatter, rating histogram,
matchup-cluster panels) used to carry a hardcoded dark-navy palette
(``#1a1a2e`` paper / ``#16213e`` plot / ``#e0e0e0`` font) belonging to no
theme -- three permanently dark charts on a light-default site, and a
``docs/palette_governance.md`` section-1 violation (palette hex outside
``_TOKENS``).

``scripts/deep_dive_engine.js`` now resolves those colors from the ACTIVE
``[data-theme]`` block with ``getComputedStyle`` (the shim governance section
8 specifies), falling back to the DEFAULT_THEME resolution that
``deep_dive._THEME_FALLBACK_HEX`` injects.  These tests pin the three ways
that arrangement can silently rot:

1. a hardcoded chrome hex creeping back into a layout,
2. the Python fallback map and the JS ``themeColor()`` call sites drifting
   apart (a token asked for but never injected resolves to '' -> Plotly
   falls back to ITS default, i.e. a white canvas),
3. a token being re-valued in theme.py until its marks stop separating from
   the plot fill they are drawn on.

Test 3 is the "bake the cheap lens into a guard" case: the mark-contrast
floor is mechanical, so it lives in the suite instead of in a review note.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from gopvpsim import theme
from tests.conftest import load_deep_dive

deep_dive = load_deep_dive()

JS_SRC = Path(__file__).resolve().parents[1] / 'scripts' / 'deep_dive_engine.js'
JS = JS_SRC.read_text()

# WCAG floor for a non-text MARK against the surface it is drawn on
# (references/color-formula.md check 5). Text tokens are held to 4.5 by
# palette_governance section 3; markers only need 3.
MARK_CONTRAST_MIN = 3.0


# --------------------------------------------------------------------------
# 1. No chrome hex left in the layouts
# --------------------------------------------------------------------------

def _code_lines():
    """JS source with whole-line ``//`` comments dropped.

    The comments deliberately quote the retired hexes (that is how the next
    reader knows what was replaced), so a scan for dead palette values has to
    look at code only.
    """
    return [ln for ln in JS.splitlines() if not ln.lstrip().startswith('//')]


def test_no_layout_carries_a_hardcoded_background_or_font():
    """paper/plot/grid/legend/hover chrome is shim-sourced, not literal.

    ``bordercolor`` on a per-trace ``hoverlabel`` is exempt: those carry the
    trace's own identity hue on purpose (tier color, anchor hue, ...), which
    is a palette question, not a chrome one.
    """
    offenders = [
        line.strip()
        for line in _code_lines()
        if re.search(r'(paper_bgcolor|plot_bgcolor|gridcolor|zerolinecolor|'
                     r'bgcolor|bordercolor)\s*:\s*[\'"]#', line)
        and 'hoverlabel' not in line
    ]
    assert offenders == [], offenders


def test_the_three_canvases_all_source_chrome_from_plotchrome():
    """Every Plotly layout in the file gets its backgrounds from the shim.

    Counted rather than located: a fourth canvas added later must opt in
    too, or this fails.
    """
    n_layouts = len(re.findall(r'paper_bgcolor', JS))
    n_shimmed = len(re.findall(r'paper_bgcolor:\s*\w+\.paper', JS))
    assert n_layouts == 3, f"expected 3 Plotly layouts, found {n_layouts}"
    assert n_shimmed == n_layouts


def test_the_dark_navy_palette_is_gone():
    """The pre-shim literals must not reappear in engine CODE."""
    code = '\n'.join(_code_lines())
    for dead in ('#1a1a2e', '#16213e', '#0f3460', '#2a2a4a', '#e0e0e0',
                 '#8899aa', '#cccccc', '#ffffff'):
        assert dead not in code, (
            f"{dead} is retired chrome/neutral hex; use themeColor()")


# --------------------------------------------------------------------------
# 2. Python fallback map <-> JS call sites
# --------------------------------------------------------------------------

def _js_requested_tokens():
    """Tokens the JS asks themeColor() for, as a set."""
    return set(re.findall(r"themeColor\(\s*'(--[A-Za-z0-9-]+)'\s*\)", JS))


def test_every_token_the_js_requests_is_injected_as_a_fallback():
    missing = _js_requested_tokens() - set(deep_dive._PLOT_THEME_TOKENS)
    assert missing == set(), (
        f"themeColor() asks for {sorted(missing)} but deep_dive."
        f"_PLOT_THEME_TOKENS does not inject it; getComputedStyle failure "
        f"would leave those marks with no color at all")


def test_no_fallback_token_is_injected_without_a_consumer():
    unused = set(deep_dive._PLOT_THEME_TOKENS) - _js_requested_tokens()
    assert unused == set(), f"dead fallback entries: {sorted(unused)}"


def test_fallback_values_are_the_default_theme_column_of_theme_py():
    idx = theme._THEME_ORDER.index(theme.DEFAULT_THEME)
    for tok, val in deep_dive._THEME_FALLBACK_HEX.items():
        assert val == theme._TOKENS[tok][idx], tok


def test_fallback_map_is_json_injectable_and_placeholder_is_wired():
    assert '__THEME_FALLBACK_JS__' in JS
    # json.dumps must survive: the substitution is a raw text replace, so a
    # value that isn't valid JS-literal JSON would produce a syntax error in
    # every shipped dive.
    json.loads(json.dumps(deep_dive._THEME_FALLBACK_HEX, sort_keys=True))


def test_theme_change_drops_the_memo_and_re_renders():
    """A theme switch must repaint the canvases, not just the CSS."""
    assert "attributeFilter: ['data-theme']" in JS
    obs = JS[JS.index('new MutationObserver'):]
    obs = obs[:obs.index('.observe(')]
    assert '_themeVarCache = {}' in obs
    assert 'updateView()' in obs
    assert 'mcRefreshAll()' in obs


# --------------------------------------------------------------------------
# 3. The marks still separate from the plot fill they are drawn on
# --------------------------------------------------------------------------

def _contrast(hex_a: str, hex_b: str) -> float:
    def lum(h: str) -> float:
        chan = [int(h.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        chan = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                for c in chan]
        return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]
    la, lb = lum(hex_a), lum(hex_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def test_every_shim_mark_clears_the_contrast_floor_in_every_theme():
    """--surface-2 is the plot fill; every mark painted on it must clear 3:1.

    This is why --surface-2 (not --bg, not --surface) is the plot fill: the
    tier tokens were already AA-solved against --surface-2 for the badges, so
    reusing it as the canvas fill lands every tier marker at its solved
    contrast for free.  Re-valuing --surface-2 without re-checking the marks
    is the regression this catches.
    """
    marks = list(deep_dive._PLOT_THEME_TOKENS)
    marks += [f'--tier-{i}' for i in range(1, 9)] + ['--tier-mirror']
    marks.remove('--surface')    # legend panel fill, not a mark
    marks.remove('--surface-2')  # the fill itself
    marks.remove('--border-2')   # recessive grid, deliberately sub-3:1

    failures = []
    for col, name in enumerate(theme._THEME_ORDER):
        fill = theme._TOKENS['--surface-2'][col]
        for tok in marks:
            ratio = _contrast(theme._TOKENS[tok][col], fill)
            if ratio < MARK_CONTRAST_MIN:
                failures.append((name, tok, round(ratio, 2)))
    assert failures == [], failures


def test_the_grid_token_stays_recessive_but_visible():
    """--border-2 draws the grid: readable enough to follow, never dominant."""
    for col, name in enumerate(theme._THEME_ORDER):
        ratio = _contrast(theme._TOKENS['--border-2'][col],
                          theme._TOKENS['--surface-2'][col])
        assert 1.1 <= ratio <= 3.0, (name, round(ratio, 2))
