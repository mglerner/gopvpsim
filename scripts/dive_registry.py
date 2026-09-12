"""Derive the website dive list from the opponent pools.

WHY THIS EXISTS. Until 2026-09-09 the dive list was a 950-line hand-written
``DIVES`` literal in run_website_dives.py, maintained independently of the
opponent pools. The two drifted badly: of 71 GL pool species, 31 had no dive
page (everything the rebalance and ItsAxn's tier list brought in -- Deoxys
(Defense), Hydreigon (Shadow), Toxapex, Ninetales (Alolan), Rillaboom,
Spidops, ...), while 20 dive focals were absent from the pool (last season's
picks that have since fallen out: Greedent #197, Lickilicky #155, Wigglytuff
#107, Sealeo, Sliggoo). Nothing regenerated one from the other and nothing
warned when they diverged.

It also carried a lot of pure duplication: ``html_base`` is the constant
'index.html' on all 95 entries, ``opponents_file`` is 95 copies of 2 values,
and 9 of 13 ``reference`` movesets simply restated PvPoke's default -- which
means they go silently STALE when PvPoke rebalances (Oinkologne's default
moved to TAKE_DOWN this season and the pinned reference did not follow).

WHAT IS DERIVED vs OVERRIDDEN. Everything mechanical comes from the pool:
species, league, shadow, slug, html_base, opponents_file. Only genuinely
editorial content lives in the tables below -- moveset pins, non-default
reference lines, strategy-policy choices, how many movesets to show, and
whether hand-authored thresholds apply.

WIRED IN 2026-09-10 (run_website_dives.DIVES = all_dives()).

MOVESET RULES (2026-09-11). "Bake" must mean "bake with a legit set of
moves", so how many movesets a page renders is a RULE, not a per-slug fact:

1. Every dive renders DEFAULT_TOP_MOVESETS screened movesets. The old
   literal carried 42 per-slug ``top_movesets`` overrides (35 of them ``1``,
   a cheap-coverage setting from a 2026-06-25 bulk add) that were copied
   verbatim into this table by the equivalence gate. They made Sableye
   render ONE moveset and Shadow Sableye FOUR, so the two pages shared no
   moveset at all. ``top_movesets`` is no longer an override key.
2. PvPoke's default moveset is always a rendered page: deep_dive.py sweeps
   the ``--reference auto`` moveset and appends it when the screen prunes
   it (deep_dive.py "Reference sweep"). Nothing to configure here.
3. A shadow/plain PAIR renders the UNION of both members' screened sets
   (``pair_partner`` below; run_website_dives passes ``--union-with-form``
   plus the partner's pins so each dive can reproduce the partner's screen
   deterministically). Pairing requires the same species and league and
   either the same ``--fast`` pin or one side unpinned, so the Forretress
   fast-move split pages pair only with their like-fast shadow sibling.
"""
from __future__ import annotations

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mechanical, and identical across every entry of the old literal.
HTML_BASE = 'index.html'
DEFAULT_OPPONENTS = {
    'great': 'opponent_pools/gl_top50_plus_cs.txt',
    'ultra': 'opponent_pools/ul_top60.txt',
}

# PvPoke writes regional forms as "Corsola (Galarian)"; the published slugs put
# the region FIRST ("galarian-corsola-great-league"). A rule, not exceptions --
# it covers 7 of the 11 slugs the naive rule got wrong.
_REGIONAL = re.compile(r'^(.*?)\s*\((Alolan|Galarian|Hisuian|Paldean)\)$')


def dive_slug(species, league, shadow=False):
    """The published slug for a dive. URL STABILITY DEPENDS ON THIS."""
    m = _REGIONAL.match(species)
    name = f'{m.group(2)} {m.group(1)}' if m else species
    if shadow:
        name = 'Shadow ' + name
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return f'{base}-{league}-league'


# Slugs the rule cannot produce. Kept because the URLs are already published.
SLUG_EXCEPTIONS = {
    # Forretress ships one page per FAST MOVE; the primary keeps the fast move
    # in its slug, and the sibling lives in EXTRA_DIVES below.
    ('Forretress', 'great', False): 'forretress-volt-switch-great-league',
    ('Forretress', 'great', True): 'forretress-shadow-volt-switch-great-league',
    # "Complete Forme" is shortened to "complete" in the published URL.
    ('Zygarde (Complete Forme)', 'ultra', False): 'zygarde-complete-ultra-league',
}

