# Plan: top-N opponent filter + limited-cup dives

*Drafted 2026-07-02 (planning-only session). Origin: Reddit feedback on the
launch post (`docs/reddit/post_a/post_a.md`) -- u/LeansCenter asked for (a)
evaluating a focal against only the top 10/20/50 meta opponents instead of
the full pool, and (b) limited-cup support (e.g. "top 10 in Sunshine Cup in
GL, top 20 in Mega Cup in UL"), with the two options separate/composable.
Michael's reply noted the full result table is already buried in the HTML,
but much of the page (the card etc.) is baked during the full dive run.*

*Facts below were established by a 5-agent recon pass over the codebase
(2026-07-02); every claim carries file:line evidence. Nothing has been
implemented.*

## TL;DR

The two asks decompose cleanly, and both are cheaper than they look:

1. **Top-N opponent filter = a client-side feature.** The dive HTML already
   ships the complete per-(IV, shield-scenario, opponent) score grid
   (`SCORES_GZ`), and every headline metric (avg battle score, wins,
   Matchups Kept, "Gives up vs #1", histograms) is recomputed in
   `deep_dive_engine.js` at view time by looping over all opponents. Adding
   an opponent mask is a mechanical JS change plus one new bake-time DATA
   field (per-opponent meta rank, which is NOT currently embedded). The real
   design work is the honesty problem: the Python-baked sections (card,
   tiers, Top Picks, narrative) assert full-pool claims and must be flagged
   when a filter is active.
2. **Cup support = a pool + rankings feature, not an engine feature.**
   `deep_dive.py` already accepts `--opponents-file` with per-line moveset
   overrides; PvPoke publishes cup-specific rankings in the same schema
   (live-verified for Sunshine GL); the sweep cache is keyed per opponent
   column so a cup dive warm-serves every overlapping (opponent, moveset,
   IV) column and the slayer cache is pool-independent. A per-cup dive costs
   about one normal dive (~10 min GL cold, less warm), not a re-bake.

They compose: a cup dive page inherits the top-N control for free (its
embedded rank metadata just comes from the cup rankings).

## Established facts (recon results)

### Client side

- Full grid embedded: `SCORES_GZ` = per-(moveset, opp-IV-mode) flat uint16
  arrays, index `iv*nS*nO + si*nO + oi`, gzip+base64
  (`deep_dive.py:5584-5611`), decoded to `SCORES[key]` at load
  (`deep_dive.py:5641-5665`).
- Avg battle score is NOT pre-averaged in Python: `computeYValues` sums over
  all `nO` opponents in JS (`deep_dive_engine.js:211-263`, avg at
  `:256-260`); wins modes, Matchups Kept (`:2445`), and the paste-box
  "Gives up vs #1" column (`:1216-1218`) likewise loop `oi` over `0..nO-1`.
- All primary dropdowns are true client-side recomputes via `updateView()`
  (`deep_dive_engine.js:2787-2916`); the controls strip is ~8 `<select>`s
  with `onchange="updateView()"` (`deep_dive.py:5029-5116`) -- clean
  precedent for a new control. The paste-box overlay composes at the IV
  axis and its per-opponent column already re-renders inside `updateView`
  (`:2820-2822`), so the hook point for a mask exists.
- **No per-opponent rank metadata is embedded.** `DATA.opponents` is in pool
  order (`deep_dive.py:4163-4212`), and the committed pool file is NOT rank
  order: `gl_top50_plus_cs.txt` (78 entries) has 4 hand-extended focals
  first, then the top-50-union-CS section, then 2026-06-25 union additions
  appended, no per-line rank. So "top 10/20/50" needs rank embedded at bake
  time.
- Page size is a non-issue for this feature: a rank array is tiny; the size
  audit (`docs/s11_html_size_audit.md`) shows SCORES_GZ is only ~3.5 MB even
  on the 46 MB outlier page.

### Baked (Python) sections -- the honesty surface

Everything below is computed at bake time over the FULL pool and will not
respond to a client-side mask. Under a filtered view these are wrong-or-
misleading unless flagged (never-present-unflagged-known-wrong rule):

| Section                             | Full-pool claim                            | Evidence                             |
| ----------------------------------- | ------------------------------------------ | ------------------------------------ |
| Infographic card                    | win rate "% of N opponents", key wins/     | `deep_dive.py:3728-3853` (_cardCtx), |
|                                     | losses, robustness %, two-#1s counts       | `deep_dive_card.py:379`              |
| Methodology line (JS)               | "against {nO} opponents" hard-quotes nO    | `deep_dive_engine.js:2773-2775`      |
| Auto-derived tiers + ivTiers colors | thresholds from full-grid flips/boundaries | `deep_dive.py:3518-3620`             |
| Top Picks / recIvs                  | avg rank over all opponents                | `deep_dive.py:2995-3037, 3446-3449`  |
| IV Flavor Guide narrative           | derives from full-pool tiers/boundaries    | `deep_dive.py:2721-2859`             |
| Notable-IVs census counts           | sweeps damage boundaries over whole pool   | `deep_dive.py:3136-3138`             |
| clusterGaps overlay                 | Python-precomputed full-pool averages      | `deep_dive.py:4314-4341`             |
| Slayer "anchors N/M" checklist      | denominator from pool-derived auto anchors | `deep_dive.py:7287-7295, 7373-7375`  |

Subset-SAFE: the mirror-slayer categories themselves (focal-vs-focal
iteration, pool-independent, `deep_dive_slayer.py:250-282`); per-opponent
anchor-flip and boundary bullets stay individually true but list
out-of-subset opponents.

### Replay / re-render path

The replay blob holds the full render-input state including all per-opponent
grids (`deep_dive.py:7770-7797`), so a subset re-render without re-simming
is data-feasible -- but `render_dive_html` has no subset parameter
(`deep_dive.py:6085-6170`), the card robustness headline re-SIMS at render
time (`deep_dive.py:5449-5464, 917-979`; minutes-not-seconds at k=512), and
**this checkout has no `userdata/replay/` or `userdata/website/` at all** --
verify where the blobs from the 2026-06-28 bake live before planning a
re-render-only rollout. Fallback rollout vehicle: a warm chain re-run (sweep
cache all-hits, slayer cache warm), which is hours not days.

### Cups / rankings / cache

- `data.py` is hardwired to all/overall rankings for great/ultra/master
  (`data.py:160-164`), but the fetch layer takes arbitrary URLs with the
  same TTL/atomic caching (`data.py:34-48`; `load_group` is the precedent,
  `:182-190`).
- PvPoke publishes cup rankings in the same schema:
  `rankings/<cup>/overall/rankings-<cp>.json` -- live-verified 2026-07-02
  for `sunshine` GL: HTTP 200, 455 entries, each with the `moveset` field
  `get_default_moveset` needs. NOT all cups necessarily have rankings
  (some have `rankingAlias` / `hideRankings`) -- check per cup.
- The cached gamemaster already carries 24 cups (incl. `sunshine`, `mega`)
  with machine-readable include/exclude filters (filterType type/tag/id) and
  formats; zero code reads them today.
- Sweep cache: keyed per opponent COLUMN; "removing/reordering opponents is
  all-hits" is the module's own docstring (`sweep_cache.py:4-9`). Column key
  = opp species/shadow/IVs/level/moveset (`:204-214`); opponent IVs come
  from the gamemaster `defaultIVs` keyed by CP cap only
  (`pokemon.py:368-383`), so same-CP cups reuse them. A cup-specific
  opponent MOVESET mints a new column key = honest miss = new sims, additive
  (existing columns untouched). Slayer cache has no pool in its key
  (`slayer_cache.py:68-111`) -- fully warm for a cup dive of a known focal.
- v7 gamemaster hash is `md5(pokemon+moves)`, so cup/format churn never
  invalidates anything (`sweep_cache.py:122-157`).
- Bake economics: GL dive ~10.2 min mean cold, UL ~24.6 min
  (`overnight_eta.py:63-77`); the "~16h" Reddit figure matches the repo's
  "~16-20h" full-chain estimate incl. the ~7h ML tail; the actual 2026-06-28
  bake was 9h54m. A cup pilot is minutes-per-focal, not a re-bake.
- Site plumbing gaps for cups: `build_website_index._parse_dive_slug`
  recognizes only great/ultra/master suffixes (`build_website_index.py:52-54,
  317-323`) -- a cup slug silently falls out of the index today.
  `verify_overnight`'s completeness guard is GL-only and knows nothing of
  cup dives. `deep_dive.py` already has `--opponents-file` + per-line
  `| fast=... | charged=...` overrides and an `opponentLabel`
  (`deep_dive.py:6207-6226, 4196`) -- a cup dive is expressible today with
  zero engine changes if the pool file carries cup movesets inline.

## Design

### Feature 1 -- client-side opponent filter (MVP)

*(Updated 2026-07-02 after Michael's decisions: the control is a
PER-OPPONENT CHECKBOX PANEL, not a fixed top-N select. Motivating use case:
"looking at Azu, I might want to drill down and say 'How do I beat Medi'" --
single-opponent selection is a first-class use, not an edge case.)*

**Control.** A collapsible, scrollable checkbox panel in the controls strip
listing every opponent, one checkbox each, all checked by default. Ordering:
by meta rank (from `DATA.oppMetaRank`), unranked entries (CS extras, active
variants, hand-extended focals) at the very end. Convenience buttons above
the list: `All / None / Top 10 / Top 20 / Top 50` (the top-N buttons check
exactly the ranked opponents with rank <= N -- so the original Reddit ask is
two clicks). Changes fire the same `updateView()` path as the 8 existing
selects. No persistence (matches every other control; the old/new-mechanics
TODO's query-param question can fold this in later if wanted).

**Data.** Embed at bake time:

- `DATA.oppMetaRank`: per-opponent rank int or null, from
  `load_rankings(league)` position (for cup pages: the cup rankings),
  matched by speciesName; null for unranked entries (CS extras, active
  variants, hand-extended focals).
- `DATA.rankSnapshot`: the rankings snapshot date string, so the UI can say
  "top N per PvPoke rankings as of YYYY-MM-DD" (the pool itself is a drifted
  snapshot -- current GL #1 `Mimikyu (Busted)` isn't even in the pool file,
  so the label must be snapshot-honest).

**Mask semantics.** The mask is simply the checked set of opponent indices.
Unranked opponents are selectable like any other (they sort to the end of
the panel rather than being dropped -- Michael's call, 2026-07-02). The
top-N convenience buttons select `oppMetaRank != null && oppMetaRank <= N`.
The methodology line shows the real denominator: "against 18 of 86
opponents (custom selection)". Edge case to handle: zero boxes checked
(disable Apply / treat as All rather than dividing by zero).

**What recomputes under the mask** (all existing JS loops, threaded with an
index mask): scatter y-values for every y-mode, Top-IVs summary table,
histograms, Matchups Kept, paste-box "Gives up vs #1", methodology text.

**What gets flagged/hidden (honesty rule).** Whenever any opponent is
unchecked:

- A prominent banner under the controls: "Filtered view (K of M
  opponents): the scatter, summary table, and histograms reflect only your
  selection. The infographic card, tiers, Top Picks, Notable IVs, and
  narrative below are computed against the full pool of M opponents."
- Hide the clusterGaps overlay (Python-precomputed full-pool; hiding is
  honest and one line).
- Leave ivTiers scatter coloring available but covered by the banner text
  (tier definitions are full-pool). Optional later polish: auto-switch
  color mode to neutral under filter.

Baked sections are NOT recomputed in this phase -- that's the entire point
of the banner. (Recomputing tiers/narrative/card client-side would mean
porting large Python analytics to JS; explicitly out of scope.)

**Rollout.** Requires re-rendering shipped pages (new DATA field + JS).
RESOLVED 2026-07-02: this machine has NO replay blobs and a nearly-empty
sweep cache (240 columns of Medicham smoke-test leftovers), so the dev
fixture comes from a fresh local dive. **Dev dive scoped and launched
2026-07-02:** Azumarill GL with the exact production flags
(`run_website_dives.build_command` shape: gl_top50_plus_cs pool,
`--top-movesets 1 --opp-ivs both --bait both --no-thresholds --interactive
--standalone --mirror-slayer ... --split-movesets`), output to
`userdata/dives/azumarill-dev/`, replay blob auto-dumped to
`userdata/replay/`. ~10 min cold; also warms the sweep cache for every
later GL dev iteration. Site-wide rollout of the shipped pages still needs
either the bake machine's replay blobs or a warm chain re-run -- decide at
implementation time.

### Feature 2 -- limited-cup dives (pilot one cup, then generalize)

Server-side, per-cup baked pages -- NOT a client-side pool swap (a cup meta
contains opponents absent from the baked grids, so client-side is
impossible; recon confirmed).

**Active-cup scan (2026-07-02, `../pvpoke` @ `00f0afe7f`).** Active formats
(showFormat, rankings published), curated-meta size / ranked-universe size:

| Cup                   | CP    | Meta group | Ranked | Type restriction                 |
| --------------------- | ----- | ---------- | ------ | -------------------------------- |
| Equinox Cup (Devon)   | 1500  | 20         | 488    | fire/flying/grass/ground/normal  |
| Bastille Cup (Devon)  | 1500  | 27         | 225    | bug/dragon/poison/steel/water    |
| Tsuki Cup (BF)        | 1500  | 34         | 207    | fairy/ghost/ice/normal/rock      |
| Copa Diluvio (BF)     | 1500  | 38         | 140    | dark/steel/water/dragon          |
| Summer Cup            | 1500  | 44         | 651    | normal/grass/fire/water/elec/bug |
| Liga Ultra (BF)       | 2500  | 41         | 885    | (exclusion list only)            |
| Coupe du Sillage (BF) | 10000 | 34         | 225    | fairy/flying/ice/psychic/water/N |

**Pilot candidate: Equinox Cup** (smallest curated meta at 20 species, GL
CP 1500 so opponent default IVs share the existing key path) -- pending
Michael's confirmation in the pre-implementation dialog (alternatives:
Bastille / Tsuki / Copa Diluvio). Useful discovery: PvPoke's curated cup
GROUP files (`groups/equinox.json` etc.) are fetchable by the existing
`deep_dive.py --group` path today, so the pilot pool can start from the
curated 20-species meta rather than a rankings top-N slice; movesets still
come from the cup rankings per the decided policy.

1. **Rankings.** Extend `data.py`: `load_rankings(league, cup="overall")`
   (or a sibling `load_cup_rankings(cup, cp)`) using the existing
   `_fetch_json` with key `rankings_{cup}_{cp}`. Guard: not every cup key
   has rankings (rankingAlias/hideRankings) -- fail loudly with the list of
   valid cups. `get_default_moveset` grows a cup dimension with fallback to
   overall-league moveset when the species is unranked in the cup (455
   sunshine entries vs 1143 overall; coverage differs). The
   `_DEFAULT_MOVESET_FALLBACK` escape hatch (keyed (speciesId, league))
   needs the same dimension or a documented "cup ignores it" rule.
2. **Pool recipe.** `build_opponent_pool.py`: `recipe_cup_topN(cup, cp, n)`
   -> committed `opponent_pools/<cup>_<league>_top<N>.txt`, in cup-rank
   order, with per-line `| fast=... | charged=...` overrides baked FROM the
   cup rankings. This keeps `deep_dive.py` untouched for the pilot (the
   per-line override syntax is the existing escape hatch) and makes the
   pool file self-documenting. Skip `active_variants.toml` merge for cup
   dives (`--no-active-variants`) unless a variant is cup-relevant.
3. **Focal selection.** Hand-picked by Michael (meta judgment). The cup
   legality data exists declaratively in `gm['cups']` include/exclude
   filters; a validation helper is optional for the pilot (pool comes from
   cup rankings, hence already legal) and required for the generalization.
4. **Dive invocation.** Existing `deep_dive.py` flags: `--opponents-file`
   + `--opponent-label "Sunshine Cup (GL) top N"` + normal split-moveset
   config. Card/page labeling must say the cup, not bare "Great League".
5. **Site surface.** DECIDED (2026-07-02 dialog): slug scheme is
   `<species>-<cup>-cup` (e.g. `talonflame-equinox-cup`) -- the cup name
   implies league/CP, and `_parse_dive_slug` learns a cup->league map
   alongside `_LEAGUE_SUFFIXES`. Landing page gets its OWN "Cup dives"
   section, grouped by cup, below the league sections (rotating cup
   content stays out of the evergreen league lists). Extend
   `verify_overnight` or explicitly exempt cup dives from the
   completeness guard (silent-incompleteness lens).
6. **Downstream guard (gobattlekit).** Cup dives write
   `thresholds/<slug>.toml`; the gobattlekit bundler globs `*_great.toml`
   (Great-only) -- a cup slug ending in `_great` would be silently bundled
   into the iOS app's default thresholds. Either name cup thresholds so
   they cannot match (e.g. `..._sunshine1500.toml`) or put them in
   `thresholds/cups/`. This is a hard requirement, not polish.
7. **Explicitly out of the pilot:** matchup web, comparisons, ML-style cup
   guides, mega battle support (megas are in the gamemaster but our engine
   has never simmed one -- treat "Mega Cup" as its own later project with
   its own validation pass).

### Composition

Cup pages embed `oppMetaRank` from the cup rankings, so the Feature-1
control works there unchanged ("top 10 in Sunshine Cup" = the exact Reddit
ask). No extra work beyond using the right rankings source at bake time.

## Phasing and rough effort

| Phase | Scope                                                         | Effort                      |
| ----- | ------------------------------------------------------------- | --------------------------- |
| 1     | Opponent checkbox panel: DATA.oppMetaRank + panel + top-N     | ~1 session + re-render/     |
|       | buttons + mask threading + banner + tests; re-render pages    | warm re-run                 |
| 2     | Cup pilot (one cup, 3-5 focals): cup rankings loader, pool    | ~1-2 sessions + ~1h compute |
|       | recipe, slug/index, thresholds naming guard, labels           |                             |
| 3     | Generalize: more cups, legality-filter evaluation, per-cup    | on demand                   |
|       | verify_overnight coverage; (separate: mega engine validation) |                             |

Phase 1 and 2 are independent; either can go first. Phase 1 delivers the
larger share of the Reddit ask for zero sim cost.

## Decisions (Michael, 2026-07-02)

1. **UI shape -- DECIDED: per-opponent checkbox panel.** Rationale: drill
   down to specific opponents ("looking at Azu... how do I beat Medi").
   Top-N becomes convenience buttons over the same checkboxes.
2. **Unranked opponents -- DECIDED: keep, sorted to the very end** of the
   checkbox list (not dropped).
3. **Phase-1 dev fixture -- DECIDED: local dive.** No replay blobs / warm
   cache on this machine, so the smallest reasonable dive (Azumarill GL,
   production flags, top_movesets=1) was run locally 2026-07-02 to produce
   the page fixture + replay blob. Site-wide rollout vehicle still open
   (bake machine's blobs vs warm chain re-run).
4. **Cup pilot -- DECIDED: Equinox Cup** (dialog, 2026-07-02): Devon
   Equinox Cup, GL 1500, 20-species curated meta. Remaining human input:
   the FOCAL LIST for the pilot (pure meta judgment -- which 3-5 species
   are worth an Equinox dive).
5. **Cup slug + landing-page taxonomy -- DECIDED** (dialog, 2026-07-02):
   slug = `<species>-<cup>-cup` (cup implies league/CP; index parser gets
   a cup->league map); landing page gets its own "Cup dives" section
   grouped by cup, below the league sections. The implementation gate is
   CLEARED.
6. **Cup moveset policy -- DECIDED: cup-rankings movesets with
   overall-league fallback** for species unranked in the cup.

## Risks / lens-grid residue

- **Honesty x rendered layer**: the banner is the load-bearing mitigation;
  the JS methodology line must show the true denominator. Test: with topN
  active, no visible number on the page silently mixes subsets.
- **Does-it-act x index layer**: cup slugs currently fall through
  `_parse_dive_slug` -> a published cup dive would silently miss the index.
  Extend parser + add an index-presence check to the publish gate.
- **Change-propagation x gobattlekit**: the `*_great.toml` glob collision
  (Design item 6). Verify with a dry run of the bundler before the first
  cup dive ships thresholds.
- **Survive x cache layer**: cup dives are purely additive to the sweep
  cache (new column keys); same `--no-sweep-cache`-during-WIP-engine
  discipline applies. No new invalidation surface (v7 hash ignores cups).
- **Input-freshness**: `DATA.oppMetaRank` is a snapshot; label it with its
  date. The pool files themselves are drifted snapshots -- top-N semantics
  are "top N of the ranked opponents present in this dive's pool", and the
  UI copy must say so.
- **Silent-incompleteness x verify layer**: verify_overnight is GL-only
  today (existing TODO); cup dives add a second uncovered class -- note it
  in that TODO rather than solving here.

## Open questions to verify at implementation time

1. Where the 2026-06-28 bake's replay blobs live (not on this checkout) and
   whether all 44 dives have one.
2. ~~Which cup keys have real PvPoke rankings files~~ RESOLVED 2026-07-02
   via the local `../pvpoke` clone (@ `00f0afe7f`): all seven active
   formats have rankings (table above); `championshipseries` hides
   rankings and aliases `all`. Re-check freshness of the clone before the
   pilot bake (`git -C ../pvpoke pull`).
3. Exact semantics of `gm['cups']` filterType values across all 24 cups
   (needed for Phase 3 legality checking, not the pilot).
4. Whether every shipped page's SCORES matrix covers all oppIvMode keys the
   mask paths touch (the engine has a missing-key fallback at
   `deep_dive_engine.js:309-335`).
5. Warm re-run wall-clock for the 44-dive chain (logs from the June cold
   run are gone; `overnight_eta.py` has warm detection but no recorded
   figure).
6. Trivial cleanup opportunity noted in passing: stale "61 for GL" comment
   at `deep_dive_engine.js:360`.
