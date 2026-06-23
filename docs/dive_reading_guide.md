# How to read a deep dive

Attribution: hybrid (AI + expert), the project's "both" tier. The prose was AI-drafted by Claude (Opus 4.8) on 2026-06-23 and reviewed by Michael Lerner; the methodology it describes was shaped by community experts.

A deep-dive page packs a lot into one scroll. This guide walks the page top to
bottom and says what each part answers, so you can jump to the piece you need
instead of reading all of it. For the underlying vocabulary (breakpoint, bulkpoint,
CMP, anchor, spread), read [`concepts.md`](concepts.md) first; this guide assumes
those terms.

The running examples are the Great League Tinkaton dive and the Shadow Corviknight
dive.

## Start at the infographic

The infographic at the top is the summary. Read it first; the rest of the page is the
detail behind it.

- **Header line** - species, typing, league/CP cap, and the recommended moveset
  (for Tinkaton: Fairy Wind / Bulldoze, Gigaton Hammer).
- **Win rate.** The single-IV win rate is always there (the reference IV vs each
  opponent's default IV, all 9 shield scenarios). Tinkaton shows 58%. Dives that
  computed the opponent-IV sweep add a second box, the top-512 robustness number
  (each opponent swept across its top-512 stat-product IVs); Shadow Corviknight shows
  54% single, 55% robustness. When the two are close, the matchups don't depend on
  the opponent rolling a weak IV. When the robustness number is lower, some wins flip
  once the opponent's IV improves.
- **Target spreads.** Two to six IV spreads, each with a role label (High HP, Max
  Bulk, Attack Weight, Generalist) and the opponents it clears. The first spread is
  the lead: the rank-1 battle-score IV, and the one the headline win rates and
  wins/losses describe. Each spread carries a census line of the form "N guaranteed
  breakpoints, M guaranteed bulkpoints" counting how many opponents that spread
  clears on each axis; Tinkaton's Max Bulk spread (0/15/0) reads "50 guaranteed
  breakpoints, 48 guaranteed bulkpoints."
- **Why this IV?** When the battle-score #1 and the stat-product #1 are different IVs
  and the win-rate gap clears the gate, a short blurb names both and explains the
  gap. Near-ties (Tinkaton, Shadow Corviknight) stay silent, so most cards don't show
  it.
- **Headline wins and losses.** The card's "Key wins" and "Key losses" rows: the
  standout matchups for the lead spread, each with its battle score in parentheses.

If you only have ten seconds, the infographic is the whole story. Everything below it
either expands a card claim or gives you a per-IV / per-opponent lens on the same
simulation.

## The scatter plot

Below the card. Each point is an IV; the axes and coloring are switchable through
the controls (battle score, wins-vs-default, wins-vs-mirror, threshold-tier color,
and so on). Use it to see the shape of the IV space rather than to read individual
recommendations.

The **Check my collection** paste box overlays your own Pokemon. Paste a Poke Genie
CSV export and the scatter highlights which of your mons (and their pre-evolutions)
land in each tier. The collection stays in your browser; nothing is uploaded.

The scatter also carries an **Efficient (Pareto)** category. Hover the legend entry
for the tooltip.

## Efficient IVs: the crown and the trophy

Two badges flag standout IV spreads.

- **Crown (the crown glyph).** An IV spread is *efficient* when no other spread for
  the same species and league beats it on all three scaled stats at once (Attack,
  Defense, and HP at the league CP cap, with shadow multipliers applied). A dominated
  spread wastes free stats, since some other reachable spread is at least as good on
  every stat and strictly better on one. Efficiency does not depend on the threshold
  set you are looking at: if a spread is efficient at all, it stays efficient in every
  list it appears in. The crown shows up on the infographic spreads, the threshold-tier
  IV lists, the per-matchup IV finder, the scatter "Efficient (Pareto)" category, and
  your collection table. This is orgodemir's "efficient IV" concept (u/orgodemir,
  https://www.reddit.com/r/TheSilphArena/comments/yxzg7f/).
- **Trophy (the trophy glyph).** This is this project's own addition, not orgodemir's.
  It appears only in your pasted-collection table. Among your mons that qualify for a
  target, a mon earns a trophy when it dominates another of your own mons on all three
  scaled stats and none of yours dominates it back: it is the best of what you actually
  caught. The crown outranks the trophy, so a mon that earns a crown shows only the
  crown.

Identical IV spreads are treated as ties (the comparison is strict), so duplicate IVs
all get the same badge.

## IV Recommendations

The canonical "which IV should I build" section. It folds three things that used to
be separate:

- the noteworthy-IV cards (the "here are the IVs worth catching and why" grid),
- the IV Flavor Guide prose as the section intro (General Good, Fortified {Opp},
  {Opp} Slayer, and the rest of the flavor families),
- the stat-cutoff Threshold-Tier cards as a labeled sub-view, with the expert-authored
  TOML tiers and the auto-derived sim tiers kept distinct.

For most species the Flavor Guide leads with a "General Good [Recommended]" baseline
that almost any catch clears, then a handful of rarer flavors that pick up a specific
matchup at a stat cost. The Corviknight guide, for instance, lists General Good plus
a Pelipper Slayer (trades bulk for the Pelipper 2-1, 2-2) and a Fortified Aegislash
(Blade) (adds bulk for the Aegislash matchup, costs the mirror).

## Threats where your build choice matters

The opponent-centric view. Instead of "this IV beats these opponents," it asks "for
this opponent, does my build choice change the result?" and lists only the opponents
where it does.

- **Decision rows** - opponents where a different recommended spread flips the
  overall matchup. The chips show which build wins; expand a row for the 9-shield
  grid and the exact stat cutoffs.
- **Stealable** - opponents you lose overall against every build, but where a build
  can still take individual shield scenarios via a breakpoint. Useful when a specific
  shield count is close. Example from Tinkaton: "Aegislash (Shield) - High HP steals
  1v0, 2v0, 2v1; Attack Weight steals 1v0, 2v0, 2v1, 2v2 (Atk >= 104.56)."
- **Hoisted callouts** - opponents with no in-range boundary collapse into a single
  "Wins with any recommended build: ..." line (or the losing equivalent), so the
  table only holds threats where the build actually matters.

This is the section to read when your question is "how do I handle opponent X" rather
than "which IV is best overall."

## Per-matchup IV finder

Collapsed by default, below IV Recommendations. It's the fine-grained lens: every
specific (opponent, shield) matchup with the IVs that win it. The Shadow Corviknight
dive carries 220 of these. Open it when you want to confirm a single cell ("which IV
beats this opponent in this shield count"); skip it otherwise.

## Battle-Rating Distribution

A histogram of per-matchup battle ratings for the reference IV across the opponent
pool, under whatever Shields / Opponent-IVs / Bait you've selected in the controls.
It shows how the wins and losses are distributed rather than a single average: a pile
of narrow wins reads differently from a few blowouts.

## Expert Analysis vs Simulation zones

Some dives carry an **Expert Analysis** zone (gold, source-attributed) alongside the
simulation-derived sections. Expert prose is human-authored and credited; the
simulation sections are auto-generated from this project's battle sim. The split is
deliberate so you know which claims come from a person and which come from the model.

## Reading order, short version

1. Infographic - the summary and the win rate(s).
2. IV Recommendations - which IV to build.
3. Threats where your build choice matters - per-opponent build decisions.
4. Per-matchup IV finder - the per-cell detail, only when you need it.

The scatter plot and the distribution histogram are exploration tools, as is the
paste-box overlay for checking your own collection. None of them change the
recommendation; they let you see it.

## ML IV guides differ slightly

The Master League IV guides are a separate format under Articles, organized per stat
rather than around a card. Two pieces are worth knowing:

- **Close calls** - a compact callout where a less-than-perfect IV still wins a
  matchup but the post-match margin shifts enough to matter (a shield spent, a
  near-death survival, or roughly one fewer charged move of energy banked).
- **Check my IVs** - paste candidate spreads (atk/def/hp) and get a PvPoke-style
  table showing only the matchups where those spreads differ. Spreads that agree
  everywhere are hidden. Nothing is uploaded.
