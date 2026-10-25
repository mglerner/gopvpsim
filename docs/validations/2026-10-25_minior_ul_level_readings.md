# Minior shell level: in-game readings (2026-10-25)

Michael read the CP shown in the battle UI for his own Miniors in friend /
Training battles: the Core's CP at the opening bell, then the CP it drops to
when the Meteor shell takes over. The shell's CP pins its battle level exactly
(neighbouring half-levels differ by 10-20 CP; CP formula with PvPoke's
gamemaster base stats, Core 218/131/155, Meteor 116/194/155). No XL candy
or power-ups were spent: any Minior can enter an Ultra League (UL) battle,
and any Core at 1500 CP or below can enter a Great League (GL) one.

## Readings

| Minior (IVs, Core level) | Core CP | League | Shell CP | Shell level | Boost | PvPoke formula | Community cap rule |
| ------------------------ | ------- | ------ | -------- | ----------- | ----- | -------------- | ------------------ |
| 12/15/7, L15             | 946     | Great  | 1113     | 26.5        | +11.5 | 29.0 (1218)    | 41.5 (1499)        |
| 0/9/15, L25              | 1500    | Great  | 1494     | 48.5        | +23.5 | 48.0 (1485)    | 48.5 (1494)        |
| 1/4/3, L26               | 1484    | Great  | 1496     | 52.0        | +26.0 | 49.5 (1452)    | 52.0 (1496)        |
| 12/15/7, L15             | 946     | Ultra  | 1029     | 24.5        | +9.5  | 22.5 (945)     | n/a                |
| 0/9/15, L25              | 1500    | Ultra  | 1297     | 37.5        | +12.5 | 37.5 (1297)    | n/a                |
| 1/4/3, L26               | 1484    | Ultra  | 978      | 26.5        | +0.5  | 39.0 (1274)    | n/a                |
| 15/10/11, L26            | 1653    | Ultra  | 1553     | 42.5        | +16.5 | 39.0 (1484)    | n/a                |
| 14/10/14, L28            | 1789    | Ultra  | 1624     | 46.0        | +18.0 | 41.5 (1536)    | n/a                |
| 15/9/8, L30              | 1884    | Ultra  | 1632     | 47.5        | +17.5 | 44.5 (1574)    | n/a                |
| 15/13/13, L35            | 2101    | Ultra  | 1829     | 55.0        | +20.0 | 52.0 (1766)    | n/a                |

Every shell CP matches one half-level exactly (the neighbouring half-levels
are 9-21 CP away), so the level column is pinned, not fitted. The second
batch (rows 1, 3, 6-7, 9-10) was read on 2026-10-25 after the first four.
The 1/4/3 Ultra reading was re-read in a second Ultra battle against a
different opponent (Spark) and gave 978 again, so it is real and does not
depend on the opponent.

## What the readings say

- **The shell level ceiling is 55, not 52.** The 15/13/13 Core at L35 drops
  to 1829 in Ultra, which is the Meteor form at exactly L55 (L54.5 would be
  1818). PvPoke's `cpms` table runs to 55; our `pokemon.CPM` stops at 52.
  This settles the ceiling half of the open question in PvPoke's favour.
- **GL**: the cap rule is exact for Cores near the cap (1500 -> 48.5,
  1484 -> 52.0, so the shell does sit above L50 and above L51), but it is
  NOT the general rule: the L15 Core at 946 drops to 1113 (L26.5), not to
  1499 (L41.5). PvPoke's formula (L29, 1218) misses that one too.
- **UL**: PvPoke's formula is exact at Core L25 and low everywhere else:
  +2.0 (L15), +3.5 (L26, 15/10/11), +4.5 (L28), +3.0 (L30), +3.0 (L35,
  reading at the ceiling). The boost (+9.5, +12.5, +16.5, +18.0, +17.5,
  +20.0 for L15, L25, L26, L28, L30, L35) is not a function of Core level
  alone: the two L25/L26 Cores differ by four levels of boost.
