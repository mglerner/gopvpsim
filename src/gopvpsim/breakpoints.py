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

from typing import NamedTuple

from .moves import (
    damage as calc_damage,
    type_effectiveness, stab as calc_stab,
    BONUS, mega_multiplier, damage_constant,
)
from .pokemon import (
    get_species, best_level, CPM, LEAGUE_CAPS,
    battle_stats, effective_stats, find_pokemon_entry,
    mega_level as _species_mega_level,
)


# ---------------------------------------------------------------------------
# Pure-math helpers
# ---------------------------------------------------------------------------

# _K is now a thin alias for the shared constant -- kept as a name because
# the module docstring's algebra (and the tests) refer to "K". The formula
# itself lives in ONE place, gopvpsim.moves.damage_constant.
_K = damage_constant


# NOTE (deliberate divergence from PvPoke, 2026-09-02). PvPoke added the Mega
# Bonus to DamageCalculator.damage() and damageByStats() but NOT to its own
# breakpoint() / bulkpoint() solvers (DamageCalculator.js:117-136), so upstream
# a supermega's `*_PLUS` breakpoint table disagrees with the damage numbers
# printed either side of it, by the full 1.3x. We apply the factor here.
#
# This fails CLAUDE.md's "don't diverge unless PvPoke is worse" gate in
# PvPoke's favour on all three questions: its solver is internally
# inconsistent with its own damage function, breakpoints ARE this project's
# deliverable, and matching the inconsistency would ship a knowingly wrong
# threshold. Recorded in DEVELOPER_NOTES "PvPoke bugs found".
def atk_for_damage(dmg: int, def_: float, move: dict,
                   attacker_types: list[str], defender_types: list[str],
                   mega_level: "int | None" = None) -> float:
    """Minimum effective attack stat that deals `dmg` damage with `move`.

    This is the breakpoint threshold — any atk >= this value deals at least `dmg`.

    ``mega_level`` is the ATTACKER's Mega Level (None when it is not a mega);
    it only bites for a mega-exclusive ``isMegaMove`` move.
    """
    k = _K(move['power'], move['type'], attacker_types, defender_types,
           mega_multiplier(move, mega_level))
    return (dmg - 1) * def_ / k


def def_for_damage(dmg: int, atk: float, move: dict,
                   attacker_types: list[str], defender_types: list[str],
                   mega_level: "int | None" = None) -> float:
    """The critical defense threshold at which incoming damage drops from dmg+1 to dmg.

    A defender with def > this threshold takes dmg damage.
    A defender with def <= this threshold takes dmg+1 damage.
    At exactly this value, damage is still dmg+1 (the threshold is exclusive).

    This matches PvPoke's DamageCalculator.bulkpoint formula, EXCEPT that we
    apply the Mega Bonus and PvPoke does not -- see the note above
    :func:`atk_for_damage`. ``mega_level`` is the ATTACKER's.
    """
    k = _K(move['power'], move['type'], attacker_types, defender_types,
           mega_multiplier(move, mega_level))
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
    *,
    mega_level: "int | None" = None,
) -> list[Breakpoint]:
    """All attack breakpoints in [atk_min, atk_max].

    Returns a list of Breakpoint(atk_threshold, damage) sorted by atk_threshold.
    Each entry is the minimum attack that first achieves `damage` against this defender.

    ``mega_level`` is the ATTACKER's Mega Level, or None when it is not a
    mega. It must be threaded here as well as into the solver: the loop
    bounds come from :func:`calc_damage`, so a mismatch between the two would
    scan the wrong damage range.
    """
    mm = mega_multiplier(move, mega_level)
    # Power-0 moves (SPLASH, YAWN, TRANSFORM, the AEGISLASH_CHARGE_* fast moves)
    # deal a flat 1 damage at every attack, so there is no breakpoint. Guard the
    # K==0 case: atk_for_damage would compute (dmg-1)*def/0 -> ZeroDivisionError,
    # which the deep-dive pipeline swallows into a warning and drops EVERY anchor
    # for the whole dive (Aegislash Shield's canonical fast move is power 0).
    if _K(move['power'], move['type'], attacker_types, defender_types, mm) == 0:
        return []

    d_min = calc_damage(move['power'], atk_min, defender_def,
                        move['type'], attacker_types, defender_types, mm)
    d_max = calc_damage(move['power'], atk_max, defender_def,
                        move['type'], attacker_types, defender_types, mm)

    result = []
    for dmg in range(d_min, d_max + 1):
        thresh = atk_for_damage(dmg, defender_def, move, attacker_types,
                                defender_types, mega_level)
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
    *,
    mega_level: "int | None" = None,
) -> list[Bulkpoint]:
    """All defense bulkpoints in [def_min, def_max].

    Returns a list of Bulkpoint(def_threshold, damage) sorted by def_threshold.
    Each entry is the minimum defense at which incoming damage is reduced to `damage`.

    ``mega_level`` is the ATTACKER's (the mon whose move we are bulking
    against), or None when it is not a mega.
    """
    mm = mega_multiplier(move, mega_level)
    d_at_min = calc_damage(move['power'], attacker_atk, def_min,
                           move['type'], attacker_types, defender_types, mm)
    d_at_max = calc_damage(move['power'], attacker_atk, def_max,
                           move['type'], attacker_types, defender_types, mm)

    result = []
    for dmg in range(d_at_max, d_at_min + 1):
        thresh = def_for_damage(dmg, attacker_atk, move, attacker_types,
                                defender_types, mega_level)
        if def_min <= thresh <= def_max:
            result.append(Bulkpoint(thresh, dmg))

    return sorted(result)


