Every battle score on this site is computed at *specific* IVs on both
sides. That makes any single number - a battle rating, a W-L record, a
"wins the 1-1" claim - a **point estimate**: true for the two exact
spreads that were simmed, and silent about what happens when either
side's IVs move. **IV robustness** is the follow-up question: *does
this outcome survive the IVs?* It splits into the half you can't
control (which spread did the opponent happen to roll?) and the half
you can (exactly which of *your* spreads win this fight?).

This guide explains the machinery behind every robustness surface on
the site - the per-opponent robustness numbers in the dives, and the
matrix / cheat-sheet / per-pair pages built for Worlds 2026. The
worked examples below are a 2026-08 snapshot of the Worlds pages; the
method is general and will show up on future surfaces (limited cups,
post-rebalance re-checks) in the same shapes.

## The three kinds of matchup

For a given pair of Pokemon in a given shield scenario, checking every
competitive IV combination on both sides can only end three ways:

- **Safe** - you win no matter what either side rolled. IVs are
  irrelevant; build whatever you like.
- **Dead** - you lose no matter what. Also IV-irrelevant.
- **IV-decided** - some spreads win and some lose. This is the only
  kind of matchup where IV planning pays, and finding these cells is
  the whole point of the analysis.

Most matchups are safe or dead. The robustness surfaces exist to find
the IV-decided minority and then show you *where the line falls*.

## You've already seen a robustness number

The classic dives have carried one for a while: the per-opponent
robustness figure asks "do we beat this opponent regardless of which
good IV it rolled?" - a win is only credited if your spread beats the
opponent across its whole competitive IV cohort (top 512 spreads by
stat product), per shield scenario. An exact 500-500 tie counts as
*not* beaten. That is the conservative direction: it protects you from
the opponent's roll, which you can't see and can't control.

The Worlds-style pages flip the lens around as well: for one opponent
spread (or its whole cohort), *which of your 4096 spreads* win? Both
directions come from the same underlying data.

## Exact enumeration, not sampling

The robustness data is a set of **outcome planes**: a win/loss bit for
every (your spread) x (their spread) x (shield scenario) combination,
simmed exhaustively. Nothing is sampled or interpolated - when a page
says "192 of the top-512 spreads win this", that is a count over
actual battles, and hovering a cell shows exact spread counts and
score margins. Bait strategy changes outcomes, so planes are baked for
bait ON and bait OFF separately and shown side by side. (The bait
toggle applies to the focal side only; in the "no-bait" line the
opponent still baits, which is why the two directions of a no-bait
pair describe different battles and need not mirror each other.)

## Cohorts and probe spreads

"Every IV combination" needs a competitive cut, and one cut is not
enough:

- **Top-512 cohort** - the opponent's (or your) best 512 spreads by
  stat product. This covers what a rank-focused player runs.
- **Attack-IV band** - the best-stat-product spread *for each attack
  IV* (16 spreads, 0 through 15 attack). Attack-weighted builds are a
  real choice (winning charge-move priority, hitting breakpoints), and
  they are exactly the spreads a pure stat-product cut throws away.
  The band is labeled separately and never pooled into the 512.

On the focal side, summary tables use two **probe spreads** - the
rank-1 stat-product spread and the max-attack spread within the
top-512 - as representative builds. Probes are a screen, not a proof:
a pair can be "IV-decided in probe slices only", and the per-pair
detail pages recompute everything from the full 4096-spread grid
rather than trusting the probes.

## Reading a W/L/? grid

Each pair gets a 3x3 shield grid in PvPoke's battle-matrix layout:
rows are your shields (0/1/2 top to bottom), columns are the
opponent's, so "2-1" means you keep two shields and they keep one.
Each cell holds one letter:

- **W** - beats every cohort spread (safe),
- **L** - beats none (dead),
- **?** - IV-decided: some cohort spreads win, some lose.

The hub matrix is the same information as color only; its links open
the text-carrying cheat sheets, so nothing depends on color alone.

## Robustness curves

For an IV-decided cell, the next question is *how* the outcome varies
across your spreads. The per-pair pages plot the share of the
opponent's cohort you beat as a function of your stat-product rank, in
bands of 16 spreads. A flat curve means your IVs barely matter; a
cliff means a hard cutoff - some stat crosses a damage tier - and the
page names the boundary. As a snapshot example, the Aegislash (Shield)
vs Altaria page's 2-2 reads: 0 of Aegislash's top-512 spreads beat
every top-512 Altaria, 275 beat none, and the bands in between climb
from 0.4% to about 6% of Altarias beaten - IV-decided, but shallowly:
no Aegislash spread makes the matchup safe.

## Reach or deny: closed-form cutoffs

Damage in this game is stepwise: a fast or charged move does a fixed
integer of damage until a stat threshold flips it to the next integer.
That makes the IV question exactly solvable - no simulation needed for
this part:

- **Reach** (breakpoint): the attack value where your move starts
  dealing one more damage per hit.
- **Deny** (bulkpoint): the defense/HP value where *their* move drops
  by one, or where you survive one more hit.

The pages compute these cutoffs in closed form and print them as
ladders ("attack >= X reaches the 4-damage Snarl"). One honesty
subtlety the tables keep straight: "your spread beats *their
particular spread*" and "your spread is *guaranteed* against their
whole cohort" are different quantities - a cutoff that wins the
per-spread fight can still lose to a bulkier roll from the same
cohort. Ladder rows are labeled with which claim they make. The IV
explorer runs the same closed-form ladders in your browser: enter IVs
and a level, and it lists which cutoffs you reach or hold against
every meta entry.

## Honesty rails

Robustness analysis is exactly the place where a pipeline can quietly
overclaim, so the shipped pages carry their own checks:

- **Screens are labeled as screens.** The matrix's IV-decided flags
  come from a fast screen; the detail pages re-derive their scenarios
  from the full grids, not from the screen.
- **The false-negative rate is measured and printed.** On the 2026-08
  Worlds snapshot: of 21 sampled "clean" (not-flagged) pairs given the
  full 4096-spread treatment, 4 showed some IV-dependence in the
  top-512 x top-512 block - worst case, 31.1% of one focal's top-512
  spreads had a scenario-dependent outcome. A green cell means "the
  screen found nothing", not "proven settled", and the hub says so
  next to the number.
- **Exact counts everywhere.** Tables show "192/512", not "mostly";
  ties are counted against you; deferred work (pairs that missed the
  compute budget) is listed by name rather than silently omitted.

## Where this appears today

- **Worlds 2026 pages**: the hub matrix (31x31 meta), per-species
  cheat sheets, 401 per-pair detail pages, the IV explorer, and the
  CMP board (charge-move-priority order with per-pair IV flip
  thresholds).
- **Classic dives**: the per-opponent robustness figures and the dive
  card's headline, which use the same top-512 opponent-cohort notion.

The Worlds pages are pinned to the pre-Worlds game data (Worlds runs
on the older battle system), but nothing in the method is
Worlds-specific: wherever a matchup is close enough that a roll of the
dice on either side's IVs could flip it, this is the machinery that
finds the line and tells you which side of it your Pokemon is on.
