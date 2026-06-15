# mercuryish response — Discord-split version

Headers stripped to bold labels (no `##`), split into 6 paste-ready
messages, each under Discord's 2000-char limit. Content is verbatim
from `mercuryish_response.md` (tone-passed 2026-05-23). Send AFTER
publish, per the ordering note in that file.

Paste each block between the `=== MESSAGE N ===` markers as its own
Discord message. The markers themselves are not part of the text.

=== MESSAGE 1 ===
Thanks again for the awesome, detailed review. I fixed a lot of bugs, and I think basically everything you mentioned is fixed. Here's what changed:

**General**
- Rewrote prose to use **"IV spread"** consistently when referring to a full atk/def/hp triple, keeping bare "IV" for single-stat references. Applied across every guide and on the literal tier-card member-count labels (now "220 IV spreads" instead of "220 IVs").
- Standardized the modifier-first naming convention everywhere shadow and regional Pokemon appear: **Shadow Forretress** instead of "Forretress (Shadow)", **Galarian Corsola** instead of "Corsola (Galarian)", and so on. I think it's fixed in all user-facing text. Internal lookups still use the gamemaster's speciesName since that's how PvPoke does it under the hood, but you shouldn't see any of that.
- Oinkologne Male now displays as **"Oinkologne (Male)"** everywhere the dive surfaces the species. Matches "Oinkologne (Female)".
- Dive H1 banners and `<title>` tags now include the full display name. The Shadow Forretress dive's H1 reads "Shadow Forretress - Great League IV Deep Dive" instead of just "Forretress - Great League".

=== MESSAGE 2 ===
**How This Works**
- Rewrote the second paragraph under "We render with Plotly so every IV spread is inspectable". The framing now describes the scatter as a one-shot every-IV-spread comparison view, not a catch-probability tool (which lives in the IV Flavor Guide). This might be worth another look from you to see if the changes are good.
- Fixed **Opponent-IVs to Opponent IVs** (no hyphen) to match the live dropdown label.
- Dropped the **"sibling forms"** jargon; the relevant prose now names the actual cases (Oinkologne Male/Female, Aegislash Shield/Blade) inline. Stupid AI slop language I should have caught.

**IV Flavor Guide**
- Explained the **% column** under "How to read the zone" with a worked example using the table already in the guide.
- Rewrote the **Catches needed** framing to "assumes a 0/0/0 IV floor unless stated otherwise" instead of the wild-vs-everything-else framing.
- Named the higher-floor sources (weather, raid, hatch, trade, research, Shadow rescue) and linked the Pokemon Go Wiki IV-floor reference for the per-source table. Kept the guide-prose lean rather than embedding the full floor table ... I could change that if you think it's worth adding more text.
- Standardized on **"General Good"** for the flavor and **"non-General"** as the partition adjective. Dropped "the General cohort" and the proper-noun "General" as a standalone reference.
- "trade" became **"tradeoff"** in the losses-paragraph description.
- Fixed **Atk / Def / HP capitalization** inconsistencies (canonical case in prose, lowercase preserved only in literal cutoff format like `atk>=X`).

=== MESSAGE 3 ===
**Envelope Position**
- Dropped the "grey triangle band" descriptor; the caption now points at the **Anchor IVs** legend label, which is what you actually search for. Same fix on the Deep-Dive Scatter guide.
- Added a paragraph explaining **why the Anchor IV markers change color across the rank axis**: each triangle has a cyan border ring (the "I'm in the Anchor IVs cohort" signal) and an inner fill that matches what the IV spread would look like in the base scatter underneath. In threshold mode that's tier color or Viridis-by-score; in stat-axis Color modes it overrides to gold. Does this make sense?

**Reading a CD Article**
- First of all, this is the section I'm feeling most sketchy about. I love the idea of doing this by code, but I really doubt it can substitute for actual human analysis.
- Added the missing **orange-banner** authorship tier ("LLM-drafted, not yet human-reviewed") so the CD-article guide's authorship list matches the four tiers in Under the Hood.
- Rewrote the **obsolescence banner** section to explain the editorial trigger (an `[obsolescence]` TOML field flipped by hand), with three concrete trigger types: CD-move framing turned out wrong, opponent-meta drift, simulator bugfix invalidating the headline conclusion.

