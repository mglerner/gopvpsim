#!/usr/bin/env python
"""Tier-0 closed-form damage-tier tables for the Worlds 2026 robustness
analysis (plan: docs/worlds_prep_plan.md, session 2).

Damage in the legacy engine is ``floor(0.5 * BONUS * power * atk / def_
* eff * stab) + 1`` (moves.py, one site), monotone nondecreasing in atk
and nonincreasing in def_ under IEEE-754 rounding (each step is a
correctly-rounded op with a fixed positive operand; verified in the
2026-08-10 float-exactness audit). So every cutoff here is computed by
FLOAT BISECTION down to adjacent binary64 values against the EXACT
engine predicate -- the returned cutoffs are exact by construction, in
EFFECTIVE stat space (shadow multipliers already applied, as iv_rank
emits and the engine consumes).

Two things this module refuses to do, both audit findings:

* No retyped damage constants. The predicate literally calls
  ``gopvpsim.moves.damage``; a local ``0.5 * 1.3 * ...`` copy is the
  drift the float32-constant bug class comes from
  (tests/test_worlds_tier0.py scans for it).
* No closed form for form-change species (Aegislash). Blade-form attack
  is NON-MONOTONE in the Shield-form attack IV (a +1 atk IV can drop a
  whole Blade level via the CP-cap-quantized whole-level rule), so an
  "atk >= cutoff" card is wrong in SIGN, not just imprecise.
  ``closed_form_excluded`` is the enforced gate; zero-power form moves
  (AEGISLASH_CHARGE_*) additionally hard-fail the power guard.

Cutoffs are per (move, tier, opponent def) / (move, tier, attacker atk)
FUNCTIONS, not a single separable pair -- in float arithmetic the
rounding depends on both operands, and the shipped reach numbers are
COMPOSITE ``n_fast * dmg_fast + n_charged * dmg_charged >= hp`` cutoffs
(``ko_cutoff``), which the plan's per-move framing understates. Two
DISTINCT quantities feed a reach card and must never be conflated
(2026-08-10 review): the per-spread ``ko_cutoff`` (one opponent
(def, hp)) and the cohort-max ``guarantee_cutoff`` ("beats every
plausible X") -- DragapultSim's published Tinkaton-vs-Mantine pair maps
109.28 to the former (the 0/15/7 anchor) and 110.21 to the latter, and
our engine reproduces both to <0.1 under the minimal ENERGY-LEGAL plan
(14 Fairy Wind + 2 Gigaton; 12 fast moves cannot fund 2 Gigatons).

Stage axes: stage-0 reach cutoffs are conservative (safe) but stage-0
DENY cutoffs are optimistic whenever the attacker carries an
opponent-def debuff (Bulldoze: "denies at 170.36 def" becomes ~213 once
one lands). 10 of the 31 meta entries carry a stage-moving move, so
every cutoff function takes explicit ``stage_atk`` / ``stage_def`` and
``movable_stage_axes`` reports which axes a pair can move (delegating
to deep_dive_signature.movable_axes -- the audited superset of the
engine's mutation sites, would_shield projection quirk included).
Renderers must not print a stage-0 deny number for a stage-affected
pair without the staged rows or an explicit flag.
"""
import math
import os
import sys

from gopvpsim.moves import damage as _engine_damage
from gopvpsim.battle import _stat_stage_mult
from gopvpsim.pokemon import SHADOW_ATK_BONUS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deep_dive_lib.robustness import _species_has_form_change

# Effective-stat bisection bracket. GL effective stats live in ~[60, 260];
# ML best-buddy shadows top out well under 500. The bracket is validated
# per call (predicate must be False at lo, True at hi), so a pathological
# input fails loud rather than clamping.
ATK_BRACKET = (1.0e-2, 1.0e5)
DEF_BRACKET = (1.0e-2, 1.0e5)

# Algebraic-seed drift tripwire: tests/test_worlds_tier0.py computes the
# naive associated-constant seed (which lives in the TEST, keeping this
# module free of damage-constant arithmetic) and asserts it stays within
# this many ULP of the exact bisected cutoff -- a blowup means the engine
# expression in moves.py was reordered.
SEED_ULP_TRIPWIRE = 8


class ClosedFormError(ValueError):
    """A closed-form request the damage model cannot honestly answer."""


def closed_form_excluded(species_name):
    """True when the species is footnoted OUT of every closed-form page
    (form-change species; see module docstring for the Aegislash
    non-monotonicity mechanism)."""
    return _species_has_form_change(species_name)


def staged_damage(move, atk, def_, attacker_types, defender_types,
                  stage_atk=0, stage_def=0):
    """The engine's damage for one move at explicit stat stages.

    Mirrors battle.py's consumption exactly: stats are stage-multiplied
    (``stat * _stat_stage_mult(s)``) BEFORE the single damage site in
    moves.py. ``atk``/``def_`` are EFFECTIVE (shadow-applied) stats.
    """
    power = move['power']
    if not power > 0:
        raise ClosedFormError(
            f"move {move.get('moveId', move.get('name', '?'))!r} has no "
            f"damage component (power={power!r}) -- closed-form tiers are "
            f"undefined for it (Aegislash form moves land here)")
    return _engine_damage(power, atk * _stat_stage_mult(stage_atk),
                          def_ * _stat_stage_mult(stage_def),
                          move['type'], attacker_types, defender_types)


