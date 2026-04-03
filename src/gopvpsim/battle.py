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
from .data import parse_types

ENERGY_CAP = 100
MAX_TURNS  = 500   # ~4 minutes; prevents infinite loops

# ---------------------------------------------------------------------------
# Policy debug log
#
# When simulate() is called with debug=True, this list is populated with
# strings describing internal policy decisions (OMT fires, DP choices).
# It is reset at the start of each simulate() call.
# ---------------------------------------------------------------------------
_policy_log: list[str] = []
_policy_debug: bool = False

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

def pvpoke_shield(attacker: "BattlePokemon", defender: "BattlePokemon", move: dict) -> bool:
    """
    Shield policy mirroring PvPoke's ActionLogic.wouldShield.

    Returns True only when the defender has a shield available AND the move is
    dangerous enough that a smart player would use it.  Mirrors the heuristic in
    ActionLogic.js: shield if
      - post-move HP is within one attacker charge-cycle of 0, OR
      - any of the attacker's charged moves deals ≥ 71 % of remaining HP (and
        the attacker's fast DPT is high), OR
      - any of the attacker's charged moves would KO after the cycle damage.
    """
    if defender.shields <= 0:
        return False
    return would_shield(attacker, defender, move)

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

def _calc_turns_to_live(
    attacker: "BattlePokemon",
    defender: "BattlePokemon",
) -> float:
    """
    Port of PvPoke's turnsToLive sub-DP (ActionLogic.js lines 38-138).

    Simulates the defender's attack sequence to estimate how many turns until
    the attacker is KO'd.  Returns math.inf if a KO is not found.

    State: {hp, opEnergy, turn, shields}
      hp        – attacker's remaining HP
      opEnergy  – defender's energy
      turn      – turns into the future for this state
      shields   – attacker's remaining shields

    When attacker shields > 0 the DP models the defender baiting with their
    cheapest charged move (shielded → 1 damage).  When shields == 0 it
    checks whether any charged move would KO.
    """
    opp_fast_damage   = defender.fast_move_damage(attacker)
    opp_fast_energy   = defender.fast_move.get('energyGain', 5)
    opp_fast_turns    = defender.fast_move.get('_turns', 1)
    atk_fast_turns    = attacker.fast_move.get('_turns', 1)
    wins_cmp          = attacker.atk >= defender.atk
    fastest_cm_energy = min(m['energy'] for m in defender.charged_moves)

    turns_to_live: float = math.inf

    # Build initial state.
    # In our timing model, fast moves with D ≤ 2 always land before the action-
    # decision phase, so _queued_fast is None.  For D ≥ 3 moves, compute the
    # PvPoke-equivalent cooldown: defender.cooldown turns remaining (= D − k,
    # where k turns have already elapsed).  The fast move lands after
    # defender.cooldown − 1 more turns, but the DP turn offset uses the full
    # defender.cooldown to match PvPoke's `opponent.cooldown / 500`.
    opp_in_fast = defender._queued_fast is not None
    if opp_in_fast:
        pvp_turns = defender.cooldown          # matches PvPoke's cooldown / 500
        initial = {
            'hp':       attacker.hp - opp_fast_damage,
            'opEnergy': min(ENERGY_CAP, defender.energy + opp_fast_energy),
            'turn':     pvp_turns,
            'shields':  attacker.shields,
        }
    else:
        initial = {
            'hp':       attacker.hp,
            'opEnergy': defender.energy,
            'turn':     0,
            'shields':  attacker.shields,
        }

    queue = [initial]

    while queue:
        curr = queue.pop(0)

        # Prune far-future states when the attacker can still survive another hit
        if curr['hp'] > opp_fast_damage:
            if wins_cmp:
                if curr['turn'] > atk_fast_turns:
                    continue
            else:
                if curr['turn'] > atk_fast_turns + 1:
                    continue

        # Shields up → model opponent baiting with cheapest charged move
        if curr['shields'] != 0:
            if curr['opEnergy'] >= fastest_cm_energy:
                queue.insert(0, {
                    'hp':       curr['hp'] - 1,          # shielded: 1 dmg
                    'opEnergy': curr['opEnergy'] - fastest_cm_energy,
                    'turn':     curr['turn'] + 1,
                    'shields':  curr['shields'] - 1,
                })
        else:
            # No shields: check whether any charged move would KO
            for cm in defender.charged_moves:
                if curr['opEnergy'] >= cm['energy']:
                    cm_dmg = defender.charged_move_damage(cm, attacker)
                    if cm_dmg >= curr['hp']:
                        turns_to_live = min(curr['turn'], turns_to_live)
                        opp_cd = defender.fast_move.get('cooldown', 500)
                        atk_cd = attacker.fast_move.get('cooldown', 500)
                        if attacker.atk > defender.atk and opp_cd % atk_cd == 0:
                            turns_to_live += 1
                        break
                    queue.insert(0, {
                        'hp':       curr['hp'] - cm_dmg,
                        'opEnergy': curr['opEnergy'] - cm['energy'],
                        'turn':     curr['turn'] + 1,
                        'shields':  curr['shields'],
                    })

        # Would a fast move KO?
        if curr['hp'] - opp_fast_damage <= 0:
            turns_to_live = min(curr['turn'] + opp_fast_turns, turns_to_live)
            break
        else:
            queue.insert(0, {
                'hp':       curr['hp'] - opp_fast_damage,
                'opEnergy': min(ENERGY_CAP, curr['opEnergy'] + opp_fast_energy),
                'turn':     curr['turn'] + opp_fast_turns,
                'shields':  curr['shields'],
            })

    return turns_to_live


