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
2% and 98% of the IV spreads beat. On the reference
{{dive:species_display}} {{dive:league_display}} dive's 1v1 scenario
(a 2026-07 snapshot; your dive shows live values), that's 15 of 87
opponents: 28 are always-win, 37 are always-lose, and 15 actually
flip depending on your IVs. Each spread's fingerprint is its win/loss
vector over just those 15.

## Clusters: fingerprints, not score bands

IV spreads with similar fingerprints get grouped into clusters
(bottom-up, by how many marginal matchups they disagree on - no fixed
cluster count is assumed, and a split is only kept when every cluster
holds a meaningful number of spreads). Clusters are ordered weakest
to strongest by how many marginal fights their members win on
average.

The key honesty note baked into the layout: **win-sets cross rather
than nest.** A "stronger" cluster usually gains matchups *and trades
some away*. The cluster summary table says both - on the reference
dive's 1v1, the stronger cluster gains Florges (+92pp), Sableye
(+81pp), and Feraligatr (+76pp), but trades away Empoleon (-73pp) and
Mimikyu (-68pp). That trade is the real content of the section: it
tells you the two groups of spreads are built for different jobs, not
that one strictly beats the other.

Each headline also carries a **silhouette** score - a 0-to-1 measure
of how cleanly the fingerprints separate. When it's below 0.30 the
headline says "weak separation" outright; read weakly-separated
clusters as tendencies, not tiers.

## The three stat-plane panels

The scatter panels project the same IV spreads onto each pair of
battle stats - **atk x def**, **atk x hp**, **def x hp** - colored by
cluster. This is the "invisible in score, obvious in stats" view: the
clusters usually overlap completely on the main scatter's score axis,
but fall into clean stat regions here, because crossing a breakpoint
or bulkpoint is what moves a spread from one cluster to the next.

The **Shield scenario** dropdown (0v0 / 1v1 / 2v2, defaulting to 1v1)
switches everything in the section at once - panels and tables. There
is deliberately no "average across scenarios" view: different shield
counts reward different stats, and averaging them washes out exactly
the structure this section exists to show.

## The tables under the panels

- **Cluster summary** - one row per cluster: size, mean stats,
  stat-product rank range, mean marginal wins, and the named
  gains / trades-away vs the previous cluster.
- **Per-cluster win rates** (collapsed) - the full grid: one row per
  sharp marginal opponent, one column per cluster, each cell the
  share of that cluster's spreads that win the fight. Blue tint =
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

## Where to go next

- **[Deep-Dive Scatter](../deep-dive-scatter/)** - the average-score
  view the clusters deliberately don't use; the Color and Shields
  dropdowns there are the complementary lens.
- **[Threshold Tiers](../threshold-tiers/)** - authored anchors and
  tier cutoffs; the flip-threshold table's "named" column points at
  these.
- **[Envelope Position](../envelope-position/)** - the other
  "is this category doing something rank doesn't predict" metric.
