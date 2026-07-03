# Both-self-debuff PvPoke divergence cluster -- investigation + keep-vs-fix

Decision material for Michael. READ-ONLY investigation (no engine edits, no
dive/sweep run). Follows up TODO.md "#3-followup" and the bug-#3 commit
(`50e8cd2`) note that the farm-stack fix's oracle surfaced ~117 pre-existing
both-self-debuff PvPoke divergences (~7 winner-flips) on Lurantis / Blaziken /
non-default movesets.

Applies the CLAUDE.md "When our sim diverges from PvPoke" gate.

**Bottom line: KEEP. Do not change engine behavior. No re-dive needed.**
The cluster is the broad both-self-debuff manifestation of two ALREADY-DOCUMENTED
intentional divergences; in this sub-population PvPoke is demonstrably *worse*
(it leads a worse-typed self-debuff move and loses fights we win), and the only
two PvPoke-default movesets affected show zero winner-flips.

> **[2026-07-03 correction]** The "zero default-moveset winner-flips" wording
> is falsified as literally stated: the re-measurement (Addendum below) found
> one default-moveset flip on current data (Braviary vs Lugia ML 2-0,
> ours-WIN/PvPoke-LOSE, same mechanism). The claim survives only re-scoped as
> "zero PvPoke-FAVORABLE default-moveset flips." KEEP verdict unchanged
> (strengthened, in fact — see Addendum).

---

## What "the cluster" is

The both-self-debuff population = a focal running a moveset whose **charged
moves are ALL self-debuffing** (no non-debuffing alternative for the farm-swap
or the post-DP bandaid to escape into). 15 charged moves are self-debuffing
(Brave Bird, Close Combat, Superpower, Overheat, Leaf Storm, Draco Meteor,
Wild Charge, ...); **36 species can field two of them** at once. Almost all such
movesets are OFF-META (PvPoke never recommends two self-debuff nukes).

---

## VERIFIED (measured / traced this run)

All numbers below were produced this session: our engine via
`gopvpsim.battle.simulate(..., charged_policy=pvpoke_dp)` at 15/15/15, PvPoke
via `scripts/pvpoke_trace.js` against `../pvpoke` at the matching best-level for
each league. Harness validated against the bug-3 oracle (Pinsir vs Cresselia
9/9 exact, incl. the 656 farm-stack repro cell).

### V1. The cluster reproduces, and every flip favors US

GL re-derivation scan -- 8 both-self-debuff focals (Pinsir, Hariyama, Lurantis,
Blaziken, Sirfetch'd, Staraptor, Passimian, Flareon; default fast move + a
forced two-self-debuff charged pair) x 10 bulky GL walls (Cresselia, Registeel,
Azumarill, Lickitung, Dewgong, Quagsire, Swampert, Bastiodon, Mandibuzz,
Carbink) x 9 shields = **720 cells: 30 score-diffs, 8 winner-flips.**

- **All 8 winner-flips are the same direction: our focal WINS, PvPoke's focal
  LOSES. Zero reverse-flips.** 7 of 8 occur at opponent-shields = 0.
- (My focal/opponent set differs from the bug-3 commit's 378-cell scan, so the
  raw counts differ from "117/7"; the *character* -- ours-favorable, off-meta --
  is the same. This is a re-derivation, not a re-run of that exact scan.)

The 8 flips:

| focal    | moveset              | opponent  | sh  | ours    | PvPoke   |
| -------- | -------------------- | --------- | --- | ------- | -------- |
| Lurantis | Leaf Storm + S.Power | Cresselia | 1-0 | 691 WIN | 477 LOSE |
| Blaziken | Brave Bird + Overht  | Cresselia | 1-0 | 512 WIN | 370 LOSE |
| Blaziken | Brave Bird + Overht  | Bastiodon | 1-0 | 646 WIN | 416 LOSE |
| Blaziken | Brave Bird + Overht  | Bastiodon | 2-0 | 646 WIN | 416 LOSE |
| Blaziken | Brave Bird + Overht  | Mandibuzz | 1-0 | 586 WIN | 378 LOSE |
| Blaziken | Brave Bird + Overht  | Mandibuzz | 2-1 | 530 WIN | 340 LOSE |
| Flareon  | Overheat + S.Power   | Cresselia | 1-0 | 642 WIN | 487 LOSE |
| Flareon  | Overheat + S.Power   | Mandibuzz | 1-0 | 556 WIN | 408 LOSE |

