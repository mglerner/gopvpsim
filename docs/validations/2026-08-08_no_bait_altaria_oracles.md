# No-bait Altaria oracles: Tinkaton 0-1 and Spidops 1s (2026-08-08)

Closes the two remaining "no-bait oracle tests from iv-tech deep dives"
cases in TODO.md. Both reference claims reproduce in our sim, and one of
them turns out to explain a standing open question about our win
threshold.

Tests landed in `tests/test_battle.py`:

* `test_tinkaton_0v1_vs_rank1_shadow_altaria_bulk_gate_no_bait`
* `test_tinkaton_0v1_vs_rank1_shadow_altaria_baiting_rescues_low_bulk`
* `test_spidops_1v1_vs_rank1_altaria_bulk_gate`
* `test_spidops_1v1_vs_default_iv_altaria_needs_133_hp`

## Method

Great League, PvPoke default movesets resolved through
`gopvpsim.data.get_default_moveset` (Tinkaton Fairy Wind / Gigaton Hammer
+ Bulldoze; Spidops Shadow Claw / Lunge + Rock Tomb; Altaria Dragon
Breath / Sky Attack + Flamethrower). Opponent "rank #1" is the top
stat-product spread from `iv_rank`; "default IV" is
`pvpoke_default_ivs`. Shields are focal-first, opponent-second, matching
the references' `0-1` / `1s` vocabulary (`docs/concepts.md`). Both sides
run `pvpoke_simulate_shield`; the focal side's charged policy is
`pvpoke_dp` with `bait_shields` toggled, the opponent always baits.

Measured at repo HEAD `2896a25`, engine untouched (this lane adds tests
and this note only).

## Case 1 -- Tinkaton vs rank #1 Shadow Altaria, 0-1

Reference (`docs/tinkaton_deep_dive_reference.md:31`):

> 143.04 defense with 141 hp (or 143.72 defense with 140 hp) lets you win
> the 0-1s against the rank #1 shadow altaria without baiting

Rank #1 Shadow Altaria is 0/14/15 @ L29 (atk 121.72, def 128.89, hp 141).
Scores below are Tinkaton's pvpoke score.

| Tinkaton IVs | def    | hp  | bait ON | bait OFF | note                                 |
| ------------ | ------ | --- | ------- | -------- | ------------------------------------ |
| 0/14/9       | 143.04 | 141 | win 627 | win 503  | reference spread A                   |
| 0/15/8       | 143.73 | 140 | win 625 | win 503  | reference spread B (ref says 143.72) |
| 1/14/14      | 141.66 | 143 | win 629 | win 506  | below the def line, +3 hp            |
| 0/14/10      | 141.66 | 140 | win 621 | LOSS 269 | same def as above, 3 fewer hp        |
| 0/13/10      | 142.36 | 141 | win 624 | LOSS 251 | reference hp, def short              |
| 0/10/15      | 138.96 | 143 | win 625 | LOSS 251 | max hp alone is not enough           |

Both reference spreads win without baiting, and the gate is real: three
spreads short of it lose. The "without baiting" qualifier is fully
load-bearing -- with baiting on, *every* spread wins this cell, including
15/15/15.

Mechanism, read off the logged timeline rather than assumed:

* Shadow Altaria's Flamethrower lands for **80** at def=143.04 and **81**
  at def=141.66. That is a genuine bulkpoint.
* Bait OFF at 0/14/9: Gigaton Hammer at T15 eats the shield, Flamethrower
  80 at T17, Sky Attack 32 at T29, and Tinkaton survives on 1 HP to land
  the second Gigaton Hammer (84) at T30.
* Bait OFF at 0/14/10: Flamethrower 81 and one less HP means Tinkaton is
  one Gigaton Hammer short -- it throws Bulldoze (10) at T28 and dies.
* Bait ON at 0/14/10: Bulldoze at T15 eats the shield instead, so Gigaton
  Hammer lands unshielded (83) at T26. Easy win, no bulk needed.

## Case 2 -- Spidops vs Altaria, 1s

Reference (`docs/spidops_deep_dive_reference.md:35`):

