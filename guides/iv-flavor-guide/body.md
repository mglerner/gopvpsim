The **IV Flavor Guide** is the teal-bordered zone at the top of the
IV Recommendations section on every dive page. It groups the
IV space into a short list of named play-style archetypes - a
"flavor" - each one paired with the specific matchups that flavor
buys you and the specific matchups it costs.

It's the fastest section to read on the whole page, and it's the
right place to start if you're deciding which IV spread to chase.

<figure>
<img src="screenshots/flavor-example.png"
     alt="The teal-bordered IV Flavor Guide zone on a dive
          page, showing four flavors with a summary table and an
          expanded 'General Good' flavor below.">
<figcaption>
The IV Flavor Guide zone on the Tinkaton UL dive. The summary table
lists the four flavors the simulation derived, each with how many
IVs qualify and how many catches it takes to land one. Below the
table, each flavor expands (the "General Good" one is open here)
with its stat signature, a safe-baseline description, and the
opponent-by-opponent matchups that flavor's stat cutoffs buy you.
</figcaption>
</figure>

## What a flavor is

A flavor is a **named cluster of IV spreads with a shared stat
signature and a shared strategic intent**. The screenshot above shows the Tinkaton
UL dive's four flavors:
<span style="color:#3fb950;font-weight:600">General Good</span> is a
broad "safe baseline" cut covering 82.4% of the IV space;
<span style="color:#bc8cff;font-weight:600">Fortified Walrein</span>
is a much narrower cut that trades attack range for a defensive
threshold against Walrein;
<span style="color:#58a6ff;font-weight:600">Dusknoir Slayer</span>
and <span style="color:#f0883e;font-weight:600">Steelix (Shadow) Slayer</span>
each give up bulk to clear a specific damage breakpoint against
their namesake opponent.

A flavor is **not** an arbitrary PvPoke preset. It's derived by:

1. Taking the mechanical tier cutoffs from the simulation sweep
   (every Atk/Def/HP threshold that changes the matchup list).
2. Mapping each cutoff's shape - does it bound Atk, Def, HP,
   or a combination - onto a SwagTips-style name family. Pure-Def
   cuts become `Fortified {Opp}` or `Premium Bulk`. Pure-Atk cuts
   tied to a specific opponent become `{Opp} Slayer`. Broad cuts
   with no single anchor become `General Good`.
3. Attaching the per-flavor trade-off list by partitioning the IV
   space at the flavor's cut and comparing the flavor cohort's
   win rate against the General Good flavor's win rate across every
   opponent in the dive's pool.

The code that does this is `refine_flavor_names` in
`scripts/deep_dive_narrative.py`. The name is the editorial label;
the cluster is the mechanical output.

## The six name families

Every flavor you see on a dive comes out of one of six families. The
family is chosen from the shape of the cut (Atk, Def, HP, or a
combination) plus whether the cut is tied to a specific opponent:

- **General Good** - a broad cut with Atk, Def, and HP floors, no
  single opponent anchor. This is the "recommended" flavor on most
  dives; clearing it gets you the bulk of the species' meta coverage
  without chasing anything specific.
- **Premium Bulk** - a Def + HP cut with no Atk floor. The defensive
  counterpart to General Good: the cut narrows to bulkier IV spreads,
  but isn't tied to a named opponent.
- **Attack Weight** - a pure Atk cut with no Def or HP floor. Narrows
  to the high-Atk tail of the IV space; usually surfaces on species
  whose role is "open with a charged move, win by damage race."
- **High Bulk** - a pure Def cut, no Atk or HP floor. Rarer; usually
  a species-specific pattern where the HP dimension doesn't carry
  a bulkpoint.
- **{Opponent} Slayer** - a cut (Atk, or Atk + HP) tied to a
  specific opponent's damage breakpoint. Lapras Slayer, Tinkaton
  Slayer, etc. The cutoff is the attack threshold at which one of
  the focal's moves steps up a damage tier against that opponent,
  plus any HP requirement from the neighboring matchup boundary.
- **Fortified {Opponent}** - a cut (Def, or Def + HP) tied to a
  specific opponent's bulkpoint. Fortified Greedent, Fortified
  Clodsire, etc. The cutoff is the defense threshold at which one
  of the opponent's moves steps **down** a damage tier against the
  focal.

