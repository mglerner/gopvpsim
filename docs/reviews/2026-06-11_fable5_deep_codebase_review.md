# Fable 5 deep codebase review — 2026-06-11

> **Status (end of day 2026-06-11):** every finding actionable
> outside a dedicated session was fixed the same day — see the
> CHANGELOG 2026-06-11 entry for the commit-by-commit record. Two
> findings were partially wrong and corrected by oracle probes (E2's
> meter-init premise; the [1,2] residual turned out to be our own
> extra bait-wait condition, not an unported branch). Remaining
> live content here: §I (the S7 register), §H (the split plan), §G
> (the invariants list — permanent reference). Read the rest as a
> point-in-time snapshot.

**Method.** Six parallel read-only review agents (engine core, library,
dive orchestrator, analysis/rendering, JS+website pipeline,
tests+harness), each reading its scope in full, cross-checked against
the local PvPoke clone, DEVELOPER_NOTES.md, TODO.md, and the cached
gamemaster. The orchestrator then spot-verified the three most
consequential claims directly. Static analysis only — the S6 overnight
chain was running, so no pytest, no sims, no `load_rankings` triggers.

**How to read the status tags:**

- `CONFIRMED` — orchestrator independently read the cited code and the
  claim holds at the code level.
- `REPORTED` — agent finding with quoted-code evidence; not
  independently re-verified. Treat as high-quality lead, not fact.
- `NEEDS-ORACLE` — claim about PvPoke-behavior divergence that must be
  verified against `scripts/pvpoke_trace.js` before any code change,
  per the CLAUDE.md divergence policy. Some of these may turn out to
  be wrong about PvPoke, or right-but-intentionally-divergent.

**Standing caveat.** Every fix derived from this doc gets a failing
test first (Goal-Driven Execution), and every engine-fidelity fix runs
the oracle harness + perf gate. Nothing here has been run, only read.

---

## Executive summary

| Area                | Critical | Likely-bug | Fragility | Dead-code | Refactor/nit |
| ------------------- | -------- | ---------- | --------- | --------- | ------------ |
| Engine core (E)     | 1        | 6          | 3         | 1         | 4            |
| Library (L)         | 1        | 3          | 5         | 1         | 5            |
| Dive orch. (D)      | 2        | 4          | 4         | 1         | 3            |
| Analysis/render (R) | 0        | 7          | 4         | 2         | 2            |
| Website/JS (W)      | 0        | 3          | 6         | 1         | 5            |
| Tests/harness (T)   | 2        | 1          | 6         | 1         | 3            |

**The headline findings, in order of consequence:**

1. **D1 (CONFIRMED): the mirror-slayer iteration runs on the 1v1
   scenario only in the standard website chain.** Scenario expansion
   to all 9 happens at deep_dive.py:5465; the slayer call consumes the
   pre-expansion list at :5204. Every published Slayer Builds /
   Top-Mirror CMP / archetype table was computed against 1v1-only
   mirror results while everything else on the page is all-9 — and the
   S2 tie-explosion fix degenerates at nS=1 (live log evidence: round-1
   pool of 1,772 vs the `--mirror-slayer-pool 30` cap).
2. **L1 (CONFIRMED): anchor resolution never applies shadow
   multipliers to shadow opponents.** `_opponent_ref` has a
   `shadow` kwarg; no call site passes it and nothing parses the
   `" (Shadow)"` suffix. Every breakpoint anchor vs a shadow opponent
   is ~20% too strict (def 6/5 too high), every bulkpoint vs a shadow
   too lenient. Empirically visible in the published Sylveon dive:
   the card-verified `squag_fairy_wind_5` anchor (true threshold
   ≈121.4 atk) tags 0 of 78 rows because the unmultiplied threshold is
   ≈145.7. Affects published tier cards and auto-anchors for every
   pool that keeps shadow pairs — which is all of them, by policy.
3. **E1 (CONFIRMED): `buffTarget == 'both'` applies the wrong buff
   array to the opponent.** `_apply_move_buffs` uses `move['buffs']`
   for both sides; PvPoke (and the real game) use `buffsSelf` /
   `buffsOpponent`. Only OBSTRUCT has `buffTarget='both'`: we RAISE
   the opponent's def by +1 per Obstruct instead of lowering it.
   Obstagoon is not in current GL/UL website pools (only the Orlando
   CS pool), so no published dive is tainted — but any future pool
   refresh that picks up Obstagoon would be.
4. **T1 (REPORTED, structural): pytest can refresh the 24h
   gamemaster/rankings cache mid-run.** The `integration` marker
   doesn't fence the arc-S1/S3/S4 tests that hit `load_gamemaster` /
   `get_default_moveset`, so any pytest invocation can trigger the
   refetch — the exact mid-chain corruption hazard this session
   worked around by hand. Fix is cheap (conftest pins
   `data.CACHE_TTL` to infinity during tests).
5. **T2 (REPORTED): the numba JIT kernels and pure-Python fallbacks
   have no equivalence test**, and the suite only ever exercises
   whichever path the machine takes. A divergence in either copy
   passes the full suite on the dev machine.

**Publish-gate implication for S6.** The chain currently running
re-dives all 20 species with D1 and L1 present. The published slayer
tables will be 1v1-only and shadow-opponent anchors will stay wrong.
Options: (a) publish anyway, batch-fix D1+L1(+E1), re-dive again later
(re-dives are cheap-ish now: S4 sweep cache makes unchanged opponents
near-free, but engine/anchor fixes invalidate relevant keys); (b) let
the chain finish but hold publish until the fix batch + targeted
re-dive. Michael's call — flagged in the session handoff.

---

## A. Engine core (battle.py, _dp_jit.py, moves.py, formchange.py)

