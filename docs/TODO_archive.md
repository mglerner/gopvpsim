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
- **#2 float32 damage constants** -- DONE (`4e57321`). STAB/BONUS/super-effective
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
- **#2 [MED] FIXED 2026-06-27 (`4e57321`)** -- damage formula now uses the
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
