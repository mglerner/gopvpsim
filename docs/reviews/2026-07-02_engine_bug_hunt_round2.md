# Engine correctness bug-hunt, round 2 — 2026-07-02

Second adversarial multi-agent hunt of the battle engine vs the PvPoke
oracle, run in an isolated worktree (`hunt2` @ c7f9ba2, pvpoke clone
pinned @ 00f0afe7f). Same protocol as the 2026-06-27 round-1 hunt: 7
independent finder lenses -> per-finding double verification (one "is
this already documented?" skeptic + one "reproduce/refute empirically"
skeptic) -> triage. **4 confirmed (1 medium, 3 low), 0 uncertain, 16
dismissed.** No high-severity engine bugs found — round 1's fixes held
up under a substantially wider probe surface.

New instrument this round: `scripts/pvpoke_trace.js` grew
`--p1-bait <0|1|2>` / `--p2-bait <0|1|2>` flags (PvPoke `baitShields`:
0 = no bait, 1 = selective/default, 2 = always), set exactly the way
PvPoke's UI bait-picker sets it (`PokeSelect.js:1155` direct property
assignment; survives `Pokemon.reset()`). This enabled the first-ever
**no-bait oracle grid** — until now the no-bait surface (thresholds /
CD-article analysis mode) had zero reference cross-checks. The patch is
committed with this report and stays.

Data pinning caveat that future oracle work MUST repeat: the live TTL
cache carried a **different gamemaster md5** than the pinned pvpoke
clone. All sims in this hunt redirected `gopvpsim.data.CACHE_DIR` to a
scratch copy of the pinned clone's `gamemaster.json`
(md5 `363e44f3f9d9a56cf9dc7d9e3abd735e`) so both engines read identical
data; without that, the grid diffs would have been polluted by
gamemaster drift, not engine behavior.

Report provenance: the finder/skeptic evidence packets for four lenses
(no-bait-grid, invariants, jit-parity, and — partially — cache-migration)
survived the multi-agent handoff intact and are reported in full below.
The coverage notes for the remaining lenses were truncated in the
handoff; those lenses produced no entries in the confirmed or uncertain
lists, but their detailed coverage/dismissed records are not
reproduced here. Treat their coverage claims as weaker than the four
documented lenses.

## Status / what needs Michael