(The 22 score-only diffs go BOTH ways on margin but agree on winner.)

### V2. Mechanism -- PvPoke leads/concentrates the WORSE-typed self-debuff move

Traced chargedLogs + PvPoke `dpPlans` on all three named flips:

- **Lurantis vs Cresselia 1-0.** Ours: Leaf Storm (grass, neutral, 85) x2 ->
  WIN. PvPoke: **its near-KO DP plan is Leaf Storm x2 (identical to ours), but
  the EXECUTED chargedLog leads Superpower** (fighting, NVE into psychic) then
  Leaf Storm -> LOSE. The DP-plan-vs-executed mismatch proves a **post-DP
  bandaid swap** -- this is the documented `bandaid[866]/[885]` "near-KO plan
  choice" swap (`finalState.moves[0]` -> `activeChargedMoves[0]` when
  opp.shields==0, selfDebuffing, energy>50, hp/maxhp>0.5, dmg/oppHP<0.8).

- **Blaziken vs Bastiodon 1-0** and **Flareon vs Mandibuzz 1-0.** Here PvPoke's
  DP *plan itself* is the worse move (`[BRAVE_BIRD, OVERHEAT]` /
  `[SUPER_POWER, SUPER_POWER]`) and executes it. Brave Bird is double-resisted
  by Bastiodon (flying vs rock/steel) and carries -3 def; Superpower is neutral
  but weaker than Overheat (130 power). **Our per-turn best-DPE recompute leads
  Overheat** (the correctly-typed nuke) and wins. This is the
  **bestChargedMove-ordering** divergence (DEVELOPER_NOTES Divergence #3:
  PvPoke caches bestChargedMove / orders activeChargedMoves at init; we recompute
  per-turn vs the current opponent).

Common theme across both mechanisms: **PvPoke ends up leading a worse-typed
self-debuff move; our move selection picks the correct nuke.** Both our
behaviors are already-documented intentional deviations we believe are correct.

### V3. Our wins are legitimate fights, not score artifacts

Full battle log for Flareon vs Mandibuzz 1-0 confirms a real, legal sequence:
Ember farm -> Overheat (101) at T15 -> shield the Foul Play -> Superpower (37)
at T24, Flareon survives, score 556. Energy/shield bookkeeping is consistent.
Not a coincidence-of-score win.

### V4. Shipped (default-moveset) impact: ZERO winner-flips

Only **2 PvPoke-DEFAULT movesets in any league are both-self-debuff**:
Braviary (Master, Close Combat + Brave Bird) and Zacian-Hero (Ultra, Wild
Charge + Close Combat). Scan of those two x 8 league-appropriate opponents x 9
shields = **144 cells: 6 score-diffs, 0 winner-flips.** The 6 diffs are
same-winner margin (and go both directions -- e.g. Zacian vs Swampert 1-0 ours
519 < PvPoke 625). So the deep-dive deliverables that actually ship (winner +
breakpoint/bulkpoint thresholds) are intact on the default-meta movesets. This
matches the bug-3 commit's "0/2160 default-meta cells changed."

---

## ASSUMED / INFERRED (not exhaustively proven this run)

- **No reverse-flip exists in the unscanned population.** I found 0
  PvPoke-better winner-flips in 720 (GL) + 144 (UL/ML default) = 864 cells, but
  my opponent set is a hand-picked bulky-wall list. A Lapras-style
  bulky-comeback case -- where PvPoke's slower multi-throw plan genuinely wins a
  close fight our single-nuke-stack loses -- cannot be *excluded* by absence.
  The **single-self-debuff analog of exactly this risk is already xfail-pinned**
  (Moltres-G / Lapras [1,2], DEVELOPER_NOTES "Near-KO DP plan choice"). In the
  *both*-self-debuff sub-population the risk is lower than the single-debuff case
  because PvPoke's swap target is itself self-debuffing and worse-typed (no
  HP-retention upside like the non-debuff Fly chain), but I did not prove it
  cannot happen.
