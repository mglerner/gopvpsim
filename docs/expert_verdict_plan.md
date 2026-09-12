<!-- Provenance: synthesized 2026-09-11 by a 24-agent workflow (5 readers, 4
independent proposals, 12 adversarial critiques, synthesis, completeness
critic, revision) run from the Fable session that produced
docs/scenario_clusters_plan.md. Every number in section 3 was recomputed
from the 2026-09-11 Shadow Sableye GL replay blob by the synthesis and
revision agents; Michael has NOT reviewed it yet. The HTML companion is
~/coding/reports/gopvpsim-scenario-clusters-plan-2026-09-11.html.
Exploration-mode doc: Claude prose is fine here; nothing in it ships. -->

# Expert verdict plan: the "build brief"

Synthesis of four proposals (clusters-first, expert-first, product-first,
skeptic-minimal), each attacked by three adversarial lenses (correctness,
expert credibility, ship policy / engineering), then revised against a
completeness critique (14 items; every one is either taken below or
listed in section 8 with the reason). Worked case: Shadow Sableye, Great
League, Shadow Claw / Drain Punch + Foul Play, bake 2026-09-11
(`userdata/replay/20260911_005150_Sableye_great_shadow.replay.pkl.gz`).
Every number in section 3 was recomputed from that blob for this document
(`scratchpad/judge/j1.py`, `j2.py`, `j3.py`; revision scripts
`scratchpad/reviser/r1.py` .. `r4.py` and re-runs of the critic's `v6.py`
/ `v10.py`; all under `nice -n 19`, no sims, nothing written to the repo
or to `userdata`); where a number is cited from a critique instead, it
says so.

Vocabulary used below (defined once here, per the docs style rule):

- CMP (Charge Move Priority): when both sides throw a charged move on the
  same turn, the higher attack stat goes first. Our engine and PvPoke
  compare the shadow-STRIPPED attack (`src/gopvpsim/battle.py:2720-2729`),
  so for a shadow focal the CMP line is `1.2 x opponent raw attack`. On an
  EXACT tie the engine is seat-dependent (see field 15 and guard G-tie).
- Clean cut: a stat value T such that, for one (opponent, shield scenario)
  cell, EVERY spread with `stat >= T` wins and NO spread with `stat < T`
  wins (win = score > 500 via `gopvpsim.battle.is_win`; 500 is a tie).
  This is the new primitive. It is stricter than the shipped "flips at"
  boundary (75/25 gate, `scripts/deep_dive_analysis.py:521`) and than the
  clusters section's best single-stat rule (misclassifications allowed).
- Rung: a clean cut on the attack axis, named by the cell(s) it owns.
- Co-gate: a second-stat condition (Def >= d or HP >= h) that, INSIDE the
  spreads clearing a rung, wins one named cell 100% of the time.
  Sufficient, never necessary; printed with the win rate outside it.
- Alternative target: a (Def, HP) rectangle containing no spread that
  clears the floor, printed with the cells it guarantees that the floor
  cannot, and vice versa. The bulk fork, stated as a stat triple.
- Mode: one of the four baked opponent-IV x bait settings (`pvpoke`,
  `pvpoke:nobait`, `rank1`, `rank1:nobait`). The `:nobait` axis is focal
  only; the opponent always baits (`scripts/deep_dive_lib/sweep.py:611`).
- SP: stat product; "rank-1" means the stat-product rank-1 spread.

## 0. The one-paragraph answer

Ship a per-moveset "build brief" section computed only from clean cuts,
with a closed-form CMP / breakpoint mechanism label on every rung, a
coverage ladder (how much of the opponent's own IV grid the printed line
strictly beats, ties counted separately), a rank-1 adjudication, a
per-shield-count mirror block, one alternative (bulk) target stated as a
stat triple with the cells it trades, a "changes the score, not the
matchup" list, an explicit "not claimed" tally, and a degradation ladder
that prints an honest negative when the grid has no clean structure. No
cohort means anywhere -- not above-vs-below the floor and not across
stat bands inside it: under a CP cap any band comparison measures
def/hp/atk composition, and all three critique lenses independently
killed every proposal that used one. The skeptic-minimal skeleton wins;
the expert-first ladder, frontier, bulk fork and score-only section, the
product-first override/degradation rules, and the clusters-first
scenario-admission gate are grafted onto it. Before any renderer is
written, a no-sim sweep over the 82 Great League blobs on disk measures
how many dives produce a floor at all, and Michael sets the go/no-go bar
from that table (Phase 0 item 4, decision D12).

## 1. Scoring the proposals

| Proposal        | Survived                                                                                                                                                                                                                                                                                                                                                                                                                | Died                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Verdict                            |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| clusters-first  | Score-tier fingerprint (K=2, silhouette 0.499, floor 148.7107, reproduced by 2 critics); scenario admission gate (n_sharp>=6, n_patterns>=8); 4-mode floor row; score-only ledger; pool-membership robustness (drop Aegislash/Annihilape variants: same floor); attained-value print guard; the HP "stretch rung" idea (taken as a co-gate search on HP, section 4 stage 9)                                             | WHAT IT BUYS/COSTS and NET tables are band means (bulk-confounded: every printed cost cell is best explained by def or hp, not atk); 6 of 8 headline gains already bought at cheaper rungs; mirror claim is an opponent-IV artifact (rank-1 mirror: 9/4096 win 1v1); "148.71072" literal selects 1925 not 1940; "BUILD TARGET" noun collides with the pinned cross-label contract; no mechanism; 9 headers of clustering diagnostics in reader register; its stretch rung (148.71 + HP >= 124, n=117) is 98.3% / 88.9% on two of its three cells, not 100% | Keep as corroboration only         |
| expert-first    | Stage 2 clean cut (40 atk / 0 def / 0 hp cells, exact); Stage 1 triage (278/245/161); per-cell unanimity ledger (13/9 exact); CMP closed form (12 cells strictly inside their gaps); (def,hp) substitution frontier (exact); fork B bulk target (Def >= 101.33, HP >= 125, n=114, 9 cells no floor clearer wins: exact, taken as field 8); score-only section; rank-1 adjudication; degradation ladder; no-TOML routing | Annihilape "0% of rest" is 30.9%; 10 of 22 mode bands inflated (4 of 13 gains are 4/4, not 7); "22 not claimed" is 139; Stage 6 argmax does not produce its own fork (argmax is n=297); Stage 5 confirmation is a tautology for non-CMP rungs; bulk target is sufficient-only under a masthead claiming 100%-both-ways; ladder omits Mantine 142.48 and miscounts its tail ("7 further floors"); cohort-mean scores in Stage 12; editorial sentences ("the ones to build for")                                                                             | Best structure; graft most of it   |
| product-first   | Orthant primitive (41 cells, exact; rejects the Aegislash window); NO CALL ladder wording; human override block with `body` / `target`; one [Recommended] badge on the page; pole-label fix; null rung; aggregate numbers all reproduce                                                                                                                                                                                 | Headline sentence false for 21 of 23 cells (cells with lower floors counted as bought by 148.71); Step 4 gate either aborts on the worked case or is a tautology; knee rule gives 142.48 or 152.58 depending on reading, never 148.71; CONFIRMED is one-sided (two-sided count is 0/23 = THIN); band-mean net table; cost list topped by the degenerate 0v2; moveset hold is counts not intersection (9 of 23 shared with ms1); claims deep_dive_analysis.py is in the engine hash (it is not); tail line miscounted                                       | Keep UI/override/degradation ideas |
| skeptic-minimal | Clean cut + ten guards; CMP mechanism with strict in-gap test (13 own-line hits vs ~0.006 chance rate); G2 anti-0.01-trap; G3 rank-1 must lose; G10 print-precision abort; unconditional mirror clause; energy evidence (all 1876 losers: score 396, energy 40); "one opponent species" said out loud; reconciliation of the three numbers                                                                              | Its own Step 3 rule (abs(n - 2048)) selects Feraligatr (Shadow) 2v2 at 148.71, not Annihilape; G8 misses the mirror's Foul Play 58->59 breakpoint at +1 Def; "171 of 173 atk values below" is 68; 148.10 strictly beats only 14.6% of Annihilape's own IV grid (hundo needs 150.69) and no coverage ladder is printed; G5 "4/4 modes" is guaranteed for any CMP line because both baked cohorts are low-attack; example spread 6/9/7 dominated by 7/6/10; G6 dedup before G5; not a pure function of the blob (CMP needs live gamemaster)                  | Winner as the skeleton             |

Why the skeptic skeleton wins: it is the only design whose every printed
claim is a per-cell, 100%-both-ways fact plus a closed-form mechanism, and
whose failures were all in the SELECTION and PRESENTATION layers (fixable
below) rather than in the evidence layer. The expert-first Build Brief has
the right genre shape but its fork objective cannot regenerate its own
example; the product-first Call has the right page furniture but its
central sentence is false by construction; the cluster floor is a fitted
number that reads as fitted.

Grafts (from -> into the winner):

