# Worlds 2026 robustness analysis — plan of record

Decided 2026-08-10 (Michael + Claude session; three-design adversarial panel,
verdicts preserved in session scratch). Worlds: **Aug 28-30, 2026, Moscone
Center, San Francisco** — ~2.5 weeks out at planning time.

Terminology note (Michael): the classic automated per-species pages are
**"dives"**; "deep" is reserved for deeper-than-automated work. This section is
the **"Worlds 2026 robustness analysis"** — never "deep dives".

## Confirmed format facts

- **Old mechanics.** Worlds is played in Competitors Cup, which per Niantic
  "uses the current [pre-2026-06-23] PvP battle system"
  (pokemongo.com/news/pvp-updates-competitors-cup-2026). Our default `legacy`
  engine IS that system — oracle-tested, full cache support. `mechanics='new'`
  is not used anywhere in this campaign.
- **Open Great League** 1500 + the Play! Pokemon banned list (Michael
  confirmed 2026-08-10: Worlds is NOT a limited meta like the 2026
  Internationals). `format_confirmed = true` from day one.
- **Mimikyu is banned** (Play! ban list:
  pokemon.com/us/play-pokemon/about/play-pokemon-pokemon-go-championship-series-banned-pokemon-list,
  where it is listed first; + Niantic: not eligible for Competitors Cup; it
  only functions under the new turn system. Both re-verified by direct fetch
  2026-08-10). It is
  PvPoke's open-GL #1, so the page shows it as an explicit "banned at Worlds"
  row rather than silently omitting it. Corpus sanity check: 0 Mimikyu in
  21,719 roster entries across 36 captured events.
- The June 2026 "Forever Forward" rebalance IS legal at Worlds (quarterly
  rebalances are legal immediately per the P!P handbook). Gamemaster cache is
  post-rebalance and current vs pvpoke master `397d23dc1` (pulled 2026-08-10;
  battle engine byte-identical to the vetted vintage; gamemaster delta since
  the 08-06/08 bake is purely-additive mega content).

## Evidence base

- **Tournament usage:** 36 Dracoviz events captured (commit `9a5fd67`), 33
  open-GL (EUIC/LAIC/NAIC are limited-meta and excluded from open-meta
  stats; see docs/tournament_data/README.md). Recent bucket = 16 events with
  event date >= 2026-03, 1,801 teams; top-cut = final_rank <= 8, n=128.
  All shares team-level. Every number in the meta table below was
  adversarially re-verified by independent recompute (all 55 usage rows, all
  ranks, all badges: 0 material mismatches).
- **Model side:** current post-rebalance PvPoke open-GL rankings (cache
  2026-08-09; 1,143 entries). Join trap worth remembering:
  `data.species_id()` resolves last-wins, so `duplicate`-tagged twins
  (`cradily_b`, `lanturnw`) shadow the real entries — use a duplicate-aware
  resolver.
- **CP->IV reverse-engineering stays dead** (TODO_backlog: tried, abandoned).
  Opponent IV cohorts are model-derived, never "IVs the pros ran".
- Usage evidence vs the June rebalance [RESOLVED session 4, 2026-08-10,
  web research]: Forever Forward went live IN-GAME 2026-06-02 1 p.m. PDT
  (pokemongo.com/news/go-battle-league-forever-forward; the GBL Season 27
  switchover; pvpoke merged the data the same day). So the recent-bucket
  events predate the rebalance EXCEPT Turin (2026-06-06/07, rk9.gg
  pokemon-turin-2026), which was played post-rebalance by 4 days. The
  original "all usage evidence predates the June rebalance" claim here was
  WRONG for Turin; the shipped pages state the split explicitly.

## The meta: 32 entries (31 at planning time + Thievul, added 2026-08-18)

Badges: **PLAYED** = top-25 recent usage AND top-30 current rank; **PLAYED**\*
= top-25 usage, current rank sank below 30; **MODEL** = current top-30 rank,
no meaningful tournament footprint (rebalance risers); **FORCED** = editorial
include. Split shadow entries get **per-variant** modal movesets (pooling hid
that the field runs Bug Bite Shadow Forretress while PvPoke defaults Volt
Switch). Moveset rule: per-variant modal when modal% >= 60, else
`get_default_moveset`; disagreements are shown on the page as data.