# ---------------------------------------------------------------------------
# Gamemaster helpers
# ---------------------------------------------------------------------------

def _get_types(species_name: str) -> list[str]:
    """Return the type list for a species from the gamemaster."""
    from .moves import parse_types
    # find_pokemon_entry, not get_pokemon_entry: the cached index's own
    # KeyError carries only the bare name, and callers key off THIS message
    # (DRY review 2026-08-05 entry 12 / L11).
    mon = find_pokemon_entry(species_name)
    if mon is None:
        raise KeyError(f"Species not found: {species_name!r}")
    return parse_types(mon)


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

def _blade_round_down(species_name: str, level: float) -> float:
    """Round a half-level down to the whole level below for Aegislash (Blade).

    Blade powers up in whole-level increments only, so the standard
    half-level grid is wrong for it as the focal species. Canonical rule:
    ``Pokemon.at_best_level`` (pokemon.py:350-357) and ``iv_rank``
    (pokemon.py:389-402); ``scripts/deep_dive_lib/sweep.py`` repeats it too.

    This is a deliberate local copy, not a shared helper: ``pokemon.py`` is
    one of ``scripts/sweep_cache.py``'s ``_ENGINE_FILES``, so hoisting this
    there (even as a pure addition) would bump the engine hash and stale the
    whole sweep cache. See the DRY review's architecture note about the rule
    being duplicated in four places.
    """
    if species_name == 'Aegislash (Blade)' and level % 1.0 != 0:
        return level - 0.5
    return level


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
    attacker_shadow: bool = False,
    defender_shadow: bool = False,
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
    # Mega Bonus rides on the ATTACKER in both directions -- for a bulkpoint
    # the attacker is the fixed side whose move we are bulking against.
    _attacker_mega_mult = mega_multiplier(
        move, _species_mega_level(attacker_species))

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
    d_level     = _blade_round_down(defender_species, d_level)
    d_stats     = battle_stats(d_base['atk'], d_base['def'], d_base['hp'],
                               defender_atk_iv, defender_def_iv, defender_sta_iv,
                               d_level)
    _, defender_def = effective_stats(d_stats['atk'], d_stats['def'],
                                      defender_shadow)

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
                level = _blade_round_down(attacker_species, level)
                stats = battle_stats(
                    a_base['atk'], a_base['def'], a_base['hp'],
                    atk_iv, def_iv, sta_iv, level,
                )
                # Attack side only: the stat product below keeps the RAW def,
                # unchanged from before this routed through effective_stats.
                atk_stat, _ = effective_stats(stats['atk'], stats['def'],
                                              attacker_shadow)
                dmg      = calc_damage(
                    move['power'], atk_stat, defender_def,
                    move['type'], attacker_types, defender_types,
                    _attacker_mega_mult,
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
    attacker_shadow: bool = False,
    defender_shadow: bool = False,
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
    # Mega Bonus rides on the ATTACKER in both directions -- for a bulkpoint
    # the attacker is the fixed side whose move we are bulking against.
    _attacker_mega_mult = mega_multiplier(
        move, _species_mega_level(attacker_species))

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
    a_level     = _blade_round_down(attacker_species, a_level)
    a_stats     = battle_stats(a_base['atk'], a_base['def'], a_base['hp'],
                               attacker_atk_iv, attacker_def_iv, attacker_sta_iv,
                               a_level)
    attacker_atk, _ = effective_stats(a_stats['atk'], a_stats['def'],
                                      attacker_shadow)

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
                level = _blade_round_down(defender_species, level)
                stats = battle_stats(
                    d_base['atk'], d_base['def'], d_base['hp'],
                    atk_iv, def_iv, sta_iv, level,
                )
                # Defense side only: the stat product below keeps the RAW atk,
                # unchanged from before this routed through effective_stats.
                _, def_stat = effective_stats(stats['atk'], stats['def'],
                                              defender_shadow)
                dmg = calc_damage(
                    move['power'], attacker_atk, def_stat,
                    move['type'], attacker_types, defender_types,
                    _attacker_mega_mult,
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
