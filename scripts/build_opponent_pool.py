#!/usr/bin/env python3
"""
Generate an opponent-pool text file for ``deep_dive.py --opponents-file``.

The committed pool files under ``opponent_pools/`` (e.g.
``gl_top50_plus_cs.txt``) are regeneratable via this script so they can
be refreshed when PvPoke's rankings or groups drift. Each pool file is
a newline-delimited list of PvPoke ``speciesName`` values; blank lines
and ``#`` comments are ignored by the deep_dive parser.

Usage::

    # Regenerate the default GL pool (top 50 rankings ∪ championshipseries).
    python scripts/build_opponent_pool.py gl_top50_plus_cs

    # Write to a custom path.
    python scripts/build_opponent_pool.py gl_top50_plus_cs \
        --out /tmp/pool.txt

List known recipes with ``--list``. The recipes are hardcoded here
rather than parameterized because "top 50 + championshipseries" is a
specific meta-analyst choice and the point of committing the resulting
file is to make the dives reproducible against a named pool.
"""
import argparse
import collections
import datetime
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'src'))

from gopvpsim.data import (load_gamemaster, load_group, load_rankings,  # noqa: E402
                           load_cup_rankings)
from gopvpsim.pokemon import LEAGUE_CAPS  # noqa: E402  (canonical CP caps)


def _id_to_name_map():
    gm = load_gamemaster()
    return {m['speciesId']: m['speciesName'] for m in gm['pokemon']}


def _cs_names():
    """Return the championshipseries group as PvPoke speciesName values."""
    id_to_name = _id_to_name_map()
    names = []
    for entry in load_group('championshipseries'):
        if isinstance(entry, str):
            names.append(id_to_name.get(entry, entry))
        elif isinstance(entry, dict):
            sid = entry.get('speciesId') or entry.get('id')
            if sid:
                names.append(id_to_name.get(sid, sid))
    return names


# ---------------------------------------------------------------------------
# Curated INCLUSIONS -- species that must be in a pool regardless of the cut
# ---------------------------------------------------------------------------
# The mirror of scripts/verify_opponent_pools.py's CURATED_EXCLUSIONS. An
# entry here is a deliberate hand-extension: a species we want dives to sim
# against even though it does not clear the recipe's rank cut.
#
# Recorded HERE, next to the recipes, so a regeneration applies it
# automatically -- and verify_opponent_pools.py imports this same table and
# FAILS when a required species is missing from a committed pool. Without
# that pairing, "remember to add X" is a note someone has to honour by hand
# every time the pools are rebuilt, which is how the pools went stale in the
# first place.
#
# Add one only with a stated reason. "It seems good" is a ranking argument --
# the recipe already handles those.
# AUGMENTATION SOURCES (Michael, 2026-09-08)
# ------------------------------------------
# The GL top-N recipes cut on PvPoke's rankings alone -- a threshold on a
# SIMULATED 1v1 score. The augmentation source is a world-class human expert's
# tier list, and the reason (Michael, 2026-09-08) is that such a player knows
# things a sim score structurally cannot express:
#
#   1. Which mons actually PERFORM, as against "sim heroes" -- species that
#      rank well because the simulation grants them favourable play, most often
#      by being heavily BAIT-DEPENDENT. A sim's bait policy is a modelled
#      opponent; a real opponent does not reliably fall for the bait, so the
#      score overstates the species by exactly the amount the bait was assumed
#      to work.
#   2. Which mons play well in real 3v3 battles -- swap pressure, safe-swap
#      duty, how a species carries energy or a shield advantage into the next
#      matchup.
#
# Both cut against OUR numbers as much as PvPoke's; this is not a claim that
# their ranker is uniquely blind. We score isolated 1v1s under a bait policy of
# our own, and `simulate()` takes exactly two BattlePokemon with no
# incoming-Pokemon path, so every multi-mon consideration in (2) is invisible
# to us by construction. See the Deoxys (Defense) caveat below for a case where
# we can name the resulting error and its direction.
#
# Secondary, and true only in this window: a tier list is forward-looking,
# while a ranking can only score the gamemaster it has -- and ours is still
# partly a guess at the rebalance.
#
# DO NOT justify this with the Deoxys (Defense) numbers. An earlier draft of
# this block claimed PvPoke had it GL #540 while players rated it a threat,
# making it look like the ranker missed something the community saw. That is
# wrong and Michael corrected it (2026-09-08): #540 scores the OLD moveset and
# nobody rated it there either, #60 scores the NEW one and the community
# agrees. Ranker and players concur at both points; the moveset changed between
# them, not the opinion. It is an example of PvPoke tracking a rebalance
# correctly -- the opposite of a blind spot.
#
#   * ItsAxn, expected tier list for the new season (screenshot supplied
#     2026-09-08). Tiers, strongest first: Meta Defining, Top Meta, Meta,
#     Strong Spice, Fringe Spice, Garbage. Anything in the top THREE tiers is
#     a candidate for the GL pool regardless of rank.
#
# NOT TRANSCRIBED YET, on purpose. The source we hold is an IMAGE of ~250
# sprites, and reading species off it by eye would land some wrong. That is a
# silent failure: a misread species in a pool sims the wrong opponent, and no
# test catches it -- the pool guard only checks a name against rankings, and a
# wrong-but-real species passes.
#
# HOW TO TRANSCRIBE IT (Michael, 2026-09-08): the tier list comes from an
# ItsAxn video; pull the TRANSCRIPT and take the names from there, using the
# sprites only to cross-check. Names in text, image as verification -- never
# the reverse. Michael has the link when it is time to build lists.
#
# Confidently readable from the image so far, pending that pass: Mimikyu,
# Cramorant and Sableye (Meta Defining), Deoxys (Defense) (Top Meta), Quagsire
# and Altaria (Meta) -- and Deoxys (Defense) is already an entry below, added
# on independent grounds, which is a small check on the source.

