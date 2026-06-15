# Mercuryish review — Envelope Position

Source: `guides/envelope-position/body.md`. Per G6, also flip
authorship to `both` once edits applied (already at `"both"`; verify).

---

## Item 1 [EP-1]: rename "grey triangle band" — it's not grey

**Mercuryish:** "The Envelope Position guide describes a 'grey triangle
band' below the plot of Tinkaton IV spreads. I spent a minute trying to
find anything grey-colored before seeing that the legend indicated
something called 'Anchor IVs.' Grey is not the color I would use to
describe that, especially considering that it changes colors. (Why does
it change colors? I understand why the non-Anchor IVs do, but why
these?)"

**Current** (`body.md:34-37`):

```text
Scatter plot from the Tinkaton UL dive. The grey triangle band is the
Anchor IVs overlay. Orange <strong>Steelix (Shadow) Slayer</strong>
tightly rides the top edge (envelope-rider-top). Red
<strong>Annihilape Bulk</strong> tightly rides the bottom
```

**Proposed (rename only):**

```text
Scatter plot from the Tinkaton UL dive. The triangle markers labelled
<strong>Anchor IVs</strong> in the legend trace the band. Orange <strong>Steelix (Shadow) Slayer</strong>
tightly rides the top edge (envelope-rider-top). Red
<strong>Annihilape Bulk</strong> tightly rides the bottom
```

**Notes:** drops the misleading "grey" descriptor and points the reader
at the legend label, which is what they'll actually look for.

**For the color-shift question** ("Why does it change colors?"), see
**INDEX Q2**. Need to trace the color logic before drafting an
explanation paragraph.

---

## Item 2 [EP-2 / G2]: "IV" → "IV spread" pass

| Line    | Current                                                                                                                                                                                                                                                                   | Proposed                                                                                                                                                                              |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1-3     | "named IV category answers one question: when IVs in this category win, are they winning because the IVs themselves are special"                                                                                                                                          | "named IV-spread category answers one question: when IV spreads in this category win, are they winning because the IV spreads themselves are special"                                 |
| 6-9     | "deciding which IV to chase. A category that 'rides above' the Anchor IVs band at its rank is doing something that the rank alone doesn't buy you. A category that 'straddles' the band is doing roughly what rank already predicts, and chasing a specific IV inside it" | "deciding which IV spread to chase. ...and chasing a specific IV spread inside it"                                                                                                    |
| 14-15   | "a set of reference IVs (usually rank-1-by-stat-product or a small neighborhood around it)"                                                                                                                                                                               | unchanged (the antecedent is "reference IVs" as a cohort, fine)                                                                                                                       |
| 119-122 | "Score-wise, members are interchangeable with what a typical rank-matched anchor IV would produce"                                                                                                                                                                        | "Score-wise, members are interchangeable with what a typical rank-matched anchor IV spread would produce"                                                                             |
| 159-160 | "Work the envelope tag together with the category's member count (how many IVs qualify)"                                                                                                                                                                                  | "Work the envelope tag together with the category's member count (how many IV spreads qualify)"                                                                                       |
| 168-170 | "Most IVs already sit here; you don't need to chase anything specific"                                                                                                                                                                                                    | "Most IV spreads already sit here; you don't need to chase anything specific"                                                                                                         |
| 175-178 | "paste your own IVs into the plot, switch to the category whose tag you like, and see instantly which of your catchable IVs land inside a rider-top band vs a straddle"                                                                                                   | "paste your own IV spreads into the plot, switch to the category whose tag you like, and see instantly which of your catchable IV spreads land inside a rider-top band vs a straddle" |

**Notes:** about 6-7 places. The lead is the most reader-facing.

---

## Item 3 [EP-3 / G3]: "PvPoke" check

The guide doesn't mention PvPoke or pvpoke.com. No edit.

---

## Summary of envelope-position changes

If you accept EP-1 (rename) and EP-2 (terminology):

- 1 caption rewrite (EP-1, with optional color-shift explanation pending Q2)
- ~7 wording tweaks for IV/IV-spread (EP-2)

After Edit pass: rebuild guides.
