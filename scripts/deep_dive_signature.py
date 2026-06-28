"""Damage-signature dedup for deep-dive IV sweeps (arc S3, 2026-06-10).

Two focal IV profiles fight bit-identical battles against a given
opponent whenever every stat-derived value the battle engine consumes
is identical. The audit of battle.py / _dp_jit.py found exactly three
ways raw stats enter a battle:

  1. damage:  every damage number flows through
     ``moves.damage(power, atk * stage_mult, def_ * stage_mult, ...)``
     (per-move, per-stat-stage; see _ensure_dmg_cache /
     _ensure_dp_cache);
  2. CMP:     pairwise attack-priority comparisons between the two
     combatants (``>``, ``>=``, ``<``, ``!=`` at the CMP/ordering sites
     in battle.py), captured exactly by the 3-way sign of
     (focal.cmp_atk - opp.cmp_atk). NB this is the shadow-STRIPPED
     attack (``atk / 1.2`` for a shadow mon): the x1.2 boosts damage but
     not priority, so the dedup column divides each side by its own
     shadow factor (signature_groups, per the 2026-06-13 cmp_atk fix) —
     NOT the raw focal.atk/opp.atk an earlier version of this note named;
  3. HP:      the integer max HP.

Everything else (moves, types, energy, cooldowns, buff config, form
triggers) is identical across profiles of one sweep. So the
"signature" of a (focal profile, opponent) pair is the tuple of all
damage values both directions (over every reachable stat-stage
combination, for every form combination when either side changes
form), the CMP sign per form combination, and the HP. Profiles with
equal signatures get one representative sim; the score fans out.

Stat stages only move when something can move them. Mutation sites:
  - _apply_move_buffs (buffTarget-aware: 'self'/'opponent'/'both',
    gated on buffApplyChance > 0 — the deterministic meter fires
    eventually for any chance > 0);
  - would_shield's temporary projection (battle.py:466-473), which
    IGNORES buffTarget: any charged move with buffs[0] > 0 moves the
    thrower's atk stage; otherwise buffs[1] moves the shield
    decider's def stage;
  - form-change nativeStatBuffs (applied to the mon entering the
    form, e.g. Mimikyu Busted).
A stage axis that nothing can move stays at 0, and the signature
only carries the stage-0 damage row; a movable axis carries the full
-4..+4 range (a reachable superset — over-inclusion can only reduce
dedup, never correctness).

Floating-point exactness: damage_vec mirrors moves.damage's operand
order exactly (left-to-right ``0.5 * BONUS * power * atk / def_ *
eff * stab``), and stage-adjusted stats are computed as
``stat * _stat_stage_mult(s)`` exactly like the engine. IEEE-754
float64 elementwise ops in numpy are bit-identical to Python scalar
float ops, so vectorized floors match math.floor per element
(pinned by tests/test_signature_dedup.py).
"""
import numpy as np

from gopvpsim.battle import _stat_stage_mult
from gopvpsim.formchange import build_form_change_state
from gopvpsim.moves import BONUS, stab, type_effectiveness

FULL_STAGES = tuple(range(-4, 5))
ZERO_STAGE = (0,)


def damage_vec(power, atk, def_, move_type, attacker_types, defender_types):
    """Vectorized bit-exact mirror of gopvpsim.moves.damage.

    ``atk`` / ``def_`` may be scalars or float64 arrays (at least one
    should be an array). Returns an int64 array.
    """
    eff = type_effectiveness(move_type, defender_types)
    stab_ = stab(move_type, attacker_types)
    return np.floor(0.5 * BONUS * power * atk / def_ * eff * stab_).astype(np.int64) + 1


def _form_dict(types, fast_move, charged_moves, atk, def_):
    return {
        'types': tuple(types),
        'fast': fast_move,
        'charged': list(charged_moves),
        'atk': atk,
        'def_': def_,
    }


def _native_movability(cfgs):
    """(atk_movable, def_movable) from nativeStatBuffs across form configs."""
    atk_mov = def_mov = False
    for cfg in cfgs:
        if cfg is None:
            continue
        for fd in cfg.forms:
            if fd.native_stat_buffs is not None:
                if fd.native_stat_buffs[0] != 0:
                    atk_mov = True
                if fd.native_stat_buffs[1] != 0:
                    def_mov = True
    return atk_mov, def_mov


