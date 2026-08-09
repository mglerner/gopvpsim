"""Phase-1 moveset screen and the parallel Phase-2 IV sweep.

Moved verbatim out of ``scripts/deep_dive.py`` by the DRY review 2026-08-05
entry 12 split (TODO.md "Split scripts/deep_dive.py", target 5).
``deep_dive.py`` keeps a re-export shim for every name defined here, so
existing importers keep working unchanged.

LOAD-BEARING (review section G, invariant 22): ``_sweep_worker`` and
``_sweep_worker_init`` are handed to ``multiprocessing.Pool``, which pickles
them BY QUALIFIED NAME -- now ``deep_dive_lib.sweep._sweep_worker``. A
spawn-mode child therefore imports this module directly (it inherits the
parent's ``sys.path``, which carries ``scripts/``); it must stay importable
without ``deep_dive`` itself. ``tests/test_deep_dive_lib_workers.py`` pins
that with a real Pool round-trip.
"""
import math
import os
import sys
import time

from dataclasses import dataclass
from typing import NamedTuple

from gopvpsim.pokemon import (
    Pokemon, get_pokemon_entry, get_species, iv_rank, CPM, best_level,
    LEAGUE_CAPS, LEAGUE_MAX_LEVEL, cp as calc_cp,
)
from gopvpsim.moves import get_moves
from gopvpsim.data import parse_types
from gopvpsim.battle import BattlePokemon, simulate, pvpoke_dp, ENERGY_CAP
from gopvpsim.formchange import attach_form_change

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import deep_dive_analysis as analysis
import deep_dive_rendering as rendering
from deep_dive_logging import get_logger, worker_log_setup
from deep_dive_lib.opponents import (
    parse_opponent_spec, resolve_opp_ivs, variant_ivs,
)

logger = get_logger()

_pretty_name = analysis.pretty_name
parse_mode = rendering.parse_mode
parse_energy = rendering.parse_energy


def make_battle_pokemon(species, fast_id, charged_ids, league, shields,
                        atk_iv, def_iv, sta_iv, shadow=False, max_level=None):
    """Build a BattlePokemon from species + IVs + move IDs.

    Routes through BattlePokemon.from_pokemon so form-change state
    (Aegislash, Morpeko, Mimikyu) is wired up like the oracle tests
    and the scripts/battle.py CLI.

    ``max_level`` overrides the league max power-up level (best-buddy / L51);
    ``None`` = league default.
    """
    pokemon = Pokemon.at_best_level(species, atk_iv, def_iv, sta_iv,
                                    league=league, shadow=shadow,
                                    max_level=max_level)
    fast_moves, charged_moves = get_moves()
    fm = dict(fast_moves[fast_id])
    cms = [dict(charged_moves[cid]) for cid in charged_ids]
    return BattlePokemon.from_pokemon(
        pokemon, fm, cms, shields=shields,
        league_cp=LEAGUE_CAPS[league],
    )


def sim_score(focal_species, fast_id, charged_ids, league, shields_focal,
              shields_opp, atk_iv, def_iv, sta_iv, shadow,
              opp_species, opp_fast, opp_charged, opp_shadow=False,
              opp_iv_mode='pvpoke', threshold_registry=None, mechanics='legacy'):
    """Run one sim and return the focal mon's PvPoke score (0-1000)."""
    bp0 = make_battle_pokemon(focal_species, fast_id, charged_ids, league,
                              shields_focal, atk_iv, def_iv, sta_iv, shadow)

    opp_name, variant, parsed_shadow = parse_opponent_spec(opp_species)
    opp_is_shadow = opp_shadow or parsed_shadow
    variant_iv = variant_ivs(opp_name, variant, league, threshold_registry)
    if variant_iv is not None:
        oa, od, os_ = variant_iv
    else:
        oa, od, os_ = resolve_opp_ivs(opp_name, league, opp_is_shadow, opp_iv_mode)
    bp1 = make_battle_pokemon(opp_name, opp_fast, opp_charged, league,
                              shields_opp, oa, od, os_, shadow=opp_is_shadow)

    result = simulate(bp0, bp1,
                      charged_policy_0=pvpoke_dp,
                      charged_policy_1=pvpoke_dp,
                      mechanics=mechanics)
    return result.pvpoke_score(0)


def moveset_label(fast_id, charged_ids):
    """Short human-readable moveset label with pretty names."""
    fast = _pretty_name(fast_id)
    charged = ', '.join(_pretty_name(c) for c in charged_ids)
    return f"{fast} / {charged}"


def moveset_label_raw(fast_id, charged_ids):
    """Raw moveset label for internal parsing (e.g. _build_move_tuples)."""
    return f"{fast_id} / {', '.join(charged_ids)}"


# ---------------------------------------------------------------------------
# Phase 1: Quick screen
# ---------------------------------------------------------------------------

# Avg-score gap (out of 1000) within which the top moveset and the reference
# (meta) moveset are treated as a near-tie, so the reference is preferred for
# the landing page. ~1.5-2.5% of a typical pool avg -- small enough that a
# clearly-better moveset still keeps the landing.
_REF_TIE_MARGIN = 10.0


