<!-- TODO.md is a LIVE BACKLOG, not an append-only chronological log. Keep it
short: completed/shipped work moves to CHANGELOG.md (root-cause writeups,
dates, SHAs) or docs/TODO_archive.md (verbatim session batches); only OPEN
items and forward-looking design notes live here. When you finish an item,
delete its bullet or move the writeup out -- do not leave a 'DONE/RESOLVED'
narrative inline. This convention was set 2026-06-27 after the file hit ~1980
lines of mostly-completed chronological batches. -->

## Post-launch status (2026-06-28)

The cold re-dive is **DONE** (bake 2026-06-28 01:55–11:49, `overnight chain
SUCCESS`; the engine bug-hunt + cache-rework batch + session-6 fixes all rode
it). Full shipped record: CHANGELOG.md "2026-06-28". The site is published and
on the trusted engine. Re-dive runbook (for the next time one is needed):
`docs/predive_checklist.md` is the STANDING pre-cold-dive gate; run
`overnight_redive.sh` and watch with `scripts/chain_status.py --chain overnight`.

### P1 — sanity-check the session-6 fixes in rendered output (verification gate)

The best-buddy-toggle + shadow-default-IV fixes shipped to the **live site**
via this bake but were never confirmed in rendered HTML. Spot-check:
Registeel GL (no-op toggle shows + "(no change for this mon)" hint), Carbink
GL (active L51 sweep actually changes spreads), UL Mimikyu vs Shadow Raikou 2-2
(should now be a 707 win, was a 470 loss). Cheap; never-ship-unflagged-wrong
applies since it's public.

### Open follow-ups (non-gating; render/tooling-only ones re-render from replay)

- **[tooling] per-slug historical-timing ETA estimator** (Michael greenlit
  2026-06-28; the just-finished cold bake is the clean per-slug seed dataset).
  Today `overnight_eta.py` buckets every dive crudely (`gl_full`/`ul_full`/
  `forretress`) + flat fallback mean, so a heavyweight (sableye/medicham/carbink)
  and a no-op (registeel) both read `gl_full` but differ ~5x. Agreed build (scope
  1): keep a per-slug cold-timing table parsed from `[N/M] slug ... Done in X min`
  pairs in `userdata/logs/20*/overnight_*.log`, key each estimate on species,
  bucket-mean only for never-seen slugs. All `scripts/` tooling, nothing
  engine-hashed. (Stopgaps already landed: `37655db` recalibrated baselines,
  `58dc88d` folded the ~7h ML tail into the whole-script ETA.)
- **[render DRY] score-key `{mi}_{mode}@51` parity (Python<->JS).** Open-coded in
  `deep_dive.py` + `deep_dive_engine.js`; consistent today, loud failure mode.
  Optional belt-and-suspenders parity test only (it's a cache/render data
  contract, not a refactor target).
- **[tooling, silent-incompleteness] verify_overnight UL opponent-count
  assertion.** The completeness guard is GL-only; a UL opponent silently
  deranked by a fresh gamemaster would drop from every UL dive and still pass the
  gate GREEN. LATENT (UL 68/68 resolve on the current gamemaster). Needs a
  marker/expected-count design decision before asserting.
- **[tooling] F3: narrative auto-gen patch is WARN-not-FAIL** (`run_website_dives.py`
  ~624). Low; optional: surface the WARN where `verify_overnight` scans.
- **[render] `#opp-<slug>` canonical landing.** `#opp-` links land on the
  first-rendered mention; pick one canonical per-opponent target. Low; render-only.
- **[engine, low] #3-followup: both-self-debuff PvPoke divergences.** The bug-#3
  oracle exposed ~117 pre-existing PvPoke divergences (7 winner-flips) on the
  broader both-self-debuff population (Lurantis, Blaziken; non-default movesets) —
  likely the near-KO-DP / `_optimize_move_timing` self-debuff-timing cluster.
  Investigate, decide keep-vs-fix (CLAUDE.md gate). Repro: DEVELOPER_NOTES
  "#2-#6" + `docs/reviews/2026-06-27_engine_bug_hunt.md`.
- **[engine, cosmetic] #6 bandaid[910]** uses defender max-damage move not
  `bestChargedMove` (battle.py); measured cosmetic (16/16 oracle match). Low.

