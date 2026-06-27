# Cache-rework bundle — design proposal v2 (2026-06-27)

Status: DRAFT for Michael sign-off. No code written yet. v2 folds in the
2026-06-27 adversarial review (3 red-team agents) + Michael's
clarification: "fine with two separate caches, but share as much
ARCHITECTURE as possible — don't fix GL/UL one session and re-do the same
thing for ML the next."

## 0. The reframe (two findings)

**Finding A — the paths can't share columns.** ML envelope is *master*
league, opponents fixed *15/15/15*, focal at a *64-combo grid* on a fixed
*50/51* level pair; dives are GL/UL, resolved opp IVs, full 4096 at per-IV
`best_level`. Every key field differs -> zero shared columns.

**Finding B — the paths are *transposed*, so they can't even share one
column LAYOUT.** The dive sweep is *opponent-major*: its worker builds a
whole `(n_ivs, n_scenarios)` column for one opponent and writes it
atomically (deep_dive.py:2229-2241, sweep_cache.py:187-205). The ML sweep
is *focal-IV-major*: `won_set`/`score_set`/`result_metrics`
(iv_envelope_analysis.py:147/214/172) fix ONE focal IV spread and loop all
60 opponents — one call touches one *row* of each of 60 columns. Forcing
the ML path onto opponent-major columns means rewriting `main()` steps
2/4/5 + all three sim helpers (a large, behavior-adjacent rewrite). The
review rates this CRITICAL and not worth it.

**Conclusion (UPDATED — Michael 2026-06-27: fold T2 in).** Unify the cache
FOUNDATION *and* the sim loop. The ML path is rewritten to call ONE
generalized `iv_sweep` (the dive's worker), so there is a single
opponent-major sweep engine and a single column-cache layout for both
GL/UL dives and ML guides — the simpler interface we'll want anyway, built
now while it's all in context. The transpose risk (silent score drift from
reordering the validated sim path; blast radius onto the dive worker all
dives depend on) is contained by a **golden-master equivalence gate**: the
pre-refactor ML guide JSON and the existing dive oracle/sweep tests must
reproduce byte-for-byte after the merge (§3b).

Both caches share ONE foundation module that owns everything you'd
otherwise re-implement twice:

- hashing (engine / gamemaster / key) — already shared
- CACHE_VERSION discipline + atomic multi-plane storage
- selective predicate invalidation (per-entry engine stamp)
- version/vintage-aware GC

Add a feature once (energy plane, a new predicate, GC policy) -> all three
caches (sweep, ML, slayer) get it. That is the "share the architecture"
the handoff and Michael actually want; the literal "share columns" premise
in TODO.md:215 is false (Finding A) and the "merge the sim loop" deep
variant is a trap (Finding B).

### Honest payoff scoping (no-overclaim rule)

| change                                 | what it actually buys                                                                                 |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| ML stores scores (not just booleans)   | warm re-run of an UNCHANGED guide is ~all-hits (kills the full warm re-sim, not just 46k — see §3)    |
| predicate invalidation (per-col stamp) | ENGINE fixes (bug #1) -> warm partial re-bake                                                         |
| energy plane on dive cache             | recovers the dive cache, which is **dead today** (`--compare-energy` defaults ON -> forces cache OFF) |
| GC                                     | caps the ~45 GB unbounded growth                                                                      |

What it does NOT buy: a faster *first* cold bake (nothing to reuse), and
**gamemaster-bump re-bakes stay cold** unless the operator drives the
predicate tool with a move-delta predicate (§4) — because the global
`gamemaster_hash` can't be safely dropped (alt-form stats live in a
separate gamemaster entry; slayer_cache.py:66-68 keeps it for exactly this
reason). I'll state this precisely in TODO when we land it.

## 1. Shared foundation: `cache_base.py`

Extract from today's `sweep_cache.py`:

- `engine_hash()`, `gamemaster_hash()`, `_key_hash()` (already there)
- `CACHE_VERSION` discipline (one per cache, documented bump rules)
- **multi-plane entry storage**: an entry is a set of NAMED planes written
  as one `.npz` (atomic tmp + `os.replace`, like put_column today). dive
  entry = `{score: float64, energy: uint8}`; ML entry =
  `{score: int16, won: bool, energy: uint8, hp: uint16, max_hp: uint16,
  shields: uint8}` (see §2/§3). Plane-agnostic get/put.
- **per-entry engine stamp + predicate invalidation** (§4)
- **GC hooks** (§6)

`SweepCache`, the new `MlEnvelopeCache`, and `SlayerCache` all become thin
subclasses/configs. No path changes its sim loop or its key granularity.

## 2. Energy plane on the dive cache (recover the dead cache)

`--compare-energy` already defaults ON (deep_dive.py:6250) and energy-on
forces `use_sweep_cache=False` (deep_dive.py:2093) — so **the sweep cache
is already unused on the default dive path**. This is the single biggest
realized win and it's a recovery, not a new feature.