| #   | Entry               | Badge   | Usage | Rank | Moveset                                   |
| --- | ------------------- | ------- | ----- | ---- | ----------------------------------------- |
| 1   | Lickilicky          | PLAYED  | 36.9% | 2    | Rollout / Body Slam / Shadow Ball         |
| 2   | Quagsire (Shadow)   | PLAYED  | 26.3% | 8    | Mud Shot / Aqua Tail / Stone Edge         |
| 3   | Quagsire            | PLAYED  | 7.5%  | 9    | Mud Shot / Aqua Tail / Mud Bomb           |
| 4   | Forretress (Shadow) | PLAYED  | 17.5% | 15   | Bug Bite / Sand Tomb / Rock Tomb          |
| 5   | Forretress          | PLAYED  | 15.9% | 11   | Volt Switch / Rock Tomb / Sand Tomb       |
| 6   | Wigglytuff          | PLAYED* | 33.1% | 48   | Charm / Icy Wind / Swift                  |
| 7   | Corviknight         | PLAYED  | 29.3% | 19   | Sand Attack / Air Cutter / Payback        |
| 8   | Empoleon            | PLAYED  | 26.6% | 5    | Metal Sound / Hydro Cannon / Drill Peck   |
| 9   | Altaria             | PLAYED  | 24.4% | 4    | Dragon Breath / Sky Attack / Flamethrower |
| 10  | Feraligatr          | PLAYED  | 19.3% | 14   | Shadow Claw / Hydro Cannon / Ice Beam     |
| 11  | Stunfisk            | PLAYED* | 18.9% | 71   | Thunder Shock / Mud Bomb / Discharge      |
| 12  | Corsola (Galarian)  | PLAYED  | 17.2% | 16   | Astonish / Night Shade / Power Gem        |
| 13  | Azumarill           | PLAYED  | 14.2% | 21   | Bubble / Ice Beam / Play Rough            |
| 14  | Medicham            | PLAYED* | 13.6% | 33   | Psycho Cut / Ice Punch / Dynamic Punch    |
| 15  | Tinkaton            | PLAYED  | 13.4% | 3    | Fairy Wind / Gigaton Hammer / Bulldoze    |
| 16  | Guzzlord            | PLAYED  | 13.1% | 24   | Dragon Tail / Brutal Swing / Sludge Bomb  |
| 17  | Gourgeist (Super)   | PLAYED* | 12.9% | 87   | Incinerate / Seed Bomb / Shadow Ball      |
| 18  | Togekiss            | PLAYED* | 12.0% | 112  | Peck / Aura Sphere / Psyshock             |
| 19  | Aegislash (Shield)  | FORCED  | 4.5%  | 65   | Psycho Cut / Shadow Ball / Gyro Ball      |
| 20  | Ninetales           | MODEL   | 3.9%  | 12   | Ember / Weather Ball (Fire) / Energy Ball |
| 21  | Jumpluff            | MODEL   | 1.3%  | 17   | Fairy Wind / Acrobatics / Energy Ball     |
| 22  | Fearow              | MODEL   | 1.9%  | 20   | Peck / Drill Peck / Drill Run             |
| 23  | Kingdra             | MODEL   | <1.3% | 23   | Dragon Breath / Surf / Swift              |
| 24  | Sableye (Shadow)    | MODEL   | 4.7%  | 30   | Shadow Claw / Foul Play / Drain Punch     |
| 25  | Jellicent           | PLAYED  | 11.7% | 10   | Hex / Surf / Shadow Ball                  |
| 26  | Clodsire            | PLAYED  | 9.3%  | 18   | Poison Sting / Stone Edge / Earthquake    |
| 27  | Furret              | PLAYED  | 10.6% | 27   | Sucker Punch / Swift / Trailblaze         |
| 28  | Altaria (Shadow)    | PLAYED  | 4.6%  | 6    | per-variant modal TBD at bake             |
| 29  | Grumpig             | PLAYED* | 7.3%  | 43   | Psywave / Dynamic Punch / Shadow Ball     |
| 30  | Diggersby           | PLAYED* | 8.3%  | 41   | Mud Shot / Fire Punch / Scorching Sands   |
| 31  | Mantine             | FORCED  | 0.6%  | 53   | Wing Attack / Twister / Water Pulse       |
| 32  | Thievul             | FORCED  | 0.1%  | 41   | Sucker Punch / Night Slash / Icy Wind     |

Convention note (locked at meta.toml generation, 2026-08-10): the Usage
column above mixes conventions — split species (Quagsire, Forretress) show
per-variant shares while unsplit rows show pooled (shadow-agnostic) shares.
`worlds/meta.toml` makes **per-variant primary** (the only self-consistent
basis once variants are separate entries) and emits
`usage_recent_pooled_pct` alongside, which reproduces every number above.
Altaria (Shadow)'s literal badge is PLAYED (it was split out of a pooled
PLAYED row) while the per-variant mechanical rule says MODEL; meta.toml
records both (`badge` vs `badge_rule`) so the divergence is visible.