- **The 1/4/3 L26 Ultra reading (978 = L26.5, boost +0.5)** is the outlier,
  and it reproduced against a second opponent. The same Minior reaches L52
  in Great, and the other L26 Core (15/10/11) reaches L42.5 in Ultra. +0.5
  is exactly the go-iv Master League rule (Core + 0.5), which reads like a
  boost condition that FAILED for this Minior rather than a formula giving
  a small number. What is distinctive about it: the lowest defense IV (4;
  every other reading has >= 9) and the lowest stamina IV (3; others >= 7).
  Attack IV alone is not it (0/9/15 got +12.5).
- Closed-form rules tried against the UL points (with and without the
  outlier), none fits: match the Core's CP, stat product with Meteor or
  Core HP, attack x defense, attack + defense, PvPoke's GL formula, a
  constant level boost, a constant CPM ratio, a constant fraction of the
  league cap. Shell/Core ratios per reading (attack 0.62-0.71, defense
  1.63-1.83, CP 0.87-1.09) are not constant either. The rule is still open.
- **Why CP can go up or down**: the shell has about two thirds of the
  Core's attack x sqrt(defense) term, so at equal level its CP is lower; the
  game raises the shell's level to compensate. In GL the raise goes right
  up to the cap for Cores near it. In UL the raise is smaller and does not
  reach the cap, so whether the displayed CP rises or falls depends on
  whether CPM(shell)^2 / CPM(core)^2 beats about 1.5.
- **Different shell stats in UL and GL for the same Minior is expected**:
  the shell level is set per league (0/9/15 reads 48.5 in GL and 37.5 in
  UL; 12/15/7 reads 26.5 and 24.5). What is NOT expected is the 1/4/3 gap
  (52.0 vs 26.5), which is why that reading is flagged.

## Consequences

- The UL Minior (Core) dive (`minior-core-ultra-league`, rendered
  2026-10-25) uses PvPoke's rule, under which every spread's shell sits at
  the top of the level table (ours 52.0, PvPoke's 55.0; that ceiling gap
  alone moves 43% of a 2,880-cell UL grid and flips 59 of 500 winners, see
  CHANGELOG 2026-10-25). The L35 reading confirms 55 is the in-game
  ceiling, so the +6 CPM entries are owed regardless of the rule. The rule
  below the ceiling is still unknown, and PvPoke's formula reads 3-4.5
  levels low at Core L26-L35, so the page's shell phase stays UNCONFIRMED;
  the callout says so. The Core-only
  dive has no shell phase and is PvPoke-exact (48/48 live, 12/12 PvPoke).
- Our GL dives sweep Cores at L22.5-27, at or near the cap, where the cap
  rule and PvPoke's formula agree to within a half-level; the 1/15/13 and
  5/14/15 cases were PvPoke-exact in `tests/test_minior.py`. The two
  near-cap GL readings (1500 -> 48.5, 1484 -> 52.0; formula 48.0 / 49.5)
  are the known half-level-or-so discrepancy noted in DEVELOPER_NOTES; the
  946 -> L26.5 reading is far from any spread the GL dives use.

## Further readings still wanted (all free)

- Ultra, same-level pairs, now the decisive readings: 4/0/8 vs 13/10/7
  (L22, Core CP 1273 / 1370; Core+0.5 would read 856 / 941); 1/1/0 vs
  13/5/3 (L8, 441 / 476; Core+0.5 = 305 / 343); 10/2/1 vs 6/3/8 (L29,
  1699 / 1713; Core+0.5 = 1159 / 1150); 8/2/6 L1 CP 29 (the floor;
  Core+0.5 = 40). If the low-defense /
  low-stamina partners come back at Core+0.5 while the others get large
  boosts, the condition is on those IVs.
- Master, any Minior, to pin the Core+0.5 baseline (15/10/11 L26 -> 1140;
  15/13/13 L35 -> 1427; 0/9/15 L25 -> 980).
- Great, away from the cap: 1/1/0 L8 CP 441; 13/10/7 L22 CP 1370; 8/2/6
  L1 CP 29. The 12/15/7 L15 reading (946 -> 1113) already shows the cap
  rule is not general in GL.

Scratch: the hypothesis scans and the per-Minior prediction tables were run
in-session (2026-10-25); the numbers above are from those runs. The two
Poke Genie rows stored as Meteor (7/1/7 L16 CP 624, 11/6/2 L4 CP 147) are
scan misreads (no Core IV/level reproduces their CP and HP together), so
there is no stored-Meteor reading to take.
