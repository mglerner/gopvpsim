# Fix packet: shadow-cmp (2026-06-13)

Shadow x1.2 must NOT enter CMP-flavored attack comparisons. Michael
confirmed live-game behavior 2026-06-12; PvPoke agrees (every reference
CMP comparison reads shadow-free `stats.atk`; `shadowAtkMult` exists
only in the damage path: Pokemon.js:1995-2002 getEffectiveStat,
DamageCalculator.js). Largest oracle-grid family: 204 cells tagged
`shadow_cmp`, including ALL 30 winner flips.

Patch: `userdata/fix_packets_2026-06-13/shadow-cmp.patch`
(verified `git apply --check` clean against HEAD f4a3b3e, the
current main tip — note HEAD advanced past the a73d855 session
snapshot via the energy-lead/matchup-web/threshold commits; the
patch was generated from and verified against the newer tree.
Also verified: incoming-gate.patch + bestcm-superpower.patch +
shadow-cmp.patch all apply cleanly STACKED at f4a3b3e, in either
order, in a scratch clone).

## 1. Root cause and seam decision

`pokemon.py:195` folds the shadow x1.2 into `Pokemon.atk`, and
`BattlePokemon.atk` inherits the folded value. Damage needs the fold;
CMP comparisons must not see it.

**Seam: a stored `cmp_atk` value, not a derived property.**
`cmp_atk` is computed directly as `(base_atk + atk_iv) * CPM[level]`
everywhere, never as `atk / 1.2`. Reason: float exactness. The whole
draw semantics (section 3) hinges on base-vs-shadow same-IV pairs
comparing EQUAL; `(x * 1.2) / 1.2 == x` is not guaranteed in IEEE-754,
while recomputing the pre-fold product is bit-identical to the base
form's value. Validated in-session: shadow and base Empoleon 5/15/13
L19 give `cmp_atk == 125.1899635` exactly on both sides.

Plumbing:
- `Pokemon.cmp_atk` property (new, pokemon.py) — the canonical source.
- `BattlePokemon.cmp_atk` init field, default `None` -> falls back to
  `atk` in `__post_init__`. Correct for every non-shadow caller, so
  test helpers and scripts that build non-shadow mons from raw stats
  need no changes.
- `from_pokemon` passes `pokemon.cmp_atk` (covers scripts/battle.py,
  tests/_make_battle_pokemon, audit_oracle_harness, build_matchup_web,
  deep_dive make_battle_pokemon — all route through from_pokemon).
- `formchange.FormData.cmp_atk` (both forms), `apply_form_change`
  swaps it with `atk`, and `attach_form_change` repairs `bp.cmp_atk`
  from the default form (covers dive workers that construct
  form-change species from raw folded stats).
- Dive workers that build BattlePokemon from raw folded stats get
  explicit wiring: `scripts/deep_dive.py` `_sweep_worker` (focal:
  recomputed from `focal_mon` baseStats + a_iv + CPM[lv]; opponent:
  new `opp_cache['cmp_atk']` from `Pokemon.cmp_atk`) and
  `scripts/deep_dive_slayer.py` `slayer_iter_worker` (both sides).
  The worker reads `opp['cmp_atk']` strictly (no `.get`) so a future
  opp_cache builder that forgets the key fails loudly, not silently.

NOT changed (deliberate):
- `scripts/harness_grid.py` — has no shadow support at all (Pokemon
  built without `shadow=`), so its fallback `cmp_atk = atk` is already
  shadow-free. No edit traces to the bug.
- `scripts/profile_slayer.py` — perf profiling, same-shadow mirror,
  no behavioral assertion.
- `gopvpsim/anchors.py:628` `mon.atk > best_atk` — that is a max-ATK
  pick for a damage reference (worst-case incoming damage), where the
  folded stat is the RIGHT one. Not CMP-flavored.
- `iv_rank` / `compute_iv_metadata` folded stats — display/stat-product
  surfaces, untouched.

## 2. Complete CMP-site enumeration (battle.py, 10 sites)

Every comparison of `.atk` against the opponent's `.atk` in
battle.py, with its reference line (PvPoke clone @ 9b7407782, the
same code pvpoke_trace.js executes). All switched to `cmp_atk`:

| battle.py (pre-patch) | context                                    | reference (all `stats.atk`) |
| --------------------- | ------------------------------------------ | --------------------------- |
| 241                   | pvpoke_simulate_shield cycle-KO CMP adjust | Battle.js:1116              |
| 372                   | _calc_turns_to_live `wins_cmp`             | ActionLogic.js:10           |
| 397                   | TTL JIT `cmp_bonus` (hoisted)              | ActionLogic.js:106          |
| 459                   | TTL pure-Python cmp bonus                  | ActionLogic.js:106          |
| 677                   | _optimize_move_timing turns_planned+1      | ActionLogic.js:307          |
| 1038                  | pvpoke_dp `wins_cmp`                       | ActionLogic.js:10           |
| 1114-1115 (+1125)     | fire_now double-fire gate `a_atk > d_atk`  | ActionLogic.js:181          |
| 2312                  | `use_priority`                             | Battle.js:255               |
| 2405                  | simultaneous fast-landing sort             | Battle.js:825-833 priority  |
| 2432                  | charged-action CMP sort                    | Battle.js:825-833 priority  |

(1114 was not in the grid writeup's list; ActionLogic.js:181 confirms
it is also a `stats.atk` comparison.) `_dp_jit.py` needs NO changes:
both kernels take `wins_cmp`/`cmp_bonus` as pre-computed booleans.
Remaining `.atk` reads in battle.py (damage caches, stage tables,
1909/2014 etc.) are damage-path and stay folded. Verified post-edit:
zero remaining `.atk <op> .atk` comparisons in the patched file.

## 3. The mutual-KO draw path: NO porting needed

Second bundled semantic: PvPoke's Battle.js:454/471 — when
`usePriority == false`, a mon fainted by a charged move this turn
still has its own same-turn charged move resolve (`action.valid`
is only revoked under `usePriority`), producing mutual-KO 500/500
draws in base-vs-shadow same-IV mirrors (equal `stats.atk` =>
`usePriority = false`, Battle.js:253-257).

**Verdict: the draw path is ALREADY ported and does not need new
code.** battle.py:2442 gates the charged-KO cancellation on
`use_priority` (`if use_priority and attacker.hp <= 0 and actor_idx
in charged_ko: continue`), and 2450-2454 implements the fast-KO
cancel with the opponentChargedMoveThisTurn exception (Battle.js:
471-490). The ONLY reason we never produced the draws is that
`use_priority` was computed from folded atk (base-vs-shadow same-IV
=> atks differ by x1.2 => use_priority True => the fainted side's
charged is cancelled => we crown a winner). Fixing the 2312
comparison alone re-opens the existing path: winner None, scores
floor to exactly 500/500 (full damage + zero HP on both sides).

Validated in-session against the patched package in /tmp (repo
untouched): Empoleon 5/15/13 L19 base vs shadow, WATERFALL /
HYDRO_CANNON + DRILL_PECK, 0v0 -> 500/500 winner None — byte-exact
with the grid's PvPoke ground truth.

## 4. Patch contents

```
src/gopvpsim/pokemon.py               | +15  (cmp_atk property)
src/gopvpsim/battle.py                | 45+/13- (field, __post_init__,
                                        from_pokemon, 10 comparison sites)
src/gopvpsim/formchange.py            | +10  (FormData.cmp_atk both forms,
                                        apply/attach wiring)
scripts/deep_dive.py                  | +5   (sweep worker both sides,
                                        opp_cache key)
scripts/deep_dive_slayer.py           | +5   (slayer worker both sides)
tests/test_dive_worker_form_change.py | +1   (opp_cache fixture key —
                                        keeps the strict worker green)
```

## 5. Test plan

### Existing tests — expected ZERO changes (statically verified)

Computed folded vs shadow-free predicates for every shadow fixture in
the suite; none flips, so every existing score/log fixture must stay
byte-identical:

- `test_shadow_swampert_vs_registeel` (9 cells): folded 149.54 vs
  96.72, free 124.62 vs 96.72 — Swampert wins CMP either way.
  (Re-validated 1v1 = 902 in-session on the patched package.)
- Corviknight 0/15/2 vs Shadow Sableye 4/15/15 L47 oracle family:
  folded 106.67 vs 143.60, free 106.67 vs 119.67 — Sableye wins CMP
  either way.
- `test_default_moveset_shadow_runs` (Shadow Quagsire vs Medicham):
  folded 136.51 vs 109.86, free 113.75 vs 109.86 — no flip (smoke
  assert anyway).
- JIT parity / reset-reuse parametrizations reuse the same pairs.
- 153-cell audit (`scripts/audit_oracle_harness.py`): its only shadow
  matchup is swampert_shadow vs registeel — unchanged per above.