CURATED_INCLUSIONS = {
    'gl_top50_plus_cs': {
        'Deoxys (Defense)': (
            'Michael, 2026-09-06. Post-rebalance it switches its fast move to '
            'LOW_KICK and jumps GL #540 -> #60 (measured on '
            'origin/twilight-trails vs origin/master). Still outside the '
            'top-50 cut, hence the hand-extension. Kit becomes '
            'LOW_KICK / PSYCHO_BOOST, THUNDERBOLT.\n'
            '\n'
            'CAVEAT, and it cuts against us: it fires Psycho Boost (35 '
            'energy, guaranteed self -2 attack) and then SWAPS OUT to shed '
            'the debuff. Our core never switches (simulate() takes exactly '
            'two BattlePokemon, no incoming-Pokemon path), so we sim it '
            'eating the -2 for the rest of the fight. Our numbers UNDERSTATE '
            'it as an opponent -- read a Deoxys (Defense) matchup score as a '
            'floor, not an estimate. Same limitation as the swap rules in '
            'docs/validations/2026-09-03_new_turn_system_ground_truth.md.'),
        'Melmetal': (
            'Michael, 2026-09-06. The Twilight Trails rebalance takes '
            'DOUBLE_IRON_BASH from 55 to 70 power; its moveset is otherwise '
            'UNCHANGED, so the buff is the whole story. Jumps GL #79 -> #7 '
            '(measured on origin/twilight-trails vs origin/master), so it '
            'will clear the top-50 cut on merit post-rebalance and this entry '
            'becomes belt-and-braces rather than load-bearing. Kept anyway: '
            'Meltan is farmable without limit via the Mystery Box, so it is '
            'the one species an opponent can scout for a SPECIFIC IV spread '
            'rather than taking what they catch -- worth guaranteeing in the '
            'pool independent of where any given ranking pass puts it.'),
    },
    'gl_top30_plus_cs_top100': {
        'Melmetal': 'same as gl_top50_plus_cs -- this is the fast-dive GL pool',
        'Deoxys (Defense)': ('same as gl_top50_plus_cs, including the '
                             'no-swap caveat -- this is the fast-dive GL pool'),
    },
    # Hand-built files with no recipe: verify enforces, a human adds on rebuild.
    'ul_top60.txt': {
        'Melmetal': ('as GL. UL #72 -> #6 post-rebalance, so likewise clears '
                     'on merit; kept for the same scoutability reason.'),
        'Deoxys (Defense)': ('as GL, including the no-swap caveat. UL #345 -> '
                             '#84 post-rebalance -- still outside the top-60 '
                             'cut, so this one stays load-bearing.'),
    },
    'master_top60.txt': {
        'Melmetal': ('as GL. Already clears the ML cut at #38 -- pinned so a '
                     'regeneration cannot silently drop it.'),
    },
}