| Idea                                                            | From           | Status in this plan                             |
| --------------------------------------------------------------- | -------------- | ----------------------------------------------- |
| Ascending rung ladder with exact cell ownership                 | expert-first   | Section 3 "Rungs"; section 4 stage 6            |
| (def, hp) substitution frontier, printed in full                | expert-first   | Section 3 "Bulk"; stage 9                       |
| Bulk fork as a second stat triple (fork B)                      | expert-first   | Field 8 "Alternative target"; stage 9b          |
| "Changes the score, not the matchup" as first-class             | all four       | Stage 10, with a CLEAN score step (not a mean)  |
| Rank-1 adjudication with materiality gate                       | expert/product | Stage 11                                        |
| Degradation ladder with printed counts                          | product-first  | Stage 12                                        |
| Human override block (`body` beats machine; `target` re-scored) | product-first  | Stage 13; open decision D4                      |
| Scenario admission (n_sharp>=6 and n_patterns>=8)               | clusters-first | Stage 1; also the "degenerate scenario" label   |
| All-scenario cluster partition as corroboration line            | clusters-first | Stage 14 (optional line, never the headline)    |
| HP stretch rung, made exact                                     | clusters-first | Stage 9 co-gate search on HP as well as Def     |
| Coverage ladder over the opponent's own 4096 grid               | critiques      | Stage 5; strict wins, ties counted, guard G-tie |
| Buff-stage breakpoint test (opponent's own kit only)            | critiques      | Stage 4b                                        |
| Opponent rank printed inline; top-50 gate for headline          | critiques      | Stage 2 gate G-rank                             |
| Example spreads by a printed rule, dominance-checked            | critiques      | Stage 8                                         |
| Pool dedup of byte-identical columns                            | critiques      | Stage 1                                         |
| Blob stamping of opponent facts (replay purity)                 | critiques      | Phase 0 prerequisite                            |
| Generality sweep BEFORE the renderer, with a go/no-go bar       | ship critic    | Phase 0 item 4; decision D12                    |

## 2. The verdict form

One section per moveset arm, headed "Build brief", placed as the first
block of the IV Recommendations zone (above the scatter controls, outside
the collapsed `<details id="dd-analysis">`) -- placement is decision D11,
this is the recommendation -- rendered inside `scripts/deep_dive.py`.
Fields, in order; a field that has nothing true to say prints its silence
sentence (in the last column) rather than nothing.

| #   | Field              | Content                                                                                                                                                                                                     | Silence rule                                                                                                                                                                                                                                                                                                                                                                                                                |
| --- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Header             | Species, league, moveset arm, level cap, bake date, gamemaster stamp, rankings snapshot, opponent-IV cohorts baked, pool size                                                                               | Always printed                                                                                                                                                                                                                                                                                                                                                                                                              |
| 2   | Floor              | ONE attack (or def/hp) clean cut: printed value, mechanism, opponent + its IVs, pool count and %, grunt/catch count, modes and movesets it holds in; if one base species owns it, say so                    | "No floor: N of M contested matchups separate cleanly on any single stat; too few to recommend against. Build for stat product."                                                                                                                                                                                                                                                                                            |
| 3   | Coverage           | For a CMP floor: the line vs rank-1 / PvPoke-default / 10-10-10 / grid median / hundo / 12-12-12 / max opponent build; per row: % of the opponent's grid STRICTLY beaten, tied-spread count, focal clearers | Omitted for non-CMP floors, with the reason branched on the mechanism kind: a BREAKPOINT floor says the ladder measures a priority line and this floor does not move with the opponent's attack; only an UNATTRIBUTED floor says the mechanism is unattributed. (Corrected 2026-09-12: the original wording conflated the two and printed "mechanism unattributed" under an attributed SUPER_POWER breakpoint on Melmetal.) |
| 4   | Rank-1 check       | Rank-1 spread, which side of the floor, lowest MATERIAL rung it misses, its total wins                                                                                                                      | "Rank-1 already clears the floor; there is no trade to make."                                                                                                                                                                                                                                                                                                                                                               |
| 5   | Rungs above        | Ascending clean rungs above the floor with pool >= 25%: value, cells owned (at most 3 names per row, then "+N more"), mechanism, modes, movesets, co-gates; plus a machine-generated tail sentence          | "No further clean rung above the floor keeps 25% of the grid."                                                                                                                                                                                                                                                                                                                                                              |
| 6   | Rungs below        | Ascending material rungs below the floor (10%..90% of grid): what "almost every build" already clears and rank-1 does not; same name cap                                                                    | "No material rung below the floor."                                                                                                                                                                                                                                                                                                                                                                                         |
| 7   | Bulk               | Whether any def/hp clean cut exists; the hp -> max-def frontier inside the floor; Def and HP co-gates inside the floor (100% of the sub-rectangle, printed with the rate outside it); no band means         | "No clean Def or HP cut on this dive (0 of N contested cells)." (always printed when true)                                                                                                                                                                                                                                                                                                                                  |
| 8   | Alternative target | The (Def, HP) rectangle disjoint from the floor that guarantees the most cells the floor cannot: stat triple, member count, the cells it guarantees, the cells it gives up, "no spread satisfies both"      | "No bulk rectangle of >= 100 spreads guarantees a cell the floor cannot."                                                                                                                                                                                                                                                                                                                                                   |
| 9   | Example spreads    | Three, by printed rules: best SP clearing the floor; most cells won among clearers with SP >= 95%; bulkiest (max def x hp) among those; per-scenario wins                                                   | Fewer if the rules coincide; never fewer than one                                                                                                                                                                                                                                                                                                                                                                           |
| 10  | Cost               | Reverse single-stat clean cuts (if any) + field 8's give-up list + the exact cell diff of example #2 vs rank-1, opponent rank inline, plus the 0v0/even-shield loss list                                    | "This test found no reverse clean cut; the bulk cost is field 8's list and the diff below."                                                                                                                                                                                                                                                                                                                                 |
| 11  | Mirror             | Per shield count, vs the named mirror build (cohort + seat stated), win rate below/above the floor, the mirror's own rungs, whether examples clear them; scores permitted here                              | "Mirror not in pool."                                                                                                                                                                                                                                                                                                                                                                                                       |
| 12  | Score only         | Cells won (or lost) by every spread where the score steps cleanly by >= 60 at an achievable attack value: value, min-above / max-below, rank                                                                | "None."                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 13  | Not claimed        | Count of contested cells with no clean rule, with the top-ranked ones named and their win rate inside the floor (recomputed, guarded)                                                                       | Always printed                                                                                                                                                                                                                                                                                                                                                                                                              |
| 14  | How sure           | Mechanical only: clean counts, per-mode cuts, per-moveset cuts, coverage percentile, the CMP shadow-strip caveat, single-owner sentence when it applies, cohorts checked, corroboration line                | Always printed                                                                                                                                                                                                                                                                                                                                                                                                              |
| 15  | Provenance         | "clean cut" defined; how it relates to the page's "flips at" and "best rule" numbers, with this dive's three values for one opponent; the engine's CMP tie convention with line references                  | Always printed                                                                                                                                                                                                                                                                                                                                                                                                              |

Confidence language: none. No adjective (strong, solid, definitive, best,
recommended, consistent, reliable, worth) and no comparative about which
build is better. Confidence is the printed fraction with the failing modes
named, the coverage percentile, and the pool count. Banned-word scan is a
render gate (stage 15), not a style note.

Register: counts, stats, named opponents with rank, shield scenarios,
mechanism sentences with the move named. Battle scores appear only in
field 2's evidence line (the constant losing score), field 11 (the
mirror's 0v0 line, where the 503-vs-500 pair is the claim) and field 12
(where they are the claim). Enforced by G-scores (typed number tokens,
stage 15), not by eye. No sentence containing "mean", "average" or "on
average" anywhere in the block (G-means). No silhouettes, K, accuracies,
or source paths in the reader-facing block; the guard audit goes in a
collapsed evidence block beneath it.

Ordering rationale: floor -> coverage -> rank-1 is the genre's opening
("most X should have at least Y; the rank-1 does not"); rungs above/below
is the ladder; bulk / alternative target / examples / cost is the price
and the fork; mirror and score-only are the genre's mandatory side
sections; not-claimed, how-sure and provenance close.

## 3. The worked Shadow Sableye GL brief, as rendered

Every number below is from `ms0`, `pvpoke` mode, level cap 50 unless the
line says otherwise. Recomputed for this document unless marked (cit.).

```
BUILD BRIEF -- Shadow Sableye, Great League
Shadow Claw / Drain Punch + Foul Play (1 of 4 moveset arms on this page)
Level cap 50. Bake 2026-09-11. Opponent pool: 76 entries (GL top-50 +
Community Showcase). Opponents at PvPoke-default IVs (also checked at
rank-1 IVs, with and without focal baiting). Rankings snapshot 2026-09-11.
Stats are shadow-effective (attack x1.2 applied).

FLOOR        Atk >= 148.10        2220 of 4096 spreads (54.2%)
             Mechanism: charge-move priority vs Annihilape. A PvPoke-default
             Annihilape (4/13/13, L17.0) has 123.38 attack; 1.2 x 123.38 =
             148.05 sits inside the boundary (148.01, 148.10]. Our damage
             into it does not change across the boundary (Shadow Claw 11,
             Foul Play 72, Drain Punch 15 on both sides).
             Owns: 0v1 Annihilape (rank 30; the Close Combat + Rage Fist
             pool entry is the same column). After collapsing pool
             variants this floor is owned by ONE base species; if
             Annihilape leaves the pool the floor has no owner.
             Below 148.10: 0 of 1876 spreads win; every one scores 396
             and ends with 40 energy. At or above: 2220 of 2220 win
             (627-666), all ending at 0 energy -- one fight on each side,
             not a plan switch.
             Holds: clean in 4 of 4 modes (cut 148.10 at PvPoke IVs,
             146.75 at rank-1 IVs) and on 4 of 4 moveset arms (same cut,
             same 2220). Shadow Annihilape (rank 31) is NOT owned: bait-
             only (no-bait: 53% / 44% of clearers win) and dirty on the
             other three arms (47%).
             Rocket-grunt encounters (Shadow Sableye is untradeable; no IV
             floor assumed): 1 encounter for a 50% chance, 2 for 75%.
             No clean Def or HP condition exists for this cell.
             Caveat: this line exists because charge-move priority ignores
             the shadow x1.2 -- our engine's and PvPoke's convention, not
             verified against the live game.

COVERAGE     What the floor beats, over Annihilape's own 4096 GL spreads
             (strict: the Annihilape on the line loses priority to the
             "beats" share, ties with the "ties" count):
             (CMP vs Annihilape)                    line    beats  ties  focal
               rank-1 Annihilape (2/15/15)        146.73    3.6%    88   2657
               PvPoke default (4/13/13)  <- floor 148.05   14.6%   132   2220
               10/10/10 (raid/research floor)     149.77   43.1%   122   1511
               median Annihilape build            150.05   50.0%    57   1405
               hundo (15/15/15)                   150.69   58.3%    79   1109
               12/12/12 (lucky trade)             151.07   66.7%   154    983
               ties the max-attack Annihilape
               (15/0/0; 25 spreads)               155.32   99.4%    25     43
             "focal" = our spreads clearing that line. No focal spread
             strictly out-prioritises every Annihilape: 43 clear 155.32
             and tie the top 25. 148.10 is the PvPoke-default line, not a
             guarantee: a hundo Annihilape out-prioritises everything
             under 150.69. The best-SP spread clearing 150.69 is 14/7/15
             L44.0 (94.3% of rank-1 SP).

RANK-1       0/15/15 at L49.5 (141.76 / 105.42 / 127 HP) misses the floor
             by 6.35 attack and clears 0 of the 40 clean attack cuts on
             this dive. The lowest material rung it misses is 143.60
             (charge-move priority vs a PvPoke-default Shadow Sableye
             mirror, 1v0); it also loses priority to a default Thievul
             (143.86) and Florges (144.09). It wins 367 of 684 cells. It
             is a member of the Alternative target below.

RUNGS ABOVE  (ascending; pool = spreads clearing it; modes = of 4)
 148.55  1v1 Sableye (Shadow) mirror (r34)   1970 (48.1%)  modes 2/4
         Foul Play 58 -> 59 into the mirror after its Drain Punch (+1 Def:
         103.85 x 1.25). Holds only vs a PvPoke-default mirror; a rank-1
         mirror (0/15/15) denies it (9 of 4096 spreads win).
 148.71  1v1 + 2v2 Feraligatr (Shadow) (r32)  1940 (47.4%)  modes 2v2 4/4,
         1v1 3/4 (rank-1 Feraligatr: 31% already win below the cut)
         Charge-move priority: 1.2 x 123.88 (5/11/14, L19.5) = 148.65 in
         (148.64, 148.71]. Other arms: 2v2 at 146.34; 1v1 same. Co-gate:
         Def >= 96.63 here also buys 0v1 Feraligatr (r19): 100% of 1382
         clearers with that Def, 49% of the 558 without.
 149.69  1v1 Hippowdon (r46)                  1538 (37.5%)  modes 4/4
         Mechanism unattributed (not a priority line: 139.42; no damage
         step at any reachable stage). Other arms: dirty.
 150.25  1v1 Empoleon (Shadow) (r14)          1345 (32.8%)  modes 4/4
         Charge-move priority: 1.2 x 125.19 = 150.23. Same on all 4 arms.
 Beyond 150.25 there are 12 more clean rungs (15 cells), the highest at
 156.30. One keeps more than 25% of the grid and is bait-only: 2v2
 Tinkaton 150.61 (28.2%; lost by every spread without baiting). The other
 11 keep under 23%: 1v0 Tinkaton 151.22, 1v0 Florges 151.25, +12 more
 cells.
 Dropped: 1v2 Wartortle 148.64 (r110; holds in 1 of 4 modes).

RUNGS BELOW  (what most builds already clear; 10%-90% of the grid)
 143.60  1v0 mirror (r34)              87.1%  priority 143.60 (4/15/15)
 143.77  2v2 Azumarill (r24)           87.1%  unattributed; 4/4 modes
         2v2 mirror                          bait-only on other arms
 143.91  1v0 Kingdra (r45)             86.8%  unattributed; 4/4
         1v0 Toxapex (r126)
         2v1 Thievul (r16; 2 sets)           priority 143.86 (4/15/15)
 144.15  2v1 Florges (r15)             86.5%  priority 144.09 (6/13/14);
                                             Foul Play 43 -> 44 coincides
 144.91  1v1 Ninetales (r12)           79.8%  unattributed; 4/4
 145.58  1v0 Cramorant (r5)            73.0%  priority 145.50 (5/15/13);
                                             rank-1 Cramorant: 92% win below
 145.91  2v2 Empoleon (Shadow) (r14)   72.3%  unattributed; 4/4
 146.21  1v1 Kingdra (Shadow) (r47)    71.3%  priority 146.18 (5/15/12); 4/4
 147.02  1v2 Lapras (r37)              63.6%  unattributed; 3/4

BULK         No clean Def or HP cut exists on this dive (0 of 161
             contested cells; 40 are attack cuts). Inside the floor the
             trade is HP against Def (max Def per HP, all at 148.10+):
               HP 115 -> 105.74   117 -> 104.48   119 -> 102.94
               HP 121 -> 101.54   123 ->  99.50   125 ->  98.05
               HP 127 ->  95.93
             Within the 2220 clearers, cells won run 330-382. 698 clearers
             have 100+ Def; 86 have 100+ Def with 120+ HP.
             Co-gates inside the floor (every clearer in the sub-rectangle
             wins the cell; sub-rectangle >= 5% of the grid; opponent in
             the top 50; scenario not degenerate; rate without it shown):
               Def >= 99.72  (761 clearers)  2v2 Dondozo (r39)        44% without
               Def >= 100.55 (559)           1v1 Umbreon (r38)        73%
                                             2v2 Umbreon (r38)        87%
               Def >= 101.41 (377)           2v2 Araquanid (Shadow) (r44)  69%
               Def >= 102.02 (257)           1v1 Vigoroth (Shadow) (r43)   67%
                                             2v2 Vigoroth (Shadow) (r43)    2%
               HP  >= 121    (671)           1v1 Vigoroth (Shadow) (r43)   58%
                                             2v2 Umbreon (r38)        86%
                                             2v2 Dondozo (r39)        47%
                                             2v2 Araquanid (Shadow) (r44)  63%
               HP  >= 122    (449)           0v0 Mantine (r11)        52%
               HP  >= 123    (291)           0v1 Snorlax (r13)        58%
                                             1v1 Umbreon (r38)        77%
             These are sufficient conditions: the "without" rate is what
             clearers outside the sub-rectangle still win.

ALTERNATIVE  Def >= 101.41 and HP >= 125 (114 spreads, 2.8%; SP 95.1% to
TARGET       100%, rank-1 is a member; attack 141.76-145.47, so no spread
             satisfies both this and the floor).
             Rule: among (Def, HP) rectangles with >= 100 members and no
             floor clearer, the one guaranteeing the most contested cells
             the floor cannot (won by every member; by at most 1% of
             clearers); ties broken by member count; the printed cuts are
             the least attained values among members.
             Guarantees 9 cells the floor does not (at most 3 of 2220
             clearers win any of them): 0v0 Quagsire (r7), 0v0 Corviknight
             (Shadow) (r17), 0v0 Turtonator (r59), 0v0 Charjabug (r60),
             0v0 Stunfisk (r113), 0v2 Deoxys (Defense) (r28; degenerate
             scenario), 1v2 Charjabug (r60), 1v2 Rillaboom (r70), 2v1
             Bombirdier (r228). Three of the nine are top-50 opponents.
             Gives up 7 cells the floor guarantees (won by no member):
             0v1 Annihilape (r30; 3 pool entries, 2 distinct fights), 1v0
             Cramorant (r5), 1v1 Kingdra (Shadow) (r47), 1v2 Lapras (r37),
             2v2 Empoleon (Shadow) (r14).
             Members win 351-374 cells; floor clearers win 330-382.

EXAMPLES     (existence proofs; each rule is printed)
  best stat product clearing the floor:
    6/9/7   L50.0  148.23 / 101.54 / 121   SP 95.95% (#488)   371 cells
            misses the mirror 1v1 (148.55) and Feraligatr (Shadow) (148.71)
  most cells won among clearers with SP >= 95%:
    7/2/14  L49.5  148.79 /  96.35 / 126   SP 95.17% (#817)   382 cells
  bulkiest (max Def x HP) among clearers with SP >= 95%:
    10/13/11 L45.5 148.19 / 101.54 / 121   SP 95.93% (#501)   371 cells
  cells won by shield scenario (0v0 0v1 0v2 1v0 1v1 1v2 2v0 2v1 2v2):
    rank-1 0/15/15   36  8  4  63  36  23  76  70  51   = 367
    7/2/14           28 14  2  69  39  26  76  73  55   = 382
    6/9/7            27 13  3  68  35  23  76  73  53   = 371
  Clearers reach 1500 CP at lower level: median L48.0 (385 of 2220 at
  L45 or below) vs L50.0 below the floor (56 of 1876).

COST         This test finds no reverse single-stat clean cut (0 in 4
             modes x 4 arms x 3 stats). The bulk cost as a target is the
             Alternative target's 9 cells above. The cost as a cell diff:
             7/2/14 vs rank-1: 38 cells gained, 24 lost (two gained and
             one lost Aegislash (Shield) cell excluded: open engine
             divergence, see the mechanics note; 40 / 25 with them).
             Lost, top-20 opponents: 0v0 Quagsire (r7), 0v0 Empoleon
             (r10), 0v0 Corviknight (Shadow) (r17), 1v1 Mantine (r11),
             2v2 Empoleon (r10). Also lost: 0v0 Dondozo, Araquanid
             (Shadow), Hippowdon, Turtonator, Charjabug, Stunfisk, Cradily
             (Shadow), the 0v0 mirror; 0v1 Malamar (Mega); 0v2
             Deoxys (Defense), Malamar, Snorlax (Shadow); 1v1 Guzzlord;
             1v2 Hippowdon, Charjabug, Rillaboom; 2v1 Bombirdier; 2v2
             Kingdra, Cradily (Shadow).
             Gained, top-20: 0v0 Snorlax (r13), Thievul-IW (r16); 0v1
             Feraligatr (r19); 1v0, 1v1, 2v1, 2v2 Cramorant (r5); 1v1
             Ninetales (r12); 1v2 + 2v2 Mantine (r11); 2v1 Florges (r15),
             Thievul x2 (r16); 2v2 Empoleon (Shadow) (r14).
             The 0-shield is where attack builds pay: rank-1 wins 36 of
             76 there, 0/15/13 wins 37, every listed clearer 27-28.

MIRROR       vs a PvPoke-default Shadow Sableye (4/15/15, L47.0: 143.60 /
             103.85 / 125). Seat: our Sableye is the optimised row; the
             mirror opponent always baits. Win rate below -> at/above
             148.10:
               0v0   0.3% ->   0%   (rank-1 wins it at 503; the best
                                     clearer ties at 500)
               0v1  15.7% ->   0%
               1v0  71.9% -> 100%   priority line 143.60
               1v1     0% -> 88.7%  clean at 148.55 (Foul Play 58 -> 59)
               2v2  71.8% -> 100%   clean at 143.77
               0v2, 1v2: lost by every spread. 2v0, 2v1: won by every one.
             Against a rank-1 mirror (0/15/15): 1v0 and 2v2 won by every
             spread; 1v1 won by 9 of 4096; the attack floor buys nothing.

CHANGES THE SCORE, NOT THE MATCHUP  (clean score step >= 60 at one
             achievable attack value; won or lost by every spread on both
             sides)
 148.10  0v0 Annihilape (Shadow) (r31)   661 -> 888   won on both sides
 147.02  2v2 Corviknight (r4)            661 -> 747   won on both sides
 147.02  2v2 Lapras (r37)                677 -> 843   won on both sides
 144.15  0v0 / 1v1 / 2v2 Florges (r15)   113 -> 263 / 209 -> 327 /
                                          304 -> 404  lost on both sides
 143.91  2v2 Thievul (r16)               244 -> 440   lost on both sides
 148.77  2v2 Araquanid (r22)             419 -> 481   lost on both sides
 148.77  1v1 Moltres (Galarian) (r56)    419 -> 322   lost on both sides
 The often-quoted 0v0 Feraligatr (Shadow), 0v1 Thievul and 0v1 Hippowdon
 score movements are not clean steps (the score varies with bulk inside
 one attack value) and are not listed.

NOT CLAIMED  121 of the 161 contested matchups have no clean single-stat
             rule and are not claimed. Among them, inside the floor:
             0v1 Feraligatr (r19) 75%, 0v1 Electrode (Hisuian) (r35) 41%,
             0v1 Kingdra (r45) 43%, 0v1 Aegislash (Shield) 86% -- the
             Aegislash win is a window (147.56-154.03), and this dive
             carries an open Aegislash form-change difference from PvPoke
             (see the mechanics note).

HOW SURE     40 clean attack cuts, 0 Def, 0 HP (ms0, PvPoke IVs); the
             floor's partition is exact in all 4 modes and all 4 arms.
             After collapsing pool variants, this floor is owned by one
             base species (Annihilape, rank 30); if it leaves the pool
             the floor has no owner.
             The floor's number moves with the opponent's build (146.73
             at rank-1 IVs; 150.69 vs a hundo); the direction does not.
             Both baked opponent cohorts sit in the low-attack tail of
             Annihilape's grid (3.6% and 14.6% strictly beaten), so "4 of
             4 modes" is not robustness against attack-weighted builds;
             the coverage ladder is. Independent corroboration: the
             all-scenario cluster partition (Matchup clusters, K=2,
             silhouette 0.50) splits this grid at 148.71, one rung above
             the floor (cit.).
             Not checked: opponent IVs other than the two cohorts,
             post-match HP and shields, the level-51 view (its own
             Annihilape cut is 148.09, 2345 clearing), XL/dust cost.

PROVENANCE   This section's numbers are clean cuts (100% both ways).
             The page prints two other numbers for the same opponent:
             "flips at 145.91 Atk [2960 IVs]" under Threats (75/25 gate;
             740 of those 2960 lose) and "best rule 148.06" in Matchup
             clusters (most accurate split, errors allowed). 148.10 is
             the lowest attack any winning spread has.
             Priority ties: the coverage ladder counts an exact attack
             tie as NOT beaten. The engine itself is seat-dependent on an
             exact tie (battle.py:3454 drops priority and keeps the
             player-0-first order; :829 and :1648 give the tie to the
             attacker; :622, :854, :916 require a strict win), so a tied
             line is not a guarantee in either direction.
```

Numbers in the block that were cited rather than recomputed here: the
cluster corroboration (K=2, silhouette 0.499, floor 148.7107; reproduced by
two critics), the "flips at 145.91 / 2960 / 740" (three critics), and
"9 of 4096 win the rank-1 mirror 1v1" (recomputed: rank1 mode 1v1 cells
won = 9). The Aegislash window bounds 147.56-154.03 were recomputed this
revision (2020 winners), as were the strict coverage column, the tail
sentence, the L51 cut, the not-claimed percentages, the alternative
target, the co-gates and the cost diff.

Numbers this revision corrects in the previous draft of this document,
all recomputed from the blob: the coverage "beats" column was
tie-inclusive (5.7 / 17.8 / 46.1 / 51.3 / 60.3 / 70.4 / 100.0) and is now
strict (3.6 / 14.6 / 43.1 / 50.0 / 58.3 / 66.7 / 99.4) with tie counts;
"8 more clean rungs" beyond 150.25 is 12 rungs / 15 cells; the L51
Annihilape cut is 148.096558 (prints 148.09), not 148.10; the not-claimed
inside-floor rates were stale (Aegislash 83% -> 86%, Feraligatr 63% ->
75%, Electrode (Hisuian) 40% -> 41%, Kingdra 38% -> 43%); the mirror 0v0
line quoted the plain Sableye's 488 for the shadow mirror (best clearer:
500); the 143.91 rung dropped 1v0 Toxapex; the cost diff now excludes
the Aegislash cells (38 / 24) as G-caveat requires. Two corrections this
synthesis had already made to numbers the proposals printed: the
skeptic's "171 of 173 distinct atk values below 148.10" is 68 of 173;
the expert-first "Annihilape 0% of rest" is 30.9% at its fork and 0%
only at the cell's own cut, which is why the brief prints per-cell cuts
and never a fork-level necessity number.

