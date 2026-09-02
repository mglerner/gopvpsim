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

from .moves import get_moves, parse_types
from .pokemon import CPM, cp, effective_stats, get_pokemon_entry_by_id


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
    # Multi-id constraint (gamemaster `moveIDs`, plural -- Cramorant's
    # DIVE/SURF list). Empty for single-moveId forms; matches_move checks both.
    move_ids: tuple = ()
    # Index (into FormChangeConfig.forms) of the form this changes INTO when
    # the trigger fires. None means "resolve dynamically" (gamemaster
    # alternativeFormId 'variable' -- Cramorant's HP-conditional prey pick,
    # resolved at the battle.py charged_move trigger site).
    target_idx: "int | None" = None

    def matches_move(self, move_id: str) -> bool:
        """True when ``move_id`` satisfies this form's trigger constraint
        (PvPoke Battle.js:1609-1610: moveId == 'ANY', exact moveId match,
        or membership in the plural moveIDs list)."""
        return (self.move_id == 'ANY'
                or self.move_id == move_id
                or move_id in self.move_ids)


@dataclass(frozen=True, slots=True)
class FormChangeConfig:
    """Precomputed form-change state for a BattlePokemon."""
    forms: tuple              # FormData per form -- [0]=starting form; 2 for
                              # toggle/one-way species, 3 for Cramorant
                              # ([0]=base, [1]=Gulping, [2]=Gorging; the
                              # variable-target resolution depends on that order)
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

# Every move id a form change can swap in at battle time, keyed by the id a
# stored moveset might actually list. A form change reads the mapped-to move
# from the gamemaster (_swap_fast_move / _swap_charged_move) even though it is
# NOT in the stored moveset. Cache migration uses this to expand the "moves the
# battle reads" set (see form_change_swapped_moves).
_FORM_CHANGE_MOVE_SWAPS = {**_AEGISLASH_FAST_MOVE_MAP, **_MORPEKO_CHARGED_MOVE_MAP}

# Moves a form change can cause the battle to READ without any swap: a
# Cramorant moveset listing DIVE or SURF makes the battle read the Gulp
# Missile entries (fired from the extra-charged registry, never in the
# stored moveset). Keyed by trigger move so form_change_swapped_moves can
# stay a pure function of move ids; unioning these for a NON-Cramorant
# DIVE/SURF user is over-broad in the safe direction (cache invalidation
# re-sims a column it didn't need to, never serves a stale one).
_FORM_CHANGE_TRIGGERED_MOVES = {
    'DIVE': ('GULP_MISSILE_ARROKUDA', 'GULP_MISSILE_PIKACHU'),
    'SURF': ('GULP_MISSILE_ARROKUDA', 'GULP_MISSILE_PIKACHU'),
}


def form_change_swapped_moves(move_ids):
    """Return the ADDITIONAL move ids a form change could swap in for ``move_ids``.

    A stored moveset lists only one side of each swap (e.g. Aegislash's default
    GL fast move is the AEGISLASH_CHARGE_* variant, never the plain counterpart
    it reverts to; Morpeko stores one Aura Wheel). Battle code reads the mapped
    counterpart at form-change time, so a consumer reasoning about "which move
    entries this battle reads" (e.g. gamemaster-delta cache invalidation) must
    union in these. Cramorant's Gulp Missiles are the no-swap case of the same
    contract: DIVE/SURF in a moveset make the battle read the missile entries.
    Returns an empty set when nothing is swappable.
    """
    move_ids = tuple(move_ids)   # callers pass generators (migrate_cache);
                                 # we iterate twice
    extra = {_FORM_CHANGE_MOVE_SWAPS[m] for m in move_ids
             if m in _FORM_CHANGE_MOVE_SWAPS}
    for m in move_ids:
        extra.update(_FORM_CHANGE_TRIGGERED_MOVES.get(m, ()))
    return extra


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _swap_charged_move(charged_moves, move_map):
    """Return a new tuple of charged move dicts with any mapped moves swapped.

    Swapped-in moves are copied: the gamemaster's move dicts are global,
    and battle code mutates move dicts in place (`_cached_damage`,
    `_turns`). Without the copy, two BattlePokemon whose form changes
    swap in the same move (e.g. a Morpeko mirror) would share one dict
    and cross-contaminate each other's per-battle damage memo.
    """
    _, all_charged = get_moves()
    result = []
    for cm in charged_moves:
        mid = cm['moveId']
        if mid in move_map:
            alt_id = move_map[mid]
            result.append(dict(all_charged[alt_id]))
        else:
            result.append(cm)
    return tuple(result)


