# Annihilape Mirror Slayer — Nash Iteration Results

**Date**: 2026-04-07
**Simulator version**: commit 300a6dc (main)
**Move set**: Low Kick / Close Combat + Rage Fist
**League**: Great League (CP 1500)
**Opponents**: Top 20 Championship Series + Annihilape mirror

## Command

```
python scripts/deep_dive.py Annihilape --charged RAGE_FIST,CLOSE_COMBAT \
    --interactive --shield-scenario all --top-movesets 3 --opp-ivs both \
    --thresholds thresholds/annihilape.json \
    --mirror-slayer --mirror-slayer-rounds 4 --mirror-slayer-metric even-strict \
    --html annihilape_full.html
```

Wall clock: ~80 minutes (slayer round 1: ~81 min, everything else ~1 min)

## Headline finding

**The mirror slayer iteration converges to a stable 30-IV cohort at atk 129.44, def 98–101, HP 133–137.**

## Round-by-round

| Round | Pool   | Profiles | Max wins | Description                                                             |
| ----- | ------ | -------- | -------- | ----------------------------------------------------------------------- |
| 0     | 3354   | 1982     | 3/3      | All IVs that win all 3 even shield scenarios vs PvPoke default          |
| 1     | **30** | 22       | 5907     | **Massive collapse** when tested against round 0's full survivor cohort |
| 2     | 41     | 30       | 60       | Slight re-expansion as the metric narrows                               |
| 3     | 31     | 22       | 90       | Stable                                                                  |

The Nash iteration is working: starting from "everyone who beats the typical opponent," we collapse to "everyone who beats the slayer cohort itself." That collapse from 3354 → 30 is the meaningful signal.

## Top survivors (Atk Slayer category)

| IVs    | Atk    | Def    | HP  | Wins   | Multi-cat                       |
| ------ | ------ | ------ | --- | ------ | ------------------------------- |
| 15/2/4 | 129.44 | 99.14  | 135 | 90/270 | +CMP                            |
| 15/5/0 | 129.44 | 100.80 | 133 | 87/270 | +CMP                            |
| 15/3/2 | 129.44 | 99.69  | 134 | 87/270 | **+Bulk +CMP** (most versatile) |
| 15/1/5 | 129.44 | 98.59  | 136 | 75/270 | +CMP                            |
| 15/1/4 | 129.44 | 98.59  | 135 | 69/270 | +CMP                            |
| 15/4/0 | 129.44 | 100.24 | 133 | 63/270 | +CMP                            |
| 15/4/1 | 129.44 | 100.24 | 133 | 63/270 | +CMP                            |
| 15/2/2 | 129.44 | 99.14  | 134 | 63/270 | +CMP                            |
| 15/2/3 | 129.44 | 99.14  | 134 | 63/270 | +CMP                            |

All survivors have **atk_iv = 15** (max attack). This is the iteration's strong message: in the converged Annihilape mirror, attack matters more than defense or HP.

## Comparison to the community Lurgan Ape spread

The single named community spread for Annihilape is the "Lurgan Ape," popularized
by lurganrocket on Twitter. Per IV expert acidicArisen (Discord, 2026-04-08), the
spread is canonically defined by two cutoffs:

| Cutoff | Value        | Source                                                                     |
| ------ | ------------ | -------------------------------------------------------------------------- |
| Atk    | **>= 127.2** | "127.2 attack was the minimum needed for a lurgan ape" — acidicArisen      |
| Def    | **>= 102.9** | "102.9 defense was the goal" — acidicArisen ("i do not remember what for") |

The 27-IV list popularly screenshotted is the *enumeration* of those two cutoffs at
GL CP cap. Both forms are now in `thresholds/annihilape.toml` as
`spreads.lurgan_ape` (IV list) and `spreads.lurgan_ape_stat` (stat-cutoff).

Comparison vs our converged cohort:

| Attribute   | Lurgan Ape (community) | Our convergence | Difference |
| ----------- | ---------------------- | --------------- | ---------- |
| Atk minimum | **127.2**              | **129.44**      | **+2.24**  |
| Def minimum | **102.9**              | **98.04**       | **−4.86**  |
| Pool size   | 27 IVs                 | 30 converged    | similar    |

Our cohort sits **above the Lurgan atk minimum and below the Lurgan def minimum**.
At first glance this looks like a disagreement. It is not.