Fix: always capture energy (free — `result.energy_remaining[0]` is already
computed; bounded int 0..100, stored `uint8` with a store-time
`assert 0<=e<=100` so any future fractional/overflow energy fails loud).
Then drop the bypass. **Three wiring pieces the review flagged (cache+energy
have NEVER coexisted, so the hit path KeyErrors today):**

1. `put_column` writes an energy plane alongside score.
2. cache-HIT fan-out (deep_dive.py:2216-2223) must also populate
   `profile_energy_per_opp` from the cached energy plane (today it only
   fills scores -> `r['per_opp_energy'][(si, oi)]` KeyErrors at :2281 for
   any cached opponent).
3. canonical-order accumulation must stay hit-order-independent for energy
   too (the existing float-order invariant, deep_dive.py:2252).

Energy fan-out by the damage-signature is already proven correct
(`test_compare_energy.py` pins `cs_on==cs_off`; signature groups
bit-identical battles, so identical energy — deep_dive_signature.py:223+).
New test: warm-vs-cold `iv_sweep(use_cache=True, capture_energy=True)`
asserts `canonical_energy` bit-identical (the current tests only cover the
two halves separately, never together).

## 3. ML cache: opponent-major columns on the shared foundation (T2)

The ML path now uses the SAME opponent-major column cache as the dive,
because it now runs the same `iv_sweep` engine (§3b). Per opponent, the
column captures `{score, won, energy, hp, max_hp, shields}` over the focal
grid x shields. (The dive captures only `{score, energy}` — capture set is
configurable per call; planes are stored as captured. The extra fields are
free to read from `BattleResult` and, like score/energy, are bit-identical
under the focal signature dedup because they are deterministic outputs of a
bit-identical battle.)

`won_set`/`score_set`/`result_metrics` stop being per-spread sim loops and
become THIN VIEWS over the assembled `iv_sweep` grid: `won` reads the `won`
plane, `score_set` reads `score/won/energy`, close-calls read all six. So a
warm re-bake of an unchanged guide does ~zero sims (only the `calc_damage`
analytic helpers run). `WonSetCache` is retired; the ML path uses the
shared column cache.

Column key carries `iv_floor` (the `--iv-floor 10` grid is 216 combos not
64; a positional column must not mis-map IV->row), opponent identity, and
the shield set — all already handled by the dive's `column_key_fields` /
`focal_key_fields`, which the ML calls now reuse. `won` is stored
explicitly because it needs the opponent score, which the focal-score plane
doesn't carry.

## 3b. Unified `iv_sweep` + golden-master equivalence gate (the T2 merge)

Generalize the dive's `iv_sweep`/`_sweep_worker` to accept the few axes
where ML differs, then have ML call it:

- `focal_ivs=None` -> full 4096 (dive); ML passes its 64/216-combo grid.
- focal level policy: per-IV `best_level` (dive) vs a FIXED level (ML
  passes `my_lvl` in {50,51}).
- opponent IV/level policy: resolved (dive) vs FIXED `15/15/15` at a fixed
  `opp_lvl` (ML).
- `capture=('score','energy')` (dive) vs the six-tuple (ML).

ML's 2x2 quadrant structure becomes four `iv_sweep` calls (one per
`(my_lvl, opp_lvl)`); `main()` steps 2/4/5 index the returned grid instead
of looping per spread. This collapses three helpers + the quadrant loops
into "call `iv_sweep` 4x, index the grid" — the simpler interface.

**Equivalence gate (the risk container).** Two oracles, both must stay
byte-identical:

1. **Dive side:** the full pytest suite + the oracle harness +
   `test_sweep_cache.py` bit-identity (the generalized worker must not
   perturb GL/UL output). Plus a smoke-dive byte-compare (replay render)
   before/after.
2. **ML side:** BEFORE refactoring, generate reference guide JSON for a
   representative sample — the two `BUILDS` species (Dialga/Palkia Origin)
   + one shadow focal + one floor-10 species — committed as golden
   fixtures. AFTER the refactor, regenerate and assert byte-identical,
   with cache OFF and ON. (Golden is point-in-time / gamemaster-pinned;
   it's a session-scoped equivalence proof, retired or gamemaster-keyed
   afterward.)

If either oracle drifts, the merge is wrong — fail loud, don't ship.
The float-accumulation-order invariant (deep_dive.py:2252) and the
signature-dedup representative selection are the two specific things the
gate is protecting; both are covered by byte-identity.

## 4. Selective invalidation: per-entry engine stamp (not dir-copy)

v1 proposed copying column files between old/new engine focal dirs. The
review showed that's fragile (gamemaster coupling, partial/concurrent
copy, format-bump nullifies it). Cleaner: **move the engine hash OUT of
the focal-dir key and store it as a per-entry stamp** inside each `.npz`.

Read path: stamp == current engine hash -> hit. stamp != current ->
consult a registered predicate: `unaffected` -> serve + re-stamp in place
(bless); `affected` -> miss (re-sim, overwrite). One mechanism, both
caches, no second directory, no copy/concurrency hazard.