def build_focal_side(focal_mon, focal_types, fm_template, cms_template,
                     profile_list, league_cp, shadow):
    """Build the focal-side signature struct from sweep profile tuples.

    profile_list entries: (pk, atk, def_, hp, atk_iv, def_iv, sta_iv, level)
    — the same tuples iv_sweep hands to the workers.
    """
    atk = np.array([p[1] for p in profile_list], dtype=np.float64)
    def_ = np.array([p[2] for p in profile_list], dtype=np.float64)
    hp = np.array([p[3] for p in profile_list], dtype=np.int64)
    forms = [_form_dict(focal_types, fm_template, cms_template, atk, def_)]
    cfg0 = None
    if focal_mon.get('formChange') is not None:
        alt_atks, alt_defs = [], []
        base_atks, base_defs = [], []
        for p in profile_list:
            cfg = build_form_change_state(
                focal_mon, p[4], p[5], p[6], p[7], league_cp, shadow,
                fm_template, cms_template)
            if cfg is None:
                break
            cfg0 = cfg
            alt_atks.append(cfg.forms[1].atk)
            alt_defs.append(cfg.forms[1].def_)
            base_atks.append(cfg.forms[0].atk)
            base_defs.append(cfg.forms[0].def_)
        if cfg0 is not None:
            f1 = cfg0.forms[1]
            forms.append(_form_dict(
                f1.types, f1.fast_move, f1.charged_moves,
                np.array(alt_atks, dtype=np.float64),
                np.array(alt_defs, dtype=np.float64)))
            # apply_form_change restores the base form from FormData's
            # recomputed stats; if those ever drift bitwise from the
            # construction-time stats, treat the recomputation as a
            # third "form" so the signature still covers every value
            # the battle can use. (Same expression today — this is
            # belt-and-braces, normally dead.)
            b_atk = np.array(base_atks, dtype=np.float64)
            b_def = np.array(base_defs, dtype=np.float64)
            if not (np.array_equal(b_atk, atk) and np.array_equal(b_def, def_)):
                forms.append(_form_dict(
                    cfg0.forms[0].types, cfg0.forms[0].fast_move,
                    cfg0.forms[0].charged_moves, b_atk, b_def))
    native_atk, native_def = _native_movability([cfg0])
    return {'forms': forms, 'hp': hp, 'shadow': bool(shadow),
            'native_atk': native_atk, 'native_def': native_def}


def build_opp_side(opp, league_cp):
    """Build the opponent-side signature struct from an iv_sweep
    opp_cache entry (scalar stats)."""
    forms = [_form_dict(opp['types'], opp['fm'], opp['cms'],
                        float(opp['atk']), float(opp['def_']))]
    cfg = None
    if opp['mon'].get('formChange') is not None:
        cfg = build_form_change_state(
            opp['mon'], *opp['ivs'], opp['level'], league_cp,
            opp['shadow'], opp['fm'], opp['cms'])
        if cfg is not None:
            f1 = cfg.forms[1]
            forms.append(_form_dict(f1.types, f1.fast_move,
                                    f1.charged_moves, f1.atk, f1.def_))
            f0 = cfg.forms[0]
            if f0.atk != opp['atk'] or f0.def_ != opp['def_']:
                forms.append(_form_dict(f0.types, f0.fast_move,
                                        f0.charged_moves, f0.atk, f0.def_))
    native_atk, native_def = _native_movability([cfg])
    return {'forms': forms, 'shadow': bool(opp['shadow']),
            'native_atk': native_atk, 'native_def': native_def}


def _side_moves(side):
    """(all moves, charged-only moves) across a side's forms."""
    all_moves, charged = [], []
    for f in side['forms']:
        all_moves.append(f['fast'])
        all_moves.extend(f['charged'])
        charged.extend(f['charged'])
    return all_moves, charged


def _chance(m):
    raw = m.get('buffApplyChance', 0)
    return float(raw) if raw else 0.0


