# pogo-dives palette authoring contract

This is the single contract for the pogo-dives color palette. Read it
before touching any color in any renderer, and before adding a theme.
The standing rule (Michael's): the palette suite ships FULL and
CONSISTENT or it does not ship. No half-migrated renderer, no
mismatched hex sneaking past review. If you start a palette change,
finish every consumer in the same arc.

## 1. The token contract and where it lives

All palette values live in ONE place: `src/gopvpsim/theme.py`, in the
`_TOKENS` dict. Each entry maps a CSS custom-property name (e.g.
`--win`) to a 4-tuple of hex values, one per theme, in the fixed order
declared by `_THEME_ORDER`:

    ("gruvbox-dark", "gruvbox-light", "pokemon-dark", "pokemon-light")

`theme_css()` walks `_TOKENS` and emits a `[data-theme="..."]{ ... }`
block per theme. Every renderer injects `theme_css()` into its
`<style>` and references colors ONLY as `var(--token)`. The active
`data-theme` attribute on `<html>` selects which column applies. Change
a value in `_TOKENS` and every page re-themes on its next render -- no
per-renderer edits.

The hard rule for renderers: a literal hex in renderer CSS or in
JS-emitted inline style is a contract violation. The only sanctioned
literal-hex homes are (a) `_TOKENS` itself and (b) `_TYPE_COLORS` in
`deep_dive_card.py` (the Pokemon type-brand palette, intentionally out
of scope -- see section 7).

## 2. Token categories

The tokens partition into six categories. When you add a theme you fill
every token in every category; partial fills are the failure mode this
doc exists to prevent.

- chrome: structural surfaces and text. `--bg`, `--surface`,
  `--surface-2`, `--border`, `--border-2`, `--text`, `--text-muted`,
  `--heading`, `--title`, `--accent`, `--accent-2`, `--bar-track`,
  `--callout-bg`, `--callout-fg`, `--callout-strong`.
- outcome: win/loss/tie/flip/energy text. `--win`, `--loss`, `--tie`,
  `--flip`, `--energy`.
- cell-tints: table-cell backgrounds. `--cell-win-bg`,
  `--cell-loss-bg`, `--cell-neutral-bg`. Dark themes deepen the page bg
  TOWARD the hue (darker than `--bg` so light text stays legible);
  light themes use pale tints. `--cell-neutral-bg` in gruvbox-light is
  deliberately LIGHTER than the page bg so the inherently-weak
  `--text-muted` chrome text lifts to AA on it.
- callout-tiers: authorship-callout borders, which double as deep-dive
  zone left-borders. `--callout-ai` (orange), `--callout-auto` (blue,
  also the sim-zone border), `--callout-expert` (gold, also the
  expert-zone border), `--callout-both` (green). Plus `--zone-narrative`
  (teal, non-purple) for the generic narrative zone.
- categorical-identity: ordered/keyed palettes where the COUNT and
  ORDER are load-bearing. `--opp-1..--opp-12` (12 colorblind-distinct
  hues: red, orange, gold, lime, green, teal, cyan, blue, indigo,
  purple, magenta, rose), `--tier-1..--tier-8` (blue, orange, green,
  red, purple, teal, magenta, gold), the chip families
  `--catw-*` / `--rarity-*` / `--cat-*`, the `--env-*` envelope set,
  and the `--sex-male` / `--sex-female` identity pair. Several chip
  tokens are intentional same-value aliases of each other (see
  section 6) -- kept as distinct names for call-site clarity.
- matrix: matchup-web heatmap fills and text. `--matrix-win-bg/-fg`,
  `--matrix-loss-bg/-fg`, `--matrix-tie-bg/-fg`. The bg is alpha-ramped
  at render time via `color-mix` (win/loss carry margin as a 12-67%
  ramp; tie is flat, no ramp).

## 3. The contrast rule

Every value in `_TOKENS` MUST pass WCAG AA. The threshold and the
background depend on what the token paints:

- Text tokens (outcome, categorical-identity used as text, matrix `-fg`,
  `--notable`, `--sex-*`, chip text): contrast ratio >= 4.5 against the
  background they render on, in ALL FOUR themes. The reference
  background is the token's documented surface:
  - opponent name text (`--opp-*`): the page `--bg`.
  - tier badge text (`--tier-*`): `--surface-2` (badges render as
    tier-color TEXT on `--surface-2`, not saturated fill).
  - matrix `-fg`: the matching `-bg` (light themes flip the text dark,
    dark themes keep it light).
  - outcome text in cells (`--win`/`--loss`): must clear 4.5 on BOTH
    the page bg AND the harder cell tint (`--cell-*-bg`). The outcome
    values were re-solved against the cell tint for exactly this.
- Background/fill tokens (cell-tints, matrix `-bg`, chip fills): the
  paired text must clear 4.5 ON that fill. For the alpha-ramped matrix
  fills, verify at the ramp endpoints.

There is no "looks fine" exemption. A value that is AA on three themes
and fails the fourth is a failed value; fix it or the suite is not
shippable.

## 4. Add-a-new-theme checklist

A new theme is a new entry in `_THEME_ORDER` plus a new column in every
`_TOKENS` tuple. Do all of this, in order, in one arc:

1. Add the theme key to `_THEME_ORDER` and a (key, label) pair to
   `THEMES` for the picker.
2. Fill EVERY token. Extend each tuple in `_TOKENS` with one value.
   Zero gaps -- a missing column is a Python error or, worse, a silent
   wrong-length tuple. Grep that every tuple now has the new arity.
3. Run the contrast check (section 3) on every new value, against its
   documented background, for the new theme. Treat any sub-4.5 result
   as blocking.
4. Re-verify the OTHER themes did not regress (they should not, but the
   check is cheap and the rule is "full and consistent").
5. Render one of each page type (deep dive, article, index, card,
   matchup web, envelope guide) under the new theme and eyeball the
   six categories -- cells, chips, matrix, callouts, opponent names,
   tier badges.

Until all four (now five) themes pass for a token, that token is not
done, and the suite is not done.

## 5. The DEFAULT_THEME dead-code trap

`theme.py` defines `DEFAULT_THEME = "gruvbox-light"`. It is imported by
nothing (verified: zero references outside its own definition). It is
DEAD CODE and a trap: editing it changes nothing.

The REAL default is the literal `data-theme="gruvbox-light"` string
hardcoded on the `<html>` element in roughly eight renderers
(`deep_dive.py`, `render_article.py`, `render_iv_envelope_article.py`,
`compare_loadouts.py`, `build_guides.py`, `deep_dive_card.py`,
`build_matchup_web.py`, and `build_website_index.py` -- the last has it
twice). Changing the site default today means editing all of those.

Fix: make `theme.py` the one edit point. Export a helper (e.g. a
`html_open_tag()` or a `DEFAULT_THEME`-consuming `data_theme_attr()`)
and have every renderer emit the attribute from it, so one edit in
`theme.py` changes the default everywhere. Either wire `DEFAULT_THEME`
into a shared emitter or delete it -- do not leave a constant that
looks authoritative but governs nothing.

## 6. Intentional chip aliases (one hue per concept)

Some categorical tokens share identical values on purpose, kept as
separate names so call sites read clearly:

- `--rarity-uncommon` == `--catw-slight` (green)
- `--rarity-rare` == `--cat-anchors` == `--catw-bulk` == `--tier-1` (blue)
- `--rarity-common` == `--catw-none` (gray)
- `--cat-cmp` == `--catw-heavy` (orange)
- `--catw-rank1` == `--tier-8` (gold)
- `--catw-tilt` == `--tier-6` (teal)

When you revalue one of an alias group, revalue ALL of it, or the
"one hue per concept" guarantee breaks silently. (A lint that asserts
alias-equal tokens stay equal is a good guard; see section 8.)

## 7. What is intentionally OUT of the contract

- Pokemon type-brand palette: `_TYPE_COLORS` in `deep_dive_card.py`.
  These are brand colors for the 18 types; they are not themeable and
  stay as literal hex. Only the FORCED text drawn ON those chips is in
  scope (it must be a contrast-safe token, not a hardcoded near-black).
- Sprite/raster art: any PNG/sprite asset. Not CSS, not in scope.
- Stale guide/CD screenshots: prose pages embed point-in-time
  screenshots whose colors predate the current palette. Do not try to
  recolor images; if a screenshot misleads, recapture it, do not patch
  the token table to match an old PNG.

## 8. Two sources of truth, and the prose-drift gap

The palette has TWO live consumers, and both must move together:

1. CSS tokens: `var(--token)` resolved by the browser from the
   `theme_css()` blocks. This is the primary surface.
2. A deferred Plotly `getComputedStyle` shim: Plotly markers cannot
   read CSS variables directly. The plan is a small JS shim that calls
   `getComputedStyle(document.documentElement).getPropertyValue('--tier-1')`
   (etc.) at chart-build time and feeds the resolved hex into Plotly's
   `marker.color`. Until that shim lands, Plotly marker colors are
   injected as resolved hex through a Python placeholder
   (`__TIER_COLORS_JS__`), which means the tier hues exist in TWO forms
   at once -- CSS var and Python-resolved literal. Keep them sourced
   from the same `_TOKENS` values so the badges and the scatter markers
   never diverge.

Separately, the guide and CD-article PROSE hand-quotes hex values in
running text (so a reader can match "the gold chip (`#a68405`)" to what
they see). Hand-quoted hex DRIFTS the moment a token is revalued and
nothing catches it. Mitigation, required before the next revalue:
either a lint that scans `articles/` and guide prose for hex literals
and checks them against `_TOKENS`, OR a generated legend (render the
swatch + hex from `_TOKENS` into the page) so prose references a single
generated source instead of a typed constant. Do not ship a palette
revalue without one of these in place, or the prose silently lies.

## 9. The migrate-CSS-and-JS-together hazard

Several consolidations span a Python-emitted CSS string AND a JS array
that Python injects. The opponent palette and the tier palette are
both like this: the CSS classes live in `deep_dive_rendering.py` /
`deep_dive_analysis.py`, while `deep_dive_engine.js` consumes the same
hues through injected placeholders (`__TIER_COLORS_JS__`) and through
JS-built inline `style=` strings. If you migrate the CSS to `var()` but
leave the JS emitting old literal hex (or vice versa), the on-page
badge and the scatter marker for the same tier will mismatch -- exactly
the "mismatched colors sneaking through" failure. Rule: CSS tokens and
every JS color that mirrors them migrate in the SAME commit, and you
verify a rendered dive shows badge == marker == legend before calling
it done.
