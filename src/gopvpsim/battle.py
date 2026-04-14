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
from functools import partial
from typing import Callable

from .moves import damage as calc_damage, type_effectiveness, stab
from .data import parse_types

# Optional numba JIT for the near-KO DP loop. If unavailable (numba not
# installed, LLVM mismatch, etc.), pvpoke_dp falls back to the pure-Python
# loop further down.
try:
    import numpy as _np
    from ._dp_jit import _near_ko_dp_jit as _NEAR_KO_DP_JIT
except Exception:                       # pragma: no cover - jit optional
    _np = None
    _NEAR_KO_DP_JIT = None

ENERGY_CAP = 100
MAX_TURNS  = 500   # ~4 minutes; prevents infinite loops


def _stat_stage_mult(stage: int) -> float:
    """PvPoke stat stage multiplier for a stage in [-4, +4]."""
    if stage >= 0:
        return (4 + stage) / 4.0
    else:
        return 4.0 / (4 - stage)

# ---------------------------------------------------------------------------
# Policy debug log
#
# When simulate() is called with debug=True, this list is populated with
# strings describing internal policy decisions (OMT fires, DP choices).
# It is reset at the start of each simulate() call.
# ---------------------------------------------------------------------------
_policy_log: list[str] = []
_policy_debug: bool = False
_shield_trace: bool = False
_dp_trace: bool = False

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

