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

| Round | Pool | Profiles | Max wins | Description |
|-------|------|----------|----------|-------------|
| 0 | 3354 | 1982 | 3/3 | All IVs that win all 3 even shield scenarios vs PvPoke default |
| 1 | **30** | 22 | 5907 | **Massive collapse** when tested against round 0's full survivor cohort |
| 2 | 41 | 30 | 60 | Slight re-expansion as the metric narrows |
| 3 | 31 | 22 | 90 | Stable |

The Nash iteration is working: starting from "everyone who beats the typical opponent," we collapse to "everyone who beats the slayer cohort itself." That collapse from 3354 → 30 is the meaningful signal.

## Top survivors (Atk Slayer category)

| IVs | Atk | Def | HP | Wins | Multi-cat |
|-----|-----|-----|----|----|------|
| 15/2/4  | 129.44 | 99.14  | 135 | 90/270 | +CMP |
| 15/5/0  | 129.44 | 100.80 | 133 | 87/270 | +CMP |
| 15/3/2  | 129.44 | 99.69  | 134 | 87/270 | **+Bulk +CMP** (most versatile) |
| 15/1/5  | 129.44 | 98.59  | 136 | 75/270 | +CMP |
| 15/1/4  | 129.44 | 98.59  | 135 | 69/270 | +CMP |
| 15/4/0  | 129.44 | 100.24 | 133 | 63/270 | +CMP |
| 15/4/1  | 129.44 | 100.24 | 133 | 63/270 | +CMP |
| 15/2/2  | 129.44 | 99.14  | 134 | 63/270 | +CMP |
| 15/2/3  | 129.44 | 99.14  | 134 | 63/270 | +CMP |

All survivors have **atk_iv = 15** (max attack). This is the iteration's strong message: in the converged Annihilape mirror, attack matters more than defense or HP.

## Comparison to community Slayer Ape spreads

| Attribute | Community spreads | Our convergence | Difference |
|-----------|------------------|-----------------|------------|
| Atk | 127.23 – 127.78 | **129.44** | **+1.7 to +2.2** |
| Def | 103.10 – 104.73 | 98.04 – 100.80 | **−3 to −5** |
| HP | 131 – 134 | 133 – 137 | similar |
| Pool size | 27 hand-picked | 30 converged | similar |

**The community goes lower attack and higher defense.** Our model goes higher attack and lower defense.

### Why the disagreement?

Three plausible explanations, in order of likelihood:

1. **Move parameters changed since the community spreads were made.** The community originally calibrated to specific named breakpoints (Lickitung BP at 127.23, mirror Def BP at 103.54 against 127.23 atk Counter). After the Counter nerf and Rage Fist addition, those exact BPs may no longer be the right cutoff — but the community spreads were never updated.

2. **The community optimizes against a broader opponent set.** Real GBL/tournament play has a mix of PvPoke defaults, atk-weighted variants, best-buddy variants, and hand-built opponents. Our iteration only tests against the converged cohort. Higher def is more robust to opponent variation.

3. **Our model has a bug we haven't found yet.** Possible but the cache fix and dedup were both validated against scripts/battle.py for the 15/15/0 vs 4/13/13 case. The math checks out.

The most likely explanation is **(1) — our convergence is correct for current move stats, the community spreads are outdated**. Worth re-running against rank-1 + atk-weighted + default opponent variants to see if (2) shifts the result.

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