## NEXT SESSION (queued 2026-06-21): gobattlekit owned-mon breakdown screen

Build the "which of my mons should I build?" breakdown in the gobattlekit iOS
app — the same feature already live on the website (the deep-dive paste-box
"Gives up vs #1" column) and as a Python reference (`scripts/owned_breakdown.py`).

- **Scope (decided):** GL + UL, the species we've already dived (zero new sims,
  smallest mobile bundle).
- **Architecture:** EXTRACT per-IV dropped-vs-rank-1 from existing dive grids
  (no re-sim) — the dive embeds the full 4096-IV score grid. gobattlekit has NO
  battle engine and must not get one (lean iOS build); it consumes pre-baked
  data + recomputes only the analytic layer on-device.
- **Two remaining build steps:**
  1. **Bitmask exporter.** `scripts/export_owned_breakdown_bundle.py` already
     extracts the breakdown but emits a full-list JSON that is **~25.6 MB for 15
     species — too big for mobile**. Add a per-IV BITMASK variant: 246 even-shield
     (opp × scenario) cells -> ~31 bytes/IV + a one-time names header, decoded
     on-device. (top-K-stat-product bake was a DEAD END — those spreads all give
     up nothing; owned mons have arbitrary IVs.)
  2. **Toga screen** modeled on `gobattlekit/src/gobattlekit/screens/user_iv_checker.py`,
     reading the baked artifact (bundle like `default_thresholds.toml` via
     `tools/threshold_export/`); resolve owned mons through their evolution line;
     **add parity vectors** to gobattlekit `tests/test_parity_vectors.py`.
- **Full plan + findings + file:line pointers:** `docs/owned_mon_breakdown_plan.md`.
  Memory: `project_owned_mon_breakdown.md`. Convention note: web + iOS use the
  dive's opponent IVs; the Python CLI uses 15/15/15 (they differ slightly).

## Old/new mechanics user toggle (POST-SHIP)

*(2026-06-26, Michael)* Post-ship idea, flagged so it is not lost; do NOT
pre-ship or design heavily yet. If the site/app gets traction, P!P-series /
Worlds competitors may want it for prep, and **Worlds runs on the OLD battle
mechanics**. So expose a user-facing toggle between old and new mechanics on
the dive site.

Light design notes (not yet designed):
- Preference storage: cookies (never used here) vs radio buttons vs a query
  param. Look at what PvPoke does for its "Preview next season" version as
  prior art before picking.
- Cache: the cache-rework (shipped 2026-06-27, CHANGELOG) does NOT key on the
  turn model, so a `new`-mechanics dive force-disables the sweep cache today.
  Adding a real toggle means keying the cache by mechanics so old-vs-new
  results cache separately while our engine stays current — extend
  `sweep_cache`/`migrate_cache` rather than re-deriving them.

## Form-change "starts in alt form" dives + on-page descriptions (POST-PUBLISH)

