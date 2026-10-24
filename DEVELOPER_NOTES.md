<!-- DEVELOPER_NOTES is a session-startup read (see CLAUDE.md) and MUST stay
small enough to read WHOLE in one shot: ~25k-token read cap at ~2.36
chars/token, so keep `wc -c` under ~52k chars (~900 lines). When adding an
entry, pair it with a trim or push dated root-cause prose to CHANGELOG -- a
future session must not read half and think it read all. Shipped/dated
history -> CHANGELOG; live invariants + open divergences -> here. The
2026-10-24 trim archived the removed blocks and the long-form originals of
the heavily condensed sections in CHANGELOG ("DEVELOPER_NOTES trimmed to its
read-whole cap"); sections condensed in place have no archive block, so the
complete pre-trim text is `git show 0829b5a:DEVELOPER_NOTES.md`. PvPoke JS
line numbers are as of the pvpoke commit named in each entry. -->

# Developer Notes

## PvPoke re-vetting log

**2026-10-24 -- re-vetted against pvpoke `38f70320d`** (range
`a93147bf1..38f70320d`). `e87448291` "Sandbox mode fix" is UI/sandbox only
(the page-side double-simulate of bug-report draft 9;
`tests/test_pvpoke_sandbox.py` re-pinned to the fixed page, 662/[51,0]).
`4d2908fac` + `38f70320d` add Minior: triggers `battle_start` and `hp`, the
Meteor hold-energy rule (`ActionLogic.js:254-263`), the Meteor wouldShield
rule (`:1256`), the level formulas (`Pokemon.js:2562-2580`) and the
form-animation cooldown reset (`Battle.js:548`); every sim-relevant line is
gated on `activeFormId == "minior_meteor"` except the trigger dispatch, so
`pvpoke_dp` stays a valid PoGoDives baseline for every other species.
**Ported as-is** (`tests/test_minior.py`; "Form change gotchas" 7, "PvPoke
bugs found" #11); porting exposed four port-fidelity gaps, all fixed
PvPoke-exact: fast-landing queue order ("Form change gotchas" 7(a)) and the
TTL order, stack-two twins and battle-start freeze order ("Key implementation
details"); class A followed the same day. Engine digests:
`tests/fixtures/pvpoke_engine_digests.json`.

Earlier vettings (2026-06-06 at `bc532fbda`; the first full oracle-harness
audit the same day) are archived in CHANGELOG. Record a new entry here only
for the CURRENT pin; move the previous one to CHANGELOG when you do.

## Current status (updated 2026-10-24)

<!-- sync:test_count -->3215<!-- /sync --> tests collected (canonical bump: `scripts/verify_dev_counts.py
--update` rewrites the derivable sentinels in place -- do not hand-edit
this number). The oracle audit (`scripts/audit_oracle_harness.py`, GL + UL)
verifies the simulator against PvPoke's live engine for
<!-- sync:pvpoke_matchups_verified -->43<!-- /sync --> matchups
(<!-- sync:pvpoke_cells_verified -->387<!-- /sync --> cells: <!-- sync:pvpoke_cells_exact -->367<!-- /sync --> exact on score+winner+chargedLog, 20 cells =
documented divergences, each traced to a mechanism: 8 are bug #8 Hangry
stickiness, 3 are our deliberate Shield-form Aegislash estimate-stage
choice ("Form change gotchas" item 6), 9 are the #10 first-throw slot
quirk (Aegislash-S vs Moltres-G; its GB-first positive control row is 9/9
exact). Per-cell reasons live on the MATCHUPS entries in the audit script;
the cell-count progression (108 -> 387, 2026-06..10) is in CHANGELOG.

### Verified correct
- **Type effectiveness**: All <!-- sync:type_chart_cells_verified -->324<!-- /sync --> matchups match PvPoke exactly
- **Damage formula**: Verified against manual calculation
- **Buff/debuff mechanics**: Guaranteed buff (Beedrill 9/9), chance buff
  (Corviknight 9/9), self-debuff meter threshold
- **DP queue insertion**: Three PvPoke strategies ported (farm-down <=,
  ready <=+dedup, not-ready <)
- **selfBuffing/selfDebuffing flags**: Match PvPoke's chance thresholds
  (==1 for selfBuffing, >=0.5 for selfDebuffing)
- **Shield policy**: pvpoke_simulate_shield uses precomputed flags
- **Shadow Pokemon**: atk x`6/5`; def x`float32(5/6)` = 0.8333333134651184,
  the GAME's value, NOT `5/6` and NOT PvPoke's `0.83333331` ("Engine
  constant sourcing").
- **Both-side buffs**: Corviknight mirror (Air Cutter only) 9/9; both
  buffApplyMeters fire independently.

## Turn model: `mechanics='new'` (2026-06-23 PvP turn system; default since 2026-09-09)

`simulate(...)` takes `mechanics='legacy'|'new'` (default `'new'` since
2026-09-09, `7e6a82b`); `'new'` implements the in-game PvP turn changes of
2026-06-23 (spec: pokemongo.com/news/pvp-updates2026). `--mechanics` on
`scripts/battle.py` and `scripts/deep_dive.py` defaults to `new`, as does
`deep_dive_slayer.SLAYER_DEFAULT_MECHANICS` (pinned to the engine's default
by `tests/test_dive_worker_form_change.py::
test_the_slayer_default_mechanics_tracks_the_engine`). **Validated against
PvPoke master** (its own implementation merged 2026-09-09); the oracle audit
and the pytest suite run at the default. Both disk caches key on `mechanics`
(a field only for non-legacy values).

`'legacy'` is retired: `simulate()` raises `ValueError` unless
`GOPVPSIM_ALLOW_LEGACY_MECHANICS=1` is set (`2615c6e`; `conftest.py` opts a
few tests in), kept only so the port-fidelity history stays runnable; every
`'new'` behavior sits behind an explicit `if mechanics == 'new':` branch.
(History 2026-06-23..09-10: CHANGELOG.)

The 5 spec changes on our 1v1 core: **1** (damage+energy resolve at END of
turn) and **2** (same-turn one-turn fasts TIE) -- modeled; the fast-landing
step snapshots damage/energy against the start-of-step state and applies all
results together, so a higher-CMP fast cannot pre-empt a same-turn fast.
**5** (charged attacks resolve BEFORE fast-attack damage, buffs included) --
modeled: in `new` mode charged actions resolve at step 2.5 of the SAME turn,
ahead of the step-3 fast landings. CORRECTED 2026-09-03 (`f1ff911`): the
first port read the spec's "charged begins at the start of the next turn"
literally and deferred the charged move a turn; the live game's order is a
priority ordering WITHIN a turn (swaps > charged > fast), and PvPoke made
and reverted the same mistake
(`docs/validations/2026-09-03_new_turn_system_ground_truth.md`). **3** and
**4** (swaps) -- NOT MODELED: the 1v1 core never switches; documented, not
faked.

**Decision layer = PURE PLUMBING (2026-06-24).** `mechanics` is threaded
through `pvpoke_dp`, `_calc_turns_to_live`, `_optimize_move_timing`,
`would_shield`, `pvpoke_simulate_shield` and every policy, but under `new`
the decision layer runs the LEGACY decisions unchanged. Corpus-tested: every
attempt to re-optimize the AI for the new clock washed out or broke a
non-regression floor. A real but non-generalizable sub-optimality is
knowingly deferred post-ship. Pinned by `tests/test_new_turn_mechanics.py::
test_new_decisions_identical_to_legacy`; writeup, the deferred cases and the
resume harness (`scripts/corpus_policy_driver.py`):
`docs/validations/new_mechanics_decision_layer_2026_06_24.md`.

**Slayer cache identity.** The slayer engine stamp is
`slayer_cache.slayer_engine_hash()` = `md5(sweep_engine_hash +
deep_dive_slayer.py bytes)[:12]` -- composed, not folded into
`sweep_cache._ENGINE_FILES`, because **the sweep stamp must not move** (the
sweep never reads the slayer worker). Pinned by
`tests/test_slayer_engine_stamp.py`. `migrate_cache.py --slayer` blesses
against the slayer stamp; `--list-stamps` prints a separate SLAYER section.
(The 2026-09-22 close-out and its one-time invalidation: CHANGELOG.)

## Performance baseline (regression gate)

**Rule: after any change to `battle.py`, `_dp_jit.py`, or `moves.py`,
re-run the benchmark below and compare against the current baseline. A drop
of more than ~10% means stop and investigate before committing.** The
2026-04-15 correctness arc silently halved throughput and nobody noticed for
eight weeks because the old figure kept being quoted.

Canonical benchmark (single-process, ~10s, Annihilape mirror):

```
python scripts/profile_slayer.py --n-focal 60 --n-opp 20
```

**Current baseline: 5,800 sims/s** at `6f99b08` (engine `5a813036625c`,
2026-09-25), new turn system, post-2026-09-09 gamemaster, warm JIT cache
(the first run after an engine edit pays ~1-2 s compile). NOT re-measured
after the 2026-10-24 Minior / class-A engine edits -- run it before the next
bake and record the number here. The earlier rows
(2026-04..06, in CHANGELOG) are NOT comparable: gamemaster data changes
shift battle lengths and therefore sims/s, so after a rankings/gamemaster
refresh re-baseline on a commit with a known-good number rather than
comparing across data vintages. cProfile runs (`--profile`) are ~2-5x
slower than wall-time runs; compare like with like.

**Caveat when timing dives (not the canonical benchmark):** `deep_dive.py`
serves IV sweeps from the disk cache by default, so a repeated dive reports
0 sims. Pass `--no-sweep-cache` for timing runs.

## Sweep disk cache + replay-from-saved-state (arc S4)

Two iteration-speed layers shipped 2026-06-10; design rationale in CHANGELOG
("Sweep disk cache + replay-from-saved-state").

**Sweep cache** (`scripts/sweep_cache.py`, CACHE_VERSION 8, v7 schema):
`iv_sweep` persists each opponent's column to `~/.cache/gopvpsim/sweep/` and
skips cache-hit opponents. Keys include the moveset, scenarios, bait mode,
`mechanics` and `focal_max_level`; opponent-side keys carry resolved IVs +
moveset, so rankings drift produces clean misses. Columns are multi-plane
`.npz` (`{score, energy}`, plus `{won,hp,max_hp,shields}` when
`capture_metrics`) in canonical iv_meta order -- hits are bit-identical to
fresh sims (`tests/test_sweep_cache.py`). Shared `.npz` foundation:
`scripts/cache_base.py`.

- **Engine hash is a per-column STAMP** (v6), not part of the key dir: a
  `.json` sidecar `{engine, gamemaster, col}` per column. A stale stamp is a
  miss, and `scripts/migrate_cache.py --from-engine X --predicate NAME`
  blesses columns a localized fix provably doesn't touch (rewrites the
  sidecar) and DELETES the rest, so they re-sim cold.
- **Gamemaster hash is ALSO a per-column STAMP** (v7), NARROWED to the
  sim-relevant subset `md5(pokemon + moves)` (`sweep_cache.gamemaster_subset`;
  CPM, type chart, STAB/BONUS and shadow mults are hardcoded in the engine).
  Non-sim churn never invalidates, and a balance patch is migrated by
  COMPUTING the affected set from the delta: `migrate_cache.py
  --from-gamemaster <stamp> --old-gamemaster-file <blob>` re-sims a column
  iff an entry the battle reads for it (base species with `_shadow`
  stripped, transitively-expanded form-change alt forms, or a move either
  side uses) changed or was removed; an unresolvable species is re-simmed.
  `slayer_cache.py` shares `gamemaster_hash()`.
- **Energy is always captured + stored**, so the default `--compare-energy`
  dive serves warm.

**Discipline when changing the engine (full text in CLAUDE.md).**
`put_column` overwrites a column **in place**, so a dive with the cache on
under a work-in-progress engine overwrites the trusted columns (a safe miss
later, but the warm backup is gone). Iterating on an engine file: run dives
with **`--no-sweep-cache`**. There is intentionally no flag to redirect the
cache dir -- the guard is `--no-sweep-cache`, not a second location. GC
never causes this: it buckets by gamemaster vintage, not engine.

**Rule: before a cold re-dive, check for a tractable migration first**
(policy and its two soundness guards: CLAUDE.md "Before a cold re-dive").
Past bumps and their predicates are listed in CHANGELOG; the `--from-engine`
value a migration needs is the OLD hash, so read it off `--list-stamps`
BEFORE committing the engine change, or recover it from git.

**Never compare gamemaster blobs by raw file md5.** `_fetch_json`
re-serializes with `json.dumps` before writing (`data.py`), so the cache
file's bytes never equal the git blob's even when the content is identical.
Compare after `json.load`, or via `sweep_cache.gamemaster_hash()`. Old blobs
for `--old-gamemaster-file` come from the pvpoke git history
(`git -C ../pvpoke show <sha>:src/data/gamemaster.json`); git is the
archive, no copies are kept.

### Pre-rebalance data vintage pin

Record the baseline here BEFORE a gamemaster move (`docs/rebalance_checklist.md`
section A) as pvpoke commit + `gamemaster_hash()` stamp; move it to
CHANGELOG once its migration is applied. **Pending (2026-10-24):** old stamp
`9856aa366b5d` (blob: pvpoke `c15fb6f7e`) -> live `03e7b77024e9`; command
and engine side in TODO "Minior -- open items". The 2026-08-31 Twilight
Trails pin (`46bd08a77` / `c431557dcc76`) is archived in CHANGELOG.

Operational notes: hit log line per sweep is `sweep cache: N/M opponent
columns hit`. `scripts/gc_cache.py` (`--dry-run` default) prunes stale
columns: current-schema dirs are always kept and reclaimed at COLUMN
granularity (gamemaster stamp outside the current + N-1 window), older-schema
dirs get DIR-level vintage pruning; `rm -r ~/.cache/gopvpsim/sweep` is always
safe. The ML IV-guide path rides the same cache via `iv_sweep`. Library
callers default to OFF; only the CLI turns it on.

**Replay** (`scripts/replay_analysis.py`): every interactive dive dumps its
render-input state to `userdata/replay/*.replay.pkl.gz` after sims complete
(skip with `--no-replay-dump`); `python scripts/replay_analysis.py
userdata/replay/<blob> [--html OUT]` re-runs `deep_dive.render_dive_html`
(the live code path) and produces HTML byte-identical to the original
dive's. Prefer it over inline-HTML editing for Python renderer changes
(inline edits remain fine for pure JS/CSS tweaks in built files). Blobs are
gitignored, never published; delete freely.

## Engine constant sourcing (the game is ground truth; PvPoke is the oracle)

Damage-relevant magic numbers come in two tiers, and **when they conflict we
match the game, not PvPoke**:

- **Primary source = the game.** PoGo computes damage in float32 and stores
  its constants as float32, so the correct value of such a constant is
  `float32(<the true ratio>)`, used as a float64 literal in our otherwise-
  float64 arithmetic: STAB/BONUS/SUPER_EFFECTIVE (`moves.py`) and
  `SHADOW_DEF_MULT` (`pokemon.py`); every plausible decimal near 5/6
  collapses to float32(5/6) = 0.8333333134651184.
- **Oracle = PvPoke** (`pvpoke_trace.js` / `audit_oracle_harness.py`).
  Usually the same values. But `DamageCalculator.js` writes `SHADOW_DEF` as
  the truncated decimal `0.83333331`, ~3.5e-9 below the true float32(5/6).
  We use the game value; it flips ~0 cells, but a stray shadow-defender
  oracle cell on that knife-edge would be expected, not a regression.

Where the constants live (single source of truth per language):

- **Python:** `gopvpsim.moves` (STAB_MULTIPLIER / BONUS / SUPER_EFFECTIVE)
  and `gopvpsim.pokemon` (SHADOW_ATK_BONUS / SHADOW_DEF_MULT). Every Python
  consumer imports the named constant -- no second copy.
- **JS:** the shipped dive / user-collection engines RECEIVE these from
  Python via injection (`deep_dive.py` -> `DATA.collection` -> `opts`);
  `deep_dive_user_collection.js`'s fallback default is pinned equal to the
  Python constant by `tests/test_js_shadow_constants.py` (it drifted once,
  unnoticed, because production never read it). The JS port does NOT compute
  raw damage, so only the shadow multipliers are duplicated there.

### Applying the constants: `pokemon.effective_stats`

`pokemon.effective_stats(atk, def_, shadow)` is the ONE application of the
shadow multipliers: pass the RAW pair, get the effective pair back (it used
to be written out six-plus separate ways). The arithmetic is `raw * MULT`,
in that order, and non-shadow returns its inputs untouched. Float
multiplication is NOT associative, so folding a multiplier into the CPM
would change scores; `tests/test_shadow_stats.py` pins the order and every
routed call site. HP and CP are never shadow-adjusted. The JS port keeps its
own multiply (constants injected) -- intentional, pinned by
`tests/test_js_shadow_constants.py`.

### League facts: `pokemon.LEAGUES`

`pokemon.LEAGUES` is one `League(cp, max_level, open_rankings)` row per
league; `LEAGUE_CAPS`, `LEAGUE_CP` (the same object) and `LEAGUE_MAX_LEVEL`
are derived views for the ~30 dict-shaped call sites
(`tests/test_league_descriptor.py`). **The table has to stay in
`pokemon.py`**: it is an engine-hash file (`sweep_cache._ENGINE_FILES`), and
a CP cap / level ceiling changes simulated stats -- the same constants in an
unhashed module would let the sweep cache serve columns computed under the
old values. `data.py` reads it through a FUNCTION-level import
(`data._league_cp`) because `pokemon` imports `data` at module scope. Little
League has no open PvPoke rankings, so `data.load_rankings('little')` fails
loudly; `load_cup_rankings` is the way in. The JS user-collection fallback
tables carry the `little` row too (`d59e801`), pinned by whole-table
equality in `tests/test_js_shadow_constants.py`.

## PvPoke bugs found

<!-- sync:pvpoke_bugs_documented -->8<!-- /sync --> bugs documented below (sections 1, 2, 3, 7, 8, 9, 10, 11 --
numbering is discovery order; #4 was retracted 2026-04-15 and is excluded
from the count; #5/#6 were never numbered entries). Filed upstream
2026-07-16 as pvpoke/pvpoke #378 (#3 Gyro Ball), #379 (#8 Morpeko), #380
(#1 dead pruning), #381 (the initializeMove DPE-overwrite, Report 4 only)
and #382 (#2 bestChargedMove staleness); #7 was held back. Nothing has been
filed since -- PvPoke has not responded -- and Michael's standing call
(2026-10-24) is NOT to file more; Reports 8 and 11 stay drafts and Report 10
is moot (ported), all in `docs/pvpoke_bug_reports.md`.

### 1. BattleState .hp/.oppHealth naming inconsistency

**File**: `ActionLogic.js:1284` (class definition) vs the dominance checks at
`:649`, `:697`, `:746` (pvpoke `38f70320d`). `BattleState` stores
`.oppHealth` and `.oppShields`, but the dominance checks reference `.hp` and
`.shields` (undefined in JS -> always false -> dead code). We replicate the
dead-code behavior (no pruning); the `intended_pruning` toggle that offered
the apparently intended pruning was deleted 2026-06-12 (`1558e31`, zero
consumers).

### 2. bestChargedMove not recomputed on opponent form change

**File**: `Pokemon.js` `selectBestChargedMove` (~`:841-865` at `38f70320d`);
`changeForm` (`:2471`) calls `resetMoves` on self only. PvPoke caches `bestChargedMove` at init and
does NOT recompute it when the **opponent** changes form (e.g. Aegislash
Shield->Blade). Since 2026-07-03 we MATCH this (divergence #3 below): the NB-1
sweep showed our old per-turn recompute was not reliably better.

### 3. Aegislash selects Gyro Ball over Shadow Ball -- FIXED UPSTREAM

Fixed in pvpoke `574aeb0da` (`ActionLogic.js:954`, `!selfBuffing` ->
`!selfDebuffing`), filed by us as pvpoke/pvpoke#378. PvPoke master throws 0
Gyro Balls across the 36 pre-09-27 Aegislash oracle cells. Kept for the
record and the bug count. The residual Gyro-Ball-vs-Shadow-Ball first-throw
differences found 2026-09-28 are NOT #3 but its inverse, from a different
mechanism: see #10. (Original entry: CHANGELOG archive.)

### 7. needsBoost / non-guaranteed-buff plan selection is dead code

**File**: `ActionLogic.js:546-570, 824, 903` (decideAction DP, `38f70320d`).
The code looks like it accumulates a `stateList` of KO plans tagged with
`.chance` and picks the highest-chance plan when the Pokemon "needs the BOOST
to win". Two faults make it inert: `:570` unconditionally sets
`changeTTKChance = 0` ("DISABLE THE NON-GUARANTEED BUFF EVALUATION SYSTEM"),
gating off every chance-<1 DPQueue push; and `needsBoost` (`:824`) is
declared `false` and never assigned `true`, so the `:903` gate always fires.
Confirmed empirically 2026-04-15 (the log line never fired in 36 traced sims
of the four GL species with chance-buff default moves). **Our stance**: not
ported -- doing so would diverge from PvPoke's observable behavior toward a
feature it explicitly disabled. Revisit if PvPoke removes the `:570` reset or
assigns `needsBoost = true`.

### 8. Morpeko form change is one-way instead of a true toggle

**File**: `Battle.js:1555-1573` (post-attack `charged_move` form trigger,
`38f70320d`) and `pokemon.json` (`morpeko_hangry` has `formChange: null`).
The gamemaster says `type: "toggle"`, and the real game toggles Full Belly
<-> Hangry after **every** charged move (Michael verified in-game
2026-06-06: Full Belly on battle start AND every switch-in, `resetOnSwitch:
true`). PvPoke's
trigger is gated on `activeFormId != alternativeFormId`, so Full Belly ->
Hangry passes but Hangry never toggles back (`morpeko_hangry` carries no
`formChange` of its own); Morpeko sticks in Hangry for the battle. The guard
was written for one-way changers and wrongly catches a toggle.

**Our code**: `formchange.py` makes the Hangry form inherit the
`charged_move` trigger so it toggles back, so our chargedLog disagrees with
PvPoke's whenever Morpeko throws a 2nd+ charged move (ours Aura Wheel
Electric from Full Belly, PvPoke's Dark from a stuck Hangry); score-relevant
wherever an unshielded 2nd+ Aura Wheel meets an Electric-vs-Dark
effectiveness difference, where PvPoke's published numbers are wrong.
**Stance: keep our toggle.** Pinned by the chargedLog assertion on
`test_morpeko_vs_azumarill_form_change` and the 8 known-divergence cells in
`scripts/audit_oracle_harness.py`. `docs/pvpoke_divergences.md` item 2.

### 9. Stale IV-rank chip on battle permalink loads (UI-only)

**File**: `Interface.js:1858-1875` vs `PokeSelect.js:418` (updateIVRank;
found 2026-08-10). Loading a permalink with custom IVs renders the "Rank #N /
4096" chip for the DEFAULT spread and never refreshes it (typing an IV by
hand does). GL Mimikyu 0/8/14 shows "#42" where PvPoke's own
`getIVRank("overall")` gives #80, which is what our card prints.
Display-only; not filed. Related non-bug: PvPoke floors displayed atk/def to
1 decimal, our cards round.

### 10. Shield-start Aegislash's first throw follows the input order (quirk, not ported)

**Files**: `Pokemon.js:757-763` (shuffle clause 1), `:790-796` (clause 4;
`resetMoves` at `:711` re-pushes the same move objects). Found 2026-09-28.

**Mechanism.** `resetMoves()`'s priority shuffle has a clause 1 (same energy:
move the buffing or higher-damage move to slot 0), gated on
`!selfDebuffing`, and a clause 4 that in `aegislash_shield` form stamps every
charged move `selfDebuffing = true` IN PLACE, never undone; `resetMoves()`
runs several times before a fight, so clause 1 is dead and slot 0 is the
user's input order. Ours restores the pristine move dicts in
`reset_for_battle` (`_restore_shuffle_stamp`; needed, or a reused Blade
inherits the stamp -- the 2026-09-12 leak), so clause 1 is live at the first
Shield shuffle and slot 0 is the harder-hitting move vs THIS opponent.

**Consequences** (1080-cell GL sample): 52 cells differ only in chargedLog;
5 differ in score (Moltres-G x4, Guzzlord (0,0)), all ~+100 for Aegislash
under ours (Moltres-G (0,0): PvPoke's last throw is the resisted Shadow
Ball, 308/691 vs our 408/591). Proved
both ways (PvPoke with `--p1-charged GYRO_BALL,SHADOW_BALL` reproduces ours;
the audit's `..._gb_first_vs_moltres_galarian_form_change` row is the
standing 9/9 positive control; emulating the stamp in ours makes all 57
cells PvPoke-exact). **Caveat:** ours is order-invariant only at the first
Shield-form throw; the stamp then persists in BOTH engines.

**Verdict: not ported.** PvPoke's slot 0 is an artifact of how many times
`resetMoves()` ran, and where it changes the score it throws the resisted
move. Pinned in `tests/test_form_change_oracle.py`
(`test_aegislash_shield_vs_moltres_g_first_throw_divergence` + the GB-first
control) and as nine audit xfail cells. `docs/pvpoke_divergences.md` item 8.

### 11. Minior's Meteor level: the simulator steps whole levels, the site shows half levels (ported with a switch)

**File**: `Pokemon.js:2590-2612` (`getFormStats`, Minior branch; `38f70320d`).
The Meteor level walk steps `0.5` only when `this.activeFormId ==
"minior_core"` or `this.decrementer == "minior_meteor"` (sic: `decrementer`
is never assigned, a typo for a form-id check), else `1`. `changeForm` sets
`activeFormId` to the NEW form first, so the battle-start Core -> Meteor
change steps WHOLE levels while the site UI steps half levels: displayed and
simulated Meteor stats disagree for about a third of GL spreads (10/6/10: UI
43.5, sim 43.0). We port the BATTLE path behind
`formchange.MINIOR_HALF_LEVEL_STEP` (False = sim path, default); pinned on
both settings by `tests/test_minior.py::test_meteor_level_from_stored_core_gl`.
Neither path matches every in-game reading (go-iv's empirical rule fits
11/11, PvPoke's 3/9 GL); Michael's call: trust PvPoke's model, revisit when
the community settles. Impact <= ~2 Meteor levels. Draft:
`docs/pvpoke_bug_reports.md` Report 11 (not filed).

### 4. Mimikyu SS timing -- RETRACTED 2026-04-15

Phantom: a missing timeline log line in our disguise-bust branch, not a
behavior difference.

## Resolved engine divergences (historical index)

Once-open divergences, all RESOLVED and test-pinned; the index with each
item's mechanism, dates and pins is archived in CHANGELOG ("DEVELOPER_NOTES
trimmed", 2026-10-24): the shadow-x1.2-in-CMP bug (fixed by `cmp_atk`), the
2026-06-27 engine bug-hunt #2-#7 (`docs/reviews/2026-06-27_engine_bug_hunt.md`),
the incoming selfDefenseDebuffing shield gate, the bait-wait hold, the
Snorlax/Obstagoon OMT KO-override, the OMT `turns_planned` divisor, and the
2026-04 arc. The one live invariant from that arc -- the SUPER_POWER
DPE-edge > 0.3 carve-out -- is self-documented in `battle.py`
`_estimate_best_cm`. Recurring lesson: "score-neutral" claims about
decision-timing deviations need a trace, not reasoning -- each was an extra
condition the reference lacks, with a plausible comment, producing real
margin errors.

## Known divergences from PvPoke implementation

Places where our code intentionally does NOT match PvPoke's implementation,
plus open gaps. Each is a potential source of score mismatches; check these
before assuming a score difference is a PvPoke bug. The public-facing list is
`docs/pvpoke_divergences.md` (its own numbering; each entry here cites its
item).

### Breakpoint / bulkpoint solvers apply the Mega bonus (deliberate, 2026-09-02)

PvPoke adds the 1.3x Mega bonus to `DamageCalculator.damage()` but NOT to
its `breakpoint()` / `bulkpoint()` solvers, so upstream a supermega's
breakpoint table disagrees with the damage printed beside it. Ours applies
the factor (`breakpoints.py`): breakpoints ARE this project's deliverable,
and PvPoke's solver is inconsistent with its own damage function. Not yet in
`docs/pvpoke_divergences.md`.

### Minior (2026-10-24): UL level clamp, animation clock, 4 open sweep cells

None of the gaps below is in the oracle audit (the 90 Minior oracle cells
are, all exact).

- **UL Meteor level 52 vs PvPoke's 55 (deliberate).** Meteor cannot reach
  2500 CP, so PvPoke's walk never steps down from its table end (55) and
  ours stops at `max(CPM)` = 52 (`formchange._MINIOR_PVPOKE_LEVEL_CAP`
  clamps the start; GL is unaffected because every GL answer is <= 52). UL
  Minior is unverified in-game and outside every pool. Pinned by
  `test_meteor_level_ul_clamps_to_our_cpm_table`. `docs/pvpoke_divergences.md`
  item 9.
- **`animationTime` (5000 ms) on the hp flip is not added to a clock.**
  PvPoke adds it to its wall-clock `time`, which only feeds the timeline
  display and the 240 s time-out ("Battle timeout" below); no score effect
  unless a fight nears the limit.
- **4 of 702 scratch-sweep cells differ** (`userdata/logs/minior_midflight_
  sweep_6.log` vs `pvpoke_trace.js`; the log lists 14, but the ten Lickitung
  cells are the harness level-cap artifact, "Key implementation details").
  Morpeko 2-2 both seats = bug #8. Medicham vs Minior 1-2 (ours 351 / PvPoke
  373) and 2-2 (734 / 391): same DP plan [Ice Punch x3] in both engines, then
  PvPoke's post-DP bandaid region (`ActionLogic.js` ~838-990) swaps slot 0 to
  Dynamic Punch and ours does not -- NOT traced to a line. Michael's call:
  ship, improve later (TODO "Minior -- open items").

### bandaid[929] stack-switch is ungated on bait_shields (no-bait only)

In `pvpoke_dp`'s self-debuff-stacking handler, the terminal `elif` swaps a
self-debuffing max-damage move to a cheaper non-debuffing move when the
opponent would shield the nuke (or the cheaper move is self-buffing). PvPoke
gates this swap on `baitShields` (`ActionLogic.js:940` at `38f70320d`); we
do not. So in no-bait analysis PvPoke keeps the self-debuffing move and we
swap.

**Why we keep ours.** When `would_shield` is True the move is shielded either
way (1 damage), so the swap only avoids eating the self-debuff on a throw
that is shielded regardless -- avoid-waste, not bait tempo, same family as
the `[910]`/`[918]` self-debuff timing that PvPoke itself leaves ungated.
PvPoke's gated line throws the nuke into a guaranteed shield: strictly
dominated (A/B across the GL+UL self-debuff focals: gating flips 284
winners, ALL against the focal, zero the other way). **No PvPoke oracle**:
`pvpoke_trace.js` cannot set `baitShields`, so the no-bait dimension is never
compared upstream; revisit if a no-bait oracle path is ever added. Pinned by
`tests/test_bandaid929_nobait_divergence.py`. `docs/pvpoke_divergences.md`
item 6.

### Battle timeout: flat 500-turn guard vs PvPoke's 240s display clock

PvPoke ends battles when `time > 240000` ms (`Battle.js:636` at `38f70320d`),
where `time` mixes 500 ms turns with 10,000 ms charged-move "minigame"
adjustments (a charged round REPLACES the turn's 500 ms; a shielded round
discounts one), so its effective turn cap shrinks with every charged throw.
Ours is a flat `MAX_TURNS = 500` guard. Intentionally NOT matching: both are
infinite-loop guards and neither is reachable in a 1v1 (the bulkiest GL wall
fight traced, Carbink mirror 2v2, ends at 85 turns / ~118 s), and the
minigame bookkeeping would complicate the hot loop for no observable effect;
revisit only if a real matchup times out in either sim.
`docs/pvpoke_divergences.md` item 5. **Team-sim caveat (Michael, 2026-06-11):** the 240 s is the real
game's MATCH timer for a 3v3; in a team sim the three pairings SPLIT it and
timing out becomes a real outcome, so port PvPoke's clock semantics as
match-level state when the "Team/multi-mon simulation" TODO lands.

### Near-KO DP plan choice: nuke-with-self-debuff vs serial-Fly (RESOLVED 2026-09-25)

**We now match PvPoke.** The `_cached_damage` memo that our port of
bandaid[866] reads is refreshed at PvPoke's four refresh points (battle start
in `simulate`, `_optimize_move_timing` for both sides' moves with no energy
gate, `would_shield`, the form-changer's moves in `apply_form_change`), so the
bandaid fires exactly where PvPoke's bandaid[885] does (the 2026-04-15
keep-our-plan decision inverted under the new turn system; Michael's call
2026-09-25). Pinned by `tests/test_battle.py::
test_moltres_g_nearKO_plan_divergence_pinned`. **One deviation stays**:
bandaid[866] only swaps when the target cms[0] is non-debuffing, so the
both-self-debuff cluster (`docs/reviews/2026-06-28_both_self_debuff_divergence_cluster.md`,
KEEP; `tests/test_both_self_debuff_divergence.py`) is unchanged.
`docs/pvpoke_divergences.md` item 4; the original analysis is in CHANGELOG.

### 3. Move-selection freeze at resetMoves (matches PvPoke; FIXED 2026-07-03)

**PvPoke** freezes the activeChargedMoves ordering, each move's raw `.dpe`,
`bestChargedMove`, and the farm-down constants in `resetMoves()` -- at battle
start and again on *self* form change (only `move.damage` refreshes per use).
We used to recompute them every `pvpoke_dp` call from current-stage damage,
documented as strictly better; the NB-1 bounding sweep
(`docs/reviews/2026-07-03_nb1_bounding_sweep.md`) FALSIFIED that (the
recompute crosses PvPoke's init-tuned 0.3/1.5 guards mid-fight in BOTH
directions, including a shipped winner flip against us: Forretress (Shadow)
vs Cradily GL 1-0, ours 413 LOSS vs oracle 588 WIN). `_ensure_dp_init_cache`
now freezes those quantities once per battle (reset only on self form
change); `_ensure_dp_cache` keeps the per-stage damage tables fresh. Pinned
in `tests/test_nb1_selection_freeze.py` (Groups A/B).

**Remaining intentional divergence**: the post-DP don't-bait dpeRatio site
(battle.py, "the NB-1 freeze carve-out") stays FRESH and internally
consistent; PvPoke's uses `move.damage` with mixed refresh-on-use staleness
(a cache artifact), so matching it would emulate a PvPoke bug. Pinned as
Group C. `docs/pvpoke_divergences.md` item 1.

## Threshold model: damage tiers vs matchup boundaries

The deep dive reports two kinds of stat threshold. **Damage-tier
boundaries** (`_aggregate_flips_by_anchor`): the exact def (or atk) at which
`floor(0.5 * 1.3 * Power * Atk/Def * Eff * STAB) + 1` steps by 1 --
pure-formula, invariant to battle conditions ("Anchor-Driven Matchup
Flips"). **Matchup-flipping boundaries** (`_find_matchup_boundaries`): the
minimum def (+HP) at which the outcome flips from loss to win -- usually
higher, because per-hit reductions must accumulate to change the turn count
("Matchup-Flipping Boundaries", tier cards). Under energy-lead work damage
tiers won't change, matchup boundaries will.

## Key implementation details

### DP queue insertion (pvpoke_dp)

PvPoke uses three insertion strategies in the DP queue:
1. **Farm-down** (`<=`): insert after same-turn states
2. **Ready-move** (`<=` + dedup): dedup at exact turn, then insert after
3. **Not-ready-move** (`<`): insert before same-turn, giving charged-move KO
   paths priority over farm-down

Order within one pop: the farm-down state goes in FIRST, before the
charged-move expansions (PvPoke inserts it inside the per-move loop, ahead of
each move; once is equivalent). The two orders differ only on a same-turn tie
with a ready move (a 1-turn fast whose single hit KOs), where the farm-down
state pops first, as in PvPoke (ported 2026-09-28,
`tests/test_farmdown_order_port.py`).

### DP "stack two self-debuffing moves" expansion -- both twins (2026-10-24)

PvPoke's DP has TWO blocks that expand a state by stacking two copies of a
self-debuffing charged move (selfDebuffing, `buffs[0] < 0`, `2 * energy <=
100`) and throwing both: a READY twin (`ActionLogic.js:668-717`, inserted
AFTER same-turn states with `<=`, skipped when `fm_stack == 0`, and it can
produce negative turn counts when energy > 2E -- kept verbatim) and a
NOT-READY twin (`:764-808`, inserted BEFORE same-turn states with `<`).
Eligibility reads `buffs` directly, so the Aegislash `[0,0]` selfDebuffing
stamp (bug #10) does not qualify. Both twins were missing until Minior's
hold-to-100 AI made Malamar reach 2x Super Power energy routinely; porting
only the ready twin regressed 36 cells; with both, a 14,022-cell GL scan
moved 496 cells, every one onto PvPoke's value. GL default movesets that
qualify: Super Power and Psycho Boost (28 species). Plumbing: `cm_stack_ok`
in `_ensure_dp_init_cache` ->
int8 array into `_near_ko_dp_jit`; Python fallback `_dp_insert_farm_down`
and `_dp_insert_not_ready`. Pinned: `tests/test_minior.py` fix 3.

### turnsToLive walks the defender's FROZEN move order (2026-10-24)

PvPoke's TTL loop iterates `opponent.activeChargedMoves` -- the post-shuffle
order from `resetMoves`, not ascending energy; the two differ exactly when
the shuffle promoted a move (Minior vs Drapion 1-1 461/538 -> 680/319).
`_ensure_dmg_cache` reads the defender's `_dp_init_cache['order']` when that
cache already exists (ascending fallback otherwise), and
`_ensure_dp_init_cache` invalidates `_dmg_cache_opp` after building so the
arrays rebuild in the frozen order. Do NOT build the init cache from inside
`_ensure_dmg_cache`: `reset_for_battle`'s damage-cache call runs before the
shuffle-stamp restore, which broke the Aegislash reuse test. Pinned:
`tests/test_minior.py` fix 2.

### Battle-start freeze order is per seat, change-after-freeze (2026-10-24)

See "Form change gotchas" item 7(b): `simulate()`'s setup loop mirrors
`Battle.start` -- for each seat, `_ensure_dp_init_cache(opp)` and the
`_cached_damage` stamps against the opponent AS IT STANDS, then that seat's
`battle_start` form change. Freezing lazily at the first DP call (after both
changes) got seat 0 wrong whenever Minior sat in seat 1. Pinned:
`tests/test_minior.py` fix 4 (both seats).

### Cooldown gates DECISIONS, not landings; a form animation resets both (class A, 2026-10-24)

`Battle.js:548`: at the end of a round, `if(roundChargedMoveUsed ||
roundFormAnimation) poke.cooldown = 500` for BOTH Pokemon. The charged-move
arm is from 2019 and our turn model always reproduced it; the
`roundFormAnimation` arm (new in `4d2908fac`, set only by the `hp`-trigger
change at `Battle.js:1668`) fires only on Minior's Meteor -> Core flip. In
PvPoke cooldown only gates `getTurnAction` (`:732`), while a queued fast
resolves on its own turn clock (`:405-410`): after the reset BOTH Pokemon
may act again next turn while a fast already in flight still lands on
schedule, so a Pokemon can decide with its own fast in the air and a 4-turn
mover can have two fasts in flight. Ported in `simulate()`: `_queued_fasts`
is a LIST; the Phase B gate is PvPoke's plain `cooldown == 0` (a landing
fast still shows cooldown 1 at decision time, so normal flow is unchanged);
the new-mechanics landing no longer zeroes the attacker's cooldown; TTL and
the two DP adjustments test `defender.cooldown` as PvPoke does;
`_optimize_move_timing` counts the attacker's own queued fasts
(`ActionLogic.js:301-313`); a fast-triggered flip sets both cooldowns to 1.
Sweep 41 -> 4 open cells, audit unchanged. Pinned: `tests/test_minior.py`
fix 5. `docs/pvpoke_divergences.md` item 10.

Two lessons from attributing those cells: (1) PvPoke's decisionLog "uses X"
is logged at RESOLUTION, not at queue time; (2) **pin `level=` in audit and
sweep specs when a species' GL best level exceeds 50** -- Lickitung 7/15/15
is best-buddy 50.5 under our default cap and 50 under PvPoke's autoLevel,
and that one level moved Acrobatics across a floor boundary (99 vs 98) in
ten cells that looked like engine divergences.

### CMP tie resolution: exact ties fall to player index (PROP-1)

Charge-move priority (CMP) orders two same-turn charged moves by `cmp_atk`
(the pre-shadow attack), higher first. On an **exact** tie the engine applies
**no** priority -- `use_priority = (p0.cmp_atk != p1.cmp_atk)` is False
(except the Cramorant mirror, which forces it on; gotcha 5), so
`charged_actions` keeps its build order: **player 0's charged move resolves
before player 1's, and neither cancels the other** (the cancel guard is also
gated on `use_priority`). PvPoke-faithful (Battle.js skips the attack-sort
when the attacks are equal); a documented property, not a divergence:
whichever Pokemon is passed as `p0` wins an exact CMP tie. The asymmetric
`>=` at the `wins_cmp` sites and the strict `>` at the `cmp_bonus`/turns
sites are the per-perspective shadows of this rule: the evaluated side takes
the tie but earns no turn *bonus* from it.

### selfBuffing / selfDebuffing thresholds

PvPoke gates these flags on `buffApplyChance`: `selfBuffing` = chance == 1
only (guaranteed buffs); `selfDebuffing` = chance >= 0.5 (excludes low-chance
like HJK at 10%); `DRAGON_ASCENT` is explicitly excluded from selfDebuffing.
They drive the shield policy: guaranteed self-buff moves use the
`wouldShield` heuristic, chance-buff moves are always shielded.

### Form change gotchas

Non-obvious behaviors that are easy to get wrong:

**1. HP does not scale on form change.** When Aegislash switches between
Shield form (97 atk, 272 def) and Blade form (272 atk, 97 def), HP and
max_hp stay fixed at the STARTING form's values -- PvPoke's `changeForm()`
explicitly comments out the HP update (`//this.stats.hp = newStats.hp;`).

**2. Aegislash Blade form uses whole levels only.** Shield -> Blade rounds
DOWN to the nearest whole level (a Blade that could be 22.5 sits at 22);
PvPoke's `getFormStats()` does this via `newLevel--` (discovered by
cascade1185, explained by Caleb Peng). Players picking an Aegislash to power
up need the Blade level to land on a favorable whole number.

**3. The Blade->Shield reverse level formula can overshoot OUR CPM table
(not PvPoke's) -- a deliberate divergence.** PvPoke's `aegislash_shield`
branch overshoots the Shield level (`blade_level / 0.5 + 2` in GL) then
walks down until CP fits, using cpms entries up to level 55. Our table ended
at 51.0 when this crashed the first Aegislash (Blade) GL dive (`KeyError:
52.0`, 2026-06-11); it now ends at 52.0 (Mega Level 4), so the GL start fits
and only higher starts are clamped. `_aegislash_shield_level` clamps its
start to `max(CPM)` -- levels above the table don't exist in-game, so this
is the defensible choice, but PvPoke's shield-revert stats can sit above ours
where the clamp bites (`tests/test_pokemon.py::TestAegislashShieldLevelOverflow`;
the `formchange.py` docstring still says 51.0). Blade really reverts to
Shield in-battle (`activate_shield`), so this is load-bearing.

**4. A fast landing after a mid-flight revert credits the CURRENT form's
energy (FIXED 2026-07-03).** When Aegislash (Blade) shields a charged move
with its own multi-turn fast in flight, the `activate_shield` revert swaps
its fast to the Shield variant, and the in-flight fast lands with the new
move's damage AND energyGain (6, not the old 9), as in PvPoke. Pinned by
`tests/test_fc1_aegislash_revert_energy.py`.

**5. Cramorant is the first MULTI-form / variable-target changer (ported
2026-08-24 from pvpoke 78c64048a).** `FormChangeConfig.forms` is N-length
(base/Gulping/Gorging, order pinned; `BattlePokemon._form_idx`).
`alternativeFormId: "variable"` resolves at the `charged_move` trigger: prey
= Gulping iff hp/max_hp is STRICTLY > 0.5 post-attack. Gulp Missile is NEVER
in `charged_moves` (a 0-energy charged move would break ~30
affordability/DPE sites); it lives in the per-instance `_extra_charged`
registry and is inserted into `_resolve_charged`'s action list when a
prey-holder takes an unshielded, non-instant charged hit, dealing flat
`floor(0.15*target_max_hp)+1`; tags `instant` (unshieldable) and
`ignoresFaint` (fires from the grave; lethal both ways = 500/500 draw).
`use_priority` is forced True in the mirror. AI adds: the Dive/Surf-ASAP pre-farm-down rule, prey-holder
energy stacking (on bandaid[918]'s gate), and four wouldShield tail rules,
two of which replicate PvPoke's shipped `move.moveID` TYPOS as-is for oracle
parity (a lethal Dive is never shielded); the tail also ports upstream's
Aegislash-shield-form rule. Oracle: 4 audit matchups x 9 exact + 54 fixture
cells (`tests/test_cramorant.py`). Policy tiers: `docs/cramorant_policy_plan.md`.

**6. Shield-form Aegislash prices its CHARGED moves at the Blade atk (FIXED
2026-09-27).** Every Shield-form charged throw changes form
(`activate_charged`) BEFORE damage resolves, so it lands with Blade stats;
PvPoke's estimate knows this (`DamageCalculator.js:43-50`). Ours used the
Shield atk (Shadow Ball estimated 44 vs Azumarill, dealt 91), so every
consumer -- farm gate, DP plan, bandaid[918], TTL, the opponent's
would_shield -- passed up KOs PvPoke takes. Fixed in
`BattlePokemon._charged_atk_base`, the ONE source for the charged rows of all
three damage builders (the fix must live in the caches, a gate-only fix fixes
nothing); keyed on the current form's trigger, so every other case takes
`self.atk`, and fast moves always use the current form's atk. Pinned by
`tests/test_battle.py::test_aegislash_shield_charged_estimate_uses_blade_atk`.

DELIBERATE DEVIATION -- the atk STAGE. We multiply the Blade atk by the
CURRENT atk-stage multiplier; PvPoke uses the stage-blind Blade atk although
its own throw applies the stage, so after an atk debuff PvPoke over-estimates
(Shadow Ball 91 at -1 where 73 is dealt). It is the whole of the
`cradily_vs_aegislash_blade` oracle xfails (1,1)/(1,2)/(2,2); pinned at our
value by `tests/test_form_change_oracle.py::
test_cradily_vs_aegislash_blade_estimate_stage_divergence`. Kept because
PvPoke's choice is internally inconsistent and not demonstrably better;
revisit if that changes. `docs/pvpoke_divergences.md` item 7.

**7. Minior: the first `battle_start` + `hp` changer, and the freeze is
seat-dependent (2026-10-24).** The stored, CP-capped form is Core (218/131);
`simulate()` changes it to Meteor (116/194) in its setup, at the level
`formchange._minior_meteor_level` gives (PvPoke's formula + whole-level walk,
bug #11), with HP locked to Core's (item 1). Meteor drops ONE WAY to Core
when `hp / max_hp < 0.5` with hp > 0, checked after EVERY landing on it --
fast or charged, shielded or not (`_apply_hp_form_trigger`,
`Battle.js:1644-1670`). Both sides hold charged energy while a shell is up
(`DP[minior_hold]`) and `would_shield` spares the shell when `damage * 2 <
hp`. Two gotchas: (a) the hp check runs at the END of the attacker's useMove,
so a landing that flips the form re-prices every fast still in flight
(`_fast_results` is recomputed after a landing's hp-trigger), and fast
landings resolve in queue order (queued turn, then seat); (b) PvPoke's
`Battle.start` runs each seat's `resetMoves()` (the freeze, divergence #3) and
THEN that seat's battle_start change, so with Minior in seat 1 the opponent
freezes against CORE and in seat 0 against METEOR; `simulate()` reproduces
that per seat (Ariados vs Minior 2-1: 625/375 PvPoke-exact, vs 265/734
freezing after both changes). Unknown gamemaster triggers now raise
(`formchange._check_trigger`) instead of silently simming the stored form.
'Minior (Core only)' (`data.SPECIES_VARIANTS`) is the same Core spread with
the form change stripped -- a Minior re-entering battle already flipped
(`resetOnSwitch: false`). Pinned in `tests/test_minior.py`.

## Active alt-moveset opponent variants

`opponent_pools/active_variants.toml` lists project-wide alt-moveset opponent
variants that auto-merge onto every loaded pool (`deep_dive.py`
`_apply_active_variants`; skip with `--no-active-variants`), for a meta
species with a competitive fast-move split. Each `[[variants]]` entry:
`species` (PvPoke speciesName, base form), optional `shadow`, `fast` and/or
`charged`, free-form `note`; display name auto-generated (`Forretress
(Shadow) (Bug Bite)`). A variant absent from the loaded pool is skipped, so
one TOML ships across leagues; an inline collision in the pool file wins. The
same `| fast=ID` / `| charged=A,B` syntax works on pool lines
(`_parse_opponent_pool_line`) for pool-specific variants.

## Deep dive output file layout

Deep dive HTML files and their logs are user-specific scratch, never
committed: anything you might revisit goes under `userdata/dives/`
(gitignored, survives reboots); throwaway in-session smokes go to the
session scratchpad, not `/tmp` (CLAUDE.md shell hygiene). Reference dives
under `docs/validations/` are checked in deliberately.

## Log file layout

`scripts/deep_dive.py` and `scripts/deep_dive_slayer.py` route progress,
warnings and final tables through the structured logger
(`scripts/deep_dive_logging.py`; design: `docs/structured_logger_design.md`).

- **Per-run log file**: `userdata/logs/YYYY-MM/YYYYMMDD_HHMMSS_<species>_
  <league>[_shadow].log` (gitignored), INFO/WARNING/RESULT plus DEBUG under
  `--verbose`. **Latest-run symlink** `userdata/logs/latest.log` is swapped
  atomically; `tail -f userdata/logs/latest.log` is the canonical monitor.
- **Flags**: `--verbose`, `--quiet` (INFO off stdout; WARNINGs and RESULT
  records still appear), `--log-file PATH` (`/dev/null` disables the file
  handler), `--log-dir DIR` (ignored when `--log-file` is given).
- **Worker processes**: spawn-mode pool workers do not inherit handlers; each
  pool initializer calls `deep_dive_logging.worker_log_setup(log_path,
  verbose=...)`, and a new multiprocessing surface must thread both through
  `initargs`. CLAUDE.md "Debugging conventions" has the ad-hoc-print rules.
- **Cleanup**: `scripts/clean_logs.py` (dry-run default; `--older-than`,
  `--keep-last`, `--archive`; `--execute` to act). No auto-purge in
  `deep_dive.py`.

## All-in-one vs split-moveset HTML

The all-in-one interactive HTML (`--interactive` without `--split-movesets`)
generates the Deep Dive Results section once for the top-ranked moveset
only; the moveset dropdown swaps the scatter data and the IV Flavor Guide
narrative, but the rest of the analysis stays on the top moveset. In
`--split-movesets` mode each file gets its own full
`generate_analysis_sections` call, so every section reflects its moveset --
the intended website experience (all-in-one is for quick interactive
score-distribution comparison during development). A tripwire in
`generate_interactive_html` verifies each split file's results subheader
names that file's moveset (why: CHANGELOG archive, 2026-06-10 history note).

## Dive-card spreads: `card_specs` is the only selection rule (2026-09-17)

`deep_dive_which_build.card_specs` is the ONLY spread-selection rule on a
dive page; the stat-extreme "poles" that the scatter overlay, the threat
chips and "Top Picks" used to choose independently are gone, as is Top
Picks: `data_obj['recIvs']` (overlay) = the card's spreads;
`data_obj['recNames']` (chips) = the card titles' short forms; the L51 pass
reuses the league-cap spreads. **Fallback when a page has no builds**:
composite-score `rec_candidates`, filtered by the `efficient_frontier`
strict-dominance guard, capped at `REC_MAX_SPREADS`, labelled "Top pick #N".
Never a pole: `tests/test_card_pole_tiebreak.py` pins the retirement (a pole
that came back would re-open the 2026-06-24 UL Mimikyu dominated-spread bug).

**Names and SP1.** One canonical short name per standout ("Most matchups
won", "Highest avg battle score"; `CARD_SHORT` / `STANDOUT_KIND`), every
surface LEADS with it. "Stat-product rank-1 (SP1)" is defined once per
surface and written SP1 everywhere else (`deep_dive_which_build.sp1_prose`);
the standalone card defines "SP #N" and "SP1" in its own foot. Each standout
prints the matchup LISTS behind its counts (`deep_dive_builds.standout_block`)
and `n_profile_peers`, the OTHER spreads that win every decision matchup it wins.

**The nested wide build** (`deep_dive_builds.wide_build`): at most one region
of the same lattice that (1) holds EVERY member of the primary, (2) is at
least `WIDE_MIN_FACTOR` (2x) its size, and (3) carries a rule at the fidelity
the table prints; ranked among those on how many of the preset's OUTSIDE
standouts it holds, then guaranteed cells, then size. Clauses 1 and 3 are
FILTERS, not ranking terms. It lives at `bl['wide']`, NOT in `bl['builds']`,
so the objectives line, card set, nearest-build search and UpSet columns
keep seeing two or three builds; the opt-in surfaces are the table row and
paragraph under Build 1's, the collapsed summary clause, the standouts'
membership, and the panel (LAST in the payload's `builds` array, `col:
null`). Every count it prints is a RETENTION on the preset's own scale.
Round-by-round record: CHANGELOG.

**Section-plot legend geometry** (two measured, undocumented Plotly 2.35.2
facts behind `_wbFitLegend`): a horizontal legend's DRAWN height is capped at
half the graph height, so size from `gd._fullLayout.legend._height`, not
`rect.bg`; and `Plotly.react` does not re-read the graph div's height -- use
`Plotly.relayout(gd, {autosize: true})` (setting `layout.height` kills
responsive width). The invariant is the PLOT AREA (322-324px); the panel's
height is what moves.

## Article lifecycle

Articles live in `articles/*.toml` and render to
`userdata/website/articles/<slug>/` via `scripts/render_article.py`; schema
in `docs/article_schema.md`. To mark one obsolete, set `[obsolescence]`
`status = "obsolete"`, `as_of`, `note`, re-render, republish
(`scripts/publish_website.sh --push`); the renderer shows a red banner with
the note. `authorship` is `auto` (scaffold) / `both` (human-edited, sim-
backed) / `expert` (fully human-written); the banner colour follows it
(blue -> green -> gold).
