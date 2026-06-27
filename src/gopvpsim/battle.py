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

# Optional numba JIT for the near-KO DP loop and the turnsToLive sub-DP.
# If unavailable (numba not installed, LLVM mismatch, etc.), pvpoke_dp and
# _calc_turns_to_live fall back to the pure-Python loops further down.
try:
    import numpy as _np
    from ._dp_jit import _near_ko_dp_jit as _NEAR_KO_DP_JIT
    from ._dp_jit import _calc_ttl_jit as _CALC_TTL_JIT
except Exception:                       # pragma: no cover - jit optional
    _np = None
    _NEAR_KO_DP_JIT = None
    _CALC_TTL_JIT = None

ENERGY_CAP = 100
# Infinite-loop guard, NOT a faithful port of PvPoke's timeout. PvPoke ends
# battles when its display clock passes 240,000 ms (Battle.js:653), and that
# clock mixes 500 ms turns with 10,000 ms charged-move minigame adjustments --
# so its effective turn cap shrinks with every charged throw. Documented as
# an intentional divergence (DEVELOPER_NOTES "Known divergences"): the
# bulkiest realistic GL wall fight (Carbink mirror, 2v2) ends at 85 turns,
# so neither guard is reachable in practice.
MAX_TURNS  = 500


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
# Key: (your_fast_turns, their_fast_turns)  -- capped at 5 for each
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


def always_shield(attacker: "BattlePokemon", defender: "BattlePokemon", move: dict,
                  mechanics: str = 'legacy') -> bool:
    return defender.shields > 0

def never_shield(attacker: "BattlePokemon", defender: "BattlePokemon", move: dict,
                 mechanics: str = 'legacy') -> bool:
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

def _estimate_best_cm(owner: "BattlePokemon", opponent: "BattlePokemon") -> "tuple[int, dict] | tuple[None, None]":
    """PvPoke's bestChargedMove for `owner` vs `opponent`.

    Returns (idx, move) where idx indexes owner.charged_moves. Delegates
    to the pvpoke_dp setup cache, whose ``best_idx`` runs PvPoke's
    selectBestChargedMove (Pokemon.js:790-822) on the energy-sorted,
    priority-shuffled move list -- including the literal SUPER_POWER
    carve-out (Pokemon.js:799): Superpower only displaces the incumbent
    when its DPE edge exceeds .3, where any other move needs just .03.

    The previous max-actual-DPE approximation here returned SUPER_POWER
    for Malamar-likes, which wrongly entered the Battle.js:1105-1124
    defender-bestCM shield branch below; PvPoke's bestChargedMove there
    is the shuffled, carved-out pick (Foul Play for Malamar vs most of
    the GL pool), so PvPoke never enters that branch and always-shields.
    (2026-06-12 oracle grid, bestcm_estimate family: 38 cells.)
    """
    if not owner.charged_moves:
        return (None, None)
    dp = owner._ensure_dp_cache(opponent)
    slot = dp['best_idx']
    return (dp['order'][slot], dp['cms'][slot])


def _cheapest_cm(owner: "BattlePokemon") -> "dict | None":
    """Approximate PvPoke's activeChargedMoves[0] (priority slot).

    PvPoke's priority shuffle (Pokemon.js:711-787) reorders by buff/cost;
    the slot-0 move after shuffle is typically the cheapest-energy
    non-special move. We use cheapest-by-energy as a defensible proxy.
    """
    if not owner.charged_moves:
        return None
    return min(owner.charged_moves, key=lambda m: m['energy'])


def pvpoke_simulate_shield(attacker: "BattlePokemon", defender: "BattlePokemon", move: dict,
                           mechanics: str = 'legacy') -> bool:
    """
    PvPoke's simulate-mode shield policy (Battle.js line 1077).

    ``mechanics`` is threaded through to ``would_shield`` for the experimental
    new-turn-system scaffold (mechanics='new'). NOTE: the audit of 2026-06-24
    found NO mechanically-grounded new-clock adjustment for the shield policy
    -- the only turn-based gate (the selfDefenseDebuffing cycle-KO branch's
    ``turns_to_next >= att_turns_to_next`` comparison) shifts +1 on BOTH sides
    under the new clock (defender's and attacker's charged both resolve one
    turn later), so it washes out. The parameter is plumbed for future
    re-tuning; today new == legacy for the shield decision. (The grounded
    new-clock adjustments live in _calc_turns_to_live and _optimize_move_timing.)

    For standard charged moves: always shield (useShield = true).
    For selfBuffing moves (sub-filtered to self-atk-buff / opp-def-debuff):
    use the wouldShield heuristic.
    This mirrors Battle.js: useShield = true, then overridden only for
    move.selfBuffing (Battle.js:1090-1101) and for the
    defender-bestChargedMove-selfDefenseDebuffing branch (Battle.js:1105-1124)
    where the defender saves shields for the post-self-debuff window.

    Note the INCOMING move's selfDefenseDebuffing flag routes nothing in
    Battle.js: its only selfDefenseDebuffing test (line 1105) is on the
    defender's own bestChargedMove. A self-def-debuffing nuke like
    Superpower is not selfBuffing (GameMaster.js:873 sets selfBuffing only
    for positive self-buffs and guaranteed opponent debuffs), so PvPoke
    simply always-shields it. We previously also routed incoming
    selfDefenseDebuffing moves through wouldShield -- a port error removed
    2026-06-13 (see DEVELOPER_NOTES "Open divergences", RESOLVED entry).
    """
    if defender.shields <= 0:
        if _shield_trace:
            _policy_log.append(
                f"  shield({defender.species} sh=0 vs {move.get('moveId')}): False (no shields)")
        return False

    use_shield = True  # Battle.js:1084 default

    # PvPoke Battle.js lines 1083-1101: use wouldShield heuristic for
    # self-buffing moves and guaranteed opponent-def-debuff moves.
    # PvPoke's selfBuffing flag (GameMaster.js:873) covers all guaranteed
    # opponent debuffs AND positive self-buffs.  The shield check
    # (Battle.js:1090-1101) sub-filters to self-atk-buff or opp-def-debuff
    # before routing to wouldShield.  We replicate that sub-filter here.
    self_buffing = move.get('selfBuffing', False)
    buffs = move.get('buffs')
    bt    = move.get('buffTarget')
    # PvPoke Battle.js:1091-1100 sub-filter: self-atk-buff or opp-def-debuff;
    # buffTarget 'both' qualifies via buffsSelf[0] > 0 or buffsOpponent[1] < 0.
    _bs = move.get('buffsSelf')
    _bo = move.get('buffsOpponent')
    sb_subroute = (self_buffing and buffs is not None
                   and ((bt == 'self' and buffs[0] > 0)
                        or (bt == 'opponent' and buffs[1] < 0)
                        or (bt == 'both' and _bs is not None
                            and _bo is not None
                            and (_bs[0] > 0 or _bo[1] < 0))))
    use_heuristic_incoming = sb_subroute
    if use_heuristic_incoming:
        use_shield = would_shield(attacker, defender, move, mechanics=mechanics)
        if _shield_trace:
            tag = "oppDefDebuff" if bt == 'opponent' else "selfBuff"
            _policy_log.append(
                f"  shield({defender.species} sh={defender.shields} vs"
                f" {move.get('moveId')} [incoming {tag}]): → wouldShield={use_shield}")

    # Battle.js:1105-1124 -- defender saves shields for its own post-self-
    # defense-debuff fragility window.  Fires when defender.bestChargedMove
    # is selfDefenseDebuffing.  Two sub-branches by attacker.shields.
    d_best_idx, d_best_cm = _estimate_best_cm(defender, attacker)
    if d_best_cm is not None and d_best_cm.get('selfDefenseDebuffing', False):
        sd_value = would_shield(attacker, defender, move, mechanics=mechanics)
        if attacker.shields > 0:
            use_shield = sd_value
            if _shield_trace:
                _policy_log.append(
                    f"  shield({defender.species} sh={defender.shields} vs"
                    f" {move.get('moveId')} [defBestCM={d_best_cm.get('moveId')} selfDefDebuff,"
                    f" attShields={attacker.shields}]): → wouldShield={sd_value}")
        else:
            a_first = _cheapest_cm(attacker)
            if a_first is not None:
                d_fast_energy = defender.fast_move.get('energyGain', 5)
                d_fast_turns  = defender.fast_move.get('_turns', 1)
                d_fast_dmg    = defender.fast_move_damage(attacker)
                fast_to_next = math.ceil(
                    max(0, d_best_cm['energy'] - defender.energy) / d_fast_energy)
                turns_to_next = fast_to_next * d_fast_turns
                cycle_dmg = (fast_to_next * d_fast_dmg
                             + defender.charged_move_damage(d_best_cm, attacker))

                a_fast_energy = attacker.fast_move.get('energyGain', 5)
                a_fast_turns  = attacker.fast_move.get('_turns', 1)
                att_fast_to_next = math.ceil(
                    max(0, a_first['energy'] - attacker.energy) / a_fast_energy)
                att_turns_to_next = att_fast_to_next * a_fast_turns
                if attacker.cmp_atk > defender.cmp_atk:
                    att_turns_to_next -= 1

                if (turns_to_next >= att_turns_to_next
                        and attacker.hp <= cycle_dmg):
                    use_shield = sd_value
                    if _shield_trace:
                        _policy_log.append(
                            f"  shield({defender.species} sh={defender.shields} vs"
                            f" {move.get('moveId')} [defBestCM={d_best_cm.get('moveId')} selfDefDebuff,"
                            f" attShields=0, cycleKO]): → wouldShield={sd_value}")
                elif _shield_trace:
                    _policy_log.append(
                        f"  shield({defender.species} sh={defender.shields} vs"
                        f" {move.get('moveId')} [defBestCM={d_best_cm.get('moveId')} selfDefDebuff,"
                        f" attShields=0, no cycleKO: hp={attacker.hp} cycleDmg={cycle_dmg}"
                        f" turnsCmp={turns_to_next}vs{att_turns_to_next}]): keep useShield={use_shield}")

    # Aegislash Shield form: don't waste shields if damage < half HP
    # PvPoke Battle.js:1126
    if (defender._form_change is not None
            and defender._form_change.forms[int(defender._form_is_alt)].species_id == 'aegislash_shield'
            and attacker.charged_move_damage(move, defender) * 2 < defender.hp):
        if _shield_trace:
            _policy_log.append(
                f"  shield({defender.species} sh={defender.shields} vs"
                f" {move.get('moveId')}): False (Aegislash Shield suppression)")
        return False

    if _shield_trace and not use_heuristic_incoming and not (d_best_cm is not None and d_best_cm.get('selfDefenseDebuffing', False)):
        _policy_log.append(
            f"  shield({defender.species} sh={defender.shields} vs"
            f" {move.get('moveId')}): True (always shield)")
    return use_shield

def use_first_available(attacker: "BattlePokemon", defender: "BattlePokemon",
                        mechanics: str = 'legacy') -> "int | None":
    """Throw the first charged move we have enough energy for."""
    for i, move in enumerate(attacker.charged_moves):
        if attacker.energy >= move['energy']:
            return i
    return None

def bait_with_cheapest(attacker: "BattlePokemon", defender: "BattlePokemon",
                       mechanics: str = 'legacy') -> "int | None":
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
        # No shields -- throw highest damage
        return max(affordable, key=lambda im: im[1]['power'])[0]

def no_bait(attacker: "BattlePokemon", defender: "BattlePokemon",
            mechanics: str = 'legacy') -> "int | None":
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

