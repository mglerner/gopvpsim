# Changelog

Completed/shipped work, reverse chronological. **Not** part of the
session-startup read (see `CLAUDE.md`). Purely historical reference
for "when did we ship X" and "what was the root cause of that old
bug." Active pending work lives in `TODO.md`; still-relevant
invariants and PvPoke bugs live in `DEVELOPER_NOTES.md`.

## 2026-06-10 — Mirror-slayer redesign: archetypes + tie-explosion fix (perf+correctness arc S2)

Interactive design session with Michael; his four decisions: replace
the HTML section, fractional-wins + score-tiebreak round metric,
top-mirror cohort as the primary CMP denominator (Nash secondary),
retire the Atk/Bulk/CMP Slayer labels.

**Archetypes are now the first-class output.**
`build_slayer_archetypes` (deep_dive_slayer.py, replaces
`categorize_slayers`) classifies the FULL IV space, sim-free:

- **Anchors-First Slayer** — clear the max achievable number of
  counted anchor parents, then rank by Top-Mirror CMP% / atk.
  Explicit TOML parents always count; auto parents only when
  selective (<50% pass rate) — the slayer-card signal-loss fix.
- **CMP-First Slayer ("lab mon")** — top-N max-atk spreads with a
  clears-vs-sacrifices anchor checklist; no anchor required.

The Nash iteration is demoted to producing the mirror opponent
population: new `all_scores` export (dense per-IV mirror wins vs the
converged pool) feeds the archetype rows and makes the winsMirror
y-axis dense (4096 values vs ~30); the Nash cohort survives only as
the secondary "Nash CMP %" column (JS "Mirror Slayer CMP %"
unchanged). Top-Mirror CMP% computed Python-side with the same
semantics as the JS (2dp rounding, ties-as-beats, top-50 by avg
score, self included).

**Tie explosion fixed.** Round metric is graded — per-opponent credit
= scenarios won / scenarios counted (the Matchups Kept formulation,
`bb6f63e`), avg-score tiebreak; `_cut_pool` honors
`--mirror-slayer-pool` exactly except on exact metric ties. Smoke
measurement (Tinkaton GL, pool 30): Round 1 = 29 opponents × 2,978
profiles ≈ 86k sims vs the old 2,756 × 2,978 × 9 = 8.2M (~95× cut);
slayer phase 20.7s and no longer dominates the dive budget.

**HTML.** "Mirror Slayer Iteration" section replaced by "Slayer
Builds": two compact archetype tables (Anchors/CMP% columns, badge
walls with per-anchor tooltips, 100-row hard cap with an explicit
dropped-count note), iteration diagnostics collapsed, Level-3
sub-anchor distribution kept. Per-row `data-anchors` attributes and
the filter-panel JS/CSS deleted — the Jumpluff 60.7MB-table mechanism
is gone. Scatter star-diamonds, Notable IVs composites, and the
collection table now key off the two archetype names (plumbing was
name-agnostic). docs/concepts.md vocabulary updated.

Gates: 710 passed + 14 xfailed (sentinel 722→724; +3 new tests, −1
retired); engine files untouched so no bench/oracle rerun required.
Smoke HTML: /tmp scale, 2.97MB, tables capped, dense mirrorWinsByIv
confirmed.

Watch item for S6 re-dives: Tinkaton's Anchors-First cohort is broad
(1,349 IVs clear the max-cleared parent count) — ranking makes the
top rows meaningful, but if broad cohorts recur, consider requiring
all counted parents or tightening the selectivity gate.

## 2026-06-10 — Form-change plumbing in dive workers (perf+correctness arc S1)

The deep-dive sweep/slayer workers (and the phase-1 moveset screen)
constructed `BattlePokemon` directly from effective stats, so
`_form_change` was always None — every published Aegislash / Mimikyu /
Morpeko dive simmed those species without form mechanics, on both the
focal and opponent side. The engine itself was always correct (oracle
suite); the dive pipeline never opted in.

Fix: IVs + level are threaded through the sweep profile tuples,
`opp_cache` entries, and slayer opponent tuples; workers call the new
`gopvpsim.formchange.attach_form_change` (also the canonical path
inside `BattlePokemon.from_pokemon` now). Form-change species sweep
per-IV instead of per-stat-profile because alt-form stats depend on
raw IVs + level (Blade whole-level rounding) — measured cost 1.1-1.35x
more sims, confined to those species. Form-swapped move dicts are
copied rather than shared from the global gamemaster tables (a mirror
battle would otherwise cross-contaminate `_cached_damage` between the
two sides). Slayer disk-cache `CACHE_VERSION` bumped 1→2.

Verification: `tests/test_dive_worker_form_change.py` pins worker ==
`from_pokemon` equivalence (focal side, opponent side, slayer mirror)
and the PvPoke-harness-verified 773 cell. Smoke dive (Aegislash
(Shield) UL, 10 opponents): top-IV avg score 237.9 → 390.7, with
def-IV differentiation the no-form-change baseline couldn't see.
Gates: 708 passed + 14 xfailed; benchmark 2,254 sims/s (baseline
2,278, −1.1%); oracle harness 98 exact + 10 documented divergences.

Side finding: non-interactive `generate_html` crashes with a
`NameError` (pre-existing, unrelated) — logged in TODO under the
existing "non-interactive is strictly worse" item.

## 2026-06-07 — HTTPS on the website + Oinkologne NAIC re-dive

