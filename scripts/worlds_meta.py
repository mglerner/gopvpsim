#!/usr/bin/env python3
"""
Generate ``worlds/meta.toml`` -- the Worlds 2026 robustness-analysis meta.

Plan of record: ``docs/worlds_prep_plan.md`` (decided 2026-08-10). The
entry LIST is a human decision and lives here as a literal (``META``):
speciesId-resolvable display name, shadow flag, badge, and for the FORCED
entries their provenance reason. Everything AROUND that decision is
COMPUTED and refreshable:

* usage stats from ``docs/tournament_data/cs_2026_*.json`` (Dracoviz), team
  level, open-GL events only (EUIC/LAIC/NAIC are limited metas -- see that
  directory's README), recent bucket = event date >= ``RECENT_CUTOFF``;
* per-variant modal movesets (shadow and non-shadow counted SEPARATELY --
  pooling hid that the field runs Bug Bite Shadow Forretress while PvPoke
  defaults Volt Switch), falling back to ``get_default_moveset`` when the
  modal is weak;
* current PvPoke open-GL rank via a duplicate-aware resolver.

Usage::

    python scripts/worlds_meta.py            # regenerate worlds/meta.toml
    python scripts/worlds_meta.py --check    # exit 1 if the file is stale

The generator is idempotent: re-running with unchanged inputs rewrites a
byte-identical file (the ``generated`` stamp is carried over when nothing
else moved), so ``--check`` is a clean drift gate.

NOTE ON USAGE SHARES: every share here is PER-VARIANT (Shadow Altaria is
not Altaria), because the meta table itself splits variants into separate
entries and a per-variant share is the only self-consistent choice. The
plan doc's table quotes a POOLED (shadow-agnostic) share for several
non-shadow rows -- Altaria 24.4, Empoleon 26.6, Feraligatr 19.3, Ninetales
3.9, Diggersby 8.3, Grumpig 7.3 -- while quoting per-variant for others
(Quagsire 7.5, Forretress 15.9). ``usage_recent_pooled_pct`` is emitted
alongside so both readings are visible and neither is silently wrong.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import glob
import json
import os
import re
import sys
from typing import NamedTuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'src'))

from gopvpsim.data import (get_default_moveset, load_gamemaster,  # noqa: E402
                           load_rankings)

OUT_PATH = os.path.join(REPO, 'worlds', 'meta.toml')
TOURNAMENT_GLOB = os.path.join(REPO, 'docs', 'tournament_data', 'cs_2026_*.json')

# --- Usage-corpus conventions (docs/tournament_data/README.md) --------------

# The three Internationals ran LIMITED metas; their rosters answer a
# different question and are excluded from every open-meta statistic.
LIMITED_META_EVENTS = frozenset({'euic', 'laic', 'naic'})

# Event date is decoded from the MongoDB ``_id`` timestamps (all records in
# a dump share one creation date, shortly after the event weekend).
# Buenos Aires is the documented exception: a late backfill of a September
# 2025 event uploaded 2026-06-09, so its decoded date is not its event date.
EVENT_DATE_OVERRIDES = {'buenos_aires': '2025-09'}

RECENT_CUTOFF = '2026-03'   # "recent" bucket = event date >= this (YYYY-MM)
TOP_CUT_RANK = 8            # top-cut bucket = final_rank <= this

# --- Moveset rule (plan: "per-variant modal when modal% >= 60") -------------

MODAL_MIN_PCT = 60.0
MODAL_MIN_N = 20

# --- Badge rule (plan: "Badges: PLAYED = ...") ------------------------------

BADGE_USAGE_TOP = 25    # "top-25 recent usage"
BADGE_RANK_TOP = 30     # "top-30 current rank"

REJECT_TOP_N = 55       # the candidate page shows the usage top-55

# --- Dracoviz name normalization (build_opponent_pool.py) -------------------

# Dracoviz encodes regional/form variants as "[<name> [<form> Form]]" or
# "[<name> [<form> Forme]]"; a minority of rows carry the BARE inner form
# ("Galarian Form", "Alolan Form") with no brackets. Both must be handled --
# dropping the bare rows costs Corsola (Galarian) ~0.8pp of recent usage.
_FORM_RE = re.compile(r'^\[[^[]+\[(.+?) (?:Form|Forme)\]\]$')
_BARE_FORM_RE = re.compile(r'^(.+?) (?:Form|Forme)$')

# Species where Dracoviz drops the form distinction but PvPoke treats forms
# as separate entries; default to the GL-competitive pick.
_FORM_DEFAULTS = {
    'Gourgeist':  'Super',     # Super is the GL meta size
    'Aegislash':  'Shield',    # GL registers in Shield form
}


# ---------------------------------------------------------------------------
# THE HUMAN DECISION: the entries, their badges, and forced provenance.
# Order is the plan table's order (docs/worlds_prep_plan.md "The meta").
# Fields: (species display name, shadow, badge, forced provenance or None)
# plus an OPTIONAL 5th element, a MovesetFork, for the rows that enter the
# meta twice on the same species with different charged moves. Rows without
# a fork stay 4-tuples so the 31 original decisions are untouched.
# ---------------------------------------------------------------------------


class MovesetFork(NamedTuple):
    """One arm of a same-species moveset fork.

    Shadow variants already split one species into two entries, and the
    schema handles that with a real gamemaster speciesId per variant
    (``quagsire`` / ``quagsire_shadow``). A MOVESET fork has no such
    speciesId, so:

    * ``species_id`` is an explicit, made-up identity. It is the entry's
      key EVERYWHERE downstream -- plane filenames, manifest pair keys,
      cheat-sheet filenames -- so it must never change once baked (a
      changed/removed species_id fails worlds_planes.meta_delta and
      forces a full re-bake). That is why the Night Slash arm keeps the
      bare ``thievul`` it was first baked under rather than gaining a
      tidier symmetric suffix.
    * ``gamemaster_name`` is therefore emitted alongside, because
      ``name`` is no longer a gamemaster-resolvable species name and the
      bake's legality preflight needs the real one.
    * both arms are real, distinct entries, so every pair between them
      and the rest of the meta is baked -- INCLUDING the cross-arm pair.
      Only the true self-mirror (an entry against itself) is excluded,
      which itertools.combinations already does by identity.

    ``label`` is the display suffix; it must name this arm's own fork
    axis, because the arms share the rest of the moveset and a label
    like "Thievul" vs "Thievul (Play Rough)" would read as "the real one
    and a footnote".
    """
    label: str
    species_id: str
    fast_move_id: str
    charged_move_ids: tuple

AEGISLASH_REASON = (
    'Editorial include. Ships as aegislash_shield -- the real, '
    'battle-reachable Aegislash (starts Shield, transforms to Blade on its '
    'first charged move); the site\'s separate "Starts Blade" dive is an '
    'unreachable diagnostic hypothetical and is NOT this entry. The '
    'arithmetic-hostile entry: the form change disables signature dedup, '
    'and Blade attack is non-monotone in the Shield attack IV, so it is '
    'budgeted as the expensive pair-family and footnoted out of the '
    'closed-form pages.'
)

THIEVUL_REASON = (
    'post-CD editorial include (Michael, 2026-08-18): Icy Wind Thievul is '
    'Worlds-legal (CD 08-16 precedes Worlds; not on the Play! banned list); '
    'PvPoke GL rank ~41; no tournament footprint yet. '
    # The corpus figure is appended so the reason cannot read as
    # contradicting the usage column beside it (never-present-known-wrong):
    # "no footprint" means no MEANINGFUL one, and the corpus says exactly
    # how little there is -- all of it pre-CD, i.e. a different Pokemon
    # competitively (Night Slash / Play Rough, PvPoke GL rank 122).
    'Exact corpus figures: 1 of 1,801 recent open-GL teams (0.06%), 6 of '
    '3,649 across the whole corpus, 0 of 128 top-cut teams -- and every '
    'one of those predates the Community Day, when Thievul had no Icy '
    'Wind and sat at PvPoke GL rank 122.'
)

# The fork rationale, shared by both arms (Michael, 2026-08-18). It is a
# refusal to take a side, not a recommendation: the two arms genuinely win
# on different axes, and which one is better is IV-CONDITIONAL, so a single
# row would silently pick for the reader.
THIEVUL_FORK_REASON = (
    ' Thievul enters the matrix as TWO builds, not one. Both run Sucker '
    'Punch + Icy Wind and fork only on the second charged move: Night Slash '
    "(PvPoke's post-CD default) or Play Rough (the build the Community Day "
    'dive landed on). The choice is genuinely contested, so shipping one '
    'row would take a side; both are baked as full entries and every pair '
    'between them and the rest of the meta -- including the pair BETWEEN '
    'the two arms -- is simmed. Full Night-Slash-vs-Play-Rough treatment: '
    'thievul-lickilicky-robustness.html.'
    # Each claim below is scoped to the metric and pool that produced it.
    # An unscoped "Night Slash is better for top-stat-product spreads"
    # reads as meta-wide and is contradicted by the two rows beside it;
    # scoped to Lickilicky it is exactly right, and this matrix reproduces
    # the deep analysis's own number for it (verified 2026-08-18).
    ' Which arm is better depends on the METRIC and the MATCHUP, so this '
    'page states its own convention rather than a verdict. On the '
    "matrix's win-count convention -- summed over all 9 shield scenarios "
    'and the 31 shared opponents, 279 cells per slice -- Icy Wind + Play '
    'Rough leads on BOTH probe spreads: 167.30 vs 157.85 at the rank-1 '
    'stat-product spread and 158.56 vs 149.48 at the max-attack spread '
    '(top-512 cohort, baiting on). Night Slash\'s case rests on three '
    'things this count does not capture. (1) BAIT-ROBUSTNESS, which the '
    'planes here confirm directly: switching the focal side to no-bait '
    'moves Icy Wind + Play Rough by 8.11 and Night Slash by 0.72, so '
    'nearly all of Play Rough\'s margin is bait-dependent. (2) BATTLE '
    'RATING rather than win count -- on PvPoke\'s rating metric, and at '
    '2-2, Night Slash led on the deep analysis\'s 88-Pokemon pool. (3) '
    'The LICKILICKY matchup specifically, for high-stat-product spreads: '
    'at 1-1 against the top-512 Lickilicky cohort, the rank-1 Thievul '
    'spread beats 512 of 512 with Night Slash and 373 of 512 (72.9%) '
    'with Play Rough -- our planes reproduce the deep analysis\'s figure '
    'exactly -- while the SAME matchup flips the other way on the '
    'max-attack spread (83 of 512 vs 512 of 512), which is what "IV-'
    'conditional" means here. The 88-pool win-count and battle-rating '
    'numbers come from the linked analysis, not from this matrix; the '
    'per-scenario grids below are what this page measures.'
)

THIEVUL_NS_FORK = MovesetFork(
    label='NS+IW', species_id='thievul',
    fast_move_id='SUCKER_PUNCH',
    charged_move_ids=('ICY_WIND', 'NIGHT_SLASH'))

THIEVUL_PR_FORK = MovesetFork(
    label='IW+PR', species_id='thievul_iw_pr',
    fast_move_id='SUCKER_PUNCH',
    charged_move_ids=('ICY_WIND', 'PLAY_ROUGH'))

MANTINE_REASON = (
    'Editorial include (added 2026-08-10 at Michael\'s request). '
    'DragapultSim named it a top Worlds threat alongside Tinkaton. It earns '
    'no badge on our axes -- open-GL rank 53, 0.61% recent open-GL usage '
    '(11/1,801 teams) -- but it was a real pick at NAIC (7.25%, 24/331 '
    'teams, in a Mantine-friendly limited meta; NAIC cup rank 5), the likely '
    'context for the callout. Tinkaton-vs-Mantine is the designated amber '
    'validation pair '
    '(x.com/DragapultSim/status/2083251310996939262).'
)

META = [
    ('Lickilicky',         False, 'PLAYED',  None),
    ('Quagsire',           True,  'PLAYED',  None),
    ('Quagsire',           False, 'PLAYED',  None),
    ('Forretress',         True,  'PLAYED',  None),
    ('Forretress',         False, 'PLAYED',  None),
    ('Wigglytuff',         False, 'PLAYED*', None),
    ('Corviknight',        False, 'PLAYED',  None),
    ('Empoleon',           False, 'PLAYED',  None),
    ('Altaria',            False, 'PLAYED',  None),
    ('Feraligatr',         False, 'PLAYED',  None),
    ('Stunfisk',           False, 'PLAYED*', None),
    ('Corsola (Galarian)', False, 'PLAYED',  None),
    ('Azumarill',          False, 'PLAYED',  None),
    ('Medicham',           False, 'PLAYED*', None),
    ('Tinkaton',           False, 'PLAYED',  None),
    ('Guzzlord',           False, 'PLAYED',  None),
    ('Gourgeist (Super)',  False, 'PLAYED*', None),
    ('Togekiss',           False, 'PLAYED*', None),
    ('Aegislash (Shield)', False, 'FORCED',  AEGISLASH_REASON),
    ('Ninetales',          False, 'MODEL',   None),
    ('Jumpluff',           False, 'MODEL',   None),
    ('Fearow',             False, 'MODEL',   None),
    ('Kingdra',            False, 'MODEL',   None),
    ('Sableye',            True,  'MODEL',   None),
    ('Jellicent',          False, 'PLAYED',  None),
    ('Clodsire',           False, 'PLAYED',  None),
    ('Furret',             False, 'PLAYED',  None),
    ('Altaria',            True,  'PLAYED',  None),
    ('Grumpig',            False, 'PLAYED*', None),
    ('Diggersby',          False, 'PLAYED*', None),
    ('Mantine',            False, 'FORCED',  MANTINE_REASON),
    ('Thievul',            False, 'FORCED',  THIEVUL_REASON + THIEVUL_FORK_REASON,
     THIEVUL_NS_FORK),
    ('Thievul',            False, 'FORCED',  THIEVUL_REASON + THIEVUL_FORK_REASON,
     THIEVUL_PR_FORK),
]

# --- Community-Day move injection (the meta.toml half) ----------------------
#
# Move ids an entry is allowed to run even though the PINNED sim gamemaster
# (8f1d6cca5c0f, pvpoke f60a41199) does not list them in that species' legal
# pool. This mirrors the `[Species.cd_prep]` table in thresholds/*.toml and
# obeys CLAUDE.md's rule for it: NEVER infer "the CD move is the one missing
# from the pool" -- prove the gamemaster lags with eliteMoves + the pvpoke
# commit history before adding a row here.
#
# Thievul / ICY_WIND, proven 2026-08-14 and re-verified 2026-08-18
# (docs/thievul_cd_plan.md): our pinned gamemaster gives Thievul
# chargedMoves = [NIGHT_SLASH, PLAY_ROUGH] and NO eliteMoves, while upstream
# pvpoke commit f754cd6fc ("Icy Wind Thievul", 2026-08-14) adds ICY_WIND to
# BOTH chargedMoves and eliteMoves, and the refreshed rankings default
# Thievul to Sucker Punch / Night Slash + Icy Wind (GL rank ~41). So the
# injected pool is exactly current pvpoke's pool: the lag is real and the
# injection is vintage-equivalent, not a guess. Retire this table once the
# un-pinned gamemaster stably lists the move.
#
# Keyed by species_id (not display name) so a moveset fork's arms each
# declare their own injection explicitly.
INJECTED_MOVES = {
    'thievul': ['ICY_WIND'],
    'thievul_iw_pr': ['ICY_WIND'],
}

_ICY_WIND_NOTE = (
    'Icy Wind injected: the pinned sim gamemaster predates the Community '
    'Day. We sim on pvpoke f60a41199 (gamemaster 8f1d6cca5c0f), the '
    'pre-Worlds vintage every other number on this site was baked at, and '
    'it still lists Thievul without Icy Wind. Upstream pvpoke added Icy '
    'Wind to Thievul as an elite charged move on 2026-08-14 (commit '
    'f754cd6fc), so the injected move pool matches current pvpoke exactly '
    '-- but the move data itself comes from the pinned gamemaster, where '
    'Icy Wind already exists (other species learn it). Nothing else about '
    'Thievul is injected: Sucker Punch, Night Slash and Play Rough are all '
    "in Thievul's pinned legal pool."
)

INJECTION_NOTES = {
    'thievul': _ICY_WIND_NOTE,
    'thievul_iw_pr': _ICY_WIND_NOTE,
}

# Reasons for the named runner-ups (plan: "Runner-ups that stay OUT but
# render as rejects on the candidate page"). Everything else in the usage
# top-55 that is not in META gets 'below cut'.
REJECT_REASONS = {
    'Cradily':            'runner-up: biggest old->recent faller',
    'Talonflame':         'runner-up: stays out',
    'Annihilape':         'runner-up: stays out, current rank 146',
    'Lapras':             'runner-up: stays out, 0% of top cuts',
    'Moltres (Galarian)': 'runner-up: stays out',
}

BANNED_REASON = (
    'Banned at Worlds: Play! Pokemon banned list, and Niantic states it is '
    'not eligible for the Competitors Cup (it only functions under the new '
    'turn system). PvPoke\'s open-GL #1, shown explicitly rather than '
    'silently omitted. Corpus sanity check: 0 Mimikyu in 21,719 roster '
    'entries across 36 captured events.'
)

# Both ban citations re-verified by direct fetch 2026-08-10: the Play!
# banned list names Mimikyu first; the Niantic post states Competitors Cup
# (the Worlds format) uses the current [old] battle system, where Mimikyu
# is not eligible.
BANNED_CITATIONS = [
    'https://pokemongo.com/news/pvp-updates-competitors-cup-2026',
    'https://www.pokemon.com/us/play-pokemon/about/'
    'play-pokemon-pokemon-go-championship-series-banned-pokemon-list',
]


# ---------------------------------------------------------------------------
# Usage corpus
# ---------------------------------------------------------------------------

def dracoviz_display_name(mon, *, pooled=False):
    """Normalize a Dracoviz roster entry to a PvPoke speciesName.

    ``pooled=True`` drops the Shadow distinction, giving the base-species
    (shadow-agnostic) name used for the pooled usage share.
    """
    name = mon['name']
    form = mon.get('form', '')
    base = name
    if form:
        m = _FORM_RE.match(form) or _BARE_FORM_RE.match(form)
        if m:
            base = f'{name} ({m.group(1)})'
    elif name in _FORM_DEFAULTS:
        base = f'{name} ({_FORM_DEFAULTS[name]})'
    if mon.get('shadow', False) and not pooled:
        base = f'{base} (Shadow)'
    return base


def _event_month(slug, records):
    """YYYY-MM event month for a dump, honoring the documented overrides."""
    if slug in EVENT_DATE_OVERRIDES:
        return EVENT_DATE_OVERRIDES[slug]
    stamps = [int(r['_id'][:8], 16) for r in records if '_id' in r]
    dt = datetime.datetime.fromtimestamp(min(stamps), datetime.UTC)
    return dt.strftime('%Y-%m')


def load_events():
    """Load the open-GL Dracoviz dumps as ``[(slug, month, records), ...]``."""
    events = []
    for path in sorted(glob.glob(TOURNAMENT_GLOB)):
        slug = os.path.basename(path)[len('cs_2026_'):-len('.json')]
        if slug in LIMITED_META_EVENTS:
            continue
        with open(path) as f:
            records = json.load(f)
        events.append((slug, _event_month(slug, records), records))
    return events


def _bucket_shares(events, *, rank_cutoff=None, pooled=False):
    """Team-level appearance counts over a bucket: ``(n_teams, Counter)``.

    A team contributes at most 1 to each name it carries (team-level share,
    not entry-level). Records with no roster are not teams (Melbourne/Lima
    each carry two such rows) and never reach the denominator.
    """
    teams = 0
    counts = collections.Counter()
    for _slug, _month, records in events:
        for rec in records:
            roster = rec.get('roster') or []
            if not roster:
                continue
            if rank_cutoff is not None and rec.get('final_rank', 10 ** 9) > rank_cutoff:
                continue
            teams += 1
            for name in {dracoviz_display_name(m, pooled=pooled) for m in roster}:
                counts[name] += 1
    return teams, counts


def _modal_movesets(events):
    """Per-variant moveset counters over the recent bucket.

    Key: ``(fast, (charge_a, charge_b))`` with the charge pair sorted and
    Dracoviz's trailing ``*`` (legacy/Elite-TM marker) stripped. Counted at
    the ENTRY level -- the question is "what moveset does a field copy of
    this mon run", not "how many teams ran one".
    """
    out = collections.defaultdict(collections.Counter)
    for _slug, _month, records in events:
        for rec in records:
            for mon in (rec.get('roster') or []):
                name = dracoviz_display_name(mon)
                fast = _clean_move(mon.get('fast'))
                pair = tuple(sorted((_clean_move(mon.get('charge1')),
                                     _clean_move(mon.get('charge2')))))
                out[name][(fast, pair)] += 1
    return out


def _clean_move(name):
    """Strip Dracoviz's trailing legacy marker and bracket-form notation."""
    name = (name or '').strip()
    if name.endswith('*'):
        name = name[:-1].strip()
    # Dracoviz writes "Weather Ball [Fire]"; the gamemaster writes
    # "Weather Ball (Fire)".
    return name.replace('[', '(').replace(']', ')')


