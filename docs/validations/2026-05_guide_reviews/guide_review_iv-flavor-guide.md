# Mercuryish review — IV Flavor Guide

Source: `guides/iv-flavor-guide/body.md`. **This file rewritten 2026-05-16
with mercuryish's amended IV-Flavor-Guide feedback (5/4/26).** The
original review file only had a G2 terminology audit because mercuryish
hadn't given specific IV-Flavor-Guide feedback yet; this version
incorporates his six concrete items.

---

## Item 1 [IFG-1]: explain the `%` column under "How to read the zone"

**Mercuryish:** "Under the 'How to read the zone' subheading, the % column
is not explained."

**Current** (`body.md:98-103`):

```text
Top of the zone: a one-sentence species-level summary ("In Great
League, {{dive:species_display}} has N flavors: A, B, C") plus an
overview table with one row per flavor:

| Flavor                     |  IVs |     % | Catches needed     |
| -------------------------- | ---: | ----: | ------------------ |
| General Good [Recommended] | 4027 | 98.3% | almost any will do |
```

The text after the table (lines 109-115) explains the **IVs** and
**Catches needed** columns but **never explains the `%`** column.

**Proposed:** add a sentence to the existing per-column explanation
paragraph (`body.md:109-115`). Current text:

```text
The **IVs** column is the count of IV spreads out of
{{dive:iv_space_size}} that meet this flavor's stat cuts. The
**Catches needed** column is the expected number of catches to hit
at least one qualifying IV with 50-75% probability, assuming
uniformly random IVs (accurate for wild catches; less accurate for
traded or raid Pokemon with their own IV floors).
```

Replace with:

```text
The **IVs** column is the count of IV spreads out of
{{dive:iv_space_size}} that meet this flavor's stat cuts. The **%**
column is that count expressed as a fraction of the IV space - a
quick visual for "how big is this flavor relative to all legal IV
spreads." The **Catches needed** column is the expected number of
catches to hit at least one qualifying IV spread (more on this
column below).
```

**Notes:** also folds in the G2 terminology fix on "IV spread."

---

## Item 2 [IFG-2]: rephrase "Catches needed" wild-vs-floor framing

**Mercuryish:** "The current wording of the 'Catches needed' explanation
fails to acknowledge the change for spawns boosted by weather. Instead of
saying 'This column works for wild spawns but not for x, y, and z,' I
would just say 'This column assumes an IV floor of 0 unless stated
otherwise.' or something along those lines."

**Current** (`body.md:111-115`):

```text
The **Catches needed** column is the expected number of catches to hit
at least one qualifying IV with 50-75% probability, assuming
uniformly random IVs (accurate for wild catches; less accurate for
traded or raid Pokemon with their own IV floors).
```

**Proposed:**

```text
The **Catches needed** column is the expected number of catches to
hit at least one qualifying IV spread, with 50-75% probability. The
column assumes an IV floor of 0/0/0 unless stated otherwise; that
matches plain wild spawns. Weather-boosted, lure, raid, hatch, trade,
and research-reward catches use a higher IV floor (see below) and
need correspondingly fewer catches.
```

**Notes:** folds in IFG-3 ("state otherwise" examples) via the "see
below" pointer. Cleaner than dropping the floor list inline — keeps the
column explanation short and pushes the floor table to a dedicated
paragraph.

---

## Item 3 [IFG-3]: actually state the IV-floor exceptions

**Mercuryish:** "Adding onto the point above, it would be useful to 'state
otherwise' when appropriate. (Some legendary Pokemon have an IV floor of
1, mythical Pokemon have an IV floor of 10, etc)."

