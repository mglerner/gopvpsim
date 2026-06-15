# Mercuryish review — Reading the Deep-Dive Scatterplot

Source: `guides/deep-dive-scatter/body.md`. Per G6, also flip authorship
`ai` → `both` once edits applied.

---

## Item 1 [DDS-1]: "grey triangle band" rename (same as EP-1) + Opp-IVs hyphen fix

**Mercuryish:** "The point about the grey triangles I brought up earlier
applies here as well. You mention the grey triangles here under the
example Tinkaton plot."

**Current** (`body.md:18-25`):

```text
Scatter plot from the Tinkaton UL dive. The control strip across the
top (Moveset / Shields / Opp-IVs / Bait / Y-axis / Color / Anchors)
re-renders the plot instantly without re-simulating. On the plot
itself, each dot is one of 4,096 IV spreads. The grey triangle band
is the Anchor IVs reference cohort; the coloured overlays
(<span style="color:#3fb950;font-weight:600">Ampharos Atk</span>,
...
```

**Proposed:**

```text
Scatter plot from the Tinkaton UL dive. The control strip across the
top (Moveset / Shields / Opponent IVs / Bait / Y-axis / Color / Anchors)
re-renders the plot instantly without re-simulating. On the plot
itself, each dot is one of 4,096 IV spreads. The triangle markers
labelled <strong>Anchor IVs</strong> in the legend trace the reference
cohort's score band; the coloured overlays
(<span style="color:#3fb950;font-weight:600">Ampharos Atk</span>,
...
```

**Notes:** same fix as EP-1 + corrects `Opp-IVs` → `Opponent IVs` (the
actual dropdown label).

---

## Item 2 [DDS-2]: explain Filled vs Outline distinction

**Mercuryish:** "I do not understand the distinction between 'Filled' and
'Outline' for Anchor IVs mentioned in the guide."

**Current** (`body.md:77-80`):

```text
- **Anchors** - switches the Anchor IVs overlay between `Filled` (a
  subdued cyan blob) and `Outline` (ring markers). Outline mode is
  useful when a rider-top category sits inside the anchor band and
  you want its trace to read clearly instead of fighting the fill.
```

**Status:** the prose explains the *visual* difference but not the
*decision*. The screenshot shows triangles, not a "subdued cyan blob,"
which adds to mercuryish's confusion.

**Need to verify:** which mode renders triangles vs the cyan blob.
Possibly the screenshot is in `Outline` mode and the prose mistakenly
describes the `Filled` default in band-shape terms.

**Provisional proposal (pending verification):**

```text
- **Anchors** - switches the Anchor IVs overlay between two display
  modes:
    - **Filled** (default) - the Anchor IVs cohort renders as a soft
      colour band across the rank axis. Easier to read at a glance:
      "is my IV spread above or below the band?" answers the
      envelope-position question directly.
    - **Outline** - the Anchor IVs cohort renders as ring markers
      (one per anchor IV spread). Use this when a rider-top category
      sits inside the Filled band and you want its trace to read
      clearly without the fill behind it.
  Pick **Filled** when reading the band as a baseline; pick **Outline**
  when comparing a specific category trace against the band.
```

**Question for you:** want me to verify the Filled-vs-Outline rendering
in code first, or stub this with a TODO?

---

## Item 3 [DDS-3]: "Opp-IVs" → "Opponent IVs" (folded into DDS-1)

Already incorporated into DDS-1 above.

---

## Item 4 [DDS-4 / G2]: "IV" → "IV spread" pass

| Line    | Current                                                                                                                                   | Proposed                                                                                                                                               |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1-2     | "Each of the 4096 legal IV spreads becomes one point on the plot"                                                                         | unchanged                                                                                                                                              |
| 8-10    | "see **which specific IVs** land where"                                                                                                   | "see **which specific IV spreads** land where"                                                                                                         |
| 33-36   | "Two IVs with identical stat products get tied ranks"                                                                                     | "Two IV spreads with identical stat products get tied ranks"                                                                                           |
| 67-71   | "switches opponents between PvPoke's default IVs and each opponent's rank-1-by-stat-product IVs. Rank-1 opponents are marginally bulkier" | "switches opponents between PvPoke's default IV spreads and each opponent's rank-1-by-stat-product IV spread. Rank-1 opponents are marginally bulkier" |
| 110     | "**IVs**: the canonical `atk/def/hp` triple (e.g. `15/11/11`)"                                                                            | unchanged (defining what "IVs" means in the hover - literal label)                                                                                     |
| 138-139 | "Paste your Poke Genie CSV export into the textarea... and every matching IV on the plot gets circled"                                    | "Paste your Poke Genie CSV export into the textarea... and every matching IV spread on the plot gets circled"                                          |
| 154-160 | "Highlight IVs: the ad-hoc pin"                                                                                                           | unchanged (literal UI label)                                                                                                                           |
| 162     | "Type a comma-separated list of IV triples"                                                                                               | unchanged (defines what to type)                                                                                                                       |
| 169-174 | "**Find my IVs on the plot.** Paste your collection..."                                                                                   | "**Find my IV spreads on the plot.** Paste your collection..."                                                                                         |
| 184     | "high-CMP IVs with low battle-rank penalty are the XL-candy picks"                                                                        | "high-CMP IV spreads with low battle-rank penalty are the XL-candy picks"                                                                              |
| 188-192 | "Points that were bunched on the average view spread out, and IVs sitting on an atk breakpoint become visible"                            | "...and IV spreads sitting on an atk breakpoint become visible"                                                                                        |
| 204-208 | "Two IVs with the same score but different charge-move timings look identical on the plot"                                                | "Two IV spreads with the same score..."                                                                                                                |

**Notes:** ~8 wording tweaks. The "Highlight IVs" UI label and "IV
triple" terminology stay as-is.

---

## Item 5 [DDS-5 / G3]: "PvPoke" / "pvpoke.com" check

Consistent. No edit.

---

## Summary of deep-dive-scatter changes

If you accept DDS-1, DDS-2, DDS-4:

- 1 caption rewrite (DDS-1, includes DDS-3 hyphen fix)
- 1 paragraph expansion (DDS-2, pending verification of Filled vs Outline)
- ~8 wording tweaks for IV/IV-spread (DDS-4)

After Edit pass: rebuild guides + flip authorship to `both`.
