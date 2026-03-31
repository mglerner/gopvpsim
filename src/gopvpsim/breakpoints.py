"""
Breakpoint and bulkpoint analysis.

Terminology
-----------
breakpoint : the attacker's effective attack stat at which fast-move (or charged-move)
             damage against a specific defender increases by 1.
bulkpoint  : the defender's effective defense stat at which damage received from a
             specific attacker/move decreases by 1.

Derivation from the damage formula
-----------------------------------
D = floor(K * atk / def) + 1
where K = 0.5 * BONUS * power * stab * effectiveness

Solving for atk (breakpoint — minimum attack that achieves damage D):
    atk_min = (D - 1) * def / K                        [atk_for_damage]

Solving for def (bulkpoint — minimum defense that reduces damage to D):
    def_min = K * atk / D                              [def_for_damage]
    (above this defense, floor(K*atk/def) < D, so damage <= D)

These formulas match PvPoke's DamageCalculator.breakpoint / .bulkpoint.
"""

import math
from typing import NamedTuple

from .moves import (
    damage as calc_damage,
    type_effectiveness, stab as calc_stab,
    BONUS,
)
from .pokemon import (
    get_species, best_level, CPM, LEAGUE_CAPS,
    battle_stats,
)


# ---------------------------------------------------------------------------
# Pure-math helpers
# ---------------------------------------------------------------------------

def _K(power: float, move_type: str, attacker_types: list[str],
       defender_types: list[str]) -> float:
    """The constant part of the damage formula: 0.5 * BONUS * power * stab * eff."""
    eff   = type_effectiveness(move_type, defender_types)
    stab_ = calc_stab(move_type, attacker_types)
    return 0.5 * BONUS * power * stab_ * eff


def atk_for_damage(dmg: int, def_: float, move: dict,
                   attacker_types: list[str], defender_types: list[str]) -> float:
    """Minimum effective attack stat that deals `dmg` damage with `move`.

    This is the breakpoint threshold — any atk >= this value deals at least `dmg`.
    """
    k = _K(move['power'], move['type'], attacker_types, defender_types)
    return (dmg - 1) * def_ / k


def def_for_damage(dmg: int, atk: float, move: dict,
                   attacker_types: list[str], defender_types: list[str]) -> float:
    """The critical defense threshold at which incoming damage drops from dmg+1 to dmg.

    A defender with def > this threshold takes dmg damage.
    A defender with def <= this threshold takes dmg+1 damage.
    At exactly this value, damage is still dmg+1 (the threshold is exclusive).

    This matches PvPoke's DamageCalculator.bulkpoint formula.
    """
    k = _K(move['power'], move['type'], attacker_types, defender_types)
    return k * atk / dmg


# ---------------------------------------------------------------------------
# Range-based analysis (pure math)
# ---------------------------------------------------------------------------

class Breakpoint(NamedTuple):
    atk_threshold: float   # minimum attack needed
    damage:        int     # damage achieved at this threshold


class Bulkpoint(NamedTuple):
    def_threshold: float   # minimum defense needed
    damage:        int     # damage received at/above this threshold


def breakpoints(
    move: dict,
    attacker_types: list[str],
    defender_def: float,
    defender_types: list[str],
    atk_min: float,
    atk_max: float,
) -> list[Breakpoint]:
    """All attack breakpoints in [atk_min, atk_max].

    Returns a list of Breakpoint(atk_threshold, damage) sorted by atk_threshold.
    Each entry is the minimum attack that first achieves `damage` against this defender.
    """
    d_min = calc_damage(move['power'], atk_min, defender_def,
                        move['type'], attacker_types, defender_types)
    d_max = calc_damage(move['power'], atk_max, defender_def,
                        move['type'], attacker_types, defender_types)

    result = []
    for dmg in range(d_min, d_max + 1):
        thresh = atk_for_damage(dmg, defender_def, move, attacker_types, defender_types)
        if atk_min <= thresh <= atk_max:
            result.append(Breakpoint(thresh, dmg))

    return sorted(result)


def bulkpoints(
    move: dict,
    attacker_atk: float,
    attacker_types: list[str],
    defender_types: list[str],
    def_min: float,
    def_max: float,
) -> list[Bulkpoint]:
    """All defense bulkpoints in [def_min, def_max].

    Returns a list of Bulkpoint(def_threshold, damage) sorted by def_threshold.
    Each entry is the minimum defense at which incoming damage is reduced to `damage`.
    """
    d_at_min = calc_damage(move['power'], attacker_atk, def_min,
                           move['type'], attacker_types, defender_types)
    d_at_max = calc_damage(move['power'], attacker_atk, def_max,
                           move['type'], attacker_types, defender_types)

    result = []
    for dmg in range(d_at_max, d_at_min + 1):
        thresh = def_for_damage(dmg, attacker_atk, move, attacker_types, defender_types)
        if def_min <= thresh <= def_max:
            result.append(Bulkpoint(thresh, dmg))

    return sorted(result)


# ---------------------------------------------------------------------------
# Gamemaster helpers
# ---------------------------------------------------------------------------

def _get_types(species_name: str) -> list[str]:
    """Return the type list for a species from the gamemaster."""
    from .data import load_gamemaster
    gm  = load_gamemaster()
    mon = next((m for m in gm['pokemon'] if m['speciesName'] == species_name), None)
    if mon is None:
        raise KeyError(f"Species not found: {species_name!r}")
    types = mon.get('types', mon.get('type', None))
    if types is None:
        raise KeyError(f"No type data for {species_name!r}")
    return [types] if isinstance(types, str) else list(types)