class Usage:
    """The computed usage picture: buckets, shares, ranks, modal movesets."""

    def __init__(self, events):
        self.events = events
        self.recent = [e for e in events if e[1] >= RECENT_CUTOFF]
        self.old = [e for e in events if e[1] < RECENT_CUTOFF]
        self.teams_recent, self._recent = _bucket_shares(self.recent)
        self.teams_all, self._all = _bucket_shares(events)
        self.teams_old, self._old = _bucket_shares(self.old)
        self.teams_topcut, self._topcut = _bucket_shares(
            self.recent, rank_cutoff=TOP_CUT_RANK)
        _, self._recent_pooled = _bucket_shares(self.recent, pooled=True)
        self.movesets = _modal_movesets(self.recent)
        self.order = [n for n, _ in sorted(self._recent.items(),
                                           key=lambda kv: (-kv[1], kv[0]))]
        self.rank = {n: i + 1 for i, n in enumerate(self.order)}

    @staticmethod
    def _pct(counts, name, total):
        return round(100.0 * counts.get(name, 0) / total, 2) if total else 0.0

    def recent_pct(self, name):
        return self._pct(self._recent, name, self.teams_recent)

    def recent_pooled_pct(self, name):
        return self._pct(self._recent_pooled, name, self.teams_recent)

    def all_pct(self, name):
        return self._pct(self._all, name, self.teams_all)

    def old_pct(self, name):
        return self._pct(self._old, name, self.teams_old)

    def topcut_pct(self, name):
        return self._pct(self._topcut, name, self.teams_topcut)

    def usage_rank(self, name):
        return self.rank.get(name, 0)


