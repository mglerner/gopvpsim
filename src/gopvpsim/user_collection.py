"""
Poke Genie CSV parser, collection stat calculation, and threshold matching.

This module is **shared** between pogo-simulator and gobattlekit (see
``memory/project_shared_user_collection.md`` for the design). Pure Python
(stdlib only) so it imports cleanly on iOS via BeeWare.

Typical flow for a "check my collection against IV targets" workflow::

    from gopvpsim.user_collection import parse_csv, check_thresholds
    from gopvpsim.evolution_lines import load_evolution_lines

    mons = parse_csv('/path/to/pokegenie_export.csv')
    results = check_thresholds(
        '/path/to/pokegenie_export.csv',
        thresholds,                 # {species: {League: {name: {...}}}}
        league='great',
        evolution_lines=load_evolution_lines(),
    )
    # results is {species_name: [{mon, stats, matched, ...}, ...]}

CSV format: Poke Genie export. The parser reads these columns by name
and ignores everything else, so it works on any CSV with at least::

    Name, Form, CP, Atk IV, Def IV, Sta IV, Level Min,
    Shadow/Purified, Lucky

Thresholds are specified as a nested dict keyed on the PvPoke-style
species name (e.g. ``'Tinkaton'``, ``'Tauros (Paldea Combat)'``,
``'Annihilape (Shadow)'``). Each species has per-league sub-dicts keyed
on the ``'Great'`` / ``'Ultra'`` / ``'Master'`` league label (capitalized,
matching gobattlekit's historical schema). Each target is a dict with::

    {
      'attack':  float,      # minimum battle-effective attack
      'defense': float,      # minimum battle-effective defense
      'stamina': int,        # minimum HP
      'ivs':     [[a,d,s]],  # optional: exact IV whitelist
      'onlytop': int,        # optional: only if SP-rank <= N
    }

Shadow handling: ``ivs_to_stats_at_cap`` applies PvPoke's shadow
multipliers (×1.2 atk, ×5/6 def) to the returned attack/defense
values. Thresholds should therefore be expressed in *battle-effective*
terms. This differs from gobattlekit's pre-port behavior, which never
applied shadow multipliers — thresholds authored for gobattlekit may
need re-verification for shadow-form species.
"""

import csv
import math

from .data import load_gamemaster
from .evolution_lines import get_final_forms, load_evolution_lines
from .pokemon import (
    CPM, LEAGUE_CAPS, SHADOW_ATK_BONUS, SHADOW_DEF_MULT,
    battle_stats, best_level, cp as compute_cp, get_pokemon_index,
    iv_rank,
)


# ---------------------------------------------------------------------------
# Form name resolution — Poke Genie form → PvPoke speciesName suffix
# ---------------------------------------------------------------------------

FORM_MAP = {
    '': None,
    'Normal': None,
    'Alola': 'Alolan',
    'Galar': 'Galarian',
    'Hisui': 'Hisuian',
    'Paldea': 'Paldean',
    'Altered': 'Altered',
    'Origin': 'Origin',
    'Defense': 'Defense',
    'Speed': 'Speed',
    'Land': 'Land',
    'Sky': 'Sky',
    'Therian': 'Therian',
    'Confined': 'Confined',
    'Hero': 'Hero',
    'Average': 'Average',
    'Small': 'Small',
    'Large': 'Large',
    'Super': 'Super',
    'Pom-Pom': 'Pom-Pom',
    'Rainy': 'Rainy',
    'Snowy': 'Snowy',
    'Trash': 'Trash',
    'Mega': 'Mega',
}


def get_species_name(name: str, form: str, is_shadow: bool) -> str:
    """Combine Poke Genie ``name``/``form``/``is_shadow`` into the PvPoke
    ``speciesName`` key used by the gamemaster.

    The ``form`` value is normalized via :data:`FORM_MAP` so that
    Poke Genie's ``'Galar'`` becomes the PvPoke suffix ``'Galarian'``.
    Unknown form values pass through unchanged (so additional PvPoke
    variants like ``'Paldea Combat'`` are handled as long as Poke Genie
    emits a matching label).

    Examples::

        get_species_name('Tinkaton', '',        False) → 'Tinkaton'
        get_species_name('Weezing',  'Galar',   False) → 'Weezing (Galarian)'
        get_species_name('Sableye',  '',        True)  → 'Sableye (Shadow)'
        get_species_name('Weezing',  'Galar',   True)  → 'Weezing (Galarian) (Shadow)'
    """
    form_str = FORM_MAP.get(form, form)
    species = name
    if form_str:
        species = f'{name} ({form_str})'
    if is_shadow:
        species = f'{species} (Shadow)'
    return species


