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

---

# Fix applied 2026-09-10: (2, 1) re-exempted (option A)

Swept the regressed cell before changing it. **Every setting that lets the
(2, 1) rule fire is negative:**

    (2,1) dpt_max   UL 2v1 win/mean    GL 2v1 win/mean   worst slice mean
    0.0100          +0 / +0.000        +0 / +0.000        +0.000
    0.0125          +0 / +0.000        +0 / +0.000        +0.000
    0.0150 (ship)   +0 / -1.325        +0 / +0.329        -1.325
    0.0175          +0 / -1.342        +0 / -2.932        -2.932
    0.0200+         -2 / -3.758        +0 / -2.685        -3.758

    (2,1) gate      UL 2v1             GL 2v1
    cmp_ready_dpt   +0 / -1.325        +0 / +0.329
    cmp             -2 / -7.042        -2 / -8.664
    always          -5 / -12.550       -3 / -10.322
    off             +0 / +0.000        +0 / +0.000

Only turning it off returns to zero, which is the fallback the original
campaign already documented ("Exemption = exactly 0 everywhere, which
satisfies the bar"). So `(2, 1)` is `None` again.

**Exempting is strictly better than the v4 rule on today's data**: identical
total wins (+59 vs plain PvPoke either way -- the rule contributed no net
wins at all) and a better mean.

## The accepted exception: UL 0v1

One slice still fails the self-imposed bar (`battle.py:296`, "every start
scenario must be >= 0 on BOTH mean rating delta and net win flips"):

    ultra 0v1:  -2 win cells, +8.308 mean

Both lost cells are Dondozo (bait and nobait). Michael's call (2026-09-10) was
to KEEP the (0, 1) rule and record the exception rather than switch it off,
because:

* the -2 UL win-cells are exactly offset by +2 GL win-cells -- **net zero
  wins**, not a loss;
* the mean is strongly positive in BOTH leagues (+8.3 UL, +8.7 GL);
* switching it off zeroes the GL gain too, costing ~0.95 mean-of-slice-means
  to satisfy a per-scenario rule that is about avoiding harm where there is no
  net harm.

**Root cause not addressed.** Dondozo's moves were NOT rebalanced
(Waterfall / Surf / Outrage all unchanged), so the flip is the new turn
ordering, not move data. Finding that is the only route to keeping the GL gain
without the UL loss; until then the exception stands as measured.

## Caveat carried forward

The margin numbers here are mine (mean score delta per cell) and still do not
reconcile with the published bar's units -- they record UL 0v0 as +0.558 where
I measure +9.033. The WIN-CELL counts are plain counts and are directly
comparable; the mean column orders options correctly against each other but
cannot be checked against the August figures.

---

# UL 0v1 / Dondozo: PRE-EXISTING, not a rebalance regression

The fix writeup above attributed this slice to "the new turn ordering, not move
data". **That was wrong**, and the correction matters because it moves the item
off the rebalance list entirely.

## What it actually is

Cramorant vs Dondozo, UL, 0 focal shields / 1 opponent shield:

    baseline (plain PvPoke)   515   winner 0  (Cramorant WINS)
    pogodives strat           500   winner None  (simultaneous-KO TIE)

The strat converts a win into a draw, in both bait modes -- which is the whole
of the slice's -2.

## Three causes ruled out, by measurement

* **Turn model.** Running the cell under `mechanics='legacy'` and
  `mechanics='new'` gives byte-identical results (515/0 and 500/None in both).
  The new clock has nothing to do with it.
* **Move data.** Neither side's kit changed in any sim-relevant field.
  Dondozo's WATERFALL / SURF / OUTRAGE are untouched, and Cramorant's only
  diffs are `unlisted: None -> True` on the two Gulp Missiles -- a display
  flag, not a sim input.
* **Pool composition.** Re-running the whole UL 0v1 slice against the pool as
  it stood at 83b8929 (2026-06-25, 67 opponents, pre-dating the August
  campaign) gives the SAME -2, and the same two Dondozo cells.

So it was there in August, under the old pool, the old moves and the legacy
engine.

## Why the August campaign did not catch it

Not established. The strict-bar doc records UL 0v1 as a cell the OLD rule
failed on flips (-526) which the sheet's `gate iff CMP won` fixed, and reports
the fixed slice as "+8.8..+9.7" MEAN RATING without a flip count for UL. The
sheet table is also labelled "stride-8 outcome", i.e. a subsample, so the most
likely explanation is that the full-pool flip count for this slice was never
measured. That is a guess; the campaign's raw output would settle it.

## What to do about it

Nothing urgent, and specifically NOT a re-fit input: a rule tuned to rescue
this cell would be tuned against a weakness the strat has always had, not
against anything the rebalance did. It is a genuine strategic cost of
dive-early into a bulky opponent that can trade into the missile.

Left as the single accepted exception, now correctly labelled.
