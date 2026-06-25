# Theme rollout status (de-slop restyle)

Working tracker for wiring the shared 4-theme system
(`src/gopvpsim/theme.py`) into every renderer. Source spec:
`/tmp/THEME_HANDOFF_SPEC.md` (from the UI session). Default theme
`gruvbox-light`; folds into the current publish (phase2 re-renders all
pages once the waiter is armed).

## Done

- **Foundation** `src/gopvpsim/theme.py` (commit 4b542af): 4 themes
  (gruvbox-dark/-light, pokemon-dark/-light) on a 24-token contract,
  pre-paint head script, universal compact picker (native select, fixed
  top-right -- chosen over the spec's sidebar idea because only 2 of 7
  renderers have a sidebar), `GRUVBOX_CREDIT_HTML`.
- **`--callout-both` token added** (commit ed1ca5f): the spec's token table
  listed only ai/auto/expert callout tiers, but the reader guides use a 4th
  "both" (joint LLM+human) tier. Added so it themes on light backgrounds.
  FLAG FOR REVIEW.
- **Renderer 1/7 -- ML IV guides** `render_iv_envelope_article.py` +
  `support_footer_html` tokenized w/ Gruvbox credit (commit 582dfde).
- **Renderer 2/7 -- reader guides** `build_guides.py` (commit ed1ca5f).
- Preview of the ML-guide page type (all 4 themes):
  `/tmp/palkia-origin-ml-iv-guide-THEMED.html`.

## Per-renderer pattern (see the two done commits as worked examples)

1. `<html>` -> `<html data-theme="gruvbox-light">`
2. `theme_head_script()` early in `<head>` (after charset)
3. `theme_css()` prepended into the `<style>` block
4. `theme_picker_html()` once just after `<body>`
5. hex -> `var(--token)` (map below)
6. structural swings: callouts get an all-sides 1px border carrying the tier
   color (no left bar / `::before`), border-radius -> 0; cards/panels/inputs
   -> 2px; chips/badges keep 4px; h2/h3 type scale
   (`font-size:1.15em;font-weight:700;letter-spacing:.02em`); remove
   `text-transform:uppercase` from section labels; retire purple `#c8a2d0`.
7. import `theme_css, theme_head_script, theme_picker_html` from `gopvpsim.theme`.

**Template brace gotcha:** f-string templates (`f"""..."""`) take
`{theme_css()}` directly (the returned CSS braces are runtime data, not
parsed). `.format()` templates (CSS braces escaped as `{{ }}`) CANNOT take
raw CSS literally -- pass theme output as `.format()` kwargs, the way
`{SUPPORT_FOOTER}` is already passed.

## Canonical hex -> token map (unambiguous; safe scripted replace)

```
#1a1a2e -> --bg            #3fb950 -> --win        #16213e -> --surface
#0f162a,#10182c -> --surface-2                     #24314d -> --border-2
#e0e0e0,#e6ecf5,#cdd6e5 -> --text                  #f85149 -> --loss
#8ea1bd,#8b949e,#9bb0d0 -> --text-muted            #f0b429 -> --flip
#c8a2d0 -> --heading (purple; retire)              #1a2540 -> --bar-track
#e94560 -> --title                                 #7fd3b0 -> --energy
#2e241a,#2e2a1a -> --callout-bg                     #9be89b -> --accent
#e8903a -> --callout-ai     #7db87d -> --callout-both
```

## Overloaded hexes -- role-decide per occurrence, NEVER blind-replace

- `#0f3460`: border/rule -> `--border`; dark fill (chip/select/button bg)
  -> `--surface-2`. (67 occ sitewide; in deep_dive.py both roles appear --
  see fill lines 4479/4503/4510/4539/4558/4565, border the rest.)
