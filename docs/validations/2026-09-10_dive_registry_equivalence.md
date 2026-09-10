# Deriving DIVES from the pool: the equivalence gate

Step D of the website-update plan. `scripts/dive_registry.py` builds the dive
list FROM the opponent pools; `run_website_dives.DIVES` is the hand-written
literal it would replace. This is the diff, run before any swap.

## The generator is faithful

    derived  135   (GL 75, UL 60)
    literal   95   (GL 62, UL 33)
    shared slugs  71

**All 24 literal-only slugs are GENUINE drops** -- species absent from the
current pools -- and **zero are artifacts of the generator's slug rule.** That
was the thing worth checking: an earlier naive rule got 84/95 slugs right, and
a wrong slug would have silently retired a live URL and minted a new one beside
it. With the regional-prefix rule plus three explicit exceptions, the generator
reproduces every shared slug exactly.

So the divergence below is editorial content, not a bug.

## What a straight swap would do

**24 published URLs would 404** (species no longer in any pool):

    GL: Dewgong, Diggersby, Dragonair, Dusclops (+Shadow), Forretress
        (Shadow) volt-switch, Stunfisk (Galarian), Greedent, Grumpig,
        Lickilicky, Mimikyu (Busted), Oinkologne (Female), Sealeo (+Shadow),
        Seismitoad, Jumpluff (Shadow), Lapras (Shadow), Sliggoo, Talonflame,
        Wigglytuff
    UL: Kingdra, Lickilicky, Malamar, Mimikyu (Busted)

Note Mimikyu still HAS a page -- `mimikyu-great-league` is shared. What is
dropped is the separate `mimikyu-busted-*` page, because the pool carries one
entry for the species (sid `mimikyu`).

**64 pages would appear**, and they are mostly the species the rebalance and
the tier lists brought in: Deoxys (Defense), Ninetales (Alolan), Rillaboom,
Toxapex, Spidops, Charjabug, Hisuian Electrode, Mantine, Marowak, Snorlax,
Annihilape, Cresselia, Steelix, Swampert, plus both megas.

## Cost

Measured single-dive wall clock at website settings on 2026-09-09: Deoxys
(Defense) GL 6.6 min, Melmetal GL 5.8 min. At ~6 min per dive:

    literal    95 dives  ~=  9.5 h
    derived   135 dives  ~= 13.5 h

So the swap is roughly +4 hours of bake, a ~42% increase.

## The decision this leaves

Three shapes, none of them free:

1. **Full swap.** Every pool species gets a page; the 24 retire. Cleanest
   invariant ("pool == pages"), costs 13.5 h and 24 dead URLs.
2. **Derive + keep the 24 as explicit legacy entries.** No URL breaks, but
   ~159 dives (~16 h) and the pages describe species no dive sims against.
3. **Derive + retire selectively.** Keep the handful of the 24 that still
   matter editorially, retire the rest. Cheapest defensible middle, but
   reintroduces the hand-maintained list this refactor exists to remove.

Not decided here. The generator is ready either way.