- **NB-1 (MEDIUM)** is a genuine decision point under the CLAUDE.md
  divergence policy: our per-turn `bestChargedMove` recompute — long
  documented as strictly better than PvPoke's init-time cache, with
  Aegislash as the only known mismatch — is now proven **worse** than
  PvPoke in a non-Aegislash case that sits on the production dive
  surface. The documented claim is falsified either way, so the
  no-action option is off the table: pick a fix (evaluate the 0.3
  selfBuffing guard against the energy-ordered list, or cap the
  recompute's regressions), or update the three doc sites + add an
  xfail pin. A fix bumps the engine hash; the affected class looks
  cleanly predicate-able for `migrate_cache.py` (self-buffing CM on one
  side + opponent-atk-debuff CM on the other), subject to the
  one-localized-fix-per-bump rule.
- **PROP-1, JIT-COV-1, JIT-COV-2 (LOW)** need no code changes to shipped
  behavior: a short "Known engine properties" doc note, a handful of
  added parity-test matchups, and a one-line comment (or two extra
  kernel return scalars) respectively. All three are cheap; none is
  urgent.
- **No shipped winner flips were found anywhere in this round.** NB-1
  shifts ratings (-84 of 1000 in the sampled cells) but not winners at
  the sampled builds; everything else confirmed is doc/test hygiene.

---

## Confirmed findings (by severity)

### NB-1. [MEDIUM] Per-turn `bestChargedMove` recompute picks a dominated move after an opponent atk-debuff — falsifies the documented "Aegislash-only, ours-always-better" claim

- **Where:** `src/gopvpsim/battle.py:2204-2247` (`best_idx` selection
  loop; fired via `farm_swap_idx` at `:1326`/`:1358`); the
  INTENTIONAL DIVERGENCE note it contradicts is at `:1286-1293`, with
  echoes in DEVELOPER_NOTES divergence #3 / PvPoke bug #2 and
  `docs/pvpoke_divergences.md` #1.
- **What happens:** Greedent (Mud Shot, Body Slam + Trailblaze) vs
  Forretress (Volt Switch, Sand Tomb + Rock Tomb), GL, 15/15/15,
  L22 vs L23. PvPoke promotes self-buffing Trailblaze to slot 0 at
  init (`Pokemon.js:756-762`), then displaces it with Body Slam
  because the raw DPE gap 0.311 exceeds the 0.3 selfBuffing guard
  (`Pokemon.js:791-822`) — **once, cached**. We re-run that selection
  per turn. After Forretress's Rock Tomb lands -1 atk on Greedent
  (debuffs apply even on a shielded throw), the DPE gap at stage -1
  shrinks to 0.242 < 0.3, the guard keeps promoted Trailblaze, and the
  farm-down path fires Trailblaze (11 dmg, 45e) where PvPoke lands two
  Body Slams (17 dmg, 35e each) in the same window.
- **Spot-check re-verified while writing this report** (pinned
  gamemaster, default bait-on `pvpoke_dp` both sides): 1-1 ours
  [268,732] vs oracle [352,648]; 1-2 ours [188,812] vs oracle
  [272,728] — delta **-84** in both cells, no winner flip (Forretress
  wins all sampled cells; 2-1 and 2-2 match the oracle exactly).
  Timeline signature: `T24 Forretress uses Rock Tomb -> SHIELDED` then
  `T27 Greedent uses Trailblaze -> 11 dmg`.
- **Repro (ours):** pin `data.CACHE_DIR` to a copy of the pinned
  clone's gamemaster, build both mons via
  `Pokemon.at_best_level(..., league='great')` +
  `BattlePokemon.from_pokemon`, `simulate(..., charged_policy_0=
  pvpoke_dp, charged_policy_1=pvpoke_dp)`.
  **Repro (oracle):**
  `node scripts/pvpoke_trace.js --pvpoke-root <pinned pvpoke> --p1
  greedent --p2 forretress --p1-fast MUD_SHOT --p1-charged
  BODY_SLAM,TRAILBLAZE --p2-fast VOLT_SWITCH --p2-charged
  SAND_TOMB,ROCK_TOMB --p1-ivs 15/15/15 --p2-ivs 15/15/15 --p1-level 22
  --p2-level 23 --p1-shields 1 --p2-shields 1 --cp 1500`
- **Both skeptics confirmed.** The repro skeptic reproduced end-to-end
  independently and verified the PvPoke-source mechanism; one finder
  overstatement was corrected: Trailblaze is not literally strictly
  dominated (it grants +1 atk), but the outcome is still empirically 84
  points worse with identical opponent play. The doc skeptic confirmed
  no source anywhere records a recompute-worse case — the three doc
  sites affirmatively claim the opposite.
- **Blast radius:** on the production surface — reproduces under
  default bait-on policies, so it is NOT confined to the new no-bait
  grid. Greedent (this exact default moveset) is a pool opponent in
  `opponent_pools/gl_top50_plus_cs.txt`; Forretress and Forretress
  (Shadow) are shipped focals, so their GL dive columns vs Greedent
  carry the misplay (~84 rating points in 1-1/1-2 at the sampled
  build), flowing into dive HTML and the Forretress GL gobattlekit
  export. No greedent.toml exists, so no Greedent-focal dive is
  affected. No winner flips observed, but other IV spreads/levels
  could flip. The class generalizes: any PvPoke-promoted self-buffing
  charged move (Trailblaze / Power-Up Punch family, energy gap <= 10
  to the nuke) vs any opponent atk-debuff move (Rock Tomb, Icy Wind,
  Lunge, ...) that drags the raw DPE gap across the 0.3 guard
  mid-fight. Only 4 cells of this shape were in the 320-cell grid
  corpus; a targeted sweep (atk-debuff opponents x promoted-self-buff
  focals) would quantify the full footprint and is the natural next
  step before choosing fix-vs-document.

### PROP-1. [LOW — doc gap, not a bug] Exact-`cmp_atk` ties resolve by player index: mirrors are not 500/500 and A-vs-B / B-vs-A are not complementary (oracle-verified PvPoke-faithful)

- **Where:** `src/gopvpsim/battle.py:2529` (`use_priority=False` on
  exact ties, so the `:2555` CMP sort never runs and charged actions
  resolve in list order), `:2790` (stable fast-landing sort leaves
  equal keys in index order), `:1962` (`cmp_atk` strips the shadow
  x1.2, making every normal-vs-own-shadow matchup an exact tie).
- **What happens:** p0 acts first on simultaneous actions when both
  sides have identical `cmp_atk`. 21/432 default-moveset mirror sims
  (GL+UL pools, 0-0/1-1/2-2) score away from 500/500 (up to 106/893
  for the Aegislash Shield mirror 2-2); 7/4800 swapped-pair scenarios
  are non-complementary — every one an equal-`cmp_atk` pair
  (Forretress vs Forretress Shadow, Toucannon Shadow vs Toucannon).
- **Why it is not an engine bug:** every checked case matches PvPoke
  **bit-for-bit in both player orders** (Forretress GL mirror 0-0 =
  512/488 winner 0 in both sims; Forretress vs own shadow GL 1-1 =
  524/476 winner 0 in BOTH orders in both sims; Aegislash Shield GL
  mirror 0-0 = 435/564 winner 1 in both). Per the divergence policy,
  matching the reference is correct. Both skeptics confirmed
  independently (the repro skeptic rebuilt the sweep from scratch:
  20/324 mirror cells asymmetric, 7/75 own-shadow swaps
  non-complementary — same kind and scale). The repro skeptic also
  verified no pipeline code assumes complementarity (no
  1000-complement derivation anywhere; the sweep cache keys focal and
  opponent as distinct roles, so no column is served for the swapped
  orientation).
- **Repro:** `node scripts/pvpoke_trace.js --pvpoke-root <pinned
  pvpoke> --p1 forretress --p2 forretress --p1-fast VOLT_SWITCH
  --p1-charged SAND_TOMB,ROCK_TOMB --p2-fast VOLT_SWITCH --p2-charged
  SAND_TOMB,ROCK_TOMB --p1-ivs 15/15/15 --p2-ivs 15/15/15 --p1-level 23
  --p2-level 23 --p1-shields 0 --p2-shields 0 --cp 1500` vs the same
  matchup in our sim: both give 512/488 winner 0.
- **Blast radius:** interpretive, not numeric. Shipped mirror and
  normal-vs-own-shadow cells (the pools deliberately keep both forms:
  Quagsire, Forretress, Altaria, Empoleon, Sealeo, ...) carry a
  deterministic p0-first component that in-game is effectively a coin
  flip — but PvPoke's numbers carry the identical component, so
  shipped data is reference-consistent. Any FUTURE aggregation that
  assumes mirror = 500/500 or swap-complementarity (mirror-synth
  tiers, expected-wins, swap-order dedup) would silently miscount.
- **Recommendation:** a short "Known engine properties" note in
  DEVELOPER_NOTES (and/or the `docs/concepts.md` CMP entry). No code
  change.

### JIT-COV-1. [LOW — test gap] In-tree JIT parity test leaves 6 kernel-mirrored branches unexercised

- **Where:** `tests/test_battle.py:1848-1894`
  (`test_jit_and_python_dp_paths_agree`: 3 matchups x (1,1)/(2,2)
  shields).
- **What's uncovered** (19/25 kernel-mirrored branches hit; misses
  verified by `sys.settrace` over the test's exact battles, with a
  control line in the same loop confirming the tracer): (a) TTL cmp
  turn bonus (`battle.py:518` / `_dp_jit.py:490-491`); (b) near-KO
  atk-stage clamps +4/-4 (`battle.py:1461/1463` /
  `_dp_jit.py:208-211`); (c) greedy fallback when no KO plan found
  within MAX_ITERS (`battle.py:1513`); (d) dedup same-energy pop-worse
  (`battle.py:1018` / `_dp_jit.py:234-247`); (e) dedup same-energy
  keep (`battle.py:1021` / `_dp_jit.py:248-250`).