def screen_movesets(species, movesets, league, shadow, opponents, opp_movesets,
                    shield_scenarios, top_n, opp_iv_mode='pvpoke',
                    threshold_registry=None, mechanics='legacy',
                    reference_moveset=None):
    """
    Quick screen: sim rank-1 IVs for each moveset against opponents.
    Return the top N movesets by average score.

    ``reference_moveset`` is the (fast_id, charged_ids) of the PvPoke meta
    moveset, if known. When it screens within ``_REF_TIE_MARGIN`` of the
    top-scoring moveset (a near-tie), it is promoted to the front so the
    landing page defaults to the meta pick rather than an off-meta move
    that only edged ahead by sim noise + the alphabetical sort tie-break.
    (Mimikyu GL 2026-06-26: Thunder vs Play Rough screen within ~0.3 pts;
    Thunder won the landing purely on 'THUNDER' > 'PLAY_ROUGH'.)
    """
    if top_n == 0 or len(movesets) <= 1:
        # top_n==0 is the explicit "keep my order, don't screen" opt-out;
        # a single moveset has nothing to order.
        logger.info(f"  {len(movesets)} moveset(s) - skipping screen phase.")
        return movesets

    # When len(movesets) <= top_n there's nothing to *prune*, but we still
    # run the screen to ORDER the movesets by score: the landing page is
    # moveset[0], and it must be the best-scoring moveset, not whatever
    # order the pool/enumeration produced. (Shadow Sableye 2026-06-25:
    # 4 FP-pairs == top_movesets=4, so the old early-return shipped
    # Dazzling Gleam as the landing page even though Drain Punch both
    # scores higher and is the reference moveset.) scored[:top_n] keeps
    # all of them when len <= top_n.
    logger.info(f"  Phase 1: Screening {len(movesets)} movesets (rank-1 IVs, "
                f"{len(opponents)} opponents, {len(shield_scenarios)} scenario(s))...")
    t0 = time.time()

    # Use rank-1 IVs for screening
    ranked = iv_rank(species, league=league, shadow=shadow)
    r1 = ranked[0]
    a_iv, d_iv, s_iv = r1['atk_iv'], r1['def_iv'], r1['sta_iv']

    scored = []
    for fast_id, charged_ids in movesets:
        total = 0.0
        count = 0
        for opp_name, (opp_fast, opp_charged) in zip(opponents, opp_movesets):
            for s_focal, s_opp in shield_scenarios:
                score = sim_score(species, fast_id, charged_ids, league,
                                  s_focal, s_opp, a_iv, d_iv, s_iv, shadow,
                                  opp_name, opp_fast, opp_charged,
                                  opp_iv_mode=opp_iv_mode,
                                  threshold_registry=threshold_registry,
                                  mechanics=mechanics)
                total += score
                count += 1
        avg = total / count if count else 0
        scored.append((avg, fast_id, charged_ids))

    scored.sort(reverse=True)

    # Near-tie -> prefer the reference (meta) moveset for the landing slot.
    # The sort tie-breaks alphabetically by move id, which can hand the
    # landing to an off-meta move that screened within sim noise of the
    # reference. If the reference is within _REF_TIE_MARGIN of the top, move
    # it to the front so the default page is the meta pick. Keep the moveset
    # it displaced as a survivor too (even if top_n would prune it) so it
    # stays a selectable page in the dropdown.
    _keep = top_n
    if reference_moveset is not None and scored:
        _ref_key = (reference_moveset[0], tuple(sorted(reference_moveset[1])))
        _ref_pos = next(
            (i for i, (_, f, c) in enumerate(scored)
             if (f, tuple(sorted(c))) == _ref_key), None)
        if _ref_pos is not None and _ref_pos != 0:
            if scored[0][0] - scored[_ref_pos][0] <= _REF_TIE_MARGIN:
                logger.info(
                    f"  Near-tie: promoting reference moveset "
                    f"{moveset_label(scored[_ref_pos][1], scored[_ref_pos][2])} "
                    f"(avg={scored[_ref_pos][0]:.1f}) to the landing over "
                    f"{moveset_label(scored[0][1], scored[0][2])} "
                    f"(avg={scored[0][0]:.1f}); within {_REF_TIE_MARGIN} pts.")
                scored.insert(0, scored.pop(_ref_pos))
                # Keep the displaced movesets too. If the reference came from
                # OUTSIDE the original top_n, promoting it would otherwise push
                # the original #(top_n) out of the kept window -- so keep
                # top_n + 1 (all original top_n plus the reference). If it was
                # already within top_n, the set is unchanged (just reordered).
                _keep = top_n + 1 if _ref_pos >= top_n else max(top_n, 2)

    elapsed = time.time() - t0
    logger.info(f"  Screened in {elapsed:.1f}s. Top movesets:")
    for i, (avg, fast_id, charged_ids) in enumerate(scored[:_keep]):
        logger.info(f"    {i+1:3d}. {moveset_label(fast_id, charged_ids):<45s} avg={avg:.0f}")
    if len(scored) > _keep:
        logger.info(f"    ... ({len(scored) - _keep} more pruned)")

    return [(fast_id, charged_ids) for _, fast_id, charged_ids in scored[:_keep]]


# ---------------------------------------------------------------------------
# Phase 2: Full IV sweep (parallelized, deduped by stat profile)
# ---------------------------------------------------------------------------

# Worker state for multiprocessing (set via initializer, avoids pickling per call)
_worker_state = {}