## 4. The algorithm, end to end

Inputs: the replay blob only (score cubes `[4096, 9, 76]` per moveset per
mode; per-spread meta; L51 meta/scores; energy planes) plus, until Phase 0
lands, live gamemaster/rankings reads for opponent stats and ranks (see
guard G-purity). Win predicate is `gopvpsim.battle.is_win` everywhere
(`tests/test_win_boundary.py` scans for it).

| Stage | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | Sableye result                                                                                                                                                                                                                                                                 |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1     | Triage per cell: all-win / all-lose / contested. Dedup byte-identical opponent columns per scenario. Label scenarios with `n_sharp < 6 or n_patterns < 8` "degenerate" (still computed, never a headline source).                                                                                                                                                                                                                                                                                                                                                                                                                     | 278 / 245 / 161; Annihilape = CC+RF in 0v1; 0v2 (5/16) and 2v0 (1/2) degenerate                                                                                                                                                                                                |
| 2     | Clean cuts on atk, def, hp for every contested cell: `T = min stat over winners`; accept iff `(stat >= T) == win` elementwise. Record `n_pass`, the gap `(prev attained, T]`, and distinct attained values below T. Record the set of distinct base species owning each cut value (for G-owner).                                                                                                                                                                                                                                                                                                                                      | 40 atk, 0 def, 0 hp; 29 distinct atk values; 148.10 owned by 1 base species                                                                                                                                                                                                    |
| 3     | Per-cell status in every mode and every moveset arm: clean (own cut), dirty (win rates below/above the ms0 cut), all-win, all-lose.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | table in `scratchpad/judge/j1.out` section B                                                                                                                                                                                                                                   |
| 4a    | CMP label: build the opponent as the bake did (`resolve_opp_ivs` + `Pokemon.at_best_level`), `line = SHADOW_ATK_BONUS x cmp_atk` (focal shadow) or `1.0 x` (not shadow); label CMP iff `prev < line <= T` STRICTLY inside the gap.                                                                                                                                                                                                                                                                                                                                                                                                    | 13 cells own-line hits: Annihilape x3, Feraligatr (S) x2, Kingdra (S), Cramorant, Thievul x2, Florges, mirror 1v0, Empoleon (S) 1v1, Malamar (Mega)                                                                                                                            |
| 4b    | Breakpoint label: recompute `moves.damage` for each focal move into the opponent at the two attained values straddling T, at every DEF STAGE THE OPPONENT'S OWN KIT CAN REACH (stage 0 always; +1/+2 only if it has a self-Def buff), and at every focal ATK stage an opponent debuff can impose. Label BREAKPOINT iff an integer changes.                                                                                                                                                                                                                                                                                            | mirror 1v1: Foul Play 58 -> 59 at +1 Def (Drain Punch); Florges 2v1: Foul Play 43 -> 44 at stage 0 (coincides with CMP)                                                                                                                                                        |
| 4c    | Otherwise UNATTRIBUTED. Print the number with no mechanism clause; never invent one.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Hippowdon 1v1, Ninetales 1v1, Azumarill 2v2, Lapras 1v2, Empoleon (S) 2v2, Kingdra 1v0                                                                                                                                                                                         |
| 5     | Coverage ladder for each CMP rung: `1.2 x cmp_atk` over the opponent's own 4096-spread GL grid; print rank-1, default, 10/10/10, median, hundo, 12/12/12, max, each with the STRICT share of the grid beaten (`grid_atk < line_atk`), the tied count (`==`), and focal clearers. The max row is labelled "ties the max-attack <opp> (N spreads)" and never "any <opp>". G-tie refuses a "100.0%" cell unless the strict share is 100.0%.                                                                                                                                                                                              | Annihilape: 146.73 / 148.05 / 149.77 / 150.05 / 150.69 / 151.07 / 155.32; strict 3.6 / 14.6 / 43.1 / 50.0 / 58.3 / 66.7 / 99.4; ties 88 / 132 / 122 / 57 / 79 / 154 / 25                                                                                                       |
| 6     | Floor selection (see D1): among atk rungs that pass G-material (three clauses), G-rank (opponent PvPoke open-league rank <= 50, not mega/unranked), G-attributed (CMP or BREAKPOINT), G-direction (all 4 modes: win rate at/above T >= 0.90 and > below), G-scenario (not degenerate), G-caveat (opponent not in `mechanics_notice` set), pick the LOWEST rung whose pool is inside the decision band [25%, 60%]. Rungs above with pool >= 25% are "rungs above"; material rungs below are "rungs below". The tail sentence (count of rungs beyond, cell count, max value, max pool, named examples) is generated from the same list. | floor 148.10 (54.2%); above: 148.55, 148.71, 149.69, 150.25; beyond: 12 rungs / 15 cells, max 156.30, max pool 28.2% (bait-only); below: 143.60 .. 147.02                                                                                                                      |
| 7     | Print-precision: printed = `floor(T x 100) / 100`; assert no attained value in `[printed, T)` in the L50 grid AND no L51 attained value whose 2-dp rendering equals `printed` lies below T; else print 3 dp; else abort. Each level view prints its OWN cut (D8).                                                                                                                                                                                                                                                                                                                                                                     | L50: 148.1039982 -> "148.10", 2220. L51: 148.096558 -> "148.09", 2345 (the L50 literal selects 2220 on the L51 grid, not 2345)                                                                                                                                                 |
| 8     | Example spreads by three printed rules (best SP; most cells won with SP >= 95%; max def x hp with SP >= 95%), each dominance-checked against the others; per-scenario wins for each and for rank-1.                                                                                                                                                                                                                                                                                                                                                                                                                                   | 6/9/7, 7/2/14, 10/13/11                                                                                                                                                                                                                                                        |
| 9     | Bulk: def/hp clean-cut count; hp -> max-def frontier inside the floor; co-gate search on BOTH Def and HP, for the floor AND for every printed rung above: the least attained threshold t such that every clearer with `stat >= t` wins the cell, accepted iff the sub-rectangle holds >= 5% of the grid, the cell's rate inside the rung is < 90%, the opponent passes G-rank, G-scenario and G-caveat; printed with the win rate outside the sub-rectangle. No band means, no correlations.                                                                                                                                          | frontier printed; floor co-gates: 6 Def rows, 7 HP rows (section 3); rung 148.71: Def >= 96.63 for 0v1 Feraligatr. The clusters-first HP stretch rung (148.71 + HP >= 124) fails the 100% bar (98.3%, 88.9%) and its exact form (HP >= 125) holds 75 spreads, under the 5% bar |
| 9b    | Alternative target: over attained (Def, HP) pairs, rectangles `(def >= d) & (hp >= h)` with >= 100 members and no floor clearer; score = contested cells won by every member and by <= 1% of floor clearers; maximise score, then member count; print the least attained member values as the cuts, the guaranteed list, the give-up list (cells every floor clearer wins and no member wins), and both cells-won ranges. Silence sentence when the best score is 0.                                                                                                                                                                  | Def >= 101.41 & HP >= 125, 114 spreads, 9 guaranteed / 7 given up; rank-1 is a member                                                                                                                                                                                          |
| 10    | Score-only: degenerate-win or degenerate-lose cells where `min score at/above T - max score below T >= 60` (or the reverse) at an attained T; print T, the two scores, rank. Cohort means are never used.                                                                                                                                                                                                                                                                                                                                                                                                                             | 8 rows (section 3)                                                                                                                                                                                                                                                             |
| 11    | Rank-1 adjudication: side of the floor; lowest MATERIAL rung missed (materiality: the rung excludes >= 1% of the grid and is an attained value); total cells; the priority lines it loses; whether it is a member of the alternative target.                                                                                                                                                                                                                                                                                                                                                                                          | misses by 6.35; 0 of 40; loses priority to the default mirror; member of the alternative target                                                                                                                                                                                |
| 12    | Degradation ladder (evaluated in order; each prints its count): (a) no contested cells -> section omitted; (b) no clean cut on any stat -> "No floor" sentence; (c) clean cuts exist but none passes stage 6 -> print the ladder with no floor marked and say why each failed; (d) floor pool < 2% -> "too rare", withhold the floor label; (e) fewer than 2 modes / 2 arms baked -> cap the modes/arms columns and say so.                                                                                                                                                                                                           | not triggered                                                                                                                                                                                                                                                                  |
| 13    | Human override: new optional TOML block `[Species.League.brief]` with `body` (prose) and `target` (stat triple). `body` non-empty -> human text renders, machine result demoted to one labelled line. `target` non-empty -> stages 5-11 recomputed against the human floor; if it is not a clean cut, print "not a clean cut in this bake: N of M clearers win" instead of substituting. Both empty -> machine brief with an explicit "Auto-derived" label (written by this renderer, not inherited).                                                                                                                                 | both empty                                                                                                                                                                                                                                                                     |
| 14    | Corroboration line (optional): the all-scenario score-tier cluster floor if `choose_k` returns a partition with silhouette >= 0.4; printed as "the cluster partition splits at X", never as the floor.                                                                                                                                                                                                                                                                                                                                                                                                                                | 148.71 (cit.)                                                                                                                                                                                                                                                                  |
| 15    | Render gates over the assembled string and its typed tokens: banned-word scan (G-words); ASCII only; every printed number re-derived from the same arrays and compared to the string about to be rendered, percentages included (G-recompute); `rows + omitted == total` for every list AND `sum(names printed) + sum(N in "+N more") == cells` for every rung row (G-names); every count inside a truncation sentence re-derived from the list it summarises; no score-kind token outside fields 2, 11, 12 (G-scores); no sentence containing "mean" / "average" (G-means).                                                          | pass on the section 3 block (the previous draft failed G-recompute on four percentages, G-names on one row, and the tail-sentence count)                                                                                                                                       |

