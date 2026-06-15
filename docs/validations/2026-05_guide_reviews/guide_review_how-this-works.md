# Mercuryish review — How This Works

Source: `guides/how-this-works/body.md`. After applying changes, run
`python scripts/build_guides.py` to regenerate `userdata/website/guides/
how-this-works/index.html`. Per G6, also flip `guides/how-this-works/
guide.toml` `authorship = "ai"` → `"both"` in the same commit.

---

## Item 1 [HTW-1]: rewrite "every IV is inspectable" para 2 — wrong framing

**Mercuryish:** "I am not a fan of the second paragraph under the 'We
render with Plotly so every IV is inspectable' subheading. The plot does
not say anything about how realistic it is to catch or trade for a
specific IV spread. The main appeal of the plot (as I understand it) is
to see how each IV spread compares to all other IV spreads at once, so I
would consider changing the 'how realistic it is' part to something like
that. I see the catch probability listed in the deep dive section, but
it does not include trades & is not included in the graph (which is the
section this is described under)."

**Current** (`body.md:77-80`):

```text
This is the part we built that PvPoke doesn't have. Instead of asking
"what's the best IV," it lets you ask "which of the IVs I could realistically
catch or trade for is the right one to invest in," which is usually the
question that matters in a teambuilding session.
```

**Proposed:**

```text
This is the part we built that PvPoke doesn't have. Instead of asking
"what's the best IV spread," the scatter lets you ask "how does each IV
spread compare to every other one at once" - the cluster shapes,
breakpoint banding, and outlier IV spreads are all visible on the same
canvas. The catch- and trade-probability question is answered separately
in the IV Flavor Guide and Threshold Tier sections; the scatter is the
"see them all together" view.
```

**Notes:** keeps the contrast with PvPoke's "one-IV-at-a-time" framing
that opens the section, swaps the catch/trade framing for the scatter's
actual job (everything-at-once comparison), and explicitly delegates
the catch-probability question to the right section. Also bakes in
**[G2]** (`IV` → `IV spread`).

---

## Item 2 [HTW-2]: "Opponent-IVs" → "Opponent IVs" (no hyphen)

**Mercuryish:** "The first paragraph of the 'We render with Plotly so
every IV is inspectable' subheading says 'The dropdowns at the top of
the plot (Shields / Opponent-IVs / Bait) re-color the plot live - same
data, different lens.' The actual website has 'Opponent IVs' as a
dropdown (without the hyphen)."

**Current** (`body.md:74-76`):

```text
The dropdowns at the top of the plot
(Shields / Opponent-IVs / Bait) re-color the plot live - same data,
different lens.
```

**Proposed:**

```text
The dropdowns at the top of the plot
(Shields / Opponent IVs / Bait) re-color the plot live - same data,
different lens.
```

**Notes:** mechanical fix; the dropdown label on the actual scatter is
"Opponent IVs" (verified in the dive HTML). Also affects
`deep-dive-scatter/body.md` — see that file's Item DDS-1.

---

## Item 3 [HTW-3]: define or remove "sibling forms"

**Mercuryish:** "Under the 'What you should trust, and what you shouldn't'
subheading, what are 'sibling forms'?"

**Current** (`body.md:97-101`):

```text
- Rankings across opponent pools that use different rules than
  pvpoke.com (we sometimes cap CP on opponents or include sibling
  forms; each dive's methodology footer spells out what pool was
  used).
```

**Proposed (option B from INDEX Q1):**

```text
- Rankings across opponent pools that use different rules than
  pvpoke.com (we sometimes cap CP on opponents or include both forms
  of multi-form species like Oinkologne Male/Female or Aegislash
  Shield/Blade; each dive's methodology footer spells out what pool
  was used).
```

**Notes:** drops the jargon, names the two real cases. If you'd rather
keep the term and define it inline, swap to option A from INDEX Q1
(`include sibling forms (e.g. Oinkologne Male and Female, Aegislash
Shield and Blade)`).

---

## Item 4 [HTW-4 / G2]: "every IV" referring to a triple → "every IV spread"

**Mercuryish (general feedback):** "rewriting every use of 'IV' in
reference to an IV spread to 'IV spread' would reduce confusion."

The guide already says "IV spread" in some places (e.g. "every legal IV
spread") but uses "IV" in other places where the antecedent is a triple.
The mechanical pass:

| Line  | Current                                                                                                                                                                                  | Proposed                                                                                                                                                                                              |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 17    | "to sweep one species against an opponent pool across every IV spread"                                                                                                                   | unchanged (already correct)                                                                                                                                                                           |
| 44    | "We sweep every IV, not just the top ones"                                                                                                                                               | "We sweep every IV spread, not just the top ones"                                                                                                                                                     |
| 46-50 | "PvPoke's UI shows you one IV matchup at a time, usually the stat-product rank-1 IVs on both sides. We run the simulation against every legal IV spread on your side - all 4096 of them" | "PvPoke's UI shows you one IV-spread matchup at a time, usually the stat-product rank-1 IV spread on both sides. We run the simulation against every legal IV spread on your side - all 4096 of them" |
| 52-56 | "IVs matter to PvP teambuilding in a way that rank-1 doesn't capture. Two IV spreads with similar stat products..."                                                                      | "IV spreads matter to PvP teambuilding in a way that rank-1 doesn't capture. Two IV spreads with similar stat products..."                                                                            |
| 70-71 | "The scatter plot on every dive page is a Plotly figure with one point per IV."                                                                                                          | "The scatter plot on every dive page is a Plotly figure with one point per IV spread."                                                                                                                |
| 71-73 | "Hovering a point shows you its stat-product rank..."                                                                                                                                    | unchanged                                                                                                                                                                                             |

**Notes:** Headings worth eyeballing too: "We sweep every IV, not just
the top ones" becomes a heading change.

**Question:** "rank-1 doesn't capture" — worth being explicit:
"rank-1 stat product IV spreads don't capture."

---

## Item 5 [HTW-5 / G3]: standardize "PvPoke" vs "pvpoke.com"

The guide is already mostly consistent — "PvPoke" for the tool,
"pvpoke.com" only for live site URL surface (lines 91 and 99). No edit
needed.

---

## Item 6 [HTW-6]: minor — github link (not in mercuryish's feedback)

**Current** (`body.md:114-115`):

```text
the code is at
[github.com/mglerner](https://github.com/mglerner)
```

Points to your profile rather than the repo. Worth updating if the
source repo is intended to be linkable from the public guide.

**Proposed:** defer to you — only flag if the source repo is meant to be
public.

---

## Summary of how-this-works changes

If you accept HTW-1 through HTW-4 and skip HTW-5/HTW-6:

- 1 paragraph rewrite (HTW-1)
- 1 hyphen fix (HTW-2)
- 1 jargon clarification (HTW-3)
- ~6 wording tweaks for IV/IV-spread (HTW-4)

After Edit pass: rebuild guides + flip authorship to `both`.