def pvpoke_ai(attacker: "BattlePokemon", defender: "BattlePokemon",
              mechanics: str = 'legacy') -> "int | None":
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
    mechanics: str = 'legacy',
) -> float:
    """
    Port of PvPoke's turnsToLive sub-DP (ActionLogic.js lines 38-138).

    ``mechanics`` is threaded as scaffold for the experimental new-turn-system
    decision layer, but currently produces NO behavior change: new == legacy
    here. A "+1 on the charged-KO branch under new" correction was tried
    (mechanically grounded -- the defender's charged KO lands one turn later)
    and REVERTED 2026-06-24: feeding the inflated ttl into pvpoke_dp's fire_now
    made glass-cannon attackers (e.g. Aegislash Blade) DELAY their lethal
    charged move and bleed HP, regressing ~8+ GL matchups vs the
    new-resolution/legacy-decisions baseline (Aegislash Blade vs Tinkaton 2-1:
    644 -> 132). The grounded new-clock decision changes are being rebuilt
    against a non-regression corpus (see scripts and docs/validations); until a
    change clears that floor, new uses the legacy decision path verbatim.

    Simulates the defender's attack sequence to estimate how many turns until
    the attacker is KO'd.  Returns math.inf if a KO is not found.

    State tuple: (hp, opEnergy, turn, shields)
      hp        – attacker's remaining HP
      opEnergy  – defender's energy
      turn      – turns into the future for this state
      shields   – attacker's remaining shields

    The original PvPoke code does ``queue.unshift()`` and ``queue.shift()``
    (push/pop at the front).  Both ends behave like a stack here -- we read
    the most-recently-pushed state next -- so a list with ``append()``/
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
    wins_cmp          = attacker.cmp_atk >= defender.cmp_atk

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

    if _CALC_TTL_JIT is not None:
        # Numba-JIT'd kernel (same loop as the pure-Python below).
        # Defender-side damage/energy buffers were rebuilt alongside the
        # damage cache by fast_move_damage() above -- no per-call asarray.
        # The CMP turn bonus is loop-invariant, so it's hoisted here.
        cmp_bonus = (attacker.cmp_atk > defender.cmp_atk
                     and defender.fast_move.get('cooldown', 500)
                         % attacker.fast_move.get('cooldown', 500) == 0)
        ok, ttl = _CALC_TTL_JIT(
            initial[0], initial[1], initial[2], initial[3],
            opp_fast_damage, opp_fast_energy, opp_fast_turns,
            atk_fast_turns, wins_cmp, cmp_bonus,
            defender._cached_charged_dmgs_np, defender._cm_energy_np,
            ENERGY_CAP,
        )
        if ok:
            # Keep the historical return types: int for finite, math.inf
            # otherwise (turn counts are small, exact in float64).
            return math.inf if ttl == math.inf else int(ttl)
        # stack overflow (never expected) → fall through to Python loop

    # Pure-Python fallback (numba unavailable). Same algorithm as the JIT
    # in _dp_jit.py -- kept so the project still runs without numba.
    # Hoist defender's charged-move energy + damage into parallel arrays so
    # the inner loop avoids method/dict lookups. The damage cache was
    # populated by defender.fast_move_damage(attacker) above.
    d_cm_dmgs   = defender._cached_charged_dmgs
    d_cm_energy = [cm['energy'] for cm in defender.charged_moves]
    n_d_cms     = len(d_cm_energy)
    fastest_cm_energy = min(d_cm_energy) if d_cm_energy else 0

    turns_to_live: float = math.inf

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
                        if attacker.cmp_atk > defender.cmp_atk and opp_cd % atk_cd == 0:
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
                # NO energy cap: PvPoke's turnsToLive DP lets hypothetical
                # defender energy exceed 100 (ActionLogic.js fast-push has
                # no Math.min), which changes KO detection near full
                # energy. The real battle loop caps; this worst-case
                # estimator deliberately mirrors PvPoke (review finding E7).
                c_op_e + opp_fast_energy,
                c_turn + opp_fast_turns,
                c_shields,
            ))

    return turns_to_live


def would_shield(attacker: "BattlePokemon", defender: "BattlePokemon", move: dict,
                 mechanics: str = 'legacy') -> bool:
    """
    Port of PvPoke's ActionLogic.wouldShield.

    ``mechanics`` is accepted for the new-turn-system scaffold but does NOT
    change behavior: wouldShield's projections are energy/damage-based, not
    turn-clock-based, so the +1 charged-resolution offset has no grounded
    effect here (see pvpoke_simulate_shield docstring). Plumbed for future
    re-tuning only.

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
    # Must happen BEFORE the charged-move loop below -- PvPoke evaluates
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
            if _shield_trace:
                cm_reasons.append(f"{cm.get('moveId')}({cm_dmg})≥hp/1.4({defender.hp/1.4:.0f})&dpt({fast_dpt:.1f})>1.5")
        if cm_dmg >= defender.hp - cycle_damage:
            use_shield = True
            if _shield_trace:
                cm_reasons.append(f"{cm.get('moveId')}({cm_dmg})≥hp-cycle({defender.hp}-{cycle_damage}={defender.hp-cycle_damage})")

    # "Shield the first in a series of Attack debuffing moves like
    # Superpower, if they would do major damage" -- ActionLogic.js:1186-1190,
    # the final override of wouldShield. Uses the incoming move's damage
    # (PvPoke's move.damage, freshly computed at the top of wouldShield).
    if move.get('selfAttackDebuffing', False) and damage / defender.hp > 0.55:
        use_shield = True
        if _shield_trace:
            cm_reasons.append(
                f"selfAtkDebuff dmg({damage})/hp({defender.hp})>0.55")

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
#   - the highest-damage move    (max_dmg_idx)  -- for the shields-down sort
#   - whether any move debuffs   (has_debuf)    -- gates that sort branch
#   - net debuff count           (debuf_count)  -- for _dp_insert_ready dedup
#
# Tracking these as scalars avoids a per-state `list + [n]` allocation in the
# inner loop and makes the state numba-friendly. With no moves: first_idx is
# -1 and the other scalars are 0.
class _DPState:
    __slots__ = ('energy', 'hp', 'turn', 'shields',
                 'first_idx', 'max_dmg_idx', 'has_debuf', 'debuf_count',
                 'atk_stage')
    def __init__(self, energy, hp, turn, shields,
                 first_idx, max_dmg_idx, has_debuf, debuf_count,
                 atk_stage=0):
        self.energy      = energy
        self.hp          = hp
        self.turn        = turn
        self.shields     = shields
        self.first_idx   = first_idx
        self.max_dmg_idx = max_dmg_idx
        self.has_debuf   = has_debuf
        self.debuf_count = debuf_count
        self.atk_stage   = atk_stage