def compute_iv_metadata(species, league, shadow=False, iv_floor=None,
                        focal_max_level=None):
    """
    Compute metadata for all valid IV spreads of a species/league.

    Returns list of dicts (one per valid IV) with keys:
        atk_iv, def_iv, sta_iv, level, cp, atk, def_, hp, stat_product
    The list is in canonical iteration order (a=0..15, d=0..15, s=0..15),
    skipping IVs that exceed CP cap at level 1.

    When ``iv_floor`` is a tuple ``(atk_floor, def_floor, sta_floor)``,
    any IV with ``atk<atk_floor``, ``def<def_floor``, or
    ``sta<sta_floor`` is pruned at enumeration time. This is used by
    ``deep_dive.py --species-iv-floor ATK,DEF,STA`` to trim the focal
    species' IV space for tight-league dives (e.g. UL at 13/13/13
    collapses 4096 candidates to 27).

    ``focal_max_level`` overrides the league max power-up level for this
    (focal) species only — used by the best-buddy/L51 toggle to build the
    focal one level higher WITHOUT touching opponents (who keep reading the
    global ``LEAGUE_MAX_LEVEL``). ``None`` = the league default (today's
    behavior, byte-identical).
    """
    from gopvpsim.pokemon import SHADOW_ATK_BONUS, SHADOW_DEF_MULT
    base = get_species(species)
    base_atk, base_def, base_sta = base['atk'], base['def'], base['hp']
    max_cp = LEAGUE_CAPS[league]
    if focal_max_level is None:
        focal_max_level = LEAGUE_MAX_LEVEL.get(league, 51.0)

    a_floor = d_floor = s_floor = 0
    if iv_floor is not None:
        a_floor, d_floor, s_floor = iv_floor

    # Aegislash (Blade) powers up in whole levels only; mirror the
    # rounding from Pokemon.at_best_level / iv_rank. See
    # DEVELOPER_NOTES "Form change gotchas" + S1 commit 1b6c075.
    _blade_round_down = (species == 'Aegislash (Blade)')

    iv_meta = []
    for a in range(a_floor, 16):
        for d in range(d_floor, 16):
            for s in range(s_floor, 16):
                lv = best_level(base_atk, base_def, base_sta, a, d, s,
                                max_cp=max_cp,
                                max_level=focal_max_level)
                if lv is None:
                    continue
                if _blade_round_down and lv % 1.0 != 0:
                    lv -= 0.5
                cpm = CPM[lv]
                atk_stat = (base_atk + a) * cpm
                def_stat = (base_def + d) * cpm
                if shadow:
                    atk_stat *= SHADOW_ATK_BONUS
                    def_stat *= SHADOW_DEF_MULT
                hp_stat = math.floor((base_sta + s) * cpm)
                mon_cp = calc_cp(base_atk, base_def, base_sta, a, d, s, lv)
                iv_meta.append({
                    'atk_iv': a, 'def_iv': d, 'sta_iv': s,
                    'level': lv, 'cp': mon_cp,
                    'atk': atk_stat, 'def_': def_stat, 'hp': hp_stat,
                    'stat_product': atk_stat * def_stat * hp_stat,
                })
    return iv_meta


def _stat_profile_key(meta, per_iv=False):
    """Profile key for sweep dedup. With per_iv, the key also carries
    (IVs, level) so every IV spread sims separately — required for
    form-change species, where the alt form's stats depend on the raw
    IVs and level (Blade-side whole-level rounding), not just the
    default form's effective stats."""
    key = (round(meta['atk'], 4), round(meta['def_'], 4), int(meta['hp']))
    if per_iv:
        key += (meta['atk_iv'], meta['def_iv'], meta['sta_iv'], meta['level'])
    return key


def group_ivs_by_stat_profile(iv_meta_list, per_iv=False):
    """
    Group IVs by effective (atk, def, hp) so we sim each profile once.
    With per_iv=True (form-change focal species), group per IV spread
    instead — measured cost 1.1-1.35x more sims (see _stat_profile_key).

    Returns:
        profile_to_indices: dict of profile_key -> [iv_idx, ...]
        profile_data: dict of profile_key ->
                      (atk, def, hp, atk_iv, def_iv, sta_iv, level)
                      (high-precision stats of the representative IV,
                      plus the IVs/level the worker needs to build
                      form-change state)
    """
    profile_to_indices = {}
    profile_data = {}
    for idx, meta in enumerate(iv_meta_list):
        key = _stat_profile_key(meta, per_iv)
        profile_to_indices.setdefault(key, []).append(idx)
        if key not in profile_data:
            profile_data[key] = (meta['atk'], meta['def_'], meta['hp'],
                                 meta['atk_iv'], meta['def_iv'],
                                 meta['sta_iv'], meta['level'])
    return profile_to_indices, profile_data


# ---------------------------------------------------------------------------
# Shared battle-pair construction (D10)
# ---------------------------------------------------------------------------

class BattleSide(NamedTuple):
    """One side's ingredients for ``build_battle_pair``.

    Exactly what a worker carries per (focal profile, opponent) cell: the
    effective stats it sims at, plus the raw IVs / level / gamemaster entry
    that ``attach_form_change`` needs to build the alt-form state.
    """
    species: str
    types: tuple
    atk: float
    def_: float
    hp: int
    shadow: bool
    fm_template: dict
    cms_template: list
    mon: dict               # gamemaster entry (form-change ingredients)
    ivs: tuple              # (atk_iv, def_iv, sta_iv)
    level: float
    initial_energy: int = 0


def _build_side(side, league_cp):
    bp = BattlePokemon(
        species=side.species, types=side.types,
        atk=side.atk, def_=side.def_, max_hp=side.hp,
        shadow=side.shadow,
        # Move dicts are PRIVATE per BattlePokemon (review section G,
        # invariant 1) -- copy the templates, never share them.
        fast_move=dict(side.fm_template),
        charged_moves=[dict(cm) for cm in side.cms_template],
    )
    # Energy-lead axis: reset_for_battle re-applies initial_energy before
    # every scenario, so setting it once here covers the caller's whole
    # shield-scenario loop.
    bp.initial_energy = side.initial_energy
    # Form-change state must be attached AFTER the move dicts are in place
    # (the FormData references bp's own dicts); no-op for species without a
    # formChange entry.
    attach_form_change(bp, side.mon, *side.ivs, side.level,
                       league_cp, side.shadow)
    return bp