Guards, what each checks, what happens on failure, and the printed wording.
The three build-breakers (G-print, G-recompute, G-words) raise
`RuntimeError` with a required message format so an overnight corpus
render says what broke:
`<guard>: field=<field name> cell=<scenario> <opponent> printed='<string>'
recomputed=<value> (blob=<path> arm=<n> mode=<name>)`. A guard that lacks
a cell (G-words) prints `cell=-` and the offending word.

| Guard          | Checks                                                                                                                                                      | On failure                                                                            | Wording                                                                                                                              |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| G-clean        | `(stat >= T) == win` elementwise, both directions                                                                                                           | Cell has no single-stat claim; counted in "Not claimed"                               | "N of M contested matchups have no clean single-stat rule and are not claimed."                                                      |
| G-material-hi  | pool <= 90%                                                                                                                                                 | Rung dropped (below); never a floor                                                   | "A clean cut exists at X but N of 4096 spreads clear it, so it is not a build decision."                                             |
| G-material-lo  | pool >= 10%                                                                                                                                                 | Rung listed under "beyond" (above); never a floor                                     | "A clean cut exists at X but only N of 4096 spreads clear it, so it is not a build decision."                                        |
| G-material-gap | >= 20 distinct attained values below T (kills the 141.77-vs-141.76 line)                                                                                    | Rung dropped; never a floor                                                           | "A clean cut exists at X but only K distinct attainable values lie below it, so it separates N spreads from 4096 - N."               |
| G-rank         | Opponent base species has PvPoke open-league rank <= 50; megas/unranked excluded from floor and null rung                                                   | Rung printed with rank tag, ineligible as floor                                       | "(rank 110; not a floor candidate)" / "(mega; not a floor candidate)"                                                                |
| G-attributed   | CMP strictly inside the gap, or a damage-integer step at a reachable stage                                                                                  | Rung printed as "unattributed"; ineligible as floor                                   | "Mechanism unattributed."                                                                                                            |
| G-direction    | In every mode: win rate at/above T >= 0.90 and strictly greater than below                                                                                  | Rung printed with "bait-only" / "PvPoke IVs only" tag; ineligible as floor            | "holds in 2 of 4 settings (fails: no-bait)"                                                                                          |
| G-scenario     | Scenario not degenerate (n_sharp >= 6, n_patterns >= 8)                                                                                                     | Cells from it are listed with a "degenerate scenario" tag; never a floor              | "0v2 is near-hopeless here (1.9 of 76 won); its cells are reported, not recommended."                                                |
| G-caveat       | Opponent not in `mechanics_notice.CAVEAT_SPECIES` (today: Aegislash)                                                                                        | Cell excluded from floor/rungs/cost totals; named under "Not claimed" with the caveat | "(open engine divergence vs PvPoke; see mechanics note)"; cost line prints the excluded counts                                       |
| G-dedup        | Byte-identical columns collapsed before counting                                                                                                            | Counts use distinct fights; variants named on the row                                 | "(the Close Combat + Rage Fist entry is the same column)"                                                                            |
| G-owner        | Distinct base species owning the floor's cut value, after dedup                                                                                             | If exactly 1: the single-owner sentence is REQUIRED in fields 2 and 14                | "After collapsing pool variants, this floor is owned by one base species (X, rank N); if it leaves the pool the floor has no owner." |
| G-tie          | Coverage rows use strict `<`; a row may read "100.0%" only if the strict share is 100.0%; the max row is labelled by its tie count                          | RuntimeError (build-breaker) if a tie-inclusive 100% reaches the string               | "ties the max-attack X (N spreads); no focal spread strictly out-prioritises it"                                                     |
| G-names        | Per rung row: at most 3 cell names, then "+N more"; `names + N == cells` per row; `rows + omitted == total` per list; tail-sentence counts re-derived       | RuntimeError (build-breaker)                                                          | "+N more cells"                                                                                                                      |
| G-scores       | Every number is emitted as a typed token (score / count / pct / stat / rank / level); no `score` token outside fields 2, 11, 12                             | RuntimeError (build-breaker)                                                          | n/a                                                                                                                                  |
| G-means        | No sentence containing "mean", "average", "on average" in the reader block; no cohort-mean computation reaches a token                                      | RuntimeError (build-breaker)                                                          | n/a                                                                                                                                  |
| G-print        | Stage 7 two-grid print-precision test                                                                                                                       | 3 dp, then RuntimeError abort in the required format                                  | n/a (build-breaker)                                                                                                                  |
| G-recompute    | Every printed number (counts AND percentages AND stat values) equals its re-derivation from the arrays; row counts add up                                   | RuntimeError abort in the required format (a code bug, should be loud)                | n/a (build-breaker)                                                                                                                  |
| G-cmp-fresh    | For a CMP label, the opponent facts used are the ones stamped in the blob (Phase 0) or, before that, the label is dropped when the live line leaves the gap | Downgrade to "unattributed" + WARN; never abort a dive for a gamemaster refresh       | "mechanism unattributed (opponent build changed since the bake)"                                                                     |
| G-purity       | The render is a function of the blob; live reads (rankings for ranks, gamemaster for CMP) are stamped with their snapshot date                              | Byte-identity claim qualified in the provenance line until Phase 0                    | "Ranks and opponent builds from the 2026-09-11 snapshot."                                                                            |
| G-words        | No banned adjective/comparative; ASCII only                                                                                                                 | RuntimeError abort in the required format                                             | n/a                                                                                                                                  |
| G-trivial      | >= 2 modes and >= 2 arms in the blob before "N of N" is printed                                                                                             | Column capped and labelled                                                            | "one moveset arm simmed; cross-arm robustness not measured"                                                                          |

