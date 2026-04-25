# Dewgong moveset choice: Bl+IW vs IW+DR (2026-04-25)

## Question

Our screening picks **Ice Shard / Blizzard, Icy Wind** (avg=465 against
20-opp screening pool). PvPoke's `rankings-1500.json` `moveset` field
recommends **Ice Shard / Icy Wind, Drill Run**. The community runs
IW+DR in practice. Why the disagreement?

## Methodology

Ran rank-1 SP Dewgong (0/12/15) against the 65-entry
`gl_top50_plus_cs.txt` opponent pool with each charged-move pair, all
9 shield scenarios, PvPoke-default opponent IVs. Used the same engine
as the production deep_dive (`scripts/deep_dive.sim_score`).

Cross-checked against PvPoke's matrix UI screenshots (rank-1 IVs,
~52 opps; their record format is W-L-D out of the 52).

## Aggregate result

|                                     |             Avg score | Wins / Losses |
| ----------------------------------- | --------------------: | ------------: |
| **Ours, Bl+IW**                     |       498.2 (65 opps) |    36 W, 29 L |
| **Ours, IW+DR**                     |       494.1 (65 opps) |    28 W, 37 L |
| **Δ (Bl - DR)**                     |              **+4.1** |   **+8 wins** |
| PvPoke matrix, IW/Bl                |      502.69 (52 opps) |       31-21-0 |
| PvPoke matrix, IW/DR                |      492.52 (52 opps) |       24-28-0 |
| PvPoke matrix Δ (Bl - DR)           |            **+10.17** |   **+7 wins** |
| PvPoke ranking JSON `moveset` field | (declares IW+DR best) |           n/a |

**Three of three matrices say Bl+IW wins on aggregate.** The only
source recommending IW+DR is PvPoke's `moveset` field in
rankings-1500.json — which **disagrees with PvPoke's own matrix UI**.
PvPoke's recommended-moveset field is computed by a different
criterion than the matrix average (likely coverage, breadth, or
weighted by opponent meta-frequency / historical usage).

## Per-opponent agreement

PvPoke's "Differences" panel for IW/DR vs IW/Bl:

* **Bl gains** (8): Clefable, Clodsire, Corsola (G), Feraligatr (S),
  Politoed (S), Quagsire, Stunfisk (G), Wigglytuff
* **DR gains** (1): Sableye (S)
* Net: +7 W/L flips for Bl

Our sim's win-flips (where Bl wins, DR doesn't, or vice versa):

* **Bl wins** (8): Quagsire, Azumarill, Talonflame, Dondozo,
  Oinkologne (F), Corsola (G), Talonflame (S), Quagsire (S)
* **DR wins** (0): none
* Net: +8 W/L flips for Bl

**Direction agrees** (~+7-8 flips for Bl in both). **Specific
opponents diverge** — overlap with PvPoke's diff list is only 2 of 8
(Quagsire, Corsola Galarian).

Three notable per-opponent divergences with PvPoke matrix:

| Opponent   | PvPoke IW/DR | PvPoke IW/Bl | Ours IW+DR | Ours Bl+IW |
| ---------- | :----------: | :----------: | :--------: | :--------: |
| Wigglytuff |  473 (loss)  |  636 (win)   | 526 (win)  | 613 (win)  |
| Clefable   |    (loss)    |    (win)     | 504 (win)  | 549 (win)  |
| Talonflame |  540 (tie)   |  540 (tie)   | 468 (loss) | 537 (win)  |

In Wigglytuff and Clefable, PvPoke calls DR a loss while we call it a
win. In Talonflame, PvPoke ties them while we have Bl winning by 69.
**Our sim is more lenient toward DR than PvPoke's matrix.** Same
direction at aggregate, narrower per-opponent magnitude — likely a
charged-move-availability / energy-curve divergence worth a
post-ship trace, not a ship-blocker.

## DR's typed-coverage advantage

Our pool-wide top divergences where DR scores meaningfully higher
than Bl (sorted by abs Δ):

| Opponent           | Type(s)      | Bl+IW | IW+DR | Δ(Bl-DR) |
| ------------------ | ------------ | ----: | ----: | -------: |
| Empoleon (Shadow)  | Water/Steel  |   267 |   433 |     -166 |
| Empoleon           | Water/Steel  |   300 |   438 |     -138 |
| Lapras (Shadow)    | Water/Ice    |   236 |   367 |     -130 |
| Tinkaton           | Steel/Fairy  |   372 |   481 |     -109 |
| Sealeo             | Ice/Water    |   370 |   464 |      -94 |
| Aegislash (Shield) | Steel/Ghost  |   502 |   594 |      -91 |
| Sealeo (Shadow)    | Ice/Water    |   344 |   424 |      -80 |
| Drapion (Shadow)   | Poison/Dark  |   554 |   624 |      -70 |
| Lapras             | Water/Ice    |   288 |   356 |      -68 |
| Steelix            | Steel/Ground |   353 |   407 |      -55 |

Pattern: DR shines vs **Steel-types** (Drill Run is SE for Steel,
1.6×) and vs **Ice/Water-resists-Ice opponents** (Lapras, Sealeo)
where Blizzard's Ice STAB does NVE damage. Bl wins broadly across
neutral matchups by raw power; DR has decisive Steel coverage.

## Practical interpretation

Why community runs IW+DR despite both matrices saying Bl wins:

1. PvPoke's recommended-moveset field anchors meta consensus, not the
   matrix output.
2. Steel-type coverage is a "feels safe" advantage — DR decisively
   handles Tinkaton, Empoleon, Steelix, etc. where Bl is mediocre.
   In tournament play, decisive matchups outweigh marginal ones.
3. Blizzard's 75-energy cost is hard to set up against fast-energy
   openers; Icy Wind+Drill Run cycle (45e + 50e) is more reliable
   throw-twice. Score-average underweights this risk.

## Recommendation for ship

Ship our screening winner (Bl+IW) as the headline moveset. Add a
short transparent note in the article body acknowledging that
PvPoke's recommended-moveset field disagrees, that the community
runs IW+DR for Steel coverage, and that our matrix and PvPoke's
own matrix both put Bl ahead on aggregate. The reader can pick.

The chain is currently re-diving Dewgong with `top_movesets=3`, so
the published page will surface the top 3 screened movesets (likely
including Aqua Jet variants too) plus the IW+DR auto reference.