def build_battle_pair(focal, opp, league_cp):
    """Build the (focal, opponent) BattlePokemon pair for one sim cell.

    ONE construction path for both process pools: ``_sweep_worker`` (focal
    vs a meta opponent) and ``deep_dive_slayer.slayer_iter_worker`` (focal
    vs a mirror of itself), plus ``scripts/profile_slayer.py``'s benchmark.
    They iterate DIFFERENT grids and stay separate workers on purpose (June
    review D10 / the 2026-08-05 DRY review's do-not-merge list); only this
    ~20-line core is shared, so a change to how a dive mon is built (shadow
    flags, form-change wiring, energy lead) can no longer land on one worker
    and miss the other.

    The pair is built ONCE per (profile, opponent) and the caller
    ``reset_for_battle()``s it between shield scenarios, which keeps the
    damage/DP caches warm across the scenario axis.
    """
    return _build_side(focal, league_cp), _build_side(opp, league_cp)


# Order MUST match the metric tuple the worker appends (won, hp, max_hp,
# shields). These are the extra per-cell fields the ML guide path needs
# beyond score/energy; they become cache planes of the same names.
_METRIC_NAMES = ('won', 'hp', 'max_hp', 'shields')


def _sweep_worker_init(species, focal_types, fm_template, cms_template,
                       opp_cache, shield_scenarios, focal_bait=True,
                       log_path=None, verbose=False,
                       focal_mon=None, league_cp=1500, focal_shadow=False,
                       focal_energy=0, mechanics='legacy', capture_metrics=False):
    """Initialize shared state in each sweep worker process."""
    # Spawn-mode workers (default on macOS) do not inherit the parent
    # logger's handlers; re-attach a FileHandler so any worker-side
    # log record lands in the same per-run file.
    worker_log_setup(log_path, verbose=verbose)
    _worker_state['species'] = species
    _worker_state['focal_types'] = focal_types
    _worker_state['fm_template'] = fm_template
    _worker_state['cms_template'] = cms_template
    _worker_state['opp_cache'] = opp_cache
    _worker_state['shield_scenarios'] = shield_scenarios
    _worker_state['focal_bait'] = focal_bait
    _worker_state['focal_mon'] = focal_mon
    _worker_state['league_cp'] = league_cp
    _worker_state['focal_shadow'] = focal_shadow
    _worker_state['focal_energy'] = focal_energy
    _worker_state['mechanics'] = mechanics
    _worker_state['capture_metrics'] = capture_metrics
    if focal_bait:
        _worker_state['focal_policy'] = pvpoke_dp
    else:
        import functools
        _worker_state['focal_policy'] = functools.partial(
            pvpoke_dp, bait_shields=False)


def _sweep_worker(pair_chunk):
    """
    Sim a chunk of (focal stat profile, opponent index) pairs across the
    shield-scenario axis.

    pair_chunk: list of ((profile_key, atk, def, hp, atk_iv, def_iv,
                          sta_iv, level), opp_idx) tuples.
    Returns ({(profile_key, opp_idx): [score per scenario]}, n_sims).
    """
    ws = _worker_state
    species = ws['species']
    focal_types = ws['focal_types']
    fm_template = ws['fm_template']
    cms_template = ws['cms_template']
    opp_cache = ws['opp_cache']
    shield_scenarios = ws['shield_scenarios']
    focal_policy = ws.get('focal_policy', pvpoke_dp)
    focal_mon = ws['focal_mon']
    league_cp = ws['league_cp']
    focal_shadow = ws['focal_shadow']
    focal_energy = ws.get('focal_energy', 0)
    mechanics = ws.get('mechanics', 'legacy')
    capture_metrics = ws.get('capture_metrics', False)

    # Energy is always captured: it is a free read of result.energy_remaining
    # and is persisted alongside score so --compare-energy re-dives serve warm.
    # capture_metrics additionally records (won, hp, max_hp, shields) per sim —
    # the extra per-cell fields the ML guide path needs (won_set / score_set /
    # result_metrics), so they too come from one shared sweep instead of a
    # separate sim loop. All are deterministic outputs of the same battle, so
    # the signature dedup fans them out exactly like score/energy.
    results = {}
    energy_results = {}
    metrics_results = {}
    n_sims = 0
    for (profile_key, atk_stat, def_stat, hp_stat, a_iv, d_iv, s_iv, lv), oi in pair_chunk:
        opp = opp_cache[oi]
        # One BattlePokemon pair per (profile, opponent), reset between
        # scenarios — keeps the damage/DP caches warm across the
        # shield-scenario axis instead of rebuilding them per sim.
        bp0, bp1 = build_battle_pair(
            BattleSide(species, focal_types, atk_stat, def_stat, hp_stat,
                       focal_shadow, fm_template, cms_template,
                       focal_mon, (a_iv, d_iv, s_iv), lv, focal_energy),
            BattleSide(opp['species'], opp['types'], opp['atk'], opp['def_'],
                       opp['hp'], opp['shadow'], opp['fm'], opp['cms'],
                       opp['mon'], opp['ivs'], opp['level']),
            league_cp)
        scores = []
        energies = []
        metrics = [] if capture_metrics else None
        for s_focal, s_opp in shield_scenarios:
            bp0.reset_for_battle(s_focal, opponent=bp1)
            bp1.reset_for_battle(s_opp, opponent=bp0)
            result = simulate(bp0, bp1,
                              charged_policy_0=focal_policy,
                              charged_policy_1=pvpoke_dp,
                              mechanics=mechanics)
            sc0 = result.pvpoke_score(0)
            scores.append(sc0)
            # Focal's leftover energy (0..100) at battle end -- the post-match
            # state for the compare widget's "banks N charged moves" line.
            energies.append(result.energy_remaining[0])
            if capture_metrics:
                metrics.append((
                    sc0 > result.pvpoke_score(1),       # won
                    max(0, result.hp_remaining[0]),     # hp
                    result.max_hp[0],                   # max_hp
                    result.shields_remaining[0],        # shields
                ))
            n_sims += 1
        results[(profile_key, oi)] = scores
        energy_results[(profile_key, oi)] = energies
        if capture_metrics:
            metrics_results[(profile_key, oi)] = metrics
    return results, energy_results, metrics_results, n_sims


