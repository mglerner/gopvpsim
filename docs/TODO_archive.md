# TODO archive -- completed pre-redive session batches

Verbatim relocation (2026-06-27) of the completed chronological session-log
that had accumulated at the top of `TODO.md` (sessions 1-4 pre-redive
fast-follow batches, the adversarial assessment batches, OVERNIGHT
2026-06-27, LAUNCHED 2026-06-25, and the ML-sweep progress-reporting work).
Nothing here is open work -- still-open residuals were hoisted into TODO.md's
'Pre-launch open items' list. Kept for provenance / root-cause history;
consult on demand, not at session startup. Newest shipped work also lands in
`CHANGELOG.md`.

----

### Pre-dive {layer}x{lens} sweep (2026-06-27 PM, session 3)

Ran the first full grid sweep (now `docs/predive_checklist.md`). It caught what
the earlier location-oriented passes missed. LANDED before launch:

- **[GATING, data] Oinkologne (Female) GL reference TACKLE -> MUD_SLAP** -- Mud
  Slap CD shipped (in fastMoves + eliteMoves, PvPoke default); the TACKLE pin was
  a pre-CD leftover from the removed CD article. `run_website_dives.py`.
- **[GATING, silent-incompleteness] ML bake failures now visible.** The ML tail
  step is WARN-not-FAIL by design, so the chain printed SUCCESS and the morning
  verifier was blind to a partial/OOM ML bake. Fixed: `overnight_redive.sh` final
  status surfaces ML failure; `verify_overnight.py` check [5] asserts every
  ML-pool species has a fresh `_iv_envelope_all9.json` + flags any ML WARN line.
- **[hardening, resource lens -> code guard] `run_iv_guides.py` concurrency
  preflight** prints `jobs x per-guide-workers` and HARD-FAILS if > physical
  cores (`--allow-oversubscribe` to override) -- the ML-oversubscription bug
  can't recur silently.
- **[render correctness] `pvp_damage` DRY/precision fix** -- `deep_dive_analysis.py`
  re-implemented damage with double-precision 1.3/1.2; now imports
  `moves.BONUS`/`STAB_MULTIPLIER` (bit-for-bit with the engine; was wrong on
  5394/5.6M boundary cases). Render-path narrative cells only; no engine-hash bump.
- **[render correctness] win-count 500 boundary unified to `> 500`** (500 = tie,
  per vendored PvPoke `BattleHistogram.js`/`Interface.js`). The Python census was
  right; the JS overlay's `>= 500` was the bug. Fixed all JS win-classification
  sites + Python `_won_set`. Render/overlay only.

FAST-FOLLOW backlog from the sweep (non-gating, render/tooling-only,
re-renderable via replay -- do NOT block launch; ~17 confirmed findings, top ones):

**Session-4 (2026-06-27 PM, Claude AFK churn) resolved most of these -- see
the commits below. Remaining open items kept at the bottom.**

- **[DONE] [med, dead affordance]** comparison pages (`compare_loadouts.py`)
  sortable-header affordance with no sort JS -- DROPPED the `sortable` class +
  its cursor/hover CSS so headers no longer signal interactivity (kept the
  `data-sort` th type-hints as latent metadata). Articles keep their working
  sorter; only the comparison path lacked the JS.
  *Enhancement follow-up (low):* articles already ship a generic
  `table.sortable` click-sorter (`generate_article.py` ~3440-3505) that reads
  the SAME `th data-sort` type-hint scheme compare_loadouts uses. Wiring it up
  for the comparison pages is a clean reuse -- ideally extract a shared helper
  (e.g. into `render_article.py`) and use it from both files rather than
  duplicating the JS. Needs click-testing of the bool/pct/num cell parsing +
  the sort-arrow CSS. Render-only.
- **[DONE] [med, silent-incompleteness]** `build_matchup_web.py` partial-matrix
  exit-0 -- now HARD-FAILS on any pool-resolution skip on a non-limited run
  (`--allow-skipped` override, mirrors `run_iv_guides.py --allow-oversubscribe`).
- **[DONE/n-a] Tinkaton GL** reference -- already handled by commit `1651217`
  (drop stale PLAY_ROUGH; track get_default_moveset). Full L4 reference-pin
  freshness re-check this session: all pins fresh or intentional variants
  (Forretress BUG_BITE variants; Mimikyu-Busted pins == base Mimikyu default;
  Sableye GL same charged-move SET in a different ORDER -- cosmetic, our sim
  baits by policy not list order). The Oinkologne/Tinkaton stale-pin class is
  fully resolved.
- **[DONE] [low] DRY/cleanup:** `LEAGUE_CP` re-declarations consolidated to the
  canonical `gopvpsim.pokemon.LEAGUE_CP` (`generate_article.py`,
  `compare_loadouts.py`). `gc_cache.py`'s `iv_envelope` iteration is
  INTENTIONAL (report-only surfacing of the legacy dir for manual pruning; the
  `if d.is_dir()` guard makes it a no-op once deleted) -- closed as not-a-bug.
- **[DONE] [test-side + broader] win-set `>= 500` -> `> 500`.** Session-3's
  "unified ALL win-classification sites" claim was FALSE (adversarial skeptic
  pass): `>= 500` (counts a 500 TIE as a win) was still live in
  `deep_dive_analysis` (find_flips, probe_tier_cutoff), `deep_dive_narrative`
  (_flavor_max_winrates, _find_losses_vs_general), `deep_dive_slayer` (4 win
  counts), `export_owned_breakdown_bundle`, `generate_article`,
  `compare_loadouts` (+ user-facing title/doc text). All unified to `> 500`;
  the two desync-prone reimplementation tests fixed in lockstep with their
  production targets. JS path was already `> 500`, so the whole surface is now
  consistent. Render/analysis-only, rides the cold pass.

**Still open (low):**
- score-key `{mi}_{mode}@51` format open-coded in Python and JS (DRY) -- NOT
  touched this session: it is a cache/render data contract, too risky to
  refactor unattended. Do it deliberately with a re-render check.
- `overnight_eta.py` doesn't model the ~7h ML tail (ETA accuracy, enhancement).
- **No shared win-predicate constant.** The `> 500` / `500 = tie` boundary is
  open-coded at ~dozens of Python+JS sites. A shared `is_win(score)` / WIN_TIE
  constant would have prevented the session-3 incomplete-unification entirely.
  Deferred (broad, cross-language touch); flagged as the real DRY root-cause.

### Session-4 adversarial round-2 (2026-06-27 PM, fresh-eyes finder fleet)

Three independent adversarial finders run over the under-covered grid cells
(each self-refuting). Results:

- **[CLEAN] L2 cache-key completeness.** Audited every key in
  `sweep_cache`/`slayer_cache`/`cache_base`/ML path. ALL complete -- every
  result-affecting input is in the key, the per-column engine stamp, the
  `required_planes` gate, or the `mechanics != 'legacy'` cache disable (verified
  wired + un-bypassable). Bug #4 (slayer focal-level-cap) confirmed fixed.
  No findings (high confidence).
- **[CLEAN, doc-only fixes landed] L1 cmp_atk migration.** The shadow-strip
  CMP migration is COMPLETE in code (all 13 order-deciding sites use
  `cmp_atk`; the 6 remaining `.atk` are damage/stat/construction). Landed: two
  stale comments that predated the fix (`deep_dive_signature.py` docstring,
  `_dp_jit.py` param comments) corrected to `cmp_atk`.
- **[FIXED] L3 orchestration F1** -- `build_website_index.py` could drop a
  rendered page (unreachable from nav) and exit 0. Now hard-fails on a dropped
  page-with-index.html (`--allow-skipped` override); the chain runs it
  un-overridden. Also dropped the stale `40 dives`/`Twenty`/`36+4` literals in
  `overnight_redive.sh`.

**Still open from round-2 (orchestration, LOW-MED -- for Michael):**
- **F2 [low, DOWNGRADED after audit]** split-moveset page absence is invisible
  to `verify_overnight.py` check [2] (it asserts present-file *freshness*, never
  a *missing* file). BUT the audited backstop holds: the split-emit loop
  (`deep_dive.py:6031-6061`) has NO try/except, so a failed `generate_interactive
  _html` (write/render error) propagates -> the dive exits nonzero -> the chain's
  `step()` is FATAL -> abort. So a *failed* split write can't silently ship. The
  only uncovered case is a moveset silently dropped from the split set -- but the
  split-page COUNT is data-dependent (surviving movesets after screening, not the
  requested `top_movesets`; see the "only one moveset surviving" warning path at
  :6065), so the finder's proposed count-vs-top_movesets check would
  FALSE-POSITIVE on legitimate screening. Net: not worth a naive count guard; if
  ever wanted, the dive must emit its actual-surviving count for the verifier to
  assert against. Leaving as-is.
- **F3 [low]** narrative auto-gen patch is WARN-not-FAIL + unverified
  (`run_website_dives.py` ~624). Low severity -- empty narrative blocks are an
  accepted ship state (human fills them) -- but it's the same WARN-not-FAIL
  shape. Optional: surface the WARN in a form `verify_overnight` scans.