- **Sharpened by the repro skeptic:** 3 of the 6 misses ((a), (e), and
  clamp +4) fire in ordinary default-moveset GL meta battles (Azumarill
  vs Bastiodon / Annihilape) — so branches feeding shipped scores have
  no parity pin. Two OTHER kernel branches are **provably unreachable**
  for real 2-charged-move configs (near-KO queue-overflow sentinel:
  peak queue 1001 < QUEUE_CAP 1024; TTL `ok=False`: frontier bounded by
  the turn prune), so no integration test can ever cover them — the
  `iters=-1` -> pure-Python fallback wiring at `battle.py:1402-1413`
  was instead verified with a stub kernel (178 invocations, outcomes
  bitwise-identical to kernels-disabled).
- **No live divergence:** 360 realistic battles kernels-on vs
  kernels-off were bitwise-identical (score, winner, hp, energy,
  shields, full timeline) — this is a latent gap, not a wrong number.
- **Recommendation:** add matchups (or a small direct-call parity
  corpus) to the in-tree test that exercise the 6 branches, so a future
  edit to either side of the hand-mirrored pairs cannot silently
  desynchronize while the suite stays green.

### JIT-COV-2. [LOW — latent trap, currently inert] JIT-path final `_DPState` silently zeroes plan `energy` and `atk_stage`