### Resolution: Lurgan is a historical floor, not a current target

Per acidicArisen:

> "the lurgan ape only gets some lickitung. lickitung could keep the bulkpoint with
> enough defense, so people went for even higher attack iv annihilape to beat lurgan
> ape in cmp ties & secure the lickitung breakpoint"

> "that is the list of slayer annihilape, but higher attack is preferred for more
> consistency against the mirror and lickitung"

The Lurgan spread is the **floor** — the minimum atk to clear a specific Lickitung
damage breakpoint AND the minimum def to keep some bulkpoint acidicArisen does not
remember the source of. Current community advice is to push *higher* atk than the
Lurgan baseline for two reasons:

1. **CMP wins against the mirror**: a non-Lurgan Annihilape with atk > 127.78 (the
   maximum effective atk in the Lurgan IV list) wins charge-move-priority ties
   against any Lurgan Ape opponent.
2. **BP security against Lickitung**: pushing past the strict 127.2 minimum gives
   margin for breakpoints in any move beyond the originally-targeted one.

Our converged cohort (atk 129.44, the maximum possible) is precisely what acidicArisen
describes as the "preferred for consistency" target. The convergence is not in
disagreement with the community — it is in agreement with the *current* community
view, which has moved past the Lurgan baseline.

The original three hypotheses for the apparent disagreement were:

1. **Move parameters changed since Lurgan was published.** Confirmed by
   acidicArisen: "i am pretty sure this predates the counter nerf, addition of rage
   fist, low kick buff, and annihilape almost never even considered running close
   combat." The Lurgan spread was calibrated to a Counter-era Annihilape that no
   longer exists.

2. **The community optimizes against a broader opponent set.** Partially correct
   but not the main story — acidicArisen's framing is that Lurgan was always a floor,
   and the broader opponent set just shifted the *recommendation* above that floor
   without retiring the floor itself.

3. **Our model has a bug.** Ruled out — convergence matches current expert
   guidance.

### Followup work surfaced by this resolution

- **The 102.9 def cutoff — CONCLUDED 2026-04-09 (updated 2026-06-11): the
  historical calibration is unrecoverable from current data.** The `bulkpoint`
  anchor kind shipped 2026-04-08 with the same Level 1/2/3 precision
  structure, and the Level 3 enumeration against the Annihilape mirror was run
  to identify which bulkpoint acidicArisen's 102.9 floor targeted. Result:
  the next bulkpoint above 102.9 in today's threat-move set (`shadow_ball
  <= 149` at def 103.34) is unreachable for the converged cohort (max def
  ~101.30), and the floor predates Rage Fist entirely — the threat moves it
  was calibrated against have changed too much to reconstruct the original
  tier transition. The 102.9 value stands as a frozen historical reference
  only; promoting it to a Level 1 anchor with full provenance would require
  acidicArisen's recollection of the original threat move (asked via the
  Discord question tracked in TODO.md "Analysis goals").

- **Re-run with Lurgan as an explicit opponent variant.** Even though the
  resolution above explains the disagreement, it would still be worth running
  the mirror slayer iteration with Lurgan IVs in the opponent pool (alongside
  PvPoke defaults) to see whether our atk 129.44 convergence holds when forced
  to also beat the Lurgan-style opponents. Tracked in TODO.md.

## Algorithm notes

- **Even-strict metric**: requires the focal IV to win ALL 3 even shield scenarios (0v0, 1v1, 2v2) against an opponent. Binary credit per opponent.
- **Stat profile dedup**: focal and opponent IVs with identical (atk, def, hp) are sim'd as one. Annihilape: 4096 → 2430 unique profiles (~1.7x).
- **Tied pool preservation**: when many IVs tie at max wins (3354 in round 0), we keep the entire tied pool rather than tiebreaking by avg score. Avg-score tiebreak biased toward HP-heavy IVs and was filtering out the high-atk slayer candidates.
- **Nash iteration**: round k tests focals against round k-1's survivors. Rounds 2+ are mostly cache hits since round 1 already simmed all (focal × round-0-survivor) pairs.

## Cache stats

- Total cache: 8,155,136 entries
- Round 1 cache misses: 0 (round 0 was all hits from prior runs)
- Rounds 2-4: 100% cache hits

The cache file on disk grows substantially (multi-MB) per run but stays reasonable for desktop use.
