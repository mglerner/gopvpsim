"""
Numba JIT'd near-KO DP loop for pvpoke_dp.

This module isolates the hot inner DP loop from `pvpoke_dp` (battle.py) so
that numba can compile it ahead of time and cache the result on disk
(`@njit(cache=True)`).

The JIT function `_near_ko_dp_jit` is a faithful port of the pure-Python
near-KO loop: it pops the front of a queue, expands each state by every
charged move (ready → insert AFTER same-turn with dedup; not-ready → insert
BEFORE same-turn), and adds a farm-down state. The plan summary tracked per
state is a small set of scalars (first thrown move, max-damage move, has-
debuffing flag, net debuff count) — see `_DPState` in battle.py for the
rationale.

Each state also carries an `atk_stage` (attacker atk-stage). Chance-1
self-atk-buffs and chance-1 opp-def-debuffs increment it on throw; the
kernel indexes a precomputed per-stage damage table (9 rows, one per stage
in [-4..+4]) for `cm_dmgs` and `fast_damage`. This mirrors PvPoke's
`attackMult` accumulation in ActionLogic.js.

Numba is treated as an optional dependency. If the import fails or numba
itself errors out at compile time, this module exposes
`_near_ko_dp_jit = None` and `pvpoke_dp` falls back to the pure-Python loop
that already lives in battle.py.

Performance contract:
- Inputs are passed as numpy arrays (int64 / float64 / int8) to avoid the
  per-call object overhead Python uses.
- The queue is preallocated as parallel numpy arrays of fixed capacity
  (QUEUE_CAP). The Python version's queue rarely exceeds ~50 entries at
  steady state; capacity 1024 is comfortable headroom.
- Pop from front is O(n) (memmove of the queue tails). Same as the
  Python `list.pop(0)` we are replacing — not worth a circular buffer.
"""
from __future__ import annotations

import numpy as np

QUEUE_CAP = 1024
MAX_ITERS = 500

try:
    from numba import njit
except ImportError:                     # pragma: no cover - numba optional
    njit = None


