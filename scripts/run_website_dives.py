#!/usr/bin/env python
"""Run deep dives for the website, sequentially.

Dive configurations live in the DIVES list below. Each entry specifies
the species, league, output slug, and any non-default flags. The script
builds the full deep_dive.py command and runs dives one at a time.

Usage:
    python scripts/run_website_dives.py                  # all dives
    python scripts/run_website_dives.py tinkaton          # slug substring filter
    python scripts/run_website_dives.py --dry-run         # show commands only
"""

import argparse
import os
import subprocess
import sys
import time


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
WEBSITE_DIR = os.path.join(REPO_ROOT, 'userdata', 'website')
DEEP_DIVE = os.path.join(SCRIPT_DIR, 'deep_dive.py')

# ---- Dive configurations ----
# Each dict must have: species, league, slug, html_base
# Optional overrides (defaults shown):
#   opponents: 20            (top N from rankings)
#   opponents_file: None     (overrides opponents)
#   top_movesets: 5
#   opp_ivs: 'both'
#   bait: 'both'
#   reference: 'auto'
#   no_thresholds: False
#   shadow: False
#   extra_args: []           (escape hatch for unusual flags)

DIVES = [
    # Order is deliberate: Shadow Sableye pulled to position 1
    # (2026-06-02 — Michael's stated interest after the new-season pull).
    # Foul Play is locked as 1st charged, varying 2nd charged across all
    # 4 legal partners (Power Gem, Drain Punch, Dazzling Gleam, Shadow
    # Sneak) in a single shared-dir dive: `--charged FOUL_PLAY` triggers
    # enumerate_movesets's "pair with all legal partners" branch (line
    # 594), and top_movesets=4 renders every FP-pair via --split-movesets.
    # Sableye has exactly 5 legal charged moves (FP + the 4 partners), so
    # this guarantees the 3 partners Michael specifically asked about
    # (PG / DP / DG) render, plus Shadow Sneak as a 4th option for free.
    # Then Oinkologne pair so the CD article can regenerate earliest if
    # the later dives slip. Tinkaton next (GL then UL). Aegislash pair
    # follows, GL before UL per the D2 decision on 2026-04-18. The other
    # new-season focals (Seismitoad, Jumpluff, Ninetales) bring up the
    # rear next to the existing niche group (Dewgong, Stunfisk, Galarian
    # Corsola). `--reserve-cpus 1` on every entry per the
    # `feedback_reserve_cpu_for_dives` discipline so local work stays
    # responsive if someone else lands on the box mid-run.
    {
        'species': 'Sableye',
        'league': 'great',
        'slug': 'shadow-sableye-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 4,
        'no_thresholds': True,
        'shadow': True,
        'extra_args': ['--fast', 'SHADOW_CLAW', '--charged', 'FOUL_PLAY'],
        # Reference charged moves listed alphabetically (DRAIN_PUNCH <
        # FOUL_PLAY) to match enumerate_movesets' canonical sorted-tuple
        # pair form. Mismatched order (FP first) caused a duplicate
        # m4 HTML in the 2026-06-02 run because the dedup compared
        # (DRAIN_PUNCH, FOUL_PLAY) vs (FOUL_PLAY, DRAIN_PUNCH) as
        # different tuples. Alphabetical here keeps them in sync.
        'reference': 'SHADOW_CLAW,DRAIN_PUNCH,FOUL_PLAY',
    },
    # Male Oinkologne (rank ~204) dive removed 2026-06-25 -- only Female (the
    # meta #36) is dived now. NOTE: this retires the male-vs-female comparison
    # article (it can't be regenerated without the male dive); mark that page
    # Archived / known-out-of-date at publish time.
    {
        'species': 'Oinkologne (Female)',
        'league': 'great',
        'slug': 'oinkologne-female-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        # 2026-06-27: Mud Slap CD has shipped -- MUD_SLAP is now in both
        # fastMoves and eliteMoves and is PvPoke's default fast move
        # (get_default_moveset returns MUD_SLAP). The old TACKLE pin was a
        # pre-CD leftover from the now-removed CD article; the live dive must
        # reference the current meta build.
        'reference': 'MUD_SLAP,BODY_SLAM,TRAILBLAZE',
    },
    {
        'species': 'Tinkaton',
        'league': 'great',
        'slug': 'tinkaton-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        # No 'reference' override: track get_default_moveset (FAIRY_WIND /
        # GIGATON_HAMMER, BULLDOZE) like the UL dive does, so the dive can't
        # go stale again. The old 'FAIRY_WIND,BULLDOZE,PLAY_ROUGH' pin was a
        # pre-CD leftover -- Gigaton Hammer (Tinkaton's CD/Elite-TM signature,
        # an eliteMoves entry) is now PvPoke's default and the stronger build.
    },
    # Fearow GL -- added 2026-06-26 as a launch dive (a one/two-turn fast-move
    # pick suggested by an HSH Discord member; common in GL, no debuff/boost/
    # form-change mechanic so the sim is clean). No hand-authored thresholds
    # exist, so --no-thresholds; default moveset from PvPoke rankings is
    # Peck / Drill Peck + Drill Run.
    {
        'species': 'Fearow',
        'league': 'great',
        'slug': 'fearow-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'no_thresholds': True,
        'reference': 'PECK,DRILL_PECK,DRILL_RUN',
    },
    {
        'species': 'Tinkaton',
        'league': 'ultra',
        'slug': 'tinkaton-ultra-league',
        'html_base': 'index.html',
        # Standard PvPoke UL top-60 opponent pool.
        'opponents_file': 'opponent_pools/ul_top60.txt',
        'no_thresholds': True,
    },
    # Aegislash (Blade) isn't in PvPoke rankings; pass --fast / --charged
    # explicitly via extra_args and --no-thresholds so the auto-loader
    # doesn't search for aegislash_blade.toml in the ranking-keyed paths.
    # Canonical Shield moveset from get_default_moveset is mirrored on
    # Blade so the hypothetical starts-Blade comparison is apples-to-
    # apples. (The Blade dive STARTS in Blade form, an unreachable
    # battle-start state, to isolate Blade-form offense; the in-battle
    # form change is still live, so it reverts to Shield if it shields.)
    #
    # Aegislash GL dives rejoined the overnight chain 2026-04-21 (was
    # previously out-of-band against cs_2026_orlando_top32.txt). The
    # 2026-04-21 pre-ship rename refactor drops compound <br> tier-card
    # names and emits auto-gen standalone-mode narrative for non-CD
    # species; keeping GL Aegislash out of the chain would leave the
    # shipped GL dives on the old compound format, and the Aegislash
    # Blade-vs-Shield GL comparison page + form-change guide article
    # link directly into those GL dives.
    {
        'species': 'Aegislash (Blade)',
        'league': 'great',
        'slug': 'aegislash-blade-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 5,
        'no_thresholds': True,
        'extra_args': ['--fast', 'PSYCHO_CUT',
                       '--charged', 'SHADOW_BALL,GYRO_BALL'],
        'reference': 'PSYCHO_CUT,SHADOW_BALL,GYRO_BALL',
    },
    {
        'species': 'Aegislash (Shield)',
        'league': 'great',
        'slug': 'aegislash-shield-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'extra_args': ['--fast', 'AEGISLASH_CHARGE_PSYCHO_CUT',
                       '--charged', 'SHADOW_BALL,GYRO_BALL'],
        'reference': 'AEGISLASH_CHARGE_PSYCHO_CUT,SHADOW_BALL,GYRO_BALL',
    },
    # UL Aegislash entries were dropped 2026-05-17 per an HSH Discord member
    # review (S2): UL Aegislash is not competitively viable; an HSH Discord member
    # + UL-player contacts confirmed. GL stays.
    # Forretress 4-way: normal vs shadow × Bug Bite vs Volt Switch, same
    # charged moves (Sand Tomb + Rock Tomb — PvPoke default, also the CS
    # meta standard for both fast-move variants). Against the Orlando
    # 2026 top-32 pool. Goal is a fast-move + shadow comparison article
    # built post-dive via compare_loadouts.py. top_movesets=1 because
    # fast+charged are both pinned; only one moveset matches.
    {
        'species': 'Forretress',
        'league': 'great',
        'slug': 'forretress-volt-switch-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'extra_args': ['--fast', 'VOLT_SWITCH',
                       '--charged', 'SAND_TOMB,ROCK_TOMB'],
        'reference': 'VOLT_SWITCH,SAND_TOMB,ROCK_TOMB',
    },
    {
        'species': 'Forretress',
        'league': 'great',
        'slug': 'forretress-bug-bite-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'extra_args': ['--fast', 'BUG_BITE',
                       '--charged', 'SAND_TOMB,ROCK_TOMB'],
        'reference': 'BUG_BITE,SAND_TOMB,ROCK_TOMB',
    },
    {
        'species': 'Forretress',
        'league': 'great',
        'slug': 'forretress-shadow-volt-switch-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'shadow': True,
        'extra_args': ['--fast', 'VOLT_SWITCH',
                       '--charged', 'SAND_TOMB,ROCK_TOMB'],
        'reference': 'VOLT_SWITCH,SAND_TOMB,ROCK_TOMB',
    },
    {
        'species': 'Forretress',
        'league': 'great',
        'slug': 'forretress-shadow-bug-bite-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'shadow': True,
        'extra_args': ['--fast', 'BUG_BITE',
                       '--charged', 'SAND_TOMB,ROCK_TOMB'],
        'reference': 'BUG_BITE,SAND_TOMB,ROCK_TOMB',
    },
    # Dewgong + Stunfisk — GL niche picks Michael wanted to ship
    # alongside the main 2026-04-24 batch. Bumped to top_movesets=3
    # 2026-04-25 to surface enough of the meta to capture practical
    # alternatives: Dewgong's Aqua Jet variants are most-played by raw
    # PvPoke usage (41k vs IcyWind 35k vs DrillRun 32k); Stunfisk has
    # Earthquake/Discharge/Mud Bomb tradeoffs worth comparing. Each
    # dive emits the top 3 screened movesets + the auto reference =
    # ~3-4 per-moveset HTML pages. `reference` omitted so the loader
    # uses PvPoke's default (get_default_moveset) per
    # feedback_use_pvpoke_default_moveset.
    {
        'species': 'Dewgong',
        'league': 'great',
        'slug': 'dewgong-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 3,
    },
    {
        'species': 'Stunfisk',
        'league': 'great',
        'slug': 'stunfisk-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 3,
    },
    # Galarian Corsola GL — niche pick added 2026-04-26. PvPoke top
    # moveset is fine (no `reference` override, so the loader pulls
    # get_default_moveset). top_movesets=1 keeps the surface to a single
    # screened-winner page; bump later if alt-moveset comparison becomes
    # interesting. No thresholds TOML yet — clean dive; we'll author
    # anchors after seeing what flips. opponent_pools/active_variants.toml
    # will auto-merge Forretress (Bug Bite) ± shadow into the matchup
    # matrix unless --no-active-variants is set.
    {
        'species': 'Corsola (Galarian)',
        'league': 'great',
        'slug': 'galarian-corsola-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
    },
    # New-season additions (2026-06-02 PvPoke pull afa3ad740). All four
    # follow the Galarian Corsola pattern: top_movesets=1 (single screened
    # winner page), no_thresholds (clean dive; author anchors after
    # eyeballing the result), PvPoke get_default_moveset via no explicit
    # reference. Bump movesets / add thresholds once the meta picture
    # settles. Each species is also in the refreshed opponent pool
    # (`opponent_pools/gl_top50_plus_cs.txt`) so it appears as an
    # opponent in everyone else's dives, not just as a focal here.
    # Note: Shadow Sableye is pulled to position 1 above (Michael's
    # stated interest); the other three new-season focals stay here.
    {
        'species': 'Seismitoad',
        'league': 'great',
        'slug': 'seismitoad-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
    },
    {
        'species': 'Jumpluff',
        'league': 'great',
        'slug': 'jumpluff-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
    },
    {
        'species': 'Jumpluff',
        'league': 'great',
        'slug': 'shadow-jumpluff-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'shadow': True,
    },
    {
        'species': 'Ninetales',
        'league': 'great',
        'slug': 'ninetales-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
    },
    {
        'species': 'Ninetales',
        'league': 'great',
        'slug': 'shadow-ninetales-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'shadow': True,
    },
    # Sylveon (NAIC GL focal) dive removed 2026-06-25 (rank ~115; the NAIC event
    # pick is no longer a coverage priority). thresholds/sylveon.toml is retained
    # in case it returns.
    # Mimikyu (2026-06-24): newly released and PvPoke-ranked in GL+UL;
    # the disguise mechanic is already ported and PvPoke-exact in our
    # engine (test_mimikyu_vs_azumarill_form_change 9/9, plus the new
    # azumarill_vs_mimikyu_form_change opponent-side oracle row 9/9).
    # No explicit `reference` so the loader pulls get_default_moveset:
    # SHADOW_CLAW + [SHADOW_SNEAK, PLAY_ROUGH] in both leagues (speciesId
    # 'mimikyu'; the bare name resolves correctly — 'Mimikyu (Busted)'
    # maps to mimikyu_busted which is NOT in rankings). Larger standard
    # pools (gl_top50_plus_cs / ul_top60) for a robust
    # read, both of which now also carry Mimikyu as an opponent.
    # no_thresholds: clean dive, author anchors after eyeballing.
    {
        'species': 'Mimikyu',
        'league': 'great',
        'slug': 'mimikyu-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
    },
    {
        'species': 'Mimikyu',
        'league': 'ultra',
        'slug': 'mimikyu-ultra-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/ul_top60.txt',
        'top_movesets': 1,
        'no_thresholds': True,
    },
    # Mimikyu (Busted) starts-busted dives (2026-06-27): a hypothetical that
    # STARTS in Busted form (permanent -1 def from turn one), to isolate the
    # post-bust state -- legitimate because once Busted, Mimikyu stays Busted
    # for the rest of the battle regardless of swaps. Mirrors the Aegislash
    # (Blade) starts-in-alt-form pattern: 'Mimikyu (Busted)' is NOT in PvPoke
    # rankings (maps to mimikyu_busted), so pin get_default_moveset's
    # SHADOW_CLAW + [SHADOW_SNEAK, PLAY_ROUGH] via extra_args + reference and
    # use no_thresholds. The -1 def is applied by the engine's native-stat-buff
    # path (see test_mimikyu_starts_busted.py; the starts-busted state is
    # validated by equivalence to the PvPoke-oracle in-battle bust). UL inherits
    # the standard best-buddy-on default, consistent with the base Mimikyu UL
    # dive above.
    {
        'species': 'Mimikyu (Busted)',
        'league': 'great',
        'slug': 'mimikyu-busted-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'extra_args': ['--fast', 'SHADOW_CLAW',
                       '--charged', 'SHADOW_SNEAK,PLAY_ROUGH'],
        'reference': 'SHADOW_CLAW,SHADOW_SNEAK,PLAY_ROUGH',
    },
    {
        'species': 'Mimikyu (Busted)',
        'league': 'ultra',
        'slug': 'mimikyu-busted-ultra-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/ul_top60.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'extra_args': ['--fast', 'SHADOW_CLAW',
                       '--charged', 'SHADOW_SNEAK,PLAY_ROUGH'],
        'reference': 'SHADOW_CLAW,SHADOW_SNEAK,PLAY_ROUGH',
    },
    # (The standalone 'mimikyu-ultra-league-best-buddy' dive was REMOVED
    # 2026-06-24, Phase 2: the standard 'mimikyu-ultra-league' dive above now
    # carries an in-page "Allow best-buddy (Level 51)" toggle -- Ultra defaults
    # best-buddy on -- with the correct focal-only L51 semantics, so the
    # separate page (which raised BOTH focal and opponents via --max-level 51)
    # was redundant. Built page + index link removed too. Verified: the standard
    # UL Mimikyu dive embeds the active toggle (ivL51 + @51 grids).)
    # Corviknight (2026-06-24): Shadow Corviknight is now officially PvPoke-ranked
    # in GL (a top pick), so it graduates from the constructed pre-release one-off
    # to a real dive. Both forms are dived so the new sibling-trade card bar is
    # two-sided -- each form's card shows its breakpoint/bulkpoint trade vs the
    # other, which is exactly the "shadow or regular?" build question. Default
    # moveset (Sand Attack / Air Cutter, Payback) via get_default_moveset;
    # no_thresholds (clean dive, author anchors after eyeballing).
    {
        'species': 'Corviknight',
        'league': 'great',
        'slug': 'corviknight-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
    },
    {
        'species': 'Corviknight',
        'league': 'great',
        'slug': 'shadow-corviknight-great-league',
        'html_base': 'index.html',
        'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
        'top_movesets': 1,
        'no_thresholds': True,
        'shadow': True,
    },
    # Meta-coverage additions (2026-06-25, off the fresh PvPoke pull). Clean
    # dives on the new-season template: top_movesets=1 (single screened-winner
    # page), no_thresholds (author anchors later), PvPoke get_default_moveset
    # (no explicit reference). GL high-meta picks we weren't yet diving + both
    # Stunfisks (Galarian Steel/Ground AND the regular Electric/Ground we
    # already shipped), and two UL adds (Galarian Moltres, Lickilicky).
    {'species': 'Lickilicky', 'league': 'great', 'slug': 'lickilicky-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Altaria', 'league': 'great', 'slug': 'altaria-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Altaria', 'league': 'great', 'slug': 'shadow-altaria-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True, 'shadow': True},
    {'species': 'Empoleon', 'league': 'great', 'slug': 'empoleon-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Empoleon', 'league': 'great', 'slug': 'shadow-empoleon-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True, 'shadow': True},
    {'species': 'Feraligatr', 'league': 'great', 'slug': 'feraligatr-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Feraligatr', 'league': 'great', 'slug': 'shadow-feraligatr-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True, 'shadow': True},
    {'species': 'Kingdra', 'league': 'great', 'slug': 'kingdra-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Kingdra', 'league': 'great', 'slug': 'shadow-kingdra-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True, 'shadow': True},
    {'species': 'Azumarill', 'league': 'great', 'slug': 'azumarill-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Sableye', 'league': 'great', 'slug': 'sableye-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Medicham', 'league': 'great', 'slug': 'medicham-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Sealeo', 'league': 'great', 'slug': 'shadow-sealeo-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True, 'shadow': True},
    {'species': 'Grumpig', 'league': 'great', 'slug': 'grumpig-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Talonflame', 'league': 'great', 'slug': 'talonflame-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Stunfisk (Galarian)', 'league': 'great', 'slug': 'galarian-stunfisk-great-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/gl_top50_plus_cs.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Moltres (Galarian)', 'league': 'ultra', 'slug': 'galarian-moltres-ultra-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/ul_top60.txt',
     'top_movesets': 1, 'no_thresholds': True},
    {'species': 'Lickilicky', 'league': 'ultra', 'slug': 'lickilicky-ultra-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/ul_top60.txt',
     'top_movesets': 1, 'no_thresholds': True},
    # Zygarde (Complete Forme) UL focal dive (added 2026-06-25 per Michael).
    # Already a ul_top60 opponent; this gives it its own dive page. Default
    # moveset Dragon Tail / Crunch + Earthquake (get_default_moveset).
    {'species': 'Zygarde (Complete Forme)', 'league': 'ultra', 'slug': 'zygarde-complete-ultra-league',
     'html_base': 'index.html', 'opponents_file': 'opponent_pools/ul_top60.txt',
     'top_movesets': 1, 'no_thresholds': True},
]


# When set by --reserve-cpus on the CLI, overrides every dive's per-entry
# reserve_cpus (e.g. 0 to use ALL cores for an unattended overnight run; the
# per-dive default of 1 exists for keeping a core free during interactive work).
_RESERVE_OVERRIDE = None


def build_command(dive):
    """Build the deep_dive.py command list from a dive config dict."""
    html_path = os.path.join(WEBSITE_DIR, dive['slug'], dive['html_base'])

    cmd = [sys.executable, DEEP_DIVE, dive['species'],
           '--league', dive['league']]

    if 'opponents_file' in dive:
        cmd += ['--opponents-file', dive['opponents_file']]
    elif 'opponents' in dive:
        cmd += ['--opponents', str(dive['opponents'])]

    cmd += ['--top-movesets', str(dive.get('top_movesets', 5))]
    cmd += ['--opp-ivs', dive.get('opp_ivs', 'both')]
    cmd += ['--bait', dive.get('bait', 'both')]
    cmd += ['--reference', dive.get('reference', 'auto')]

    if dive.get('no_thresholds'):
        cmd += ['--no-thresholds']
    if dive.get('shadow'):
        cmd += ['--shadow']

    cmd += [
        '--html', html_path,
        '--interactive',
        '--standalone',
        '--mirror-slayer',
        '--mirror-slayer-metric', 'all',
        '--mirror-slayer-rounds', '4',
        '--mirror-slayer-pool', '30',
        '--mirror-slayer-show', '20',
        '--split-movesets',
        '--reserve-cpus', str(_RESERVE_OVERRIDE if _RESERVE_OVERRIDE is not None
                              else dive.get('reserve_cpus', 1)),
    ]

    # Best-buddy / L51 toggle. 'best_buddy' may be 'on'/'off'/'auto' (default
    # 'auto' = on for Great + Ultra; no-op species show the toggle but it does
    # nothing, with no extra sims). 'best_buddy_display' (50/51)
    # picks which level the page opens on. Per-species TOML can also set these;
    # the CLI flag here wins over the TOML.
    if 'best_buddy' in dive:
        cmd += ['--best-buddy', dive['best_buddy']]
    if 'best_buddy_display' in dive:
        cmd += ['--best-buddy-display', str(dive['best_buddy_display'])]

    if 'extra_args' in dive:
        cmd += dive['extra_args']

    return cmd


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('filter', nargs='?', default=None,
                        help='Substring filter on slug (e.g. "tinkaton", "ultra")')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print commands without running them')
    parser.add_argument('--reserve-cpus', type=int, default=None,
                        help='Override every dive\'s --reserve-cpus (e.g. 0 to '
                             'use all cores for an unattended run; default keeps '
                             'each dive\'s per-entry value, normally 1)')
    args = parser.parse_args()

    global _RESERVE_OVERRIDE
    _RESERVE_OVERRIDE = args.reserve_cpus

    dives = DIVES
    if args.filter:
        dives = [d for d in dives
                 if args.filter.lower() in d['slug'].lower()]

    if not dives:
        print("No matching dives found.")
        return

    print(f"Found {len(dives)} dive(s) to run:\n")
    for d in dives:
        print(f"  - {d['slug']}")
    # Copy-paste monitor recipe (Michael's standing ask: every dive/chain
    # kick should hand over the watch command for a second terminal).
    print("\nMonitor in a second terminal:\n"
          "  watch -c -n 5 scripts/chain_status.py --chain overnight\n",
          flush=True)
    print()

    for i, dive in enumerate(dives):
        cmd = build_command(dive)
        cmd_str = ' '.join(cmd)
        print(f"{'='*60}")
        print(f"[{i+1}/{len(dives)}] {dive['slug']}")
        print(f"{'='*60}")
        print(f"  {cmd_str}\n")

        if args.dry_run:
            continue

        t0 = time.time()
        result = subprocess.run(cmd, cwd=REPO_ROOT)
        elapsed = time.time() - t0
        if result.returncode != 0:
            print(f"\n  [FAILED] {dive['slug']} (exit code {result.returncode})")
            print(f"  Stopping. Fix the issue and re-run.")
            sys.exit(1)
        print(f"\n  Done in {elapsed/60:.1f} min\n")

        # Auto-generate the species-narrative block post-dive. The
        # patcher reads the dive's embedded SCORES_GZ + DATA and fills
        # empty intro.body / meta_role.good_at / meta_role.bad_at from
        # templates in scripts/auto_gen_narrative.py. Idempotent with
        # --force; fires for every species with dive data (CD species
        # get the CD-vs-baseline comparison, non-CD species like
        # Aegislash get the standalone stats rollup via B2 templates).
        # Runs per-dive so a failure doesn't block later dives.
        dive_dir = os.path.join(WEBSITE_DIR, dive['slug'])
        if os.path.isdir(dive_dir):
            patcher = os.path.join(SCRIPT_DIR, 'patch_dive_species_narrative.py')
            patch_cmd = ['python', patcher, dive_dir, '--force']
            print(f"  Patching narrative: {' '.join(patch_cmd)}")
            patch_result = subprocess.run(patch_cmd, cwd=REPO_ROOT)
            if patch_result.returncode != 0:
                print(f"  [WARN] narrative patch failed for {dive['slug']} "
                      f"(rc={patch_result.returncode}); continuing.")

    if not args.dry_run:
        print(f"\nAll {len(dives)} dive(s) complete.")
        print("Run 'python scripts/build_website_index.py' to rebuild the index.")


if __name__ == '__main__':
    main()
