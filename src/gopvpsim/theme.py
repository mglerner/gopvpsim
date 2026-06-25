"""Shared theme system for every pogo-dives rendered page.

One source of truth for the site palette. Four selectable themes
(gruvbox-dark, gruvbox-light, pokemon-dark, pokemon-light) are defined on a
single CSS-variable contract, so switching theme is one attribute swap and
no renderer carries its own palette. Every renderer:

  1. sets ``data-theme`` on its ``<html>`` (the static default below),
  2. injects ``theme_css()`` into its ``<style>`` block,
  3. uses ``var(--token)`` in place of hardcoded palette hex,
  4. drops ``theme_head_script()`` early in ``<head>`` (pre-paint, no flash)
     and ``theme_picker_html()`` once in the body (the compact picker).

The picker is a single compact control emitted here, identical on every
page type, because only 2 of the 7 renderers have a sidebar to host it.

Palette adapted from Gruvbox by Pavel "morhetz" Pertsev
(https://github.com/morhetz/gruvbox), MIT license.
"""

DEFAULT_THEME = "gruvbox-light"

# Display order + labels for the picker.
THEMES = [
    ("gruvbox-light", "Gruvbox Light"),
    ("gruvbox-dark", "Gruvbox Dark"),
    ("pokemon-light", "Pokemon Light"),
    ("pokemon-dark", "Pokemon Dark"),
]

# token -> (gruvbox-dark, gruvbox-light, pokemon-dark, pokemon-light).
# Column order matches _THEME_ORDER below. Values are the spec contract;
# change them here and every page re-themes on next render.
_THEME_ORDER = ("gruvbox-dark", "gruvbox-light", "pokemon-dark", "pokemon-light")
_TOKENS = {
    "--bg":             ("#282828", "#fbf1c7", "#12161d", "#f7f8fa"),
    "--surface":        ("#32302f", "#ebdbb2", "#1a212b", "#eef1f5"),
    "--surface-2":      ("#1d2021", "#f9f5d7", "#161c25", "#ffffff"),
    "--border":         ("#3c3836", "#d5c4a1", "#273140", "#d8dee6"),
    "--border-2":       ("#504945", "#d5c4a1", "#2b3645", "#dbe2ea"),
    "--text":           ("#ebdbb2", "#3c3836", "#e8eaed", "#1c2530"),
    "--text-muted":     ("#a89984", "#7c6f64", "#93a0b0", "#5d6b7a"),
    "--heading":        ("#ebdbb2", "#3c3836", "#eef0f3", "#243240"),
    "--title":          ("#fabd2f", "#b57614", "#ffcb05", "#003a70"),
    "--accent":         ("#83a598", "#076678", "#5aa9e6", "#2a6fc4"),
    "--accent-2":       ("#83a598", "#076678", "#3d7dca", "#3d7dca"),
    "--win":            ("#b8bb26", "#79740e", "#54c45e", "#2f9e44"),
    "--loss":           ("#fb4934", "#9d0006", "#f5483c", "#e3350d"),
    "--tie":            ("#fabd2f", "#b57614", "#f4c542", "#a87b00"),
    "--flip":           ("#fabd2f", "#b57614", "#ffcb05", "#c79100"),
    "--bar-track":      ("#3c3836", "#ebdbb2", "#273140", "#e3e8ee"),
    "--energy":         ("#8ec07c", "#427b58", "#66c6b0", "#138a72"),
    "--callout-bg":     ("#32302f", "#f4e8c1", "#1b212b", "#eef1f5"),
    "--callout-fg":     ("#ebdbb2", "#5c4a1a", "#cfd6df", "#3a4654"),
    "--callout-strong": ("#fbf1c7", "#3c3836", "#ffffff", "#1c2530"),
    "--callout-ai":     ("#fe8019", "#af3a03", "#ff8c42", "#c2410c"),
    "--callout-auto":   ("#83a598", "#076678", "#3d7dca", "#2a6fc4"),
    "--callout-expert": ("#fabd2f", "#b57614", "#ffcb05", "#b57614"),
    # "both" = joint LLM+human authorship tier (green). Not in the original
    # spec table (which listed only ai/auto/expert) but the reader guides use a
    # 4th tier; added so it themes correctly on all backgrounds. Tracks the
    # energy-green per theme for now; can diverge later without touching sites.
    "--callout-both":   ("#8ec07c", "#427b58", "#66c6b0", "#138a72"),
    # Matchup-web heatmap cells (scripts/build_matchup_web.py). The matrix
    # conveys win/loss MARGIN as a continuous alpha ramp (12%-67%) over a
    # single fill color per outcome -- NOT discrete shade tiers -- so each
    # outcome needs one fill (-bg, alpha-ramped at render time via color-mix)
    # plus one text color (-fg). Tie is a flat bg+fg pair (no ramp; s==500
    # only). Greens/reds stay clearly green/red per theme (heatmap
    # convention) while lightness is tuned to each background so the
    # strong-vs-marginal contrast stays legible. Light themes flip the text
    # dark; dark themes keep it light.
    "--matrix-win-bg":  ("#4e8a3a", "#5a8a2e", "#3a8f4a", "#2f9e44"),
    "--matrix-win-fg":  ("#b8e8b8", "#2f4a14", "#c4f0c4", "#14532d"),
    "--matrix-loss-bg": ("#b33636", "#b3261e", "#c43a3a", "#e3350d"),
    "--matrix-loss-fg": ("#ecc0c0", "#6e1410", "#f5cccc", "#7a1c08"),
    "--matrix-tie-bg":  ("#3c3836", "#ece0bd", "#232b38", "#e6eaf0"),
    "--matrix-tie-fg":  ("#d5c4a1", "#5c4a1a", "#c4cdd9", "#3a4654"),
}