def _make_jit():
    """Build the JIT function. Returns None if numba is unavailable.

    Wrapped in a builder function so an import-time numba failure (e.g.
    LLVM mismatch) degrades gracefully — battle.py's pure-Python loop
    handles the fallback.
    """
    if njit is None:
        return None

    @njit(cache=True)
    def _near_ko_dp_jit(
        cm_dmgs,            # float64[:] (root-stage damage; used for max-dmg ordering)
        cm_energy,          # int64[:]
        cm_self_debuf,      # int8[:]   (0/1 per move)
        cm_debuf_delta,     # int8[:]   (-1/0/+1 per move)
        cm_buff_delta,      # int8[:]   (atk-stage delta per throw)
        cm_dmgs_stage,      # float64[:,:] shape (9, n_cms); indexed by stage+4
        fast_dmg_stage,     # int64[:]    shape (9,); indexed by stage+4
        root_atk_stage,     # int
        n_cms,              # int
        start_energy,       # int
        start_hp,           # float
        start_shields,      # int
        fast_damage,        # int (unused — kept for signature stability)
        fast_energy,        # int
        fast_turns,         # int
        intended_pruning,   # bool
    ):
        """Run the near-KO DP. Returns a 9-tuple of scalars:

            (found, first_idx, max_dmg_idx, has_debuf, debuf_count,
             final_turn, final_hp, final_shields, iters)

        ``found=False`` means no KO plan was discovered within MAX_ITERS;
        callers fall back to the best-DPE greedy. ``first_idx=-1`` means the
        plan is the trivial farm-down (no charged moves); the caller should
        return None (PvPoke "no action") in that case.
        """
        # Preallocated queue (struct of arrays).
        q_energy   = np.empty(QUEUE_CAP, dtype=np.int64)
        q_hp       = np.empty(QUEUE_CAP, dtype=np.float64)
        q_turn     = np.empty(QUEUE_CAP, dtype=np.int64)
        q_shields  = np.empty(QUEUE_CAP, dtype=np.int64)
        q_first    = np.empty(QUEUE_CAP, dtype=np.int64)
        q_max_idx  = np.empty(QUEUE_CAP, dtype=np.int64)
        q_has_deb  = np.empty(QUEUE_CAP, dtype=np.int8)
        q_deb_cnt  = np.empty(QUEUE_CAP, dtype=np.int64)
        q_atk_stg  = np.empty(QUEUE_CAP, dtype=np.int64)

        q_energy[0]  = start_energy
        q_hp[0]      = start_hp
        q_turn[0]    = 0
        q_shields[0] = start_shields
        q_first[0]   = -1
        q_max_idx[0] = -1
        q_has_deb[0] = 0
        q_deb_cnt[0] = 0
        q_atk_stg[0] = root_atk_stage
        q_size = 1

        found = False
        out_first = -1
        out_max_idx = -1
        out_has_deb = np.int8(0)
        out_deb_cnt = 0
        out_turn = 0
        out_hp = 0.0
        out_shields = 0

        iters = 0
        while q_size > 0 and iters < MAX_ITERS:
            iters += 1

            # ---- Pop from front (O(n) shift, mirrors list.pop(0)) ----
            curr_e       = q_energy[0]
            curr_hp      = q_hp[0]
            curr_t       = q_turn[0]
            curr_sh      = q_shields[0]
            curr_first   = q_first[0]
            curr_max_idx = q_max_idx[0]
            curr_has_deb = q_has_deb[0]
            curr_deb_cnt = q_deb_cnt[0]
            curr_atk_stg = q_atk_stg[0]
            for k in range(q_size - 1):
                q_energy[k]  = q_energy[k + 1]
                q_hp[k]      = q_hp[k + 1]
                q_turn[k]    = q_turn[k + 1]
                q_shields[k] = q_shields[k + 1]
                q_first[k]   = q_first[k + 1]
                q_max_idx[k] = q_max_idx[k + 1]
                q_has_deb[k] = q_has_deb[k + 1]
                q_deb_cnt[k] = q_deb_cnt[k + 1]
                q_atk_stg[k] = q_atk_stg[k + 1]
            q_size -= 1

            # KO achieved → first plan reached is fastest (BFS-by-turn).
            if curr_hp <= 0.0:
                found = True
                out_first = curr_first
                out_max_idx = curr_max_idx
                out_has_deb = curr_has_deb
                out_deb_cnt = curr_deb_cnt
                out_turn = curr_t
                out_hp = curr_hp
                out_shields = curr_sh
                break

            curr_max_dmg = -1.0
            if curr_max_idx >= 0:
                curr_max_dmg = cm_dmgs[curr_max_idx]

            stage_row_idx = curr_atk_stg + 4
            curr_fast_dmg = fast_dmg_stage[stage_row_idx]

            for n in range(n_cms):
                move_dmg_root = cm_dmgs[n]         # for max-dmg ordering
                move_dmg      = cm_dmgs_stage[stage_row_idx, n]
                move_e        = cm_energy[n]

                # Update scalar plan summary for the new state.
                new_first = curr_first if curr_first >= 0 else n
                if move_dmg_root > curr_max_dmg:
                    new_max_idx = n
                else:
                    new_max_idx = curr_max_idx
                new_has_deb = curr_has_deb | cm_self_debuf[n]
                new_deb_cnt = curr_deb_cnt + cm_debuf_delta[n]
                new_atk_stg = curr_atk_stg + cm_buff_delta[n]
                if new_atk_stg > 4:
                    new_atk_stg = 4
                elif new_atk_stg < -4:
                    new_atk_stg = -4

                if curr_e >= move_e:
                    # ---- Move ready: insert AFTER same-turn (<=) ----
                    new_e = curr_e - move_e
                    new_t = curr_t + 1
                    new_sh = curr_sh
                    if curr_sh > 0:
                        new_hp = curr_hp - 1.0
                        new_sh -= 1
                    else:
                        new_hp = curr_hp - move_dmg

                    # Phase 1 dedup (PvPoke ActionLogic.js 544-586): scan
                    # states at exactly turn == new_t. Same-hp same-energy
                    # same-atk_stage → keep the lower-debuff one;
                    # same-hp+atk_stage different-energy → drop the new state.
                    insert_element = True
                    i = 0
                    qsz = q_size
                    while i < qsz and q_turn[i] == new_t:
                        if q_hp[i] == new_hp and q_atk_stg[i] == new_atk_stg:
                            if q_energy[i] == new_e:
                                if q_deb_cnt[i] > new_deb_cnt:
                                    # Pop existing worse state at i.
                                    for k in range(i, qsz - 1):
                                        q_energy[k]  = q_energy[k + 1]
                                        q_hp[k]      = q_hp[k + 1]
                                        q_turn[k]    = q_turn[k + 1]
                                        q_shields[k] = q_shields[k + 1]
                                        q_first[k]   = q_first[k + 1]
                                        q_max_idx[k] = q_max_idx[k + 1]
                                        q_has_deb[k] = q_has_deb[k + 1]
                                        q_deb_cnt[k] = q_deb_cnt[k + 1]
                                        q_atk_stg[k] = q_atk_stg[k + 1]
                                    qsz -= 1
                                    # do NOT advance i — new element shifted into i
                                else:
                                    insert_element = False
                                    i += 1
                            else:
                                insert_element = False
                                i += 1
                        else:
                            i += 1
                    q_size = qsz

                    if insert_element:
                        # Phase 2 dominance (intended-pruning only).
                        i = 0
                        dominated = False
                        if intended_pruning:
                            while i < q_size and q_turn[i] <= new_t:
                                if (q_hp[i] <= new_hp
                                        and q_energy[i] >= new_e
                                        and q_shields[i] <= new_sh):
                                    dominated = True
                                    break
                                i += 1
                        else:
                            while i < q_size and q_turn[i] <= new_t:
                                i += 1

                        if not dominated and q_size < QUEUE_CAP:
                            # Insert at position i (shift right).
                            for k in range(q_size, i, -1):
                                q_energy[k]  = q_energy[k - 1]
                                q_hp[k]      = q_hp[k - 1]
                                q_turn[k]    = q_turn[k - 1]
                                q_shields[k] = q_shields[k - 1]
                                q_first[k]   = q_first[k - 1]
                                q_max_idx[k] = q_max_idx[k - 1]
                                q_has_deb[k] = q_has_deb[k - 1]
                                q_deb_cnt[k] = q_deb_cnt[k - 1]
                                q_atk_stg[k] = q_atk_stg[k - 1]
                            q_energy[i]  = new_e
                            q_hp[i]      = new_hp
                            q_turn[i]    = new_t
                            q_shields[i] = new_sh
                            q_first[i]   = new_first
                            q_max_idx[i] = new_max_idx
                            q_has_deb[i] = new_has_deb
                            q_deb_cnt[i] = new_deb_cnt
                            q_atk_stg[i] = new_atk_stg
                            q_size += 1
                else:
                    # ---- Move not ready: insert BEFORE same-turn (<) ----
                    # ceil((move_e - curr_e) / fast_energy)
                    diff = move_e - curr_e
                    fm_needed = (diff + fast_energy - 1) // fast_energy
                    turns_needed = fm_needed * fast_turns
                    new_e = fm_needed * fast_energy + curr_e - move_e
                    new_t = curr_t + turns_needed + 1
                    new_sh = curr_sh
                    if curr_sh > 0:
                        new_hp = curr_hp - curr_fast_dmg * fm_needed - 1.0
                        new_sh -= 1
                    else:
                        new_hp = curr_hp - curr_fast_dmg * fm_needed - move_dmg

                    i = 0
                    dominated = False
                    if intended_pruning:
                        while i < q_size and q_turn[i] < new_t:
                            if (q_hp[i] <= new_hp
                                    and q_energy[i] >= new_e
                                    and q_shields[i] <= new_sh):
                                dominated = True
                                break
                            i += 1
                    else:
                        while i < q_size and q_turn[i] < new_t:
                            i += 1

                    if not dominated and q_size < QUEUE_CAP:
                        for k in range(q_size, i, -1):
                            q_energy[k]  = q_energy[k - 1]
                            q_hp[k]      = q_hp[k - 1]
                            q_turn[k]    = q_turn[k - 1]
                            q_shields[k] = q_shields[k - 1]
                            q_first[k]   = q_first[k - 1]
                            q_max_idx[k] = q_max_idx[k - 1]
                            q_has_deb[k] = q_has_deb[k - 1]
                            q_deb_cnt[k] = q_deb_cnt[k - 1]
                            q_atk_stg[k] = q_atk_stg[k - 1]
                        q_energy[i]  = new_e
                        q_hp[i]      = new_hp
                        q_turn[i]    = new_t
                        q_shields[i] = new_sh
                        q_first[i]   = new_first
                        q_max_idx[i] = new_max_idx
                        q_has_deb[i] = new_has_deb
                        q_deb_cnt[i] = new_deb_cnt
                        q_atk_stg[i] = new_atk_stg
                        q_size += 1

            # ---- Farm-down state (no new charged move thrown) ----
            if curr_fast_dmg > 0 and curr_hp > 0.0:
                fm_to_ko = int((curr_hp + curr_fast_dmg - 1) // curr_fast_dmg)
                fd_turn = curr_t + fm_to_ko * fast_turns
                fd_energy = curr_e + fast_energy * fm_to_ko

                # Insert AFTER same-turn (<=). Intended-pruning would block
                # if any earlier same-turn state already has hp < 0; we
                # carry an int8 dummy for that since farm-down hp == 0.
                i = 0
                blocked = False
                if intended_pruning:
                    while i < q_size and q_turn[i] <= fd_turn:
                        if q_hp[i] < 0.0:
                            blocked = True
                            break
                        i += 1
                else:
                    while i < q_size and q_turn[i] <= fd_turn:
                        i += 1

                if not blocked and q_size < QUEUE_CAP:
                    for k in range(q_size, i, -1):
                        q_energy[k]  = q_energy[k - 1]
                        q_hp[k]      = q_hp[k - 1]
                        q_turn[k]    = q_turn[k - 1]
                        q_shields[k] = q_shields[k - 1]
                        q_first[k]   = q_first[k - 1]
                        q_max_idx[k] = q_max_idx[k - 1]
                        q_has_deb[k] = q_has_deb[k - 1]
                        q_deb_cnt[k] = q_deb_cnt[k - 1]
                        q_atk_stg[k] = q_atk_stg[k - 1]
                    q_energy[i]  = fd_energy
                    q_hp[i]      = 0.0
                    q_turn[i]    = fd_turn
                    q_shields[i] = curr_sh
                    q_first[i]   = curr_first
                    q_max_idx[i] = curr_max_idx
                    q_has_deb[i] = curr_has_deb
                    q_deb_cnt[i] = curr_deb_cnt
                    q_atk_stg[i] = curr_atk_stg
                    q_size += 1

        return (found, out_first, out_max_idx, int(out_has_deb), out_deb_cnt,
                out_turn, out_hp, out_shields, iters)

    return _near_ko_dp_jit


_near_ko_dp_jit = _make_jit()
