The **Matchup clusters** section is the first block inside the
collapsed **Dive Analysis** details near the bottom of every dive
page. It answers a question the scatter plot can't: *which IV spreads
are actually interchangeable, and which win a genuinely different set
of fights?*

The scatter's y-axis is an average over the whole opponent pool, and
averages hide structure: two IV spreads can sit at the same average
score while winning different opponents. This section drops the
average entirely and groups IV spreads by their **win/loss fingerprint**
- the exact set of marginal matchups each spread wins.

## Sharp marginals: the only opponents that matter here

For one shield scenario, most opponents are *settled*: every IV spread
beats them, or none does. Nothing about your IV choice can change
those fights, so they carry no information about which spread to
build.

The action is in the **sharp marginal** opponents - the ones between
{{mc:sharp_lo_pct}}% and {{mc:sharp_hi_pct}}% of the IV spreads beat.
On the reference
{{dive:species_display}} {{dive:league_display}} dive's 1v1 scenario
(a 2026-07 snapshot; your dive shows live values), that's 15 of 87
opponents: 28 are always-win, 37 are always-lose, and 15 actually
flip depending on your IVs. Each spread's fingerprint is its win/loss
vector over just those 15. (A live page opens on the combined
{{mc:all_scen_display}} view, so pick **1v1** in the Shield scenario
dropdown to follow this example.)

## Clusters: fingerprints, not score bands

IV spreads with similar fingerprints get grouped into clusters
(bottom-up, by how many marginal matchups they disagree on - no fixed
cluster count is assumed, and a split is only kept when every cluster
holds a meaningful number of spreads). Clusters are ordered weakest
to strongest by how many marginal fights their members win on
average.

The number of clusters isn't fixed: the method scores each candidate
count ({{mc:kmin}} through {{mc:kmax}}) by **silhouette** - how cleanly
the fingerprints separate - and keeps only counts where every cluster
clears a minimum size. Among those, it deliberately picks the **fewest**
clusters that come within a hair ({{mc:sil_epsilon}}) of the best
silhouette, so a coarser, more readable grouping wins whenever it's
essentially as good as a finer one. If no split clears the
minimum-size floor, the section says so outright rather than inventing
clusters.

The key honesty note baked into the layout: **win-sets cross rather
than nest.** A "stronger" cluster usually gains matchups *and trades
some away*. The cluster summary table says both - on the reference
dive's 1v1, the stronger cluster gains Florges (+92pp), Sableye
(+81pp), and Feraligatr (+76pp), but trades away Empoleon (-73pp) and
Mimikyu (-68pp). That trade is the real content of the section: it
tells you the two groups of spreads are built for different jobs, not
that one strictly beats the other.

Each headline also carries a **silhouette** score - a 0-to-1 measure
of how cleanly the fingerprints separate. When it's below
{{mc:weak_sil}} the headline says "weak separation" outright; read
weakly-separated clusters as tendencies, not tiers.

## The three stat-plane panels

The scatter panels project the same IV spreads onto each pair of
battle stats - **atk x def**, **atk x hp**, **def x hp** - colored by
cluster. This is the "invisible in score, obvious in stats" view: the
clusters usually overlap completely on the main scatter's score axis,
but fall into clean stat regions here, because crossing a breakpoint
or bulkpoint is what moves a spread from one cluster to the next.

The **Shield scenario** dropdown switches everything in the section at
once - panels and tables. It lists **every shield scenario the dive
baked**, lopsided ones included, and each entry carries its own K and
silhouette, so the list itself tells you where the structure on that
page is. The lopsided scenarios (0v1, 1v0, 2v1) are often the sharpest
ones - worth a click before you conclude a dive has no clean bands.

The last entry, **{{mc:all_scen_display}}**, is the default. It is the
**concatenated fingerprint**: every non-degenerate scenario's
marginal-matchup bits laid side by side into one long fingerprint,
clustered with the same machinery. It is deliberately *not* an average
of scores across scenarios - a mean score above 500 is not a fight
won, and averaging washes out exactly the structure this section
exists to show. Concatenating asks the section's own question once
instead of nine times: *which fights do you win across every shield
state?* In that view each table row is one **(opponent, scenario)**
pair - "Furret [0v0]" - because the same opponent can be a sharp
marginal in several shield states and flip differently in each. Its
bits are ordered most-discriminating first, which is the tie-break the
clustering uses when several merges are equally close.

