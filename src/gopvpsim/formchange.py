"""
Form change mechanics for Pokemon Go PvP.

Supports three form-change Pokemon:
  - Morpeko: toggles AURA_WHEEL_ELECTRIC <-> AURA_WHEEL_DARK after each charged move
  - Aegislash: swaps Shield <-> Blade forms (stats, fast moves, level) on
    charged move use and shielding
  - Mimikyu: disguise absorbs first unshielded charged hit (dmg=1), then
    permanent -1 def stage

The system is data-driven: form change triggers and effects are read from the
gamemaster's formChange field on each Pokemon entry.  Adding a new form-change
Pokemon with an existing trigger type requires no code changes here.
"""
import math
from dataclasses import dataclass

from .data import parse_types
from .moves import get_moves
from .pokemon import CPM, SHADOW_ATK_BONUS, SHADOW_DEF_MULT, cp, get_pokemon_entry_by_id


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FormData:
    """Precomputed stats/moves for one form."""
    species: str              # speciesName
    species_id: str           # speciesId (for activeFormId checks)
    types: tuple              # immutable type tuple
    atk: float                # effective attack stat
    def_: float               # effective defense stat
    fast_move: dict           # move dict
    charged_moves: tuple      # tuple of move dicts
    trigger: str | None       # what triggers change FROM this form
    move_id: str | None       # constraint on triggering move ("ANY" or specific moveId)
    native_stat_buffs: tuple[int, int] | None  # buffs applied when ENTERING this form


@dataclass(frozen=True, slots=True)
class FormChangeConfig:
    """Precomputed form-change state for a BattlePokemon."""
    forms: tuple              # (FormData, FormData) — [0]=default, [1]=alt
    reset_on_switch: bool
    effect: str | None        # "protect" for Mimikyu, None otherwise


# ---------------------------------------------------------------------------
# Move remapping tables
# ---------------------------------------------------------------------------

# Aegislash Shield form uses special 0-damage fast moves; Blade form uses normal ones.
_AEGISLASH_FAST_MOVE_MAP = {
    'AEGISLASH_CHARGE_PSYCHO_CUT': 'PSYCHO_CUT',
    'AEGISLASH_CHARGE_AIR_SLASH': 'AIR_SLASH',
    'PSYCHO_CUT': 'AEGISLASH_CHARGE_PSYCHO_CUT',
    'AIR_SLASH': 'AEGISLASH_CHARGE_AIR_SLASH',
}