- Non-shadow tests: `cmp_atk` falls back to `atk`; all comparisons
  bitwise-identical to pre-patch. Corviknight mirror keeps
  use_priority False exactly as before (equal atk == equal cmp_atk).

Important corollary: the current suite has NO coverage of this bug —
that is why the grid found 204 cells the suite never saw.

### New tests to add (tests/test_battle.py)

1. **Unit, no sims** (`test_cmp_atk_wiring`):
   - `Pokemon.cmp_atk == base-counterpart .atk` at same IV/level for a
     shadow mon; `Pokemon.atk == cmp_atk * SHADOW_ATK_BONUS`.
   - `BattlePokemon(...)` without cmp_atk -> `bp.cmp_atk == bp.atk`.
   - `from_pokemon` on a shadow Pokemon -> `bp.cmp_atk < bp.atk` and
     equals the base form's atk exactly.
   - formchange: `build_form_change_state(..., shadow=True)` on the
     Aegislash entry -> both FormData.cmp_atk == their atk / fold
     recomputation `(base+iv)*cpm` (use the direct product, not
     division, in the assertion).

2. **Oracle: base-vs-shadow same-IV mirror draws** —
   `test_empoleon_base_vs_shadow_mirror`. Both sides Empoleon 5/15/13
   L19 (gamemaster defaultIVs cp1500), default GL moveset via
   `get_default_moveset` (currently WATERFALL / HYDRO_CANNON +
   DRILL_PECK), base = p0, shadow = p1, pvpoke_dp both sides.
   Fixture values = PvPoke ground truth from the 2026-06-12 grid
   (scratch_oracle_grid/results.jsonl, harness = pvpoke_trace.js):

   | cell | score(p0) | winner | chargedLog                            |
   | ---- | --------- | ------ | ------------------------------------- |
   | 0v0  | 500       | None   | HC, HC, HC, HC                        |
   | 0v1  | 295       | 1      | HC (shielded), HC, HC, HC             |
   | 0v2  | 90        | 1      | HC (sh), HC, HC (sh), HC              |
   | 1v0  | 704       | 0      | HC, HC (sh), HC, HC                   |
   | 1v1  | 500       | None   | HC (sh), HC (sh), HC, HC, HC, HC      |
   | 1v2  | 340       | 1      | HC (sh), HC (sh), HC (sh), HC, HC, HC |
   | 2v0  | 909       | 0      | HC, HC (sh), HC, HC (sh)              |
   | 2v1  | 659       | 0      | HC (sh), HC (sh), HC, HC (sh), HC, HC |
   | 2v2  | 500       | None   | HC (sh) x4, HC x4                     |

   (HC = 'Empoleon: Hydro Cannon'; attribution order in the full pv
   logs is in results.jsonl.) 0v0 validated in-session: patched sim
   produces 500/500/None.

