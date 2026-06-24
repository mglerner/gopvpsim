# Mimikyu: legacy vs new PvP mechanics -- hand-validation pack

Generated 2026-06-24 to validate the experimental `--mechanics new` turn model
(the 2026-06-23 in-game PvP system). PvPoke has not implemented the new system,
so there is no reference for it; this pack lets a human cross-check.

## How to use this

1. Recreate the setup below in PvPoke (it runs the legacy system).
2. Compare PvPoke's battle timeline + rating to OUR **legacy** timeline here. If
   they match, our legacy engine is faithful (the thing we have always validated).
3. Then read OUR **new** timeline to see how the 2026-06-23 mechanics change the
   same fight. There is nothing to compare it to except expert judgment -- which
   is the point of this pack.

Each turn is 0.5 s of battle time. The score is the battle rating from the
focal (Mimikyu) side; >= 500 means Mimikyu wins. PvPoke shows the same rating.

## Setup (both cases)

- Mimikyu, Shadow Claw / Shadow Sneak + Play Rough, 15/15/15, Great League.
- Azumarill, Bubble / Ice Beam + Play Rough, 15/15/15, Great League.

## The key caveat: forced loss, or worse path?

In `--mechanics new` ONLY the resolution changed -- a charged move now lands at
the start of the next turn instead of the same turn. The AI decision layer
(`pvpoke_dp`, `_optimize_move_timing`, `_calc_turns_to_live`, `would_shield`)
does NOT know about the new timing; none of those functions take a mechanics
argument, so Mimikyu still chooses its moves as if the legacy clock applied.

So when the matchup flips below, Mimikyu is throwing the same move at the same
moment it would under legacy, and the new rules make it land a turn later, which
cascades. That is a legacy-brained pilot playing a new game. We CANNOT say
Mimikyu "has to lose" the new-mechanics version -- a Mimikyu that actually
re-planned for the new cadence (threw earlier, picked Play Rough, shielded on a
different beat) might hold the win. Treat the new-mechanics result as a likely-
pessimistic floor, not a proven outcome. Re-optimizing the AI for the new timing
is a separate, larger task, and it also has no reference to validate against.

## CASE A -- expected SAME (Mimikyu 0 shields vs Azumarill 0 shields)

Result: legacy 759, new 759. Same outcome (Mimikyu wins comfortably; the
charged-timing shift moves internal lines but never threatens the result).

