# Tinkaton GH Cluster Analysis & Matchup Flip Tables

**Date**: 2026-04-07
**Data source**: `tinkaton_gh_all9.html` (all 9 shield scenarios, 39 Championship Series opponents)
**Moveset**: Fairy Wind / Bulldoze + Gigaton Hammer
**Reference IV**: PvPoke default (4/15/14, Atk=106.20, Def=140.27, HP=142)
**Analysis script**: `scripts/analyze_deep_dive.py`

## 1. Per-Scenario Rank Instability

The single most striking finding is how unstable IV rankings are across scenarios.
Our overall #1 (2/13/13) is rank #2670 in the 2v0 scenario:

```
       IVs  0v0  0v1  0v2  1v0  1v1  1v2  2v0  2v1  2v2  Avg
  2/13/13      1      1      4    131    185      2   2670      7      9     1
  0/11/12      2      2      5    217    246      4   2680      3      4     2
  0/ 8/15      3      9     78    206    199      1   2654      1      1     3
  0/ 9/14     56      8      6    279    194      5   2676      2      5     4
  2/12/14     15      5      1    146     91     35   2644      4      6     5
  0/12/11      5      3     17    425    457      9   2723     13     13     6
  0/14/ 9    103     12     11    599    470     31   2733     24     22    14
```

**Pattern**: Low-attack IVs (atk ~105.5-106.0) dominate 0v0, 0v1, 0v2, 1v2, 2v1, 2v2.
But in 1v0 and especially 2v0 (shield advantage), they rank ~2600-2700 out of 4096.
High-attack IVs take over in shield-advantage scenarios because attack stat matters more
when you're shielding and the opponent isn't.

The reference's 0/14/9 (rank #14 overall) is rank #599 in 1v0, rank #470 in 1v1, and
rank #2733 in 2v0. Its high defense matters in shield-disadvantage but not shield-advantage.

**Takeaway**: No single IV spread is "best" — the optimal IV depends on the shield
scenario you expect. The average across all 9 is a reasonable compromise, but it hides
massive scenario-dependent swings.

## 2. Cluster Analysis: What Drives the Clusters?

### 0v0 (no shields): Stat product + type matchups

Top 50 cluster: atk ~106.7 avg (lower than pop avg 108.7), def ~137.8, HP ~143.
The cluster favors bulk over attack. **Galarian Stunfisk** is the #1 differentiator
(+83.5 gap) — bulk lets Tinkaton survive long enough to land Gigaton Hammers against
this tanky opponent.

The top 50 is *worse* against Jellicent (-29.0) — Jellicent punishes low-attack
spreads because you need attack to break through before it farms you down.

### 1v1 (even shields): Defense and HP both matter

Top 50 cluster: atk ~105.7, def ~140.4, HP ~143.
This scenario most rewards balanced stats. **Steelix** is the #1 differentiator (+180.8) —
the Steelix matchup is extremely sensitive to Tinkaton's bulk.

### 2v2 (both double shield): HP dominates

Top 50 cluster: atk ~105.7, def ~139.4, HP ~143.
With both sides double-shielding, battles go long and HP matters most. The cluster
shifts toward HP-heavy spreads. **Steelix** (+196.6) and **G. Stunfisk** (+181.1)
are the biggest differentiators.

The top 50 is much *worse* against Lapras (-93.1) — Lapras with double shields
can farm down low-attack Tinkaton.

### 1v2 (shield disadvantage): Bulk is everything

Top 50 cluster: atk ~105.6, def ~140.9, HP ~143.
When you have 1 shield and opponent has 2, survival is paramount. This is where
defense-heavy IVs like the reference's 0/14/9 shine.

### 2v0 (shield advantage): Attack takes over

Top 50 cluster: atk ~110.1 (!), def ~133.4, HP ~137.
Completely different regime. With 2 shields vs 0, you want maximum attack to KO
before the opponent can charge. Our balanced top picks rank ~2600-2700 here.

## 3. Matchup Flip Table: Key Results

Flips are scored vs PvPoke default IVs (4/15/14). A "gain" means the IV wins a
matchup that the reference loses (crossing the 500-point boundary).

### Our #1 overall: 2/13/13 — Gains 8, Loses 0

The cleanest flip profile of any IV spread tested:

| Scenario | Opponent            | Ref | 2/13/13 | Delta |
| -------- | ------------------- | --- | ------- | ----- |
| 2v0      | Stunfisk (Galarian) | 418 | **746** | +328  |
| 0v0      | Quagsire (Shadow)   | 403 | **623** | +220  |
| 1v2      | Togekiss            | 291 | **503** | +212  |
| 1v2      | Clefable            | 302 | **503** | +201  |
| 0v1      | Charjabug           | 392 | **535** | +143  |
| 2v1      | Stunfisk            | 491 | **584** | +93   |
| 0v0      | Corsola (Galarian)  | 453 | **503** | +50   |
| 2v1      | Corviknight         | 496 | **500** | +4    |

No lost matchups. It picks up wins against G. Stunfisk, Shadow Quagsire, Togekiss,
Clefable, Charjabug, Stunfisk, G. Corsola, and Corviknight. Many of these are
asymmetric-scenario flips that wouldn't show up in even-only analysis.

### Reference top pick: 0/14/9 — Gains 5, Loses 2