# Additional pages for a species that already has one. Forretress is the ONLY
# case in the current list -- it is dived at both fast moves because the choice
# genuinely changes the matchup spread, which no rankings default can express.
EXTRA_DIVES = [
    dict(species='Forretress', league='great', shadow=False,
         slug='forretress-bug-bite-great-league',
         extra_args=['--fast', 'BUG_BITE', '--charged', 'SAND_TOMB,ROCK_TOMB'],
         reference='BUG_BITE,SAND_TOMB,ROCK_TOMB'),
    dict(species='Forretress', league='great', shadow=True,
         slug='forretress-shadow-bug-bite-great-league',
         extra_args=['--fast', 'BUG_BITE', '--charged', 'SAND_TOMB,ROCK_TOMB'],
         reference='BUG_BITE,SAND_TOMB,ROCK_TOMB'),
]

# Editorial per-dive settings, keyed by slug. Anything absent is derived.
#   extra_args    -- pin a specific moveset (form splits, off-meta builds)
#   reference     -- the comparison line on the page
#   policy        -- 'both' renders pvpoke AND pogodives strategy tiers
#   (top_movesets is deliberately NOT an override key: every dive renders
#    the same DEFAULT_TOP_MOVESETS, see the moveset rules below)
#   thresholds    -- True where hand-authored thresholds/*.toml apply; the old
#                    literal spelled this as no_thresholds=True on 90 of 95
#                    entries, i.e. thresholds are the EXCEPTION, not the rule
DIVE_OVERRIDES = {'aegislash-blade-great-league': {'extra_args': ['--fast',
                                                 'PSYCHO_CUT',
                                                 '--charged',
                                                 'SHADOW_BALL,GYRO_BALL'],
                                  'reference': 'PSYCHO_CUT,SHADOW_BALL,GYRO_BALL'},
 'aegislash-shield-great-league': {'extra_args': ['--fast',
                                                  'AEGISLASH_CHARGE_PSYCHO_CUT',
                                                  '--charged',
                                                  'SHADOW_BALL,GYRO_BALL'],
                                   'reference': 'AEGISLASH_CHARGE_PSYCHO_CUT,SHADOW_BALL,GYRO_BALL'},
 'cradily-great-league': {'extra_args': ['--fast',
                                         'ACID',
                                         '--charged',
                                         'GRASS_KNOT,ROCK_TOMB'],
                          'reference': 'ACID,GRASS_KNOT,ROCK_TOMB'},
 'cramorant-great-league': {'policy': 'both'},
 'cramorant-ultra-league': {'policy': 'both'},
 'dewgong-great-league': {'thresholds': True},
 'fearow-great-league': {'reference': 'PECK,DRILL_PECK,DRILL_RUN'},
 'forretress-shadow-volt-switch-great-league': {'extra_args': ['--fast',
                                                               'VOLT_SWITCH',
                                                               '--charged',
                                                               'SAND_TOMB,ROCK_TOMB'],
                                                'reference': 'VOLT_SWITCH,SAND_TOMB,ROCK_TOMB'},
 'forretress-volt-switch-great-league': {'extra_args': ['--fast',
                                                        'VOLT_SWITCH',
                                                        '--charged',
                                                        'SAND_TOMB,ROCK_TOMB'],
                                         'reference': 'VOLT_SWITCH,SAND_TOMB,ROCK_TOMB'},
 'mimikyu-busted-great-league': {'extra_args': ['--fast',
                                                'SHADOW_CLAW',
                                                '--charged',
                                                'SHADOW_SNEAK,PLAY_ROUGH'],
                                 'reference': 'SHADOW_CLAW,SHADOW_SNEAK,PLAY_ROUGH'},
 'mimikyu-busted-ultra-league': {'extra_args': ['--fast',
                                                'SHADOW_CLAW',
                                                '--charged',
                                                'SHADOW_SNEAK,PLAY_ROUGH'],
                                 'reference': 'SHADOW_CLAW,SHADOW_SNEAK,PLAY_ROUGH'},
 'oinkologne-female-great-league': {'reference': 'MUD_SLAP,BODY_SLAM,TRAILBLAZE',
                                    'thresholds': True},
 'shadow-sableye-great-league': {'reference': 'SHADOW_CLAW,DRAIN_PUNCH,FOUL_PLAY'},
 'stunfisk-great-league': {'thresholds': True},
 'thievul-great-league': {'reference': 'SUCKER_PUNCH,NIGHT_SLASH,PLAY_ROUGH',
                          'thresholds': True},
 'tinkaton-great-league': {'thresholds': True}}