def _get_move(move_id: str) -> dict:
    """Return a move dict by ID."""
    from .moves import get_moves
    fast, charged = get_moves()
    if move_id in fast:
        return fast[move_id]
    if move_id in charged:
        return charged[move_id]
    raise KeyError(f"Move not found: {move_id!r}")


# ---------------------------------------------------------------------------
# High-level IV analysis
# ---------------------------------------------------------------------------

def iv_breakpoints(
    attacker_species: str,
    move_id: str,
    defender_species: str,
    defender_atk_iv: int = 15,
    defender_def_iv: int = 15,
    defender_sta_iv: int = 15,
    *,
    league: str = 'great',
    attacker_max_level: float = 51.0,
    defender_max_level: float = 51.0,
) -> list[dict]:
    """Damage dealt by every attacker IV combo against a specific defender.

    For each of the 4096 (atk_iv, def_iv, sta_iv) combos for the attacker,
    computes the best level under the league CP cap and the damage dealt with
    `move_id` against the fixed defender.

    Returns a list of dicts sorted by (damage desc, stat_product desc):
        atk_iv, def_iv, sta_iv, level, cp, atk, damage, stat_product
    """
    move            = _get_move(move_id)
    attacker_types  = _get_types(attacker_species)
    defender_types  = _get_types(defender_species)
    max_cp          = LEAGUE_CAPS[league]

    a_base  = get_species(attacker_species)
    d_base  = get_species(defender_species)

    # Build defender's effective defense stat
    d_level = best_level(
        d_base['atk'], d_base['def'], d_base['hp'],
        defender_atk_iv, defender_def_iv, defender_sta_iv,
        max_cp=max_cp, max_level=defender_max_level,
    )
    if d_level is None:
        raise ValueError(f"{defender_species} can't fit in {league} league at those IVs")
    d_stats     = battle_stats(d_base['atk'], d_base['def'], d_base['hp'],
                               defender_atk_iv, defender_def_iv, defender_sta_iv,
                               d_level)
    defender_def = d_stats['def']

    results = []
    for atk_iv in range(16):
        for def_iv in range(16):
            for sta_iv in range(16):
                level = best_level(
                    a_base['atk'], a_base['def'], a_base['hp'],
                    atk_iv, def_iv, sta_iv,
                    max_cp=max_cp, max_level=attacker_max_level,
                )
                if level is None:
                    continue
                stats = battle_stats(
                    a_base['atk'], a_base['def'], a_base['hp'],
                    atk_iv, def_iv, sta_iv, level,
                )
                atk_stat = stats['atk']
                dmg      = calc_damage(
                    move['power'], atk_stat, defender_def,
                    move['type'], attacker_types, defender_types,
                )
                sp = atk_stat * stats['def'] * stats['hp']
                results.append({
                    'atk_iv':      atk_iv,
                    'def_iv':      def_iv,
                    'sta_iv':      sta_iv,
                    'level':       level,
                    'atk':         atk_stat,
                    'damage':      dmg,
                    'stat_product': sp,
                })

    results.sort(key=lambda r: (-r['damage'], -r['stat_product']))
    return results


def iv_bulkpoints(
    defender_species: str,
    move_id: str,
    attacker_species: str,
    attacker_atk_iv: int = 15,
    attacker_def_iv: int = 15,
    attacker_sta_iv: int = 15,
    *,
    league: str = 'great',
    defender_max_level: float = 51.0,
    attacker_max_level: float = 51.0,
) -> list[dict]:
    """Damage received by every defender IV combo from a specific attacker/move.

    For each of the 4096 (atk_iv, def_iv, sta_iv) combos for the defender,
    computes the best level under the league CP cap and the damage received from
    `move_id` thrown by the fixed attacker.

    Returns a list of dicts sorted by (damage asc, stat_product desc):
        atk_iv, def_iv, sta_iv, level, def_, hp, damage, stat_product
    """
    move            = _get_move(move_id)
    attacker_types  = _get_types(attacker_species)
    defender_types  = _get_types(defender_species)
    max_cp          = LEAGUE_CAPS[league]

    a_base = get_species(attacker_species)
    d_base = get_species(defender_species)

    # Build attacker's effective attack stat
    a_level = best_level(
        a_base['atk'], a_base['def'], a_base['hp'],
        attacker_atk_iv, attacker_def_iv, attacker_sta_iv,
        max_cp=max_cp, max_level=attacker_max_level,
    )
    if a_level is None:
        raise ValueError(f"{attacker_species} can't fit in {league} league at those IVs")
    a_stats     = battle_stats(a_base['atk'], a_base['def'], a_base['hp'],
                               attacker_atk_iv, attacker_def_iv, attacker_sta_iv,
                               a_level)
    attacker_atk = a_stats['atk']

    results = []
    for atk_iv in range(16):
        for def_iv in range(16):
            for sta_iv in range(16):
                level = best_level(
                    d_base['atk'], d_base['def'], d_base['hp'],
                    atk_iv, def_iv, sta_iv,
                    max_cp=max_cp, max_level=defender_max_level,
                )
                if level is None:
                    continue
                stats = battle_stats(
                    d_base['atk'], d_base['def'], d_base['hp'],
                    atk_iv, def_iv, sta_iv, level,
                )
                def_stat = stats['def']
                dmg = calc_damage(
                    move['power'], attacker_atk, def_stat,
                    move['type'], attacker_types, defender_types,
                )
                sp = stats['atk'] * def_stat * stats['hp']
                results.append({
                    'atk_iv':       atk_iv,
                    'def_iv':       def_iv,
                    'sta_iv':       sta_iv,
                    'level':        level,
                    'def':          def_stat,
                    'hp':           stats['hp'],
                    'damage':       dmg,
                    'stat_product': sp,
                })

    results.sort(key=lambda r: (r['damage'], -r['stat_product']))
    return results