# Static chrome for the picker. Uses tokens so it adapts to the active theme.
# Fixed top-right, low footprint; relocatable by editing only this rule.
_PICKER_CSS = """
  .theme-picker { position:fixed; top:8px; right:8px; z-index:1000;
    font-size:12px; opacity:.85; }
  .theme-picker:hover, .theme-picker:focus-within { opacity:1; }
  .theme-picker select { font:inherit; font-size:12px; padding:2px 6px;
    color:var(--text); background:var(--surface); border:1px solid var(--border);
    border-radius:2px; }
  @media print { .theme-picker { display:none; } }
"""


def theme_css() -> str:
    """Return the ``[data-theme=...]`` token blocks + picker chrome CSS.

    Inject this into every page's ``<style>`` block. It defines all four
    themes on the same variable names, so the renderers reference only
    ``var(--token)`` and the active ``data-theme`` on ``<html>`` selects which
    set of values applies.
    """
    blocks = []
    for col, name in enumerate(_THEME_ORDER):
        decls = "\n".join(
            f"    {tok}: {vals[col]};" for tok, vals in _TOKENS.items()
        )
        blocks.append(f'  [data-theme="{name}"] {{\n{decls}\n  }}')
    return "\n".join(blocks) + "\n" + _PICKER_CSS


def theme_head_script() -> str:
    """Inline pre-paint script: apply the stored theme before the body paints.

    Place EARLY in ``<head>`` (before any visible content). The static
    ``data-theme`` on ``<html>`` gives a valid default; this synchronously
    overrides it with the user's stored choice, so there is no theme flash.
    """
    return (
        "<script>(function(){try{var t=localStorage.getItem('pogo-theme');"
        "if(t)document.documentElement.setAttribute('data-theme',t);}"
        "catch(e){}})();</script>"
    )


def theme_picker_html() -> str:
    """Return the compact theme picker (one per page, anywhere in the body).

    A native ``<select>`` (most compact, accessible). On change it sets
    ``data-theme`` and persists to ``localStorage``; an inline sync sets the
    control to the stored value on load.
    """
    opts = "".join(
        f'<option value="{val}">{label}</option>' for val, label in THEMES
    )
    return (
        '<div class="theme-picker"><select aria-label="Theme" '
        "onchange=\"document.documentElement.setAttribute('data-theme',this.value);"
        "try{localStorage.setItem('pogo-theme',this.value);}catch(e){}\">"
        f"{opts}</select></div>"
        "<script>(function(){try{var t=localStorage.getItem('pogo-theme');"
        "if(t){var s=document.querySelector('.theme-picker select');"
        "if(s)s.value=t;}}catch(e){}})();</script>"
    )


# Footer credit line (required by the spec). Append to the sitewide footer.
GRUVBOX_CREDIT_HTML = (
    'Theme palette adapted from '
    '<a href="https://github.com/morhetz/gruvbox">Gruvbox</a> by '
    'Pavel "morhetz" Pertsev (MIT).'
)
