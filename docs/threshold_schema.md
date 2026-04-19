# Threshold file schema

This document specifies the TOML format for `thresholds/*.toml` files and the CLI
flags that overlay them. It assumes you've read [`concepts.md`](concepts.md) — the
words *spread*, *anchor*, *breakpoint*, *CMP*, and *slayer category* are used here
without re-explaining them.

## Why TOML

The legacy format was JSON. We moved to TOML because:

- TOML supports comments. The threshold files are hand-edited and we frequently want
  to leave commented-out alternatives next to current values, or annotate why a
  spread was deprecated. JSON cannot represent that.
- `tomllib` is in the Python standard library since 3.11 (read-only), so no new
  dependency.
- Trailing commas, multi-line lists, and table headers (`[Species.Great.spreads.x]`)
  read better than deeply nested JSON braces for the kind of nested structure these
  files have.

The loader is read-only — these files are hand-edited, never written
programmatically.

## File layout

One TOML file per species, named `thresholds/<species_lower>.toml`. Top-level table
is the species name (matching the species name used by `scripts/deep_dive.py`).
Inside that, one sub-table per league. Inside each league, three sub-tables:
`spreads`, `anchors`, and (optionally) `meta`.

```toml
[Species]
sources = "free-form text describing where this data came from"

[Species.Great.meta]
# Optional. Reserved for league-level notes that don't fit elsewhere.
notes = "..."

[Species.Great.spreads.<spread_name>]
# A spread entry — see "Spreads" below.

[Species.Great.anchors.<anchor_name>]
# An anchor entry — see "Anchors" below.
```

The same structure repeats under `[Species.Ultra]`, `[Species.Master]`, etc. Leagues
are independent of each other; nothing is inherited across leagues.

### Top-level (cross-species) anchors and spreads

For things that aren't species-specific — e.g., a Lickitung damage-breakpoint anchor
that any focal species might want to reference, or a Lickitung-cohort spread used by
several deep dives — define them at the top of a shared file `thresholds/_shared.toml`:

```toml
[shared.Great.spreads.lickitung_default]
# ...

[shared.Great.anchors.lickitung_brkp_any]
# ...
```

Per-species files can reference shared entries by their fully-qualified name (e.g.,
`shared.Great.spreads.lickitung_default`). On name collision, per-species wins.

---

## Species narrative (Shape 2, 2026-04-19)

Species-level editorial prose that renders at the top of the interactive
deep dive HTML (above the scatter dashboard). Three optional sub-tables,
all nested directly under the species table (not under a league):

```toml
[Species]
sources = "..."

[Species.intro]
authorship = "expert"
author = "Drafted by Claude (Opus 4.7), not yet human-reviewed"
body = """One-paragraph BLUF intro."""

[Species.meta_role]
authorship = "expert"
author = "Drafted by Claude (Opus 4.7), not yet human-reviewed"
good_at   = """Paragraph on what this species punishes."""
bad_at    = """Paragraph on what this species loses to."""
team_role = """Paragraph on build intent / team-slot framing."""
body      = ""  # optional escape hatch: overrides the three fields above

[Species.verdict]
authorship = "expert"
author = "By Michael Lerner"
editorial = """The "should you invest?" paragraph."""
outlook   = """Optional short meta-outlook closer."""
```

**Field shape is identical to `articles/<slug>.toml`'s same-named blocks**
(`[intro]` / `[meta_role]` / `[verdict]`) — prose migrates from article
to dive with zero rewrites. See `docs/article_schema.md` for per-field
semantics. Differences specific to the dive-side usage:

* Rendered above the interactive scatter, inside a gold-bordered
  `<section class="dd-species-narrative">` block. Intro uses `<h2>Overview</h2>`;
  Meta Role and Verdict use `<h3>` sub-headings.
* Any subset of the three sub-tables may be present. Each populated block
  renders; absent blocks are silently skipped. All three absent → the
  narrative wrapper isn't emitted at all.
