# Cramorant strict-bar campaign (overnight 2026-08-25/26)

**Directive (Michael, 2026-08-25 ~20:50):** by morning, the PoGoDives
strat must sit "somewhere between net zero and big positive for every
single scenario" — clarified mid-campaign to the STRICT bar: for every
start scenario, in every (league x opp-IV mode x bait mode) slice,
the strat must be `>= 0` on BOTH mean rating delta AND net win flips
vs plain PvPoke. No negative cells ship.

**Result: the bar is met.** The uniform rule (dive gate 3.0 + adaptive
tank lead40 + 2-0 exemption) was replaced by a per-START-scenario
strategy sheet (`_POGODIVES_SHEET` in `battle.py`, commit 8fc5764).
Verified on the production score tensors at 512-IV stride before the
rebake; every changed cell passes with positive value, and the four
untouched scenarios are byte-identical to the previously baked
pogodives tensors.

## Where the old rule failed (full-tensor, 4096 IVs x pool)

| cell                  | mean rating | net flips | verdict          |
| --------------------- | ----------- | --------- | ---------------- |
| GL 0v0 (both baits)   | -2.00       | +10,634   | fail (rating)    |
| GL 1v0 (pvpoke IVs)   | -15.79      | +271      | fail (bad trade) |
| GL 1v0 (rank1 IVs)    | -13.23      | -1,971    | fail (both)      |
| GL 2v1 (worst mode)   | -32.16      | -2,925    | fail (both)      |
| GL 2v2 (pvpoke bait)  | -1.72       | +14,652   | fail (rating)    |
| UL 2v1 (all modes)    | -8.7..-12.9 | +11,166.. | fail (rating)    |
| UL 0v1 (rank1 nobait) | +23.66      | -526      | fail (flips)     |

## The sheet (per start scenario: my shields v opponent's)

| start | rule                                                                                | stride-8 outcome (worst / best slice)                                     |
| ----- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| 0v0   | gate iff CMP won AND opp fast DPT < 0.022/maxHP                                     | +0.68..+3.07 mR, +888..+1,294 flips (GL); +0.77..+1.26, +113..+165 (UL)   |
| 0v1   | gate iff CMP won                                                                    | +13.4..+19.7 mR, ~+500 flips (GL); +8.8..+9.7 (UL)                        |
| 0v2   | shipped rule (unchanged)                                                            | already passed                                                            |
| 1v0   | gate off, tank lead-rule at aggressive 2.0                                          | +0.89..+1.17 (GL); +1.50..+1.71, +88..+99 flips (UL)                      |
| 1v1   | shipped rule (unchanged)                                                            | already passed                                                            |
| 1v2   | shipped rule (unchanged)                                                            | already passed                                                            |
| 2v0   | exempt (round-7 verdict, unchanged)                                                 | exactly 0                                                                 |
| 2v1   | exempt — see "the 2v1 hole" below                                                   | exactly 0                                                                 |
| 2v2   | gate iff CMP AND DPT AND opp cheapest charged < 55 energy; tank 'cheap' rule at 1.8 | +2.10..+4.77 mR, +791..+1,283 flips (GL); +8.2..+9.9, +1,282..+1,547 (UL) |