# NB the ranks above are the reason these entries are NOT self-maintaining.
# Every rank cited is from PRE-rebalance master unless marked post-; the
# post-rebalance figures come from origin/twilight-trails, whose move data is
# still partly PvPoke-guessed (17 of 27 changed moves carry inferred
# energies). Re-check them when the rebalance is public -- an entry that has
# become redundant is clutter, and one whose reasoning has gone stale is worse.


_AEGISLASH_REASON = (
    'Michael, 2026-09-09: TEMPORARY, pending a fix. Our engine over-farms '
    'Aegislash in SHIELD form. Traced on aegislash_blade vs azumarill [1v0] '
    'against pvpoke master: both engines toggle Blade->Shield->Blade, but '
    'PvPoke commits its second Shadow Ball on T30 ("it KOs or it wants to '
    'farm down afterwards") while ours banks to the full 100 energy and '
    'throws on T44 -- 25 turns farming at 1 damage per Psycho Cut vs their '
    '10. Scores 570/429 ours vs 712/287 theirs. That is 6 of the 6 '
    'undocumented oracle mismatches. Sims against a wrong Aegislash would '
    'contaminate every other focal, so it comes out until the DP commit '
    'behaviour in the low-attack form is fixed. REMOVE THIS once the oracle '
    'grid is green -- Aegislash clears the cut on merit and belongs here.'
)


# ---------------------------------------------------------------------------
# Curated EXCLUSIONS -- species the recipe produces that we deliberately drop
# ---------------------------------------------------------------------------
# Lives here for the same reason CURATED_INCLUSIONS does: so a REGENERATION
# applies it. verify_opponent_pools.py keeps the matching entries so the
# absence reads as a decision rather than as drift. Before 2026-09-09 only the
# checker had a table, which meant a rebuild silently re-added anything
# excluded -- the exact "remember to redo it by hand" step the inclusion table
# was built to kill.
#
# An entry needs a reason someone actually decided. "Not looked at yet" is
# drift, not an exclusion.

CURATED_EXCLUSIONS = {
    'gl_top50_plus_cs': {
        'Aegislash (Blade)': _AEGISLASH_REASON,
        'Aegislash (Shield)': _AEGISLASH_REASON,
    },
    'gl_top30_plus_cs_top100': {
        'Aegislash (Blade)': _AEGISLASH_REASON,
        'Aegislash (Shield)': _AEGISLASH_REASON,
    },
    # NOT ul_top60.txt: Aegislash has been out of the UL pool since
    # 2026-06-25 for an unrelated reason (not UL-viable as an opponent -- see
    # that file's header). Adding it here would overwrite a correct, older
    # record with this one's reason.
}


def apply_exclusions(pool_key, names):
    """Drop any curated exclusions from ``names`` (order preserved)."""
    drop = set(CURATED_EXCLUSIONS.get(pool_key, {}))
    return [n for n in names if n not in drop]


# ---------------------------------------------------------------------------
# ItsAxn "Meta and better" -- community tier list, folded into the GL cut
# ---------------------------------------------------------------------------
# Source: ItsAxn, new-season GL tier list.
#   https://www.youtube.com/watch?v=EstL6_1AB-w
# Tiers, strongest first: meta defining > top meta > (regular) meta > spice >
# fringe spice > garbage (stated by him at 00:28-00:36). Michael's rule
# (2026-09-09): everything in META OR BETTER is a pool candidate regardless of
# where PvPoke's ranker puts it -- see AUGMENTATION SOURCES above for why an
# expert's read catches things a 1v1 score cannot ("sim heroes", 3v3 play).
#
# TRANSCRIBED FROM THE TRANSCRIPT, not from the tier-list image, per the
# procedure in AUGMENTATION SOURCES. Boundaries used:
#   top meta ends  15:30  ("And rounding out our top meta...")
#   meta ends     ~21:59  (first spice language: "might be an interesting
#                          spice pick")
#
# JUDGMENT CALLS, so they can be revisited:
#  * EXCLUDED as passing references rather than tier placements -- each is
#    named inside another mon's sentence: Floette ("Carbink or Floette that
#    otherwise were..."), Electrike ("want to see Electrike"), Wigglytuff
#    ("Just like Wigglytuff was").
#  * EXCLUDED by Michael (2026-09-09) as sitting on the meta/spice boundary
#    at 20:47-21:49, where each is discussed only as a move-buff beneficiary
#    rather than placed: Doublade (#71), Maushold (#200), Oinkologne (#340),
#    Nidoqueen (#235), Persian (#139), Audino (#376), Mega Malamar.
#  * NOT LISTED HERE because they already clear the top-50 cut on merit
#    post-rebalance: Mimikyu (Busted) #18, Deoxys (Defense) #28, Corsola
#    (Galarian) #3, Sableye #48, Blastoise #50, Dondozo #39. He rates all of
#    them meta-or-better and the ranker now agrees.
#  * Aegislash (Blade) is in his TOP META at #72 and is deliberately NOT here:
#    it is in CURATED_EXCLUSIONS because OUR ENGINE sims it wrong, not because
#    it is weak. Restore it to this list when that defect is fixed.