Why no cohort means anywhere, including inside the floor: at the floor,
below-floor spreads average def 100.45 / hp 120.9 and above-floor 98.37 /
118.4 (cit.); every printed "cost" in the clusters-first and product-first
cards was best explained by def or hp, not by the floor. The same
confound lives INSIDE the floor: across the HP bands 112-115 -> 124-127
among the 2220 clearers, mean Def falls 100.19 -> 95.85 and mean attack
151.93 -> 149.59 (corr(atk, def | floor) = -0.388, corr(atk, hp | floor)
= -0.383), so the previous draft's "cells won rise with HP" was a
composition statement about spreads that also have less attack and less
Def, and is deleted. The only cost constructions allowed are reverse
clean cuts, the alternative target's exact give-up list, and an explicit
cell diff between two named spreads; the only bulk constructions are the
exact frontier and exact co-gates.

## 5. Phasing

Smallest shippable first. Nothing here simulates; everything is verified
by `scripts/replay_analysis.py` replaying the Sableye blob to a scratch
path and diffing. No publish without Michael's explicit per-instance go,
and none of it runs while a bake is on the machine. Every guard and every
Phase 0 item ships in the same commit as a test that fails without it
(repo testing policy); the Phase 1 list names them.

### Phase 0 (prerequisites, own commits)

