"""
Move data and damage formula.

Damage formula: floor(0.5 * BONUS * power * atk / def * effectiveness * stab) + 1

Type effectiveness uses PoGo's adjusted multipliers:
  immune / double resist → 0.390625  (mainline: 0 or 0.25)
  not very effective     → 0.625  (mainline: 0.5)
  neutral                → 1.0
  super effective        → 1.6    (mainline: 2; stored as float32(1.6), SUPER_EFFECTIVE)
  double super effective → ~2.56  (float32(1.6)^2; computed automatically for dual types)

Note: PoGo has no true immunities — 0.390625 is used instead of 0.
"""
import math

from .data import load_gamemaster

# Damage constants are the float32-truncated values the game (and PvPoke's
# DamageCalculator.js) actually use, NOT exact 1.2/1.3/1.6: the game computes
# damage in single precision, so ~0.009% of calcs land one integer higher than
# exact doubles would -- precisely on the breakpoint/bulkpoint boundaries that
# are this project's deliverable. Matching them makes our boundaries agree with
# PvPoke and the game. (0.625 / 0.390625 resist cells are exact in float32.)
STAB_MULTIPLIER = 1.2000000476837158203125    # float32(1.2) = PvPoke STAB
BONUS = 1.2999999523162841796875              # float32(1.3) = PvPoke BONUS (chargeMultiplier=1 in sim)
SUPER_EFFECTIVE = 1.60000002384185791015625   # float32(1.6) = PvPoke SUPER_EFFECTIVE

# Mega Evolution bonus (PvPoke DamageCalculator.js:10, added 574aeb0da).
# Indexed by megaLevel - 1, so MEGA_BONUS[3] is Mega Level 4 ("Super Max").
# Same float32-truncated treatment as the constants above -- indices 2 and 3
# are bit-identical to STAB_MULTIPLIER and BONUS respectively, which is the
# tell that Niantic stores them as float32 too.
#
# This applies ONLY to a mega-tagged attacker throwing a mega-EXCLUSIVE
# charged move (`isMegaMove`, the 13 `*_PLUS` ids) -- never to a mega's
# ordinary moves, and never to a non-mega. See mega_multiplier().
MEGA_BONUS = (
    1.0,
    1.10000002384185791015625,   # float32(1.1)
    1.2000000476837158203125,    # float32(1.2)
    1.2999999523162841796875,    # float32(1.3)
)


def mega_multiplier(move, mega_level):
    """Return the Mega Bonus damage factor for ``move``, or 1.0.

    ``mega_level`` is the attacker's Mega Level (1-4) when the attacker is
    mega-tagged, or None when it is not a mega. PvPoke's gate is
    ``attacker.hasTag("mega") && move?.isMegaMove`` (DamageCalculator.js:40);
    ``mega_level=None`` encodes the first half, ``isMegaMove`` the second.

    PvPoke indexes MEGA_BONUS without a bounds check, so an out-of-range
    level yields ``undefined`` and NaN damage. We raise instead -- there is
    no legal path to it, and a silent NaN would poison a whole sweep.
    """
    if mega_level is None or not move.get('isMegaMove'):
        return 1.0
    if not 1 <= mega_level <= 4:
        raise ValueError(
            f"mega_level must be 1-4, got {mega_level!r} for "
            f"{move.get('moveId')!r}")
    return MEGA_BONUS[mega_level - 1]

# ---------------------------------------------------------------------------
# Type effectiveness table — effectiveness[attacker_type][defender_type]
# Values are PoGo-adjusted multipliers (not mainline 0/0.5/1/2).
# For dual-type defenders, multiply the two individual values.
# Double resist = 0.390625 = 0.625^2 (exact, matching PvPoke).
# ---------------------------------------------------------------------------