def _min_true(pred, lo, hi, what):
    """Minimal float in [lo, hi] with ``pred`` True.

    ``pred`` must be monotone False -> True over [lo, hi]. Bisection on
    binary64 midpoints terminates at adjacent floats; the result is
    exact w.r.t. the predicate (no epsilon anywhere). Raises
    ClosedFormError when the bracket does not straddle the boundary.
    """
    if pred(lo):
        raise ClosedFormError(f'{what}: satisfied over the whole bracket '
                              f'(lo={lo!r}) -- tier below the attainable range')
    if not pred(hi):
        raise ClosedFormError(f'{what}: unsatisfiable within the bracket '
                              f'(hi={hi!r}) -- tier above the attainable range')
    while True:
        mid = lo + (hi - lo) / 2.0
        if mid <= lo or mid >= hi:
            break
        if pred(mid):
            hi = mid
        else:
            lo = mid
    return hi


def _max_true(pred, lo, hi, what):
    """Maximal float in [lo, hi] with ``pred`` True (monotone True ->
    False). Companion of _min_true; same exactness argument."""
    if not pred(lo):
        raise ClosedFormError(f'{what}: unsatisfiable within the bracket '
                              f'(lo={lo!r})')
    if pred(hi):
        raise ClosedFormError(f'{what}: satisfied over the whole bracket '
                              f'(hi={hi!r})')
    while True:
        mid = lo + (hi - lo) / 2.0
        if mid <= lo or mid >= hi:
            break
        if pred(mid):
            lo = mid
        else:
            hi = mid
    return lo


def atk_cutoff(move, attacker_types, defender_types, tier, def_,
               stage_atk=0, stage_def=0, bracket=ATK_BRACKET):
    """Minimal EFFECTIVE atk dealing >= ``tier`` damage vs ``def_``.

    Consumer predicate: ``atk >= atk_cutoff``  <=>  ``damage >= tier``.
    Requires tier >= 2 (tier 1 is every hit: floor(x)+1 >= 1 always).
    """
    if tier < 2:
        raise ClosedFormError(f'tier {tier} < 2 is unconditionally reached')
    return _min_true(
        lambda a: staged_damage(move, a, def_, attacker_types,
                                defender_types, stage_atk, stage_def) >= tier,
        *bracket, what=f'atk_cutoff(tier={tier}, def_={def_})')


def def_cutoff(move, attacker_types, defender_types, tier, atk,
               stage_atk=0, stage_def=0, bracket=DEF_BRACKET):
    """MAXIMAL effective def_ still TAKING >= ``tier`` from ``atk``.

    Take-predicate: ``def_ <= def_cutoff``; DENY-predicate is the strict
    complement ``def_ > def_cutoff`` (asymmetric on purpose -- "def >=
    cutoff denies" would be wrong by one representable float).
    """
    if tier < 2:
        raise ClosedFormError(f'tier {tier} < 2 is unconditionally reached')
    return _max_true(
        lambda d: staged_damage(move, atk, d, attacker_types,
                                defender_types, stage_atk, stage_def) >= tier,
        *bracket, what=f'def_cutoff(tier={tier}, atk={atk})')


def tier_table(move, attacker_types, defender_types, def_, atk_lo, atk_hi,
               stage_atk=0, stage_def=0):
    """The move's damage-tier ladder vs one opponent def over an
    attainable effective-atk range.

    Returns rows ``{'tier': d, 'atk_cutoff': x}`` for every tier above
    the floor tier at ``atk_lo``, up to the tier at ``atk_hi``; the
    floor tier itself carries ``'atk_cutoff': None`` (held everywhere in
    range). Rows are exact: within [atk_lo, atk_hi], damage >= d iff
    atk >= that row's cutoff.
    """
    d_lo = staged_damage(move, atk_lo, def_, attacker_types, defender_types,
                         stage_atk, stage_def)
    d_hi = staged_damage(move, atk_hi, def_, attacker_types, defender_types,
                         stage_atk, stage_def)
    rows = [{'tier': d_lo, 'atk_cutoff': None}]
    for d in range(d_lo + 1, d_hi + 1):
        rows.append({'tier': d, 'atk_cutoff': atk_cutoff(
            move, attacker_types, defender_types, d, def_,
            stage_atk, stage_def)})
    return rows