Aegislash ships as `aegislash_shield` — the real, battle-reachable Aegislash
(starts Shield, transforms to Blade on its first charged move). [Corrected
2026-08-10, session-2 design audit: this doc previously said "with the
'Starts Blade' variant per the existing dive convention", conflating two
shipped dives — "Starts Blade" is the display label of the SEPARATE
`aegislash-blade-great-league` dive, an unreachable diagnostic hypothetical
(src/gopvpsim/display.py DIVE_CHIP_OVERRIDES), which is NOT part of the
Worlds meta.] It is the arithmetic-hostile entry (form change disables
signature dedup, and Blade atk is NON-MONOTONE in the Shield atk IV — a +1
atk IV can drop a whole Blade level via CP-cap quantization, so closed-form
inequality cards are wrong in sign, not just imprecise) — budgeted as the
expensive pair-family and footnoted out of the closed-form pages.

Mantine (#31) is the second FORCED entry (added 2026-08-10 at Michael's
request): DragapultSim specifically called it a top Worlds threat alongside
Tinkaton. It earns no badge on our axes — open-GL rank 53, 0.61% recent
open-GL usage (11/1,801 teams) — but it was a real pick at NAIC (7.25%,
24/331 teams, in a Mantine-friendly limited meta; NAIC cup rank 5), which is
the likely context for the callout. Its provenance chip states all of this.
Moveset: PvPoke default, which matches the NAIC field modal (19/24 ran Wing
Attack / Twister / Water Pulse). Once the amber pipeline exists,
Tinkaton-vs-Mantine is the designated validation pair: DragapultSim's thread
(x.com/DragapultSim/status/2083251310996939262) published specific numbers —
Tinkaton needs 110.21 atk to guarantee the Gigaton-2-shot breakpoint (12/6/11
best spread) or 108.27 atk targeting rank-1 Mantine (4/1/12); Mantine denies
with 170.36 def (0/15/7, bulkpoints any Tinkaton under 109.28 atk) or 165.73
def (bulkpoints under 108.27) — to check our reach-or-deny card against
before shipping. [Session-2 reproduction (2026-08-10): under the minimal
ENERGY-LEGAL plan (14 Fairy Wind + 2 Gigaton — 12 fasts cannot fund 2
Gigatons) and with the quantities paired correctly, our engine gives
guarantee_cutoff = 110.18 (their 110.21 "guarantee") and per-spread cutoff
109.20 vs the 0/15/7 anchor (their 109.28), both banded <0.1 in
tests/test_worlds_tier0.py — the residual is cross-implementation
stat/rounding, not error. Their 108.27 / "rank-1 (4/1/12)" / 165.73 trio
does NOT map onto our stat model (our 4/1/12 Mantine has 159.02 def; our SP
rank-1 is 0/15/14) — treat those as unmapped, revisit in session 4.]
[Session-4 partial resolution (2026-08-10): 108.27 now maps STRUCTURALLY —
it is a per-spread ko_cutoff vs their rank-1 anchor, and our reach strip's
same quantity vs OUR rank-1 anchor (0/15/14) gives 108.22; the 0.05
residual is the anchor-spread difference under their stat model. The
165.73 deny and the 4/1/12 anchor identity remain unmapped (their stat
model differs); no further action planned — the pair pages print OUR
anchors explicitly.]

