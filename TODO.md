<!-- TODO.md is a LIVE BACKLOG, not an append-only chronological log. Keep it
short: completed/shipped work moves to CHANGELOG.md (root-cause writeups,
dates, SHAs) or docs/TODO_archive.md (verbatim session batches); only OPEN
items and forward-looking design notes live here. When you finish an item,
delete its bullet or move the writeup out -- do not leave a 'DONE/RESOLVED'
narrative inline. This convention was set 2026-06-27 after the file hit ~1980
lines of mostly-completed chronological batches. -->

## FUTURE: PoGoDives strategy page (Michael, 2026-09-24)

Expand the Cramorant strategy article into ONE PoGoDives-strategy page with
a section per strat: Cramorant (the existing content), the stat-effect strat
(Drain Punch-style "throw the effect move into a predicted shield"; plan:
docs/statfx_strat_plan.md), and room for later ones. Not started.

Today: `scripts/render_pogodives_strategy_article.py` ->
`userdata/website/articles/cramorant-pogodives-strategy/`. Carry over its
contracts: every number recomputed from the rendered dive tensors at render
time; showcase links computed and gated by verify_url (never hardcoded --
the 2026-09-12 stale-link incident); authorship "both" with Michael's
review; ASCII-only prose; publish only on Michael's explicit go.

Prerequisites for the stat-effect section: the rule ported into the engine
behind the PoGoDives marker, certified per page it ships on (Sableye DP+FP
pages first), a migrate_cache predicate for the tier change, and a rebake,
so the section's numbers can come from real PoGoDives-tier tensors. Also
decide: keep the old slug (Cramorant dive pages link to it) or move to a
general slug with the old one redirecting. Toggle copy is already approved
(plan doc, "Page copy"); the page should also state the shield-prediction
dependence (the fragility results).

## OPEN: published dive tensors that do not reproduce (found 2026-09-23)

The statfx lab re-sims plain PvPoke for every cell it touches and checks it
against the page tensor. On **25 of 165** class pages (engine hash
`9ac12a2754a1`, same as the bake stamp) 1-92 cells per page (~0.01-0.1%)
differ. The mismatched cells are NOT a lab artifact: rebuilt through the
dive's own `build_battle_pair` path, reused across scenarios OR fresh per
scenario, they match the lab and not the tensor. Examples:

- Florges GL vs Shadow Annihilape: spreads 3161/3190 (atk 123.3775648 = an
  exact CMP tie with the opponent) and 3973/4002 (atk 123.178, loses CMP)
  appear with their score rows SWAPPED in the tensor.
- Zygarde (Complete) UL vs Mimikyu: 92 cells, e.g. spread 1044 1v1/2v1 =
  325/337 in the tensor vs 400/414 re-simmed.
- Not all CMP-related: Forretress, Giratina, Snorlax, Araquanid opponents too.

