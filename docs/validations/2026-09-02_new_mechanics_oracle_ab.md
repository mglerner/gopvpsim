# Our `mechanics='new'` vs PvPoke's new-mechanics branch: 243-cell A/B

**Headline: our `new` turn model disagrees with PvPoke's on 104 of 243 oracle
cells (43%).** It has never been cross-checked before -- DEVELOPER_NOTES
records it as coded from the published spec alone and pinned only by our own
spec-derived unit tests -- and this is the first time a reference existed to
check it against.

Run 2026-09-02, after Michael reported that the legacy turn system is gone
from the live game as of today.

## Why this matters now

`mechanics='legacy'` is the default in `simulate()`, in every CLI, in every
dive, and in the oracle harness. If legacy is gone from the game, the default
path now models a ruleset that no longer exists, and our 226-cell agreement
with PvPoke master only certifies that we match *their legacy model* -- the
question that stopped mattering.

`--mechanics new` is the intended answer. This measures whether it is ready.
It is not.

## Method

The harness (`scripts/audit_oracle_harness.py`) already runs BOTH engines over
all 27 matchups x 9 shield cells and compares score + winner + chargedLog. It
gained a `--mechanics` flag; the PvPoke side is pointed at a shadow root.

```
python scripts/audit_oracle_harness.py                      # control
python scripts/audit_oracle_harness.py --mechanics new \
       --pvpoke-root <shadow>                               # experiment
```

**The shadow root is `origin/twilight-trails`'s `src/js` over MASTER's
`src/data`.** That separation is load-bearing: twilight-trails is the season
branch and also carries the move rebalance (27 changed moves, verified), so
using its data too would confound the turn model with move-data changes and
make the result uninterpretable.

```
cd ../pvpoke && git archive origin/twilight-trails src/js | tar -x -C <shadow>
ln -s ~/coding/pvpoke/src/data <shadow>/src/data
```

## Result

| run                                         | exact | known div | mismatches |
| ------------------------------------------- | ----- | --------- | ---------- |
| CONTROL: our legacy vs PvPoke master legacy | 226   | 17        | **0**      |
| our `new` vs PvPoke's new-mechanics JS      | 122   | 16        | **104**    |

The control is what makes the experiment readable: the same harness, same
matchups, same data, zero mismatches on the legacy axis. So the 104 are
attributable to the turn model, not to harness or data drift.

### Shape of the disagreement

```
winner FLIPS            5
same winner, score     99
chargedLog-only         0
|score delta|          median 11, max 236
direction              63 ours-higher, 41 ours-lower, mean +6.7
matchups affected      24 of 27
```

Worst: `shadow_swampert_vs_registeel` (9/9), `tinkaton_vs_aegislash_shield`
(9/9), `mienfoo_vs_medicham_high_jump_kick` (7/9),
`aegislash_vs_azumarill_form_change` (7/9),
`azumarill_vs_aegislash_shield_form_change` (7/9), `cramorant_vs_registeel`
(7/9).

**Read of the shape.** This does not look like a decision-logic divergence.
Those flip winners and rewrite chargedLogs; here there are zero
chargedLog-only cells, only 5 winner flips, and the modal failure is a
same-winner score difference with a median magnitude of 11 and no consistent
direction. That is the signature of a TIMING difference -- battles ending a
turn or two apart, or damage/energy landing on a different step -- affecting
nearly every matchup because nearly every matchup has turns.

Candidate causes, from the five commits on `origin/new-mechanics`:

- `041d8c722` "Updated action priority order"
- `442a4afe8` "Timing updates"
- `a2685efe6` "Fixed Fast Attack display time after Charged Attack"
- `a1b3ebd95` "0 turn switches after Charged Attack"

Note `041d8c722` in particular. DEVELOPER_NOTES records a deliberate decision
that our `new` mode ships the decision layer as PURE PLUMBING -- under `new`
it runs the LEGACY decisions unchanged, because a corpus test found every
attempt to re-optimize either washed out or broke a non-regression floor. If
PvPoke changed action priority for the new clock, that conclusion is now
contradicted by the reference, and the "pure plumbing" invariant
(`test_new_decisions_identical_to_legacy`) is pinning a choice the oracle no
longer agrees with.

**Not yet established:** which of the four commits accounts for how much. The
same block-by-block revert technique used for the mega ActionLogic A/B applies
directly -- build one shadow root per commit and re-run -- and would attribute
the 104 cells without guesswork. That is the obvious next step and was not
done here.

## What this does NOT say

- It does not say PvPoke is right and we are wrong. PvPoke's new-mechanics
  branch is unmerged and unreleased; it is an implementation of the same
  published spec we coded from. It is, however, the only reference that
  exists, and being 43% apart from it means at least one of us is wrong in
  ways neither has caught.
- It does not measure against the GAME. Neither side has been validated
  against live play.
- The 16 "known divergences" in the experiment column are the legacy-derived
  xfail sets, which have no reason to apply under a different turn model. The
  harness prints a warning saying so. Treat only the mismatch count as
  meaningful.

## Consequence for the season bake

Baking with `--mechanics legacy` models a ruleset the game no longer runs.
Baking with `--mechanics new` produces numbers that disagree with the only
available reference on 43% of the cells we check. Neither is currently a
defensible basis for published spreads, and the gap needs closing before a
season bake rather than after.

Raw per-cell output: `2026-09-02_new_mechanics_oracle_ab_raw.txt`.