- `#58a6ff`: 2nd-header -> `--accent-2`; link -> `--accent`.
- `#5b8dd9`: link -> `--accent`; panel/auto-tier border -> `--callout-auto`.
- `#d4a017`: tie -> `--tie`; expert-tier border -> `--callout-expert`.
- `#d29922`: ai-tier border -> `--callout-ai`; expert/credit border ->
  `--callout-expert`. (resolve by which selector it's on.)

## Remaining renderers (5) + cmp_panels.js

- [ ] **`build_website_index.py`** (30 hex, 2 pages: index + support page).
      Index is `.format()`-style (escaped `{{ }}`), support page is a plain
      string -> inject theme per the brace gotcha. `a.chip` bg `#0f3460` is a
      FILL -> `--surface-2`; `a.chip` keeps 4px (chip). `.btn:hover #c63350`
      -> use `filter:brightness(1.1)` instead of a hex. `#1b4b80` (chip hover
      bg) -> `--border-2`. No callouts here.
- [ ] **`compare_loadouts.py`** (79 hex). Check for `.cmp-*` margin bars
      (spec-covered, same mapping as the ML guide) and any gradient cells
      before scripting.
- [ ] **`build_matchup_web.py`** (44 hex). `.format()` template (inject via
      kwargs). **DECISION NEEDED:** the W/L matrix uses multiple paired
      bg/text shades for win/loss/tie *margin tiers* (`#128204`/`#b8e8b8`,
      `#ecc0c0`/`#e89b9b`, `#2b2615`/`#f0d890`, muted variants). Mapping to
      single `--win`/`--loss`/`--tie` tokens FLATTENS the margin info. Options:
      (a) add win/loss/tie *-strong/-muted* shade tokens to the contract, or
      (b) accept flattening (matrix becomes 3 flat colors). Ask the user.
      `#0f3460` here is all borders -> `--border`.
- [ ] **`deep_dive.py`** (133 hex -- the big one). f-string template
      (line ~4462). Embeds the dive card by appending `_ddcard.CARD_CSS`
      (line ~5243) -> the card must be themed too (do deep_dive_card first).
      `#0f3460` role-split (above). Callouts: `.ddcard-note` (gold) ->
      `--callout-expert`; `.ddcard-sib` (purple `#b07cff`) -> border
      `--accent` (purple retired); `.panel` -> `--callout-auto`.
      `#1a3a6e` (lighter control border) -> `--border-2`.
- [ ] **`deep_dive_card.py`** (72 hex, uppercase=2). **PRESERVE `_TYPE_COLORS`**
      (Pokemon type badges, spec section 7 -- NOT palette tokens). Remove
      uppercase from section labels; small role chips may keep uppercase.
      Callouts `.ddcard-note`/`.ddcard-sib` as above.
- [ ] **`cmp_panels.js`** em-dash cleanup (~lines 63, 114) -> ASCII hyphen;
      grep the renderers for any other em-dashes in emitted public text.

## Verify recipe (per file)

Render a representative page, then check: 4 `[data-theme="..."]` blocks
present, picker present, Gruvbox credit present, no leftover OLD palette hex
in the `<style>` block (allow `#fff`, `_TYPE_COLORS`). Aesthetic pass across
the 4 themes is human (cannot be auto-verified).

## STATUS UPDATE -- rollout essentially complete

All 7 original renderers themed + committed (foundation 4b542af; ML guide
582dfde; reader guides ed1ca5f; matchup web + 6 `--matrix-*` shade tokens
0d08244; deep_dive + card 6f4732f; index + compare + cmp_panels em-dash
6cdaee9). cmp_panels.js em-dash cleanup done.

Contract additions beyond the original spec table:
- `--callout-both` (joint authorship tier; reader guides use a 4th tier).
- `--matrix-win/loss/tie-bg/-fg` (6): the matchup matrix is a CONTINUOUS
  alpha ramp, not discrete tiers -- preserved via `color-mix(... N%,
  transparent)` over a themed fill (user-approved option (a)).

Preserved as theme-independent data-viz (do NOT tokenize): `_TYPE_COLORS`
(type badges) and `THRESHOLD_COLORS` (Plotly tier palette) in
deep_dive_card.py / deep_dive.py.

8th renderer (discovered late, in progress): `render_article.py` /
`sidebar_css()` -- used by CD articles AND shared into compare_loadouts'
summary/methodology/verdict panels. Theming `sidebar_css()` retroactively
finishes those compare panels (imported at render time). Only article TOML
is the Oink CD article (being removed); no article page currently ships.

Outstanding verification:
- deep_dive.py full dive-page render verified at PHASE2 (replay render
  contends with the running sweep; static checks pass now).
- Aesthetic pass across all 4 themes x every page type = human, pre-publish.
- matchup light-theme `--matrix-*-fg` legibility on the 67%-alpha fill is
  the spot most worth a human look.
