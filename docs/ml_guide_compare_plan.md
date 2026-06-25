# ML / IV-guide "close calls" compare embed — locked plan

Bring the deep-dive "Compare my candidates" close-calls panels to the ML / IV
guides, for a small set of **named builds** (not user-typed IVs). Design scouted
2026-06-24; decisions locked with Michael below.

## Locked decisions

- **Named builds (in-box):** draw from the existing 64-combo recommended table
  (all stats 12-15, already simmed) -> **zero extra sims**. Set = stat-product
  #1 (`rec_rows[0]`), an attack-leaning combo, a bulk-leaning combo, and perfect
  15/15/15. (N approx 4. Exact attack/bulk pickers + labels TBD in build.)
- **Energy: included.** Extend `result_metrics` harvesting to the named builds
  across quadrants; embed a parallel energy grid + an `energyMoves`
  `{fast:{gain,abbr}, charged:[{cost,abbr}]}` blob. ~doubles embed bytes.
- **Panel code: shared** from `scripts/deep_dive_engine.js` (`cmpFlipPanel` /
  `cmpMarginPanel`) — guide JS depends on the deep-dive engine. The guide builds
  a fixed `live` list from the named builds instead of the `cmpAdd` input box.
- **Opponent pool:** the full `master_top60.txt` (60 opps) the guide already
  sims. **Per-species** embed in each guide HTML.
- **Quadrants:** `def` = `nobb_vs_nonbb` (neither best-buddied), `alt` =
  `wbb_vs_bb` (both) — the ✦ "should I best-buddy?" overlay, mirroring the
  deep-dive L50-default / L51-overlay semantics.

## Pipeline (scripts/run_iv_guides.py orchestrates)

1. `scripts/iv_envelope_analysis.py --all-shields <species>` — sim stage,
   single-core, tens of min -> `userdata/dives/<slug>_iv_envelope_all9.json`.
2. `scripts/render_iv_envelope_article.py <json>` — fast HTML stage ->
   `userdata/website/articles/<slug>-ml-iv-guide/`.
3. `scripts/build_website_index.py` — re-index.

## Build steps

**A. Harvest (`iv_envelope_analysis.py`).** The named builds are already simmed
(`won_set` :140-159 vs the 60-opp pool x 9 shields x 4 quadrants; the headline
also runs `result_metrics` :162-187). Only the boolean `won` survives today; the
raw `r.pvpoke_score(0)` (the exact cmp value, centered on 500) is thrown away.
Add a `score_set()` (or widen `won_set`) to capture `int(score)` per
`(disp, sh)`; harvest the flat vector for the N named builds across the 4
quadrants (and energy via `result_metrics`, currently headline-only). Define a
`named_builds(rec_rows)` helper. Emit a new top-level `cmp_builds` block in the
analysis JSON (`data` :493-518): `{scenarios, opponentsDisplay, quadrants,
builds:[{label,ivs}], scores:{quadrant: flat uint list}, energy:{...},
energyMoves}`.

**B. Embed (`render_iv_envelope_article.py`).** New `SECTIONS` entry near
`checkmyivs` (:59). Lift the uint16 -> LE -> gzip(level9, mtime=0) -> base64 pack
(`deep_dive.py` ~5203-5220) and the `DecompressionStream` decoder (~5260-5284).
Emit `DATA.nOpponents/nScenarios/scenarios/opponentsDisplay`, packed
`SCORES`/`ENERGY` keyed so `cmpGrids().def -> nobb_vs_nonbb`,
`.alt -> wbb_vs_bb`, plus `DATA.movesets[0].energyMoves`.

**C. Share panels (`deep_dive_engine.js`).** Make `cmpFlipPanel`/`cmpMarginPanel`
(+ helpers `cmpVal`, `cmpHp`, `cmpScenLabel`, `cmpEnergyGrids`) reusable by the
guide. Guide supplies a fixed `live` from `cmp_builds.builds` and a `grids`
object ({def, alt, altCap}). No `cmpAdd` plumbing on the guide.

## Size

N=4 x 9 x 60 uint16 = 4.3 KB raw/quadrant; x4 ~ 17 KB raw -> ~2-4 KB gz/species
(scores cluster near 500). Energy ~doubles it. ~1000x smaller than a full grid.

## Open during build

- Exact attack/bulk pickers + build labels.
- Whether to expose all 4 quadrants or just the def/alt pair (size linear).
- Guide-side display will want Michael's iteration (the deep-dive energy line
  took several display passes).