ITSAXN_META_PLUS = {
    'Lickilicky':          'top meta, 05:19, x12 mentions; GL #155',
    'Toxapex':             'top meta, 08:36; GL #126',
    'Charjabug':           'top meta, 11:53; GL #60',
    'Forretress':          'top meta, 12:49; GL #55',
    'Spidops':             'top meta, 13:20; GL #57',
    'Morpeko (Hangry)':    'top meta, 14:04 (he says "Full Belly"; PvPoke '
                           'ranks the Hangry form, and it form-changes in '
                           'battle either way); GL #88',
    'Rillaboom':           'meta, 16:14; GL #70. Also named by Michael.',
    'Wartortle':           'meta, 17:16; GL #110',
    'Bombirdier':          'meta, 18:37; GL #228',
    'Dunsparce':           'meta, 18:53; GL #91',
    'Volbeat':             'meta, 19:17; GL #193',
}


def apply_itsaxn(names):
    """Append ItsAxn meta-or-better picks missing from ``names``."""
    out = list(names); have = set(out)
    for species in ITSAXN_META_PLUS:
        if species not in have:
            out.append(species)
    return out


def apply_inclusions(pool_key, names):
    """Append any curated inclusions missing from ``names`` (order preserved)."""
    out = list(names)
    have = set(out)
    for species in CURATED_INCLUSIONS.get(pool_key, {}):
        if species not in have:
            out.append(species)
    return out


def recipe_gl_top50_plus_cs():
    """Top 50 GL rankings union PvPoke championshipseries group.

    PvPoke's championshipseries adds bulky mons that don't clear the
    rankings' top 50 cut (Talonflame, Togekiss, Furret, Diggersby,
    Politoed, Togekiss, etc.) plus a few meta-niche picks. The union is
    the opponent pool we use for "real" GL deep dives where you want
    comprehensive coverage.
    """
    top50 = [r['speciesName'] for r in load_rankings('great')[:50]]
    cs = _cs_names()
    seen, union = set(), []
    for n in top50 + cs:
        if n not in seen:
            seen.add(n)
            union.append(n)
    union = apply_exclusions('gl_top50_plus_cs',
                             apply_itsaxn(
                                 apply_inclusions('gl_top50_plus_cs', union)))
    return union, (f'Top 50 GL overall rankings (PvPoke) union the '
                   f'championshipseries group. {len(union)} unique species.')


def recipe_gl_top30_plus_cs_top100():
    """Top 30 GL rankings union championshipseries members ranked <= 100.

    Smaller opponent pool for faster deep dives. Drops the deepest CS
    entries (Politoed #101, Togekiss #106, Steelix #147, Piloswines
    #235/#256) while keeping every CS mon within realistic meta reach.
    Lands at ~42 species vs 61 for gl_top50_plus_cs. Deep dives scale
    worse than O(N^2), so trimming the pool is a large time win.
    Shadow/non-shadow pairs are deliberately both kept when both fall
    inside the cuts — the stat-multiplier shifts make them distinct
    prep targets, not near-duplicates.
    """
    rankings = load_rankings('great')
    rank = {r['speciesName']: i + 1 for i, r in enumerate(rankings)}
    top30 = [r['speciesName'] for r in rankings[:30]]
    cs_filt = [n for n in _cs_names() if rank.get(n, 10**9) <= 100]
    seen, union = set(), []
    for n in top30 + cs_filt:
        if n not in seen:
            seen.add(n)
            union.append(n)
    union = apply_exclusions('gl_top30_plus_cs_top100',
                             apply_itsaxn(
                                 apply_inclusions('gl_top30_plus_cs_top100', union)))
    return union, (f'Top 30 GL overall rankings (PvPoke) union '
                   f'championshipseries members ranked <= 100. '
                   f'{len(union)} unique species.')