### E1 — buffTarget 'both' applies wrong buff array — CONFIRMED
critical-correctness · battle.py:2186-2195, moves.py selfBuffing
derivation, battle.py:184-188 shield sub-route · confidence high

`_apply_move_buffs` applies `move['buffs']` to both targets when
`buffTarget == 'both'`. Gamemaster OBSTRUCT: `buffs [0,1]`,
`buffsSelf [0,1]`, `buffsOpponent [0,-1]`. PvPoke Battle.js:1406-1442
selects `buffsOpponent` for the defender. Ours gives the opponent
+1 def per Obstruct instead of -1 — an inverted matchup over a long
fight. Two same-root facets: (a) `selfBuffing` derivation in moves.py
omits PvPoke's `'both'` clause (GameMaster.js:873), so OBSTRUCT isn't
selfBuffing for us; (b) the shield sub-route omits Battle.js:1097-1100's
`'both'` sub-filter, so we always-shield Obstruct where PvPoke routes
through wouldShield. **Fix:** use buffsSelf/buffsOpponent for 'both'
in all three sites; add an Obstagoon oracle fixture via pvpoke_trace.

### E2 — buff meter rounding vs PvPoke accumulator — NEEDS-ORACLE
likely-bug · battle.py:2176-2197 · confidence: mechanism high on our
side; **conflicts with a passing fixture — verify before touching**

Ours: counter fires every `round(1/chance)` uses (chance .3 → fires on
use 3, 6, 9). Agent's read of PvPoke Battle.js:1389-1397: float
accumulator fires on whole-number crossings (.3 → fires on use 4, 7,
10). **However**: the Corviknight mirror (Air Cutter, chance .3, both
sides buffing) passes 9/9 exactly against PvPoke including chargedLog,
which should be impossible if the meters disagree on use 3 vs 4 and a
3rd Air Cutter lands. Either the agent misread PvPoke's meter init/
semantics, or no fixture battle reaches a 3rd buff proc. Resolve with
a long-battle pvpoke_trace probe (Registeel Zap Cannon walls are the
natural case) BEFORE changing anything. The in-code comment "matches
PvPoke's Math.round(1/buffApplyChance)" cites code that doesn't exist
in the current clone either way.

### E3 — would_shield missing selfAttackDebuffing clause — NEEDS-ORACLE
likely-bug · battle.py:474-550 vs ActionLogic.js:1186-1190 ·
confidence high it's absent; medium on impact

