# Reddit Launch Plan (cross-repo arc)

Status: PLANNING. This is a multi-session, two-repo arc (`gopvpsim` +
`gobattlekit`). It runs AFTER the website publish, in its own session(s).
Surfaced 2026-06-25 by the pre-publish completeness audit, which found the
whole Reddit deliverable had no home in the task list.

## Decisions already made
- Website brand/URL stays **pogo-dives** (`mglerner.com/pogo-dives/`).
- Repo + Python package + (eventually) local dir standardize on **gopvpsim**
  (globally unique on GitHub; package rename would be invasive). The local
  dir rename `pogo-simulator -> gopvpsim` is DEFERRED to a clean session (do
  not rename mid-flight: it breaks running sessions + gobattlekit's relative
  paths). Tracked as a discrete TODO, coordinated with gobattlekit.
- Public attribution handle is **TitanTrainers15** (not the real name).

## Deliverables
Two cross-linking, copy-paste **plain-text** Reddit posts that reference each
other:
1. **GoBattleKit** (the iOS app) -- owned by the gobattlekit repo/session.
2. **Website + simulator** (pogo-dives + gopvpsim) -- owned by this repo.

## Hard prerequisites (gates before posting)
1. **Website published** (pogo-dives live; attribution signed off; --ship
   gates green). This is the current arc.
2. **`gopvpsim` repo flipped PUBLIC** ("TODO before we post"; Matt approved).
   Gates sending Matt the repo link. Distinct from the website rsync push.
3. **Naming finalized** = gopvpsim (done as a decision); dir-rename done OR
   explicitly deferred with gobattlekit's path refs updated in lockstep.
4. **App-store vs TestFlight timing go/no-go**: post now with the public
   TestFlight link (testflight.apple.com/join/CpCtGsES + "what the listing
   will look like"), or DELAY until the App Store listing is live. UNRESOLVED
   -- gates WHEN to post.

## Content prep (before drafting)
- **Attribution / tag list** (cross-check MEMORY: reference_iv_spectrum_reddit_post,
  project_pvpoke_attribution_module, project_public_contact_discord):
  u/RyanoftheDay, u/JRE47 (crediting, not replacing their work), XehrFelrose
  (ML style, copied), the z11xr0 IV-spectrum-graphs poster, and
  Matt/KakunaMattata42/EmpoleonDynamite (PvPoke). Conditional: orgodemir IF a
  Pareto feature ships.
- **z11xr0 original-graph image recovery**: the source graphs were dead;
  needed the Wayback Machine to view. Recover a working image to link before
  using it in the IV-spectrum attribution.
- **Screenshots + hosting**: capture "Compare my candidates" / close-calls
  screenshots (ML scans + GL/UL dives) and the graphs Matt liked. Decide
  hosting (can Reddit embed, or is Imgur needed?).
- **Dive-selection scan**: pick featured dives where the graph structure is
  visually distinct (Mimikyu GL/UL, UL Tinkaton "fern", horizontal-band
  examples). CAVEAT: Mimikyu graphs come from `--mechanics new`, which MEMORY
  (project_new_pvp_system_2026_06) flags UNVALIDATED -- do NOT feature output
  we can't stand behind; validate first or pick a different example.
- **Writing constraints**: tone = casual / non-expert / non-authoritative.
  Apply feedback_avoid_ai_prose_tells + feedback_no_em_dashes; do fresh web
  research on avoiding AI-sounding prose. Per ship-mode policy, **Michael
  drafts the prose**; Claude does mechanical parts / outlines / bullets only.

## Cross-repo coordination
- The two posts reference each other -> draft together, publish in a
  coordinated window.
- The gobattlekit session owns its app post + updates its references to this
  project (repo=gopvpsim, website=pogo-dives, sibling dir=gopvpsim post-rename).
- See the naming-handoff prompt handed to the gobattlekit session.