1. Blob stamping: at bake time write per opponent, per opponent-IV mode:
   IVs, level, atk/def/hp, `cmp_atk`, types, PvPoke rank, rankings date,
   gamemaster hash. Additive schema change in the deep-dive save path
   (`scripts/deep_dive.py` where `moveset_data` is assembled; the L51
   view already stores a parallel meta). Test: a replay of a stamped blob
   never calls `load_gamemaster` / `load_rankings` (monkeypatch both to
   raise). Until this lands, G-purity prints the qualified invariant.
2. Flag the loose number where it renders: in the Threats "flips at"
   bullets print the pass-group win rate ("145.91 Atk [2960 IVs, 75% of
   them win]"). `scripts/deep_dive_analysis.py` is NOT in the engine hash
   (`scripts/sweep_cache.py` `_ENGINE_FILES`), so this is render-side.
   Test: fails without the change (pin "2960 IVs, 75%" on the Sableye
   blob). Do NOT change `pass_winrate_min` yet (D6).
3. `scripts/mechanics_notice.py`: export `CAVEAT_SPECIES = ('Aegislash',)`.
   Test: the tuple is non-empty and each entry names a species the
   notice text mentions (positive control: emptying it fails).
4. Generality sweep, BEFORE any renderer code: run stages 1-6 and 9b (the
   compute core of Phase 1, with every selection constant passed as a
   parameter) over the 82 Great League replay blobs on disk (74 distinct
   species x shadow arms; newest blob per arm), at `nice -n 19`, only
   while no bake is running. Writes
   `userdata/analysis/<date>_brief_sweep/yield.md`: one row per arm with
   contested count, clean atk/def/hp counts, rungs surviving each stage-6
   gate, floor found y/n, floor pool %, floor axis, alternative-target
   found y/n; plus the corpus distribution of eligible-rung pool % and
   score-step sizes, from which the [25%, 60%] decision band, the 10-90%
   materiality bar, the >= 20-attained-values clause and the >= 60 score
   step are set (today all four are calibrated on one species). The
   ship critic's spot check (Deoxys-D, Melmetal, Furret, Altaria all
   split on hp/def with poor single-axis fits) predicts a low attack-axis
   yield. Pin the table in DEVELOPER_NOTES. Test:
   `test_brief_sweep_yield` asserts the table has one row per arm on disk
   and that the number of arms with a floor is >= the measured value
   minus 0 (a floor, updated only by re-running the sweep). Then Michael
   decides D12 before Phase 1 starts. Effort: one session; no sim time;
   blob reads only.

### Phase 1: compute core (`scripts/deep_dive_brief.py`, new)

Stages 1-5, 7, 9, 9b, 10, 11 (the sweep in Phase 0 item 4 already
exercises 1-6 and 9b; Phase 1 finishes and pins them). Pure numpy over
the blob dict plus the stamped opponent facts. Tests
(`tests/test_deep_dive_brief.py`, marked `local_artifacts` where they
read the blob), each pinned to values recorded in this document and
failing without the code:

- clean cuts on Sableye ms0/pvpoke: exactly 40 atk / 0 def / 0 hp; the
  Annihilape 0v1 cut is `148.1039982` with n=2220, 0 of 1876 below.
- negative controls: 141.77 fails G-material-gap (and G-material-hi);
  Aegislash (Shield) 0v1 fails G-clean (window); Wartortle 1v2 fails
  G-direction; Malamar (Mega) 0v0 fails G-rank; 0v2 Annihilape (Shadow)
  fails G-scenario.
- G-caveat: on a synthetic cube where an Aegislash column IS a clean cut
  (no real Sableye cell qualifies: all 40 clean cuts are non-Aegislash),
  the cut is excluded from the rung list and named under "Not claimed"
  with the caveat tag; positive control on the real blob: with
  `CAVEAT_SPECIES` monkeypatched to `()`, the 7/2/14-vs-rank-1 cost diff
  changes from 38 / 24 to 40 / 25 and the caveat tag disappears.