def would_shield(attacker: "BattlePokemon", defender: "BattlePokemon", move: dict) -> bool:
    """
    Port of PvPoke's ActionLogic.wouldShield.

    Returns True if the defender is expected to use a shield against `move`.
    Checks whether the post-move HP is survivable given incoming cycle damage,
    and whether any of the attacker's charged moves are threatening enough.
    """
    damage     = attacker.charged_move_damage(move, defender)
    post_hp    = defender.hp - damage

    fast_turns  = attacker.fast_move.get('_turns', 1)
    fast_damage = attacker.fast_move_damage(defender)
    fast_energy = attacker.fast_move.get('energyGain', 5)
    fast_dpt    = fast_damage / fast_turns

    # Energy remaining after firing `move` (0 if not currently affordable)
    leftover_energy = max(attacker.energy - move['energy'], 0)
    # Fast attacks needed before the next charge cycle, plus one margin
    fast_attacks_needed = math.ceil((move['energy'] - leftover_energy) / fast_energy) + 1
    cycle_damage = (fast_attacks_needed * fast_damage + 1) * defender.shields

    use_shield = post_hp <= cycle_damage

    for cm in attacker.charged_moves:
        cm_dmg = attacker.charged_move_damage(cm, defender)
        if cm_dmg >= defender.hp / 1.4 and fast_dpt > 1.5:
            use_shield = True
        if cm_dmg >= defender.hp - cycle_damage:
            use_shield = True

    return use_shield


# DP state: (energy, opp_hp, turn, opp_shields, moves_list)
# moves_list: list of move indices thrown in this branch
class _DPState:
    __slots__ = ('energy', 'hp', 'turn', 'shields', 'moves')
    def __init__(self, energy, hp, turn, shields, moves):
        self.energy  = energy
        self.hp      = hp
        self.turn    = turn
        self.shields = shields
        self.moves   = moves


