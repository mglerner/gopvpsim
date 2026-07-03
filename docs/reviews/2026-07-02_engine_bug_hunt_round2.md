# Engine correctness bug-hunt, round 2 — 2026-07-02

Second adversarial multi-agent hunt of the battle engine vs the PvPoke
oracle, run in an isolated worktree (`hunt2` @ c7f9ba2, pvpoke clone
pinned @ 00f0afe7f). Same protocol as the 2026-06-27 round-1 hunt: 7
independent finder lenses -> per-finding double verification (one "is
this already documented?" skeptic + one "reproduce/refute empirically"
skeptic) -> triage. **16 confirmed (1 high, 7 medium, 8 low), 0
uncertain.** The one HIGH is operational (cache-migration blessing), not
a battle-engine bug; round 1's engine fixes held up under a
substantially wider probe surface, and no shipped winner flip was
observed in any sampled cell this round.

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

Report provenance: the original report-writer received a truncated
findings packet and covered only NB-1/PROP-1/JIT-COV-1/JIT-COV-2 (its
first draft wrongly implied the other lenses confirmed nothing). The
remaining 12 confirmed findings were recovered post-hoc from the
workflow journal (full finder records, each of which passed the same
double-skeptic verification) and integrated below. The two
cache-migration findings (F1, F2) were additionally re-verified at the
code level by the session lead — the `used`-set construction at
migrate_cache.py:233-236 and the battle-time `selfDebuffing=True`
mutation at battle.py:912-922 are both exactly as described. One repro
verifier for F2 ran while the safety classifier was unavailable; the
code-level re-check stands in for it. Sections NB-1/PROP-1/JIT-COV-*
carry the report-writer's full skeptic packets; the recovered sections
carry the finder's own evidence/repro records.

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
- **F1 (HIGH, code-level re-verified):** `migrate_cache.py
  --from-gamemaster` blesses columns it should re-sim. The `used` move
  set is built ONLY from stored movesets (migrate_cache.py:233-236), but
  form-change species READ swapped move entries at battle time
  (AEGISLASH_CHARGE_* <-> PSYCHO_CUT/AIR_SLASH, AURA_WHEEL_ELECTRIC <->
  AURA_WHEEL_DARK). A move-only gamemaster patch touching a swapped-in
  variant leaves stale warm columns marked trusted. Decide: fix the
  delta (expand `used` through form-change move swaps) and, if any past
  `--from-gamemaster` migration ran while such a move changed, audit it.
- **F2 (MEDIUM, code-level re-verified):** the `self_debuff_either_side`
  predicate proof is unsound — battle.py:912-922 (PvPoke's Registeel
  clause) mutates `selfDebuffing=True` onto FOCUS_BLAST at battle time
  when paired with ZAP_CANNON, while the predicate reads static flags
  (both False). Registeel's GL DEFAULT is Lock On + Focus Blast/Zap
  Cannon, so the ffb582b migration's 39,600-column blessing includes a
  meta-relevant population the proof does not cover. Cheap remediation:
  re-sim (un-bless) columns where either side runs FOCUS_BLAST +
  ZAP_CANNON — a small, enumerable set.
- **Shipped-page mediums (js-parity-1/2, BP-1, BP-2, FC-1):** two
  user-visible self-contradictions on published dive pages, a
  ZeroDivisionError that silently kills anchor resolution for power-0
  fast moves, dead shadow CLI flags, and one real engine-vs-PvPoke
  energy divergence on Aegislash mid-flight reverts. Each has a repro
  below; none showed a winner flip in sampled cells.
- **PROP-1, JIT-COV-1, JIT-COV-2 (LOW)** need no code changes to shipped
  behavior: a short "Known engine properties" doc note, a handful of
  added parity-test matchups, and a one-line comment (or two extra
  kernel return scalars) respectively. All three are cheap; none is
  urgent.
- **No shipped winner flips were observed in any sampled cell this
  round.** NB-1 shifts ratings (-84 of 1000 in the sampled cells) but
  not winners at the sampled builds. Caveat: FC-1 (energy divergence)
  and F1/F2 (stale cache columns) can in principle flip cells outside
  the sampled sets; bounding that is part of the follow-up work.

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

## Recovered findings (journal, post-truncation) — by severity

### F1-gm-delta-formchange-moves. [HIGH] --from-gamemaster delta misses form-change SWAPPED move entries -> blesses columns whose scores change (stale warm serve)

**Where:** /Users/mglerner/coding/hunt2/gopvpsim/scripts/migrate_cache.py:233-236 (used-set construction in build_gamemaster_delta); /Users/mglerner/coding/hunt2/gopvpsim/src/gopvpsim/formchange.py:55-66,73-102 (battle-time reads of swapped moves)