* `author` attribution: identical behavior to the article renderer — the
  string is rendered verbatim (HTML-escaped) as a muted italic line at the
  end of each populated block. See `docs/article_schema.md` "Per-block
  author attribution" for recommended phrasings. **Reader-visible
  distinction between AI-drafted and human-written prose depends on this
  field being set.**
* `authorship = "expert"` is the only mode wired today; `both` / `auto`
  log a warning and render verbatim as if `expert` (same as the article
  renderer). Auto-synthesis is future work.
* Per-form species (e.g. Oinkologne Male in `oinkologne.toml` vs Female
  in `oinkologne_female.toml`) each carry their own narrative, written
  from that form's vantage. Cross-form comparison framing belongs in the
  CD article's `[form_comparison]` spec, not the dive's narrative.

Species with no `[Species.intro]` / `[Species.meta_role]` / `[Species.verdict]`
tables (most species today) render dives unchanged — the Shape 2 renderer
is a pure-addition, backwards-compatible feature.

---

## Spreads

A spread is a named set of IVs. It comes in one of two forms, and the two forms are
mutually exclusive within a single spread entry.

### Stat-cutoff form

```toml
[Annihilape.Great.spreads.atk_floor]
description = "Hard atk floor — anything below this can't be a slayer candidate."
attack = 127.0       # minimum effective attack
defense = 0          # minimum effective defense (0 = no constraint)
stamina = 0          # minimum effective stamina (0 = no constraint)
```

Membership: an IV belongs to this spread iff its effective stats meet *all three*
minimums. A value of 0 means "no constraint on this stat."

### IV-list form

```toml
[Annihilape.Great.spreads.lurgan_ape]
description = "Community Slayer Ape spread popularized by lurganrocket. Predates the Counter nerf, Rage Fist addition, and Low Kick buff. Treated as a historical anchor, not a current target."
ivs = [
    [11, 10, 2],
    [15, 12, 5],
    [11, 11, 0],
    [15, 13, 4],
    # ... full list
]
```

Each entry in `ivs` is a 3-element array `[atk_iv, def_iv, sta_iv]`. Membership: an
IV belongs to this spread iff its `(atk_iv, def_iv, sta_iv)` exactly matches one of
the listed entries.

### Optional fields on either form

```toml
[Annihilape.Great.spreads.lurgan_ape]
description = "..."     # human-readable; appears in HTML output
source = "..."          # citation, URL, or attribution
deprecated = true       # excluded from default loading; explicit reference still works
ivs = [ ... ]
```

### Mutual exclusion

A spread entry must have *either* (`attack`, `defense`, `stamina`) *or* (`ivs`),
never both. The loader rejects mixed entries with a clear error.

---

## Anchors

An anchor is a named yes/no rule applied to focal IVs. Every anchor has a `kind`
field that determines how the rule is computed. Three kinds today: `cmp`,
`damage_breakpoint`, and `bulkpoint`. `damage_breakpoint` and `bulkpoint` are
mirror-image atk-side / def-side ladder anchors with the same three precision
levels — see the table in [`concepts.md`](concepts.md) for the side-by-side. The
schema is designed so additional kinds can be added later without disturbing
existing files.

### Optional fields on all anchor kinds

All anchor kinds accept these optional fields:

```toml
[Species.Great.anchors.example]
kind = "..."
description = "..."          # human-readable; appears in HTML output
source = "acidicArisen"      # expert attribution; controls HTML zone routing
display_name = "..."         # short label for HTML badges; auto-derived if absent
```

The `source` field serves two purposes:

1. **Attribution**: displayed in the Expert Analysis zone header of the deep dive HTML.
2. **Zone routing**: anchors (and spreads) with `source` set appear in the Expert
   Analysis zone. Items without `source` appear in the Simulation Deep Dive zone.
   When no items have `source`, the output has a single zone (backwards compatible).

### CMP anchors

```toml
[Annihilape.Great.anchors.cmp_vs_lurgan]
kind = "cmp"
spread = "lurgan_ape"
# Optional:
description = "Win CMP ties against the community Lurgan Ape spread."
strict = true              # default: focal_atk > max(spread.atk). false → focal_atk >= max(spread.atk)
```

How it's resolved:

1. Look up the spread named in `spread`. Must exist in this league (per-species or
   shared).
2. For each IV in the spread, compute the effective attack at the appropriate level
   (the loader handles the level math; for IV-list spreads it computes per-IV, for
   stat-cutoff spreads it uses the cutoff value directly).
3. Take the maximum. Call it `T`.
4. The anchor's check on a focal IV with effective atk `A` is `A > T` (or `A >= T`
   if `strict = false`).

A focal IV "passes" a CMP anchor iff that comparison is true.

### Damage-breakpoint anchors

These have three precision levels (see `concepts.md` for the rationale). All three
share the same `kind = "damage_breakpoint"` discriminator and the same
opponent-specification fields; they differ in which of `move` / `deals_at_least` /
`above_atk` are present.

#### Level 1 — fully explicit

You name the focal move and the damage tier you want to clear.

```toml
[Annihilape.Great.anchors.lickitung_counter_5]
kind = "damage_breakpoint"
opponent = "Lickitung"
move = "COUNTER"
deals_at_least = 5
description = "Counter must deal ≥ 5 damage to default Lickitung."
```

How it's resolved:

1. Compute the opponent's effective defense at its reference IVs (default: PvPoke
   rank-1; overridable via `opponent_ivs` or `opponent_spread`, see below).
2. For the focal `move`, find the smallest focal effective atk `T` at which the
   integer damage formula yields `≥ deals_at_least`.
3. The anchor's check on a focal IV with effective atk `A` is `A >= T`.

If no atk value in the survivor range produces enough damage, the anchor is
unreachable and is reported as such in the deep-dive output (rather than silently
producing zero passes).

#### Level 2 — reference-anchored

You name an attack floor and let the loader find the next breakpoint above it. Use
this to reproduce community spreads when you know the calibration atk but not the
exact (move, tier).

```toml
[Annihilape.Great.anchors.lickitung_brkp_above_lurgan]
kind = "damage_breakpoint"
opponent = "Lickitung"
above_atk = 127.23
description = "Find the smallest atk above 127.23 at which any focal move's damage to Lickitung steps up. Reproduces the Lurgan-era community Lickitung BP."
# Optional:
move = "COUNTER"          # restrict to one move; if omitted, all focal moves are scanned
```

How it's resolved:

1. Compute opponent reference def as in Level 1.
2. For each focal move (or just the named `move` if specified), compute the integer
   damage at every focal effective atk in the survivor range.
3. Find the smallest atk `T` such that `T > above_atk` AND damage at `T` is strictly
   greater than damage at `above_atk` for at least one move.
4. The anchor's check is `A >= T`.