@dataclass
class SweepConfig:
    """The run-wide ``iv_sweep`` knobs, resolved once per dive (D9).

    Everything here is CONSTANT across a dive's sweeps -- only the focal
    moveset, the composite opp-IV mode, and the two opt-in axes
    (``capture_energy`` / ``focal_max_level``) vary between the calls
    ``deep_dive.main`` makes. Before this, the same eight lines were
    hand-typed at five call sites (Phase 2, the extra composite modes, the
    reference sweep, the base-form census, the best-buddy pass), so adding a
    knob meant editing five argument lists and any miss was silent (commit
    06bedca is the worked example).

    Defaults MIRROR ``iv_sweep``'s own defaults, so an omitted field passes
    through unchanged.
    """
    iv_floor: tuple = None
    log_path: str = None
    verbose: bool = False
    threshold_registry: object = None
    reserve_cpus: int = 0
    signature_dedup: bool = True
    use_sweep_cache: bool = False
    mechanics: str = 'legacy'

    @classmethod
    def from_args(cls, args, log_path=None, threshold_registry=None):
        """Build from the deep_dive CLI namespace. The two negated flags
        (``--no-signature-dedup`` / ``--no-sweep-cache``) are inverted HERE,
        once, instead of at every call site."""
        return cls(
            iv_floor=args.iv_floor,
            log_path=log_path,
            verbose=args.verbose,
            threshold_registry=threshold_registry,
            reserve_cpus=args.reserve_cpus,
            signature_dedup=not args.no_signature_dedup,
            use_sweep_cache=not args.no_sweep_cache,
            mechanics=args.mechanics,
        )

    def as_kwargs(self):
        """Pass-through kwargs for ``iv_sweep``: ``iv_sweep(..., **cfg.as_kwargs())``.

        NOT ``dataclasses.asdict`` -- that deep-copies, and
        ``threshold_registry`` must reach the sweep as the SAME object.
        """
        return dict(self.__dict__)