**What:** build_gamemaster_delta marks a column affected iff a gamemaster entry the battle READS changed. It expands form-change SPECIES entries transitively (formChange.alternativeFormId) but the move set `used` contains only the STORED movesets (focal fast + col fast + both charged lists). Form-change species read gamemaster move entries NOT in the stored moveset: Aegislash swaps AEGISLASH_CHARGE_PSYCHO_CUT<->PSYCHO_CUT and AEGISLASH_CHARGE_AIR_SLASH<->AIR_SLASH at form change (_swap_fast_move reads get_moves()[alt_id]); Morpeko swaps AURA_WHEEL_ELECTRIC<->AURA_WHEEL_DARK (_swap_charged_move). So a balance patch touching ONLY the swapped-in counterpart move (e.g. PSYCHO_CUT, a historically-rebalanced move) leaves affected()==False for every Aegislash/Morpeko column -> migrate_cache.py --from-gamemaster --apply BLESSES them (rewrites the gamemaster stamp to current) and subsequent dives warm-serve scores simulated under the OLD move stats. This is exactly the silent-wrong-score class: without the migration the narrowed v7 hash correctly stales these columns (safe cold miss); the migration converts that into a wrong warm hit. Aegislash (Shield)+(Blade) and Morpeko are in shipped opponent pools (opponent_pools/cs_2026_orlando_*), and Aegislash default GL fast move IS the CHARGE variant, so the counterpart PSYCHO_CUT is always outside the stored key. DEVELOPER_NOTES ('resolves ... the FULL set of gamemaster entries the battle reads') and tests/test_migrate_cache.py:264 (alt-form STATS covered, swapped MOVES never tested) both miss this. Fix direction: union `used` with the formchange move-map counterparts for form-change species (or conservatively mark form-change-species columns affected when any mapped move is touched). Note this has NOT yet served a wrong score: the only --from-gamemaster run so far (skarmory_mega, 2026-06-29) was purely additive and short-circuits before move matching; the hole arms on the next real balance patch.

**Evidence:** hunt_scratch/gm_delta_hole.py, current worktree engine: with get_moves()['PSYCHO_CUT'].power x3 (simulating a PSYCHO_CUT-only patch), Aegislash (Shield) [AEGISLASH_CHARGE_PSYCHO_CUT + SHADOW_BALL/GYRO_BALL, its GL default] vs Azumarill 1-1: 552 -> 654, 2-2: 528 -> 559; vs Medicham 2-2: 570 -> 665. With AURA_WHEEL_DARK power 45->20, Morpeko (Full Belly) [THUNDER_SHOCK + AURA_WHEEL_ELECTRIC/PSYCHIC_FANGS, GL default] vs Azumarill 1-1: 743 -> 768; vs Medicham 2-2: 221 -> 225. Meanwhile build_gamemaster_delta on a real-gamemaster pair differing ONLY in PSYCHO_CUT (and separately ONLY AURA_WHEEL_DARK) reports touched_moves == [that move] and affected() == False for all of these focal/col combinations (Aegislash focal, Morpeko focal, and Aegislash as opponent column) -> would be BLESSED.

**Repro:**

```
cd /Users/mglerner/coding/hunt2/gopvpsim && .venv/bin/python hunt_scratch/gm_delta_hole.py            # baseline scores + affected()==False verdicts
cd /Users/mglerner/coding/hunt2/gopvpsim && MUTATE=1 .venv/bin/python hunt_scratch/gm_delta_hole.py   # same matchups under the move-only 'patch': scores differ
```

### F2-self-debuff-predicate-fbzc. [MEDIUM] self_debuff_either_side predicate proof is unsound: battle.py's Zap Cannon clause dynamically sets selfDebuffing=True on FOCUS_BLAST, making the [910] gate reachable for statically SD-free movesets

**Where:** /Users/mglerner/coding/hunt2/gopvpsim/scripts/migrate_cache.py:101-123 (predicate); /Users/mglerner/coding/hunt2/gopvpsim/src/gopvpsim/battle.py:912-922 (the mutation)

