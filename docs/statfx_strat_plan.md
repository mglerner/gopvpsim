# Stat-effect strat -- plan of record

*(Michael, 2026-09-22: "scope out a general thing, but specifically test it
on sableye and shadow sableye." Triggered by the question of when Sableye
should fire Drain Punch.)*

## The gap

Our engine is a port of PvPoke's battle AI (Artificial Intelligence, here
meaning its move-choice logic). It chooses a charged move by immediate
damage-per-energy (DPE) and turns-to-KO (knock out). A handful of PvPoke
tie-break clauses nudge self-buffing moves forward when their DPE is
close, but nothing values a stat change for the turns it outlasts the
throw. Drain Punch (40 energy, +1 Defense, guaranteed) loses to Foul Play
(40 energy, same-type attack bonus) on DPE, so the engine opens with Foul
Play, and the +1 Defense that would have cushioned every later hit is never
priced.

A 2026-09-22 scratch probe (engine timing kept, only the move identity
swapped, PvPoke default IVs, top-40 GL, 9 shield scenarios) put the
hindsight ceiling at +26 mean rating / +20 net wins for Shadow Sableye and
+36 / +32 for Sableye with Drain Punch + Foul Play, over 342 matchups
each. Simple rules capture only part of it: "Drain Punch into shields" is
positive whenever the opponent starts with shields and negative when it
does not.

## The class

A charged move whose stat change is **guaranteed** (`buffApplyChance` 1)
and **persists** for the rest of the fight:

| flavor      | effect on the fight            | examples                            |
| ----------- | ------------------------------ | ----------------------------------- |
| self-buff   | our later damage/bulk improves | Drain Punch, Trailblaze, Rage Fist  |
| opp-debuff  | their later damage/bulk drops  | Icy Wind, Rock Tomb, Chilling Water |
| self-debuff | our later damage/bulk drops    | Superpower, Brave Bird, Wild Charge |