# ---------------------------------------------------------------------------
# Gamemaster / rankings resolution
# ---------------------------------------------------------------------------

class Resolver:
    """Duplicate-aware speciesName -> speciesId -> current-rank resolution.

    ``data.species_id`` builds a speciesName -> speciesId index with a plain
    dict comprehension, so a ``duplicate``-tagged twin that appears LATER in
    the gamemaster wins ("last wins"): 'Cradily' resolves to ``cradily_b``
    (rank 132) instead of ``cradily`` (rank 44), and 'Lanturn' to
    ``lanturnw``. Preferring untagged entries is the whole point of this
    class -- the meta table's ranks are wrong without it.
    """

    def __init__(self):
        gm = load_gamemaster()
        by_name = collections.defaultdict(list)
        for mon in gm['pokemon']:
            by_name[mon['speciesName']].append(mon)
        self._by_name = by_name
        self._by_id = {m['speciesId']: m for m in gm['pokemon']}
        self._rank = {e['speciesId']: i + 1
                      for i, e in enumerate(load_rankings('great'))}
        self.rankings_entries = len(self._rank)
        self._move_ids = collections.defaultdict(list)
        for mv in gm['moves']:
            self._move_ids[mv['name']].append(mv['moveId'])
        self._move_names = {mv['moveId']: mv['name'] for mv in gm['moves']}

    def entry(self, species_name):
        """Gamemaster entry for a display name, preferring non-duplicates."""
        candidates = self._by_name.get(species_name)
        if not candidates:
            return None
        preferred = [m for m in candidates
                     if 'duplicate' not in (m.get('tags') or [])]
        return (preferred or candidates)[0]

    def species_id(self, species_name):
        entry = self.entry(species_name)
        return entry['speciesId'] if entry else None

    def current_rank(self, species_name):
        """Current PvPoke open-GL rank, or 0 when the species is unranked."""
        sid = self.species_id(species_name)
        return self._rank.get(sid, 0)

    def legal_move_ids(self, species_name):
        entry = self.entry(species_name)
        if entry is None:
            return frozenset()
        ids = []
        for key in ('fastMoves', 'chargedMoves', 'eliteMoves'):
            ids.extend(entry.get(key) or [])
        return frozenset(ids)

    def move_id(self, display_name, species_name):
        """Map a move DISPLAY name to its gamemaster moveId. Hard-fails.

        Three gamemaster names are ambiguous -- 'Psycho Cut' and 'Air Slash'
        (the Aegislash form-specific AEGISLASH_CHARGE_* twins) and 'Aura
        Wheel' (Morpeko's two typings) -- so the species' legal move pool
        breaks the tie. Aegislash (Shield) therefore resolves 'Psycho Cut'
        to AEGISLASH_CHARGE_PSYCHO_CUT, which is the form-specific id the
        engine needs.
        """
        candidates = self._move_ids.get(display_name)
        if not candidates:
            raise SystemExit(
                f'error: move name {display_name!r} ({species_name}) has no '
                f'gamemaster match -- fix the normalization in _clean_move')
        if len(candidates) == 1:
            return candidates[0]
        legal = self.legal_move_ids(species_name)
        narrowed = [c for c in candidates if c in legal]
        if len(narrowed) == 1:
            return narrowed[0]
        raise SystemExit(
            f'error: move name {display_name!r} is ambiguous for '
            f'{species_name}: {candidates} (legal narrowing -> {narrowed})')

    def move_name(self, move_id):
        """Canonical display name for a moveId. Hard-fails on unknown ids."""
        try:
            return self._move_names[move_id]
        except KeyError:
            raise SystemExit(f'error: unknown moveId {move_id!r}') from None