def _swap_fast_move(fast_move, move_map):
    """Return a copy of the alternate fast move dict if mapped, else the
    same move (copied for the same shared-global-dict reason as
    _swap_charged_move)."""
    mid = fast_move['moveId']
    if mid in move_map:
        all_fast, _ = get_moves()
        return dict(all_fast[move_map[mid]])
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
    """Compute Aegislash Shield form level from Blade form level (reverse).

    Mirrors PvPoke getFormStats() aegislash_shield branch. The formula
    deliberately overshoots; the caller walks down whole levels until CP
    fits. We clamp the start to our level cap (max CPM table key, 51.0):
    a low-IV Blade caps at level ~25 in GL, putting the raw formula at
    52+, past the end of OUR CPM table -- the eager per-IV config build
    crashed on it (KeyError: 52.0, first Aegislash (Blade) GL dive after
    arc S1). PvPoke does NOT overflow there: its cpms table reaches level
    55, so it walks down from 52 using above-cap CPM values that don't
    exist in-game (a genuine overflow needs a start past 55). The clamp
    is therefore a deliberate divergence, not a mirror -- PvPoke's
    shield-revert stats can sit above ours (up to CPM(55) vs our
    CPM(51)). See DEVELOPER_NOTES "Known divergences" item 3 and
    bug-hunt round-2 FC-2; the upstream bug-report draft claiming this
    overflow was PvPoke's was retracted 2026-07-16 (our bug only).
    """
    if league_cp <= 1500:
        start = (blade_level / 0.5) + 2
    elif league_cp <= 2500:
        start = round(blade_level / 0.75)
    else:
        return blade_level
    return min(float(start), max(CPM))