### Legacy
```
--- Mimikyu 0s  vs  Azumarill 0s (score: 759) ---
T  1: Mimikyu uses Shadow Claw
T  1: Azumarill uses Bubble
T  2: Mimikyu fast → 5 dmg, energy 8
T  3: Mimikyu uses Shadow Claw
T  3: Azumarill fast → 5 dmg, energy 11
T  4: Azumarill uses Bubble
T  4: Mimikyu fast → 5 dmg, energy 16
T  5: Mimikyu uses Shadow Claw
T  6: Mimikyu fast → 5 dmg, energy 24
T  6: Azumarill fast → 5 dmg, energy 22
T  7: Mimikyu uses Shadow Claw
T  7: Azumarill uses Bubble
T  8: Mimikyu fast → 5 dmg, energy 32
T  9: Mimikyu uses Shadow Claw
T  9: Azumarill fast → 5 dmg, energy 33
T 10: Azumarill uses Bubble
T 10: Mimikyu fast → 5 dmg, energy 40
T 11: Mimikyu uses Shadow Claw
T 12: Mimikyu fast → 5 dmg, energy 48
T 12: Azumarill fast → 5 dmg, energy 44
T 13: Mimikyu uses Shadow Claw
T 13: Azumarill uses Bubble
T 14: Mimikyu fast → 5 dmg, energy 56
T 15: Mimikyu uses Shadow Claw
T 15: Azumarill fast → 5 dmg, energy 55
T 16: Mimikyu fast → 5 dmg, energy 64
T 16: Azumarill uses Ice Beam → 1 dmg
T 16: Mimikyu (Busted) disguise busted (1 dmg)
T 17: Mimikyu (Busted) uses Shadow Claw
T 17: Azumarill uses Bubble
T 18: Mimikyu (Busted) fast → 5 dmg, energy 72
T 19: Azumarill fast → 6 dmg, energy 11
T 19: Mimikyu (Busted) uses Play Rough → 69 dmg
T 20: Mimikyu (Busted) uses Shadow Claw
T 20: Azumarill uses Bubble
T 21: Mimikyu (Busted) fast → 5 dmg, energy 20
T 22: Mimikyu (Busted) uses Shadow Claw
T 22: Azumarill fast → 6 dmg, energy 22
T 23: Azumarill uses Bubble
T 23: Mimikyu (Busted) fast → 5 dmg, energy 28
T 24: Mimikyu (Busted) uses Shadow Claw
T 25: Mimikyu (Busted) fast → 5 dmg, energy 36
T 25: Azumarill fast → 6 dmg, energy 33
T 26: Mimikyu (Busted) uses Shadow Claw
T 26: Azumarill uses Bubble
T 27: Mimikyu (Busted) fast → 5 dmg, energy 44
T 28: Mimikyu (Busted) uses Shadow Claw
T 28: Azumarill fast → 6 dmg, energy 44
T 29: Azumarill uses Bubble
T 29: Mimikyu (Busted) fast → 5 dmg, energy 52
T 30: Mimikyu (Busted) uses Shadow Sneak → 57 dmg

```
### New
```
--- Mimikyu 0s  vs  Azumarill 0s (score: 759) ---
T  1: Mimikyu uses Shadow Claw
T  1: Azumarill uses Bubble
T  2: Mimikyu fast → 5 dmg, energy 8
T  3: Mimikyu uses Shadow Claw
T  3: Azumarill fast → 5 dmg, energy 11
T  4: Azumarill uses Bubble
T  4: Mimikyu fast → 5 dmg, energy 16
T  5: Mimikyu uses Shadow Claw
T  6: Mimikyu fast → 5 dmg, energy 24
T  6: Azumarill fast → 5 dmg, energy 22
T  7: Mimikyu uses Shadow Claw
T  7: Azumarill uses Bubble
T  8: Mimikyu fast → 5 dmg, energy 32
T  9: Mimikyu uses Shadow Claw
T  9: Azumarill fast → 5 dmg, energy 33
T 10: Azumarill uses Bubble
T 10: Mimikyu fast → 5 dmg, energy 40
T 11: Mimikyu uses Shadow Claw
T 12: Mimikyu fast → 5 dmg, energy 48
T 12: Azumarill fast → 5 dmg, energy 44
T 13: Mimikyu uses Shadow Claw
T 13: Azumarill uses Bubble
T 14: Mimikyu fast → 5 dmg, energy 56
T 15: Mimikyu uses Shadow Claw
T 15: Azumarill fast → 5 dmg, energy 55
T 16: Mimikyu fast → 5 dmg, energy 64
T 17: Azumarill uses Ice Beam → 1 dmg
T 17: Mimikyu (Busted) disguise busted (1 dmg)
T 17: Mimikyu (Busted) uses Shadow Claw
T 17: Azumarill uses Bubble
T 18: Mimikyu (Busted) fast → 5 dmg, energy 72
T 19: Azumarill fast → 6 dmg, energy 11
T 20: Mimikyu (Busted) uses Play Rough → 69 dmg
T 20: Mimikyu (Busted) uses Shadow Claw
T 20: Azumarill uses Bubble
T 21: Mimikyu (Busted) fast → 5 dmg, energy 20
T 22: Mimikyu (Busted) uses Shadow Claw
T 22: Azumarill fast → 6 dmg, energy 22
T 23: Azumarill uses Bubble
T 23: Mimikyu (Busted) fast → 5 dmg, energy 28
T 24: Mimikyu (Busted) uses Shadow Claw
T 25: Mimikyu (Busted) fast → 5 dmg, energy 36
T 25: Azumarill fast → 6 dmg, energy 33
T 26: Mimikyu (Busted) uses Shadow Claw
T 26: Azumarill uses Bubble
T 27: Mimikyu (Busted) fast → 5 dmg, energy 44
T 28: Mimikyu (Busted) uses Shadow Claw
T 28: Azumarill fast → 6 dmg, energy 44
T 29: Azumarill uses Bubble
T 29: Mimikyu (Busted) fast → 5 dmg, energy 52
T 31: Mimikyu (Busted) uses Shadow Sneak → 57 dmg

```

## CASE B -- expected DIFFERENT (Mimikyu 1 shield vs Azumarill 2 shields)

Result: legacy 605 (Mimikyu WINS), new 491 (Mimikyu LOSES). The flip.
Divergence: legacy throws Shadow Sneak at T21 (resolves that turn) and busts the
disguise at T32; new throws it at T22 (resolves the next turn) and busts at T33.
The whole back half slides one turn, Azumarill lands one more hit, and Mimikyu
finishes below the 500 line. See the caveat above on whether this is forced.