# ---------------------------------------------------------------------------
# Badge rule
# ---------------------------------------------------------------------------

def classify_badge(usage_rank, current_rank):
    """The plan's badge definitions, as code.

    PLAYED  = top-25 recent usage AND top-30 current rank
    PLAYED* = top-25 recent usage, current rank sank below 30
    MODEL   = top-30 current rank, no meaningful tournament footprint
    ''      = neither axis (FORCED is editorial and never computed here)

    Ranks are 1-based; 0 means "unranked/unseen" and never counts as top-N.
    """
    played = 0 < usage_rank <= BADGE_USAGE_TOP
    modeled = 0 < current_rank <= BADGE_RANK_TOP
    if played:
        return 'PLAYED' if modeled else 'PLAYED*'
    return 'MODEL' if modeled else ''


# ---------------------------------------------------------------------------
# Moveset choice
# ---------------------------------------------------------------------------

def choose_moveset(display_name, species_name, shadow, usage, resolver):
    """Return the chosen moveset dict for one meta entry.

    Per-variant modal wins when it is both dominant (>= MODAL_MIN_PCT) and
    well-sampled (>= MODAL_MIN_N entries); otherwise PvPoke's default. The
    per-VARIANT split is load-bearing: pooling Shadow into non-Shadow hid
    that the field runs Bug Bite Shadow Forretress while PvPoke defaults
    Volt Switch.
    """
    counter = usage.movesets.get(display_name, collections.Counter())
    n = sum(counter.values())
    modal_pct = 0.0
    modal = None
    if n:
        (modal, count), = counter.most_common(1)
        modal_pct = round(100.0 * count / n, 1)

    default_fast, default_charged = get_default_moveset(
        species_name, 'great', shadow=shadow)
    default_ids = [default_fast] + sorted(default_charged)

    if modal is not None and modal_pct >= MODAL_MIN_PCT and n >= MODAL_MIN_N:
        source = 'modal'
        fast_id = resolver.move_id(modal[0], display_name)
        charged_ids = sorted(resolver.move_id(c, display_name)
                             for c in modal[1])
    else:
        source = 'default'
        fast_id = default_fast
        charged_ids = sorted(default_charged)

    chosen_ids = [fast_id] + charged_ids
    return {
        'fast_move_id': fast_id,
        'charged_move_ids': charged_ids,
        'fast_move': resolver.move_name(fast_id),
        'charged_moves': [resolver.move_name(m) for m in charged_ids],
        'moveset_source': source,
        'moveset_modal_pct': modal_pct,
        'moveset_n': n,
        'default_disagrees': chosen_ids != default_ids,
        'default_fast_move_id': default_fast,
        'default_charged_move_ids': sorted(default_charged),
    }


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def fork_moveset(fork, species_name, shadow, resolver):
    """choose_moveset's counterpart for a fork arm: the moveset is the
    human decision in the MovesetFork itself, not a corpus/default
    lookup. ``moveset_source`` still tells the truth about how it
    relates to PvPoke -- 'default' when this arm IS PvPoke's pick, so
    the arm that happens to match renders identically to a normal
    default row, and 'variant' when it deliberately diverges."""
    default_fast, default_charged = get_default_moveset(
        species_name, 'great', shadow=shadow)
    fast_id = fork.fast_move_id
    charged_ids = sorted(fork.charged_move_ids)
    is_default = (fast_id == default_fast
                  and charged_ids == sorted(default_charged))
    return {
        'fast_move_id': fast_id,
        'charged_move_ids': charged_ids,
        'fast_move': resolver.move_name(fast_id),
        'charged_moves': [resolver.move_name(m) for m in charged_ids],
        'moveset_source': 'default' if is_default else 'variant',
        'default_disagrees': not is_default,
        'default_fast_move_id': default_fast,
        'default_charged_move_ids': sorted(default_charged),
    }