# Morpeko swaps its signature charged move between forms.
_MORPEKO_CHARGED_MOVE_MAP = {
    'AURA_WHEEL_ELECTRIC': 'AURA_WHEEL_DARK',
    'AURA_WHEEL_DARK': 'AURA_WHEEL_ELECTRIC',
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _swap_charged_move(charged_moves, move_map):
    """Return a new tuple of charged move dicts with any mapped moves swapped."""
    _, all_charged = get_moves()
    result = []
    for cm in charged_moves:
        mid = cm['moveId']
        if mid in move_map:
            alt_id = move_map[mid]
            result.append(all_charged[alt_id])
        else:
            result.append(cm)
    return tuple(result)


def _swap_fast_move(fast_move, move_map):
    """Return the alternate fast move dict if mapped, else the same move."""
    mid = fast_move['moveId']
    if mid in move_map:
        all_fast, _ = get_moves()
        return all_fast[move_map[mid]]
    return fast_move


def _aegislash_alt_level(shield_level, league_cp):
    """Compute Aegislash Blade form level from Shield form level.

    PvPoke's getFormStats() uses:
      GL: newLevel = ceil(shield_level * 0.5) + 1
      UL: newLevel = ceil(shield_level * 0.75)
    Then steps down by whole levels until CP fits.

    The game only uses whole levels for Blade form (not half levels).
    This was discovered by cascade1185 and confirmed by Caleb Peng.
    """
    if league_cp <= 1500:
        start = math.ceil(shield_level * 0.5) + 1
    elif league_cp <= 2500:
        start = math.ceil(shield_level * 0.75)
    else:
        # Master league: same level (no CP cap constraint)
        return shield_level
    # Step down whole levels until CP fits (computed later by caller)
    return float(start)


def _aegislash_shield_level(blade_level, league_cp):
    """Compute Aegislash Shield form level from Blade form level (reverse)."""
    if league_cp <= 1500:
        start = (blade_level / 0.5) + 2
    elif league_cp <= 2500:
        start = round(blade_level / 0.75)
    else:
        return blade_level
    return float(start)


def build_form_change_state(mon_entry, atk_iv, def_iv, sta_iv,
                            level, league_cp, shadow,
                            fast_move, charged_moves):
    """Build a FormChangeConfig from a gamemaster entry and battle setup.

    Args:
        mon_entry: full gamemaster dict for this Pokemon
        atk_iv, def_iv, sta_iv: IVs (0-15)
        level: the Pokemon's level in its starting form
        league_cp: CP cap (1500, 2500, or 10000)
        shadow: whether this is a shadow Pokemon
        fast_move: the fast move dict being used
        charged_moves: list of charged move dicts being used

    Returns:
        FormChangeConfig or None if the species has no form change.
    """
    fc = mon_entry.get('formChange')
    if fc is None:
        return None

    trigger = fc.get('trigger')
    if trigger == 'none':
        # Busted Mimikyu has trigger='none' — no form change FROM this form
        return None

    alt_id = fc.get('alternativeFormId')
    if alt_id is None:
        return None

    alt_entry = get_pokemon_entry_by_id(alt_id)
    alt_fc = alt_entry.get('formChange', {})

    species_id = mon_entry['speciesId']
    alt_species_id = alt_entry['speciesId']

    # Default form data (current form)
    default_types = tuple(parse_types(mon_entry))
    default_native_buffs = None
    raw_buffs = mon_entry.get('nativeStatBuffs')
    if raw_buffs and any(b != 0 for b in raw_buffs):
        default_native_buffs = tuple(raw_buffs)

    # Alt form data
    alt_types = tuple(parse_types(alt_entry))
    alt_native_buffs = None
    raw_alt_buffs = alt_entry.get('nativeStatBuffs')
    if raw_alt_buffs and any(b != 0 for b in raw_alt_buffs):
        alt_native_buffs = tuple(raw_alt_buffs)

    shadow_atk = SHADOW_ATK_BONUS if shadow else 1.0
    shadow_def = SHADOW_DEF_MULT if shadow else 1.0

    # Compute alt form stats
    alt_base = alt_entry['baseStats']
    alt_level = level  # same level by default

    # Aegislash: level recalculation
    if species_id == 'aegislash_shield':
        alt_level = _aegislash_alt_level(level, league_cp)
        # Step down whole levels until CP fits
        while alt_level >= 1.0:
            if cp(alt_base['atk'], alt_base['def'], alt_base['hp'],
                  atk_iv, def_iv, sta_iv, alt_level) <= league_cp:
                break
            alt_level -= 1.0
        alt_level = max(1.0, alt_level)
    elif species_id == 'aegislash_blade':
        alt_level = _aegislash_shield_level(level, league_cp)
        while alt_level >= 1.0:
            if cp(alt_base['atk'], alt_base['def'], alt_base['hp'],
                  atk_iv, def_iv, sta_iv, alt_level) <= league_cp:
                break
            alt_level -= 1.0
        alt_level = max(1.0, alt_level)

    alt_cpm = CPM[alt_level]
    alt_atk = (alt_base['atk'] + atk_iv) * alt_cpm * shadow_atk
    alt_def = (alt_base['def'] + def_iv) * alt_cpm * shadow_def

    # Compute alt form moves
    alt_fast_move = fast_move
    alt_charged_moves = tuple(charged_moves)

    # Aegislash: swap fast moves between CHARGE variants and normal
    if species_id in ('aegislash_shield', 'aegislash_blade'):
        alt_fast_move = _swap_fast_move(fast_move, _AEGISLASH_FAST_MOVE_MAP)

    # Morpeko: swap AURA_WHEEL charged move
    if species_id in ('morpeko_full_belly', 'morpeko_hangry'):
        alt_charged_moves = _swap_charged_move(charged_moves, _MORPEKO_CHARGED_MOVE_MAP)

    # Build FormData for both forms
    default_fd = FormData(
        species=mon_entry['speciesName'],
        species_id=species_id,
        types=default_types,
        atk=(mon_entry['baseStats']['atk'] + atk_iv) * CPM[level] * shadow_atk,
        def_=(mon_entry['baseStats']['def'] + def_iv) * CPM[level] * shadow_def,
        fast_move=fast_move,
        charged_moves=tuple(charged_moves),
        trigger=trigger,
        move_id=fc.get('moveId'),
        native_stat_buffs=default_native_buffs,
    )

    alt_trigger = alt_fc.get('trigger')
    alt_fd = FormData(
        species=alt_entry['speciesName'],
        species_id=alt_species_id,
        types=alt_types,
        atk=alt_atk,
        def_=alt_def,
        fast_move=alt_fast_move,
        charged_moves=alt_charged_moves,
        trigger=alt_trigger if alt_trigger != 'none' else None,
        move_id=alt_fc.get('moveId'),
        native_stat_buffs=alt_native_buffs,
    )

    reset_on_switch = fc.get('resetOnSwitch', True)
    effect = fc.get('effect')

    return FormChangeConfig(
        forms=(default_fd, alt_fd),
        reset_on_switch=reset_on_switch,
        effect=effect,
    )


# ---------------------------------------------------------------------------
# Runtime form change
# ---------------------------------------------------------------------------

def apply_form_change(bp, opponent):
    """Apply a form change to a BattlePokemon. Mutates bp in place.

    Swaps species, types, atk, def_, fast_move, charged_moves to the
    target form's precomputed values. Does NOT change hp or max_hp
    (matches PvPoke's commented-out hp line). Applies nativeStatBuffs
    as stat stage adjustments. Invalidates damage caches on both sides.

    Args:
        bp: the BattlePokemon changing forms
        opponent: the opposing BattlePokemon (for cache invalidation)
    """
    cfg = bp._form_change
    target_idx = 1 if not bp._form_is_alt else 0
    fd = cfg.forms[target_idx]

    bp.species = fd.species
    bp.types = list(fd.types)
    bp.atk = fd.atk
    bp.def_ = fd.def_
    bp.fast_move = fd.fast_move
    bp.charged_moves = list(fd.charged_moves)

    # Do NOT change bp.hp or bp.max_hp (PvPoke behavior)

    # Apply native stat buffs when entering this form
    if fd.native_stat_buffs is not None:
        atk_buff, def_buff = fd.native_stat_buffs
        bp.atk_stage = max(-4, min(4, bp.atk_stage + atk_buff))
        bp.def_stage = max(-4, min(4, bp.def_stage + def_buff))

    # Rebuild charged move identity index
    bp._cm_id_to_idx = {id(cm): i for i, cm in enumerate(bp.charged_moves)}

    # Invalidate damage caches on both sides
    bp._dmg_cache_opp_id = -1
    opponent._dmg_cache_opp_id = -1

    bp._form_is_alt = not bp._form_is_alt
