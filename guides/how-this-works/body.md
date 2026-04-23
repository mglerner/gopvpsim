If you've used PvPoke, most of what you see on this site is built on top
of it. This page is the short version of what the tool is, where the
numbers come from, and what you can and can't trust.

## The simulator is PvPoke, rewritten in Python

Every matchup on this site is scored by the same decision-making logic
PvPoke uses on its battle page: the same fast-move / charge-move timing,
the same shield decisions, the same damage formula, the same shadow
multipliers, the same priority rules for simultaneous charge moves. We
read the same `gamemaster.json` that PvPoke publishes, so when Niantic
changes a move's power or energy cost, our dives change with PvPoke's
next data release.

The reason it's a rewrite and not a wrapper is that PvPoke's battle
simulator runs in your browser. To sweep one species against an opponent
pool across every IV spread and every shield scenario, we need it
running in a loop without a browser in the way. A Python port gets us
that, and also gets us a test suite.

## We check ours against PvPoke's

PvPoke is the reference. To make sure the Python rewrite matches, we
keep a suite of cross-checks:

- **{{dev:test_count}} passing tests** covering damage, type matchups,
  buffs and debuffs, shield policies, shadow multipliers, and the
  dynamic-programming logic PvPoke uses to pick which charge move to
  throw.
- **{{dev:pvpoke_matchups_verified}} matchups verified cell-for-cell**
  against PvPoke's simulate-mode score table, across all nine shield
  scenarios - {{dev:pvpoke_cells_verified}} per-scenario scores that
  match exactly, not just "close."
- **{{dev:type_chart_cells_verified}} type-effectiveness cells**
  matching PvPoke exactly.

When our simulator produces a different number than PvPoke's, it's a
bug in one of them and we go find out which. Often it's ours. A few
times it's turned out to be PvPoke's - we document those in our
developer notes ({{dev:pvpoke_bugs_documented}} so far) so readers know
when we're intentionally running a fixed version of the reference
logic.

## We sweep every IV, not just the top ones

PvPoke's UI shows you one IV matchup at a time, usually the stat-product
rank-1 IVs on both sides. We run the simulation against every legal IV
spread on your side - all {{dive:iv_space_size}} of them (Atk 0-15, Def
0-15, Sta 0-15) - at every level that keeps the CP under the league
cap.

Why the full sweep: IVs matter to PvP teambuilding in a way that
rank-1 doesn't capture. Two IV spreads with similar stat products can
sit on opposite sides of an important damage breakpoint or a CMP tie,
and the only way to see which IVs fall on which side is to simulate
them all. The **Threshold Tiers** on every dive page are the output of
that sweep: they name the specific cutoff an IV has to clear to reach
the next meaningful tier against each notable opponent. See the
[Threshold Tiers guide](../threshold-tiers/) for how to read those
cards.

For every IV spread, we simulate against the league's meta opponent
pool (currently {{dive:opponent_count}} opponents on the reference
{{dive:species_display}} {{dive:league_display}} dive) in each of the
nine shield scenarios (0-0, 0-1, 0-2, 1-0, 1-1, 1-2, 2-0, 2-1, 2-2).
That's one dive, fully scored.

## We render with Plotly so every IV is inspectable

The scatter plot on every dive page is a Plotly figure with one point
per IV. Hovering a point shows you its stat-product rank, its battle
rank, its avg battle score, its per-opponent win/loss list, and which
threshold tiers it clears. The dropdowns at the top of the plot
(Shields / Opponent-IVs / Bait) re-color the plot live - same data,
different lens.

This is the part we built that PvPoke doesn't have. Instead of asking
"what's the best IV," it lets you ask "which of the IVs I could realistically
catch or trade for is the right one to invest in," which is usually the
question that matters in a teambuilding session.

## What you should trust, and what you shouldn't

**Trust:**

- The win-rate numbers. Same logic as PvPoke's simulate mode, cross-
  checked cell for cell on every matchup we've verified.
- The threshold-tier cutoffs. These are derived from the damage
  formula by exhaustive search, not estimated.
- The opponent pool composition when it matches what you see on
  pvpoke.com for the same league and date.

**Be careful with:**

- Per-dive verdicts that depend on editorial framing - the prose
  around the numbers is there to highlight what we think matters, not
  to replace your own read of the matchup list.
- Rankings across opponent pools that use different rules than
  pvpoke.com (we sometimes cap CP on opponents or include sibling
  forms; each dive's methodology footer spells out what pool was
  used).

**Known limits:**

- We simulate 1v1s. Switch advantage, alignment, and shield burn across
  a full 3v3 match are outside the scope of what a per-matchup score
  can tell you.
- The handful of matchups where our sim disagrees with PvPoke are
  documented in our developer notes, along with why we believe ours is
  right and PvPoke's is wrong (or vice versa). When the disagreement is
  intentional, we mark it as a known divergence rather than silently
  papering over it.

If you want the gory details, the code is at
[github.com/mglerner](https://github.com/mglerner) and every dive page
has a **Run parameters (CLI invocation)** section at the bottom
showing the exact command that produced it.