# ---------------------------------------------------------------------------
# Poke Genie CSV parser
# ---------------------------------------------------------------------------

def parse_csv(csv_path: str) -> list:
    """Parse a Poke Genie CSV export into a list of mon dicts.

    Each dict carries::

        {'name': str, 'form': str, 'cp': int,
         'atk_iv': int, 'def_iv': int, 'sta_iv': int,
         'level': float,            # Level Min column
         'is_shadow': bool, 'lucky': bool}

    Rows with missing required columns or unparseable values are
    silently skipped (Poke Genie occasionally emits partial rows for
    unseen forms). The BOM-aware ``utf-8-sig`` encoding is used since
    Poke Genie's Android export writes a UTF-8 BOM.

    The parser only reads the named columns, so any CSV with at least
    the required fields works — the full Poke Genie export (50+
    columns) parses fine, as does a hand-trimmed subset.
    """
    mons: list = []
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                mons.append({
                    'name':      row['Name'].strip(),
                    'form':      row['Form'].strip(),
                    'cp':        int(row['CP']),
                    'atk_iv':    int(row['Atk IV']),
                    'def_iv':    int(row['Def IV']),
                    'sta_iv':    int(row['Sta IV']),
                    'level':     float(row['Level Min']),
                    'is_shadow': row['Shadow/Purified'].strip() == '1',
                    'lucky':     row['Lucky'].strip() == '1',
                })
            except (KeyError, ValueError):
                continue
    return mons


# ---------------------------------------------------------------------------
# Stat calculation (shadow-aware, reuses pokemon.py primitives)
# ---------------------------------------------------------------------------

def ivs_to_stats_at_cap(
    base_atk: float, base_def: float, base_sta: float,
    atk_iv: int, def_iv: int, sta_iv: int,
    *, shadow: bool = False, max_level: float = 51.0, max_cp: int = 1500,
) -> "dict | None":
    """Return max-achievable battle stats under a CP cap.

    Walks levels in 0.5 increments and returns the stats at the highest
    level whose CP is ``<= max_cp``. For shadow pokemon, applies
    PvPoke's ×1.2 atk / ×5/6 def multipliers on the returned
    ``attack`` and ``defense`` (CP itself is unaffected by shadow).

    Returns ``None`` if no level under ``max_level`` fits the CP cap
    (rare — happens for low-base-stat species in higher leagues).

    Return dict::

        {'level': float, 'cp': int,
         'attack': float, 'defense': float, 'stamina': int,
         'stat_prod': int, 'bulk_prod': int}

    The ``stat_prod`` and ``bulk_prod`` values are floored after the
    multiplication, matching gobattlekit's historical convention.
    """
    lv = best_level(base_atk, base_def, base_sta, atk_iv, def_iv, sta_iv,
                    max_cp=max_cp, max_level=max_level)
    if lv is None:
        return None
    stats = battle_stats(base_atk, base_def, base_sta,
                         atk_iv, def_iv, sta_iv, lv)
    shadow_atk = SHADOW_ATK_BONUS if shadow else 1.0
    shadow_def = SHADOW_DEF_MULT if shadow else 1.0
    attack  = stats['atk'] * shadow_atk
    defense = stats['def'] * shadow_def
    stamina = stats['hp']
    return {
        'level':     lv,
        'cp':        compute_cp(base_atk, base_def, base_sta,
                                atk_iv, def_iv, sta_iv, lv),
        'attack':    attack,
        'defense':   defense,
        'stamina':   stamina,
        'stat_prod': math.floor(attack * defense * stamina),
        'bulk_prod': math.floor(defense * stamina),
    }


def compute_rank_lookup(
    species: str, *, league: str = 'great',
    max_level: float = 51.0, shadow: bool = False,
) -> dict:
    """Return a ``{(atk_iv, def_iv, sta_iv): rank}`` dict for a species.

    Wraps :func:`gopvpsim.pokemon.iv_rank` (which ranks all 4096 IV
    combinations by stat product) and flattens the result to a flat
    lookup table. Rank 1 is the highest stat product, matching
    PvPoke's rank convention with IV-sum tiebreaking.
    """
    ranked = iv_rank(species, league=league,
                     max_level=max_level, shadow=shadow)
    return {(e['atk_iv'], e['def_iv'], e['sta_iv']): e['rank']
            for e in ranked}


# ---------------------------------------------------------------------------
# Threshold matcher (dict schema — gobattlekit compatibility)
# ---------------------------------------------------------------------------