Hard preconditions enforced by the bless step:
- **`gamemaster_hash` must be byte-identical** old->new (the predicate
  models only the engine delta; gamemaster stays in the key). Refuse
  loudly otherwise.
- A predicate may only bless what it can PROVE. Bug #1's shadow-XOR
  predicate is proven (single hunk b1b58f1; `cmp_atk=atk/1.2` for shadow;
  both-shadow and both-non-shadow preserve the `>` under a common positive
  divisor — exact, and FP-safe for realistic distinct stats). For a proven
  predicate we drop the 1-2% sampling (it's statistically useless against a
  clustered defect — ~1 column of 60) and instead pin the proof with a
  test. For UNPROVEN predicates: no bless (cold), or stratified
  boundary-targeted re-sim, never blind sampling.

bug #1 predicate: `affected = (focal.shadow != opp.shadow)`. This same
tool handles a localized GAMEMASTER move-rebalance too (predicate
`affected = move in (focal∪opp moveset)`), PROVIDED rankings/base-stats
(hence resolved opp IVs/level/moveset) are unchanged — the operator
characterizes the delta by diffing gamemaster.json.

**Sequencing:** land the foundation + `.npz` format bump BEFORE the bug-#1
engine fix, so the stamp mechanism exists when the fix ships and the
re-dive is actually warm. (If the format bump rides WITH the fix, the
first re-dive is cold — the review's MED finding.)

## 5. Bug #4 — slayer cache focal level cap

`slayer_cache.compute_cache_key` (:50) lacks `focal_max_level` -> Master
mirror-slayer collides across `--max-level` (silent stale hits). Add the
field (mirror sweep's name), bump `slayer_cache.CACHE_VERSION` 3->4, add
`tests/test_slayer_cache_key.py` level-cap-separation case. Independent of
§1-§4; do it first. (Slayer also moves onto the foundation so it gets the
stamp + GC, but the bug-#4 fix itself is just the key field + version.)

## 6. GC tool — `scripts/gc_cache.py`

Walk `~/.cache/gopvpsim/{sweep,slayer,iv_envelope}`, read each entry's
`(engine, gamemaster)` vintage, prune by policy. `--dry-run` default
(report only); `--apply` deletes. Never auto-runs. Default policy:
keep-current-gamemaster (decision D below: + N-1?).

## 7. Phasing (each independently shippable + tested)

1. **Bug #4 slayer key** — isolated, lowest risk, warms up the harness.
2. **`cache_base.py` foundation** + move `SweepCache` onto it, **`.npz`
   multi-plane format**, **energy plane + 3 wiring pieces**, drop the
   `capture_energy` bypass. Pinned by extended `test_sweep_cache.py` +
   new warm/cold energy bit-identity test.
3. **Per-entry engine stamp + predicate tool**, proven on bug #1's
   shadow-XOR predicate (the foundation must exist before the bug-#1 fix).
4. **Generalize `iv_sweep`/`_sweep_worker`** (focal-IV list + level/opp
   policies + capture spec). Pinned by the DIVE-side oracle: full pytest +
   harness + sweep bit-identity + smoke-dive byte-compare all green (no
   GL/UL regression).
5. **Generate golden ML guide JSON fixtures** (pre-refactor reference,
   sample species) — the ML-side oracle.
6. **Rewrite `iv_envelope_analysis` core** to call the unified `iv_sweep`
   per quadrant; `won_set`/`score_set`/`result_metrics` become grid views;
   rewire `main()` steps 2/4/5; retire `WonSetCache`. Pinned by the golden
   guide JSON byte-identity (cache OFF and ON).
7. **`gc_cache.py`** — pure maintenance, last.

The T2 sim-loop merge (steps 4-6) is now IN scope (Michael 2026-06-27),
gated by the two oracles in §3b.

## 8. Cleanups noticed (not blockers)

- `verify_signature_dedup.py:75` mis-unpacks `iv_sweep`'s 5-tuple into 4
  names -> latent `ValueError` if run. Fix opportunistically.
- ML path clamps energy `max(0, int(...))` (iv_envelope_analysis.py:224)
  while dive stores raw — unify on clamp-before-cast + the store assert.

## 9. Sign-off decisions

A. RESOLVED — shared foundation + ONE unified `iv_sweep` engine; ML rebuilt
   on it (T2 folded in, Michael 2026-06-27).
B. RESOLVED (pending C/D) — always capture energy + `.npz` multi-plane
   format, integral to the plan.
E. RESOLVED — T2 in scope, gated by §3b oracles.

C. RESOLVED — per-entry engine stamp (Michael 2026-06-27).
D. RESOLVED — GC keeps current + N-1 gamemaster vintage; `--dry-run`
   default, `--apply` required to delete (Michael 2026-06-27).

All decisions resolved; implementation may proceed per the §7 phasing.