| Scenario | Opponent            | Ref     | 0/14/9  | Delta |
| -------- | ------------------- | ------- | ------- | ----- |
| 2v0      | Stunfisk (Galarian) | 418     | **744** | +326  |
| 1v2      | Clefable            | 302     | **507** | +205  |
| 0v1      | Charjabug           | 392     | **542** | +150  |
| 2v1      | Stunfisk            | 491     | **585** | +94   |
| 0v0      | Corsola (Galarian)  | 453     | **507** | +54   |
| 0v2      | **Steelix**         | **503** | 329     | -174  |
| 1v2      | **Steelix**         | **570** | 452     | -118  |

Gains 5 flips but **loses Steelix in 0v2 and 1v2**. The Steelix losses are because
0/14/9 has lower HP (141 vs 142 for the reference) — the HP tradeoff for defense
hurts in Steelix matchups where survival requires raw HP.

### Reference's other pick: 0/15/8 — Gains 6, Loses 5

Net +1. Gains G. Stunfisk, Togekiss, Clefable, Charjabug, Stunfisk, G. Corsola
but **loses 5 Steelix matchups** across different shield scenarios. Too much
defense at the cost of HP.

### Reference's "solid" pick: 2/13/5 — Gains 0, Loses 2

Net -2. This high-attack, low-HP spread loses 2 Steelix matchups and gains nothing.
The reference valued it for CMP ties (atk=106.94), but in our sim the CMP benefits
don't translate to matchup flips.

### The Steelix Pattern

**Steelix is the single most important matchup differentiator.** Nearly every IV
spread's flip profile is dominated by Steelix — it's the matchup most sensitive to
Tinkaton's stat distribution. Low-HP spreads (HP <= 140) lose 5-7 Steelix matchups.
HP >= 141 reduces this to 1-2 losses. HP >= 142 with adequate defense eliminates
Steelix losses entirely.

This explains why our average-score rankings favor HP so strongly: the Steelix matchup
spans 5+ shield scenarios and swings by 200+ points per scenario.

## 4. The GH Great Threshold Problem

The "GH Great" threshold (def >= 143.03, HP >= 138) was designed from the community
reference. But our flip analysis reveals a problem: **the low-HP GH Great spreads
(HP=138) all have net negative flip profiles**:

| IV     | Def    | HP  | Gains | Loses | Net |
| ------ | ------ | --- | ----- | ----- | --- |
| 0/12/3 | 143.04 | 138 | 0     | 2     | -2  |
| 0/14/5 | 143.04 | 138 | 2     | 5     | -3  |
| 0/14/6 | 143.04 | 138 | 2     | 5     | -3  |
| 0/15/5 | 143.73 | 138 | 2     | 5     | -3  |
| 0/15/6 | 143.73 | 138 | 2     | 5     | -3  |

These spreads meet the defense threshold but their low HP costs them 2-5 Steelix
matchups. The only GH Great spreads with positive net flips are:

| IV         | Def    | HP      | Gains | Loses | Net    |
| ---------- | ------ | ------- | ----- | ----- | ------ |
| **0/14/9** | 143.04 | **141** | 5     | 2     | **+3** |
| 0/15/8     | 143.73 | 140     | 6     | 5     | +1     |
| 0/14/8     | 143.04 | 140     | 5     | 5     | 0      |

The reference's recommendation of 0/14/9 specifically is validated — it's the best
GH Great spread by net flips. But the threshold definition itself (HP >= 138) is
too permissive. **HP >= 141 would be a better threshold** for GH Great.

## 5. Revised Recommendations

Based on both average-score and matchup-flip analysis:

### Best overall IV: 2/13/13

- Atk=105.91, Def=140.99, HP=142, SP Rank #14
- Average score: #1 (564.5)
- Net flips: +8 (gains 8, loses 0) — cleanest flip profile
- Misses GH Good threshold by 0.67 defense
- Wins CMP vs rank #1 Corviknight (105.58 < 105.91)

### Best threshold IV: 0/14/9

- Atk=105.58, Def=143.04, HP=141, SP Rank #2
- Average score: #14 (560.5)
- Net flips: +3 (gains 5, loses 2)
- Meets GH Great threshold
- The reference's recommendation is correct for threshold-optimizing players

### Best balanced IV: 0/11/12

- Atk=105.58, Def=141.00, HP=143, SP Rank #3
- Average score: #2 (563.9)
- Net flips: +7 (gains 8, loses 1)
- Good balance of average performance and flip count
- Loses only Steelix 0v2

## Appendix: Full Net Flip Summary (Top 15 by Net)

```
       IVs      Atk      Def   HP      Avg  Gains  Loses   Net        Tier
  ------------------------------------------------------------------------
   2/13/13   105.91   140.99  142    564.5      8      0    +8
   0/11/11   105.58   141.00  142    562.6      8      1    +7
   0/11/12   105.58   141.00  143    563.9      8      1    +7
   0/12/11   105.58   141.68  142    562.7      8      1    +7     GH Good
   0/ 8/15   105.58   138.96  145    563.3      7      1    +6
   0/ 9/14   105.58   139.64  144    562.9      7      1    +6
   0/ 7/15   105.58   138.28  145    561.5      6      1    +5
   2/11/14   105.91   139.64  143    562.3      5      0    +5
   2/11/15   105.91   139.64  143    562.3      5      0    +5
   2/12/14   105.91   140.31  143    562.9      5      0    +5
   1/14/13   105.23   141.66  142    556.8      6      2    +4     GH Good
   1/14/14   105.23   141.66  143    557.8      6      2    +4     GH Good
   1/15/13   105.23   142.34  142    557.3      6      2    +4     GH Good
   0/14/ 9   105.58   143.04  141    560.5      5      2    +3    GH Great
   0/14/14   104.56   141.66  143    556.2      5      3    +2     GH Good
```
