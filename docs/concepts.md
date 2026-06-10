# Concepts and vocabulary

This document defines the terms used throughout the deep-dive HTML outputs and the
threshold configuration files. If you've opened a deep-dive report and seen labels
like "Anchors-First Slayer [lickitung_brkp, cmp_vs_lurgan]" or "survivor cohort" and
want to know what they mean, this is the place.

For the TOML file format that *configures* these things, see
[`threshold_schema.md`](threshold_schema.md). This document is purely conceptual and
contains no schema details.

---

## The basics

### IV spread

A description of a *set of IVs*. Two flavors:

- **Stat-cutoff form**: a region in IV space described by minimum stat values, e.g.
  "atk ≥ 127.23, def ≥ 0, sta ≥ 0." Any IV that meets or exceeds all the cutoffs is
  considered part of the spread.
- **IV-list form**: an explicit list of (atk_iv, def_iv, sta_iv) tuples, e.g. the
  community "Lurgan Ape" spread, which is a hand-picked set of 27 specific IV combos.

Both forms answer the same question: "is this IV a member of this named cohort?" The
form you use depends on whether the cohort is naturally describable as a region (use
stat-cutoff) or as a hand-picked list (use IV-list).

### Survivor cohort

The set of IVs that *survived* a slayer iteration — i.e., the IVs that, when tested
against an opponent set, won enough matchups to be considered viable slayers. The
mirror slayer iteration converges to a cohort by repeatedly re-testing focals against
the previous round's cohort until the survivor set stabilizes. Since the 2026-06
redesign the cohort's job is to be the *mirror opponent population* — the
denominator behind the mirror CMP % and mirror-wins columns — rather than the
optimization target itself.

A survivor cohort is just an IV-list spread with a particular *origin* (the
iteration). It's not a special data type.

### Breakpoint

A focal-attack threshold at which one of the focal's moves deals strictly more
integer damage to the opponent than it did at the previous attack value. Crossing a
breakpoint is a discrete jump in damage output.

Breakpoints are per-(move, opponent) — Counter against Lickitung has its own ladder
of breakpoints, distinct from Low Kick against Lickitung, distinct from Counter
against Cresselia. There can also be multiple breakpoints for a single (move,
opponent) pair: a move might step from 4 → 5 damage at one focal atk value and from
5 → 6 at a higher one.

### Bulkpoint

The defensive mirror of a breakpoint: a focal-defense threshold at which one of the
opponent's moves deals strictly *less* integer damage to the focal. Crossing a
bulkpoint is a discrete jump in damage taken (downward).

### CMP (Charge Move Priority)

When both Pokémon fire a charged move on the same turn, the one with higher *raw
attack stat* (not damage, not IVs — the actual computed atk number) goes first. If
its move KOs the opponent, the opponent's move is cancelled. "Winning CMP" means
having strictly higher atk than the opponent. CMP is binary and brutal — a single
point of effective atk can decide a mirror.

### Slayer archetypes

Two build archetypes used to highlight notable IVs. They correspond to *distinct
lexicographic strategies* — which goal comes first:

- **Anchors-First Slayer** — hit the important break/bulkpoints first, then win CMP
  as much as possible. Members are the IVs that clear the *maximum achievable
  number* of counted anchor parents, ranked among themselves by Top-Mirror CMP %
  and then attack. Explicit TOML anchors always count; auto-generated anchors count
  only when *selective* (cleared by less than half the IV space), so "everyone
  passes it" anchors can't saturate the archetype.
- **CMP-First Slayer** (the "lab mon") — win Charge Move Priority first, pick up
  anchors as a secondary goal. Members are the max-attack spreads; no anchor is
  required for membership. The per-row anchor checklist *reports* which anchors
  each spread clears vs sacrifices.

Both archetypes are computed directly from the anchor thresholds and the sweep
scores — no extra simulation. The mirror iteration's role is supplying the opponent
population behind the CMP % and mirror-wins columns, not being the objective. A
single IV can belong to both archetypes (cross-category badges mark the overlap).

(Until 2026-06 the dive surfaced three post-hoc labels — Atk / Bulk / CMP Slayer —
applied to the Nash survivor pool. They were retired: Atk and CMP membership are now
visible directly in the per-row anchor checklist, and Bulk's HP+def-above-median
rule was structurally saturated; see TODO "Slayer-card signal-loss audit.")

---

## Spreads vs anchors

These two words sound similar but mean different things, and the deep-dive output
uses both. Be precise:

|            | **Spread**                             | **Anchor**                                        |
| ---------- | -------------------------------------- | ------------------------------------------------- |
| What it is | *Data*: a description of a set of IVs  | *A rule*: a yes/no test applied to one IV         |
| Answers    | "Is this IV a member of THAT cohort?"  | "Does this IV satisfy THIS condition?"            |
| Form       | Stat-cutoff region OR explicit IV list | A derived numeric threshold + a comparison        |
| Example    | `lurgan_ape` = a list of 27 IVs        | `cmp_vs_lurgan` = focal_atk > max(lurgan_ape.atk) |