PvPoke's final wouldShield clause ("shield the first in a series of
Attack debuffing moves like Superpower": `selfAttackDebuffing &&
damage/hp > 0.55 → shield`) has no counterpart in our port. Affects
incoming Superpower-class moves (Machamp, Obstagoon, Sirfetch'd).
Verify with a Superpower-user trace grid, then port.

### E4 — DP attacker-stage tracking drops negative deltas — NEEDS-ORACLE
likely-bug · battle.py:730-749 vs ActionLogic.js:519-526 · confidence
high on mechanism; medium on net impact

`_cm_buff_delta` returns only positive chance-1 deltas; PvPoke's DP
adds `buffs[0]` regardless of sign, so Draco Meteor / Superpower
plans are damage-discounted in PvPoke's DP but not ours. Stage-table
machinery already supports negative rows (`has_neg`). Interacts with
the documented intentional bandaid[866] divergence — re-run the MG
cluster grid after fixing.

### E5 — lethal-throw slot-1 bait gate missing — NEEDS-ORACLE
likely-bug · battle.py:1146-1164 vs ActionLogic.js:221 · confidence
high on misport; medium on impact

PvPoke gates the slot-1 lethal throw on `!poke.baitShields`; we allow
slot 1 unconditionally, and the in-code comment asserts the inverse of
the JS. In default bait-on mode we can fire cms[1] for the kill where
PvPoke falls through to OMT.

### E6 — Mimikyu disguise-break move selection — NEEDS-ORACLE
likely-bug · battle.py:1062-1074 vs ActionLogic.js:237-251 ·
confidence medium-high

PvPoke breaks disguise only with the pre-shuffle cheapest charged move
(`fastestChargedMove`), and does nothing if that move is unaffordable
or self-debuffing. We scan all shuffled moves and fire the first
affordable non-debuffing one. Current Mimikyu fixtures pass, so add a
trace fixture where the cheapest move is self-debuffing before
changing.

### E7 — TTL DP caps defender energy; PvPoke doesn't — NEEDS-ORACLE
likely-bug (narrow) · battle.py:466, _dp_jit.py:524-526 · confidence
high mechanism, low frequency

Both our TTL implementations clamp hypothetical defender energy at
100; PvPoke's turnsToLive DP lets it exceed 100 (changing KO
detection near full energy). Python and JIT agree with each other.
Either match PvPoke or document as an intentional divergence — it's
currently silent.

### E8 — id()-keyed damage/DP caches can alias — REPORTED
fragility · battle.py:1870-1872, 1930-1933, 2110-2122 · confidence
high mechanism, current impact low

Caches validate on `id(defender)`; CPython reuses addresses, so a
freed-and-replaced opponent at the same address with stages 0/0 would
serve stale damage tables. All current callers construct or reset in
safe pairs; nothing enforces it. **Hardening is one line:** hold
`self._dmg_cache_opp = defender` and compare `is` — a held reference
can't alias.

### E9 — near-KO JIT silently drops states at QUEUE_CAP — REPORTED
fragility · _dp_jit.py:270, 321, 364 · confidence high (code fact)

Queue-full states are dropped with no overflow flag; the Python
fallback is unbounded. The TTL kernel returns `ok=False` and falls
back — the near-KO kernel should too. This is the one place JIT/Python
parity is structurally unguaranteed (pairs with T2).

### E10 — move-dict private-ownership invariant is unenforced — REPORTED
fragility · battle.py:680, 799-808, 2252; documented only in
formchange.py:73-91 · confidence high

Battle code writes `_turns`, `_cached_damage`, and FOCUS_BLAST buff
keys into move dicts; correctness requires every BattlePokemon to own
private copies. All current callers comply by convention. **Fix:**
`__post_init__` copies the dicts itself (also removes caller
boilerplate). Note `charged_move_damage` resolves by `id(move)` —
passing a copied dict raises KeyError, so the copy must happen at
construction, not later.

### E11 — bandaid[866] divergence writeup mechanism is wrong — REPORTED
nit (doc) · DEVELOPER_NOTES "Near-KO DP plan choice" · confidence high

PvPoke's `move.damage` is set by `initializeMove` at battle init and
refreshed by every wouldShield call — it is essentially never
undefined, contra the writeup. The decision and cluster data stand
(measured from traces); the divergence surface is broader than
documented. Correct the writeup; optionally re-size with a grid run.

### E12 — intended_pruning is dead and drifted — REPORTED
dead-code · battle.py:854-980, 1655 + _dp_jit plumbing · confidence high

Zero consumers outside the engine; and the mode compares only
hp/energy/shields where PvPoke's (dead) check also compares buffs —
if ever enabled it would wrongly prune. S7 candidate: delete, or fix
and test if kept for research.

### E13 — fast/charged classification by energyGain misfiles TRANSFORM
nit · moves.py:171-172 · confidence high, impact negligible

Classify charged by `energy > 0` (PvPoke's own test) instead.

### E14 — MAX_TURNS 500 vs PvPoke's 480 — REPORTED
nit · battle.py:43 vs Battle.js:653 · confidence high, impact rare
(timeout walls only). Also: stale "overkill counts" comment on
pvpoke_score.

### E15 — micro-fidelity deltas in OMT turnsPlanned + shield-gate clamps
nit · battle.py:645-654, 218-231 · confidence high facts, low impact
Ours clamps negative turn counts PvPoke lets go negative; decide
match-or-annotate per divergence policy.

---

## B. Library (pokemon, anchors, thresholds, data, breakpoints, …)

### L1 — shadow multipliers never applied in anchor resolution — CONFIRMED
critical-correctness · anchors.py:432, 624 (call sites), 276-347
(helpers) · confidence high

See headline #2. Fix in the resolvers (detect `" (Shadow)"` /
gamemaster shadow tag → pass `shadow=True`); pin with a Shadow
Quagsire 121.70 resolution test; re-dive affected published species.
Root-cause class: four parallel "effective stats" implementations
apply shadowness inconsistently (see L15 / architecture note).

### L2 — Level-1 bulkpoint anchors one damage tier too lenient — REPORTED
likely-bug (latent) · anchors.py:645-647 · confidence high

`def_for_damage(takes_at_most + 1)` admits defenses that actually take
t+1 damage; the Level-3 path is consistent, making the +1 asymmetric.
Latent (no shipped TOML uses `takes_at_most`), but TODO plans
promoting a bulkpoint to Level 1, which would trip it. Fix + pin
before that promotion.

### L3 — species→speciesId slug too naive — REPORTED
likely-bug · data.py:181 + 4 duplicated sites (anchors.py:880, 899;
deep_dive.py:908, 4721, 4740) · confidence high

Handles spaces/parens only; apostrophes, periods, hyphens break:
Farfetch'd (Galarian), Mr. Mime, Ho-Oh, Sirfetch'd, Porygon-Z →
KeyError → silent pool-skip (logger.warning) leaving matrix holes.
Centralize one slug helper; regression-test over every gamemaster
entry present in rankings.

### L4 — TOML parser ignores unknown keys silently — REPORTED
fragility · thresholds.py:476-601 · confidence high

A typo'd anchor field (`deal_at_least`) silently converts a Level-1
anchor into a Level-3 discover-and-tag anchor. Add per-kind allowlist
rejection — it's the one gap that defeats the existing validation.

### L5 — data.py cache: non-atomic writes, corrupt-fresh-cache fatal —
REPORTED · fragility · data.py:40-63, 104-133 · confidence high

Temp-file + `os.replace`; wrap cache reads in try → refetch; fold
`load_group` into `_fetch_json`. Matters because pytest and dives
write this cache concurrently (see T1).

### L6 — 'little' league half-plumbed — REPORTED
fragility · pokemon.py:49-71 · confidence high

`LEAGUE_CP`/`LEAGUE_MAX_LEVEL` know 'little'; `LEAGUE_CAPS` doesn't →
KeyError in at_best_level/iv_rank/anchors. Also little=51.0 max level
contradicts the dict's own best-buddy rationale. Unify the three
league dicts into one descriptor (also closes L7/L12b drift).

### L7 — pvpoke_default_ivs level discarded — REPORTED
likely-bug (ML-only today) · anchors.py:290-296, 331-337 · confidence
medium

`_lv` from PvPoke defaults is thrown away and re-derived at
LEAGUE_MAX_LEVEL — diverges for master league (50 vs 51), inflating ML
anchor-opponent stats ~0.6%.

### L8 — breakpoints.cmp_threshold has zero callers — REPORTED
dead-code · breakpoints.py:346-384 · S7 candidate.

### L9 — build_auto_anchors docstring Args contradicts body — REPORTED
nit · anchors.py:858-860 · fix the Args line (param is intentionally
ignored).

### L10 — case-variant league keys parse but never resolve — REPORTED
fragility · thresholds.py:634-654 · confidence high

`[Tinkaton.great]` (lowercase) parses fine and silently never
resolves (resolver queries capitalized only). Normalize on load.
Also: narrative top-level tables become phantom species entries.

### L11 — linear gamemaster scans + duplicated helpers — REPORTED
refactor · anchors.py:300-302, 341-343, 561-563 · use cached
`get_pokemon_entry`; merge `_opponent_ref`/`_opponent_atk_ref`;
delete `_select_moves_bulk` (byte-identical twin).

### L12 — three small doc/default inaccuracies — REPORTED
nit · breakpoints.py:91-93 (threshold comment direction), 179-192
(max_level 51.0 default vs league semantics — silently includes
best-buddy levels in scripts/breakpoints.py output), thresholds.py:858
(error message omits bulkpoint).

### L13 — variant display strings silently drop auto-anchor coverage —
REPORTED · fragility · anchors.py:874-910 + deep_dive.py:5307-5313

`'Forretress (Bug Bite)'` resolves to no species → anchor family
silently `[]`. Add a dropped-count to the existing "Resolved N
anchors" log line; strip variant suffixes pre-resolution.

### L14 — _iv_combo_best_level skips CP validation when floor ≥ cap —
REPORTED · nit (unreachable with current data) · pokemon.py:376-386.

### L15 — cache invalidation is inconsistent library-wide — REPORTED
refactor · evolution_lines.invalidate_cache clears 2 of ~6
gamemaster-derived caches · S7: one `gopvpsim.invalidate_caches()` +
one shared effective-stats primitive (the L1 root-cause class).

---

## C. Dive orchestrator (deep_dive.py, slayer, caches, chain)

### D1 — slayer iteration runs pre-scenario-expansion (1v1 only) — CONFIRMED
critical-correctness · deep_dive.py:5204 (call) vs :5465 (expansion) ·
confidence high

See headline #1. Consequences beyond the metric collapse: archetype
tables and `auto_discover_thresholds` consume 1v1-only Phase-2
results; the "matches the JS TOP_MIRROR_N" comment is false in the
default chain; the S2 graded-tie fix degenerates (pool cap 30 blown to
1,772 in today's live log — masked only by cache hits). **Fix:** move
expansion (or pass the expanded list) ahead of the slayer block; log
loudly when slayer runs nS=1 with a non-'all' metric. Note the slayer
cache key embeds the scenario list, so the fix cold-starts that cache
(expected).

### D2 — slayer cache key omits iv_floor — REPORTED (latent)
critical-correctness when triggered · slayer_cache.py:39-60 +
deep_dive_slayer.py:197-213 · confidence high

Cache entries are keyed by positional iv_meta indices; iv_floor
changes the index↔IV mapping; the key has no iv_floor. A
`--species-iv-floor` dive sharing species/league/moveset with a
floorless dive silently reads the other's indices. Add iv_floor to
the key + bump CACHE_VERSION.

### D3 — slayer-cache _move_hash omits buff fields; no engine hash —
REPORTED · likely-bug · slayer_cache.py:27-36 · confidence high

A rebalance touching only `buffs`/`buffApplyChance` produces stale
hits; the manual CACHE_VERSION bump already failed once. Reuse
sweep_cache's engine_hash + gamemaster_hash.

### D4 — replay never restores _OPPONENT_VARIANT_REGISTRY — REPORTED
likely-bug · deep_dive.py:701, 2411-2441; replay_analysis.py ·
confidence medium-high

Replays of any GL dive (all carry active-variant Forretress) can
render differently than the live dive — the variant opponent's info
silently vanishes via the blanket `except Exception: pass` at
:2440-2441. Serialize the registry into the replay state. This
contradicts the S4 "byte-identical" contract for variant-carrying
dives (S4's verification predated active-variant pools? verify with
one replay diff once the chain is done).

### D5 — reference-moveset dedup is order-sensitive — REPORTED
likely-bug · deep_dive.py:5538-5544 vs :596 · confidence high

Screened movesets sort charged pairs; `--reference` preserves user/
rankings order; dedup compares label strings. Already produced one
duplicate-page incident (2026-06-02), "fixed" by a comment-enforced
convention; every `--reference auto` dive remains exposed. Compare
canonical tuples instead.

### D6 — shadow-focal auto-mirror is a chimera — REPORTED
likely-bug · deep_dive.py:4970-4993 · confidence medium-high

Shadow dive appends plain `args.species` as mirror opponent →
non-shadow stats with shadow-rankings moveset; mirror-synth matches
the non-shadow entry. Masked today because the GL pool carries both
Sableye forms. Append the `(Shadow)` form for shadow focals.

### D7 — three more silent-degradation sites — REPORTED
fragility · deep_dive.py:2310/2608 (mirror synth hardcodes the
`'{mi}_pvpoke'` score key — silently no-op for rank1-only or
bait-off-only dives), :2440-2441 (blanket except around per-opponent
info build), deep_dive_slayer.py:51-52 (silent `({}, [])` under 50
results). Add log lines / narrow the except.

### D8 — Phase-1 screening always bait-on, pre-expansion scenario —
REPORTED · fragility · deep_dive.py:1013-1057 · document or thread
`focal_bait` through.

### D9 — iv_sweep's 4 parallel call sites — REPORTED
refactor · deep_dive.py:5101, 5478, 5514, 5552 · introduce a
SweepConfig dataclass; this is the natural seam for the split's
sweep.py.

### D10 — sweep/slayer worker near-clones — REPORTED
refactor · verified in-sync through the S1 form-change commit, but
enforced only by parallel editing. Split plan: single
`build_battle_pair` + `profile_key` in sweep.py, imported by slayer.

### D11 — confirmed-dead orchestrator code — REPORTED
dead-code (S7 register) · `load_thresholds` legacy JSON loader
(:149-169); re-export aliases `_slayer_worker_init`/
`_slayer_iter_worker`/`_build_focal_meta`; `screen_n` double-assign
(:4988); write-only `focal_in_opponents`; unused slayer-worker
base-stat params; unused `opponent_name` param. generate_html deletion
blast radius mapped: `classify_iv`, `_threshold_desc`, `_hover_text`,
`THRESHOLD_COLORS`, `_plotly_script_tag` are SHARED (keep);
`hover_text` (rendering) + `load_thresholds` go with it.

### D12 — both disk caches write non-atomically — REPORTED
fragility · sweep_cache.py:153-165, slayer_cache.py:87-96 ·
self-healing on read but silently converts corruption into full
re-sims. Temp + os.replace; debug-log failed loads.

### D13 — run_website_dives.py shebang is python3 — REPORTED
nit · violates the project python-vs-python3 rule; works only because
the chain invokes via `python`.

### D14 — tier-assignment recompute duplicated — REPORTED
nit · deep_dive.py:2195-2215 vs :2669-2689 · have one call the other.

**Verified non-findings worth recording** (agent checked, clean):
signature dedup's CMP-sign theorem holds (`.atk` never stage-mutated);
S4 id()-cache fix is identity-pinned correctly; no `hash()`
nondeterminism in output paths; float accumulation order pinned;
S1 form-change plumbing symmetric across sweep/slayer workers.

---

## D. Analysis / rendering / narrative

### R1 — mirror-synth tier drop sites localized — REPORTED
(this is the known TODO item, now mapped) · deep_dive_narrative.py:
561-582 (strict-subset dedup kills it; no axis guard despite comment
claiming "same stat axis"), :270 (`rest[:3]` selectivity cap can cut
it pre-refine) · minimal fix: exempt `* Mirror Bulk/Atk` names in the
dedup loop (mirroring the :154 exemption) + add the documented
same-axis guard; check the :270 cap needs a mirror reserve slot.

### R2 — "indirect" flavor losses claimed without checking the flavor
actually loses — REPORTED · likely-bug · deep_dive_narrative.py:
339-346 · prose states "will cost several matchups, such as X" for
matchups the specialist cohort may win 60-90% of. Gate on the flavor
cohort's real win rate like the direct method (:414) does.

### R3 — flavor rename can desync tradeoffs keying — REPORTED
likely-bug · deep_dive_narrative.py:479-495, 584-595 · rename
collision overwrites another flavor's tradeoffs; re-disambiguation
renames without moving keys → prose silently empties. Key tradeoffs
by stable id, or move keys in the rename loop.

### R4 — mirror-synth bail uses substring species match — REPORTED
likely-bug · deep_dive_analysis.py:940-946 · "Oinkologne" ⊂
"Oinkologne (Female) Bulk" → male-form mirror synthesis silently
bails. Word-boundary match. Directly relevant to the M/F dives.

### R5 — tier cards claim coverage of boundaries whose HP rider they
don't meet — REPORTED · likely-bug · deep_dive_rendering.py:1829-1844 ·
a tier with no HP cutoff passes the HP-rider filter. Treat missing
cutoff like too-low (or render the unmet rider).

### R6 — analyze/augment_deep_dive are SCORES_GZ-incompatible fossils —
REPORTED · dead-code · both regex `var SCORES = {...}` which is now
runtime-empty; carry stale duplicate copies of banding/cluster/CSS.
S7: teach them to gunzip or delete in favor of replay blobs.

### R7 — tier-card DOM ids collide across expert/sim zones — REPORTED
likely-bug · deep_dive_rendering.py:1751-1822 via 3148/3198 · both
calls restart `ti=0`; expand buttons cross-toggle. Add a per-call uid
prefix (precedent: `ms{idx}` in slayer renderer).

### R8 — auto-gen prose hardcodes "of 9" + tier cutoffs assume 9 —
REPORTED · fragility · auto_gen_narrative.py:594-597, 394-406 ·
honest-prose gate: interpolate len(rates), scale tier thresholds.

### R9 — alpha-section crash on degenerate banding input — REPORTED
likely-bug (crash) · deep_dive_rendering.py:2756/2779 ·
`max(..., default-tolerates-None)` then unconditional `d[1]["..."]`
→ TypeError when all three stats have <3 distinct values (floored/
tiny pools). Guard.

### R10 — mirror-synth strictness mismatches — REPORTED
fragility · deep_dive_analysis.py:1031-1052 · HP-floor pass hardcodes
strict-by-stat; emitted tier tested with `>=` downstream vs strict `>`
gate → member count can contradict the tier's own desc. Carry
`anchor.strict`; emit a `>=`-equivalent threshold.

### R11 — Flavor Guide vs rest-of-page format drift — REPORTED
refactor · scenario format ('1-1' vs '1v1') and opponent color hashing
(10-color raw-case vs 16-color lowercased) differ between
deep_dive_narrative and deep_dive_rendering — same opponent, different
color on one page. Import the rendering helpers.

### R12 — `b[4:]` slice coupling on bullet HTML — REPORTED
fragility · deep_dive_rendering.py:1756-1760 · breaks visibly if
`emit_opponent_ids` is ever enabled on the tier-card path. Pass
toggle_id/top_n properly instead.

### R13 — three wrong-claim heuristics in prose — REPORTED
nit · rendering:2110-2125 (divide by literal 50; HP notes always
print regardless of delta), narrative:1184-1187 (single-flavor branch
hardcodes "favors high bulk" + def-only boundaries even for atk-cut
flavors).

### R14 — `_group_sort_key` dead; `hover_text` static-path-only —
REPORTED · dead-code · rendering:1019-1024 (delete now, zero risk),
:507-556 (goes with generate_html in S7).

### R15 — docstring says 6/9 gate, code uses 5/9; over-broad except in
type-effectiveness; 'atk tilt' tooltip overclaims — REPORTED · nit ·
deep_dive_analysis.py:905-923, auto_gen_narrative.py:242, 1544-1604.

---

## E. Website / JS / pipeline

### W1 — format_md table-detection false positives — REPORTED
fragility (always-on hook) · format_md.py:288-308, 161-172 ·
indented tables get a phantom first cell + de-indent; `\|` and
code-span pipes split cells. **No current .md triggers either**
(grepped), but the hook runs on every .md write. Fix both + add an
idempotency corpus test.

### W2 — chain_status log glob hardcodes 2026 — REPORTED
likely-bug (time bomb) · chain_status.py:54 · on 2027-01-01 the
monitor silently goes blind. One-char-class fix.

### W3 — missing SCORES key hard-crashes the dive page — REPORTED
fragility · deep_dive_engine.js:207-236 · partial mode-matrix dives
let the user select a nonexistent oppIv×bait combo → TypeError →
frozen UI. Latent (published dives carry the full matrix). Fall back +
sync dropdowns, or emit bait dropdown only when the full product
exists.

### W4 — table-sort collapsed-state check runs after sort — REPORTED
likely-bug · deep_dive_engine.js:1091-1110 · comment says "before
sorting"; code sorts first → collapsed table can silently expand with
a desynced button label. Compute before sort; share MAX_VISIBLE.

### W5 — article generator assumes sibling dives share opponent order —
REPORTED · fragility · generate_article.py:330-375, 1577-1599 · zips
first file's names against sibling files' rates; a stale sibling
publishes wrong per-opponent numbers silently. 5-line guard: assert
opponent-list identity across siblings.

### W6 — legend item listeners accumulate across renders — REPORTED
likely-bug · deep_dive_engine.js:2788-2815 · gd-level handlers are
guarded; per-item listeners aren't — N stacked toggles make
click-to-lock appear broken after dropdown churn. Guard per element;
generation-stamp the async retry poller. (Medium confidence — d3 node
reuse inferred, not executed.)

### W7 — chain_status regexes degrade silently; slug class rejects
digits — REPORTED · fragility · chain_status.py:201-208 etc. ·
`porygon2-*`-class slugs vanish from the Dive line today. Widen to
`[a-z0-9-]+`; add a canned-log-line self-test so format drift fails a
test instead of blanking the monitor.

### W8 — website-index slug parsers break on multi-word species —
REPORTED · fragility · build_website_index.py:103, 309-311 ·
`mr-mime`/`tapu-fini`/`ho-oh` → species "Mr"/"Tapu"/"Ho". Two
divergent token-class sets in the same file. Unify; longest-prefix
match against gamemaster slugs.

### W9 — publish gates verify a frozen Oinkologne-only surface —
REPORTED · fragility · publish_website.sh:62-75 +
verify_no_unicode_dashes.py:122-139 · rsync --delete ships the whole
tree; link/dash verification covers four hardcoded paths. Also
build_guides renders with `smarty`, which MANUFACTURES the banned
en/em-dashes from `--` in guide markdown — outside the verified
surface. Enumerate surfaces from the tree; drop smarty or
post-process.

### W10 — article flip-badge logic duplicated Python↔JS; JS toggle
drops deep-link rewrite — REPORTED · refactor · generate_article.py:
1365-1510 vs 1603-1745 · badges keep stale hrefs after a toggle.
Data-attributes + one shared JS renderer when next touched.

### W11 — 11 unreferenced patch_dive_* retrofit scripts — REPORTED
dead-code (S7 register, gated) · only patch_dive_engine /
opp_anchors / tier_anchors are referenced (retrofit_3_dives.sh,
itself historical), and patch_dive_species_narrative is LIVE in the
chain (run_website_dives.py:420) — keep that one regardless.

### W12-W15 — nits · unescaped pasted-CSV species in hover HTML +
no-embedded-newline CSV parity gap (engine.js:380-401,
user_collection.js:119); contradictory Top-Mirror cohort comments
(engine.js:2042-2056 — code includes focal; delete the stale
sentence); Matchups-Kept sort is uncached O(50M ops) per header click
(engine.js:2249-2262 — give it the per-shield-Δ cache treatment);
article matchup-table sort indicator lies on load
(generate_article.py:1835-1931).

---

## F. Tests & harness

### T1 — pytest can refresh the live data cache mid-run — REPORTED
critical-correctness (operational) · data.py:13/44 + unmarked tests in
test_slayer_smoke, test_sweep_cache, test_signature_dedup,
test_dive_worker_form_change, test_anchors, test_data · confidence high

The `integration` marker doesn't fence gamemaster/rankings loads;
`pytest -m "not integration"` can still trigger the 24h refetch. This
is the documented reproducibility hazard AND the reason this review
couldn't run tests. **Fix structurally:** conftest fixture pins
`data.CACHE_TTL = float('inf')` (and optionally fails loudly on a cold
cache) for all test runs; then mark the genuinely-network tests.

### T2 — no JIT↔Python equivalence test — REPORTED
critical-correctness (latent) · _dp_jit.py / battle.py:35-36 ·
parametrize a handful of existing oracle fixtures with
`battle._NEAR_KO_DP_JIT`/`_CALC_TTL_JIT` monkeypatched to None;
assert identical scores+chargedLogs. Pairs with E9's overflow flag.

### T3 — selfDefenseDebuffing shield gate has no passing test —
REPORTED · likely-bug-shaped gap · the only tests through that path
are the 7 MG xfails; a regression keeps them xfailing (different
wrong score, still XFAIL) and the suite stays green. Add the resolved
probe (MG vs Florges [2,0], d1=0) as a passing fixture.

### T4 — no xfail_strict — REPORTED
fragility · pyproject.toml · the project's own policy depends on
XPASS being loud (Mimikyu precedent). `strict=True` on the
divergence-pin markers (Aegislash + MG); leave the gamemaster-drift
xfail non-strict.

### T5 — audit_chargedlog_fixtures.py superseded + stale — REPORTED
dead-code · hand-duplicates fixtures (the exact typo-risk the newer
audit_oracle_harness avoids); not updated for the June rebalance. S7
delete candidate.

### T6 — MG UL fixtures outside any audit — REPORTED
fragility · audit_oracle_harness is GL-only; the 7 hand-typed UL MG
scores (2026-04-15, pre-rebalance) have had no re-vet, and being
xfail, staleness is doubly invisible. Add per-matchup `cp` to the
audit + the MG cluster as known-divergence cells.

### T7 — reset_for_battle reuse untested for Mimikyu/Morpeko — REPORTED
fragility · `_REUSE_MATCHUPS` covers buffs/Zap-Cannon/Aegislash; the
two stateful one-shot mechanics (disguise + permanent -1 def stage;
hunger toggle + Full-Belly re-entry) are exactly what would leak
across the 9-scenario reuse loop. Two more parametrize rows.

### T8 — deep_dive.py exec'd 7 times per test run — REPORTED
refactor · seven importlib loads, one (deliberately) registered in
sys.modules, plus an order-dependent eighth via `import deep_dive` in
test_pokemon. One shared conftest loader.

### T9 — pvpoke_trace.js shim-drift register — REPORTED
fragility · the harness depends on: tab-sensitive string anchors in
ActionLogic.js (one probe — termAnchor at line ~132 — silently skips
instead of throwing; make it throw), the GameMaster $.ajax boot
protocol, Pokemon.js API (initialize/autoLevel/setIV/selectMove slot
semantics), Battle.js logDecision + literal log strings, and a
DUPLICATED copy of Ranker.js's score formula. Add the dependency list
as a header comment; assert the score formula against a known cell at
boot.

### T10-T13 — smaller test-quality items — REPORTED
Vacuous-pass guard in test_pvpoke_score_perfect_win (assert the
precondition instead of gating on it); `<=` energy-lead assertion
can't catch a no-op; skip-guards on committed TOMLs convert deletion
into silence (drop them); chance<0.5 self-debuff meter explicitly
untested (synthetic 10%-meter test); doc-reference oracles re-resolve
movesets at runtime (deliberate, but log the resolved moveset in the
assert message).

---

## G. Merged load-bearing invariants (preserve through any refactor)

Engine:
1. Move dicts are PRIVATE per BattlePokemon (written: `_turns`,
   `_cached_damage`, FOCUS_BLAST buff keys). Enforced by convention
   only (E10). `charged_move_damage` resolves moves by `id()` —
   copies raise KeyError.
2. Damage/DP caches are sound only for a stable attacker/defender
   pair; any stat/move/form mutation must invalidate BOTH sides
   (formchange does; nothing else may mutate without doing the same).
3. `_ensure_dp_cache` contents may depend only on (opponent,
   atk_stage, def_stage) + static move data — nothing
   hp/energy/shields-dependent.
4. DP queue insertion order is semantic (farm `<=`, ready `<=`+dedup,
   not-ready `<`) and hand-mirrored in the JIT; change both or
   neither.
5. Stage-table rows alias the root for unreachable stages; reachable
   = exactly what `cm_buff_delta` can produce (E4's fix must update
   `has_neg` in both Python and numpy builds).
6. TTL JIT buffers are rebuilt by `fast_move_damage` — the ensure
   call must precede the kernel.
7. `simulate()` is not reentrant (module-global trace state);
   parallelism stays process-based.
8. `use_priority` frozen at battle start from base atk (matches
   PvPoke, including the mid-battle form-change quirk).
9. `_DPState.hp` float-but-integer-valued; exact `==` dedup — keep
   damage integral.

Library:
10. damage = floor(K·atk/def)+1 pairs with non-strict `>=` on the
    atk side and strict `>` on the def side; the two derivations are
    coupled (L2 is what breaking this looks like).
11. TOML league keys are capitalized; the bridge is exactly
    `.lower()`/`.capitalize()` (L10).
12. Registry merge is overlay-wins at spread/anchor level; auto-gen
    is gated per-kind by existing anchor kinds.
13. Anchor name grammar (`auto_`, `_brkp_`/`_blkp_`/`cmp_vs_`,
    `::label`) is parsed downstream — renames change rendering.
14. Aegislash Blade whole-level rounding exists at FOUR sites
    (pokemon.py:235, :280, breakpoints.py:220, deep_dive.py:1107).
15. Gamemaster shadow entries carry base stats; shadowness is applied
    exactly once via the flag (L1 is what forgetting looks like).
16. `get_moves()` mutates the shared gamemaster cache with derived
    flags at first call (E1's flag fix propagates globally —
    intended, but know it).

Pipeline:
17. Canonical IV order (a→d→s post-floor) is the universal index
    space: canonical_scores flattening, sweep-cache rows, JS DATA
    arrays, slayer focal_idx, replay blobs. Changing enumeration
    corrupts both disk caches (slayer cache has no guard — D2).
18. `score_arrays` keys are `'{mi}_{composite_mode}'` with bait-on
    collapsing to the bare mode; consumers hardcode `'_pvpoke'` (D7).
19. Profile tuple `(pk, atk, def_, hp, a, d, s, level)` + per-IV
    extension for formChange species must stay synced between sweep
    and slayer (D10).
20. Opponent identity is a free-form display string requiring the
    process-local variant registry (D4).
21. Moveset 0 = landing moveset; split files re-index; the tripwire
    assertion at deep_dive.py:3840-3844 guards the fa34f39 bug class —
    never reintroduce cross-file rendered-HTML caching.
22. Spawn-mode workers resolve by qualified module name; cross-module
    attribute injection (slayer.compute_iv_metadata) exists only in
    the parent.
23. Determinism contracts: int scores; gzip mtime=0; md5 not hash();
    float accumulation in canonical (si,oi) order.
24. `sweep_cache._ENGINE_FILES` must list every behavior-bearing
    gopvpsim module; extending gopvpsim requires extending the tuple.
25. The dive HTML is the database: `var DATA = `…`;\n` string-slicing,
    sibling opponent-order alignment (W5), slug functions synced
    across four sites, log-line formats as chain_status's API, JS
    collection parser mirroring user_collection.py row-for-row.
26. Win boundary is `score >= 500` (ties win) — hardcoded at several
    sites beyond the `win_threshold` parameter; sweep all if it ever
    changes.
27. format_md runs on every .md write and must stay idempotent and
    content-preserving (W1 marks the current boundary of that
    guarantee).

---

## H. deep_dive.py split plan — validated & revised

The TODO "Refactoring" plan is partially stale: anchor_flips, most of
slayer, and the per-section renderers are ALREADY extracted
(deep_dive_analysis.py / deep_dive_slayer.py / deep_dive_rendering.py).
Revised plan from the section map (full map in the orchestrator-agent
report, agent a5a2dc9):

1. **Pre-split shrink (S7, gated):** D11 dead code + generate_html
   deletion (~450 lines) — shared helpers identified, blast radius
   mapped.
2. **New module the plan missed: `opponents.py`** (deep_dive.py
   :664-970 — variant registry, parse_opponent_spec, pool parsing,
   active variants, atk-weighted expansion). Both sweep.py and
   render.py need it; without it the split creates the circular dep
   the plan worried about. Move `_OPPONENT_VARIANT_REGISTRY` with it
   and fix D4 in the same cut.
3. **Dependency order:** opponents → sweep (needs opponents +
   sweep_cache + signature; absorbs compute_iv_metadata +
   profile-key helpers, killing the slayer attribute-injection) →
   slayer → categories (pure) → render → residual deep_dive.py
   (CLI + main + replay glue).
4. **Split `generate_interactive_html` (1,250 lines) first** into pure
   `build_data_obj()` + HTML assembly — the pure half is what replay
   needs and is unit-testable.
5. **RenderContext dataclass** for the 28-kwarg render_results_section
   call; same context feeds narrative + analysis sections (which
   currently re-derive nS/nO independently).
6. **Spawn-mode constraint:** worker resolution becomes
   `deep_dive_lib.sweep._sweep_worker`; sys.path setup must run at
   module import, not in main(). Add a spawn-mode smoke test (the one
   risk unit tests can't catch).
7. **Replay compat:** keep thin re-export shims in deep_dive.py for
   one cycle.

---

## I. S7 cleanup register (all gated on Michael's sign-off)

Dead code: E12 intended_pruning; L8 cmp_threshold; D11 set (legacy
JSON loader, re-export aliases, write-only vars, unused params);
generate_html + hover_text + load_thresholds bundle; R6
analyze/augment_deep_dive (or teach them SCORES_GZ); R14
_group_sort_key (zero-risk, can go anytime); T5
audit_chargedlog_fixtures; W11 patch_dive_* set (11 unreferenced;
keep patch_dive_species_narrative — live in chain; 3 others
referenced only by historical retrofit_3_dives.sh); plus
CANDIDATE-DELETE script inventory from the test agent
(clean_ryanswag_dump, measure_html_size, retrofit_3_dives.sh,
patch_dive_gzip, …) and UNCLEAR items needing a call
(check_sableye_energy_lead — TODO still references it; summarize_perf
— feeds ETA calibration; scripts/moves.py stub).

Consolidations: L11 (gamemaster index + merged ref helpers), L15
(one invalidate_caches + one effective-stats primitive), L6 (one
league descriptor), D9 (SweepConfig), D14 (tier recompute), R11
(shared scenario/color helpers), W8 (one slug parser), W10
(badge renderer), T8 (one conftest deep_dive loader).

---

## J. Recommended sequencing

**Batch 0 — before/at S6 publish decision (Michael):** decide
publish-now-vs-hold given D1 + L1 affect the chain's output. Either
way, D1 + L1 + E1 are the first fix batch; all three are
small-diff, high-blast-radius, and each gets a pinning test
(D1: nS assertion + pool-cap honored; L1: Shadow Quagsire 121.70
resolution oracle; E1: Obstagoon trace fixture).

**Batch 1 — test-infrastructure safety (cheap, do with Batch 0):**
T1 CACHE_TTL conftest pin; T4 xfail_strict on divergence pins; T2 JIT
parity test; T3 shield-gate passing fixture. These make every later
engine fix safely verifiable.

**Batch 2 — engine fidelity round (one session, oracle-driven):**
E2 (resolve the Corviknight contradiction first), E3, E4, E5, E6, E7,
E14, E15 — each: pvpoke_trace probe → decide fix-vs-document per the
divergence policy → harness grid + perf gate. E8/E9/E10 hardenings
ride along (one-liners with tests).

**Batch 3 — silent-wrongness in published prose/cards:** R2, R5, R10,
R13, R4, R1 (+R3), L13, D6, D7. These change rendered claims; bundle
with a replay-based before/after diff on one dive.

**Batch 4 — cache/robustness:** D2, D3, D12, L5, L3, L4, L10, W5, W2,
W7, W1.

**S7 (gated):** section I register + the split plan (section H).

**Fold into existing TODO items:** W3/W4/W6/W12-W15 (JS) ride the
table-sorting/color-modes UI session; R8/R13 ride the auto-gen prose
template session (G1/G2/G7); W9 rides the next publish-tooling touch.

---

*Reviewer agent IDs (resumable this session): engine a3f26a23,
library a9baecea, orchestrator a5a2dc9f, rendering a286bfbd, website
aa5beeed, tests a78d968d.*