> 140.67 defense with 132+ hp flips the 1s vs the rank #1 altaria without
> baits by reducing sky attack damage. 140.85 defense with 133+ hp covers
> the default IV altaria (4/12/13)

Rank #1 Altaria is 0/14/15 @ L29 (atk 101.44, def 154.67, hp 141);
default-IV Altaria is 4/12/13 @ L28.5 (atk 103.41, hp 138). Bait mode
made **no** difference in any Spidops cell, so one column covers both.

vs rank #1 Altaria:

| Spidops IVs | def    | hp  | result   | note                               |
| ----------- | ------ | --- | -------- | ---------------------------------- |
| 1/14/14     | 140.72 | 132 | win 503  | minimal spread meeting the claim   |
| 2/15/15     | 140.99 | 132 | win 503  | the reference's recommended spread |
| 1/13/15     | 139.94 | 132 | LOSS 404 | hp met, def short                  |
| 0/12/12     | 140.67 | 131 | LOSS 404 | def on the line, hp one short      |
| 1/11/15     | 138.88 | 133 | win 503  | def short but +1 hp                |

vs default-IV Altaria:

| Spidops IVs | def    | hp  | result   | note                              |
| ----------- | ------ | --- | -------- | --------------------------------- |
| 0/13/14     | 140.96 | 133 | win 503  | minimal spread meeting the claim  |
| 0/14/15     | 141.23 | 133 | win 503  | more def, same 133 hp             |
| 0/14/13     | 141.75 | 132 | LOSS 416 | MORE def than the winners, 132 hp |
| 1/11/15     | 138.88 | 133 | LOSS 416 | 133 hp met, def well short        |

The stated mechanism holds. Spidops' Rock Tomb debuffs Altaria's attack
before the decisive Sky Attack, which then lands for **54** at def=140.72
and **55** at def=139.94. The winner finishes on exactly 1 HP, so that
single point of Sky Attack damage is the entire margin.

The 0/14/13 row is the interesting one: it carries more defense than
either winner against default-IV Altaria and still loses on 132 hp. The
reference's "133+ hp" is therefore an independent constraint, not a
paraphrase of the defense number.

## Partial resolution of the "more forgiving win threshold" note

TODO.md carried an open follow-up on the shipped Tinkaton-vs-Medicham
oracle: "our sim has a more forgiving win threshold than the reference
(many Tinkaton spreads below def=141.66 win the 1v1, e.g. 0/10/15 at
def=138.96)."

Re-measured here, both bait modes, Tinkaton vs rank #1 non-best-buddy
Medicham 1-1:

| Tinkaton IVs | def    | hp  | atk    | result   |
| ------------ | ------ | --- | ------ | -------- |
| 1/14/14      | 141.66 | 143 | 105.23 | win 520  |
| 0/14/9       | 143.04 | 141 | 105.58 | win 521  |
| 0/14/10      | 141.66 | 140 | 104.56 | win 503  |
| 0/10/15      | 138.96 | 143 | 104.56 | win 506  |
| 0/0/0        | 137.31 | 138 | 108.58 | LOSS 492 |
| 15/15/15     | 135.18 | 136 | 108.91 | LOSS 492 |

The threshold is not actually loose. 0/10/15 has def 138.96 but hp 143,
for a def x hp product of 19871 against the reference spread's 141.66 x
138 = 19549 -- it is the *bulkier* Pokemon, so it winning is expected.
Genuinely thinner spreads (0/0/0, 15/15/15) do lose. The same pattern
shows up in both cases above (Tinkaton 1/14/14 and Spidops 1/11/15 both
clear their gates from under the quoted defense, on extra HP), and the
Spidops reference states the trade explicitly at line 23: "anything here
can work with more defense/less hp or vice versa".

So the reference numbers are sufficient conditions on a (def, hp) pair,
not defense floors, and our sim agrees with them. The residual worry
about a systematically loose win threshold is not supported by this data.

**Not verified here:** no round-trip against pvpoke.com/battle. That was
the other half of the original follow-up and still has not been done --
these numbers are our sim against the written references, not against
PvPoke's own simulator. Treat the resolution above as "the loose-threshold
hypothesis has no support in our data", not as "our sim matches PvPoke
on these cells".