def _match_target(stats: dict, iv_tuple: tuple, target: dict) -> bool:
    """Return True if the mon's stats + IVs satisfy a single target spec."""
    if stats['attack']  < target.get('attack',  0): return False
    if stats['defense'] < target.get('defense', 0): return False
    if stats['stamina'] < target.get('stamina', 0): return False
    if 'ivs' in target:
        if not any(tuple(iv) == iv_tuple for iv in target['ivs']):
            return False
    if 'onlytop' in target:
        if stats['rank'] > target['onlytop']:
            return False
    return True


def check_thresholds(
    csv_path: str, thresholds: dict, *,
    league: str = 'great', max_level: float = 51.0,
    evolution_lines: "dict | None" = None, include_empty: bool = False,
) -> dict:
    """Parse a Poke Genie CSV and match each mon against an IV target dict.

    For each row in the CSV:

    1. Resolve the species name (form + shadow suffix).
    2. If the resolved name isn't in ``thresholds``, walk its evolution
       chain via :func:`gopvpsim.evolution_lines.get_final_forms` and
       check each possible final form. Branching pre-evos like Eevee
       are tried against every reachable final.
    3. Compute max-level battle stats under the league CP cap
       (shadow-adjusted if applicable).
    4. Look up the mon's stat-product rank for the target species.
    5. For each target under ``thresholds[species][league_label]``,
       check attack / defense / stamina floors, the optional ``ivs``
       whitelist, and the optional ``onlytop`` rank cap. Collect names
       of all matching targets.
    6. If any targets match, append a result record under the target
       species. A single mon can appear under multiple species if its
       evolution has multiple branches (e.g. an Eevee that qualifies
       for both Umbreon and Sylveon targets).

    ``thresholds`` schema::

        {species_name: {LeagueLabel: {target_name: {attack, defense,
                                                     stamina, ivs?,
                                                     onlytop?}}}}

    Returns ``{species_name: [result_record, ...]}`` where each record
    is::

        {'mon':            parsed mon dict,
         'csv_species':    species as resolved from the CSV row,
         'final_species':  target species matched against,
         'is_pre_evo':     True if csv_species != final_species,
         'stats':          output of ivs_to_stats_at_cap + 'rank',
         'matched':        list of target_name strings}

    When ``include_empty=True``, species that appear in ``thresholds``
    but have no matching mons in the CSV get an empty list entry in
    the result (useful for UI rendering).
    """
    max_cp = LEAGUE_CAPS[league]
    if evolution_lines is None:
        evolution_lines = load_evolution_lines()

    pokemon_index = get_pokemon_index()
    mons = parse_csv(csv_path)
    league_label = league.capitalize()

    # Lazy rank-table cache: species -> (shadow_flag) -> lookup dict.
    # Key on shadow because shadow changes stat product ordering.
    rank_cache: dict = {}

    def _get_rank(species: str, iv_tuple: tuple, shadow: bool) -> int:
        key = (species, shadow)
        if key not in rank_cache:
            rank_cache[key] = compute_rank_lookup(
                species, league=league, max_level=max_level, shadow=shadow)
        return rank_cache[key].get(iv_tuple, 4096)

    results: dict = {}

    for mon in mons:
        csv_species = get_species_name(
            mon['name'], mon['form'], mon['is_shadow'])

        # Resolve target species: either a direct threshold hit, or any
        # final form reachable via evolution.
        targets_to_try: list = []
        if csv_species in thresholds:
            targets_to_try.append(csv_species)
        else:
            for final in get_final_forms(csv_species):
                if final in thresholds and final not in targets_to_try:
                    targets_to_try.append(final)

        if not targets_to_try:
            continue

        for final_species in targets_to_try:
            species_thresholds = thresholds[final_species].get(league_label)
            if not species_thresholds:
                continue
            if final_species not in pokemon_index:
                continue

            base = pokemon_index[final_species]
            stats = ivs_to_stats_at_cap(
                base['atk'], base['def'], base['hp'],
                mon['atk_iv'], mon['def_iv'], mon['sta_iv'],
                shadow=mon['is_shadow'],
                max_level=max_level, max_cp=max_cp,
            )
            if stats is None:
                continue

            iv_tuple = (mon['atk_iv'], mon['def_iv'], mon['sta_iv'])
            stats['rank'] = _get_rank(final_species, iv_tuple, mon['is_shadow'])

            matched = [
                name for name, target in species_thresholds.items()
                if _match_target(stats, iv_tuple, target)
            ]
            if matched:
                results.setdefault(final_species, []).append({
                    'mon':           mon,
                    'csv_species':   csv_species,
                    'final_species': final_species,
                    'is_pre_evo':    csv_species != final_species,
                    'stats':         stats,
                    'matched':       matched,
                })

    if include_empty:
        for species in thresholds:
            if species not in results and league_label in thresholds[species]:
                results[species] = []

    return results