def build_entries(usage, resolver):
    """The meta entries, in plan-table order."""
    entries = []
    for row_spec in META:
        species_name, shadow, badge, forced_reason = row_spec[:4]
        # 5th element is optional: only moveset-fork rows carry one.
        fork = row_spec[4] if len(row_spec) > 4 else None
        # gm_name is the gamemaster/corpus-resolvable species name; display
        # is what readers see. They differ ONLY for fork arms, so every
        # non-fork row resolves exactly as it always did.
        gm_name = f'{species_name} (Shadow)' if shadow else species_name
        display = f'{species_name} ({fork.label})' if fork else gm_name
        if resolver.species_id(gm_name) is None:
            raise SystemExit(f'error: {gm_name!r} is not in the gamemaster')
        sid = fork.species_id if fork else resolver.species_id(gm_name)
        # Usage and rank are SPECIES-level facts: the corpus and PvPoke's
        # rankings do not distinguish fork arms, so both arms show the same
        # figures rather than a fabricated split.
        usage_rank = usage.usage_rank(gm_name)
        current_rank = resolver.current_rank(gm_name)
        row = {
            'name': display,
            'species': species_name,
            'species_id': sid,
            'shadow': shadow,
            'badge': badge,
            'badge_rule': classify_badge(usage_rank, current_rank),
            'current_rank': current_rank,
            'usage_rank': usage_rank,
            'usage_recent_pct': usage.recent_pct(gm_name),
            'usage_recent_pooled_pct': usage.recent_pooled_pct(species_name),
            'usage_all_pct': usage.all_pct(gm_name),
            'usage_old_pct': usage.old_pct(gm_name),
            'usage_topcut_pct': usage.topcut_pct(gm_name),
        }
        if display != gm_name:
            row['gamemaster_name'] = gm_name
        if fork:
            row.update(fork_moveset(fork, species_name, shadow, resolver))
        else:
            row.update(choose_moveset(gm_name, species_name, shadow,
                                      usage, resolver))
        if forced_reason is not None:
            row['forced_reason'] = forced_reason
        injected = INJECTED_MOVES.get(sid)
        if injected:
            # A DEAD injection is a silent legality hole: it would widen
            # worlds_bake's preflight for a move the entry never runs. The
            # injected ids must (a) exist in the gamemaster moves db and
            # (b) actually appear in this entry's chosen moveset.
            chosen = {row['fast_move_id'], *row['charged_move_ids']}
            for mid in injected:
                resolver.move_name(mid)   # hard-fails on an unknown moveId
                if mid not in chosen:
                    raise SystemExit(
                        f'error: {display} declares injected move {mid!r} '
                        f'but its chosen moveset is {sorted(chosen)} -- a '
                        'dead injection must not ship (drop the '
                        'INJECTED_MOVES row or fix the moveset)')
            row['injected_move_ids'] = sorted(injected)
            row['injected_moves'] = [resolver.move_name(m)
                                     for m in sorted(injected)]
            row['injection_note'] = INJECTION_NOTES[sid]
        entries.append(row)
    ids = [e['species_id'] for e in entries]
    if len(set(ids)) != len(ids):
        raise SystemExit(f'error: duplicate species_id in META: '
                         f'{sorted({i for i in ids if ids.count(i) > 1})}')
    return entries