- G-dedup: Annihilape and Annihilape (Close Combat+Rage Fist) collapse in
  0v1 (identical columns), and 2v1 Thievul's two sets do NOT (distinct
  columns; they collapse only in 2v2).
- G-owner: the 148.1039982 cut is owned by exactly one base species and
  the sentence is emitted; on a synthetic cube with two owners it is not.
- CMP: Annihilape line 148.0531 inside (148.0106, 148.1040]; Wartortle
  line 129.14 NOT inside its gap; Feraligatr (Shadow) line equals plain
  Feraligatr's at the same IVs.
- breakpoint at buff stage: mirror 1v1 148.5540 labelled Foul Play 58->59
  at +1 Def; the same test at stage 0 only must NOT label it (records the
  pre-fix behaviour).
- print guard, pinned pair: L50 `148.1039982 -> "148.10"`, 2220; L51
  `148.096558 -> "148.09"`, 2345; the L50 literal applied to the L51
  grid selects 2220, not 2345; `+1 ulp` literal `148.71072` selects 1925
  not 1940.
- coverage, strict: Annihilape grid min/max lines 145.21 / 155.32; the
  seven rows pin (strict %, ties, focal) = (3.6, 88, 2657), (14.6, 132,
  2220), (43.1, 122, 1511), (50.0, 57, 1405), (58.3, 79, 1109), (66.7,
  154, 983), (99.4, 25, 43); G-tie: a tie-inclusive 100.0% on the max
  row raises; the max row's label contains "ties".
- score-only: Annihilape (Shadow) 0v0 at 148.10 is a clean step 661->888;
  Feraligatr (Shadow) 0v0 is NOT (max-below 500 > min-above 472).
- rank-1: 0/15/15 clears 0 of 40; lowest material rung missed 143.60;
  it is a member of the alternative target.
- alternative target: Def >= 101.4055 & HP >= 125, n=114, 9 guaranteed
  cells (named), 7 give-ups (named), disjoint from the floor; the
  rectangle `def >= 103.02 & hp >= 125` (n=54, 10 cells) is rejected by
  the >= 100 clause (records why the rule has a size floor).
- co-gates: floor co-gates are exactly the 13 rows in section 3 (6 Def,
  7 HP) under the 5% / <90% / rank / scenario / caveat filters; rung
  148.7107 yields Def >= 96.63 for 0v1 Feraligatr (1382 at 100%, 558 at
  49.1%); the HP stretch rung (148.7107 + HP >= 124) is rejected with
  measured rates 0.983 / 0.889 / 1.000.
- not-claimed rates: 121 cells; inside-floor rates pin to 0.746 / 0.409 /
  0.430 / 0.858 for Feraligatr / Electrode (Hisuian) / Kingdra /
  Aegislash (Shield).
- G-recompute self-test: corrupt one printed count AND, separately, one
  printed percentage in the NOT CLAIMED field AND one stat value in the
  frontier; each must raise with the required message format naming the
  field, the printed string and the recomputed value.
- G-names self-test: drop one name from the 143.91 row (4 cells) without
  adjusting "+N more"; must raise.
- G-scores self-test: emit a score token in field 5; must raise.
- G-means self-test: inject "on average" into field 7; must raise.
- G-trivial: on a one-arm synthetic blob the arms column is capped and
  labelled.
- degradation ladder: a synthetic cube per rung (a)-(e) renders its
  sentence with the right count.

### Phase 2: selection + render

Stages 6, 8, 12, 13, 15 and the HTML. Insert in
`scripts/deep_dive_lib/render.py` just before the results section
(~line 1306), per moveset arm, outside `<details id="dd-analysis">`
(line 1354) -- or inside it, per D11. Explicit provenance markup (an
`authored-auto` wrapper with a visible "Auto-derived" label and the blob
stamp) -- do not rely on `_authored_by_class`, which only decorates TOML
narrative blocks (`scripts/deep_dive_rendering.py:1318-1341`). Add
`CLEAN_CUT_TIP` beside `BOUNDARY_RULE_TIP` / `BEST_RULE_TIP`
(`deep_dive_rendering.py:1051-1065`) and make the cross-reference
three-way; delete the two tips' direction sentence (measured backwards on
this dive: 145.91 < 148.06 < 148.10). Numbers are assembled as typed
tokens (`Num(kind, value, field)`) so G-scores and G-recompute operate on
the token list, then the string. Tests: `tests/test_scenario_vocabulary.py`
gains the third label; a rendered-artifact test pins the Sableye brief's
floor line, rungs, alternative target, and "Not claimed" count; a
synthetic-cube test renders each degradation rung; banned-word and ASCII
gates have a positive control (inject "definitive" -> RuntimeError).
`docs/concepts.md` gains "clean cut", "rung", "co-gate", "alternative
target", "coverage ladder", "build brief"; retire "band" for "cluster".

### Phase 3: reconcile the neighbouring surfaces (own commits, corpus re-render)

Each item below rewrites text on every published dive page (135
`*-league` page directories under `userdata/website` at the time of
writing; the bake in progress adds more) and forces the corpus
re-render. The first two are Michael's call (D10); the third is a defect
fix and is not.

