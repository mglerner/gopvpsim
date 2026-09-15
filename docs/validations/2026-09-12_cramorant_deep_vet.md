# Cramorant strat deep re-verification (2026-09-12, in progress)

Commissioned by Michael 2026-09-12 after the strategy article's showcase
links were found stale: "fix the verification of the strategy right now
... this is our 1st Fable look at the strat, so we're free to vet things
deeply. Then, once our strat is solid, yeah, we do want new examples."
The UL 0v1 Dondozo exception (2026-09-10) is NOT grandfathered: it stays
only if the re-derivation shows it is a genuine cost of a rule that earns
its place.

## Why the 2026-09-10 re-verify was not enough

It ran `cramorant_policy_lab.py --pogodives-verify`: ONE moveset
(Peck / Dive + Fly), ONE IV spread (PvPoke default), its own per-cell
mean-score metric that could not be reconciled with the bar's units (the
doc says so), against a GL pool that has since changed; and from
2026-09-10 the lab could not even load the GL pool (list/str crash on the
Thievul `charged=` rows, fixed 2026-09-12). The article, meanwhile,
claims certification over all five movesets x 4096 spreads.

## Instruments (all on branch `cramorant-reinvestigate`)

- `scripts/cramorant_certify.py` -- the strict bar over the FULL grid
  from the rendered dive pages' tensors: 5 moveset pages x 2 leagues x 2
  opponent-IV modes x 2 bait modes x 2 level caps x 9 start scenarios =
  720 cells at 4096-IV resolution, in seconds. Per cell: net win flips,
  mean rating delta, negative opponents, top-100-stat-product lens,
  exemption check (None rows must be byte-identical). `--selftest N`
  re-sims random cells through the production path: 30/30 integer-exact
  on 2026-09-12.
- `scripts/cramorant_mini_sweep.py` -- one slice re-simmed under knob /
  sheet-row overrides; `--check-tensor` integer-exact at shipped knobs
  (5168/5168 on the failing slice; 3268/3268 on a @51 twin); coprime
  `--stride` for screens (power-of-two strides alias the stamina axis);
  `--log` captures both tiers' timelines for a cell.
- `scripts/cramorant_recertify.py` -- every slice of the CHANGED start
  scenarios under a candidate override set, certifier-style table with
  shipped-vs-run numbers. Stride 1 is the bar; ~620k sims per slice.

## Full-grid read, shipped sheet (GL page baked 2026-09-12, UL page
2026-09-11, both post-rebalance engine)

    league scen slices  min mean  min net  total net   min top100 mean
    great  0v0      40     0.000        0      86696             0.000
    great  0v1      40     0.000        0      42026             0.000
    great  0v2      40     0.000        0      34360             0.000
    great  1v0      40     1.121        0      51316             0.040
    great  1v1      40     2.708     2974    1055648             1.198
    great  1v2      40     3.163     6815     648140             1.576
    great  2v0      40     0.000        0          0             0.000
    great  2v1      40     0.000        0          0             0.000
    great  2v2      40    -4.217      288     272722             0.869
    ultra  0v0      40     0.000        0      68716             0.000
    ultra  0v1      40     0.000        0       1444             0.000
    ultra  0v2      40     0.000        0       1615             0.000
    ultra  1v0      40     1.156      624     124290            -1.689
    ultra  1v1      40    12.623    11804     991574             9.744
    ultra  1v2      40    11.119     8407     688709             8.735
    ultra  2v0      40     0.000        0          0             0.000
    ultra  2v1      40     0.000        0          0             0.000
    ultra  2v2      40     3.474    10433     725781             4.208