def _optimize_move_timing(attacker: "BattlePokemon", defender: "BattlePokemon") -> bool:
    """
    Port of ActionLogic.js lines 237-344 (optimizeMoveTiming).

    Returns True if the attacker should throw a fast move instead of a charged
    move this turn, in order to avoid gifting the opponent extra turns.

    PvPoke fires this when opponent.cooldown == 0 (just became able to act, about
    to queue a new fast move) or opponent.cooldown > targetCooldown.  In our
    model the opponent is processed first in the decide-loop, so by the time the
    attacker decides, the defender's cooldown has already been set to fm['_turns']
    if it queued a fast move this turn.  That means:
      - defender just queued  → defender.cooldown == fm_turns  (e.g. 2 for PC)
      - defender mid-cooldown → defender.cooldown == 1
    We map PvPoke's "cooldown == 0" to our "cooldown == fm_turns" (just queued),
    and keep the "> targetCooldown" condition as-is in turn units.
    """
    atk_cd = attacker.fast_move.get('cooldown', 500)   # ms
    def_cd = defender.fast_move.get('cooldown', 500)    # ms
    atk_turns = attacker.fast_move.get('_turns', 1)
    def_turns = defender.fast_move.get('_turns', 1)

    # --- Compute targetCooldown (in turns = ms/500) ---
    target_cd = 1   # default 500 ms

    if atk_cd >= 2000:
        target_cd = 2
    if atk_cd >= 1500 and def_cd == 2500:
        target_cd = 2
    if atk_cd == 1000 and def_cd == 2000:
        target_cd = 2

    # No optimisation when moves have the same cooldown
    if atk_cd == def_cd:
        return False
    # No optimisation when attacker's move is a longer even multiple (e.g. 4T vs 2T)
    if atk_cd % def_cd == 0 and atk_cd > def_cd:
        return False
    if target_cd == 0:
        return False

    opp_cd = defender.cooldown
    # In our model "just queued" == opp_cd == def_turns; treat it like PvPoke's 0
    just_queued = (opp_cd == def_turns)
    if not (just_queued or opp_cd == 0 or opp_cd > target_cd):
        return False   # timing is already fine — proceed with charged move

    # --- Override conditions (any True → don't optimize, fire charged move) ---
    opp_fast_dmg = defender.fast_move_damage(attacker)

    # Would faint from the next opponent fast move
    if attacker.hp <= opp_fast_dmg:
        return False

    # Throwing a fast move would overflow energy past 100
    if attacker.energy + attacker.fast_move.get('energyGain', 0) > ENERGY_CAP:
        return False

    # Turns planned vs turns to live
    affordable_cms = [m for m in attacker.charged_moves if attacker.energy >= m['energy']]
    if not affordable_cms:
        return False
    cheapest_energy = min(m['energy'] for m in affordable_cms)
    turns_planned = atk_turns + (attacker.energy // cheapest_energy)
    if attacker.atk < defender.atk:
        turns_planned += 1
    ttl = _calc_turns_to_live(attacker, defender)
    if turns_planned > ttl:
        return False

    # Can KO opponent right now with a charged move (shields == 0 only)
    if defender.shields == 0:
        for cm in attacker.charged_moves:
            if attacker.energy >= cm['energy']:
                if attacker.charged_move_damage(cm, defender) >= defender.hp:
                    return False

    # Opponent's next charged move can KO within our fast-move window
    fms_in_atk_fm = atk_turns // def_turns   # opponent FMs that fit inside our FM
    for cm in defender.charged_moves:
        fms_needed = math.ceil(
            max(0, cm['energy'] - defender.energy) / defender.fast_move['energyGain']
        )
        turns_from_cm = fms_needed * def_turns + 1
        if attacker.shields > 0:
            effective_dmg = 1 + opp_fast_dmg * fms_in_atk_fm
        else:
            effective_dmg = (defender.charged_move_damage(cm, attacker)
                             + opp_fast_dmg * fms_in_atk_fm)
        if turns_from_cm <= atk_turns and effective_dmg >= attacker.hp:
            return False

    # Fast moves alone within our fast-move window could KO us
    fms_in_atk_fm2 = (atk_turns + 1) // def_turns   # Math.floor((atk_cd+500)/def_cd)
    if attacker.hp <= opp_fast_dmg * fms_in_atk_fm2:
        return False

    if _policy_debug:
        _policy_log.append(
            f"  OMT: {attacker.species} delays (energy={attacker.energy}, "
            f"def_cd={defender.cooldown}, just_queued={just_queued})"
        )
    return True   # optimize: throw fast move instead


def _dp_insert(queue: list, ns: "_DPState") -> None:
    """Insert ns into the priority queue (sorted by turn, ascending)."""
    i = 0
    while i < len(queue) and queue[i].turn <= ns.turn:
        i += 1
    queue.insert(i, ns)


def pvpoke_dp(attacker: "BattlePokemon", defender: "BattlePokemon") -> "int | None":
    """
    PvPoke's DP charged-move AI (ActionLogic.js port, no-buff case).

    Two phases mirroring PvPoke:

    Farm-down  (opponent HP > 2 × best-cycle damage):
        Select bestChargedMove (highest actual DPE).
        Bait with cheapest move only if the opponent would shield bestChargedMove.
        If current energy < selectedMove.energy → wait (return None).

    Near-KO    (opponent HP ≤ 2 × best-cycle damage):
        Run a forward DP over charge-move sequences to find the fastest KO.
        Fire the first move in the optimal plan; wait if not yet affordable.
    """
    fast_turns       = attacker.fast_move.get('_turns', 1)
    fast_energy      = attacker.fast_move.get('energyGain', 5)
    fast_damage      = attacker.fast_move_damage(defender)
    atk_fast_cd      = attacker.fast_move.get('cooldown', 500)
    opp_fast_cd      = defender.fast_move.get('cooldown', 500)
    opp_fast_damage  = defender.fast_move_damage(attacker)
    wins_cmp         = attacker.atk >= defender.atk

    cms = attacker.charged_moves

    def actual_dpe(m: dict) -> float:
        return attacker.charged_move_damage(m, defender) / m['energy']

    # ------------------------------------------------------------------ #
    # turnsToLive: fire highest-damage move now if about to be KO'd
    # Port of ActionLogic.js lines 38-207
    # ------------------------------------------------------------------ #
    turns_to_live = _calc_turns_to_live(attacker, defender)

    # Adjustments (ActionLogic.js lines 142-161) — always applied
    if attacker.hp <= opp_fast_damage * 2 and opp_fast_cd == 500:
        turns_to_live -= 1

    if (attacker.hp <= opp_fast_damage
            and defender._queued_fast is not None
            and opp_fast_cd > 500):
        turns_to_live = defender.cooldown      # PvPoke: opponent.cooldown / 500
        if defender.hp > attacker.fast_move_damage(defender):
            turns_to_live -= 1

    if (attacker.hp <= opp_fast_damage
            and defender._queued_fast is None
            and opp_fast_cd <= atk_fast_cd + 500):
        if defender.hp > attacker.fast_move_damage(defender):
            turns_to_live -= 1

    fire_now = (
        turns_to_live * 500 < atk_fast_cd
        or (turns_to_live * 500 == atk_fast_cd and not wins_cmp)
        or (turns_to_live * 500 == atk_fast_cd and attacker.hp <= opp_fast_damage)
    )

    if fire_now:
        # Highest-damage affordable move (PvPoke iterates n from len down to 0,
        # length index is OOB → skipped; effectively reverse order)
        max_dmg_idx = None
        prev_dmg    = -1
        for n in range(len(cms) - 1, -1, -1):
            if attacker.energy >= cms[n]['energy']:
                dmg = attacker.charged_move_damage(cms[n], defender)
                if dmg > prev_dmg:
                    max_dmg_idx = n
                    prev_dmg    = dmg
                # Double-fire: if have energy for two of same move and win CMP
                if (attacker.energy >= cms[n]['energy'] * 2
                        and attacker.atk > defender.atk
                        and dmg * 2 > prev_dmg):
                    max_dmg_idx = n
                    prev_dmg    = dmg * 2
        if max_dmg_idx is None:
            if _policy_debug:
                _policy_log.append(
                    f"  DP[fire_now]: {attacker.species} no affordable move → fast"
                )
            return None   # no affordable move → fast move
        if _policy_debug:
            _policy_log.append(
                f"  DP[fire_now]: {attacker.species} fires {cms[max_dmg_idx].get('moveId')} "
                f"(ttl={turns_to_live}, energy={attacker.energy})"
            )
        return max_dmg_idx

    # ------------------------------------------------------------------ #
    # optimizeMoveTiming (ActionLogic.js lines 237-344)
    # ------------------------------------------------------------------ #
    if _optimize_move_timing(attacker, defender):
        return None

    best_idx = max(range(len(cms)), key=lambda i: actual_dpe(cms[i]))
    best_cm  = cms[best_idx]

    # bestCycleDamage: fast moves needed to charge from 0 + one charge move
    fm_to_charge   = math.ceil(best_cm['energy'] / fast_energy)
    best_cycle_dmg = fast_damage * fm_to_charge + attacker.charged_move_damage(best_cm, defender)

    # ------------------------------------------------------------------ #
    # Farm-down path
    # ------------------------------------------------------------------ #
    if defender.hp > 2 * best_cycle_dmg:
        selected_idx = best_idx

        # Bait only if opponent has shields AND would shield the best move
        if (defender.shields > 0 and len(cms) > 1
                and not cms[0].get('selfDebuffing', False)
                and would_shield(attacker, defender, best_cm)):
            selected_idx = min(range(len(cms)), key=lambda i: cms[i]['energy'])

        if attacker.energy < cms[selected_idx]['energy']:
            if _policy_debug:
                _policy_log.append(
                    f"  DP[farm]: {attacker.species} waits for "
                    f"{cms[selected_idx].get('moveId')} (energy={attacker.energy}/"
                    f"{cms[selected_idx]['energy']})"
                )
            return None   # wait for the selected move
        if _policy_debug:
            _policy_log.append(
                f"  DP[farm]: {attacker.species} fires "
                f"{cms[selected_idx].get('moveId')} (energy={attacker.energy})"
            )
        return selected_idx

    # ------------------------------------------------------------------ #
    # Near-KO: DP to find the fastest charge-move sequence that KOs
    # ------------------------------------------------------------------ #
    queue: list = [_DPState(attacker.energy, float(defender.hp), 0, defender.shields, [])]
    final_state: "_DPState | None" = None
    iters = 0

    while queue and iters < 500:
        iters += 1
        curr = queue.pop(0)

        # KO achieved — this is the fastest plan (chance == 1 path → break)
        if curr.hp <= 0:
            final_state = curr
            break

        for n, move in enumerate(cms):
            move_dmg = attacker.charged_move_damage(move, defender)

            if curr.energy >= move['energy']:
                # Fire immediately (costs 1 extra turn for the charge move)
                new_e  = curr.energy - move['energy']
                new_t  = curr.turn + 1
                new_sh = curr.shields
                if curr.shields > 0:
                    new_hp = curr.hp - 1
                    new_sh -= 1
                else:
                    new_hp = curr.hp - move_dmg
            else:
                # Fast-forward: ceil((cost − energy) / energyGain) fast moves
                fm_needed    = math.ceil((move['energy'] - curr.energy) / fast_energy)
                turns_needed = fm_needed * fast_turns
                new_e  = fm_needed * fast_energy + curr.energy - move['energy']
                new_t  = curr.turn + turns_needed + 1
                new_sh = curr.shields
                if curr.shields > 0:
                    new_hp = curr.hp - fast_damage * fm_needed - 1
                    new_sh -= 1
                else:
                    new_hp = curr.hp - fast_damage * fm_needed - move_dmg

            _dp_insert(queue, _DPState(new_e, new_hp, new_t, new_sh, curr.moves + [n]))

        # Farm-down state: fast-move to KO from here with no more charged moves.
        # PvPoke ActionLogic.js adds this for every state to represent "stop here,
        # just fast-move until the opponent faints."
        if fast_damage > 0 and curr.hp > 0:
            fm_to_ko  = math.ceil(curr.hp / fast_damage)
            fd_turn   = curr.turn + fm_to_ko * fast_turns
            fd_energy = curr.energy + fast_energy * fm_to_ko
            # Only insert if no strictly-negative-HP KO state already exists
            # at turn <= fd_turn (mirrors PvPoke's DPQueue[i].hp < 0 check).
            can_insert = True
            for s in queue:
                if s.turn > fd_turn:
                    break
                if s.hp < 0:
                    can_insert = False
                    break
            if can_insert:
                _dp_insert(queue, _DPState(fd_energy, 0.0, fd_turn,
                                           curr.shields, curr.moves[:]))

    # ------------------------------------------------------------------ #
    # Select move from plan
    # ------------------------------------------------------------------ #
    if final_state is None:
        # No KO found — fallback to best-DPE greedy
        affordable = [(i, m) for i, m in enumerate(cms) if attacker.energy >= m['energy']]
        if not affordable:
            return None
        return max(affordable, key=lambda im: actual_dpe(im[1]))[0]

    if not final_state.moves:
        # Farm-down plan: no charged moves needed, just fast-move to KO.
        # PvPoke returns undefined (no action) in this case.
        return None

    # When shields are down, PvPoke sorts the plan by damage descending
    # so the highest-damage move fires first (ActionLogic.js lines 851-858).
    if defender.shields == 0:
        plan = sorted(final_state.moves,
                      key=lambda n: attacker.charged_move_damage(cms[n], defender),
                      reverse=True)
    else:
        plan = final_state.moves

    first_idx  = plan[0]
    first_move = cms[first_idx]

    # Post-DP bandaid: if shields up and cheapest has better DPE, prefer it
    # (ActionLogic.js lines 861-864)
    if (defender.shields > 0 and len(cms) > 1
            and attacker.energy >= cms[0]['energy']
            and cms[0]['energy'] <= first_move['energy']
            and actual_dpe(cms[0]) > actual_dpe(first_move)):
        first_idx  = 0
        first_move = cms[first_idx]

    # Bait-wait check (ActionLogic.js lines 820-835):
    # If shields are up and we can afford the planned move but NOT the most
    # expensive move (sorted by energy), and the expensive move has better DPE
    # than our planned first move → wait for the expensive move instead.
    # This prevents wasting energy on a cheaper move when a better one is coming.
    if defender.shields > 0 and len(cms) > 1:
        sorted_by_energy = sorted(range(len(cms)), key=lambda i: cms[i]['energy'])
        expensive_idx = sorted_by_energy[-1]
        expensive_cm  = cms[expensive_idx]
        if (attacker.energy < expensive_cm['energy']
                and actual_dpe(expensive_cm) > actual_dpe(first_move)
                and not expensive_cm.get('selfDebuffing', False)):
            return None   # bait-wait: hold off for the better move

    if attacker.energy < first_move['energy']:
        if _policy_debug:
            _policy_log.append(
                f"  DP[near-ko]: {attacker.species} waits for "
                f"{first_move.get('moveId')} (energy={attacker.energy}/"
                f"{first_move['energy']}, plan={[cms[i].get('moveId') for i in plan]})"
            )
        return None   # wait until affordable
    if _policy_debug:
        _policy_log.append(
            f"  DP[near-ko]: {attacker.species} fires "
            f"{first_move.get('moveId')} (energy={attacker.energy}, "
            f"plan={[cms[i].get('moveId') for i in plan]})"
        )
    return first_idx


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
        types = parse_types(mon)
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
    max_hp:       list[int]     # [p0_max_hp, p1_max_hp]
    energy_remaining: list[int]
    shields_remaining: list[int]
    timeline:     list[str] = field(default_factory=list)  # human-readable log

    def pvpoke_score(self, player: int) -> float:
        """
        Compute PvPoke's battle rating for `player` (0 or 1).

        score = 500 * (damage_dealt / opponent_max_hp)
              + 500 * (hp_remaining / own_max_hp)

        >500 means this player won, <500 means they lost.
        """
        opp = 1 - player
        # Match PvPoke's Math.floor formula exactly: opp_hp can be negative (overkill counts)
        return math.floor(
            500 * (self.max_hp[opp] - self.hp_remaining[opp]) / self.max_hp[opp]
            + 500 * max(0, self.hp_remaining[player]) / self.max_hp[player]
        )


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
    debug: bool = False,
) -> BattleResult:
    """
    Run a 1v1 battle between p0 and p1 and return the result.

    p0 and p1 are mutated in place — reset them before reuse.

    debug=True also enables policy decision logging (OMT fires, DP choices).
    Policy log lines are interleaved into BattleResult.timeline at the turn
    they occur; they are indented with two leading spaces for easy filtering.
    Implies log=True.
    """
    global _policy_debug, _policy_log

    if debug:
        log = True
    _policy_debug = debug
    _policy_log   = []

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

        # Flush any policy-debug entries generated during decide step
        if _policy_debug and _policy_log:
            for entry in _policy_log:
                timeline.append(f"T{turn:>3}: {entry.lstrip()}")
            _policy_log.clear()

        # --- 3. Resolve fast move landings (fire BEFORE charged moves) ---
        # PvPoke: naturally-due fast moves get priority+20 and resolve before
        # charged moves. When two fast moves land simultaneously, PvPoke sorts
        # by effective attack descending (higher atk fires first).
        if len(fast_landings) > 1:
            fast_landings.sort(key=lambda ia: pokemon[ia[0]].atk, reverse=True)
        for actor_idx, move in fast_landings:
            attacker = pokemon[actor_idx]
            defender = pokemon[1 - actor_idx]

            if attacker.hp <= 0 or defender.hp <= 0:
                continue

            dmg = attacker.fast_move_damage(defender)
            attacker.energy = min(ENERGY_CAP, attacker.energy + move['energyGain'])
            defender.hp = max(0, defender.hp - dmg)
            attacker.cooldown = 0
            attacker._fm_since_charge += 1

            log_event(
                f"{attacker.species} fast → {dmg} dmg, "
                f"energy {attacker.energy}"
            )

        # --- 4. Resolve charged moves (higher priority first) ---
        # Skip if defender was already killed by the fast move this turn.
        if use_priority and len(charged_actions) == 2:
            charged_actions.sort(key=lambda ia: pokemon[ia[0]].atk, reverse=True)

        for actor_idx, move in charged_actions:
            attacker = pokemon[actor_idx]
            defender = pokemon[1 - actor_idx]

            if attacker.energy < move['energy']:
                continue   # raced to this — no longer affordable

            if defender.hp <= 0:
                continue   # defender already fainted from fast move this turn

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

        # After any charged move this turn, fire "floating" fast moves then reset.
        # PvPoke Battle.js: a fast move queued in the same turn as a charged move
        # (timeSinceActivated < requiredTimeToPass) fires at -20 priority (after
        # the charged move) rather than being cancelled.  This is simulate mode
        # only — queuedActions is never cleared by a charged move in simulate mode.
        if charged_actions:
            for i, p in enumerate(pokemon):
                if p._queued_fast is not None:
                    # Only fire if the pokemon survived (if killed by charged move,
                    # PvPoke marks faintSource="charged" and the fast is invalid).
                    if p.hp > 0:
                        defender = pokemon[1 - i]
                        if defender.hp > 0:
                            qmove = p._queued_fast[1]
                            dmg = p.fast_move_damage(defender)
                            p.energy = min(ENERGY_CAP, p.energy + qmove['energyGain'])
                            defender.hp = max(0, defender.hp - dmg)
                            p._fm_since_charge += 1
                            log_event(
                                f"{p.species} floating fast → {dmg} dmg, "
                                f"energy {p.energy}"
                            )
            for p in pokemon:
                p.cooldown = 0
                p._queued_fast = None
                p._fm_since_charge = 0

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
        winner            = winner,
        turns             = turn,
        hp_remaining      = [p0.hp, p1.hp],
        max_hp            = [p0.max_hp, p1.max_hp],
        energy_remaining  = [p0.energy, p1.energy],
        shields_remaining = [p0.shields, p1.shields],
        timeline          = timeline,
    )