def _build_variable_form_change(mon_entry, fc, atk_iv, def_iv, level, shadow,
                                fast_move, charged_moves):
    """Build the 3-form FormChangeConfig for a 'variable' form change (Cramorant).

    forms = (base, Gulping, Gorging) -- battle.py's variable-target
    resolution (prey pick by HP fraction, PvPoke Battle.js:1611-1623)
    depends on that order. All three Cramorant forms share base stats,
    types, level, and move pools; the real deltas are the display name,
    species_id (the AI/shield gates key on it), and the exit trigger
    (DIVE/SURF from base via the plural moveIDs list; the form's own Gulp
    Missile from a prey form, which reverts to base). The prey form ids
    are hardcoded exactly like PvPoke's switch(attacker.speciesId)
    (Battle.js:1613-1622) -- the gamemaster does not enumerate the
    'variable' options anywhere.
    """
    species_id = mon_entry['speciesId']
    if species_id != 'cramorant':
        raise ValueError(
            f"alternativeFormId 'variable' is only implemented for cramorant "
            f"(got {species_id!r}); mirror PvPoke's Battle.js switch when a "
            f"new variable form-changer ships")

    cm_tuple = tuple(charged_moves)
    cpm = CPM[level]

    def _fd(entry, trigger, move_id, move_ids, target_idx):
        base = entry['baseStats']
        atk, def_ = effective_stats((base['atk'] + atk_iv) * cpm,
                                    (base['def'] + def_iv) * cpm, shadow)
        raw = entry.get('nativeStatBuffs')
        native = tuple(raw) if raw and any(b != 0 for b in raw) else None
        return FormData(
            species=entry['speciesName'],
            species_id=entry['speciesId'],
            types=tuple(parse_types(entry)),
            atk=atk,
            def_=def_,
            fast_move=fast_move,
            charged_moves=cm_tuple,
            trigger=trigger,
            move_id=move_id,
            native_stat_buffs=native,
            move_ids=move_ids,
            target_idx=target_idx,
        )

    base_fd = _fd(mon_entry, fc.get('trigger'), fc.get('moveId'),
                  tuple(fc.get('moveIDs', ())), None)
    prey_fds = []
    for prey_id in ('cramorant_gulping', 'cramorant_gorging'):
        entry = get_pokemon_entry_by_id(prey_id)
        pfc = entry.get('formChange', {})
        prey_fds.append(_fd(entry, pfc.get('trigger'), pfc.get('moveId'),
                            (), 0))

    return FormChangeConfig(
        forms=(base_fd, *prey_fds),
        reset_on_switch=fc.get('resetOnSwitch', True),
        effect=fc.get('effect'),
    )


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

    # Cramorant: alternativeFormId 'variable' -- the target form is resolved
    # at battle time (HP-conditional prey pick), and there are THREE forms.
    if alt_id == 'variable':
        return _build_variable_form_change(
            mon_entry, fc, atk_iv, def_iv, level, shadow,
            fast_move, charged_moves)

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
    alt_atk, alt_def = effective_stats((alt_base['atk'] + atk_iv) * alt_cpm,
                                       (alt_base['def'] + def_iv) * alt_cpm,
                                       shadow)

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
    default_atk, default_def = effective_stats(
        (mon_entry['baseStats']['atk'] + atk_iv) * CPM[level],
        (mon_entry['baseStats']['def'] + def_iv) * CPM[level],
        shadow)
    default_fd = FormData(
        species=mon_entry['speciesName'],
        species_id=species_id,
        types=default_types,
        atk=default_atk,
        def_=default_def,
        fast_move=fast_move,
        charged_moves=tuple(charged_moves),
        trigger=trigger,
        move_id=fc.get('moveId'),
        native_stat_buffs=default_native_buffs,
        target_idx=1,
    )

    alt_trigger = alt_fc.get('trigger')
    # For toggle types, the alt form should use the same trigger as the default
    # so it can toggle back (e.g. Morpeko Hangry has no formChange in gamemaster
    # but needs to toggle back to Full Belly on the next charged move).
    form_type = fc.get('type')
    if form_type == 'toggle' and alt_trigger is None:
        alt_trigger = trigger
    alt_fd = FormData(
        species=alt_entry['speciesName'],
        species_id=alt_species_id,
        types=alt_types,
        atk=alt_atk,
        def_=alt_def,
        fast_move=alt_fast_move,
        charged_moves=alt_charged_moves,
        trigger=alt_trigger if alt_trigger != 'none' else None,
        move_id=fc.get('moveId') if form_type == 'toggle' and alt_fc.get('moveId') is None else alt_fc.get('moveId'),
        native_stat_buffs=alt_native_buffs,
        target_idx=0,
    )

    reset_on_switch = fc.get('resetOnSwitch', True)
    effect = fc.get('effect')

    return FormChangeConfig(
        forms=(default_fd, alt_fd),
        reset_on_switch=reset_on_switch,
        effect=effect,
    )


def attach_form_change(bp, mon_entry, atk_iv, def_iv, sta_iv,
                       level, league_cp, shadow):
    """Build and attach form-change state to a BattlePokemon.

    No-op (returns None) for species without a form change. The single
    canonical attach path — used by BattlePokemon.from_pokemon and by
    the deep-dive workers that construct BattlePokemon from raw stats.

    Must be called with bp's own fast_move/charged_moves already in
    place (the FormData for the default form references those dicts).
    """
    fc = build_form_change_state(
        mon_entry, atk_iv, def_iv, sta_iv,
        level, league_cp, shadow,
        bp.fast_move, bp.charged_moves,
    )
    if fc is not None:
        bp._form_change = fc
        if fc.effect == 'protect':
            bp._form_disguise_active = True
        # Extra-charged registry (PvPoke's extraChargedMovePool): moves the
        # battle can fire that are never in the selectable moveset -- today
        # only Cramorant's Gulp Missiles. Keyed by moveId; per-instance dict
        # COPIES because battle code mutates move dicts in place (same
        # aliasing hazard as _swap_charged_move). Built from the STARTING
        # entry's list, like PvPoke's constructor. The 13 supermegas also
        # carry extraChargedMoves but have no formChange, so they never get
        # here -- their third move is selected into the moveset instead (the
        # dive/oracle paths pass it in `charged_moves`), which is why this
        # registry stays Cramorant-only.
        #
        # NB the reason this comment used to give was that
        # hasThirdChargedMove() "hard-returns false". That stopped being true
        # at pvpoke 574aeb0da, where it became `self.hasTag("mega")`.
        extra = mon_entry.get('extraChargedMoves')
        if extra:
            _, all_charged = get_moves()
            bp._extra_charged = {mid: dict(all_charged[mid]) for mid in extra}
    # A focal that STARTS in a natively stat-buffed form (currently only
    # Mimikyu (Busted), nativeStatBuffs [0,-1]) carries those stages from
    # turn one. This must run even when fc is None: a terminal alt form has
    # no formChange of its own, so build_form_change_state returns None, yet
    # the static buff still applies for the whole battle. Persist as the
    # battle-start stages so reset_for_battle restores them per scenario.
    raw = mon_entry.get('nativeStatBuffs')
    if raw and any(b != 0 for b in raw):
        bp.initial_atk_stage = max(-4, min(4, raw[0]))
        bp.initial_def_stage = max(-4, min(4, raw[1]))
        bp.atk_stage = bp.initial_atk_stage
        bp.def_stage = bp.initial_def_stage
    return fc