**716/720 cells pass. 4 FAIL:** GL Peck / Hydro Pump + Surf, 2v2, no-bait,
both opponent-IV modes, both caps: mean -3.30 (pvpoke IVs) / -4.22 (rank1
IVs), driven by Corviknight (-3835 flips, -324 mean) and Shadow
Corviknight (-2691 / -4083). The v5 certification never had this build in
GL (it entered with the 2026-09-11 moveset rules). Trace at iv 11
(0/0/11): identical until T34, where Corviknight throws a 44-damage Air
Cutter (~35% of Cramorant's HP). PvPoke SHIELDS and later wins 662 (eats
the T44 Air Cutter, missile fires, Surf KOs). The loaded-opponent tank at
1.6 DECLINES for a 23-damage missile (~15% of Corviknight's HP), spends
the shield at T36 and dies to the T44 Air Cutter, 300. Plain PvPoke wins
~650 in 3835/4096 spreads; PoGoDives loses 300 in all of them.

**The Dondozo -2 does not exist at full resolution.** UL 0v1's only
negative opponent is Jellicent (rating only: -14 mean, 0 flips). The
2026-09-10 "-2 win cells" was the single PvPoke-default spread (15/15/15,
iv 4095), where the strat turns a 515 win into a 500 tie; across the 4096
spreads Dondozo nets >= 0.

**Hidden per-opponent losses inside passing slices** (worst slice, cap 50):
GL 1v1 Mandibuzz -4020 / Umbreon -3800 (Dive + Hydro Pump, pvpoke bait);
GL 1v2 Shadow Corviknight -3314, Snorlax -3340, Jumpluff -1885; GL 2v2
Toxapex -1753, Altaria (Shadow) -1476, Guzzlord -1559 (but +72 mean),
Azumarill -1436, Bombirdier -505; GL 0v0 Altaria -1095 (+17 mean); UL 1v1
Miltank -1792, Snorlax -1596; UL 1v2 Snorlax -1536; UL 2v2 Shadow
Corviknight -2000. UL 1v0 top-100-SP mean -1.05 (Dive + Fly, rank1;
Corviknight -4.73). The bar aggregates over the pool, so these hide.

## Campaign (workflow `cramorant-deep-vet`, 2026-09-12 evening)

Six tracer agents (one per loss cluster: T1 the 2v2 Corviknight failure,
T2 other 2v2 losers, T3 1v1, T4 1v2, T5 0v1/1v0/0v0 incl. Dondozo, T6
constants liveness + the 2v1 exemption), each followed by a skeptic on
holdout slices, then a referee synthesising a v6 sheet proposal and the
stride-1 re-certification plan. Results: appended below when they land.

## Campaign results (13 agents: 6 tracers, 6 skeptics, 1 Fable referee)

Full reports: the workflow journal (session
`ad4bd9d9`, run `wf_62d879e7-6ef`) and the agents' scratch dirs under
`userdata/analysis/2026-09-12_cramorant_deep_vet/` in the clone.

### Mechanism map (species names are labels for the cells, not the rule)

- **M1 -- last-shield tank vs a non-chipping opponent (2v2).** The loaded-
  opponent tank at 1.6 declines a 44-damage hit (34% of our bar) on our LAST
  shield to fire a missile whose payload is fixed at int(0.15 x their max HP)
  + 1 regardless of typing. Against an opponent whose fast move deals 1 per
  turn (Sand Attack), all their damage is charged, so the kept shield is worth
  a whole charged move and our HP does not decay: hoarding HP beats hoarding
  the shield. Probe over every divergent tank decision: shields==1 mean delta
  -15.2 (GL) / -7.1 (UL); shields==2 +8.1 / +14.0. The gate contributes 0
  cells on the failing page: 100% tank. => **v6 `lead_ready_chip`**.
- **M2 -- terminal-KO overkill (1v0).** Cramorant declines a 43-damage hit to
  fire a missile one turn before its own Dive KOs anyway; the shield is never
  spent. UL rank1 top-100-SP -1.05 @50 / -1.69 @51, all Corviknight. =>
  **v6 `lead_ready_ko`** (-4.73 -> 0.00; 320 cells better / 0 worse; a
  byte-identical no-op everywhere else; on today's gamemaster it removes a
  loss rather than adding value, and migrates to Dusknoir under +10% power).
- **M3 -- hardest-hit decline with no reallocation value (1v1).** Umbreon /
  Mandibuzz (GL Dive+HP bait), Miltank / Snorlax (UL Dive+Fly nobait). The
  local trace is right but the identical decision inputs give +3800 on the
  sibling page or bait mode: what flips is Cramorant's OWN tempo after the
  decision, which the tank never reads. Every candidate (`lead_harder` etc.)
  is a near-blanket tank-off that costs 35% of the row and creates Milotic
  (Shadow) -924 / Cresselia (Shadow) -2304. **Unfixed; documented.**
- **M4 -- 1v2 nuke-tank into a reloading opponent.** Snorlax / Shadow
  Corviknight / Jumpluff / UL Snorlax, 100% tank. `f_or_drained` clears them
  but is an absolute damage cutoff in GL (max HP constant 123), sits 0.02 from
  a cliff, wipes Feraligatr +1032 and a top-SP slice, and its benefit vanishes
  under +/-10% power. Row passes the bar everywhere. **Leave; documented.**
- **M5 -- the 2v2 gate downgrades the one throw that lands** (Toxapex,
  Azumarill, Altaria (Shadow), Guzzlord on the Dive+Fly page only). The
  opponent blanks 2 of 3 throws; the rush turns the landing Fly into a Dive
  and PvPoke's own weak-move save declines it, so no shield burns. Every gate
  retune fails the UL Dive+Fly holdout (-320..-830 net). Guzzlord's -1559
  flips / +72.6 mean is rating padded onto lost fights, paid with 504-519
  razor wins. **Leave; documented.**
- **M6 -- 2v2 tank coin-flips on the future shield ledger** (Bombirdier -505
  dies holding both shields; Sableye (Shadow) +919 wins by declining into the
  red). Downstream payoff, not local arithmetic. **Unfixed.**
- **M7 -- damage-only DPE misprices the Gulp cycle at 0v1** (UL Dondozo 19
  ties, Jellicent -14 mean). Adding the missile to the Gulp side reproduces
  the split: vs Dondozo (27+37)/40 = 1.60 > 70/45 (shipped RIGHT); vs
  Jellicent (25+30)/40 = 1.375 < 63/45 (shipped wrong). The parameter-free
  missile-inclusive gate fixes Dondozo (515 -> 621) but collapses GL 0v1 from
  +13.4 to +1.2 mean and goes net-negative in two GL slices: structurally
  incompatible. **Documented boundary cost.**
- **M8 -- 0v0 per-pair bulk breakpoint** (GL rank1 Altaria -1095 flips, 0
  gained, +17.2 mean; monotone in Cramorant's attack IV). Conditioning on own
  bulk = fitting to Altaria. **Documented.**
- **M9 -- rating-only win-margin taxes at 2v2** (Araquanid (Shadow), Spidops,
  Dondozo: 0 flips, wins by less). Undiagnosed at decision level.
- **M10 -- structure.** The gate column equals one predicate: gate on iff
  opp_start_shields >= my_start_shields (reproduces all 9 rows). GL cap 51 ==
  cap 50 bit-identical (CP cap binds); 1v0 bait == nobait. Three constants
  are dead (`_POGODIVES_GATE_DPT_MAX`, `_POGODIVES_GATE_MIN_ENERGY`,
  `_POGODIVES_TANK_CHEAP_FRAC`); deleting them needs the synthetic-row tests
  and `cramorant_sensitivity.py` updated -- a separate hygiene commit.

### Decisions (referee, adopted 2026-09-12)

| row           | action | rule                                                                                                                                                                    |
| ------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0v0, 0v1, 0v2 | keep   | unchanged; Altaria / Dondozo / Jellicent recorded as boundary costs                                                                                                     |
| 1v0           | change | `lead_ready_ko`: lead_ready + terminal-KO guard (2 x energyGain slack, inside the measured plateau)                                                                     |
| 1v1, 1v2      | keep   | hidden losers documented; no candidate survived the skeptics                                                                                                            |
| 2v0, 2v1      | exempt | unchanged; every 2v1 alternative is mean-negative in GL, the only window is the post-first-shield 1v1 sub-game                                                          |
| 2v2           | change | `lead_ready_chip`: lead_ready + last-shield guard, division-free form "their fast move deals <= 1 per turn" (the ratio form at 0.012 split 70 GL cells on our own bulk) |

**Dondozo (Michael's condition):** not a defect. At full resolution UL 0v1
pvpoke mode has 19 negative Dondozo cells of 4096, all attack IV 15, all
razor wins (503/506/515) turned into exact 500 ties: 0 net flips, -123
rating against +614,916 of gains on the same opponent; rank1 mode has zero.
The rush is priced correctly once the missile is counted; the tie is its
razor edge. The only clean removal costs ~90% of GL 0v1's rating. Kept, and
the 2026-09-10 "-2 win cells" line is corrected below.

### Failing-first cells (tests/test_pogodives_v6.py)

    GL Peck/HP+Surf 2v2 nobait, Cramorant 0/0/11 vs Corviknight 4/12/14:  plain 662, v5 300 -> v6 662
    UL Peck/Dive+Fly 1v0 rank1 @51, Cramorant 0/15/15 vs Corviknight 0/15/15: plain 765, v5 632 -> v6 765

### Not trusted yet / next cycle

- Stride-1 re-certification of the two changed rows (90 slices: 2v2 60, 1v0
  30 after the cap-51 and bait degeneracies) waits for the rebake to free the
  cores; stride-13 screens and the adjacency check are in
  `userdata/cramorant_lab/v6_*.json`.
- P-C: the KO guard applied at 1v1 measured positive in GL (mean +0.8 x4,
  removes Bombirdier) and neutral in UL -- untraced.
- P-D: the constant-free 1v2 variant `lead_drained` (honest cost: most of the
  row's value) if the hidden losers there must go.
- Michael's calls: Guzzlord 2v2 flips-vs-rating (documented cost or target?);
  the dead-constant hygiene commit; whether to re-express the gate column as
  the one predicate.

## Stride-1 re-certification, priority slices (2026-09-12 night, v6 threaded)

`cramorant_mini_sweep.py --stride 1` on the referee's priority set (15 of
the 90 changed-row slices; the rest wait for the rebake to free cores).
"was" = the shipped v5 tensor. Plain-tier mismatches in the two GL m4
slices (1 and 64 cells) are the Aegislash (Blade) contamination, not v6.

| slice                                   | net was -> v6    | mean was -> v6   |
| --------------------------------------- | ---------------- | ---------------- |
| GL HP+Surf 2v2 pvpoke/nobait @50 (FAIL) | +288 -> +6814    | -3.298 -> +3.089 |
| GL HP+Surf 2v2 rank1/nobait @50 (FAIL)  | +3606 -> +11291  | -4.217 -> +3.244 |
| GL Dive 2v2 pvpoke/bait @50             | +2683 -> +2683   | +4.712 -> +4.709 |
| GL Dive+Fly 2v2 pvpoke/bait @50         | +5577 -> +5577   | +2.087 -> +2.084 |
| UL HP+Surf 2v2 pvpoke/bait @50          | +14613 -> +12613 | +6.519 -> +6.504 |
| UL HP+Surf 2v2 pvpoke/bait @51          | +14282 -> +12634 | +6.714 -> +6.771 |
| UL HP+Surf 2v2 pvpoke/nobait @50        | +10433 -> +12433 | +3.474 -> +6.688 |
| UL HP+Surf 2v2 pvpoke/nobait @51        | +10883 -> +12531 | +4.027 -> +6.886 |
| UL HP+Surf 2v2 rank1/bait @50           | +12857 -> +11465 | +6.288 -> +6.168 |
| UL HP+Surf 2v2 rank1/bait @51           | +12173 -> +10973 | +6.298 -> +6.185 |
| UL HP+Surf 2v2 rank1/nobait @50         | +12958 -> +13852 | +6.877 -> +8.207 |
| UL HP+Surf 2v2 rank1/nobait @51         | +12222 -> +13136 | +6.760 -> +8.117 |
| UL Dive+Fly 1v0 rank1/bait @50          | +1429 -> +1429   | +1.589 -> +1.665 |
| UL Dive+Fly 1v0 rank1/bait @51          | +913 -> +913     | +1.156 -> +1.323 |
| UL Dive+Fly 1v0 pvpoke/bait @51         | +624 -> +624     | +1.290 -> +1.357 |

All 15 pass the bar on both metrics. The four failing cells are fixed with
large margins. Disclosed cost of the chip guard: UL HP+Surf 2v2 BAIT mode
gives back 1200-2000 win-cells per slice (mean flat) for +900-2000 in
no-bait mode; the page nets -784 win-cells over its eight 2v2 slices with
mean up everywhere. Remaining 75 slices: GL 2v2 (16 more at cap 50), UL
2v2 pages m0/m2/m3/m4 (32), GL 1v0 (10), UL 1v0 m1/m2/m3/m4 (16) plus the
UL index 1v0 nobait twins; run `cramorant_recertify.py --scenarios 2v2,1v0
--stride 1` when the machine is free (~4-6 h serial under load).

## Stride-1 re-certification, ALL 90 changed-row slices (2026-09-15, machine free, 16-way)

`userdata/cramorant_lab/v6_stride1_full/` (per-slice JSON) + log
`userdata/logs/2026-09/v6_stride1_20260915.log`; 20 minutes wall clock.
Both Cramorant pages as re-baked (GL 2026-09-12, UL 2026-09-13).

**90 / 90 PASS, 0 FAIL** on both metrics -> v6 is certified under the
go/no-go rule. Worst margins: min net 0 (GL HP+Surf 1v0 pvpoke/bait,
unchanged from shipped), min mean +1.121 (GL Dive+Fly 1v0). Total net win-
cells over the 90 slices: shipped 937,116 -> v6 931,522 (-0.6%), with the
four failing cells fixed and every top-SP lens >= 0 at the stride-13 read.
Where the chip guard gives value back (bait modes, where the rush is the
opponent's bait target and the last-shield decline was paying): GL HP+Surf
2v2 bait -3.8k / -3.6k net, mean 6.2 -> 3.4; UL Peck/Surf 2v2 all eight
slices -1.1k..-1.9k net, mean -0.4..-0.7; UL HP+Surf 2v2 bait -1.2k..-2.0k,
mean flat. Disclosed, accepted: the bar is per-slice non-negativity on both
metrics, which every slice meets, and the alternative was shipping a row
that loses 300 in 3835/4096 spreads against one opponent.