- **Where:** `src/gopvpsim/battle.py:1415-1416` — when the JIT kernel
  finds a KO plan, `final_state` is rebuilt as an 8-arg `_DPState`
  with `energy` hardcoded to 0 and `atk_stage` taking the constructor
  default 0, because the kernel's 9-tuple does not return them. The
  pure-Python path (`:1431`) carries the plan's real final values.
- **Why inert today:** every downstream consumer of `final_state`
  (bait-wait, plan-sort, bandaids [861]-[929], the farm-down
  boost-move override at `:1549-1554`, `_dp_trace`) reads only
  kernel-returned fields (`first_idx`, `max_dmg_idx`, `has_debuf`,
  `debuf_count`, `turn`, `hp`, `shields`). Empirically 0 mismatches
  across 8658 scenario-battles + 120k direct kernel cases. But any
  future code reading `final_state.energy` or `.atk_stage` on the JIT
  path silently diverges from the Python path, and nothing flags the
  fields as unpopulated.
- **Recommendation:** one-line comment at the construction site, or
  return the two extra scalars from the kernel. (Confidence "likely"
  rather than "reproduced" — the trap is by definition about future
  code; the inertness claim is what was verified.)

---

## Uncertain (needs Michael)

None this round — every surviving finding was double-confirmed. The
NB-1 fix-vs-document decision (above) is the only item requiring a
judgment call.

---

## Dismissed (checked, not actionable)