def build_rejects(usage, resolver, meta_names):
    """Usage top-55 rows that are NOT in the meta, plus the banned row."""
    rejects = []
    for name in usage.order[:REJECT_TOP_N]:
        if name in meta_names:
            continue
        rejects.append({
            'name': name,
            'species_id': resolver.species_id(name) or '',
            'banned': False,
            'usage_rank': usage.usage_rank(name),
            'current_rank': resolver.current_rank(name),
            'usage_recent_pct': usage.recent_pct(name),
            'usage_all_pct': usage.all_pct(name),
            'usage_old_pct': usage.old_pct(name),
            'usage_topcut_pct': usage.topcut_pct(name),
            'reason': REJECT_REASONS.get(name, 'below cut'),
        })

    banned = {
        'name': 'Mimikyu',
        'species_id': resolver.species_id('Mimikyu') or 'mimikyu',
        'banned': True,
        'usage_rank': usage.usage_rank('Mimikyu'),
        'current_rank': resolver.current_rank('Mimikyu'),
        'usage_recent_pct': usage.recent_pct('Mimikyu'),
        'usage_all_pct': usage.all_pct('Mimikyu'),
        'usage_old_pct': usage.old_pct('Mimikyu'),
        'usage_topcut_pct': usage.topcut_pct('Mimikyu'),
        'reason': BANNED_REASON,
        'citations': BANNED_CITATIONS,
    }
    rejects.append(banned)
    return rejects