def ko_cutoff(fast, charged, n_fast, n_charged, hp,
              attacker_types, defender_types, def_,
              stage_atk=0, stage_def=0, bracket=ATK_BRACKET):
    """Minimal effective atk with ``n_fast * dmg(fast) + n_charged *
    dmg(charged) >= hp`` -- the PER-SPREAD reach/deny quantity (one
    opponent (def, hp)). The "beats every plausible X" guarantee is
    ``guarantee_cutoff``, its max over a cohort -- do not print one as
    the other (the reach-card conflation the 2026-08-10 review caught).
    Callers own energy feasibility of (n_fast, n_charged): this is
    damage arithmetic only, and an energy-infeasible plan produces a
    number no battle can realize (minimal legal n_fast is
    ``ceil(n_charged * charged.energy / fast.energyGain)`` from zero
    energy).

    A sum of monotone-nondecreasing float maps is monotone, so the same
    bisection argument applies. ``n_fast=0`` / ``n_charged=0`` are
    legal (pure-fast or pure-charged plans).
    """
    if hp <= 0:
        raise ClosedFormError(f'hp={hp!r} must be positive')
    if n_fast < 0 or n_charged < 0 or (n_fast == 0 and n_charged == 0):
        raise ClosedFormError(f'need a non-empty plan, got n_fast={n_fast} '
                              f'n_charged={n_charged}')

    def total(a):
        t = 0
        if n_fast:
            t += n_fast * staged_damage(fast, a, def_, attacker_types,
                                        defender_types, stage_atk, stage_def)
        if n_charged:
            t += n_charged * staged_damage(charged, a, def_, attacker_types,
                                           defender_types, stage_atk,
                                           stage_def)
        return t

    return _min_true(lambda a: total(a) >= hp, *bracket,
                     what=f'ko_cutoff({n_fast}xfast+{n_charged}xcharged '
                          f'>= {hp} vs def {def_})')


def guarantee_cutoff(fast, charged, n_fast, n_charged,
                     attacker_types, defender_types, cohort,
                     stage_atk=0, stage_def=0):
    """max over an opponent cohort of ko_cutoff -- the "beats every
    plausible X with this plan" number -- plus the binding spread.

    ``cohort``: iv_rank-shaped entries (reads ``def_`` and ``hp``).
    Returns ``(cutoff, binding_entry)``.
    """
    if not cohort:
        raise ClosedFormError('empty cohort')
    best = None
    for entry in cohort:
        c = ko_cutoff(fast, charged, n_fast, n_charged, entry['hp'],
                      attacker_types, defender_types, entry['def_'],
                      stage_atk, stage_def)
        if best is None or c > best[0]:
            best = (c, entry)
    return best


def cmp_threshold(opp_cmp_atk, focal_shadow, bracket=ATK_BRACKET):
    """Focal effective-atk thresholds for the CMP comparison vs a fixed
    opponent ``cmp_atk`` (battle.py cmp_atk: ``atk / SHADOW_ATK_BONUS``
    when shadow, else ``atk``; the division is walked, NOT inverted
    algebraically -- ``fl(fl(x*1.2)/1.2) != x`` for ~1/3 of spreads).

    Returns ``{'win_above': a, 'tie_min': t0|None, 'tie_max': t1|None}``:
    focal cmp_atk > opponent's iff ``atk >= win_above``; the tie band
    [tie_min, tie_max] (empty = None) is the effective-atk range whose
    cmp_atk EQUALS the opponent's exactly.

    An exact tie is a THIRD state, not a focal win: the engine disables
    priority entirely (``use_priority`` False), both charged moves
    resolve in player-index order (PROP-1), and in-game it is a coin
    flip. Callers must never render the tie band as "focal wins CMP".
    NB our shadow division breaks ~30 of PvPoke's exact shadow-twin ties
    by 1 ULP (2026-08-10 audit; engine-side fix is a pending decision)
    -- this function matches OUR engine so the CMP board can never
    contradict the baked planes.
    """
    def cmp_of(a):
        return a / SHADOW_ATK_BONUS if focal_shadow else a

    win_above = _min_true(lambda a: cmp_of(a) > opp_cmp_atk, *bracket,
                          what=f'cmp win vs {opp_cmp_atk}')
    ge_above = _min_true(lambda a: cmp_of(a) >= opp_cmp_atk, *bracket,
                         what=f'cmp tie vs {opp_cmp_atk}')
    if ge_above < win_above:
        return {'win_above': win_above, 'tie_min': ge_above,
                'tie_max': math.nextafter(win_above, -math.inf)}
    return {'win_above': win_above, 'tie_min': None, 'tie_max': None}


def movable_stage_axes(focal_moves, opp_moves):
    """Which stat-stage axes this pair can move, per side.

    ``focal_moves`` / ``opp_moves``: ``(fast_dict, [charged_dicts])``.
    Returns ``((focal_atk, focal_def), (opp_atk, opp_def))`` booleans.
    Delegates to deep_dive_signature.movable_axes -- the audited exact
    superset of the engine's stage-mutation sites (buffTarget-aware
    _apply_move_buffs, the would_shield temp projection that IGNORES
    buffTarget, and native form buffs). Single-form sides only:
    form-change species are closed_form_excluded before this matters.
    """
    import deep_dive_signature as _sig

    def side(moves):
        fm, cms = moves
        return {'forms': [{'fast': fm, 'charged': list(cms)}],
                'native_atk': False, 'native_def': False}

    focal, opp = side(focal_moves), side(opp_moves)
    return _sig.movable_axes(focal, opp), _sig.movable_axes(opp, focal)
