# Mercuryish review — Threshold Tiers

Source: `guides/threshold-tiers/body.md`. Most of mercuryish's
"Threshold Tiers" feedback is actually about the **dive cards
themselves**, not this guide — those are the four bug-report items B1-B4
in the INDEX. Items in this file are guide-text only.

Per G6, also flip `guides/threshold-tiers/guide.toml` to `authorship =
"both"` once edits applied. (Already at `"both"` per the existing toml;
verify no change needed.)

---

## Item 1 [TT-1]: "five tiers" should be six (token bug)

**Mercuryish:** "In the guide for how to interpret the threshold tiers,
you say that the Oinkologne deep dive has five tiers. Does it not have
six?"

**Current** (`body.md:131-132`):

```text
{{dive:species_display}} {{dive:league_display}} has
{{dive:tier_count}} threshold-tier cards on its featured moveset.
```

renders as

> "Oinkologne (Male) Great League has 5 threshold-tier cards on its
> featured moveset."

**Status:** the guide text is fine — `{{dive:tier_count}}` is the right
mechanism. The bug is in the token resolver (`scripts/build_guides.py:
274`), not the body.md. See **INDEX item B4** for the fix.

**No body.md change.** Once B4 lands, the rendered guide will read "6"
without touching this file.

---

## Item 2 [TT-2 / G2]: "IV" → "IV spread" pass

| Line    | Current                                                                                                      | Proposed                                                                                                            |
| ------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| 1-2     | "named stat cutoff that an IV has to clear"                                                                  | "named stat cutoff that an IV spread has to clear"                                                                  |
| 41-42   | "what an IV has to clear to be a member of the tier"                                                         | "what an IV spread has to clear to be a member of the tier"                                                         |
| 42-44   | "means the IV's effective attack stat (base + IV, at the level the CP cap allows) has to be at least 142.54" | "means the IV spread's effective attack stat (base + IV, at the level the CP cap allows) has to be at least 142.54" |
| 45      | "of the 4096 possible IV spreads"                                                                            | unchanged                                                                                                           |
| 46      | "the higher the number, the easier the tier is to hit with a catchable IV"                                   | "...with a catchable IV spread"                                                                                     |
| 53      | "every IV that does meet it"                                                                                 | "every IV spread that does meet it"                                                                                 |
| 84-91   | "any IV that meets the stricter cutoff automatically meets the looser one"                                   | "any IV spread that meets..."                                                                                       |
| 102-105 | "the stricter one trades off def-sacrificing (or hp-low) IVs the looser one keeps"                           | "...def-sacrificing (or hp-low) IV spreads the looser one keeps"                                                    |
| 109     | "The `... IVs` style member count"                                                                           | unchanged (references the literal card label) — see followup                                                        |
| 113-122 | "rough rules of thumb" bullets — "common tier"                                                               | unchanged                                                                                                           |
| 125     | "a tier with 46 members is an order of magnitude rarer than one with 460"                                    | unchanged                                                                                                           |
| 126-127 | "which of your catchable IVs fall inside each"                                                               | "which of your catchable IV spreads fall inside each"                                                               |
| 138     | "every IV that does meet it also flips"                                                                      | "every IV spread that does meet it also flips"                                                                      |
| 144-145 | "the member-IV list (collapsed at the bottom of the card) tells you which specific IV spreads qualify"       | unchanged                                                                                                           |

**Followup:** the tier card itself displays "(220 IVs)" as the member
count label (rendered by `deep_dive_rendering.py:1678`). Per
mercuryish's strict reading, this should read "(220 IV spreads)" or "(220
spreads)". **Card text issue, not a guide issue**, but worth calling out
— same renderer change would unify the dive's labeling with the guide's
terminology.

**Question for you:** apply the IV-count label change too? It's a
1-LOC fix in `deep_dive_rendering.py` and would re-render every tier
card on every dive on next publish.

---

## Item 3 [TT-3 / G3]: "PvPoke" usage check

This guide doesn't mention "pvpoke.com" or "PvPoke" anywhere — no edit
needed.

---

## Item 4 [TT-4]: bug-report cross-references (no body.md change)

The other Threshold Tiers feedback items are bug reports against the
shipped tier cards, not the guide:

- B1 — capitalization mix (coordinated with G4 naming decision)
- B2 — `bulk` suffix
- B3 — Oinkologne (Male) bare
- B4 — five vs six (handled in TT-1 above, just notes the token-resolver
  fix)

See INDEX for proposed code patches.

---

## Summary of threshold-tiers changes

If you accept TT-2 (terminology audit):

- ~10 wording tweaks for IV/IV-spread (TT-2)
- 0 paragraph rewrites
- The "5 vs 6" issue is fixed via INDEX B4 token-resolver patch.

After Edit pass: rebuild guides.