### Session-4 round-3: all-Opus adversarial DRY audit (2026-06-27 PM)

A Workflow (5 finders + 2 refute-by-default skeptics PER finding, every agent
`model: 'opus'`) over the DRY angles. 17 findings -> 3 live-bugs + 9
drift-hazards (all skeptic-verified). All 3 live-bugs were the SAME issue and
are FIXED:

- **[LIVE-BUG, FIXED `bfde6ab`] win/tie boundary `>= win_threshold` survivors.**
  My OWN `ddb996a` "finish unifying win-classification" commit was incomplete --
  I grepped the literal `>= 500` and missed six per-cell sites written as
  `>= win_threshold` (variable, default 500): `deep_dive_rendering._og_win` +
  bait-diff masks, `deep_dive_analysis` aggregate_flips/find_matchup_boundaries/
  synthesize_mirror_tier per-IV count, `deep_dive.py` "Beats {opp}". They
  counted an exact-500 TIE as a win (esp. mirror diagonals). Root-caused to DRY:
  the boundary lived as a bare literal AND a param, operator hand-copied ~20x.
  Fixed via single source `battle.WIN_RATING` + `is_win()`, the 6 operator
  flips, 4 prose strings, and `tests/test_win_boundary.py` (tokenize scan that
  FAILS on any new `>= win_threshold`). Cohort-MEAN gate left as the one
  documented `>=`. Render-path only; rides the cold bake.

DRY consolidations also landed this session: opponent-slug -> canonical
`opp_slug` (`d70bd89`, latent), `ENERGY_CAP` + oracle `LEAGUE_CP` -> canonical
(`c90a3fd`).

The 9 drift-hazards are all confirmed **currently-consistent (NOT live bugs)**;
left deliberately, with rationale:

- `LEAGUE_CAPS` vs `LEAGUE_CP` (the `little` split) -- INTENTIONAL: `LEAGUE_CAPS`
  doubles as the supported-analysis-league set (`choices=list(LEAGUE_CAPS)`); a
  `little` input fails LOUD (KeyError), not silently. Optional: a 2-line comment
  at both defs documenting the split. (Would bump engine hash -- pokemon.py.)
- 9-scenario `SHIELDS`/even-shield literals open-coded at ~14 sites -- consistent;
  **skeptics explicitly warn DO NOT consolidate before the bake** (engine-hash
  bump for zero correctness gain). Post-bake cleanup only.
- score-key `{mi}_{mode}@51` (Python<->JS) -- consistent, loud failure mode,
  render-only; optional parity test (belt-and-suspenders), not a bug.
- `engine.js loadCollection` vs `match_mons` -- INTENTIONAL (two consumers: filter
  -for-export vs show-all-and-flag; shared stat kernel IS verified). Optional:
  document at engine.js:643.
- JS shadow mults -- already guarded by `test_js_shadow_constants.py`; the
  positive-contrast template. No action.

### Pre-redive adversarial assessment batch (2026-06-27 PM, session 2)

An ultracode adversarial assessment (8 fresh-eyes finders over the engine +
chain, each finding independently refuted/prioritized) was run before committing
to the hours-long cold bake. It refuted 11/13 raw findings and surfaced ONE real
launch-blocker plus several free ride-alongs; all landed, all ride the cold pass:

- **A1 [BLOCKER] SHADOW_DEF_MULT was `5/6`, not the game's value** -- fixed to
  `float32(5/6) = 0.8333333134651184` (`fb2f9de` -> `f7f9509`). `5/6` (float64
  0.8333333333) is ~2.8e-8 too large, so we dealt ~1 LESS damage to shadow
  defenders at floor() breakpoint boundaries (the deliverable). The GAME stores
  this as float32; PvPoke's `0.83333331` is an imprecise float64 transcription
  (~3.5e-9 low), so we match the GAME, not PvPoke -- a deliberate, documented
  game-over-oracle choice (DEVELOPER_NOTES "Engine constant sourcing"). Hid
  because the only shadow oracle fixture (Shadow Swampert vs Registeel) sits
  off-boundary. Also fixed a stale `5/6` copy in `deep_dive_user_collection.js`
  + added `tests/test_js_shadow_constants.py` drift tripwire.
- **B2 bandaid[910] defer-self-debuff read the wrong index** -- `cm_self_buff[
  first_idx]` -> `cm_self_buff[0]` (activeChargedMoves[0], per ActionLogic.js:929)
  (`c5c515e`). Real port bug; ZERO shipped-default impact.
- **B3 `buffApplyChance` string-compare** -- `float()`-coerced in `_priority_
  shuffle` + the bestChargedMove tie-break (`c5c515e`); same class as #7. ~Nil
  shipped-default impact.
- **ML-sweep parallelism** -- post-cache-rework each guide fans across all cores
  via `iv_sweep`, so the old concurrent-guides model (overnight `--reserve 0`)
  oversubscribed ~10x on a 10-core host (thrash + OOM-kill/missing-guide risk;
  the cache is corruption-SAFE -- atomic .npz writes, disjoint focal dirs, torn
  files self-heal as a miss -- so no wrong data, but a thrashed run could ship an
  INCOMPLETE bake). Fixed: `run_iv_guides.py` defaults to SERIAL, overnight uses
  `--jobs 1` (the GL/UL pattern) (`fd52021`).
- **UI flip "(+N more)" was dead text** -- now a real no-JS inline expander in
  all 3 contexts, with the toggle markup DRY'd into one `cover_toggle_html`
  helper + single `COVER_TOGGLE_CSS` (`85e7284`). Output-neutral (re-render
  byte-identical).
- **Duplicate `id="opp-<slug>"` anchors** -- each opponent's deep-link anchor was
  emitted by multiple sections (5 open-coded sites + 2 per-fn seen-sets) -> ~57
  duplicate ids/page (invalid HTML; browser jumps to first only). DRY'd into one
  render-scoped `opp_anchor_id()` helper + registry (reset per page in
  `generate_interactive_html`); first mention per opponent emits, rest skip
  (`fc40c17`). Net 86 ids/86 distinct, 0 dups, all 72 `#opp-` links resolve, slug
  set preserved. Render-only. "Flavor 1" (de-dup, land on first-rendered mention)
  -- see the Flavor-2 future fix below.
- **Cleanup**: deleted the stale `pogo-simulator/` husk (a 16K symlink-to-gopvpsim
  shell; completes the long-deferred `pogo-simulator -> gopvpsim` rename).

Final gate (whole batch): full suite 1100p/14xf, oracle audit clean, benchmark
3,436 sims/s.

FUTURE FIX (render-only, NOT a launch blocker -- re-renderable via replay
anytime): **`#opp-` canonical landing ("Flavor 2").** Today (`fc40c17`) a
`#opp-<slug>` link lands on the *first-rendered* mention of that opponent, which
is inconsistent across opponents (sometimes a rich `dd-opp-row` detail breakdown,
sometimes a bare name span in a coverage list, sometimes a flip-list `<li>`).
Flavor 2 = pick ONE canonical per-opponent target (prefer the `dd-opp-row` detail
when present, else the breakpoint `<li>`) so every link lands on the most useful
spot consistently. Deferred because (a) it changes nav behavior and (b) needs a
canonical-target design decision (not every opponent has a `dd-opp-row`). Links
were unused so this is low priority; do it as a focused render change + replay
re-render when convenient.

### Session-1 pre-redive batch (2026-06-27 PM) -- also rides the cold pass

(ML-sweep progress reporting also LANDED 2026-06-27: `df51527` route
iv_envelope_analysis progress through the structured logger / `3d0b2e8` unlink
stale per-guide log per run / `2d82b51` watch views surface per-worker phase /
`0a207a0` tests -- per-guide `userdata/logs/iv_guides/<slug>.log` with phase
lines, surfaced by `iv_guides_status.py` + `chain_status.py`.)

Session-1 commits (all ride the cold pass for free):
- **#2 float32 damage constants** -- DONE (`f1538ff`). STAB/BONUS/super-effective
  now use float32-truncated doubles matching the game/PvPoke. Boundary-scattered,
  no clean predicate -> this is what makes the re-dive cold (so everything else
  this session rides it for free).
- **#5 bandaid[929] no-bait swap** -- DOCUMENTED as a kept divergence (`0fcc290`);
  `docs/pvpoke_divergences.md` #6 + `tests/test_bandaid929_nobait_divergence.py`.
  Ungated on `bait_shields` on purpose (PvPoke's gated line is strictly
  dominated); NO engine behavior change. (Measured: gating would flip 284 winners,
  all in our favor.)
- **#7 `_cm_debuf_delta` dead branch** -- FIXED + vetted (`377c48e`). The
  guaranteed-self-buff arm was a `'1' == 1` str/int dead branch; now
  `float(...) == 1.0`, matching PvPoke (JS `"1"==1` coerces). Empirically +
  structurally ZERO dive impact (0/10458 cells, 0/~900k DP-decision probes);
  ultracode-vetted (oracle clean 37 divergences, suite green, bench 3,482 sims/s).
  `tests/test_cm_debuf_delta.py`. REMOVES a divergence (not added to the
  divergences doc).
