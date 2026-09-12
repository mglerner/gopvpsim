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
