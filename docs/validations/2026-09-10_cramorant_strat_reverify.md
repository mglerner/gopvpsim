# Cramorant strat re-verify after the Twilight Trails rebalance

The rebalance re-verify that TODO.md has carried since 2026-08-25: the
PoGoDives Cramorant strategy sheet's constants were fitted on pre-rebalance
move data, so they had to be re-measured once the rebalance landed.

Run 2026-09-10, `cramorant_policy_lab.py --league both --pogodives-verify`,
against the current GL (73) and UL (60) pools. Raw:
`userdata/cramorant_lab/reverify_2026-09-10.json` (14,364 cells = 6 variants x
2 leagues x pool x 9 shield cells x 2 bait modes).

**This ran under `mechanics='new'`.** Until 2026-09-09 the lab was hard-wired
to the legacy default, so a re-verify before that would have certified the
strat against a turn system the game no longer runs.

## Headline: still net-positive, but it no longer clears its own bar

    variant        W     D     L    net
    pg_lead30   1299   117   978    +76
    pg_lead35   1299   117   978    +76
    pg_lead40   1299   117   978    +76      <- the shipped sheet
    pg_lead45   1299   117   978    +76
    pg_static14 1299   117   978    +76
    baseline    1240   108  1046     +0

## Finding 1: the LEAD constant is now inert

Every lead threshold produces an identical result. Across 2,394 distinct
cells, the pogodives variants differ from EACH OTHER in **12**. Lead 30, 35,
40, 45 and a static-14 control are effectively the same policy.

The shipped sheet is `pg_lead40`, and that 40 was a fitted constant. It is no
longer load-bearing: the same numbers come out anywhere from 30 to 45, and
from not conditioning on lead at all.

## Finding 2: two slices fail, one of them negative

Per shield slice, mean score delta of `pg_lead40` vs baseline, and the
win-cell delta:

    league  slice   win delta   mean score delta
    great   2v0          0           0.000
    great   2v1          0          +0.329
    ultra   1v0          0          +0.050
    ultra   2v0          0           0.000
    ultra   0v1         -2          +8.308
    ultra   2v1          0          -1.325   <- NEGATIVE

* **UL 2v1 is negative.** Driven entirely by Jellicent (-127 in both bait
  modes); every other opponent in the slice is 0. The strat is worse than
  plain PvPoke there.
* **UL 0v1 loses two win cells**, both Dondozo (bait and nobait). Its mean is
  still positive, so an aggregate-only check would have missed this.

The strict-bar doc (`cramorant_strict_bar_2026_08_26.md`) records the bar as
"prefer a worst-slice margin >= +0.5, not bare >= 0", with the binding cell UL
0v0 at +0.558. **CAVEAT: I did not reproduce their margin definition.** My
column is mean score delta per cell; their +0.558 for UL 0v0 does not match my
+9.033 for the same slice, so the two metrics differ. Read findings 1 and 2 as
metric-independent -- a negative slice, lost win cells, and an inert constant
are problems under any definition -- but do NOT read my numbers as directly
comparable to the published bar.

## What this does NOT say

Not an engine regression. The oracle harness shows our engine matching PvPoke
on all 36 Cramorant cells post-rebalance (see the 2026-09-09 test work), so
this is the fitted POLICY drifting against new move data, exactly as the
2026-08-25 note predicted.

## Consequences

1. The shipped sheet v5's certification does not carry over. It should not be
   re-published as-is on the strength of the old bar.
2. Jellicent is the single opponent to look at first -- it was ALREADY the
   disclosed caveat in the v2 notes ("in Great the rule fires materially
   against ONE opponent (Jellicent)"), and it is now the whole of the UL 2v1
   regression.
3. The lead constant can probably be dropped rather than re-fitted, which
   would simplify the sheet. Needs the re-fit campaign to confirm.