| Lens         | Item                                                                               | Disposition                                                                                                                                                                                                                                       |
| ------------ | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| no-bait-grid | bandaid[929] no-bait swap family (78/83 divergent cells, ALL 15 winner flips)      | Documented intentional divergence (round-1 bug #5, `docs/pvpoke_divergences.md` #6, pinned test). The grid gives it its first real-PvPoke confirmation: every cell diverges in the documented direction (ours cheap-non-debuff vs pv debuf-nuke). |
| no-bait-grid | Moltres-G vs Dondozo UL: single Brave Bird vs chained Fly (+22/-10, no flips)      | Documented intentional divergence #4 (near-KO plan choice, bandaid[866]/[885] subgate); new opponent instance of the measured family.                                                                                                             |
| no-bait-grid | Annihilape (S) vs Malamar (S) UL 2-2: Foul Play into shield one turn before KO     | Score-identical (284/715 both), cosmetic end-of-fight ordering per the divergence policy; would only matter for future multi-mon energy carry-over.                                                                                               |
| no-bait-grid | 127 apparent chargedLog mismatches                                                 | Harness artifact: PvPoke logs "Talonflame (Shadow): ...", we log the base name. Normalizing " (Shadow)" drops differing cells 210 -> 83 with scores untouched. Remember for future automated chargedLog diffing.                                  |
| no-bait-grid | Prior agent's `--no-bait` harness patch                                            | Re-verified byte-consistent with its report (Malamar vs Furret GL 1-1 bait-0 = [694,305] winner 0). Not a finding.                                                                                                                                |
| invariants   | Mirror matches not scoring 500/500 as an engine bug                                | Real invariant violation but bit-for-bit PvPoke-identical in every oracle spot-check; folded into PROP-1 as a documentation gap only.                                                                                                             |
| invariants   | Suspected Fly-vs-Brave-Bird divergence (shadow Talonflame, tie -> 488/511 loss)    | Dissolved: harness error — shadow Talonflame's PvPoke default is FLAME_CHARGE,FLY (no Brave Bird). With per-form defaults, PvPoke reproduces our scores exactly in both orders.                                                                   |
| invariants   | Aegislash/Talonflame mirrors where p1 wins despite p0's index advantage            | Oracle-confirmed reference behavior (PvPoke gives the identical 435/564 winner-1); downstream of the same index-order tie handling.                                                                                                               |
| invariants   | Two UL pool entries failed to build (Cradily/ACID, Golisopod/FURY_CUTTER)          | Corpus-loader limitation (pinned alt-moveset line syntax), not an engine/data bug; species skipped (66/68 UL covered).                                                                                                                            |
| jit-parity   | Numeric JIT-vs-Python divergence in battle outcomes                                | None found: 8658 scenario-battles (full outcome tuples incl. timeline) + 120k direct kernel fuzz cases, 0 mismatches.                                                                                                                             |
| jit-parity   | farm-down `fm_to_ko` ceil formulations (math.ceil vs `(hp+dmg-1)//dmg`)            | Identical on integral float64 < 2^53; hp is always integer-valued in both paths. 0 fuzz mismatches.                                                                                                                                               |
| jit-parity   | int/float coercion differences (int64 vs arbitrary-precision, float64 promotion)   | All quantities far below exactness bounds; int division only with positive operands; even the hypothetical energyGain=0 ZeroDivisionError raises in BOTH paths.                                                                                   |
| jit-parity   | TTL `ok=False` and near-KO `iters=-1` overflow fallbacks are dead code             | True by design — documented E9 backstops, proven unreachable for real configs; fallback wiring verified live via stub kernel.                                                                                                                     |
| jit-parity   | TTL kernel ignores its `energy_cap` argument                                       | Already documented (in-code at `_dp_jit.py:508-512` / `battle.py:536-540`, review finding E7): deliberately mirrors PvPoke's turnsToLive DP; both paths agree.                                                                                    |
| jit-parity   | JIT `cm_dmgs` float64 stage-table row vs Python int `cm_dmgs_root` list            | Same values (int-to-float64 exact); max-damage `>` comparison bit-identical. 0 mismatches empirically.                                                                                                                                            |
| jit-parity   | Import-guard fallback (numba genuinely absent) differs from the test's monkeypatch | Verified equivalent in a subprocess with numba masked at import: same None-ness check, bitwise-identical outcomes.                                                                                                                                |

---

## Coverage map (what round 2 probed, and what it did not)

Negative results below are the point: a lens that found nothing is
coverage evidence for the subsystems it swept.

### no-bait-grid (NEW lens; found NB-1)

Covered: 80 matchups (12 GL + 8 UL bait-relevant focals x 4 pool
opponents, default movesets, self-debuff > self-buff > energy-gap
prioritized; Aegislash/Mimikyu excluded to avoid form-change noise) x
4 shield cells ([1,1],[1,2],[2,1],[2,2]) = 320 cells, focal bait=0 vs
opponent bait=1 on BOTH engines, pinned gamemaster. 320/320 ran;
237/320 exact on score+winner+chargedLog after shadow-name
normalization; all 83 divergent cells root-caused (78 documented
bandaid[929], 2 documented near-KO Moltres-G family, 2 NB-1, 1
cosmetic delta=0 tail).

Not covered: bait=2 (always-bait); both-sides-no-bait;
0-opponent-shield cells (bait logic dead by construction); Master
league; non-default movesets/IV spreads; species outside the two
pools; a meta-wide sweep for NB-1-shaped winner flips (only 4 cells of
that shape were in the corpus).

### invariants (found PROP-1)

Covered (all clean unless noted): mirror symmetry (432 sims -> 21
asymmetries, all PROP-1); swap symmetry + determinism + score-formula
recompute + winner-vs-HP consistency + bounds (~14,400 sims -> only
the 7 cmp-tie swap asymmetries); per-WRITE state invariants via an
instrumented BattlePokemon (1,932 sims incl. form changers -> 0);
boundary probes (IV 0/0/0, ML level caps, L51, synthetic simultaneous
fast-KO tie 500/500, simultaneous charged double-KO with/without CMP,
800-turn MAX_TURNS wall, initial_energy clamps, shadow-both-sides cmp
ordering -> 0 failures); timeline-replay conservation (1,588 replays
re-deriving HP/energy/shields from the log -> 0); mechanics='new'
subset (948 sims -> 0); reset_for_battle vs fresh construction
bit-for-bit (360 pairs -> 0); alternate charged policies no_bait /
bait_with_cheapest / optimal_timing (1,242 sims -> 0).

Not covered: full ML pool sweep (only 4 ML matchups); best-buddy
levels; non-default IV spreads beyond 0/0/0; the pvpoke_dp baitShields
parameter dimension; the pure-Python `_dp_jit` fallback (numba active
throughout); PvPoke-score oracle sweeps (round 1's lens; only targeted
oracle runs here).

### jit-parity (found JIT-COV-1, JIT-COV-2)

Covered: switch mechanism (import guard + monkeypatch verified
equivalent to genuine numba absence); battle-level corpus GL top-32 +
UL top-20 + 16 off-IV variants, all pairs x 9 shield scenarios (8658
scenario-battles), full outcome tuples bit-for-bit: 0 mismatches;
direct kernel fuzz 60k near-KO + 60k TTL: 0 mismatches; adversarial
line-by-line kernel-vs-Python diff (coercion, ceil, dedup, insertion
scans, overflow sentinels, cache arrays); parity-test branch coverage
measured by tracing (19/25); overflow backstop verified via stub.

Not covered: Master league pools; mechanics='new' decisions; 3+
charged moves at the simulate() level (kernel-level fuzz-covered);
multiprocessing-worker kernel execution; numba on-disk compile-cache
staleness across versions; PvPoke fidelity (path-vs-path audit only).

### cache-migration (no confirmed findings)

Covered (per the surviving portion of the packet — see provenance note
above): full reads of `scripts/migrate_cache.py`, `sweep_cache.py`,
`migrate_v6_to_v7.py`, `gc_cache.py`, `cache_base.py`,
`src/gopvpsim/formchange.py`, the battle.py bandaid block /
`_priority_shuffle` / `_cm_debuf_delta` / dp-cache flag plumbing,
moves.py selfDebuffing derivation, and deep_dive.py's iv_sweep cache
plumbing (key construction, put_column, mechanics gates, call sites),
against CLAUDE.md's cache sections and the DEVELOPER_NOTES sweep-cache
+ bandaid[910] records. No confirmed or uncertain findings emerged
from this lens. Its detailed dismissed list did not survive the
handoff.

### Remaining lenses

Three further lenses ran and produced no confirmed or uncertain
findings; their coverage/dismissed records were truncated in the
report handoff (see provenance note). Do not count their subsystems as
deeply swept on the basis of this report alone.

### Not reached by round 2 at all (union)

Master league at sweep scale; best-buddy levels; broad non-default IV
spreads; always-bait and both-sides-no-bait oracle surfaces;
mechanics='new' vs any reference (none exists); numba-absent
pure-Python fallback under the full corpus; a targeted NB-1-class
sweep (promoted-self-buff focals x atk-debuff opponents) to bound its
meta-wide footprint — the natural follow-up before the NB-1
fix-vs-document decision.