- **Exact PvPoke internal for Blaziken/Flareon** (init-cache vs
  activeChargedMoves priority-shuffle) is attributed to Divergence #3 by the
  DP-plan trace but I did not step the JS to distinguish the two sub-causes.
  Doesn't change the decision.

---

## KEEP-vs-FIX recommendation: KEEP

Per CLAUDE.md "When our sim diverges from PvPoke", all three gate questions
point to KEEP:

1. **Is PvPoke demonstrably better here? NO -- the opposite.** In every traced
   flip PvPoke leads a worse-typed self-debuff move (Superpower into
   psychic/neutral, Brave Bird double-resisted by Bastiodon) and LOSES a fight
   our engine WINS. Leading your best-typed nuke is correct play; PvPoke's
   choice is strictly dominated in this sub-population (the move it swaps/orders
   to is also self-debuffing, so there is no HP-retention or tempo upside, just
   worse damage).

2. **Do we have a defensible reason? YES -- two already-documented intentional
   divergences.** The cluster is the broad both-self-debuff union of (a)
   Divergence #3 (per-turn bestChargedMove recompute vs PvPoke's init cache) and
   (b) the near-KO `bandaid[866]/[885]` `_cached_damage` subgate. The
   both-self-debuff case is the CLEAN sub-case of (b): PvPoke's bandaid swap can
   only land on another self-debuffing move, so unlike the mixed Moltres-G
   population (6:1 + 1 Lapras reverse) there is no compensating benefit -- we are
   unambiguously right here.

3. **Would matching PvPoke make us worse for the use case? YES.** Matching would
   flip ~8 focal-WINS to focal-LOSSES on these movesets, degrading the measured
   matchup quality (and any breakpoint/bulkpoint readout) for zero correctness
   gain. The use case is real-PvP teambuilding analysis, where the focal would
   in fact throw its best nuke.

**Action: document and do not change behavior.** This is already covered in
spirit by the DEVELOPER_NOTES "Near-KO DP plan choice" + Divergence #3 entries;
suggest adding a one-line pointer there that the both-self-debuff population is
the favorable-direction extension of the same two divergences, and (optionally)
an xfail pinning one flip (e.g. Lurantis vs Cresselia 1-0: ours 691/WIN,
PvPoke 477/LOSE) as ours-correct, mirroring the Moltres-G/Lapras xfail. No
suite change is required for correctness; the existing suite already passes.

**Revisit only if** a wider opponent scan surfaces a reverse-flip
(PvPoke-better, like Lapras in the single-debuff family) -- then re-evaluate
that specific matchup shape against the existing near-KO divergence note.

---

## Migratability verdict (conditional -- we are NOT fixing)

Recorded per the task's "if a fix is warranted" branch; moot under KEEP.

**If a future engine change ever DID move us toward PvPoke here, the touched set
is cleanly migratable -- no schema change, focal-only predicate.**

- **Predicate (touched set):** focal moveset has `n_charged >= 2` AND **every**
  charged move is `selfDebuffing`. Pure function of the sidecar's stored focal
  charged-moveset + the gamemaster `selfDebuffing`/`buffs`+`buffTarget==self`
  flags -- both already in the sweep-cache sidecar (movesets + gamemaster hash).
  `migrate_cache.py --predicate` would WARM-SERVE every column where the focal
  is NOT all-self-debuff.
- **Proof outline:** the divergence requires the farm-swap (`farm_swap_idx`) /
  post-DP bandaid to be unable to escape into a non-debuffing move. A focal with
  >=1 non-debuffing charged move always has that escape and already matches
  PvPoke on the self-debuff path (bug-3: Malamar Super Power + Foul Play 18/18
  exact). So `touched_set` subset of `{focal all-self-debuff}`. The predicate
  keys on the FOCAL only -- correct, because the divergence is about the focal's
  own move selection, not the opponent's (confirmed: the mechanism is
  bestChargedMove ordering / finalState swap, both focal-internal).
