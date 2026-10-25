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
| 0/9/15, L25              | 1500    | Great  | 1494     | 48.5        | +23.5 | 48.0 (1485)    | 48.5 (1494)        |
| 0/9/15, L25              | 1500    | Ultra  | 1297     | 37.5        | +12.5 | 37.5 (1297)    | n/a                |
| 12/15/7, L15             | 946     | Ultra  | 1029     | 24.5        | +9.5  | 22.5 (945)     | n/a                |
| 14/10/14, L28            | 1789    | Ultra  | 1624     | 46.0        | +18.0 | 41.5 (1536)    | n/a                |

"PvPoke formula" is `formchange._minior_meteor_level` as ported (GL start
`floor((47L/25 + 1) * 2) / 2`, UL start `floor((73L/50 + 26/25) * 2) / 2`,
then the whole-level walk down under the cap). "Community cap rule" is the
go-iv model for GL: the highest half-level whose Meteor CP is under 1500
(jgmcelwain/go-iv#48). The cap rule has no UL answer because the shell can
never reach 2500 CP.

## What the readings say

- **GL**: the cap rule is exact; PvPoke's formula is one half-level low for
  a Core sitting on 1500 (the go-iv "+0.5 when Core is on the cap" case).
- **UL**: PvPoke's formula is exact at Core L25 and misses by +2.0 and +4.5
  levels at L15 and L28. The level boost (+9.5, +12.5, +18.0 for L15, L25,
  L28) is not linear in Core level, so the rule involves something beyond
  the level (IVs, CP, or stats).
- Closed-form rules tried against the three UL points, none fits all three:
  match the Core's CP (gives 52+), stat product with Meteor HP (34.5),
  stat product with Core HP (39), attack x defense (39), attack + defense
  (40), PvPoke's GL formula (53.5), "+18 levels", "CPM x 1.16". The L25
  reading is on PvPoke's line; the other two sit above it by amounts that
  grow with the attack IV (0, 12, 14), which is only a hint.
- **Why CP can go up or down**: the shell has about two thirds of the
  Core's attack x sqrt(defense) term, so at equal level its CP is lower; the
  game raises the shell's level to compensate. In GL the raise goes right
  up to the cap (hence 1500 -> 1494). In UL the raise is smaller and does
  not reach the cap, so whether the displayed CP rises or falls depends on
  whether CPM(shell)^2 / CPM(core)^2 beats about 1.5.

## Consequences

- The UL Minior (Core) dive (`minior-core-ultra-league`, rendered
  2026-10-25) uses PvPoke's rule, under which every spread's shell sits at
  the top of the level table (ours 52.0, PvPoke's 55.0; that ceiling gap
  alone moves 43% of a 2,880-cell UL grid and flips 59 of 500 winners, see
  CHANGELOG 2026-10-25). The in-game rule is unknown above Core L28, so the
  page's shell phase is UNCONFIRMED; the callout says so. The Core-only
  dive has no shell phase and is PvPoke-exact (48/48 live, 12/12 PvPoke).
- Our GL dives sweep Cores at L22.5-27, at or near the cap, where the cap
  rule and PvPoke's formula agree to within a half-level; the 1/15/13 and
  5/14/15 cases were PvPoke-exact in `tests/test_minior.py`. The one GL
  reading here (Core on 1500 -> 48.5, formula 48.0) is the known
  half-level discrepancy already noted in DEVELOPER_NOTES.

## Proposed further readings (all free)

From Michael's Poke Genie export (74 Miniors, 72 stored as Core, 2 as
Meteor), chosen so each group answers one question; predictions are the
shell CP after the drop under PvPoke's formula (UL) and under the cap rule
vs the formula (GL):

- UL, higher Core levels: #88 15/13/13 L35 CP 2101 (formula 1766, L52);
  #37 15/9/8 L30 CP 1884 (1574, L44.5).
- UL, same-level pairs with opposite attack IVs: #106 10/2/1 vs #110 6/3/8
  (L29); #109 15/10/11 vs #33 1/4/3 (L26); #7 13/10/7 vs #45 4/0/8 (L22);
  #24 13/5/3 vs #101 1/1/0 (L8); #22 8/2/6 L1 CP 29 (floor).
- GL, cap rule vs formula away from the cap: #3 12/15/7 L15 946 (1499 vs
  1218); #4 0/9/15 L9 536 (1494 vs 672); #33 1/4/3 L26 1484 (1478 at L51 vs
  1452); #101 1/1/0 L8 441 (1453 at L51 vs 580); #7 (1492 vs 1483); #22
  (1491 vs 81). Two of these test whether the shell can sit above L50.
- The two Meteor-stored Miniors (#28 7/1/7 L16 CP 624; #29 11/6/2 L4 CP
  147) exercise PvPoke's inverse path (`_minior_core_level`): predicted
  Core CP after the drop 587 / 92 in UL and 463 / 61 in GL.

Scratch: the hypothesis scan and the per-Minior prediction table were run
in-session (2026-10-25); the numbers above are from those runs.