3. **Oracle: cross-species CMP flip** —
   `test_shadow_quagsire_vs_feraligatr_cmp`. Quagsire 4/15/10 L28.5
   shadow, MUD_SHOT / AQUA_TAIL + MUD_BOMB, vs Feraligatr 5/11/14
   L19.5, SHADOW_CLAW / HYDRO_CANNON + CRUNCH (both = gamemaster
   defaultIVs + current get_default_moveset; moveset confirmed from
   the saved grid trace). The x1.2 fold flipped CMP: folded 133.51 vs
   123.88 (Quagsire first — wrong), free 111.25 vs 123.88 (Feraligatr
   first — matches PvPoke decisionLog T11). PvPoke ground truth:

   | cell | score(p0) | winner |     | cell | score(p0) | winner |
   | ---- | --------- | ------ | --- | ---- | --------- | ------ |
   | 0v0  | 464       | 1      |     | 1v2  | 276       | 1      |
   | 0v1  | 344       | 1      |     | 2v0  | 807       | 0      |
   | 0v2  | 116       | 1      |     | 2v1  | 751       | 0      |
   | 1v0  | 552       | 0      |     | 2v2  | 408       | 1      |
   | 1v1  | 392       | 1      |     |      |           |        |

   0v0 validated in-session: patched sim gives 464/536, winner 1,
   chargedLog byte-identical (was 555/444 winner 0 — a real flip).
   CAVEAT: cells 1v0 and 2v0 have pv score pairs summing to 999
   (the known feraligatr +-1 rounding family, grid_summary unknown
   bucket #9, a SEPARATE mechanism). If they come back +-1 with
   identical logs, pin them at the pv value with an xfail-style
   comment referencing the rounding family rather than chasing it in
   this packet; full chargedLogs are in results.jsonl.

### Fixture fallout summary

- Refreshed to new values: none (no existing fixture flips).
- New fixtures: the two oracle tables above + unit test.
- Patched fixture builder: tests/test_dive_worker_form_change.py
  `_opp_cache_entry` (adds the cmp_atk key the strict worker reads).

## 6. Expected blast radius

**Oracle grid (3420 cells):** the 204 `shadow_cmp` cells (86
log-moves, 76 score, 12 log-shield, 30 winner flips — the flips
include all 20 ordered draw cells [altaria, empoleon, ninetales,
quagsire base<->shadow at various shield parities] and 10 cross-species
flips [quagsire_shadow vs feraligatr/seaking/ninetales,
ninetales_shadow vs kingdra both directions, altaria_shadow vs
kingdra]). Affected pairs: every grid pair with exactly one shadow
side where the fold changes the atk ordering, plus all four
base-vs-shadow mirrors. NOTE the tag is signature-based, not
probe-verified (use_priority could not be probed without editing the
frozen engine): expect the large majority to go exact, but some cells
may carry secondary mechanisms (bestcm/bandaid residue) — re-run the
grid and re-classify rather than assuming 204/204.

**Dives:** any dive where the focal is shadow OR any opponent is
shadow and the fold changes an atk ordering vs some IV spread —
in practice every GL dive (pools keep shadow pairs by policy, and
opponent_pools/active_variants.toml fires Forretress shadow on every
GL pool). Base-vs-shadow mirror sections and Top-Mirror CMP % for
shadow species are the most visibly affected surfaces. The 43
untracked thresholds/*.toml in the working tree include 12 shadow
forms whose CMP-adjacent numbers predate this fix — re-validate after
re-dive.

**Caches:** battle.py, pokemon.py, formchange.py are all in
sweep_cache._ENGINE_FILES, so applying the patch rotates the engine
hash and invalidates every sweep/slayer cache automatically. No
manual CACHE_VERSION bump needed (the deep_dive*.py worker edits are
outside the hash, but their behavior change is fully derivative of
the engine change the hash already covers). First dive after applying
is a full re-sim.

**Slayer dives:** expected numerically unchanged — mirrors share the
shadow flag on both sides, and ordering comparisons are invariant
under a common x1.2 (equality exactly preserved: same multiplier on
identical floats). The slayer worker wiring is for correctness/
consistency only.

**Perf:** one extra float field per BattlePokemon; comparisons read a
stored attribute exactly as before. No measurable cost expected, but
run the regression gate anyway (baseline 2,278 sims/s,
DEVELOPER_NOTES).

**Packet interplay:** hunks do not overlap the incoming-gate packet
(battle.py:187-209) or the bestCM packet sites; context lines at the
241 hunk start at line ~227, clear of the 187-209 region — apply
order should be free, but apply this one LAST if any fuzz appears
(it touches the most lines). Re-run the grid only after all packets
land, then attribute residuals.

## 7. Verification commands (tomorrow, post-batch)

```
cd ~/coding/MGLPoGo/gopvpsim
git apply --check userdata/fix_packets_2026-06-13/shadow-cmp.patch   # sanity
git apply userdata/fix_packets_2026-06-13/shadow-cmp.patch

# 1. Full suite — expect green with ZERO fixture edits (key claim of §5)
python -m pytest tests/ -q

# 2. 153-cell audit — expect unchanged (no shadow CMP flips in it)
python scripts/audit_oracle_harness.py

# 3. Spot-check the two validated cells against the live harness
node scripts/pvpoke_trace.js --pvpoke-root ~/coding/MGLPoGo/pvpoke --cp 1500 \
  --p1 empoleon --p1-fast WATERFALL --p1-charged HYDRO_CANNON,DRILL_PECK \
  --p1-ivs 5/15/13 --p1-level 19 --p1-shields 0 \
  --p2 empoleon_shadow --p2-fast WATERFALL --p2-charged HYDRO_CANNON,DRILL_PECK \
  --p2-ivs 5/15/13 --p2-level 19 --p2-shields 0

# 4. Re-run the full grid into a NEW file (run_grid.py skips existing
#    cells in its --out, so don't reuse results.jsonl), then re-classify:
python scratch_oracle_grid/run_grid.py --out scratch_oracle_grid/results_postfix.jsonl
#    expect: shadow_cmp 204 -> ~0 (re-classify the residue; secondary
#    mechanisms possible), exact >= 3290/3420 once the other two
#    packets are also applied (3136 + ~200 minus overlap/residue)

# 5. Perf regression gate (DEVELOPER_NOTES baseline 2,278 sims/s)
python scripts/profile_slayer.py        # or the documented gate command

# 6. Add the new tests from §5 and re-run pytest
```

## 8. Open questions

1. **Draw severity in downstream consumers.** PvPoke draws score
   500/500 winner None; our `BattleResult.winner=None` flows into
   dive aggregation as... check `pvpoke_score`-only consumers are
   fine (they are — score is symmetric), but anything that buckets
   "wins" by `winner == 0` now sees None for true mirrors. Mirror
   synth / Matchups-Kept fractional expected-wins should treat a
   draw as 0.5 — verify the aggregation code paths once before
   re-diving shadow species.
2. **In-game CMP equal-stat behavior is a coin flip**; PvPoke
   deterministically resolves equal-atk simultaneous charged moves
   in actor order (stable sort), and so do we (p0 first). Fine for
   parity; flag in docs/concepts.md if the draw semantics get a
   user-facing writeup.
3. **Residue attribution:** which of the 204 cells don't go exact
   after this patch (signature tag is not probe-proof). The grid
   re-run in §7 answers it empirically.

## Adversarial review

**Verdict: NEEDS-WORK** (2 blocking issues; everything else verified
clean). Reviewed 2026-06-12 against PvPoke clone 9b7407782 (read the
reference lines directly, not the drafter's quotes) and a /tmp scratch
clone with the patch applied (repo untouched).

### Blocking issues

1. **CRITICAL — missed call site: `scripts/deep_dive_signature.py:243`.**
   The signature-dedup CMP column is
   `np.sign(ff['atk'] - of['atk'])` on FOLDED atk, and the module
   docstring pins "CMP: ... sign of (focal.atk - opp.atk)" as part of
   the bit-identical-battles invariant. Post-patch the engine compares
   `cmp_atk`, so the grouping predicate no longer matches the engine:
   with exactly one shadow side, any opponent whose cmp_atk falls
   inside the focal spread's shadow-free atk range (a ~5-9% wide band;
   x1.2 keeps both profiles' FOLDED signs equal while their FREE signs
   differ) merges profiles that now fight differently. One
   representative's score fans out to profiles with the opposite true
   CMP sign — silently wrong dive scores, and (worse) the wrong
   columns get persisted into the sweep cache under the NEW engine
   hash, so they outlive the run. signature_dedup is ON by default
   (deep_dive.py:1378-1384). Forretress shadow fires on every GL pool
   (active_variants.toml) and 12 of the 43 pending thresholds TOMLs
   are shadow forms, so this is not a corner case — it partially
   defeats the fix on the exact surface (dives) the packet targets.
   Required: plumb cmp_atk through `build_focal_side` (free atk is
   derivable from profile tuples: baseStats + p[4] a_iv + CPM[p[7]]),
   `_form_dict` (carry FormData.cmp_atk), and `build_opp_side`
   (opp['cmp_atk']), switch line 243 to the cmp_atk vectors, and add a
   one-side-shadow straddle case to tests/test_signature_dedup.py.
   Note deep_dive_signature.py is NOT in sweep_cache._ENGINE_FILES —
   fine here only because battle.py rotates the hash in the same
   patch; do not split them across commits.

2. **CRITICAL — §5 "existing tests: ZERO changes" is false.**
   `tests/test_signature_dedup.py::_opp_entry` builds opp_cache dicts
   WITHOUT a `cmp_atk` key and `_groups_and_member_scores` drives the
   real `deep_dive._sweep_worker` (line 135), whose patched read is
   strict (`opp['cmp_atk']`, no `.get` — by design). Both
   grouped-profiles tests KeyError on the patched tree. The patch
   updates the test_dive_worker_form_change.py fixture but missed this
   second builder. Required: add `'cmp_atk': pkm.cmp_atk` to
   `_opp_entry` (and fold into the §4 diffstat / §5 fallout list).

### Verified clean (no action)

- `git apply --check` clean at HEAD f4a3b3e; stacked
  incoming-gate -> bestcm-superpower -> shadow-cmp applies cleanly;
  all patched files byte-compile. battle.py hunk ranges (238+) clear
  of incoming-gate (163-209) and bestcm (125-152); no other packet
  introduces a new `.atk` comparison.
- Reference reading confirmed verbatim: `stats.atk` is set ONLY as
  `cpm * (base + iv)` (Pokemon.js:342/419, never folded);
  shadowAtkMult applied only in getEffectiveStat (Pokemon.js:1995+)
  and DamageCalculator; all seven cited CMP sites read `stats.atk`
  (Battle.js:255/831/1116, ActionLogic.js:10/106/181/307). Battle.js
  831's atk bump is inside the `action.type == "charged"` branch and
  Battle.js:431's sort is stable with both fast priorities 0 in
  simulate mode, so equal-cmp_atk insertion-order resolution matches.
  Draw path confirmed: the charged-faint cancel at Battle.js:471 is
  usePriority-gated, matching battle.py's existing gate.
- 10-site enumeration is complete: post-patch grep shows zero
  remaining `.atk <op> .atk` comparisons in battle.py; remaining
  `.atk` reads are damage-path. `_dp_jit.py` takes precomputed
  booleans (only stale comments at 426-427, see minor notes).
- Plumbing verified: scripts/battle.py, audit_oracle_harness (via
  test_battle._make_battle_pokemon), build_matchup_web (via
  deep_dive.make_battle_pokemon — its "sweep-worker pattern" comment
  is about reset_for_battle reuse, construction still routes through
  from_pokemon), and reset_for_battle's form swap-back (goes through
  the patched apply_form_change). harness_grid (non-shadow only,
  skips `_shadow` ids), profile_slayer (same-fold mirror), and
  anchors.py:628 (damage-reference max, folded is correct) exclusions
  all justified.
- Cache story verified: battle.py/pokemon.py/formchange.py all in
  `_ENGINE_FILES`; slayer_cache reuses sweep_cache.engine_hash. No
  manual CACHE_VERSION bump needed.
- Numeric claims recomputed independently on the patched tree:
  Swampert-shadow 149.54/124.62 vs Registeel 96.72; Quagsire-shadow
  4/15/10 L28.5 133.51/111.25 vs Feraligatr 5/11/14 L19.5 123.88
  (real flip); Quagsire-shadow 15/15/15 136.51/113.75 vs Medicham
  109.86 (no flip); Empoleon 5/15/13 L19 base-vs-shadow cmp_atk
  exactly equal at 125.1899635; gamemaster defaultIVs match all three
  fixture specs. Slayer x1.2-invariance argument is sound (stat
  separations >= ~0.005 are far above float-collision scale).
- Grid evidence: grid_classified.json confirms 204 shadow_cmp cells
  (86 log_moves / 76 score / 12 log_shield / 30 winner_flip) and the
  packet's "20 ordered draw cells" is correct — grid_summary.md's
  "incl. all 14 PvPoke draws" headline is the stale number (JSON has
  20 shadow_cmp draw flips + 8 already-matching draws elsewhere).
  Don't "fix" the packet back to 14.
- JS surfaces: deep_dive_engine.js atk uses are display/sort and
  same-form Mirror-CMP %, which are fold-invariant within one form.

### Minor (non-blocking)

- Stale comments left behind: `_dp_jit.py:426-427` still describe
  wins_cmp/cmp_bonus as `.atk` comparisons, and the battle.py
  fast_landings comment still says "descending atk order ... PvPoke
  matches this" (in simulate mode PvPoke fast actions tie at priority
  0; equal-cmp_atk insertion order is the matching behavior). Fix or
  not — _dp_jit.py is in _ENGINE_FILES but the hash rotates anyway.
- §6 interplay note should mention that renderer-D2-D5.patch as
  listed does NOT apply after renderer-D1-D4 (deep_dive_rendering.py
  2674 conflict); the
  `renderer-D2-D5.rebased-after-D1-D4.rendering-only.patch` variant
  applies cleanly on the full stack (verified). That's D2-D5's packet
  to own, but tomorrow's apply order should use the rebased file.
- §8 open question 1 is mostly moot for the sweep path: the worker
  stores only `result.pvpoke_score(0)` (draws land as 500), no
  winner-bucketing. Still worth a one-time check of winner==0
  consumers outside the sweep (compare_loadouts, article win-rate
  framing) before re-diving shadow species.
