"""
Battle simulation loop with pluggable shield/bait policies.

Turn model (ported from PvPoke's Battle.js):
- Each turn = 500 ms.
- A Pokemon with cooldown == 0 chooses an action each turn.
- Fast move: queued on turn T with duration D turns.
    - Damage/energy applied on turn T + D - 1 (the last turn of the window).
    - Cooldown resets to 0 so the pokemon can act again on turn T + D.
- Charged move: resolves immediately in the same turn it is chosen.
    - Requires energy >= move cost.
    - If the defender has shields and the shield policy says shield: damage = 1,
      shields -= 1.
    - All cooldowns reset to 0 after any charged move.
- Priority: charged moves resolve before fast moves in the same turn.
  If both throw charged moves, the one with higher effective attack goes first.
- Energy is capped at 100.
- Battle ends when either Pokemon reaches 0 HP, or after MAX_TURNS turns.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from .moves import damage as calc_damage, type_effectiveness, stab

ENERGY_CAP = 100
MAX_TURNS  = 500   # ~4 minutes; prevents infinite loops

# ---------------------------------------------------------------------------
# Optimal charge-move timing
#
# Source: gobattlekit/src/gobattlekit/data/gamemaster.py
#
# Key: (your_fast_turns, their_fast_turns)  — capped at 5 for each
# Value: (start, step) arithmetic sequence of YOUR fast-move counts at which
#        to throw the charge move, or None if timing doesn't matter.
#
# Example: (2, 3) → (1, 3) means throw after your 1st fast move, then your
# 4th, 7th, 10th, ... (i.e. fast_move_count ≥ start and (count−start) % step == 0)
# ---------------------------------------------------------------------------
OPTIMAL_TIMING: dict[tuple[int, int], tuple[int, int] | None] = {
    (1, 1): None,   (1, 2): (1, 2), (1, 3): (2, 3), (1, 4): (3, 4), (1, 5): (4, 5),
    (2, 1): None,   (2, 2): None,   (2, 3): (1, 3), (2, 4): (1, 2), (2, 5): (2, 5),
    (3, 1): None,   (3, 2): (1, 2), (3, 3): None,   (3, 4): (1, 4), (3, 5): (3, 5),
    (4, 1): None,   (4, 2): None,   (4, 3): (2, 3), (4, 4): None,   (4, 5): (1, 5),
    (5, 1): None,   (5, 2): (1, 2), (5, 3): (1, 3), (5, 4): (3, 4), (5, 5): None,
}


# ---------------------------------------------------------------------------
# Shield / charged-move policies
# ---------------------------------------------------------------------------

# ShieldPolicy(attacker_bp, defender_bp, move) -> bool
#   Return True to use a shield.
ShieldPolicy = Callable[["BattlePokemon", "BattlePokemon", dict], bool]

# ChargedMovePolicy(attacker_bp, defender_bp) -> int | None
#   Return index into attacker_bp.charged_moves to throw, or None to fast-move.
ChargedMovePolicy = Callable[["BattlePokemon", "BattlePokemon"], "int | None"]


def always_shield(attacker: "BattlePokemon", defender: "BattlePokemon", move: dict) -> bool:
    return defender.shields > 0

def never_shield(attacker: "BattlePokemon", defender: "BattlePokemon", move: dict) -> bool:
    return False

def use_first_available(attacker: "BattlePokemon", defender: "BattlePokemon") -> "int | None":
    """Throw the first charged move we have enough energy for."""
    for i, move in enumerate(attacker.charged_moves):
        if attacker.energy >= move['energy']:
            return i
    return None

def bait_with_cheapest(attacker: "BattlePokemon", defender: "BattlePokemon") -> "int | None":
    """
    Bait-shield heuristic: if defender has shields, prefer the cheapest charged
    move first; otherwise use the highest-damage move available.
    """
    affordable = [
        (i, m) for i, m in enumerate(attacker.charged_moves)
        if attacker.energy >= m['energy']
    ]
    if not affordable:
        return None
    if defender.shields > 0:
        # Throw cheapest to bait a shield
        return min(affordable, key=lambda im: im[1]['energy'])[0]
    else:
        # No shields — throw highest damage
        return max(affordable, key=lambda im: im[1]['power'])[0]

def no_bait(attacker: "BattlePokemon", defender: "BattlePokemon") -> "int | None":
    """
    Never bait: always fire the affordable move with the highest actual
    damage-per-energy, regardless of whether the defender has shields.
    Corresponds to PvPoke's bait toggle set to 'Off'.
    """
    affordable = [
        (i, m) for i, m in enumerate(attacker.charged_moves)
        if attacker.energy >= m['energy']
    ]
    if not affordable:
        return None
    def actual_dpe(im):
        i, m = im
        return attacker.charged_move_damage(m, defender) / m['energy']
    return max(affordable, key=actual_dpe)[0]

def pvpoke_ai(attacker: "BattlePokemon", defender: "BattlePokemon") -> "int | None":
    """
    Mimic PvPoke's ActionLogic AI:
    - When defender has shields: throw the cheapest affordable move (bait).
    - When defender has no shields: throw the affordable move with the highest
      actual damage-per-energy (bestChargedMove in PvPoke terms).
    Fires as soon as any move is affordable; does not wait for a 'better' move.
    """
    affordable = [
        (i, m) for i, m in enumerate(attacker.charged_moves)
        if attacker.energy >= m['energy']
    ]
    if not affordable:
        return None
    if defender.shields > 0:
        return min(affordable, key=lambda im: im[1]['energy'])[0]
    else:
        def actual_dpe(im):
            i, m = im
            dmg = attacker.charged_move_damage(m, defender)
            return dmg / m['energy']
        return max(affordable, key=actual_dpe)[0]

def optimal_timing(attacker: "BattlePokemon", defender: "BattlePokemon") -> "int | None":
    """
    Fire a charged move only on the optimal fast-move counts, as determined by
    the OPTIMAL_TIMING table keyed on (your_fast_turns, their_fast_turns).

    When timing doesn't matter (None entry) or when the current fast-move count
    is at an optimal point, delegates to pvpoke_ai for move selection.
    Otherwise returns None (queue another fast move instead).

    Note: may lead to losses in some matchups vs always-fire policies because
    waiting for optimal timing means taking extra fast-move damage.
    """
    your_turns  = min(attacker.fast_move.get('_turns', 1), 5)
    their_turns = min(defender.fast_move.get('_turns', 1), 5)
    pattern     = OPTIMAL_TIMING.get((your_turns, their_turns))

    if pattern is None:
        return pvpoke_ai(attacker, defender)

    start, step = pattern
    fm = attacker._fm_since_charge
    on_time = fm >= start and (fm - start) % step == 0
    if on_time:
        return pvpoke_ai(attacker, defender)
    # Not yet at the optimal window — but don't hold energy above the cap;
    # fire anyway if we can't afford to wait.
    if attacker.energy >= ENERGY_CAP:
        return pvpoke_ai(attacker, defender)
    return None


# ---------------------------------------------------------------------------
# BattlePokemon — mutable battle state
# ---------------------------------------------------------------------------

@dataclass
class BattlePokemon:
    """Wraps a Pokemon with the mutable state needed during a battle."""
    species:         str
    types:           list[str]   # 1 or 2 type strings
    atk:             float       # effective attack = (base_atk + atk_iv) * cpm
    def_:            float       # effective defense
    max_hp:          int
    fast_move:       dict        # gamemaster move dict
    charged_moves:   list[dict]  # gamemaster move dicts
    shields:         int = 2
    initial_energy:  int = 0     # energy at battle start (0–100)

    # Mutable battle state
    hp:                 int   = field(init=False)
    energy:             int   = field(init=False)
    cooldown:           int   = field(init=False)   # turns remaining
    _fm_since_charge:   int   = field(init=False, repr=False)  # fast moves since last charge (either player)
    # Queued fast move: (queued_on_turn, move_dict) or None
    _queued_fast:  "tuple[int, dict] | None" = field(init=False, repr=False)

    def __post_init__(self):
        self.hp                = self.max_hp
        self.energy            = min(ENERGY_CAP, max(0, self.initial_energy))
        self.cooldown          = 0
        self._fm_since_charge  = 0
        self._queued_fast      = None

    @classmethod
    def from_pokemon(cls, pokemon, fast_move: dict, charged_moves: list[dict],
                     shields: int = 2, initial_energy: int = 0) -> "BattlePokemon":
        """Build a BattlePokemon from a Pokemon dataclass + move dicts."""
        from .data import load_gamemaster
        gm  = load_gamemaster()
        mon = next(m for m in gm['pokemon'] if m['speciesName'] == pokemon.species)
        types = mon.get('types', [mon.get('type1', 'normal')])
        if isinstance(types, str):
            types = [types]
        return cls(
            species        = pokemon.species,
            types          = types,
            atk            = pokemon.atk,
            def_           = pokemon.def_,
            max_hp         = pokemon.hp,
            fast_move      = fast_move,
            charged_moves  = charged_moves,
            shields        = shields,
            initial_energy = initial_energy,
        )

    def fast_move_damage(self, defender: "BattlePokemon") -> int:
        m = self.fast_move
        return calc_damage(
            m['power'], self.atk, defender.def_,
            m['type'], self.types, defender.types,
        )

    def charged_move_damage(self, move: dict, defender: "BattlePokemon") -> int:
        return calc_damage(
            move['power'], self.atk, defender.def_,
            move['type'], self.types, defender.types,
        )


# ---------------------------------------------------------------------------
# BattleResult
# ---------------------------------------------------------------------------

@dataclass
class BattleResult:
    winner:       "int | None"  # 0, 1, or None for tie / time-out
    turns:        int
    hp_remaining: list[int]     # [p0_hp, p1_hp] at battle end
    energy_remaining: list[int]
    shields_remaining: list[int]
    timeline:     list[str] = field(default_factory=list)  # human-readable log


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def simulate(
    p0: BattlePokemon,
    p1: BattlePokemon,
    *,
    shield_policy_0: ShieldPolicy   = always_shield,
    shield_policy_1: ShieldPolicy   = always_shield,
    charged_policy_0: ChargedMovePolicy = bait_with_cheapest,
    charged_policy_1: ChargedMovePolicy = bait_with_cheapest,
    log: bool = False,
) -> BattleResult:
    """
    Run a 1v1 battle between p0 and p1 and return the result.

    p0 and p1 are mutated in place — reset them before reuse.
    """
    pokemon   = [p0, p1]
    policies  = [
        (charged_policy_0, shield_policy_0),
        (charged_policy_1, shield_policy_1),
    ]
    timeline  = []
    turn      = 0

    # Pre-compute fast move durations (turns = cooldown_ms / 500)
    for p in pokemon:
        p.fast_move['_turns'] = p.fast_move.get('cooldown', 500) // 500

    # Priority: higher effective attack breaks ties on charged moves
    use_priority = (p0.atk != p1.atk)

    def log_event(msg: str):
        if log:
            timeline.append(f"T{turn:>3}: {msg}")

    while turn < MAX_TURNS:
        turn += 1

        # --- 1. Decrement cooldowns ---
        for p in pokemon:
            p.cooldown = max(0, p.cooldown - 1)

        # --- 2. Decide actions ---
        # Each pokemon with cooldown==0 chooses: charged move or fast move.
        # Fast moves are queued; charged moves are collected for this turn.
        charged_actions = []   # list of (actor_index, move_dict)
        fast_landings   = []   # fast moves that land this turn

        for i, p in enumerate(pokemon):
            opponent = pokemon[1 - i]
            charged_pol, _ = policies[i]

            # Check if a previously queued fast move lands this turn
            if p._queued_fast is not None:
                queued_turn, qmove = p._queued_fast
                duration = qmove['_turns']
                if (turn - queued_turn) >= duration - 1:
                    fast_landings.append((i, qmove))
                    p._queued_fast = None

            # Can act (cooldown==0 and no pending fast move)?
            if p.cooldown == 0 and p._queued_fast is None:
                move_idx = charged_pol(p, opponent)
                if move_idx is not None:
                    charged_actions.append((i, p.charged_moves[move_idx]))
                else:
                    # Queue a fast move
                    fm = p.fast_move
                    p._queued_fast = (turn, fm)
                    p.cooldown = fm['_turns']
                    log_event(f"{p.species} uses {fm.get('name', fm['moveId'])}")

        # --- 3. Resolve charged moves (higher priority first) ---
        if use_priority and len(charged_actions) == 2:
            charged_actions.sort(key=lambda ia: pokemon[ia[0]].atk, reverse=True)

        for actor_idx, move in charged_actions:
            attacker = pokemon[actor_idx]
            defender = pokemon[1 - actor_idx]

            if attacker.energy < move['energy']:
                continue   # raced to this — no longer affordable

            _, shield_pol = policies[1 - actor_idx]
            use_shield    = shield_pol(attacker, defender, move)

            attacker.energy -= move['energy']

            if use_shield and defender.shields > 0:
                dmg = 1
                defender.shields -= 1
                log_event(f"{attacker.species} uses {move.get('name', move['moveId'])} → SHIELDED (1 dmg)")
            else:
                dmg = attacker.charged_move_damage(move, defender)
                log_event(f"{attacker.species} uses {move.get('name', move['moveId'])} → {dmg} dmg")

            defender.hp = max(0, defender.hp - dmg)

        # After any charged move this turn, reset all cooldowns and timing counters
        if charged_actions:
            for p in pokemon:
                p.cooldown = 0
                p._queued_fast = None
                p._fm_since_charge = 0

        # --- 4. Resolve fast move landings ---
        for actor_idx, move in fast_landings:
            attacker = pokemon[actor_idx]
            defender = pokemon[1 - actor_idx]

            # A pokemon fainted from a charged move this turn cannot deal fast damage.
            # A pokemon that has already fainted cannot receive fast damage.
            if attacker.hp <= 0 or defender.hp <= 0:
                continue

            dmg = attacker.fast_move_damage(defender)
            attacker.energy = min(ENERGY_CAP, attacker.energy + move['energyGain'])
            defender.hp = max(0, defender.hp - dmg)
            attacker.cooldown = 0   # ready to act next turn
            attacker._fm_since_charge += 1

            log_event(
                f"{attacker.species} fast → {dmg} dmg, "
                f"energy {attacker.energy}"
            )

        # --- 5. Check for faint ---
        if p0.hp <= 0 or p1.hp <= 0:
            break

    # Determine winner
    if p0.hp > 0 and p1.hp <= 0:
        winner = 0
    elif p1.hp > 0 and p0.hp <= 0:
        winner = 1
    else:
        winner = None   # tie or time-out

    return BattleResult(
        winner           = winner,
        turns            = turn,
        hp_remaining     = [p0.hp, p1.hp],
        energy_remaining = [p0.energy, p1.energy],
        shields_remaining= [p0.shields, p1.shields],
        timeline         = timeline,
    )
