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

NOT WIRED IN YET. run_website_dives.DIVES is still the live list; this module
is built alongside it so the two can be diffed before the swap.
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
         reference='BUG_BITE,SAND_TOMB,ROCK_TOMB', top_movesets=1),
    dict(species='Forretress', league='great', shadow=True,
         slug='forretress-shadow-bug-bite-great-league',
         extra_args=['--fast', 'BUG_BITE', '--charged', 'SAND_TOMB,ROCK_TOMB'],
         reference='BUG_BITE,SAND_TOMB,ROCK_TOMB', top_movesets=1),
]

# Editorial per-dive settings, keyed by slug. Anything absent is derived.
#   extra_args    -- pin a specific moveset (form splits, off-meta builds)
#   reference     -- the comparison line on the page
#   policy        -- 'both' renders pvpoke AND pogodives strategy tiers
#   top_movesets  -- how many movesets to render (default 5)
#   thresholds    -- True where hand-authored thresholds/*.toml apply; the old
#                    literal spelled this as no_thresholds=True on 90 of 95
#                    entries, i.e. thresholds are the EXCEPTION, not the rule
DIVE_OVERRIDES = {'aegislash-blade-great-league': {'extra_args': ['--fast',
                                                 'PSYCHO_CUT',
                                                 '--charged',
                                                 'SHADOW_BALL,GYRO_BALL'],
                                  'reference': 'PSYCHO_CUT,SHADOW_BALL,GYRO_BALL',
                                  'top_movesets': 5},
 'aegislash-shield-great-league': {'extra_args': ['--fast',
                                                  'AEGISLASH_CHARGE_PSYCHO_CUT',
                                                  '--charged',
                                                  'SHADOW_BALL,GYRO_BALL'],
                                   'reference': 'AEGISLASH_CHARGE_PSYCHO_CUT,SHADOW_BALL,GYRO_BALL',
                                   'top_movesets': 1},
 'altaria-great-league': {'top_movesets': 1},
 'azumarill-great-league': {'top_movesets': 1},
 'corviknight-great-league': {'top_movesets': 1},
 'cradily-great-league': {'extra_args': ['--fast',
                                         'ACID',
                                         '--charged',
                                         'GRASS_KNOT,ROCK_TOMB'],
                          'reference': 'ACID,GRASS_KNOT,ROCK_TOMB',
                          'top_movesets': 1},
 'cramorant-great-league': {'policy': 'both'},
 'cramorant-ultra-league': {'policy': 'both'},
 'dewgong-great-league': {'thresholds': True, 'top_movesets': 3},
 'empoleon-great-league': {'top_movesets': 1},
 'fearow-great-league': {'reference': 'PECK,DRILL_PECK,DRILL_RUN'},
 'feraligatr-great-league': {'top_movesets': 1},
 'forretress-shadow-volt-switch-great-league': {'extra_args': ['--fast',
                                                               'VOLT_SWITCH',
                                                               '--charged',
                                                               'SAND_TOMB,ROCK_TOMB'],
                                                'reference': 'VOLT_SWITCH,SAND_TOMB,ROCK_TOMB',
                                                'top_movesets': 1},
 'forretress-volt-switch-great-league': {'extra_args': ['--fast',
                                                        'VOLT_SWITCH',
                                                        '--charged',
                                                        'SAND_TOMB,ROCK_TOMB'],
                                         'reference': 'VOLT_SWITCH,SAND_TOMB,ROCK_TOMB',
                                         'top_movesets': 1},
 'galarian-corsola-great-league': {'top_movesets': 1},
 'galarian-moltres-ultra-league': {'top_movesets': 1},
 'galarian-stunfisk-great-league': {'top_movesets': 1},
 'grumpig-great-league': {'top_movesets': 1},
 'jumpluff-great-league': {'top_movesets': 1},
 'kingdra-great-league': {'top_movesets': 1},
 'lickilicky-great-league': {'top_movesets': 1},
 'lickilicky-ultra-league': {'top_movesets': 1},
 'medicham-great-league': {'top_movesets': 1},
 'melmetal-great-league': {'top_movesets': 4},
 'melmetal-ultra-league': {'top_movesets': 4},
 'mimikyu-busted-great-league': {'extra_args': ['--fast',
                                                'SHADOW_CLAW',
                                                '--charged',
                                                'SHADOW_SNEAK,PLAY_ROUGH'],
                                 'reference': 'SHADOW_CLAW,SHADOW_SNEAK,PLAY_ROUGH',
                                 'top_movesets': 1},
 'mimikyu-busted-ultra-league': {'extra_args': ['--fast',
                                                'SHADOW_CLAW',
                                                '--charged',
                                                'SHADOW_SNEAK,PLAY_ROUGH'],
                                 'reference': 'SHADOW_CLAW,SHADOW_SNEAK,PLAY_ROUGH',
                                 'top_movesets': 1},
 'mimikyu-great-league': {'top_movesets': 1},
 'mimikyu-ultra-league': {'top_movesets': 1},
 'ninetales-great-league': {'top_movesets': 1},
 'oinkologne-female-great-league': {'reference': 'MUD_SLAP,BODY_SLAM,TRAILBLAZE',
                                    'thresholds': True},
 'sableye-great-league': {'top_movesets': 1},
 'seismitoad-great-league': {'top_movesets': 1},
 'shadow-altaria-great-league': {'top_movesets': 1},
 'shadow-corviknight-great-league': {'top_movesets': 1},
 'shadow-empoleon-great-league': {'top_movesets': 1},
 'shadow-feraligatr-great-league': {'top_movesets': 1},
 'shadow-jumpluff-great-league': {'top_movesets': 1},
 'shadow-kingdra-great-league': {'top_movesets': 1},
 'shadow-ninetales-great-league': {'top_movesets': 1},
 'shadow-sableye-great-league': {'extra_args': ['--fast',
                                                'SHADOW_CLAW',
                                                '--charged',
                                                'FOUL_PLAY'],
                                 'reference': 'SHADOW_CLAW,DRAIN_PUNCH,FOUL_PLAY',
                                 'top_movesets': 4},
 'shadow-sealeo-great-league': {'top_movesets': 1},
 'stunfisk-great-league': {'thresholds': True, 'top_movesets': 3},
 'talonflame-great-league': {'top_movesets': 1},
 'thievul-great-league': {'reference': 'SUCKER_PUNCH,NIGHT_SLASH,PLAY_ROUGH',
                          'thresholds': True,
                          'top_movesets': 6},
 'tinkaton-great-league': {'thresholds': True},
 'zygarde-complete-ultra-league': {'top_movesets': 1}}


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
    """Build the dive list for a league from its opponent pool."""
    dives = []
    for name in read_pool(league):
        shadow = '(Shadow)' in name
        species = name.replace('(Shadow)', '').strip()
        key = (species, league, shadow)
        slug = SLUG_EXCEPTIONS.get(key) or dive_slug(species, league, shadow)
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
        for f in ('extra_args', 'reference', 'top_movesets', 'policy'):
            if extra.get(f) is not None:
                d[f] = extra[f]
        dives.append(d)
    return dives


def all_dives():
    return derive_dives('great') + derive_dives('ultra')
