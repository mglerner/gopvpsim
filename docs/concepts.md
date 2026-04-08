# Concepts and vocabulary

This document defines the terms used throughout the deep-dive HTML outputs and the
threshold configuration files. If you've opened a deep-dive report and seen labels
like "Atk Slayer [lickitung_bp, cmp_vs_lurgan]" or "survivor cohort" and want to know
what they mean, this is the place.

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
the previous round's cohort until the survivor set stabilizes.

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

### Slayer categories

Three classes used to highlight notable IVs in a survivor cohort. They're meant to
correspond to *distinct strategies*, not three different cuts of the same metric:

- **Atk Slayer** — IVs that clear a *named damage breakpoint or set of breakpoints*
  against a notable opponent. The point is not "above-median attack" (which is
  vacuous); the point is "this IV reaches a damage tier the median doesn't."
- **Bulk Slayer** — IVs that have notably high HP+def, trading off some attack for
  the ability to absorb more incoming damage.
- **CMP Slayer** — IVs whose raw attack stat is high enough to win CMP ties against a
  reference opponent (e.g., the converged mirror cohort, or a community-defined
  baseline).

A single IV can belong to multiple categories. The most versatile IVs are the ones
tagged with all three.

---

## Spreads vs anchors

These two words sound similar but mean different things, and the deep-dive output
uses both. Be precise:

| | **Spread** | **Anchor** |
|---|---|---|
| What it is | *Data*: a description of a set of IVs | *A rule*: a yes/no test applied to one IV |
| Answers | "Is this IV a member of THAT cohort?" | "Does this IV satisfy THIS condition?" |
| Form | Stat-cutoff region OR explicit IV list | A derived numeric threshold + a comparison |
| Example | `lurgan_ape` = a list of 27 IVs | `cmp_vs_lurgan` = focal_atk > max(lurgan_ape.atk) |

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

That set is what makes the Atk Slayer category informative. Instead of "atk above
median" (vacuous), you get "passes lickitung_bp + cmp_vs_lurgan" (actionable: it
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

Suppose we have a damage-breakpoint anchor named `lickitung_bp`, defined as "clear a
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

In the Annihilape case, mercuryish (an IV expert in the community) confirmed that
the original Lurgan Ape spread was calibrated to a Lickitung BP near atk 127.23 —
but the original tweet describing exactly which move + tier was the calibration
point couldn't be found. Level 2 lets us reproduce that reasoning without needing to
recover the lost tweet.

### Level 3 — discover and tag

You don't know the move *or* the tier and want to find out. The loader enumerates
*every* (move, tier) breakpoint against the named opponent within the survivor atk
range and treats each as its own sub-anchor. Each focal IV gets tagged with the list
of sub-anchors it clears: `lickitung_bp:[counter→5, low_kick→6]`.

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

When you read a deep-dive report, the slayer survivor table will look something like
this (sketch — actual rendering may differ):

```
Atk Slayer (3 of 30 survivors clear at least one named breakpoint)
─────────────────────────────────────────────────────────────────
IVs        Atk      Def     HP    Tags                       Wins
15/3/2     129.44   99.69   134   lickitung_bp, cmp_vs_lurgan, cmp_vs_mirror, bulk    87/270
15/2/4     129.44   99.14   135   lickitung_bp, cmp_vs_lurgan                          90/270
15/15/0    129.44   101.91  131   cmp_vs_lurgan                                        45/270
...
```

The Atk Slayer category is *hidden* when no survivor in the cohort clears any named
breakpoint. The category is only shown when there's something specific to point at,
and each row's "Tags" column tells you exactly what that IV does that distinguishes
it.

The CMP Slayer category shows the IVs that pass at least one `cmp_*` anchor. Bulk
Slayer continues to use the HP+def-above-median heuristic (it's structural rather
than anchor-driven). The most versatile IVs — those that appear in multiple
categories — are highlighted at the top of each table.

Tables are expandable to show the full survivor cohort, not just the highlighted
rows; the highlighting calls out the IVs that matter most under whichever lens you're
using (e.g., the top quartile by anchor-tag count).

---

## Where to go next

- To configure spreads and anchors for a species, see
  [`threshold_schema.md`](threshold_schema.md).
- For a worked example of the mirror slayer iteration that produced the Annihilape
  survivor cohort discussed above, see
  [`validations/2026-04-07_annihilape_mirror_slayer_iteration.md`](validations/2026-04-07_annihilape_mirror_slayer_iteration.md).
