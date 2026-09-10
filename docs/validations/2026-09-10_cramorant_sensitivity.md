# Which Cramorant strat constants actually do anything?

Run before committing to a post-rebalance re-fit, to find out whether the
sheet is over-parameterised. `scripts/cramorant_sensitivity.py` perturbs each
fitted constant four ways and counts how many of the 2,394 corpus cells move
(GL 73 + UL 60 opponents x 9 shield cells x 2 bait modes).

## Result: one constant carries almost all the leverage

    constant                        shipped   max cells moved   net-W range
    _POGODIVES_TANK_AGGRESSIVE          1.4      65  (2.7%)      [-14, +6]
    _POGODIVES_TANK_CONSERVATIVE        2.2      31  (1.3%)      [ -1, +2]
    _POGODIVES_GATE_0V0_MIN_ENERGY       40      24  (1.0%)      [ -4, -2]
    _POGODIVES_DIVE_GATE_DPE            3.0      21  (0.9%)      [ -1, +0]
    _POGODIVES_GATE_MISSILE_FRAC       0.15      16  (0.7%)      [ -2, -2]
    _POGODIVES_GATE_MISSILE_FAST        4.2      12  (0.5%)      [ -2, +0]
    _POGODIVES_TANK_LEAD                0.4       9  (0.4%)      [ +0, +0]
    _POGODIVES_GATE_MIN_ENERGY           40       7  (0.3%)      [ +0, +0]
    _POGODIVES_TANK_CHEAP_FRAC         0.15       0  (0.0%)      [ +0, +0]
    _POGODIVES_GATE_DPT_MAX           0.022       0  (0.0%)      [ +0, +0]

`_POGODIVES_TANK_AGGRESSIVE` is the only constant with real leverage. Eight of
the ten move under 1.5% of cells, and two move NOTHING.

## The two zeros are DEAD CODE, not merely insensitive

Both were then confirmed structurally, not just measured:

* **`_POGODIVES_TANK_CHEAP_FRAC`** is read only under `tank_rule == 'cheap'`.
  The shipped sheet uses only `lead` and `lead_ready`. No cell can reach it.
* **`_POGODIVES_GATE_DPT_MAX`** is read as
  `entry.get('dpt_max', _POGODIVES_GATE_DPT_MAX)`. The dpt check runs only for
  gates `cmp_dpt` / `cmp_dpt_e` / `cmp_ready_dpt`; the sheet uses just
  `cmp_ready_dpt`, on exactly one cell, `(2, 1)` -- which supplies its own
  `dpt_max: 0.015`. So the global is shadowed at its only consumer.

`cmp_dpt`, `cmp_dpt_e` and the `'cheap'` tank rule are likewise unused by the
current sheet, along with the hardcoded 55-energy bound inside `cmp_dpt_e`.

## Why this matters for the re-fit

**It kills the obvious plan.** The 2026-09-10 re-verify found UL 2v1 negative,
driven entirely by Jellicent, and the natural response was "sweep
`_POGODIVES_GATE_DPT_MAX`". That would have measured nothing: the constant is
shadowed at (2,1), which is the very cell that regressed. The knob that
matters there is the SHEET's own `dpt_max: 0.015`.

So the re-fit should target:

1. the `(2, 1)` entry's own `dpt_max` (the Jellicent regression),
2. `_POGODIVES_TANK_AGGRESSIVE` and the per-cell `tank_aggr` values, which is
   where the leverage actually is,

and can leave the six low-leverage globals alone, since perturbing any of them
across a plausible range moves at most 1.3% of cells and at most 4 wins.

## Caveat

Single-constant perturbation only. It does not test interactions -- two
constants that each move little could still matter jointly. It is a screen for
"what is safe to ignore", not a proof of independence.