_EFFECTIVENESS_RAW = {
    'normal': {
        'normal': 1.0,        'fire': 1.0,   'water': 1.0,   'electric': 1.0,
        'grass':  1.0,        'ice':  1.0,   'fighting': 1.0, 'poison': 1.0,
        'ground': 1.0,        'flying': 1.0, 'psychic': 1.0,  'bug': 1.0,
        'rock':   0.625,      'ghost': 0.390625,'dragon': 1.0,'dark': 1.0,
        'steel':  0.625,      'fairy': 1.0,
    },
    'fire': {
        'normal': 1.0,   'fire': 0.625, 'water': 0.625,  'electric': 1.0,
        'grass':  1.6,   'ice':  1.6,   'fighting': 1.0,  'poison': 1.0,
        'ground': 1.0,   'flying': 1.0, 'psychic': 1.0,   'bug': 1.6,
        'rock':   0.625, 'ghost': 1.0,  'dragon': 0.625,  'dark': 1.0,
        'steel':  1.6,   'fairy': 1.0,
    },
    'water': {
        'normal': 1.0,   'fire': 1.6,   'water': 0.625,  'electric': 1.0,
        'grass':  0.625, 'ice':  1.0,   'fighting': 1.0,  'poison': 1.0,
        'ground': 1.6,   'flying': 1.0, 'psychic': 1.0,   'bug': 1.0,
        'rock':   1.6,   'ghost': 1.0,  'dragon': 0.625,  'dark': 1.0,
        'steel':  1.0,   'fairy': 1.0,
    },
    'electric': {
        'normal': 1.0,   'fire': 1.0,   'water': 1.6,    'electric': 0.625,
        'grass':  0.625, 'ice':  1.0,   'fighting': 1.0,  'poison': 1.0,
        'ground': 0.390625, 'flying': 1.6, 'psychic': 1.0,   'bug': 1.0,
        'rock':   1.0,   'ghost': 1.0,  'dragon': 0.625,  'dark': 1.0,
        'steel':  1.0,   'fairy': 1.0,
    },
    'grass': {
        'normal': 1.0,   'fire': 0.625, 'water': 1.6,    'electric': 1.0,
        'grass':  0.625, 'ice':  1.0,   'fighting': 1.0,  'poison': 0.625,
        'ground': 1.6,   'flying': 0.625,'psychic': 1.0,  'bug': 0.625,
        'rock':   1.6,   'ghost': 1.0,  'dragon': 0.625,  'dark': 1.0,
        'steel':  0.625, 'fairy': 1.0,
    },
    'ice': {
        'normal': 1.0,   'fire': 0.625, 'water': 0.625,  'electric': 1.0,
        'grass':  1.6,   'ice':  0.625, 'fighting': 1.0,  'poison': 1.0,
        'ground': 1.6,   'flying': 1.6, 'psychic': 1.0,   'bug': 1.0,
        'rock':   1.0,   'ghost': 1.0,  'dragon': 1.6,    'dark': 1.0,
        'steel':  0.625, 'fairy': 1.0,
    },
    'fighting': {
        'normal': 1.6,   'fire': 1.0,   'water': 1.0,    'electric': 1.0,
        'grass':  1.0,   'ice':  1.6,   'fighting': 1.0,  'poison': 0.625,
        'ground': 1.0,   'flying': 0.625,'psychic': 0.625,'bug': 0.625,
        'rock':   1.6,   'ghost': 0.390625,'dragon': 1.0,    'dark': 1.6,
        'steel':  1.6,   'fairy': 0.625,
    },
    'poison': {
        'normal': 1.0,   'fire': 1.0,   'water': 1.0,    'electric': 1.0,
        'grass':  1.6,   'ice':  1.0,   'fighting': 1.0,  'poison': 0.625,
        'ground': 0.625, 'flying': 1.0, 'psychic': 1.0,   'bug': 1.0,
        'rock':   0.625, 'ghost': 0.625,'dragon': 1.0,    'dark': 1.0,
        'steel':  0.390625, 'fairy': 1.6,
    },
    'ground': {
        'normal': 1.0,   'fire': 1.6,   'water': 1.0,    'electric': 1.6,
        'grass':  0.625, 'ice':  1.0,   'fighting': 1.0,  'poison': 1.6,
        'ground': 1.0,   'flying': 0.390625,'psychic': 1.0,  'bug': 0.625,
        'rock':   1.6,   'ghost': 1.0,  'dragon': 1.0,    'dark': 1.0,
        'steel':  1.6,   'fairy': 1.0,
    },
    'flying': {
        'normal': 1.0,   'fire': 1.0,   'water': 1.0,    'electric': 0.625,
        'grass':  1.6,   'ice':  1.0,   'fighting': 1.6,  'poison': 1.0,
        'ground': 1.0,   'flying': 1.0, 'psychic': 1.0,   'bug': 1.6,
        'rock':   0.625, 'ghost': 1.0,  'dragon': 1.0,    'dark': 1.0,
        'steel':  0.625, 'fairy': 1.0,
    },
    'psychic': {
        'normal': 1.0,   'fire': 1.0,   'water': 1.0,    'electric': 1.0,
        'grass':  1.0,   'ice':  1.0,   'fighting': 1.6,  'poison': 1.6,
        'ground': 1.0,   'flying': 1.0, 'psychic': 0.625, 'bug': 1.0,
        'rock':   1.0,   'ghost': 1.0,  'dragon': 1.0,    'dark': 0.390625,
        'steel':  0.625, 'fairy': 1.0,
    },
    'bug': {
        'normal': 1.0,   'fire': 0.625, 'water': 1.0,    'electric': 1.0,
        'grass':  1.6,   'ice':  1.0,   'fighting': 0.625,'poison': 0.625,
        'ground': 1.0,   'flying': 0.625,'psychic': 1.6,  'bug': 1.0,
        'rock':   1.0,   'ghost': 0.625,'dragon': 1.0,    'dark': 1.6,
        'steel':  0.625, 'fairy': 0.625,
    },
    'rock': {
        'normal': 1.0,   'fire': 1.6,   'water': 1.0,    'electric': 1.0,
        'grass':  1.0,   'ice':  1.6,   'fighting': 0.625,'poison': 1.0,
        'ground': 0.625, 'flying': 1.6, 'psychic': 1.0,   'bug': 1.6,
        'rock':   1.0,   'ghost': 1.0,  'dragon': 1.0,    'dark': 1.0,
        'steel':  0.625, 'fairy': 1.0,
    },
    'ghost': {
        'normal': 0.390625, 'fire': 1.0,   'water': 1.0,    'electric': 1.0,
        'grass':  1.0,   'ice':  1.0,   'fighting': 1.0,  'poison': 1.0,
        'ground': 1.0,   'flying': 1.0, 'psychic': 1.6,   'bug': 1.0,
        'rock':   1.0,   'ghost': 1.6,  'dragon': 1.0,    'dark': 0.625,
        'steel':  1.0,   'fairy': 1.0,
    },
    'dragon': {
        'normal': 1.0,   'fire': 1.0,   'water': 1.0,    'electric': 1.0,
        'grass':  1.0,   'ice':  1.0,   'fighting': 1.0,  'poison': 1.0,
        'ground': 1.0,   'flying': 1.0, 'psychic': 1.0,   'bug': 1.0,
        'rock':   1.0,   'ghost': 1.0,  'dragon': 1.6,    'dark': 1.0,
        'steel':  0.625, 'fairy': 0.390625,
    },
    'dark': {
        'normal': 1.0,   'fire': 1.0,   'water': 1.0,    'electric': 1.0,
        'grass':  1.0,   'ice':  1.0,   'fighting': 0.625,'poison': 1.0,
        'ground': 1.0,   'flying': 1.0, 'psychic': 1.6,   'bug': 1.0,
        'rock':   1.0,   'ghost': 1.6,  'dragon': 1.0,    'dark': 0.625,
        'steel':  1.0,   'fairy': 0.625,
    },
    'steel': {
        'normal': 1.0,   'fire': 0.625, 'water': 0.625,  'electric': 0.625,
        'grass':  1.0,   'ice':  1.6,   'fighting': 1.0,  'poison': 1.0,
        'ground': 1.0,   'flying': 1.0, 'psychic': 1.0,   'bug': 1.0,
        'rock':   1.6,   'ghost': 1.0,  'dragon': 1.0,    'dark': 1.0,
        'steel':  0.625, 'fairy': 1.6,
    },
    'fairy': {
        'normal': 1.0,   'fire': 0.625, 'water': 1.0,    'electric': 1.0,
        'grass':  1.0,   'ice':  1.0,   'fighting': 1.6,  'poison': 0.625,
        'ground': 1.0,   'flying': 1.0, 'psychic': 1.0,   'bug': 1.0,
        'rock':   1.0,   'ghost': 1.0,  'dragon': 1.6,    'dark': 1.6,
        'steel':  0.625, 'fairy': 1.0,
    },
}

