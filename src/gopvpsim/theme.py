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
    # Outcome text (re-valued phase-2: AA-solved against BOTH page bg and the
    # harder --cell-*-bg tints).
    "--win":            ("#31a547", "#247934", "#2c933f", "#257b35"),
    "--loss":           ("#e96767", "#c31c1c", "#e54848", "#cb1d1d"),
    "--tie":            ("#b08c05", "#846904", "#9d7d05", "#896d04"),
    "--flip":           ("#cd7e0b", "#995f08", "#b7710a", "#a06309"),
    "--bar-track":      ("#3c3836", "#ebdbb2", "#273140", "#e3e8ee"),
    "--energy":         ("#0ea295", "#0b7970", "#0d9085", "#0b7e74"),
    "--callout-bg":     ("#32302f", "#f4e8c1", "#1b212b", "#eef1f5"),
    "--callout-fg":     ("#ebdbb2", "#5c4a1a", "#cfd6df", "#3a4654"),
    "--callout-strong": ("#fbf1c7", "#3c3836", "#ffffff", "#1c2530"),
    "--callout-ai":     ("#cd580e", "#d85d0e", "#b54e0c", "#e2610f"),
    "--callout-auto":   ("#357cd4", "#4184d6", "#296dc1", "#4a8ad8"),
    "--callout-expert": ("#977804", "#9f7f05", "#856a04", "#a68405"),
    # "both" = joint LLM+human authorship tier (green). Not in the original
    # spec table (which listed only ai/auto/expert) but the reader guides use a
    # 4th tier; added so it themes correctly on all backgrounds.
    "--callout-both":   ("#2a8e3d", "#2c9540", "#257d36", "#2e9c43"),
    # On-fill text tokens (phase-2 split of the old single on-fill token): each is solved
    # against ONE fill, so both clear AA in all four themes (the old single token
    # could not clear --title and --accent at once in gruvbox-light).
    # --on-title: text on var(--title) button fills (build_website_index .btn).
    "--on-title":       ("#000000", "#000000", "#000000", "#ffffff"),
    # --on-accent: text on var(--accent) button fills (#ivc-go envelope CTA).
    "--on-accent":      ("#000000", "#ffffff", "#000000", "#ffffff"),
    # Matchup-web heatmap cells (scripts/build_matchup_web.py). The matrix
    # conveys win/loss MARGIN as a continuous alpha ramp (12%-67%) over a
    # single fill color per outcome -- NOT discrete shade tiers -- so each
    # outcome needs one fill (-bg, alpha-ramped at render time via color-mix)
    # plus one text color (-fg). Tie is a flat bg+fg pair (no ramp; s==500
    # only). Greens/reds stay clearly green/red per theme (heatmap
    # convention) while lightness is tuned to each background so the
    # strong-vs-marginal contrast stays legible. Light themes flip the text
    # dark; dark themes keep it light.
    "--matrix-win-bg":  ("#1f5a2e", "#cfe8c2", "#1a5128", "#d3f0d9"),
    "--matrix-win-fg":  ("#77d789", "#217030", "#58cd6e", "#237633"),
    "--matrix-loss-bg": ("#7a2424", "#f3d2c8", "#7a2222", "#fbdcd6"),
    "--matrix-loss-fg": ("#f19999", "#b91a1a", "#f09797", "#c41c1c"),
    "--matrix-tie-bg":  ("#3c3836", "#ece0bd", "#232b38", "#e6eaf0"),
    "--matrix-tie-fg":  ("#b2a373", "#6d613c", "#a3925a", "#736740"),
    # ---- Phase-2 new semantic tokens ----
    # Cell tints: dark themes deepen page bg TOWARD the hue (darker than --bg
    # so light text stays legible); light themes use pale tints. gruvbox-light
    # --cell-neutral-bg is deliberately LIGHTER than page bg to lift --text-muted
    # to AA.
    "--cell-win-bg":     ("#1d241d", "#eaf0d6", "#0d160f", "#e7f3ea"),
    "--cell-loss-bg":    ("#2c1d1d", "#f6ddd2", "#170c0e", "#fbe4e0"),
    "--cell-neutral-bg": ("#222222", "#fdf7dd", "#0d1117", "#eceff3"),
    # Notable / efficient / slayer-overlay gold highlight text.
    "--notable":         ("#b68a14", "#88670f", "#a27b12", "#8e6b0f"),
    # Gender identity (text; lane tints derived via color-mix at render).
    "--sex-male":        ("#5d8df3", "#1e61ef", "#437bf1", "#2667ef"),
    "--sex-female":      ("#e461a8", "#c9227c", "#df4297", "#d12381"),
    # Attack-weight chips (catw). Several are intentional same-value aliases
    # (see section 6 / governance): rank1==tier-8, none==rarity-common,
    # slight==rarity-uncommon, heavy==cat-cmp, bulk==rarity-rare/cat-anchors/
    # tier-1, tilt==tier-6.
    "--catw-rank1":      ("#a68405", "#866b04", "#a28105", "#8e7104"),
    "--catw-none":       ("#888888", "#6e6e6e", "#858585", "#757575"),
    "--catw-slight":     ("#2e9c43", "#257e36", "#2d9841", "#28863a"),
    "--catw-heavy":      ("#df6300", "#b55000", "#da6000", "#c05500"),
    "--catw-bulk":       ("#4a8ad8", "#2a6ec2", "#4586d7", "#2c75ce"),
    "--catw-tilt":       ("#0d998c", "#0b7c72", "#0d9589", "#0b8378"),
    # Envelope set.
    "--env-top":         ("#34af4b", "#216d2f", "#2f9d43", "#257c35"),
    "--env-elev":        ("#679cde", "#2460a9", "#4c8bd9", "#296cbf"),
    "--env-dep":         ("#bb9506", "#745d03", "#a78505", "#846904"),
    "--env-bottom":      ("#ec7676", "#bc1b1b", "#e85959", "#d41e1e"),
    # Anchor-rarity chips (aliases of catw-none/slight/bulk).
    "--rarity-common":   ("#888888", "#6e6e6e", "#858585", "#757575"),
    "--rarity-uncommon": ("#2e9c43", "#257e36", "#2d9841", "#28863a"),
    "--rarity-rare":     ("#4a8ad8", "#2a6ec2", "#4586d7", "#2c75ce"),
    # Slayer-category chips (anchors == rarity-rare/catw-bulk/tier-1;
    # cmp == catw-heavy).
    "--cat-anchors":     ("#4a8ad8", "#2a6ec2", "#4586d7", "#2c75ce"),
    "--cat-cmp":         ("#df6300", "#b55000", "#da6000", "#c05500"),
    # Generic deep-dive narrative-zone left-border (teal, non-purple).
    "--zone-narrative":  ("#0c8b80", "#0c897e", "#0b7a70", "#0d988c"),
    # Opponent identity (12 colorblind-distinct hues; md5-hash indexed mod 12).
    "--opp-1":           ("#e96767", "#d41e1e", "#e54848", "#dc1f1f"),
    "--opp-2":           ("#e27100", "#aa5500", "#ca6500", "#b15800"),
    "--opp-3":           ("#b08c05", "#846904", "#9d7d05", "#896d04"),
    "--opp-4":           ("#779d0c", "#597509", "#6a8c0a", "#5d7a09"),
    "--opp-5":           ("#31a547", "#257c35", "#2c933f", "#268137"),
    "--opp-6":           ("#0ea295", "#0b7970", "#0d9085", "#0b7e74"),
    "--opp-7":           ("#0e9dc0", "#0a7690", "#0c8cac", "#0b7b97"),
    "--opp-8":           ("#5893db", "#296cbf", "#3e82d6", "#2b71c7"),
    "--opp-9":           ("#8a84ee", "#5f57e7", "#7871eb", "#655de8"),
    "--opp-10":          ("#b472f0", "#9536ea", "#a85aee", "#993feb"),
    "--opp-11":          ("#df5ecb", "#bd25a6", "#d83cc0", "#c527ac"),
    "--opp-12":          ("#e16892", "#ca2961", "#db4c7e", "#d22a65"),
    # Threshold-tier ordered set (tier-1==rarity-rare/cat-anchors/catw-bulk;
    # tier-6==catw-tilt; tier-8==catw-rank1). Render as tier-color TEXT on
    # --surface-2.
    "--tier-1":          ("#4a8ad8", "#2a6ec2", "#4586d7", "#2c75ce"),
    "--tier-2":          ("#d66a00", "#ad5600", "#d16800", "#b85b00"),
    "--tier-3":          ("#2e9c43", "#257e36", "#2d9841", "#28863a"),
    "--tier-4":          ("#e75757", "#d81f1f", "#e65151", "#e12929"),
    "--tier-5":          ("#ae65ef", "#973aeb", "#ab61ef", "#9d47ec"),
    "--tier-6":          ("#0d998c", "#0b7c72", "#0d9589", "#0b8378"),
    "--tier-7":          ("#dc4dc6", "#c126a9", "#db47c3", "#cc28b3"),
    "--tier-8":          ("#a68405", "#866b04", "#a28105", "#8e7104"),
    # Mirror tier: distinct purple for the same-species mirror breakpoint/
    # bulkpoint tier (deep_dive_analysis), kept separate from --tier-5 so it
    # reads as a "different category" from per-opponent tiers. Rendered as
    # tier-color TEXT on --surface-2 (4.70-4.77 AA all themes).
    "--tier-mirror":     ("#9970f7", "#7a51d8", "#976cf7", "#8356e7"),
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


def data_theme_attr() -> str:
    return f'data-theme="{DEFAULT_THEME}"'


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