def pvpoke_simulate_shield(attacker: "BattlePokemon", defender: "BattlePokemon", move: dict) -> bool:
    """
    PvPoke's simulate-mode shield policy (Battle.js line 1077).

    For standard charged moves: always shield (useShield = true).
    For selfBuffing or selfDefensiveDebuffing moves: use wouldShield heuristic.
    This mirrors Battle.js: useShield = true, then overridden for
    move.selfBuffing and move.selfDefensiveDebuffing.
    """
    if defender.shields <= 0:
        if _shield_trace:
            _policy_log.append(
                f"  shield({defender.species} sh=0 vs {move.get('moveId')}): False (no shields)")
        return False

    # PvPoke Battle.js lines 1083-1094: only use wouldShield heuristic for
    # moves with precomputed selfBuffing flag (requires buffApplyChance==1)
    # or selfDefenseDebuffing flag (requires buffApplyChance>=0.5).
    # Chance-buff moves like Air Cutter (30%) are NOT selfBuffing in PvPoke,
    # so they are always shielded.
    self_buffing        = move.get('selfBuffing', False)
    self_def_debuffing  = move.get('selfDefenseDebuffing', False)
    if self_buffing or self_def_debuffing:
        result = would_shield(attacker, defender, move)
        if _shield_trace:
            tag = "selfBuff" if self_buffing else "selfDefDebuff"
            _policy_log.append(
                f"  shield({defender.species} sh={defender.shields} vs"
                f" {move.get('moveId')} [{tag}]): → wouldShield={result}")
        return result
    # Aegislash Shield form: don't waste shields if damage < half HP
    # PvPoke Battle.js:1119
    if (defender._form_change is not None
            and defender._form_change.forms[int(defender._form_is_alt)].species_id == 'aegislash_shield'
            and attacker.charged_move_damage(move, defender) * 2 < defender.hp):
        if _shield_trace:
            _policy_log.append(
                f"  shield({defender.species} sh={defender.shields} vs"
                f" {move.get('moveId')}): False (Aegislash Shield suppression)")
        return False

    if _shield_trace:
        _policy_log.append(
            f"  shield({defender.species} sh={defender.shields} vs"
            f" {move.get('moveId')}): True (always shield)")
    return True

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

    State tuple: (hp, opEnergy, turn, shields)
      hp        – attacker's remaining HP
      opEnergy  – defender's energy
      turn      – turns into the future for this state
      shields   – attacker's remaining shields

    The original PvPoke code does ``queue.unshift()`` and ``queue.shift()``
    (push/pop at the front).  Both ends behave like a stack here — we read
    the most-recently-pushed state next — so a list with ``append()``/
    ``pop()`` (LIFO) gives identical exploration order in O(1) per op,
    instead of the O(n) ``insert(0, ...)`` / ``pop(0)`` the dict version
    used.

    When attacker shields > 0 the DP models the defender baiting with their
    cheapest charged move (shielded → 1 damage).  When shields == 0 it
    checks whether any charged move would KO.
    """
    opp_fast_damage   = defender.fast_move_damage(attacker)
    opp_fast_energy   = defender.fast_move.get('energyGain', 5)
    opp_fast_turns    = defender.fast_move.get('_turns', 1)
    atk_fast_turns    = attacker.fast_move.get('_turns', 1)
    wins_cmp          = attacker.atk >= defender.atk

    # Hoist defender's charged-move energy + damage into parallel arrays so
    # the inner loop avoids method/dict lookups. The damage cache was
    # populated by defender.fast_move_damage(attacker) above.
    d_cm_dmgs   = defender._cached_charged_dmgs
    d_cm_energy = [cm['energy'] for cm in defender.charged_moves]
    n_d_cms     = len(d_cm_energy)
    fastest_cm_energy = min(d_cm_energy) if d_cm_energy else 0

    turns_to_live: float = math.inf

    # Build initial state.
    # In our timing model, fast moves with D ≤ 2 always land before the action-
    # decision phase, so _queued_fast is None.  For D ≥ 3 moves, compute the
    # PvPoke-equivalent cooldown: defender.cooldown turns remaining (= D − k,
    # where k turns have already elapsed).  The fast move lands after
    # defender.cooldown − 1 more turns, but the DP turn offset uses the full
    # defender.cooldown to match PvPoke's `opponent.cooldown / 500`.
    if defender._queued_fast is not None:
        initial = (attacker.hp - opp_fast_damage,
                   min(ENERGY_CAP, defender.energy + opp_fast_energy),
                   defender.cooldown,
                   attacker.shields)
    else:
        initial = (attacker.hp,
                   defender.energy,
                   0,
                   attacker.shields)

    stack = [initial]

    while stack:
        c_hp, c_op_e, c_turn, c_shields = stack.pop()

        # Prune far-future states when the attacker can still survive another hit
        if c_hp > opp_fast_damage:
            if wins_cmp:
                if c_turn > atk_fast_turns:
                    continue
            else:
                if c_turn > atk_fast_turns + 1:
                    continue

        # Shields up → model opponent baiting with cheapest charged move
        if c_shields != 0:
            if c_op_e >= fastest_cm_energy:
                stack.append((
                    c_hp - 1,                          # shielded: 1 dmg
                    c_op_e - fastest_cm_energy,
                    c_turn + 1,
                    c_shields - 1,
                ))
        else:
            # No shields: check whether any charged move would KO
            for n in range(n_d_cms):
                e = d_cm_energy[n]
                if c_op_e >= e:
                    cm_dmg = d_cm_dmgs[n]
                    if cm_dmg >= c_hp:
                        if c_turn < turns_to_live:
                            turns_to_live = c_turn
                        opp_cd = defender.fast_move.get('cooldown', 500)
                        atk_cd = attacker.fast_move.get('cooldown', 500)
                        if attacker.atk > defender.atk and opp_cd % atk_cd == 0:
                            turns_to_live += 1
                        break
                    stack.append((
                        c_hp - cm_dmg,
                        c_op_e - e,
                        c_turn + 1,
                        c_shields,
                    ))

        # Would a fast move KO?
        if c_hp - opp_fast_damage <= 0:
            tt = c_turn + opp_fast_turns
            if tt < turns_to_live:
                turns_to_live = tt
            break
        else:
            stack.append((
                c_hp - opp_fast_damage,
                min(ENERGY_CAP, c_op_e + opp_fast_energy),
                c_turn + opp_fast_turns,
                c_shields,
            ))

    return turns_to_live


def would_shield(attacker: "BattlePokemon", defender: "BattlePokemon", move: dict) -> bool:
    """
    Port of PvPoke's ActionLogic.wouldShield.

    Returns True if the defender is expected to use a shield against `move`.
    Checks whether the post-move HP is survivable given incoming cycle damage,
    and whether any of the attacker's charged moves are threatening enough.

    Mirrors ActionLogic.js lines 1110-1140: temporarily applies the move's
    stat change before computing subsequent-cycle damage, then resets.
    If buffs[0] > 0 (atk buff): apply to attacker.
    Otherwise: apply to defender (matches PvPoke's else-branch).
    """
    damage  = attacker.charged_move_damage(move, defender)
    post_hp = defender.hp - damage

    # Temporarily apply move buffs for damage projection (ActionLogic.js 1110-1140)
    move_buffs   = move.get('buffs', [0, 0]) or [0, 0]
    saved_stage  = None
    if move_buffs[0] > 0:
        saved_stage = attacker.atk_stage
        attacker.atk_stage = max(-4, min(4, attacker.atk_stage + move_buffs[0]))
    else:
        saved_stage = defender.def_stage
        defender.def_stage = max(-4, min(4, defender.def_stage + move_buffs[1]))

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

    # Reset the temporarily applied buff (ActionLogic.js 1136-1140)
    # Must happen BEFORE the charged-move loop below — PvPoke evaluates
    # charged-move threat with normal stats, not the temporarily-applied
    # buff from the move being evaluated.
    if move_buffs[0] > 0:
        attacker.atk_stage = saved_stage
    else:
        defender.def_stage = saved_stage

    cm_reasons = []
    for cm in attacker.charged_moves:
        cm_dmg = attacker.charged_move_damage(cm, defender)
        if cm_dmg >= defender.hp / 1.4 and fast_dpt > 1.5:
            use_shield = True
            cm_reasons.append(f"{cm.get('moveId')}({cm_dmg})≥hp/1.4({defender.hp/1.4:.0f})&dpt({fast_dpt:.1f})>1.5")
        if cm_dmg >= defender.hp - cycle_damage:
            use_shield = True
            cm_reasons.append(f"{cm.get('moveId')}({cm_dmg})≥hp-cycle({defender.hp}-{cycle_damage}={defender.hp-cycle_damage})")

    if _shield_trace:
        buff_note = ""
        if move_buffs != [0, 0]:
            buff_note = f" buffs={move_buffs}"
        reasons = []
        if post_hp <= cycle_damage:
            reasons.append(f"postHP({post_hp})≤cycle({cycle_damage})")
        reasons.extend(cm_reasons)
        reason_str = ', '.join(reasons) if reasons else 'none'
        _policy_log.append(
            f"  wouldShield({defender.species} hp={defender.hp} sh={defender.shields},"
            f" {attacker.species}→{move.get('moveId')} dmg={damage}{buff_note}):"
            f" fast_dmg={fast_damage} cycle={cycle_damage} → {use_shield}"
            f" [{reason_str}]"
        )

    return use_shield


# DP state: scalar-only fields (no Python list of moves).
#
# Originally each state carried a `moves: list[int]` of charge-move indices
# thrown in this branch. The post-DP code only needs four pieces of
# information about the plan:
#   - the first move thrown      (first_idx)
#   - the highest-damage move    (max_dmg_idx)  — for the shields-down sort
#   - whether any move debuffs   (has_debuf)    — gates that sort branch
#   - net debuff count           (debuf_count)  — for _dp_insert_ready dedup
#
# Tracking these as scalars avoids a per-state `list + [n]` allocation in the
# inner loop and makes the state numba-friendly. With no moves: first_idx is
# -1 and the other scalars are 0.
class _DPState:
    __slots__ = ('energy', 'hp', 'turn', 'shields',
                 'first_idx', 'max_dmg_idx', 'has_debuf', 'debuf_count')
    def __init__(self, energy, hp, turn, shields,
                 first_idx, max_dmg_idx, has_debuf, debuf_count):
        self.energy      = energy
        self.hp          = hp
        self.turn        = turn
        self.shields     = shields
        self.first_idx   = first_idx
        self.max_dmg_idx = max_dmg_idx
        self.has_debuf   = has_debuf
        self.debuf_count = debuf_count


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
    # Match PvPoke ActionLogic.js line 263:
    # "if( (opponent.cooldown == 0 || opponent.cooldown > targetCooldown) && targetCooldown > 0)"
    # With the two-pass decision model, both pokemon see each other's pre-queuing
    # cooldown at decision time (matching PvPoke's cooldownsToSet mechanism).
    if not (opp_cd == 0 or opp_cd > target_cd):
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

    # Can KO opponent with a non-self-debuffing charged move (shields == 0 only),
    # but only if the fast move alone wouldn't also kill (PvPoke ActionLogic.js
    # lines 298-309: sets .damage on move objects as a side effect used by
    # bandaid[866] later).
    if defender.shields == 0:
        _fast_dmg = attacker.fast_move_damage(defender)
        for cm in attacker.charged_moves:
            if attacker.energy >= cm['energy']:
                cm['_cached_damage'] = attacker.charged_move_damage(cm, defender)
                if (cm['_cached_damage'] >= defender.hp
                        and not cm.get('selfDebuffing', False)
                        and defender.hp > _fast_dmg):
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
            f"opp_cd={defender.cooldown})"
        )
    return True   # optimize: throw fast move instead


def _cm_debuf_delta(m: dict) -> int:
    """Per-move delta for the dedup tie-break debuff count.

    +1 for self-debuffing, −1 for guaranteed self-buffing. Precomputed once
    per cms-list at the top of pvpoke_dp so the inner loop only carries an
    integer running sum.
    """
    delta = 0
    if m.get('selfDebuffing', False):
        delta += 1
    if (m.get('buffApplyChance') == 1
            and m.get('buffTarget') == 'self'
            and sum(m.get('buffs', [0, 0])) > 0):
        delta -= 1
    return delta


# ---------------------------------------------------------------------------
# DP queue insertion strategies (PvPoke ActionLogic.js lines 469-762)
#
# PvPoke uses three different insertion strategies with built-in pruning.
# However, the dominance checks (lines 600, 697) and the farm-down blocking
# check (line 479) reference ``.hp`` and ``.shields`` on BattleState objects.
# BattleState stores those values as ``.oppHealth`` and ``.oppShields``
# (lines 1190-1192), so ``.hp``/``.shields`` are ``undefined`` in JS.
# Since ``undefined < 0`` and ``undefined <= number`` are always ``false``
# in JavaScript, these pruning checks are dead code — they never fire.
#
# The ``intended_pruning`` flag controls whether we replicate PvPoke's
# *actual* JS behavior (pruning disabled) or the apparently *intended*
# behavior (pruning enabled, as if ``.hp``→``.oppHealth`` and
# ``.shields``→``.oppShields`` were used).
# ---------------------------------------------------------------------------


def _dp_insert_farm_down(queue: list, ns: "_DPState", *,
                         intended_pruning: bool = False) -> None:
    """Farm-down insertion (PvPoke lines 469-491).

    Insert AFTER same-turn states (``<=``).

    PvPoke line 479 checks ``DPQueue[i].hp < 0`` to block insertion, but
    ``.hp`` is undefined on BattleState (stored as ``.oppHealth``), so
    ``undefined < 0`` is always ``false`` and farm-down always inserts.
    With ``intended_pruning=True``, the blocking check uses our real
    ``.hp`` field and actually fires.
    """
    n = len(queue)
    ns_turn = ns.turn
    i = 0
    if intended_pruning:
        while i < n and queue[i].turn <= ns_turn:
            if queue[i].hp < 0:
                return  # blocked by existing KO state
            i += 1
    else:
        while i < n and queue[i].turn <= ns_turn:
            i += 1
    queue.insert(i, ns)


def _dp_insert_ready(queue: list, ns: "_DPState", *,
                     intended_pruning: bool = False) -> None:
    """Ready-move insertion (PvPoke lines 541-616).

    Phase 1 — dedup (lines 544-586): scan states at exactly
    ``turn == ns.turn``.  If an existing state has the same hp (and
    buffs, always 0), don't insert (different energy) or compare debuff
    counts (same energy).  This check uses ``.oppHealth`` (real field)
    and is always active.

    Phase 2 — dominance (lines 598-608): scan states at
    ``turn <= ns.turn``.  Block if existing state has hp <= newHp AND
    energy >= newEnergy AND shields <= newShields.  This check uses
    ``.hp``/``.shields`` (undefined), so it is dead code in PvPoke.
    Only active when ``intended_pruning=True``.

    Insert AFTER same-turn states (``<=``).
    """
    # Phase 1: dedup (always active — uses .oppHealth, a real field)
    i = 0
    insert_element = True
    n = len(queue)
    ns_turn = ns.turn
    ns_hp = ns.hp
    ns_energy = ns.energy
    ns_debuf = ns.debuf_count
    while i < n and queue[i].turn == ns_turn:
        q = queue[i]
        # buffs always 0 → buffs check always matches
        if q.hp == ns_hp:
            if q.energy == ns_energy:
                # Same energy — compare net debuff counts (precomputed
                # scalar on each state, no per-comparison list scan)
                if q.debuf_count > ns_debuf:
                    queue.pop(i)  # remove worse existing state
                    n -= 1
                else:
                    insert_element = False
                    i += 1
            else:
                # Different energy, same hp → don't insert
                insert_element = False
                i += 1
        else:
            i += 1

    if not insert_element:
        return

    # Phase 2: dominance check (dead code in PvPoke; active if intended)
    i = 0
    if intended_pruning:
        ns_shields = ns.shields
        while i < n and queue[i].turn <= ns_turn:
            q = queue[i]
            if (q.hp <= ns_hp
                    and q.energy >= ns_energy
                    and q.shields <= ns_shields):
                return  # dominated by existing state
            i += 1
    else:
        while i < n and queue[i].turn <= ns_turn:
            i += 1
    queue.insert(i, ns)


def _dp_insert_not_ready(queue: list, ns: "_DPState", *,
                         intended_pruning: bool = False) -> None:
    """Not-ready-move insertion (PvPoke lines 686-708).

    Insert BEFORE same-turn states (strict ``<``).  This gives
    charged-move KO paths priority over farm-down KOs at the same turn.

    Dominance check (lines 696-704) uses ``.hp``/``.shields`` (undefined
    on BattleState), so it is dead code in PvPoke.  Only active when
    ``intended_pruning=True``.

    Verified: the ``<`` insertion order produces 2 exact PvPoke matches
    and 3 closer scores for Azu vs Forretress (Sand+Rock) compared to
    the old ``<=`` order.
    """
    n = len(queue)
    ns_turn = ns.turn
    i = 0
    if intended_pruning:
        ns_hp = ns.hp
        ns_energy = ns.energy
        ns_shields = ns.shields
        while i < n and queue[i].turn < ns_turn:
            q = queue[i]
            if (q.hp <= ns_hp
                    and q.energy >= ns_energy
                    and q.shields <= ns_shields):
                return  # dominated by existing state
            i += 1
    else:
        while i < n and queue[i].turn < ns_turn:
            i += 1
    queue.insert(i, ns)


def pvpoke_dp(attacker: "BattlePokemon", defender: "BattlePokemon",
              *, intended_pruning: bool = False,
              bait_shields: bool = True) -> "int | None":
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

    intended_pruning:
        False (default) — replicate PvPoke's actual JS behavior.  The DP
        queue dominance checks (lines 600, 697) and farm-down blocking
        (line 479) reference ``.hp``/``.shields`` which are undefined on
        BattleState (stored as ``.oppHealth``/``.oppShields``), making
        them dead code.  Not-ready states insert with ``<`` (before
        same-turn), ready states use dedup + ``<=`` (after same-turn).

        True — what PvPoke apparently intended.  Dominance checks and
        farm-down blocking are functional (using our real ``.hp`` and
        ``.shields`` fields).  This prevents dominated states from
        accumulating in the queue.

    bait_shields:
        True (default) — PvPoke's simulate-mode default: the attacker
        may throw a cheap charged move first to burn an opponent shield,
        setting up a high-DPE follow-up.  Mirrors ``battle.baitShields=true``.

        False — "never bait." The attacker never deliberately throws a
        sub-optimal move to draw a shield. Farm-down always selects
        ``bestChargedMove``; bait-wait is disabled; near-KO plans prefer
        the max-damage move as the first throw. Useful for "can I win
        this without needing the bait to be called?" analysis.
    """
    fast_turns       = attacker.fast_move.get('_turns', 1)
    fast_energy      = attacker.fast_move.get('energyGain', 5)
    fast_damage      = attacker.fast_move_damage(defender)
    atk_fast_cd      = attacker.fast_move.get('cooldown', 500)
    opp_fast_cd      = defender.fast_move.get('cooldown', 500)
    opp_fast_damage  = defender.fast_move_damage(attacker)
    wins_cmp         = attacker.atk >= defender.atk

    # PvPoke's activeChargedMoves is sorted by energy (cheapest first).
    # Sort a copy so bandaid indices match PvPoke's convention.
    cms = sorted(attacker.charged_moves, key=lambda m: m['energy'])
    n_cms = len(cms)

    # Hoist per-cm constants into parallel arrays so the hot DP loop can
    # do array lookups instead of dict accesses + method calls. The damage
    # cache (BattlePokemon._cached_charged_dmgs) was populated by the
    # fast_move_damage() call above. Map sorted cms back through that.
    a_charged = attacker.charged_moves
    a_cm_dmgs = attacker._cached_charged_dmgs
    a_idx_map = attacker._cm_id_to_idx
    cm_dmgs    = [a_cm_dmgs[a_idx_map[id(m)]] for m in cms]
    cm_energy  = [m['energy'] for m in cms]
    # original-charged-moves index for each sorted entry — used by callers
    # that need to return an index into attacker.charged_moves
    cm_orig_idx = [a_idx_map[id(m)] for m in cms]
    # Per-cm self-debuff flag and net debuff delta — precomputed once so the
    # near-KO DP body can update its scalar plan summary in O(1) without dict
    # lookups on each move dispatch.
    cm_self_debuf = [1 if m.get('selfDebuffing', False) else 0 for m in cms]
    cm_debuf_delta = [_cm_debuf_delta(m) for m in cms]

    def _orig_idx(move: dict) -> int:
        """Map a move back to its index in attacker.charged_moves."""
        return a_idx_map[id(move)]

    def actual_dpe(i: int) -> float:
        return cm_dmgs[i] / cm_energy[i]

    def raw_dpe(m: dict) -> float:
        """PvPoke's move.dpe = power/energy (no type effectiveness)."""
        return m['power'] / m['energy']

    # ------------------------------------------------------------------ #
    # Break Mimikyu disguise ASAP (ActionLogic.js lines 236-241)
    # When facing a Pokemon with a protect effect and active disguise,
    # throw cheapest non-self-debuffing charged move immediately.
    # ------------------------------------------------------------------ #
    if (defender._form_change is not None
            and defender._form_change.effect == 'protect'
            and defender._form_disguise_active
            and defender.shields == 0):
        for _n in range(n_cms):
            if (attacker.energy >= cm_energy[_n]
                    and not cms[_n].get('selfDebuffing', False)):
                if _policy_debug:
                    _policy_log.append(
                        f"  DP[break_disguise]: {attacker.species} fires "
                        f"{cms[_n].get('moveId')} to break disguise")
                return cm_orig_idx[_n]

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
        a_energy    = attacker.energy
        a_atk       = attacker.atk
        d_atk       = defender.atk
        for n in range(n_cms - 1, -1, -1):
            cm_e = cm_energy[n]
            if a_energy >= cm_e:
                dmg = cm_dmgs[n]
                if dmg > prev_dmg:
                    max_dmg_idx = n
                    prev_dmg    = dmg
                # Double-fire: if have energy for two of same move and win CMP
                if (a_energy >= cm_e * 2
                        and a_atk > d_atk
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
        return cm_orig_idx[max_dmg_idx]

    # ------------------------------------------------------------------ #
    # ActionLogic.js lines 212-233: fire a lethal charged move immediately,
    # BEFORE OMT consideration.  Conditions (all must hold):
    #   - shields down
    #   - move would KO (hp <= damage)
    #   - move is not self-debuffing
    #   - fast move alone wouldn't also kill (preserve the energy if it's
    #     unnecessary to use a charged move)
    # Only the first two charged moves (n=0 and n=1) are checked (PvPoke
    # uses n==0 || (n==1 && !baitShields); pvpoke_dp uses selective bait
    # so baitShields=True → both n=0 and n=1 are eligible).
    # ------------------------------------------------------------------ #
    if defender.shields == 0:
        _fast_dmg = fast_damage
        d_hp      = defender.hp
        for _n in range(min(2, n_cms)):
            if attacker.energy >= cm_energy[_n]:
                _cm = cms[_n]
                if (cm_dmgs[_n] >= d_hp
                        and not _cm.get('selfDebuffing', False)
                        and d_hp > _fast_dmg):
                    if _policy_debug:
                        _policy_log.append(
                            f"  DP[lethal]: {attacker.species} fires "
                            f"{_cm.get('moveId')} (energy={attacker.energy})"
                        )
                    return cm_orig_idx[_n]

    # ------------------------------------------------------------------ #
    # optimizeMoveTiming (ActionLogic.js lines 237-344)
    # ------------------------------------------------------------------ #
    if _optimize_move_timing(attacker, defender):
        return None

    # Aegislash Shield form: farm energy before throwing charged moves.
    # PvPoke ActionLogic.js:957-961: delay unless the move would KO.
    if (attacker._form_change is not None
            and attacker._form_change.forms[int(attacker._form_is_alt)].species_id == 'aegislash_shield'
            and attacker.energy < 100 - (fast_energy / 2)):
        best_cm_dmg = max(cm_dmgs[n] for n in range(n_cms) if attacker.energy >= cm_energy[n]) if any(attacker.energy >= cm_energy[n] for n in range(n_cms)) else 0
        if best_cm_dmg < defender.hp:
            if _policy_debug:
                _policy_log.append(
                    f"  DP[aegislash_farm]: {attacker.species} farms energy "
                    f"(energy={attacker.energy}, threshold={100 - fast_energy // 2})")
            return None

    best_idx = max(range(n_cms), key=actual_dpe)
    best_cm  = cms[best_idx]

    # bestCycleDamage: fast moves needed to charge from 0 + one charge move
    fm_to_charge   = math.ceil(cm_energy[best_idx] / fast_energy)
    best_cycle_dmg = fast_damage * fm_to_charge + cm_dmgs[best_idx]

    # ------------------------------------------------------------------ #
    # Farm-down path
    # ------------------------------------------------------------------ #
    if defender.hp > 2 * best_cycle_dmg:
        selected_idx = best_idx

        # Bait only if opponent has shields AND would shield the best move.
        # cms is sorted by energy, so the cheapest is index 0.
        # Gated on bait_shields — no-bait mode always keeps selected_idx=best_idx.
        if (bait_shields
                and defender.shields > 0 and n_cms > 1
                and not cms[0].get('selfDebuffing', False)
                and would_shield(attacker, defender, best_cm)):
            selected_idx = 0

        if attacker.energy < cm_energy[selected_idx]:
            if _policy_debug:
                _policy_log.append(
                    f"  DP[farm]: {attacker.species} waits for "
                    f"{cms[selected_idx].get('moveId')} (energy={attacker.energy}/"
                    f"{cm_energy[selected_idx]})"
                )
            return None   # wait for the selected move
        if _policy_debug:
            _policy_log.append(
                f"  DP[farm]: {attacker.species} fires "
                f"{cms[selected_idx].get('moveId')} (energy={attacker.energy})"
            )
        return cm_orig_idx[selected_idx]

    # ------------------------------------------------------------------ #
    # Near-KO: DP to find the fastest charge-move sequence that KOs
    # ------------------------------------------------------------------ #
    final_state: "_DPState | None" = None
    iters = 0

    if _NEAR_KO_DP_JIT is not None:
        # Numba-JIT'd inner DP. Same algorithm as the Python loop below;
        # operates on numpy scalar arrays for ~5-10x inner-loop speedup.
        cm_dmgs_np    = _np.asarray(cm_dmgs, dtype=_np.float64)
        cm_energy_np  = _np.asarray(cm_energy, dtype=_np.int64)
        cm_self_db_np = _np.asarray(cm_self_debuf, dtype=_np.int8)
        cm_db_dlt_np  = _np.asarray(cm_debuf_delta, dtype=_np.int8)
        (found, _first, _max_idx, _has_deb, _deb_cnt,
         _f_turn, _f_hp, _f_sh, iters) = _NEAR_KO_DP_JIT(
            cm_dmgs_np, cm_energy_np, cm_self_db_np, cm_db_dlt_np,
            n_cms,
            int(attacker.energy),
            float(defender.hp),
            int(defender.shields),
            int(fast_damage),
            int(fast_energy),
            int(fast_turns),
            bool(intended_pruning),
        )
        if found:
            final_state = _DPState(0, _f_hp, _f_turn, _f_sh,
                                   _first, _max_idx, _has_deb, _deb_cnt)
        # else: final_state stays None → fall through to greedy fallback
    else:
        # Pure-Python fallback (numba unavailable). Same algorithm as the
        # JIT in _dp_jit.py — kept here so the project still runs without
        # numba installed.
        queue: list = [_DPState(attacker.energy, float(defender.hp), 0,
                                 defender.shields, -1, -1, 0, 0)]
        while queue and iters < 500:
            iters += 1
            curr = queue.pop(0)

            # KO achieved — this is the fastest plan (chance == 1 path → break)
            if curr.hp <= 0:
                final_state = curr
                break

            curr_e        = curr.energy
            curr_hp       = curr.hp
            curr_t        = curr.turn
            curr_sh       = curr.shields
            curr_first    = curr.first_idx
            curr_max_idx  = curr.max_dmg_idx
            curr_max_dmg  = cm_dmgs[curr_max_idx] if curr_max_idx >= 0 else -1.0
            curr_has_deb  = curr.has_debuf
            curr_deb_cnt  = curr.debuf_count
            for n in range(n_cms):
                move_dmg = cm_dmgs[n]
                move_e   = cm_energy[n]

                # Update scalar plan summary for the new state.
                new_first = curr_first if curr_first >= 0 else n
                if move_dmg > curr_max_dmg:
                    new_max_idx = n
                else:
                    new_max_idx = curr_max_idx
                new_has_deb = curr_has_deb | cm_self_debuf[n]
                new_deb_cnt = curr_deb_cnt + cm_debuf_delta[n]

                if curr_e >= move_e:
                    new_e  = curr_e - move_e
                    new_t  = curr_t + 1
                    new_sh = curr_sh
                    if curr_sh > 0:
                        new_hp = curr_hp - 1
                        new_sh -= 1
                    else:
                        new_hp = curr_hp - move_dmg

                    _dp_insert_ready(
                        queue,
                        _DPState(new_e, new_hp, new_t, new_sh,
                                 new_first, new_max_idx, new_has_deb, new_deb_cnt),
                        intended_pruning=intended_pruning)
                else:
                    fm_needed    = math.ceil((move_e - curr_e) / fast_energy)
                    turns_needed = fm_needed * fast_turns
                    new_e  = fm_needed * fast_energy + curr_e - move_e
                    new_t  = curr_t + turns_needed + 1
                    new_sh = curr_sh
                    if curr_sh > 0:
                        new_hp = curr_hp - fast_damage * fm_needed - 1
                        new_sh -= 1
                    else:
                        new_hp = curr_hp - fast_damage * fm_needed - move_dmg

                    _dp_insert_not_ready(
                        queue,
                        _DPState(new_e, new_hp, new_t, new_sh,
                                 new_first, new_max_idx, new_has_deb, new_deb_cnt),
                        intended_pruning=intended_pruning)

            if fast_damage > 0 and curr_hp > 0:
                fm_to_ko  = math.ceil(curr_hp / fast_damage)
                fd_turn   = curr_t + fm_to_ko * fast_turns
                fd_energy = curr_e + fast_energy * fm_to_ko
                _dp_insert_farm_down(
                    queue,
                    _DPState(fd_energy, 0.0, fd_turn, curr_sh,
                             curr_first, curr_max_idx, curr_has_deb, curr_deb_cnt),
                    intended_pruning=intended_pruning)

    # ------------------------------------------------------------------ #
    # Select move from plan
    # ------------------------------------------------------------------ #
    if final_state is None:
        # No KO found — fallback to best-DPE greedy
        affordable = [i for i in range(n_cms) if attacker.energy >= cm_energy[i]]
        if not affordable:
            return None
        best_sorted_idx = max(affordable, key=actual_dpe)
        return cm_orig_idx[best_sorted_idx]

    if final_state.first_idx < 0:
        # Farm-down plan: no charged moves needed, just fast-move to KO.
        # PvPoke returns undefined (no action) in this case.
        if _dp_trace:
            _policy_log.append(
                f"  DP-trace[{attacker.species}]: farm-down plan (no charged moves)")
        return None

    if _dp_trace:
        _policy_log.append(
            f"  DP-trace[{attacker.species}]: raw plan first="
            f"{cms[final_state.first_idx].get('moveId')}"
            f" max_dmg={cms[final_state.max_dmg_idx].get('moveId')}"
            f" has_deb={bool(final_state.has_debuf)}"
            f" turn={final_state.turn} hp={final_state.hp:.0f}"
            f" shields={final_state.shields} iters={iters}")

    has_debuffing_move = bool(final_state.has_debuf)
    final_first_thrown = final_state.first_idx
    final_max_dmg_idx  = final_state.max_dmg_idx

    # Bait-wait check (ActionLogic.js lines 820-835):
    # If shields are up and we can't yet afford cms[1] but it has better DPE
    # than our planned first move → wait for cms[1] instead.
    # PvPoke uses raw dpe (power/energy) here.
    # Skipped entirely when bait_shields=False (never delay a ready shot to
    # set up a bait).
    if bait_shields and defender.shields > 0 and n_cms > 1:
        cm1 = cms[1]
        if (attacker.energy < cm_energy[1]
                and raw_dpe(cm1) > raw_dpe(cms[final_first_thrown])
                and not cm1.get('selfDebuffing', False)):
            bait = True
            # Don't bait if an effective self-buffing move exists (line 826)
            if (raw_dpe(cm1) / raw_dpe(cms[0]) <= 1.5
                    and cms[0].get('selfBuffing', False)):
                bait = False
            if bait:
                if _dp_trace:
                    _policy_log.append(
                        f"  DP-trace[{attacker.species}]: bait-wait for {cm1.get('moveId')}")
                return None

    # PvPoke sorts plan by damage descending only when baitShields is falsy or
    # when opponent.shields == 0 AND no debuffing move (ActionLogic.js lines 850-858).
    # In scalar form: first_idx = max_dmg_idx (sort branch) or first_thrown.
    if (not bait_shields) or (defender.shields == 0 and not has_debuffing_move):
        first_idx = final_max_dmg_idx
    else:
        first_idx = final_first_thrown

    # Don't-bait-if-won't-shield (ActionLogic.js lines 838-847):
    # This one uses actual damage (move.damage / move.energy).  PvPoke reads
    # final_state.moves[0] (= first thrown) for fm0_dpe, then mutates
    # moves[0] = 1 — only takes effect when shields > 0 (so the sort branch
    # above does NOT fire), so we override `first_idx` directly here.
    # Skipped in no-bait mode: the plan-sort branch above already forced
    # max_dmg_idx, and no-bait never rewrites the first throw for bait reasons.
    if bait_shields and defender.shields > 0 and n_cms > 1:
        cm1 = cms[1]
        fm0_dpe = actual_dpe(final_first_thrown)
        if fm0_dpe > 0 and attacker.energy >= cm_energy[1]:
            dpe_ratio = actual_dpe(1) / fm0_dpe
            if dpe_ratio > 1.5 and not would_shield(attacker, defender, cm1):
                first_idx = 1

    first_move = cms[first_idx]

    # --- Post-DP bandaids (ActionLogic.js lines 861-935) ---

    # [861] Prefer low energy with better DPE when shields up (raw dpe)
    if (defender.shields > 0 and len(cms) > 1
            and attacker.energy >= cms[0]['energy']
            and cms[0]['energy'] <= first_move['energy']
            and raw_dpe(cms[0]) > raw_dpe(first_move)
            and not cms[0].get('selfDebuffing', False)):
        if _dp_trace:
            _policy_log.append(
                f"  DP-trace[{attacker.species}]: bandaid[861] prefer-low-energy:"
                f" {first_move.get('moveId')} → {cms[0].get('moveId')}")
        first_idx  = 0
        first_move = cms[first_idx]

    # [866] Prefer non-debuffing when shields down, both sides have significant HP,
    #       and the debuffing move won't KO.
    #       PvPoke uses move.damage which is only set as a side effect of the OMT
    #       "can KO" check (line 301). If OMT didn't fire, .damage is undefined
    #       and undefined/hp < 0.8 is NaN < 0.8 = false in JS → bandaid skips.
    _cached_dmg = first_move.get('_cached_damage')
    if (defender.shields == 0 and n_cms > 1
            and first_move.get('selfDebuffing', False)
            and first_move['energy'] > 50
            and attacker.hp / attacker.max_hp > 0.5
            and _cached_dmg is not None
            and _cached_dmg / defender.hp < 0.8):
        if _dp_trace:
            _policy_log.append(
                f"  DP-trace[{attacker.species}]: bandaid[866] avoid-self-debuff:"
                f" {first_move.get('moveId')} → {cms[0].get('moveId')}")
        first_idx  = 0
        first_move = cms[first_idx]

    # [871] Force more efficient move of the same energy (raw dpe)
    if (len(cms) > 1
            and cms[0]['energy'] == first_move['energy']
            and raw_dpe(cms[0]) > raw_dpe(first_move)
            and not cms[0].get('selfDebuffing', False)):
        if _dp_trace:
            _policy_log.append(
                f"  DP-trace[{attacker.species}]: bandaid[871] same-energy-better-dpe:"
                f" {first_move.get('moveId')} → {cms[0].get('moveId')}")
        first_idx  = 0
        first_move = cms[first_idx]

    # [876] Force more efficient similar-energy move if chosen is self-debuffing (raw dpe)
    if (len(cms) > 1
            and cms[0]['energy'] - 10 <= first_move['energy']
            and raw_dpe(cms[0]) > raw_dpe(first_move)
            and first_move.get('selfDebuffing', False)
            and not cms[0].get('selfDebuffing', False)):
        if _dp_trace:
            _policy_log.append(
                f"  DP-trace[{attacker.species}]: bandaid[876] avoid-debuff-similar-energy:"
                f" {first_move.get('moveId')} → {cms[0].get('moveId')}")
        first_idx  = 0
        first_move = cms[first_idx]

    # [881] Force more efficient similar-energy move if one is self-buffing (raw dpe)
    if (len(cms) > 1
            and cms[0]['energy'] - first_move['energy'] <= 5
            and raw_dpe(cms[0]) > raw_dpe(first_move)
            and cms[0].get('selfBuffing', False)):
        if _dp_trace:
            _policy_log.append(
                f"  DP-trace[{attacker.species}]: bandaid[881] prefer-self-buff:"
                f" {first_move.get('moveId')} → {cms[0].get('moveId')}")
        first_idx  = 0
        first_move = cms[first_idx]

    # [886] Don't bait with self-debuffing moves (raw dpe)
    # Gated on bait_shields — the whole bandaid is about rerouting a bait
    # choice, which is a no-op in no-bait mode.
    if bait_shields and defender.shields > 0 and len(cms) > 1:
        cm1 = cms[1]
        if (attacker.energy >= cm1['energy']
                and raw_dpe(cm1) > raw_dpe(first_move)
                and first_move.get('selfDebuffing', False)
                and not cm1.get('selfDebuffing', False)):
            if _dp_trace:
                _policy_log.append(
                    f"  DP-trace[{attacker.species}]: bandaid[886] no-debuff-bait:"
                    f" {first_move.get('moveId')} → {cm1.get('moveId')}")
            first_idx  = 1
            first_move = cm1

    # [895] While shields up, prefer close non-debuffing when debuffing won't KO
    if defender.shields > 0 and len(cms) > 1:
        if (cms[0].get('selfDebuffing', False)
                and not cms[1].get('selfBuffing', False)):
            # Is attacker baiting or will debuffing move not come close to KO?
            if (bait_shields
                    or defender.hp - attacker.charged_move_damage(cms[0], defender) > 10):
                # Is the second move close in energy and DPE? (raw dpe)
                if (cms[1]['energy'] - cms[0]['energy'] <= 10
                        and raw_dpe(cms[1]) / raw_dpe(cms[0]) > 0.7):
                    if _dp_trace:
                        _policy_log.append(
                            f"  DP-trace[{attacker.species}]: bandaid[895] shields-up-prefer-non-debuff:"
                            f" {first_move.get('moveId')} → {cms[1].get('moveId')}")
                    first_idx  = 1
                    first_move = cms[1]

    # [910] Defer self-debuffing until after survivable charged moves
    if (first_move.get('selfDebuffing', False)
            and attacker.shields == 0
            and attacker.energy < 100
            and defender.charged_moves):
        opp_best = max(defender.charged_moves,
                       key=lambda m: defender.charged_move_damage(m, attacker))
        if (defender.energy >= opp_best['energy']
                and not would_shield(defender, attacker, opp_best)
                and not first_move.get('selfBuffing', False)):
            if _dp_trace:
                _policy_log.append(
                    f"  DP-trace[{attacker.species}]: bandaid[910] defer-self-debuff:"
                    f" waiting for opponent to fire {opp_best.get('moveId')}")
            return None

    # [918] If self-debuffing move doesn't KO, stack as many as possible
    if first_move.get('selfDebuffing', False):
        target_energy = (100 // first_move['energy']) * first_move['energy']
        if attacker.energy < target_energy:
            move_dmg = attacker.charged_move_damage(first_move, defender)
            opp_fast_dmg = defender.fast_move_damage(attacker)
            opp_fast_cd = defender.fast_move.get('cooldown', 500)
            atk_fast_cd = attacker.fast_move.get('cooldown', 500)
            if ((defender.hp > move_dmg or defender.shields != 0)
                    and (attacker.hp > opp_fast_dmg * 2
                         or opp_fast_cd - atk_fast_cd > 500)):
                if _dp_trace:
                    _policy_log.append(
                        f"  DP-trace[{attacker.species}]: bandaid[918] stack-self-debuff:"
                        f" energy={attacker.energy}/{target_energy}, waiting")
                return None
        elif defender.shields > 0 and len(cms) > 1:
            # At target energy and shields up: use cheaper non-debuff if self-buffing
            # or if opponent would shield (line 929-933)
            cm0 = cms[0]
            if (cm0['energy'] - first_move['energy'] <= 10
                    and not cm0.get('selfDebuffing', False)):
                if (cm0.get('selfBuffing', False)
                        or would_shield(attacker, defender, first_move)):
                    if _dp_trace:
                        _policy_log.append(
                            f"  DP-trace[{attacker.species}]: bandaid[929] stack-switch:"
                            f" {first_move.get('moveId')} → {cm0.get('moveId')}")
                    first_idx  = 0
                    first_move = cm0

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
    return _orig_idx(first_move)


# Policy callback for intended-pruning mode (usable as charged_policy_N).
pvpoke_dp_intended = partial(pvpoke_dp, intended_pruning=True)


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

@dataclass(slots=True)
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
    _queued_fast:    "tuple[int, dict] | None" = field(init=False, repr=False)
    # Stat stages: each in [-4, +4]
    atk_stage: int = field(init=False, repr=False)
    def_stage: int = field(init=False, repr=False)
    # Buff apply meters for deterministic probabilistic buffs: {moveId: count}
    _buff_apply_meters: dict = field(init=False, repr=False)

    # Damage cache (vs current opponent at current stat stages).
    # Within one simulate() call, charged_move_damage(move, defender) is fully
    # determined by (self.atk * stage_mult, defender.def_ * stage_mult, move,
    # types). The pvpoke_dp policy can call this hundreds of times per
    # simulate() with the same inputs — we memoize the full per-move table
    # and invalidate via key comparison.
    _dmg_cache_opp_id:    int       = field(init=False, repr=False)
    _dmg_cache_atk_stage: int       = field(init=False, repr=False)
    _dmg_cache_def_stage: int       = field(init=False, repr=False)
    _cached_fast_dmg:     int       = field(init=False, repr=False)
    _cached_charged_dmgs: list      = field(init=False, repr=False)
    _cm_id_to_idx:        dict      = field(init=False, repr=False)

    # Form change state (None for Pokemon without form changes)
    _form_change:          "FormChangeConfig | None" = field(init=False, repr=False)
    _form_is_alt:          bool = field(init=False, repr=False)
    _form_disguise_active: bool = field(init=False, repr=False)

    def __post_init__(self):
        self.hp                = self.max_hp
        self.energy            = min(ENERGY_CAP, max(0, self.initial_energy))
        self.cooldown          = 0
        self._fm_since_charge  = 0
        self._queued_fast      = None
        self.atk_stage         = 0
        self.def_stage         = 0
        self._buff_apply_meters = {}
        # Damage cache starts invalid (opp id -1 never matches any real id).
        self._dmg_cache_opp_id    = -1
        self._dmg_cache_atk_stage = 0
        self._dmg_cache_def_stage = 0
        self._cached_fast_dmg     = 0
        self._cached_charged_dmgs = []
        # Identity-keyed lookup so charged_move_damage(move, ...) can find
        # its precomputed entry even when the policy passes a sorted copy
        # of self.charged_moves (same dict objects, different order).
        self._cm_id_to_idx = {id(cm): i for i, cm in enumerate(self.charged_moves)}
        # Form change state
        self._form_change = None
        self._form_is_alt = False
        self._form_disguise_active = False

    @classmethod
    def from_pokemon(cls, pokemon, fast_move: dict, charged_moves: list[dict],
                     shields: int = 2, initial_energy: int = 0,
                     league_cp: int | None = None) -> "BattlePokemon":
        """Build a BattlePokemon from a Pokemon dataclass + move dicts."""
        from .data import load_gamemaster
        from .formchange import build_form_change_state
        gm  = load_gamemaster()
        mon = next(m for m in gm['pokemon'] if m['speciesName'] == pokemon.species)
        types = parse_types(mon)
        bp = cls(
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
        # Set up form change if applicable
        if league_cp is None:
            league_cp = 1500  # default to GL
        fc = build_form_change_state(
            mon, pokemon.atk_iv, pokemon.def_iv, pokemon.sta_iv,
            pokemon.level, league_cp, pokemon.shadow,
            fast_move, charged_moves,
        )
        if fc is not None:
            bp._form_change = fc
            if fc.effect == 'protect':
                bp._form_disguise_active = True
        return bp

    @property
    def current_form_trigger(self) -> str | None:
        """Return the trigger for changing FROM the current form, or None."""
        if self._form_change is None:
            return None
        return self._form_change.forms[int(self._form_is_alt)].trigger

    def change_form(self, opponent: "BattlePokemon") -> None:
        """Apply the form change to this BattlePokemon."""
        from .formchange import apply_form_change
        apply_form_change(self, opponent)

    def _ensure_dmg_cache(self, defender: "BattlePokemon") -> None:
        """Populate _cached_fast_dmg and _cached_charged_dmgs vs `defender`
        at the current stat stages, if not already valid."""
        if (self._dmg_cache_opp_id == id(defender)
                and self._dmg_cache_atk_stage == self.atk_stage
                and self._dmg_cache_def_stage == defender.def_stage):
            return
        atk_eff = self.atk * _stat_stage_mult(self.atk_stage)
        def_eff = defender.def_ * _stat_stage_mult(defender.def_stage)
        my_types  = self.types
        opp_types = defender.types
        fm = self.fast_move
        self._cached_fast_dmg = calc_damage(
            fm['power'], atk_eff, def_eff,
            fm['type'], my_types, opp_types,
        )
        self._cached_charged_dmgs = [
            calc_damage(cm['power'], atk_eff, def_eff,
                        cm['type'], my_types, opp_types)
            for cm in self.charged_moves
        ]
        self._dmg_cache_opp_id    = id(defender)
        self._dmg_cache_atk_stage = self.atk_stage
        self._dmg_cache_def_stage = defender.def_stage

    def fast_move_damage(self, defender: "BattlePokemon") -> int:
        if (self._dmg_cache_opp_id != id(defender)
                or self._dmg_cache_atk_stage != self.atk_stage
                or self._dmg_cache_def_stage != defender.def_stage):
            self._ensure_dmg_cache(defender)
        return self._cached_fast_dmg

    def charged_move_damage(self, move: dict, defender: "BattlePokemon") -> int:
        if (self._dmg_cache_opp_id != id(defender)
                or self._dmg_cache_atk_stage != self.atk_stage
                or self._dmg_cache_def_stage != defender.def_stage):
            self._ensure_dmg_cache(defender)
        return self._cached_charged_dmgs[self._cm_id_to_idx[id(move)]]


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
# Buff/debuff application
# ---------------------------------------------------------------------------

def _apply_move_buffs(
    attacker: "BattlePokemon",
    defender: "BattlePokemon",
    move: dict,
) -> None:
    """
    Apply stat stage changes from a charged move.

    Fires even when the move is shielded (shieldBuffModifier defaults to 0 in
    PvPoke, meaning no suppression).  Uses a deterministic meter for moves with
    buffApplyChance < 1: the buff fires every floor(1/chance) uses (simulate
    mode equivalent of PvPoke's buffApplyMeter logic).
    """
    buffs = move.get('buffs')
    if not buffs:
        return
    chance_str = move.get('buffApplyChance', '0')
    chance     = float(chance_str) if chance_str else 0.0
    if chance <= 0:
        return

    move_id   = move.get('moveId', '')
    meter     = attacker._buff_apply_meters.get(move_id, 0) + 1
    threshold = round(1.0 / chance)   # matches PvPoke's Math.round(1/buffApplyChance)

    if meter >= threshold:
        attacker._buff_apply_meters[move_id] = 0
        atk_chg = buffs[0]
        def_chg = buffs[1]
        target  = move.get('buffTarget', 'opponent')
        if target in ('self', 'both'):
            attacker.atk_stage = max(-4, min(4, attacker.atk_stage + atk_chg))
            attacker.def_stage = max(-4, min(4, attacker.def_stage + def_chg))
        if target in ('opponent', 'both'):
            defender.atk_stage = max(-4, min(4, defender.atk_stage + atk_chg))
            defender.def_stage = max(-4, min(4, defender.def_stage + def_chg))
    else:
        attacker._buff_apply_meters[move_id] = meter


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def simulate(
    p0: BattlePokemon,
    p1: BattlePokemon,
    *,
    shield_policy_0: ShieldPolicy   = pvpoke_simulate_shield,
    shield_policy_1: ShieldPolicy   = pvpoke_simulate_shield,
    charged_policy_0: ChargedMovePolicy = bait_with_cheapest,
    charged_policy_1: ChargedMovePolicy = bait_with_cheapest,
    log: bool = False,
    debug: bool = False,
    trace_shields: bool = False,
    trace_dp: bool = False,
) -> BattleResult:
    """
    Run a 1v1 battle between p0 and p1 and return the result.

    p0 and p1 are mutated in place — reset them before reuse.

    debug=True also enables policy decision logging (OMT fires, DP choices).
    Policy log lines are interleaved into BattleResult.timeline at the turn
    they occur; they are indented with two leading spaces for easy filtering.
    Implies log=True.

    trace_shields=True logs every shield policy call with inputs and results.
    trace_dp=True logs DP queue plan and bandaid decisions.
    Both imply log=True and debug=True.
    """
    global _policy_debug, _policy_log, _shield_trace, _dp_trace

    if trace_shields or trace_dp:
        debug = True
    if debug:
        log = True
    _policy_debug  = debug
    _shield_trace  = trace_shields
    _dp_trace      = trace_dp
    _policy_log    = []

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

        # --- 2. Decide and queue actions ---
        # Mirrors PvPoke's cooldownsToSet mechanism: both pokemon see each
        # other's pre-queuing state at decision time. Implemented in three
        # phases:
        #
        # Phase A — detect fast-move landings (but keep _queued_fast set so
        #   the turnsToLive DP can see in-flight FMs during decisions).
        # Phase B — collect decisions (no state mutation; each pokemon sees
        #   the other's cooldown/energy BEFORE any new queuing this turn).
        # Phase C — apply decisions and clear landed-FM state.
        charged_actions = []   # list of (actor_index, move_dict)
        fast_landings   = []   # fast moves that land this turn
        _fired_fast     = []   # indices of pokemon whose queued FM fires now

        # Phase A: mark FMs that land this turn (added to fast_landings).
        # _queued_fast is intentionally NOT cleared here; it stays set so
        # that Phase B decision-making can observe the in-flight state.
        for i, p in enumerate(pokemon):
            if p._queued_fast is not None:
                queued_turn, qmove = p._queued_fast
                duration = qmove['_turns']
                if (turn - queued_turn) >= duration - 1:
                    fast_landings.append((i, qmove))
                    _fired_fast.append(i)

        # Phase B: collect decisions; no state changes yet.
        # Each pokemon with cooldown==0 AND no pending multi-turn FM decides.
        # Note: pokemon whose FM fired in Phase A still have _queued_fast set
        # and cooldown > 0, so they cannot decide this turn (correct: the FM
        # fires in step 3 and only then is their cooldown reset to 0).
        _pending: list = []   # (i, 'charged'|'fast_1'|'fast_multi', data)
        for i, p in enumerate(pokemon):
            opponent = pokemon[1 - i]
            charged_pol, _ = policies[i]

            if p.cooldown == 0 and p._queued_fast is None:
                move_idx = charged_pol(p, opponent)
                if move_idx is not None:
                    _pending.append((i, 'charged', move_idx))
                else:
                    fm = p.fast_move
                    log_event(f"{p.species} uses {fm.get('name', fm['moveId'])}")
                    if fm['_turns'] == 1:
                        # PvPoke: requiredTimeToPass = 0 → fires same step.
                        _pending.append((i, 'fast_1', fm))
                    else:
                        _pending.append((i, 'fast_multi', fm))

        # Flush any policy-debug entries generated during Phase B.
        if _policy_debug and _policy_log:
            for entry in _policy_log:
                timeline.append(f"T{turn:>3}: {entry.lstrip()}")
            _policy_log.clear()

        # Phase C: apply decisions and clear fired-FM state.
        # Clear _queued_fast only for FMs that fired in Phase A.
        for i in _fired_fast:
            pokemon[i]._queued_fast = None

        for i, action_type, data in _pending:
            p = pokemon[i]
            if action_type == 'charged':
                charged_actions.append((i, p.charged_moves[data]))
            elif action_type == 'fast_1':
                fast_landings.append((i, data))
                p.cooldown = 1   # blocks re-acting until next turn
            else:   # 'fast_multi'
                p._queued_fast = (turn, data)
                p.cooldown = data['_turns']

        # --- 3. Resolve fast move landings (fire BEFORE charged moves) ---
        # Naturally-due fast moves resolve before charged moves. When two fast
        # moves land simultaneously, the game resolves them in descending atk
        # order (higher effective attack fires first). PvPoke matches this.
        if len(fast_landings) > 1:
            fast_landings.sort(key=lambda ia: pokemon[ia[0]].atk, reverse=True)
        for actor_idx, move in fast_landings:
            attacker = pokemon[actor_idx]
            defender = pokemon[1 - actor_idx]

            # PvPoke Battle.js lines 448-450: a dead pokemon's in-flight fast move
            # is only invalid if faintSource == "charged".  In step 3 (fast landings)
            # the only possible kill source is a fast move, so attacker.hp <= 0 here
            # means faintSource="fast" → still valid.  Skip only on dead defender.
            if defender.hp <= 0:
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

        charged_ko = set()  # track Pokemon KO'd by charged moves this turn

        for actor_idx, move in charged_actions:
            attacker = pokemon[actor_idx]
            defender = pokemon[1 - actor_idx]

            # PvPoke Battle.js line 464-467: cancel if KO'd by a
            # higher-priority charged move (CMP).
            if use_priority and attacker.hp <= 0 and actor_idx in charged_ko:
                continue

            # PvPoke Battle.js lines 471-490: cancel a charged move when the
            # attacker was killed by the opponent's fast move this turn, UNLESS
            # the opponent is also throwing a charged move this turn (the
            # opponentChargedMoveThisTurn exception — simultaneous charged moves
            # are allowed even if one side was killed by a fast move).
            if attacker.hp <= 0:
                opponent_also_charged = any(ai == 1 - actor_idx
                                            for ai, _ in charged_actions)
                if not opponent_also_charged:
                    continue

            if attacker.energy < move['energy']:
                continue   # raced to this — no longer affordable

            if defender.hp <= 0:
                continue   # defender already fainted from fast move this turn

            attacker.energy -= move['energy']

            # Form change: activate_charged (Aegislash Shield -> Blade)
            # Fires BEFORE damage so charged move uses new form's attack.
            _trigger = attacker.current_form_trigger
            if _trigger == 'activate_charged':
                _fc_mid = attacker._form_change.forms[int(attacker._form_is_alt)].move_id
                if _fc_mid == 'ANY' or _fc_mid == move['moveId']:
                    attacker.change_form(defender)
                    log_event(f"{attacker.species} changed form")

            _, shield_pol = policies[1 - actor_idx]
            use_shield    = shield_pol(attacker, defender, move)

            if use_shield and defender.shields > 0:
                dmg = 1
                defender.shields -= 1

                # Form change: activate_shield (Aegislash Blade -> Shield)
                if defender.current_form_trigger == 'activate_shield':
                    defender.change_form(attacker)
                    log_event(f"{defender.species} changed form (shielded)")

                log_event(f"{attacker.species} uses {move.get('name', move['moveId'])} → SHIELDED (1 dmg)")
            else:
                dmg = attacker.charged_move_damage(move, defender)

                # Form change: charged_move_damage / Mimikyu disguise
                if (defender._form_disguise_active
                        and defender.current_form_trigger == 'charged_move_damage'
                        and defender._form_change is not None
                        and defender._form_change.effect == 'protect'):
                    dmg = 1
                    defender._form_disguise_active = False
                    defender.change_form(attacker)
                    log_event(f"{defender.species} disguise busted (1 dmg)")
                else:
                    log_event(f"{attacker.species} uses {move.get('name', move['moveId'])} → {dmg} dmg")

            defender.hp = max(0, defender.hp - dmg)
            if defender.hp <= 0:
                charged_ko.add(1 - actor_idx)

            # Apply stat stage buffs/debuffs (fires even when shielded)
            _apply_move_buffs(attacker, defender, move)

            # Form change: charged_move (Morpeko toggle)
            _trigger = attacker.current_form_trigger
            if _trigger == 'charged_move':
                _fc_mid = attacker._form_change.forms[int(attacker._form_is_alt)].move_id
                if _fc_mid == 'ANY' or _fc_mid == move['moveId']:
                    attacker.change_form(defender)
                    log_event(f"{attacker.species} changed form")

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