**Proposed addition:** new paragraph after the per-column explanation
(insert after IFG-2's revision, around `body.md:115`):

```text
**IV floor by source.** Pokemon Go uses a higher random-IV floor for
catches that aren't plain wild spawns. The most common cases:

| Source                               | IV floor (Atk / Def / HP) |
| ------------------------------------ | ------------------------- |
| Wild spawn (no weather boost)        | 0 / 0 / 0                 |
| Weather-boosted wild spawn           | 4 / 4 / 4                 |
| Lure / Incense                       | 0 / 0 / 0 (same as wild)  |
| Raid catch (weather-unboosted)       | 10 / 10 / 10              |
| Raid catch (weather-boosted)         | 12 / 12 / 12              |
| Hatched (egg)                        | 10 / 10 / 10              |
| Trade (great / ultra / best friend)  | 1+ / 1+ / 1+ (stepped)    |
| Research reward                      | 10 / 10 / 10              |
| Shadow Pokemon (rescued from Rocket) | 6 / 6 / 6 (rocket floor)  |

When the IV floor is higher, fewer catches are needed to hit a target
spread - the "Catches needed" column understates the rate for
non-wild sources. A raid-only species like a legendary will hit most
flavor cutoffs within a few catches.
```

**Notes:**
- Above table is the *standard* set of Pokemon Go IV floors. Worth
  spot-verifying — especially the trade-stepped floor and the rocket
  floor — before shipping.
- Doesn't promise the **Catches needed** column will recompute against
  these floors. It still assumes a 0/0/0 floor; this paragraph just
  tells the reader how to mentally adjust.
- If you'd rather make the column smart enough to choose a floor
  per-species (e.g., legendaries default to floor 10), that's a code
  change in the catch-phrase generator, not a guide edit. Out of scope
  for this review unless you want to pull it in.

**Question for you:**
- Verify the floor table is right before I ship this paragraph?
- Or skip the table and just write a sentence ("non-wild catches have
  IV floors of 1, 6, 10, or 12 depending on source; see the Pokemon Go
  wiki for the full table"), keeping the guide focused?

---

## Item 4 [IFG-4]: pick a consistent term for "General"

**Mercuryish:** "The explanation refers to the 'General' fairly often. I
would pick a consistent wording choice for it. I like 'General Good' and
'General/non-General flavors.' Including 'the General cohort' and
'General' as a proper noun separate from 'General Good' might be
confusing."

**Status:** the guide currently uses three forms inconsistently:

1. **"General Good"** (line 65, 99, 116, etc.) — the family name.
2. **"General"** as a proper noun standing for "General Good" (lines
   116, 122, 125, 195-196 etc.).
3. **"the General cohort"** as a noun for "the cohort of IV spreads
   that qualifies for General Good" (lines 52, 124).

Mercuryish wants (1) and "General / non-General" as the only two forms.
Drop the "General cohort" and proper-noun "General" usage.

**Proposed:** rewrite-pass over the affected lines.

| Line    | Current                                                                                                                                                                                                              | Proposed                                                                                                                                                                                                 |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 51-53   | "comparing the flavor cohort's win rate against the General cohort's win rate across every opponent in the dive's pool"                                                                                              | "comparing the flavor cohort's win rate against the General Good flavor's win rate across every opponent in the dive's pool"                                                                             |
| 116     | "The cards default to the General flavor open and the rest collapsed"                                                                                                                                                | "The cards default to the General Good flavor open and the rest collapsed"                                                                                                                               |
| 122     | "**Body - losses paragraph** (only shown for non-General flavors)"                                                                                                                                                   | "**Body - losses paragraph** (only shown for non-General-Good flavors)" — or keep as-is if "non-General" reads cleaner per mercuryish's "General / non-General flavors" suggestion (his exact phrasing). |
| 125     | "**Body - threshold ladder** (on General)"                                                                                                                                                                           | "**Body - threshold ladder** (on General Good)"                                                                                                                                                          |
| 195-196 | "Three flavors on the reference dive, in the order they're presented: **General Good** ..."                                                                                                                          | unchanged (uses "General Good" correctly)                                                                                                                                                                |
| 198-200 | line 198 says "General Good" but the prose after says "Doesn't chase a specific opponent; sits above most of the meta. The threshold-ladder in its card names every opponent and scenario the General floor unlocks" | "...names every opponent and scenario the General Good floor unlocks"                                                                                                                                    |
| 207-208 | "Gain: Greedent 0-0 ... Loss: Forretress 2-0 ... (the higher def cut excludes def-sacrificing IVs that clear other matchups via the attack side)"                                                                    | unchanged                                                                                                                                                                                                |
| 215-216 | "Loss: Azumarill 1-1 ... Corsola (Galarian) 0-0 drop out (low-def IVs lose the defensive matchups)"                                                                                                                  | unchanged                                                                                                                                                                                                |
| 217-218 | "Reading the three together: General is the default pick; the two namesakes are the trades to consider"                                                                                                              | "Reading the three together: General Good is the default pick; the two namesakes are the trades to consider"                                                                                             |

**Notes:** mercuryish's suggestion is "General Good" (full name) plus
"General / non-General" as a binary partition phrase. I read that as: use
"General Good" when naming the flavor, and "non-General" only as an
adjective for the partition complement. The proper-noun "General" as a
standalone reference should go.

If you'd rather adopt mercuryish's literal "General / non-General"
phrasing for the partition (instead of "General Good / non-General-Good"),
the table's row for line 122 stays as currently written (`non-General`).
That's the cleaner read; I'd default to it.

---

## Item 5 [IFG-5]: "trade" → "tradeoff" in the losses-paragraph description

**Mercuryish:** "In the 'Body - losses paragraph' description, I think it
should say tradeoff instead of trade."

**Current** (`body.md:122-124`):

```text
- **Body - losses paragraph** (only shown for non-General flavors):
  the matchups the flavor gives up relative to General. This is the
  trade.
```

**Proposed:**

```text
- **Body - losses paragraph** (only shown for non-General flavors):
  the matchups the flavor gives up relative to General Good. This is
  the tradeoff.
```

**Notes:** small fix + ties in IFG-4's "General → General Good" rule.

---

## Item 6 [IFG-6]: stat capitalization consistency (Atk / Def / HP)

**Mercuryish:** "The stats (Atk, Def, HP) have inconsistent capitalization."

**Audit needed.** Quick grep through the file shows:

- `Atk` capitalized (lines 30, 81, 86, 119, 198-211) ← canonical
- `Def` capitalized (lines 70, 75, 81, 86, 119, 195, 207, 211) ← canonical
- `HP` all-caps (lines 70, 75, 119, 195, 207, 211) ← canonical
- Lowercased: `atk`, `def`, `hp` show up in code blocks and stat-cutoff
  spec text (`atk≥X`) — these are *labels in a literal stat-cutoff
  format* and should stay lowercase to match the actual rendering on the
  dive cards.

**Action:** spot-check the file for any prose-context lowercase `atk`,
`def`, or `hp`. Likely candidates:

| Line    | Current                                                                                                                                      | Proposed                                                                   |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 67-68   | "**Premium Bulk** - a def + hp cut with no atk floor"                                                                                        | "**Premium Bulk** - a Def + HP cut with no Atk floor"                      |
| 73      | "**Attack Weight** - a pure atk cut with no def or hp floor"                                                                                 | "**Attack Weight** - a pure Atk cut with no Def or HP floor"               |
| 76      | "**High Bulk** - a pure def cut, no atk or hp floor"                                                                                         | "**High Bulk** - a pure Def cut, no Atk or HP floor"                       |
| 80-81   | "a cut (atk, or atk + hp) tied to a specific opponent's damage breakpoint"                                                                   | "a cut (Atk, or Atk + HP) tied to a specific opponent's damage breakpoint" |
| 85-86   | "a cut (def, or def + hp) tied to a specific opponent's bulkpoint"                                                                           | "a cut (Def, or Def + HP) tied to a specific opponent's bulkpoint"         |
| 117-118 | "**Header**: flavor name + stat signature (e.g. `93.67 Def, 148 HP`). The stat signature is the minimum each constrained axis has to clear." | unchanged (already correct in the example)                                 |

**Notes:** the rule is "canonical-cased (Atk / Def / HP) in prose; raw
lowercase in code blocks where the literal `atk≥X` format is being
quoted." After this pass, the file reads consistently.

---

## Item 7 [IFG-7 / G2]: "IV" → "IV spread" terminology audit

**(Original audit from pre-amend; kept for completeness — coordinate with the
specific edits above to avoid double-rewriting the same line.)**

| Line    | Current                                                                                                                          | Proposed                                                                                      |
| ------- | -------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| 1-4     | "groups the IV space into a short list of named play-style archetypes"                                                           | unchanged (IV space is fine as a noun-of-art for the 4096-spread universe)                    |
| 8-9     | "the right place to start if you're deciding which IV to chase"                                                                  | "the right place to start if you're deciding which IV spread to chase"                        |
| 26-27   | "A flavor is a **named cluster of IVs with a shared stat signature"                                                              | "A flavor is a **named cluster of IV spreads with a shared stat signature"                    |
| 50-53   | "partitioning the IV space at the flavor's cut and comparing the flavor cohort's win rate against the General cohort's win rate" | folded into IFG-4 (General Good rename)                                                       |
| 119-122 | "The **Catches needed** column is the expected number of catches to hit at least one qualifying IV"                              | folded into IFG-2 (rewrite)                                                                   |
| 134-141 | namesake guarantee section — already correct                                                                                     | unchanged                                                                                     |
| 165-169 | "**IV Flavor Guide** tells you *'what archetype does this cluster of IVs represent..."                                           | "**IV Flavor Guide** tells you *'what archetype does this cluster of IV spreads represent..." |
| 207-216 | "**Lapras Slayer** ({{dive:top_tier_clear_count}} IVs)..."                                                                       | "**Lapras Slayer** ({{dive:top_tier_clear_count}} IV spreads)..."                             |

**Notes:** "IV space" stays as a reserved noun-of-art for the 4096-spread
universe.

---

## Summary of iv-flavor-guide changes

If you accept all seven items:

- 1 paragraph rewrite (IFG-1, +1 sentence)
- 1 paragraph rewrite (IFG-2)
- 1 new paragraph + table (IFG-3, pending floor-table verification)
- ~7 terminology consistencies (IFG-4)
- 1 word fix (IFG-5)
- ~5 capitalization fixes (IFG-6)
- ~3 wording tweaks for IV/IV-spread (IFG-7, deduped against the above)

After Edit pass: rebuild guides via `python scripts/build_guides.py`. Per
G6, also flip `guides/iv-flavor-guide/guide.toml` `authorship = "ai"` →
`authorship = "both"` in the same commit.