- **Soundness caveats (standard for migrate_cache):** (a) only valid if the
  self-debuff fix is the SOLE change in that engine-hash bump -- a co-batched
  unrelated fix would need its own predicate or forces cold; (b) one-shot,
  pinned to the specific `--from-engine` hash.

So: **migratable cleanly if ever fixed, but the recommendation is KEEP, so no
migration is needed.**

---

## Repro pointers (for re-running)

- Self-debuff move set + 36-species population: enumerate gamemaster moves with
  `buffTarget=='self'` and a negative buff, then species with >=2 such charged
  moves (incl. eliteMoves).
- GL scan harness pattern: our `simulate(a,d, charged_policy_0/1=pvpoke_dp)` at
  15/15/15 vs `node scripts/pvpoke_trace.js --pvpoke-root ../pvpoke` at each
  side's GL best level. Validate against `tests/test_bug3_farm_stack.py`
  (Pinsir vs Cresselia) before trusting counts. NOTE: pvpoke_trace returns
  `score` as `[p1, p2]`; use `score[0]`. Get levels from
  `Pokemon.at_best_level(name, 15,15,15, league=...).level` -- a wrong level
  silently changes the winner (this bit me mid-investigation).
- Mechanism trace: PvPoke `dpPlans` (near-KO DP plan) vs `chargedLog` (executed)
  -- a mismatch is a post-DP bandaid[866]/[885] swap; a match with a worse-typed
  lead is the Divergence-#3 bestChargedMove ordering.

---

## Addendum 2026-07-03 — re-measured on c7f9ba2 (post-bandaid[910] ffb582b)

Everything above was measured one commit BEFORE the bandaid[910] fix
(`ffb582b`, 2026-06-29 15:29), whose proven touched set
(`self_debuff_either_side`) contains this entire cluster. Re-measured on
`c7f9ba2` (our engine) vs pvpoke `00f0afe7f`; only `ffb582b` touched engine
files in between, so the A/B attribution is complete.

**KEEP verdict: STILL HOLDS, strengthened.**

- **V1 GL scan (same 720 cells): 29 score-diffs (was 30), still exactly 8
  winner-flips, all 8 rows byte-identical to the table above.** The one
  changed cell is score-only: Lurantis vs Swampert 0-0, old ours 956 vs
  PvPoke 769 -> new ours 769 = exact agreement (the fix working as intended).
- **The fix's total footprint across all 864 re-measured cells: 4 cells
  (1 GL + 3 UL), every one moved TO exact PvPoke agreement, zero flips
  created or dissolved.** The V4 pinned example "Zacian vs Swampert UL 1-0
  ours 519" is DEAD: now 625 = PvPoke 625, exact agreement. Do not reuse
  any pre-addendum V4 number.
- **V4 re-scope:** on current data there IS one default-moveset winner-flip —
  Braviary (AIR_SLASH / CLOSE_COMBAT+BRAVE_BIRD) vs Lugia (DRAGON_TAIL /
  AEROBLAST+FLY) ML 2-0: ours 695 WIN / PvPoke 417 LOSE. A/B: pre-existing,
  not fix-caused (0 of 72 Braviary cells changed). Traced: PvPoke throws
  double-resisted Close Combat into psychic/flying where we lead Brave Bird —
  the same worse-typed-self-debuff-lead mechanism (Divergence #3 family), and
  ours-favorable like every other flip. Why the 2026-06-28 scan missed it is
  unknowable: the V4 opponent sets were never recorded, and default movesets
  resolve from a live 1-day-TTL rankings cache. Lesson recorded in the pins.
- **Regression pins: `tests/test_both_self_debuff_divergence.py`** (4 tests:
  Lurantis/Cresselia GL 1-0 = 691 w0; Blaziken/Bastiodon GL 1-0 = 646 w0;
  Braviary/Lugia ML 2-0 = 695 w0; Zacian/Swampert UL 1-0 = 625 w0 agreement
  pin). Movesets hard-coded — default-moveset resolution drifts with the
  rankings cache and would silently invalidate the pins.