**ROOT CAUSE (diagnosed 2026-09-23): signature dedup is not exact.** On
all three probed pairs, `deep_dive.iv_sweep` with signature dedup ON
reproduces the published tensor exactly, and dedup OFF (per-profile ground
truth) differs: Florges GL vs Shadow Annihilape 396 cells, Zygarde UL vs
Mimikyu 774, Blastoise UL vs Forretress 6 (full 4096-spread columns; the
lab's stride-29 sample understated this). The columns were freshly simmed
at the bake on the current engine hash, so this is not a stale-cache or
migration problem. Two gaps in `scripts/deep_dive_signature.py`:

1. **Shadow CMP strip (line ~291).** The CMP sign is computed as
   `atk / 1.2` for shadow sides -- the exact lossy round trip `ebf5944`
   (2026-09-20) removed from the engine (`cmp_atk` now carries `raw_atk`).
   An exact CMP tie against a shadow side is signed as a win/loss, so the
   spread is grouped with, and given the fight of, a non-tie spread.
2. **Missing attack axis for the DP's debuff projection.** `_cm_buff_delta`
   (PvPoke's `attackMult -= buffs[1]`) models a chance-1 opponent-DEFENSE
   debuff (Sand Tomb, Bulldoze, ...) as +stages on the ATTACKER's attack
   inside `pvpoke_dp`, and the DP reads damage at those attack stages.
   `movable_axes` does not count that as making the attacker's attack
   movable, so those damages are never tabulated; `atk*1.25/def` vs
   `atk/(def*0.8)` then floors differently at rare boundaries and two
   "identical" spreads plan differently. Forretress (opponent side) and
   Zygarde (focal side, Bulldoze vs Mimikyu) both trace to this.

**Code FIXED 2026-09-23 (a4ca14e)**: both gaps closed; failing-first tests
on the three pairs; dedup ON == OFF on all three real pages; the default
`verify_signature_dedup.py` corpus EXACT MATCH.

**Cache: correctness already protected.** `deep_dive_signature.py` IS in
the sweep engine hash (`sweep_cache.engine_hash()` adds it; the slayer stamp
builds on that), so a4ca14e moved the hash 9ac12a2754a1 -> d78c67fd06a7 and
every cached column is now a safe miss. (An earlier note in this session
said the opposite; it was wrong.) The published site still shows the old
cells until the next bake + publish.

**Cache migration: BUILT + dry-run, NOT applied (b6e369a, 2026-09-23).**
Run these before the next bake (both default to dry-run; `--apply` writes):

    direnv exec . python scripts/migrate_cache.py --from-engine 9ac12a2754a1 \
        --predicate signature_regroup_20260923 --apply
    direnv exec . python scripts/migrate_cache.py --slayer --from-engine 9ac12a2754a1 \
        --predicate signature_fix_slayer_20260923 --apply

Dry-run results: sweep 239,091 blessed / 43,077 deleted-to-re-sim (15.3%;
26 min single-threaded); slayer 150 blessed / 0 deleted. Old-grouping
reconstruction matched the real pre-fix module on 1,504/1,504 sampled
columns. `legacy_guard_20260922` was removed unrun (unsafe: same delta).
Do NOT land another engine-hashed change before applying these, or the
predicates' from->to delta no longer covers everything.

**Bake estimate:** ~35-40 h migrated vs ~57 h cold (the 09-20 chain took
37.7 h; sweep sims were only ~1.4 h of it). Run the pre-dive checklist first.

## Thievul CD -- residue (shipped record: CHANGELOG 2026-08-15/16 + TODO_archive)

- MICHAEL: reply to u/LeansCenter on the r/TheSilphArena launch thread
  (as u/SpaceBearAI; open since 2026-08-15). Drafted bullets: 44W-44L
  -> 62W-25L at 1-1/rank-1 IVs/88-mon pool; IW+PR beats PvPoke's
  NS+IW default by ~14 wins; PvPoke overall GL rank 122 -> 41.
  Context: docs/thievul_cd_plan.md:85-109. Their post-rebalance
  IV-reshuffle question becomes actionable when the ~2-week rebalance
  lands.
- MICHAEL: HSH discord message (docs/hsh_message_notes.md) -- the
  draft is pre-Worlds stale (bullets 1 and 5 are written as future
  events that have passed); refresh to post-Worlds framing before
  sending, or kill.
- Shipped thievul robustness pages carry two wording issues from the
  pair-1 review: the 'IV tech without meta cost' card costs 5W on the
  lickilicky page (its own max-meta card shows 63W vs 58W), and the
  debuff-stage cross-check ladder was built from the rank-1 opponent
  instead of the simulated probe (stage -3 renders 21; correct is 22;
  `stage_ladder_from_rank1` in pairs/thievul_lickilicky.toml
  preserves the shipped bytes and documents it). Rebuilding with the
  current kit fixes both -- republishing is Michael's call.
- `thresholds/thievul.toml` [cd_prep] retirement rides the
  post-Worlds bundle (see the Worlds checklist below).

## Cramorant -- open items (port/campaign/publish record: CHANGELOG 2026-08-24..27 + TODO_archive)

The 2026-09-12..15 reinvestigation record (Aegislash reuse-leak fix, sheet
v6 certified 90/90 and merged, the 2026-09-15 merges + cache migrations
and the gamemaster-vintage swap recipe) is in CHANGELOG 2026-09-12 and
2026-09-15.

**Michael's three open decisions** (leave as-is until answered):

- **Guzzlord 2v2: documented cost or target?** Shipped: -1559 win-cells,
  +72.6 mean on GL Dive+Fly 2v2 nobait -- the rush pads rating onto lost
  fights (258 -> 420) and pays with 504-519 razor wins. RECOMMENDATION:
  documented cost. It passes the bar (both slice metrics positive), every
  gate retune that removes it fails the UL Dive+Fly holdout by -320..-830
  net, and it is one opponent. If "target": the only lever is the 2v2 gate
  (M5 in the deep-vet doc), which means a GL-only conditional and a new
  campaign; nothing in v6 changes.
- **Gate-column refactor.** The referee re-derived that `gate on iff
  opp_start_shields >= my_start_shields` reproduces all 9 rows.
  RECOMMENDATION: yes, but as a behaviour-neutral hygiene commit AFTER v6
  ships (own engine-hash bump with an always-true blessing predicate, like
  `neutral_batch_20260810`), together with deleting the three dead
  constants (`_POGODIVES_GATE_DPT_MAX`, `_POGODIVES_GATE_MIN_ENERGY`,
  `_POGODIVES_TANK_CHEAP_FRAC`) and their `cmp_dpt`/`cmp_dpt_e`/
  `cmp_ready_dpt`/`cheap` branches; needs `tests/test_pogodives.py`'s
  synthetic rows and `cramorant_sensitivity.py` updated. If "no": nothing
  changes; the sheet stays a 9-row table with per-row gate strings.
- **Report 9 (PvPoke `hasActed` survives `Pokemon.reset()`).** Draft text:
  `docs/pvpoke_bug_reports.md` Report 9; a standalone copy is in
  `~/coding/reports/pvpoke-report9-hasacted-2026-09-15.html` (card on
  pogo-reports.html). RECOMMENDATION: file it -- browser-verified,
  one-line fix, and it plausibly explains Report 3's unresolved 429-vs-510
  from July. If filed: note the issue number in `docs/pvpoke_bug_reports.md`
  and, once PvPoke fixes it, the Lapras page-level pin (446) in
  `tests/test_pvpoke_sandbox.py` and the article test's run1==run2 gate
  start failing -- delete the pin and keep the gate. If not filed: nothing
  changes; our verifier already emulates the page.
  Michael 2026-09-12: "make report 9 a TODO for later". Follow that file's
  filing conventions; check the issue tracker for a duplicate first.

**Lens-grid item, OPEN: the data-cache TTL keeper.** A launch-time
preflight should refuse a bare `run_website_dives.py` run without the TTL
keeper, or the runner should own the keeper. 88bec7b (2026-09-20) pins the
data cache (`GOPVPSIM_PIN_DATA_CACHE=1`) only inside `overnight_redive.sh`;
a direct `run_website_dives.py` launch -- how the 2026-09-12 rebake ran,
letting the live gamemaster refresh mid-bake -- is still unpinned.

**Post-bake Cramorant verification -- still owed** (no evidence it ran
after the 2026-09-20 bake; the strategy article is still the 2026-09-12
render): `verify_overnight.py` + the ship gates, then
`python scripts/cramorant_certify.py --league both --selftest 5`
(must print 0 bar failures, 0 exemption violations, selftest all exact) and
`cramorant_mini_sweep.py --check-tensor` on the two v6 cells in
`tests/test_pogodives_v6.py` (the Blade contamination is gone, so
--check-tensor is a full integer-exact gate again). `--league` and
`--scenario` are REQUIRED, so the bare `... --check-tensor` form that used
to stand here could not be run at all; both argv were verified against the
current pages 2026-09-20:

    python scripts/cramorant_mini_sweep.py --league great \
        --page index_m4_peck_hydro_pump_surf.html --scenario 2v2 \
        --opp-ivs pvpoke --bait nobait --cap 50 --stride 1 --check-tensor
    python scripts/cramorant_mini_sweep.py --league ultra \
        --page index.html --scenario 1v0 \
        --opp-ivs rank1 --bait bait --cap 51 --stride 1 --check-tensor

`--page` names a file in `userdata/website/cramorant-<league>-league/`, and
the `index_mN_*` numbering comes from the bake's moveset SCREEN -- re-check
the filenames after the re-dive (`index.html` is the landing, PECK / DIVE,
FLY in both leagues; the GL v6 cell is the Peck / Hydro Pump + Surf page,
the UL one is the landing). Then re-render the strategy article
(`render_pogodives_strategy_article.py`; rehearse it with `--out <scratch>`
first -- the showcase gate re-picks and page-verifies) and run
`tests/test_pogodives_article_showcases.py`.

- **DEEP RE-VERIFICATION CAMPAIGN (started 2026-09-12, Fable's first look
  at the strat; Michael: "we're free to vet things deeply").** Instruments:
  `scripts/cramorant_certify.py` (strict bar over the FULL 720-cell grid
  from the dive tensors, seconds; `--selftest N` proves the tensors are
  today's engine) and `scripts/cramorant_mini_sweep.py` (one tensor slice
  re-simmed through the production path with knob / sheet-row overrides;
  `--check-tensor` must be integer-exact at shipped knobs before any
  variant is trusted; coprime `--stride` for screens, 1 for certification).
  First full-grid read (GL page baked 2026-09-12, UL page 2026-09-11, both
  new engine): 716/720 cells pass, 4 FAIL -- GL Peck/Hydro Pump+Surf 2v2
  no-bait (both opp-IV modes, both caps), mean -3.3/-4.2, driven by
  Corviknight (-3835 flips, -324 mean) and Shadow Corviknight; the v5
  certification never had that build in GL. The UL 0v1 Dondozo "-2" does
  NOT exist at full resolution (only Jellicent is negative there, on
  rating); it was a single-spread artefact of the PvPoke-default IV run.
  Sequence: (1) mechanism-trace the failures and the big hidden
  per-opponent losers (GL 1v1 Mandibuzz/Umbreon on Dive+HP, GL 1v2
  Snorlax / Shadow Corviknight, UL 1v1 Snorlax / Miltank), (2) propose
  mechanism-not-names row changes, screen at coprime stride, (3) certify
  changed rows at stride 1 once the rebake frees the cores, (4) THEN new
  showcases and the article prose pass. Full-res compute waits for the
  rebake; tensor reads and stride screens do not.

  **STATUS 2026-09-12 late: sheet v6 IMPLEMENTED on the branch** (13-agent
  campaign; record: `docs/validations/2026-09-12_cramorant_deep_vet.md`).
  Two row changes -- (1,0) `lead_ready_ko` (terminal-KO guard), (2,2)
  `lead_ready_chip` (last-shield "can they chip us" guard, division-free);
  everything else kept, 2v1 stays exempt, Dondozo documented as a boundary
  cost (19/4096 razor ties, 0 net flips), not an exception. Stride-13 screen
  of the changed rows over all 160 slices: 0 bar failures, the 4 failing GL
  cells go -3.36/-4.27 -> +3.05/+3.35 mean, every top-SP lens >= 0 (worst
  2v2 +1.65, 1v0 +0.03); 2v2 total net +77,153 -> +77,243, 1v0 unchanged.
  Stride-61 adjacency: all 560 slices of the 7 unchanged rows identical to
  shipped. Costs to disclose: UL Peck/Surf 2v2 net +1057 -> +911 (mean
  -0.7), UL HP/Surf 2v2 bait -154 net, GL Dive+Fly 2v2 mean -0.003; the KO
  guard is NOT a perfect GL no-op when threaded (GL 1v0 Dive+Surf / HP+Surf
  mean -0.008 / -0.006, net unchanged) -- wrapper-to-threaded drift, as the
  playbook warns. Stride-1 on the 15 priority slices (both failing GL
  cells, GL top-SP margins, all 8 UL HP+Surf 2v2 slices, UL 1v0 lenses):
  15/15 pass, failing cells -3.3/-4.2 -> +3.09/+3.24 mean, cost = UL
  HP+Surf 2v2 bait mode -1200..-2000 win-cells/slice (mean flat).
  REMAINING: (a) stride-1 re-certification of the other 75 changed-row
  slices (`cramorant_recertify.py --scenarios 2v2,1v0
  --stride 1`, ~4-6 h serial under load; parallelise once the rebake frees
  cores); (b) merge order after the rebake is published: Aegislash fix
  (2e8d36b, predicate species-startswith-Aegislash), then the v6 rule
  commit (Cramorant-only, predicate = the pogodives case registry), each
  alone on its hash bump; (c) rebake the Cramorant pages and run
  `cramorant_certify.py --league both` as the ship gate; (d) THEN new
  showcases (the renderer re-picks from the survivors automatically) and
  Michael's prose pass; (e) hygiene commit deleting the three dead
  constants (needs test_pogodives synthetic rows + cramorant_sensitivity
  updated). MICHAEL'S CALLS: Guzzlord 2v2 and the gate column are the
  open decisions above; P-C (KO guard at 1v1, measured positive in GL)
  and P-D (constant-free 1v2 `lead_drained`, costs most of the row)
  next cycle.
- **LIVE ARTICLE STALE -- needs Michael's regen-vs-remove call (found
  2026-09-12).** Michael clicked the GL-vs-Jellicent showcase pair and both
  links showed the same 642 win. Audit
  (`userdata/analysis/2026-09-12_cramorant_showcase_audit/` in the clone):
  the ENGINE is fine -- our plain-PvPoke sim reproduces PvPoke's AI exactly
  on all four showcase cells (481 / 642 / 427 / 297) -- the ARTICLE is stale
  in three independent ways: (1) the four sandbox links were hardcoded
  2026-08-27 with the pre-e6827a0 turn clock, so on today's pvpoke.com they
  replay 634 / 642 / 493 (a LOSS) / 614 instead of the advertised 674 / 666
  / 541 / 573; (2) the Jellicent 2-1 premise is gone -- PvPoke's own plan
  now WINS it (Shadow Ball 100->90) and the sheet exempts (2,1), so "our
  line" IS PvPoke's there; (3) Blastoise's PvPoke default moveset moved
  Rollout -> Bite, so that showcase simmed an off-meta fight. Fixed in the
  renderer (computed + gated showcases, see the encoder note below; GL
  replacement = Mandibuzz 1-1, 460 -> 686, PROPOSED, Michael to confirm or
  pick another from the candidate list in the audit dir). STILL STALE and
  NOT touched (ship-mode prose, Michael's editorial pass): the cheat-sheet
  2-1 row (describes the retired ready-nuke window; the sheet now plays
  plain PvPoke there), the 1-1/1-2 row's "lead of 40+ percentage points"
  (constant is inert), the hero's "certified never worse ... in any of the
  nine shield scenarios ... on both win rate and average battle rating"
  (UL 0v1 is -2 win cells, the accepted Dondozo exception), the Methods
  "no negative cell shipped", and the UL "honest flags" paragraph's 2-1
  headroom framing. Per the 2026-08-31 rule (no staleness markers; a
  no-regen article is REMOVED), the live page should either be re-rendered
  after Michael's prose pass or taken down until then. Re-render also
  refreshes every tensor-derived number from the rebaked dives.

  SECOND FINDING, same day, browser-verified: pvpoke.com runs a sandbox
  link's battle TWICE (runSandboxSim, then startBattle's setTimeout) and
  `Pokemon.reset()` never clears `hasActed`, so the Pokemon that acted on
  run 1's KO turn loses its turn-1 action in run 2 and every scripted
  action on the old parity is dropped. Our verify_url gate ran the engine
  ONCE, so it passed links the site renders differently (Azumarill 690
  -> site 547; Blastoise 624 -> 515; the 09-10 Lapras "fixed" link 662 ->
  site 446, a loss). verify_url now emulates the page (two runs) by
  default (`page=False` = engine-level); the Lapras test pins BOTH
  numbers so a PvPoke fix is noticed; upstream draft = Report 9 in
  docs/pvpoke_bug_reports.md (NOT filed; likely also explains Report 3's
  unresolved 429-vs-510). Showcases were re-picked from the cells that
  survive the faithful gate (scan_candidates_faithful.py in the audit
  dir): GL Toxapex 0-0, GL Feraligatr 1-1, UL Shadow Feraligatr 2-2, UL
  Talonflame 1-2 -- all PROPOSED, Michael to confirm. All eight links were
  opened on pvpoke.com in Chrome on 2026-09-12 and show the advertised
  numbers (630/478, 630/492, 598/477, 573/297).

  Three more things the adversarial pass (5 agents + critic) turned up:

  * HOT -- the rebake running in the MAIN tree re-rendered the article at
    10:23 on 2026-09-12 from main's renderer, i.e. WITH the stale hardcoded
    block. `publish_website.sh` after this bake would republish the broken
    links. Land `cramorant-reinvestigate` (or at least its renderer +
    driver commits) and re-render the article before any publish that
    includes it; or exclude the article from the publish.
  * The article's NUMBERS were rendered under `mechanics='legacy'`: its
    surviving values (494/674, 427/541, 297/573) are today's legacy-clock
    values byte-for-byte, and none of showcase 1's or 3's moves changed
    in the rebalance. The default flipped to 'new' on 2026-09-09 (7e6a82b),
    13 days after the block was hardcoded. So EVERY number on the page
    (ledger tables, deltas, correlations, staircases) is a legacy-clock
    number; the re-render from the rebaked (new-clock) dive pages fixes
    all of them at once. The links, by contrast, broke because of PvPoke's
    post-charge cooldown (on master since the 2026-09-08 Twilight Trails
    merge acb3ce461, 500 ms), and Jellicent because of Shadow Ball 100->90
    (same merge).
  * ENCODER RULE CORRECTED (scripts/pvpoke_sandbox.py, timeline_to_actions):
    the 2026-09-10 fix shifted by the COUNT of prior charged actions, but
    Battle.js:540 applies ONE 500 ms cooldown per ROUND with any charged
    move, so a same-turn pair (CMP double throw) over-shifted everything
    after it by +1 -- 17/17 such cells mis-encoded (Cramorant vs Swampert
    UL 0-0: sim 703, link 815). Now shifts by DISTINCT prior resolved
    turns; pinned by test_same_turn_charged_pair_shifts_one_turn_not_two.
    None of the four showcases had a same-turn pair, so no published link
    was wrong because of this.
  * CERTIFICATION TOOL WAS BROKEN IN GL: `cramorant_policy_lab.load_pool(
    'great')` raised AttributeError on the two Thievul `charged=` rows
    added 2026-09-10 (the parser returns a list; the lab split it as a
    string). Fixed + tests/test_cramorant_policy_lab_pool.py. Note for the
    reinvestigation: the 2026-09-10 re-verify covered ONE moveset
    (Peck/Dive+Fly) and ONE IV spread (PvPoke default) against a GL pool
    that has since changed (rank cut 50->60, megas admitted, Thievul split),
    while the article claims certification over all five movesets x 4096
    spreads. Re-certifying at the article's own resolution is the first
    task of the reinvestigation once the rebake frees the cores.
  * Other stale surfaces found: ~/coding/reports/pogo-reports.html's
    Cramorant card and gopvpsim-cramorant-pogodives-vs-pvpoke-2026-08-25.html
    still claim "certified, no negative cells" (UL 0v1 Dondozo says
    otherwise); the article's meta.toml description says "All numbers
    recomputed from the dive tensors at render time" (true only once the
    branch lands). Dive pages carry no sandbox links and no prose claims,
    so they self-heal on rebake.
- REBALANCE re-verify: **RUN 2026-09-10; failed, then FIXED (option A).**
  (2,1) is exempt again -- every firing setting was negative, and exempting
  is strictly better than the v4 rule (same total wins, better mean).
  ONE ACCEPTED EXCEPTION remains: UL 0v1 is -2 win cells (both Dondozo) with
  +8.3 mean, kept because the -2 is exactly offset by +2 in GL.

  CORRECTED 2026-09-10: this is PRE-EXISTING, not a rebalance regression, and
  an earlier note here wrongly blamed the turn ordering. Measured: the cell is
  byte-identical under legacy and new mechanics; neither side's kit changed in
  any sim-relevant field (Cramorant's only Gulp Missile diff is an `unlisted`
  display flag); and the whole slice is the SAME -2 against the June 2026 pool
  that predates the August campaign. The strat simply turns a 515 win into a
  500/500 tie vs Dondozo -- a standing cost of dive-early into a bulky
  opponent. NOT a re-fit input. Original failure notes:
- REBALANCE re-verify: **RUN 2026-09-10, and it FAILED the bar.** Still
  net-positive overall (+76 win-cells vs baseline) but UL 2v1 is NEGATIVE
  (-1.325 mean, all of it Jellicent) and UL 0v1 loses two win cells (both
  Dondozo). Separately the LEAD constant is now inert -- lead 30/35/40/45 and
  a static control differ in 12 of 2,394 cells, so the fitted 40 in the
  shipped sheet buys nothing. Sheet v5's certification does NOT carry over;
  do not re-publish on the old bar. Full writeup + the caveat that I did not
  reproduce their exact margin metric:
  `docs/validations/2026-09-10_cramorant_strat_reverify.md`. Original note:
- REBALANCE re-verify (Michael 2026-08-25): a big move rebalance is
  expected ~2 weeks post-Worlds. When it lands: gamemaster-delta
  migration as usual, PLUS re-run the policy-lab verification corpus
  (~10 min) -- the strat's fitted constants were tuned on
  pre-rebalance move data, and the EDGE constants (0.022 DPT, 1v0
  aggr 2.0, 2v1 dpt_max 0.0155, 55-energy one-opponent patch)
  re-verify at FULL resolution with a worst-slice margin target of
  +0.5 (disclosures: docs/validations/cramorant_strict_bar_2026_08_26
  .md). This is also the standing argument for mechanism-not-names
  round-6 discriminators (they re-derive from new numbers at battle
  time).
- OPEN VALUE (next campaign): UL Dive+Surf 2v2 under the OLD tank was
  +15-21k flips at passing rating; a per-build tank discriminator
  would recover it (sheet v5 ships zero there).
- Upstream bug-report candidates (pvpoke): the two `move.moveID`
  typos (ActionLogic.js:368, :1239 -- the latter makes opponents
  never shield a lethal Dive, plausibly inflating published Cramorant
  scores; H4 in docs/cramorant_policy_plan.md measures it). Draft
  after checking whether the campaign produced the H4 numbers;
  follows docs/pvpoke_bug_reports.md conventions.
- Hard-counters lists: RE-DERIVE from the sheet-v5 rebaked tensors
  before any public surface carries one. Both earlier rosters (the
  static-tank "five losers" and the lead40-derived set) predate the
  shipped sheet.