# ---------------------------------------------------------------------------
# Runtime form change
# ---------------------------------------------------------------------------

def apply_form_change(bp, opponent, target_idx=None):
    """Apply a form change to a BattlePokemon. Mutates bp in place.

    Swaps species, types, atk, def_, fast_move, charged_moves to the
    target form's precomputed values. Does NOT change hp or max_hp
    (matches PvPoke's commented-out hp line). Applies nativeStatBuffs
    as stat stage adjustments. Invalidates damage caches on both sides.

    Args:
        bp: the BattlePokemon changing forms
        opponent: the opposing BattlePokemon (for cache invalidation)
        target_idx: index into cfg.forms of the form to enter. None (the
            default) is the 2-form toggle -- the other form -- and is
            only valid for 2-form configs; multi-form species (Cramorant)
            must pass the resolved target explicitly.
    """
    cfg = bp._form_change
    if target_idx is None:
        if len(cfg.forms) != 2:
            raise ValueError(
                'apply_form_change default toggle is only valid for 2-form '
                f'configs; this one has {len(cfg.forms)} forms -- pass '
                'target_idx explicitly (guard from the 2026-08-24 review: '
                '1 - _form_idx would index -1 from a third form)')
        target_idx = 1 - bp._form_idx
    fd = cfg.forms[target_idx]

    bp.species = fd.species
    bp.types = list(fd.types)
    bp.atk = fd.atk
    bp.def_ = fd.def_
    bp.fast_move = fd.fast_move
    # Ensure _turns is set on the new fast move (normally set in simulate() setup)
    if '_turns' not in bp.fast_move:
        bp.fast_move['_turns'] = bp.fast_move.get('cooldown', 500) // 500
    bp.charged_moves = list(fd.charged_moves)

    # Do NOT change bp.hp or bp.max_hp (PvPoke behavior)

    # Apply native stat buffs when entering this form
    if fd.native_stat_buffs is not None:
        atk_buff, def_buff = fd.native_stat_buffs
        bp.atk_stage = max(-4, min(4, bp.atk_stage + atk_buff))
        bp.def_stage = max(-4, min(4, bp.def_stage + def_buff))

    # Rebuild charged move identity index
    bp._cm_id_to_idx = {id(cm): i for i, cm in enumerate(bp.charged_moves)}
    # The Mega Bonus factors are per-move-dict, and the moves were just
    # rebound; the SPECIES also changed, so re-resolve the Mega Level too
    # (no mega has a formChange today, but nothing here depends on that).
    from .pokemon import mega_level as _ml
    bp.mega_level = _ml(bp.species)
    bp._refresh_mega_mults()

    # Invalidate damage + DP setup caches on both sides
    bp._dmg_cache_opp = None
    opponent._dmg_cache_opp = None
    bp._dp_cache = None
    opponent._dp_cache = None
    # PvPoke re-runs resetMoves() ONLY for the pokemon that changed form
    # (Pokemon.js changeForm -> resetMoves), so ONLY the form-changer's frozen
    # move selection (ordering / raw dpe / best_idx) is recomputed. The
    # opponent keeps its frozen selection against the pre-change state -- its
    # _dp_cache above is reset only to refresh the FRESH per-stage damage
    # tables vs bp's new stats, not the frozen selection. Resetting the
    # opponent's _dp_init_cache here would wrongly re-select its move against
    # bp's new form (an NB-1-class staleness divergence). See
    # BattlePokemon._ensure_dp_init_cache.
    bp._dp_init_cache = None

    bp._form_idx = target_idx