# Normalize super-effective cells (authored as the readable literal 1.6) to the
# float32-truncated constant the game uses (PvPoke DamageMultiplier.SUPER_EFFECTIVE);
# 0.625 / 0.390625 / 1.0 are exact in float32 and pass through unchanged. Done once
# here so type_effectiveness()'s per-lookup hot path stays branch-free. Dual-type
# effectiveness (the product of two cells) then yields SUPER_EFFECTIVE**2 for
# double-SE, matching PvPoke rather than exact 2.56.
EFFECTIVENESS = {atk: {d: (SUPER_EFFECTIVE if v == 1.6 else v) for d, v in row.items()}
                 for atk, row in _EFFECTIVENESS_RAW.items()}

# ---------------------------------------------------------------------------
# Gamemaster access
# ---------------------------------------------------------------------------

_fast_moves    = None
_charged_moves = None


def get_moves():
    """Return (fast_moves, charged_moves) dicts keyed by moveId. Cached."""
    global _fast_moves, _charged_moves
    if _fast_moves is None:
        gm = load_gamemaster()
        _fast_moves    = {m['moveId']: m for m in gm['moves'] if m['energyGain'] != 0}
        _charged_moves = {m['moveId']: m for m in gm['moves'] if m['energyGain'] == 0}
        # Add derived properties matching PvPoke's GameMaster.js lines 859-875.
        # Key: selfBuffing requires buffApplyChance == 1 (guaranteed),
        #      selfDebuffing requires buffApplyChance >= 0.5.
        for m in _charged_moves.values():
            buffs  = m.get('buffs')
            bt     = m.get('buffTarget')
            chance = float(m.get('buffApplyChance', 0) or 0)
            mid    = m.get('moveId', '')
            # selfDebuffing: chance >= 0.5, self-targeting, negative buff,
            # with DRAGON_ASCENT excluded (PvPoke line 859)
            m['selfDebuffing'] = bool(
                buffs and bt == 'self' and chance >= 0.5
                and mid != 'DRAGON_ASCENT'
                and (buffs[0] < 0 or buffs[1] < 0))
            # selfAttackDebuffing / selfDefenseDebuffing: subsets of selfDebuffing
            m['selfAttackDebuffing']  = bool(m['selfDebuffing'] and buffs[0] < 0)
            m['selfDefenseDebuffing'] = bool(m['selfDebuffing'] and buffs[1] < 0)
            # selfBuffing: PvPoke GameMaster.js:873 — guaranteed positive
            # self-buff OR guaranteed opponent debuff (any kind).  The name is
            # misleading but PvPoke uses the same flag for both categories
            # (Psychic Fangs, Sand Tomb, Acid Spray, etc. all count).
            # buffTarget 'both' (OBSTRUCT) qualifies via a positive buffsSelf.
            bs = m.get('buffsSelf')
            m['selfBuffing'] = bool(
                buffs and chance == 1
                and ((bt == 'opponent')
                     or (bt == 'self' and (buffs[0] > 0 or buffs[1] > 0))
                     or (bt == 'both' and bs is not None
                         and (bs[0] > 0 or bs[1] > 0))))
    return _fast_moves, _charged_moves