Chance effects (Moonblast 10%, Air Cutter 12.5%) are out of scope: a
strategy cannot choose to land them. Self-debuffs are the mirror-image
question (when to *accept* the cost) and are phase 3, because the engine
already carries one deviation there (throw a self-debuffing move only when
a fast-move KO won't suffice).

Membership is computed from move data (`stat_effect` in
`scripts/statfx_lab.py`); rules never name a species. At the 2026-09-22
dive list (136 pages, PvPoke default moveset per page), 56 pages carry a
guaranteed effect: 14 self-buff, 31 opp-debuff, 11 self-debuff (pages can
carry two). Dive pages render their top five movesets, so the real count
is higher (plain Sableye's default is Foul Play + Power Gem, but its page
also renders Drain Punch + Foul Play).

## Architecture

- **Where it lives:** a second registered case in the PoGoDives tier
  (`pogodives_dp`; see `docs/cramorant_policy_plan.md`). The tier's
  per-side semantics, thin dispatch, fallback invariant (byte-identical
  to `pvpoke_dp` when no case applies) and cache key normalization
  (non-applicable pairs reuse the plain PvPoke columns) all carry over
  unchanged. The applicability predicate is focal-side: the marked side's
  moveset contains a class move. Only the marked side plays the strat; the
  opponent stays plain PvPoke, as for Cramorant.
- **What it changes (phase 1):** move IDENTITY only, at the fire points
  `pvpoke_dp` already chose, and only to an alternative that is affordable
  at that moment. Timing is untouched, so every changed battle differs from
  plain PvPoke by exactly the swapped throws. "Hold energy for the pricier
  effect move" is phase 2; it needs the timing layer and a bigger oracle.
- **How rules are shaped:** a per-START-scenario sheet (my shields v
  theirs), each row naming a rule from a small generic vocabulary, `None`
  = plain PvPoke from that start. Same shape as `_POGODIVES_SHEET`, because
  the Cramorant campaign showed uniform rules fail the strict bar in some
  start scenarios while clearly winning in others, and the first Sableye
  probe shows the same split.
- **Rule vocabulary (features, all generic):** opponent shields up; whether
  the non-effect move KOs now; our current stage on the effect's stat
  (capped at +/-4); an estimate of throws remaining (energy + fast-move gain
  over PvPoke's turns-to-live, / cheapest charged cost). New features are
  added when an oracle trace motivates them, not speculatively.

## Evaluation contract (reused from the Cramorant campaign)

- **Pool and opponents:** read from the rendered dive page (its 78 GL
  opponents, per-mode opponent IVs), so the lab evaluates exactly what the
  page publishes.
- **Production-path proof:** the lab re-sims the plain PvPoke (`engine`)
  variant too and `summarize` aborts unless it equals the page tensor
  integer-exactly on every simmed cell.
- **Strict bar:** for every start scenario, in every (opponent-IV mode x
  bait) slice, the strat must be `>= 0` on BOTH mean rating delta AND net
  win flips vs plain PvPoke. No negative cells ship.
- **Resolution:** screen at a stride coprime with 16 (13) so the stamina
  axis does not alias; certify at stride 1 (all 4096 spreads) before any
  engine change.
- **Instruments:** `scripts/statfx_lab.py` -- `oracle` (hindsight ceiling
  at one spread), `rules` (variant grid, incremental `.npz` per task under
  `userdata/statfx_lab/`), `summarize` (strict-bar table). Direct
  `simulate()` calls; the sweep cache is never touched.

## Phases

1. **Sableye / Shadow Sableye, Drain Punch + Foul Play (now).** Screen the
   variant grid at stride 13, assemble a per-start sheet from the rows
   that pass, certify it at stride 1. Then the other Drain Punch pairings
   on the two pages (Power Gem, Shadow Sneak, Dazzling Gleam), which have
   unequal energy and so test the "affordable alternative" restriction.
2. **Generalize to the class.** Run the certified rule vocabulary (not the
   Sableye sheet values) over every class page; per-page sheets are
   allowed, but a rule that only works on one species is a smell to
   report, not a feature. Add the hold-energy timing layer if the oracle
   shows the identity-only ceiling leaves most of the value on the table.
3. **Self-debuffers.** Separate rule family; must be reconciled with the
   existing self-debuff timing deviation.
4. **Ship.** Engine change behind the PoGoDives marker, a fully-scoped
   `migrate_cache.py` predicate (pogodives-tier columns of class focals),
   rebake of the affected pages, and the pre-dive checklist
   (`docs/predive_checklist.md`) before the bake. **Page copy (Michael, 2026-09-23;
   wording approved the same day):** every page that uses the strat says so
   next to the strategy toggle: "When we expect the opponent to shield, we
   throw [Drain Punch] into the shield so its [+1 Defense] lands for free.
   This is the [PoGoDives strategy]; you can switch to the PvPoke strategy
   with the toggle." The bracketed move and effect are generated from the
   rule and the page's moveset, and the link points at the strategy article.
   Never hand-written per page. Avoid the word "bait": at equal energy
   (Drain Punch vs Foul Play) neither move is the cheap one.

## Phase 1 results so far (2026-09-22, stride 13 = 316 of 4096 spreads)

Both Sableye pages with Drain Punch + Foul Play (78 opponents, 9 start
scenarios, {pvpoke, rank1} opponent IVs x {bait, nobait}). Cell = WORST of
the four slices: mean rating delta / net win flips vs plain PvPoke; `*` =
strict bar met in all four. The `engine` variant equalled the page tensor
on every simmed cell in every run.

| rule (Shadow Sableye) | 0v0        | 0v1        | 0v2       | 1v0         | 1v1          | 1v2         | 2v0      | 2v1         | 2v2         |
| --------------------- | ---------- | ---------- | --------- | ----------- | ------------ | ----------- | -------- | ----------- | ----------- |
| shields               | 0/0*       | +23.6/-159 | +3.3/-159 | 0/0*        | +21.2/+2911* | +15.4/+338* | 0/0*     | +12.8/+294* | +11.1/+814* |
| shields_pred          | 0/0*       | +26.6/0*   | +6.3/0*   | 0/0*        | +22.8/+2911* | +16.9/+338* | 0/0*     | +13.0/+294* | +11.2/+814* |
| shields_pred+early    | +1.4/+520* | +23.2/-159 | +3.3/-159 | -30.5/-1184 | +19.3/+2685* | +15.2/+345* | -7.7/-26 | +12.3/+147* | +10.4/+771* |

| rule (Sableye)     | 0v0         | 0v1         | 0v2      | 1v0       | 1v1          | 1v2         | 2v0       | 2v1         | 2v2          |
| ------------------ | ----------- | ----------- | -------- | --------- | ------------ | ----------- | --------- | ----------- | ------------ |
| shields            | 0/0*        | +36.8/+739* | +15.3/0* | 0/0*      | +48.7/+5401* | +36.5/+557* | 0/0*      | +23.3/+667* | +28.3/+2927* |
| shields_pred       | 0/0*        | +38.3/+739* | +16.7/0* | 0/0*      | +47.6/+5331* | +36.0/+557* | 0/0*      | +23.4/+667* | +28.4/+2927* |
| shields_pred+early | -14.0/-1736 | +38.5/+843* | +16.3/0* | -30.8/-58 | +45.9/+5273* | +36.1/+557* | -12.9/-84 | +22.9/+688* | +27.3/+2885* |

- **`shields`** (Drain Punch whenever the opponent has a shield up and Foul
  Play would not KO) fails on Shadow Sableye at 0v1/0v2, and every lost
  win is ONE opponent: Aegislash (Shield), which declines to shield hits
  under half its HP. The rule swapped a landing Foul Play (52) for a
  landing Drain Punch (11).
- **`shields_pred`** (the same, but only when the opponent's shield policy
  would shield the Drain Punch) passes all nine scenarios on both pages
  with one uniform rule. Scenarios where the opponent starts with no
  shields are exactly zero: the rule never fires there.
- **`early`** (buff while the stage is still 0) is the only thing that adds
  value at 0v0, and only on Shadow Sableye; it costs heavily whenever we
  hold shields and the opponent does not. Not adopted.
- **Modeling assumption to keep visible:** `shields_pred` asks PvPoke's
  shield policy, i.e. it assumes a PvPoke-like shielder. Real players who
  shield differently are not modelled; `shields` is the policy-free
  version, and it is within a few rating points of `shields_pred`
  everywhere except against Aegislash-like shield logic.

**Certified at stride 1 (all 4096 spreads, 2026-09-22):** `shields_pred`
meets the strict bar in all 9 start scenarios x 4 slices on both pages;
`engine` equalled the page tensor on every cell.

| page           | worst-slice mean / net flips, per start (0v0 .. 2v2)                                  | wins gained / lost | cells changed |
| -------------- | ------------------------------------------------------------------------------------- | ------------------ | ------------- |
| Shadow Sableye | 0/0, +26.7/+1, +6.3/0, 0/0, +22.8/+37760, +16.9/+4404, 0/0, +13.0/+3812, +11.2/+10564 | 544,058 / 6,631    | 24.3%         |
| Sableye        | 0/0, +38.4/+9519, +16.7/0, 0/0, +47.5/+69118, +36.0/+7275, 0/0, +23.3/+8618, +28.3/+38078 | 807,082 / 4,844 | 31.5%         |

Instrument outputs: `userdata/statfx_lab/{shadow,plain}_sableye_dpfp_pred_s1/`.

**Other Drain Punch pairings (phase 1b, stride 13, 2026-09-23):**
`shields_pred` meets the strict bar in all 9 scenarios x 4 slices on all
six: Drain Punch + {Power Gem, Dazzling Gleam, Shadow Sneak} on both
Sableye pages. Worst-slice means where it fires: Sableye +2.5 to +37.7,
Shadow Sableye +1.5 to +16.7. The unequal energy (Drain Punch 40 vs 50-55)
does not break the affordable-swap restriction. The policy-free `shields`
fails once (Sableye DP + Shadow Sneak, 0v1/0v2, net -53/-73), the same
Aegislash-style miss as before.

**Class sweep (phase 2 screen, stride 29 = 142 of 4096 spreads, 2026-09-23):**
the certified `shields_pred` rule, unchanged, on every other rendered
moveset page whose pair is one helpful guaranteed-effect move + one plain
move: 165 pages across 58 dives (plus the 6 Drain Punch pairings above).
Grouped by the effect move's energy relative to the other move:

| effect move vs other | pages | pass all 9 x 4 | fail | notes                                                   |
| -------------------- | ----- | -------------- | ---- | ------------------------------------------------------- |
| equal energy         | 22    | 22             | 0    |                                                         |
| cheaper              | 90    | 83             | 7    | all 7 tiny: worst mean >= -2.2, worst net >= -86        |
| pricier              | 59    | 10             | 48   | Skull Bash (+35) worst: Snorlax GL 2v1 -118 mean        |

Mechanism: throwing the effect move into a shield is free only when it
costs no more than the move it replaces. A pricier effect move spends the
extra energy on a throw that is blocked anyway. Next rule candidate:
`shields_pred` gated on `E.energy <= O.energy` (checked at runtime from move
data, still species-free); the 7 small cheaper-move failures need a look
before certification. Largest gains (worst-slice mean in the best
scenario): Bubble Beam (Jellicent UL +129), Icy Wind (Seismitoad UL +123),
Chilling Water (Florges UL +107, Alolan Ninetales UL +106), Rock Tomb
(Cradily GL +94), Drum Beating (Rillaboom UL +93).

**Baseline caveat:** on 25 of the 165 pages the lab's plain-PvPoke re-sim
did NOT reproduce the published tensor (1-92 cells per page, ~0.01-0.1%);
those pages are scored against the re-sim instead (`summarize --baseline
engine`), which is the right comparison for the strat question. The
mismatch itself is a dive-integrity finding tracked in TODO.md.

**Refined rule v2 (2026-09-23/24).** Three background diagnoses of the 7
small cheaper-effect-move failures found three swap-VETOES (each only
removes swaps) plus three genuine edge costs:

| veto | condition to KEEP the swap                                        | motivating case                                   |
| ---- | ----------------------------------------------------------------- | ------------------------------------------------- |
| gate | effect move costs <= the move it replaces                         | the class sweep (10/59 pricier pages pass)        |
| A    | opponent is also predicted to shield the move we replace          | Tinkaton UL vs Shadow Talonflame                  |
| B    | the E-shield prediction survives the opponent's same-turn effects | Tinkaton UL vs Shadow Cradily / Toucannon         |
| G1   | the swap does not leave a spare immediately-affordable throw      | Shadow Talonflame UL Flame Charge vs Ninetales    |

Edge costs with no clean species-free fix (the PvPoke AI reacts better to
the changed state many turns later): Sand Tomb vs Walrein / Shadow
Corviknight (the extra debuff stops the AI dying with unspent energy),
Skeledirge vs Deoxys-Defense (spare energy drifts 17 turns), Tinkaton UL
0v2 vs Dusknoir. Two agents independently found a rollout veto (sim the
rest of the battle both ways, keep the swap only if not worse) fixes all of
them; NOT adopted -- it is search, not a statable rule, and it wins by
exploiting PvPoke-AI quirks, so it would fail the shield-fragility stress.

**v2 screen, stride 13, 114 pages** (effect move <= other move, incl. both
Sableye DP+FP pages): v2 passes the strict bar on 108/114 (gated rule
106/114; v2 fixed 2, broke 0). Mean rating gain over all cells +11.3 (gated
+11.5). Still failing: the 3 Sand Tomb pages, Skeledirge 0v2 (net -185,
mean +0.1), Tinkaton UL 0v2 (-1.1), and Rillaboom UL m1 2v1 (net -1, mean
0.0, new at stride 13). Four more pages (3 Shadow Annihilape, Zygarde UL
m1) failed the tensor check at stride 13 -- the signature-dedup bug -- and
are scored against the re-sim.

**Ablation (Alolan Ninetales UL m3, the largest v2 cost, -5.4/cell):** G1 is
the ENTIRE cost; removing A or B changes nothing there. Candidate G1b
(apply G1 only when the swap burns the opponent's LAST shield) recovers the
gated gains wherever the opponent keeps a spare shield (0v2/1v2/2v2) and
still fixes Shadow Talonflame, but not 0v1/1v1/2v1. Next: re-screen with
G1b before adopting it.

## Fragility and shield prediction

The certified rule fires on "the opponent would shield this", answered by
PvPoke's shield policy. Its gain is paid for by that prediction: if the
opponent does NOT shield, we traded the bigger hit for the smaller one.
Measured by the lab's `--opp-shield {never,always}` stress mode, with the
Cramorant strat run through the same stress for comparison. Stride 13,
worst of the 4 slices, mean rating delta vs plain PvPoke re-simmed against
the SAME shielder (scenarios where a strat never fires are omitted):

| strat vs opponent that ...     | 0v1   | 0v2   | 1v1   | 1v2   | 2v1   | 2v2   |
| ------------------------------ | ----- | ----- | ----- | ----- | ----- | ----- |
| DP rule, Shadow Sableye, never | -24.4 | -29.7 | -51.5 | -63.6 | -28.1 | -36.8 |
| DP rule, Sableye, never        | -41.7 | -43.7 | -50.5 | -56.4 | -48.6 | -56.9 |
| Cramorant GL, never            | -2.7  | -0.3  | -13.6 | -11.3 | 0     | -14.6 |
| Cramorant UL, never            | +1.6  | -0.1  | +1.6  | +1.8  | 0     | -16.8 |
| DP rule, Shadow Sableye, always | +26.6 | +6.3 | +22.8 | +16.9 | +13.0 | +11.2 |
| DP rule, Sableye, always       | +38.5 | +16.7 | +48.4 | +35.9 | +24.2 | +28.4 |
| Cramorant GL, always           | +16.5 | +7.5  | +21.3 | +26.9 | 0     | +0.1  |
| Cramorant UL, always           | +15.9 | +22.0 | +44.7 | +46.7 | 0     | +26.5 |

Against an always-shielder both strats keep their value. Against a
never-shielder the Drain Punch rule loses 24-64 rating wherever it fires,
while Cramorant loses at most ~17 and stays positive in several UL
scenarios: the DP rule is markedly more dependent on shield prediction.
(0v0/1v0 carry Cramorant gains of +1 to +9 in both stresses; the DP rule
never fires there.) A longer-term consequence (Michael, 2026-09-23): a
game-theoretic (GTO) shielding model -- mixed shield/no-shield play by both
sides instead of PvPoke's deterministic rule -- would let strats like this
one be judged against opponents who adapt, not just against one fixed
shielder.

## Open questions for Michael

- Does the strat ride the existing PoGoDives tier on every class page, or
  only on pages where it certifies? (Cramorant-style: only where
  certified.)
- The oracle is per-cell hindsight: it knows the opponent's future plays.
  A player cannot, so the ceiling is an upper bound, not a target.