Because the combined view asks the hardest version of the question, it
is usually the *least* cleanly separated entry on a page. So its block
ends by naming the two sharpest single scenarios, with the number of
sharp marginals each silhouette was measured over - a short
fingerprint separates more easily, so 0.76 over 7 marginals and 0.48
over 28 are not the same kind of evidence.

Some scenarios have nothing to cluster, and they say so with their
counts rather than disappearing. A scenario is **degenerate** when
fewer than {{mc:degen_min_sharp}} opponents are sharp marginals, or
when those opponents produce fewer than {{mc:degen_min_patterns}}
distinct win patterns: on that little data every candidate cluster
count scores near-perfectly, which is a property of the measurement
and not of your IVs. Those scenarios are left out of the
{{mc:all_scen_display}} fingerprint too. A scenario that clears the
floor but still has no split keeping every cluster above the minimum
size is reported as **fragmented** instead - different message, and
its bits still count toward the combined view. The absence is
informative either way, and the page leads with the finding rather
than the apology: "0v2 shields: every spread wins 0-5 of 76 opponents
here, so the IV choice moves at most 5 matchups in this shield state"
tells you no IV choice saves that shield state.

## The tables under the panels

- **Cluster summary** - one row per cluster: size, mean stats,
  stat-product rank range, mean marginal wins, and the named
  gains / trades-away vs the previous cluster.
- **Per-cluster win rates** (collapsed) - the full grid: one row per
  sharp marginal opponent, one column per cluster, each cell the
  share of that cluster's spreads that win the fight. Green tint =
  mostly wins, red = mostly loses; the percentage is always printed,
  so nothing rides on color alone.
- **Stat rules** (collapsed) - a short decision tree over (atk, def,
  hp) that reproduces the cluster labels, with its agreement shown as
  an **in-sample** accuracy. Read it as "how well the clusters reduce
  to stat regions," not as a prediction claim.
- **Matchup flip thresholds** (collapsed) - one row per sharp
  marginal: its win rate, the single stat threshold that best
  predicts the flip ("wins iff atk >= 109.10"), how accurate that
  one-stat rule is, and whether an authored anchor already **names**
  that opponent. Rows where no single-stat rule beats
  always-predicting the majority outcome say so instead of showing a
  fake threshold. High-accuracy **UNNAMED** rows are the interesting
  ones: they're candidate anchors the experts haven't written up yet.

## What this section does NOT react to

The section is computed at bake time for the page's featured moveset,
with the default opponent IVs and bait-selective shield play, over
the full opponent pool. It does **not** follow the scatter's moveset /
opponent-IV / bait dropdowns or the opponent filter - the caption at
the top of the section says exactly what it was computed with.

If you've pasted your collection into the paste-box, the cluster
panels mark your on-grid spreads as gold stars - hover one to see
which of your mons sits there and which cluster it lands in. (The
tables stay collection-agnostic.)

## Where this came from

This section replaced an earlier experimental "banding & clusters"
block (retired 2026-07) that clustered on the opponent-averaged score.
That method usually fired on numerical noise in the average - and even
when it caught a real tier, it couldn't say *which matchups defined
it*. The matchup-space reframe comes from a dedicated methodology
re-evaluation across 17 dived species; the section's collapsed "How
this works" note carries the short version.

Until 2026-09 the section clustered only the even scenarios
(0v0 / 1v1 / 2v2) and had no combined view. In the 9-species survey
that motivated the change, the odd scenarios most often carried the
highest silhouette on the page, so the section was leaving out its own
best material.

## Where to go next

- **[Deep-Dive Scatter](../deep-dive-scatter/)** - the average-score
  view the clusters deliberately don't use; the Color and Shields
  dropdowns there are the complementary lens.
- **[Threshold Tiers](../threshold-tiers/)** - authored anchors and
  tier cutoffs; the flip-threshold table's "named" column points at
  these.
- **[Envelope Position](../envelope-position/)** - the other
  "is this category doing something rank doesn't predict" metric.