# --- Championship-series tournament pools ---
#
# Dracoviz publishes per-team rosters (see scripts/fetch_dracoviz_tournament.py);
# we snapshot one JSON dump per tournament under docs/tournament_data/. These
# recipes consume a dump and emit an opponent pool ordered by in-practice
# usage frequency, filtered by `final_rank <= cutoff`. Useful for questions
# like "what should I actually prep against?" where PvPoke's curated
# championshipseries group is too broad or stale.

# Dracoviz encodes regional/form variants as "[<name> [<form> Form]]" or
# "[<name> [<form> Forme]]". Extract the inner form name.
_FORM_RE = re.compile(r'^\[[^[]+\[(.+?) (?:Form|Forme)\]\]$')

# Species where Dracoviz drops the form distinction but PvPoke treats
# forms as separate entries; default to the GL-competitive pick.
_FORM_DEFAULTS = {
    'Gourgeist':  'Super',     # Super is the GL meta size
    'Aegislash':  'Shield',    # GL registers in Shield form (Blade triggers mid-battle)
}


def _dracoviz_to_pvpoke_name(mon):
    """Convert a Dracoviz roster entry to a PvPoke speciesName string."""
    name = mon['name']
    form = mon.get('form', '')
    if form:
        m = _FORM_RE.match(form)
        base = f'{name} ({m.group(1)})' if m else name
    elif name in _FORM_DEFAULTS:
        base = f'{name} ({_FORM_DEFAULTS[name]})'
    else:
        base = name
    if mon.get('shadow', False):
        base = f'{base} (Shadow)'
    return base


def _load_tournament_rosters(dump_name):
    path = os.path.join(REPO, 'docs', 'tournament_data', f'{dump_name}.json')
    with open(path) as f:
        return json.load(f)