### Legacy
```
--- Mimikyu 1s  vs  Azumarill 2s (score: 605) ---
T  1: Mimikyu uses Shadow Claw
T  1: Azumarill uses Bubble
T  2: Mimikyu fast → 5 dmg, energy 8
T  3: Mimikyu uses Shadow Claw
T  3: Azumarill fast → 5 dmg, energy 11
T  4: Azumarill uses Bubble
T  4: Mimikyu fast → 5 dmg, energy 16
T  5: Mimikyu uses Shadow Claw
T  6: Mimikyu fast → 5 dmg, energy 24
T  6: Azumarill fast → 5 dmg, energy 22
T  7: Mimikyu uses Shadow Claw
T  7: Azumarill uses Bubble
T  8: Mimikyu fast → 5 dmg, energy 32
T  9: Mimikyu uses Shadow Claw
T  9: Azumarill fast → 5 dmg, energy 33
T 10: Azumarill uses Bubble
T 10: Mimikyu fast → 5 dmg, energy 40
T 11: Mimikyu uses Shadow Claw
T 12: Mimikyu fast → 5 dmg, energy 48
T 12: Azumarill fast → 5 dmg, energy 44
T 13: Mimikyu uses Shadow Claw
T 13: Azumarill uses Bubble
T 14: Mimikyu fast → 5 dmg, energy 56
T 15: Mimikyu uses Shadow Claw
T 15: Azumarill fast → 5 dmg, energy 55
T 16: Azumarill uses Bubble
T 16: Mimikyu fast → 5 dmg, energy 64
T 17: Mimikyu uses Shadow Claw
T 18: Mimikyu fast → 5 dmg, energy 72
T 18: Azumarill fast → 5 dmg, energy 66
T 19: Mimikyu uses Shadow Claw
T 19: Azumarill uses Bubble
T 20: Mimikyu fast → 5 dmg, energy 80
T 21: Azumarill fast → 5 dmg, energy 77
T 21: Mimikyu uses Shadow Sneak → SHIELDED (1 dmg)
T 22: Mimikyu uses Shadow Claw
T 22: Azumarill uses Bubble
T 23: Mimikyu fast → 5 dmg, energy 38
T 24: Mimikyu uses Shadow Claw
T 24: Azumarill fast → 5 dmg, energy 88
T 25: Mimikyu fast → 5 dmg, energy 46
T 25: Azumarill uses Ice Beam → SHIELDED (1 dmg)
T 26: Mimikyu uses Shadow Claw
T 26: Azumarill uses Bubble
T 27: Mimikyu fast → 5 dmg, energy 54
T 28: Mimikyu uses Shadow Claw
T 28: Azumarill fast → 5 dmg, energy 44
T 29: Azumarill uses Bubble
T 29: Mimikyu fast → 5 dmg, energy 62
T 30: Mimikyu uses Shadow Claw
T 31: Mimikyu fast → 5 dmg, energy 70
T 31: Azumarill fast → 5 dmg, energy 55
T 32: Mimikyu uses Shadow Claw
T 32: Azumarill uses Ice Beam → 1 dmg
T 32: Mimikyu (Busted) disguise busted (1 dmg)
T 32: Mimikyu (Busted) floating fast → 5 dmg, energy 78
T 33: Mimikyu (Busted) uses Shadow Claw
T 33: Azumarill uses Bubble
T 34: Mimikyu (Busted) fast → 5 dmg, energy 86
T 35: Azumarill fast → 6 dmg, energy 11
T 35: Mimikyu (Busted) uses Shadow Sneak → SHIELDED (1 dmg)
T 36: Mimikyu (Busted) uses Shadow Claw
T 36: Azumarill uses Bubble
T 37: Mimikyu (Busted) fast → 5 dmg, energy 44
T 38: Mimikyu (Busted) uses Shadow Claw
T 38: Azumarill fast → 6 dmg, energy 22
T 39: Azumarill uses Bubble
T 39: Mimikyu (Busted) fast → 5 dmg, energy 52
T 40: Mimikyu (Busted) uses Shadow Claw
T 41: Mimikyu (Busted) fast → 5 dmg, energy 60
T 41: Azumarill fast → 6 dmg, energy 33
T 42: Mimikyu (Busted) uses Shadow Claw
T 42: Azumarill uses Bubble
T 43: Mimikyu (Busted) fast → 5 dmg, energy 68
T 44: Azumarill fast → 6 dmg, energy 44
T 44: Mimikyu (Busted) uses Play Rough → 69 dmg
T 45: Mimikyu (Busted) uses Shadow Claw
T 45: Azumarill uses Bubble
T 46: Mimikyu (Busted) fast → 5 dmg, energy 16
T 47: Mimikyu (Busted) uses Shadow Claw
T 47: Azumarill fast → 6 dmg, energy 55
T 48: Mimikyu (Busted) fast → 5 dmg, energy 24

```
### New
```
--- Mimikyu 1s  vs  Azumarill 2s (score: 491) ---
T  1: Mimikyu uses Shadow Claw
T  1: Azumarill uses Bubble
T  2: Mimikyu fast → 5 dmg, energy 8
T  3: Mimikyu uses Shadow Claw
T  3: Azumarill fast → 5 dmg, energy 11
T  4: Azumarill uses Bubble
T  4: Mimikyu fast → 5 dmg, energy 16
T  5: Mimikyu uses Shadow Claw
T  6: Mimikyu fast → 5 dmg, energy 24
T  6: Azumarill fast → 5 dmg, energy 22
T  7: Mimikyu uses Shadow Claw
T  7: Azumarill uses Bubble
T  8: Mimikyu fast → 5 dmg, energy 32
T  9: Mimikyu uses Shadow Claw
T  9: Azumarill fast → 5 dmg, energy 33
T 10: Azumarill uses Bubble
T 10: Mimikyu fast → 5 dmg, energy 40
T 11: Mimikyu uses Shadow Claw
T 12: Mimikyu fast → 5 dmg, energy 48
T 12: Azumarill fast → 5 dmg, energy 44
T 13: Mimikyu uses Shadow Claw
T 13: Azumarill uses Bubble
T 14: Mimikyu fast → 5 dmg, energy 56
T 15: Mimikyu uses Shadow Claw
T 15: Azumarill fast → 5 dmg, energy 55
T 16: Azumarill uses Bubble
T 16: Mimikyu fast → 5 dmg, energy 64
T 17: Mimikyu uses Shadow Claw
T 18: Mimikyu fast → 5 dmg, energy 72
T 18: Azumarill fast → 5 dmg, energy 66
T 19: Mimikyu uses Shadow Claw
T 19: Azumarill uses Bubble
T 20: Mimikyu fast → 5 dmg, energy 80
T 21: Azumarill fast → 5 dmg, energy 77
T 22: Mimikyu uses Shadow Sneak → SHIELDED (1 dmg)
T 22: Mimikyu uses Shadow Claw
T 22: Azumarill uses Bubble
T 23: Mimikyu fast → 5 dmg, energy 38
T 24: Mimikyu uses Shadow Claw
T 24: Azumarill fast → 5 dmg, energy 88
T 25: Mimikyu fast → 5 dmg, energy 46
T 26: Azumarill uses Ice Beam → SHIELDED (1 dmg)
T 26: Mimikyu uses Shadow Claw
T 26: Azumarill uses Bubble
T 27: Mimikyu fast → 5 dmg, energy 54
T 28: Mimikyu uses Shadow Claw
T 28: Azumarill fast → 5 dmg, energy 44
T 29: Azumarill uses Bubble
T 29: Mimikyu fast → 5 dmg, energy 62
T 30: Mimikyu uses Shadow Claw
T 31: Mimikyu fast → 5 dmg, energy 70
T 31: Azumarill fast → 5 dmg, energy 55
T 32: Mimikyu uses Shadow Claw
T 33: Azumarill uses Ice Beam → 1 dmg
T 33: Mimikyu (Busted) disguise busted (1 dmg)
T 33: Azumarill uses Bubble
T 33: Mimikyu (Busted) fast → 5 dmg, energy 78
T 34: Mimikyu (Busted) uses Shadow Claw
T 35: Mimikyu (Busted) fast → 5 dmg, energy 86
T 35: Azumarill fast → 6 dmg, energy 11
T 36: Mimikyu (Busted) uses Shadow Claw
T 36: Azumarill uses Bubble
T 37: Mimikyu (Busted) fast → 5 dmg, energy 94
T 38: Azumarill fast → 6 dmg, energy 22
T 39: Mimikyu (Busted) uses Shadow Sneak → SHIELDED (1 dmg)
T 39: Mimikyu (Busted) uses Shadow Claw
T 39: Azumarill uses Bubble
T 40: Mimikyu (Busted) fast → 5 dmg, energy 52
T 41: Mimikyu (Busted) uses Shadow Claw
T 41: Azumarill fast → 6 dmg, energy 33
T 42: Azumarill uses Bubble
T 42: Mimikyu (Busted) fast → 5 dmg, energy 60
T 43: Mimikyu (Busted) uses Shadow Claw
T 44: Mimikyu (Busted) fast → 5 dmg, energy 68
T 44: Azumarill fast → 6 dmg, energy 44
T 45: Mimikyu (Busted) uses Shadow Claw
T 45: Azumarill uses Bubble
T 46: Mimikyu (Busted) fast → 5 dmg, energy 76
T 47: Azumarill fast → 6 dmg, energy 55
T 48: Mimikyu (Busted) uses Play Rough → 69 dmg
T 48: Mimikyu (Busted) uses Shadow Claw
T 49: Azumarill uses Ice Beam → 52 dmg

```