Thievul (#32) is the third FORCED entry, added 2026-08-18 — the only
entry added AFTER the meta table was first baked, and the reason the
late-add path in the Guardrails section got exercised for real. It is a
post-Community-Day editorial include (Michael): Icy Wind Thievul is
Worlds-legal (the Nickit Community Day ran 2026-08-16, before Worlds Aug
28-30, and Thievul is absent from the Play! banned list), and the
post-CD PvPoke open-GL rank is ~41. It earns no badge on our axes —
0.06% recent open-GL usage (1 of 1,801 teams), 0 of 128 top-cut teams,
and all six corpus appearances predate the CD, when Thievul had no Icy
Wind and sat at rank 122. Moveset is PvPoke's post-CD default, Sucker
Punch / Night Slash + Icy Wind.

**Icy Wind is INJECTED, and the pages say so.** We sim on the pinned
pre-Worlds gamemaster 8f1d6cca5c0f (pvpoke f60a41199), which predates
the CD: it lists Thievul with chargedMoves [NIGHT_SLASH, PLAY_ROUGH] and
no eliteMoves. Upstream pvpoke f754cd6fc ("Icy Wind Thievul",
2026-08-14) adds ICY_WIND to BOTH chargedMoves and eliteMoves, so the
lag is PROVEN, not inferred from absence — CLAUDE.md's Baxcalibur trap
avoided — and the injected pool equals current pvpoke's pool exactly.
Mechanism: a per-entry `injected_move_ids` list in `worlds/meta.toml`
(from `worlds_meta.INJECTED_MOVES`), honored by
`worlds_bake.preflight_moveset_legality` only for the declaring entry
and only for ids that exist in the pinned gamemaster's global moves db;
a DEAD injection (declared but not run) is an error at both generation
and preflight time. Disclosure: the full note on Thievul's cheat sheet,
a chip on the hub's moveset cell, and one sentence in the provenance
line every Worlds page carries. Retire the table (and this paragraph)
once the un-pinned gamemaster stably lists the move.

The late add cost one `worlds_code` bump (the preflight edit), which
would normally force a cold re-bake of all 1,860 Tier-1 planes. Per
CLAUDE.md's migration doctrine it was blessed forward instead:
`worlds_bake.WORLDS_CODE_LINEAGE` carries a written proof that the FULL
producer delta since 653d776f9028 cannot change any baked plane,
consumed once via an explicit `--bless-worlds-code` flag that records
the blessing in the manifest. Verified after the bake: 0 of the 1,860
pre-existing manifest entries changed and 0 pre-existing npz files were
touched; the 124 new planes (31 new pairs x 2 directions x 2 bait modes)
took 10.2 s.

Runner-ups that stay OUT but render as rejects on the candidate page:
Cradily (biggest faller, -34.6pp old->recent), Talonflame, Annihilape (rank
146), Lapras (0% top-cut), Moltres (Galarian). Flagged-not-explained
divergences shown on the page: Togekiss (21.1% of top-cuts, rank 112) and the
other collapsed-rank PLAYED* entries — we do not claim nerf vs model error.

## Products (six; no classic dives in scope)

1. **Hub + candidate table** (`worlds.html`, root-level like `cups.html`; one
   "Worlds 2026" card on the main index; retire-able in one commit). Full
   ~55-row candidate table incl. rejects, badges, modal-vs-default moveset
   disagreements, honesty chips, Mimikyu banned-row.
2. **Robustness matrix** (30x30): per cell, the fraction of the opponent's
   plausible IV spreads beaten, per shield scenario (never aggregated to one
   number). Green / red / **amber = IV-decided**; amber links to (4).
3. **Per-species cheat sheets** (30): one row per opponent — W/L per shield
   scenario, robustness bar, win-margin band (HP/energy at end), amber flags.
   Phone-readable. This is the front door.
4. **Per-pair detail pages** (amber pairs only): 4096x512 outcome grids per
   scenario + the reach-or-deny strip (closed-form: atk/def floors, coverage
   counts both sides, stat-product cost vs rank-1, farm-cycle ratios — no
   strategy verbs). Every printed flip threshold is confirmed by a boundary
   re-sim before ship.
5. **IV explorer** (client-side): enter IVs+level, get breakpoints reached /
   bulkpoints held vs all 30, from shipped closed-form JSON. Needs a JS port
   of best_level + damage formula with a Python-vs-JS parity test
   (non-trivial-output assertion per testing policy).
6. **CMP board**: meta-wide charge-move-priority order with per-pair IV
   thresholds to flip near-ties.

## Sim plan

Engine: `legacy` (default), both bait modes (`bait on` AND `no-bait` are
first-class planes — Worlds players want the no-bait line; footnote: no-bait
carries the documented intentional bandaid[929] divergence, sim-validated but
invisible to the bait-on PvPoke oracle). Opponent IV cohorts: top-512 by stat
product PLUS an attack-weighted cohort (best-SP-within-each-attack-band —
breakpoint-chasers run off-SP spreads; sweeping only top-512-SP would miss
exactly the spreads this analysis is about). Cohorts labeled separately.

- **Tier 0 — closed-form** (seconds): damage-tier separability => per-pair
  (move, tier, atk-cutoff, def-cutoff) tables; feeds products 4, 5, 6 and the
  equivalence classes. Aegislash excluded (footnoted).
- **Tier 1 — probe** (minutes): probe focal spreads x cohorts x 9 scenarios x
  both directions x 465 pairs. Feeds the matrix + cheat sheets.
- **Tier 2 — joint grids** (overnight max): full 4096 x 512 x 9, amber pairs
  only, usage-ranked worklist with a hard wall-clock budget cap; deferred
  pairs are listed on the page. The amber screen's false-negative rate is
  MEASURED (full grids on ~15 sampled "clean" pairs) and printed.

Session-1 **go/no-go probe**: Tier 1 on 5 pairs; count amber. If amber is
scarce, the headline pivots to the closed-form breakpoint ladder and the
matrix demotes — decided before any renderer is written.

**Probe result (2026-08-10): GO.** 5 pairs x 2 directions x (2 probe spreads
x 2 cohorts x 9 scenarios x 2 bait modes = 72 cells/direction): 60/720 cells
amber (8.3%), 8 of 10 directions carry at least one amber cell, and the amber
concentrates in specific shield scenarios rather than scattering like noise
(Tinkaton-vs-Mantine is IV-decided in the 0-0 and 2-2 lines — matching
DragapultSim's "notably in the 0s & 2s" — while Corviknight-vs-Lickilicky
ambers at 0-0/2-2 and Quagsire(S)-vs-Empoleon at the asymmetric 1-2/2-0).
58,068 sims in 8.7 s single-process (6.7k sims/s serial; the bake pool
parallelizes this), so full Tier 1 over 465 pairs projects to minutes.
Matrix confirmed as the headline; renderer work proceeds. Probe script:
session scratchpad `go_no_go_probe.py` (throwaway; the Tier-1 driver is the
committed successor).

## Guardrails (as code, per the {layer} x {lens} rule)

- Worlds planes live in `worlds/planes/*.npz` (packbits won-bool + uint16
  RAW pvpoke score; margin = score - 500 is derived at read time — corrected
  2026-08-10: the original "margin" wording would wrap negative losses in
  uint16, and the won-plane stays the win/loss authority since >500 is a
  strict inequality), NEVER the sweep disk cache. Manifest stamps engine
  hash + gamemaster hash + a worlds_code source hash (producer code lives
  outside the engine hash — the CACHE_VERSION-shaped gap); `verify_worlds.py`
  hard-fails on mismatch and runs an ML-completeness-style coverage check.
- **The bake driver is idempotent and manifest-driven: it bakes only pairs
  missing from the manifest.** Adding a mon later (Michael asked re: Cradily,
  2026-08-10) = one meta.toml row + N new pairs simmed + re-render — an
  evening, mostly unattended. Caveat: only while engine + gamemaster hashes
  are unchanged; a hash mismatch forces a full plane re-bake (by design). So
  batch late adds, and don't touch engine files mid-season.
- Tests assert: no output path matches `*_great.toml` (iOS bundler collision,
  topn_cup_filter_plan.md:281-306); the bake runs with the sweep cache
  disabled; the driver leaves `src/gopvpsim/` untouched (engine-hash bump
  would stale the 42GB GL cache). Preflight in the bake script, not prose.
- Sequencing: the pending behavior-neutral engine-hash batch (comment wording
  + parse_types relocation, TODO.md) lands BEFORE any Worlds bake, with its
  fully-blessing migration, so the GL cache eats exactly one bump.
- Ship-mode narrative policy applies: all page prose is auto-gen structure or
  left empty for Michael; a printed "deliberately not built" block (no leads /
  switches / best-6 advice) states the non-expert constraint.

## Build order (~5 sessions, cut from the bottom)

1. `scripts/worlds_meta.py` -> `worlds/meta.toml` (this table + badges +
   provenance, format_confirmed=true) + go/no-go probe.
2. Robustness driver: split a pool-parallel bool-plane core out of
   `opp_iv_robustness` (deep_dive.py:598-660; keep the (wins,total) wrapper so
   existing tests pass) + Tier 0 closed-form module + npz/manifest writer.
3. Tier 1 bake + matrix + cheat-sheet renderer + hub + index card.
4. Amber pages + reach-or-deny (with boundary re-sim confirmation) + Tier 2
   bake + FN-rate measurement.
5. IV explorer (JS port + parity tests) + CMP board + `verify_worlds.py` +
   ship gates + publish.

Post-Worlds: the section retires by removing the index card and `worlds/`
(planes are outside every shared cache). Keep `worlds/meta.toml` and this doc
as the record. Re-poll the Dracoviz `2026-worlds` slug as the event
approaches; if rosters land pre-event, the candidate table gains a "brought
to Worlds" column — usage evidence, not a re-selection.