# ---------------------------------------------------------------------------
# Damage calculation
# ---------------------------------------------------------------------------

def parse_types(mon: dict) -> list[str]:
    """Extract a Pokemon's type list from a gamemaster entry, filtering placeholder 'none' values.

    Single-type Pokemon are stored as e.g. ['steel', 'none'] in PvPoke's gamemaster.

    Lives here (not data.py) because it is damage-affecting -- it produces the
    type lists that reach type_effectiveness()/stab() on every damage calc --
    and must sit inside the engine-hashed closure (sweep_cache._ENGINE_FILES)
    so an edit to it invalidates cached sweep columns.
    """
    types = mon.get('types', [mon.get('type1', 'normal')])
    if isinstance(types, str):
        types = [types]
    return [t for t in types if t and t != 'none']


def type_effectiveness(move_type, defender_types):
    """Combined type effectiveness multiplier for a move vs a defender.

    defender_types: sequence of 1 or 2 type strings.
    Dual-type effectiveness is the product of the two individual values,
    which naturally gives 0.390625 for double resist and 2.56 for double SE.
    """
    result = 1.0
    for dtype in defender_types:
        result *= EFFECTIVENESS[move_type][dtype]
    return result


def stab(move_type, attacker_types):
    """Return STAB multiplier: 1.2 if move type matches an attacker type, else 1.0."""
    return STAB_MULTIPLIER if move_type in attacker_types else 1.0