def movable_axes(side, other):
    """Return (atk_movable, def_movable) for `side`, given both sides'
    movesets — the exact superset of the engine's stage-mutation sites
    (see module docstring)."""
    own_all, own_charged = _side_moves(side)
    oth_all, oth_charged = _side_moves(other)

    def b(m):
        return m.get('buffs') or (0, 0)

    atk_mov = side['native_atk'] or any(
        # _apply_move_buffs: own self/both-target moves touching atk
        b(m)[0] != 0 and _chance(m) > 0
        and m.get('buffTarget', 'opponent') in ('self', 'both')
        for m in own_all if m.get('buffs')
    ) or any(
        # would_shield temp projection: own charged move with atk buff
        b(m)[0] > 0 for m in own_charged if m.get('buffs')
    ) or any(
        # _apply_move_buffs: other side's opponent/both-target moves
        b(m)[0] != 0 and _chance(m) > 0
        and m.get('buffTarget', 'opponent') in ('opponent', 'both')
        for m in oth_all if m.get('buffs')
    )

    def_mov = side['native_def'] or any(
        b(m)[1] != 0 and _chance(m) > 0
        and m.get('buffTarget', 'opponent') in ('self', 'both')
        for m in own_all if m.get('buffs')
    ) or any(
        b(m)[1] != 0 and _chance(m) > 0
        and m.get('buffTarget', 'opponent') in ('opponent', 'both')
        for m in oth_all if m.get('buffs')
    ) or any(
        # would_shield else-branch: other side's charged move without a
        # positive atk buff applies buffs[1] to OUR def stage
        b(m)[0] <= 0 and b(m)[1] != 0 for m in oth_charged if m.get('buffs')
    )
    return atk_mov, def_mov


def signature_groups(focal_side, opp_side):
    """Group focal profiles by battle signature vs one opponent.

    Returns a list of (rep_pos, member_positions) — positions index
    into the profile_list that built focal_side. Profiles in one group
    fight bit-identical battles vs this opponent in every shield
    scenario, so one representative sim covers the group.
    """
    n = len(focal_side['hp'])
    f_atk_mov, f_def_mov = movable_axes(focal_side, opp_side)
    o_atk_mov, o_def_mov = movable_axes(opp_side, focal_side)
    # CMP is decided on the UNBOOSTED attack: shadow's x1.2 boosts damage but
    # not priority (battle.py cmp_atk, 2026-06-13 fix). Strip it per side so
    # the CMP column matches the engine even for shadow-mismatched pairs.
    # (Defaults False so any caller that pre-dates the 'shadow' key is treated
    # as non-shadow, i.e. the old effective-atk behavior.)
    f_cmp_div = 1.2 if focal_side.get('shadow') else 1.0
    o_cmp_div = 1.2 if opp_side.get('shadow') else 1.0
    a_f = FULL_STAGES if f_atk_mov else ZERO_STAGE
    d_f = FULL_STAGES if f_def_mov else ZERO_STAGE
    a_o = FULL_STAGES if o_atk_mov else ZERO_STAGE
    d_o = FULL_STAGES if o_def_mov else ZERO_STAGE

    cols = [focal_side['hp']]
    for ff in focal_side['forms']:
        for of in opp_side['forms']:
            # CMP: 3-way sign covers >, >=, <, != comparisons, on cmp_atk
            cols.append(np.sign(
                ff['atk'] / f_cmp_div - of['atk'] / o_cmp_div).astype(np.int64))
            for m in [ff['fast'], *ff['charged']]:
                for a_s in a_f:
                    atk_eff = ff['atk'] * _stat_stage_mult(a_s)
                    for d_s in d_o:
                        def_eff = of['def_'] * _stat_stage_mult(d_s)
                        cols.append(damage_vec(
                            m['power'], atk_eff, def_eff, m['type'],
                            ff['types'], of['types']))
            for m in [of['fast'], *of['charged']]:
                for a_s in a_o:
                    atk_eff = of['atk'] * _stat_stage_mult(a_s)
                    for d_s in d_f:
                        def_eff = ff['def_'] * _stat_stage_mult(d_s)
                        cols.append(damage_vec(
                            m['power'], atk_eff, def_eff, m['type'],
                            of['types'], ff['types']))

    mat = np.column_stack(cols)
    groups = {}
    for pos in range(n):
        groups.setdefault(mat[pos].tobytes(), []).append(pos)
    return [(members[0], members) for members in groups.values()]