- Strategy article PAIR (Michael 2026-08-25, queued): (1) playing
  Cramorant and (2) playing AGAINST Cramorant -- the shipped
  cramorant-pogodives-strategy article covers the PoGoDives strat
  itself, not this pair. Evidence base = the lab campaign: dive-early
  numbers (the 1.5-vs-3.0 gate, the Kingdra exception), the prey-tank
  rule + "tank unless clearly ahead", the shield-economy structure
  (better with shields on the board, the shield-ahead tax), the
  missile HP-breakpoint family (floor(15%*maxHP)+1 steps); vs-side:
  energy stacking, don't-shield-weak-hits, the re-derived
  hard-counters set (bullet above), and the carefully-caveated
  withhold finding (our crude withhold counter-policy BACKFIRED --
  baseline Cramorant won MORE vs withholding opponents, +628 vs +233
  W-L -- don't oversell). TONE: warm toward PvPoke on public surfaces
  (feedback-pvpoke-tone). SHIP-MODE POLICY applies: narrative TOML
  blocks are Michael's prose or honest auto-gen; Claude supplies
  verified bullets + data sections only. Vehicle: articles/*.toml +
  render_article.py.

ACCEPTED TEST DEBT (per policy, recorded): (a) the dive-ASAP gate's
fresh-vs-frozen `move.damage` divergence (documented at the rule in
battle.py) has no discriminating test -- needs a post-missile-debuff
re-dive scenario where the two damage bases differ; write it if such an
oracle cell ever drifts. (b) The opponent-pool question -- whether
Cramorant (GL rank 13) enters `gl_top50_plus_cs.txt` / `ul_top60.txt`
as an OPPONENT for other species' dives -- is a Michael curation call;
until then no shipped dive sims against it.

## Worlds 2026 -- surfaces FROZEN through Aug 30; post-Worlds checklist

Worlds is Aug 28-30. The full arc (sessions 1-5, the 08-14 publish,
the Thievul moveset fork, the robustness/mirror deep pages, Greninja +
Annihilape, verify_worlds green at 555 pair pages / 0 deferred) is
recorded in CHANGELOG 2026-08-10..27 and docs/TODO_archive.md; plan of
record: docs/worlds_prep_plan.md.

STANDING RULES while the surface lives: publish only with Michael's
explicit per-instance go; long bakes detached + run-to-completion;
legacy engine only, both bait modes, never the sweep cache, no
`*_great.toml`; before ANY Worlds render, re-pin the gamemaster:
`git -C ../pvpoke show f60a41199:src/data/gamemaster.json >
~/Documents/gopvpsim_cache/gamemaster.json` (the cache currently holds
the LIVE blob, restored + hash-verified 2026-08-27; while a pin is up:
no Cramorant sims, and ~63 Cramorant-family test failures are expected
pin artifacts).

POST-WORLDS checklist (after 08-30):

- DECIDED (Michael, 2026-08-31): the Worlds surfaces **RETIRE at the
  Twilight Trails site update** -- "I don't think anyone will ever look
  at it post-Worlds." Publish-path unblocking is DONE ahead of that:
  `verify_worlds.py` is out of the `run_ship_gates.py` roster (it
  failed from main on all six stamps, and because the roster is shared
  by all four entry points it blocked EVERY publish path, not just a
  Worlds one), and the `publish_website.sh` Worlds re-render is now
  opt-in behind `WORLDS_RERENDER=1`. The 593 pages stay published
  exactly as shipped until the retire lands; `scripts/verify_worlds.py`
  is unchanged, so a rebake can still run it by hand.
  Correction to the old note here: the pinned worktree did NOT green
  the gate either -- the gamemaster stamp reads the machine-level
  cache, which holds the live blob. There was no clean publish path
  from any tree.
  NB the next publish must carry a full dive-page re-render -- the
  publish gate sentinel `userdata/.cards_rerender_pending` is SET as of
  2026-08-31 and blocks it until then. Two render-only fixes are
  waiting: (a) dead tooltips on the shipped pages' best-buddy L51 half
  (hydration bug fixed 061d93c); (b) the cup dive banner's false "this
  dive is kept as a dated archive" claim, removed from deep_dive.py
  2026-08-31 -- the 5 shipped *-equinox-cup pages still render it.
  Neither touched file is engine-hashed, so there is no sim cost.
  BEFORE re-rendering, settle the vintage question: the render path
  reads LIVE gamemaster/rankings while scores come frozen from the
  blob, so re-rendering a page that advertises "snapshot as of
  2026-08-26" against today's gamemaster mixes vintages.
- Worktree `gopvpsim-worlds`: REMOVED 2026-08-31. Its only working-tree
  delta was `scripts/worlds_meta.py`, verified byte-identical to
  `main` before removal (the Greninja/Annihilape editorial was already
  committed); the three symlinks were unlinked individually first so
  nothing could follow them into the main repo.
- Retire together: `thresholds/thievul.toml` [Thievul.cd_prep], the
  worlds/meta.toml `injected_move_ids` declarations + their on-page
  disclosures (build_worlds_pages.py:569-660), and the 4 injection
  guards in tests/test_worlds_bake_guards.py (3 currently
  auto-skipping under the live gamemaster, as designed).
- Aegislash rebake decision: the Cramorant port changes
  aegislash_shield modeling (161 measured cell flips vs Shadow
  Sableye; cold rebake = 57h). LEGALITY INPUT (verified 2026-08-27,
  Play! handbook second-Tuesday rule): Cramorant debuted 08-18 ->
  eligible 09-01 -> NOT Worlds-legal, so the question is purely
  Aegislash sim fidelity; if the surface retires after 08-30 the
  rebake case is weak. (Thievul's Icy Wind: eligible 08-25 -> legal;
  meta.toml's conclusion stands.)
- cmp_atk 1-ULP shadow-tie fix (deferred past Worlds; Michael
  2026-08-10): carry pre-shadow atk on BattlePokemon; own hash bump +
  a test recording the pre-fix values + a no-shadow-either-side
  migration predicate -- do NOT fold into a neutral batch. Pinned by
  tests/test_worlds_tier0.py::test_cmp_shadow_roundtrip_artifact_is_real.

DECISIONS / EDITORIAL for Michael:

- Corviknight vs Shadow Quagsire per-spread scatter for
  r/TheSilphArena (the surviving lead after the skipped Discord
  post). OPEN QUESTION before drafting: which scenario? (memory says
  the 2-2 scatter; the original reminder pointed at 0-shield;
  re-verified data shows real structure in both 0-0, win_frac_all
  0.809, and 2-2, 0.86, while 1-1 is near-hopeless at 0.004.)
  Editorial findings, durable copy:
  ~/coding/reports/gopvpsim-worlds-2026-refresh-2026-08-27.html
  (core-breaker top-5: Medicham, Azumarill, Guzzlord, Aegislash-S,
  Mantine -- Mantine out-breaks Greninja 2:1 IV-robustly; Greninja
  27/35, its case is the energy-lead snowball; Annihilape 9th, #1 on
  the strict tier; HSH Greninja verification: 5/6 breaks confirmed,
  Tinkaton refuted).
- Deferred mirror bakes (Michael-approved deferral):
  empoleon__vs__empoleon and feraligatr__vs__feraligatr.
- Deferred joint-IV review minors (all in the 319c8a2 commit
  message): duplicate-grid double embedding (~826KB/page),
  pareto-axis self-inclusion, one-option basis dropdown, wall-table
  25-vs-12 wording, CSV dropped-row accounting, raw key fragments in
  the answers dump, sim-count phrasing.

Non-gating polish (open): (a) a11y -- badge text 4.36:1 in
pokemon-dark; hub matrix mini-grids are color-only (cheat sheets are
the text alternative); (b) optional session-6 survival strip (scoped
2026-08-11: tied to the reach table's LIVE plan only, one row per
attainable incoming fast tier, fast-pressure-only arithmetic
labeled, own adversarial round before ship); (c) optional
pooled-usage display (usage_recent_pooled_pct in meta.toml, unshown).
Planning artifacts preserved in userdata/worlds_planning/.

## Condensed-meta funnel bundle (queued 2026-08-19, Michael)

Bundle the whole Worlds chain for reuse on future condensed metas
(limited cups with ~20 real picks): meta table -> Tier-0/1 planes ->
amber screen -> Tier-2 grids -> hub/matrix/cheat sheets -> joint-IV
deep pages. The chain is now proven end-to-end (the 08-19..27 runs).
Inventory: `worlds_bake/planes/tier0/tier2/
render_data/build_worlds_pages/verify_worlds` are already meta.toml-
driven; the Worlds-hardcoded parts are `worlds_meta.py` (entry list +
badges are literals; needs a cup-roster config + a usage source that
isn't the Worlds Dracoviz corpus), the `worlds/` output paths + page
copy, and the `worlds_`-prefixed naming. `joint_iv_from_worlds.py` +
`worlds_shortlist.py` bridge to the deep-page kit and generalize with
the same meta-config handle. PvPoke publishes per-cup rankings
(topn_cup_filter_plan.md), so cup default movesets have a source.
Standing publish/bake/pin constraints: see the Worlds section above.

## Article regen triage (Twilight Trails, post-2026-09-08)

Michael, 2026-08-31: once the full move-update data is live, **every
article gets a per-article regen / no-regen decision** -- we do not
blanket-regenerate. The gate is meta relevance in **open + cups**: an
article about a species that is far out of the meta on both does not
earn a regen, however stale its numbers.

The surface (62 rendered dirs under `userdata/website/articles/`):

- **61 `*-ml-iv-guide`** dirs, driven by `opponent_pools/master_top60.txt`
  (`run_iv_guides.py`). ML is where Lugia's new Earth Power lands, so
  this is not a low-churn surface.
- **`cramorant-pogodives-strategy`** -- couples to the fitted-constant
  re-verification already in `docs/rebalance_checklist.md` section A
  step 3; don't regen it before that passes.
- **`articles/oinkologne-cd-2026-05.toml`** -- still all PLACEHOLDER
  bodies, so nothing is shipped and nothing is wrong today. Worth
  knowing before anyone picks it up: its comparison axis is Mud Slap
  vs Tackle/Take Down, and **Take Down goes 5->14 power with increased
  energy gain**, which can invert the article's thesis. Decide
  regen-vs-drop on the meta test above before spending an authoring
  session on it.

DECIDED (Michael, 2026-08-31) -- **no staleness markers; the live site
is centered on current live stuff.** A no-regen article is REMOVED from
the site rather than left up with a caveat. This satisfies the
never-ship-unflagged-known-wrong rule by not shipping the wrong page at
all, which is stronger than flagging it.

TOOLING READY (built 2026-08-31, ahead of the rebalance):
`scripts/archive_article.py --slug <slug> --vintage YYYY-MM-DD [--stamp
<hash>]` copies a live article to a dated snapshot slug and marks the
copy; the index renders snapshots in a collapsed Archive block. Design
+ rationale: `docs/article_archive_plan.md`. `--vintage` is deliberately
REQUIRED -- archiving happens after the new data lands, so the live
gamemaster stamp at that moment is the NEW one and defaulting to it
would mislabel the snapshot.

Mechanism if you instead DELETE outright: remove the rendered dir from
`userdata/website/articles/`, then re-run `build_website_index.py`.
The index discovers articles by scanning
`userdata/website/articles/*/meta.toml`
(`build_website_index.py:49,1007`), so the card disappears on its own,
and `publish_website.sh` rsyncs with `--delete` (:105), so the live
page goes with it. No hand-editing of index.html.

If a removed article is worth keeping, it archives in the **git repo**,
not on the site. Wrinkle to solve when it first comes up: `userdata/`
is gitignored (`.gitignore:43`), so archiving a *rendered* page needs a
tracked path -- the cheap alternative is to keep only the source
(`articles/*.toml` is already tracked) and re-render from it if ever
wanted.

Still open, Michael's: what counts as "in the meta" for the cups half,
given the season ships eight of them (Willpower, Retro, Mega Color,
Little, Fantasy, Halloween, GO LAIC, Mega Catch).

## Site lifecycle policy (Michael, 2026-09-02)

Standing shape, seasons repeat:

1. A new season is announced.
2. Things get added to the site progressively through the season
   (cups, event/CD articles, condensed-meta surfaces).
3. **At the start of the next season, ALL of it comes down**, and the
   new season's surfaces get added as needed. Rinse, repeat.

The live site is centered on current live content; nothing is left up
carrying a staleness caveat (see "Article regen triage"). Retired
surfaces are re-renderable from their replay blobs, and articles worth
keeping archive as dated snapshots via
`scripts/archive_article.py` (docs/article_archive_plan.md).

**What a season-start bake actually covers.** The chain
(`overnight_redive.sh`) already does more than "GL/UL/ML dives":

- `run_website_dives.py` -- 100 dive entries (GL + UL + ML)
- `run_iv_guides.py` over `master_top60` -- 61 ML IV guides, a separate
  multi-hour job and ~60% of the article surface
- 4 comparison renders + the GL matchup web (need sims)
- Reader's guides, index rebuild, ship gates (render-only)

Opponent-pool freshness is a code-level guard since e8ac919 (2026-09-02):
`run_website_dives.py` hard-fails on stale pools (`--allow-stale-pools`
overrides). Record: CHANGELOG 2026-09-02.

## NEXT BAKE: mirror population as opponent columns (Michael, 2026-09-22)

**Clones cleaned up 2026-09-22:** the seeded-lattice and mirror-proto
prototypes now live as branches `experiment/seeded-lattice-2026-09-17` and
`experiment/mirror-proto-2026-09-21` in this repo (local only); the three
clone directories are deleted.

**Status 2026-09-22 (Michael): WAIT.** Not worth its own bake; it rides the
next bake that happens for another reason. PRE-LAUNCH PREREQUISITE for that
bake: build the population sweep + the block that reads it FIRST (one agent
round, ~half a day, additive columns, no hash bump), so the bake carries it
for free. The gamemaster_subset narrowing (sim-read fields only, prevents
UI-only PvPoke churn from cooling the cache) also rides that bake ONLY IF it
is cold for its own reasons; never force a cold bake for it.

Decision: "the mirrors I will meet" = (1) PvPoke's rank-ordered IV list for
the focal, top N (bulk-first by construction), PLUS (2) the page's own
builds -- each named build's most-winning member and SP1 (what our readers
will build once the page exists). Labelled separately on the page. The
Nash mirror-slayer cohort is NOT this (prototype 2026-09-21,
`userdata/analysis/2026-09-21_mirror_proto/report.md`: attack-first on
Melmetal GL, bimodal on Shadow Sableye, never converged); it stays as the
Slayer Builds input. The render-only CMP line against that cohort ships
first (branch `mirror-line`) and is replaced by these numbers when the
bake lands.

Michael, 2026-09-22 (after the four previews on branch `mirror-line`,
d66a78d): the cohort version is NOT rendered site-wide. Its content
reduces to "pick the highest attack you have inside the build you chose"
plus what that attack buys (Melmetal GL and Azumarill: nothing; Melmetal
UL: the fork clears both cuts with every member). DONE on `mirror-line`:
the block is two sentences under the builds table, and everything behind
it is kept and still pinned for the population version to reuse --
mirror_surface, the decision cells / cohort-rate / Spearman facts (now
computed and NOT rendered), the trace, the glossary terms. The population
version earns the block because it compares ACROSS builds ("Build 3 wins
the 1v1 mirror against 40% of common Melmetals; Build 2 against 85% and
gives up these four matchups").

Shape (bake-side, changes the blob schema -- own bake, own hash bump):
- After the main sweeps and BEFORE render, compute builds
  (`deep_dive_builds.compute_builds`, ~2 s) so (2) is known; then sweep the
  focal grid against the mirror population as extra opponent columns: same
  species+form as the focal (and the other shadow form when it is in the
  pool), explicit IVs, level = under-cap max, default moveset; sweep cache
  keys columns on opponent IVs already (`sweep_cache.column_key_fields`),
  so they warm like any other column.
- Store under `state['mirror_population']`: the member list (source tag:
  'pvpoke_rank' / 'build:<role>' / 'sp1', IVs, stats), and per-member
  per-scenario scores (4096 x 9 x M), both bait modes; opponent-IV modes do
  not apply (the IVs are the point).
- Size cap: N = 20 from the rank list + up to ~6 build members => ~26
  columns x 2 bait sweeps x movesets. Measured 2026-09-20: ~0.7 s per
  column-sweep, so ~3 min per 5-moveset dive, ~6 h across the corpus,
  warm afterwards.
- Page: the "The mirror" block (from `mirror-line`) reads this instead of
  the cohort: per scenario, the share of the population each build's
  members beat (median, min); the CMP quantiles (a_50 / a_75, strict
  engine rule) from the population's attack; "Build 2 beats 83% of common
  Melmetal builds in the 1v1 and wins CMP against 71%". Optional: a
  thresholds-TOML override list for species where Michael knows what the
  community runs (candidate 3, deferred).
- Guards: the population must include SP1 and the rank list's #1; a test
  that the per-scenario mirror-vs-population numbers reproduce from the
  stored scores; the vintage stamp covers it.

## BUILD BRIEF (2026-09-12): decisions taken, what is next, Cramorant hand-off

Status: `scripts/deep_dive_brief.py` + tests merged to main (b6e6263), standalone
only (HTML + JSON + sweep under `userdata/analysis/2026-09-12_build_brief/`).
Report: `~/coding/reports/gopvpsim-build-brief-2026-09-12.html`. Design of
record: `docs/expert_verdict_plan.md`.

Michael's answers, 2026-09-12 evening:

1. **Bulk floors (Def / HP lines) = v3, standalone, before integration.** Same
   three primitives (exact / one-sided gate / near-exact) on Def and HP with
   bulkpoint mechanism labels. Altaria (Def >= 148.29 vs 2v2 Clodsire) and
   Furret (Def >= 102.06 vs 1v1 Lapras) are the acceptance cases.
2. **Placement (D11): split by outcome.** Above the scatter as the first IV
   Recommendations block when a line (or a cost-demoted line) exists; inside
   the collapsed Dive Analysis block on pure negatives.
3. **Flavor guide (D10): retire BOTH** the `[Recommended]` badge and the
   "almost any will do" catch phrase when the brief ships, as separate commits.
4. **Sequencing: Cramorant first.** Page integration of the brief WAITS until
   the Cramorant strategy reinvestigation lands. v3 (standalone) may proceed.

Naming + spread visibility (Michael, 2026-09-13): the section is called
**"Which one to build?"** (not "build brief"; "verdict" and "recommended"
stay reserved). Collapsed by default; the summary line is the question plus
the headline's first sentence. Integration must make the line VISIBLE AS
SPREADS: (1) example spreads in the first sentence ("... 148.10 attack, which
6/9/7 at L50, 10/13/11 at L45.5 and 2218 other spreads reach"); (2) hover/tap
on the number lists the top spreads by stat product with a "show all N"
expander (reuse the flavor guide's Member IVs pattern); (3) a small in-section
plot (SP rank vs wins; at-or-above-the-line filled, bulk alternative in its
own color, rest muted; hover = IVs/level/stats/side of the line), drawn
client-side like the cluster panels; plus the main scatter's color mode.

Shield scenarios in "Which one to build?" (Michael, 2026-09-13): accepted
as a middle point that the section is inert to the main plot's Shields
dropdown (every fact in it is scenario-tagged and the floor is chosen across
all nine; the y-axis is wins of 684). Follow-ups, in order: (1) a "scenario"
control on the section's OWN selector (filter rungs to one scenario, y-axis
= that scenario's wins, summary reworded), never coupled to the main plot's
dropdowns; (2) the real synthesis: a usage prior over shield states (lead /
safe swap / closer) so floor selection can weight cells and the headline can
say "in the shield states Sableye usually sees". (2) needs an expert-supplied
or usage-derived prior; the sim does not have one.

SPREAD-SETS ANALYSIS DONE (2026-09-15; report
`~/coding/reports/gopvpsim-spread-sets-2026-09-15.html`, artifacts + 112
per-blob fact files with explicit member lists under
`userdata/analysis/2026-09-15_spread_sets/`, ~246 MB, gitignored, not to
keep forever). Michael's framing: SETS of spreads are the primitive (users
check their mons against a set on the plot; gobattlekit gets explicit IV
lists); descriptions are labels. Findings on the deduplicated corpus (108
dives / 448 arms / 7944 named sets, pvpoke mode, L50):
- Two-/three-stat structure beyond every single-stat threshold (atk, def,
  hp AND stat product): 88% of arms have at least one such top-50 cell, but
  the MAGNITUDE is small: 3.8% of decision cells, 1.8% after a materiality
  bar (best single-stat rule wins the cell <= 95%). With only the four
  brief-specified generators (no S5 boxes): 32% of arms.
- Plain Sableye: the 863-spread 0v1 cluster wins Annihilape AND
  Aegislash-Shield for every member; "atk >= 123.4 and HP >= 118" does NOT
  (55%); the exact description is atk-floor + a Def-vs-HP staircase; the
  genre's linear form "atk >= 123.4 and Def + 1.15*HP >= 255.88" fits at
  J=0.98. Shadow Sableye's strongest cluster IS the floor set (2220).
- Description shapes: 11% single threshold, 36% two-stat box, 15%
  atk-floor + staircase, 36% list-only (at 95% fidelity 830 of those
  rescued). The linear Def + k*HP family fits exactly 82 sets, 4% of the
  hard sets at 99%, 14% at 95%: the list stays the primitive.
- Frontier slope (corpus): median 0.54 Def per HP (q 0.36-0.80); the "1 HP
  for 2 Def" ratio was Michael's paraphrase, not a RyanSwag quote; the
  SHAPE is the genre's, the ratio is species-specific.
- Score-only structure ("do better or worse"), ten dives: 12 of 486
  (set, cell) pairs have non-overlapping p5-p95 score bands with no result
  flip; strict separation never occurs.
- gobattlekit: no schema change; `ivs = [[a,d,s],...]` already exists;
  floors express lower bounds only, so 59% of sets need the explicit list;
  the list is lossless only under the L50 cap; MAX_TARGETS=4 and file size
  are the real constraints.
OPEN: (1) the per-arm set-keeping cut (18 per arm) still uses the old
interest score; adopt the material-cells ranking in spread_sets.py and
re-run the corpus (~2.5 h, nice'd); (2) extend the score column to the
corpus; (3) product: plot the named sets as color groups in "Which one to
build?" with the collection overlay (the sets JSON is the input), and an
export of explicit lists to gobattlekit behind the four-target cap.

BUILDS LATTICE DONE (2026-09-16; report
`~/coding/reports/gopvpsim-builds-lattice-2026-09-16.html`, artifacts under
`userdata/analysis/2026-09-16_builds/`, 17 MB, re-runnable from the blobs in
~5 min via builds_lattice.py; verify_builds.py re-derives 12 arms from the
blobs with zero mismatches). "Builds, not lines": per (dive, moveset) the
lattice of intersections (<= 4) of the top-8 named sets from the
2026-09-15 spread-sets analysis; 2-3 builds per moveset = the region
guaranteeing the most decision cells (primary), a FORK (disjoint region
whose guaranteed cells differ, Jaccard < 0.8), and the rank-1 region
(constructed as a (Def, HP) box when no lattice region holds rank-1).
Corpus (108 dives / 448 arms / 993 builds): best region beats best single
set by a median 6 guaranteed decision cells (88% of arms gain; 26% gain
>= 10); 79% of arms name a fork; the fork is the textbook "bulk side
holding rank-1" on only 20% of fork arms (26% both sides carry an attack
floor); the two objectives (region guaranteeing the most cells vs the
single most-winning spread) pick different builds on 41% of arms, by a
median 4 matchups vs 4.5 cells; 54% of builds are rule-quotable (30%
two-stat box, 23% attack floor + printed Def-vs-HP staircase, 18%
three-stat box), 23% list-only. Honesty: 23% of guaranteed (build, cell)
pairs are cells the rest of the grid wins > 90% anyway; the median build
guarantees ZERO cells that are both material and survive all opponent
IV/bait modes -- one of those two bars must loosen before a headline.
A shield-scenario prior (an explicit flat-defaulted knob) re-weights
objective A directly: even-shields changes the leading build on 16% of
multi-build arms, 1v1-only on 24% (partly size tie-breaks among tiny
counts). Sableye shadow: primary atk >= 150.24 + Def >= d(HP) (61
spreads, 55 cells) vs fork def >= 101.4 & HP >= 125 (114, 41 cells,
holds rank-1); the grid's most-winning spread 7/2/14 is in neither.
OPEN: (1) the lattice searches only the 18 named sets per arm (a
hand-built (Def, HP) box out-guarantees every lattice region on 45 arms:
the generators are the binding constraint); (2) decide the material /
all-modes bars for headlines; (3) objective B under the prior needs the
per-scenario win cube; (4) product: this is the v4 input for "Which one
to build?" (builds as color groups + UpSet panel + explicit lists +
collection overlay + gobattlekit targets).

"WHICH ONE TO BUILD?" v4 + BUILD CRITERIA KNOB (Michael, 2026-09-16; in
progress on branch wotb-v4 in the clone): the section shows 2-3 BUILDS
(primary / fork / rank-1 region from the intersection lattice), not one
line. A "Build criteria" dropdown in the scatter controls strip with THREE
presets and no free weights: "All shields, equal" (default), "Even shields
(0v0, 1v1, 2v2)", "1v1 only (open GBL lead)". The knob drives exactly three
surfaces and the page says so: the section (ranking, selection, summary,
headline, plot, UpSet), the Matchup clusters "all scenarios" partition
(one precomputed per preset), and a NEW Shields entry "All (by build
criteria)" (weighted wins); the old 'avg' entry is renamed "All (equal
weight)" and never changes. All other sections stay all-nine-equal, with a
one-line caption saying so. Section text self-labels the preset
("[even shields]"). Preset persists in the URL hash. gobattlekit export
stays at the default preset. Placeholder "lead-and-closer" prior: skipped.
Gate before the rebake: Michael reviews the preview renders (Sableye pair
+ Melmetal) and says go.

RANKINGS-VINTAGE SENSITIVITY (found 2026-09-16 fixing test drift on wotb-v4,
commit 9adc094): opponent PvPoke ranks are a LIVE read at render time
(build_opp_meta_ranks -> get_rankings_for). The 2026-09-15 refresh moved
Annihilape 30 -> 31 and Charjabug 60 -> 41; with RANK_GATE = 50 the newly
eligible Charjabug cells deleted Melmetal's floor. So a rankings refresh can
change a page's verdict with no change in sim data. Tests now freeze a
rankings fixture (tests/fixtures/pvpoke_rankings_20260908.json, great+ultra
only; cups raise loudly). For the next rebake: run through the chain wrapper
/ TTL keeper so all 135 pages see ONE rankings vintage (the direct
run_website_dives.py launch on 2026-09-12 did not). Proper fix, before the
bake after this one: stamp opponent facts (ranks, default builds) into the
blob at dive time (expert_verdict_plan Phase 0 "blob stamping", deferred), so
replay re-renders cannot drift. Other test modules that read live rankings
were not audited.

Cramorant reinvestigation hand-off (for the session that picks it up):

- Work in a LOCAL CLONE on a branch (`git clone ~/coding/gopvpsim
  ~/coding/gopvpsim-cramorant`, branch `cramorant-reinvestigate`), the way
  the moveset-rules and build-brief work was done. Read blobs / policy-lab
  corpus from the main repo by absolute path; write outputs under the clone's
  own `userdata/`. Python: `/Users/mglerner/coding/gopvpsim/.venv/bin/python`
  run from the clone (direnv is not loaded there).
- The strat lives in engine-hashed code. Do NOT edit engine files in the main
  tree while a bake runs (mixed-vintage bake). Merge engine changes only after
  the current rebake is published, then decide migration (localized predicate
  vs cold re-dive) per the CLAUDE.md cache rules.
- CPU: the dive rebake launched 2026-09-12 18:02 uses all cores
  (`userdata/logs/2026-09/rebake_movesets_20260912.log`). Reading, analysis
  and small lab runs are fine; full-resolution policy-lab corpus runs should
  wait for it to finish.
- Start from the Cramorant section above, `docs/strat_development_playbook.md`,
  `docs/cramorant_policy_plan.md`, and
  `docs/validations/2026-09-10_cramorant_strat_reverify.md`.

## HIGH PRIORITY: parallelize the dive step (~13h/bake on the table)

**PLAN ONLY -- do not implement without Michael's go** (his call 2026-09-12:
"make a plan for it, but don't implement").

### Measured, on the completed 2026-09-10/12 Twilight Trails bake

`scripts/bake_timing_report.py <chain log>` over all 135 dives:

| bucket                | time      |
| --------------------- | --------- |
| parallel (sweeps)     | 28.4h     |
| serial (render tails) | **13.4h** |
| **serial share**      | **32%**   |

Totals reconcile with the step's own 150,385s = 41.8h, so the split is
trustworthy. Two hard CPU readings behind the buckets: a sweep phase showed a
20-process tree at 1626% CPU (~16.3 of 18 cores, 0% system idle); a render
tail showed the parent alone at 99-100% with no workers alive.

`run_website_dives.py:278` launches each dive with a blocking
`subprocess.run` in a loop -- strictly serial, no `--jobs`. So for ~13.4h of a
41.8h bake, 17 of 18 cores idle.

Report caveats (fix while you are in there): rows are keyed by species NAME,
so a species with both a GL and a UL dive collapses into one summed row (81
rows for 135 dives) -- totals are right, per-dive rows are not. And intervals
inherit the last marker seen, so the unclassified bucket is near-zero by
construction and is NOT evidence the markers are healthy.

### The prize

Overlapping 2-3 dives fills each other's render tails. Ceiling is the serial
share: ~13h off a 41.8h dive step, so roughly 28-30h instead of 41.8h. Not the
"~5h" an earlier estimate here claimed -- that was computed against a projected
17h dive step, and the real one ran 41.8h.

### Implementation plan

1. **Per-dive log capture (do this FIRST, it is load-bearing).** Dive stdout is
   currently inherited straight into the chain log. Concurrent dives would
   interleave into mush AND break `chain_status.py`, which parses that log's
   `[N/M] slug` banners and `Done in X.X min` markers. Give each dive its own
   file, then have the parent emit the banner lines itself.
2. **Split `--reserve-cpus` across workers.** The chain passes
   `--reserve-cpus 0` and `sweep.py:798` computes
   `min(cpu_count() - reserve, len(chunks))`, so each dive asks for all 18.
   Three concurrent dives would ask for 54. Divide the budget by the job count
   (18 cores / 3 jobs -> `--reserve-cpus 12` each), and note the render tail
   uses ONE core regardless, so the ideal is oversubscribing slightly.
3. **Add `--jobs N` to `run_website_dives.py`**, defaulting to 1 so nothing
   changes until asked for. A small process pool over the DIVES list.
4. **Verify cache safety before trusting it.** `put_column`'s sidecar write is
   atomic (tmp + `os.replace`, `sweep_cache.py:202-210`) but the tmp filename
   is FIXED (`<name>.tmp`), so two writers to the SAME column collide.
   Concurrent dives have different focals -> different columns -> safe today.
   Confirm that still holds for the mirror-slayer and signature-dedup paths,
   which are the ones that write outside the plain focal column.
5. **Do NOT touch the ML guide tail.** `run_iv_guides.py --jobs 1` is serial ON
   PURPOSE -- it is the fix for the 2026-06-27 oversubscription bug, and its
   preflight hard-fails when `jobs x per-guide workers > cores`. Also pointless
   now: the whole ML tail measured **3.9 min** for 60 guides on 2026-09-12
   (48 profiles x 60 opponents at `DEFAULT_IV_FLOOR = 12`, vs 4096 IVs x 76
   opponents x 9 scenarios for a GL dive). See the ml_tail note below.
6. **Memory is not a constraint:** 0.8 GB per dive process, 64 GB machine.

### Measurement pitfall

Counting workers by grepping `deep_dive.py` in `ps` output MISSES the forked
pool children and reports `procs=1 cpu%=0` during sweeps -- i.e. it makes a
saturated machine look idle. Count the process tree by ppid. (This produced a
wrong reading on 2026-09-10 that had to be retracted.)

## Re-dive runbook

**Twilight Trails (2026-09-08) one-shot gate:** before any
`migrate_cache.py --apply`, hardlink-snapshot the sweep cache --
`cp -al ~/.cache/gopvpsim/sweep ~/.cache/gopvpsim/sweep_pre_twilight`.
The migration unlinks the `.npz` score planes of the affected columns,
which ARE the pre-rebalance per-spread scores a before/after comparison
needs. Full rationale + the rest of the sequence:
`docs/rebalance_checklist.md` section A step 1. Baseline vintage pin
(pvpoke 46bd08a77 / stamp c431557dcc76): DEVELOPER_NOTES
"Pre-rebalance data vintage pin".

For the next cold re-dive: `docs/predive_checklist.md` is the STANDING
pre-cold-dive gate; run `overnight_redive.sh` and watch with
`scripts/chain_status.py --chain overnight`. (Last bake: **2026-08-06/08**,
the v8 entries-12+13 engine -- ALL GREEN, mixed-vintage recovery proven;
see CHANGELOG "2026-08-06/08". LID STAYS OPEN for the whole bake.)

A failed chain step that has since been diagnosed and fixed goes in
`docs/chain_resolutions.toml` (read by `verify_overnight.py` check [1/5]) --
do NOT edit `overnight_status.txt` or the chain log to force the gate green.

**Don't use `publish_website.sh` (dry run) to ask "is the site current?"** It
regenerates guides + `index.html` on every invocation, so it rewrites the files
it then compares by mtime; it always reports a ~18-path delta even when the
content is identical. Compare content instead (md5 vs the live URLs, or
`rsync --checksum`). Detail in CHANGELOG "2026-08-04".

## DRY review 2026-08-05: fully executed -- open residue only

The review (`docs/reviews/2026-08-05_dry_review.md`) is fully executed
and signed off (plotly shim accepted as-is 2026-08-08, overlay-hue
aliasing recorded as a decision in docs/palette_governance.md section
6); the record lives in CHANGELOG and the report's status header.

Standing reference: the report's "Do NOT do" section lists the
intentional duplicates and refuted claims -- check it before
re-reporting any DRY finding.

## Engine bug-hunt round 2 (2026-07-03): 16 confirmed findings need triage

`docs/reviews/2026-07-02_engine_bug_hunt_round2.md` — 1 HIGH, 7 medium,
8 low; 0 uncertain; all double-skeptic-verified. ("No shipped winner flips
in sampled cells" held for the hunt's own samples; the NB-1 bounding sweep
below later found one on a wider grid.)

**Still open:**
- **js-parity residue** (LOW): only the winsMirror branch inside the
  SHA-pinned `deep_dive_engine.js` region (~:1497-1511) still uses the
  literal "Gives up vs #1" header for a fourth metric (a mirror-cohort
  win-shortfall COUNT). Renaming costs a REGION_SHA256 re-stamp
  (`patch_dive_gives_up_column.py` + its pin test) -- fold into whatever
  next pays that re-stamp. (History: -1/-2/-4 + -5's honest-claim half
  fixed in the DRY arc; -3 fixed `8c1f98e`; -5's follow-on closed
  `c911eff`; BP-3 fixed `fa1bd1d`, and "BP-4" was a typo -- the round2
  report has no such finding.)

### Open follow-ups (non-gating; render/tooling-only ones re-render from replay)

- **[cli] breakpoints max-level default divergence:**
  `iv_breakpoints`/`iv_bulkpoints` default attacker/defender max level
  to 51.0 while `iv_rank`/`at_best_level` default to LEAGUE_MAX_LEVEL
  (50.0 in GL/UL), so `scripts/breakpoints.py`'s rank column and damage
  table can disagree on level for EVERY species. Changing the default
  moves every CLI number -- needs its own scoped decision. (Surfaced by
  the BP-3 fix `fa1bd1d`, which strictly reduced the mismatch.)
- **[render, product decision] js-parity-3 scale half:** on a
  `--species-iv-floor` dive, `spRanks` is dense 1..n over the pruned
  subset while `rankLookup` stays global 1..4096, and the JS column
  interleaves both scales. Fix = bake spRanks from
  `compute_rank_lookup` (rank table needed before the DATA block,
  alt-cap for the L51 twin, "(Shadow)" key path) -- and it changes what
  IV-floor pages display (rank 1 may not appear at all). Caveat
  documented at `deep_dive_engine.js:~1270` + `sp_rank_array`'s
  docstring.
- **[render] matchup_clusters' own SP rank**
  (`deep_dive_matchup_clusters.py:649-652`) is a FOURTH convention
  (argsort over the 2dp display arrays); it now diverges from the
  unified three post-`8c1f98e`. Fixing changes rendered cluster
  "SP #a-#b" labels.

## Top-N opponent filter + limited-cup dives (planned 2026-07-02)

From Reddit launch-post feedback (u/LeansCenter): (a) evaluate a focal vs
only the top 10/20/50 meta opponents, (b) limited-cup dives (Sunshine Cup
etc.), separate/composable. Full plan with recon evidence, phasing, and the
open decisions (UI shape, cup pilot choice, rollout vehicle):
`docs/topn_cup_filter_plan.md`. Headlines: top-N is a client-side mask over
the already-embedded SCORES_GZ grid plus a bake-time `oppMetaRank` field and
an honesty banner over the full-pool baked sections; cups are a pool+rankings
feature (PvPoke publishes cup rankings; sweep cache warm-serves overlapping
columns; ~minutes per focal, not a re-bake).

**Phases 1-2 SHIPPED** (2026-07; CHANGELOG "2026-07-03" + TODO_archive).
**Phase 3 remains**: more cups, legality-filter eval, app-side cup
toggles, mega engine -- see the plan doc.

## Cache GC: prune all namespaces + dive-script opt-in prompt

Make `scripts/gc_cache.py` able to prune **every** cache namespace, and wire a
prune option into the dive scripts wherever caches get created.

- **GC coverage.** Today only `sweep/` has vintage-aware pruning (gamemaster in
  `meta.json`); `slayer/` and `iv_envelope/` are report-only because they bake
  gamemaster+engine into opaque filename hashes with no readable vintage. Give
  those two a readable vintage (sidecar or meta file at write time) so GC can
  apply the same N-1 retention to them. (`iv_envelope/` may be retired instead
  once the ML path moves onto the sweep cache — cache-rework Phase 6.)
- **Dive-script opt-in.** Wherever a cache is created (`deep_dive.py`,
  `deep_dive_slayer.py`, the IV-envelope/ML path, sweep), add a prune option
  that **defaults to "don't prune."** When the run is a *full* dive of a whole
  league (UL / GL / ML), **ask Michael whether to prune** before/after the dive
  rather than silently keeping or silently deleting.
- Retention target stays N-1 (current gamemaster + 1 prior), matching the
  existing `gc_cache.py --keep-vintages 2` default.

## NEXT SESSION (queued 2026-06-21): gobattlekit owned-mon breakdown screen

Build the "which of my mons should I build?" breakdown in the gobattlekit iOS
app — the same feature already live on the website (the deep-dive paste-box
"Gives up vs #1" column) and as a Python CLI (`scripts/owned_breakdown.py` —
one of three sibling metrics that deliberately do NOT match each other; see
its header, corrected in `c911eff`).

- **Scope (decided):** GL + UL, the species we've already dived (zero new sims,
  smallest mobile bundle).
- **Architecture:** EXTRACT per-IV dropped-vs-rank-1 from existing dive grids
  (no re-sim) — the dive embeds the full 4096-IV score grid. gobattlekit has NO
  battle engine and must not get one (lean iOS build); it consumes pre-baked
  data + recomputes only the analytic layer on-device.
- **One remaining build step** (step 1, the bitmask exporter, shipped
  2026-06-29 `c1ea231` -- details in TODO_archive):
  2. **Toga screen** modeled on `gobattlekit/src/gobattlekit/screens/user_iv_checker.py`,
     reading the baked artifact (bundle like `default_thresholds.toml` via
     `tools/threshold_export/`); resolve owned mons through their evolution line;
     **add parity vectors** to gobattlekit `tests/test_parity_vectors.py`.
- **Full plan + findings + file:line pointers:** `docs/owned_mon_breakdown_plan.md`.
  Memory: `project_owned_mon_breakdown.md`. Convention note: web + iOS use the
  dive's opponent IVs; the Python CLI uses 15/15/15 (they differ slightly).

## Old/new mechanics user toggle (POST-SHIP)

*(2026-06-26, Michael)* Post-ship idea, flagged so it is not lost; do NOT
pre-ship or design heavily yet. If the site/app gets traction, P!P-series /
Worlds competitors may want it for prep, and **Worlds runs on the OLD battle
mechanics**. So expose a user-facing toggle between old and new mechanics on
the dive site.

Light design notes (not yet designed):
- Preference storage: cookies (never used here) vs radio buttons vs a query
  param. Look at what PvPoke does for its "Preview next season" version as
  prior art before picking.
- Cache: the cache-rework (shipped 2026-06-27, CHANGELOG) does NOT key on the
  turn model, so a `new`-mechanics dive force-disables the sweep cache today.
  Adding a real toggle means keying the cache by mechanics so old-vs-new
  results cache separately while our engine stays current — extend
  `sweep_cache`/`migrate_cache` rather than re-deriving them.

## Form-change "starts in alt form" dives + on-page descriptions (POST-PUBLISH)

*(2026-06-26, Michael)* Aegislash got fixed pre-launch (relabeled "Starts
Blade" + a top-of-page form-change note on both GL dives) because it was the
only form-change dive that read as confusing on the site. The rest is
deferred post-publish:

- **If a Morpeko dive is ever added, it must carry a form-change note at the
  top too** (Full Belly <-> Hangry toggles AURA_WHEEL Electric/Dark after
  each charged move). Same `_FORM_CHANGE_NOTES` mechanism.

## Limited-availability mons: real IV floors for ML sweeps (PARALLEL, post-ship)

*(2026-06-25, scratch_thoughts)* The ML IV-guide sweeps assume a 12/12/12 IV
floor (right for traded / grind-able species). But some mons you only get one
or two of in PoGo -- mostly mythicals (Marshadow, Hoopa, Zygarde) but NOT all
(Genesect is grind-able; Marshadow/Hoopa/Zygarde are not). Their real-world IV
floor is LOWER than 12/12/12, so the shipped ML guide can't evaluate a
legitimately owned spread (Michael's Marshadow is 11/13/11). Steps: (1)
enumerate which species are in the limited-availability category, (2) determine
each one's IRL IV floor (research-reward / quest-encounter IVs), (3) re-run the
ML sweep for any with a floor below 12/12/12. Independent of everything else --
fire as a PARALLEL task, ship whatever is done, re-ship the corrected guides
later (they finish after the UI decisions, or get rewritten during UI rework).
FLAG (never-ship-unflagged-known-wrong rule): until corrected, the limited-mon
ML guides ship with a floor that is wrong for them -- decide whether to add an
"assumes a 12/12/12 IV floor" caveat on those pages or ship unflagged.

Resolved slice (floor-10 resweeps, enumeration research, shadow-legendary
gap) recorded in TODO_archive + `docs/reviews/2026-07-03_limited_availability_iv_floors.md`.
STILL OPEN (both need Michael, both optional/low): (a) OPTIONAL belt-and-
suspenders -- evaluate Dialga/Latias/Lugia/Reshiram (Shadow) down to 6/6/6 in
their ML guides (the four Giovanni-primary legendaries whose grindability is
only medium-confidence; worst-case floor is a bounded 6/6/6); (b) re-run the
audit when Eternatus returns (Niantic announced it will).

## Pre-ship arc — residual open polish

The 2026-04/06 pre-ship arc shipped (site published 2026-06-07; see
CHANGELOG.md). The minor polish residue:

- **Favicon.** pogodives.com has never had one (the 2026-08-27 publish
  removed DreamHost's 0-byte placeholder `favicon.ico`/`favicon.gif`,
  provisioned 08-24 -- we never made a real one). To add: drop
  `favicon.ico` (or PNG + `<link rel="icon">` in the templates) into
  `userdata/website/`; it then rides every publish. Candidate art: the
  Cramorant HOME sprite / a dive-flag glyph.

- **G16 — methodology-details guide pointers (remaining half).** The
  comparison-page block shipped `95fcf74` (wrong win-rate boundary
  fixed + derived counts + guide pointer) and the Meta Coverage half
  shipped earlier (`e6d431c`). Remaining, both in
  `generate_article.py` and both currently regeneration-unverifiable
  (the male-Oinkologne article was retired in `7df5165`, so no article
  renders from HEAD): (a) `:1835-1848` Opponent-IVs/Bait recap ->
  pointer at `guides/cd-article/body.md#dropdown-control` (anchor
  confirmed present); (b) `:2461-2469` "About these tiers" --
  move-THEN-point: the no-1:1-mapping fact must first be ADDED to the
  guide's IV Recommendations section, else a bare pointer deletes
  information.

- **G1 + G2 + G7 — richer auto-gen prose template** [post-ship,
  recommended]. F1 Meta Role, F2 key-flips callout, and
  F-fast/charge-moves shipped as deterministic rollups; JRE-style
  prose ("Mud Slap takes Male Oinkologne from 0% to 76.6% vs
  Steelix — the signature upgrade") would close the register
  gap. Template change, not Claude-drafted prose, so
  ship-policy-clean. 0.5-1 session. Benefits every future dive.
  Bundles with **Row D** — bulk-vs-peers paragraph (micro-gap from
  original §3.D, never made it through F1's auto-gen template).

- **F-tier-name-cleanup** [post-ship] — simplify IV-rec tier card
  names (current: `Steelix (Shadow) Slayer -   (Wigglytuff Slayer
  -   (Wigglytuff Atk))`) to RyanSwag's name/signature convention
  per `docs/reference_deep_dives/ryanswag/STYLE_ANALYSIS.md`.
  Bundles with S5a rename work in post-S5 arc.

- **F-shadow-narrative** [post-ship] — Shadow-variant comparison
  prose block for species that have shadow forms (not applicable
  to Oinkologne ship).

- **F5** [post-ship, gated ≥3-5 shipped articles] —
  multi-article-reader cross-linking footer. Not worth building
  until cross-reference surface is large enough.

- **R3 removal candidate.** Meta Coverage "Shield asymmetry
  dominates the extremes" explanatory paragraph — currently
  hidden; re-evaluate for removal post-ship if hide reads as
  bloat.

- **Personal-collection: `scripts/suggest_builds.py`.** CLI
  helper: takes `--species`, `--league`, `--roles lead,closer`,
  path to a PokeGenie CSV export, and the shipped dive HTML.
  Parses Top IVs + Anchors + Matchup Flip tables, intersects with
  the collection, prints a ranked shortlist per role with the key
  tradeoffs (atk/HP/def, anchor flips, score Δ, XL/dust cost).
  Maybe 2-3 hours; deprioritize if scatter paste-box overlay +
  Mirror CMP columns are enough.

- **P2 single-form opponent links.** `_render_matchup_delta_section`
  (line 1954) doesn't yet link opponent cells — applies to
  non-CD articles that aren't per-form. Extend when the first
  such article actually ships.

- **P3 article-surface design question.** Dive-side envelope-tag
  retrofit shipped 2026-04-23 (`patch_dive_envelope_tags.py`);
  a category-card surface on the CD article itself (linking
  envelope-shape to a specific "Cost to XL" judgment) remains
  the original P3 question and has not been addressed.

- **Cross-form opponent expansion (parked).** Item 4 (auto-
  form-sibling expansion in `build_opponent_pool.py`) — design
  done but parked pending review of rendered Oinkologne article;
  decide pool-level vs render-level filter for hypothetical-form
  rows. See memory `project_form_change_pool_expansion_parked.md`.

## Deferred cleanup: backwards-compatibility removal pass

The S7 dead-code removal pass ran 2026-06-12 (see CHANGELOG). Still open
(deliberately NOT cut in S7):

- **parse_types lazy alias in data.py** — the 2026-08-10 relocation
  (engine-hash batch) moved `parse_types` to `moves.py`, but
  `../gobattlekit/tools/threshold_export/export_thresholds.py` imports
  it from `gopvpsim.data` by name (pinned by
  `tests/test_gobattlekit_api_pin.py`), so `data.py` keeps a lazy
  PEP-562 `__getattr__` alias. Post-Worlds: switch gobattlekit's import
  to `gopvpsim.moves`, re-pin the api-pin test, then delete the alias.
- **Gobattlekit threshold schema compatibility** in
  `gopvpsim.user_collection.check_thresholds` (and `as_legacy_dict` in
  thresholds.py) — once gobattlekit has actually migrated to use the
  shared module and we've confirmed it works, we may want to simplify
  the dict schema or unify with pogo-simulator's TOML anchor schema.
  But not before gobattlekit's migration lands. **The gobattlekit
  threshold pipeline actively consumes both as of 2026-06-12 — do not
  touch without coordinating.**
- **§I consolidations** (L11 gamemaster index, L15 unified
  invalidate_caches + effective-stats primitive, L6 league descriptor,
  D9 SweepConfig, D14 tier recompute, R11 shared scenario/color
  helpers, W8 slug parser, W10 badge renderer, T8 conftest deep_dive
  loader) — deferred from S7: D9/D14/T8 are seams the dedicated
  deep_dive.py split session will rework anyway, and the library
  consolidations (L6/L11/L15) are behavior-adjacent refactors, not
  deletions. Bundle them with the split session or their natural
  feature sessions.

## Battle simulator

* **PvPoke bug reports: FILED 2026-07-16** (CHANGELOG has the full
  writeup): pvpoke/pvpoke #378 Gyro Ball, #379 Morpeko, #380 dead
  pruning, #381 DPE overwrite, #382 bestChargedMove question. Residual
  opens:
  - **Report 5 (needsBoost retired-or-returning question) held back** —
    paste-ready in `docs/pvpoke_bug_reports.md`; if filed later, adjust
    the opener's "5 reports today" line and re-check
    `git log 10fd1a6e4..master -- src/js/` first.
  - **Engage with Matt's responses** as they come (volunteer,
    ~two-week cycles; don't re-ping).
  - **[investigation, unexplained] site-vs-headless 429/510
    discrepancy:** pvpoke.com single-battle UI gives 429 where headless
    runs of the byte-identical engine + gamemaster + inputs give 510
    (Aegislash SB-only vs Azumarill, the knife-edge "3 turns can flip"
    cells; reproduces at both April and July vintages, robust to
    bait/OMT/levels/IVs sweeps). Some UI-side battle setup input we
    haven't identified. Detail in `docs/pvpoke_bug_reports.md` header.
    Low priority, but don't cite harness battle ratings as
    site-reproducible in razor-thin cells until resolved.

* **Known PvPoke divergences** — DEVELOPER_NOTES "Known divergences"
  is the single source of truth (bestChargedMove per-turn recompute,
  the near-KO plan cluster, the battle-timeout guard). Re-audit
  anytime: `python scripts/audit_oracle_harness.py` (covers GL + UL;
  current baseline 207 cells = 172 exact + 35 documented; re-audited
  2026-08-06 A/B at origin/main vs the entry-13 batch, identical both
  sides -- the old 170+37 went stale at the hunt2 merge).

* **Speed test** -- compare our speed vs the PvPoke JS code, look for
  ways we can speed ours up. *(Partly addressed 2026-06-10: holistic
  perf review found and fixed a 2.0x engine regression dating to the
  2026-04-15 correctness arc — see DEVELOPER_NOTES "Performance
  baseline" for the regression gate and `docs/perf/` for the writeup.
  The vs-PvPoke-JS throughput comparison itself remains open.)*

## Shared user_collection module — Option-2 migration prep

*(from gobattlekit's 2026-06-11/12 deep review, sections F/J — CP9 +
CP12. Not urgent; gobattlekit is otherwise ready to consume
`gopvpsim.user_collection` and has aligned its matching semantics to
ours. The CP4 over-leveled-mon fix and CP13 Burmy→Mothim fix shipped
here 2026-06-12; these are the remaining seams.)*

* **Split heavy deps into extras** — `pyproject.toml` hard-requires
  `numpy` + `markdown`, but the `user_collection` import path
  (user_collection → evolution_lines + pokemon → data) needs neither.
  numpy on iOS via BeeWare is a real packaging problem. Move them to
  an extra (e.g. `gopvpsim[sim]`) so a mobile app can take a core
  dependency. Note the user_collection docstring's "stdlib only"
  claim is false at package level until `certifi` (imported by
  data.py at module load) is also dealt with.

* **Injectable gamemaster/CPM source** — `match_mons` hardwires
  `get_pokemon_index()` → data.py's network-backed cache
  (`~/Documents/gopvpsim_cache/`, 24h TTL, NoDataError when offline
  with no cache). gobattlekit needs to supply its own bundled +
  ETag-cached gamemaster. Add a provider injection point (parameter
  or settable loader) on match_mons / get_pokemon_index /
  evolution_lines.

* **Golden parity-vector emitter** *(seeded by the gobattlekit
  threshold-pipeline session, 2026-06-12)* — a script that emits
  (species, IVs, level) → (stats, CP, rank) fixtures from our
  canonical primitives, checked into gobattlekit as test vectors so
  its stat math can't drift from ours. Complements the CSV parity
  corpus below (that one covers parsing/matching; this covers the
  arithmetic).

* **Shared CSV parity corpus (CP12)** — a small synthetic CSV
  (shadow, over-cap, out-of-range, gendered, branched-evo rows) +
  golden expected-results JSON, checked into BOTH repos and run by
  both suites, so the row-for-row contract can't silently drift
  again (it demonstrably did: gender, shadow, level-gating). Until
  Option 2 deletes the duplicate implementation, this is the only
  tripwire.

## Tests to add

* **pvpoke.com/battle browser round-trip for the iv-tech oracles**
  (the one human step left from the old "No-bait oracle tests" entry;
  everything else DONE 2026-08-08, AFK churn `000ea87`+`cc64923`, both
  reference claims REPRODUCE with mechanisms read off battle timelines
  -- Tinkaton 0-1 vs Shadow Altaria bulkpoint at def=143.04, Spidops 1s
  vs Altaria Sky-Attack reduction -- and the "more forgiving win
  threshold" follow-up resolved: bait-ON wins for every spread are real,
  the reference's claim is specifically no-bait). Round-trip the key
  cells at pvpoke.com/battle when convenient.

## Refactoring

* **Pain points captured during real debugging** — see memory file
  `project_post_ship_cleanup_pain_points.md` (silent early-returns
  with no logging, no replay-from-saved-state mode, hardcoded magic
  numbers assuming `nS=9`, parallel call-site duplication,
  free-form-string opponent identity, `data_obj`-as-mutable-bag,
  `id()`-keyed caches). Specific friction encountered while
  diagnosing the 2026-04-25 mirror-tier-synthesis no-fire bug;
  read this *before* starting the deep_dive.py split below so the
  cuts address actual pain rather than aesthetic ones.

* **Split `scripts/deep_dive.py` — steps 1-5 DONE (2026-08-06/08, DRY
  review entry 12; `7b665ac` + follow-ons).** 8032 -> **5077** lines. The
  landed layout differs from the original plan in *naming*, not in
  substance: the anchor-flip and slayer code went to the pre-existing
  2026-04-12 modules (`deep_dive_analysis.py`, `deep_dive_rendering.py`,
  `deep_dive_slayer.py`) rather than to new `deep_dive_lib/anchor_flips
  .py` / `deep_dive_lib/slayer.py`, and three modules nobody planned
  fell out of the cut (`opponents.py`, `score_pack.py`, `shields.py`).
  Landed homes: `build_iv_categories` deep_dive_lib/categories.py:23;
  `aggregate_flips_by_anchor` deep_dive_analysis.py:363 +
  `render_anchor_flip_bullets` deep_dive_rendering.py:1358 (deep_dive.py
  keeps alias shims for the tests); `iterative_slayer_discovery`
  deep_dive_slayer.py:245 with the spawn worker `slayer_iter_worker`
  :149 pinned by `tests/test_deep_dive_lib_workers.py:155` — do NOT
  "finish" targets 2-3 by creating the originally-planned filenames,
  that would churn working test-pinned code and break spawn-mode worker
  resolution; `categorize_slayers` was superseded, not moved (see
  `src/gopvpsim/anchors.py:858`); `generate_analysis_sections`
  deep_dive_lib/render.py:504; sweep foursome deep_dive_lib/sweep.py.
  **What's actually left (open):** two functions are ~69% of the
  remaining 5077 lines — `generate_interactive_html` (:1254, ~1874:
  page assembly, the `var DATA` emit, the collection panel) and `main`
  (:3440, ~1637: arg parsing + orchestration, fine where it is). A
  step 6 would be "extract the page-assembly half into
  `deep_dive_lib/page.py`", with `build_collection_data()` (see "Tests
  to add") as its natural first, smallest slice. Not scheduled.
  **Doc gap:** DEVELOPER_NOTES has no `deep_dive_lib` entry — the only
  layout description is `deep_dive_lib/__init__.py`'s docstring; worth
  a paragraph next time that file is touched. No dedicated
  `test_render.py`/`test_sweep.py` yet.

## Moveset / variant comparison tool

* **N=3 / N=4 renderer support for `compare_loadouts.py`** — MVP
  (N=2) shipped 2026-04-18. N=4 ceiling covers the canonical
  (moveset × form) cross (e.g. Forretress: Volt Switch / Bug Bite ×
  Shadow / normal). Remaining work: N=3 and N=4 renderer support,
  plus verdict templating for N-way ranking (MVP keeps verdict
  simple, just for Male-vs-Female).

  Design constraint: stay loadout-list-keyed, not A/B-keyed
  (`loadouts: list[LoadoutSpec]`, pairwise-delta iteration via
  `itertools.combinations`). N=4 ceiling: more than 4 makes the
  matchup-delta table unreadable. Don't design past this.

## User-facing documentation (post-arc)

The Reader's Guide arc shipped 2026-04-23/24 — infrastructure
(`build_guides.py`, landing page, dev-count sentinels), plus seven
guide bodies, ALL at `authorship=both` as of 2026-07 (the old
"pending review" note here was stale). A 56-agent staleness audit ran
2026-07-07 (43 findings applied; detail in TODO_archive). An eighth
guide, **Matchup Clusters** (`guides/matchup-clusters/`), was drafted
at `authorship=ai` and promoted to `both` 2026-07-07 (`1368bce`).

Open follow-ups:

- **Review the IV Robustness guide** (`guides/iv-robustness/`,
  published 2026-08-15 at `authorship=ai` -> promote to `both`).
  General robustness methodology (planes, cohorts/probes, W/L/? grids,
  curves, reach/deny, honesty rails) with the Worlds pages as the
  worked example. Follow-up when convenient: link the guide FROM the
  Worlds hub/cheat sheets -- that means re-rendering Worlds surfaces,
  so it requires the gamemaster re-pin first (see the Worlds NOTE
  above); don't do it casually.
- **Glossary gap:** `docs/concepts.md` does not define the envelope-crosser
  vocabulary the dives print (`elevated-band-crosser` /
  `depressed-band-crosser`, `deep_dive_rendering.py:~1551`); found closing
  the Shadow Sableye GL bands reminder (CHANGELOG 2026-09-22).
- **Two stale screenshots** (low): `envelope-position/screenshots/
  envelope-example.png` (pre-rename "Top Picks" legend) and
  `iv-flavor-guide/screenshots/flavor-example.png` (pre-2026-06-25
  purple theme; zone is teal now) — retake from HEAD-rendered dives
  when convenient.
- **Round-3 screenshots** if/when reader confusion surfaces a
  specific gap (round-1 + round-2 screenshots shipped via `32fae84`
  and `e449b38`).
- **Add topics** beyond the five shipped — Michael asked that the
  topic list be a conversation at the start of the task, not a
  fixed scope. Plan a session to (a) add topics surfaced by
  an HSH Discord member / new readers, (b) reorder by current reader
  confusion, (c) decide whether related topics merge.

The IV Flavor Guide write-up is owed to an HSH Discord member per
`project_acidic_arisen_writeup_commitment.md` (NB: that memory file
lives in the retired pogo-simulator project's memory dir,
`~/.claude/projects/-Users-mglerner-coding-MGLPoGo-pogo-simulator/memory/`,
not this project's) — the guide sits at `both` today; promoting it to
`expert` is the closing of that commitment.

## Low priority

* **ML guide "what do I get by best-buddying these?" view** — the "All
  cases" IV-compare view (shipped 2026-06-28, `b494b28`) hides
  best-buddy-conditional flips by default and badges their count
  ("N best-buddy flips hidden"). A natural follow-up is a dedicated
  summary that answers, for the user's candidate spreads, *what
  matchups best-buddying unlocks/loses* — e.g. "best-buddy 15/15/14 to
  win Solgaleo 2-1 + Kyurem 2-2; 15/14/15 gains nothing." The data is
  already there (the alt grids / sibling quadrant rows); this is a
  rendering/summarization feature, not new sim. Deferred 2026-06-28 by
  Michael ("don't want to engineer that now").

* **Team/multi-mon simulation** — currently only 1v1; real PvP is 3v3 with
  switching. Add team composition and switch-timing support. When this
  lands, honor `reset_on_switch`: Morpeko must re-enter in Full Belly on
  every switch-in (confirmed in-game 2026-06-06; see DEVELOPER_NOTES §8).
  Also port the MATCH-level 240 s clock (Michael, 2026-06-11): the real
  game's timer spans the whole 3v3, charged-move animations consume it,
  and games are genuinely won on time — see DEVELOPER_NOTES "Battle
  timeout" divergence entry for PvPoke's clock semantics to mirror.

## Turn system (new mechanics) -- open residue

The 2026-09-02..10 history (the wait decision, the 09-03 re-port 104 -> 1,
the default flip, PvPoke shipping to master, the oracle / test / pool
re-baseline, the tripwire re-pin) and the 2026-09-22 legacy guard are in
CHANGELOG 2026-09-02..03 and 2026-09-09..10. Open:

- **Aegislash x Azumarill, 6 oracle cells** (`scripts/mechanics_notice.py`
  is the canonical wording: 237 of 243 cells match PvPoke master). One
  form-change interaction: `aegislash_vs_azumarill (1,1) (2,1)`,
  `aegislash_blade_vs_azumarill (1,0) (2,0)`,
  `azumarill_vs_aegislash_shield (1,1) (1,2)`. Two flip `log_ok=False`;
  `aegislash_blade_vs_azumarill (1,0)` diverges 570/429 vs 712/287, the
  widest gap on the grid. Traced 2026-09-09, timeboxed -- symptom found,
  root cause NOT: our Aegislash farms in SHIELD form for 43 turns at 1
  damage per Psycho Cut, banks the full 100 energy, then form-changes to
  Blade on T44 and throws Shadow Ball for 91; PvPoke's Aegislash is very
  likely committing earlier. Next probe: PvPoke's chargedLog side by side
  with ours. (The SHADOW_BALL 100 -> 90 hypothesis is dead, b0c4fb0.)
  Excluding Aegislash from the pools is no escape hatch: both forms come
  out of the AUTO recipe and both are dive focals.
  - When resolved: delete `scripts/mechanics_notice.py` and its call sites
    (`deep_dive.py`, `scripts/battle.py`, `deep_dive_brief.py`); its own
    docstring states that deletion condition.
- **Un-xfail candidates:** 3 documented divergences VANISHED in the
  2026-09-09 re-measure (2 aegislash_blade, 1
  corviknight_vs_moltres_galarian). Do not un-xfail them piecemeal before
  the Aegislash cluster is understood; they may be the same root cause
  moving. (The 13 strict xfails in `tests/test_battle.py` are also on the
  2026-09-25 scout's Tests list.)
- **Threshold-TOML prose (3b(c) of the 2026-09-09 re-vet):** 182
  descriptions cited a decimal number in prose; each one whose underlying
  threshold moved is now a wrong published sentence. d363b1d has since
  archived the 58 derived stat-cutoff spreads, so re-count first
  (`grep -hE '^\s*description\s*=.*[0-9]+\.[0-9]+' thresholds/*.toml`
  finds 135 single-line hits on 2026-09-25; not the same method). Where a
  value is re-derivable we can propose it, but which bulkpoint defines a
  named spread is editorial and stays Michael's; ship-mode narrative
  policy applies.
- **Worlds artifact tests are skipped, not broken** (066e528, Michael
  2026-09-10: "no need to rederive any worlds stuff, that'll come again in
  a year"): `test_worlds_meta.py::test_generator_is_idempotent`,
  `test_worlds_bake_guards.py::test_one_pair_bake_is_idempotent_and_clean`,
  `test_build_worlds_pair_pages.py::test_reach_reproduces_dragapultsim_guarantee`.
  Re-deriving would overwrite the record of what was published under the
  engine that produced it. Un-skip when the 2027 Worlds cycle starts, or
  earlier if the IV-robustness work needs them.
- **Next engine-hash bump:** `src/gopvpsim/battle.py:3424-3427` still calls
  `mechanics='new'` "EXPERIMENTAL" / "UNVALIDATED"; fix the comment only on
  a bump that is happening anyway (the file is engine-hashed).

DUP DOM IDS: measured 2026-09-10, NOT a blocker, but the de-dupe item that
the pre-dive checklist says "TODO carries" is no longer in this file, so it is
restored here.

Live-DOM state on a 5-moveset dive page (Melmetal GL, after stripping BOTH
`<script>` and `<template>` -- see the checklist's Lens 4):

    duplicated ids            240   all of the form af-<hash>
    multiplicity              2-5   (tracks the moveset count)
    duplicated anchor targets   0   of 60 -- navigation is UNAFFECTED
    referenced by href=#/JS/aria  0 -- nothing looks them up

So they are invalid HTML that nothing depends on. Emitted by
deep_dive_rendering.anchor_group_id once per moveset section. Worth cleaning
for standards-compliance, not for behaviour; do it when the renderer is next
open, and re-measure with the template-stripping trigger.

IDEA, parked 2026-09-09 (Michael: re-think after more dives land): a
"does IV choice still matter once you're bulky?" number for the dive page.
Metric is the RATIO, not the absolute spread -- what fraction of the full
4096-spread score range still shows up among the bulkiest 10%:

    Melmetal UL   full 25.8   top-10% 12.0   kept 47%
    DD GL         full 31.2   top-10% 13.9   kept 45%
    Melmetal GL   full 39.4   top-10% 12.7   kept 32%
    DD UL         full 72.3   top-10% 12.8   kept 18%

The absolute top-decile range is nearly constant (12.0-13.9 across all four)
and so carries NO information; only the denominator separates them. DD UL has
the widest total spread of the four yet the flattest top end -- almost all its
value is in being bulky at all. Melmetal UL keeps its gradient all the way up,
which is the "worth digging in before spending resources" case.

Caveat that needs resolving with more data: points-gained tells a different
story than shape. Best-vs-median inside the top decile is 4.9 for Melmetal UL
vs 7.5 for DD UL, i.e. DD UL rewards optimization MORE in raw points while
having the flatter shape. Which of the two a reader actually needs is the open
question. Computable from the replay blob alone -- no re-simming.

## Backlog (someday / maybe) — see `docs/TODO_backlog.md`

The long-tail design notes / research reproductions / UI wishlist live in
`docs/TODO_backlog.md` (split out 2026-06-28 to keep this file readable in one
shot). All still open — detail preserved verbatim there. Index of what's there:

- **Policies to add** — Selective baiting, random buff/debuff modes, EV-based
  baiting, new-mechanics decision-layer re-optimization.
- **Analysis goals** — RyanSwag-style matchup-flip annotations + wins y-axis,
  meta-wide slayer reference, SwagTips/reddit/iv-tech reproductions, the
  Tinkaton scatter-cluster + clustering-methodology investigations.
- **Slayer card UX** — signal-loss systemic audit (saturation of slayer/tier
  badges).
- **Slayer iteration cleanup** — Max-Wins column, Lurgan-as-opponent re-run,
  validation-doc reframe.
- **HTML output paths** — orphaned-artifact detector,
  mirror-slayer table size (mechanism removed; demote-vs-optimize).
- **Dive card** — High-HP strictly-dominated-spread bug, opponent-IV
  robustness axis, signature-dedup notes.
- **Upcoming plan-mode session** — dive/article content + information
  architecture (articles-vs-dives taxonomy, card placement, ML enrichment).
- **CD article generator** — S8 envelope-annotation wiring.
- **Deep-dive narrative** — (move-display DRY lifted to Refactoring above),
  catch-phrase tier, narrative-flavor plot tiers, TOML composite categories,
  RyanSwag-style autogenerated section.
- **Reproducibility** — non-reproducible opponent data (fingerprint + logging).
- **UI / Display** — scatter color modes, pretty-print names, CLI help
  enumeration, table sorting, client-side anchor add/remove.
- **Schema simplification** — TOML simplification triggers (collect friction).

---

Historical/shipped work lives in `CHANGELOG.md`; long-tail open backlog in
`docs/TODO_backlog.md`.