def damage_constant(power, move_type, attacker_types, defender_types,
                    mega_mult=1.0):
    """K -- the attack/defense-INDEPENDENT part of the damage formula.

        damage(...) == floor(K * atk / def_) + 1

    This is the single definition of the damage formula's constant half, and
    the ONLY place the operand order is spelled out. Two kinds of caller need
    it separately from :func:`damage`:

    * the breakpoint / bulkpoint solvers, which INVERT the formula
      (``atk = (D - 1) * def_ / K``, ``def_ = K * atk / D``) and therefore
      cannot go through ``damage()`` at all;
    * the vectorized numpy mirror in ``scripts/deep_dive_signature.py``,
      which evaluates the same formula across whole IV arrays at once.

    Both used to re-spell ``0.5 * BONUS * power * stab * eff`` inline -- four
    and one copies respectively. That is the same unforced-copy shape that
    let the shadow multiplier rot (DEVELOPER_NOTES "Engine constant
    sourcing"), and it is why ``pokemon.effective_stats`` exists; this is the
    same treatment for the damage constant.

    OPERAND ORDER IS LOAD-BEARING. Float multiplication is not associative,
    so ``0.5*BONUS*power*stab*eff`` then ``*atk/def_`` is not bit-identical to
    ``0.5*BONUS*power*atk/def_*eff*stab`` on inputs that land within an ulp of
    an integer -- measured at 0 / 400,000 random realistic inputs but
    21,412 / 5,733,000 constructed ulp-boundary probes. The order here is the
    one the solvers already used, so routing them through this function moves
    nothing; ``damage()`` now shares it, which makes the solver round-trip
    exact BY CONSTRUCTION instead of by luck. Do not reorder these operands
    without a cold re-bake.
    """
    eff   = type_effectiveness(move_type, defender_types)
    stab_ = stab(move_type, attacker_types)
    return 0.5 * BONUS * power * stab_ * eff * mega_mult


def damage(power, atk, def_, move_type, attacker_types, defender_types,
           mega_mult=1.0):
    """Compute damage dealt by one move.

    floor(K * atk / def) + 1, with K from :func:`damage_constant`

    Args:
        power:          move's base power
        atk:            attacker's effective attack stat
        def_:           defender's effective defense stat
        move_type:      move's type string (e.g. 'water')
        attacker_types: sequence of attacker's type strings (for STAB)
        defender_types: sequence of defender's type strings (for effectiveness)
        mega_mult:      Mega Bonus factor from :func:`mega_multiplier`; 1.0
                        (an exact float identity) for everything that is not
                        a mega throwing its mega-exclusive charged move.

    This is the ONE place the Mega Bonus is applied. PvPoke computes
    ``move.damage`` (and therefore ``move.dpe``) through the same
    DamageCalculator (Pokemon.js:882/890), so its shuffle, bestChargedMove,
    DP and every bandaid already see the boosted number -- injecting here
    reproduces that for free. Do NOT add a second injection at
    damage-dealing time.

    PvPoke places the factor differently in its two damage functions
    (after chargeMultiplier in ``damage()``, before ``effectiveness`` in
    ``damageByStats()``), and our operand order is a third one. All three
    agree on every captured mega fixture. ``mega_mult`` is exactly 1.0 off
    the mega path and ``x * 1.0`` is an exact identity, so no non-mega
    damage can move because of it.
    """
    k = damage_constant(power, move_type, attacker_types, defender_types,
                        mega_mult)
    return math.floor(k * atk / def_) + 1