*(2026-06-26, Michael)* Aegislash got fixed pre-launch (relabeled "Starts
Blade" + a top-of-page form-change note on both GL dives) because it was the
only form-change dive that read as confusing on the site. The rest is
deferred post-publish:

- **Mimikyu "starts busted" dives, GL and UL.** Rationale: real battles are
  3v3 with switching, but once Mimikyu is in Busted form it stays Busted for
  the rest of the battle regardless of swaps, so a "starts in Busted form"
  dive is legitimately useful (unlike a transient mid-fight state). Add a
  GL and a UL "starts busted" dive alongside the existing Disguise-intact
  dives. Mirrors the Aegislash (Blade) "starts in alt form" pattern: a focal
  species started in the alt form, form change still live.
- **Form-change descriptions on the Mimikyu dives** (disguise absorbs the
  first unshielded charged hit -> 1 dmg + permanent -1 def, then Busted for
  the rest of the battle). Reuse the `_FORM_CHANGE_NOTES` mechanism added in
  `scripts/deep_dive.py` (keyed by focal speciesName) -- just add Mimikyu
  keys; keep it qualitative/factual like the Aegislash notes.
- **If a Morpeko dive is ever added, it must carry a form-change note at the
  top too** (Full Belly <-> Hangry toggles AURA_WHEEL Electric/Dark after
  each charged move). Same `_FORM_CHANGE_NOTES` mechanism.

## Limited-availability mons: real IV floors for ML sweeps (PARALLEL, post-ship)

*(2026-06-25, scratch_thoughts)* The ML IV-guide sweeps assume a 12/12/12 IV
floor (right for traded / grind-able species). But some mons you only get one
or two of in PoGo -- mostly mythicals (Marshadow, Hoopa, Zygarde) but NOT all
(Genesect is grind-able; Marshadow/Hoopa/Zygarde are not). Their real-world IV
floor is LOWER than 12/12/12, so the shipped ML guide can't evaluate a
legitimately owned spread (Michael's Marshadow is 11/13/11). Steps: (1)
enumerate which species are in the limited-availability category, (2) determine
each one's IRL IV floor (research-reward / quest-encounter IVs), (3) re-run the
ML sweep for any with a floor below 12/12/12. Independent of everything else --
fire as a PARALLEL task, ship whatever is done, re-ship the corrected guides
later (they finish after the UI decisions, or get rewritten during UI rework).
FLAG (never-ship-unflagged-known-wrong rule): until corrected, the limited-mon
ML guides ship with a floor that is wrong for them -- decide whether to add an
"assumes a 12/12/12 IV floor" caveat on those pages or ship unflagged.

## Pre-ship arc — residual open polish

The 2026-04/06 pre-ship arc shipped (site published 2026-06-07; see
CHANGELOG.md). The minor polish residue:

- **G16 — methodology-details guide pointer.** Replace the
  in-article hidden-but-present methodology prose with a one-line
  guide pointer (the hide layer is already in place; G16 is the
  last-mile substitution). ~30 min.

- **G1 + G2 + G7 — richer auto-gen prose template** [post-ship,
  recommended]. F1 Meta Role, F2 key-flips callout, and
  F-fast/charge-moves shipped as deterministic rollups; JRE-style
  prose ("Mud Slap takes Male Oinkologne from 0% to 76.6% vs
  Steelix — the signature upgrade") would close the register
  gap. Template change, not Claude-drafted prose, so
  ship-policy-clean. 0.5-1 session. Benefits every future dive.
  Bundles with **Row D** — bulk-vs-peers paragraph (micro-gap from
  original §3.D, never made it through F1's auto-gen template).

- **F-tier-name-cleanup** [post-ship] — simplify IV-rec tier card
  names (current: `Steelix (Shadow) Slayer -   (Wigglytuff Slayer
  -   (Wigglytuff Atk))`) to RyanSwag's name/signature convention
  per `docs/reference_deep_dives/ryanswag/STYLE_ANALYSIS.md`.
  Bundles with S5a rename work in post-S5 arc.

- **F-shadow-narrative** [post-ship] — Shadow-variant comparison
  prose block for species that have shadow forms (not applicable
  to Oinkologne ship).

- **F5** [post-ship, gated ≥3-5 shipped articles] —
  multi-article-reader cross-linking footer. Not worth building
  until cross-reference surface is large enough.

- **R3 removal candidate.** Meta Coverage "Shield asymmetry
  dominates the extremes" explanatory paragraph — currently
  hidden; re-evaluate for removal post-ship if hide reads as
  bloat.

- **Personal-collection: `scripts/suggest_builds.py`.** CLI
  helper: takes `--species`, `--league`, `--roles lead,closer`,
  path to a PokeGenie CSV export, and the shipped dive HTML.
  Parses Top IVs + Anchors + Matchup Flip tables, intersects with
  the collection, prints a ranked shortlist per role with the key
  tradeoffs (atk/HP/def, anchor flips, score Δ, XL/dust cost).
  Maybe 2-3 hours; deprioritize if scatter paste-box overlay +
  Mirror CMP columns are enough.

- **CD-prep tracking — delete `[cd_prep]` blocks** after the
  Oinkologne CD ships, or after PvPoke stably lists Mud Slap for
  2+ gamemaster refreshes. The auto-injection plumbing
  (`enumerate_movesets(..., cd_prep_fast=, cd_prep_charged=)`,
  commit `e61c14e`) stays.

- **P2 single-form opponent links.** `_render_matchup_delta_section`
  (line 1954) doesn't yet link opponent cells — applies to
  non-CD articles that aren't per-form. Extend when the first
  such article actually ships.

- **P3 article-surface design question.** Dive-side envelope-tag
  retrofit shipped 2026-04-23 (`patch_dive_envelope_tags.py`);
  a category-card surface on the CD article itself (linking
  envelope-shape to a specific "Cost to XL" judgment) remains
  the original P3 question and has not been addressed.

- **Cross-form opponent expansion (parked).** Item 4 (auto-
  form-sibling expansion in `build_opponent_pool.py`) — design
  done but parked pending review of rendered Oinkologne article;
  decide pool-level vs render-level filter for hypothetical-form
  rows. See memory `project_form_change_pool_expansion_parked.md`.

## Deferred cleanup: backwards-compatibility removal pass

The S7 dead-code removal pass ran 2026-06-12 (see CHANGELOG). Still open
(deliberately NOT cut in S7):

- **Gobattlekit threshold schema compatibility** in
  `gopvpsim.user_collection.check_thresholds` (and `as_legacy_dict` in
  thresholds.py) — once gobattlekit has actually migrated to use the
  shared module and we've confirmed it works, we may want to simplify
  the dict schema or unify with pogo-simulator's TOML anchor schema.
  But not before gobattlekit's migration lands. **The gobattlekit
  threshold pipeline actively consumes both as of 2026-06-12 — do not
  touch without coordinating.**
- **§I consolidations** (L11 gamemaster index, L15 unified
  invalidate_caches + effective-stats primitive, L6 league descriptor,
  D9 SweepConfig, D14 tier recompute, R11 shared scenario/color
  helpers, W8 slug parser, W10 badge renderer, T8 conftest deep_dive
  loader) — deferred from S7: D9/D14/T8 are seams the dedicated
  deep_dive.py split session will rework anyway, and the library
  consolidations (L6/L11/L15) are behavior-adjacent refactors, not
  deletions. Bundle them with the split session or their natural
  feature sessions.

## Battle simulator

* **File PvPoke bug reports** *(NO URGENCY — Michael's explicit call
  2026-06-11: he'll file when he has time to engage with any upstream
  responses; do not nag)* — paste-ready GitHub-issue drafts live in
  `docs/pvpoke_bug_reports.md` (2026-06-11): 7 curated reports
  — the list below minus the retracted Mimikyu timing item (#5, our
  own logging artifact) and the debunked-premise bestChargedMove item
  (#2, initializeMove DOES set move.damage at init; the real issue
  there is the DPE-overwrite, drafted as report 4) — plus the new
  Blade→Shield CPM-table overflow found 2026-06-11. Filing them
  upstream is Michael's action. (The discovery list formerly
  enumerated here duplicated DEVELOPER_NOTES "PvPoke bugs found"
  and the drafts doc — those two are the sources of truth.)

* **Known PvPoke divergences** — DEVELOPER_NOTES "Known divergences"
  is the single source of truth (bestChargedMove per-turn recompute,
  the near-KO plan cluster, the battle-timeout guard). Re-audit
  anytime: `python scripts/audit_oracle_harness.py` (covers GL + UL;
  current baseline 153 cells = 136 exact + 17 documented).

* **Speed test** -- compare our speed vs the PvPoke JS code, look for
  ways we can speed ours up. *(Partly addressed 2026-06-10: holistic
  perf review found and fixed a 2.0x engine regression dating to the
  2026-04-15 correctness arc — see DEVELOPER_NOTES "Performance
  baseline" for the regression gate and `docs/perf/` for the writeup.
  The vs-PvPoke-JS throughput comparison itself remains open.)*

## Shared user_collection module — Option-2 migration prep

*(from gobattlekit's 2026-06-11/12 deep review, sections F/J — CP9 +
CP12. Not urgent; gobattlekit is otherwise ready to consume
`gopvpsim.user_collection` and has aligned its matching semantics to
ours. The CP4 over-leveled-mon fix and CP13 Burmy→Mothim fix shipped
here 2026-06-12; these are the remaining seams.)*

* **Split heavy deps into extras** — `pyproject.toml` hard-requires
  `numpy` + `markdown`, but the `user_collection` import path
  (user_collection → evolution_lines + pokemon → data) needs neither.
  numpy on iOS via BeeWare is a real packaging problem. Move them to
  an extra (e.g. `gopvpsim[sim]`) so a mobile app can take a core
  dependency. Note the user_collection docstring's "stdlib only"
  claim is false at package level until `certifi` (imported by
  data.py at module load) is also dealt with.

* **Injectable gamemaster/CPM source** — `match_mons` hardwires
  `get_pokemon_index()` → data.py's network-backed cache
  (`~/Documents/gopvpsim_cache/`, 24h TTL, NoDataError when offline
  with no cache). gobattlekit needs to supply its own bundled +
  ETag-cached gamemaster. Add a provider injection point (parameter
  or settable loader) on match_mons / get_pokemon_index /
  evolution_lines.

* **Golden parity-vector emitter** *(seeded by the gobattlekit
  threshold-pipeline session, 2026-06-12)* — a script that emits
  (species, IVs, level) → (stats, CP, rank) fixtures from our
  canonical primitives, checked into gobattlekit as test vectors so
  its stat math can't drift from ours. Complements the CSV parity
  corpus below (that one covers parsing/matching; this covers the
  arithmetic).

* **Shared CSV parity corpus (CP12)** — a small synthetic CSV
  (shadow, over-cap, out-of-range, gendered, branched-evo rows) +
  golden expected-results JSON, checked into BOTH repos and run by
  both suites, so the row-for-row contract can't silently drift
  again (it demonstrably did: gender, shadow, level-gating). Until
  Option 2 deletes the duplicate implementation, this is the only
  tripwire.

## Tests to add

* **Regression tests for the two `68ad233` port-fidelity fixes (confirmed
  coverage holes, 2026-06-28 round-2 finder fleet).** Both fixes ride the cold
  bake with NO dedicated test pinning them (both skeptics agreed on the facts;
  see DEVELOPER_NOTES / the 68ad233 commit). Both are LOW severity (~zero
  shipped-default impact) but a "simplify" could silently revert them. **A valid
  test MUST verify the revert-fails property** — temporarily revert the fix and
  confirm the asserted value changes; a test that passes both ways is worse than
  none (false confidence). Attempted 2026-06-28: a naive
  Buzzwole(COUNTER/Power-Up Punch+Super Power) vs Melmetal(default) 0-0 config
  did NOT fire the guard (718 identical fixed-vs-reverted), so the original
  assessment's exact Melmetal moveset is needed.
  1. **bandaid[910] index** (`battle.py:1736`, `not cm_self_buff[0]` =
     activeChargedMoves[0]/cheapest, per ActionLogic.js:929). Oracle repro from
     the commit: **Buzzwole (Power-Up Punch + Super Power) vs Melmetal 0-0,
     687 (old, `cm_self_buff[first_idx]`) -> 812 (fixed) = PvPoke oracle** — find
     the exact Melmetal moveset that reproduces 812 (default DOUBLE_IRON_BASH +
     DYNAMIC_PUNCH gives 718 and does not fire the guard). Then mirror the
     `tests/test_bug3_farm_stack.py` 9-shield oracle pattern.
  2. **buffApplyChance float coercion** (`battle.py:909` _priority_shuffle +
     `:2216` bestChargedMove tie-break). The gamemaster mixes `'.5'`/`'0.2'`
     string formats; `'.5' > '0.2'` is False as strings but True as floats, so
     the `float()` coercion is load-bearing for ordering. Needs two both-buff
     charged moves with mixed-format buffApplyChance on one species, hitting the
     tie-break path (no concrete species recorded — "affects enumerated alt-move
     combos", per the commit). Construct + verify revert-fails.

* **Guard for the IV-scanner `maxLevel` single-source (fixed `725c184`).** No
  test pins `_collection_data['maxLevel']` (deep_dive.py:4602) to
  `LEAGUE_MAX_LEVEL.get(league)`, so a future re-hardcode could silently
  re-introduce the GL/UL "owned mons one level too high" bug. The strong pin:
  render a tiny GL dive with a collection and assert the emitted
  `DATA.collection.maxLevel == 50.0` (a table-only assertion is too weak — it
  wouldn't catch line 4602 drifting). Heavy (needs a dive render + a Poke Genie
  CSV fixture); deferred. Also worth folding in: the latent dead-code `51.0`
  fallbacks in `deep_dive_user_collection.js:275` (`ivsToStatsAtCap` default,
  caller always passes maxLevel) and `:344` (`matchMons`, zero live call sites)
  — single-source these to a league-aware ceiling if matchMons is ever wired up.
  **Round-4 (2026-06-28) found the same-class `51.0` latent default in the
  shared library `src/gopvpsim/user_collection.py:209` (`ivs_to_stats_at_cap`)
  and `:263` (`compute_rank_lookup`).** NOT currently wrong (every shipped
  deep_dive bake site overrides it), but it's a league-unaware default that a
  future caller could hit. **This module is consumed by gobattlekit** (CLAUDE.md
  "gobattlekit" / shared `user_collection`), so changing the default signature
  needs cross-repo coordination — do NOT change unattended; either make the
  default `None` + derive from `league` (like `owned_breakdown.py` `786d437`),
  or require an explicit cap, after checking gobattlekit's call sites. The JS
  regression guard `verify_js_parser.py:152,302` ALSO hardcodes `51.0` with
  `league='great'`, so it can't catch a league-awareness regression — fix the
  fixture to the league-derived ceiling when adding the strong pin above.

* **No-bait oracle tests from iv-tech deep dives** — `pvpoke_dp`
  accepts `bait_shields=False`; sanity tests for the farm-down gate
  landed in `test_battle.py` (see `test_pvpoke_dp_no_bait_*`).
  Real-world oracle cases from the HSH #iv-tech deep dives still
  open:

  1. **Tinkaton vs rank #1 shadow Altaria 0-1** —
     `docs/tinkaton_deep_dive_reference.md:31`. "143.04 defense with
     141 hp … win the 0-1s *without baiting*." Reference also flags
     inconsistency due to shadow IV variance.
  2. **Spidops vs rank #1 Altaria 1s** —
     `docs/spidops_deep_dive_reference.md:35`. "140.67 defense with
     132+ hp flips the 1s vs the rank #1 altaria *without baits* by
     reducing sky attack damage."

  (Tinkaton vs Medicham 1-1, Tinkaton vs rank #1 Azumarill 1-2, and
  Corviknight vs default-IV Shadow Sableye all shipped 2026-04-12.)

  Open followup from case 1: our sim has a more forgiving win
  threshold than the reference (many Tinkaton spreads below
  def=141.66 win the 1v1, e.g. 0/10/15 at def=138.96). Reference may
  be overly conservative, or our sim is missing a nuance. Worth
  round-tripping at pvpoke.com/battle.

  Each remaining test should parametrize over `bait_shields=[True,
  False]` when the reference makes a directional claim. Priority:
  low-to-medium — integration oracles, not correctness-blocking.

* **Auto-anchor fallback gating tests** — `build_auto_anchors()` and
  the per-kind gating logic are currently only verified by smoke runs
  against real Annihilape data. Add explicit unit tests for the
  gating cases (no kinds existing → all three fire; one kind existing
  → other two fire; all three existing → empty registry).
  *Note: bulkpoint gating tests landed in 2026-04-08; this entry now
  covers the broader BP/CMP gating coverage gap.*

## Refactoring

* **Pain points captured during real debugging** — see memory file
  `project_post_ship_cleanup_pain_points.md` (silent early-returns
  with no logging, no replay-from-saved-state mode, hardcoded magic
  numbers assuming `nS=9`, parallel call-site duplication,
  free-form-string opponent identity, `data_obj`-as-mutable-bag,
  `id()`-keyed caches). Specific friction encountered while
  diagnosing the 2026-04-25 mirror-tier-synthesis no-fire bug;
  read this *before* starting the deep_dive.py split below so the
  cuts address actual pain rather than aesthetic ones.

* **Move display-name single-source (DRY, confirmed 2026-06-28).** Two helpers
  derive a move's label two incompatible ways on the same dive page — header
  "Super Power" vs narrative "Superpower" (~39 moves): `auto_gen_narrative._gm_move_display`
  uses the gamemaster `name`; `deep_dive_analysis.pretty_name`/`pretty_moveset`
  title-cases the raw moveId. Route both through one helper (have `pretty_name`
  consult the gamemaster name). Cosmetic, render-only, but broad multi-file +
  ship-narrative-adjacent — do deliberately. Full detail: backlog "Deep-dive
  narrative — open polish".

* **Split `scripts/deep_dive.py`** *(deferred from 2026-04-09; not
  blocking, but file is now ~6100 lines as of 2026-04-10)* — After the structured IV
  categories shipped, the file is approaching the size where edits
  start fighting the line-cap. Concrete extraction targets, in rough
  order of independence:
  1. **`scripts/deep_dive_lib/categories.py`** — `IVCategory` dataclass,
     `build_iv_categories()`, `_stat_cutoffs_from_anchors()`,
     `_format_stat_cutoffs()`, `_composite_tradeoff_prose()`,
     `_matchup_subtitle()`. Pure-Python, already isolated, already has
     unit tests in `tests/test_iv_categories.py`. Easiest move.
  2. **`scripts/deep_dive_lib/anchor_flips.py`** — `_aggregate_flips_by_anchor()`,
     `_render_anchor_flip_bullets()`. Pure-Python, already isolated,
     already has tests in `tests/test_flip_aggregator.py`.
  3. **`scripts/deep_dive_lib/slayer.py`** — `iterative_slayer_discovery()`,
     `categorize_slayers()`, `_slayer_iter_worker()`, related helpers.
     The multiprocessing entry points complicate this — workers are
     resolved by qualified name, so the move requires careful import
     plumbing.
  4. **`scripts/deep_dive_lib/render.py`** — `generate_analysis_sections()`,
     the per-section helpers (`_render_notable_ivs_section`,
     `_iv_label`, `_tier_badge_html`, `_threshold_desc`,
     `_hover_text`, etc.), the CSS string. This is the actual monster
     (~1500 lines and growing). Needs a small "renderer context"
     dataclass first to avoid passing a 15-arg tuple around.
  5. **`scripts/deep_dive_lib/sweep.py`** — `iv_sweep()`, the worker
     init/run pair, `screen_movesets()`, `compute_iv_metadata()`,
     `group_ivs_by_stat_profile()`. Numba-touching code; same
     multiprocessing import-plumbing concern as slayer.
  Remaining in `scripts/deep_dive.py` after all five steps: argument
  parsing, the top-level orchestration in `main()`, and the legacy
  non-interactive `generate_html()` (already on the chopping block —
  see "Non-interactive `generate_html` is now strictly worse" above).
  Test split: each module gets its own `tests/test_<module>.py`; the
  existing tests already prove the importlib pattern works for
  modules that can't import from `gopvpsim` directly.
  **Recommendation**: do this in a dedicated session, not interleaved
  with feature work — refactor diffs and feature diffs shouldn't ride
  the same commit. Mechanical (file moves + import fixes) so it
  shouldn't take long once started; the risk is multiprocessing
  worker resolution and CSS-string fragment positioning.

## Moveset / variant comparison tool

* **N=3 / N=4 renderer support for `compare_loadouts.py`** — MVP
  (N=2) shipped 2026-04-18. N=4 ceiling covers the canonical
  (moveset × form) cross (e.g. Forretress: Volt Switch / Bug Bite ×
  Shadow / normal). Remaining work: N=3 and N=4 renderer support,
  plus verdict templating for N-way ranking (MVP keeps verdict
  simple, just for Male-vs-Female).

  Design constraint: stay loadout-list-keyed, not A/B-keyed
  (`loadouts: list[LoadoutSpec]`, pairwise-delta iteration via
  `itertools.combinations`). N=4 ceiling: more than 4 makes the
  matchup-delta table unreadable. Don't design past this.

## User-facing documentation (post-arc)

The Reader's Guide arc shipped 2026-04-23/24 — infrastructure
(`build_guides.py`, landing page, dev-count sentinels), plus five
guide bodies: How This Works / Under the Hood, Envelope Position,
Threshold Tiers, IV Flavor Guide, CD Article, Deep-Dive Scatter.
Envelope Position + Threshold Tiers are at `authorship=both`; the
others are still `authorship=ai` pending Michael review.

Open follow-ups:

- **Promote remaining guides from `ai` to `both` / `expert`** as
  Michael reviews and edits each one.
- **Round-3 screenshots** if/when reader confusion surfaces a
  specific gap (round-1 + round-2 screenshots shipped via `32fae84`
  and `e449b38`).
- **Add topics** beyond the five shipped — Michael asked that the
  topic list be a conversation at the start of the task, not a
  fixed scope. Plan a session to (a) add topics surfaced by
  an HSH Discord member / new readers, (b) reorder by current reader
  confusion, (c) decide whether related topics merge.

The IV Flavor Guide write-up is owed to an HSH Discord member per
`project_acidic_arisen_writeup_commitment.md` — promoting that
guide from `ai` to `expert` is the closing of that commitment.

## Low priority

* **ML guide "what do I get by best-buddying these?" view** — the "All
  cases" IV-compare view (shipped 2026-06-28, `b494b28`) hides
  best-buddy-conditional flips by default and badges their count
  ("N best-buddy flips hidden"). A natural follow-up is a dedicated
  summary that answers, for the user's candidate spreads, *what
  matchups best-buddying unlocks/loses* — e.g. "best-buddy 15/15/14 to
  win Solgaleo 2-1 + Kyurem 2-2; 15/14/15 gains nothing." The data is
  already there (the alt grids / sibling quadrant rows); this is a
  rendering/summarization feature, not new sim. Deferred 2026-06-28 by
  Michael ("don't want to engineer that now").

* **Team/multi-mon simulation** — currently only 1v1; real PvP is 3v3 with
  switching. Add team composition and switch-timing support. When this
  lands, honor `reset_on_switch`: Morpeko must re-enter in Full Belly on
  every switch-in (confirmed in-game 2026-06-06; see DEVELOPER_NOTES §8).
  Also port the MATCH-level 240 s clock (Michael, 2026-06-11): the real
  game's timer spans the whole 3v3, charged-move animations consume it,
  and games are genuinely won on time — see DEVELOPER_NOTES "Battle
  timeout" divergence entry for PvPoke's clock semantics to mirror.

## Backlog (someday / maybe) — see `docs/TODO_backlog.md`

The long-tail design notes / research reproductions / UI wishlist live in
`docs/TODO_backlog.md` (split out 2026-06-28 to keep this file readable in one
shot). All still open — detail preserved verbatim there. Index of what's there:

- **Policies to add** — Selective baiting, random buff/debuff modes, EV-based
  baiting, new-mechanics decision-layer re-optimization.
- **Features to add** — energy-lead axis (safe-switch / closer matchup flips;
  full sketch + empirical precedent).
- **Analysis goals** — RyanSwag-style matchup-flip annotations + wins y-axis,
  meta-wide slayer reference, SwagTips/reddit/iv-tech reproductions, the
  Tinkaton scatter-cluster + clustering-methodology investigations.
- **Slayer card UX** — signal-loss systemic audit (saturation of slayer/tier
  badges); cluster-section gating.
- **Slayer iteration cleanup** — Max-Wins column, Lurgan-as-opponent re-run,
  validation-doc reframe.
- **HTML output paths** — orphaned-artifact detector, split-moveset re-render,
  mirror-slayer table size (mechanism removed; demote-vs-optimize).
- **Dive card** — High-HP strictly-dominated-spread bug, opponent-IV
  robustness axis, signature-dedup notes.
- **Upcoming plan-mode session** — dive/article content + information
  architecture (articles-vs-dives taxonomy, card placement, ML enrichment).
- **CD article generator** — S8 envelope-annotation wiring.
- **Deep-dive narrative** — (move-display DRY lifted to Refactoring above),
  catch-phrase tier, narrative-flavor plot tiers, TOML composite categories,
  RyanSwag-style autogenerated section.
- **Reproducibility** — non-reproducible opponent data (fingerprint + logging).
- **UI / Display** — scatter color modes, pretty-print names, CLI help
  enumeration, table sorting, client-side anchor add/remove.
- **Schema simplification** — TOML simplification triggers (collect friction).

---

Historical/shipped work lives in `CHANGELOG.md`; long-tail open backlog in
`docs/TODO_backlog.md`.