def iv_sweep(species, fast_id, charged_ids, league, shadow,
             opponents, opp_movesets, shield_scenarios, opp_iv_mode='pvpoke',
             iv_floor=None, log_path=None, verbose=False,
             threshold_registry=None, reserve_cpus=0, signature_dedup=True,
             use_sweep_cache=False, mechanics='legacy',
             focal_max_level=None, opp_max_level=None, capture_energy=False,
             capture_metrics=False):
    """
    Sim all 4096 IV spreads for one moveset against all opponents.
    Parallelized across focal stat profiles (deduped by atk/def/hp) using
    multiprocessing - IVs with identical effective stats produce identical
    battles, so we sim each profile once and copy the result to all
    matching IVs (~1.7x speedup).

    With ``signature_dedup`` (default), profiles are further grouped
    per-opponent by damage signature (see deep_dive_signature.py):
    profiles whose damage tables, CMP sign, and HP all match vs a given
    opponent fight bit-identical battles, so one representative sim per
    (signature, opponent) covers the whole group. Provably exact;
    ``--no-signature-dedup`` / signature_dedup=False restores the
    per-profile path (used by the verification script and tests).

    With ``use_sweep_cache``, per-opponent score columns are persisted
    to disk (see scripts/sweep_cache.py) and opponents whose column key
    hits are skipped entirely — an unchanged dive command re-runs
    all-hits, a pool edit sims only the new/changed columns. Off by
    default so library callers and tests always sim; the deep_dive CLI
    turns it on unless --no-sweep-cache is passed.

    opp_iv_mode may be a composite mode string encoding bait-shields and
    energy-lead axes:
      'pvpoke', 'rank1'        - bait-on (default pvpoke_dp behavior)
      'pvpoke:nobait', 'rank1:nobait'
                                - bait-off (pvpoke_dp bait_shields=False)
      'pvpoke:e1', 'pvpoke:nobait:e2'
                                - focal starts with 1 (2) fast moves of
                                  stored energy (safe-switch / closer
                                  carry-over). Raw energy = N x the
                                  moveset's fast energyGain, capped at
                                  (100 - cheapest charged cost) since
                                  higher leads are unreachable in play
                                  (the charged move would already have
                                  been thrown). Opponent always starts
                                  at 0.
    When the ``:nobait`` suffix is present, the focal uses a no-bait policy;
    the opponent still baits normally.

    ``focal_max_level`` raises ONLY the focal species' max power-up level
    (best-buddy/L51 toggle); opponents keep their league default unless
    ``opp_max_level`` is also set (the opponent over-level seam — e.g. an ML
    sweep, or a niche meta where everyone runs a best-buddied opponent). Both
    default ``None`` = league default (today's behavior).

    ``capture_energy`` (opt-in) also records the focal's post-match energy per
    (IV, scenario, opponent) -- the 5th return ``canonical_energy`` (parallel to
    ``canonical_scores``); it is ``None`` otherwise. Capturing forces the disk
    cache off (the cache stores only the score column).

    Returns (results, n_sims, canonical_scores, canonical_meta, canonical_energy)
    where results is one dict per IV, sorted by avg_score desc, and
    canonical_energy is None unless ``capture_energy``.
    """
    # Split composite mode into opponent-IV, bait, and energy-lead axes.
    opp_iv_mode_simple, bait_mode = parse_mode(opp_iv_mode)
    focal_bait = (bait_mode == 'bait')
    energy_mult = parse_energy(opp_iv_mode)
    import multiprocessing

    fast_moves_db, charged_moves_db = get_moves()

    # Raise-on-miss, as the bare next() here always did -- an unknown focal
    # is a caller bug, not something this sweep should paper over.
    focal_mon = get_pokemon_entry(species)
    focal_types = parse_types(focal_mon)
    fm_template = dict(fast_moves_db[fast_id])
    cms_template = [dict(charged_moves_db[cid]) for cid in charged_ids]

    # Energy-lead in raw energy points: fast-move multiples from the
    # mode string x this moveset's energy gain, capped at the highest
    # reachable carry-over (you'd have thrown the cheapest charged
    # move before exceeding it).
    focal_energy = 0
    if energy_mult:
        _eg = fm_template.get('energyGain', 0)
        _cap = ENERGY_CAP - min(cm['energy'] for cm in cms_template)
        focal_energy = min(energy_mult * _eg, max(0, _cap))

    # Cache opponent stats (BattlePokemon is mutated by simulate, but stats are fixed)
    opp_cache = []
    for opp_name, (opp_fast, opp_charged) in zip(opponents, opp_movesets):
        opp_clean, variant, opp_is_shadow = parse_opponent_spec(opp_name)
        variant_iv = variant_ivs(opp_clean, variant, league, threshold_registry)
        if variant_iv is not None:
            oa, od, os_ = variant_iv
        else:
            oa, od, os_ = resolve_opp_ivs(opp_clean, league, opp_is_shadow, opp_iv_mode_simple)
        opp_pokemon = Pokemon.at_best_level(opp_clean, oa, od, os_,
                                            league=league, shadow=opp_is_shadow,
                                            max_level=opp_max_level)
        opp_mon = get_pokemon_entry(opp_clean)
        opp_types = parse_types(opp_mon)
        opp_fm = dict(fast_moves_db[opp_fast])
        opp_cms = [dict(charged_moves_db[cid]) for cid in opp_charged]
        opp_cache.append({
            'species': opp_clean, 'types': opp_types,
            'atk': opp_pokemon.atk, 'def_': opp_pokemon.def_,
            'hp': opp_pokemon.hp, 'fm': opp_fm, 'cms': opp_cms,
            'shadow': opp_is_shadow,
            # Form-change ingredients (worker calls attach_form_change;
            # no-op for species without a formChange entry).
            'mon': opp_mon, 'ivs': (oa, od, os_),
            'level': opp_pokemon.level,
            # Sweep-cache column key ingredients (resolved move IDs;
            # display-name differences with identical resolution
            # correctly share a column).
            'fast_id': opp_fast, 'charged_ids': list(opp_charged),
        })

    # Pre-compute IV metadata and group by stat profile (focal-side dedup).
    # Form-change species group per IV spread instead: the alt form's
    # stats depend on raw IVs + level, so identical default-form stats
    # do NOT imply identical battles (see _stat_profile_key).
    focal_per_iv = focal_mon.get('formChange') is not None
    iv_meta = compute_iv_metadata(species, league, shadow=shadow,
                                  iv_floor=iv_floor,
                                  focal_max_level=focal_max_level)
    # Effective focal level cap for cache keying. ``focal_max_level`` covers the
    # best-buddy path; the legacy ``--max-level`` flag instead mutates the
    # global LEAGUE_MAX_LEVEL in place (and does NOT pass focal_max_level), so
    # key on the resolved cap to keep an L50 and L51 sweep distinct regardless
    # of which path raised the focal level.
    _eff_focal_cap = (focal_max_level if focal_max_level is not None
                      else LEAGUE_MAX_LEVEL.get(league, 51.0))
    profile_to_indices, profile_data = group_ivs_by_stat_profile(
        iv_meta, per_iv=focal_per_iv)
    profile_list = [(pk, *dat) for pk, dat in profile_data.items()]

    # Sweep disk cache: load per-opponent score columns from previous
    # runs (see scripts/sweep_cache.py); only cache-miss opponents get
    # simmed below. Columns store post-fan-out per-IV float64 scores in
    # canonical iv_meta order, so hits are bit-identical to a fresh sim.
    n_ivs_total = len(iv_meta)
    sweep_cache = None
    cached_cols = {}  # oi -> {'score': ndarray, 'energy': ndarray}
    # The sweep cache key (sweep_cache.focal_key_fields) does NOT include the
    # turn-mechanics model, so a 'new'-mechanics run would collide with any
    # legacy-cached columns. The 'new' model is experimental; disable the
    # persistent cache for it rather than widen the cache-key schema (which
    # CLAUDE.md flags as coordination-sensitive).
    if mechanics != 'legacy':
        use_sweep_cache = False
    # Energy is now always captured + stored in the column (v5), so
    # capture_energy no longer bypasses the cache — a --compare-energy re-dive
    # serves warm. capture_energy only gates whether energy is exposed on the
    # returned results.
    # Planes a column must carry to count as a hit. Dives keep score+energy;
    # the ML guide path also caches the (won, hp, max_hp, shields) metric
    # planes (_METRIC_NAMES) so its warm re-bake re-sims nothing.
    req_planes = (('score', 'energy') + _METRIC_NAMES if capture_metrics
                  else ('score', 'energy'))
    if use_sweep_cache:
        import sweep_cache as swc
        sweep_cache = swc.SweepCache(swc.focal_key_fields(
            species, league, shadow, fast_id, charged_ids,
            iv_floor, shield_scenarios, bait_mode,
            energy_lead=focal_energy, focal_max_level=_eff_focal_cap))
        for oi, opp in enumerate(opp_cache):
            col = sweep_cache.get_column(
                swc.column_key_fields(opp['species'], opp['shadow'],
                                      opp['ivs'], opp['level'],
                                      opp['fast_id'], opp['charged_ids']),
                n_ivs_total, len(shield_scenarios),
                required_planes=req_planes)
            if col is not None:
                cached_cols[oi] = col
        if cached_cols:
            logger.info(f"      sweep cache: {len(cached_cols)}/"
                        f"{len(opp_cache)} opponent columns hit")
    missing_ois = [oi for oi in range(len(opp_cache))
                   if oi not in cached_cols]

    # Signature dedup: per opponent, group profiles whose battles are
    # provably bit-identical (same damage tables both ways, same CMP
    # sign, same HP — see deep_dive_signature.py) and sim one
    # representative per group.
    n_profiles = len(profile_list)
    if signature_dedup and missing_ois:
        import deep_dive_signature as sig
        focal_side = sig.build_focal_side(
            focal_mon, focal_types, fm_template, cms_template,
            profile_list, LEAGUE_CAPS[league], shadow)
        groups_by_opp = {
            oi: sig.signature_groups(
                focal_side,
                sig.build_opp_side(opp_cache[oi], LEAGUE_CAPS[league]))
            for oi in missing_ois
        }
    else:
        trivial = [(pos, [pos]) for pos in range(n_profiles)]
        groups_by_opp = {oi: trivial for oi in missing_ois}

    pair_list = [(profile_list[rep_pos], oi)
                 for oi, groups in groups_by_opp.items()
                 for rep_pos, _members in groups]
    total_pairs = n_profiles * len(missing_ois)
    if signature_dedup and pair_list:
        logger.info(f"      signature dedup: {n_profiles} profiles x "
                    f"{len(missing_ois)} opponents -> {len(pair_list)} "
                    f"representative pairs "
                    f"({total_pairs / len(pair_list):.2f}x)")

    # Parallel sim: ~100 chunks across the worker pool. imap_unordered
    # hands chunks out as workers free up - finer granularity gives more
    # frequent progress reports and better load balancing.
    n_chunks_target = 100
    chunk_size = max(1, (len(pair_list) + n_chunks_target - 1) // n_chunks_target)
    chunks = [pair_list[i:i+chunk_size] for i in range(0, len(pair_list), chunk_size)]
    # Worker count is (cores - reserve), capped by the number of chunks so we
    # never spawn idle workers (each would only cost an extra opp_cache copy).
    # --reserve-cpus is the knob for leaving cores free. (The old ceiling was a
    # literal 16, a vestigial holdover from the original 16-atk_iv-chunk
    # partitioning; the sweep is now ~100 chunks, so 16 needlessly capped
    # >16-core hosts.) Only used when `chunks` is non-empty (guarded below).
    n_workers = min(max(1, multiprocessing.cpu_count() - reserve_cpus), len(chunks))

    import time as _time
    sim_start = _time.time()
    chunk_results = []
    if chunks:  # all-columns-hit sweeps skip the pool entirely
        with multiprocessing.Pool(
            processes=n_workers,
            initializer=_sweep_worker_init,
            initargs=(species, focal_types, fm_template, cms_template,
                      opp_cache, shield_scenarios, focal_bait,
                      log_path, verbose,
                      focal_mon, LEAGUE_CAPS[league], shadow,
                      focal_energy, mechanics, capture_metrics),
        ) as pool:
            last_print = sim_start
            completed = 0
            for result in pool.imap_unordered(_sweep_worker, chunks):
                chunk_results.append(result)
                completed += 1
                now = _time.time()
                if now - last_print >= 10 and completed < len(chunks):
                    elapsed = now - sim_start
                    frac = completed / len(chunks)
                    eta = (elapsed / frac) * (1 - frac)
                    logger.info(f"      progress: {completed}/{len(chunks)} chunks "
                                f"({frac*100:.0f}%), eta {eta:.0f}s")
                    last_print = now

    # Merge pair results, then fan each representative's scores out to
    # every profile in its signature group. Energy is always present (the
    # worker always returns it); whether it reaches the caller is gated by
    # capture_energy at the end.
    pair_scores = {}
    pair_energy = {}
    pair_metrics = {}
    n_sims = 0
    for pair_res, pair_en, pair_met, chunk_sims in chunk_results:
        pair_scores.update(pair_res)
        pair_energy.update(pair_en)
        pair_metrics.update(pair_met)
        n_sims += chunk_sims

    profile_per_opp = {}
    profile_energy_per_opp = {}
    # profile_metrics_per_opp[pk][(si, oi)] = (won, hp, max_hp, shields),
    # in _METRIC_NAMES order. Only populated when capture_metrics.
    profile_metrics_per_opp = {}
    for oi, groups in groups_by_opp.items():
        for rep_pos, members in groups:
            rep_key = (profile_list[rep_pos][0], oi)
            scores = pair_scores[rep_key]
            energies = pair_energy[rep_key]
            metrics = pair_metrics.get(rep_key)
            for pos in members:
                pk = profile_list[pos][0]
                per_opp = profile_per_opp.setdefault(pk, {})
                e_per_opp = profile_energy_per_opp.setdefault(pk, {})
                for si, sc in enumerate(scores):
                    per_opp[(si, oi)] = sc
                for si, en in enumerate(energies):
                    e_per_opp[(si, oi)] = en
                if metrics is not None:
                    m_per_opp = profile_metrics_per_opp.setdefault(pk, {})
                    for si, mt in enumerate(metrics):
                        m_per_opp[(si, oi)] = mt

    # Fill cache-hit columns: all IVs in a profile share effective
    # stats, hence identical battles, so the profile's first IV index
    # reads the stored per-IV column exactly.
    iv_idx_by_profile = None
    if cached_cols:
        iv_idx_by_profile = {pk: idxs[0]
                             for pk, idxs in profile_to_indices.items()}
        for oi, planes in cached_cols.items():
            score_col = planes['score']
            energy_col = planes['energy']
            metric_cols = ([planes[m] for m in _METRIC_NAMES]
                           if capture_metrics else None)
            for pk, rep_idx in iv_idx_by_profile.items():
                per_opp = profile_per_opp.setdefault(pk, {})
                e_per_opp = profile_energy_per_opp.setdefault(pk, {})
                m_per_opp = (profile_metrics_per_opp.setdefault(pk, {})
                             if capture_metrics else None)
                for si in range(len(shield_scenarios)):
                    per_opp[(si, oi)] = float(score_col[rep_idx, si])
                    e_per_opp[(si, oi)] = int(energy_col[rep_idx, si])
                    if m_per_opp is not None:
                        m_per_opp[(si, oi)] = tuple(
                            int(mc[rep_idx, si]) for mc in metric_cols)

    # Persist freshly simmed columns (expanded to per-IV order): score +
    # energy planes always, plus the metric planes when captured.
    if sweep_cache is not None and missing_ois:
        import numpy as _np
        import sweep_cache as swc
        n_sc = len(shield_scenarios)
        for oi in missing_ois:
            opp = opp_cache[oi]
            score_col = _np.empty((n_ivs_total, n_sc), dtype=_np.float64)
            energy_col = _np.empty((n_ivs_total, n_sc), dtype=_np.float64)
            metric_planes = ({m: _np.empty((n_ivs_total, n_sc),
                                           dtype=_np.float64)
                              for m in _METRIC_NAMES} if capture_metrics
                             else {})
            for pk, idxs in profile_to_indices.items():
                score_col[idxs, :] = [profile_per_opp[pk][(si, oi)]
                                      for si in range(n_sc)]
                energy_col[idxs, :] = [profile_energy_per_opp[pk][(si, oi)]
                                       for si in range(n_sc)]
                for mi, m in enumerate(_METRIC_NAMES):
                    if capture_metrics:
                        metric_planes[m][idxs, :] = [
                            profile_metrics_per_opp[pk][(si, oi)][mi]
                            for si in range(n_sc)]
            sweep_cache.put_column(
                swc.column_key_fields(opp['species'], opp['shadow'],
                                      opp['ivs'], opp['level'],
                                      opp['fast_id'], opp['charged_ids']),
                {'score': score_col, 'energy': energy_col, **metric_planes})

    # Build per-IV results by expanding profile sims to all matching IVs.
    # The list is built in canonical iteration order (matches iv_meta order).
    n_scenarios = len(shield_scenarios)
    n_opponents = len(opp_cache)
    results = []
    for idx, meta in enumerate(iv_meta):
        pk = _stat_profile_key(meta, per_iv=focal_per_iv)
        per_opp = profile_per_opp[pk]
        # Compute avg_score for this IV (same for all IVs sharing the
        # profile). Sum in canonical (si, oi) order, not dict insertion
        # order: with the sweep cache, insertion order depends on which
        # columns were hits, and float accumulation order must not.
        total_score = sum(per_opp[(si, oi)]
                          for si in range(n_scenarios)
                          for oi in range(n_opponents))
        count = len(per_opp)
        avg_score = total_score / count if count else 0
        result = dict(meta)  # copy a, d, s, level, cp, atk, def_, hp, stat_product
        result['avg_score'] = avg_score
        result['per_opp'] = per_opp
        if capture_energy:
            result['per_opp_energy'] = profile_energy_per_opp[pk]
        if capture_metrics:
            # Split the (won, hp, max_hp, shields) tuples into one per_opp_<m>
            # dict per metric, so the ML grid-views index each field directly.
            m_per_opp = profile_metrics_per_opp[pk]
            for mi, m in enumerate(_METRIC_NAMES):
                result['per_opp_' + m] = {k: v[mi] for k, v in m_per_opp.items()}
        results.append(result)

    # Build canonical-order score array (in iv_meta order, same as results list)
    canonical_scores = []
    canonical_energy = [] if capture_energy else None
    canonical_meta = []  # [(a,d,s, lv, cp, atk, def_, hp), ...]
    for r in results:
        canonical_meta.append((
            r['atk_iv'], r['def_iv'], r['sta_iv'],
            r['level'], r['cp'],
            r['atk'], r['def_'], r['hp'],
        ))
        for si in range(n_scenarios):
            for oi in range(n_opponents):
                canonical_scores.append(round(r['per_opp'][(si, oi)]))
                if capture_energy:
                    canonical_energy.append(round(r['per_opp_energy'][(si, oi)]))

    # Now sort and rank
    results.sort(key=lambda r: r['avg_score'], reverse=True)
    for i, r in enumerate(results):
        r['battle_rank'] = i + 1

    # Same rank convention as gopvpsim.pokemon.iv_rank / deep_dive's
    # sp_rank_array: unrounded stat product descending, IV sum descending
    # as the tiebreak (PvPoke's convention). Feeds the CLI summary table.
    # The trailing -a/-d/-s components settle FULL ties (identical stat
    # product AND IV sum, which are common) in ascending a/d/s order, i.e.
    # iv_rank's enumeration order -- without them the ranks of tied rows
    # would inherit the avg_score sort applied just above.
    by_sp = sorted(results,
                   key=lambda r: (r['stat_product'],
                                  r['atk_iv'] + r['def_iv'] + r['sta_iv'],
                                  -r['atk_iv'], -r['def_iv'], -r['sta_iv']),
                   reverse=True)
    for i, r in enumerate(by_sp):
        r['sp_rank'] = i + 1

    return results, n_sims, canonical_scores, canonical_meta, canonical_energy