A seventh family, **TOML-defined**, covers cases where a human has
given the flavor a specific name in `thresholds/<species>.toml`
(e.g. "GL-General Good", "Slight Atk Weight"). The renderer passes
those through unchanged. An eighth, **{Species} Mirror Atk / Mirror
Bulk**, is synthesized automatically when the mirror matchup needs
its own cut; like TOML names, it passes through unchanged.

## How to read the zone

Top of the zone: a one-sentence species-level summary ("In Great
League, {{dive:species_display}} has N flavors: A, B, C") plus an
overview table with one row per flavor:

| Flavor                         |  IVs |     % | Catches needed     |
| ------------------------------ | ---: | ----: | ------------------ |
| General Good [Recommended]     | 4081 | 99.6% | almost any will do |
| Fortified Diggersby            |    2 |  0.0% | very rare          |
| Wigglytuff Slayer              |    3 |  0.1% | very rare          |
| Grumpig Slayer                 |    3 |  0.1% | very rare          |
| Oinkologne (Female) Mirror Atk | 3842 | 93.8% | almost any will do |

(Numbers above are a snapshot of the reference
{{dive:species_display}} {{dive:league_display}} dive; the actual
table on your dive shows its own live values.)

The **IVs** column is the count of IV spreads out of
{{dive:iv_space_size}} that meet this flavor's stat cuts. The **%**
column is that count expressed as a fraction of the IV space - the
same number as the IVs column, just in percent form for quick
scanning. In the example table above, General Good covers ~99.6% of
the IV space (almost any wild catch clears its cutoffs), while
Fortified Diggersby and the two Slayer cuts each cover a handful of
spreads (almost every catch misses them). Use **%** for "how often does this flavor
come up at random"; use **Catches needed** (described next) to turn
the same information into a tangible catch count.

The **Catches needed** column is the expected number of catches to
hit at least one qualifying IV spread, with 50-75% probability. The
column assumes an IV floor of 0/0/0 unless stated otherwise; that
matches plain wild spawns. Weather-boosted, raid, hatched, traded,
research-reward, and Shadow-rescue catches use higher IV floors and
need correspondingly fewer catches - see the
[Pokemon Go Wiki's IV floor reference](https://pokemongo.fandom.com/wiki/Individual_Values)
for the per-source floor table.

Below the table, each flavor has its own collapsible card:

- **Header**: flavor name + stat signature (e.g. `93.67 Def, 148 HP`).
  The stat signature is the minimum each constrained axis has to
  clear.
- **Body - gains paragraph**: a short sentence naming the opponents
  and shield scenarios this flavor wins relative to General Good.
- **Body - losses paragraph** (only shown for non-General flavors):
  the matchups the flavor gives up relative to General Good. This is
  the tradeoff.
- **Body - threshold ladder** (on General Good): a bulleted list of
  the exact Def / Atk / HP combinations that clear specific opponents.
  This is the "what is each part of the cut buying me" detail.

The cards default to the General Good flavor open and the rest collapsed.
Click any header to expand.

## The namesake guarantee

For `{Opp} Slayer` and `Fortified {Opp}` flavors, the flavor's name
**names a specific opponent** - and that opponent is guaranteed to
appear in the gains list. Lapras Slayer wins Lapras. Fortified
Greedent wins Greedent. This is a hard invariant enforced by the
renderer: if the cut's mechanics don't actually flip the named
matchup, the flavor gets a different name (or gets dropped).

The namesake guarantee means the flavor card can be read as a
contract: **"name the opponent in the flavor, look at the gains
list, verify the matchup is there."** If it isn't, that's a bug in
the renderer and worth reporting.

Two namesakes can't merge into one flavor: if two cuts produce the
same stat signature, they end up as separate cards with
disambiguators in the name (e.g. `Lapras Slayer (123.74+ Atk)` vs
another slayer sharing the cut).

## Distinction from Threshold Tiers

Threshold Tiers and the IV Flavor Guide answer **different questions
about the same data**. They overlap, sometimes confusingly, and the
distinction is worth getting straight:

- **Threshold Tiers** tell you *"what cutoff do I need to clear to
  hit this tier, and which IV spreads qualify?"* Tier cards are
  named after their mechanical anchor (e.g. "Lapras Slayer" because
  the cut comes from Lapras's breakpoint), list every IV spread that
  meets the cut, and show you the full list of per-opponent anchors
  the tier clears. Tier cards are **mechanical**.
- **IV Flavor Guide** tells you *"what archetype does this cluster
  of IV spreads represent, and what tradeoff does picking it make?"*
  Flavor cards name the play-style, name one or two load-bearing
  gains, name one or two load-bearing losses, and skip the
  exhaustive anchor list. Flavor cards are **editorial**.

The tier-name unify (shipped 2026-04-23) means the two surfaces now
share the same flavor name: a Threshold Tier card named "Lapras
Slayer" and the flavor card named "Lapras Slayer" refer to the same
cut. But you read them for different reasons. Start with the flavor
card if you haven't picked a direction; drop into the tier card
once you want the full anchor list.

A note the zone itself carries at its top: *"This IV Flavor
Guide and the Threshold Tiers answer different questions and may
not line up 1:1."* The places they don't line up are usually:

- A flavor with a namesake has a small member count driven by the
  gain, but a tier with the same cut may list many more opponents
  it incidentally clears.
- A tier with no named anchor ("General" or "Atk X+") has no
  flavor-side name drama - the flavor just becomes "General Good"
  or "Attack Weight."
- TOML-authored tier names pass through to flavor names unchanged;
  auto-derived tier names get mapped through `refine_flavor_names`.

## Worked example: {{dive:species_display}} in {{dive:league_display}}

Five flavors on the reference dive (a 2026-07 snapshot; your dive's
zone carries the live values), in the order they're presented:

**General Good** (4081 IV spreads, ~99.6%) - the broad cut. 100.97
Def and 156 HP as a bulk baseline, 107.21 Atk as a coverage floor.
Doesn't chase a specific opponent; sits above most of the meta. The
threshold-ladder in its card names every def/HP step and what it
unlocks (101.50 Def with 156+ HP for the Lapras and Kingdra sets,
103.38 Def with 164+ HP for Florges and Feraligatr 0-0, and so on).
Recommended for most players.

**Fortified Diggersby** (2 IV spreads) - defensive namesake. Trades
attack range (no Atk floor) for a 114.62 Def cut with 163 HP. Gain:
Diggersby 1-1 / 1-2 / 2-2, Corsola (Galarian) 1-2, Dondozo 1-1 flip
into wins. Loss: Cradily (Acid) 1-0, Dragonair 2-1, Dusclops
(Shadow) 1-2 drop out (the higher Def cut excludes Def-sacrificing
IV spreads that clear other matchups via the attack side).
Vanishingly rare - 2 of the 4096 spreads.

**Wigglytuff Slayer / Grumpig Slayer** (3 IV spreads each) -
offensive namesakes sharing a shape. Trade bulk for a 116.21 /
116.44 Atk cut while holding 160 HP. Gain: the namesake matchup
plus Azumarill 1-2 and Clodsire 1-2. Loss: Annihilape (Close
Combat+Rage Fist) 2-1, Charjabug 1-1, Corsola (Galarian) 0-1 drop
out (low-Def IV spreads lose the defensive matchups).

**Oinkologne (Female) Mirror Atk** (3842 IV spreads, ~93.8%) - the
mirror-synth family: 109.18 Atk with 155 HP, the attack cut the
mirror matchup needs. Broad, because most spreads already clear it.

Reading them together: General Good is the default pick; the rare
namesakes are the tradeoffs to consider if you care about the
Diggersby-family defensive matchups or the Wigglytuff / Grumpig
flips specifically. Each flavor's category also carries an envelope
shape (see the [Envelope Position](../envelope-position/) guide) -
rendered on the matching composite card in the Per-matchup IV finder
- telling you whether its members reliably beat the anchor band or
just tilt in the right direction on average.

## Where to go next

- **[Threshold Tiers](../threshold-tiers/)** - the mechanical tier
  cards that drive the flavor-naming. When a flavor says "Lapras
  Slayer," the Threshold Tier with the same name is where the
  cutoff came from.
- **[Envelope Position](../envelope-position/)** - each flavor's
  category carries an envelope shape (rider-top, straddles band,
  etc.), shown on the matching composite card in the Per-matchup IV
  finder. The shape tells you whether the flavor's win-rate lift is
  consistent across members or only shows up on a sub-cluster.
- **[Reading a CD Article](../cd-article/)** - the CD article's IV
  Recommendations card grid is a compact distillation of the flavor
  cuts, one card per form.
- **[How This Works](../how-this-works/)** - if you want the short
  version of how the simulation sweep that powers all of this is
  built.
