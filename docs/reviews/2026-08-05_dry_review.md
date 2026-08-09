# DRY / Single-Sourcing Review -- 2026-08-05

> **Status (2026-08-05, same day):** entries 1-3 SHIPPED, commits
> `d81c4ad..1db4f65` (entry 1: all five wrong-output fixes; entry 2: the
> gender+min-level evolution walk; entry 3: all five ops/gate items),
> each with regression tests -- suite 1322 passed. Entry-1 render fixes
> live in the generators; shipped HTML updates on the next re-render.
>
> **Final status (2026-08-08): THE REVIEW IS FULLY EXECUTED.** Entries
> 12+13 shipped with the v8 cold bake 2026-08-06/08 (CHANGELOG); the
> entry-15 fold-ins and every recorded per-entry deferral were cleared
> by the 2026-08-08 AFK churn (28 commits, 41-agent workflow, CHANGELOG
> "AFK deferral churn"), including the plotly theme shim -- Michael
> reviewed the rendered previews and signed it off as-is 2026-08-08
> (aliasing recorded as an accepted decision, palette_governance.md
> section 6). Every render-side change reached pogodives.com via the
> 2026-08-08 evening re-render + publish (CHANGELOG). Suite over the
> full arc: 1290 -> 1719 tests. Nothing in this document remains
> unactioned or undispositioned.
>
> **Status update (2026-08-05, evening): entries 4-11 + 14 + the two
> entry-12 "safe-any-time" cherries SHIPPED**, commits
> `caeded9..7e66ba2` (12 commits; 30-agent lane-partitioned workflow,
> 2 adversarial verifiers per entry, 3 must-fix findings caught and
> fixed in-flight). Suite 1514 passed / 14 xfailed (+192 tests today);
> ship gates green; engine-hash files verified untouched. STILL OPEN:
> entry 12 proper (deep_dive.py split; CACHE_VERSION cold) and entry 13
> (engine DRY batch) -- both scheduled against the next bake window --
> plus entry 15's fold-in-when-touching items and the per-entry
> deferrals recorded in the implementing commits. Read the rest as a
> point-in-time snapshot.
>
> **Corrections from the same-day human re-audits** (three claims did
> not survive re-verification -- two from the review's agents, one from
> the first re-audit round itself; the fixes stand in all cases):
> (1) The entry-1 Annihilape 0/9/14 "reproduced" example is WRONG as an
> end-to-end tier flip -- its def arithmetic is exact (102.998235 vs
> 103.0), but every Annihilape tier also carries an atk requirement
> that 0/9/14 fails at either precision, and no Annihilape dive page
> was ever shipped. The verifier reproduced the def comparison only.
> (2) The first re-audit round then estimated "48 of 94 shipped dives,
> 2328 flipped spreads" from a replay-blob sweep -- ALSO WRONG: the
> sweep classified against blob['thresholds'], a legacy rounded-cutoff
> structure the page tier system does not use (pages tier on
> anchor-derived FULL-PRECISION cutoffs). The superseding measurement,
> taken after the 2026-08-05 re-render: a direct DATA.ivTiers diff of
> all 97 shipped pages, old live vs new local -- ZERO tier-assignment
> changes. The tier-precision fix is consistency hardening (bake now
> matches the paste-box scanner's semantics; boundary tests pin it),
> with no visible effect on any currently-shipped page.
> (3) The entry-1 "9 of the top-80 meta species" rank-1 count measures
> 7 on a full re-run (Corsola (Galarian), Umbreon, Medicham,
> Talonflame, Mantine, Talonflame (Shadow), Aegislash (Blade)); every
> species the review NAMED is confirmed divergent.

**Date:** 2026-08-05
**Method:** 9 Opus finder agents swept the June S7 DRY register plus the post-June surface (July cup work, matchup-cluster section, the Python<->JS render boundary, ops/cache tooling). 3 adversarial Opus verifiers re-read every cited site at HEAD, re-ran the live reproductions, and issued verdicts with corrections. This document is the Fable synthesis pass over the verified set.
**How to read:** Section "Ranked do-this list" is the deliverable -- a prioritized work plan, not a register. Entries are ranked by (drift-damage risk x fix cheapness) and grouped into bundles where the fixes share a session. Scope: S = under ~1h / one-or-two files; M = multi-file, one session; L = dedicated session. Two tags are rendered loudly where true: **[ENGINE-HASH]** (fix touches an `_ENGINE_FILES` member -> hash bump -> sweep-cache cold unless migrated) and **[CROSS-REPO: gobattlekit]** (touches the surface `../gobattlekit` consumes).
**Ranking rule for engine-hash items (Michael, 2026-08-05):** engine-hash impact is a BATCHING signal, not a demotion. All confirmed engine-file-touching fixes are collected into one "engine DRY batch" bundle (entry 13) that rides a single cold re-dive, scheduled against the next natural bake.

## Executive summary

62 verified findings; 61 confirmed, 1 intentional, 0 fully gone. Six findings arrived as duplicate pairs (same defect found from two angles) and are merged in the ranked list, leaving **56 distinct defects**. Six specific sub-claims inside otherwise-confirmed findings were refuted by verifiers and are listed under "Do NOT do".

| Axis      | Breakdown                                      |
| --------- | ---------------------------------------------- |
| Verdict   | confirmed 61, intentional 1, refuted 0, gone 0 |
| Kind      | register (June) 20, new (post-June) 42         |
| Status    | present 57, partial 5, gone 0                  |
| Fix scope | S 33, M 26, L 3                                |
| Flags     | [ENGINE-HASH] 3, [CROSS-REPO: gobattlekit] 4   |

Merged duplicate pairs: scenario-label (mc-scenario-label-key + js-py-scenario-label-formats), pvpoke URL skeleton (pvpoke-battle-url-skeleton-triplicated + js-py-pvpoke-battle-url-skeleton), score-key (score-key-parity-py-js + js-py-score-key-shape), WIN_RATING (mc-win-rating-redeclared + js-py-win-rating-500), league CP caps (league-cp-map-two-new-copies + js-py-league-cp-caps), level ceilings (l51-league-ceiling-default + js-py-level-ceilings).

## Ranked do-this list

### 1. Live wrong-output fixes (bundle) -- five S fixes; ships with a re-render, no re-sim

Every item here is wrongness visible on a shipped page or in a tool's answer TODAY. Cheapest damage-stopping work in the review.

- **R11 color hash:** add `.lower()` to the md5 input at `scripts/deep_dive_narrative.py:983` (one character). The same opponent currently renders in two hues on one page (shipped Azumarill page: Altaria is `--opp-3` in tables, `--opp-10` in narrative). Do NOT wait for the deep_dive split.
- **js-parity-1 tier precision:** classify tier membership on the unrounded `meta[5]/meta[6]` in `scripts/deep_dive.py:4205-4221` (keep the rounded arrays for display only). Fixes the shipped contradiction where the bake colors an IV as a tier member but the page's own paste-box scanner rejects it (reproduced: Annihilape 0/9/14, def 102.9982 vs threshold 103.0). Fix the deep_dive.py side, NOT user_collection rounding -- that alternative is cross-repo.
- **js-parity-2 mirror CMP:** extract an `_atkBeats(a, b)` 2dp-round/ties-count helper in `scripts/deep_dive_engine.js` and call it from `cmpMirror` (:3505), `_computeMirrorCmpPct` (:2603), and the Top-Mirror block (:2618). Ends "Mirror CMP 100%" and "Loses mirror CMP" for the same IV on one page.
- **owned-breakdown rank-1:** delete `rank1_spread` (`scripts/owned_breakdown.py:95-111`) and take `iv_rank(...)[0]` from `src/gopvpsim/pokemon.py` (read-only import, no engine edit). The hand-rolled copy uses the opposite tie-break and misses the Aegislash rounding; 9 of the top-80 meta species disagree today, so the CLI contradicts the website column and the gobattlekit bundle it is documented to match.
- **js-parity-5 honest-claim fix (minimal half):** correct `scripts/owned_breakdown.py:13-14` -- the website JS does not reproduce its numbers and no gobattlekit implementation exists; say what each surface actually measures. (Per the never-present-known-wrong rule.) Reconciling the three "Gives up vs #1" metrics / disambiguating the two identical column labels is the M-sized follow-on.

### 2. Gender-blind evolution walk (collection-evo-walk-gender-blind) -- M **[CROSS-REPO: gobattlekit]**

Highest correctness severity in the batch: `bottle_cap_advisor.collect_owned` (`scripts/bottle_cap_advisor.py:85-94`) and `scripts/owned_breakdown.py:200-204` copy user_collection's Genie-row -> final-forms walk WITHOUT the gender filter (and without the min_level guard), so male Lechonks count as owned Oinkologne (Female) and the Gold-Bottle-Cap advisor can name a target the user cannot actually build. Extract the gender-aware walk from `src/gopvpsim/user_collection.py:337-385` into a shared helper and route both scripts through it. The extraction is additive and safe; any change to `match_mons`' signature/defaults needs gobattlekit coordination -- do attended.

### 3. Ops and gate hardening (bundle) -- all S, no re-render, no cache cost

The layer that runs rather than renders; per the lens-grid rule these are guards that must not be duplicated.

- **ship-surface-glob:** extract the byte-identical `_find_ship_surfaces()` (`scripts/verify_article_links.py:82` / `scripts/verify_no_unicode_dashes.py:122`) into one shared module and add `WEBSITE_DIR.glob('*.html')` -- closes the real hole where cups.html and support.html ship (rsync --delete, `publish_website.sh:96`) with neither gate ever scanning them. Strongest finding of the batch; both pages are clean today, so this closes a latent hole, not an active bug.
- **ship-gate-roster:** single SHIP_GATES list; `overnight_redive.sh:208` and `phase2_preship.sh:111` currently skip the unicode-dash gate that `publish_website.sh` and `verify_overnight.py` run. (Mitigation: verify_overnight, the documented morning check, does run both -- the chains just print SUCCESS with violations present.)
- **newest-chain-log:** reuse `overnight_eta._run_stamp` (filename-stamp sort) in `verify_overnight.newest_chain_log` (`:59-61`, currently a path sort the producer's own comment calls broken); move `_run_stamp` to a shared helper so `chain_status.py` (third rule: mtime) can adopt it. Currently returns the right log by coincidence (both surviving logs share one dir); re-arms on the next cross-month filing.
- **ml-guide-slug:** define `json_slug`/`article_slug` once (in the producer `iv_envelope_analysis.py` or a tiny shared module) and import in `run_iv_guides.py`, `chain_status.py`, `iv_guides_status.py`, `render_iv_envelope_article.py`; `verify_overnight.py:283` then checks the producer's own name. Cleanest mechanical win in the review.
- **cache-sidecar schema:** give `sweep_cache.py`/`slayer_cache.py` a `write_sidecar()`/`read_sidecar()` pair and route `migrate_cache._bless`/`_bless_slayer`/`_iter_columns` and `gc_cache.py` through them, so the endorsed warm-migration path can never drop a future sidecar field and the unlink-before-write invariant (2026-06-29 red-team) lives in one place. Nothing is dropped today; the exposure is the next added field, on the artifact whose only fallback is a multi-hour cold re-dive.

### 4. Cross-boundary constant pins (bundle) -- S; the test_js_shadow_constants pattern applied twice

The shadow-multiplier pin (finding js-py-shadow-multipliers, ruled intentional) is the worked example: duplicate allowed, but a tripwire test MUST pin it. Two unpinned analogues:

- **WIN_RATING = 500 (merged pair):** extend `tests/test_win_boundary.py`'s scan (currently `SCRIPTS.glob('*.py')` only, `:64`) to `*.js` with a literal `>= 500` rule -- the boundary drifted three times and last regressed in the JS half the test cannot see (~13 open-coded sites in `deep_dive_engine.js` + `cmp_panels.js`). Also swap `deep_dive_matchup_clusters.py:54` to `from gopvpsim.battle import WIN_RATING` (import-only; reads battle.py, does not edit it -- no hash bump). The cheap guard captures most of the value; injecting WIN_RATING into DATA and rewriting the JS sites is optional later.
- **League CP caps (merged pair):** `build_opponent_pool.py:39` imports `pokemon.LEAGUE_CAPS` instead of its unforced copy; pin the JS fallback literal (`deep_dive_user_collection.js:349`) by extending `tests/test_js_shadow_constants.py` -- this is exactly the shape that already rotted once (SHADOW_DEF_MULT sat wrong until 2026-06-27). `data.py:29`'s copy is cycle-forced (pokemon imports data); it resolves properly with the league-descriptor unification in the engine batch (entry 13), or via a function-level import meanwhile. Do NOT move the canonical dict out of pokemon.py (see Do NOT do).

### 5. Py<->JS wire-contract single-sourcing (bundle) -- M; shared mechanism: emit the string from Python into DATA, one JS helper, round-trip parity check

These are all load-bearing wire strings between the Python bake and the shipped JS, currently held together by comments. One session, one mechanism.

- **SCORES_GZ key (merged pair):** route the three inline reconstructions (`deep_dive_engine.js:3444-3449` cmpGrids, `:3462-3465` cmpEnergyGrids, `:3487` cache key) through `getScoreKey`, and strip `@51` properly in the W3 fallback (`:474-490`). The existing `test_js_score_key_parity.py` tripwire covers only the `getScoreKey` body.
- **Composite mode grammar `base[:nobait][:eN]`:** one grammar (Python already has `parse_mode`/`parse_energy`/`compose_mode` in `deep_dive_rendering.py:517-560`); mirror once in JS, replacing the three hand parsers (`engine.js:3080`, `:3239`, `:484`); add a round-trip check to the harness. These strings are the score-lookup keys; a divergence lands in the silent-fallback path and renders a different mode than the dropdowns show.
- **Scenario label `{a}v{b}` (merged pair):** bake the label alongside the tuple in `DATA.scenarios`; the load-bearing key reconstruction (`engine.js:2078-2080`), the other 'v' sites, and cmp_panels' divergent `'-'` form (`cmp_panels.js:33`) all read it. A maintainer normalizing labels today has a 50% chance of picking the form that kills the cluster overlay silently.
- **Moveset label `FAST / CM1, CM2`:** ship structured `fast`/`charged` fields in `DATA.movesets` and have `cmpBattleUrl` (`engine.js:3552-3556`) read those instead of string-splitting the display label; consider `generate_article.py:1372`'s parser in the same pass.
- **Tier-card slug:** emit the slug into the tiers payload from the one Python helper (`deep_dive_rendering.py:1896-1899`); JS (`engine.js:1752-1754`) stops recomputing; `generate_article.py:2409`'s divergent variant uses the same helper. Three implementations currently converge on real data -- latent deep-link break, silent no-op failure mode.

### 6. July cup-plumbing consolidation (bundle) -- M; all files touched by the 2026-07-03 commit family (aa8dac8 / 96c9bc9 / c8c761b / 27cd097)

The July cup work reproduced the same conventions in parallel across layers. One session closes all of it:

- Export a public `data.get_rankings_for(league, cup)` and `rankings_cache_path(league, cup)`; `deep_dive.build_opp_meta_ranks` (`:1228-1234`) and `rankings_snapshot_date` (`:1261-1268`) call them, dropping the private-name imports; narrow the bare `except Exception` to OSError so a renamed cache key can no longer silently erase the archive-vintage banner.
- One cup registry (key, league, pretty name) consumed by `data._CUPS_WITH_RANKINGS`' check, `deep_dive._CUP_PRETTY`, and `build_website_index._CUP_SUFFIXES` -- the two pretty-name fallbacks already disagree ("Bastille Cup" vs "Bastille").
- Preflight assert in `run_website_dives.py` (`slug.endswith(f"-{cup}-cup")`) so the three-way slug convention (producer / index router / verify_overnight glob) cannot silently drift.
- Shared `cup_label_and_snapshot()` helper for `deep_dive.py:4815-4836` and `deep_dive_card.py:655-661`; fix the card's missing no-date path (the card is the artifact that ships standalone).
- Shared `_page_shell()`/`_index_css()` for `render_index`/`render_cup_index` (`build_website_index.py:655-696` vs `:809-846`; the cup copy omits `.dives-box`/`.scroll-hint` rules that the shared `_render_dives_grouped` output can need).
- W8 + slug-parser merge: `_slug_to_pretty_title` calls `_parse_dive_slug` and formats the result -- kills the "Shadow  Corviknight" doubled space, the never-fixed fallback parser, and the duplicated suffix/token sets. Confirm `tests/test_website_index_slugs.py` covers both entry points first.
- `build_opponent_pool.py` drops `_CP_BY_LEAGUE` for the pokemon.py import (overlaps entry 4).

### 7. Move display names (move-display-name-two-renderers) -- M; deliberate re-render, already scheduled in TODO.md:515-525

Teach `deep_dive_analysis.pretty_name` and the two open-coded `.title()` sites in `generate_article.py` (`:1897`, `:2018`) to consult the gamemaster via `auto_gen_narrative._gm_move_display`'s rule. 39 of 334 moves currently render two ways on one page ("Super Power" vs "Superpower", the whole Hidden Power family). Render-only, touches the helper not the ship-mode prose, but changes ~39 labels on every page -- do it as its own deliberate re-render, not as a ride-along.

### 8. PvPoke link-builder consolidation (bundle) -- M

- Export `_moveset_segment` from `pvpoke_links.py` (public alias) and call it from `opponent_link_data` and `deep_dive._opp_link_data` -- the FAST-CM1-CM2 guard exists three times. (The dive cannot call `opponent_link_data` wholesale -- it must use the sim's resolved movesets -- so the segment helper is the correct shared surface. The focal blob's missing `moves` field is deliberate; leave it.)
- generate_article <-> compare_loadouts: consolidate the five duplicated helpers (`_species_move_pools`, `_pvpoke_move_segment`, multi URL, single URL, opponent resolver) into `compare_loadouts.py` (generate_article already imports from it); keep generate_article's extra speciesId fallback; delete the dead `compare_loadouts._pvpoke_multi_url`.
- URL skeleton (merged pair): add a parity test that renders one known (species, ivs, level, shields, moveset) tuple through `pvpoke_links.battle_url` and both JS `cmpBattleUrl` builders and asserts identical URLs. This grammar already broke once in a way only manual link-loading caught (the `10000-51` Great-League fallback, fixed 2026-06-21), and a wrong-but-200 URL is invisible to verify_article_links.

### 9. Level-ceilings cluster (merged pair: l51 + js-py-level-ceilings) -- M **[CROSS-REPO: gobattlekit]**

One item, not two: the league-blind `max_level = 51.0` default at `user_collection.py:209/:263/:298/:417` (four sites, two of which pair it with `league='great'` in the same signature) plus its two JS mirrors (`deep_dive_user_collection.js:275/:344`) and the engine's bare 50/51 literals (`engine.js:825/:1642/:3450`). Derive from `pokemon.LEAGUE_MAX_LEVEL` (read-only -- no engine bump) or make defaults None-means-derive; pin the JS default with the entry-4 test pattern. The exact "owned mons one level too high" bug was already fixed once at the dive bake site; the harness blind spot is documented in `verify_js_parser.py:33-40`. Changing user_collection defaults is a behavior change on the gobattlekit-consumed surface -- coordinate, do attended.

### 10. JS gender-filter mirror + harness fixture (js-parity-4) -- M **[CROSS-REPO: gobattlekit]**

`deep_dive_user_collection.js.matchMons` honors only a single caller-global `requireGender`; the Python `match_mons` filters per-target-species. The file's own row-for-row contract claim is therefore false, and `verify_js_parser.py` structurally cannot see it (no gender-differentiated species in TEST_THRESHOLDS, never passes requireGender). Fix the JS to mirror per-target semantics (JS-only change is safe) and add Oinkologne + requireGender to the harness. If instead `match_mons`' semantics/signature change, that needs gobattlekit coordination. Related to entry 2 (same underlying contract).

### 11. Package-level invalidate_caches() -- engine-free half of L15 -- M

Add a `gopvpsim.invalidate_caches()` that clears all nine gamemaster/rankings-derived module caches (pokemon `_pokemon_index`/`_gm_entry_index`/`_gm_id_index`, moves `_fast_moves`/`_charged_moves`, data `_species_id_index`/`_rankings_index`, evolution_lines' two) by assigning module globals from data.py/`__init__.py` -- no engine file is edited. Replaces `tests/conftest.py:53,55`'s reach into private state. The July cup work grew the uncovered set to seven with no invalidator; a mid-run gamemaster refresh currently leaves modules disagreeing with no error. The effective-stats half of L15 stays in the engine batch (entry 13).

### 12. deep_dive.py split bundle -- L; scheduled session. NOTE: D10 forces a CACHE_VERSION bump -> whole sweep cache cold with NO migrate predicate available. Schedule this session against a planned bake -- ideally the same window as entry 13.

Everything the verifiers marked "bundles with the deep_dive.py split" (TODO.md:352-358, 527-556):

- **T8 first:** conftest `deep_dive` loader fixture registering ONE shared `sys.modules['deep_dive']` object (the guarded files' own comments say worker pickling requires it; ten unguarded files currently mint fresh objects, so behavior is collection-order dependent). Collapses 14 exec_module preambles + 2 variants. Doing this first also enables the dom-id test below.
- **D9:** a SweepConfig (or kwargs dict) for the 8-line pass-through block re-typed at five `iv_sweep` call sites (+2 external). The "missed kwarg already fired" evidence was refuted (see Do NOT do), but one-feature-edits-five-blocks is proven by commit 06bedca.
- **D10:** extract the ~20-line `build_battle_pair()` core shared by `_sweep_worker` and `slayer_iter_worker` -- NOT a merged worker (they iterate different grids); bring `profile_slayer.run_sims` onto it, which also fixes its missing `mechanics=` (benchmarks currently measure 'legacy' regardless of what the real workers run).
- **D14:** route the inline clone at `deep_dive.py:3686` through `_recompute_tier_assignments` (drop-in, S -- can land any time); unify `classify_iv` (`:654`) and the `:4211` copy here where the data shapes get reworked.
- **L11 scripts side:** route the 7 scripts/ linear gamemaster scans through a `.get()`-style accessor (None-on-miss -- a naive swap to the KeyError-raising `get_pokemon_entry` changes failure modes; see Do NOT do). The 4 non-engine library sites (anchors.py x3, breakpoints.py:160) can come along; the battle.py:2035 hop waits for entry 13.
- **mc-single-stat-flip:** share the sorted-stat/cumsum primitive between `single_stat_flip` and `find_matchup_boundaries`, and cross-label the two flip numbers the page prints for the same opponent. Do NOT merge the rules -- they answer different questions.
- **R11 scenario-vocabulary half:** pick one vocabulary (the '0v0' family used everywhere else) and route the ~12 sites through a shared helper; pairs with entry 5's DATA label.
- **js-py-dom-id-registry:** promote the verifier's check into a test: render one small dive via the new fixture, assert every `getElementById` literal in the JS (39 ids) resolves in the produced HTML. A guard, not a constants file -- the ids live in HTML string literals and a manifest would hurt readability.
- **js-py-score-pack:** `_pack_u16()` helper collapsing deep_dive.py's two identical encoders (S, can land early); emit ONE parameterized JS decoder template instead of two string literals; round-trip test spanning the dive and ML-guide chains (iv_envelope_analysis encoder / render_iv_envelope_article decoder).

### 13. ENGINE DRY BATCH **[ENGINE-HASH]** -- one bump, one cold re-dive, scheduled against the next natural bake

Per the ranking rule: these are not demoted, they are batched. All three confirmed engine-file-touching fixes ride a SINGLE hash bump:

- **L6 league descriptor:** unify caps / CP / max-level / 'little' membership into one structure in `pokemon.py`, fixing the four disagreeing dicts (pokemon.py x3 + data.py:29) and the docstrings that advertise 'little' while `LEAGUE_CAPS[league]` KeyErrors on it (reproduced live, two paths). Retire the hand-written 50/51 comments in deep_dive.py:4764 and owned_breakdown.py:128.
- **L11 battle.py hop:** route `BattlePokemon.from_pokemon` (`battle.py:2035`) through the cached gamemaster accessor -- the per-battle O(n) scan.
- **L15 effective-stats primitive:** one place applies the shadow multipliers (currently re-applied 6+ ways across pokemon/user_collection/breakpoints/formchange/scripts -- the exact shape that produced the L1 shadow-anchor bug), plus any in-engine invalidation hooks.

Combined win: solid (kills the 4-dict league drift and the 6-way shadow-stat repetition) but not urgent enough to justify a standalone multi-hour bake. Schedule against the next gamemaster/balance-forced cold re-dive, or the same window as entry 12's CACHE_VERSION cold. Note: L6's minimal 'little' addition alone would be a trivially provable migrate predicate (pure addition), but batching the three makes the delta unmigrate-able -- which is fine, because the batch rides a forced-cold bake anyway; do not also plan a warm migration for this bump. Engine-free halves are already pulled out to entries 4, 6, 11, and 12.

### 14. matchup-clusters cleanup (bundle) -- S items, one short session in deep_dive_matchup_clusters.py (+ guide)

Prophylaxis, safe to land any time:

- Hoist `_hamming(patterns)` (byte-identical at :138 and :192 -- the distance definition must not live twice) and pass the matrix into `_weighted_silhouette`. (Perf angle is minor; u is small.)
- Shared `_small_pop_floor()` for the two `max(2, min(C, n // 8))` copies (:232, :428).
- Use `_base_opponent` instead of the inline single-level variant strip (:771) -- move it to a shared module (deep_dive imports matchup_clusters, so a backwards import won't work). The inline copy would wrongly fold 'X (Shadow)' -> 'X'.
- Win-rate tint (:595): pick a lane deliberately -- recommend theme tokens `--win`/`--loss` (gains light-theme support); note palette[5] #e66767 vs --loss #e96767 are one hex digit apart, so state the intent in the commit.
- Cluster-params prose (M sub-item): single-source the 2%/98%/0.03/0.30/K-range numbers into the in-page note and `guides/matchup-clusters/body.md` via a resolver source or `dev:` sentinel emitted FROM the module constants -- NOT a hand-typed `[tokens]` literal (that is a fourth copy).
- Ride-alongs: extract the cluster trace-spec helper in engine.js (cosmetic-only; lowest-value item of the review) and name the even-shield triple once in a shared scripts constant when convenient.

### 15. Deferred / fold-in-when-touching

- **js-py-plotly-chrome-hexes (L):** theme-aware Plotly shim (the canvases are dark-only on a light-default site; the orphan hexes bypass theme.py entirely) + re-run the dataviz validator for CLUSTER_PALETTE against the new surfaces. Already tracked as known-open at deep_dive.py:2450-2452; dedicated session.
- **js-py-cmp-css (M, latent):** hoist the duplicated `.cmp-*` stylesheet into one constant imported by both renderers next time cmp panels are touched. All 21 classes verified styled in BOTH files today -- future-drift risk only.
- **js-py-localstorage-theme-key (S):** `_THEME_KEY` constant next time theme.py is touched. Three literals within ~20 lines of one file; lowest exposure in the batch.

## Do NOT do

Intentional designs and refuted claims -- so future review passes stop re-finding them:

- **format_md.py vendored duplicate** (scripts/ vs dotfiles): deliberate, documented in CLAUDE.md; port changes both ways.
- **gobattlekit threshold-schema shims** (`user_collection.py` + `thresholds.py as_legacy_dict`): cross-repo contract, do-not-touch per TODO.md.
- **js-py-shadow-multipliers:** ruled INTENTIONAL -- deliberate fallback duplication pinned by `tests/test_js_shadow_constants.py`. It is the template for entries 4 and 8, not a defect.
- **W10 "stale href after variant toggle":** REFUTED -- `pvpoke_single_battle_url` encodes no variant-dependent field, so the baked href stays correct. Fix only the Py/JS classification+tooltip duplication.
- **D9 "the missed-kwarg hazard already fired at :7784":** REFUTED -- that site discards the energy return; omitting `capture_energy` there is correct. The duplication itself stands.
- **owned_breakdown "silently drops shadow scaling":** refuted as a rank-1 defect -- uniform multipliers cannot change the argmax. The tie-break and Aegislash rounding are the real divergences.
- **dive-slug "REGIONAL sets already diverged":** refuted -- `_parse_dive_slug` handles 'shadow' in a separate branch; functionally equivalent today. The two-parsers problem stands.
- **build_website_index 'cups' exclude "third diverged container list":** it is a defensive stale-dir cleanup, not drift.
- **Deep-dive focal link's missing 'moves' field:** deliberate (live moveset toggle); keep it.
- **Do not move LEAGUE_CAPS out of pokemon.py:** that variant of the caps fix edits an engine file -- a cold re-dive for a cosmetic win. Import FROM pokemon.py instead.
- **Do not drop-in-swap the L11 scans to `get_pokemon_entry`:** it raises KeyError where all five sites depend on None/[]-on-miss. Add a `.get()`-style accessor first.
- **Do not merge the two flip-threshold engines or the two multiprocessing workers wholesale:** each pair deliberately answers different questions / iterates different grids; share only the primitive core (entry 12).
- **Do not tokenize the cluster params as `[tokens]` literals:** that adds a fourth hand-typed copy (entry 14).

## Already fixed since June

No register item is fully gone, but five were partially closed -- TODO.md's S7 register lines (352-358, 457-459, 515-525) should be updated to reflect the closed halves:

| Register item | What got fixed                                                                                                              | Still open                                             |
| ------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| W8            | `_parse_dive_slug` got `_known_species_slugs` longest-prefix matching                                                       | fallback title parser never fixed (entry 6)            |
| R11           | narrative/rendering palettes unified to the same 12-entry `--opp-*` list                                                    | `.lower()` hash case + scenario vocab (entries 1, 12)  |
| L51 cluster   | `verify_js_parser.py` harness is league-aware (HARNESS_MAX_LEVEL = 50.0); the dive bake single-sources via LEAGUE_MAX_LEVEL | 4 Python defaults + 2 JS mirrors (entry 9)             |
| D14           | `_recompute_tier_assignments` helper extracted                                                                              | the :3686 clone was never routed through it (entry 12) |
| Score key     | `getScoreKey` + `test_js_score_key_parity.py` tripwire exist                                                                | 3 inline JS reconstructions unpinned (entry 5)         |
| Shadow mults  | pinned by `test_js_shadow_constants.py` after the 2026-06-27 rot                                                            | nothing -- reclassified intentional                    |

Also present since June: `tests/conftest.py` exists (T1 CACHE_TTL pins + mock_gm fixtures) -- the seam T8's loader fixture needs is already in place.