=== MESSAGE 4 ===
**Reading the Deep-Dive Scatterplot**
- Same "grey triangle band" caption fix as Envelope Position.
- Expanded the **Filled vs Outline** dropdown explanation. Pick **Filled** when reading "is my IV spread above or below the band"; pick **Outline** when comparing a specific category trace against the band without the fill in the way. Source-verified against the actual JS rendering (Filled = cyan-tinted fill at opacity 0.65; Outline = transparent fill with cyan border ring).
- Fixed **Opp-IVs to Opponent IVs** in the caption and the guide.toml description (the dropdown label is "Opponent IVs" without the hyphen).

**Threshold Tiers**
- Anchor-bullet capitalization on tier cards: the left-side anchor name (formerly lowercase like `lickilicky bulk` or `quagsire_shadow bulk`) is now title-cased and follows the same Shadow / Galarian / Alolan prefix convention as the rest of the site: **"Lickilicky bulk"**, **"Shadow Quagsire bulk"**, **"Galarian Corsola"**, etc.
- The "5 tiers vs 6" guide claim: the token resolver now counts the General-fallback card too, so the guide reports 6 instead of 5 on Oinkologne GL (matches what you actually see on the dive). Thanks for catching this.
- Stripped the redundant " bulk" suffix from anchor bullets inside def-only tier cards (e.g. Fortified Greedent). The Bulk Slayer card and the flat "Anchor-Driven Matchup Flips" section keep the suffix because their inputs can mix breakpoint + bulkpoint anchors.

=== MESSAGE 5 ===
**Under the Hood**
- Defined **xfail** inline as "expected-failure test" with two external links: pytest docs (canonical) and the Ganssle xfail-vs-skip blog post (these are refs I like).
- Rewrote the "Overriding any of this" section to be explicit that TOML editing is a contributor flow, not a client-side UI. The prior phrasing read as if any reader could click a button to add an anchor.
- Added a paragraph on the auto-fallback gate-and-replace mechanism for hand-authored anchors, so the doc clarifies what removal-like control already exists (gated supersession) vs what doesn't yet (no client-side UI).

**Corrections on the dive simulation**
- **Aegislash (Blade) whole-level rounding.** I thought I had handled this originally. My in-battle Shield-to-Blade transform already enforced this, but the focal-species path (when Aegislash (Blade) was the dive's subject) was using the standard half-level grid. So a 1/14/11 Aegislash (Blade) dive was displaying L22.5 / 1487 CP and simulating at those stats, when the real-world build is L22 / 1454 CP. Patched and re-dived. Sim now matches your reference exactly.
- Added a "Blade form only powers up in whole levels" section to the Aegislash form-change GL article, with the 1/14/11 to L22 / 1454 CP worked example and a link to the cascade1185 / Caleb Peng discovery.

=== MESSAGE 6 ===
**Where I went a different direction**
- **Aegislash UL is gone.** I was thinking of Doublade. Oops.
- **IV-floor reference**: I went with a single sentence + Pokemon Go Wiki link instead of embedding the full per-source floor table inline. Per-source numbers needed verification I didn't get to, and the wiki keeps the table maintained.

=== MESSAGE 7 ===
**Stuff your feedback triggered that wasn't on your list**
- Promoted the reviewed guides from "ai" to "AI + human" authorship, per your 5/8 OK on the "AI + human" tag without name attribution. Affects the 4 guides that were on "ai" (How This Works, CD Article, Deep-Dive Scatter, IV Flavor Guide); the other 3 were already on "both".
- **Fixed a separate paste-box bug** surfaced while debugging the Oinkologne (Male)/(Female) naming asymmetry: every Lechonk in a Poke Genie CSV was matching BOTH the Male and Female Oinkologne dives, because (a) PvPoke's gamemaster lists Lechonk's evolutions as `['oinkologne', 'oinkologne']` (both pointing to the bare Male form, orphaning Oinkologne (Female)), and (b) the paste-box parser ignored the Gender column entirely. Fixed both. The Female dive now detects only female Oinkologne and the Male dive only male, verified end-to-end on my own collection export (45 female + 34 male).
- Renamed the literal "(220 IVs)" Notable IVs / tier-card label to "(220 IV spreads)" so the dive surface matches the guide terminology.
- Tracked the "client-side add/remove anchors" feature you asked about as a future TODO; documented the contributor-only TOML flow in the Under the Hood guide for the meantime.

Thanks again for the awesome feedback!
