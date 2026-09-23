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
   (`docs/predive_checklist.md`) before the bake.

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

## Open questions for Michael

- Does the strat ride the existing PoGoDives tier on every class page, or
  only on pages where it certifies? (Cramorant-style: only where
  certified.)
- The oracle is per-cell hindsight: it knows the opponent's future plays.
  A player cannot, so the ceiling is an upper bound, not a target.