# ---------------------------------------------------------------------------
# TOML rendering (hand-rolled: no writer dependency, fully stable key order)
# ---------------------------------------------------------------------------

def _toml_value(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f'{value:.2f}'
    if isinstance(value, str):
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_toml_value(v) for v in value) + ']'
    raise TypeError(f'unsupported TOML value: {value!r}')


def _emit_table(lines, header, row, keys):
    lines.append(f'[[{header}]]')
    for key in keys:
        if key in row:
            lines.append(f'{key} = {_toml_value(row[key])}')
    lines.append('')


ENTRY_KEYS = [
    'name', 'gamemaster_name', 'species', 'species_id', 'shadow',
    'badge', 'badge_rule', 'forced_reason',
    'current_rank', 'usage_rank',
    'usage_recent_pct', 'usage_recent_pooled_pct', 'usage_all_pct',
    'usage_old_pct', 'usage_topcut_pct',
    'fast_move', 'charged_moves', 'fast_move_id', 'charged_move_ids',
    'moveset_source', 'moveset_modal_pct', 'moveset_n',
    'default_disagrees', 'default_fast_move_id', 'default_charged_move_ids',
    'injected_move_ids', 'injected_moves', 'injection_note',
]

REJECT_KEYS = [
    'name', 'species_id', 'banned', 'usage_rank', 'current_rank',
    'usage_recent_pct', 'usage_all_pct', 'usage_old_pct', 'usage_topcut_pct',
    'reason', 'citations',
]