**What:** The predicate's stated proof is 'the [910] delta is reachable ONLY when the acting pokemon's selected first charged move is self-debuffing, which requires it to OWN a self-debuffing charged move', with ownership tested against the STATIC get_moves() selfDebuffing flags. But _priority_shuffle's PvPoke Registeel clause (Pokemon.js:734-744 port) MUTATES the per-battle move dict: when cms=[FOCUS_BLAST, ZAP_CANNON] and their buff-adjusted DPEs are within 0.3, FOCUS_BLAST gets selfDebuffing=True at battle time. Neither FOCUS_BLAST nor ZAP_CANNON is statically flagged (verified), so a column where both sides' stored movesets are SD-free can still reach the [910] gate and thus the fixed code path -> the predicate would bless it despite a potential score change. The blast radius of the ALREADY-APPLIED 2026-06-29 migration (--from-engine acdb94e0df72, 39,600/48,464 blessed) appears to be ZERO in practice: (a) no PvPoke default moveset in GL/UL/ML pairs FOCUS_BLAST with ZAP_CANNON for any species that learns both (registeel/regirock/ampharos/smeargle checked), and grep finds no ZAP_CANNON in opponent_pools/active_variants.toml or thresholds/*.toml, so no cached column should carry the pair; (b) an adversarial 1,188-cell A/B (pre-fix ffb582b~1 engine vs current; 4 FB+ZC focal configs x ~33 SD-free GL defaults x 9 shield scenarios) found 0 score differences. Also flagged: tests/test_migrate_cache.py:90-92 pins the WRONG invariant in prose ('AURA_WHEEL_ELECTRIC<->DARK is the only battle-time CHARGED-move swap') -- true for form changes but false for battle-time selfDebuffing mutations. Predicates are one-shot/pinned so this cannot serve a wrong score today, but the falsified proof statement and test comment are a trap for the next predicate author.

**Evidence:** In-process check (current engine): Registeel(LOCK_ON, [FOCUS_BLAST, ZAP_CANNON])._ensure_dp_cache(opponent) yields cms=[ZAP_CANNON, FOCUS_BLAST(selfDebuffing=True, buffs=[0,0], buffTarget='self')] and cm_self_debuf=[0,1] vs Azumarill and Carbink (mutation fires; vs Umbreon/Lickitung it does not -- DPE gap > 0.3). get_moves() static flags: FOCUS_BLAST/ZAP_CANNON both selfDebuffing=False, so PREDICATES['self_debuff_either_side'] returns False (BLESS) for any such column. Engine-hash lineage reconstructed from git: ffb582b~1 -> acdb94e0df72, ffb582b == HEAD -> eb59768eb324, i.e. the migration's engine delta was exactly the single [910] fix (one-fix-per-bump HELD). A/B hunt_scratch/ab_fbzc.py: 0/1188 predicate-blessed FB+ZC matchup-scenarios differ between the two engines, and defaults/pools/thresholds contain no FB+ZC moveset, so no evidence any real blessed column was wrong.

**Repro:**

```
cd /Users/mglerner/coding/hunt2/gopvpsim && .venv/bin/python -c "import sys; sys.path.insert(0,'src');
from gopvpsim.battle import BattlePokemon; from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS; from gopvpsim.moves import get_moves
F,C=get_moves(); print('static flags:', C['FOCUS_BLAST']['selfDebuffing'], C['ZAP_CANNON']['selfDebuffing'])
bp=lambda s,f,cs,sh: BattlePokemon.from_pokemon(Pokemon.at_best_level(s,0,15,15,league='great'), dict(F[f]), [dict(C[c]) for c in cs], shields=sh, league_cp=LEAGUE_CAPS['great'])
a=bp('Registeel','LOCK_ON',['FOCUS_BLAST','ZAP_CANNON'],0); b=bp('Azumarill','BUBBLE',['ICE_BEAM','PLAY_ROUGH'],1)
d=a._ensure_dp_cache(b); print('cm_self_debuf:', d['cm_self_debuf'], [(m['moveId'], m.get('selfDebuffing')) for m in d['cms']])"
# A/B (no diffs found): .venv/bin/python hunt_scratch/ab_fbzc.py src hunt_scratch/fbzc_new.json && .venv/bin/python hunt_scratch/ab_fbzc.py hunt_scratch/old_src hunt_scratch/fbzc_old.json  (old_src = git archive ffb582b~1 src/gopvpsim)
```

### js-parity-1. [MEDIUM] Tier coloring (rounded stats) vs paste-box scanner (full-precision stats) contradict at threshold boundaries -- 7 shipped tiers / 220 IVs affected

**Where:** scripts/deep_dive.py:4136 (rounded compare) vs scripts/deep_dive_engine.js:753 (full-precision compare)

**What:** Python bakes plot coloring / tier tables by comparing DISPLAY-ROUNDED stats (iv_atk/iv_def = round(full, 2), deep_dive.py:4107) against the tier threshold, while the JS paste-box scanner (loadCollection) compares the FULL-precision attack/defense from POGOCollection.ivsToStatsAtCap against the same threshold. Any IV whose true stat lies in [thresh-0.005, thresh) is colored as a tier member on the scatter and listed in the Python-side tier tables, but the same mon pasted into the scanner reports it does NOT qualify for that tier. Because thresholds are themselves round(p25_stat, 2) of the same stat array (deep_dive.py:639), the boundary-defining IV lands in this window whenever round() went up (~50% of stat-gated tiers).

**Evidence:** Scan of shipped thresholds/*.toml spread tiers: 7 distinct (species, league, tier, stat) boundaries with colored-but-scanner-rejected IVs, 220 IV instances total: Annihilape GL 'High Atk (mirror)' defense=103.0 -> 105 IVs (true def 102.9982349, rounds to 103.00); Malamar GL 'Swag Recommended' attack=120.23 -> 57; Azumarill GL 'kieng_champion' defense=133.7 -> 22; Sylveon GL 4 tiers -> 36. End-to-end through the actual JS: Annihilape 0/9/14 GL -> ivsToStatsAtCap defense=102.9982349, scanner match=false; Python path round(102.9982349,2)=103.0 >= 103.0 -> colored TIER.

**Repro:**

```
(cd /Users/mglerner/coding/hunt2/gopvpsim && .venv/bin/python hunt_scratch/tier_boundary_repro.py)  # mechanism repro through both real code paths; the shipped-TOML scan is in the session transcript (tomllib walk of thresholds/*.toml + ivs_to_stats_at_cap window check)
```

### js-parity-2. [MEDIUM] Compare-candidates 'mirror CMP' pill contradicts the Mirror Slayer CMP % column -- the ba81139 rounding fix was not applied to cmpMirror

**Where:** scripts/deep_dive_engine.js:3249 (cmpMirror) vs scripts/deep_dive_engine.js:2347 (_computeMirrorCmpPct)

**What:** Commit ba81139 (2026-04-22) fixed 'Mirror CMP %' by rounding both sides to 2dp and counting ties as beats, precisely because DATA.ivAtk is baked display-rounded (deep_dive.py:4107) while DATA.mirrorCohortAtk is baked full-precision (deep_dive.py:4387). The later compare-candidates widget (1996b5e) reintroduced the raw comparison: cmpMirror does `DATA.ivAtk[iv] >= cohort[0] - 1e-6`, and the 1e-6 epsilon cannot absorb the up-to-0.005 display rounding. In the exact scenario documented in the _computeMirrorCmpPct comment (Tinkaton UL: cohort collapses to full-precision atk 142.8509983; baked ivAtk = 142.85), the max-atk IV's Top IVs row shows 'Mirror Slayer CMP % = 100%' while its compare card shows 'Loses mirror CMP'. The L51 branch (mirrorCohortAtk51, also full-precision -- deep_dive.py:4396-4412) has the same defect. Reverse-direction false 'Wins' (ivAtk rounded up past a cohort min the true atk sits below) is also possible.

**Evidence:** node hunt_scratch/cmp_mirror_repro.js (extracts both functions verbatim from deep_dive_engine.js, feeds the baked-value pair 142.85 / 142.8509983): prints 'Mirror CMP % ... 100%', 'cmpMirror pill: LOSES mirror CMP', 'contradiction: true'. git log confirms ordering: ba81139 (rounding fix, 2026-04-22) predates 1996b5e (compare widget).

**Repro:**

```
(cd /Users/mglerner/coding/hunt2/gopvpsim && node hunt_scratch/cmp_mirror_repro.js)
```

### BP-1. [MEDIUM] Power-0 move (e.g. Aegislash Shield's canonical fast move) crashes breakpoints() with ZeroDivisionError, silently killing ALL anchor resolution for the dive

**Where:** src/gopvpsim/breakpoints.py:59 (atk_for_damage `(dmg - 1) * def_ / k` with k=0), reached via src/gopvpsim/anchors.py:517 (_resolve_bp_anchor level 3), swallowed at scripts/deep_dive.py:7331 (`except Exception` -> warning -> resolved=[])

**What:** The gamemaster has 5 power-0 moves (SPLASH, YAWN, TRANSFORM, AEGISLASH_CHARGE_AIR_SLASH, AEGISLASH_CHARGE_PSYCHO_CUT) learnable by 49 species. For power 0, _K() returns 0.0 and atk_for_damage(1, ...) computes 0.0/0.0 -> ZeroDivisionError. breakpoints() always enumerates dmg from d_min=1, so ANY call with a power-0 move raises. In the deep-dive pipeline the focal moveset feeds _resolve_bp_anchor for every auto-generated per-opponent anchor; the exception propagates out of resolve_anchors and deep_dive.py's broad try/except downgrades it to a log warning and drops EVERY anchor (atk-slayer, bulk-slayer, CMP tags) for the whole dive. Aegislash (Shield) is a shipped species (thresholds/aegislash_shield.toml, GL dive at userdata/website/aegislash-shield-great-league/) whose canonical fast move IS AEGISLASH_CHARGE_PSYCHO_CUT (power 0), so this is a live path, not hypothetical. bulkpoints() happens to be safe (returns [] because def_for_damage divides by dmg>=1, and the thresh-0 entry is filtered). Fix is one guard: return [] from breakpoints() (or skip the move in _resolve_bp_anchor) when _K == 0. Not documented in DEVELOPER_NOTES, either review file, TODO, or any xfail; the only nearby awareness is anchors.py:608's docstring about def-side divide-by-zero.

**Evidence:** breakpoints(YAWN, ...) raises ZeroDivisionError; end-to-end repro: build_auto_anchors + resolve_anchors for 'Aegislash (Shield)' GL with [AEGISLASH_CHARGE_PSYCHO_CUT, SHADOW_BALL, FLASH_CANNON] raises ZeroDivisionError from breakpoints.py:59 via anchors.py:517. Gamemaster scan: 5 power-0 moves, 49 learner species (Snorlax w/ Yawn is a real PvP archetype).

**Repro:**

```
cd /Users/mglerner/coding/hunt2/gopvpsim && .venv/bin/python -c "import sys; sys.path.insert(0,'src'); from gopvpsim.anchors import build_auto_anchors, resolve_anchors; from gopvpsim.moves import get_moves; from gopvpsim.pokemon import iv_rank, get_pokemon_entry; from gopvpsim.data import parse_types; f,c = get_moves(); grid = iv_rank('Aegislash (Shield)', league='great'); atks=[r['atk'] for r in grid]; defs=[r['def_'] for r in grid]; reg = build_auto_anchors('Aegislash (Shield)','great',['Azumarill'],survivor_ivs=[(0,15,15)]); resolve_anchors(reg,'Aegislash (Shield)','great',[f['AEGISLASH_CHARGE_PSYCHO_CUT'],c['SHADOW_BALL']],parse_types(get_pokemon_entry('Aegislash (Shield)')),min(atks),max(atks),def_min=min(defs),def_max=max(defs))"  # -> ZeroDivisionError
```

### BP-2. [MEDIUM] scripts/breakpoints.py --shadow-atk/--shadow-def flags are dead in the math: damage tables computed non-shadow while the header prints shadow stats

**Where:** scripts/breakpoints.py:89-94 (iv_breakpoints call) and :142-146 (iv_bulkpoints call)

**What:** The CLI defines --shadow-atk/--shadow-def and iv_breakpoints/iv_bulkpoints have attacker_shadow/defender_shadow kwargs (default False), but the CLI never forwards the flags into either call. The flags only affect the printed context header (Pokemon.at_best_level(..., shadow=...)) and the rank-lookup table. Result: with --shadow-atk the header shows the shadow attack (Machamp 164.6) while every damage tier in both tables is computed at non-shadow attack (137.1); with --shadow-def the header shows shadow defense (Registeel def=153.0) while tiers use 183.6. The correct shadow tables differ materially: Machamp COUNTER vs Registeel breakpoint tiers are {8: 4096} as printed vs {10: 1760, 9: 2336} with attacker_shadow=True; bulkpoint tiers {7: 77, 8: 4019} as printed vs {9: 3655, 10: 441}. This is un-flagged wrong output under an explicit user-requested flag. Not in the deep-dive pipeline (which uses iv_rank + anchors and applies shadow correctly post-commit 3fa656b); CLI-only. Not documented anywhere (the 2026-06-11 review's shadow findings L1/headline-2 cover anchors.py, not this script).

**Evidence:** diff of CLI output with/without --shadow-atk changes ONLY the header line 'atk=164.6' vs 'atk=137.1' -- breakpoint and bulkpoint tables byte-identical. Library cross-check shows the true shadow tiers (9/10 split) differ from the printed 8-flat table.

**Repro:**

```
cd /Users/mglerner/coding/hunt2/gopvpsim && .venv/bin/python scripts/breakpoints.py Machamp COUNTER Registeel --shadow-atk > /tmp/a.txt 2>/dev/null; .venv/bin/python scripts/breakpoints.py Machamp COUNTER Registeel > /tmp/b.txt 2>/dev/null; diff /tmp/a.txt /tmp/b.txt  # only the header differs. Then: .venv/bin/python -c "import sys; sys.path.insert(0,'src'); from collections import Counter; from gopvpsim.breakpoints import iv_breakpoints; print(dict(Counter(r['damage'] for r in iv_breakpoints('Machamp','COUNTER','Registeel',league='great',attacker_shadow=True))))"  # {10: 1760, 9: 2336} vs the CLI's 8-flat
```

### FC-1. [MEDIUM] Fast move landing after Aegislash Blade->Shield mid-flight revert credits the STALE queued move's energy (9) instead of the current form's move (6, PvPoke behavior)

**Where:** /Users/mglerner/coding/hunt2/gopvpsim/src/gopvpsim/battle.py:2833 (legacy floating-fast block, `qmove['energyGain']`); same defect at battle.py:2771 (mechanics='new' step-3 landing, `move['energyGain']` from `_queued_fast`)

**What:** When Aegislash (Blade) shields an incoming charged move while its own multi-turn fast (Psycho Cut 2t / Air Slash 3t) is in flight, the activate_shield revert swaps bp.fast_move to the Shield-form CHARGE variant. The in-flight fast then resolves with damage from the NEW move (fast_move_damage uses self.fast_move -> 1 dmg) but energy from the OLD queued move dict (+9). PvPoke's processAction (Battle.js ~912: `var move = poke.fastMove;`) uses the CURRENT move for both, and its fast branch additionally hard-codes `energyGain = 6` when `attacker.activeFormId == "aegislash_shield"` (Battle.js ~1313-1321) plus a timeline hardcode keyed on `move.moveId.indexOf("AEGISLASH_CHARGE") == -1` (Battle.js ~1495) that exists precisely for this stale-landing case — so the oracle credits 6, we credit 9. Our behavior matches NEITHER self-consistent interpretation (old move completes: 9 energy + PC damage; new move lands: 6 energy + 1 dmg) — it is an internally inconsistent old/new mix, so it is a bug under any reading of the game. In legacy mode the only reachable site is the floating-fast block (queued fasts are otherwise always flushed on charged turns before a form change can intervene); in new mode the step-1.5 deferred-charged revert happens BEFORE step-3 landings and queued fasts are never floated, so line 2771 hits the same stale dict.

**Evidence:** Timeline: Aegislash (Shield, SB-only) 4/14/15 L46 vs Steelix 0/15/15 L23.5 GL 1-1 — T25 'Aegislash (Blade) uses Psycho Cut' (queued), Steelix Psychic Fangs shielded, 'changed form (shielded)', then 'floating fast -> 1 dmg, energy 40' (31+9; PvPoke semantics give 37). Scenario fires with the DEFAULT GL moveset across the meta: scan found it in Gligar/Diggersby/Furret/Jumpluff/Drapion/Mandibuzz/Steelix cells. A/B vs a scratch copy patched to PvPoke semantics (p.fast_move['energyGain']), Aegislash (Shield) 4/14/15 SB+GB vs 19 GL meta opponents x 9 shield cells (171 cells): 81 cells change score/energy, 4 winner flips (Gligar 2-2: 462 L -> 504 W; Jumpluff 2-2: 507 W -> 439 L; Mandibuzz 2-0: 511 W -> 393 L; Sableye 2-1: 518 W -> 500 tie). New-mode reachability confirmed: same revert-then-landing sequence in Steelix/Drapion/Umbreon/Registeel new-mode runs. Whole-battle oracle isolation is blocked by documented Aegislash decision divergences (PvPoke bug #3 Gyro Ball + shield-form farm behavior), but the PvPoke source lines above are unambiguous, and aegislash_shield.toml / aegislash_blade.toml are shipped thresholds.

**Repro:**

```
cd /Users/mglerner/coding/hunt2/gopvpsim && .venv/bin/python -c "import sys; sys.path.insert(0,'src'); from gopvpsim.battle import BattlePokemon, simulate; from gopvpsim.pokemon import Pokemon, LEAGUE_CAPS; from gopvpsim.moves import get_moves; F,C=get_moves(); mk=lambda sp,f,cs,sh,iv: BattlePokemon.from_pokemon(Pokemon.at_best_level(sp,*iv,league='great'), dict(F[f]), [dict(C[c]) for c in cs], shields=sh, league_cp=1500); a=mk('Aegislash (Shield)','AEGISLASH_CHARGE_PSYCHO_CUT',['SHADOW_BALL'],1,(4,14,15)); d=mk('Steelix','THUNDER_FANG',['PSYCHIC_FANGS','CRUNCH'],1,(0,15,15)); r=simulate(a,d,log=True); [print(l) for l in r.timeline if 22<=int(l[1:4])<=26]"  # T25: revert then floating fast energy 31->40 (+9); PvPoke Battle.js:1313-1321 credits 6
```

### js-parity-3. [LOW] Two disagreeing SP-rank tables are baked into the same dive HTML; the rank-1 designation itself flips (e.g. Medicham GL 5/15/14 vs 5/15/15)

**Where:** scripts/deep_dive.py:4110 (spRanks bake: round(SP,1) + enumeration-order ties) vs src/gopvpsim/pokemon.py:339 (iv_rank: unrounded SP + iv-sum tiebreak)

**What:** DATA.spRanks (drives plot hover 'SP Rank', summary-table SP Rank column, cmp-card 'SP #', and rank1RefIvIdx at deep_dive.py:4161) ranks by SP rounded to 0.1 with ties resolved by stable enumeration order (lowest a/d/s first). DATA.collection.rankLookup (drives the scanner's off-grid SP rank and stats.rank) comes from iv_rank, which uses unrounded SP with an IV-sum-descending tiebreak explicitly 'matching PvPoke's tie-breaking behavior'. The two disagree on 25-48% of IVs (delta up to 5), and for true SP ties they disagree on WHICH IV is rank 1: Medicham GL spRanks#1 = 5/15/14 but rankLookup#1 = 5/15/15 (identical battle stats -- HP both floor to 142 -- so PvPoke convention picks the higher IV sum, 5/15/15, the famous published Medicham rank-1); same flip for Talonflame UL and Dialga ML (15/15/14 vs 15/15/15). Users cross-checking the page's 'SP Rank 1' marker against PvPoke see the wrong spread flagged, and in an IV-floor dive an off-grid pasted mon's SP rank comes from a different scale than on-grid rows in the same table (sort column interleaves the two). The JS comment at deep_dive_engine.js:969 ('same data, cheaper lookup') is factually wrong.

**Evidence:** hunt_scratch/rank_sources.py (replicates the deep_dive.py:4110-4126 bake vs compute_rank_lookup): Azumarill GL 1016/4096 differ (max delta 2), Medicham GL 1354 (max 4), Talonflame UL 1954 (max 5). Rank-1 flip check across 8 species/league configs: DIFFERENT for Medicham GL, Talonflame UL, Dialga ML. Verified Medicham 5/15/14 and 5/15/15 have bit-identical atk/def/hp at L50 (true SP tie 2109813.550957037), so the flip is purely the tiebreak.

**Repro:**

```
(cd /Users/mglerner/coding/hunt2/gopvpsim && .venv/bin/python hunt_scratch/rank_sources.py)  # plus the rank-1 flip one-liner in the transcript (compute_rank_lookup vs replicated sp_ranks, checking rank==1 triples)
```

### js-parity-4. [LOW] JS matchMons lacks Python match_mons' built-in gender filter -- row-for-row contract violated for gender-differentiated species, invisible to the enforcement harness

**Where:** scripts/deep_dive_user_collection.js:339 (matchMons) vs src/gopvpsim/user_collection.py:359-373

**What:** Python match_mons filters gendered species internally and per-target (drops a female-gendered row matching bare 'X' when 'X (Female)' exists in the pokemon index, and vice versa). The JS port only filters when the CALLER passes opts.requireGender -- a single global gender, not per-final-species -- so on identical input the two return different rows. The file header states 'The two MUST agree row-for-row on the same input -- verify_js_parser.py is the enforcement mechanism', but the harness's fixtures contain no gendered species and it never passes requireGender, so it stays green (PASS: 577/577 records agree). Production dive pages are unaffected because loadCollection injects DATA.collection.requireGender computed by deep_dive.py:4590-4594 with the same sibling rule, and a dive has a single focal species. The exposure is the library contract itself (a future caller with multi-species thresholds containing both 'X' and 'X (Female)' cannot even express Python's per-target behavior via the single requireGender opt) -- the exact contract-drift class (gender) that TODO.md's CP12 bullet records as having already bitten the gobattlekit copy.

**Evidence:** hunt_scratch/gender_parity.py: Oinkologne CSV with one female + one male row vs {'Oinkologne': {...}} thresholds -> Python match_mons returns [('male','Oinkologne')]; JS matchMons (same call shape as verify_js_parser.py) returns [['female','Oinkologne'],['male','Oinkologne']]. verify_js_parser.py run in this session: PASS (its fixture cannot see the gap).

**Repro:**

```
(cd /Users/mglerner/coding/hunt2/gopvpsim && .venv/bin/python hunt_scratch/gender_parity.py)
```

### js-parity-5. [LOW] owned_breakdown.py's normative claim ('the website-JS ... must reproduce its numbers') is false for the shipped 'Gives up vs #1' column

**Where:** scripts/owned_breakdown.py:13-14 vs scripts/deep_dive_engine.js:1165-1194

**What:** owned_breakdown.py (the self-declared 'Python REFERENCE implementation' whose numbers 'the website-JS and gobattlekit versions must reproduce') defines gives-up as: matchups the STAT-PRODUCT rank-1 spread wins but this IV loses, over even shields. The shipped JS column was deliberately re-keyed the same day (9b85f56 'track the y-axis') to reference the #1 IV on the CURRENT y-axis metric (default avgScore) over the user-selected shield scenarios -- a different reference spread and scenario set, so the numbers do not and cannot match the Python reference. The JS is self-consistently documented in its own help text; the stale in-tree claim is the defect (an un-flagged known-wrong contract statement on a surface gobattlekit is told to port from). Additionally, the compare-candidates card reuses the identical label 'Gives up vs #1' for a third, different metric (avg-score-point gap to the best-avg IV, deep_dive_engine.js:3228/3327), so one page carries two same-named numbers with different units.

**Evidence:** git log: 87e4444 (owned_breakdown.py reference, 2026-06-21) + 3c18296 (JS column, rank-1 reference, same day) + 9b85f56 (same day, switches JS reference to y-axis #1). Current JS code: _guRefIv = argmax(yValues) (deep_dive_engine.js:1186-1190), not DATA.rank1RefIvIdx; owned_breakdown.py:141 uses rank1_spread() (SP rank-1 via best_level enumeration).

**Repro:**

```
(cd /Users/mglerner/coding/hunt2/gopvpsim && git show 9b85f56 --stat && sed -n '1164,1194p' scripts/deep_dive_engine.js && sed -n '1,18p' scripts/owned_breakdown.py)
```

### BP-3. [LOW] iv_breakpoints/iv_bulkpoints skip the Aegislash (Blade) whole-level rule inside their 4096-IV loops (and for iv_bulkpoints' fixed attacker), disagreeing with iv_rank/at_best_level

**Where:** src/gopvpsim/breakpoints.py:225-231 (attacker loop, no Blade round-down) and :288-297 + :304-309 (iv_bulkpoints fixed attacker and defender loop, no Blade round-down); contrast :214-215 where the rule IS applied to the fixed defender 'per commit 1b6c075'

**What:** The Blade whole-level-only rule is applied at breakpoints.py:214 for iv_breakpoints' fixed defender, but NOT in the 4096-IV attacker loop of iv_breakpoints, NOT for iv_bulkpoints' fixed attacker, and NOT in iv_bulkpoints' 4096-IV defender loop. So when Aegislash (Blade) is the swept species, 2053/4096 combos sit at half levels while iv_rank (used for the rank column in the same scripts/breakpoints.py output) has 0 half-level combos -- the same row mixes a half-level atk/def/damage with a whole-level-convention rank, and 7 IV combos flip a COUNTER damage tier vs the whole-level convention. The 2026-06-11 review's item 14 notes the rounding is DUPLICATED at four sites (an architecture note) but does not flag the missing application in these loops. Impact is confined to the CLI script and tests (the dive pipeline uses iv_rank).

**Evidence:** iv_breakpoints('Aegislash (Blade)','PSYCHO_CUT','Azumarill'): 2053/4096 combos at half levels; iv_rank('Aegislash (Blade)', great): 0. iv_bulkpoints('Aegislash (Blade)','COUNTER','Medicham'): 2053/4096 half-level combos, of which 7 take a different COUNTER damage tier than the whole-level (level-0.5) build.

**Repro:**

```
cd /Users/mglerner/coding/hunt2/gopvpsim && .venv/bin/python -c "import sys; sys.path.insert(0,'src'); from gopvpsim.breakpoints import iv_breakpoints; from gopvpsim.pokemon import iv_rank; rb = iv_breakpoints('Aegislash (Blade)','PSYCHO_CUT','Azumarill',league='great'); print(sum(1 for r in rb if r['level']%1.0), 'of', len(rb), 'half-level in iv_breakpoints;', sum(1 for r in iv_rank('Aegislash (Blade)',league='great') if r['level']%1.0), 'in iv_rank')"
```

### FC-2. [LOW] Blade->Shield revert-level clamp rationale is factually stale vs the pinned oracle: PvPoke's cpms table reaches level 55 (since 2020), so it computes real level-52/54/55 Shield reverts (not 'undefined') for 35 best-level IV combos, including UL 15/15/15

**Where:** /Users/mglerner/coding/hunt2/gopvpsim/src/gopvpsim/formchange.py:127-148 (_aegislash_shield_level docstring + clamp); DEVELOPER_NOTES.md 'Form change gotchas' #3

**What:** The documented claim — 'PvPoke has the same latent overflow (cpms[index] -> undefined)... Clamping is exact: levels above 51 don't exist, and the walk-down from 51 reaches the same fixed point the bigger-table walk would' — is wrong against the pinned pvpoke clone. Pokemon.js's cpms array has had 109 entries (levels 1..55) since commit ca1d9d48b (2020-11-19, 'CPM values for 51-55'), i.e. it already did at the 2026-06-06 re-vetting. Consequences: (a) for GL blade focals at level 25 with near-zero IVs, PvPoke's reverse walk keeps the reverted Shield form at level 52.0 (CP 1440 <= 1500), CPM 0.8503 vs our clamped 51.0/0.8453 (+0.6% stats); (b) for UL blade focals at 41.5 with high IVs — including the mainstream 15/15/15 — PvPoke keeps level 55.0 (CPM 0.8653, +2.4% stats vs our 51.0); (c) PvPoke's NaN overflow is real only past level 55 (start > 55), which covers 4069/8192 best-level blade focals (mostly UL blades >= 42). Our clamp remains the defensible choice (levels above 51 don't exist in-game; PvPoke's 52-55 and NaN are both bugs vs the game), but the pinned 'same fixed point / exact' claim is false vs the oracle, the doc's GL-52-off-table example is wrong, and any oracle comparison of Blade-focal dives (aegislash_blade.toml is shipped) will show real numeric divergence on shield-revert cells rather than the documented NaN.

**Evidence:** pvpoke Pokemon.js:24 cpms has 109 entries; `git log -S 0.847803702398935` -> ca1d9d48b (2020-11-19), ancestor of the bc532fbda vetting pin. Exhaustive comparison of our clamped walk-down vs a double-precision port of PvPoke getFormStats over all 4096 IVs at each build's best legal Blade level, GL+UL: 35 numeric mismatches (GL: 8 combos e.g. 0/0/0 blade L25 -> PvPoke 52.0 vs ours 51.0; UL: 26 combos at blade 41.5 -> PvPoke 55.0, 1 combo -> 54.0, incl. 15/15/15), 4069 PvPoke-NaN (off-table start > 55), rest identical. Shield CP at 52 for 0/0/0 = 1440 (fits GL cap), at 55 for 15/15/15 = 1852 (fits UL cap). Forward direction (Shield->Blade _aegislash_alt_level) is clean: 0/43,632 mismatches across IV grid x levels 1..51 x GL/UL.

**Repro:**

```
cd /Users/mglerner/coding/hunt2/pvpoke && git log --oneline -1 -S '0.847803702398935' -- src/js/pokemon/Pokemon.js  # ca1d9d48b 2020. Then port-compare: PvPoke reverse start for GL = blade_level/0.5+2; for blade L25 0/0/0, CP(shield, cpm52=0.850300014019012) = floor(97*sqrt(272)*sqrt(155)*cpm52^2/10) = 1440 <= 1500 so PvPoke returns 52.0; gopvpsim _aegislash_shield_level clamps to min(52, max(CPM))=51.0
```

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

### cache-migration (found F1 [HIGH], F2 [MEDIUM] — recovered sections above; the coverage notes below predate the recovery)

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

### Remaining lenses (js-ports, breakpoints-math, formchange-newmech)

These three lenses DID produce confirmed findings — js-parity-1..5,
BP-1..3, FC-1/2, recovered from the workflow journal into the sections
above. Their prose coverage/dismissed narratives were truncated in the
report handoff and are not reproduced here; the per-finding evidence
and repro records above are complete. Do not count their subsystems as
deeply swept beyond what those findings and repros demonstrate.

### Not reached by round 2 at all (union)

Master league at sweep scale; best-buddy levels; broad non-default IV
spreads; always-bait and both-sides-no-bait oracle surfaces;
mechanics='new' vs any reference (none exists); numba-absent
pure-Python fallback under the full corpus; a targeted NB-1-class
sweep (promoted-self-buff focals x atk-debuff opponents) to bound its
meta-wide footprint — the natural follow-up before the NB-1
fix-vs-document decision.