**HTTPS.** `mglerner.com/pogo-dives/` now serves over HTTPS via a free,
auto-renewing DreamHost Let's Encrypt cert (per-domain, so it covers
`/pogo-dives/` automatically) plus force-HTTPS. Confirmed in-browser: a
dive page loads over HTTPS with no mixed-content warnings and the Plotly
scatter renders. Mixed-content scan of the built `userdata/website/` tree
came back clean and required no generator change or republish: all 77
files containing `http://` are false positives (~5400 XML namespace
identifiers like `http://www.w3.org/2000/svg`, an ESRI attribution `<a>`
inside Plotly's unused basemap config, and a Plotly WebGL error string).
Grepping for real loads/links (`src="http://"` / `href="http://"`)
returns zero hits; Plotly is inlined at build time, not pulled from a CDN
at runtime. `publish_website.sh` is unaffected (rsync over SSH, not HTTP).

**Oinkologne NAIC re-dive.** Re-dived Oinkologne (Male + Female) GL
against the NAIC-meta cohort once PvPoke's rankings included it, and
published. Full reproducible procedure (cache invalidation, pool build,
re-dive, article refresh) is preserved in memory file
`project_oinkologne_naic_redive.md` for the next NAIC-style cycle.

## 2026-06-06 — Full oracle harness audit + Morpeko form-toggle (PvPoke bug #8)

**Oracle harness audit.** New `scripts/audit_oracle_harness.py` drives
all 12 hand-typed PvPoke-oracle matchups in `tests/test_battle.py` x 9
shield combos (108 cells) through both our sim and
`scripts/pvpoke_trace.js`, comparing score / winner / chargedLog. Result:
98 exact matches (confirming no hand-entry typo ever crept in), 6
documented Aegislash bug #3 divergence cells (intact), and 1 new finding
(Morpeko, below). Re-run anytime: `python scripts/audit_oracle_harness.py`.

**Morpeko form-toggle (PvPoke bug #8).** The audit flagged 4 Morpeko
cells whose chargedLog tagged a throw "Full Belly" where PvPoke said
"Hangry". Root cause: PvPoke implements Morpeko's `type: "toggle"` form
change as one-way (it sticks in Hangry after the first charged move),
whereas the real game toggles Full Belly <-> Hangry after every charged
move (Michael verified in-game: enters every battle in Full Belly at
start AND switch-in). Ours is the correct two-way toggle. Score-neutral
across this oracle, which is why the score-only test never caught it.
Kept per the CLAUDE.md divergence policy; pinned by a chargedLog
regression assertion on `test_morpeko_vs_azumarill_form_change` and a
known-divergence marker in the audit script. Full writeup in
DEVELOPER_NOTES.md §8.

## 2026-05-17 — Dropped UL Aegislash dives (mercuryish review, S2)

**What:** Removed every UL-Aegislash surface from the site:

- `userdata/website/aegislash-blade-ultra-league/`
- `userdata/website/aegislash-shield-ultra-league/`
- `userdata/website/comparisons/aegislash-blade-vs-shield-ul/`
- `userdata/website/articles/aegislash-form-change-guide-ul/`
- `comparisons/aegislash-blade-vs-shield-ul.toml` (source TOML)
- UL entries in `scripts/run_website_dives.py`,
  `scripts/write_aegislash_narrative.py`'s `LEAGUE_INFO`, and
  `scripts/overnight_redive.sh`'s UL render steps
- UL deep-dive / article comment references in
  `thresholds/aegislash_{shield,blade}.toml`

**Why:** Mercuryish flagged UL Aegislash as non-competitive in his
2026-04-26 review, with confirmation from his UL-player contacts.
Per the review: "I asked for second opinions from people who play
UL, and they agree that UL Aegislash is not real." We agreed —
keeping a stale-data UL surface live (where the simulation
produces numbers but the species itself isn't a live PvP option)
risks misleading readers who land on the page without context.

**Reversal cost if UL Aegislash becomes viable later:** small.
The deletion is purely site-state + scripted-config; the sim's
form-change mechanics (`src/gopvpsim/formchange.py`) still handle
Aegislash transformations in both leagues and there are no
correctness tests gated on UL Aegislash. To re-add: restore the
two `run_website_dives.py` entries, the `LEAGUE_INFO['ultra']`
block in `write_aegislash_narrative.py`, the two `overnight_redive.sh`
UL steps, and the `comparisons/aegislash-blade-vs-shield-ul.toml`
file from git history.

## 2026-04-23 — Slayer IVs "of yours" table: column-header tooltips

**Retrofit follow-up on the Mirror CMP reframe (2026-04-22).** The
Top IVs table's three mirror-adjacent columns already carried `title=`
hover text via the `help` field on `_summaryColumns()`. The Slayer IVs
"of yours" table rendered via `renderSection` extras had no equivalent,
so the same two columns (Top-Mirror CMP % and Matchups Kept) were
bare.

**What shipped:**

1. Three module-level `HELP_*` constants in `scripts/deep_dive_engine.js`
   (`HELP_MIRROR_SLAYER_CMP`, `HELP_TOP_MIRROR_CMP`,
   `HELP_MATCHUPS_KEPT`) so the Top IVs and Slayer IVs tables share
   one source of truth. The emitted HTML still inlines the full text
   per `title=` attribute, but the JS source no longer carries three
   copies of each string.
2. `renderSection` extras schema extended with an optional `help` field
   that renders as `<th title="...">`, matching the Top IVs pattern.
3. `scripts/patch_dive_slayer_help.py` — retrofit patcher, idempotent
   via `SLAYER_HELP_v1` fingerprint, partial-match safe. Applied
   in-place to all 41 shipped HTMLs under `userdata/website/*/` so
   the live site picks up the tooltip without re-diving.

Single commit: `c3edb14`.

## 2026-04-22 — Mirror CMP % semantic reframe + Highlight IVs scatter

**Arc trigger:** on Tinkaton UL the original "Mirror CMP %" column
wrapped `DATA.mirrorCohortAtk`, which collapsed to 160 entries all
at atk=142.8509983 (Nash converges on the 15/0/0 L50 atk corner).
Users sorting by CMP saw only the niche slayer-optimal build path,
not a general-purpose mirror target. Reframe splits the old column
into three semantically distinct metrics and adds a scatter
highlight tool for arbitrary IV lookup.

**What shipped (11 commits):**

1. `6dcc571` — Core reframe. Rename `Mirror CMP %` →
   `Mirror Slayer CMP %` (keeps the Nash-cohort semantic but labels
   it explicitly as niche). Add `Top-Mirror CMP %` column (cohort =
   top-50 same-species IVs by active battle score in THIS dive; IV
   counted in its own cohort so denominator stays at 50; returns a
   meaningful 0-100 spread). Add `Matchups Kept` column. Add
   "About these metrics" collapsible `<details>` box above the Top
   IVs table explaining all three metrics + the overfit-slayer
   tradeoff story + when-to-invest heuristic. Ships
   `DATA.mirrorOppIdxs` server-side so mirror-opponent identification
   handles shadow/form pools correctly.
2. `bd226f9` — Extend Slayer IVs "of yours" table with the two new
   columns. Adds `extras.cls` hint to the collection-matches table
   schema; wrap CSS tidy so Slayer type and Also in columns break
   cleanly without blowing column widths.
3. `32a1c9d` — Fix inert Show/Hide and sort buttons on
   collection-matches tables (pre-existing bug; handlers were
   IIFE-scoped and `window.*` registration was missing).
4. `a771c4e` — Scatter highlight-IVs feature. Text input below the
   plot; matching IVs render as red diamonds, other traces dim to
   ~30%. Handles two hover-routing gotchas: Y-nudge opposite to
   Yours overlays, and skip highlighted IVs from user-overlay ring
   traces (hollow circle-open hit detection routed cursors wrong).
5. `6c19e7f` — Collapse multi-mon `Yours (N)` hover block to one
   CP-list line. Was vertical-clipping the tooltip against the plot
   bottom edge for owned IVs with 2+ CSV records and full
   matchup-diff blocks. Single-mon IVs retain full detail.
6. `2b1af06` — Fix MaxListenersExceededWarning on legend handlers.
   Plotly's graphDiv is an EventEmitter that persists across
   `Plotly.react`; `gd.on()` was accumulating listeners every
   `updateView`. One-shot `_legendHandlersAttached` guard.
7. `02d9eba` — Shrink Yours-other / Yours-notable ring markers
   (size 9→6 / 13→9, opacity 0.9→0.7 on "other"). No hover/symbol/
   text changes.
8. `81db37d` — Move Highlight-IVs strip from top control strip to
   below the plot, right-aligned. Tightens the eye path from "I see
   a diamond I want to investigate" to "let me type a different IV."
9. `bb6f63e` — Matchups Kept: fractional expected-wins credit.
   Original "avg score >= 500" rule produced only 5 unique values
   across 4096 Tinkaton UL IVs; majority-of-scenarios still gave
   only 7. Final: per-opponent credit = `(scenarios won / nSel)`,
   summed across non-mirror opponents. Reduces to integer count for
   single-scenario mode; yields 70 unique 0.1-bins across 4096 IVs
   in the default avg-across-9 mode. Spot check confirms the metric
   now ranks 15/11/11 (rank 16) ahead of 15/14/8 (rank 161) —
   previously both tied at 31 with no signal.
10. `939162e` — Polish Matchups Kept About-box prose: drop
    implementation-footnote comparing fractional credit to thresholds;
    replace with a user-facing explanation of the fractional value.
11. `f9d760e` / `f5325e2` — added + reverted: attempted to add a
    `scripts/redive-shipped.sh` helper, but `scripts/overnight_redive.sh`
    + `scripts/run_website_dives.py` already do that work (plus article
    regen, comparison rebuild, link verify). Use the existing chain
    instead.

**Re-dive validation:** full overnight chain 2026-04-22 evening
exercised every shipped dive against the new JS; 12 dives + 2
Aegislash auto-articles + Oink CD article + comparison pages +
link-verify in ~8h.

## 2026-04-21 — S11 + S12: HTML dive file-size reduction (~40%)

**Motivation:** pre-ship, the Oinkologne GL m1 dive was 46 MB
uncompressed; the Oink files became actively annoying to open in a
browser or diff. Originally scoped as post-ship in the post-S5 arc
(S11-S12), fast-tracked when the file size crossed the
annoying-to-use threshold.

**What shipped (4 commits):**

1. `f839e65` — S11: audit + measurement harness. `docs/s11_html_size_audit.md`
   is the byte budget writeup: 87k `title=` attributes on anchor
   badges collapse to 1.6k unique values (18 MB of pure duplication
   on Oinkologne). Six ranked reduction approaches, recommendation
   narrows to R1 (tooltip dedup) + R2 (external shared plotly).
   `scripts/measure_html_size.py` reports uncompressed + gzip-6 +
   title-dedup projection + plotly inline bytes per file for
   before/after diffs.
2. `1fe232a` — S12-R1: dedup `title=` tooltips. Unique tooltip bodies
   get emitted once into `DATA.tooltips`; each inline `title=` becomes
   `data-t="<short-id>"`. A `DOMContentLoaded` pass walks `[data-t]`
   elements and populates `el.title` from the lookup; browsers show
   the native tooltip on hover, no custom positioning. A/B on a
   scale-matched 10-opp/1-moveset Oinkologne dive: 38.12 MB →
   26.07 MB (-31.6% uncompressed, -99.98% of `title=` bytes).
3. `5ad2d4b` — S12-R2: `--shared-plotly DIR` flag. Third mode of
   `_plotly_script_tag()`; plotly.min.js is downloaded to DIR once
   (idempotent) and each dive emits a relative `<script src=...>`
   referencing it instead of inlining the 4.35 MB source. Overrides
   `--standalone` for plotly specifically. A/B on the same dive:
   R1 + R2 = 21.72 MB uncompressed / 6.09 MB gzip (-43.0% / -40.5%
   vs baseline). Hits the S12 target.
4. `e2e0737` — TODO.md housekeeping, closes the HTML file-size entry.

**Full-scale validation:** projection on the real 46 MB Oinkologne m1
dive is ~27.9 MB (-39.4%). Verified by the next overnight re-dive.

**Precedent:** prior HTML size cut (25 MB → 10 MB, 61%) landed
2026-04-10 as commit `cab0a72` (cap member-IV tables at 50 rows).
S11/S12 is the second cut, orthogonal to that one (targets the
title-attribute and plotly-inline tail).

## 2026-04-19 — Shape 2 migration: dive-side species narrative

**Arc trigger:** pre-Oinkologne-ship decision (2026-04-19) that the
primary narrative home for a species is the **dive**
(RyanSwag-style), not the CD article. Articles continue to exist
when they do something the dive can't — disambiguating multiple
forms (Oinkologne M/F, Aegislash Blade/Shield), shadow variants, or
alt-moveset meta forks (Forretress Volt Switch vs Bug Bite). For
Oinkologne the CD article stays because M/F comparison is its
justification, but the `[intro] / [meta_role] / [verdict]` prose
now lives per-form in the threshold TOML and renders at the top of
each dive.

**3-session arc (all shipped 2026-04-19):**

1. `41bbe6f` — Session 1: renderer plumbing + per-block `author`
   attribution schema. Pure code, zero content migration. Design
   decisions:
   - Render position: above the interactive dashboard (after the
     Related Article link, before the controls bar).
   - TOML schema: new top-level `[Species.intro] /
     [Species.meta_role] / [Species.verdict]` blocks in
     `thresholds/<species>.toml` — field-for-field mirrors of
     `articles/*.toml`'s same-named blocks so prose migrates
     by copy-paste.
   - Renderer: `deep_dive_rendering.render_species_narrative()`
     alongside the existing gold-zone code.
   - Author attribution: optional `author = "..."` field per block,
     rendered as a muted italic line; reader-visible distinction
     between AI-drafted and human-written prose.
2. `bf05538` — Session 2: per-form Oinkologne M/F narrative authored
   in `thresholds/oinkologne.toml` and
   `thresholds/oinkologne_female.toml`; article
   `[intro] / [meta_role] / [verdict]` slimmed to CD-event scope.
   Every Claude-drafted block carries
   `author = "Drafted by Claude (Opus 4.7), not yet human-reviewed"`.
   Overnight re-dive bakes the narrative into the regenerated
   Oinkologne dive HTMLs.
3. `bb021fa` — Session 3: Aegislash Blade + Shield narrative authored
   in `thresholds/aegislash_blade.toml` and
   `thresholds/aegislash_shield.toml` (Shield = canonical realistic
   play pattern; Blade = always-Blade diagnostic hypothetical).
   Out-of-band GL dives against the Orlando top-32 pool landed the
   same day (Blade 14:37, Shield 15:41); HTMLs force-patched with
   the narrative injection. Aegislash UL pair runs in the overnight
   chain and picks up the narrative natively. Stress-tests the
   renderer against mid-battle form/moveset swaps.

**Same-day polish:**

- `670f57b` — Per-block `authored_by` colour coding. Gold =
  expert-authored, muted = AI-drafted.
- `464e04a` — Unify all sidebar CSS on one rounded-pseudo-element
  pattern (cleanup that made the new narrative block visually
  consistent with the gold Expert Analysis zone).

**Documentation:** `docs/article_schema.md` "Per-block author
attribution" and `docs/threshold_schema.md` "Species narrative"
carry the full schema.

## 2026-04-18 — S10: Oinkologne CD article + Male-vs-Female comparator

**Ship session for the post-S5 Oinkologne arc.** Wires the Female dive
data into the CD article, adds a Male-vs-Female form-comparison
section, extends the site index, verifies bidirectional links, and
deletes the archived Lechonk CD prep plan.

**What shipped:**

1. `scripts/compare_loadouts.py` — MVP pairwise loadout comparator.
   Loadout-list-keyed data model (`loadouts: list[LoadoutSpec]`,
   pairwise deltas via `itertools.combinations`) so N=3 / N=4 are a
   renderer extension rather than a rewrite. MVP ships N=2 only.
   Output: `userdata/website/comparisons/<slug>/index.html` plus an
   importable `build_comparison_fragment()` that `generate_article.py`
   inlines.
2. `comparisons/oinkologne-male-vs-female.toml` — comparator spec for
   the Oinkologne CD arc.
3. `generate_article.py` — new canonical `form-comparison` section
   between Matchup Delta and IV Recommendations, gated on a
   `[form_comparison]` block in the article TOML. Absent the block the
   section drops out cleanly.
4. Site-index updated with both Oinkologne dives, the article, and
   the comparison page. (Site index at `userdata/website/index.html`
   is gitignored, so the edit is local-only by design.)

**Reconciliation vs `~/.claude/plans/archive/lechonk-cd-prep.md`:**

The archived Lechonk plan scoped six sessions targeting a JRE-style
prose article by 2026-04-22. The actual ship happened through the
post-S5 Oinkologne arc (S1-S10), with three documented scope shifts:

- **JRE-style prose → Python-generated spec sheet.** Rationale: JRE
  writes for money; shipping Claude prose mimicking his voice is not
  acceptable. Tracked in TODO.md "CD article generator" (2026-04-16).
- **One dive → Male + Female dives.** Oinkologne forms have
  meaningfully different base stats (186/153/242 vs 169/162/251);
  both receive Mud Slap on the same CD, so both need threshold data.
  Tracked in memory `project_female_oinkologne.md`.
- **No comparator → compare_loadouts.py MVP.** Added this session to
  make the Male-vs-Female section a reusable tool rather than inline
  article code. Tracked in memory `project_ab_comparator_timing.md`
  and TODO.md "Moveset / variant comparison tool".

Aegislash form-change dive (floating beat in the old plan) remains
pending under TODO.md "SwagTips narrative follow-ups".

Archived plan deleted post-reconciliation.

## 2026-04-15 — Forretress/Azumarill DP plan-selection (atk-stage fix)

**Context:** our Azu vs Forr (Sand+Rock) score matrix diverged from
PvPoke by up to +118 rating points, despite our DP tracking
`has_debuf`/`debuf_count` for dedup tie-breaks. Investigated with the
new headless Node harness (`scripts/pvpoke_trace.js`) which emits a
`termLog` of every DP terminal pushed.

**Root cause.** PvPoke's `BattleState` carries a `buffs` field (the
attacker's atk-stage delta) that accumulates as the DP stacks moves
with chance-1 self-atk buffs *or* chance-1 opp-def debuffs. See
`ActionLogic.js:519-535` — line 531 `attackMult -= move.buffs[1]`
effectively promotes an opp-def debuff to a self-atk buff inside
the DP. When a child state is popped, line 471 calls
`poke.applyStatBuffs([buffs, 0])` and recomputes
`moveDamage`/`fastSimulatedDamage` against the buffed atk. Our
`_DPState` held `cm_dmgs[]` and `fast_damage` fixed at root-state
values for the *entire* DP rollout, so stacked-ST plans never
accelerated and never terminated in our reachable-state space — our
DP accepted `[RT]+farm` at turn 13 instead of PvPoke's
`[SAND_TOMB, SAND_TOMB]` at stateTurn 10.

**Fix.** `_DPState` now carries an `atk_stage` field; `pvpoke_dp`
precomputes a per-stage damage table (9 rows, stage ∈ [-4..+4]) and
each child state indexes its own row for charged- and fast-move
damage. `cm_buff_delta[n]` = +1 for chance-1 self-atk-buff or
chance-1 opp-def-debuff and bumps `new_atk_stage` on throw (clamped
to [-4, +4]). `_dp_insert_ready` phase-1 dedup now requires equal
`atk_stage` so stacked-buff plans aren't merged away. `_dp_jit.py`
mirrors the change — kernel takes `cm_buff_delta`, `cm_dmgs_stage`
(9 x n_cms), `fast_dmg_stage` (9,), `root_atk_stage`, and the queue
arrays gain a parallel `q_atk_stg` slot.

**Scoreboard.** Azu/Forretress (Sand+Rock) now matches PvPoke 9/9
exact across all shield scenarios. 157 pytest + 27/27
`verify_pvpoke_harness.py` still green. Commit `141eee1`.

**Gotcha.** Raw gamemaster `buffApplyChance` is a *string*, not a
number. The initial `!= 1` comparison was silently false for every
move; the production check is
`float(m.get('buffApplyChance', 0) or 0) != 1.0`.

## 2026-04-14 — Form Change

Data-driven via gamemaster `formChange` field. Three form-change
families implemented:
* **Morpeko** — toggles Aura Wheel between Electric and Dark.
* **Aegislash** — Shield ↔ Blade swap (stats, moveset, level
  adjust).
* **Mimikyu** — disguise effect absorbs first unshielded hit; on
  break, applies -1 def stage.

Form changes DO affect opponent shielding (Aegislash Shield form
suppresses shields when damage < half HP) and baiting (Mimikyu
opponents break disguise ASAP with the cheapest charged move).

Oracle tests: Morpeko 6/9, Aegislash 1/9, Mimikyu 6/9 match PvPoke
exactly. Remaining mismatches were initially attributed to a "DP
cycle-timing" gap; that lead was subsequently closed 2026-04-15
(Azu vs Aegislash 0v0 now throws IB twice, matching PvPoke; all
9 0v0 form-change fixtures land on harness score). Plan file:
`quizzical-hatching-kahan.md`.

**Open follow-ups** (tracked in `TODO.md`): Mimikyu deep dive with
form-change narrative; Goodra / Aegislash test-drive dives for the
new SwagTips narrative renderer.

## 2026-04-14 — PvPoke divergence RESOLVED: selfBuffing flag scope

Our `selfBuffing` flag in `moves.py` now matches PvPoke's
`GameMaster.js:873` definition: guaranteed positive self-buffs AND
guaranteed opponent debuffs (`buffTarget="opponent"`,
`buffApplyChance==1`). Previously only covered self-targeting buffs;
workarounds in shield policy and bait-wait were removed. All 8
`selfBuffing` usage sites now use the broadened flag consistently.

## 2026-04-14 — PvPoke divergence RESOLVED: activeChargedMoves priority-shuffle

PvPoke's `resetMoves` (`Pokemon.js:711-787`) reorders
`activeChargedMoves` after the energy sort based on buff/debuff
properties. The priority-shuffle uses buff-adjusted DPE
(`initializeMove`, `Pokemon.js:849-864`) for one clause. Our code
now replicates all shuffle clauses in `pvpoke_dp`.

**Historical note (corrected):** Divergence 2 was originally
documented as "bait-wait DPE ratio uses `actual_dpe`, not
buff-adjusted DPE." This was incorrect. PvPoke's
`selectBestChargedMove` (`Pokemon.js:791-796`) *overwrites* `.dpe`
to raw `damage/energy` on all `activeChargedMoves` after the
priority-shuffle, so the bait-wait 1.5 ratio check
(`ActionLogic.js:843`) also uses raw `damage/energy`, same as our
`actual_dpe`. The buff-adjusted DPE only affects the
priority-shuffle ordering (lines 711-787), not the ratio check
itself. This paragraph is load-bearing — if you ever revisit
Divergence 2, it will explain why the "obvious" fix wasn't needed.

## 2026-04-09/10 — Stat-target reframing (SwagTips round 1)

Threshold Tier cards, matchup-flipping boundaries, HP co-conditions,
auto-derive from clean dives, scatter plot visual overhaul, HTML size
reduction. 26 commits. Key design decisions:

### Two kinds of threshold
- **Damage-tier boundaries** (from `_aggregate_flips_by_anchor`): the
  def/atk at which `floor(damage_formula)` steps by 1. Invariant to
  battle conditions (energy leads, bait policies). Come from Level 3
  anchor discovery.
- **Matchup-flipping boundaries** (from `_find_matchup_boundaries`):
  the def (+HP) at which the overall battle outcome flips win→loss.
  Usually higher than the damage tier because multiple damage reductions
  must accumulate. Depend on battle conditions — will shift when we add
  energy-lead sims. Both are shown: damage tiers in anchor-flip bullets,
  matchup boundaries in their own section + tier cards.

### Auto-derive path (no TOML needed)
`_auto_derive_tiers` consumes both anchor-flip records (atk-side) and
matchup boundaries (def-side). Tiers ranked by selectivity (fewest
qualifying IVs first); General excluded from scatter plot coloring.
Tinkaton clean dive produces tiers at ~143 def (≈acidicArisen GH Great),
~140 def (≈GH Good), ~138 def (intermediate). Validated against 4/6
acidicArisen findings.

### Open threads for next sessions
- **Atk-side matchup-flipping boundaries**: `_find_matchup_boundaries`
  currently only sweeps def. Should also sweep atk for species where
  atk breakpoints flip matchups (e.g. Annihilape Lickitung BP at 127).
  Same algorithm, different partition stat.
- **Energy-lead matchup boundaries**: damage tiers don't change with
  energy leads, but matchup boundaries do. Once we add energy-lead sim
  options (`--energy-lead 1` etc.), re-sweep matchup boundaries under
  those conditions. The two-layer display (damage tier + matchup flip)
  is designed for this.
- **Shadow / atk-weighted opponent IVs**: acidicArisen's Shadow Drapion
  (140.21 def) uses "attack-weighted" opponent IVs, not rank-1 or
  PvPoke default. Our system doesn't simulate arbitrary opponent IV
  spreads. Possible fix: `--opp-ivs custom:119.80` in the TOML or CLI.
- **HP co-condition on atk-side**: currently only def anchors try HP
  co-conditions. Atk-side anchors theoretically could too (HP affects
  whether a fast-move damage increase translates to a KO), but no
  known case warrants it yet.
- **CMP anchor schema shorthand**: acidicArisen's CMP thresholds
  (105.58 Corviknight, 105.79 Lickilicky, etc.) can't be expressed as
  CMP anchors without an IV-list spread. Need a `opponent_species`
  shorthand that resolves the opponent's rank-1 atk automatically.
  Listed in "Schema simplification" TODO.
- **HTML size**: down from 25 MB to 10 MB (base64 uint16 scores +
  Notable IVs member cap). Remaining 9 MB is packed scores. Further:
  delta-encode, drop non-displayed moveset scores, or serve gzipped.
- **deep_dive.py refactor**: now ~6000 lines. The extraction targets
  in the Refactoring TODO are still valid; this session added
  `_find_matchup_boundaries`, `_auto_derive_tiers` (matchup boundary
  path), `_probe_tier_cutoff_flips`, `_render_matchup_boundary_bullets`
  as new extraction candidates for `deep_dive_lib/boundaries.py`.

## 2026-04-09 — Structured IV categories (round 1)

Unified `IVCategory` framework abstracting over slayer categories,
threshold tiers, and their intersections. New "Notable IVs" HTML
section surfaces composite (slayer ∩ tier) cards and matchup
(opponent, scenario) cards with auto-generated tradeoff prose.
Annihilape `13/0/11` lands as the canonical example: "The sole Atk
Slayer that also clears the Top 5% threshold (hp≥139). Trades mirror
dominance (45/132 wins, vs 132/132 for the top Atk Slayer survivors)
for the Top 5% cutoff." Section is gated behind a "show only notable"
header checkbox (≤ 5% of cohort or ≤ 5 members, default on). Round 1
ships zero TOML changes — composite + matchup categories are
auto-derived from existing infrastructure. Bait dimension on
`matchup_conditions` is reserved (`None`) until the bait-axis sweep
TODO lands. Commits: `f3aa4ad` (dataclass + builder), `8ff4469`
(matchup branch), `79e2e87` (renderer), `b344356` (wire-in). Cross-ref:
"Hand-named composite categories via TOML" and "Bait-axis matchup
categories" in Deep-dive narrative for round 2 followups.

## 2026-04-08 / 2026-04-09 — Bulkpoint anchor system

Def-side mirror of `damage_breakpoint` anchors. Three precision levels
(L1 explicit, L2 reference-anchored via `above_def`, L3 discover-and-tag),
parser, resolver, auto-fallback, tests, docs, Annihilape TOML entries.
Bulk Slayer category gained dual membership (structural HP+def OR
clears at least one named bulkpoint). `ResolvedAnchor` generalized to
`target_stat` with `threshold_value` so the same passes() machinery
handles both atk and def side. Commits: `13665dc` (main feature +
brkp/blkp rename + tag UX + CLI args embed — should have been split,
see commit message), `8f9369d` (clarify ×N count in hover tooltip),
`7ed5765` + `967bb09` (Compact/Expand toggle for tag cells).

**Headline finding** from running the new system on Annihilape
explicit: the historical Lurgan Ape `def ≥ 102.9` floor is *not*
recoverable as a single (move, tier) bulkpoint. The next bulkpoint
above 102.9 is `shadow_ball ≤149` at def 103.34, but 0/66 of today's
converged cohort can reach it (max cohort def ~101.30). The 102.9
floor predates Rage Fist, so the threat-move set has shifted; today's
optimization trades def for atk and lands well below the historical
baseline. Don't promote anything to Level 1 from this enumeration —
follow up via Discord with acidicArisen to recover historical context
(see "Send acidicArisen a Discord message" in Analysis goals).

## 2026-04-08 — bp → brkp short-name rename

Renamed all anchor name slugs from `_bp_` to `_brkp_` so the
breakpoint short form is unambiguous against the new bulkpoint
`_blkp_` short form. The Python kind discriminator stays
`damage_breakpoint` (full word); only the slug-style short forms
changed. Touched anchors.py, build_auto_anchors, annihilape.toml
anchor table keys, tests, and docs. Part of commit `13665dc`.

## 2026-04-08 — Ultra-short anchor abbreviations + Compact tags toggle

Tag cells in slayer cards previously truncated badges horizontally
with `text-overflow: ellipsis` at 280px max-width, hiding most of
the badges past the first 2-3. Replaced with: (a) `derive_short_name`
function producing 3-6 char badge labels (cre, lic, mirb, lic↑lur,
c:lur, quasb...) with the long form preserved in the badge hover
tooltip, (b) cell wrapping enabled, max-width bumped to 480px,
(c) Compact/Expand toggle button at the top of the slayer card grid
that caps cells at ~2 lines via an inner `<div>` wrapper (the wrapper
is needed because `<td>` ignores `max-height` in CSS — fixed in
`967bb09` after the first attempt at the toggle didn't actually work).
Part of commit `13665dc` + the three follow-ups.

## 2026-04-08 — CLI args embedded in HTML output for forensics

`format_cli_args(args, parser)` builds the *fully-resolved* equivalent
invocation: every flag emitted with its actual value, including flags
whose value happens to equal the current parser default. Embedded in
HTML two places: a grep-able `<!-- CLI: ... -->` comment near the top
and a collapsed `<details>` footer at the bottom of `<body>`. Also
printed to console at startup as `CLI: ...`. Why fully-resolved
instead of literal user input: defaults can change between runs, so
a string that omits "default" flags becomes ambiguous when read later.
This is the forensic gold standard. Part of commit `13665dc`.

## 2026-04-08 — Slayer anchor system

The TOML threshold schema (`docs/threshold_schema.md`), anchor
resolver (`gopvpsim/anchors.py`), and anchor-tagged
`categorize_slayers` are all in place. Atk Slayer and CMP Slayer use
named anchors instead of vacuous median heuristics. Three precision
levels for damage_breakpoint anchors (L1 explicit, L2
reference-anchored, L3 discover-and-tag). Auto-fallback layer
synthesizes anchors at runtime when the user doesn't provide them
via TOML, gated per kind so explicit user input always wins. Commits
`beace47` (main) and `10a693c` (acidicArisen testimony incorporated
into thresholds/annihilape.toml + anchors tests).

## 2026-04-07 — Battle simulator perf optimization (round 1 + round 2 + chunking)

Real-world impact: ~9hr → ~6 min on a full Annihilape mirror slayer
deep dive workload. Stack of optimizations:
* Damage cache + DP hoisting — +51% throughput (commit `3596fb4`)
* Numba JIT on the near-KO DP loop — +40% throughput (commit `a57c39f`)
* Stat profile dedup in `iv_sweep` — ~1.7x faster Phase 2 (commit `6ccb124`)
* Slayer iteration: dedup focal & opponent IVs by effective stats
  (commit `579aef7`)
* Slayer iteration: keep all IVs tied at top win count (commit `eb145a2`)
* Chunk count bumped from `n_workers` to ~100 for finer progress
  reporting (commit `8498ec4`)

Round 3 (numba JIT for the entire inner sim loop) was deprioritized
after round 1+2 made the workload tolerable; fastmath was confirmed
a dead-end during the round 1 work.

## 2026-04-07 — Iterative slayer discovery (Nash-style mirror match)

`scripts/deep_dive.py --mirror-slayer` runs Round 0 (focal IVs vs
PvPoke default opponent) then iterates Round k (focal IVs vs round
k-1's top survivors), stopping on convergence or `--mirror-slayer-rounds`.
Survivors are classified into RyanSwag-style Atk Slayer / Bulk Slayer
/ CMP Slayer categories. Disk cache at
`~/.cache/gopvpsim/slayer/<key>.pkl` keyed on species/league/shadow/
moves/scenarios so re-runs are near-instant. Commits `43b8784` (main),
`75fa8ce` (HTML rendering), `9cabba7` (cache key fix), `3b9d5fb`
(metric/rounds/pool/show CLI flags), `0dfcc98` (validation doc).

## 2026-04-06 — IV deep dive script + interactive HTML

`scripts/deep_dive.py` simulates all 4096 IV spreads of a focal
species against meta opponents across moveset combinations, with
threshold-tier coloring, custom group support, and an interactive
HTML mode (`--interactive`) with moveset/scenario/opp-IV switching
dropdowns. Commits `f0253d5` (script), `a4d18e5` (interactive mode),
`30452c6` (PvPoke default IVs for opponents), `4c7bcf9` (legend
isolation, matchup hover), `6924b1a` (`--standalone` inline Plotly).
Doc reorganization in `0ce1229` (CLAUDE.md, TODO.md, DEVELOPER_NOTES.md).

## 2026-04-04 to 2026-04-06 — Battle simulator correctness (Mienfoo vs Medicham)

Several rounds of bug fixing brought the battle simulator into
agreement with PvPoke's reference output:
* Three turn-model bugs: 1-turn FM timing, faintSource, FM fire order
  (commit `e036670`)
* Buff/debuff implementation (commit `6145aaa`)
* Buff meter, pvpoke_simulate_shield, trace flags (commit `ead46c1`)
* ActionLogic.js post-DP bandaids, sort cms by energy, raw_dpe
  (commit `f4d0eb3`)
* DP queue insertion strategies, intended_pruning flag (commit `44f3215`)
* Shadow Pokemon support (commit `8c5fb65`)
* `wouldShield` buff reset ordering, CMP cancellation (commit `5b07790`)
* All 9 Medicham vs Azumarill scenarios match PvPoke (commit `008d8e7`)

### Mienfoo vs Medicham — FIXED (all 9/9), root cause

Two bugs specifically responsible for the Mienfoo vs Medicham all-9
pass:

1. **wouldShield buff reset ordering** (battle.py `would_shield`):
   The charged-move threat loop ran BEFORE resetting the temporarily-
   applied stat buffs, inflating damage predictions. PvPoke resets
   buffs first (ActionLogic.js:1136-1140), then evaluates charged-move
   threat (lines 1145-1165). Fix: moved the reset before the loop.

2. **CMP (Charge Move Priority) cancellation** (battle.py `simulate`):
   When both Pokemon fire charged moves simultaneously, the lower-ATK
   Pokemon's move should be canceled if it was KO'd by the higher-ATK
   Pokemon's charged move (PvPoke Battle.js:464-467). Our code had an
   exception that always allowed both to fire. Fix: track `charged_ko`
   set and cancel if `use_priority` and attacker was KO'd by a charged
   move.

## 2026-04-01 — pvpoke_dp charged-move policy

Implemented PvPoke's `ActionLogic.js` DP-based charged-move decision
policy in Python (`gopvpsim.battle.pvpoke_dp`). Commit `62b9cfb`.

---

# Resolved (deeper history)

* **Slayer Ape / Lurgan Ape IV analysis** — Resolved 2026-04-08 by
  acidicArisen Discord testimony. The community Lurgan Ape spread is a
  *historical floor* (`atk ≥ 127.2`, `def ≥ 102.9`) calibrated to a
  Lickitung breakpoint near atk 127.23, predating the Counter nerf,
  Rage Fist addition, and Low Kick buff. Our slayer iteration's
  convergence to atk 129.44 matches *current* expert advice (push
  higher than the Lurgan baseline for CMP wins and BP security against
  the mirror and Lickitung). The "we disagree with the community"
  framing in earlier analysis was wrong — we converge to current
  expert practice; Lurgan is a frozen historical reference.
