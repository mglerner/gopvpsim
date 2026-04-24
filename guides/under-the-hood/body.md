This guide is for readers who already know PvP IV analysis - anchors,
breakpoints, bulkpoints, CMP - but haven't seen the internals of this
tool. It walks the pipeline end to end. Nothing here assumes you read
code.

If you're looking for "what do these terms mean" rather than "how is
this generated," the other six guides are a great starting point.

## What the tool actually does

For each dive, we sim each of the 4,096 possible IVs of the focal
species (0/0/0, 0/0/1, ..., 15/15/14, 15/15/15) at their best
under-cap level against a pool of opponents (currently GL top-50 plus
Championship Series additions, ~65 species), across all nine shield
scenarios (0v0 / 0v1 / ... / 2v2), under two opponent-IV variants
([PvPoke](https://pvpoke.com/) default vs stat-product rank 1) and
two bait policies (selective vs never-bait). One "score" per focal
IV x opponent x scenario x opp-IV x bait cell. That's the raw input
to every narrative and category decision on the page.

The sim itself is a pure-Python port of PvPoke's JavaScript
ActionLogic and Battle engine; we verify exact score parity against
PvPoke on a fixed oracle set. When we diverge, we document and xfail
rather than quietly differ. (There are a handful of known PvPoke bugs
we intentionally don't reproduce; the [How This Works](../how-this-works/)
guide walks through the parity check at a higher level.)

## The pipeline, top to bottom

The dive's configuration - which opponents to sweep, which damage
breakpoints we care about, which hand-authored tier cutoffs to
surface - lives in [TOML](https://toml.io/) files under
`thresholds/`. TOML is a plain-text configuration format (think INI
with better typing); one file per focal species. The sections and
anchors in that file are what the pipeline layers below read from.
A minimal example:

```toml
# thresholds/tinkaton.toml  (abbreviated)

[Tinkaton]
sources = "HomeSliceHenry's Discord #iv-tech"

# A tier spread: a named stat cutoff that the tier-cards section
# on the dive will render as a row. `source` routes it into the
# gold Expert zone.
[Tinkaton.Great.spreads."GH Good"]
attack = 0            # no attack floor
defense = 141.66      # Medicham Dynamic Punch survival, 1s no bait
stamina = 138         # HP co-floor
description = "Medicham Dynamic Punch survival (1s no bait)."
source = "HomeSliceHenry's Discord"

# A Level-3 damage-breakpoint anchor: enumerate every attack BP
# the sim finds against Jellicent. The resolver picks moves
# automatically; we just name the opponent.
[Tinkaton.Great.anchors.jellicent_brkp_any]
kind = "damage_breakpoint"
opponent = "Jellicent"
description = "Discover all Jellicent damage breakpoints."
source = "HomeSliceHenry's Discord"
```

Every section under `[Species.League.spreads]` or `[...anchors]`
becomes an input to the categorization and narrative layers below.

### 1. Anchors (the TOML authoring layer)

An "anchor" is a single named threshold with a comparison. Three
kinds:

- **CMP anchor**: beats some opponent IV on raw attack (for CMP
  ties).
- **Damage breakpoint**: attack high enough that your fast or charged
  move lands one more damage tier against a specific opponent.
- **Bulkpoint**: defense (+ optional HP co-floor) high enough that an
  opponent's move lands one less damage tier against you.

You can author an anchor at three levels of precision, depending on
how much you know:

- **Level 1**: name the target opponent and the threshold in plain
  terms ("Medicham Dynamic Punch survival, no bait"). We resolve it.
- **Level 2**: name the opponent and the specific moves to check.
- **Level 3**: enumerate every breakpoint or bulkpoint in a stat
  range. This is the "discover everything that matters against X"
  mode.

Levels are just about which fields you filled in; the resolver
handles all three uniformly. A TOML with nothing but opponent names
and "Level 3" still produces a useful dive, because we auto-derive
anchors even when you don't hand-author any. Hand-authoring lets you
carry expert provenance the tool can't know: "this is the HomeSlice
Henry Discord Tinkaton spread, def&ge;143.03 + hp&ge;138 is the
Corsola-Galarian 2-GH-survival line."

### 2. Auto-anchor fallback

When a species's TOML is empty or light on anchors, we scan the whole
opponent pool and synthesize Level-3 damage-breakpoint and bulkpoint
anchors against every opponent that shows signal. The synthesis is
gated so that species with rich hand-authored TOMLs don't get noisy
auto-additions on the same axis.

Concretely: if the TOML already has a Level-3 breakpoint anchor
against Medicham, the auto-fallback doesn't also synthesize one; but
if there's nothing against Sealeo, it adds `auto_sealeo_brkp_any`.

### 3. Notable IVs (the category layer)

Every focal IV gets tagged with the set of anchors it passes. A
"category" is a named group of IVs sharing some structural property:

- **Slayer categories** are the Nash-convergence output of iterative
  mirror slayer discovery. Round 0 starts from every IV that wins
  against a default opponent; each round tests the survivors against
  *each other* in the mirror; the set usually collapses to 30-150 IVs
  over 3-4 rounds. Those are the "survivors of the mirror."
- **Composite categories** are intersections of anchor sets: "Atk
  Slayer & Top 5% by stat product" becomes one composite card on the
  Notable IVs list.
- **Matchup categories** are synthesized per (opponent, scenario,
  bait mode) where an IV cohort wins that exact cell. They're the
  most granular and usually have the fewest members.

Categories are ranked on a selectivity metric (how many IVs pass vs
the dive baseline) so the ones that actually differentiate IVs float
to the top.

### 4. Threshold tier cards

The tier-card block at the top of the dive is separate machinery from
the Notable IVs list. A "tier" is a flat stat-cutoff spread with a
matchup-flip justification: "def &ge; 141.76 flips 2 scenarios vs
Dusclops." Tiers come from three sources:

- **TOML-authored spreads** (hand-stamped with expert rationale).
- **Auto-derived spreads** from aggregating Level-3 anchor-flips by
  opponent: "every IV with def&ge;X flips at least one matchup
  against Y, in Z scenarios."
- **Matchup-flipping boundary search**: a simulation sweep that walks
  stat cutoffs and finds the exact value at which the *aggregate*
  matchup outcome (across shield scenarios) flips from loss to win.

Auto-derived and boundary-search tiers are shown in blue (auto),
TOML-authored tiers in gold (expert). Both stay in the same grid.
The [Threshold Tiers](../threshold-tiers/) guide walks through
reading a tier card in more detail.

### 5. Narrative flavors

This is the purple "IV Flavor Guide" zone on every dive. Derivation:

- Start from the effective tier set for the active moveset.
- Pick a name family from the axis shape. Def+hp only = "Bulk" /
  "Fortified"; atk+hp = "Slayer"; all three = "General Good";
  atk-only = "Attack Weight"; def-only = "High Bulk."
- If the tier is opponent-named ("Lapras Atk") and the axis has
  attack, it becomes "Lapras Slayer." If opponent-named and axis is
  def, it becomes "Fortified Lapras."
- **Namesake guarantee**: if a flavor carries an opponent's name, at
  least one gain against that opponent must appear in the narrative's
  gains list. If the flip-aggregation layer didn't attribute anything
  to the namesake, we pull the closest matching boundary or
  anchor-flip and front-load it so the opening prose mentions the
  namesake. Required because the two sources (tier-name layer and
  flip layer) can otherwise disagree.
- **Identical-stat merge**: flavors sharing both stat signature AND
  gains list get collapsed. Lapras Slayer + Lapras (Shadow) Slayer at
  the same (123.74 atk, 149 hp) with the same gains becomes one
  "Lapras / Shadow Lapras Slayer" card.
- **Catch-phrase tier**: each flavor gets a geometric-distribution
  rarity label. "~14-28 catches for a 50-75% chance" means in 14
  catches you have a 50% shot at seeing a qualifying IV, in 28
  catches a 75% shot. "Very rare" over 500 catches, "almost any will
  do" when most IVs qualify.

The [IV Flavor Guide](../iv-flavor-guide/) guide is the
reader-facing companion for this section; this one describes how the
flavors get *derived*.

### 6. Meta Role (CD articles only)

On CD articles, the Meta Role block above the Move Comparison table
is a separate auto-gen surface. It pulls:

- A cause-and-effect bucket lead: "Mud Slap (Ground) flips the Steel
  bucket x1.6: Steelix 0%&rarr;77%, Aegislash (Shield)
  43%&rarr;100%..."
- Before&rarr;after win-rate ranges instead of raw delta points:
  readers get both the magnitude and the stakes.
- A closing synthesis paragraph: "Mud Slap shifts Oinkologne from
  33.6% baseline to 43.8% GL aggregate. Gains 21 matchups; drops 2."

Nothing in that block is editorial; every phrase is a literal rollup
of sim output. If it reads as editorial, we have a bug.

## Four authorship tiers (the colored sidebars)

Every narrative block carries one of four attribution colors:

- <span class="auth-chip expert">Gold ("expert")</span>: human analyst
  wrote this prose. You're seeing judgment calls about teambuilding,
  catch priority, meta position - things the sim can't derive. TOML
  source, hand-maintained.
- <span class="auth-chip both">Green ("both")</span>: human wrote the
  prose, but the numbers behind it come from sim. Human judgment,
  sim-backed facts.
- <span class="auth-chip auto">Blue ("auto")</span>: deterministic
  template. Every word is a literal rollup of sim output with no
  editorial judgment. What the "Meta Role" and "IV Flavor Guide"
  blocks look like by default.
- <span class="auth-chip ai">Orange ("ai")</span>: LLM-drafted prose,
  not yet human-reviewed. Distinct from "auto" because an LLM makes
  register choices a template can't. Used sparingly, with the orange
  border as a scrutiny flag.

The Reader's Guides (including this one) use "ai." The Species
narrative blocks on dives default to "auto" now, replacing earlier
ai-drafted prose, so there's no unreviewed LLM prose on the main
deep dives.

## Overriding any of this

The tool is designed so expert authoring always wins over automation.

- Adding a TOML anchor replaces whatever the auto-fallback would have
  produced on that axis.
- Adding a `[Species.intro]` / `[meta_role]` / `[verdict]` block in
  `thresholds/<species>.toml` replaces the auto-gen template for that
  species.
- Adding a named spread with `source = "..."` routes the anchor into
  the gold Expert zone so readers can tell it's your judgment call.

If you see something on a shipped dive that you disagree with,
there's a TOML knob for it. The auto-fallback is specifically
designed to stay out of the way when authored content is present.

## Where to push back

The auto-gen is deterministic; if it says something wrong, the input
was wrong (bad anchor, wrong opponent pool, stale TOML) or the
template is wrong (a bug). Both are fixable. If something reads like
editorial judgment on an auto-labeled block, flag it - that's exactly
the "template writing prose it can't justify" failure mode we want to
catch before it ships.