# Rule 1: one moveset count for every dive (deep_dive.py's own default is 5;
# named here so the chain and the tests read one number).
DEFAULT_TOP_MOVESETS = 5


def _pin(dive, flag):
    """Value of a pinned ``--fast`` / ``--charged`` in a dive's extra_args."""
    args = dive.get('extra_args') or []
    return args[args.index(flag) + 1] if flag in args else None


def pair_partner(dive, dives):
    """The shadow/plain sibling of ``dive`` in ``dives``, or None (rule 3).

    Same species and league, opposite shadow flag, and compatible fast-move
    pins: equal, or at most one side pinned. Cup dives never pair (their
    pools are cup-specific). Exactly one partner is expected; more than one
    is a registry error, not a choice to make silently.
    """
    if dive.get('cup'):
        return None
    my_fast = _pin(dive, '--fast')
    hits = []
    for other in dives:
        if other is dive or other.get('cup'):
            continue
        if (other['species'], other['league']) != (dive['species'], dive['league']):
            continue
        if bool(other.get('shadow')) == bool(dive.get('shadow')):
            continue
        their_fast = _pin(other, '--fast')
        if my_fast and their_fast and my_fast != their_fast:
            continue
        hits.append(other)
    if len(hits) > 1:
        raise ValueError(f"{dive['slug']}: {len(hits)} pair partners "
                         f"({[h['slug'] for h in hits]}); pins must disambiguate")
    return hits[0] if hits else None


def _pool_path(league):
    return DEFAULT_OPPONENTS[league]


def read_pool(league):
    """Species names from the league's opponent pool, in file order."""
    out = []
    with open(os.path.join(REPO_ROOT, _pool_path(league))) as fh:
        for raw in fh:
            entry = raw.split('#')[0].strip()
            if entry:
                out.append(entry.split('|')[0].strip())
    return out


def derive_dives(league):
    """Build the dive list for a league from its opponent pool.

    ONE dive per species, not per pool LINE. A species can appear on several
    lines with different inline movesets -- both Thievul variants are in the
    GL pool as separate OPPONENTS -- but that is a statement about who a dive
    faces, not about how many pages the species gets. Without the dedupe those
    lines mint two dives with the same slug.
    """
    dives = []
    seen_slugs = set()
    for name in read_pool(league):
        shadow = '(Shadow)' in name
        species = name.replace('(Shadow)', '').strip()
        key = (species, league, shadow)
        slug = SLUG_EXCEPTIONS.get(key) or dive_slug(species, league, shadow)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        d = dict(species=species, league=league, slug=slug,
                 html_base=HTML_BASE, opponents_file=_pool_path(league))
        if shadow:
            d['shadow'] = True
        ovr = dict(DIVE_OVERRIDES.get(slug, {}))
        thresholds = ovr.pop('thresholds', False)
        d['no_thresholds'] = not thresholds
        d.update(ovr)
        dives.append(d)
    for extra in EXTRA_DIVES:
        if extra['league'] != league:
            continue
        d = dict(species=extra['species'], league=league, slug=extra['slug'],
                 html_base=HTML_BASE, opponents_file=_pool_path(league))
        if extra.get('shadow'):
            d['shadow'] = True
        d['no_thresholds'] = True
        for f in ('extra_args', 'reference', 'policy'):
            if extra.get(f) is not None:
                d[f] = extra[f]
        dives.append(d)
    return dives


def all_dives():
    return derive_dives('great') + derive_dives('ultra')