CMP = we win charge-move priority (attacker.atk >= defender.atk),
evaluated per-IV at battle time. The 'cheap' tank rule tanks only
hits `<= 15%` of max HP (the Gulp Missile's worth); bigger hits get
PvPoke's 2.2 threshold.

## Mechanisms (fight-trace verified, agent report `mech_2v1_0v0.md`)

1. **The retuned gate's active set is one band**: it changes behavior
   only when `dpe(Fly)/dpe(Dive)` lies in (1.5, 3.0) — 27/78 GL pool
   opponents: 23 Dive-resisters + 4 Fighting types. The missile is
   water-typed, so the retune's own targets resist its payoff.
2. **The gate needs CMP won**: a forced early Dive that trades with
   the opponent's simultaneous charged move loses the tempo it buys.
   This is also why shadow variants flip sign (shadow atk bonus flips
   CMP) and why per-IV deltas are bimodal at atk breakpoints.
3. **The gate needs the opponent able to shield**: it trades a
   blankable Fly (1 dmg through a shield) for an unshieldable
   missile. At opponent-shields-0 starts that argument evaporates —
   hence the extra DPT survival condition at 0v0.
4. **Tanking's worth is bounded by the missile's ~15%-of-bar value**:
   tank cost is `500*dmg/our_maxHP` vs gain `~500*0.15`. Hits above
   ~15% of max HP are never worth eating when shield-ahead.

## Sheet v2 amendments (later the same night)

After the v1 freeze, the parallel discovery campaign closed the 2v1
hole and batch-10 measurements upgraded 2v2:

- **2v1 = the ready-nuke gate** (gate-only; tank plain PvPoke): fire
  the 3.0 gate iff CMP won AND the opponent's cheapest charged move
  costs >= 40 energy AND they hold that energy RIGHT NOW
  (`defender.energy >= cheapest` -- live-state, same class as the
  lead rule's hp read) AND their fast DPT < 0.0155 (tighter than the
  0v0 row's 0.022; plateau 0.0141-0.0168). Full-4096-IV verified:
  worst slice +2,220 net / +1.17 mean; total +22,840 net win-cells
  vs the v1 exemption's zero. CAVEAT (disclosed): in Great the rule
  fires materially against ONE opponent (Jellicent); the constants
  are meta-fitted and go on the rebalance re-verify list.
- **2v2 cheap_frac 0.15 -> 0.30** (batch-10, stride-13): flips up
  ~15-35% in every slice (GL +860..+1042, UL +934..+1259) at ~1 point
  of UL rating; all slices still pass.
- **Measured and REJECTED**: the 'draw' gate for 0v1 (zeroes GL 0v1
  entirely, worse than 'cmp' in UL) and cheap-cap tanking at 1v0
  (frac 0.30 goes rating-negative in GL). Both were mechanism-
  plausible candidates from the 1v0/0v1 trace agent; measurement
  overruled them. The independent stride-13 all-72-cell audit by that
  agent confirmed the v1 sheet passes everywhere before v2 landed.

## The 2v1 hole (CLOSED by v2 -- history)

No rule found tonight beats plain PvPoke at 2v1 in BOTH leagues:
Great wants the gate off (every gated variant bleeds -3.5..-32
rating), Ultra wants it on (+1.3..+4.8 with +46..+133 flips at
stride 64). The same species flips sign between leagues (Lapras:
GL -207 mean, UL +147), so the discriminator is pair-dynamic (level-
dependent breakpoint arithmetic), not static typing/stats. The
per-opponent oracle says ~+7k (GL) and ~+8-19k (UL) win-cells remain
on the table in this cell. Exemption = exactly 0 everywhere, which
satisfies the bar; a discovery agent's findings are in
`discovery_2v1.md` (scratchpad) for the next campaign.

Cost of the sheet vs the old rule, for honesty: the old rule's UL 2v1
was +11.4k flips (at -11 rating); the exemption gives those up until
the 2v1 discriminator is found. 1v0's UL value also shrank (+88..+99
flips vs the old +203 peak) to buy GL's rating fix.

## Overfit disclosures (flagged for the skeptic pass + rebalance)

- `0.022` (DPT gate) and `55` (cheap-energy gate) are fitted
  thresholds; the 55-energy condition exists to exclude exactly the
  Azumarill 2v2 drain (-232 mean at stride 64). Mechanism framing
  ("don't force resisted tempo Dives into heavy-nuke shield games")
  is plausible but post-hoc. Both must be re-verified at the
  post-Worlds rebalance (tests/test_rebalance_tripwire.py fires the
  checklist; the sheet's constants are all in battle.py).
- Sampling: rules were screened at 64-IV stride and confirmed at
  512-IV stride on the full opponent pools; the final bake re-runs
  everything at 4096 IVs (this doc is updated with any drift).

## Process notes

Instruments: `mini_sweep.py` (scratchpad) — targeted tensor-slice
re-sims through the production construction path, verified
integer-exact against the baked tensors at shipped knobs before use.
~10 candidate batches of 4-24 slices each, minutes apiece — three
orders of magnitude cheaper than dive rebakes. Adversarial
verification: an independent agent re-derived the full cell map and
live-reproduced 37/37 tensor cells integer-exactly; two mechanism
agents traced the failing fights. Cache: migration predicate
`pogodives_sheet_20260826` blessed 148,856 columns; 4,520
pogodives-tier columns re-simmed in the rebake.