def _optimize_move_timing(attacker: "BattlePokemon", defender: "BattlePokemon",
                          mechanics: str = 'legacy') -> bool:
    """
    Port of ActionLogic.js lines 237-344 (optimizeMoveTiming).

    ``mechanics`` is threaded as scaffold but currently produces NO behavior
    change: new == legacy here. A "turns_from_cm + 1" correction (opponent's
    charged resolves one turn later under new) was tried and REVERTED
    2026-06-24 -- like the TTL +1 it nudged optimizeMoveTiming toward DELAYING
    the charged, compounding the glass-cannon regression. The grounded new-clock
    decision changes are being rebuilt against a non-regression corpus; until a
    change clears that floor, new uses the legacy decision path verbatim.

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
        return False   # timing is already fine -- proceed with charged move

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
    if attacker.cmp_atk < defender.cmp_atk:
        turns_planned += 1
    ttl = _calc_turns_to_live(attacker, defender, mechanics=mechanics)
    if turns_planned > ttl:
        return False

    # Can KO opponent with a charged move (shields == 0 only) -- PvPoke
    # ActionLogic.js lines 317-329: if any AFFORDABLE charged move would KO
    # now, don't optimize (fire it, don't delay for timing).
    #
    # PvPoke itself does not gate this on "fast could also KO" -- the fast
    # move's next-fire turn is governed by cooldown, not available right now,
    # so the "fast would also KO" shortcut is not equivalent in time to the
    # charged KO. Dropping that gate 2026-04-15 after harness localization
    # showed Forr vs Azu (1,0) loses -15 because our Forr at T37 delays fast
    # (next VS lands at T40) instead of firing ST for the immediate KO.
    # The earlier "score identical either way" claim held only when fast
    # could fire immediately; with mid-cooldown timing, delay costs real
    # turns of incoming opponent damage.
    #
    # History: until 2026-06-11 this override ALSO excluded self-debuffing
    # moves ("leave the attacker un-debuffed for whatever comes next"),
    # reasoned to be score-neutral because the debuff fires after the KO.
    # The Snorlax-vs-Obstagoon localization falsified that: while OMT
    # delays the lethal self-debuffing throw, the opponent's fast moves
    # keep LANDING (one extra Counter = the whole -26..-29 margin cluster),
    # so the deviation traded real HP for avoiding a debuff with zero
    # post-KO effect. Removed -- matches PvPoke exactly.
    if defender.shields == 0:
        for cm in attacker.charged_moves:
            if attacker.energy >= cm['energy']:
                cm['_cached_damage'] = attacker.charged_move_damage(cm, defender)
                if cm['_cached_damage'] >= defender.hp:
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
    per cms-list in _ensure_dp_cache so the inner loop only carries an
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


def _cm_buff_delta(m: dict) -> int:
    """Per-cm atk-stage delta applied to the ATTACKER on throw.

    Mirrors PvPoke ActionLogic.js:519-536 exactly -- SIGNED on both axes:
    chance-1 self-target moves contribute ``attackMult += buffs[0]``
    (so Superpower/Draco Meteor plans have their later throws computed
    at REDUCED attack), and chance-1 opponent-target moves contribute
    ``attackMult -= buffs[1]`` (def-debuffs accelerate plans). Only
    chance-1 effects count -- PvPoke zeros changeTTKChance
    unconditionally before the DP. buffTarget 'both' (Obstruct) has no
    clause in PvPoke's DP, so it contributes nothing here either.

    (Until 2026-06-11 the self clause dropped negative deltas, so
    multi-nuke self-atk-debuff plans looked stronger to our DP than to
    PvPoke's -- review finding E4.)
    """
    buffs = m.get('buffs')
    if not buffs:
        return 0
    # buffApplyChance may be a string in raw gamemaster data.
    if float(m.get('buffApplyChance', 0) or 0) != 1.0:
        return 0
    bt = m.get('buffTarget', '')
    if bt == 'self':
        return buffs[0]
    if bt == 'opponent':
        return -buffs[1]
    return 0


def _priority_shuffle(cms: list, cm_dmgs: list, idx_map: dict) -> None:
    """PvPoke's activeChargedMoves priority-shuffle (Pokemon.js lines 711-787).

    Reorders the energy-sorted ``cms`` list in place based on buff/debuff
    properties. PvPoke runs this once at init; we re-run it whenever the
    cached damage values change (see _ensure_dp_cache). Uses buff-adjusted
    DPE for the selfBuffing-promotion clause (line 758). Verified
    2026-04-15 to affect 153/378 matchups in a 7x6x9 differential grid.

    ``cm_dmgs`` is indexed by original charged_moves position via
    ``idx_map`` (id(move) -> original index).
    """
    def _get_dmg(m):
        return cm_dmgs[idx_map[id(m)]]

    # Buff-adjusted DPE per PvPoke initializeMove (Pokemon.js:849-864).
    # Only self-atk-buff and opp-def-debuff get the multiplier.
    def _buff_adj_dpe(m):
        raw = _get_dmg(m) / m['energy']
        buffs = m.get('buffs')
        if not buffs:
            return raw
        bt = m.get('buffTarget', '')
        chance = float(m.get('buffApplyChance', 0) or 0)
        eff = 0.0
        if bt == 'self' and buffs[0] > 0:
            eff = buffs[0] * (80 / m['energy'])
        elif bt == 'opponent' and buffs[1] < 0:
            eff = abs(buffs[1]) * (80 / m['energy'])
        if eff > 0:
            return raw * (4 + eff * chance) / 4
        return raw

    # Line 715-722: same energy -- prefer buff or higher damage
    if (cms[1]['energy'] == cms[0]['energy']
            and not cms[1].get('selfDebuffing', False)):
        if cms[1].get('buffs') or _get_dmg(cms[1]) > _get_dmg(cms[0]):
            cms[0], cms[1] = cms[1], cms[0]

    # Line 726-730: same energy -- prefer higher buffApplyChance
    if (cms[1]['energy'] == cms[0]['energy']
            and cms[0].get('buffs') and cms[1].get('buffs')
            and not cms[1].get('selfDebuffing', False)
            and (cms[1].get('buffApplyChance', 0) or 0) > (cms[0].get('buffApplyChance', 0) or 0)):
        cms[0], cms[1] = cms[1], cms[0]

    # Line 734-744: Zap Cannon / Registeel clause
    if (cms[0].get('moveId') == 'FOCUS_BLAST'
            and cms[1].get('moveId') == 'ZAP_CANNON'):
        if _buff_adj_dpe(cms[1]) - _buff_adj_dpe(cms[0]) > -0.3:
            cms[0]['buffs'] = [0, 0]
            cms[0]['buffTarget'] = 'self'
            cms[0]['selfDebuffing'] = True
        else:
            cms[0].pop('buffs', None)
            cms[0].pop('buffTarget', None)
            cms[0].pop('selfDebuffing', None)

    # Line 756-762: similar energy -- promote selfBuffing move
    if (cms[1]['energy'] - cms[0]['energy'] <= 10
            and not cms[1].get('selfDebuffing', False)
            and cms[1].get('selfBuffing', False)
            and _buff_adj_dpe(cms[0]) - _buff_adj_dpe(cms[1]) < 0.3):
        cms[0], cms[1] = cms[1], cms[0]

    # Line 767-771: demote selfAttackDebuffing
    if (cms[1]['energy'] - cms[0]['energy'] <= 10
            and cms[0].get('selfAttackDebuffing', False)
            and not cms[1].get('selfDebuffing', False)):
        cms[0], cms[1] = cms[1], cms[0]

    # Line 775-779: demote expensive (>50 energy) selfDebuffing
    if (cms[1]['energy'] - cms[0]['energy'] <= 10
            and cms[0].get('selfDebuffing', False)
            and cms[0]['energy'] > 50
            and not cms[1].get('selfDebuffing', False)):
        cms[0], cms[1] = cms[1], cms[0]

    # Line 783-787: promote close-energy selfBuffing as bait
    if (cms[1]['energy'] - cms[0]['energy'] <= 5
            and cms[1].get('selfBuffing', False)):
        cms[0], cms[1] = cms[1], cms[0]


# ---------------------------------------------------------------------------
# DP queue insertion strategies (PvPoke ActionLogic.js lines 469-762)
#
# PvPoke uses three different insertion strategies with built-in pruning.
# However, the dominance checks (lines 600, 697) and the farm-down blocking
# check (line 479) reference ``.hp`` and ``.shields`` on BattleState objects.
# BattleState stores those values as ``.oppHealth`` and ``.oppShields``
# (lines 1190-1192), so ``.hp``/``.shields`` are ``undefined`` in JS.
# Since ``undefined < 0`` and ``undefined <= number`` are always ``false``
# in JavaScript, these pruning checks are dead code -- they never fire.
# We replicate PvPoke's *actual* JS behavior: no pruning. (An
# ``intended_pruning`` flag that enabled the apparently-intended checks
# existed until the 2026-06-12 S7 cleanup; it had zero consumers, and if
# ever enabled it would have pruned wrongly -- it compared only
# hp/energy/shields where PvPoke's check also compares buff state.)
# ---------------------------------------------------------------------------


def _dp_insert_farm_down(queue: list, ns: "_DPState") -> None:
    """Farm-down insertion (PvPoke lines 469-491).

    Insert AFTER same-turn states (``<=``).

    PvPoke line 479 checks ``DPQueue[i].hp < 0`` to block insertion, but
    ``.hp`` is undefined on BattleState (stored as ``.oppHealth``), so
    ``undefined < 0`` is always ``false`` and farm-down always inserts.
    """
    n = len(queue)
    ns_turn = ns.turn
    i = 0
    while i < n and queue[i].turn <= ns_turn:
        i += 1
    queue.insert(i, ns)


def _dp_insert_ready(queue: list, ns: "_DPState") -> None:
    """Ready-move insertion (PvPoke lines 541-616).

    Phase 1 -- dedup (lines 544-586): scan states at exactly
    ``turn == ns.turn``.  If an existing state has the same hp (and
    buffs, always 0), don't insert (different energy) or compare debuff
    counts (same energy).  This check uses ``.oppHealth`` (real field)
    and is always active.

    Phase 2 -- PvPoke's dominance check (lines 598-608) uses
    ``.hp``/``.shields`` (undefined), so it is dead code in PvPoke and
    not ported: we just find the insertion point.

    Insert AFTER same-turn states (``<=``).
    """
    # Phase 1: dedup (always active -- uses .oppHealth, a real field)
    i = 0
    insert_element = True
    n = len(queue)
    ns_turn = ns.turn
    ns_hp = ns.hp
    ns_energy = ns.energy
    ns_debuf = ns.debuf_count
    ns_atk_stage = ns.atk_stage
    while i < n and queue[i].turn == ns_turn:
        q = queue[i]
        # buffs check: require same atk_stage -- different stacks are genuinely
        # different states with different future damage trajectories.
        if q.hp == ns_hp and q.atk_stage == ns_atk_stage:
            if q.energy == ns_energy:
                # Same energy -- compare net debuff counts (precomputed
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

    # Phase 2: find the <= insertion point (PvPoke's dominance check
    # here is dead code in the JS -- not ported).
    i = 0
    while i < n and queue[i].turn <= ns_turn:
        i += 1
    queue.insert(i, ns)


def _dp_insert_not_ready(queue: list, ns: "_DPState") -> None:
    """Not-ready-move insertion (PvPoke lines 686-708).

    Insert BEFORE same-turn states (strict ``<``).  This gives
    charged-move KO paths priority over farm-down KOs at the same turn.

    PvPoke's dominance check (lines 696-704) uses ``.hp``/``.shields``
    (undefined on BattleState), so it is dead code in PvPoke and not
    ported.

    Verified: the ``<`` insertion order produces 2 exact PvPoke matches
    and 3 closer scores for Azu vs Forretress (Sand+Rock) compared to
    the old ``<=`` order.
    """
    n = len(queue)
    ns_turn = ns.turn
    i = 0
    while i < n and queue[i].turn < ns_turn:
        i += 1
    queue.insert(i, ns)


def pvpoke_dp(attacker: "BattlePokemon", defender: "BattlePokemon",
              *, bait_shields: bool = True, mechanics: str = 'legacy') -> "int | None":
    """
    PvPoke's DP charged-move AI (ActionLogic.js port, no-buff case).

    ``mechanics`` is threaded through turnsToLive, optimizeMoveTiming, and the
    shield heuristic as scaffold for the experimental new-turn-system decision
    layer, but currently produces NO behavior change: new == legacy decisions.
    The grounded new-clock decision changes are being rebuilt against a
    non-regression corpus (the first attempt -- TTL/OMT +1 -- regressed
    glass-cannon attackers and was reverted 2026-06-24). Legacy (default) is
    byte-identical regardless.

    Two phases mirroring PvPoke:

    Farm-down  (opponent HP > 2 × best-cycle damage):
        Select bestChargedMove (highest actual DPE).
        Bait with cheapest move only if the opponent would shield bestChargedMove.
        If current energy < selectedMove.energy → wait (return None).

    Near-KO    (opponent HP ≤ 2 × best-cycle damage):
        Run a forward DP over charge-move sequences to find the fastest KO.
        Fire the first move in the optimal plan; wait if not yet affordable.

    Queue insertion replicates PvPoke's actual JS behavior: the DP
    queue dominance checks (lines 600, 697) and farm-down blocking
    (line 479) reference ``.hp``/``.shields`` which are undefined on
    BattleState (stored as ``.oppHealth``/``.oppShields``), making
    them dead code, so no pruning is ported.  Not-ready states insert
    with ``<`` (before same-turn), ready states use dedup + ``<=``
    (after same-turn).

    bait_shields:
        True (default) -- PvPoke's simulate-mode default: the attacker
        may throw a cheap charged move first to burn an opponent shield,
        setting up a high-DPE follow-up.  Mirrors ``battle.baitShields=true``.

        False -- "never bait." The attacker never deliberately throws a
        sub-optimal move to draw a shield. Farm-down always selects
        ``bestChargedMove``; bait-wait is disabled; near-KO plans prefer
        the max-damage move as the first throw. Useful for "can I win
        this without needing the bait to be called?" analysis.
    """
    # Energy-sorted, priority-shuffled move order plus the per-move scalar
    # arrays, per-atk-stage damage tables, and the key-stable selections
    # (bestChargedMove, farm-down threshold/swap), cached per (opponent,
    # stat stages) -- see BattlePokemon._ensure_dp_cache.
    #
    # cm_dpe is PvPoke's move.dpe (Pokemon.js:792, 796, 845): after
    # selectBestChargedMove runs, move.dpe is overwritten to
    # `move.damage / move.energy` where move.damage is the actual
    # type-effectiveness-aware damage computed in initializeMove against
    # the CURRENT opponent. So it's "raw" in the sense of "not
    # buff-adjusted", but still type-effectiveness-aware.
    dp_cache  = attacker._ensure_dp_cache(defender)

    fast_turns       = dp_cache['fast_turns']
    fast_energy      = dp_cache['fast_energy']
    fast_damage      = dp_cache['fast_root']
    atk_fast_cd      = dp_cache['atk_fast_cd']
    opp_fast_cd      = defender.fast_move.get('cooldown', 500)
    opp_fast_damage  = defender.fast_move_damage(attacker)
    wins_cmp         = attacker.cmp_atk >= defender.cmp_atk

    # original-charged-moves index for each sorted entry -- used by callers
    # that need to return an index into attacker.charged_moves
    cm_orig_idx = dp_cache['order']
    cms     = dp_cache['cms']
    n_cms   = len(cms)
    cm_dmgs = dp_cache['cm_dmgs_root']
    cm_dpe         = dp_cache['cm_dpe']
    cm_energy      = dp_cache['cm_energy']
    cm_self_debuf  = dp_cache['cm_self_debuf']
    cm_self_buff   = dp_cache['cm_self_buff']
    cm_debuf_delta = dp_cache['cm_debuf_delta']
    cm_buff_delta  = dp_cache['cm_buff_delta']

    # ------------------------------------------------------------------ #
    # Break Mimikyu disguise ASAP (ActionLogic.js lines 236-251)
    # When facing a Pokemon with a protect effect and active disguise,
    # PvPoke throws ONLY poke.fastestChargedMove -- the pre-shuffle
    # cheapest-by-energy move (Pokemon.js:709: captured right after the
    # energy sort, BEFORE the priority shuffle; ties keep user order) --
    # and only when it is affordable and not selfDebuffing. When that
    # one move doesn't qualify there is NO early throw at all: fall
    # through to TTL / OMT / the DP. (We previously scanned every
    # shuffled slot for the first qualifying move -- review finding E6.)
    # ------------------------------------------------------------------ #
    if (defender._form_change is not None
            and defender._form_change.effect == 'protect'
            and defender._form_disguise_active
            and defender.shields == 0):
        _fastest_idx = min(range(len(attacker.charged_moves)),
                           key=lambda i: attacker.charged_moves[i]['energy'])
        _fastest_cm = attacker.charged_moves[_fastest_idx]
        if (attacker.energy >= _fastest_cm['energy']
                and not _fastest_cm.get('selfDebuffing', False)):
            if _policy_debug:
                _policy_log.append(
                    f"  DP[break_disguise]: {attacker.species} fires "
                    f"{_fastest_cm.get('moveId')} to break disguise")
            return _fastest_idx

    # ------------------------------------------------------------------ #
    # turnsToLive: fire highest-damage move now if about to be KO'd
    # Port of ActionLogic.js lines 38-207
    # ------------------------------------------------------------------ #
    turns_to_live = _calc_turns_to_live(attacker, defender, mechanics=mechanics)

    # Adjustments (ActionLogic.js lines 142-161) -- always applied
    if attacker.hp <= opp_fast_damage * 2 and opp_fast_cd == 500:
        turns_to_live -= 1

    if (attacker.hp <= opp_fast_damage
            and defender._queued_fast is not None
            and opp_fast_cd > 500):
        turns_to_live = defender.cooldown      # PvPoke: opponent.cooldown / 500
        if defender.hp > fast_damage:
            turns_to_live -= 1

    if (attacker.hp <= opp_fast_damage
            and defender._queued_fast is None
            and opp_fast_cd <= atk_fast_cd + 500):
        if defender.hp > fast_damage:
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
    # Slot eligibility is `n == 0 || (n == 1 && ! poke.baitShields)`
    # (ActionLogic.js:221): with baiting ON, slot 1 is NOT eligible for
    # the early lethal throw -- PvPoke falls through to OMT / the near-KO
    # DP instead. (A previous comment here asserted the inverse and the
    # loop checked both slots unconditionally -- review finding E5.)
    # ------------------------------------------------------------------ #
    if defender.shields == 0:
        _fast_dmg = fast_damage
        d_hp      = defender.hp
        _lethal_slots = 1 if bait_shields else min(2, n_cms)
        for _n in range(min(_lethal_slots, n_cms)):
            if attacker.energy >= cm_energy[_n]:
                if (cm_dmgs[_n] >= d_hp
                        and not cm_self_debuf[_n]
                        and d_hp > _fast_dmg):
                    if _policy_debug:
                        _policy_log.append(
                            f"  DP[lethal]: {attacker.species} fires "
                            f"{cms[_n].get('moveId')} (energy={attacker.energy})"
                        )
                    return cm_orig_idx[_n]

    # ------------------------------------------------------------------ #
    # optimizeMoveTiming (ActionLogic.js lines 237-344)
    # ------------------------------------------------------------------ #
    if _optimize_move_timing(attacker, defender, mechanics=mechanics):
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

    # PvPoke's bestChargedMove selection (Pokemon.js lines 791-822) and
    # the farm-down constants (bestCycleDamage, cycle threshold, debuf
    # swap) are precomputed in _ensure_dp_cache -- they depend only on
    # cache-key-stable inputs.
    #
    # INTENTIONAL DIVERGENCE (Divergence 3 in DEVELOPER_NOTES.md):
    # PvPoke computes bestChargedMove once at init (and on self form change).
    # We recompute per (opponent, stat stages) using current damage values,
    # which responds to stat stage changes and opponent form changes.  This
    # is more correct: PvPoke's stale cache uses Ice Beam against Aegislash
    # Blade form even when Play Rough has higher DPE after the form change.
    # Known impact: +134 delta on Aegislash 1v2/2v2 scenarios.
    best_idx       = dp_cache['best_idx']
    best_cycle_dmg = dp_cache['best_cycle_dmg']

    # ------------------------------------------------------------------ #
    # Farm-down path (PvPoke ActionLogic.js lines 365-415, "many-cycle"
    # simpler-move-selection branch).
    #
    # PvPoke's threshold is 2 cycles by default, dropped to 1.1 when the
    # bestChargedMove is self-debuffing AND a cheaper non-debuffing
    # alternative with comparable DPE exists.  When entering the path with
    # a self-debuffing bestChargedMove, PvPoke then swaps the selection to
    # the non-debuffing alt (lines 387-393, precomputed as farm_swap_idx)
    # so the first throw is the non-debuff move.  Without this, our code
    # falls through to near-KO DP, picks the debuffing move, and bandaid
    # [918] waits forever to stack -- the Moltres-G cluster root cause
    # (2026-04-15).
    # ------------------------------------------------------------------ #
    if defender.hp > dp_cache['min_cycle_thr'] * best_cycle_dmg:
        # Bait: if opponent would shield the expensive move, throw the cheap
        # one instead.  PvPoke checks activeChargedMoves[1] (the more expensive
        # move), not bestChargedMove (ActionLogic.js line 383).
        # Gated on bait_shields -- no-bait mode always keeps selected_idx=best_idx.
        # (The bait pick requires a non-debuffing cms[0], which the debuf
        # swap never rewrites -- so bait → 0, otherwise → farm_swap_idx.)
        if (bait_shields
                and defender.shields > 0 and n_cms > 1
                and not cm_self_debuf[0]
                and would_shield(attacker, defender, cms[1])):
            selected_idx = 0
        else:
            selected_idx = dp_cache['farm_swap_idx']

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

    # Per-atk-stage damage tables for the DP (cached -- see _ensure_dp_cache).
    # atk_stage runs over [-4, +4]; index as stage + 4 → [0..8].
    # Each entry recomputes damage from raw power/atk/def via calc_damage
    # (floor semantics) rather than multiplicatively scaling the root-stage
    # damage -- keeps KO thresholds exact at the 1-HP margin.
    root_atk_stage = attacker.atk_stage
    cm_dmgs_by_stage  = dp_cache['cm_dmgs_by_stage']
    fast_dmg_by_stage = dp_cache['fast_dmg_by_stage']

    _use_jit = _NEAR_KO_DP_JIT is not None
    if _use_jit:
        # Numba-JIT'd inner DP. Same algorithm as the Python loop below;
        # operates on numpy scalar arrays for ~5-10x inner-loop speedup.
        # The root-stage damage row of the stage table is computed by the
        # same calc_damage inputs as _cached_charged_dmgs, so it doubles
        # as the cm_dmgs argument (root-stage ordering tiebreak).
        cm_dmgs_stage_np = dp_cache['cm_dmgs_stage_np']
        (found, _first, _max_idx, _has_deb, _deb_cnt,
         _f_turn, _f_hp, _f_sh, iters) = _NEAR_KO_DP_JIT(
            cm_dmgs_stage_np[root_atk_stage + 4],
            dp_cache['cm_energy_np'], dp_cache['cm_self_db_np'],
            dp_cache['cm_db_dlt_np'],
            dp_cache['cm_buff_dlt_np'], cm_dmgs_stage_np,
            dp_cache['fast_dmg_stage_np'],
            int(root_atk_stage),
            n_cms,
            int(attacker.energy),
            float(defender.hp),
            int(defender.shields),
            int(fast_damage),
            int(fast_energy),
            int(fast_turns),
        )
        if iters < 0:
            # Queue overflow inside the kernel (iters = -1 sentinel):
            # non-dominated states were DROPPED, so the JIT result can't
            # be trusted -- re-run on the unbounded Python loop below.
            # Mirrors the TTL kernel's ok=False fallback (review finding
            # E9); never expected at QUEUE_CAP=1024 (~50 steady state),
            # this is the backstop that makes JIT/Python parity
            # structural rather than probabilistic.
            _use_jit = False
            found = False
            final_state = None
            iters = 0
        elif found:
            final_state = _DPState(0, _f_hp, _f_turn, _f_sh,
                                   _first, _max_idx, _has_deb, _deb_cnt)
        # else: final_state stays None → fall through to greedy fallback
    if not _use_jit:
        # Pure-Python fallback (numba unavailable, or the JIT signalled
        # queue overflow). Same algorithm as the JIT in _dp_jit.py --
        # kept here so the project still runs without numba installed.
        queue: list = [_DPState(attacker.energy, float(defender.hp), 0,
                                 defender.shields, -1, -1, 0, 0,
                                 root_atk_stage)]
        while queue and iters < 500:
            iters += 1
            curr = queue.pop(0)

            # KO achieved -- this is the fastest plan (chance == 1 path → break)
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
            curr_atk_stage = curr.atk_stage
            stage_row     = cm_dmgs_by_stage[curr_atk_stage + 4]
            curr_fast_dmg = fast_dmg_by_stage[curr_atk_stage + 4]
            for n in range(n_cms):
                move_dmg = stage_row[n]
                move_e   = cm_energy[n]

                # Update scalar plan summary for the new state.
                new_first = curr_first if curr_first >= 0 else n
                # max_dmg tracking uses root-stage damage for stable ordering
                if cm_dmgs[n] > curr_max_dmg:
                    new_max_idx = n
                else:
                    new_max_idx = curr_max_idx
                new_has_deb = curr_has_deb | cm_self_debuf[n]
                new_deb_cnt = curr_deb_cnt + cm_debuf_delta[n]
                new_atk_stage = curr_atk_stage + cm_buff_delta[n]
                if new_atk_stage > 4:
                    new_atk_stage = 4
                elif new_atk_stage < -4:
                    new_atk_stage = -4

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
                                 new_first, new_max_idx, new_has_deb, new_deb_cnt,
                                 new_atk_stage))
                else:
                    fm_needed    = math.ceil((move_e - curr_e) / fast_energy)
                    turns_needed = fm_needed * fast_turns
                    new_e  = fm_needed * fast_energy + curr_e - move_e
                    new_t  = curr_t + turns_needed + 1
                    new_sh = curr_sh
                    if curr_sh > 0:
                        new_hp = curr_hp - curr_fast_dmg * fm_needed - 1
                        new_sh -= 1
                    else:
                        new_hp = curr_hp - curr_fast_dmg * fm_needed - move_dmg

                    _dp_insert_not_ready(
                        queue,
                        _DPState(new_e, new_hp, new_t, new_sh,
                                 new_first, new_max_idx, new_has_deb, new_deb_cnt,
                                 new_atk_stage))

            if curr_fast_dmg > 0 and curr_hp > 0:
                fm_to_ko  = math.ceil(curr_hp / curr_fast_dmg)
                fd_turn   = curr_t + fm_to_ko * fast_turns
                fd_energy = curr_e + fast_energy * fm_to_ko
                _dp_insert_farm_down(
                    queue,
                    _DPState(fd_energy, 0.0, fd_turn, curr_sh,
                             curr_first, curr_max_idx, curr_has_deb, curr_deb_cnt,
                             curr_atk_stage))

    # ------------------------------------------------------------------ #
    # Select move from plan
    # ------------------------------------------------------------------ #
    if final_state is None:
        # No KO found -- fallback to best-DPE greedy
        affordable = [i for i in range(n_cms) if attacker.energy >= cm_energy[i]]
        if not affordable:
            return None
        best_sorted_idx = max(affordable, key=lambda i: cm_dpe[i])
        return cm_orig_idx[best_sorted_idx]

    if final_state.first_idx < 0:
        # Farm-down plan: the DP found a fast-move-only KO. PvPoke
        # (ActionLogic.js:813-823) does NOT just return here -- if the
        # attacker has a "boost move" (a chance-1 buff/debuff charged move
        # that isn't self-debuffing, per Pokemon.js:1789-1799 getBoostMove),
        # it force-pushes that move onto the plan so the debuff value lands
        # on the opponent even when the KO is already guaranteed by fast
        # moves. The subsequent bandaid chain can then swap in a
        # higher-DPE charged move of similar/lower energy.
        #
        # getBoostMove iterates `self.chargedMoves` (user order) and lets
        # each match overwrite the prior -- i.e., the LAST matching move
        # wins. Mirrored here.
        boost_move = None
        for m in attacker.charged_moves:
            if (m.get('buffs')
                    and float(m.get('buffApplyChance', 0) or 0) >= 0.5
                    and not m.get('selfDebuffing', False)):
                boost_move = m
        if boost_move is None:
            if _dp_trace:
                _policy_log.append(
                    f"  DP-trace[{attacker.species}]: farm-down plan (no charged moves)")
            return None
        boost_sorted_idx = next(
            s for s, om in enumerate(cms) if om is boost_move)
        if _dp_trace:
            _policy_log.append(
                f"  DP-trace[{attacker.species}]: farm-down → boost-move override:"
                f" {boost_move.get('moveId')} (sorted_idx={boost_sorted_idx})")
        final_state = _DPState(
            final_state.energy, final_state.hp, final_state.turn,
            final_state.shields,
            boost_sorted_idx, boost_sorted_idx,
            final_state.has_debuf, final_state.debuf_count,
            final_state.atk_stage)

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

    # Bait-wait check (ActionLogic.js lines 839-853):
    # If shields are up and we can't yet afford cms[1] but it has better DPE
    # than our planned first move → wait for cms[1] instead.
    # PvPoke uses raw dpe (damage/energy) here.
    # Skipped entirely when bait_shields=False (never delay a ready shot to
    # set up a bait).
    #
    # NOTE: until 2026-06-11 this also required `not cm_self_debuf[1]` -- a
    # condition the reference does NOT have, so the hold never fired when
    # the pricier move was Superpower/Brave-Bird-class. That silently
    # produced the Snorlax [1,2] and MG-vs-Florges [1,2] divergences
    # (cheap bait thrown immediately where PvPoke holds, then fires the
    # big move under TTL pressure -- our fire_now path supplies the same
    # escape). PvPoke's only self-debuff consideration here is cm0's
    # selfBuffing exemption below.
    if bait_shields and defender.shields > 0 and n_cms > 1:
        if (attacker.energy < cm_energy[1]
                and cm_dpe[1] > cm_dpe[final_first_thrown]):
            bait = True
            # Don't bait if an effective self-buffing move exists (line 826).
            # PvPoke also uses raw damage/energy here (selectBestChargedMove
            # overwrites initializeMove's buff-adjusted dpe).
            if (cm_dpe[1] / max(cm_dpe[0], 0.001) <= 1.5
                    and cm_self_buff[0]):
                bait = False
            if bait:
                if _dp_trace:
                    _policy_log.append(
                        f"  DP-trace[{attacker.species}]: bait-wait for {cms[1].get('moveId')}")
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
    # moves[0] = 1 -- only takes effect when shields > 0 (so the sort branch
    # above does NOT fire), so we override `first_idx` directly here.
    # Skipped in no-bait mode: the plan-sort branch above already forced
    # max_dmg_idx, and no-bait never rewrites the first throw for bait reasons.
    if bait_shields and defender.shields > 0 and n_cms > 1:
        fm0_dpe = cm_dpe[final_first_thrown]
        if fm0_dpe > 0 and attacker.energy >= cm_energy[1]:
            dpe_ratio = cm_dpe[1] / fm0_dpe
            if dpe_ratio > 1.5 and not would_shield(attacker, defender, cms[1],
                                                     mechanics=mechanics):
                first_idx = 1

    first_move = cms[first_idx]

    # --- Post-DP bandaids (ActionLogic.js lines 861-935) ---

    # [861] Prefer low energy with better DPE when shields up (raw dpe)
    if (defender.shields > 0 and n_cms > 1
            and attacker.energy >= cm_energy[0]
            and cm_energy[0] <= cm_energy[first_idx]
            and cm_dpe[0] > cm_dpe[first_idx]
            and not cm_self_debuf[0]):
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
            and cm_self_debuf[first_idx]
            and cm_energy[first_idx] > 50
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
    if (n_cms > 1
            and cm_energy[0] == cm_energy[first_idx]
            and cm_dpe[0] > cm_dpe[first_idx]
            and not cm_self_debuf[0]):
        if _dp_trace:
            _policy_log.append(
                f"  DP-trace[{attacker.species}]: bandaid[871] same-energy-better-dpe:"
                f" {first_move.get('moveId')} → {cms[0].get('moveId')}")
        first_idx  = 0
        first_move = cms[first_idx]

    # [876] Force more efficient similar-energy move if chosen is self-debuffing (raw dpe)
    if (n_cms > 1
            and cm_energy[0] - 10 <= cm_energy[first_idx]
            and cm_dpe[0] > cm_dpe[first_idx]
            and cm_self_debuf[first_idx]
            and not cm_self_debuf[0]):
        if _dp_trace:
            _policy_log.append(
                f"  DP-trace[{attacker.species}]: bandaid[876] avoid-debuff-similar-energy:"
                f" {first_move.get('moveId')} → {cms[0].get('moveId')}")
        first_idx  = 0
        first_move = cms[first_idx]

    # [881] Force more efficient similar-energy move if one is self-buffing (raw dpe)
    if (n_cms > 1
            and cm_energy[0] - cm_energy[first_idx] <= 5
            and cm_dpe[0] > cm_dpe[first_idx]
            and cm_self_buff[0]):
        if _dp_trace:
            _policy_log.append(
                f"  DP-trace[{attacker.species}]: bandaid[881] prefer-self-buff:"
                f" {first_move.get('moveId')} → {cms[0].get('moveId')}")
        first_idx  = 0
        first_move = cms[first_idx]

    # [886] Don't bait with self-debuffing moves (raw dpe)
    # Gated on bait_shields -- the whole bandaid is about rerouting a bait
    # choice, which is a no-op in no-bait mode.
    if bait_shields and defender.shields > 0 and n_cms > 1:
        if (attacker.energy >= cm_energy[1]
                and cm_dpe[1] > cm_dpe[first_idx]
                and cm_self_debuf[first_idx]
                and not cm_self_debuf[1]):
            if _dp_trace:
                _policy_log.append(
                    f"  DP-trace[{attacker.species}]: bandaid[886] no-debuff-bait:"
                    f" {first_move.get('moveId')} → {cms[1].get('moveId')}")
            first_idx  = 1
            first_move = cms[first_idx]

    # [895] While shields up, prefer close non-debuffing when debuffing won't KO
    if defender.shields > 0 and n_cms > 1:
        if cm_self_debuf[0] and not cm_self_buff[1]:
            # Is attacker baiting or will debuffing move not come close to KO?
            if (bait_shields
                    or defender.hp - cm_dmgs[0] > 10):
                # Is the second move close in energy and DPE? (raw dpe)
                if (cm_energy[1] - cm_energy[0] <= 10
                        and cm_dpe[1] / cm_dpe[0] > 0.7):
                    if _dp_trace:
                        _policy_log.append(
                            f"  DP-trace[{attacker.species}]: bandaid[895] shields-up-prefer-non-debuff:"
                            f" {first_move.get('moveId')} → {cms[1].get('moveId')}")
                    first_idx  = 1
                    first_move = cms[1]

    # [910] Defer self-debuffing until after survivable charged moves
    if (cm_self_debuf[first_idx]
            and attacker.shields == 0
            and attacker.energy < 100
            and defender.charged_moves):
        opp_best = max(defender.charged_moves,
                       key=lambda m: defender.charged_move_damage(m, attacker))
        if (defender.energy >= opp_best['energy']
                and not would_shield(defender, attacker, opp_best)
                and not cm_self_buff[first_idx]):
            if _dp_trace:
                _policy_log.append(
                    f"  DP-trace[{attacker.species}]: bandaid[910] defer-self-debuff:"
                    f" waiting for opponent to fire {opp_best.get('moveId')}")
            return None

    # [918] If self-debuffing move doesn't KO, stack as many as possible
    if cm_self_debuf[first_idx]:
        target_energy = (100 // cm_energy[first_idx]) * cm_energy[first_idx]
        if attacker.energy < target_energy:
            if ((defender.hp > cm_dmgs[first_idx] or defender.shields != 0)
                    and (attacker.hp > opp_fast_damage * 2
                         or opp_fast_cd - atk_fast_cd > 500)):
                if _dp_trace:
                    _policy_log.append(
                        f"  DP-trace[{attacker.species}]: bandaid[918] stack-self-debuff:"
                        f" energy={attacker.energy}/{target_energy}, waiting")
                return None
        elif defender.shields > 0 and n_cms > 1:
            # At target energy and shields up: use cheaper non-debuff if self-buffing
            # or if opponent would shield (line 929-933)
            if (cm_energy[0] - cm_energy[first_idx] <= 10
                    and not cm_self_debuf[0]):
                if (cm_self_buff[0]
                        or would_shield(attacker, defender, first_move)):
                    if _dp_trace:
                        _policy_log.append(
                            f"  DP-trace[{attacker.species}]: bandaid[929] stack-switch:"
                            f" {first_move.get('moveId')} → {cms[0].get('moveId')}")
                    first_idx  = 0
                    first_move = cms[first_idx]

    # final_state summarizes the DP-selected plan as scalars
    # (first_idx + max_dmg_idx); there is no list-of-moves "plan" here.
    if attacker.energy < cm_energy[first_idx]:
        if _policy_debug:
            _policy_log.append(
                f"  DP[near-ko]: {attacker.species} waits for "
                f"{first_move.get('moveId')} (energy={attacker.energy}/"
                f"{cm_energy[first_idx]},"
                f" plan_first={cms[final_state.first_idx].get('moveId')}"
                f" max_dmg={cms[final_state.max_dmg_idx].get('moveId')})"
            )
        return None   # wait until affordable
    if _policy_debug:
        _policy_log.append(
            f"  DP[near-ko]: {attacker.species} fires "
            f"{first_move.get('moveId')} (energy={attacker.energy}, "
            f"plan_first={cms[final_state.first_idx].get('moveId')}"
            f" max_dmg={cms[final_state.max_dmg_idx].get('moveId')})"
        )
    return cm_orig_idx[first_idx]


def optimal_timing(attacker: "BattlePokemon", defender: "BattlePokemon",
                   mechanics: str = 'legacy') -> "int | None":
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
    # Not yet at the optimal window -- but don't hold energy above the cap;
    # fire anyway if we can't afford to wait.
    if attacker.energy >= ENERGY_CAP:
        return pvpoke_ai(attacker, defender)
    return None


# ---------------------------------------------------------------------------
# BattlePokemon -- mutable battle state
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class BattlePokemon:
    """Wraps a Pokemon with the mutable state needed during a battle.

    OWNERSHIP INVARIANT: ``fast_move`` and ``charged_moves`` must be
    PRIVATE copies (``dict(move)``), never the shared dicts from
    ``get_moves()``. Battle code writes into them ('_turns',
    '_cached_damage', the Zap-Cannon clause's buff keys), so two
    BattlePokemon sharing a move dict silently cross-contaminate -- worst
    in mirrors, where one side's cached damage is computed with the other
    side's attack. Every current caller copies; this note exists so the
    next one does too. (Moves are resolved by identity in
    ``charged_move_damage``, so copies must happen at construction --
    passing a fresh copy of an attached move later raises KeyError by
    design.)
    """
    species:         str
    types:           list[str]   # 1 or 2 type strings
    atk:             float       # effective attack = (base_atk + atk_iv) * cpm
    def_:            float       # effective defense
    max_hp:          int
    fast_move:       dict        # gamemaster move dict -- private copy (see docstring)
    charged_moves:   list[dict]  # gamemaster move dicts -- private copies
    shields:         int = 2
    initial_energy:  int = 0     # energy at battle start (0–100)
    shadow:          bool = False    # CMP uses the unboosted attack (see cmp_atk)
    # Stat stages present at battle START (native form buffs, e.g. Mimikyu
    # (Busted)'s permanent -1 def). 0/0 for everything else. Persisted as
    # init fields so reset_for_battle can restore them across the
    # shield-scenario axis (which otherwise re-zeros the live stages).
    initial_atk_stage: int = 0
    initial_def_stage: int = 0

    # Mutable battle state
    hp:                 int   = field(init=False)
    energy:             int   = field(init=False)
    cooldown:           int   = field(init=False)   # turns remaining
    _fm_since_charge:   int   = field(init=False, repr=False)  # fast moves since last charge (either player)
    # Queued fast move: (queued_on_turn, move_dict) or None
    _queued_fast:    "tuple[int, dict] | None" = field(init=False, repr=False)
    # Deferred charged move for mechanics='new' (2026-06-23 turn system):
    # a charged move chosen this turn resolves at the START of the next
    # turn. Holds the move dict (or None). NEVER set in legacy mode.
    _pending_charged: "dict | None" = field(init=False, repr=False)
    # Stat stages: each in [-4, +4]
    atk_stage: int = field(init=False, repr=False)
    def_stage: int = field(init=False, repr=False)
    # Buff apply meters for deterministic probabilistic buffs: {moveId: count}
    _buff_apply_meters: dict = field(init=False, repr=False)

    # Damage cache (vs current opponent at current stat stages).
    # Within one simulate() call, charged_move_damage(move, defender) is fully
    # determined by (self.atk * stage_mult, defender.def_ * stage_mult, move,
    # types). The pvpoke_dp policy can call this hundreds of times per
    # simulate() with the same inputs -- we memoize the full per-move table
    # and invalidate via key comparison.
    # Held REFERENCE, compared with `is`: an id() key can alias when
    # CPython reuses a freed object's address; a held reference keeps
    # the opponent alive so it cannot. (2026-06-11 review finding E8.)
    _dmg_cache_opp: "BattlePokemon | None" = field(init=False, repr=False)
    _dmg_cache_atk_stage: int       = field(init=False, repr=False)
    _dmg_cache_def_stage: int       = field(init=False, repr=False)
    _cached_fast_dmg:     int       = field(init=False, repr=False)
    _cached_charged_dmgs: list      = field(init=False, repr=False)
    _cm_id_to_idx:        dict      = field(init=False, repr=False)
    # int64 numpy views of the charged-move damages/energies (natural
    # order), consumed by the turnsToLive JIT. Rebuilt with the damage
    # cache so per-call np.asarray conversion is never needed (the
    # 2026-04-07 round-3 false-start lesson). None when numba is absent.
    _cached_charged_dmgs_np: "object" = field(init=False, repr=False)
    _cm_energy_np:           "object" = field(init=False, repr=False)

    # pvpoke_dp setup cache (vs current opponent at current stat stages).
    # Holds the priority-shuffled move order, per-move scalar arrays, the
    # per-atk-stage damage tables for the near-KO DP, and (when numba is
    # available) the numpy buffers passed to the JIT. Rebuilt by key
    # comparison like the damage cache above; without it, pvpoke_dp
    # re-sorted the moves and recomputed 9 stage rows of calc_damage on
    # every call (~27 damage computations x ~32 calls per sim), which was
    # the dominant cost of the 2026-04-15 stage-aware DP fix.
    _dp_cache: "dict | None" = field(init=False, repr=False)

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
        self._pending_charged  = None
        self.atk_stage         = self.initial_atk_stage
        self.def_stage         = self.initial_def_stage
        self._buff_apply_meters = {}
        # Damage cache starts invalid (opp id -1 never matches any real id).
        self._dmg_cache_opp       = None
        self._dmg_cache_atk_stage = 0
        self._dmg_cache_def_stage = 0
        self._cached_fast_dmg     = 0
        self._cached_charged_dmgs = []
        self._cached_charged_dmgs_np = None
        self._cm_energy_np           = None
        # Identity-keyed lookup so charged_move_damage(move, ...) can find
        # its precomputed entry even when the policy passes a sorted copy
        # of self.charged_moves (same dict objects, different order).
        self._cm_id_to_idx = {id(cm): i for i, cm in enumerate(self.charged_moves)}
        self._dp_cache = None
        # Form change state
        self._form_change = None
        self._form_is_alt = False
        self._form_disguise_active = False

    @property
    def cmp_atk(self) -> float:
        """Attack used for CMP / charge-move priority. Shadow's x1.2
        boosts damage but NOT priority (live-game behavior; PvPoke
        compares shadow-free stats.atk), so strip it here"""
        return self.atk / 1.2 if self.shadow else self.atk

    @classmethod
    def from_pokemon(cls, pokemon, fast_move: dict, charged_moves: list[dict],
                     shields: int = 2, initial_energy: int = 0,
                     league_cp: int | None = None) -> "BattlePokemon":
        """Build a BattlePokemon from a Pokemon dataclass + move dicts."""
        from .data import load_gamemaster
        from .formchange import attach_form_change
        gm  = load_gamemaster()
        mon = next(m for m in gm['pokemon'] if m['speciesName'] == pokemon.species)
        types = parse_types(mon)
        bp = cls(
            species        = pokemon.species,
            types          = types,
            atk            = pokemon.atk,
            shadow         = pokemon.shadow,
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
        attach_form_change(
            bp, mon, pokemon.atk_iv, pokemon.def_iv, pokemon.sta_iv,
            pokemon.level, league_cp, pokemon.shadow,
        )
        return bp

    def reset_for_battle(self, shields: int,
                         opponent: "BattlePokemon | None" = None) -> None:
        """Reset mutable battle state so this object can be reused for
        another simulate() call, keeping the damage and DP setup caches
        warm (their keys cover opponent identity and stat stages, so
        entries stay valid as long as base stats and moves are unchanged).

        Used by the sweep/slayer workers to share one BattlePokemon pair
        across the shield-scenario axis instead of reconstructing (and
        re-deriving every damage table) once per scenario.

        For form-changing Pokemon the base form is restored first, which
        changes this object's stats/moves -- that staleness reaches the
        OPPONENT's caches too, so `opponent` is required in that case
        (mirrors apply_form_change's both-sides invalidation).
        """
        if self._form_change is not None:
            if self._form_is_alt:
                if opponent is None:
                    raise ValueError(
                        "reset_for_battle on a form-changed Pokemon needs "
                        "the opponent for cache invalidation")
                from .formchange import apply_form_change
                apply_form_change(self, opponent)   # swap back to base form
            self._form_disguise_active = (self._form_change.effect == 'protect')
            # The alt form's move dicts may also carry the per-battle
            # damage memo cleared below -- clear both forms' lists.
            for form in self._form_change.forms:
                for cm in form.charged_moves:
                    cm.pop('_cached_damage', None)
        # Per-battle damage memo on the move dicts (set by
        # _optimize_move_timing, read by the bandaid[866] gate) -- must not
        # leak into the next battle.
        for cm in self.charged_moves:
            cm.pop('_cached_damage', None)
        self.hp = self.max_hp
        self.energy = min(ENERGY_CAP, max(0, self.initial_energy))
        self.shields = shields
        self.cooldown = 0
        self._fm_since_charge = 0
        self._queued_fast = None
        self._pending_charged = None
        self.atk_stage = self.initial_atk_stage
        self.def_stage = self.initial_def_stage
        self._buff_apply_meters = {}

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
        if (self._dmg_cache_opp is defender
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
        if _CALC_TTL_JIT is not None:
            # Prebuilt buffers for the turnsToLive JIT. Energies are
            # re-derived here (not __post_init__) so form changes -- which
            # swap the move dicts and invalidate this cache -- are covered.
            self._cached_charged_dmgs_np = _np.asarray(
                self._cached_charged_dmgs, dtype=_np.int64)
            self._cm_energy_np = _np.asarray(
                [cm['energy'] for cm in self.charged_moves], dtype=_np.int64)
        self._dmg_cache_opp       = defender
        self._dmg_cache_atk_stage = self.atk_stage
        self._dmg_cache_def_stage = defender.def_stage

    def _ensure_dp_cache(self, defender: "BattlePokemon") -> dict:
        """Return the pvpoke_dp setup cache vs `defender` at the current
        stat stages, rebuilding it if the key no longer matches.

        Contents (all in priority-shuffled order, cheapest-energy-first
        before the shuffle):
          order              original charged_moves index per sorted slot
          cms                the sorted/shuffled move-dict list itself
          cm_dmgs_root       charged damage per slot at the current stages
          cm_dpe             PvPoke move.dpe per slot (damage / energy)
          cm_energy          energy cost per slot
          cm_self_debuf      1/0 selfDebuffing flag per slot
          cm_self_buff       1/0 selfBuffing flag per slot
          cm_debuf_delta     dedup tie-break delta per slot
          cm_buff_delta      chance-1 attacker atk-stage delta per slot
          cm_dmgs_by_stage   9 rows (atk stage -4..+4) of charged damage
          fast_dmg_by_stage  9 entries of fast-move damage
          fast_root          fast-move damage at the current stages
          fast_turns / fast_energy / atk_fast_cd
                             own fast-move scalars (saves dict.get churn)
          best_idx           PvPoke bestChargedMove selection
          best_cycle_dmg / min_cycle_thr / farm_swap_idx
                             farm-down path constants (ActionLogic 365-415)
          *_np               numpy views for the JIT
                             (present only when numba is available)

        Same staleness caveats as the damage cache: keyed on the held
        defender reference plus both stat stages, explicitly invalidated
        on form change.
        """
        dp = self._dp_cache
        if (dp is not None
                and dp['opp'] is defender
                and dp['atk_stage'] == self.atk_stage
                and dp['def_stage'] == defender.def_stage):
            return dp
        self._ensure_dmg_cache(defender)
        idx_map = self._cm_id_to_idx
        cm_dmgs_root = self._cached_charged_dmgs

        # PvPoke's activeChargedMoves is sorted by energy (cheapest first),
        # then reordered by the priority-shuffle (Pokemon.js lines 711-787).
        cms = sorted(self.charged_moves, key=lambda m: m['energy'])
        if len(cms) > 1:
            _priority_shuffle(cms, cm_dmgs_root, idx_map)

        # Per-atk-stage damage tables for the near-KO DP.
        # atk_stage runs over [-4, +4]; index as stage + 4 → [0..8].
        # Each entry recomputes damage from raw power/atk/def via
        # calc_damage (floor semantics) rather than multiplicatively
        # scaling the root-stage damage -- keeps KO thresholds exact at
        # the 1-HP margin.
        #
        # The row at the CURRENT atk stage is identical to the damage
        # cache populated above (same calc_damage inputs), so it is
        # reused rather than recomputed. And when no charged move
        # carries a chance-1 atk-stage delta (cm_buff_delta all zero --
        # the common case), the DP's plan exploration can never leave
        # the current stage: the cache key pins this entry to one
        # atk_stage, and only buff deltas move the stage row index
        # mid-plan. The other 8 rows are then unreachable, so they are
        # filled with references to the root row instead of
        # 8 x (n_cms + 1) calc_damage calls -- this rebuild was ~97% of
        # all damage computations in the 2026-06-10 profile.
        cm_buff_delta = [_cm_buff_delta(m) for m in cms]
        root_row  = [cm_dmgs_root[idx_map[id(m)]] for m in cms]
        fast_root = self._cached_fast_dmg
        root_off  = self.atk_stage + 4
        if not any(cm_buff_delta):
            cm_dmgs_by_stage  = [root_row] * 9
            fast_dmg_by_stage = [fast_root] * 9
        else:
            # Some moves move the plan's atk stage. Stages strictly above
            # root are reachable only via a positive delta, below root
            # only via a negative one -- fill unreachable rows with the
            # root row (never indexed) and compute the rest.
            has_pos = any(d > 0 for d in cm_buff_delta)
            has_neg = any(d < 0 for d in cm_buff_delta)
            def_eff_val = defender.def_ * _stat_stage_mult(defender.def_stage)
            atk_base = self.atk
            atk_types = self.types
            def_types = defender.types
            fm_power = self.fast_move['power']
            fm_type  = self.fast_move['type']
            cm_dmgs_by_stage = []
            fast_dmg_by_stage = []
            for _s_off in range(9):         # stage -4 .. +4
                if (_s_off == root_off
                        or (_s_off > root_off and not has_pos)
                        or (_s_off < root_off and not has_neg)):
                    cm_dmgs_by_stage.append(root_row)
                    fast_dmg_by_stage.append(fast_root)
                    continue
                _s = _s_off - 4
                _atk_eff = atk_base * _stat_stage_mult(_s)
                cm_dmgs_by_stage.append([
                    calc_damage(cm['power'], _atk_eff, def_eff_val,
                                cm['type'], atk_types, def_types)
                    for cm in cms
                ])
                fast_dmg_by_stage.append(
                    calc_damage(fm_power, _atk_eff, def_eff_val,
                                fm_type, atk_types, def_types)
                )

        # Per-slot scalar arrays + the pvpoke_dp selections that are fully
        # determined by them. Everything below depends only on cache-key-
        # stable inputs (root damages, energies, static move flags), so
        # precomputing here moves work from every pvpoke_dp call (~6 per
        # decision turn) to the rebuild (~6 per sim).
        cm_energy_l   = [m['energy'] for m in cms]
        cm_self_debuf = [1 if m.get('selfDebuffing', False) else 0
                         for m in cms]
        cm_self_buff  = [1 if m.get('selfBuffing', False) else 0
                         for m in cms]
        n = len(cms)
        cm_dpe = [root_row[i] / cm_energy_l[i] for i in range(n)]

        if cms:
            # PvPoke's bestChargedMove selection (Pokemon.js lines
            # 791-822) -- verbatim move of the per-call loop that lived in
            # pvpoke_dp; see the INTENTIONAL DIVERGENCE note there for
            # why this recomputes per (opponent, stages) at all.
            best_idx = 0
            for _i in range(n):
                _m = cms[_i]
                _dpe_diff = cm_dpe[_i] - cm_dpe[best_idx]
                if ((_dpe_diff > 0.03 and _m.get('moveId') != 'SUPER_POWER')
                        or _dpe_diff > 0.3):
                    if (not cms[best_idx].get('selfBuffing', False)
                            or _dpe_diff > 0.3):
                        best_idx = _i
                if (abs(cm_dpe[_i] - cm_dpe[best_idx]) < 0.03
                        and cms[best_idx].get('buffs')
                        and _m.get('buffs')
                        and _m.get('buffApplyChance', 0) > cms[best_idx].get('buffApplyChance', 0)
                        and not _m.get('selfDebuffing', False)):
                    best_idx = _i
                if _m.get('moveId') == 'OBSTRUCT':
                    best_idx = _i
            if (cms[0].get('moveId') == 'OBSTRUCT'
                    and cm_energy_l[0] - cm_energy_l[best_idx] <= 5
                    and cm_dpe[best_idx] > 0
                    and cm_dpe[0] / cm_dpe[best_idx] > 0.2):
                best_idx = 0

            # bestCycleDamage + the farm-down threshold/swap selections
            # (ActionLogic.js lines 365-415) -- also key-stable.
            fast_energy = self.fast_move.get('energyGain', 5)
            fm_to_charge = math.ceil(cm_energy_l[best_idx] / fast_energy)
            best_cycle_dmg = fast_root * fm_to_charge + root_row[best_idx]

            min_cycle_thr = 2.0
            if (n > 1
                    and cm_self_debuf[best_idx]
                    and cm_energy_l[best_idx] > cm_energy_l[0]
                    and cm_dpe[0] > 0
                    and cm_dpe[best_idx] / cm_dpe[0] < 2.0):
                min_cycle_thr = 1.1

            # Swap selfDebuffing best to a non-debuffing alt whose DPE is
            # within 2x (PvPoke lines 387-393). Last qualifying alt wins;
            # the ratio is re-evaluated against the updated selection,
            # mirroring PvPoke's loop.
            farm_swap_idx = best_idx
            if cm_self_debuf[farm_swap_idx]:
                for _i in range(n):
                    if (not cm_self_debuf[_i]
                            and cm_dpe[_i] > 0
                            and cm_dpe[farm_swap_idx] / cm_dpe[_i] < 2.0):
                        farm_swap_idx = _i
        else:                            # no charged moves (unsupported,
            best_idx = 0                 # but don't crash at build time)
            best_cycle_dmg = 0
            min_cycle_thr = 2.0
            farm_swap_idx = 0

        dp = {
            'opp':       defender,
            'atk_stage': self.atk_stage,
            'def_stage': defender.def_stage,
            'order':          [idx_map[id(m)] for m in cms],
            'cms':            cms,
            'cm_dmgs_root':   root_row,
            'cm_dpe':         cm_dpe,
            'cm_energy':      cm_energy_l,
            'cm_self_debuf':  cm_self_debuf,
            'cm_self_buff':   cm_self_buff,
            'cm_debuf_delta': [_cm_debuf_delta(m) for m in cms],
            'cm_buff_delta':  cm_buff_delta,
            'cm_dmgs_by_stage':  cm_dmgs_by_stage,
            'fast_dmg_by_stage': fast_dmg_by_stage,
            'fast_root':      fast_root,
            'fast_turns':     self.fast_move.get('_turns', 1),
            'fast_energy':    self.fast_move.get('energyGain', 5),
            'atk_fast_cd':    self.fast_move.get('cooldown', 500),
            'best_idx':       best_idx,
            'best_cycle_dmg': best_cycle_dmg,
            'min_cycle_thr':  min_cycle_thr,
            'farm_swap_idx':  farm_swap_idx,
        }
        if _NEAR_KO_DP_JIT is not None:
            dp['cm_energy_np']      = _np.asarray(dp['cm_energy'], dtype=_np.int64)
            dp['cm_self_db_np']     = _np.asarray(dp['cm_self_debuf'], dtype=_np.int8)
            dp['cm_db_dlt_np']      = _np.asarray(dp['cm_debuf_delta'], dtype=_np.int8)
            dp['cm_buff_dlt_np']    = _np.asarray(dp['cm_buff_delta'], dtype=_np.int8)
            dp['cm_dmgs_stage_np']  = _np.asarray(cm_dmgs_by_stage, dtype=_np.float64)
            dp['fast_dmg_stage_np'] = _np.asarray(fast_dmg_by_stage, dtype=_np.int64)
        self._dp_cache = dp
        return dp

    def fast_move_damage(self, defender: "BattlePokemon") -> int:
        if (self._dmg_cache_opp is not defender
                or self._dmg_cache_atk_stage != self.atk_stage
                or self._dmg_cache_def_stage != defender.def_stage):
            self._ensure_dmg_cache(defender)
        return self._cached_fast_dmg

    def charged_move_damage(self, move: dict, defender: "BattlePokemon") -> int:
        if (self._dmg_cache_opp is not defender
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
        # Match PvPoke's Math.floor formula exactly. (Both sims clamp HP at
        # 0 in the battle loop -- Battle.js:1349 and our simulate() -- so the
        # max(0, ...) below is defensive; an earlier comment claiming
        # "overkill counts" was wrong.)
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
    PvPoke, meaning no suppression).

    Chance buffs (buffApplyChance < 1) use PvPoke's deterministic meter,
    ported exactly (Battle.js:1389-1397 + Pokemon.js:686-706): a float
    accumulator INITIALIZED TO THE CHANCE ITSELF (0.0 for exactly-50%
    moves), incremented by the chance per activation, firing whenever it
    crosses a whole number -- and never reset. Python and JS share IEEE-754
    doubles, so the proc schedule matches PvPoke bit-exactly, float drift
    included (chance 0.1 procs on use 10, not 9, because ten accumulated
    0.1s are still < 1.0). The chance-shifted init makes the early procs
    land where intuition expects (0.3 → use 3) but the schedule is NOT
    periodic: 0.3 procs at uses 3, 6, 10, 13...; 0.2 at 4, 10, 14...
    """
    buffs = move.get('buffs')
    if not buffs:
        return
    chance_str = move.get('buffApplyChance', '0')
    chance     = float(chance_str) if chance_str else 0.0
    if chance <= 0:
        return

    if chance >= 1:
        fire = True   # guaranteed buffs always apply (Battle.js buffRoll += 1)
    else:
        move_id = move.get('moveId', '')
        meter = attacker._buff_apply_meters.get(move_id)
        if meter is None:
            meter = 0.0 if chance == 0.5 else chance   # Pokemon.js:696-700
        start = math.floor(meter)
        meter += chance
        attacker._buff_apply_meters[move_id] = meter
        fire = math.floor(meter) > start

    if fire:
        target = move.get('buffTarget', 'opponent')
        # buffTarget 'both' carries separate per-target arrays (Battle.js:
        # 1406-1442 selects buffsSelf for the attacker and buffsOpponent for
        # the defender; the generic 'buffs' equals buffsSelf for OBSTRUCT,
        # the only such move, but must not reach the defender).
        if target in ('self', 'both'):
            sb = move.get('buffsSelf', buffs) if target == 'both' else buffs
            attacker.atk_stage = max(-4, min(4, attacker.atk_stage + sb[0]))
            attacker.def_stage = max(-4, min(4, attacker.def_stage + sb[1]))
        if target in ('opponent', 'both'):
            ob = move.get('buffsOpponent', buffs) if target == 'both' else buffs
            defender.atk_stage = max(-4, min(4, defender.atk_stage + ob[0]))
            defender.def_stage = max(-4, min(4, defender.def_stage + ob[1]))


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------
#
# EXPERIMENTAL TURN MODEL: mechanics='new' (the 2026-06-23 in-game PvP
# turn system; live 2026-06-23, spec at pokemongo.com/news/pvp-updates2026).
#
#   *** UNVALIDATED -- there is NO PvPoke reference for this mode. ***
#   PvPoke still implements the legacy turn system, so the 'new' branch is
#   coded from the published spec alone and cross-checked only against our
#   own spec-derived unit tests (tests/test_new_turn_mechanics.py), never
#   against an external oracle. Treat all 'new'-mode breakpoint/CMP output
#   as experimental.
#
# The spec lists five changes. Mapping to this engine:
#
#   1. DAMAGE + ENERGY resolve at the END of each turn. Implemented: in
#      'new' mode the fast-landing step snapshots damage/energy against the
#      start-of-step state and applies all results together, so a higher-CMP
#      fast move can no longer pre-empt (KO) a same-turn fast move.
#   2. (corollary of 1) one-turn fast attacks on the same turn TIE -- both
#      resolve. Implemented via the simultaneous-apply in change 1 (the
#      legacy CMP sort that let the higher-attack side land first is skipped).
#   5. CHARGED attacks begin at the START of the NEXT turn; charged damage
#      AND effects resolve BEFORE any fast attack finishing during the
#      charged sequence. Implemented: in 'new' mode a charged decision is
#      stamped on the actor (_pending_charged) and resolved at the TOP of the
#      following turn, before that turn's fast landings.
#
#   3. SWAPS resolve before damage, and 4. swap costs (quick=1 turn,
#      forced=0, charged-end=0) are NOT MODELED. Our 1v1 core never switches
#      (simulate() takes exactly two BattlePokemon and the loop has no
#      incoming-Pokemon path), so changes 3 and 4 are unreachable here. They
#      are documented, not faked -- see DEVELOPER_NOTES. They would only
#      matter for the out-of-scope team-sim TODO.
#
# Decision-layer caveat: the AI policies (pvpoke_dp, _optimize_move_timing,
# turnsToLive) encode LEGACY timing assumptions and are NOT re-optimized for
# the new model -- only the resolution step changes. Re-deriving an optimal
# AI for a turn system PvPoke has not shipped would be invention.
#
# PRIME-DIRECTIVE NOTE: every 'new'-mode behavior is guarded by an explicit
# `if mechanics == 'new':` branch (or a _new_-prefixed helper called only
# from such a branch). The legacy path is the unguarded existing code and is
# byte-for-byte unchanged; the default mechanics='legacy' keeps every
# current caller (oracle harness, tests, CLI, dives) on it.

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
    mechanics: str = 'legacy',
) -> BattleResult:
    """
    Run a 1v1 battle between p0 and p1 and return the result.

    p0 and p1 are mutated in place -- reset them before reuse.

    mechanics selects the turn-resolution model:

      'legacy' (DEFAULT) -- the pre-2026-06-23 turn system. This is the
        only path exercised by the oracle harness and the test suite,
        and it must stay byte-for-byte behavior-identical. Every caller
        that omits ``mechanics`` lands here.

      'new' -- EXPERIMENTAL / UNVALIDATED. Models the 2026-06-23 in-game
        PvP turn changes (pokemongo.com/news/pvp-updates2026). PvPoke has
        NOT implemented these, so there is NO reference implementation to
        cross-check against; this branch is implemented from the spec
        alone. It changes damage/energy resolution timing, CMP on
        simultaneous fast moves, and charged-move timing -- so
        breakpoint/bulkpoint/CMP outputs WILL differ from legacy by
        design. See the _new_*  helpers and the in-loop ``mechanics ==
        'new'`` branches below for exactly where it diverges, and the
        module docstring for the spec mapping and the changes (swaps)
        that are deliberately NOT modeled in 1v1.

    debug=True also enables policy decision logging (OMT fires, DP choices).
    Policy log lines are interleaved into BattleResult.timeline at the turn
    they occur; they are indented with two leading spaces for easy filtering.
    Implies log=True.

    trace_shields=True logs every shield policy call with inputs and results.
    trace_dp=True logs DP queue plan and bandaid decisions.
    Both imply log=True and debug=True.
    """
    global _policy_debug, _policy_log, _shield_trace, _dp_trace

    if mechanics not in ('legacy', 'new'):
        raise ValueError(f"mechanics must be 'legacy' or 'new', got {mechanics!r}")

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
    use_priority = (p0.cmp_atk != p1.cmp_atk)

    def log_event(msg: str):
        # Call sites must gate on `if log:` themselves -- the f-string
        # argument is evaluated before the call, and at millions of sims
        # the discarded formatting is measurable. The check here is a
        # backstop only.
        if log:
            timeline.append(f"T{turn:>3}: {msg}")

    def _resolve_charged(charged_actions, allow_dead_attacker=False):
        # Resolve a list of (actor_index, move_dict) charged moves in CMP
        # order. Extracted verbatim from the former inline step 4 so that
        # BOTH the legacy step-4 call site AND the mechanics=='new' deferred
        # block (which runs this at the TOP of the next turn) share one
        # implementation. With allow_dead_attacker=False (the default, used by
        # the legacy step-4 call) behavior is byte-for-byte identical to the
        # old inline loop, so the legacy path is unchanged (oracle/test
        # verified).
        #
        # allow_dead_attacker=True is passed ONLY from the new-mode deferred
        # block: spec change 1 says a charged move already committed still
        # resolves even if its user fainted to a fast (here, on the previous
        # turn). So we skip the "attacker killed by fast" cancel for that path.
        # The simultaneous-charged CMP cancel (charged_ko) still applies.
        if use_priority and len(charged_actions) == 2:
            charged_actions.sort(key=lambda ia: pokemon[ia[0]].cmp_atk, reverse=True)

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
            # opponentChargedMoveThisTurn exception -- simultaneous charged moves
            # are allowed even if one side was killed by a fast move).
            if attacker.hp <= 0 and not allow_dead_attacker:
                opponent_also_charged = any(ai == 1 - actor_idx
                                            for ai, _ in charged_actions)
                if not opponent_also_charged:
                    continue

            if attacker.energy < move['energy']:
                continue   # raced to this -- no longer affordable

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
                    if log:
                        log_event(f"{attacker.species} changed form")

            _, shield_pol = policies[1 - actor_idx]
            use_shield    = shield_pol(attacker, defender, move, mechanics=mechanics)

            if use_shield and defender.shields > 0:
                dmg = 1
                defender.shields -= 1

                # Form change: activate_shield (Aegislash Blade -> Shield)
                if defender.current_form_trigger == 'activate_shield':
                    defender.change_form(attacker)
                    if log:
                        log_event(f"{defender.species} changed form (shielded)")

                if log:
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
                    if log:
                        log_event(f"{attacker.species} uses {move.get('name', move['moveId'])} → {dmg} dmg")
                        log_event(f"{defender.species} disguise busted (1 dmg)")
                elif log:
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
                    if log:
                        log_event(f"{attacker.species} changed form")

    while turn < MAX_TURNS:
        turn += 1

        # --- 1. Decrement cooldowns ---
        for p in pokemon:
            p.cooldown = max(0, p.cooldown - 1)

        # --- 1.5 (mechanics=='new' ONLY) Resolve deferred charged moves ---
        # Spec change 5: a charged move chosen on turn N begins at the START
        # of turn N+1. We resolve it here, AT THE TOP of the turn -- before
        # this turn's fast landings (step 3) and before the actors decide
        # again (step 2) -- so charged damage AND effects (stat changes) land
        # before any fast attack that finishes during the charged sequence,
        # and the actors decide their next move against post-charged state.
        # _pending_charged is never set in legacy mode, so this block is dead
        # there. (Energy is consumed inside _resolve_charged at resolution
        # time, i.e. on turn N+1; see design note (d)2 -- resolving energy
        # with damage lets the legacy and new paths share one resolver.)
        if mechanics == 'new':
            _deferred = [(i, pk._pending_charged)
                         for i, pk in enumerate(pokemon)
                         if pk._pending_charged is not None]
            if _deferred:
                for i, _ in _deferred:
                    pokemon[i]._pending_charged = None
                _resolve_charged(_deferred, allow_dead_attacker=True)
                if p0.hp <= 0 or p1.hp <= 0:
                    break

        # --- 2. Decide and queue actions ---
        # Mirrors PvPoke's cooldownsToSet mechanism: both pokemon see each
        # other's pre-queuing state at decision time. Implemented in three
        # phases:
        #
        # Phase A -- detect fast-move landings (but keep _queued_fast set so
        #   the turnsToLive DP can see in-flight FMs during decisions).
        # Phase B -- collect decisions (no state mutation; each pokemon sees
        #   the other's cooldown/energy BEFORE any new queuing this turn).
        # Phase C -- apply decisions and clear landed-FM state.
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
                move_idx = charged_pol(p, opponent, mechanics=mechanics)
                if move_idx is not None:
                    _pending.append((i, 'charged', move_idx))
                else:
                    fm = p.fast_move
                    if log:
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
                if mechanics == 'new':
                    # Spec change 5: defer to the START of the next turn.
                    # Stamp the move on the actor; it is drained and resolved
                    # in step 1.5 next turn. charged_actions stays empty in
                    # 'new' mode, so the same-turn step 4 + floating-fast
                    # block below are no-ops (they gate on charged_actions).
                    p._pending_charged = p.charged_moves[data]
                else:
                    charged_actions.append((i, p.charged_moves[data]))
            elif action_type == 'fast_1':
                fast_landings.append((i, data))
                p.cooldown = 1   # blocks re-acting until next turn
            else:   # 'fast_multi'
                p._queued_fast = (turn, data)
                p.cooldown = data['_turns']

        # --- 3. Resolve fast move landings (fire BEFORE charged moves) ---
        if mechanics == 'new':
            # Spec changes 1+2: damage+energy resolve at the END of the turn,
            # so simultaneously-landing one-turn fast moves TIE -- neither can
            # pre-empt (KO) the other. We snapshot each landing's damage and
            # energy against the START-of-step state, then apply all results
            # together. No CMP sort (the legacy sort exists only to let the
            # higher-attack side land first, which the tie semantics remove).
            # A fast against a defender already fainted THIS turn (from the
            # step-1.5 deferred charged) is still skipped -- a faint is a faint.
            _fast_results = []   # (defender_idx, dmg, attacker_idx, energy)
            for actor_idx, move in fast_landings:
                attacker = pokemon[actor_idx]
                defender = pokemon[1 - actor_idx]
                if defender.hp <= 0:
                    continue   # fainted by deferred charged in step 1.5
                dmg = attacker.fast_move_damage(defender)
                _fast_results.append((1 - actor_idx, dmg, actor_idx,
                                      move['energyGain']))
            for defender_idx, dmg, attacker_idx, energy_gain in _fast_results:
                attacker = pokemon[attacker_idx]
                defender = pokemon[defender_idx]
                attacker.energy = min(ENERGY_CAP, attacker.energy + energy_gain)
                defender.hp = max(0, defender.hp - dmg)
                attacker.cooldown = 0
                attacker._fm_since_charge += 1
                if log:
                    log_event(
                        f"{attacker.species} fast → {dmg} dmg, "
                        f"energy {attacker.energy}"
                    )
        else:
            # Legacy: naturally-due fast moves resolve before charged moves.
            # When two fast moves land simultaneously, the game resolves them
            # in descending atk order (higher effective attack fires first).
            # PvPoke matches this.
            if len(fast_landings) > 1:
                fast_landings.sort(key=lambda ia: pokemon[ia[0]].cmp_atk, reverse=True)
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

                if log:
                    log_event(
                        f"{attacker.species} fast → {dmg} dmg, "
                        f"energy {attacker.energy}"
                    )

        # --- 4. Resolve charged moves (higher priority first) ---
        # Skip if defender was already killed by the fast move this turn.
        _resolve_charged(charged_actions)

        # After any charged move this turn, fire "floating" fast moves then reset.
        # PvPoke Battle.js: a fast move queued in the same turn as a charged move
        # (timeSinceActivated < requiredTimeToPass) fires at -20 priority (after
        # the charged move) rather than being cancelled.  This is simulate mode
        # only -- queuedActions is never cleared by a charged move in simulate mode.
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
                            if log:
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
            # mechanics=='new' (spec change 1): a charged move already committed
            # this turn STILL resolves even if its user is fainting from a fast
            # this turn. Under our deferral model the commit resolves at the top
            # of the NEXT turn (step 1.5), so we must not break out while a
            # _pending_charged is outstanding -- let the loop run one more turn so
            # step 1.5 fires it, then the faint check breaks. (Legacy resolves
            # charged same-turn, so this never applies there.)
            if mechanics == 'new' and (p0._pending_charged is not None
                                       or p1._pending_charged is not None):
                pass
            else:
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