def _tournament_pool(dump_name, rank_cutoff, label):
    """Order species by in-tournament appearance count (desc), filtered to
    teams with ``final_rank <= rank_cutoff`` (``None`` = all teams).

    Entries whose normalized name isn't in PvPoke's gamemaster (off-meta
    picks the sim can't score) are skipped with a warning — those teams
    still contribute their other five members to the pool.
    """
    rosters = _load_tournament_rosters(dump_name)
    if rank_cutoff is not None:
        rosters = [r for r in rosters
                   if r.get('final_rank', 10**9) <= rank_cutoff]

    gm = load_gamemaster()
    known = {m['speciesName'] for m in gm['pokemon']}

    counts = collections.Counter()
    skipped = collections.Counter()
    for r in rosters:
        for mon in r['roster']:
            nm = _dracoviz_to_pvpoke_name(mon)
            if nm in known:
                counts[nm] += 1
            else:
                skipped[nm] += 1

    if skipped:
        print(f'[warn] {sum(skipped.values())} mon entries '
              f'({len(skipped)} unique names) not in PvPoke gamemaster, '
              f'skipped:', file=sys.stderr)
        for nm, n in skipped.most_common():
            print(f'  {n:3d}  {nm!r}', file=sys.stderr)

    names = [n for n, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    header = (f'{label}. {len(names)} unique species from {len(rosters)} '
              f'teams, ordered by appearance count (most-used first).')
    return names, header


def recipe_cs_2026_orlando_all():
    """Every species used on any 2026-Orlando team (all 156 rosters)."""
    return _tournament_pool('cs_2026_orlando', None,
                            'Championship Series Orlando 2026, all teams')


def recipe_cs_2026_orlando_top32():
    """Species used by any team finishing top-32 at 2026-Orlando."""
    return _tournament_pool('cs_2026_orlando', 32,
                            'Championship Series Orlando 2026, top-32 finishers')


def recipe_cs_2026_orlando_top8():
    """Species used by any team finishing top-8 at 2026-Orlando (corebreaker-hunting pool)."""
    return _tournament_pool('cs_2026_orlando', 8,
                            'Championship Series Orlando 2026, top-8 finishers')


# --- Limited-cup meta pools ---
#
# A cup dive is mechanically Great League (CP 1500), but its opponent pool is
# the cup meta, and each opponent uses the cup's recommended moveset (which can
# differ from the open-GL moveset). Membership comes from PvPoke's curated
# `groups/<cup>.json` meta (plan Decision 4: the ~20-species curated meta, not
# a rankings top-N slice); movesets are baked from the cup rankings (Decision
# 6) as inline `| fast= | charged=` overrides so deep_dive.py needs no cup
# awareness to sim the pool. active_variants is intentionally NOT merged for
# cup dives (the cup DIVE must pass --no-active-variants).


def recipe_cup_meta(cup, league, cup_pretty):
    """Curated cup meta as an opponent pool, movesets baked from cup rankings."""
    cp = LEAGUE_CAPS[league]
    id_to_name = _id_to_name_map()
    rankings = load_cup_rankings(cup, cp)
    rank = {r['speciesId']: i + 1 for i, r in enumerate(rankings)}
    mv = {r['speciesId']: r['moveset'] for r in rankings}
    rows = []
    for e in load_group(cup):
        if isinstance(e, dict):
            sid = e.get('speciesId') or e.get('id')
        else:
            sid = e
        name = id_to_name.get(sid, sid)
        if sid in mv:
            fast, charged = mv[sid][0], mv[sid][1:]
        elif isinstance(e, dict):  # unranked in cup rankings: use the group moveset
            fast, charged = e.get('fastMove'), e.get('chargedMoves', [])
        else:
            raise ValueError(f'{sid!r} in {cup} group has no moveset source')
        rows.append((rank.get(sid, 10**9),
                     f"{name} | fast={fast} | charged={','.join(charged)}"))
    lines = [line for _, line in sorted(rows, key=lambda x: (x[0], x[1]))]
    header = (
        f'{cup_pretty} ({league.capitalize()} League CP {cp}) curated meta '
        f'({len(lines)} species), ordered by cup rank; movesets baked from the '
        f'{cup} cup rankings. Lines carry inline "| fast= | charged=" overrides '
        f'(one opponent per line); active_variants intentionally NOT merged '
        f'(dive with --no-active-variants).')
    return lines, header


def recipe_equinox_great():
    """Devon Equinox Cup (GL 1500) curated 20-species meta, cup movesets."""
    return recipe_cup_meta('equinox', 'great', 'Equinox Cup')


RECIPES = {
    'gl_top50_plus_cs': recipe_gl_top50_plus_cs,
    'equinox_great': recipe_equinox_great,
    'gl_top30_plus_cs_top100': recipe_gl_top30_plus_cs_top100,
    'cs_2026_orlando_all': recipe_cs_2026_orlando_all,
    'cs_2026_orlando_top32': recipe_cs_2026_orlando_top32,
    'cs_2026_orlando_top8': recipe_cs_2026_orlando_top8,
}


def write_pool(names, header, out_path):
    with open(out_path, 'w') as f:
        f.write(f'# {header}\n')
        f.write(f'# Generated {datetime.date.today()} by '
                f'scripts/build_opponent_pool.py\n')
        f.write('# Format: one PvPoke speciesName per line; '
                'blank lines and # comments ignored.\n\n')
        for n in names:
            f.write(n + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('recipe', nargs='?',
                   help='Recipe name (see --list).')
    p.add_argument('--out', metavar='PATH',
                   help='Override output path (default: opponent_pools/<recipe>.txt).')
    p.add_argument('--list', action='store_true', help='List available recipes.')
    args = p.parse_args()

    if args.list or not args.recipe:
        print('Available recipes:')
        for name, fn in RECIPES.items():
            doc = (fn.__doc__ or '').strip().splitlines()[0]
            print(f'  {name:25s} {doc}')
        return 0

    if args.recipe not in RECIPES:
        print(f'Unknown recipe: {args.recipe}', file=sys.stderr)
        print(f'Available: {", ".join(sorted(RECIPES))}', file=sys.stderr)
        return 2

    names, header = RECIPES[args.recipe]()
    out = args.out or os.path.join(REPO, 'opponent_pools', f'{args.recipe}.txt')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_pool(names, header, out)
    print(f'Wrote {len(names)} species to {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
