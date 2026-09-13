# Plan: matchup clusters across all shield scenarios, and surfacing them

Drafted 2026-09-11 from the Shadow Sableye GL post-bake look ("the bands
are wild", TODO reminder of 2026-09-10). Exploration-mode doc: Claude prose
is fine here. Nothing in this plan changes sim output; every item is
render/analysis-side and re-renders from replay blobs.

Analysis scripts + figures: `userdata/analysis/2026-09-11_scenario_clusters/`
(gitignored; `load01.py` is the blob loader, `an06.py` runs every scenario,
`an08.py` is the multi-species generality check, `plot07.py` draws the
per-scenario grids). Blob: `userdata/replay/20260911_005150_Sableye_great_shadow`.

## 1. What we found

### The two bands are one attack threshold

Shadow Sableye GL, SC/DP/FP, 0v1, pvpoke opponent IVs, bait-selective. The
main scatter (avg battle score vs stat-product rank) shows two bands. Running
the existing fingerprint pipeline (`scripts/deep_dive_matchup_clusters.py`)
on the 0v1 grid instead of the even shields gives K=2, silhouette 0.65, and
a depth-1 rule at 100% tree accuracy:

    atk < 148.06  -> lower band (n=1876)
    atk >= 148.06 -> upper band (n=2220)

Colored onto the scatter, the split IS the two bands (`sab_bands.png`,
left panel). The x-axis is SP rank, which scrambles attack, so an attack
threshold reads as a band rather than a step.

The finer structure Michael sketched is a ladder of attack thresholds,
found by per-opponent score deltas between strands:

| shadow-effective atk | what flips                                                 | visible to win/loss fingerprint |
| -------------------- | ---------------------------------------------------------- | ------------------------------- |
| ~143.7-144.2         | Sableye mirror +197, Thievul +163, NO win flips            | no (score-only)                 |
| ~145.7               | Kingdra win flip (+229)                                    | yes                             |
| 148.06               | Annihilape x3 (396 -> 654), Electrode-H, Aegislash-Shield  | yes (the band gap)              |
| 148.67               | Feraligatr win flip (+286), Shadow Feraligatr +113 no flip | yes (the top-end split)         |

The first row is invisible to the current method by construction (a damage
tier change with no win flip).

Mechanism, pinned later the same day (expert-verdict workflow, re-verified
by hand): 148.06 is NOT a damage breakpoint. It is a Charge Move Priority
(CMP) line against the PvPoke-default Annihilape (4/13/13, L17, 123.378
attack); CMP compares shadow-stripped attack, so a shadow focal needs
1.2 x 123.378 = 148.053 shadow-effective attack, and the first attained
value above that is 148.10. Plain Sableye flips the same cell at 123.42,
the first attained value above 123.378, with the same 2220 winners. Damage
into Annihilape does not change across the line. 148.67 is CMP against a
default Shadow Feraligatr (1.2 x 123.88 = 148.65); the 148.55 mirror rung
is a Foul Play 58 -> 59 breakpoint. See docs/expert_verdict_plan.md. The 1v1 section's root split is 148.67, which
is why "Color by: matchup cluster" on the page already looks close.

### All nine scenarios for Shadow Sableye (`sab_scen_avg.png`, `sab_scen_wins.png`)

| scen | K   | sil  | sharp | patterns | tree acc | root rule    | reads as                                             |
| ---- | --- | ---- | ----- | -------- | -------- | ------------ | ---------------------------------------------------- |
| 0v0  | 2   | 0.56 | 14    | 116      | 0.97     | hp < 123.5   | bulk cluster wins Quagsire/Charjabug/Stunfisk        |
| 0v1  | 2   | 0.65 | 13    | 69       | 1.00     | atk < 148.06 | the two bands; Annihilape breakpoint                 |
| 0v2  | 6   | 0.64 | 5     | 16       | 0.81     | atk < 147.51 | DEGENERATE: 0-5 wins, clusters interleave on scatter |
| 1v0  | 5   | 0.62 | 16    | 64       | 0.84     | atk < 151.20 | five-band attack ladder, clean on the scatter        |
| 1v1  | 3   | 0.55 | 21    | 145      | 0.98     | atk < 148.67 | upper/lower plus a low-hp tail                       |
| 1v2  | 2   | 0.46 | 18    | 291      | 0.90     | hp < 121.5   | not banded in avg score; visible in wins             |
| 2v0  | -   | -    | 1     | -        | -        | -            | DEGENERATE: everyone wins 74-76 of 76                |
| 2v1  | 2   | 0.68 | 10    | 52       | 1.00     | atk < 143.84 | Thievul/Florges flip; scatter shows more strands     |
| 2v2  | 2   | 0.42 | 21    | 278      | 0.94     | atk < 145.22 | weak; scatter has 3-4 strands                        |
| all  | 2   | 0.45 | 118b  | -        | 1.00     | atk < 148.06 | concatenated fingerprint, see section 3              |

Takeaways: the ODD scenarios (0v1, 1v0, 2v1) are the cleanest on this dive,
not the even ones. Both lopsided extremes (0v2, 2v0) are degenerate: too few
marginal opponents, so either no clusters or "perfect" tiny ones. The win-
count y-axes make the bands literal (each band is a horizontal line of equal
wins), which is a strong argument for defaulting the cluster color mode to a
wins y-axis.

### Generality (9 species, moveset 0, `an08.py`)

Sableye, Lapras, Dondozo, Jumpluff, Carbink, Medicham (GL); Corviknight,
Feraligatr (UL). Pattern holds: odd scenarios cluster robustly in most species
and often carry the highest silhouettes; 0v2 and 2v0 are degenerate in 7 of 9
(n_sharp 0-4, or wins pinned at 0 or max). Two edge cases to handle:

- Tiny fingerprints produce fake-perfect silhouettes: Feraligatr UL 0v2 K=6
  sil 1.00 with 4 sharp marginals and 7 patterns; Dondozo 0v2/2v0 sil 1.00
  with 2 sharp. Needs a floor (section 3).
- Feraligatr UL 0v0 has 12 sharp marginals but NO clustering: every K fails
  the 40-IV min-cluster floor. Worth an honest "structure too fragmented"
  message rather than the generic reason string.

## 2. Decisions already taken (Michael, 2026-09-11)

- Extend scenario coverage to all 9 scenarios plus an averaged/combined view.
- Look at the actual scenarios (done above) before designing.
- Consider moving results up the page and/or collapsing more, so this is
  reachable if it earns its place.

## 3. Proposed changes

### Phase A: compute every scenario (small, render-only)

1. `compute_matchup_clusters(..., scen_pairs=EVEN_SHIELD_PAIRS)` -> default
   to every scenario present in the dive, in grid order. Cost measured at
   0.5 s for 9 scenarios (0.2 s for 3). Payload grows ~10-15 KB per extra
   scenario (4096 small ints), x2 for the L51 template, on a 27 MB page.
2. Add an "all scenarios" entry. Two candidates were measured:
   - avg9: mean score over scenarios, win = mean > 500. Sableye K=2 sil 0.45,
     root atk < 145.22. Introduces a synthetic "win" notion (a mean above
     500 is not a fight won).
   - concatenated fingerprint: every scenario's sharp-marginal bits side by
     side (118 bits on Sableye). K=2 sil 0.45, tree acc 1.00, root atk <
     148.06, i.e. it recovers the 0v1 finding. Same Hamming machinery, no
     new distance. Root rule was atk on every species checked.
   Recommendation: concatenated fingerprint, labeled "all scenarios". It is
   literally "which fights do you win across every shield state", which is
   the section's stated identity. Keep avg9 out.
3. Degeneracy floor: skip (with an honest reason) any scenario with fewer
   than N sharp marginals or fewer than M distinct patterns. From the data,
   `n_sharp >= 6 and n_patterns >= 8` separates every real result from every
   fake-perfect one seen. Add a specific reason string for the "all K fail
   the min-cluster floor" case (Feraligatr UL 0v0).
4. Section default scenario: today 1v1. Options: keep 1v1; "all"; or the
   scenario with the best silhouette among non-degenerate ones. Michael's
   call (section 5).

### Phase B: surface it where the reader already is

1. Main scatter "Color by: matchup cluster" already follows the Shields
   dropdown when the chosen scenario's labels exist in the payload
   (`deep_dive_engine.js` ~2325). Once Phase A lands, 0v1 coloring works
   with no JS change. One fix needed: when the dropdown is "avg" (all 9),
   `getActiveScenarioIndices()` returns 9 indices, the code falls back to
   the payload default (1v1), and the legend does not say so. Map "avg" to
   the "all scenarios" clusters instead.
2. Legend names carry the rule: "C1: atk >= 148.1 (n=2220)" instead of
   "C1 - 0v1 (n=2220)". The root rule is already computed by `stat_rules`;
   emit the depth-1 rule (or "mixed" when the tree root does not separate
   cleanly) into the payload.
3. "Show all shield scenarios" 3x3 mini-grid (exists, `allscen-grid`,
   uncolored): color each mini by its own scenario's clusters and put the
   headline (K, silhouette, root rule) in each mini's title. This is the
   one-glance "which shield state has structure" view Michael asked for.
4. Section dropdown lists all scenarios + all; degenerate ones appear with
   their reason, not hidden (the absence is informative: "0v2: 0-5 wins,
   no IV distinguishes").
5. Default the cluster color mode's y-axis to "Wins vs PvPoke default" when
   the user switches Color to cluster (or add a hint in the legend). The
   bands are horizontal lines there.

### Phase C: page layout

Today `#dd-analysis` (Dive Analysis, collapsed) is emitted in
`scripts/deep_dive_lib/render.py:~1350`, after IV Recommendations, Threshold
Tiers, Per-matchup IV finder, Slayer Builds, Threats, and Anchor-Driven
Flips: roughly 2.6 MB of results HTML below the scatter on the Sableye page
(the Threats/Slayer block alone is 2.1 MB). Options, cheapest first:

- (a) Jump strip under the scatter controls: "Matchup clusters / Rank
  volatility / Flip table / Methods" anchors. No reflow, no test churn.
- (b) Promote "Matchup clusters" out of Dive Analysis to sit directly under
  the scatter + Top IVs block (it is the scatter's explanation). Leave Rank
  Volatility and the Flip Table in Dive Analysis. This is the one that makes
  the finding reachable.
- (c) Move the whole Dive Analysis block up above IV Recommendations.
- Collapsing: the results blocks are already `<details>`; the scroll cost
  is the open ones (IV Flavor Guide, Simulation-Derived Tiers, Threshold
  Tiers prose). Which are default-open needs a browser check before
  deciding; not measured here.

Recommendation: (a) + (b). (b) needs the L51 template swap to carry the
section (it already does for the current position; verify after the move).

### Phase D: method upgrades (later, each its own decision)

1. Score-tier fingerprint: quantize per-opponent score (e.g. 25-point
   bins) and cluster with the same average linkage, so score-only steps
   like the ~144 Sableye-mirror/Thievul tier become visible.
2. Hierarchical pass: re-cluster inside each cluster once (K chosen the
   same way). On Sableye this splits the upper band at atk 150 but NOT the
   Feraligatr top-end strand; the strand needs the per-opponent flip check
   (which the flip table already prints) to be named.
3. Attack-ladder detector: per opponent, scan score vs attack at fixed bulk
   and report step locations; names every band edge directly and extends
   to def/hp bulkpoints. Cheap, no clustering, but a new section.
4. Vocabulary: retire "bands" for "clusters" on the page; add
   `docs/concepts.md` entries for envelope-crosser "bands" (the
   `Envelope [elevated-band-crosser]` log vocabulary, currently undefined)
   so the two uses stop colliding.

## 4. Contracts this touches

- `tests/test_matchup_clusters.py:290` pins `set(out) <= {0v0,1v1,2v2}`;
  lines 295-316 pin the reason strings. Update with the new scope and add
  a test that a 0v1-only grid clusters (record the Sableye K=2 / 148.06
  result as the fixture).
- `guides/matchup-clusters/body.md:71-75` says the dropdown is 0v0/1v1/2v2
  and that there is "deliberately no average across scenarios" view. That
  prose is authorship=both and must be rewritten with the concatenated-
  fingerprint rationale, not just deleted. `{{mc:...}}` tokens via
  `cluster_params()` should carry any new floor numbers.
- `render_section`'s "Not available" fallback names the even pairs.
- `deep_dive_engine.js` cluster color mode: payload default fallback and the
  legend text (Phase B1/B2). `tests/test_js_wire_contract.py` pins the
  `{a}v{b}` label form; unchanged.
- Replay byte-stability (arc S4): all changes are render-side, so
  `scripts/replay_analysis.py` on the blob is the verification path and
  the shipped pages need a re-render (the `userdata/.cards_rerender_pending`
  sentinel is already set from 2026-08-31).
- The Methods "About these metrics (0v0 / 1v1 / 2v2 delta ...)" block and
  the slayer `even` metric are separate uses of EVEN_SHIELDS and stay.

## 5. Open decisions for Michael

1. Section default: 1v1 (status quo), "all scenarios", or best-silhouette.
2. "All" = concatenated fingerprint (recommended) vs avg9, or both.
3. Layout: (a)+(b) as recommended, or (c).
4. Show degenerate scenarios with their reason (recommended) or hide them.
5. Whether Phase D1 (score-tier fingerprint) is worth doing now, given it
   is what catches the one band edge the current method cannot see.

## 6. Verification plan

1. Unit: new fixture test for 0v1 on the Sableye grid (K=2, root 148.06,
   acc 1.00) and the degeneracy floor on a 0v2 grid.
2. Re-render Shadow Sableye GL from the blob with `replay_analysis.py
   --html <scratch path>`; check the 0v1 cluster coloring against
   `sab_bands.png` and that the "avg" dropdown state colors by "all".
3. `python -m pytest tests -q -m "not slow"` green; guide re-render.
4. Do NOT re-render into `userdata/website/` while the Twilight Trails bake
   is running (it is, as of this writing); replay to a scratch path.

## 7. What shipped (2026-09-13, branch `scenario-clusters`)

Phases A and B, with Michael's calls on section 5: default view = "all
scenarios"; "all" = the concatenated fingerprint; degenerate scenarios shown
with their reason; layout (Phase C) and the method upgrades (Phase D) not
touched. Plus the deferred build-brief corroboration line (stage 14).

Three things came out differently from the plan above, and each is recorded
where the code lives:

1. **"all" on Shadow Sableye GL is K=2, silhouette 0.451, root `atk < 148.68`
   over 113 bits -- the section-1 table's K, but not its `atk < 148.06` over
   ~118 bits.** The table's offline run predates the degeneracy floor and
   included 0v2's 5 bits; section 3's floor excludes them, and "'all' = every
   NON-DEGENERATE scenario's bits" is what shipped. Both readings are in the
   comment beside the exclusion in
   `deep_dive_matchup_clusters.compute_matchup_clusters` (with every
   scenario's bits: 119 bits, K=2, silhouette 0.459, `atk < 147.96`), so
   flipping it is one predicate if the fuller reading is preferred on a
   corpus look.

   **Column order turned out to be load-bearing, and is now a stated
   choice.** Hamming distance is permutation-invariant in the columns, so
   ordering cannot move a point -- but it sets `np.unique`'s lexicographic
   order of the unique patterns, which is the linkage tie-break, and a
   combined fingerprint ties constantly (2117 unique patterns over 113 bits
   share 85 distinct distances). On this grid raw collection order gives
   K=3 / 0.395 / accuracy 0.961 and most other orderings give K=2. The
   shipped order is |win-rate - 0.5| ascending -- the same sharpest-first
   order `sharp_marginals` already hands every per-scenario entry -- which
   on this grid also carries the better silhouette (0.451) and tree accuracy
   (0.983). `concat_fingerprint`'s docstring states it and
   `test_combined_bits_are_ordered_most_discriminating_first` pins both the
   order and the fact that it changes the answer here.
2. **Two no-cluster outcomes, not one.** "Degenerate" (under the 6 sharp / 8
   pattern floor; bits excluded from "all") is now distinct from
   "fragmented" (clears the floor, but no K keeps every cluster above the
   min-cluster size -- the Feraligatr UL 0v0 case in section 1; its bits
   still count toward "all"). Calling the second one degenerate would be a
   false claim about the data.
3. **The concatenated fingerprint was 30x too expensive as written.** It
   produces ~2100 unique patterns against ~280 for a single scenario, and
   both the pairwise-distance build and the merge loop were quadratic in
   that: `compute_matchup_clusters` went from ~0.2 s to 15.5 s per call at a
   4.9 GB peak (the plan budgeted 0.5 s). Two changes bring it to 0.8-1.6 s
   and ~40 MB, and are asserted BIT-IDENTICAL rather than "close":
   `_hamming` via `A.B' + B.A'` instead of a (u, u, d) broadcast, and a
   row-minimum cache instead of re-scanning the active submatrix each merge.
   Verified against the old implementations on 7 species x GL/UL and on all
   16 (moveset, mode) views of the Shadow Sableye blob -- identical labels,
   silhouettes, tree rules and flip tables everywhere -- and pinned by
   equivalence tests that carry the old code as the oracle.

Also noted while wiring the brief: the section fits its stat-rule tree on
the PAGE's 2dp-rounded `DATA.ivAtk`/`ivDef`, so a consumer starting from the
full-precision blob meta lands 0.01 off on some splits (this grid: 148.67 vs
148.68). `SECTION_STAT_DP` names the rounding and the brief rounds the same
way; a test pins it against `deep_dive.py`.

Round 2 (the two reviews) changed four more things, all reader-facing:

4. **A legend rule is emitted only when the root split is an IFF for that
   cluster** (every member on one side AND nothing else on that side), not
   when it is merely necessary. "C1: atk < 151.20" is read as a definition;
   on 1v0 the necessary-only form gave three different clusters that same
   name. Those clusters are now "C1 (n=1105)" and the depth-3 rules block is
   where their description lives.
5. **The combined block carries a signpost line** naming the two sharpest
   single scenarios -- K, silhouette, the split, and the number of sharp
   marginals the silhouette was measured over, because "sharpest" is a
   comparative claim and a silhouette rises as the fingerprints get shorter
   (plain Sableye GL tops its page at 0v1's 0.76 over 7 marginals, against
   0v0's 0.48 over 28). Every clustered dropdown option carries its own K
   and silhouette too. The default view is routinely the least separated
   partition on the page, and the page's best material was one unlabelled
   click away.
6. **"silhouette" is defined on the page**, in "How this works", with the
   calibration (above ~0.5 distinct groups, below WEAK_SIL tendencies), and
   the mini-grid titles spell "silhouette" and "split" instead of "sil" and a
   bare rule. The degenerate/fragmented sentences lead with the finding
   ("every spread wins 0-5 of 76 opponents here...") instead of the apology.
7. **The brief stopped reusing the page's word for a different count.** Its
   own screen is over CONTESTED cells and DISTINCT OPPONENT COLUMNS; the
   page's is over SHARP MARGINALS and distinct IV FINGERPRINTS. Same 6 / 8
   bar, neither count dominating the other (this blob's 0v2: page 5 / 16,
   brief 7 / 8). The sentence now names its own tests. The corroboration
   line names its source and its RELATION to the printed floor ("also splits
   it on attack -- at 148.68, 0.58 above the line printed here" / "splits it
   on HP ... the two methods do not agree"), and its silhouette gate reads
   the value as PRINTED (2dp), so it cannot go silent beside a page headline
   reading "silhouette 0.40".

Not done here and still open: Phase C layout (a)+(b), Phase D, and the
shipped-page re-render (`userdata/.cards_rerender_pending` stays set).