def render(usage, resolver, generated):
    """Render the whole file as text. No narrative prose, no authored_by."""
    entries = build_entries(usage, resolver)
    # Exclude by the GAMEMASTER name: a fork arm's display name ("Thievul
    # (NS+IW)") never matches a corpus row, so filtering on display alone
    # would let an in-meta species reappear as its own reject.
    rejects = build_rejects(
        usage, resolver,
        {e.get('gamemaster_name', e['name']) for e in entries})

    lines = [
        '# Worlds 2026 robustness analysis -- meta of record.',
        '#',
        '# GENERATED by scripts/worlds_meta.py -- do not hand-edit; the entry',
        '# list and badges are literals in that script (a human decision),',
        '# every statistic here is recomputed from the tournament corpus,',
        '# the gamemaster and PvPoke\'s open-GL rankings.',
        '#',
        '# Shares are team-level and PER-VARIANT (Shadow counted separately);',
        '# usage_recent_pooled_pct is the shadow-agnostic base-species share.',
        '',
        f'format_confirmed = {_toml_value(True)}',
        f'format = {_toml_value("open GL 1500 + Play! banned list")}',
        f'mechanics = {_toml_value("legacy (old system; Worlds-confirmed)")}',
        f'generated = {_toml_value(generated)}',
        '',
        f'usage_source = {_toml_value("docs/tournament_data/cs_2026_*.json (Dracoviz)")}',
        f'usage_recent_cutoff = {_toml_value(RECENT_CUTOFF)}',
        f'usage_excluded_events = {_toml_value(sorted(LIMITED_META_EVENTS))}',
        f'usage_events_recent = {len(usage.recent)}',
        f'usage_teams_recent = {usage.teams_recent}',
        f'usage_events_old = {len(usage.old)}',
        f'usage_teams_old = {usage.teams_old}',
        f'usage_events_all = {len(usage.events)}',
        f'usage_teams_all = {usage.teams_all}',
        f'usage_topcut_rank = {TOP_CUT_RANK}',
        f'usage_teams_topcut = {usage.teams_topcut}',
        '',
        f'rankings_league = {_toml_value("great")}',
        f'rankings_entries = {resolver.rankings_entries}',
        f'moveset_modal_min_pct = {_toml_value(MODAL_MIN_PCT)}',
        f'moveset_modal_min_n = {MODAL_MIN_N}',
        f'badge_usage_top = {BADGE_USAGE_TOP}',
        f'badge_rank_top = {BADGE_RANK_TOP}',
        f'reject_top_n = {REJECT_TOP_N}',
        '',
    ]
    for row in entries:
        _emit_table(lines, 'entries', row, ENTRY_KEYS)
    for row in rejects:
        _emit_table(lines, 'rejects', row, REJECT_KEYS)
    return '\n'.join(lines).rstrip('\n') + '\n'


_GENERATED_RE = re.compile(r'^generated = ".*"$', re.MULTILINE)


def _strip_generated(text):
    return _GENERATED_RE.sub('generated = ""', text)


def generate(out_path=OUT_PATH):
    """Render the file, carrying the old ``generated`` stamp when unchanged.

    Carrying the stamp is what makes the generator idempotent: a same-day
    re-run and a next-day re-run both leave the file byte-identical unless
    a real input moved.
    """
    usage = Usage(load_events())
    resolver = Resolver()
    today = datetime.date.today().isoformat()
    text = render(usage, resolver, today)
    if os.path.exists(out_path):
        with open(out_path) as f:
            old = f.read()
        if _strip_generated(old) == _strip_generated(text):
            text = old
    return text, usage, resolver


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    parser.add_argument('--check', action='store_true',
                        help='exit 1 if worlds/meta.toml is out of date')
    args = parser.parse_args()

    text, usage, _resolver = generate()

    if args.check:
        if not os.path.exists(OUT_PATH):
            print(f'error: {OUT_PATH} does not exist', file=sys.stderr)
            return 1
        with open(OUT_PATH) as f:
            current = f.read()
        if _strip_generated(current) != _strip_generated(text):
            print(f'error: {OUT_PATH} is stale; '
                  f'run python scripts/worlds_meta.py', file=sys.stderr)
            return 1
        print(f'{OUT_PATH} is up to date')
        return 0

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w') as f:
        f.write(text)
    print(f'Wrote {OUT_PATH}: {len(META)} entries, '
          f'{usage.teams_recent} recent teams across {len(usage.recent)} '
          f'open-GL events (>= {RECENT_CUTOFF}).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