The deep-dive output will report which move + tier `T` corresponds to (e.g., "Level
2 anchor `lickitung_brkp_above_lurgan` resolved to: Counter 4 → 5 at atk 127.78"), so
you can promote it to a Level 1 anchor if you want it locked in.

#### Level 3 — discover and tag

You don't specify a move or a target. The loader enumerates *every* breakpoint
against the named opponent within the survivor atk range and the anchor expands into
a *family* of sub-anchors at categorization time.

```toml
[Annihilape.Great.anchors.lickitung_brkp_any]
kind = "damage_breakpoint"
opponent = "Lickitung"
description = "Discover and tag every Lickitung damage breakpoint in the survivor range."
# Optional:
moves = ["COUNTER", "LOW_KICK", "RAGE_FIST"]   # restrict to a subset of focal moves
```

How it's resolved:

1. Compute opponent reference def.
2. For each focal move (or each move in the optional `moves` list), find every atk
   value in the survivor range where the integer damage steps up. Each (move,
   dmg_before, dmg_after, min_atk) tuple becomes a sub-anchor.
3. The parent anchor `lickitung_brkp_any` doesn't have a single threshold; instead,
   each focal IV is tagged with the *list* of sub-anchors it clears, e.g.
   `lickitung_brkp_any:[counter→5, low_kick→6]`.

The deep-dive output reports the per-sub-anchor distribution across the survivor
cohort ("28 of 30 clear `counter→5`, 12 of 30 clear `low_kick→6`, ..."), which is
how you discover which breakpoints actually matter for this species.

#### Specifying the opponent's reference defense

Damage breakpoints depend on the opponent's effective defense, which depends on the
opponent's IVs. Three options, in order of specificity:

```toml
# Default: rank-1 PvPoke IVs for the opponent in this league.
opponent = "Lickitung"

# Override with a specific IV combo.
opponent = "Lickitung"
opponent_ivs = [0, 15, 15]

# Override with a named spread (the loader iterates over each member and uses the
# strictest threshold — i.e., the atk value that clears the BP against the bulkiest
# member of the spread).
opponent = "Lickitung"
opponent_spread = "lickitung_default"   # references shared.Great.spreads.lickitung_default
```

Most of the time the default is fine and you don't think about this.

### Bulkpoint anchors

Bulkpoint anchors are the def-side mirror of damage-breakpoint anchors. Same three
precision levels, same opponent-specification mechanism, same expansion behavior at
Level 3. Different fields and different stat target. Use them to express "this
focal IV reaches a defense tier where the named opponent's damage to it drops by
1." Bulkpoint anchors route into **Bulk Slayer**, parallel to how damage_breakpoint
anchors route into Atk Slayer.

The TOML field map is mechanical:

| damage_breakpoint | bulkpoint         |
| ----------------- | ----------------- |
| `move`            | `move`            |
| `deals_at_least`  | `takes_at_most`   |
| `above_atk`       | `above_def`       |
| `moves` (filter)  | `moves` (filter)  |
| `opponent_ivs`    | `opponent_ivs`    |
| `opponent_spread` | `opponent_spread` |

`opponent_spread` differs in one resolver detail: damage_breakpoint picks the
*bulkiest* (max-def) member of the spread as worst case for the focal attacker;
bulkpoint picks the *punchiest* (max-atk) member as worst case for the focal
defender. Both choices are intentionally pessimistic; pin a specific representative
with `opponent_ivs` if max isn't what you want.

#### Level 1 — fully explicit (bulkpoint)

```toml
[Annihilape.Great.anchors.lickitung_body_slam_at_most_5]
kind = "bulkpoint"
opponent = "Lickitung"
move = "BODY_SLAM"
takes_at_most = 5
description = "Lickitung's Body Slam must deal ≤ 5 damage to the focal."
```

How it's resolved: compute the opponent's effective attack at its reference IVs,
then find the smallest focal effective def `T` strictly above which Body Slam's
integer damage to the focal is ≤ 5. The check on a focal IV with effective def `D`
is `D > T` (strict — `D == T` still takes 6 damage).

#### Level 2 — reference-anchored (bulkpoint)

```toml
[Annihilape.Great.anchors.mirror_blkp_above_lurgan]
kind = "bulkpoint"
opponent = "Annihilape"
above_def = 102.9
description = "Smallest def > 102.9 at which any of the mirror's threat moves' damage to the focal steps down. Reproduces the historical Lurgan-era 102.9 def floor."
```

How it's resolved: compute opponent reference atk, scan every threat move (the
opponent's fast + charged moves) for def thresholds above 102.9, pick the earliest.
The check is `D > T`.

#### Level 3 — discover and tag (bulkpoint)

```toml
[Annihilape.Great.anchors.lickitung_blkp_any]
kind = "bulkpoint"
opponent = "Lickitung"
description = "Discover and tag every Lickitung bulkpoint in the survivor def range."
# Optional:
moves = ["BODY_SLAM", "POWER_WHIP"]   # restrict to a subset of opponent threat moves
```

The parent anchor expands into one sub-anchor per `(threat move, damage tier)`
bulkpoint in the survivor def range, just like Level 3 damage breakpoints expand
into one sub-anchor per (focal move, damage tier). Each focal IV gets tagged with
the list of sub-anchors it clears, e.g.
`lickitung_blkp_any:[body_slam≤5, power_whip≤8]`.

The badge text in the HTML appends a trailing " bulk" to the parent display name
(`lickitung bulk`, `mirror bulk↑lurgan`) so bulkpoint tags are visually distinct
from breakpoint tags in the Bulk Slayer card, where both kinds can appear together.

---

## CLI flag overlays

Two flags, both optional, both layered on top of whatever the per-species TOML file
declares for the run.

### `--anchor-file <path>`

Loads an additional TOML file and merges it into the in-memory threshold structure
*after* the per-species file. Useful for "I want to try a few extra anchors without
editing the canonical file" — for example, an experimental BP scan you're not yet
sure you want to keep.

```bash
python scripts/deep_dive.py Annihilape \
    --thresholds thresholds/annihilape.toml \
    --anchor-file experiments/annihilape_extra_anchors.toml \
    ...
```

Merge rules: same as the shared / per-species merge — the overlay file wins on
name collision. Multiple `--anchor-file` flags are processed left-to-right, with
later files winning over earlier ones.

### `--anchor <inline-spec>`

Defines a single anchor inline for this run only. Repeatable. The format is:

```
--anchor "<name>:<key>=<value>,<key>=<value>,..."
```

Examples:

```bash
# CMP anchor against an inline IV list (semicolons separate IVs, slashes separate
# the three numbers in each IV):
--anchor "cmp_vs_v2:kind=cmp,ivs=15/3/2;15/2/4;15/5/0"

# Damage-breakpoint anchor (Level 1):
--anchor "ltung_counter_5:kind=damage_breakpoint,opponent=Lickitung,move=COUNTER,deals_at_least=5"

# Damage-breakpoint anchor (Level 2):
--anchor "ltung_brkp_above_127:kind=damage_breakpoint,opponent=Lickitung,above_atk=127.23"

# Damage-breakpoint anchor (Level 3):
--anchor "ltung_brkp_any:kind=damage_breakpoint,opponent=Lickitung"
```

Inline anchors with the same name as a TOML-declared anchor *replace* the TOML one
for this run only. Multiple `--anchor` flags with the same name resolve last-wins.

For inline CMP anchors that need an IV list, the IV list is provided directly in the
flag rather than via a `spread = "..."` reference, because there's no other way to
get IVs into a one-off command. If you find yourself typing out the same IV list more
than once, promote it to a TOML spread instead.

---

## Worked example: Annihilape Great League

A complete file showing every feature in use.

```toml
# thresholds/annihilape.toml

[Annihilape]
sources = """
Great League iteration findings (mirror slayer Nash convergence, 2026-04-07) +
community Lurgan Ape spread popularized by lurganrocket on Twitter +
expert testimony from mercuryish (Discord, 2026-04-08) confirming the Lurgan
spread predates the Counter nerf, Rage Fist addition, and Low Kick buff.
"""

# ─────────────────────────────────────────────────────────────────────
# Spreads
# ─────────────────────────────────────────────────────────────────────

[Annihilape.Great.spreads.lurgan_ape]
description = "Community Slayer Ape spread popularized by lurganrocket. Calibrated to a Lickitung damage breakpoint near atk 127.23. Treated as a historical anchor — current expert advice is to go higher attack than this baseline for CMP wins and BP security."
source = "Community spread, mercuryish testimony"
ivs = [
    [11, 10, 2], [15, 12, 5], [11, 11, 0], [15, 13, 4],
    [11, 9, 3],  [11, 9, 2],  [15, 14, 3], [15, 14, 2],
    [11, 10, 1], [11, 10, 0], [12, 9, 1],  [12, 9, 0],
    [15, 15, 1], [15, 15, 0], [15, 12, 4], [15, 13, 3],
    [15, 13, 2], [11, 9, 1],  [11, 9, 0],  [15, 14, 1],
    [15, 14, 0], [15, 12, 3], [15, 12, 2], [15, 13, 1],
    [15, 13, 0], [15, 12, 1], [15, 12, 0],
]

[Annihilape.Great.spreads.converged_mirror]
description = "30-IV cohort from the 2026-04-07 mirror slayer Nash iteration (even-strict metric, 4 rounds). Atk 129.44, def 98–101, HP 133–137."
source = "docs/validations/2026-04-07_annihilape_mirror_slayer_iteration.md"
ivs = [
    # Top atk slayers from the converged cohort:
    [15, 2, 4], [15, 5, 0], [15, 3, 2], [15, 1, 5],
    [15, 1, 4], [15, 4, 0], [15, 4, 1], [15, 2, 2],
    [15, 2, 3],
    # ... full 30-IV list
]

[Annihilape.Great.spreads.atk_floor]
description = "Below this attack, an Annihilape can't realistically be a slayer candidate against any of the named anchors."
attack = 127.0
defense = 0
stamina = 0

# ─────────────────────────────────────────────────────────────────────
# Anchors — CMP
# ─────────────────────────────────────────────────────────────────────

[Annihilape.Great.anchors.cmp_vs_lurgan]
kind = "cmp"
spread = "lurgan_ape"
description = "Win CMP ties against the community Lurgan Ape spread. The community calibrated their spread for CMP-vs-each-other; pushing higher atk than max(lurgan) wins the mirror against anyone using a Lurgan IV combo."

[Annihilape.Great.anchors.cmp_vs_mirror]
kind = "cmp"
spread = "converged_mirror"
description = "Win CMP ties against our converged mirror cohort (i.e., be the bully of the bullies)."

# ─────────────────────────────────────────────────────────────────────
# Anchors — damage breakpoints
# ─────────────────────────────────────────────────────────────────────

# Level 2: reproduce the Lurgan-era community Lickitung BP without
# needing to know exactly which (move, tier) it was originally calibrated to.
[Annihilape.Great.anchors.lickitung_brkp_above_lurgan]
kind = "damage_breakpoint"
opponent = "Lickitung"
above_atk = 127.23
description = "Smallest atk > 127.23 at which any focal move's damage to default Lickitung steps up. Reproduces the historical Lurgan-era 'Lickitung BP' calibration."

# Level 3: discover and tag every Cresselia BP in the survivor range.
# Per mercuryish, Cresselia was rumored to be one of the original
# calibration points but the exact (move, tier) was never confirmed.
[Annihilape.Great.anchors.cresselia_brkp_any]
kind = "damage_breakpoint"
opponent = "Cresselia"
description = "Discover and tag every Cresselia damage breakpoint in the survivor atk range. Mercuryish recalled Cresselia as a possible original calibration point — Level 3 lets us find which BP that was."

# Level 3: same idea for Umbreon.
[Annihilape.Great.anchors.umbreon_brkp_any]
kind = "damage_breakpoint"
opponent = "Umbreon"
description = "Discover and tag every Umbreon damage breakpoint in the survivor atk range."

# Level 1: a known mirror BP we want locked in.
# (Placeholder values — replace with the actual move + tier once measured.)
# [Annihilape.Great.anchors.mirror_counter_4]
# kind = "damage_breakpoint"
# opponent = "Annihilape"
# move = "COUNTER"
# deals_at_least = 4
# description = "Counter must deal ≥ 4 damage to a default mirror Annihilape."
```

## Notes on the loader

- TOML parsing uses `tomllib` (stdlib, Python 3.11+).
- Validation is done at load time: mutually-exclusive spread fields, missing
  references, malformed IV tuples, unknown opponent names, and unrecognized anchor
  `kind` values all raise with a clear error pointing at the file and table.
- Spreads referenced by anchors are resolved eagerly at load time. Spreads referenced
  only via `--anchor-file` overlays are resolved after the merge, so an overlay can
  reference a per-species spread.
- Anchor thresholds are computed once per deep-dive run (not per focal IV), so the
  per-focal categorization is just a series of float comparisons regardless of how
  many focals are in the survivor pool.

## Migration from the legacy JSON format

The legacy `thresholds/*.json` files used flat per-spread entries with no leagues
and no anchors:

```json
{
    "High Atk (mirror)": {"attack": 125.0, "defense": 103.0, "stamina": 0},
    ...
}
```

These are converted to TOML by wrapping in a `[Species.Great.spreads.<name>]` table
per entry. No anchors are inferred from JSON files — they need to be added by hand.
The loader will read either format during the transition period; once all files are
converted, JSON support can be removed.