Anchors can be *built from* spreads. The CMP anchor `cmp_vs_lurgan` takes the
`lurgan_ape` spread, computes the maximum effective atk over its members, and uses
that as a threshold for the rule "does this focal IV beat them in CMP?" But the
spread itself is just data — it doesn't know about CMP.

Why have both? Because spreads are reusable nouns (the Lurgan Ape cohort exists
independently of any test you might run on it), and anchors are the rules that
operate on focal IVs in the deep-dive (they need a name, a kind, and a derived
threshold). Mixing the two would force every cohort to commit to a specific
comparison up front, which we don't want.

---

## What an anchor *is*, plainly

An anchor is a yes/no test you can apply to a single focal IV. Each anchor reduces to
a comparison against some derived numeric threshold. The slayer categorizer asks, for
each focal IV in the survivor pool, "which anchors does this IV pass?" and labels the
IV with the set of anchor names.

That set is what makes the anchor checklist informative. Instead of "atk above
median" (vacuous), you get "passes lickitung_brkp + cmp_vs_lurgan" (actionable: it
tells you what this IV does that others don't).

### Walkthrough: a CMP anchor

Suppose we have a CMP anchor named `cmp_vs_lurgan`, defined as "win CMP against the
Lurgan Ape cohort."

1. At setup time, the loader resolves the spread reference to the IV list (27
   entries).
2. For each IV in that list, compute its effective attack at the appropriate level
   (e.g., level 16.5 or 17 for Annihilape at the Great League CP cap).
3. Take the maximum over those 27 atk values. Call it `T`.
4. The anchor's check is now simply: `focal_atk > T`.
5. Every focal IV in the survivor pool either passes this single comparison or
   doesn't. Done — the anchor produces a binary tag for each focal.

### Walkthrough: a damage-breakpoint anchor

Suppose we have a damage-breakpoint anchor named `lickitung_brkp`, defined as "clear a
damage breakpoint against Lickitung."

1. At setup time, the loader knows the opponent is Lickitung. It computes Lickitung's
   effective defense at its reference IVs.
2. For each of the focal Pokémon's moves (e.g., Annihilape's Counter, Low Kick, Rage
   Fist, Close Combat), compute the integer damage at varying focal atk values across
   the survivor range. Find the atk values where the integer damage steps up by 1.
3. That gives a list of candidate breakpoints — tuples of `(move, dmg_before,
   dmg_after, min_atk_to_clear)`. The list is the discovered breakpoint ladder against
   Lickitung.
4. The anchor's check becomes: "does focal_atk clear at least one specified
   breakpoint from this ladder?"

Step 4 hides an important question: *which* breakpoint? See the next section.

### Walkthrough: a bulkpoint anchor

A bulkpoint anchor is the def-side mirror of a damage-breakpoint anchor. Same shape,
same three precision levels, but it tests *focal defense* against incoming damage
instead of *focal attack* against outgoing damage. Suppose we have a bulkpoint anchor
named `mirror_blkp_above_lurgan`, defined as "starting from the Lurgan-era 102.9 def
floor, find the next def threshold at which the Annihilape mirror's damage to us
steps down."

1. At setup time, the loader identifies the opponent (Annihilape mirror). It computes
   the opponent's effective *attack* — symmetric to how the BP anchor computes
   opponent defense. By default this uses PvPoke's reference IVs; if a hand-built
   `opponent_spread` is given, the resolver picks the *highest-attack* member as the
   worst case for the focal defender.
2. The loader looks up the *opponent's* fast and charged moves from the gamemaster.
   These are the threat moves we're measuring incoming damage from. (BP anchors use
   the focal's own moves; bulkpoint anchors use the opponent's, because the question
   is "what hits us" rather than "what we hit.")
3. For each threat move, scan the survivor def range for def thresholds at which the
   incoming integer damage steps *down* by 1. That gives a list of candidate
   bulkpoints — tuples of `(move, dmg_before, dmg_after, min_def_to_reach)`.
4. The Level 2 anchor's check becomes: "the smallest def above 102.9 at which any
   threat move's damage drops" — pick the earliest threshold across all moves.

Bulkpoint tags show up in the per-row anchor checklist with a " bulk" suffix on the
badge (parallel to how BP anchor tags appear). Each focal IV that meets the def
threshold for at least one named bulkpoint counts that parent toward its
Anchors-First total.

### Atk-side vs def-side anchors

The two "ladder" anchor kinds are mirror images. Same shape, same three precision
levels, different stat targets:

|                    | **damage_breakpoint**                       | **bulkpoint**                               |
| ------------------ | ------------------------------------------- | ------------------------------------------- |
| Tests focal        | attack                                      | defense                                     |
| Damage direction   | outgoing (focal hits opponent)              | incoming (opponent hits focal)              |
| Threshold semantic | "smallest atk that deals ≥ N damage"        | "smallest def above which damage ≤ N"       |
| Threat moves       | focal's movepool                            | opponent's movepool                         |
| Opponent reference | effective *defense* (bulkiest IV in spread) | effective *attack* (punchiest IV in spread) |
| Badge suffix       | (none)                                      | " bulk"                                     |
| TOML keys          | `move`, `deals_at_least`, `above_atk`       | `move`, `takes_at_most`, `above_def`        |

A focal IV can clear both kinds in the same anchor pass — every cleared parent
shows in the row's anchor checklist and counts toward the Anchors-First total, so a
high-atk + above-bulkpoint IV gets credit on both axes.

---

## Which breakpoint? Three precision levels

There is no single "Lickitung BP." There are usually several — possibly one per
focal move, possibly multiple per move at different damage tiers. When community
sources talk about "the Lickitung BP," they almost always mean one specific (move,
damage tier) that mattered enough to name, but the exact (move, tier) isn't always
written down.

To handle this, damage-breakpoint anchors are specified at one of three precision
levels, and you pick the level based on how much you know.

### Level 1 — fully explicit

You know the move and the damage tier you care about. For example, "Counter must
deal at least 5 damage to Lickitung." The anchor's threshold is the smallest focal
atk at which that condition holds against Lickitung's reference defense. This is the
right level when you've already done the analysis and want to lock in a known target.

### Level 2 — reference-anchored

You know the *attack floor* you want to exceed but not exactly which move's
breakpoint that floor corresponds to. For example, "find the smallest atk above
127.23 at which any of the focal's moves takes a step up in damage against
Lickitung." This is the right level for *reproducing community spreads*, because
community spreads are typically published as atk thresholds without explicitly naming
which move's breakpoint produced them.

In the Annihilape case, acidicArisen (an IV expert in the community) confirmed that
the original Lurgan Ape spread was calibrated to a Lickitung BP near atk 127.23 —
but the original tweet describing exactly which move + tier was the calibration
point couldn't be found. Level 2 lets us reproduce that reasoning without needing to
recover the lost tweet.

### Level 3 — discover and tag

You don't know the move *or* the tier and want to find out. The loader enumerates
*every* (move, tier) breakpoint against the named opponent within the survivor atk
range and treats each as its own sub-anchor. Each focal IV gets tagged with the list
of sub-anchors it clears: `lickitung_brkp:[counter→5, low_kick→6]`.

This is exploration mode. The deep-dive output will show, for example, "of the 30
survivors, 28 clear `counter→5`, 12 clear `low_kick→6`, 3 clear `rage_fist→8`." That
distribution tells you which breakpoints actually matter for this species — and is
how you'd discover the calibration point of a community spread you don't have a
writeup for.

The natural workflow for a new species is: start at Level 3 to discover the BPs,
look at the distribution, decide which one(s) matter, and promote them to Level 1 or
Level 2 once you've made the call.

### Reference defense of the opponent

Damage breakpoints depend on the opponent's effective defense, which depends on the
opponent's IVs. Different Lickitung IVs → different def → potentially different
breakpoints. By default, anchors use the rank-1 PvPoke IVs for the named opponent;
this can be overridden if you care about a specific opponent IV cohort. The
mechanism for the override lives in [`threshold_schema.md`](threshold_schema.md).

---

## How this shows up in the deep-dive HTML

When you read a deep-dive report, the Slayer Builds archetype tables will look
something like this (sketch — actual rendering may differ):

```
Anchors-First Slayer (12 IVs)
──────────────────────────────────────────────────────────────────────────────
IVs        Atk      Def     HP    Anchors                        Top-Mirror CMP %   Avg
15/3/2     129.44   99.69   134   2/2  lickitung cmp:lurgan      96%                612.4
15/2/4     129.44   99.14   135   2/2  lickitung cmp:lurgan      96%                610.8
...
```

The Anchors-First Slayer table is *hidden* when no counted anchor resolves — it is
only shown when there's something specific to point at, and each row's Anchors
column tells you exactly what that IV does that distinguishes it. The CMP-First
Slayer table is always shown (it needs no anchors); its checklist column reports
what each max-attack spread keeps or gives up.

Tables show the top rows by each archetype's ranking and expand to the larger
cohort; the top-quartile rows are highlighted.

---

## Where to go next

- To configure spreads and anchors for a species, see
  [`threshold_schema.md`](threshold_schema.md).
- For a worked example of the mirror slayer iteration that produced the Annihilape
  survivor cohort discussed above, see
  [`validations/2026-04-07_annihilape_mirror_slayer_iteration.md`](validations/2026-04-07_annihilape_mirror_slayer_iteration.md).