- **Scanner-button render polish** -- the "Copy for IV scanner" button now also
  renders on Threshold Tier cards (`08f5c8a`) and Slayer Builds archetype cards
  (`96a1c48`), DRY'd into `_scanner_button_html` / `_cutoff_scanner_spec` helpers
  (`bd48fc9`). Render-only, no engine/cache impact.
- **Pool resolution re-checked** on the refreshed gamemaster: GL 78/78, UL 68/68
  resolve -- no silent shrinkage.

Sibling-bug status for context: **#1** (`fire_now` cmp_atk) is in `main`
(`b1b58f1`) -- the cold pass subsumes its old warm shadow-XOR re-dive plan, now
moot. **#3** (farm-down self-debuff stacking) FIXED in `main` (`7a55d43`), 0
shipped-cell impact.

Reminder: while editing engine files, run dives with `--no-sweep-cache` until
trusted (see CLAUDE.md "Sweep cache" + "Before a cold re-dive, check for a
tractable migration").

## ML-sweep progress reporting (DONE 2026-06-27 PM)

**DONE** -- shipped in `df51527` / `3d0b2e8` / `2d82b51` / `0a207a0` (see NEXT
ACTION above for the summary + verification). Original task notes kept below for
reference.

*(2026-06-27 PM, Michael)* The GL/UL dives have nice structured progress
reporting; the ML IV-guide sweeps do not -- a long ML bake runs mostly silent.

GOAL: give the ML sweeps the SAME progress reporting as the GL/UL dives, and
BAKE IT INTO THE WATCH SCRIPT so the cold ML bake is observable live during the
re-dive.

- **Match the dive's mechanism**, don't reinvent: the dives use the structured
  logger (`scripts/deep_dive_logging.py`; `docs/structured_logger_design.md`;
  CLAUDE.md "Debugging conventions") writing to a status file that the watch
  view tails. NO bare `print()` from workers (multiprocessing -- route through
  `logger.*`).
- **Watch-script parity**: the GL/UL side is watched via
  `scripts/chain_status.py` (+ `scripts/iv_guides_status.py` once the ML step
  starts), tailing `userdata/logs/...`. The ML sweep should emit
  per-guide / per-quadrant / per-opponent progress into that same surface so a
  single `watch` view covers the whole chain.
- **Start points**: `scripts/run_iv_guides.py` (driver),
  `scripts/iv_envelope_analysis.py` (per-guide sweep),
  `scripts/iv_guides_status.py` (existing ML watch view -- may already be a
  partial hook), and how the dive chain wires `chain_status.py`.
- **Why now**: do it in a FRESH session before launching the cold re-dive, so
  the ~hours-long ML bake in that re-dive is watchable instead of silent.

----

## OVERNIGHT 2026-06-27 (NOW MERGED into `main`; branch deleted 2026-06-27)

A Claude overnight session. **All five commits below are now in `main`** (the
branch `overnight/2026-06-26` was an ancestor of `main` via the cache-rework
merge, and was deleted 2026-06-27). Nothing was auto-published to the live
site -- publish is still the separate gated step. Commits:

**Done (pending your review):**
- **Mimikyu (Busted) starts-busted GL + UL dives** + the engine change they
  needed: a focal that STARTS in a terminal alt form now carries its native
  stat buffs (the Busted -1 def, which `reset_for_battle` was silently
  re-zeroing). Validated by equivalence to the PvPoke-oracle in-battle bust
  (PvPoke's *direct* `mimikyu_busted` build is the wrong oracle -- it skips
  `nativeStatBuffs`). Dives built into `userdata/website/mimikyu-busted-*`.
  `tests/test_mimikyu_starts_busted.py`.
- **Limited-mon ML IV-floor correction** (the never-ship-unflagged item
  below): `--iv-floor` flag + floor-aware renderer (no stale "12" labels) +
  `run_iv_guides.py` auto-sweeps the 6 untradeable mythicals
  (Marshadow/Meloetta/Jirachi/Keldeo x2/Zygarde-Complete) at 10/10/10.
  Eternatus is now also in the floor-10 set (Michael 2026-06-27: rare enough
  to count as special, trade status irrelevant). Floor-12 path verified
  byte-equivalent; floor-10
  render validated synthetically.
- **Engine bug #1 [HIGH] FIXED**: the `fire_now` double-fire CMP gate used
  shadow-boosted `.atk` (missed 10th site of the 2026-06-13 cmp_atk
  migration) -- flipped real winners. Oracle-verified, `tests/test_fire_now_cmp_shadow.py`.

**Running when you wake:** the full ML re-bake (`run_iv_guides.py`, 61 guides
= 55 @ floor 12 fresh cmp-JS + 6 @ floor 10) -- ~94 min/batch, so it runs
into the day; whatever's done is in `userdata/`, unpublished.
**Blast-radius note:** the bake started on the PRE-bug-#1 engine, so any
Master SHADOW guide it produced may carry the #1 behavior -- re-bake the
shadow ML guides after you accept the #1 fix.

**Bug-hunt follow-ups (open) -- full report `docs/reviews/2026-06-27_engine_bug_hunt.md`:**
- **#2 [MED] FIXED 2026-06-27 (`f1538ff`)** -- damage formula now uses the
  game's float32-truncated `BONUS/STAB_MULTIPLIER/SUPER_EFFECTIVE` constants
  (was exact `1.3/1.2/1.6` -> off-by-one on breakpoint boundaries). This is
  the boundary-scattered fix that forces the COLD re-dive; everything else
  this session rides it for free.
- **#3 [MED] FIXED 2026-06-27** -- farm-down now stacks self-debuffing moves
  (PvPoke ActionLogic.js:399-405 `energyToReach` gate). Adversarially verified
  (suite 1075p; 0/2160 default-meta cells changed; 162/162 firing configs +
  Malamar single-best match PvPoke; 378-cell scan moved 23 toward PvPoke, broke
  0). Zero impact on shipped default-moveset dives. `tests/test_bug3_farm_stack.py`,
  DEVELOPER_NOTES "#3 ... RESOLVED".
- **#3-followup [NEW, open]** the bug #3 verification's 378-cell both-self-debuff
  oracle exposed ~117 PvPoke divergences (7 winner-flips) on the BROADER
  both-self-debuff population (Lurantis LEAF_STORM+SUPER_POWER vs Cresselia,
  Blaziken BRAVE_BIRD+OVERHEAT vs Registeel, ...) that PRE-DATE #3 (already
  disagreed under the old engine, so independent of the stacking fix). Likely
  the near-KO-DP / `_optimize_move_timing` self-debuff-timing deviation cluster,
  possibly an uncharacterized separate issue. Investigate: re-run the
  both-self-debuff grid old-vs-new to confirm pre-existing, localize via
  `--trace-dp`, then decide keep-as-divergence (CLAUDE.md policy) vs fix. These
  are non-default movesets, so low ship-priority.
- **#4 [MED]** slayer disk-cache key omits the focal level cap -> stale
  cross-`--max-level` hits in Master mirror-slayer (silent-wrong output).
  Clean fix (key field + `CACHE_VERSION` bump), left for you to schedule.
- **#5 [MED/LOW]** `bandaid[929]` stack-switch missing the `bait_shields`
  gate -- decide gate-to-match vs document-as-divergence.
- Latent: `_cm_debuf_delta` `'1' == 1` str/int dead branch (cosmetic in
  tested cases, worth a cheap fix).

**Deliberately deferred:** the gobattlekit bitmask exporter (mobile-format
design choices better made with you awake).

## LAUNCHED 2026-06-25 02:10: the big re-dive (thread 2 / ship)

The overnight chain (`overnight_redive.sh`) was launched 2026-06-25 02:10,
all-cores, detached via `nohup`. It runs the 40 dives -> comparison pages ->
GL matchup web -> ML IV-guide bake (master_top60, ~7h cold) -> index ->
link verify. Realistic wall-clock ~14-18h. Prep commit `4f9846c` (NOT pushed).

Launch readiness was assessed by an adversarial workflow (verdict: NO-GO as
staged -- the chain would have run to completion but silently shipped wrong
output in 3 ways). What the prep session actually did to fix each gotcha:

1. **ML guides not in the chain -> FIXED.** Added `run_iv_guides.py
   --no-index-refresh --reserve 0` as a failure-tolerant tail step (runs
   OUTSIDE `step()` so one bad guide can't abort the final index+verify),
   sequenced before the index rebuild so the new Reshiram (Shadow) guide gets
   indexed. NB this is a second ~7h COLD job (the fresh pull orphaned the
   won-set caches); a cache-migration tool would NOT help (dives bypass the
   sweep cache under `--compare-energy`, and the guide's dominant cost -- the
   `score_set` rec-sweep -- is uncached by design; a naive re-key would also
   ship stale damage for rebalanced moves).
2. **Oink pages -> DELETED (not banner).** Decision flipped 2026-06-25 from
   "archive with banner" to "delete from the site" (no banner mechanism
   existed; Michael doesn't need the pages). Removed Steps 2 & 3 from
   `overnight_redive.sh` and deleted the 3 stale built dirs
   (`oinkologne-great-league`, `articles/oinkologne-cd-2026-05`,
   `comparisons/oinkologne-male-vs-female`). Female Oink dive stays (in DIVES).
   FOLLOW-UP: the orphaned source TOMLs (`articles/oinkologne-cd-2026-05.toml`,
   `comparisons/oinkologne-male-vs-female.toml`) and `build_guides.py`'s
   `oinkologne-great-league` reference are now dangling -- cosmetic cleanup,
   not a chain blocker.
3. **Stale "20 dives" label -> FIXED** (header + step label now say 40).
4. **Cradily UL gap -> ROOT-CAUSED + FIXED, and a SECOND species found.** It
   was NOT a shadow data gap: the bare names `Cradily` AND `Golisopod` resolve
   to GL-only clone slugs (`cradily_b` / `golisopodsh`) that are absent from UL
   rankings, so `get_default_moveset` silently dropped them from every UL dive
   (the prep's pool union missed both). Pinned the canonical UL default
   movesets inline in `ul_top60.txt` (`Cradily | fast=ACID |
   charged=ROCK_TOMB,GRASS_KNOT`; `Golisopod | fast=FURY_CUTTER |
   charged=X_SCISSOR,AQUA_JET`). (Aegislash was later removed from this pool
   entirely 2026-06-25 — not UL-viable; file renamed from
   `ul_top60_plus_aegislash.txt`.) UL pool now 68/68 resolve.
   FOLLOW-UP (deferred): make `species_id` league-aware so it prefers the
   canonical slug when the GL clone is absent for that league -- then drop the
   inline overrides. Cosmetic nit: the override labels these "Cradily (Acid /
   Rock Tomb+Grass Knot)" in UL tables (consistent with existing variant style).
5. Energy-default bypasses the sweep cache (full sim) -- expected cold-run cost.
6. **Morning check:** `python scripts/verify_overnight.py` (chain status,
   freshness, ship gates). Watch live: `watch -c -n 5 scripts/chain_status.py
   --chain overnight` and `scripts/iv_guides_status.py` once the ML step starts.
   Status file: `userdata/logs/overnight_status.txt`. Publish AFTER review via
   `scripts/publish_website.sh --push` (push still nod-gated).
   FOLLOW-UP (not done, low risk now that UL resolves 69/69): extend
   `verify_overnight.py` to assert UL opponent counts so a future silent pool
   shrink is caught the morning after, not shipped.

----

# Groomed out of TODO.md 2026-08-08 (completed 2026-06/07 narratives)

Moved verbatim per the live-backlog convention; open residues stay in
TODO.md. CHANGELOG '2026-07-03' carries the summary entry.

## hunt2 round-2 fixes + engine-batch merge + post-merge (2026-07-03)

**FIXED on main (Opus, 2026-07-03) — the non-engine-batch, non-contested slice:**
- **F1** (`57137e4`): `migrate_cache.py` `used`-set now unions form-change
  swapped-in moves via new single-sourced `formchange.form_change_swapped_moves`;
  regression test builds a minimal one-move gm delta. **Adversarially verified
  COMPLETE**: the only battle-time move swaps are Aegislash (fast) + Morpeko
  (charged); Mimikyu swaps none; no other foreign move-read exists in the four
  engine files; no wrongly-blessing scenario remains. NB: the helper lives in
  `formchange.py` (engine-hash file) -> F1 bumps the engine hash on main by a
  behavior-neutral function; harmless on the cold machine, flagged for the
  hunt2 merge (fresh final hash; different regions, should merge clean). No past
  migration was tainted (the one prior `--from-gamemaster` run, skarmory_mega,
  was purely additive).
- **F2 doc** (`57137e4`): the `self_debuff_either_side` static-flag caveat is
  now documented in the predicate docstring + a Registeel FB+ZC test assertion
  (measured harmless in `69876ee`; the "AURA_WHEEL is the only swap" line is
  corrected). Trap for the next predicate author recorded, not silently false.
- **BP-1** (`2931d1d`): `breakpoints()` returns `[]` for power-0 moves instead
  of ZeroDivisionError (was silently dropping every anchor for the whole
  Aegislash-Shield GL dive). **BP-2** (`cc70593`): CLI now forwards
  `--shadow-atk/--shadow-def` into the damage math (was header-only).
- **JIT-COV-1** (`22c0a0b`): 2 settrace-verified parity matchups now cover the
  ttl-cmp-bonus / dedup-keep / atk-stage-clamp+4 kernel branches (were unpinned).
- Full suite after: 1216 passed / 14 xfailed / 2 pre-existing new-machine
  fixture failures (`test_export_owned_breakdown`, missing `userdata/website`).
- **Out-of-scope note surfaced by the F1 verification:** `anchors.py` calls
  `get_moves()` but is NOT in `sweep_cache._ENGINE_FILES` — a separate
  engine-hash-coverage question (anchors feed breakpoint analysis, not the
  cached 1v1 column scores), worth a look but not a delta hole.

**hunt2 engine batch MERGED to main (`2a63b65`, 2026-07-03, Michael-approved):**
NB-1 (selection freeze) + FC-1 (Aegislash revert energy) + OMT (turns_planned
divisor) + would_shield-as-documented. Fast-forward from `a86b0fd`; full suite on
the merged tree 1234 passed / 14 xfailed / 2 pre-existing fixture failures.
battle.py byte-identical to the audit-passed hunt2 engine. OMT was the
cold-forcing change (touched set not statically characterizable), so the merged
engine needed a cold re-dive — **DONE: the 2026-07-06/07 bake was that re-dive**
(bake tree `753d3ba` contains `2a63b65` + `02627fe`; verified + closed out
2026-08-04, CHANGELOG). Everything else in the batch rode it for free,
including JIT-COV-2 below.

**DONE post-merge (Opus, 2026-07-03):**
- **JIT-COV-2** (`02627fe`): inline comment at the JIT `final_state = _DPState(0,
  ...)` site — `energy=0` is inert (no consumer reads `.energy`). Comment-only on an
  engine-hash file; rides the OMT-forced cold re-dive.
- **PROP-1** (`fe2c443`): DEVELOPER_NOTES "Key implementation details" now documents
  the exact-`cmp_atk`-tie -> player-index (p0-first) resolution as a PvPoke-faithful
  known property.
- **anchors.py `_ENGINE_FILES` question** (was the F1 out-of-scope note): checked —
  **BENIGN**. Engine-hash caches store only sim column scores; anchors.py feeds
  breakpoint analysis and is strictly downstream (no engine file imports it, anchors
  recompute fresh each dive), so it needs no engine-hash coverage. Caveat: replay
  blobs / gobattlekit thresholds exported before BP-1 carry old anchors by design —
  re-export any shipped ones that matter.

## Top-N Phase 1 + Equinox Cup pilot Phase 2 (shipped 2026-07)

**Phase 1 (client-side opponent filter) SHIPPED** (`b8b561e`, `f5741a3`).

**Phase 2 (Equinox Cup pilot) SHIPPED** (gopvpsim `aa8dac8..3c153fb`;
gobattlekit `0c1bd5c`). Implemented + verified 2026-07-03; confirmed
2026-08-04 as pushed (`3c153fb` is an ancestor of `origin/main`) and live
(`pogodives.com/cups.html`, `/corviknight-equinox-cup/`,
`/clodsire-equinox-cup/` all HTTP 200) -- this block previously read "NOT
pushed / NOT published, pending review" and was stale. Done: cup rankings
loader (`data.py`); `recipe_equinox_great` +
committed `opponent_pools/equinox_great.txt`; `--cup` labeling overlay
(cup-sourced oppMetaRank/rankSnapshot, cup-named title/card + archive banner,
replay-blob `cup` marker); flat `<species>-equinox-cup` slugs + separate
archive-friendly `cups/index.html` + "Limited Cups" card; gobattlekit
threshold-export collision guard (cup blobs -> `<species>_<cup>.toml`);
`verify_overnight` `*-cup` coverage. Five pilot dives run locally cache-ON
(Corviknight/Mantine/Mandibuzz/Toucannon/Clodsire); page-render 67/67,
index-presence + bundler dry-run green, suite 1245 passed. Audit report:
`~/coding/reports/gopvpsim-equinox-cup-pilot-2026-07-03.html`. The cup-index
live/archived status is auto-derived from PvPoke's `formats[].showFormat` on
each build (no hand-maintained rotation list); a rotated-out cup auto-flips to
"archived snapshot". Phase 3 (more cups,
legality-filter eval, app-side cup toggles, mega engine) remains -- see the
plan doc.

## gobattlekit bitmask exporter shipped detail (2026-06-29)

step 1, the bitmask exporter, SHIPPED
  2026-06-29 in `c1ea231`: `bitmask_from_dive` + `--bitmask` on
  `scripts/export_owned_breakdown_bundle.py`, with roundtrip + size tests in
  `tests/test_export_owned_breakdown.py`; the top-K-stat-product bake was a
  DEAD END — those spreads all give up nothing; owned mons have arbitrary
  IVs)

## limited-availability IV floors: resolved slice (2026-06-28/07-03)

DONE (2026-06-28) for the known slice: the seven species in
`run_iv_guides.FLOOR_10_SPECIES` (Marshadow, Meloetta (Aria), Jirachi, Keldeo
(Ordinary), Keldeo (Resolute), Zygarde (Complete Forme), Eternatus) are reswept
at the 10/10/10 research floor; their envelope JSONs span iv 15..10 and their
rendered guides carry the floor-aware "covered" banner (the never-ship-unflagged
FLAG is resolved for them). The enumeration research ran 2026-07-03
(adversarially-verified deep-research sweep):
`docs/reviews/2026-07-03_limited_availability_iv_floors.md`. Headlines: all
seven existing floor-10 assignments CONFIRMED; NO new species verifiably needs
adding; Melmetal is explicitly NOT limited (Mystery Box is indefinitely
repeatable). Michael RATIFIED the no-change verdict 2026-07-03. The
SHADOW-legendary gap was CLOSED 2026-07-03 (Opus, deep-research pass, appended
to the same doc): 12/12/12 safe for all 17; "1/1/1 shadow floor" is folklore
(real floors 6/6/6 Giovanni / 6/6/6 Shadow Raid); none genuinely one-shot.

## guides staleness-audit detail (2026-07-07)

43 confirmed findings applied -- reference-dive drift from the 2026-06-25 Male->Female repoint, renamed sections, swapped-tint / inverted-axis errors, the per-kind auto-anchor gating description; all factual, voice-preserving.

## August 2026 arc: Thievul CD / Cramorant / Worlds refresh (archived 2026-08-27)

Verbatim relocation of the shipped-narrative blocks that had accumulated in
TODO.md across 2026-08-15..27 (Thievul CD publish, the Cramorant
port/campaign/publish, the two Worlds sections). Compact dated records live
in CHANGELOG 2026-08-15..27; still-open residuals were hoisted into TODO.md's
rewritten Thievul / Cramorant / Worlds sections. Nothing here is open work.

----

## Thievul CD — dive PUBLISHED 2026-08-15; residue only (CD is Sun 08-16)

Dive shipped and live-verified at pogodives.com/thievul-great-league/
(4 pages: landing = SP / Icy Wind + Play Rough, the 62W-25L 1-1 build;
pre-CD reference SP / NS+PR rendered as m3). Plan + verified numbers:
`docs/thievul_cd_plan.md`. **The CD article was DROPPED by Michael's
decision 2026-08-15** — the `thresholds/thievul.toml` article slug
stays pre-registered but inert (the renderer only emits the link when
the article dir exists). **CD-day addendum (2026-08-16): the Thievul-vs-Licki IV-robustness
analysis SHIPPED** -- full 4096x4096 joint IV grids vs Lickilicky
(primary; 4 moveset/bait grids) and Lickitung (secondary), published as
`thievul-lickilicky-robustness.html` + `thievul-lickitung-robustness.html`
with an index card. Pipeline + contract: `docs/thievul_licki_analysis.md`
(pipeline: the generic `joint_iv_*` kit since 2026-08-19 -- `pairs/thievul_*.toml`; data in gitignored `userdata/thievul_lick*`).
Post-publish residue: (a) RESOLVED 2026-08-19: Michael okayed
committing the CD-day poke_genie fixture (commit 1b5ce69); (b) the
pinned gamemaster cache TTL-refreshed to `e6050f77bf06` during the
session (disclosed on-page; re-pin from pvpoke `f60a41199` before any
Worlds re-render, per the Worlds NOTE above).
Residue: (a) Michael's reply to u/LeansCenter
on the r/TheSilphArena launch thread (bullets drafted in-session
2026-08-15: 44W-44L -> 62W-25L at 1-1/rank-1 IVs/88-mon pool; IW+PR
beats PvPoke's NS+IW default by ~14 wins; PvPoke overall GL rank
122 -> 41); (b) Michael's HSH discord message
(`docs/hsh_message_notes.md`); (c) post-CD cleanup: delete the
`[cd_prep]` table once the un-pinned gamemaster stably lists Icy Wind.
CONFIRMED CAUGHT UP 2026-08-24 (live gamemaster lists Icy Wind for
Thievul; the 4 injection guards in test_worlds_bake_guards.py now
auto-skip on a caught-up gamemaster and re-arm under the Worlds pin).
KO-EDGE "DIVERGENCE" RESOLVED 2026-08-27 (adversarial
investigation): NOT an engine divergence. Our step-3-before-step-4
ordering IS PvPoke's priority scheme (due fast +20 > charged 10-15 >
floating fast -20; Battle.js:388-408/834-843), and given the same
action set the engines agree cell-for-cell (1,089 verified cells,
GL+UL top-16 x 9 shields). The 668-vs-662 gap is a sandbox-link
ENCODER artifact: timeline_to_actions (scripts/pvpoke_sandbox.py)
only emits charged moves that RESOLVE, so a decided-then-CANCELLED
charged move (CMP loser KO'd, etc.) leaves no action and PvPoke's
sandbox substitutes a phantom due fast on the KO turn. Scripting the
cancelled move (or a `wait`) makes PvPoke reproduce our score exactly
-- 7/7 mismatch cells. The 4 shipped showcase links are clean
(cancel_gap 0, byte-exact). No engine change; three-question test
moot. TWO TOOL-LAYER FIXES QUEUED:
(a) encoder blind spot -- either log cancelled charged decisions in
the timeline (display-only battle.py edit; the engine-hash bump
migrates via a lambda-False fully-blessing predicate, precedent
neutral_batch_20260810) or emit a final-turn `wait` in
timeline_to_actions. This is a verify_url publish-gate soundness
issue, not just cosmetics: 101 gap-cells matched by luck and would
ship links replaying a slightly different fight. Pin Cramorant/
Lapras UL 1-1 at 662 in tests/test_pvpoke_sandbox.py (no
cancelled-charged coverage today).
(b) rating-formula bug in all three Node harnesses
(pvpoke_url_run.js:174, pvpoke_sandbox_driver.js:120,
pvpoke_trace.js:315): they use the Ranker.js formula
floor((health+damage)*500) where the battle page (and our
pvpoke_score) uses floor(500*damage + 500*health) (Pokemon.js:2124);
sum-then-scale lands 1 low on exact fractions and produced the only
2 non-encoder mismatches in the sample (Forretress vs Corsola-G /
Clodsire 2-0, spurious 1-point oracle "divergences"). Fix the
formula + the misleading Ranker.js comments.
POST-WORLDS (after 08-30): retire cd_prep + the worlds_meta
`injected_move_ids` declarations + those 4 guards together.

----

## Cramorant (PUBLISHED 2026-08-27; residue on the rebalance + post-Worlds lists)

The Gulp Missile engine port (pvpoke 78c64048a) landed 2026-08-24 with
81 oracle-exact fixture cells + a 36-cell audit extension and a 52-agent
adversarial review (all 19 confirmed findings fixed same-day; record in
DEVELOPER_NOTES "Form change gotchas" item 5). Queued next, in order:

1. **Sweep-cache migrations — DONE, cache fully warm 2026-08-27.**
   Both port legs ran (verified 2026-08-27 from cache-state footprint:
   zero columns at the old stamps + the port predicate's exact
   Aegislash deletion pattern; the invocations themselves were never
   logged), the sheet-v4 bless ran 08-26 02:15, and the final leg
   (`--from-engine 03aff90d1e71 --predicate
   pogodives_sheet_v5_20260826`) was applied 2026-08-27: 144,336
   blessed / 0 re-sim. All 153,376 columns now stamp engine
   bff4191c3cfe + gamemaster 1398b001cf86. NB the port predicate
   emptied the 6 Aegislash focal dirs (meta.json only) — the next
   Aegislash dive is a cold bake.
2. **GL + UL dives**: `run_website_dives.py cramorant` (registry entries
   added; detached; form change -> per-IV sims, Aegislash-slow). LOCAL
   render only -- publishing needs Michael's explicit go, as always.
3. **Policy campaign** (Michael 2026-08-24, standing resource
   authorization): three tiers -- PvPoke default (shipped), never-bait
   (the dives' standard `--bait both` axis), and the **"PoGoDives
   strat"** overlay (`pogodives_dp`/`pogodives_shield`: tuned Cramorant
   cases, byte-identical `pvpoke_dp` fallback for every non-Cram
   situation, test-pinned; future non-Cram cases land one evidenced
   entry at a time). Full plan: `docs/cramorant_policy_plan.md`.
   **ROUND 1 RAN 2026-08-24 overnight** -- 80-variant grid x 4 opponent
   models x 4 IV spreads, 4-analyst + 2-skeptic adversarial workflow;
   synthesis: `docs/validations/cramorant_policy_lab_2026_08_24.md`.
   FROZEN (Michael 2026-08-25): dive gate 1.5 -> 3.0, HP gate 1.3,
   delay-Gorging off, ADAPTIVE tank lead40 (the round-5 rule that
   dominated both static tank picks; writeup addendum 2). The old
   1.4-vs-1.8 fork is superseded. Adaptive-rule inputs are
   constrained to dedup-signature functions (pinned in the plan doc).
   **OVERLAY LANDED 2026-08-25** (pogodives_dp/pogodives_shield,
   per-side marking, adaptive rule threaded into decision AND model,
   lead40 CONFIRMED on the threaded engine -- writeup addendum 3;
   cache key normalization primitives in sweep_cache with the registry
   pinned to the engine-hashed battle.py). RENDER SIDE SHIPPED
   2026-08-25 (b67b8d4 sweep/cache consumer wiring + 744c4a5 --policy
   axis & Strategy dropdown; verified 2026-08-27 live on the published
   pages — both tiers baked, PvPoke tier is the JS default).
   Round-6 discovery (IV-/opponent-dependent
   thresholds) is QUEUED FOR THE NIGHT OF 2026-08-25 (Michael's go):
   chain = current policy-both bake finishes -> GL replay re-render ->
   build mechanism-derived discriminator variants in the lab ->
   league-crossed holdout runs (tune GL/validate UL and vice versa, +
   IV spreads) -> adversarial analysis workflow -> verdict (either an
   evidenced refinement, which re-bakes the pogodives columns, or a
   confirmed-final lead40, which unblocks publish + article). Inside
   the pinned dedup-input fence; publish/article wait on this verdict.
   ROUND 6 CLOSED 2026-08-25 (writeup addendum 4): nothing ships;
   lead40 stands as the chosen frontier point. PUBLISH/ARTICLE
   UNBLOCKED. Before any public surface carries a "hard counters"
   list: use the LEAD40-derived set (UL Giratina-A both flavors, UL
   Shadow Hydreigon, GL Shadow Lapras; + persistent GL Sliggoo/
   Grumpig, UL Shadow Feraligatr/Walrein, GL Jumpluff) -- the old
   "five losers" roster was static-tank-era and names a species that
   does not lose under the shipped rule.
   **STRICT-BAR SHEET 2026-08-26 (supersedes the uniform lead40 rule;
   commit 8fc5764)**: Michael's overnight bar -- every start scenario
   `>= 0` on BOTH mean rating delta and net flips vs plain PvPoke, per
   league x opp-IV mode x bait. The uniform rule failed 5 scenario
   cells; `_POGODIVES_SHEET` (per-START-scenario rows: CMP/DPT/
   cheap-energy gate conditions, lead/cheap tank rules, 2v0 + 2v1
   exempt) passes everywhere -- full record:
   `docs/validations/cramorant_strict_bar_2026_08_26.md`. Any
   counters list derived pre-sheet needs re-deriving from the
   rebaked tensors. SHEET v3 FINAL (commit 90d8811, certified
   360/360 cells at full 4096-IV resolution over ALL 5 movesets x 2
   leagues): the 2v1 hole was closed by the ready-nuke gate (worst
   slice +2,220 net / +1.17); the skeptic round then caught a v2
   violation on the gate-inert Dive+Surf build and v3 made 2v2
   gate-only. OPEN VALUE (next campaign): UL Dive+Surf 2v2 under the
   OLD tank was +15-21k flips at passing rating; a per-build tank
   discriminator would recover it (sheet ships zero there). EDGE
   constants (0.022 DPT, 1v0 aggr 2.0, 2v1 dpt_max 0.0155, 55-energy
   one-opponent patch) are disclosed in the validation doc and on the
   rebalance re-verify list -- re-verify at FULL resolution with a
   worst-slice margin target of +0.5.
   STRATEGY ARTICLE (Michael 2026-08-26): rendered by
   `scripts/render_pogodives_strategy_article.py` (AI-drafted at
   Michael's direction; reviewed — final authorship "both", published
   2026-08-27) to userdata/website/articles/cramorant-pogodives-strategy/,
   linked from both dives via replay-rendered article_slug injection.
   DEBT: the slug's durable home is a thresholds/cramorant.toml
   [Cramorant.article] table -- until that file exists, a from-CLI
   rebake drops the dive->article link and the replay-injection step
   must be re-run (the scratchpad wrapper is trivial to recreate: load
   blob, set state['article_slug'], render_dive_html). TRAP (hit
   2026-08-26 ~05:10): the wrapper must use the NEWEST replay blobs --
   an older-vintage blob silently regresses the rendered tensors to
   the earlier engine's scores (the v3-blob slug render overwrote the
   certified v4 pages and contaminated the article's numbers until
   caught by a hero-number diff). Pick blobs by mtime, or assert the
   blob postdates the last bake.
   REBALANCE NOTE (Michael 2026-08-25): a big move rebalance is
   expected ~2 weeks out (post-Worlds, the usual pattern). When it
   lands: gamemaster-delta migration as usual, PLUS re-run the
   policy-lab verification corpus (~10 min) -- the strat's fitted
   constants were tuned on pre-rebalance move data. This is also the
   standing argument for mechanism-not-names round-6 discriminators
   (they re-derive from the new numbers at battle time).
4. **Upstream bug-report candidates** (pvpoke): the two `move.moveID`
   typos (ActionLogic.js:368, :1239 -- the latter makes opponents never
   shield a lethal Dive, plausibly inflating published Cramorant
   scores; H4 in the plan doc measures it). Draft after the campaign's
   H4 numbers exist; follows the docs/pvpoke_bug_reports.md conventions.

5. **Dive-page all-scenarios grid (Michael 2026-08-25, design
   agreed, timing open):** a "Show all shield scenarios" checkbox after
   the moveset title on dive pages -- default off; on first toggle,
   lazily render a 3x3 small-multiples grid of the main scatter (one
   panel per shield scenario) from the ALREADY-EMBEDDED per-scenario
   SCORES arrays (no resim, no state change -- the main plot/cards/
   analysis do NOT re-render). Simplified panels (category colors, no
   anchor overlays/tooltips). The panel matching the scenario dropdown
   gets a black-border highlight (CSS toggle synced to the dropdown);
   clicking a panel sets the dropdown (user-initiated full re-render,
   acceptable). Precedent: the joint-IV grid9 views; motivation: the
   2-2 Peck/Dive+Fly spread-fan is invisible without clicking through
   scenarios. Render-side only; independent of the strat work; its own
   small session (touches deep_dive.py control markup +
   deep_dive_engine.js -- keep outside the gives-up REGION_SHA pin).

6. **Cramorant strategy article pair (Michael 2026-08-25, queued
   post-sim-work):** a short article on (1) playing Cramorant and (2)
   playing AGAINST Cramorant. The lab campaign is the evidence base --
   candidate data-backed content: dive-early evidence (the 1.5-vs-3.0
   gate numbers, the Kingdra exception), the prey-tank rule + the
   "tank unless clearly ahead" adaptive result, the shield-economy
   structure (better with shields on the board, the shield-ahead tax),
   missile HP-breakpoint family (floor(15%*maxHP)+1 steps); vs-side:
   energy stacking, don't-shield-weak-hits, the five hard counters
   (Shadow Shelgon / Giratina-A / Shadow Hydreigon / Shadow Lapras),
   and the CAREFULLY-CAVEATED withhold finding (our crude withhold
   counter-policy BACKFIRED -- baseline Cramorant won MORE vs
   withholding opponents, +628 vs +233 W-L -- interesting but the
   policy was simple, don't oversell). TONE (Michael 2026-08-25, saved
   as feedback-pvpoke-tone): warm toward PvPoke on all public surfaces
   -- present our strat on its own merits with a small, kind "how this
   differs from PvPoke's sims" section; no "wrong/bug/beats" framing
   (internal docs stay precise). SHIP-MODE POLICY applies:
   narrative TOML blocks are Michael's prose (or honest auto-gen
   templates); Claude supplies verified bullets + data sections only,
   like the Discord-bullets pattern. Vehicle: the standard
   articles/*.toml + render_article.py pipeline.

ACCEPTED TEST DEBT (per policy, recorded): (a) the dive-ASAP gate's
fresh-vs-frozen `move.damage` divergence (documented at the rule in
battle.py) has no discriminating test -- needs a post-missile-debuff
re-dive scenario where the two damage bases differ; write it if such an
oracle cell ever drifts. (b) The opponent-pool question -- whether
Cramorant (GL rank 13) enters `gl_top50_plus_cs.txt` / `ul_top60.txt`
as an OPPONENT for other species' dives -- is a Michael curation call;
until then no shipped dive sims against it.

**PUBLISHED 2026-08-27 (Michael's explicit go)**: full site push to
pogodives.com -- both Cramorant dives (sheet v5 tensors, blobs
20260826_124234/140322), the strategy article (final authorship
"both" after Michael's review; 4 verify_url-gated sandbox showcases),
the site-wide all-scenarios checkbox, and the frozen Worlds surfaces.
Ship gates all green (verify_worlds run from the worktree under the
pinned gamemaster; live gamemaster restored + hash-verified after).
Sheet v5 is now recorded in the validation doc, incl. the
blob-vintage rule that caught a same-day v4 rollback. Remaining
Cramorant work is only what the lists above already carry: rebalance
re-verify, the UL Dive+Surf 2v2 open value, the article-slug durable
home, and the KO-edge tool-layer fixes (encoder + Node rating
formula; see the resolved note above -- not an engine divergence).

----

## Worlds robustness deep dives -- IN PROGRESS (session started 2026-08-19)

**DONE 2026-08-27 (~04:30): Greninja + Annihilape are in the matrix,
verify_worlds fully GREEN** (555 pair pages, 0 deferred; commit
31a7361). Executed from a vintage-pinned worktree at 6a7e534
(gopvpsim-worlds; engine 5839391a7596 / gm 8f1d6cca5c0f) -- the
Worlds surface is deliberately FROZEN at the pre-Cramorant engine
until after Aug 30 (the port changes aegislash_shield modeling; 161
measured cell flips vs Shadow Sableye; cold rebake = 57h). WHILE THE
GAMEMASTER PIN IS UP (~/Documents/gopvpsim_cache, 24h TTL -- re-cp
from userdata/gamemaster_vintages/ each session): no Cramorant sims,
and 63 Cramorant-family test failures are expected pin artifacts.
POST-WORLDS: restore the live gamemaster [DONE 2026-08-27, hash
1398b001cf86 verified], remove the worktree, re-green the fast tier
[fast tier green 2026-08-27 under the live gamemaster], and decide
whether to fold Aegislash's engine-fix into a Worlds rebake.
SEQUENCING NOTE (found 2026-08-27): `verify_worlds.py` FAILS from
main on all six stamps (engine, gamemaster, and both code stamps
drifted) and is ship gate #5 inside `publish_website.sh`, which
re-renders every Worlds surface before rsync — so ANY site publish
from main is gate-blocked until the Worlds surfaces are retired from
the publish path or rebaked; the pinned worktree is currently the
only tree that greens the gate, so remove it only AFTER that
decision.
LEGALITY INPUT for that decision (verified 2026-08-27, Play!
handbook rule: new species/moves eligible the second Tuesday after
release): Cramorant debuted Tue 08-18 (Water Festival) -> eligible
09-01 -> NOT Worlds-legal, so it can never enter the Worlds meta and
the rebake question is purely Aegislash sim fidelity; if the surface
retires after 08-30 the rebake case is weak. Thievul's Icy Wind
(08-16) -> eligible 08-25 -> legal, meta.toml's conclusion stands. Findings for editorial use (durable copy:
~/coding/reports/gopvpsim-worlds-2026-refresh-2026-08-27.html; the
scratchpad originals are session-lived): core_breaker_scan.md (top-5: Medicham, Azumarill,
Guzzlord, Aegislash-S, Mantine -- Mantine is the HSH-shaped headline,
out-breaking Greninja 2:1 IV-robustly; Greninja ranks 27/35 as a
core breaker, its case is the energy-lead snowball; Annihilape 9th,
#1 on the strict tier) + hsh_greninja_verification.md (5/6 breaks
confirmed, Tinkaton refuted, energy leads convert losses).
EDITORIAL DECISION (Michael 2026-08-27, recorded here from session
memory): the Worlds Discord post is SKIPPED — do not re-pitch
`docs/worlds_discord_bullets_draft.md` (header-marked SKIPPED; its
33-entry/528-pair numbers predate the 35-entry matrix anyway). The
surviving lead is a Corviknight vs Shadow Quagsire per-spread scatter
for r/TheSilphArena — OPEN QUESTION for Michael before drafting:
which scenario? (memory says the 2-2 scatter; the original reminder
pointed at 0-shield; re-verified data shows real structure in both
0-0, win_frac_all 0.809, and 2-2, 0.86, while 1-1 is near-hopeless
at 0.004).
ORIGINAL BRIEF (Michael 2026-08-26): HSH posted a Worlds-predictions video; one call is Greninja
making day 2 as a core breaker (breaks Shadow K9 / G-Corsola /
Lickilicky / Tinkaton / Thievul cores; main meta weakness Mantine; an
energy lead lets it run away with games). Tasks: (1) add Greninja to
the Worlds matrix; (2) add Annihilape (likely meta); (3) run our own
core-breaker scan -- do WE have HSH-style predictions (species that
break several popular cores at once)? The matrix + shortlist tooling
(`worlds_shortlist.py`, joint_iv kit) is the machinery. Reminders:
community-claim discipline (pin HSH's exact movesets/IVs and reproduce
his claim before heavy compute) and the standing Worlds gamemaster
re-pin (pvpoke f60a41199) before ANY Worlds render -- the cache is on
the Cramorant vintage.

The queued session ran 2026-08-19: shortlist SHIPPED
(`scripts/worlds_shortlist.py`, 455 amber pairs by combined usage, full
table `userdata/worlds_shortlist.md`); reuse-plan S1 COMPLETE (the
`joint_iv_*` kit replaced `thievul_licki_*`; acceptance record at
commit 8feec47, honesty-delta wording changes documented at 319c8a2;
memory: project-joint-iv-kit); pair pages baking/building through the
day via detached chains (`userdata/joint_iv/bake_chain*.log`), each
bake cross-checked exact vs the Worlds Tier-2 grids. Pages land in
`userdata/dives/<focal>_vs_<opp>_iv_robustness.html` -- LOCAL ONLY,
nothing published.

**OVERNIGHT OUTCOME (2026-08-20, pushed by ~03:35):** three site
pushes shipped -- (1) evening: 11 deep pages + links + 16 grid-amber
squares; (2) ~00:55: the 73-clean-pair audit landed (1.36B sims), FINAL
amber = 505/528 pairs (23 truly settled), 50 squares recolored from
grids with auto-generated detail pages; (3) ~03:35: three MIRROR pages
(lickilicky/wigglytuff/corviknight -- mirrors were an accidental
combinations() exclusion; all three are heavily IV-decided, e.g. the
Licki mirror's best build is rank-3182 15/3/3) + a fix for a latent
renderYourDenial crash. Mirror review round fixed 1 blocker + 3 majors.
All 11 deferred review minors shipped 2026-08-24 (28f2a4d) and
[meta.oracle] pins landed on all 18 eligible pairs (7360eb2).

**Round-2 mirrors (2026-08-24):** thievul x3 (true NS+IW mirror, IW+PR
mirror, NS+IW-vs-IW+PR cross-arm), quagsire-shadow, altaria -- built +
published-copy ready. DEFERRED to a later push (Michael-approved):
empoleon__vs__empoleon and feraligatr__vs__feraligatr mirror bakes.
Key finding baked into the kit (8ebb642): mirror grids are
seat-ASYMMETRIC by construction (row = optimized line, column =
always-baits dive convention), so there is NO antisymmetry invariant;
the MIRROR MATCH note is now data-driven (measured diagonal even-shield
wins). TEST DEBT CLOSED 2026-08-27 (37ccc01 + 93b6d91): all 7 planned guard
tests landed, each proven failing against its pre-guard commit
(writer + independent skeptic + mutation probes); the review also
caught and fixed a real producer bug -- _BP_KNOWN was missing
stage_probe_engine_default_policy, so the shipped thievul anchor
pages could not be rebuilt. Review minor 4 (cross-arm
panel labels) shipped 2026-08-26 with the GTO-fill/outline bundle.

**DECISIONS FOR MICHAEL (2026-08-19 EOD):**

- **FN audit of the hub's green/red cells — RESOLVED (the bake ran
  2026-08-19/20).** The 73-pair clean-sample bake completed (tier2
  manifest: 292 clean_sample entries = 73 pairs, 0 deferred) and the
  shipped hub reports the full-grid ground truth: 11 of 73 clean pairs
  show IV-dependence in the top-512 x top-512 block (supersedes both
  the 45/73 extra-probe screen and the original 4/21 sample figure).
  Grid-amber is folded into the hub's amber set via
  Cell.grid_scenarios/_apply_grid_amber.
- **Shipped thievul pages carry two wording issues found by the pair-1
  review**: the 'IV tech without meta cost' card costs 5W on the
  lickilicky page (its own max-meta card shows 63W vs 58W), and the
  debuff-stage cross-check ladder was built from the rank-1 opponent
  instead of the simulated probe (stage -3 renders 21; correct is 22;
  `stage_ladder_from_rank1` in pairs/thievul_lickilicky.toml preserves
  the shipped bytes and documents it). Rebuilding with the current kit
  fixes both -- republishing is your call.
- **Deferred review minors** (all in the 319c8a2 commit message):
  duplicate-grid double embedding (~826KB/page), pareto-axis
  self-inclusion, one-option basis dropdown, wall-table 25-vs-12
  wording, CSV dropped-row accounting, raw key fragments in the
  answers dump, sim-count phrasing.

----

## Worlds 2026 robustness analysis — IN PROGRESS (sessions 2-5 remain)

**Plan of record: `docs/worlds_prep_plan.md`** (read it before touching
anything Worlds). Session 1 DONE 2026-08-10 (`770a74d`): `worlds/meta.toml`
(31 entries) + `scripts/worlds_meta.py` + tests; go/no-go probe = GO
(60/720 amber, structured). Session 2 DONE 2026-08-10 (`4ef544d` +
`5c414c3` + `34a3803`): bool-plane core split into
`deep_dive_lib/robustness.py` (opp_plane + plane_task_worker; wrapper
semantics pinned), Tier-0 closed-form `scripts/worlds_tier0.py` (exact
bisected cutoffs; DragapultSim's Tinkaton-vs-Mantine numbers reproduced
<0.1 under the energy-legal 14-fast plan with guarantee-vs-per-spread
quantities paired correctly — see the plan doc's session-2 note), and
`scripts/worlds_planes.py` + `scripts/worlds_bake.py`
(manifest-stamped idempotent driver; dry-run verifies the full 1,860-key
Tier-1 worklist; guardrails are code + tests, incl. a sweep-cache poison
and a non-memoized mid-bake engine-digest check). Session 3 DONE 2026-08-10: engine batch + migration (above), Tier-1
bake (1,860/1,860 planes, 7.06M sims, 115s, manifest at the final
vintage), `worlds_render_data.py` + `build_worlds_pages.py` (hub +
31x31 matrix + 31 cheat sheets + index card, all root-level; ship
gates green), page layer adversarially verified (orientation + all
16,740 rendered numbers regenerated from planes, 0 mismatches; 84
independent re-sims exact) with the review's honesty findings fixed
(both-mode margin bands, exact spread counts, W/L/? letters,
focal-only no-bait + tie + corpus-convention disclosures, badge_rule
divergence shown, simmed moveset order). Session 4 DONE 2026-08-11 (overnight bake + morning consolidation):
Tier-2 joint grids for the top-66 usage-ranked amber pairs + 21 clean
FN samples (87 pairs, 348 grids, ~2.1B sims; 335 amber pairs deferred
by budget, listed on the hub -- extend by re-running
`worlds_tier2.py`, idempotent), 66 per-pair detail pages
(grid-selected scenarios, SVG robustness curves, boundary-confirmed
reach-or-deny with deny counts), measured FN-rate on the hub (then
4/21; superseded 2026-08-19/20 by the full 73-pair bake: 11/73), all
adversarially verified twice (second round forced the grid-based
scenario selector + wording fixes). Session 5 DONE 2026-08-11 except the publish itself: IV explorer
(worlds-explorer.html; baked closed-form ladders, zero damage
constants in JS, stat math delegated to POGOCollection, parity
bit-exact + engine-checked; conservative rounded-up cutoff display),
CMP board (worlds-cmp.html; union-cohort ranges after the hundo
blind-spot catch, ceiled thresholds, 1-ULP shadow-tie footnote
carried), `verify_worlds.py` registered as ship gate #5 (stamps,
coverage, page/deferred agreement, FN freshness, cmp/explorer
staleness, *_great.toml glob). **Session-6 candidate (Michael 2026-08-11, scoped in-session):
survival strip on pair pages** -- the bulk half of the DragapultSim
framing ("this def/HP survives one more fast hit -> the turn that
funds the 2nd charged move"). Scoping decided to avoid ladder bloat:
(a) tied to the reach table's LIVE plan only (its n_fast implies the
turns you must survive), (b) one row per attainable incoming fast
tier: hits-survived by (def-tier x HP), with the shed-cutoff that buys
+1 hit, (c) fast-pressure-only arithmetic, labeled, grids as battle
truth, (d) new surface = its own adversarial round before ship. Not
publish-gating.

Worlds is Aug 28-30. **PUBLISHED 2026-08-14** (Michael's go;
`publish_website.sh --push`, live-verified at pogodives.com): 401/401
amber pairs baked + pages, verify_worlds OK, plus the same-day
pre-publish polish batch (`157bf71`: cheat-sheet grid links, moot deny
annotation, curve hover readout). Gamemaster held at the pre-Worlds
vintage 8f1d6cca5c0f throughout (only upstream delta: three added mega
forms, sim-irrelevant). NOTE: the data cache holds that pinned old
blob; the next TTL refetch returns to current -- fine now that the
site is published, but re-pin from pvpoke `f60a41199` before
re-rendering any Worlds surface pre-Worlds. REMAINING (all
non-gating): (a) a11y polish: badge text 4.36:1 in pokemon-dark, hub
matrix mini-grids color-only (cheat sheets are the text alternative);
(b) optional session-6 survival strip (scoped above).

**THIEVUL ADDED POST-PUBLISH (2026-08-18).** The Icy Wind Community Day
(08-16) made a Worlds-legal Thievul, so the meta grew 31 -> 33: Thievul
enters as a MOVESET FORK, two FORCED entries sharing Sucker Punch + Icy
Wind and differing on the second charged move -- `thievul` (NS+IW,
PvPoke's post-CD default) and `thievul_iw_pr` (IW+PR, the CD dive's
build). Rationale, mechanism and the scoped NS-vs-PR claims are in
`docs/worlds_prep_plan.md` ("The meta"). Highlights:

- **Icy Wind is INJECTED.** The pinned gamemaster 8f1d6cca5c0f predates
  the CD; upstream pvpoke `f754cd6fc` already lists it as an eliteMove,
  so the lag is proven (CLAUDE.md's cd_prep rule), not inferred. A
  per-entry `injected_move_ids` list in meta.toml is honored by
  `worlds_bake.preflight_moveset_legality` for the declaring entry only.
  Disclosed on both cheat sheets, the hub moveset cells, and the
  provenance line every Worlds page carries. **Retire the table (and its
  disclosures) once the un-pinned gamemaster stably lists the move.**
- **Two `worlds_code` bumps, both blessed forward, no cold re-bake.**
  `worlds_bake.WORLDS_CODE_LINEAGE` holds the one-shot written proofs;
  `--bless-worlds-code` is the explicit operator opt-in and the manifest
  records each blessing. All three Tier-1 bakes were verified additive:
  0 pre-existing manifest entries changed, 0 pre-existing npz touched.
- Tier-1 coverage 1,860 -> 2,112 (= C(33,2)*4). Amber pairs 401 -> 455.
  Tier-2: 432/455 fully baked; **23 deferred**, all Thievul pairs, all
  in the low-usage tail, listed on the hub by the standing mechanism.
  Extend by re-running `worlds_tier2.py` (idempotent) -- the cross-arm
  pair `thievul,thievul_iw_pr` is among them and needs
  `--include-pair` to jump the queue.
- **Operational lesson: run long bakes DETACHED.** Two harness-managed
  background bakes were killed mid-run. `os.fork`/`os.setsid` double-fork
  survives (macOS has no `setsid` binary). Per-grid manifest keying meant
  nothing was lost either time -- restarts resume.
- The hub's FN block now reports 11/73 (the full 73-pair clean-sample
  bake of 2026-08-19/20, folded in as grid-amber); the old 4/21
  original-sample figure is retired.
Session-4 carry-in status (2026-08-10): rebalance date RESOLVED
(Forever Forward live in-game 2026-06-02 1pm PDT; Turin was
post-rebalance -- pages state the split; plan doc corrected).
DragapultSim trio PARTIALLY resolved (108.27 maps structurally to the
per-spread rank-1-anchor cutoff, ours 108.22; 165.73 deny stays
unmapped -- plan doc note). Still open for session 5: a11y polish
(badge text 4.36:1 in pokemon-dark; matrix mini-grid relies on cheat
sheets as its text alternative), optional pooled-usage display
(usage_recent_pooled_pct in meta.toml, unshown). Planning artifacts (design panel, judge
verdicts, evidence brief, probe script, usage JSON) preserved in
`userdata/worlds_planning/`. Standing rules: legacy engine only, both bait
modes, never the sweep cache, no `*_great.toml`, no `src/gopvpsim/` edits
mid-season. The behavior-neutral engine-hash batch LANDED as session 3's
first block (2026-08-10, per Michael's sequencing decision): wording fixes
+ parse_types relocation, one hash bump `1415857072fa -> <new>`, cache
warm-migrated (gamemaster leg first from a pre-batch tree — both stamps
were stale, see the session-3 commit message — then the fully-blessing
engine leg). The Tier-1 bake pins this final pre-Worlds vintage.

**DECIDED (Michael, 2026-08-10) — session-3 sequencing.** (1) DONE — the
engine-hash batch landed first (above). (2) The cmp_atk 1-ULP
shadow-tie artifact (session-2 float audit: divide-by-1.2 breaks 30 of
PvPoke's 227 exact shadow-twin CMP ties; pinned in
`tests/test_worlds_tier0.py::test_cmp_shadow_roundtrip_artifact_is_real`;
PROP-1 correction addendum in the round-2 review doc) is DEFERRED past
Worlds: planes + CMP board stay engine-consistent by construction, and
the session-5 CMP board must carry the footnote. Post-Worlds the fix
(carry pre-shadow atk on BattlePokemon) gets its own hash bump, a
test recording the pre-fix values, and a no-shadow-either-side
migration predicate — do NOT fold it into the neutral batch.
