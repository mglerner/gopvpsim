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

## ROLLOUT INCOMPLETE -- handed to the UI session (2026-06-25)

The dive re-render exposed two gaps; "all 8 renderers themed" was wrong.

1. **Missed CSS modules** (never in the renderer list): `deep_dive_rendering.py`
   (the big `.dd-*` block -- dive tables, section panels, callouts, shield
   grids, opponent chips, slayer/recommendation cards: ~60 hardcoded hex) and
   `generate_article.py`. Also the `render_article.py`/`sidebar_css` partial.
   `deep_dive.py` itself is fully tokenized (0 old hex) -- it's these imported
   modules that emit most of the dive *body* CSS, so themed dives have light
   chrome but a dark body on the light themes.

2. **Semantic/categorical colors have no light-mode variants -- the real work.**
   Pokemon names tinted by type/flavor, delta values (faded `0.0`, green
   `100%`), flavor labels, threshold %, italic prose, win/loss cell tints --
   all tuned for a DARK bg, so they fail contrast and go unreadable on the
   cream light theme (Michael's 2026-06-25 screenshots: items 2,3,4,5,7,8,9,10).
   This is NOT a hex->token swap; these palettes need contrast-checked light+dark
   variants. Use a principled system, do NOT hand-guess: **Radix Colors**
   (paired light/dark scales w/ accessible text steps), **Leonardo**
   (contrast-targeted ramps), **Okabe-Ito/ColorBrewer** for the categorical
   type set; verify WCAG AA 4.5:1 / APCA. Add per-theme semantic tokens to the
   `theme.py` contract (same pattern as the `--matrix-*` tokens).

3. **Plotly graphs (scatter + histogram) -- DEFERRED to a later session** (OK'd).
   Their colors are Plotly JS layout, not CSS; separate sub-problem (transparent
   plot bg + theme-aware fonts/grid + relayout-on-theme-switch). Items 1,6.

Owner: the UI session (resumed). Reference artifact showing exactly what breaks:
`/tmp/altaria-themed-DRAFT.html` (structural tokens applied; semantic colors
left -> the unreadable ones are now visible against light). Commits 582dfde /
ed1ca5f are the worked tokenization pattern; the canonical map + role rules are
above.

## PHASE 2 COMPLETE -- semantic tokens baked (2026-06-25)

The "ROLLOUT INCOMPLETE" gaps above are now closed. Spec/governance:
`/tmp/THEME_PHASE2_SPEC.md` (per-file selector map, AA-verified token values)
and `docs/palette_governance.md` (the palette authoring contract, now committed).
The bake values the spec session confirmed are archived at
`/tmp/THEME_PHASE2_BAKE.md`.

Done this arc (all via adversarially-verified agent workflows; the audits
caught real bugs each pass -- on-brand AA conflict, tier var/hex drift, a
mod-8 regression, and a tier-badge index-reconstruction bug):

- `theme.py` `_TOKENS`: 15 tokens re-valued to AA-pass values, ~43 added
  (opp-1..12, tier-1..8 + tier-mirror, cell tints, envelope, catw/rarity/cat
  chip families, sex-male/female, on-title/on-accent). `--on-brand` split into
  `--on-title` / `--on-accent` (the gruvbox-light button-text AA conflict).
  Added `data_theme_attr()` -- the single site-default emitter; every renderer
  now sources `data-theme` from it (DEFAULT_THEME dead-code trap closed).
- Missed CSS modules tokenized: `deep_dive_rendering.py` (dd-* body CSS, opp
  palette 16->12 mod-12, atk-weight/rarity/env/zone chips, inline styles),
  `generate_article.py` (full chrome + gender rgba via color-mix + flip cells +
  banners), `deep_dive_engine.js` (all JS-emitted inline-style/innerHTML hex ->
  var() strings), `deep_dive_narrative.py`, `patch_dive_species_narrative.py`,
  `attribution.py`, the `render_article.py` sidebar partial, plus the
  audit-discovered `write_aegislash_narrative.py`.
- Unified tier palette across CSS + JS (the migrate-together hazard):
  THRESHOLD_COLORS + TIER_COLORS_AUTO + narrative-10 collapsed to `--tier-1..8`;
  badges render as tier-color TEXT on `--surface-2` (no more saturated fill +
  forced #000). Theme-aware badges use `var(--tier-N)`; Plotly markers get
  resolved hex via `_TIER_VAR_TO_HEX` at a single injection boundary (now with
  a guard that raises on an unmapped tier color). A parallel `__TIER_VARS_JS__`
  array lets the JS summary badge read each tier's OWN var (not an index
  reconstruction), so badge == card == marker for all tiers incl. mirror and
  the General-removal case.

STILL OUT (deferred, OK'd): Plotly canvas/marker recoloring -- needs a
`getComputedStyle` shim so markers theme live; until then markers carry the
DEFAULT_THEME (gruvbox-light) resolved hex. `_TYPE_COLORS` (type-brand) stays
out of the contract.

GREEN-LIGHT STATUS (2026-06-25, post-adversarial-pass):

Independent adversarial verification (other session, 7 agents, refute-by-default,
read-only) against HEAD `9221908`: NO BLOCK -- green-lit. Token values, the tier
pipeline (badge == card == marker, mirror distinct, mod-8 wrap, injection guard
that raises on an unmapped tier), zero-leftover, and theme-switch all verified
clean at HEAD. The "block" findings it surfaced were STALE-PAGE ARTIFACTS:
on-disk dives/matchups/index were rendered ~20:00-21:42, before the ~22:55
commits, so the HTML inspectors read the OLD pre-theme palette -- false against
committed code, not regressions. The "hardcoded data-theme" finding is the known
`.replace()` sentinel (build_matchup_web.py:151 / build_website_index.py:650 ->
lines 460/791), a false positive.

REMAINING GATE before phase2 / publish -- the full dive re-render, which MUST run
HEAD `9221908` (do NOT publish the current on-disk PRE-theme output):
  1. Smoke FIRST: render ONE fresh dive (pick an auto-derive dive so it exercises
     `_next_color` + the General-removal path + a mirror tier) and ONE comparison,
     then eyeball all 4 themes. The adversarial pass render-inspected the ML guide
     / index / matchup end-to-end, but NOT a dive or comparison -- those two
     page types are source-verified-only (low risk, but un-eyeballed).
  2. If clean, run the full batch re-render at HEAD.
  3. Then arm phase2_preship.sh. Push remains nod-gated.

KNOWN sub-AA values to batch later (NON-blocking; flagged honestly -- do NOT
claim "all AA pass"): `--text-muted` gruvbox-light = 4.29:1 (pre-existing chrome
token, NOT introduced by phase-2; secondary .sub/footer/nav text; best candidate
for a small darkening). VERIFY `--accent-2` pokemon-light 3.96:1 in `.cmp-marg-h`
is large-text (>=3:1 ok) -- if it is body text it fails 4.5. Passing on the
relaxed large-text/UI threshold (fine, no action): `--title` gl 3.33 (h1
large-text >=3:1), `--callout-ai` border ~3.3 (UI component >=3:1).