- `scripts/deep_dive_narrative.py:1444-1517` `_render_rank1_self_check`:
  replace with stage 11 (materiality gate kills "needs 141.77, has
  141.76", which separates 3 spreads from 4093). Test records the pre-fix
  string. Changes every page whose rank-1 misses a 75/25 boundary. (D10)
- IV Flavor Guide: drop `[Recommended]` and "almost any will do" from the
  min-over-opponents General tier (`deep_dive_analysis.py:748-750` feeds
  it; badge rendered at `deep_dive_narrative.py:1368` and `:1399`); the
  brief owns the one `[Recommended]` badge. `_catch_phrase`
  (`deep_dive_narrative.py:42-58`) stops rendering "almost any will do"
  for pools under 90%. Changes every page. (D10)
- `scripts/deep_dive_lib/render.py:757-795` `_ensure_rc`: label card
  poles by what seeded them so "-> build Max Bulk or Max Bulk" (6 of 15
  Threats rows) cannot render; add a "clears the brief floor" flag. This
  changes every dive card in the corpus (re-render, not re-sim); it is
  a defect fix, not a judgement call, and is not on the D-list.
- `scripts/patch_dive_species_narrative.py:55`: marker
  `<div class="controls">` has not matched the renderer's
  `<div class="controls" id="dd-scatter">` (`scripts/deep_dive.py:2285`)
  since 2026-06-23, and shadow slugs resolve to the wrong TOML. Fix or
  retire; add a change-propagation test that the marker exists in
  renderer output. The brief does not use this path.

### Phase 4: corpus re-render and publish

The generality sweep has moved to Phase 0 item 4; this phase is the
corpus re-render (sets `userdata/.cards_rerender_pending`, which does not
currently exist), the four ship gates, the D12 yield check re-run on the
final code (the Phase 0 table is re-generated and diffed; any arm whose
floor changed is listed), and the publish ask. Test: the re-generated
yield table equals the Phase 0 table row-for-row, or the diff is
explained in the commit.

Effort: Phase 0 two sessions (the sweep is the second); Phase 1 one to
two; Phase 2 one to two; Phase 3 one to two; Phase 4 one. Seven to nine
sessions, none needing sim time. The proposals' 2-3 session estimates
were low by 2-3x because every one of them bundled three already-shipped
surfaces with the new section. If D12 comes back "no-go", the spend
stops after Phase 0 (two sessions) with the flag on the "flips at" line,
the caveat export and the yield table as the deliverables.

Contracts touched:

| Contract                                  | Effect                                                                                                                                                              |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_win_boundary.py`              | New module must use `is_win`; already enforced by the tokenize scan                                                                                                 |
| `tests/test_scenario_vocabulary.py:26-35` | Two-label contract becomes three-label; direction sentence removed                                                                                                  |
| Replay byte-stability (DEVELOPER_NOTES)   | Holds unconditionally only after Phase 0 stamping; qualified until then                                                                                             |
| Blob schema                               | Additive: opponent facts block; old blobs render with G-purity's qualified line                                                                                     |
| `docs/threshold_schema.md`                | New optional `[Species.League.brief]` block (`body`, `target`); never written programmatically; `.githooks/pre-commit` `authored_by="ai"` scan still applies to it  |
| gobattlekit export                        | Untouched: `export_thresholds.py` reads the blob's resolved anchors (`threshold_registry`), not `find_matchup_boundaries` (grep-verified); the brief writes neither |
| Sweep cache / engine hash                 | Untouched: no file in `_ENGINE_FILES` changes                                                                                                                       |
| ML IV guides / cards                      | Phase 3 pole relabel changes every card; re-render, not re-sim                                                                                                      |
| Ship-mode narrative policy                | Brief is a renderer; no Claude prose in TOML; `[Species.verdict]` untouched and its name not reused                                                                 |
| IV Flavor Guide (every page)              | D10: loses the `[Recommended]` badge and the General-tier catch phrase                                                                                              |

## 6. Open decisions for Michael

| #   | Decision                                                                                                                                                                                                                                                                               | Recommendation                                                                                                                                                                                                                                                                                                                                                                                         |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| D1  | Floor selection rule: lowest eligible rung in the decision band [25%, 60%] (gives 148.10), vs the abs(n - 2048) rule (gives 148.71 Feraligatr (S) 2v2), vs the cluster floor (148.71)                                                                                                  | Lowest-in-band. It is the genre's "at least X" line, it is the meta-relevant flip every critic converged on, and its sensitivity is printable (band [25,55] moves it to 148.55, which then fails G-direction). Pin the band constants from the Phase 0 sweep and print them in the evidence block.                                                                                                     |
| D2  | Which coverage line is THE printed floor for a CMP rung: PvPoke-default (148.10, 54% of grid, strictly beats 14.6% of Annihilape builds) or grid-median (150.05, 34%, beats 50.0%)                                                                                                     | Print the PvPoke-default line as the floor (it is what PvPoke and every reference tool quote) and the whole ladder beside it with the strict "beats" and "ties" columns. Do not silently promote the median line; it is a different pool.                                                                                                                                                              |
| D3  | Opponent rank gate: PvPoke open-league rank <= 50, or usage share from `docs/tournament_data` via `scripts/worlds_meta.py`                                                                                                                                                             | Rank <= 50 now (already in the render path); usage weighting later as a printed second column, never as a hidden weight.                                                                                                                                                                                                                                                                               |
| D4  | Human override: new TOML block `[Species.League.brief]` (schema change) vs no override (machine-only, labelled)                                                                                                                                                                        | Add the block. `body` wins outright; `target` is re-scored and confirmed. It is the only way expert prose ships in this slot under the narrative policy.                                                                                                                                                                                                                                               |
| D5  | Multi-moveset: one brief per arm vs one brief on the intersection                                                                                                                                                                                                                      | Per arm, labelled, with the other arms' cut for the same cell on each rung row (as in section 3). One page-top box was the product-first design and it cannot be honest: ms1 shares 9 of 23 cells with ms0.                                                                                                                                                                                            |
| D6  | The shipped 75/25 "flips at" engine: fix `pass_winrate_min` to the clean-cut test, or keep it and flag it                                                                                                                                                                              | Flag now (Phase 0 item 2, render-side, no hash bump). Replace it with clean cuts in a later commit once the Phase 0 sweep shows how many dives lose all their bullets under 100%/0%; that replacement changes the "build target" noun's owner and the two tooltips.                                                                                                                                    |
| D7  | Rocket-grunt encounter model for shadows (IV floor, untradeable) vs the wild-uniform catch model                                                                                                                                                                                       | Print encounter counts under the uniform model with the source named; verify the grunt IV floor before the corpus re-render and switch the model if it is not 0.                                                                                                                                                                                                                                       |
| D8  | Print the L51 view's own cuts, or print 3 dp when L50 and L51 disagree at 2 dp                                                                                                                                                                                                         | Own cuts per level view (148.10 at L50 with 2220; 148.09 at L51 with 2345); the page already has the toggle. The pair is a pinned fixture in Phase 1 so the two views can never be quoted with one number again.                                                                                                                                                                                       |
| D9  | Live-game CMP shadow-strip assumption (`battle.py:2720-2729`): ship with the caveat sentence, or hold until verified                                                                                                                                                                   | Ship with the caveat on every CMP row. Record the open question in DEVELOPER_NOTES; a community-sourced confirmation would retire the sentence.                                                                                                                                                                                                                                                        |
| D10 | May the brief take the page's single `[Recommended]` badge, retiring the IV Flavor Guide's General-tier badge and its "almost any will do" catch phrase, and replace the rank-1 self-check's shipped output? Affects every published dive page (135 today; the running bake adds more) | Yes to all three. Two [Recommended] labels on one page is the contradiction the reader sees first (today's General tier says "almost any will do" on a dive with a 54% floor). Ship them as separate Phase 3 commits so any one can be reverted alone.                                                                                                                                                 |
| D11 | Placement: the brief renders above the scatter as the first block of IV Recommendations on every dive, or inside the existing collapsed `<details id="dd-analysis">` IV Recommendations block                                                                                          | Above the scatter, outside the details, on dives where a floor or an alternative target exists; INSIDE the details on dives that print only the negative sentence (so a "No floor" page does not lead with an empty section). If D12 is "no-go", inside everywhere.                                                                                                                                    |
| D12 | Go/no-go from the Phase 0 sweep: the minimum share of GL arms that must produce an eligible floor (any axis) or an alternative target for the renderer (Phases 1-4) to be built at all                                                                                                 | Recommendation: build if >= 1/3 of the 74 arms produce a floor or an alternative target; between 1/6 and 1/3, build with D11's inside-the-details fallback and no corpus-wide D10 changes; below 1/6, stop after Phase 0 and keep the compute core as an analysis script (`userdata/analysis`), not a page section. The threshold is Michael's; the table is produced before any renderer code exists. |

## 7. What this will not do that a human expert can

- It cannot say WHY for 27 of the 40 clean cuts. CMP is closed-form and the
  damage integer pins breakpoints at reachable stages, but Hippowdon 1v1,
  Ninetales 1v1, Lapras 1v2, Azumarill 2v2 and others print with no cause.
  Flip attribution against a simulator plan switch (gap analysis T7/S13)
  stays open; the blob stores no move sequences. The constant-score,
  constant-energy losing side is evidence, not proof.
- It cannot see any opponent build except the two baked cohorts, both of
  which sit in the low-attack tail. The coverage ladder is closed-form and
  honest, but "covers most spreads, N exceptions" as the experts write it
  needs a per-threshold opponent-IV sweep (`robustness.opp_plane`) that
  this bake did not run. And on an exact priority tie it can only say
  "tied": the engine decides ties by seat, so a tied line is reported,
  never counted as beaten.
- It reports one attack floor and one bulk rectangle, not a full fork
  tree. The alternative target is the single best (Def, HP) rectangle by
  the stage 9b rule; the second-best (Def >= 103.02, HP >= 125, 54
  spreads, 10 cells) is below the size floor and not printed. It cannot
  express a bulk cost as a single-stat threshold on this species (0 clean
  Def or HP cuts). On bulk-first species it will often say "no floor;
  build for stat product", which is honest and will read as the feature
  being empty.
- Co-gates are searched on Def and HP, one stat at a time, at the floor
  and at each printed rung; two-stat co-gates (Def AND HP together) and
  co-gates on unprinted rungs are not searched. The clusters-first HP
  stretch rung (148.71 + HP >= 124, 117 spreads) is not reported because
  it is 98.3% on 2v1 Ninetales (Alolan) and 88.9% on 1v2 Marowak, not
  100%; its exact form (HP >= 125) holds 75 spreads, 1.8% of the grid,
  under the 5% bar.
- It cannot price a build. No XL-candy or stardust table exists in the
  repo; it can say clearers reach 1500 CP at median L48.0 vs L50.0, not
  what that costs.
- It cannot quantify margin. Post-match HP and shields are computed by the
  sweep (`sweep.py:397-400`) but never requested by the dive; "wins with
  60% HP" is out of reach. Energy is the only margin plane on the page.
- It cannot weight the meta by real usage, only by PvPoke rank.
- It cannot make the editorial call: safe-swap role, team synergy, whether
  Shadow Sableye deserves XL investment, the Corviknight-style "build for
  information value" argument, or which side of the fork to take. It
  prints both sides of the fork with their cell lists; the choice stays
  empty for a human, by policy.
- It cannot verify its own foundational assumption: if live CMP used the
  shadow-boosted attack, the entire attack ladder would disappear rather
  than shift.
- It is one bake of one gamemaster snapshot. A rebalance to Annihilape
  moves the floor directly and nothing self-checks against a newer
  gamemaster beyond the stamp. The floor has one owner (G-owner says so
  in print).
- It has been shown to produce a clean, attributed floor on exactly one
  species. Phase 0 item 4 measures the yield BEFORE the renderer exists
  and D12 decides whether to build; the honest expectation from the ship
  critic's four-blob spot check is that a large fraction of dives will
  print the negative sentence or an alternative target only.

## 8. Critic items not taken, or taken in a modified form

Every one of the 14 completeness items is addressed above. Three were
taken in a modified form; the reason is one line each.

| Item | Modification                                                                                                                                                                                                                                                                                                                                                                                                               |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | Taken as option (a), but the rectangle rule is "maximise cells guaranteed that the floor cannot, then member count, over rectangles with >= 100 members and no floor clearer" rather than "disjoint by >= 5 cells": the >= 5 wording is a threshold on the answer, not a selection rule, and cannot pick between the n=114 / 9-cell and n=54 / 10-cell rectangles; the printed cut is 101.41 (least attained), not 101.33. |
| 10   | Taken, but the G-caveat positive control pins the COST totals (38 / 24 -> 40 / 25 when `CAVEAT_SPECIES` is emptied), not the NOT CLAIMED count: on the real blob the Aegislash cells are windows and sit in NOT CLAIMED with or without the caveat, so that count cannot move; the clean-cut-AND-caveat case is a synthetic cube.                                                                                          |
| 11   | Taken (the mirror is a permitted-score field, and the 488 was the plain Sableye's number: corrected to "ties at 500"), but the gate is a typed-token check (G-scores), not a regex on bare 3-digit integers: pool counts (934, 923, 857), cell counts (367-382) and clearer counts (698, 558) are all 3-digit and would false-positive on every row.                                                                       |