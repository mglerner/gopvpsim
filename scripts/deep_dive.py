#!/usr/bin/env python
"""
IV deep dive: sim all 4096 IV spreads of a focal species against meta opponents.

The user can specify as much or as little of the focal mon's moveset as they want:
  - Full moveset (fast + 2 charged): use exactly that.
  - Fast move only: try all legal charged move pairs.
  - One charged move: try all legal fast moves × all partners for the other slot.
  - Nothing: try all legal moveset combinations.

Opponents can come from:
  - Top N of PvPoke rankings (default)
  - A PvPoke custom group (--group championshipseries)

Two-phase approach:
  Phase 1: Quick screen - sim rank-1 IVs in 1v1 shields against a few opponents
           to prune hopeless movesets down to the top N.
  Phase 2: Full 4096-IV sweep for surviving movesets across all opponents.

Usage:
    python scripts/deep_dive.py <species> [--fast FAST] [--charged MOVE1[,MOVE2]]
                                [--league great|ultra|master]
                                [--opponents N] [--top-movesets N]
                                [--shield-scenario S1,S2]
                                [--shadow]
                                [--group NAME]
                                [--thresholds FILE.json]
                                [--html output.html]

Examples:
    # Full auto: try all movesets, top 20 opponents
    python scripts/deep_dive.py Medicham

    # Tinkaton with upcoming Gigaton Hammer vs Championship Series meta
    python scripts/deep_dive.py Tinkaton --fast FAIRY_WIND \\
        --charged GIGATON_HAMMER,PLAY_ROUGH \\
        --group championshipseries --thresholds thresholds/tinkaton.json \\
        --html tinkaton_gh.html

    # Interactive HTML output
    python scripts/deep_dive.py Medicham --fast COUNTER --charged DYNAMIC_PUNCH,ICE_PUNCH \\
        --html med.html
"""
import argparse
import itertools
import json
import math
import os
from pathlib import Path
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.pokemon import (
    Pokemon, get_pokemon_entry, get_species, iv_rank, CPM, best_level,
    LEAGUE_CAPS, LEAGUE_MAX_LEVEL, cp as calc_cp, pvpoke_default_ivs,
)
from gopvpsim.moves import get_moves, type_effectiveness, stab
from gopvpsim.data import (
    load_gamemaster, load_rankings, get_default_moveset, parse_types,
    load_group as fetch_group,
)
from gopvpsim.battle import (
    BattlePokemon, simulate,
    pvpoke_dp, pvpoke_simulate_shield,
)
from gopvpsim.thresholds import (
    ThresholdRegistry, load_file as load_threshold_file, as_legacy_dict,
)
from gopvpsim.anchors import (
    resolve_anchors, tag_iv, ResolvedAnchor, build_auto_anchors,
    derive_short_name,
)
sys.path.insert(0, os.path.dirname(__file__))
import deep_dive_analysis as analysis
import deep_dive_rendering as rendering
import deep_dive_slayer as slayer
from deep_dive_logging import (
    init_logger, worker_log_setup, get_logger,
)

logger = get_logger()

# ---------------------------------------------------------------------------
# PvPoke custom group loading (via cached fetch from GitHub)
# ---------------------------------------------------------------------------

# Known PvPoke custom groups (from pvpoke/src/data/groups/).
# This list is for --help display; any name can be tried at runtime.
KNOWN_GROUPS = [
    'battlefrontiermaster', 'bayou', 'bfretro', 'catch', 'championshipseries',
    'chrono', 'electric', 'equinox', 'fantasy', 'great', 'jungle',
    'laic2025remix', 'little', 'littlegeneral', 'maelstrom', 'master', 'mega',
    'premiermaster', 'premierultra', 'remix', 'retro', 'spellcraft', 'spring',
    'ultra',
]


def _build_species_id_to_name():
    """Build a mapping from PvPoke speciesId -> speciesName."""
    gm = load_gamemaster()
    return {m['speciesId']: m['speciesName'] for m in gm['pokemon']}


def load_group(group_name):
    """
    Load a PvPoke custom group (fetched from GitHub, cached locally) and
    return list of (speciesName, fast_move_id, [charged_move_ids], is_shadow).
    """
    entries = fetch_group(group_name)

    id_to_name = _build_species_id_to_name()
    result = []
    skipped = []
    for entry in entries:
        sid = entry['speciesId']
        is_shadow = entry.get('shadowType') == 'shadow'
        if sid not in id_to_name:
            base_sid = sid.replace('_shadow', '')
            if base_sid + '_shadow' in id_to_name:
                sid = base_sid + '_shadow'
            elif base_sid in id_to_name and is_shadow:
                sid = base_sid
            else:
                skipped.append(entry['speciesId'])
                continue

        species_name = id_to_name[sid]
        fast_move = entry['fastMove']
        charged_moves = entry['chargedMoves']
        result.append((species_name, fast_move, charged_moves, is_shadow))

    if skipped:
        logger.warning(f"skipped {len(skipped)} group entries not in gamemaster: "
                       f"{', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''}")

    return result


# ---------------------------------------------------------------------------
# Threshold loading and classification
# ---------------------------------------------------------------------------

def load_thresholds(path):
    """
    Load thresholds from a JSON file.

    Format:
        {
            "GH Great": {"attack": 0, "defense": 143.03, "stamina": 138},
            "GH Good":  {"attack": 0, "defense": 141.66, "stamina": 138}
        }

    Thresholds should be ordered from most restrictive to least restrictive.
    A value of 0 means "don't care" for that stat.
    """
    with open(path) as f:
        data = json.load(f)
    # Validate structure
    for name, thresh in data.items():
        for key in ('attack', 'defense', 'stamina'):
            if key not in thresh:
                sys.exit(f"Threshold {name!r} missing required key {key!r}")
    return data


discover_slayer_thresholds = slayer.discover_slayer_thresholds


_slayer_worker_init = slayer.slayer_worker_init


_slayer_iter_worker = slayer.slayer_iter_worker


_build_focal_meta = slayer.build_focal_meta


iterative_slayer_discovery = slayer.iterative_slayer_discovery


categorize_slayers = slayer.categorize_slayers

IVCategory = rendering.IVCategory
parse_mode = rendering.parse_mode
compose_mode = rendering.compose_mode
mode_pretty_label = rendering.mode_pretty_label


def build_iv_categories(data_obj, slayer_categories=None,
                        iv_idx_by_triple=None, matchup_data=None):
    """Build the unified ``list[IVCategory]`` for a deep-dive run.

    Inputs:
        data_obj: the JS-bound data object (already populated with tiers,
            ivAllTiers, ivAtk/ivDef/ivHp, nIvs, ivA/ivD/ivS).
        slayer_categories: dict from ``categorize_slayers``. May be None
            if the run didn't include slayer iteration; in that case the
            slayer-kind branch is skipped.
        iv_idx_by_triple: optional precomputed (atk_iv, def_iv, sta_iv)
            -> canonical-index map. Built from data_obj if not given.
        matchup_data: optional dict enabling kind='matchup' categories.
            Shape:
                {
                  'scores_flat': flat list, len = nIvs * nS * nO,
                  'nS': int, 'nO': int,
                  'scenarios': [(focal_shields, opp_shields), ...],
                  'opponents': [opp_name, ...],
                  'opp_iv_mode': 'pvpoke' or 'rank1',
                  'win_threshold': float (default 500),
                }
            Each (opponent, scenario) pair becomes a candidate category;
            non-trivial partitions (1 <= winners < nIvs) are emitted.
            If None, the matchup branch is skipped.

    Output: list of IVCategory in stable order: slayer categories first,
    then tier categories, then composites, then matchups. Empty
    categories are dropped.

    The function is intentionally pure - no I/O, no HTML, no globals.
    Easy to unit-test with synthetic data_obj dicts.
    """
    n_ivs = data_obj.get('nIvs', 0)
    if n_ivs == 0:
        return []

    if iv_idx_by_triple is None:
        iv_a = data_obj.get('ivA', [])
        iv_d = data_obj.get('ivD', [])
        iv_s = data_obj.get('ivS', [])
        iv_idx_by_triple = {(iv_a[i], iv_d[i], iv_s[i]): i
                            for i in range(n_ivs)}

    categories: list = []

    # ---- Slayer categories ----
    # Iterate categorize_slayers output and lift each non-empty bucket
    # into an IVCategory. The slayer survivors carry the rich
    # _anchor_tags dict that we want to preserve as member_meta so the
    # renderer can show which specific anchors fired per IV.
    if slayer_categories:
        SLAYER_KIND_DESC = {
            'Atk Slayer': 'IVs that clear at least one named damage '
                          'breakpoint anchor against a notable opponent.',
            'Bulk Slayer': 'IVs at or above the survivor-pool HP+def median, '
                           'or that clear at least one named bulkpoint anchor.',
            'CMP Slayer': 'IVs whose raw attack beats at least one named '
                          'CMP cohort, winning Charge Move Priority ties.',
        }
        for cat_name, survivors in slayer_categories.items():
            if not survivors:
                continue
            members = []
            member_meta: dict = {}
            anchor_set: set = set()
            anchor_objs: list = []
            for r in survivors:
                triple = tuple(r.get('iv', ()))
                idx = iv_idx_by_triple.get(triple)
                if idx is None:
                    continue
                members.append(idx)
                tags = r.get('_anchor_tags', {}) or {}
                for parent_name, sublist in tags.items():
                    anchor_set.add(parent_name)
                    anchor_objs.extend(sublist)
                member_meta[idx] = {
                    'iv': triple,
                    'total_wins': r.get('total_wins', 0),
                    'avg_score': r.get('avg_score', 0.0),
                    'anchor_tags': tags,
                }
            if not members:
                continue
            members.sort()
            categories.append(IVCategory(
                name=cat_name,
                kind='slayer',
                members=members,
                description=SLAYER_KIND_DESC.get(cat_name, ''),
                source_anchors=sorted(anchor_set),
                stat_cutoffs=_stat_cutoffs_from_anchors(anchor_objs),
                member_meta=member_meta,
            ))

    # ---- Threshold tier categories ----
    # data_obj['tiers'] is the ordered list of tier dicts; ivAllTiers[i]
    # is the list of tier indices that IV i meets (inclusive - an IV
    # that's "Top 5%" also lives in "Good"). We use ivAllTiers, not the
    # primary ivTiers, because we want category membership to be
    # inclusive across the tier ladder.
    tiers = data_obj.get('tiers') or []
    iv_all_tiers = data_obj.get('ivAllTiers') or []
    iv_a = data_obj.get('ivA', [])
    iv_d = data_obj.get('ivD', [])
    iv_s = data_obj.get('ivS', [])
    for ti, tier in enumerate(tiers):
        members = [i for i in range(n_ivs)
                   if i < len(iv_all_tiers) and ti in iv_all_tiers[i]]
        if not members:
            continue
        atk_cut = tier.get('attack', 0) or None
        def_cut = tier.get('defense', 0) or None
        hp_cut = tier.get('stamina', 0) or None
        member_meta = {
            i: {'iv': (iv_a[i], iv_d[i], iv_s[i]) if i < len(iv_a) else None}
            for i in members
        }
        categories.append(IVCategory(
            name=tier['name'],
            kind='tier',
            members=members,
            description=tier.get('desc', ''),
            source_tier=tier['name'],
            stat_cutoffs={'atk': atk_cut, 'def': def_cut, 'hp': hp_cut},
            member_meta=member_meta,
        ))

    # ---- Composite categories: slayer ∩ tier ----
    # Round one uses literal-intersection naming. The composite_meta
    # entries inherit from both parents so the renderer can show, e.g.,
    # "Atk Slayer member with mirror wins 45/132, also clears Top 5%
    # (HP≥139)".
    slayer_cats = [c for c in categories if c.kind == 'slayer']
    tier_cats = [c for c in categories if c.kind == 'tier']
    for slayer in slayer_cats:
        slayer_set = set(slayer.members)
        for tier in tier_cats:
            inter = sorted(slayer_set & set(tier.members))
            if not inter:
                continue
            comp_meta: dict = {}
            for idx in inter:
                merged = {}
                if idx in slayer.member_meta:
                    merged.update(slayer.member_meta[idx])
                if idx in tier.member_meta:
                    # Don't clobber the slayer 'iv' with the tier one;
                    # they should match anyway.
                    for k, v in tier.member_meta[idx].items():
                        merged.setdefault(k, v)
                comp_meta[idx] = merged
            categories.append(IVCategory(
                name=f'{slayer.name} ∩ {tier.name}',
                kind='composite',
                members=inter,
                description=(
                    f'IVs that qualify as {slayer.name} '
                    f'and also clear the {tier.name} threshold.'
                ),
                source_categories=[slayer.name, tier.name],
                source_anchors=list(slayer.source_anchors),
                source_tier=tier.source_tier,
                stat_cutoffs=tier.stat_cutoffs,
                member_meta=comp_meta,
            ))

    # ---- Matchup categories ----
    # Synthesize one IVCategory per (opponent, scenario) pair where the
    # win/loss partition is non-trivial. The 'matchup_conditions' field
    # carries the (opponent, scenario, opp_iv_mode) tuple in declarative
    # form so the renderer (and future bait-axis sweep) can interrogate
    # it without parsing the display name.
    #
    # Selectivity: skip pairs where every IV wins or no IV wins. Both
    # are degenerate from a "named category" perspective - they'd just
    # be "everyone" or "no one". The renderer applies a separate
    # "notable" filter (small categories only) on top of this baseline.
    if matchup_data:
        scores_flat = matchup_data.get('scores_flat') or []
        nS = matchup_data.get('nS', 0)
        nO = matchup_data.get('nO', 0)
        m_scenarios = matchup_data.get('scenarios') or []
        m_opponents = matchup_data.get('opponents') or []
        opp_iv_mode = matchup_data.get('opp_iv_mode', 'pvpoke')
        win_threshold = matchup_data.get('win_threshold', 500)
        opp_iv_label = ('PvPoke default'
                        if parse_mode(opp_iv_mode)[0] == 'pvpoke' else 'rank 1')
        if (scores_flat and nS and nO
                and len(scores_flat) >= n_ivs * nS * nO):
            for oi, opp_name in enumerate(m_opponents):
                if oi >= nO:
                    break
                for si, scen in enumerate(m_scenarios):
                    if si >= nS:
                        break
                    members = []
                    member_meta: dict = {}
                    for iv in range(n_ivs):
                        score = scores_flat[iv * nS * nO + si * nO + oi]
                        if score >= win_threshold:
                            members.append(iv)
                            member_meta[iv] = {
                                'iv': (iv_a[iv], iv_d[iv], iv_s[iv])
                                if iv < len(iv_a) else None,
                                'score': score,
                            }
                    n_win = len(members)
                    if n_win == 0 or n_win == n_ivs:
                        continue  # degenerate partition - skip
                    scen_label = f'{scen[0]}v{scen[1]}'
                    name = f'Beats {opp_iv_label} {opp_name} in the {scen_label}'
                    categories.append(IVCategory(
                        name=name,
                        kind='matchup',
                        members=members,
                        description=(
                            f'IVs whose battle score against the '
                            f'{opp_iv_label} {opp_name} in the {scen_label} '
                            f'shield scenario meets the win threshold '
                            f'({win_threshold:g}).'
                        ),
                        matchup_conditions=[{
                            'opponent': opp_name,
                            'opponent_ivs': opp_iv_mode,
                            'scenario': (scen[0], scen[1]),
                            'bait': parse_mode(opp_iv_mode)[1],
                            'outcome': 'win',
                        }],
                        member_meta=member_meta,
                    ))

    return categories


def auto_discover_thresholds(results, n_tiers=2):
    """
    Discover threshold tiers automatically from simulation results.

    Analyzes the top-performing IVs to find stat values that distinguish
    them from the rest. For each stat, if the top group's 25th percentile
    is notably above the population median, that stat becomes a floor
    threshold. We use the 25th percentile (not minimum) to be robust to
    outliers.

    results: list of dicts from iv_sweep (sorted by avg_score desc)
    n_tiers: number of tiers to generate (default 2)
    """
    if not results or len(results) < 50:
        return {}

    n = len(results)

    # Tier 1: "Top 5%" - top 5% by avg score (renamed from "Premium" to
    # avoid clashing with the community use of "premium" in IV deep dives,
    # which means something more specific than a top-percentile bucket).
    # Tier 2: "Good" - top 20% by score
    tier_cuts = [max(5, n // 20), max(20, n // 5)][:n_tiers]
    tier_names = ['Top 5%', 'Good'][:n_tiers]

    # Population stats (medians)
    pop_atk = sorted(r['atk'] for r in results)
    pop_def = sorted(r['def_'] for r in results)
    pop_hp = sorted(r['hp'] for r in results)
    pop_atk_med = pop_atk[n // 2]
    pop_def_med = pop_def[n // 2]
    pop_hp_med = pop_hp[n // 2]

    thresholds = {}
    for cut, name in zip(tier_cuts, tier_names):
        top = results[:cut]

        # 25th percentile of top group (robust floor)
        top_atk = sorted(r['atk'] for r in top)
        top_def = sorted(r['def_'] for r in top)
        top_hp = sorted(r['hp'] for r in top)
        p25 = max(0, len(top) // 4)
        top_atk_p25 = top_atk[p25]
        top_def_p25 = top_def[p25]
        top_hp_p25 = top_hp[p25]

        thresh = {'attack': 0, 'defense': 0, 'stamina': 0}

        # A stat is a meaningful threshold if the top group's p25 is above
        # the population median by more than 1%
        if top_atk_p25 > pop_atk_med * 1.01:
            thresh['attack'] = round(top_atk_p25, 2)
        if top_def_p25 > pop_def_med * 1.01:
            thresh['defense'] = round(top_def_p25, 2)
        if top_hp_p25 > pop_hp_med + 1:
            thresh['stamina'] = int(top_hp_p25)

        if any(v > 0 for v in thresh.values()):
            thresholds[name] = thresh

    return thresholds


def classify_iv(result, thresholds):
    """
    Return the name of the most restrictive threshold this IV spread meets,
    or None if it doesn't meet any.

    Thresholds are checked in order (most restrictive first).
    A threshold is met if all non-zero stat requirements are satisfied:
      - attack >= threshold attack (if > 0)
      - defense >= threshold defense (if > 0)
      - stamina >= threshold stamina (if > 0)
    """
    for name, thresh in thresholds.items():
        meets = True
        if thresh['attack'] > 0 and result['atk'] < thresh['attack']:
            meets = False
        if thresh['defense'] > 0 and result['def_'] < thresh['defense']:
            meets = False
        if thresh['stamina'] > 0 and result['hp'] < thresh['stamina']:
            meets = False
        if meets:
            return name
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_legal_moves(species_name):
    """Return (fast_move_ids, charged_move_ids) that a species can learn."""
    entry = get_pokemon_entry(species_name)
    return entry['fastMoves'], entry['chargedMoves']


def enumerate_movesets(species_name, user_fast=None, user_charged=None,
                       cd_prep_fast=None, cd_prep_charged=None):
    """
    Enumerate moveset combinations based on what the user specified.

    user_fast:    a single fast move ID, or None
    user_charged: list of 1 or 2 charged move IDs, or None
    cd_prep_fast: list of fast move IDs to inject into legal_fast
                  (validated against gamemaster; used when a species'
                  threshold TOML has a [Species.cd_prep] table so pre-CD
                  dives include the incoming move even when PvPoke's
                  gamemaster hasn't added it to the species pool yet).
    cd_prep_charged: parallel list for charged moves.

    Returns list of (fast_id, [charged_id1, charged_id2]) tuples.
    Single charged move movesets are included too (some mons only need one).

    User-specified moves are validated against the gamemaster move database
    (not the species' legal list), allowing unreleased CD moves etc.
    """
    legal_fast, legal_charged = get_legal_moves(species_name)
    fast_moves_db, charged_moves_db = get_moves()

    # Extend legal lists with cd_prep moves (deduplicated, gamemaster-
    # validated). Logged loudly so the HTML output's CLI-comment / log
    # file make it obvious which moves came from the TOML vs the
    # species' native legal list.
    if cd_prep_fast:
        for mv in cd_prep_fast:
            if mv not in fast_moves_db:
                sys.exit(f"cd_prep fast move {mv!r} not in gamemaster")
            if mv not in legal_fast:
                legal_fast = list(legal_fast) + [mv]
                logger.info(
                    f"  cd_prep: injected fast move {mv} (not in "
                    f"{species_name}'s current legal pool)")
    if cd_prep_charged:
        for mv in cd_prep_charged:
            if mv not in charged_moves_db:
                sys.exit(f"cd_prep charged move {mv!r} not in gamemaster")
            if mv not in legal_charged:
                legal_charged = list(legal_charged) + [mv]
                logger.info(
                    f"  cd_prep: injected charged move {mv} (not in "
                    f"{species_name}'s current legal pool)")

    # Determine fast move candidates
    if user_fast:
        if user_fast not in fast_moves_db:
            sys.exit(f"Unknown fast move {user_fast!r} (not in gamemaster)")
        if user_fast not in legal_fast:
            logger.warning(f"{user_fast} is not in {species_name}'s current move pool "
                           f"(CD/legacy move?)")
        fast_candidates = [user_fast]
    else:
        fast_candidates = list(legal_fast)

    # Determine charged move candidates
    if user_charged and len(user_charged) == 2:
        # Full charged moveset specified - validate against gamemaster, not species
        for cm in user_charged:
            if cm not in charged_moves_db:
                sys.exit(f"Unknown charged move {cm!r} (not in gamemaster)")
            if cm not in legal_charged:
                logger.warning(f"{cm} is not in {species_name}'s current move pool "
                               f"(CD/legacy move?)")
        charged_pairs = [tuple(sorted(user_charged))]
    elif user_charged and len(user_charged) == 1:
        # One charged move specified - pair it with all legal partners
        fixed = user_charged[0]
        if fixed not in charged_moves_db:
            sys.exit(f"Unknown charged move {fixed!r} (not in gamemaster)")
        if fixed not in legal_charged:
            logger.warning(f"{fixed} is not in {species_name}'s current move pool "
                           f"(CD/legacy move?)")
        # Include the fixed move in the partner pool
        all_charged = list(set(legal_charged) | {fixed})
        charged_pairs = []
        for other in sorted(all_charged):
            if other == fixed:
                continue  # skip duplicate (e.g. GH paired with itself)
            pair = tuple(sorted([fixed, other]))
            if pair not in charged_pairs:
                charged_pairs.append(pair)
    else:
        # No charged moves specified - all pairs from legal list
        charged_pairs = list(itertools.combinations(sorted(legal_charged), 2))
        for cm in sorted(legal_charged):
            charged_pairs.append((cm,))

    movesets = []
    seen = set()
    for fast in fast_candidates:
        for pair in charged_pairs:
            key = (fast, pair)
            if key not in seen:
                seen.add(key)
                movesets.append((fast, list(pair)))
    return movesets


def make_battle_pokemon(species, fast_id, charged_ids, league, shields,
                        atk_iv, def_iv, sta_iv, shadow=False):
    """Build a BattlePokemon from species + IVs + move IDs."""
    pokemon = Pokemon.at_best_level(species, atk_iv, def_iv, sta_iv,
                                    league=league, shadow=shadow)
    fast_moves, charged_moves = get_moves()
    fm = dict(fast_moves[fast_id])
    cms = [dict(charged_moves[cid]) for cid in charged_ids]
    gm = load_gamemaster()
    mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
    types = parse_types(mon)
    return BattlePokemon(
        species=species, types=types,
        atk=pokemon.atk, def_=pokemon.def_, max_hp=pokemon.hp,
        fast_move=fm, charged_moves=cms, shields=shields,
    )


def get_top_opponents(league, n, exclude_species=None):
    """Return top N species from PvPoke rankings for the league."""
    rankings = load_rankings(league)
    opponents = []
    for r in rankings:
        name = r['speciesName']
        if exclude_species and name == exclude_species:
            continue
        opponents.append(name)
        if len(opponents) >= n:
            break
    return opponents


def resolve_opp_ivs(species_name, league, shadow, opp_iv_mode):
    """Return (atk_iv, def_iv, sta_iv) for an opponent based on the IV mode.

    opp_iv_mode:
      'pvpoke'  - PvPoke's default IVs from the gamemaster (what pvpoke.com uses)
      'rank1'   - stat-product rank 1 IVs

    Tolerates composite mode strings like ``'pvpoke:nobait'`` - the bait axis
    is focal-side and has no effect on opponent IV selection, so we strip it.
    """
    opp_iv_mode, _ = parse_mode(opp_iv_mode)
    if opp_iv_mode == 'rank1':
        ranked = iv_rank(species_name, league=league, shadow=shadow)
        r1 = ranked[0]
        return r1['atk_iv'], r1['def_iv'], r1['sta_iv']
    else:
        # pvpoke default
        _lv, a, d, s = pvpoke_default_ivs(species_name, league=league)
        return a, d, s


# Variant-suffix plumbing for attack-weighted opponent sweeps.
#
# Opponents are passed around as display strings. Shadow variants use the
# ' (Shadow)' suffix (handled inline at call sites); attack-weighted variants
# use the parallel suffix below. The parser pulls the base species back out so
# gamemaster lookups keep working; the variant tag signals to the opp_cache
# builder that the IVs should come from the shared spread registry rather than
# resolve_opp_ivs().
ATK_WEIGHTED_SUFFIX = ' (atk-weighted)'


def parse_opponent_spec(opp_name):
    """Split an opponents-list entry into (species, variant, is_shadow).

    Handles three forms:
      'Medicham'                 -> ('Medicham', None,           False)
      'Medicham (Shadow)'        -> ('Medicham', None,           True)
      'Medicham (atk-weighted)'  -> ('Medicham', 'atk_weighted', False)

    Shadow + atk-weighted in the same entry is not supported (no meta-relevant
    opponent today is both).
    """
    variant = None
    name = opp_name
    if name.endswith(ATK_WEIGHTED_SUFFIX):
        name = name[:-len(ATK_WEIGHTED_SUFFIX)]
        variant = 'atk_weighted'
    is_shadow = name.endswith(' (Shadow)')
    if is_shadow:
        name = name[:-len(' (Shadow)')]
    return name, variant, is_shadow


def _atk_weighted_spread_name(species):
    """Canonical shared-spread name for a species's atk-weighted variant."""
    return f"{species.lower().replace(' ', '_').replace('(', '').replace(')', '')}_atk_weighted"


def variant_ivs(species, variant, league, threshold_registry):
    """Return (atk_iv, def_iv, sta_iv) for a named variant, or None if absent.

    Today only 'atk_weighted' is defined; future variants can follow the same
    shared-spread naming convention.
    """
    if variant != 'atk_weighted' or threshold_registry is None:
        return None
    spread = threshold_registry.get_spread(
        species, league.capitalize(), _atk_weighted_spread_name(species),
    )
    if spread is None:
        return None
    ivs = getattr(spread, 'ivs', None)
    if not ivs:
        return None
    # IvListSpread.ivs is a tuple of (a,d,s) tuples; take the first entry.
    # Multi-IV spreads are an S4b concern; for S4a one spread = one variant.
    return ivs[0]


def expand_opponents_with_variants(opponents, opp_movesets, threshold_registry, league):
    """Append attack-weighted variants for species with a matching shared spread.

    For each base species in ``opponents``, check whether
    ``shared.<League>.spreads.<species>_atk_weighted`` exists. If so, append
    ``'<Species> (atk-weighted)'`` to the opponents list using the same
    moveset as the base entry. Silent on species without a matching spread.

    Returns (opponents_out, opp_movesets_out, added_labels).
    """
    if threshold_registry is None:
        return list(opponents), list(opp_movesets), []
    league_key = league.capitalize()
    already_present = set()
    for name in opponents:
        species, variant, _ = parse_opponent_spec(name)
        if variant == 'atk_weighted':
            already_present.add(species)

    opponents_out = list(opponents)
    opp_movesets_out = list(opp_movesets)
    added = []
    for idx, name in enumerate(list(opponents)):
        species, variant, is_shadow = parse_opponent_spec(name)
        if variant is not None:
            continue
        if is_shadow:
            continue
        if species in already_present:
            continue
        spread_name = _atk_weighted_spread_name(species)
        if threshold_registry.get_spread(species, league_key, spread_name) is None:
            continue
        variant_label = f"{species}{ATK_WEIGHTED_SUFFIX}"
        opponents_out.append(variant_label)
        opp_movesets_out.append(opp_movesets[idx])
        added.append(variant_label)
        already_present.add(species)
    return opponents_out, opp_movesets_out, added


def sim_score(focal_species, fast_id, charged_ids, league, shields_focal,
              shields_opp, atk_iv, def_iv, sta_iv, shadow,
              opp_species, opp_fast, opp_charged, opp_shadow=False,
              opp_iv_mode='pvpoke', threshold_registry=None):
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
                      charged_policy_1=pvpoke_dp)
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

def screen_movesets(species, movesets, league, shadow, opponents, opp_movesets,
                    shield_scenarios, top_n, opp_iv_mode='pvpoke',
                    threshold_registry=None):
    """
    Quick screen: sim rank-1 IVs for each moveset against opponents.
    Return the top N movesets by average score.
    """
    if top_n == 0 or len(movesets) <= top_n:
        logger.info(f"  {len(movesets)} moveset(s) - skipping screen phase.")
        return movesets

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
                                  threshold_registry=threshold_registry)
                total += score
                count += 1
        avg = total / count if count else 0
        scored.append((avg, fast_id, charged_ids))

    scored.sort(reverse=True)
    elapsed = time.time() - t0
    logger.info(f"  Screened in {elapsed:.1f}s. Top movesets:")
    for i, (avg, fast_id, charged_ids) in enumerate(scored[:top_n]):
        logger.info(f"    {i+1:3d}. {moveset_label(fast_id, charged_ids):<45s} avg={avg:.0f}")
    if len(scored) > top_n:
        logger.info(f"    ... ({len(scored) - top_n} more pruned)")

    return [(fast_id, charged_ids) for _, fast_id, charged_ids in scored[:top_n]]


# ---------------------------------------------------------------------------
# Phase 2: Full IV sweep (parallelized, deduped by stat profile)
# ---------------------------------------------------------------------------

# Worker state for multiprocessing (set via initializer, avoids pickling per call)
_worker_state = {}


def compute_iv_metadata(species, league, shadow=False, iv_floor=None):
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
    """
    from gopvpsim.pokemon import SHADOW_ATK_BONUS, SHADOW_DEF_MULT
    base = get_species(species)
    base_atk, base_def, base_sta = base['atk'], base['def'], base['hp']
    max_cp = LEAGUE_CAPS[league]

    a_floor = d_floor = s_floor = 0
    if iv_floor is not None:
        a_floor, d_floor, s_floor = iv_floor

    iv_meta = []
    for a in range(a_floor, 16):
        for d in range(d_floor, 16):
            for s in range(s_floor, 16):
                lv = best_level(base_atk, base_def, base_sta, a, d, s,
                                max_cp=max_cp,
                                max_level=LEAGUE_MAX_LEVEL.get(league, 51.0))
                if lv is None:
                    continue
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

slayer.compute_iv_metadata = compute_iv_metadata


def group_ivs_by_stat_profile(iv_meta_list):
    """
    Group IVs by effective (atk, def, hp) so we sim each profile once.

    Returns:
        profile_to_indices: dict of (atk, def, hp) -> [iv_idx, ...]
        profile_data: dict of (atk, def, hp) -> (atk, def, hp) for sim
                      (these are the high-precision values; the key uses rounded)
    """
    profile_to_indices = {}
    profile_data = {}
    for idx, meta in enumerate(iv_meta_list):
        key = (round(meta['atk'], 4), round(meta['def_'], 4), int(meta['hp']))
        profile_to_indices.setdefault(key, []).append(idx)
        if key not in profile_data:
            profile_data[key] = (meta['atk'], meta['def_'], meta['hp'])
    return profile_to_indices, profile_data


def _sweep_worker_init(species, focal_types, fm_template, cms_template,
                       opp_cache, shield_scenarios, focal_bait=True,
                       log_path=None, verbose=False):
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
    if focal_bait:
        _worker_state['focal_policy'] = pvpoke_dp
    else:
        import functools
        _worker_state['focal_policy'] = functools.partial(
            pvpoke_dp, bait_shields=False)


def _sweep_worker(profile_chunk):
    """
    Sim a chunk of focal stat profiles against the cached opponent list.

    profile_chunk: list of (profile_key, atk, def, hp) tuples.
    Returns dict of profile_key -> per_opp (which is dict of (scenario_idx, opp_idx) -> score).
    """
    ws = _worker_state
    species = ws['species']
    focal_types = ws['focal_types']
    fm_template = ws['fm_template']
    cms_template = ws['cms_template']
    opp_cache = ws['opp_cache']
    shield_scenarios = ws['shield_scenarios']
    focal_policy = ws.get('focal_policy', pvpoke_dp)

    results = {}
    n_sims = 0
    for profile_key, atk_stat, def_stat, hp_stat in profile_chunk:
        per_opp = {}
        for oi, opp in enumerate(opp_cache):
            for si, (s_focal, s_opp) in enumerate(shield_scenarios):
                bp0 = BattlePokemon(
                    species=species, types=focal_types,
                    atk=atk_stat, def_=def_stat, max_hp=hp_stat,
                    fast_move=dict(fm_template),
                    charged_moves=[dict(cm) for cm in cms_template],
                    shields=s_focal,
                )
                bp1 = BattlePokemon(
                    species=opp['species'], types=opp['types'],
                    atk=opp['atk'], def_=opp['def_'], max_hp=opp['hp'],
                    fast_move=dict(opp['fm']),
                    charged_moves=[dict(cm) for cm in opp['cms']],
                    shields=s_opp,
                )
                result = simulate(bp0, bp1,
                                  charged_policy_0=focal_policy,
                                  charged_policy_1=pvpoke_dp)
                per_opp[(si, oi)] = result.pvpoke_score(0)
                n_sims += 1
        results[profile_key] = per_opp
    return results, n_sims


def iv_sweep(species, fast_id, charged_ids, league, shadow,
             opponents, opp_movesets, shield_scenarios, opp_iv_mode='pvpoke',
             iv_floor=None, log_path=None, verbose=False,
             threshold_registry=None, reserve_cpus=0):
    """
    Sim all 4096 IV spreads for one moveset against all opponents.
    Parallelized across focal stat profiles (deduped by atk/def/hp) using
    multiprocessing - IVs with identical effective stats produce identical
    battles, so we sim each profile once and copy the result to all
    matching IVs (~1.7x speedup).

    opp_iv_mode may be a composite mode string encoding a bait-shields axis:
      'pvpoke', 'rank1'        - bait-on (default pvpoke_dp behavior)
      'pvpoke:nobait', 'rank1:nobait'
                                - bait-off (pvpoke_dp bait_shields=False)
    When the ``:nobait`` suffix is present, the focal uses a no-bait policy;
    the opponent still baits normally.

    Returns (results, n_sims, canonical_scores, canonical_meta) where results
    is one dict per IV, sorted by avg_score desc.
    """
    # Split composite mode into opponent-IV and bait axes.
    opp_iv_mode_simple, bait_mode = parse_mode(opp_iv_mode)
    focal_bait = (bait_mode == 'bait')
    import multiprocessing

    fast_moves_db, charged_moves_db = get_moves()

    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
    focal_types = parse_types(focal_mon)
    fm_template = dict(fast_moves_db[fast_id])
    cms_template = [dict(charged_moves_db[cid]) for cid in charged_ids]

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
                                            league=league, shadow=opp_is_shadow)
        opp_mon = next(m for m in gm['pokemon'] if m['speciesName'] == opp_clean)
        opp_types = parse_types(opp_mon)
        opp_fm = dict(fast_moves_db[opp_fast])
        opp_cms = [dict(charged_moves_db[cid]) for cid in opp_charged]
        opp_cache.append({
            'species': opp_clean, 'types': opp_types,
            'atk': opp_pokemon.atk, 'def_': opp_pokemon.def_,
            'hp': opp_pokemon.hp, 'fm': opp_fm, 'cms': opp_cms,
            'shadow': opp_is_shadow,
        })

    # Pre-compute IV metadata and group by stat profile (focal-side dedup)
    iv_meta = compute_iv_metadata(species, league, shadow=shadow,
                                  iv_floor=iv_floor)
    profile_to_indices, profile_data = group_ivs_by_stat_profile(iv_meta)
    profile_list = [(pk, dat[0], dat[1], dat[2]) for pk, dat in profile_data.items()]

    # Parallel sim: ~100 chunks across the worker pool. imap_unordered
    # hands chunks out as workers free up - finer granularity gives more
    # frequent progress reports and better load balancing.
    n_workers = min(max(1, multiprocessing.cpu_count() - reserve_cpus), 16)
    n_chunks_target = 100
    chunk_size = max(1, (len(profile_list) + n_chunks_target - 1) // n_chunks_target)
    chunks = [profile_list[i:i+chunk_size] for i in range(0, len(profile_list), chunk_size)]

    import time as _time
    sim_start = _time.time()
    chunk_results = []
    with multiprocessing.Pool(
        processes=n_workers,
        initializer=_sweep_worker_init,
        initargs=(species, focal_types, fm_template, cms_template,
                  opp_cache, shield_scenarios, focal_bait,
                  log_path, verbose),
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

    # Merge profile results
    profile_per_opp = {}
    n_sims = 0
    for prof_res, chunk_sims in chunk_results:
        profile_per_opp.update(prof_res)
        n_sims += chunk_sims

    # Build per-IV results by expanding profile sims to all matching IVs.
    # The list is built in canonical iteration order (matches iv_meta order).
    n_scenarios = len(shield_scenarios)
    n_opponents = len(opp_cache)
    results = []
    for idx, meta in enumerate(iv_meta):
        pk = (round(meta['atk'], 4), round(meta['def_'], 4), int(meta['hp']))
        per_opp = profile_per_opp[pk]
        # Compute avg_score for this IV (same for all IVs sharing the profile)
        total_score = sum(per_opp.values())
        count = len(per_opp)
        avg_score = total_score / count if count else 0
        result = dict(meta)  # copy a, d, s, level, cp, atk, def_, hp, stat_product
        result['avg_score'] = avg_score
        result['per_opp'] = per_opp
        results.append(result)

    # Build canonical-order score array (in iv_meta order, same as results list)
    canonical_scores = []
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

    # Now sort and rank
    results.sort(key=lambda r: r['avg_score'], reverse=True)
    for i, r in enumerate(results):
        r['battle_rank'] = i + 1

    by_sp = sorted(results, key=lambda r: r['stat_product'], reverse=True)
    for i, r in enumerate(by_sp):
        r['sp_rank'] = i + 1

    return results, n_sims, canonical_scores, canonical_meta


# ---------------------------------------------------------------------------
# HTML output with threshold highlighting
# ---------------------------------------------------------------------------

# Colors for threshold tiers - most restrictive first, then less restrictive.
# "Other" (no threshold) uses the Viridis colorscale fallback.
THRESHOLD_COLORS = [
    '#00E676',  # bright green - most restrictive tier ("best")
    '#FFD700',  # gold - next tier
    '#FF6D00',  # orange
    '#E040FB',  # purple
    '#00B0FF',  # blue
    '#FF1744',  # red
    '#76FF03',  # lime
    '#F50057',  # pink
]


PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"
PLOTLY_FILENAME = "plotly-2.35.2.min.js"


def _plotly_script_tag(standalone, shared_plotly_dir=None, html_path=None):
    """Return the <script> tag for Plotly.js.

    Three modes, picked in order:
      shared_plotly_dir set: write plotly.min.js there once (idempotent)
        and emit a relative <script src=...> referencing it. Saves
        ~4.35 MB per dive file vs --standalone; keeps offline operation
        as long as the shared dir travels with the dives. Overrides
        `standalone`.
      standalone=True: download and inline plotly.min.js (~4.35 MB
        inline blob; file works in isolation).
      otherwise: emit a CDN <script src=...> reference.
    """
    if shared_plotly_dir is not None:
        shared = Path(shared_plotly_dir)
        shared.mkdir(parents=True, exist_ok=True)
        plotly_path = shared / PLOTLY_FILENAME
        if not plotly_path.exists():
            import urllib.request
            import ssl
            import certifi
            logger.info(f"  Downloading Plotly.js to shared dir: {plotly_path}")
            ctx = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(PLOTLY_CDN, context=ctx) as r:
                plotly_path.write_bytes(r.read())
        if html_path:
            rel = os.path.relpath(
                str(plotly_path),
                os.path.dirname(os.path.abspath(html_path)),
            )
        else:
            rel = str(plotly_path)
        return f'<script src="{rel}"></script>'
    if not standalone:
        return f'<script src="{PLOTLY_CDN}"></script>'
    import urllib.request
    import ssl
    import certifi
    logger.info("  Downloading Plotly.js for standalone HTML...")
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(PLOTLY_CDN, context=ctx) as r:
        plotly_src = r.read().decode()
    return f'<script>{plotly_src}</script>'


def generate_html(species, league, moveset_results, html_path, thresholds=None,
                  opponent_label=None, shield_scenarios=None, opponent_names=None,
                  opp_iv_mode='pvpoke', standalone=False, cli_args_str=None,
                  shared_plotly_dir=None):
    """
    Generate an interactive HTML file with Plotly.js scatter plots.

    If thresholds are provided, points are colored by which threshold tier they
    meet (most restrictive first). The legend is interactive - click to
    isolate/hide groups, hover over legend entries to highlight those points.
    """
    # Build threshold tier names and assign colors
    tier_names = list(thresholds.keys()) if thresholds else []
    tier_colors = {}
    for i, name in enumerate(tier_names):
        tier_colors[name] = THRESHOLD_COLORS[i % len(THRESHOLD_COLORS)]

    opp_desc = opponent_label or "PvPoke rankings"

    plots_data = []
    for entry in moveset_results:
        fast_id, charged_ids, results = entry[0], entry[1], entry[2]
        label = moveset_label(fast_id, charged_ids)

        # Reference IV for matchup diffs: use the IV that matches the opp_iv_mode.
        # If opp_iv_mode=pvpoke, compare against PvPoke default IVs for this species.
        # If opp_iv_mode=rank1, compare against stat-product rank 1.
        ref_result = None
        if parse_mode(opp_iv_mode)[0] == 'rank1':
            # Rank 1 by stat product
            ref_result = min(results, key=lambda r: r['sp_rank'])
            ref_label = (f"SP Rank 1 ({ref_result['atk_iv']}/"
                         f"{ref_result['def_iv']}/{ref_result['sta_iv']})")
        else:
            # PvPoke default IVs
            _lv, da, dd, ds = pvpoke_default_ivs(species, league=league)
            for r in results:
                if (r['atk_iv'] == da and r['def_iv'] == dd
                        and r['sta_iv'] == ds):
                    ref_result = r
                    break
            ref_label = (f"Default ({da}/{dd}/{ds})"
                         if ref_result else None)
        ref_per_opp = ref_result.get('per_opp') if ref_result else None

        def hover(r, tier=None):
            return _hover_text(r, tier_name=tier, ref_per_opp=ref_per_opp,
                               ref_label=ref_label, opponent_names=opponent_names,
                               shield_scenarios=shield_scenarios)

        if thresholds:
            for r in results:
                r['_tier'] = classify_iv(r, thresholds)

            traces = []

            other = [r for r in results if r['_tier'] is None]
            if other:
                traces.append({
                    'name': 'Other',
                    'x': [r['sp_rank'] for r in other],
                    'y': [r['avg_score'] for r in other],
                    'text': [hover(r) for r in other],
                    'marker_color': [r['avg_score'] for r in other],
                    'use_colorscale': True,
                })

            for tier_name in tier_names:
                tier_results = [r for r in results if r['_tier'] == tier_name]
                if tier_results:
                    thresh = thresholds[tier_name]
                    thresh_desc = _threshold_desc(thresh)
                    traces.append({
                        'name': f'{tier_name} ({thresh_desc})',
                        'x': [r['sp_rank'] for r in tier_results],
                        'y': [r['avg_score'] for r in tier_results],
                        'text': [hover(r, tier_name) for r in tier_results],
                        'marker_color': tier_colors[tier_name],
                        'use_colorscale': False,
                    })

            plots_data.append({'label': label, 'traces': traces, 'results': results})
        else:
            traces = [{
                'name': 'All IVs',
                'x': [r['sp_rank'] for r in results],
                'y': [r['avg_score'] for r in results],
                'text': [hover(r) for r in results],
                'marker_color': [r['avg_score'] for r in results],
                'use_colorscale': True,
            }]
            plots_data.append({'label': label, 'traces': traces, 'results': results})

    # --- Build HTML ---
    # Embed CLI invocation as an HTML comment near the top so
    # `grep '<!-- CLI:' file.html` works for forensic comparison.
    cli_comment = ''
    if cli_args_str:
        from html import escape as _esc_cmt
        cli_comment = f'<!-- CLI: {_esc_cmt(cli_args_str)} -->\n'

    html = f"""<!DOCTYPE html>
{cli_comment}<html>
<head>
<meta charset="utf-8">
<title>{species} {league.title()} League IV Deep Dive</title>
{_plotly_script_tag(standalone, shared_plotly_dir, html_path)}
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 20px; background: #1a1a2e; color: #e0e0e0; }}
  h1 {{ color: #e94560; }}
  h2 {{ color: #0f3460; background: #16213e; padding: 8px 12px; border-radius: 4px;
        color: #e0e0e0; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 15px; }}
  .plot-container {{ margin-bottom: 30px; }}
  .summary {{ background: #16213e; padding: 12px; border-radius: 6px;
              margin-bottom: 20px; font-size: 14px; }}
  .summary table {{ border-collapse: collapse; width: 100%; }}
  .summary th, .summary td {{ text-align: left; padding: 4px 10px;
                               border-bottom: 1px solid #0f3460; }}
  .summary th {{ color: #e94560; }}
  .tier-badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px;
                 font-size: 12px; font-weight: bold; margin-left: 4px; }}
  .threshold-info {{ background: #16213e; padding: 10px; border-radius: 6px;
                     margin-bottom: 15px; font-size: 13px; }}
  .threshold-info span {{ font-weight: bold; }}
  details.meta {{ cursor: pointer; }}
  details.meta summary {{ color: #888; font-size: 13px; }}
</style>
</head>
<body>
<h1>{species} - {league.title()} League IV Deep Dive</h1>
<p class="meta">Opponents: {opp_desc}
| Shield scenario(s): {', '.join(f'{s0}v{s1}' for s0, s1 in (shield_scenarios or [(1,1)]))}
| Policy: pvpoke_dp</p>
"""

    # List opponents
    if opponent_names:
        html += '<details class="meta"><summary>Opponent list '
        html += f'({len(opponent_names)} mons)</summary><p style="margin:4px 0 8px 12px">'
        html += ', '.join(opponent_names)
        html += '</p></details>\n'

    # Threshold legend box
    if thresholds:
        html += '<div class="threshold-info">\n'
        html += '<strong>IV Thresholds:</strong><br>\n'
        for tier_name in tier_names:
            thresh = thresholds[tier_name]
            color = tier_colors[tier_name]
            desc = _threshold_desc(thresh)
            html += (f'<span class="tier-badge" style="background:{color};color:#000">'
                     f'{tier_name}</span> {desc}<br>\n')
        html += '<br><em>Hover over legend entries to isolate that tier. '
        html += 'Click to lock the isolation; click again to unlock.</em>\n'
        html += '</div>\n'

    for i, pd in enumerate(plots_data):
        results = pd['results']
        top10 = results[:10]
        html += f'<h2>{pd["label"]}</h2>\n'

        # Summary table with threshold badges
        html += '<div class="summary"><table>\n'
        html += '<tr><th>Battle Rank</th><th>IVs</th><th>Level</th><th>CP</th>'
        html += '<th>Atk</th><th>Def</th><th>HP</th><th>SP Rank</th>'
        html += '<th>Avg Score</th>'
        if thresholds:
            html += '<th>Tier</th>'
        html += '</tr>\n'
        for r in top10:
            tier = r.get('_tier', None)
            tier_html = ''
            if thresholds:
                if tier:
                    color = tier_colors.get(tier, '#666')
                    tier_html = (f'<td><span class="tier-badge" '
                                 f'style="background:{color};color:#000">'
                                 f'{tier}</span></td>')
                else:
                    tier_html = '<td>-</td>'
            html += (f'<tr><td>#{r["battle_rank"]}</td>'
                     f'<td>{r["atk_iv"]}/{r["def_iv"]}/{r["sta_iv"]}</td>'
                     f'<td>{r["level"]}</td><td>{r["cp"]}</td>'
                     f'<td>{r["atk"]:.2f}</td><td>{r["def_"]:.2f}</td><td>{r["hp"]}</td>'
                     f'<td>#{r["sp_rank"]}</td>'
                     f'<td>{r["avg_score"]:.1f}</td>{tier_html}</tr>\n')
        html += '</table></div>\n'
        html += f'<div id="plot{i}" class="plot-container" style="height:550px;"></div>\n'

    # Plotly traces
    html += '<script>\n'
    for i, pd in enumerate(plots_data):
        # Compute fixed axis ranges from all data so they never rescale
        all_x = []
        all_y = []
        for trace in pd['traces']:
            all_x.extend(trace['x'])
            all_y.extend(trace['y'])
        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(all_y), max(all_y)
        x_pad = max(1, (x_max - x_min) * 0.02)
        y_pad = max(0.5, (y_max - y_min) * 0.03)

        traces_js = []
        # Track original opacities per trace for hover restore
        original_opacities = []
        for trace in pd['traces']:
            t = {
                'x': trace['x'],
                'y': trace['y'],
                'text': trace['text'],
                'name': trace['name'],
                'mode': 'markers',
                'type': 'scattergl',
                'hoverinfo': 'text',
            }
            if trace['use_colorscale']:
                # Dim the background "Other" points when tier traces
                # exist so the tier-colored points are clearly visible.
                has_tier_traces = any(
                    not tr['use_colorscale'] for tr in pd['traces'])
                opacity = 0.4
                t['marker'] = {
                    'size': 2,
                    'color': trace['marker_color'],
                    'colorscale': 'Viridis',
                    'opacity': opacity,
                }
                if not thresholds:
                    t['marker']['colorbar'] = {'title': 'Avg Score'}
            else:
                opacity = 0.9
                t['marker'] = {
                    'size': 6,
                    'color': trace['marker_color'],
                    'opacity': opacity,
                    'line': {'width': 1, 'color': '#000'},
                }
            traces_js.append(t)
            original_opacities.append(opacity)

        layout = {
            'title': pd['label'],
            'xaxis': {
                'title': 'Stat Product Rank (1=best)',
                'range': [x_max + x_pad, x_min - x_pad],  # reversed
                'fixedrange': True,
            },
            'yaxis': {
                'title': 'Avg Battle Score',
                'range': [y_min - y_pad, y_max + y_pad],
                'fixedrange': True,
            },
            'paper_bgcolor': '#1a1a2e',
            'plot_bgcolor': '#16213e',
            'font': {'color': '#e0e0e0'},
            'hovermode': 'closest',
            'legend': {
                'bgcolor': 'rgba(22,33,62,0.8)',
                'bordercolor': '#0f3460',
                'borderwidth': 1,
            },
        }
        # Use .then() to attach legend hover behavior after Plotly finishes rendering.
        # Plotly.restyle is the correct API for per-trace marker updates.
        # We suppress default legend click/doubleclick, and instead use
        # mouseenter/mouseleave on the legend SVG <g class="traces"> elements
        # to isolate one tier at a time without rescaling axes.
        html += f"""
Plotly.newPlot("plot{i}", {json.dumps(traces_js)}, {json.dumps(layout)},
  {{responsive: true}}).then(function(gd) {{
  var origOpacities = {json.dumps(original_opacities)};
  var nTraces = origOpacities.length;
  var lockedIdx = -1;  // -1 = not locked; >= 0 = locked to that trace

  gd.on("plotly_legendclick", function() {{ return false; }});
  gd.on("plotly_legenddoubleclick", function() {{ return false; }});

  function highlightTrace(idx) {{
    for (var j = 0; j < nTraces; j++) {{
      var op = (j === idx) ? Math.min(1.0, origOpacities[j] + 0.15) : 0.03;
      Plotly.restyle(gd, {{"marker.opacity": op}}, [j]);
    }}
  }}

  function restoreAll() {{
    for (var j = 0; j < nTraces; j++) {{
      Plotly.restyle(gd, {{"marker.opacity": origOpacities[j]}}, [j]);
    }}
  }}

  var attempts = 0;
  function attachLegendHover() {{
    var items = gd.querySelectorAll(".legend .traces");
    if (items.length === 0 && attempts < 50) {{
      attempts++;
      setTimeout(attachLegendHover, 100);
      return;
    }}
    items.forEach(function(el, idx) {{
      el.style.cursor = "pointer";
      el.addEventListener("mouseenter", function() {{
        if (lockedIdx < 0) highlightTrace(idx);
      }});
      el.addEventListener("mouseleave", function() {{
        if (lockedIdx < 0) restoreAll();
      }});
      el.addEventListener("click", function() {{
        if (lockedIdx === idx) {{
          lockedIdx = -1;
          restoreAll();
        }} else {{
          lockedIdx = idx;
          highlightTrace(idx);
        }}
      }});
    }});
  }}
  attachLegendHover();
}});
"""

    # Methodology footer
    shield_desc = ', '.join(f'{s0}v{s1}' for s0, s1 in (shield_scenarios or [(1, 1)]))
    n_opponents = len(opponent_names) if opponent_names else '?'
    if parse_mode(opp_iv_mode)[0] == 'rank1':
        opp_iv_desc = 'stat-product rank 1 IVs'
    else:
        opp_iv_desc = ("PvPoke's default IVs (the IVs pvpoke.com uses when you "
                       "load a matchup)")
    html += '</script>\n'
    html += f"""
<hr style="border-color:#0f3460; margin-top:40px">
<div style="color:#888; font-size:12px; max-width:800px; margin:10px 0 30px 0; line-height:1.6">
<strong>Methodology</strong><br>
Each of the 4096 possible IV spreads (0-15 for Atk/Def/Sta) is leveled to the
highest level that stays under the {league.title()} League CP cap ({LEAGUE_CAPS[league]}).
For each IV spread, a battle is simulated against each of the {n_opponents} opponents
in the {opp_desc} pool in the {shield_desc} shield scenario(s), using the
<code>pvpoke_dp</code> policy (PvPoke's simulate-mode dynamic programming policy).
Opponents use {opp_iv_desc} at their best level for this league.
<br><br>
<strong>Avg Battle Score</strong> is the mean of the PvPoke battle scores across all
opponents and shield scenarios. The PvPoke score for a single battle is:
<code>500 &times; (damage dealt / opponent max HP) + 500 &times; (HP remaining / own max HP)</code>.
A score of 500 means a tie; above 500 is a win, below is a loss.
<br><br>
<strong>Battle Rank</strong> is the IV spread's position when all 4096 spreads are
sorted by Avg Battle Score (descending). Battle Rank #1 is the IV spread that performs
best on average against this opponent pool.
<strong>Stat Product Rank</strong> (x-axis) is the traditional PvP IV rank based on
Atk &times; Def &times; HP.
</div>
"""
    # Footer: equivalent CLI invocation, kept at the bottom so it's
    # discoverable but doesn't compete with the actual analysis content.
    if cli_args_str:
        from html import escape as _esc
        html += '<details class="meta" style="margin-top:30px;border-top:1px solid #0f3460;padding-top:10px">'
        html += '<summary>Run parameters (CLI invocation)</summary>'
        html += '<pre style="margin:8px 0;background:#16213e;'
        html += 'padding:10px;border-radius:4px;color:#e0e0e0;font-size:12px;'
        html += 'white-space:pre-wrap;word-break:break-all">'
        html += _esc(cli_args_str)
        html += '</pre></details>\n'

    html += '</body>\n</html>\n'

    with open(html_path, 'w') as f:
        f.write(html)
    logger.result(f"  HTML written to {html_path}")


_hover_text = rendering.hover_text
_threshold_desc = rendering.threshold_desc
_scenario_ranks = rendering.scenario_ranks


# ---------------------------------------------------------------------------
# Reference moveset resolution
# ---------------------------------------------------------------------------

def resolve_reference_moveset(species, league, shadow, ref_arg):
    """Return (fast_id, [charged_ids]) for the reference moveset, or None.

    ref_arg: 'auto' (PvPoke default), 'none' (skip), or 'FAST,CHARGED1,CHARGED2'
    """
    if ref_arg == 'none':
        return None
    if ref_arg == 'auto':
        try:
            fast, charged = get_default_moveset(species, league=league, shadow=shadow)
            return fast, charged
        except KeyError:
            logger.warning(f"no default moveset for {species} in {league} rankings; "
                           f"skipping reference")
            return None
    # Explicit: FAST,CHARGED1,CHARGED2
    parts = [p.strip() for p in ref_arg.split(',')]
    if len(parts) == 3:
        return parts[0], parts[1:]
    sys.exit(f"--reference must be 'auto', 'none', or FAST,CHARGED1,CHARGED2, got {ref_arg!r}")


# ---------------------------------------------------------------------------
# Deep dive analysis (banding, clusters, flips, volatility)
# ---------------------------------------------------------------------------

# Aliases for extracted analysis functions (deep_dive_analysis.py)
_find_flips = analysis.find_flips
_merge_flip_dicts = analysis.merge_flip_dicts
_build_move_tuples = analysis.build_move_tuples
_pretty_name = analysis.pretty_name
_pretty_moveset = analysis.pretty_moveset
_stat_cutoffs_from_anchors = analysis.stat_cutoffs_from_anchors
_aggregate_flips_by_anchor = analysis.aggregate_flips_by_anchor
_find_matchup_boundaries = analysis.find_matchup_boundaries
_auto_derive_tiers = analysis.auto_derive_tiers



def _rename_plotly_tiers(data_obj, flavors):
    """Rename Plotly tier entries to match narrative flavor names.

    For each non-General flavor, find the matching tier in data_obj['tiers']
    by stat threshold and replace its name with the flavor's clean name.
    Also sync HP cutoffs from the narrative (which enriches HP from matchup
    boundaries) into the tier.

    Each tier is renamed at most once per call. When multiple flavors would
    match the same tier (same stat threshold within 0.1), the first flavor
    in iteration order wins; downstream flavors fall through to the next
    unclaimed tier. ``refine_flavor_names`` pre-sorts flavors most-specific-
    first, so the first-match winner is the narrowest flavor - the one
    whose name best describes that tier's actual selectivity.

    Prior to 2026-04-21, this function produced compound names like
    ``"Steelix (Shadow) Slayer<br>  (Wigglytuff Slayer<br>  (Wigglytuff
    Atk))"`` by concatenating each rename with the previous name via
    ``<br>``. Tier cards in the IV Recommendations grid convert ``<br>``
    to ``" - "`` for single-line display, so the compound leaked into
    the cards as "Steelix (Shadow) Slayer -   (Wigglytuff Slayer -
    (Wigglytuff Atk))" - visibly wrong and misleading. The fix:
    narrative names already carry their own stat-signature
    disambiguation via ``refine_flavor_names`` (line 547-558), so the
    compound form adds no information and only noise. Plotly scatter
    legend loses its two-line format as a side effect; the signature-
    suffix "Lapras Slayer (123.74+ Atk)" carries the same info in one
    line.
    """
    plot_tiers = data_obj.get('tiers', [])
    if not plot_tiers:
        return

    renamed_ids: set[int] = set()  # Track which tiers have been claimed
    for flavor in flavors:
        if flavor['is_general']:
            continue  # General is excluded from the Plotly legend
        # Match by primary stat threshold, skipping already-renamed tiers.
        matched_tier = None
        for tier in plot_tiers:
            if id(tier) in renamed_ids:
                continue
            t_atk = tier.get('attack', 0) or 0
            t_def = tier.get('defense', 0) or 0
            if flavor['atk_cut'] > 0 and abs(t_atk - flavor['atk_cut']) < 0.1:
                matched_tier = tier
                break
            elif flavor['def_cut'] > 0 and abs(t_def - flavor['def_cut']) < 0.1:
                matched_tier = tier
                break
        if not matched_tier:
            continue

        renamed_ids.add(id(matched_tier))

        old_name = matched_tier['name']
        new_name = flavor['name']
        if old_name != new_name:
            # Preserve the original tier name so slug-generation in
            # downstream consumers (generate_article.py:_tier_card_href)
            # produces the same anchor id as the dive's own tier-card
            # rendering, which slugs from t['name'] BEFORE this rename
            # runs. Decouples the visible display name (overwritten
            # here) from the stable link slug (keyed on the original
            # auto-derived name).
            matched_tier['original_name'] = old_name
            matched_tier['name'] = new_name

        # Sync HP cutoff from narrative enrichment
        if flavor['hp_cut'] > 0 and not (matched_tier.get('stamina') or 0):
            matched_tier['stamina'] = flavor['hp_cut']
            # Recompute ivTiers assignments with the new HP cutoff
            _recompute_tier_assignments(data_obj, plot_tiers)


def _promote_flavors_to_paste_tiers(data_obj, flavors):
    """Augment DATA.pasteTiers with narrative flavors for the paste-box.

    The scatter plot reads ``DATA.tiers`` for its per-tier traces, so
    adding flavors there would colour the plot with extra buckets that
    aren't meant to be visible on the scatter. ``DATA.pasteTiers`` is
    the paste-box-only union: existing plot tiers plus any non-General
    flavor whose name isn't already represented. General is skipped
    because its cutoffs are effectively zero (every IV qualifies) and
    the paste-box would always report every owned mon under it.

    Emits entries shaped like plot tiers so the JS paste-box iterates
    them uniformly: ``{name, attack, defense, stamina, color, desc}``.
    """
    plot_tiers = list(data_obj.get('tiers') or [])
    existing_names = set()
    for t in plot_tiers:
        raw = (t.get('name') or '').split('<br>', 1)[0].strip()
        if raw:
            existing_names.add(raw)
    paste_tiers = list(plot_tiers)
    for f in flavors:
        if f.get('is_general'):
            continue
        if f.get('n_qualifying', 0) <= 0:
            continue
        name = f.get('name', '').strip()
        if not name or name in existing_names:
            continue
        paste_tiers.append({
            'name': name,
            'attack': f.get('atk_cut', 0) or 0,
            'defense': f.get('def_cut', 0) or 0,
            'stamina': f.get('hp_cut', 0) or 0,
            'color': f.get('tier_color') or '#888',
            'desc': f.get('tier_desc') or '',
        })
        existing_names.add(name)
    data_obj['pasteTiers'] = paste_tiers


def _recompute_tier_assignments(data_obj, plot_tiers):
    """Recompute ivTiers and ivAllTiers after modifying tier cutoffs."""
    n = data_obj.get('nIvs', 0)
    iv_tiers = [-1] * n
    iv_all_tiers = [[] for _ in range(n)]
    for ti, t in enumerate(plot_tiers):
        ac = t.get('attack', 0) or 0
        dc = t.get('defense', 0) or 0
        hc = t.get('stamina', 0) or 0
        for iv in range(n):
            if ac > 0 and data_obj['ivAtk'][iv] < ac:
                continue
            if dc > 0 and data_obj['ivDef'][iv] < dc:
                continue
            if hc > 0 and data_obj['ivHp'][iv] < hc:
                continue
            iv_all_tiers[iv].append(ti)
            if iv_tiers[iv] < 0:
                iv_tiers[iv] = ti
    data_obj['ivTiers'] = iv_tiers
    data_obj['ivAllTiers'] = iv_all_tiers


def _generate_narrative_for_moveset(data_obj, score_arrays, moveset_idx,
                                    scenarios, opponents, opp_iv_modes,
                                    has_toml_tiers, resolved_anchors=None):
    """Generate narrative HTML for one moveset.

    Computes matchup boundaries (and optionally anchor-flip records if
    resolved_anchors are provided), auto-derives tiers, and renders the
    SwagTips-style IV Flavor Guide zone.

    Returns narrative HTML string (may be empty).
    """
    from deep_dive_narrative import (derive_narrative_flavors,
                                     compute_flavor_tradeoffs,
                                     refine_flavor_names,
                                     enforce_namesake_guarantee,
                                     merge_identical_stat_flavors,
                                     render_narrative_zone)
    nIvs = data_obj['nIvs']
    nS = len(scenarios)
    nO = len(opponents)
    _bait_values = {parse_mode(m)[1] for m in opp_iv_modes}
    has_bait_axis = ('bait' in _bait_values and 'nobait' in _bait_values)
    opp_label = data_obj.get('oppLabel', 'opponent')

    # Compute anchor-flip records if we have resolved anchors
    anchor_flip_records = []
    if resolved_anchors:
        _seen = {}
        for _mode in opp_iv_modes:
            bait_mode = parse_mode(_mode)[1]
            _key = f'{moveset_idx}_{_mode}'
            _scores = score_arrays.get(_key, [])
            if not _scores:
                continue
            _recs = _aggregate_flips_by_anchor(
                _scores, nIvs, nS, nO,
                resolved_anchors, data_obj, scenarios, opponents,
            )
            for rec in _recs:
                rec['bait_modes'] = {bait_mode}
                dedup_key = (rec['anchor'].name, rec['opponent'],
                             frozenset(tuple(s) for s in rec['scenarios']))
                if dedup_key in _seen:
                    _seen[dedup_key]['bait_modes'] |= rec['bait_modes']
                else:
                    _seen[dedup_key] = rec
                    anchor_flip_records.append(rec)

    # Compute matchup boundaries (always available, no anchors needed)
    all_matchup_boundaries = []
    _mb_seen = {}
    for _mode in opp_iv_modes:
        bait_mode = parse_mode(_mode)[1]
        _key = f'{moveset_idx}_{_mode}'
        _scores = score_arrays.get(_key, [])
        if not _scores:
            continue
        for _sweep in ('def', 'atk'):
            _mbs = _find_matchup_boundaries(
                _scores, nIvs, nS, nO,
                data_obj, scenarios, opponents,
                sweep_stat=_sweep,
            )
            for mb in _mbs:
                mb['bait_modes'] = {bait_mode}
                dedup_key = (mb['opponent'], mb['stat'], mb['threshold'],
                             mb.get('hp_threshold'),
                             frozenset(tuple(s) for s in mb['scenarios']))
                if dedup_key in _mb_seen:
                    _mb_seen[dedup_key]['bait_modes'] |= mb['bait_modes']
                else:
                    _mb_seen[dedup_key] = mb
                    all_matchup_boundaries.append(mb)

    # Derive tiers fresh for this moveset - don't reuse data_obj['tiers']
    # which may contain moveset 0's auto-derived tiers.
    effective_tiers = []
    if has_toml_tiers and not anchor_flip_records and not all_matchup_boundaries:
        # TOML tiers with no sim data for this moveset - use TOML as-is
        effective_tiers = data_obj.get('tiers') or []
    elif anchor_flip_records or all_matchup_boundaries:
        effective_tiers = _auto_derive_tiers(
            anchor_flip_records, data_obj,
            matchup_boundaries=all_matchup_boundaries) or []

    if not effective_tiers:
        return '', []

    flavors = derive_narrative_flavors(
        effective_tiers, all_matchup_boundaries, data_obj)
    if not flavors:
        return '', []

    tradeoffs = (compute_flavor_tradeoffs(
        flavors, data_obj, score_arrays, moveset_idx,
        scenarios, opponents,
        all_matchup_boundaries=all_matchup_boundaries)
        if len(flavors) >= 2 else {})
    refine_flavor_names(flavors, tradeoffs)
    enforce_namesake_guarantee(
        flavors, tradeoffs, all_matchup_boundaries,
        anchor_flip_records=anchor_flip_records)
    merge_identical_stat_flavors(flavors, tradeoffs)
    nar_html = render_narrative_zone(
        flavors, tradeoffs, all_matchup_boundaries,
        data_obj, opp_label, has_bait_axis=has_bait_axis,
        moveset_idx=moveset_idx) or ''
    return nar_html, flavors


def generate_analysis_sections(data_obj, score_arrays, moveset_idx, opp_iv_mode,
                               shield_scenarios, opponent_names,
                               slayer_iter_result=None,
                               has_toml_tiers=False,
                               anchor_passing_sink=None,
                               threshold_registry=None,
                               moveset0_flavors_for_rename=None):
    """Generate the full analysis HTML for injection into the interactive page.

    Returns (css_str, results_html_str, analysis_html_str).
    results_html is always visible ("Deep Dive Results").
    analysis_html goes behind the toggle ("Deep Dive Analysis").

    When ``anchor_passing_sink`` is a dict, it gets populated with
    ``{anchor_id: [passing_iv_idx, ...]}`` for every anchor-flip bullet
    rendered, so the interactive HTML can embed the map as DATA and
    light up "which of your IVs hit this breakpoint" annotations after
    the user loads their CSV. Populated as a side effect - callers who
    just want HTML can leave it at None.
    """
    nIvs = data_obj['nIvs']
    nS = data_obj['nScenarios']
    nO = data_obj['nOpponents']
    scenarios = [tuple(s) for s in data_obj['scenarios']]
    opponents = opponent_names or data_obj.get('opponents', [])
    score_key = f'{moveset_idx}_{opp_iv_mode}'
    scores_flat = score_arrays.get(score_key, [])
    if not scores_flat:
        return '', '', '<!-- analysis: no scores available -->'
    moveset_label = data_obj['movesets'][moveset_idx]['label']
    ref_iv = data_obj['pvpokeRefIvIdx']
    if ref_iv < 0:
        ref_iv = 0

    logger.info("  Generating analysis sections...")

    # Determine whether both bait modes were swept (for bait annotations).
    all_modes = data_obj.get('oppIvModes', [opp_iv_mode])
    _bait_values = {parse_mode(m)[1] for m in all_modes}
    has_bait_axis = ('bait' in _bait_values and 'nobait' in _bait_values)

    # Resolved anchors are needed by both the slayer-iteration block (much
    # further down) and the new anchor-driven matchup-flip section (rendered
    # right after Key Matchup Thresholds). Extract once here.
    resolved_anchors_top = []
    if slayer_iter_result:
        resolved_anchors_top = slayer_iter_result.get('resolved_anchors', []) or []

    # Set up breakpoint narration: load move data, species types, opponent info
    fast_db, charged_db = get_moves()
    gm = load_gamemaster()
    focal_entry = next((m for m in gm['pokemon']
                        if m['speciesName'] == data_obj.get('species', '')), None)
    focal_types = parse_types(focal_entry) if focal_entry else []
    focal_moves = _build_move_tuples(moveset_label, fast_db, charged_db)

    # Cache opponent info for narration: {name: (atk, def, types, moves)}
    opp_info_cache = {}
    league = data_obj.get('league', 'great')
    for opp_name in opponents:
        try:
            opp_clean, variant, opp_is_shadow = parse_opponent_spec(opp_name)
            variant_iv = variant_ivs(opp_clean, variant, league, threshold_registry)
            if variant_iv is not None:
                oa, od, os_ = variant_iv
            else:
                oa, od, os_ = resolve_opp_ivs(opp_clean, league, opp_is_shadow, opp_iv_mode)
            opp_pokemon = Pokemon.at_best_level(opp_clean, oa, od, os_,
                                                league=league, shadow=opp_is_shadow)
            opp_entry = next((m for m in gm['pokemon']
                              if m['speciesName'] == opp_clean), None)
            opp_types = parse_types(opp_entry) if opp_entry else []
            # Get opponent's default moveset moves
            try:
                opp_fast, opp_charged = get_default_moveset(opp_clean, league=league,
                                                            shadow=opp_is_shadow)
                opp_moves_list = []
                if opp_fast in fast_db:
                    fm = fast_db[opp_fast]
                    opp_moves_list.append((opp_fast, fm['power'], fm['type']))
                for cid in opp_charged:
                    if cid in charged_db:
                        cm = charged_db[cid]
                        opp_moves_list.append((cid, cm['power'], cm['type']))
            except (KeyError, ValueError):
                opp_moves_list = []
            opp_info_cache[opp_name] = {
                'atk': opp_pokemon.atk, 'def_': opp_pokemon.def_,
                'types': opp_types, 'moves': opp_moves_list,
            }
        except Exception:
            pass  # skip opponents we can't resolve

    ref_atk = data_obj['ivAtk'][ref_iv]
    ref_def = data_obj['ivDef'][ref_iv]

    scene_ranks, avg_ranks, avg_scores, ranked = _scenario_ranks(scores_flat, nIvs, nS, nO)

    css = rendering.DEEP_DIVE_CSS

    opp_label = 'PvPoke default' if parse_mode(opp_iv_mode)[0] == 'pvpoke' else 'rank 1'

    # ---- Compute flips (needed by both results and analysis) ----
    test_set = set(ranked[:10])
    for iv in range(nIvs):
        if data_obj['ivTiers'][iv] >= 0:
            test_set.add(iv)
    test_set.discard(ref_iv)
    flips = {}
    _sorted_test = sorted(test_set)
    for _mode in all_modes:
        _key = f'{moveset_idx}_{_mode}'
        _sf = score_arrays.get(_key, [])
        if not _sf:
            continue
        _, _bm = parse_mode(_mode)
        _mode_flips = _find_flips(_sf, nIvs, nS, nO, ref_iv, _sorted_test,
                                  scenarios, opponents, bait_mode=_bm)
        flips = _merge_flip_dicts(flips, _mode_flips)
    flip_summary = [(iv, len(f['gains']), len(f['losses']), len(f['gains']) - len(f['losses'])) for iv, f in flips.items()]
    flip_summary.sort(key=lambda x: (-x[3], -x[1]))
    flip_map = {iv: (g, l, net) for iv, g, l, net in flip_summary}
    hp_list = [data_obj['ivHp'][i] for i in range(nIvs)]

    # ======== Build recommendation candidates ========
    rec_candidates = []
    for iv in ranked[:50]:
        g, l, net = flip_map.get(iv, (0, 0, 0))
        rng = max(scene_ranks[si][iv] for si in range(nS)) - min(scene_ranks[si][iv] for si in range(nS))
        if has_bait_axis and iv in flips:
            fd = flips[iv]
            net_both = sum(1 for e in fd.get('gains', []) if len(e.get('bait_modes', set())) > 1) \
                     - sum(1 for e in fd.get('losses', []) if len(e.get('bait_modes', set())) > 1)
            net_single = net - net_both
            score = -avg_ranks[iv] + net_both * 3 + net_single * 1.5 - rng * 0.001
        else:
            score = -avg_ranks[iv] + net * 3 - rng * 0.001
        rec_candidates.append({'iv': iv, 'avg_rank': avg_ranks[iv], 'avg_score': avg_scores[iv],
                                'gains': g, 'losses': l, 'net': net, 'range': rng, 'score': score})
    rec_candidates.sort(key=lambda x: x['score'], reverse=True)

    # Assign descriptive tier names based on stat profile
    for rc in rec_candidates:
        iv = rc['iv']
        atk, def_, hp = data_obj['ivAtk'][iv], data_obj['ivDef'][iv], data_obj['ivHp'][iv]
        pop_atk = sum(data_obj['ivAtk'][i] for i in ranked[:20]) / 20
        pop_def = sum(data_obj['ivDef'][i] for i in ranked[:20]) / 20
        pop_hp = sum(data_obj['ivHp'][i] for i in ranked[:20]) / 20
        # "Bait Robust" - all flips fire in both bait modes and net is positive
        if has_bait_axis and iv in flips and rc['net'] > 0:
            fd = flips[iv]
            all_entries = fd.get('gains', []) + fd.get('losses', [])
            if all_entries and all(len(e.get('bait_modes', set())) > 1 for e in all_entries):
                rc['style'] = 'Bait Robust'
                continue
        if atk > pop_atk + 0.5:
            rc['style'] = 'Attack Weight'
        elif def_ > pop_def + 2:
            rc['style'] = 'High Defense'
        elif hp > pop_hp + 2:
            rc['style'] = 'High HP'
        elif rc['net'] > 5:
            rc['style'] = 'Matchup Hunter'
        elif rc['range'] < 500:
            rc['style'] = 'Generalist'
        else:
            rc['style'] = 'Balanced'

    # Store top-3 recommended IV indices so the JS engine can render
    # them as a distinct overlay trace on the scatter plot.
    data_obj['recIvs'] = [rc['iv'] for rc in rec_candidates[:3]]

    # -- Compute anchor-flip records (used by Threshold Tiers, the flat
    #    Anchor-Driven Matchup Flips section, and Notable IVs below) --
    # Run the aggregator against every opp_iv_mode (pvpoke, rank1, or both)
    # and union the results. acidicArisen-style thresholds are often against
    # rank-1 opponent IVs; running only against pvpoke defaults would miss
    # them. Dedup by (anchor.name, opponent, frozenset(scenarios)) so a
    # record that fires in both modes doesn't appear twice.
    anchor_flip_records = []
    if resolved_anchors_top:
        _seen: dict = {}  # dedup_key -> rec (merge bait_modes on collision)
        for _mode in all_modes:
            bait_mode = parse_mode(_mode)[1]
            _key = f'{moveset_idx}_{_mode}'
            _scores = score_arrays.get(_key, [])
            if not _scores:
                continue
            _debug: dict = {}
            _recs = _aggregate_flips_by_anchor(
                _scores, nIvs, nS, nO,
                resolved_anchors_top, data_obj, scenarios, opponents,
                debug_stats=_debug,
            )
            for rec in _recs:
                rec['bait_modes'] = {bait_mode}
                dedup_key = (rec['anchor'].name, rec['opponent'],
                             frozenset(tuple(s) for s in rec['scenarios']))
                if dedup_key in _seen:
                    _seen[dedup_key]['bait_modes'] |= rec['bait_modes']
                else:
                    _seen[dedup_key] = rec
                    anchor_flip_records.append(rec)
            logger.debug(f"  Anchor-flip aggregator ({_mode}): {_debug}")

    # -- Compute matchup-flipping boundaries (def and atk sweeps) --
    # Run before tier cards so they can include boundary bullets.
    all_matchup_boundaries = []
    _mb_seen: dict = {}  # dedup_key -> mb (merge bait_modes on collision)
    for _mode in all_modes:
        bait_mode = parse_mode(_mode)[1]
        _key = f'{moveset_idx}_{_mode}'
        _scores = score_arrays.get(_key, [])
        if not _scores:
            continue
        for _sweep in ('def', 'atk'):
            _mbs = _find_matchup_boundaries(
                _scores, nIvs, nS, nO,
                data_obj, scenarios, opponents,
                sweep_stat=_sweep,
            )
            for mb in _mbs:
                mb['bait_modes'] = {bait_mode}
                dedup_key = (mb['opponent'], mb['stat'], mb['threshold'],
                             mb.get('hp_threshold'),
                             frozenset(tuple(s) for s in mb['scenarios']))
                if dedup_key in _mb_seen:
                    _mb_seen[dedup_key]['bait_modes'] |= mb['bait_modes']
                else:
                    _mb_seen[dedup_key] = mb
                    all_matchup_boundaries.append(mb)
    if all_matchup_boundaries:
        _n_def = sum(1 for m in all_matchup_boundaries
                     if m.get('stat') == 'def')
        _n_atk = sum(1 for m in all_matchup_boundaries
                     if m.get('stat') == 'atk')
        logger.info(f"  Matchup boundaries: {len(all_matchup_boundaries)} found "
                    f"({_n_def} def, {_n_atk} atk)")

    # -- Threshold Tiers (RyanSwag-style, stat-target-forward) --
    effective_tiers = data_obj.get('tiers') or []
    if has_toml_tiers:
        pass
    elif anchor_flip_records:
        effective_tiers = _auto_derive_tiers(
            anchor_flip_records, data_obj,
            matchup_boundaries=all_matchup_boundaries)
        if effective_tiers:
            logger.info(f"  Auto-derived {len(effective_tiers)} threshold tier(s) "
                        f"from anchor-flip records")
            # Inject auto-derived tiers into data_obj for scatter plot
            # coloring. Exclude the "General" tier - it's too broad (catches
            # ~all IVs) and kills the contrast that makes selective tiers
            # visible. General stays in effective_tiers for the tier cards.
            plot_tiers = [t for t in effective_tiers
                          if t['name'] != 'General']
            data_obj['tiers'] = plot_tiers
            _n = data_obj['nIvs']
            _iv_tiers = [-1] * _n
            _iv_all_tiers = [[] for _ in range(_n)]
            for _ti, _t in enumerate(plot_tiers):
                _ac = _t.get('attack', 0) or 0
                _dc = _t.get('defense', 0) or 0
                _hc = _t.get('stamina', 0) or 0
                for _iv in range(_n):
                    meets = True
                    if _ac > 0 and data_obj['ivAtk'][_iv] < _ac:
                        meets = False
                    if _dc > 0 and data_obj['ivDef'][_iv] < _dc:
                        meets = False
                    if _hc > 0 and data_obj['ivHp'][_iv] < _hc:
                        meets = False
                    if meets:
                        _iv_all_tiers[_iv].append(_ti)
                        if _iv_tiers[_iv] < 0:
                            _iv_tiers[_iv] = _ti
            data_obj['ivTiers'] = _iv_tiers
            data_obj['ivAllTiers'] = _iv_all_tiers

    # Tier-name unify (2026-04-23): rename data_obj['tiers'] to match
    # narrative flavor names so the tier-card badges and the Plotly
    # legend both display the flavor-matched name. The rename is
    # idempotent on the TOML-tier path (caller already pre-renamed in
    # generate_interactive_html); on the auto-derive path above, this
    # is the *first* chance to rename, because the block at line
    # ``data_obj['tiers'] = plot_tiers`` replaced the dicts the caller
    # would have touched.
    if moveset0_flavors_for_rename and (data_obj.get('tiers') or []):
        _rename_plotly_tiers(data_obj, moveset0_flavors_for_rename)
        # effective_tiers may be a distinct list from data_obj['tiers']
        # (auto-derive keeps 'General' locally but drops it for plotting),
        # so sync the rename into any shared-name entries too. Matching
        # is by object identity: plot_tiers is filtered from
        # effective_tiers, so the renamed dicts *are* the same objects,
        # and iterating effective_tiers picks up the mutation automatically.

    # ======== RESULTS section (always visible) ========
    import time as _time
    _rr_start = _time.time()
    logger.info(f"  Rendering results section (moveset {moveset_idx}: "
                f"{moveset_label})...")
    results_html = rendering.render_results_section(
        data_obj=data_obj, moveset_label=moveset_label, opp_label=opp_label,
        effective_tiers=effective_tiers,
        anchor_flip_records=anchor_flip_records,
        all_matchup_boundaries=all_matchup_boundaries,
        score_arrays=score_arrays, moveset_idx=moveset_idx,
        flips=flips, flip_map=flip_map, avg_ranks=avg_ranks,
        avg_scores=avg_scores, rec_candidates=rec_candidates,
        slayer_iter_result=slayer_iter_result,
        opp_info_cache=opp_info_cache, focal_moves=focal_moves,
        focal_types=focal_types, ref_atk=ref_atk, ref_def=ref_def,
        ref_iv=ref_iv, opp_iv_mode=opp_iv_mode,
        scores_flat=scores_flat, nS=nS, nO=nO, scenarios=scenarios,
        opponents=opponents, anchor_passing_sink=anchor_passing_sink,
        has_toml_tiers=has_toml_tiers, ranked=ranked,
        hp_list=hp_list, nIvs=nIvs,
        has_bait_axis=has_bait_axis,
    )
    logger.info(f"  Results section rendered in "
                f"{_time.time() - _rr_start:.1f}s")

    # Log envelope-position metric summary (S4). render_results_section
    # stashes per-category metrics on data_obj['envelopePositions'] so
    # the article generator (S6+) can consume them; this log line makes
    # them visible in per-run dive logs for spot-checking.
    _envelope_map = (data_obj.get('envelopePositions') or {}).get(
        str(moveset_idx))
    if _envelope_map:
        for _name, _ep in _envelope_map.items():
            logger.info(
                "  Envelope [%s] %s: mean_delta=%+.2f spread=%.2f "
                "(n=%d, anchors=%d)",
                _ep.get('shape', '?'), _name,
                _ep.get('mean_delta', 0.0), _ep.get('spread', 0.0),
                _ep.get('n_members', 0), _ep.get('n_anchors', 0),
            )

    # ======== IV FLAVOR GUIDE (narrative prose zone) ========
    # Narrative generation is now done per-moveset in the main HTML
    # assembly loop (_generate_narrative_for_moveset), not here.
    # This block only inserts a placeholder marker for the narrative
    # zone so the per-moveset divs can be injected there later.
    sim_marker = '<div class="dd-sim-zone">'
    narrative_placeholder = '<!-- NARRATIVE_ZONE_PLACEHOLDER -->'
    if sim_marker in results_html:
        results_html = results_html.replace(
            sim_marker, narrative_placeholder + sim_marker, 1)

    # ======== ANALYSIS section (behind toggle) ========
    analysis_parts = []

    # -- Collapsible analysis section --
    analysis_parts.append("""
<details class="dd-collapsible" id="dd-analysis">
<summary class="dd-h3" style="cursor:pointer">Deep Dive Analysis</summary>
""")

    # -- Alpha features (banding + clusters) -- hidden by default --
    analysis_parts.append("""
<div style="margin: 8px 0;">
  <label style="font-size:12px;color:#888"><input type="checkbox" id="alpha-chk"
    onchange="var on=this.checked;var d=on?'block':'none';document.getElementById('dd-alpha').style.display=d;var m=document.getElementById('dd-alpha-methods');if(m)m.style.display=d;var cw=document.getElementById('cluster-toggle-wrapper');if(cw)cw.style.display=on?'inline':'none';if(!on){var cc=document.getElementById('cluster-chk');if(cc&&cc.checked){cc.checked=false;if(typeof updateView==='function')updateView();}}"
  > Show experimental analysis (banding, clusters)</label>
</div>
<div id="dd-alpha" style="display:none">
""")
    analysis_parts.append(rendering.render_analysis_alpha_html(
        scores_flat, nIvs, nS, nO, scenarios, opponents, avg_scores,
        hp_list, data_obj, opp_label))
    # -- Close alpha features div --
    analysis_parts.append('</div>\n')

    analysis_parts.append(rendering.render_analysis_volatility_html(
        data_obj, nIvs, nS, scenarios, scene_ranks, avg_ranks, ranked,
        opp_label))

    analysis_parts.append(rendering.render_analysis_flips_html(
        data_obj, flip_summary, flips, avg_scores, ranked, ref_iv,
        opp_label, opp_info_cache, focal_moves, focal_types, ref_atk,
        ref_def, has_bait_axis=has_bait_axis))

    analysis_parts.append(rendering.render_analysis_methods_html(
        nIvs, nS, nO, data_obj, moveset_label, opp_iv_mode, ref_iv,
        opp_label))

    # Close the analysis details element
    analysis_parts.append('</details>\n')
    logger.info(f"  Analysis sections complete (moveset {moveset_idx})")

    return css, results_html, ''.join(analysis_parts)


# ---------------------------------------------------------------------------
# Interactive HTML output
# ---------------------------------------------------------------------------

def _moveset_slug(label: str) -> str:
    """Slugify a moveset label for use in a filename.

    "COUNTER / CLOSE_COMBAT, PAYBACK" → "counter_close_combat_payback"
    """
    import re
    slug = label.lower()
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    return slug.strip('_')


def _filter_moveset_data_for_split(moveset_data, current_idx, reference_idx):
    """Return (filtered_moveset_data, new_reference_idx) for a split-mode file.

    Each split file embeds only the moveset being displayed. The "vs Ref"
    hover diff is intentionally dropped in split mode - the ref moveset's
    scores would need all opp-iv/bait modes embedded to cover mode
    switches, roughly doubling each non-reference file's size (~24 MB →
    ~47 MB for a GL 61-opponent dive). Since these files are for "pick
    a mon to build", and cross-moveset comparisons belong in the
    write-up prose rather than an inline hover diff, skipping the embed
    keeps disk usage roughly flat with the pre-split single file.

    Always returns (``[current_md]``, -1). The helper exists so the
    caller site stays readable and so any future policy change (e.g.
    re-enabling a lightweight single-mode ref embed) has one place to
    live.
    """
    return [moveset_data[current_idx]], -1


def _build_split_file_list(moveset_data, reference_idx, base_html_path):
    """Plan per-moveset output files for --split-movesets.

    Returns a list of dicts, one per moveset, in the order of ``moveset_data``:
        {'url': '...', 'label': '...', 'pretty_label': '...',
         'path': '...',                    # absolute filesystem path
         'moveset_idx': int,                # index into original moveset_data
         'is_reference': bool}

    Naming: moveset 0 (the top-scoring moveset from the Phase 2 ranking)
    always becomes ``{stem}.html``; all others become
    ``{stem}_m{moveset_idx}_{slug}.html``. URLs are relative filenames so
    the dropdown navigates correctly regardless of where the files are
    opened from.

    Landing is decoupled from ``reference_idx`` on purpose: for CD-prep
    dives the reference is typically the *pre-CD* moveset (the
    comparison baseline for "vs Ref" hovers), which is exactly what we
    *don't* want as the landing page - the reader is here to see the
    CD move. moveset 0 is the top-scoring moveset by the same Phase 2
    ordering ``--top-movesets`` uses, which for CD dives is the
    CD-move variant and for non-CD dives is the meta-standard moveset
    (typically equal to reference). The ``is_reference`` flag stays on
    whichever moveset matches ``reference_idx`` so the dropdown can
    tag it, and the "vs Ref" comparison in non-landing files still
    resolves correctly.
    """
    import os as _os
    directory = _os.path.dirname(base_html_path) or '.'
    stem, ext = _os.path.splitext(_os.path.basename(base_html_path))
    landing_idx = 0
    files = []
    for mi, md in enumerate(moveset_data):
        pretty = _pretty_moveset(md['label'])
        ref_tag = ' (reference)' if mi == reference_idx else ''
        if mi == landing_idx:
            fname = f'{stem}{ext}'
        else:
            fname = f'{stem}_m{mi}_{_moveset_slug(md["label"])}{ext}'
        files.append({
            'url': fname,                            # relative - same dir
            'path': _os.path.join(directory, fname),
            'label': md['label'],
            'pretty_label': f'{pretty}{ref_tag}',
            'moveset_idx': mi,
            'is_reference': (mi == reference_idx),
        })
    return files


def generate_interactive_html(species, league, moveset_data, html_path,
                              thresholds=None, opponent_label=None,
                              shield_scenarios=None, opponent_names=None,
                              opp_iv_modes=None, reference_idx=-1,
                              standalone=False, slayer_iter_result=None,
                              cli_args_str=None, has_toml_tiers=False,
                              shadow=False, split_info=None,
                              _precomputed_analysis=None,
                              article_slug='',
                              threshold_registry=None,
                              species_narrative=None,
                              shared_plotly_dir=None):
    """Generate a single-page interactive HTML with JS-driven dropdowns.

    moveset_data: list of dicts, each with:
        'label': str (e.g. "COUNTER / DYNAMIC_PUNCH, ICE_PUNCH")
        'scores': dict of opp_iv_mode -> flat score list (canonical order)
        'meta': canonical_meta list (shared across modes for same moveset)

    split_info: optional dict for --split-movesets mode. When present, the
        moveset dropdown is replaced with a URL-navigating selector that
        jumps between sibling per-moveset HTML files. Shape:
          {'files':  [{'url': '...', 'label': '...', 'pretty_label': '...'}],
           'current': int}    # index into 'files' of the file being written
        The caller is responsible for pre-filtering ``moveset_data`` down to
        this file's slice (typically [current] for the reference file, or
        [current, reference] for non-reference files so the "vs Ref" hover
        diff keeps working).
    """
    opp_iv_modes = opp_iv_modes or ['pvpoke']
    shield_scenarios = shield_scenarios or [(1, 1)]
    opponent_names = opponent_names or []
    n_ivs = len(moveset_data[0]['meta']) if moveset_data else 0
    n_scenarios = len(shield_scenarios)
    n_opponents = len(opponent_names)

    # Reset so each emitted HTML file has its own tooltip lookup; a
    # prior file's entries must not leak into this one.
    rendering.reset_tooltip_registry()

    # Build threshold tier info
    tier_names = list(thresholds.keys()) if thresholds else []
    tier_info = []
    for i, name in enumerate(tier_names):
        color = THRESHOLD_COLORS[i % len(THRESHOLD_COLORS)]
        thresh = thresholds[name]
        tier_info.append({
            'name': name,
            'color': color,
            'attack': thresh['attack'],
            'defense': thresh['defense'],
            'stamina': thresh['stamina'],
            'desc': _threshold_desc(thresh),
            'source': thresh.get('source', ''),
            'toml_description': thresh.get('description', ''),
        })

    # Build the DATA object for JS
    # IV metadata: shared across all movesets (same species = same valid IVs)
    meta = moveset_data[0]['meta']
    iv_a = [m[0] for m in meta]
    iv_d = [m[1] for m in meta]
    iv_s = [m[2] for m in meta]
    iv_lv = [m[3] for m in meta]
    iv_cp = [m[4] for m in meta]
    iv_atk = [round(m[5], 2) for m in meta]
    iv_def = [round(m[6], 2) for m in meta]
    iv_hp = [m[7] for m in meta]
    iv_sp = [round(m[5] * m[6] * m[7], 1) for m in meta]

    # Compute stat product ranks (same for all movesets)
    sp_sorted = sorted(range(n_ivs), key=lambda i: iv_sp[i], reverse=True)
    sp_ranks = [0] * n_ivs
    for rank, idx in enumerate(sp_sorted):
        sp_ranks[idx] = rank + 1

    # Classify IVs by threshold tier
    # iv_tiers: primary tier (most restrictive match, for coloring) - -1 = none
    # iv_all_tiers: list of ALL matching tier indices (for filtering and tables)
    iv_tiers = [-1] * n_ivs
    iv_all_tiers = [[] for _ in range(n_ivs)]
    if thresholds:
        for i in range(n_ivs):
            for ti, (tname, thresh) in enumerate(thresholds.items()):
                meets = True
                if thresh['attack'] > 0 and iv_atk[i] < thresh['attack']:
                    meets = False
                if thresh['defense'] > 0 and iv_def[i] < thresh['defense']:
                    meets = False
                if thresh['stamina'] > 0 and iv_hp[i] < thresh['stamina']:
                    meets = False
                if meets:
                    iv_all_tiers[i].append(ti)
                    if iv_tiers[i] == -1:
                        iv_tiers[i] = ti  # first (most restrictive) match for coloring

    # Find canonical IV indices for the reference IV spreads
    # PvPoke default IVs for this species
    pvpoke_ref_iv_idx = -1
    rank1_ref_iv_idx = -1
    try:
        _lv, da, dd, ds = pvpoke_default_ivs(species, league=league)
        for i in range(n_ivs):
            if iv_a[i] == da and iv_d[i] == dd and iv_s[i] == ds:
                pvpoke_ref_iv_idx = i
                break
    except (ValueError, KeyError):
        pass
    # Rank 1 by stat product
    if n_ivs > 0:
        rank1_ref_iv_idx = min(range(n_ivs), key=lambda i: sp_ranks[i])

    data_obj = {
        'species': species,
        'league': league,
        'cpCap': LEAGUE_CAPS[league],
        'nIvs': n_ivs,
        'nScenarios': n_scenarios,
        'nOpponents': n_opponents,
        'scenarios': [[s0, s1] for s0, s1 in shield_scenarios],
        'opponents': opponent_names,
        # Indices into opponent_names whose species matches the focal
        # species (i.e., the mirror entry, or both forms when a pool
        # carries both normal + shadow of self). Used client-side by
        # the "Matchups Kept" column to exclude mirror matchups from
        # the denominator; the mirror axis is already covered by
        # Mirror Slayer CMP %, and counting it in Matchups Kept double-
        # counts the same tradeoff.
        'mirrorOppIdxs': [
            _i for _i, _n in enumerate(opponent_names)
            if parse_opponent_spec(_n)[0] == species
        ],
        'oppIvModes': opp_iv_modes,
        'opponentLabel': opponent_label or 'PvPoke rankings',
        'referenceIdx': reference_idx,
        'tiers': tier_info,
        'movesets': [{'label': md['label'], 'prettyLabel': _pretty_moveset(md['label'])} for md in moveset_data],
        # Reference IV indices (for matchup diff in hover text)
        'pvpokeRefIvIdx': pvpoke_ref_iv_idx,
        'rank1RefIvIdx': rank1_ref_iv_idx,
        # IV metadata
        'ivA': iv_a, 'ivD': iv_d, 'ivS': iv_s,
        'ivLv': iv_lv, 'ivCp': iv_cp,
        'ivAtk': iv_atk, 'ivDef': iv_def, 'ivHp': iv_hp,
        'ivSp': iv_sp, 'spRanks': sp_ranks, 'ivTiers': iv_tiers, 'ivAllTiers': iv_all_tiers,
    }

    # Score arrays: one per (moveset_idx, opp_iv_mode)
    score_arrays = {}
    for mi, md in enumerate(moveset_data):
        for mode in opp_iv_modes:
            key = f'{mi}_{mode}'
            score_arrays[key] = md['scores'][mode]

    # Compute cluster gap Y-values per (moveset, opp_iv_mode, scenario)
    # These are the score thresholds where significant gaps appear in the
    # sorted score distribution. Used by JS to draw horizontal lines on the plot.
    cluster_gaps = {}  # key: "mi_mode" -> list of lists (one per scenario)
    for mi, md in enumerate(moveset_data):
        for mode in opp_iv_modes:
            key = f'{mi}_{mode}'
            sf = score_arrays[key]
            per_scenario = []
            for si in range(n_scenarios):
                # Compute per-IV average score for this scenario
                scene_scores = []
                for iv in range(n_ivs):
                    base = iv * n_scenarios * n_opponents + si * n_opponents
                    total = sum(sf[base + oi] for oi in range(n_opponents))
                    scene_scores.append(total / n_opponents)
                # Sort descending, find gaps
                sorted_sc = sorted(scene_scores, reverse=True)
                gaps = [sorted_sc[i-1] - sorted_sc[i] for i in range(1, len(sorted_sc))]
                if gaps:
                    gap_sorted = sorted(gaps)
                    median_gap = gap_sorted[len(gap_sorted) // 2]
                    # Gap Y-values: the score BELOW the gap (i.e. the top of the lower cluster)
                    sig = []
                    for i, g in enumerate(gaps):
                        if g > 3 * median_gap and i < n_ivs // 4:
                            sig.append(round(sorted_sc[i+1], 1))  # score just below the gap
                    per_scenario.append(sig[:5])  # max 5 gaps per scenario
                else:
                    per_scenario.append([])
            cluster_gaps[key] = per_scenario
    data_obj['clusterGaps'] = cluster_gaps

    # Slayer IV overlay: extract canonical IV indices that landed in any
    # slayer category from the iterative-slayer-discovery result. Rendered
    # as a separate legend entry on the scatter plot with a distinct
    # marker shape (star-diamond) so users can see what avg-score trade
    # a "slayer-quality" spread costs vs the avg-score-optimal cluster.
    # Slayer membership is fundamentally a different optimization target
    # than avg score (mirror-match wins under even-strict), so the two
    # often don't coincide - visualizing the gap is the whole point.
    # The slayer iteration stores ``iv`` as a (a_iv, d_iv, s_iv) triple
    # (see line ~529 in iterative_slayer_discovery), but the JS plot
    # indexes IVs by their canonical position in iv_a/iv_d/iv_s. Build a
    # reverse lookup so we can translate triples → canonical indices.
    iv_idx_by_triple = {(iv_a[i], iv_d[i], iv_s[i]): i for i in range(n_ivs)}
    slayer_cats_by_idx: dict = {}
    if slayer_iter_result and slayer_iter_result.get('categories'):
        for cat_name, cat_rows in slayer_iter_result['categories'].items():
            for r in (cat_rows or []):
                iv_triple = r.get('iv')
                if iv_triple is None:
                    continue
                idx = iv_idx_by_triple.get(tuple(iv_triple))
                if idx is None:
                    continue
                slayer_cats_by_idx.setdefault(idx, []).append(cat_name)
    data_obj['slayerIvs'] = sorted(slayer_cats_by_idx.keys())
    # Stringify keys so json.dumps emits a clean JS object (JS treats
    # both numeric and string keys identically for object access).
    data_obj['slayerCatsByIv'] = {
        str(idx): sorted(set(cats)) for idx, cats in slayer_cats_by_idx.items()
    }

    # Mirror CMP cohort: atk values of the Nash-converged survivor pool
    # from --mirror-slayer. Used by the JS to compute each IV's
    # "Mirror CMP %" (fraction of cohort members this IV beats at CMP).
    # Sorted ascending for binary-search-friendly lookup. Emits an empty
    # list when --mirror-slayer wasn't requested or converged to nothing;
    # the JS guards on length so absent data silently skips the CMP column.
    mirror_cohort_atk = []
    if slayer_iter_result and slayer_iter_result.get('final'):
        mirror_cohort_atk = sorted(
            float(s['atk']) for s in slayer_iter_result['final']
            if s.get('atk') is not None
        )
    data_obj['mirrorCohortAtk'] = mirror_cohort_atk

    # Anchor-clear IV overlay: union the canonical IV indices that pass
    # any anchor for which _aggregate_flips_by_anchor emitted a record.
    # The aggregator runs again inside generate_analysis_sections for
    # the bullet rendering - running it here too is cheap and avoids
    # plumbing its output through a side channel. Per-IV "which anchors
    # cleared" data populates the hover tooltip.
    #
    # Only fires when slayer iteration is on (resolved_anchors come from
    # slayer_iter_result); without --mirror-slayer the anchor-clear
    # overlay is silently empty. See TODO entry "RyanSwag-style matchup
    # flip annotations" for the longer-term plan to surface anchors
    # without requiring a slayer iteration.
    # Selectivity gate: an anchor counts toward overlay membership only
    # if it's "actually selective" - i.e., passed by less than half the
    # IV pool. The bullets layer keeps all emitted anchors (an
    # easy-to-clear breakpoint is still informational about where the
    # damage tier lands), but for the overlay, "every IV clears
    # something" is degenerate noise. Without this filter, e.g. a
    # Lickilicky Hyper Beam bulkpoint at def 96.62 - which essentially
    # every spread satisfies - would mark every point on the scatter
    # as anchor-cleared and defeat the highlighting purpose.
    SELECTIVITY_MAX_PASS_RATE = 0.5
    if _precomputed_analysis is not None and 'anchorClearIvs' in _precomputed_analysis:
        data_obj['anchorClearIvs'] = _precomputed_analysis['anchorClearIvs']
        data_obj['anchorClearByIv'] = _precomputed_analysis['anchorClearByIv']
    else:
        anchor_cleared_by_idx: dict = {}
        if slayer_iter_result:
            ra = slayer_iter_result.get('resolved_anchors', []) or []
            if ra:
                mset_key = f'0_{opp_iv_modes[0]}'
                sf = score_arrays.get(mset_key, [])
                if sf:
                    # Build a stub data_obj-shaped dict the aggregator can read.
                    # It only needs ivAtk/ivDef.
                    stub = {'ivAtk': iv_atk, 'ivDef': iv_def}
                    records = _aggregate_flips_by_anchor(
                        sf, n_ivs, n_scenarios, n_opponents,
                        ra, stub, shield_scenarios, opponent_names,
                    )
                    for rec in records:
                        passing = rec.get('passing_ivs', [])
                        if not passing:
                            continue
                        pass_rate = len(passing) / n_ivs if n_ivs else 0.0
                        if pass_rate > SELECTIVITY_MAX_PASS_RATE:
                            continue  # too easy - skip for overlay purposes
                        label = (rec['anchor'].parent_display_name
                                 or rec['anchor'].label
                                 or rec['anchor'].parent)
                        for iv in passing:
                            anchor_cleared_by_idx.setdefault(iv, set()).add(label)
        data_obj['anchorClearIvs'] = sorted(anchor_cleared_by_idx.keys())
        data_obj['anchorClearByIv'] = {
            str(idx): sorted(labels) for idx, labels in anchor_cleared_by_idx.items()
        }
        if _precomputed_analysis is not None:
            _precomputed_analysis['anchorClearIvs'] = data_obj['anchorClearIvs']
            _precomputed_analysis['anchorClearByIv'] = data_obj['anchorClearByIv']

    # ---- Wins-based y-axis data ----
    # The interactive scatter's y-axis defaults to avg battle score, but
    # users want alternative metrics that count *how many matchups
    # this IV wins* under different opponent assumptions. Slayer IVs in
    # particular don't appear at the top of the avg-score-ranked plot
    # (they optimize a different target - mirror-match wins under
    # even-strict), so a wins-based axis makes that cohort visible.
    #
    # Three wins modes are exposed in addition to avg score:
    #   * winsPvpoke: count of (opp, scenario) pairs the IV wins vs the
    #     PvPoke-default opponent IV cohort. Always available.
    #   * winsRank1: same but vs rank-1-stat-product opponents. Only
    #     available if --opp-ivs is rank1 or both.
    #   * winsMirror: total mirror-match wins from the slayer iteration's
    #     final round. SPARSE - only the ~tens of slayer survivors have
    #     a value here; all other IVs are dropped from the plot when
    #     this mode is active.
    mirror_wins_by_idx: dict = {}
    mirror_wins_max = 0
    if slayer_iter_result and slayer_iter_result.get('final'):
        for r in slayer_iter_result['final']:
            iv_triple = r.get('iv')
            wins = r.get('total_wins', 0)
            if iv_triple is None:
                continue
            idx = iv_idx_by_triple.get(tuple(iv_triple))
            if idx is None:
                continue
            mirror_wins_by_idx[idx] = wins
            if wins > mirror_wins_max:
                mirror_wins_max = wins
    data_obj['mirrorWinsByIv'] = {
        str(idx): wins for idx, wins in mirror_wins_by_idx.items()
    }
    data_obj['mirrorWinsMax'] = mirror_wins_max

    # Build the y-axis mode list. Each entry: (id, label, max_value).
    # max_value is the theoretical max wins so hover text can show
    # "X / N" for the wins modes. avgScore has no max in that sense.
    y_axis_modes = [
        {'id': 'avgScore', 'label': 'Avg Battle Score', 'maxValue': None},
    ]
    if 'pvpoke' in opp_iv_modes:
        y_axis_modes.append({
            'id': 'winsPvpoke',
            'label': 'Wins vs PvPoke default',
            'maxValue': n_scenarios * n_opponents,
        })
    if 'rank1' in opp_iv_modes:
        y_axis_modes.append({
            'id': 'winsRank1',
            'label': 'Wins vs rank 1',
            'maxValue': n_scenarios * n_opponents,
        })
    if mirror_wins_by_idx:
        y_axis_modes.append({
            'id': 'winsMirror',
            'label': 'Wins vs mirror cohort',
            'maxValue': mirror_wins_max,
        })
    data_obj['yAxisModes'] = y_axis_modes

    opp_desc = opponent_label or 'PvPoke rankings'
    shield_desc = ', '.join(f'{s0}v{s1}' for s0, s1 in shield_scenarios)

    # Bait-mode meta annotation for the page header. Three cases:
    #  - all bait-on        → empty string, header unchanged
    #  - all bait-off       → " | Bait: off" (whole-dive mode)
    #  - mixed (axis active) → " | Bait: on/off selector" (driven by dropdown)
    _bait_axis_values = {parse_mode(m)[1] for m in (opp_iv_modes or ['pvpoke'])}
    if _bait_axis_values == {'nobait'}:
        _bait_meta = ' | <b style="color:#e94560">Bait: OFF</b>'
    else:
        _bait_meta = ''

    # ---- User-collection support data ----
    #
    # Everything the browser-side JS port of user_collection.py needs to
    # parse the user's Poke Genie CSV and match it against this dive's
    # auto-derived tiers - without any server round-trip and without
    # loading the full gamemaster on the client. The JS module lives at
    # scripts/deep_dive_user_collection.js and is injected into the HTML
    # alongside the engine JS. Keys mirror the Python API 1:1.
    #
    # The shadow flag controls three things:
    #   * speciesKey: 'Tinkaton' vs 'Tinkaton (Shadow)' - this is the
    #     threshold-dict key the JS builds on CSV load. A user's shadow
    #     Tinkaton in the CSV resolves via get_species_name to
    #     'Tinkaton (Shadow)', which must match the speciesKey we picked
    #     for the dive.
    #   * which gamemaster entry supplies base stats (non-shadow and
    #     shadow share base stats in PvPoke's gamemaster, but we key on
    #     the same name consistently so the matcher's dict lookups work).
    #   * which shadow branch of the rank lookup we precompute.
    from gopvpsim.evolution_lines import _load_pre_to_finals
    from gopvpsim.pokemon import (
        CPM as _CPM, SHADOW_ATK_BONUS as _SAB, SHADOW_DEF_MULT as _SDM,
        get_pokemon_index as _get_pkidx,
    )
    from gopvpsim.user_collection import compute_rank_lookup as _rank_lookup
    _collection_species_key = f'{species} (Shadow)' if shadow else species
    _collection_data = None
    _pkidx = _get_pkidx()
    if _collection_species_key in _pkidx:
        _base = _pkidx[_collection_species_key]
        # Pre-evo subset: only keys whose list of possible final forms
        # includes THIS dive's species. For a Tinkaton dive, that gives
        # {Tinkatink: [Tinkaton], Tinkatuff: [Tinkaton], Tinkaton: [Tinkaton]}.
        # Branching pre-evos (Eevee → 8 eeveelutions) contribute only if
        # the dive is one of the branches - e.g. an Umbreon dive gets
        # {Eevee: [Umbreon], Umbreon: [Umbreon]} rather than the full 8.
        _pre_to_finals_full = _load_pre_to_finals()
        _pre_to_finals_subset = {}
        for _pre, _finals in _pre_to_finals_full.items():
            _relevant = [_f for _f in _finals if _f == _collection_species_key]
            if _relevant:
                _pre_to_finals_subset[_pre] = _relevant
        # Rank lookup: {'normal' or 'shadow' → {ivKey → rank}}. The JS
        # matcher reads from this to populate stats.rank, which in turn
        # powers the hover display and any 'onlytop' target in the
        # future. Scope is small (one species, 4096 IVs).
        _ranked = _rank_lookup(
            _collection_species_key, league=league,
            max_level=LEAGUE_MAX_LEVEL.get(league, 51.0), shadow=shadow)
        _rank_shadow_key = 'shadow' if shadow else 'normal'
        _rank_table = {f'{a},{d},{s}': r for (a, d, s), r in _ranked.items()}
        # Build the threshold dict in the same shape Python's match_mons
        # expects, from the tier info already computed above. This is
        # the dict the JS constructs at CSV-load time; we could build
        # it in JS instead but pre-baking here keeps the JS simpler and
        # guarantees identical behavior to match_mons' dict-schema path.
        _league_label = league.capitalize()
        _collection_thresholds = {
            _collection_species_key: {
                _league_label: {
                    t['name']: {
                        'attack':  t['attack'],
                        'defense': t['defense'],
                        'stamina': t['stamina'],
                    }
                    for t in tier_info
                }
            }
        }
        _collection_data = {
            'speciesKey':      _collection_species_key,
            'isShadow':        shadow,
            'leagueLabel':     _league_label,
            'leagueCap':       LEAGUE_CAPS[league],
            'maxLevel':        51.0,
            'shadowAtkBonus':  _SAB,
            'shadowDefMult':   _SDM,
            # CPM table: keys are stringified floats so json.dumps emits
            # a regular JS object. The JS module's cpmAt() handles both
            # '50' and '50.0' key variants.
            'cpm':             {str(k): v for k, v in _CPM.items()},
            'pokemonIndex': {
                _collection_species_key: {
                    'atk': _base['atk'], 'def': _base['def'], 'hp': _base['hp'],
                }
            },
            'preToFinals':     _pre_to_finals_subset,
            'rankLookup':      {_collection_species_key: {_rank_shadow_key: _rank_table}},
            'thresholds':      _collection_thresholds,
            'tierNames':       [t['name'] for t in tier_info],
        }
    data_obj['collection'] = _collection_data

    # --- Build HTML ---
    plotly_tag = _plotly_script_tag(standalone, shared_plotly_dir, html_path)
    # Embed the equivalent CLI invocation as an HTML comment near the top so
    # `grep '<!-- CLI:' file.html` works for forensic comparison without
    # adding visible page chrome.
    cli_comment = ''
    if cli_args_str:
        from html import escape as _esc_cmt
        cli_comment = f'<!-- CLI: {_esc_cmt(cli_args_str)} -->\n'

    html = f"""<!DOCTYPE html>
{cli_comment}<html>
<head>
<meta charset="utf-8">
<title>{species} {league.title()} League IV Deep Dive</title>
{plotly_tag}
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 20px; background: #1a1a2e; color: #e0e0e0; }}
  h1 {{ color: #e94560; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 15px; }}
  details.meta {{ cursor: pointer; }}
  details.meta summary {{ color: #888; font-size: 13px; }}
  .controls {{ background: #16213e; padding: 10px 14px; border-radius: 6px;
               margin-bottom: 15px; display: flex; gap: 18px; align-items: center;
               flex-wrap: wrap; }}
  .controls label {{ font-size: 13px; color: #aaa; }}
  .controls select {{ background: #0f3460; color: #e0e0e0; border: 1px solid #1a3a6e;
                      padding: 4px 8px; border-radius: 4px; font-size: 13px; }}
  .plot-container {{ margin-bottom: 20px; }}
  .summary {{ background: #16213e; padding: 12px; border-radius: 6px;
              margin-bottom: 20px; font-size: 13px; overflow-x: auto; }}
  .summary table {{ border-collapse: collapse; width: 100%; }}
  .summary th, .summary td {{ text-align: left; padding: 3px 8px;
                               border-bottom: 1px solid #0f3460; }}
  .summary td {{ white-space: nowrap; }}
  .summary th {{ color: #e94560; white-space: normal; vertical-align: bottom; }}
  .tier-badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px;
                 font-size: 11px; font-weight: bold; }}
  .threshold-info {{ background: #16213e; padding: 10px; border-radius: 6px;
                     margin-bottom: 15px; font-size: 13px; }}
  .threshold-info span {{ font-weight: bold; }}
  .methodology {{ color: #888; font-size: 12px; max-width: 800px;
                  margin: 10px 0 30px 0; line-height: 1.6; }}
  details.collection-panel {{ background: #16213e; padding: 10px 14px;
                              border-radius: 6px; margin-bottom: 15px; }}
  details.collection-panel > summary {{ cursor: pointer; color: #e0e0e0;
                                         font-size: 13px; }}
  .collection-body {{ margin-top: 10px; }}
  .collection-instructions {{ font-size: 12px; color: #aaa;
                              margin-bottom: 8px; line-height: 1.5; }}
  #collection-csv {{ width: 100%; background: #0f3460; color: #e0e0e0;
                     border: 1px solid #1a3a6e; border-radius: 4px;
                     padding: 6px 8px; font-size: 11px;
                     font-family: monospace; resize: vertical;
                     box-sizing: border-box; }}
  .collection-buttons {{ display: flex; gap: 8px; align-items: center;
                         margin-top: 8px; flex-wrap: wrap; }}
  .collection-buttons button {{ background: #0f3460; color: #e0e0e0;
                                border: 1px solid #1a3a6e; border-radius: 4px;
                                padding: 4px 10px; font-size: 12px;
                                cursor: pointer; }}
  .collection-buttons button:hover {{ background: #1a3a6e; }}
  .collection-matches {{ margin-top: 12px; }}
  .collection-matches h5 {{ margin: 8px 0 4px 0; font-size: 12px;
                             color: #e0e0e0; font-weight: 600; }}
  .collection-matches table {{ border-collapse: collapse; font-size: 11px;
                                color: #e0e0e0; width: auto; }}
  .collection-matches th, .collection-matches td {{ padding: 2px 10px 2px 0;
                                                     text-align: left; }}
  /* Body cells stay on one line by default (keeps numeric columns tidy);
     headers wrap so long labels like "Top-Mirror CMP %" don't blow the
     column width out. Column widths are set by the body cells. */
  .collection-matches td {{ white-space: nowrap; }}
  .collection-matches th {{ color: #888; font-weight: 500;
                             border-bottom: 1px solid #0f3460;
                             white-space: normal;
                             vertical-align: bottom; }}
  /* Opt-in wrap class for prose-heavy columns (Slayer type, Also in).
     Applied via the extras 'cls' hint so only the targeted columns wrap.
     No word-break override so "Jirachi" stays "Jirachi", not "Jir\\nachi". */
  .collection-matches td.wrap {{ white-space: normal; max-width: 22em; }}
  .collection-matches tr.lucky td {{ color: #ffd966; }}
  .collection-matches tr.shadow td {{ color: #b084e0; }}
  .collection-matches td.rank {{ color: #9be89b; font-weight: 600; }}
  .collection-matches td.rank-sp {{ color: #6c7a89; }}
  .collection-matches tr.matches-hidden-row {{ display: none; }}
  .matches-toggle-btn {{ background: #0f3460; color: #9be89b;
                         border: 1px solid #1a3a6e; border-radius: 4px;
                         padding: 3px 10px; font-size: 11px; cursor: pointer;
                         margin: 4px 0 8px 0; }}
  .matches-toggle-btn:hover {{ background: #1a3a6e; }}
  span.user-anchor-hits {{ font-size: 11px; font-style: italic;
                           margin-left: 6px; }}
</style>
</head>
<body>
<h1>{species} - {league.title()} League IV Deep Dive</h1>
<p class="meta">Opponents: {opp_desc}
| Shield scenario(s): {shield_desc} | Policy: pvpoke_dp{_bait_meta}</p>
"""

    # Related article link (bidirectional link contract: docs/article_schema.md)
    if article_slug:
        _article_link = f'../articles/{article_slug}/'
        _articles_dir = Path(html_path).resolve().parent.parent / 'articles' / article_slug
        _article_meta = _articles_dir / 'meta.toml'
        if _article_meta.exists():
            import tomllib as _tl
            with open(_article_meta, 'rb') as _f:
                _am = _tl.load(_f)
            _article_title = _am.get('title', 'Community Day Article')
            _authorship = _am.get('authorship', 'auto')
        else:
            _article_title = f'{species} Community Day Article'
            _authorship = 'auto'
        # Label and color match the article's authorship level
        if _authorship == 'expert':
            _link_label = 'Expert Analysis'
            _border_color = '#d4a017'  # gold
        elif _authorship == 'both':
            _link_label = 'Analysis'
            _border_color = '#7db87d'  # green
        else:
            _link_label = 'Related Article'
            _border_color = '#5b8dd9'  # blue
        html += (
            '<div style="background:#16213e;padding:12px 16px;border-radius:6px;'
            f'margin:10px 0;border-left:3px solid {_border_color}">'
            f'{_link_label}: <a href="{_article_link}">{_article_title}</a>'
            '</div>\n'
        )

    # Opponent list
    if opponent_names:
        html += '<details class="meta"><summary>Opponent list '
        html += f'({len(opponent_names)} mons)</summary><p style="margin:4px 0 8px 12px">'
        html += ', '.join(opponent_names)
        html += '</p></details>\n'

    # Species narrative (Shape 2 migration): free-form expert-authored
    # prose sourced from thresholds/<species>.toml's
    # [Species.intro] / [Species.meta_role] / [Species.verdict] blocks.
    # Renders above the dashboard so a reader gets the "why should I
    # care" before the interactive scatter (RyanSwag-style). Silent
    # no-op when no blocks are populated - most species today.
    if species_narrative:
        html += rendering.render_species_narrative(species_narrative)

    # Threshold info folded into controls (legend shows tier name + desc)
    # No separate threshold-info box needed - graph legend has full detail

    # Controls
    html += '<div class="controls">\n'
    if split_info is not None:
        # URL-navigating dropdown: onchange jumps to a sibling HTML file
        # for the selected moveset. Uses a distinct id ('moveset-nav-sel')
        # so the engine's updateView() - which looks up 'moveset-sel' and
        # parseInt()'s its value - stays quiet and leaves state.movesetIdx
        # at its default (0, the current-file moveset). The CSV paste-box
        # state lives in this page's DOM and is lost on navigation; we
        # flag that inline next to the selector rather than trying to
        # persist it across files.
        cur = split_info['current']
        html += '  <label>Moveset: <select id="moveset-nav-sel" onchange="if(this.value)window.location.href=this.value">\n'
        for fi, finfo in enumerate(split_info['files']):
            sel = ' selected' if fi == cur else ''
            html += (f'    <option value="{finfo["url"]}"{sel}>'
                     f'{finfo["pretty_label"]}</option>\n')
        html += '  </select></label>\n'
        html += ('  <span style="font-size:11px;color:#888">'
                 'Switching movesets reloads the page; pasted CSV will need to be re-loaded.'
                 '</span>\n')
    elif len(moveset_data) > 1:
        html += '  <label>Moveset: <select id="moveset-sel" onchange="updateView()">\n'
        for mi, md in enumerate(moveset_data):
            ref_tag = ' (reference)' if mi == reference_idx else ''
            html += f'    <option value="{mi}">{_pretty_moveset(md["label"])}{ref_tag}</option>\n'
        html += '  </select></label>\n'

    if n_scenarios > 1:
        html += '  <label>Shields: <select id="scenario-sel" onchange="updateView()">\n'
        html += '    <option value="avg">All (avg)</option>\n'
        for si, (s0, s1) in enumerate(shield_scenarios):
            sel = ' selected' if n_scenarios == 1 else ''
            html += f'    <option value="{si}"{sel}>{s0}v{s1}</option>\n'
        html += '  </select></label>\n'

    if len(opp_iv_modes) > 1:
        _base_modes = list(dict.fromkeys(
            parse_mode(m)[0] for m in opp_iv_modes))
        _has_bait_axis = ('nobait' in _bait_axis_values
                          and 'bait' in _bait_axis_values)
        _has_oppiv_axis = len(_base_modes) > 1
        if _has_oppiv_axis:
            html += ('  <label>Opponent IVs: '
                     '<select id="oppiv-sel" onchange="updateView()">\n')
            _oppiv_labels = {'pvpoke': 'PvPoke Defaults',
                             'rank1': 'Rank 1'}
            for base in _base_modes:
                lbl = _oppiv_labels.get(base, base)
                html += f'    <option value="{base}">{lbl}</option>\n'
            html += '  </select></label>\n'
        if _has_bait_axis:
            html += ('  <label>Bait: '
                     '<select id="bait-sel" onchange="updateView()">\n')
            html += '    <option value="bait">Selective</option>\n'
            html += '    <option value="nobait">Never</option>\n'
            html += '  </select></label>\n'
    if len(y_axis_modes) > 1:
        html += '  <label>Y-axis: <select id="yaxis-sel" onchange="updateView()">\n'
        for ym in y_axis_modes:
            html += f'    <option value="{ym["id"]}">{ym["label"]}</option>\n'
        html += '  </select></label>\n'
    html += '  <label>Color: <select id="color-sel" onchange="updateView()">\n'
    html += '    <option value="threshold">Threshold tiers</option>\n'
    html += '    <option value="hp">HP</option>\n'
    html += '    <option value="def">Defense</option>\n'
    html += '    <option value="atk">Attack</option>\n'
    html += '    <option value="score">Score</option>\n'
    html += '  </select></label>\n'
    # Anchor IVs overlay mode: 'filled' is the shipped subdued cyan blob;
    # 'outline' swaps fill for ring markers so the envelope edge reads
    # clearly and named-category traces riding the top/bottom show up
    # against it instead of fighting the fill.
    html += '  <label>Anchors: <select id="anchor-display-sel" onchange="updateView()">\n'
    html += '    <option value="filled">Filled</option>\n'
    html += '    <option value="outline">Outline</option>\n'
    html += '  </select></label>\n'
    # (Highlight IVs input lives directly below the plot, right-aligned
    # under the legend, so the user's eye doesn't jump from the plot
    # back up to the control strip to pin a specific IV.)
    # (Top-IVs table controls live next to the table itself - see the
    # control strip rendered just before <div id="summary"> below.)
    # "Show clusters" is gated behind the experimental-analysis toggle
    # in the Deep Dive Analysis section - hidden by default, revealed
    # when the user opts into experimental output. The wrapper span is
    # toggled by the alpha-chk onchange handler below (in the analysis
    # sections block).
    html += '  <span id="cluster-toggle-wrapper" style="display:none"><label style="font-size:12px;color:#aaa"><input type="checkbox" id="cluster-chk" onchange="updateView()" style="margin-left:12px"> Show clusters</label></span>\n'
    if thresholds:
        html += '  <span style="font-size:11px;color:#888;margin-left:8px">Threshold tiers (e.g. GH Great / GH Good) are expert stat-cutoff regions defined in <a href="#dd-threshold-tiers" style="color:#58a6ff">Threshold Tiers</a> below. Hover legend to isolate; click to lock.</span>\n'
    html += '</div>\n'

    # "Your collection" paste-box. Hidden (display:none) until DOMContentLoaded
    # - the engine JS reveals it only if DATA.collection was populated
    # (i.e. the dive species was found in the gamemaster). Privacy note
    # reinforces that no upload happens; the textarea + FileReader both
    # run fully client-side.
    if _collection_data is not None:
        html += (
            '<details id="collection-panel" class="collection-panel" open>\n'
            '  <summary><b>Check my collection</b> '
            '<span style="font-size:11px;color:#888">'
            '- Your collection stays in your browser; nothing is uploaded.'
            '</span></summary>\n'
            '  <div class="collection-body">\n'
            '    <div class="collection-instructions">\n'
            '      Paste your Poke Genie CSV export below, or click '
            '<b>Choose file\u2026</b> to load one from disk. '
            'You\u2019ll see which of your '
            f'{species}{"s" if not species.endswith("s") else ""} '
            '(and pre-evolutions) qualify for each tier, overlaid on the '
            'scatter plot.\n'
            '    </div>\n'
            '    <textarea id="collection-csv" rows="4" '
            'placeholder="Paste CSV here (first row: Name,Form,CP,...)"></textarea>\n'
            '    <div class="collection-buttons">\n'
            '      <button id="collection-load-btn" type="button">Load</button>\n'
            '      <button id="collection-file-btn" type="button">Choose file\u2026</button>\n'
            '      <input id="collection-file-input" type="file" accept=".csv,text/csv" '
            'style="display:none">\n'
            '      <button id="collection-clear-btn" type="button">Clear</button>\n'
            '      <label style="font-size:12px;color:#aaa">'
            '<input type="checkbox" id="collection-only-chk"> Show only my mons'
            '</label>\n'
            '      <span id="collection-status" '
            'style="font-size:12px;color:#aaa;margin-left:6px"></span>\n'
            '    </div>\n'
            '    <div class="collection-manual" '
            'style="margin-top:10px;border-top:1px solid #24314d;padding-top:10px">\n'
            '      <div style="font-size:12px;color:#aaa;margin-bottom:6px">\n'
            '        <b>Or enter one at a time</b> - Atk/Def/HP IVs (0-15), '
            'level, shadow flag. Same format as PvPoke / PvPIVs.\n'
            '      </div>\n'
            '      <div style="display:flex;flex-wrap:wrap;gap:8px;'
            'align-items:center;font-size:12px">\n'
            '        <label>Species <select id="manual-species" '
            'style="font-size:12px"></select></label>\n'
            '        <label>Atk <input id="manual-atk" type="number" '
            'min="0" max="15" value="0" style="width:48px"></label>\n'
            '        <label>Def <input id="manual-def" type="number" '
            'min="0" max="15" value="15" style="width:48px"></label>\n'
            '        <label>HP <input id="manual-hp" type="number" '
            'min="0" max="15" value="15" style="width:48px"></label>\n'
            '        <label>Level <input id="manual-level" type="number" '
            'min="1" max="51" step="0.5" value="50" style="width:60px"></label>\n'
            '        <label><input id="manual-shadow" type="checkbox"> '
            'Shadow</label>\n'
            '        <button id="manual-add-btn" type="button">Add</button>\n'
            '      </div>\n'
            '      <div id="manual-list" '
            'style="margin-top:6px;font-size:12px;color:#c9d1d9"></div>\n'
            '    </div>\n'
            '    <div id="collection-matches" class="collection-matches"></div>\n'
            '  </div>\n'
            '</details>\n'
        )

    # Plot first, then summary table below
    html += '<div id="plot" class="plot-container" style="height:550px;"></div>\n'
    # Highlight-IVs strip, right-aligned directly below the plot so it
    # sits under the legend column visually. Enter applies, Escape
    # clears (keydown handler on the input); buttons are mouse-friendly
    # fallbacks. Accepts a comma-separated list of triples in "a/d/s"
    # form (also "-" or whitespace separated). Matching IVs render as
    # red diamonds on top and the rest of the plot dims to ~30% opacity.
    # Orthogonal to the collection paste-box - this is an ad-hoc "pin
    # these to the plot" tool, not a persistent user collection.
    html += (
        '<div class="highlight-strip" '
        'style="display:flex;justify-content:flex-end;align-items:center;'
        'gap:4px;margin:6px 20px 0 0;font-size:12px;color:#c9d1d9">\n'
        '  <label style="display:flex;align-items:center;gap:4px">'
        'Highlight IVs: '
        '<input id="highlight-input" type="text" '
        'placeholder="e.g. 15/11/11, 15/14/8" '
        'style="width:200px;font-size:12px" '
        'onkeydown="if(event.key===\'Enter\'){applyHighlight();event.preventDefault();} '
        'else if(event.key===\'Escape\'){clearHighlight();event.preventDefault();}">'
        '</label>\n'
        '  <button type="button" onclick="applyHighlight()" '
        'style="font-size:11px;padding:2px 8px">Apply</button>\n'
        '  <button type="button" onclick="clearHighlight()" '
        'style="font-size:11px;padding:2px 8px">Clear</button>\n'
        '  <span id="highlight-status" '
        'style="font-size:11px;color:#aaa;margin-left:8px"></span>\n'
        '</div>\n'
    )
    # Top-IVs table controls. Sit immediately above the table they
    # affect (the #summary div). The "Sort by" UX is column-header
    # clicks (see _summarySortClick in deep_dive_engine.js); only the
    # row-count selector lives here.
    html += '<div class="summary-controls" style="margin:10px 0 4px 0;font-size:0.9rem;color:#c9d1d9">\n'
    html += '  <b style="color:#58a6ff">Top IVs</b>\n'
    html += '  <label style="margin-left:12px">Rows: <select id="summary-n-sel" onchange="updateSummaryTable()">\n'
    html += '    <option value="10">10</option>\n'
    html += '    <option value="25">25</option>\n'
    html += '    <option value="50">50</option>\n'
    html += '    <option value="100">100</option>\n'
    html += '  </select></label>\n'
    html += ('  <span style="margin-left:10px;font-size:11px;color:#888">'
             "Ranked by this dive's battle simulation (not fetched from "
             'PvPoke). Click any column header to sort.</span>\n')
    html += '</div>\n'
    html += '<div id="summary" class="summary"></div>\n'

    # Methodology footer
    html += '<div id="methodology" class="methodology"></div>\n'

    # Battle-rating histogram. One block per moveset, but only the
    # active moveset is visible at any time (mirrors the narrative-zone
    # display-swap at dd-narrative-moveset). Bins the reference IV's
    # per-matchup scores (opponent x scenario, under the active
    # Shields/Opponent-IVs/Bait state) so the shape is comparable to
    # PvPoke's multi-battle histogram. Anchor ids (`histogram-<slug>`)
    # stay per-moveset so articles can deep-link, and a small hook on
    # page load switches the moveset dropdown to the anchored moveset.
    html += ('<section class="histogram-section" '
             'style="margin:20px 0">\n')
    html += ('<h3 style="color:#58a6ff;margin:0 0 6px 0;'
             'font-size:1.0rem">Battle-Rating Distribution</h3>\n')
    html += ('<p style="font-size:12px;color:#aaa;margin:0 0 10px 0">'
             'Per-matchup battle-rating distribution for the reference '
             'IV (PvPoke default or Rank 1, matching the Opponent-IVs '
             'dropdown) across the opponent pool, under the currently-'
             'selected Shields / Opponent-IVs / Bait.</p>\n')
    for _mi, _md in enumerate(moveset_data):
        _slug = _moveset_slug(_md['label'])
        _pretty = _pretty_moveset(_md['label'])
        _vis = 'block' if _mi == 0 else 'none'
        # max-width keeps the plot from stretching across the full page
        # on wide monitors - narrower histograms read better and match
        # PvPoke's visual density.
        html += (
            f'<div id="histogram-{_slug}" class="dd-histogram-moveset" '
            f'data-moveset="{_mi}" data-moveset-slug="{_slug}" '
            f'style="display:{_vis};scroll-margin-top:20px;'
            'max-width:600px;margin:0 auto">\n'
            f'  <div style="text-align:center;color:#c9d1d9;'
            f'margin:0 0 4px 0;font-size:0.9rem">{_pretty}</div>\n'
            f'  <div class="dd-histogram-plot" '
            'style="height:260px"></div>\n'
            f'  <div class="dd-histogram-caption" '
            'style="text-align:center;margin:6px 0 0 0;font-size:12px;'
            'color:#c9d1d9"></div>\n'
            '</div>\n'
        )
    html += '</section>\n'

    # Pre-compute moveset 0's narrative so we know its flavor names
    # before render_threshold_tier_cards emits the tier-card badges.
    # Historically the rename ran *after* the analysis render, so the
    # tier cards showed the auto-derived name ("Lapras Atk") while the
    # Plotly legend showed the flavor name ("Lapras Slayer"); this
    # pre-compute unifies both surfaces on the flavor name. The output
    # is cached for reuse in the per-moveset narrative loop below so we
    # don't double-render moveset 0.
    scenarios_list = [tuple(s) for s in data_obj['scenarios']]
    _resolved_anchors = None
    if slayer_iter_result:
        _resolved_anchors = slayer_iter_result.get('resolved_anchors') or None
    import time as _time
    _nar0_start = _time.time()
    moveset0_nar_html, moveset0_flavors = _generate_narrative_for_moveset(
        data_obj, score_arrays, 0,
        scenarios_list, opponent_names or [],
        opp_iv_modes or [data_obj.get('oppIvModes', ['pvpoke'])[0]],
        has_toml_tiers,
        resolved_anchors=_resolved_anchors,
    )
    logger.info(f"  Moveset 0 narrative (pre-render for rename) in "
                f"{_time.time() - _nar0_start:.1f}s")

    # Deep dive analysis sections (banding, clusters, flips, etc.)
    # The anchor_passing_sink accumulates {anchor_id: [passing_iv_idx]}
    # for every anchor-flip bullet rendered inside the analysis layer.
    # We embed it into DATA below so JS can light up "which of your
    # IVs hit this breakpoint" annotations when a CSV is loaded.
    #
    # In split-movesets mode the analysis is identical across files
    # (always uses moveset_idx=0), so the caller can pass a shared dict
    # via _precomputed_analysis. On the first call (dict is empty), we
    # compute and populate it; subsequent calls read from the cache.
    # ``moveset0_flavors`` is plumbed through so the analysis can rename
    # tier cards to the flavor-matched name before rendering them.
    if _precomputed_analysis is not None and 'css' in _precomputed_analysis:
        analysis_css = _precomputed_analysis['css']
        results_html = _precomputed_analysis['results_html']
        analysis_html = _precomputed_analysis['analysis_html']
        anchor_passing_sink = _precomputed_analysis['anchor_passing_sink']
    else:
        anchor_passing_sink = {}
        analysis_css, results_html, analysis_html = generate_analysis_sections(
            data_obj, score_arrays, 0, opp_iv_modes[0],
            shield_scenarios, opponent_names,
            slayer_iter_result=slayer_iter_result,
            has_toml_tiers=has_toml_tiers,
            anchor_passing_sink=anchor_passing_sink,
            threshold_registry=threshold_registry,
            moveset0_flavors_for_rename=moveset0_flavors)
        if _precomputed_analysis is not None:
            _precomputed_analysis.update({
                'css': analysis_css,
                'results_html': results_html,
                'analysis_html': analysis_html,
                'anchor_passing_sink': anchor_passing_sink,
            })
    data_obj['anchorFlipSets'] = anchor_passing_sink
    # Inject analysis CSS into the style block (replace closing tag we already emitted)
    html = html.replace('</style>\n</head>', analysis_css + '\n</style>\n</head>', 1)
    # Generate per-moveset narrative zones. Moveset 0 was pre-rendered
    # above for the rename; reuse its cached output here.
    narrative_blocks = []
    n_movesets = len(data_obj.get('movesets', [{}]))
    _nar_start = _time.time()
    logger.info(f"  Generating narrative for {n_movesets} moveset(s)...")
    for mi in range(n_movesets):
        _mi_start = _time.time()
        if mi == 0:
            nar_html, flavors = moveset0_nar_html, moveset0_flavors
            logger.info(f"    Narrative moveset 1/{n_movesets} reused "
                        f"(pre-rendered)")
        else:
            nar_html, flavors = _generate_narrative_for_moveset(
                data_obj, score_arrays, mi,
                scenarios_list, opponent_names or [],
                opp_iv_modes or [data_obj.get('oppIvModes', ['pvpoke'])[0]],
                has_toml_tiers,
                resolved_anchors=None,
            )
            logger.info(f"    Narrative moveset {mi+1}/{n_movesets} "
                        f"rendered in {_time.time() - _mi_start:.1f}s")
        if nar_html:
            vis = 'block' if mi == 0 else 'none'
            narrative_blocks.append(
                f'<div class="dd-narrative-moveset" data-moveset="{mi}" '
                f'style="display:{vis}">\n{nar_html}\n</div>'
            )
    logger.info(f"  All narratives rendered in "
                f"{_time.time() - _nar_start:.1f}s "
                f"({len(narrative_blocks)} non-empty block(s))")

    # Tier rename is now done inside generate_analysis_sections (via the
    # ``moveset0_flavors_for_rename`` param) so both tier cards and the
    # Plotly legend see the flavor name. Kept here as a safety net for
    # the cached-analysis path in split-moveset mode: each per-file call
    # has its own data_obj['tiers'], and the cache stores only rendered
    # HTML — so we still need to rename data_obj's in-memory tier names
    # on subsequent calls for the scatter plot's JS legend.
    if moveset0_flavors and 'tiers' in data_obj:
        _rename_plotly_tiers(data_obj, moveset0_flavors)

    # Promote narrative flavors to paste-box-only tiers. ``DATA.tiers``
    # feeds the scatter plot AND the paste-box, so adding flavors there
    # would clutter the scatter legend. Emit a separate ``DATA.pasteTiers``
    # list (plot tiers ∪ non-General flavors not already represented
    # by name match) that the JS paste-box prefers when present. Fixes
    # the Tinkaton-GL gap from docs/auto_gen_narrative_plan.md "Problem
    # observed 2026-04-19": narrative-only flavors like "Fortified
    # Azumarill" were invisible to the "Check my collection" membership
    # check because they had no ``DATA.tiers`` entry.
    if moveset0_flavors:
        _promote_flavors_to_paste_tiers(data_obj, moveset0_flavors)
    if narrative_blocks:
        narrative_combined = '\n'.join(narrative_blocks)
        placeholder = '<!-- NARRATIVE_ZONE_PLACEHOLDER -->'
        if placeholder in results_html:
            results_html = results_html.replace(placeholder, narrative_combined, 1)
        else:
            # Fallback: insert before sim zone
            sim_marker = '<div class="dd-sim-zone">'
            if sim_marker in results_html:
                results_html = results_html.replace(
                    sim_marker, narrative_combined + sim_marker, 1)

    # Results section is always visible; analysis is behind a toggle
    html += results_html
    html += analysis_html

    # Embed data. Scores are packed as little-endian uint16, gzip-
    # compressed, then base64-encoded for inline embedding. The JS
    # decoder inflates via DecompressionStream and reads the result
    # as a Uint16Array.
    import base64
    import gzip
    import struct
    packed_scores = {}
    for key, arr in score_arrays.items():
        clamped = [max(0, min(65535, int(v))) for v in arr]
        raw = struct.pack(f'<{len(clamped)}H', *clamped)
        gz = gzip.compress(raw, compresslevel=9)
        packed_scores[key] = base64.b64encode(gz).decode('ascii')
    # Dedup'd tooltip table: renderers register tooltip text as they
    # emit data-t="<sid>" attrs; we dump {sid: text} here and a
    # DOMContentLoaded pass (below) populates el.title from the
    # lookup. Saves ~18 MB on an Oinkologne-shape dive by collapsing
    # 87k repeated title= values to 1.6k unique strings.
    data_obj['tooltips'] = rendering.dump_tooltip_registry()
    html += f'<script>var DATA = {json.dumps(data_obj)};\n'
    html += f'var SCORES_GZ = {json.dumps(packed_scores)};\n'
    html += """
// -------------------------------------------------------------------
// How SCORES_GZ works (for the curious / paranoid):
//
// Each value in SCORES_GZ is a base64 string that encodes gzip-
// compressed battle-simulation scores.  The pipeline that created it:
//
//   Python side (scripts/deep_dive.py):
//     1. Simulate every IV spread vs every opponent in every shield
//        scenario.  Each sim produces an integer score 0-1000.
//     2. Pack the scores as little-endian unsigned 16-bit integers
//        (2 bytes each, same byte order your browser uses natively).
//     3. Gzip-compress the packed bytes (shrinks ~5-8x).
//     4. Base64-encode the gzip output so it can live inside HTML
//        (browsers can't embed raw binary in a <script> tag).
//
//   JS side (right here, runs when the page loads):
//     1. Base64-decode each string back to raw bytes.
//     2. Gzip-decompress via the browser's built-in DecompressionStream.
//     3. Interpret the result as a Uint16Array (the original scores).
//     4. Copy into a plain Array so the rest of the page can use it.
//
// Nothing is hidden or obfuscated -- the compression is purely to keep
// file sizes manageable (a full deep dive with 60+ opponents would be
// ~100 MB uncompressed).  You can verify the scores by running the
// same deep_dive.py command shown in the footer of this page and
// comparing the output.
// -------------------------------------------------------------------

var SCORES = {};
var _scoresReady = (async function() {
  for (var key in SCORES_GZ) {
    var bin = Uint8Array.from(atob(SCORES_GZ[key]), function(c) { return c.charCodeAt(0); });
    var ds = new DecompressionStream('gzip');
    var writer = ds.writable.getWriter();
    writer.write(bin);
    writer.close();
    var chunks = [];
    var reader = ds.readable.getReader();
    while (true) {
      var r = await reader.read();
      if (r.done) break;
      chunks.push(r.value);
    }
    var total = chunks.reduce(function(s, c) { return s + c.byteLength; }, 0);
    var merged = new Uint8Array(total);
    var offset = 0;
    for (var i = 0; i < chunks.length; i++) {
      merged.set(chunks[i], offset);
      offset += chunks[i].byteLength;
    }
    SCORES[key] = Array.from(new Uint16Array(merged.buffer));
  }
})();

// Populate title= attributes from DATA.tooltips lookup.
// Every element with data-t="<sid>" gets its title set from
// DATA.tooltips[sid]. Runs at DOMContentLoaded so native browser
// tooltips work without further JS on hover. Decouples per-element
// tooltip bulk from the HTML source (~18 MB saved on Oinkologne
// -shape dives; ~300 KB on Tinkaton-shape). See
// docs/s11_html_size_audit.md.
(function() {
  if (!DATA.tooltips) return;
  var tips = DATA.tooltips;
  var populate = function() {
    var nodes = document.querySelectorAll('[data-t]');
    for (var i = 0; i < nodes.length; i++) {
      var tip = tips[nodes[i].getAttribute('data-t')];
      if (tip) nodes[i].setAttribute('title', tip);
    }
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', populate);
  } else {
    populate();
  }
})();
"""
    html += '</script>\n'

    # User-collection JS module (POGOCollection global). Injected BEFORE
    # the engine so the engine can reference POGOCollection.parseCsvText
    # etc. on init. Kept as a separate <script> block - if the module
    # file is missing (dev moved it, etc.) the engine still loads and
    # the paste-box simply stays hidden via the DATA.collection null
    # guard in the engine init.
    _uc_js_path = os.path.join(os.path.dirname(__file__),
                               'deep_dive_user_collection.js')
    try:
        with open(_uc_js_path) as _ucf:
            html += '<script>\n' + _ucf.read() + '\n</script>\n'
    except FileNotFoundError:
        pass

    # JS engine - wrapped in an async IIFE that waits for gzip
    # decompression of score arrays to finish before initializing.
    html += '<script>\n'
    html += '(async function() {\nawait _scoresReady;\n'
    # Use data_obj['tiers'] (may have been updated by generate_analysis_sections
    # with auto-derived tiers) rather than the original tier_info.
    final_tier_info = data_obj.get('tiers', tier_info) or tier_info
    html += _interactive_js_engine(n_scenarios, n_opponents, opp_iv_modes,
                                   reference_idx, final_tier_info, opp_desc,
                                   league, shield_scenarios)
    html += '\n})();\n'
    html += '</script>\n'

    # One-line pointer to the Reader's Guide, above the About / Credits
    # details block so a first-time reader sees it before the
    # methodology deep-dive. Relative path reaches the guides landing
    # from both a dive landing (oinkologne-great-league/) and a
    # split-moveset sibling (same directory).
    html += ('<p style="margin-top:30px;color:#888;font-size:12px">'
             'New here? The <a href="../guides/">Reader\'s Guide</a> '
             'explains tier cards, envelope shapes, and the IV flavor '
             'guide in plain language.</p>\n')

    # About / Credits section
    html += '<details class="meta" style="margin-top:10px;border-top:1px solid #0f3460;padding-top:10px">'
    html += '<summary>About &amp; Credits</summary>'
    html += '<div style="margin:8px 0;font-size:0.85rem;color:#b0b8c4;line-height:1.6">'
    html += '<p><b>PoGo PvP IV Deep Dive</b> - a stat-threshold analysis tool '
    html += 'for Pokemon GO PvP IVs.</p>'
    html += '<p><b>Data &amp; Simulation Reference</b></p>'
    html += '<ul style="margin:4px 0 8px 20px">'
    html += '<li><b>PvPoke</b> (pvpoke.com) - species data (gamemaster.json), '
    html += 'meta rankings, and battle simulation reference. '
    html += 'PvPoke is open-source: github.com/pvpoke/pvpoke.</li>'
    html += '<li><b>RyanSwag</b> - mirror slayer IV framework '
    html += '(Pure Slayer / Bulky Slayer / CMP Slayer categories).</li>'
    html += '</ul>'
    html += '<p><b>Methodology</b></p>'
    html += '<ul style="margin:4px 0 8px 20px">'
    html += '<li>Damage formula: floor(0.5 x 1.3 x Power x Atk/Def x Effectiveness x STAB) + 1</li>'
    html += '<li>Breakpoints and bulkpoints are derived from the damage formula; '
    html += 'matchup-flipping boundaries are found by sweeping stat thresholds against full battle simulations.</li>'
    html += '<li>Mirror slayer iteration uses Nash-style convergence to discover IVs '
    html += 'that beat the mirror matchup.</li>'
    html += '</ul>'
    html += '</div></details>\n'

    # Footer: equivalent CLI invocation + rankings data fingerprint, kept
    # at the bottom of the page so they're discoverable but don't compete
    # with the actual analysis content. The fingerprint addresses the
    # reproducibility gap noted in TODO.md "Reproducibility": two dives
    # with identical CLI args can produce different results when the
    # underlying PvPoke rankings cache drifts. Fingerprint = the cache
    # mtime + first-5 species so a reader can spot drift between dives.
    if cli_args_str:
        from html import escape as _esc
        html += '<details class="meta" style="margin-top:30px;border-top:1px solid #0f3460;padding-top:10px">'
        html += '<summary>Run parameters (CLI invocation)</summary>'
        html += '<pre style="margin:8px 0;background:#16213e;'
        html += 'padding:10px;border-radius:4px;color:#e0e0e0;font-size:12px;'
        html += 'white-space:pre-wrap;word-break:break-all">'
        html += _esc(cli_args_str)
        html += '</pre></details>\n'

    # Rankings fingerprint
    try:
        import datetime
        from gopvpsim import data as _gpdata
        cache_path = _gpdata.CACHE_DIR / f"{league}.json"
        if cache_path.exists():
            mtime = datetime.datetime.fromtimestamp(cache_path.stat().st_mtime)
            mtime_str = mtime.strftime('%Y-%m-%d %H:%M:%S')
            rk = _gpdata.load_rankings(league)
            top5 = ', '.join(r.get('speciesName', r.get('speciesId', '?'))
                             for r in rk[:5])
            html += '<details class="meta" style="margin-top:8px">'
            html += '<summary>Rankings data fingerprint</summary>'
            html += '<pre style="margin:8px 0;background:#16213e;'
            html += 'padding:10px;border-radius:4px;color:#e0e0e0;font-size:12px;'
            html += 'white-space:pre-wrap;word-break:break-all">'
            html += f'cache file: {cache_path}\n'
            html += f'cache mtime: {mtime_str}\n'
            html += f'rankings count: {len(rk)}\n'
            html += f'top 5 species: {top5}'
            html += '</pre></details>\n'
    except Exception as _e:
        # Fingerprint is best-effort - don't break HTML generation
        # if the cache file is missing or unreadable.
        pass

    html += '</body>\n</html>\n'

    import time as _time
    _write_start = _time.time()
    logger.info(f"  Writing HTML ({len(html) / 1024 / 1024:.1f} MB) "
                f"to {html_path}...")
    with open(html_path, 'w') as f:
        f.write(html)
    logger.result(f"  Interactive HTML written to {html_path} "
                  f"({_time.time() - _write_start:.1f}s)")


_JS_ENGINE_PATH = os.path.join(os.path.dirname(__file__), 'deep_dive_engine.js')


def _interactive_js_engine(n_scenarios, n_opponents, opp_iv_modes, reference_idx,
                           tier_info, opp_desc, league, shield_scenarios):
    """Return the JS code for the interactive deep dive page.

    The JS body lives in ``scripts/deep_dive_engine.js`` so it can be
    edited as plain JavaScript (with syntax highlighting, no Python
    f-string brace escaping). Eight placeholders inside that file get
    replaced at runtime with the per-dive values below.
    """
    tier_colors_js = json.dumps([t['color'] for t in tier_info])
    tier_names_js = json.dumps([t['name'] for t in tier_info])
    scenario_mode_default = '"avg"' if n_scenarios > 1 else '"0"'
    shield_desc_default = f'{shield_scenarios[0][0]}v{shield_scenarios[0][1]}'
    opp_desc_escaped = opp_desc.replace("'", "\\'")

    with open(_JS_ENGINE_PATH) as _f:
        body = _f.read()
    substitutions = {
        '__SCENARIO_MODE_DEFAULT__': scenario_mode_default,
        '__OPP_IV_MODE_DEFAULT__': opp_iv_modes[0],
        '__TIER_COLORS_JS__': tier_colors_js,
        '__TIER_NAMES_JS__': tier_names_js,
        '__SHIELD_DESC_DEFAULT__': shield_desc_default,
        '__LEAGUE_TITLE__': league.title(),
        '__LEAGUE_CP_CAP__': str(LEAGUE_CAPS[league]),
        '__OPP_DESC_ESCAPED__': opp_desc_escaped,
    }
    for placeholder, value in substitutions.items():
        body = body.replace(placeholder, value)
    # Match the original f-string output: one leading newline (already
    # in the extracted body) and one trailing newline.
    return body + '\n'


def format_cli_args(args, parser) -> str:
    """Build the *fully-resolved* equivalent command from a parsed Namespace.

    Walks the parser's actions in declaration order and emits **every** flag
    with its actual value, including flags whose value happens to equal the
    current parser default. This is intentional: defaults can change between
    runs, so a string that omits "default" flags becomes ambiguous when read
    later - you can't tell whether `--mirror-slayer-pool` was unset (and got
    today's default) or set to today's default explicitly.

    The fully-resolved form is verbose but unambiguous: re-reading the HTML
    next month after a default has changed still tells you exactly what value
    was used. This output is the forensic record, not necessarily a
    convenient copy-paste - though it IS pasteable and will reproduce the
    same run.

    Boolean flags are emitted only when True (False is the implicit absence),
    since there's no `--no-X` form for store_true / store_false flags here.
    ``BooleanOptionalAction`` flags (which DO have a `--no-X` form) always
    emit explicitly - `--flag` for True, `--no-flag` for False - so the
    record round-trips through argparse on paste-back. Flags whose value
    is None are skipped because there's no syntax for "explicitly set to
    None" on the command line.
    """
    parts = ["python scripts/deep_dive.py"]
    positional: list[str] = []
    flags: list[str] = []
    for action in parser._actions:
        # Skip the implicit help action
        if action.dest == 'help':
            continue
        val = getattr(args, action.dest, None)
        # Positional args (no option strings)
        if not action.option_strings:
            if val is not None:
                positional.append(_shell_quote(str(val)))
            continue
        flag = action.option_strings[0]
        if isinstance(action, argparse.BooleanOptionalAction):
            # Emit the matching --flag or --no-flag form from the action's
            # own option_strings; the raw value is a bool that argparse
            # rejects as a positional on paste-back.
            want_negative = not val
            for opt in action.option_strings:
                is_negative = opt.startswith('--no-')
                if is_negative == want_negative:
                    flags.append(opt)
                    break
            continue
        if isinstance(action, argparse._StoreTrueAction):
            # store_true: only emit when True (False = absent on the cmdline)
            if val:
                flags.append(flag)
            continue
        if isinstance(action, argparse._StoreFalseAction):
            # store_false: emit only when explicitly False
            if not val:
                flags.append(flag)
            continue
        # None means "not set and no default to record"
        if val is None:
            continue
        if action.nargs in (None, '?', 0) or action.nargs == argparse.OPTIONAL:
            if isinstance(val, list):
                # action='append' - emit one occurrence per value
                for item in val:
                    flags.append(f'{flag} {_shell_quote(str(item))}')
            else:
                flags.append(f'{flag} {_shell_quote(str(val))}')
        else:
            # nargs='+', '*', or numeric - join with spaces
            if isinstance(val, (list, tuple)):
                joined = ' '.join(_shell_quote(str(v)) for v in val)
            else:
                joined = _shell_quote(str(val))
            flags.append(f'{flag} {joined}')
    return ' '.join(parts + positional + flags)


def _shell_quote(s: str) -> str:
    """Quote a string for shell display only when needed."""
    # Conservative: quote anything containing shell-meaningful characters.
    if not s:
        return "''"
    safe = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./,=:")
    if all(c in safe for c in s):
        return s
    # Use single quotes; escape any embedded single quotes the POSIX way.
    return "'" + s.replace("'", "'\"'\"'") + "'"


def main():
    parser = argparse.ArgumentParser(
        description='IV deep dive: sim all 4096 IV spreads against meta opponents.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('species', help='Focal species name (e.g. Medicham, Tinkaton)')
    parser.add_argument('--fast', default=None, metavar='MOVE',
                        help='Fast move ID (if omitted, try all legal fast moves)')
    parser.add_argument('--charged', default=None, metavar='MOVE[,MOVE]',
                        help='One or two charged move IDs, comma-separated. '
                             'Moves not yet in the species pool (CD moves) are allowed.')
    parser.add_argument('--league', default='great',
                        choices=['great', 'ultra', 'master'])
    parser.add_argument('--opponents', type=int, default=20, metavar='N',
                        help='Number of top meta opponents from rankings (default: 20). '
                             'Ignored if --group is used.')
    parser.add_argument('--group', default=None, metavar='NAME',
                        help='Use a PvPoke custom group as opponents '
                             '(e.g. championshipseries). Fetched from GitHub, '
                             'cached locally. Known groups: '
                             f'{", ".join(KNOWN_GROUPS[:8])}...')
    parser.add_argument('--opponents-file', default=None, metavar='FILE',
                        help='Read opponent species names from a file, one '
                             'per line (blank lines and # comments ignored). '
                             'Used instead of --opponents/--group when you '
                             'need a custom opponent pool (e.g. top-50 rankings '
                             'union championshipseries). Species must match '
                             'the PvPoke speciesName exactly, e.g. '
                             '"Tinkaton" or "Altaria (Shadow)". Movesets are '
                             'resolved the same way as the --opponents path '
                             '(PvPoke default moveset per species).')
    parser.add_argument('--top-movesets', type=int, default=5, metavar='N',
                        help='Keep top N movesets after Phase 1 screening (default: 5). '
                             'Screening sims the stat-product rank 1 IV against '
                             'opponents for each candidate moveset, then keeps the '
                             'top N by average score. Only the survivors go through '
                             'the full 4096-IV sweep. Set to 0 to skip screening '
                             'and sweep all candidate movesets.')
    parser.add_argument('--shield-scenario', default='1,1', metavar='S1,S2',
                        help='Shield scenario as focal,opponent (default: 1,1). '
                             'Use "all" for all 9 scenarios (0v0 through 2v2), '
                             'or "even" for 0v0+1v1+2v2.')
    parser.add_argument('--shadow', action='store_true',
                        help='Focal species is shadow')
    parser.add_argument('--opp-ivs', default='pvpoke', choices=['pvpoke', 'rank1', 'both'],
                        help='Opponent IV selection: pvpoke (PvPoke default IVs, '
                             'what pvpoke.com uses), rank1 (stat product rank 1), '
                             'or both (run both, selectable in interactive HTML). '
                             'Default: pvpoke.')
    parser.add_argument('--thresholds', default=None, metavar='FILE',
                        help='Threshold file with spreads (stat-cutoff or IV-list) '
                             'and anchors (cmp, damage_breakpoint) for the species. '
                             'Accepts .toml (full schema; see docs/threshold_schema.md) '
                             'or legacy .json (flat stat-cutoff form, no anchors). '
                             'Extension auto-detected.')
    parser.add_argument('--no-thresholds', action='store_true',
                        help='Skip the thresholds/<species>.toml auto-load. '
                             'Use for "clean" dives that rely only on '
                             'auto-derived tiers + anchor discovery from '
                             'opponent analysis, no TOML-prescribed spreads. '
                             'Has no effect if --thresholds is passed.')
    parser.add_argument('--species-iv-floor', default=None, metavar='ATK,DEF,STA',
                        help='Prune focal species IVs below this floor at '
                             'enumeration time. Comma-separated (e.g. "13,13,13" '
                             'for UL tight-spread dives - trims 4096 IVs to 27). '
                             'Applies ONLY to the focal species; opponents still '
                             'use their default / rank1 / cohort selection. The '
                             'scatter plot, tier derivation, and anchor analysis '
                             'all operate on the pruned set; the paste-box '
                             'matches list will not find user mons below the '
                             'floor even if owned.')
    parser.add_argument('--anchor-file', default=None, metavar='FILE', action='append',
                        dest='anchor_files',
                        help='Additional threshold file merged on top of --thresholds. '
                             'Repeatable; later files win on name collision. '
                             'Use for one-off anchor experiments without editing '
                             'the canonical per-species file.')
    parser.add_argument('--anchor', default=None, metavar='SPEC', action='append',
                        dest='inline_anchors',
                        help='Inline anchor definition, format '
                             '"name:kind=K,key=value,...". Repeatable; last wins '
                             'on name collision. For inline cmp cohorts use '
                             'ivs=15/3/2;15/2/4;...  For Level 3 damage_breakpoint '
                             'moves filter use moves=COUNTER;LOW_KICK. '
                             'See docs/threshold_schema.md for full key reference.')
    parser.add_argument('--html', default=None, metavar='FILE',
                        help='Write interactive HTML plot to FILE')
    parser.add_argument('--interactive', action='store_true',
                        help='Generate interactive HTML with dropdowns for moveset, '
                             'shield scenario, and opp IV mode switching. '
                             'Runs all shield scenarios and reference moveset.')
    parser.add_argument('--reference', default='auto', metavar='SPEC',
                        help='Reference moveset for comparison: auto (PvPoke default, '
                             'shown in interactive mode), none (skip), or '
                             'FAST,CHARGED1,CHARGED2. Default: auto.')
    parser.add_argument('--standalone', action='store_true',
                        help='Inline Plotly.js into the HTML so the file works '
                             'offline with no CDN dependency (~4MB larger)')
    parser.add_argument('--shared-plotly', metavar='DIR', default=None,
                        help='Write Plotly.js once to DIR and emit a '
                             '<script src=...> reference relative to the '
                             'HTML output. Saves ~4.35 MB per dive vs '
                             '--standalone when rendering multiple dives '
                             'that share a sibling directory (e.g. a '
                             'website tree). Overrides --standalone. '
                             'Example: --shared-plotly userdata/website/_shared')
    parser.add_argument('--screen-opponents', type=int, default=None, metavar='N',
                        help='Use only top N opponents for phase 1 screen '
                             '(default: same as --opponents)')
    parser.add_argument('--mirror-slayer', action=argparse.BooleanOptionalAction,
                        default=True,
                        help='Run iterative slayer discovery for the focal species '
                             '(Nash-style mirror match iteration). Adds ~2-5 min to '
                             'the deep dive but classifies survivors into Atk Slayer, '
                             'Bulk Slayer, and CMP Slayer categories. Results are '
                             'cached on disk for fast re-runs. ENABLED by default; '
                             'pass --no-mirror-slayer to skip.')
    parser.add_argument('--mirror-slayer-metric', default='all',
                        choices=['all', 'even', 'even-strict'],
                        help='Slayer iteration metric: "all" counts wins across all '
                             '9 scenarios (default), "even" counts only 0v0/1v1/2v2, '
                             '"even-strict" requires winning ALL 3 even scenarios.')
    parser.add_argument('--mirror-slayer-rounds', type=int, default=4,
                        help='Max rounds for mirror slayer iteration (default 4). '
                             'Set to 1 for "beat the typical opponent" mode (no '
                             'Nash iteration).')
    parser.add_argument('--mirror-slayer-pool', type=int, default=30,
                        help='Number of survivors to keep per iteration round '
                             '(default 30). Larger = more inclusive surviving '
                             'cohort, more IVs reported in final categories.')
    parser.add_argument('--mirror-slayer-show', type=int, default=20,
                        help='Number of IVs to show per category in final output '
                             '(default 20).')
    parser.add_argument('--no-cache', action='store_true',
                        help='Disable disk cache for slayer iteration')
    parser.add_argument('--split-movesets', action='store_true',
                        help='Emit one HTML file per moveset instead of one '
                             'big multi-moveset file. The moveset dropdown '
                             'navigates between files via window.location '
                             'rather than swapping data in-page. Reference '
                             'moveset becomes the landing page ({base}.html); '
                             'other movesets get {base}_m{idx}_{slug}.html. '
                             'Per-file size drops ~4x on multi-moveset dives. '
                             'Non-reference files still embed the reference '
                             'moveset scores so the "vs Ref" hover diff keeps '
                             'working. Ignored for single-moveset dives. '
                             'Interactive mode only.')
    parser.add_argument('--bait', default='both', choices=['on', 'off', 'both'],
                        help="Focal-side bait-shields policy: "
                             "'on' uses PvPoke simulate-mode DP "
                             "with baiting enabled. "
                             "'off' runs with pvpoke_dp bait_shields=False "
                             "(focal never baits; opponent still baits). "
                             "'both' (default) runs both modes in a single "
                             "dive, adds a bait selector to the interactive "
                             "HTML, and annotates bait-dependent matchup "
                             "flips. Doubles compute time. "
                             "Interactive mode only.")
    parser.add_argument('--verbose', action='store_true',
                        help='Route DEBUG-level aggregator diagnostics to the '
                             'log file (stdout unchanged).')
    parser.add_argument('--quiet', action='store_true',
                        help='Suppress INFO-level progress on stdout. WARNINGs '
                             'and the final Top-20 table still appear. The log '
                             'file is unaffected.')
    parser.add_argument('--log-file', default=None, metavar='PATH',
                        help='Explicit per-run log file. Use /dev/null to '
                             'disable file logging entirely. Default: '
                             'userdata/logs/YYYY-MM/YYYYMMDD_HHMMSS_<species>_<league>.log.')
    parser.add_argument('--log-dir', default=None, metavar='DIR',
                        help='Root directory for per-run log files. Monthly '
                             'subdirs and the YYYYMMDD_HHMMSS_<species>_<league>.log '
                             'filename are derived from this base. Ignored when '
                             '--log-file is given. Default: userdata/logs/.')
    parser.add_argument('--reserve-cpus', type=int, default=0, metavar='N',
                        help='Leave N CPUs idle so other local work stays '
                             'responsive. Default 0 (use up to min(cpu_count, 16)). '
                             'Applies to both the per-moveset sim sweep and the '
                             'slayer iteration pool.')

    args = parser.parse_args()

    # Fail-fast: ensure --html output directory exists (and is writable)
    # BEFORE running any simulation. Without this, a fresh dive slug
    # like "aegislash-blade-great-league/" whose parent dir doesn't
    # exist yet crashes only after 1-6 minutes of simulation when the
    # final HTML write fails. makedirs(exist_ok=True) is a no-op when
    # the dir already exists; a permission/typo/bad-mount issue
    # surfaces immediately here with a clear error.
    if args.html:
        _html_parent = os.path.dirname(os.path.abspath(args.html))
        if _html_parent:
            try:
                os.makedirs(_html_parent, exist_ok=True)
            except OSError as _e:
                parser.error(
                    f'Cannot create --html output directory '
                    f'{_html_parent!r}: {_e}'
                )

    # Parse --species-iv-floor "ATK,DEF,STA" into a (atk, def, sta) tuple
    # of ints. Empty / None stays None (no floor applied).
    _iv_floor = None
    if args.species_iv_floor:
        try:
            _parts = [int(p) for p in args.species_iv_floor.split(',')]
            if len(_parts) != 3 or any(p < 0 or p > 15 for p in _parts):
                parser.error(
                    '--species-iv-floor must be ATK,DEF,STA with three '
                    'integers in [0, 15] (e.g. "13,13,13")')
            _iv_floor = tuple(_parts)
        except ValueError:
            parser.error('--species-iv-floor must parse as three integers '
                         '(e.g. "13,13,13")')
    args.iv_floor = _iv_floor

    # Initialize the per-run logger BEFORE anything else emits output. The
    # file handler is opened before the first CLI echo so `tail -f` on
    # userdata/logs/latest.log catches the whole run.
    _, log_path = init_logger(
        args.species, args.league, shadow=args.shadow,
        verbose=args.verbose, quiet=args.quiet,
        log_file=args.log_file, log_dir=args.log_dir,
    )
    if log_path is not None:
        logger.info(f"Log file: {log_path}")

    # Capture the equivalent command line for forensic reproducibility.
    # Printed to console and embedded in HTML output so any future reader can
    # see exactly what flags produced a given dive (including defaults that
    # have since changed).
    cli_args_str = format_cli_args(args, parser)
    logger.info(f"CLI: {cli_args_str}")
    if args.iv_floor is not None:
        logger.info(f"  IV floor: atk>={args.iv_floor[0]}, def>={args.iv_floor[1]}, "
                    f"sta>={args.iv_floor[2]} (focal species only)")

    # Parse shield scenarios
    ALL_NINE = [(s0, s1) for s0 in range(3) for s1 in range(3)]
    EVEN_THREE = [(0, 0), (1, 1), (2, 2)]
    if args.shield_scenario == 'all':
        shield_scenarios = ALL_NINE
    elif args.shield_scenario == 'even':
        shield_scenarios = EVEN_THREE
    else:
        parts = args.shield_scenario.split(',')
        if len(parts) != 2:
            sys.exit("--shield-scenario must be S1,S2 (e.g. 1,1), 'all', or 'even'")
        shield_scenarios = [(int(parts[0]), int(parts[1]))]

    # Parse charged moves
    user_charged = None
    if args.charged:
        user_charged = [c.strip() for c in args.charged.split(',')]

    # Load thresholds.
    #
    # Two parallel representations are maintained during the transition from
    # the legacy flat-JSON format to the richer TOML spreads+anchors schema:
    #   - `threshold_registry`: full TOML-backed ThresholdRegistry (used by
    #     the new slayer anchor system via gopvpsim.anchors).
    #   - `thresholds`: legacy flat dict {name: {attack, defense, stamina}}
    #     that the existing tier-coloring / classify_iv / HTML tier rendering
    #     code paths expect. For TOML files we derive this via
    #     as_legacy_dict() from the registry; stat-cutoff spreads map 1:1,
    #     IV-list spreads are skipped (they have no stat-cutoff equivalent).
    thresholds = None
    threshold_registry = None
    _article_slug = ''
    _cd_prep_fast: list[str] = []
    _cd_prep_charged: list[str] = []
    _species_narrative: dict = {}
    if args.thresholds:
        try:
            threshold_registry = load_threshold_file(
                args.thresholds, species=args.species, league=args.league.capitalize(),
            )
        except Exception as e:
            logger.warning(f"failed to load {args.thresholds}: {e}")
            threshold_registry = None
        # Extract species narrative from the explicit TOML too.
        try:
            import tomllib as _tomllib
            with open(args.thresholds, 'rb') as _f:
                _raw_toml = _tomllib.load(_f)
            _sp = _raw_toml.get(args.species, {})
            for _key in ('intro', 'meta_role', 'verdict'):
                if _key in _sp and isinstance(_sp[_key], dict):
                    _species_narrative[_key] = _sp[_key]
        except Exception:
            _species_narrative = {}
    elif args.no_thresholds:
        # Explicit opt-out: no TOML registry load. Falls through to the
        # auto-derive path which reads anchor records from opponent
        # analysis only. The species-narrative blocks (Shape 2 migration)
        # are orthogonal to the threshold-registry payload - they're raw
        # TOML prose extracted alongside, not threshold data - so the
        # --no-thresholds opt-out should NOT suppress them. Read the
        # same file the auto-discover path would find, extract just
        # narrative, leave threshold_registry None.
        logger.info('  --no-thresholds: skipping threshold registry load')
        _species_lower = args.species.lower().replace(' ', '_').replace('(', '').replace(')', '')
        _narr_toml = Path(__file__).resolve().parent.parent / 'thresholds' / f'{_species_lower}.toml'
        if _narr_toml.exists():
            try:
                import tomllib as _tomllib
                with open(_narr_toml, 'rb') as _f:
                    _raw_toml = _tomllib.load(_f)
                _sp = _raw_toml.get(args.species, {})
                for _key in ('intro', 'meta_role', 'verdict'):
                    if _key in _sp and isinstance(_sp[_key], dict):
                        _species_narrative[_key] = _sp[_key]
                if _species_narrative:
                    _nkeys = ', '.join(sorted(_species_narrative.keys()))
                    logger.info(f"  Species narrative blocks: {_nkeys}")
            except Exception as _e:
                logger.warning(f"narrative load from {_narr_toml.name} failed: {_e}")
    else:
        # Auto-discover: look for thresholds/<species>.toml (case-insensitive)
        # so the user doesn't have to remember --thresholds every run.
        _species_lower = args.species.lower().replace(' ', '_').replace('(', '').replace(')', '')
        _auto_toml = Path(__file__).resolve().parent.parent / 'thresholds' / f'{_species_lower}.toml'
        if _auto_toml.exists():
            try:
                threshold_registry = load_threshold_file(
                    str(_auto_toml), species=args.species,
                    league=args.league.capitalize(),
                )
                logger.info(f"  Auto-loaded thresholds: {_auto_toml.name}")
            except Exception as e:
                logger.warning(f"auto-load {_auto_toml.name} failed: {e}")
                threshold_registry = None
            # Extract article slug if the TOML has a [Species.article] section
            try:
                import tomllib as _tomllib
                with open(_auto_toml, 'rb') as _f:
                    _raw_toml = _tomllib.load(_f)
                _article_table = _raw_toml.get(args.species, {}).get('article', {})
                _article_slug = _article_table.get('slug', '')
                if _article_slug:
                    logger.info(f"  Article link: articles/{_article_slug}/")
            except Exception:
                _article_slug = ''
            # Extract optional species narrative blocks (Shape 2 migration).
            # Same raw-TOML re-read pattern as cd_prep / article - the
            # ThresholdRegistry parser silently ignores species-level
            # sub-tables that aren't leagues, so these live outside the
            # registry and are threaded through to the renderer directly.
            _species_narrative = {}
            try:
                _sp = _raw_toml.get(args.species, {})
                for _key in ('intro', 'meta_role', 'verdict'):
                    if _key in _sp and isinstance(_sp[_key], dict):
                        _species_narrative[_key] = _sp[_key]
                if _species_narrative:
                    _nkeys = ', '.join(sorted(_species_narrative.keys()))
                    logger.info(f"  Species narrative blocks: {_nkeys}")
            except Exception:
                _species_narrative = {}
            # Extract cd_prep block so pre-CD dives include the
            # incoming move even when PvPoke's gamemaster hasn't added
            # it yet. The actual injection happens in enumerate_movesets
            # below; logging here lets the reader see the event / fast /
            # charged trio that drove the moveset enumeration.
            _cd_prep = _raw_toml.get(args.species, {}).get('cd_prep', {})
            if _cd_prep:
                _event = _cd_prep.get('event', '').strip()
                _cd_prep_fast = list(_cd_prep.get('fast_moves') or [])
                _cd_prep_charged = list(_cd_prep.get('charged_moves') or [])
                if _event:
                    logger.info(f"  cd_prep: {_event}")
                if _cd_prep_fast:
                    logger.info(f"  cd_prep fast moves: {', '.join(_cd_prep_fast)}")
                if _cd_prep_charged:
                    logger.info(f"  cd_prep charged moves: {', '.join(_cd_prep_charged)}")

    # Auto-load cross-species shared spreads / anchors from thresholds/_shared.toml
    # so per-species TOMLs (and the opponent-pool variant expansion below) can
    # reference shared entries. Skipped when --no-thresholds opts out explicitly.
    if not args.no_thresholds:
        _shared_toml = Path(__file__).resolve().parent.parent / 'thresholds' / '_shared.toml'
        if _shared_toml.exists():
            try:
                from gopvpsim.thresholds import load_toml as _load_shared
                _shared_reg = _load_shared(str(_shared_toml))
                if threshold_registry is None:
                    threshold_registry = _shared_reg
                else:
                    threshold_registry = threshold_registry.merge(_shared_reg)
                logger.info(f"  Auto-loaded shared thresholds: {_shared_toml.name}")
            except Exception as e:
                logger.warning(f"auto-load {_shared_toml.name} failed: {e}")

    # Overlay --anchor-file files on top (repeatable; later wins on collision)
    if threshold_registry is not None and args.anchor_files:
        from gopvpsim.thresholds import load_toml as _load_toml_overlay
        for overlay_path in args.anchor_files:
            try:
                overlay = _load_toml_overlay(overlay_path)
                threshold_registry = threshold_registry.merge(overlay)
                logger.info(f"  Merged anchor-file overlay: {overlay_path}")
            except Exception as e:
                logger.warning(f"failed to merge {overlay_path}: {e}")

    # Allow --anchor / --anchor-file to work without --thresholds by
    # starting from an empty registry.
    if threshold_registry is None and (args.anchor_files or args.inline_anchors):
        from gopvpsim.thresholds import ThresholdRegistry as _TR
        threshold_registry = _TR()

    # Apply --anchor inline flags (repeatable; last wins on collision)
    if threshold_registry is not None and args.inline_anchors:
        from gopvpsim.thresholds import (
            parse_inline_anchor, SpeciesThresholds, LeagueThresholds,
            ThresholdRegistry, IvListSpread, CmpAnchor,
        )
        # We build a synthetic one-species overlay containing all inline
        # anchors for this species/league, then merge it in.
        lt_overlay = LeagueThresholds(league=args.league.capitalize())
        for spec in args.inline_anchors:
            try:
                a_name, anchor = parse_inline_anchor(spec)
            except Exception as e:
                logger.warning(f"--anchor {spec!r}: {e}")
                continue
            # If an inline cmp anchor carried its own IV list, inject a
            # synthetic spread that the anchor points at.
            inline_ivs = getattr(anchor, '_inline_ivs', None)
            if isinstance(anchor, CmpAnchor) and inline_ivs:
                spread_name = anchor.spread  # "__inline__<name>"
                lt_overlay.spreads[spread_name] = IvListSpread(
                    name=spread_name,
                    ivs=tuple(tuple(iv) for iv in inline_ivs),
                    description=f"Inline cohort for --anchor {a_name}",
                )
            lt_overlay.anchors[a_name] = anchor
            logger.info(f"  Inline anchor: {a_name} ({anchor.kind})")
        if lt_overlay.spreads or lt_overlay.anchors:
            sp_overlay = SpeciesThresholds(
                species=args.species,
                leagues={args.league.capitalize(): lt_overlay},
            )
            overlay_reg = ThresholdRegistry(by_species={args.species: sp_overlay})
            threshold_registry = threshold_registry.merge(overlay_reg)

    # Derive the legacy flat dict for tier-coloring paths that still expect it.
    _toml_tiers_loaded = False
    if threshold_registry is not None:
        thresholds = as_legacy_dict(
            threshold_registry, args.species, args.league.capitalize(),
        ) or None
        if thresholds:
            _toml_tiers_loaded = True
        n_spreads = len(thresholds) if thresholds else 0
        n_anchors = 0
        sp = threshold_registry.species(args.species)
        if sp is not None:
            lt = sp.leagues.get(args.league.capitalize())
            if lt is not None:
                n_anchors = len(lt.anchors)
        if args.thresholds:
            logger.info(f"  Thresholds: {n_spreads} stat-cutoff spread(s), "
                        f"{n_anchors} anchor(s) (from {args.thresholds})")

    logger.result('')
    logger.result('=' * 60)
    logger.result(f"  {args.species}{'  (Shadow)' if args.shadow else ''} - "
                  f"{args.league.title()} League IV Deep Dive")
    logger.result('=' * 60)
    logger.result('')

    # Enumerate movesets. cd_prep_fast/charged come from the focal
    # species' [cd_prep] TOML block (populated when the species is in CD
    # prep and PvPoke's gamemaster may lag on the incoming move); an
    # empty list here is the default no-op.
    movesets = enumerate_movesets(args.species, args.fast, user_charged,
                                  cd_prep_fast=_cd_prep_fast,
                                  cd_prep_charged=_cd_prep_charged)
    logger.info(f"  {len(movesets)} moveset combination(s) to evaluate")

    # Get opponents - from group or rankings
    # Always include the focal species so we can do mirror slayer analysis.
    opponent_label = None
    if args.group and args.opponents_file:
        parser.error('--group and --opponents-file are mutually exclusive')
    focal_in_opponents = False
    if args.group:
        group_entries = load_group(args.group)
        opponents = []
        opp_movesets_full = []
        for species_name, fast_move, charged_moves, is_shadow in group_entries:
            opponents.append(species_name)
            opp_movesets_full.append((fast_move, charged_moves))
            if species_name == args.species:
                focal_in_opponents = True
        # Append focal species if not already in group
        if not focal_in_opponents:
            try:
                focal_fast, focal_charged = get_default_moveset(
                    args.species, league=args.league, shadow=args.shadow)
                opponents.append(args.species)
                opp_movesets_full.append((focal_fast, focal_charged))
                focal_in_opponents = True
                logger.info(f"  (added {args.species} to opponents for mirror analysis)")
            except (KeyError, ValueError):
                pass
        opponent_label = f"PvPoke group: {args.group} ({len(opponents)} mons)"
        logger.info(f"  Opponents: {opponent_label}")
    elif args.opponents_file:
        # Read a custom opponent list from a text file (one species per
        # line, # comments / blank lines ignored). Same downstream
        # handling as --opponents: moveset per species resolved via
        # get_default_moveset, focal species appended if missing.
        path = args.opponents_file
        with open(path) as f:
            opponents = [
                line.strip() for line in f
                if line.strip() and not line.lstrip().startswith('#')
            ]
        if args.species not in opponents:
            opponents.append(args.species)
            logger.info(f"  (added {args.species} to opponents for mirror analysis)")
        focal_in_opponents = True
        opponent_label = (f"Custom pool from {os.path.basename(path)} "
                          f"({len(opponents)} mons)")
        logger.info(f"  {len(opponents)} opponents from {path}")
        opp_movesets_full = []
        to_remove = []
        for opp in opponents:
            try:
                opp_fast, opp_charged = get_default_moveset(opp, league=args.league)
                opp_movesets_full.append((opp_fast, opp_charged))
            except (KeyError, ValueError) as _e:
                logger.warning(f"skipping {opp}: {_e}")
                to_remove.append(opp)
        for opp in to_remove:
            opponents.remove(opp)
    else:
        screen_n = args.screen_opponents or args.opponents
        opponents = get_top_opponents(args.league, args.opponents)
        # Always include focal species for mirror analysis (append if not in top N)
        if args.species not in opponents:
            opponents.append(args.species)
            logger.info(f"  (added {args.species} to opponents for mirror analysis)")
        focal_in_opponents = True
        opponent_label = f"Top {len(opponents)} from {args.league} rankings"
        logger.info(f"  {len(opponents)} meta opponents (top from {args.league} rankings)")

        # Resolve opponent movesets from rankings defaults
        opp_movesets_full = []
        to_remove = []
        for opp in opponents:
            try:
                opp_fast, opp_charged = get_default_moveset(opp, league=args.league)
                opp_movesets_full.append((opp_fast, opp_charged))
            except KeyError:
                logger.warning(f"skipping {opp} (no default moveset)")
                to_remove.append(opp)
        for opp in to_remove:
            idx = opponents.index(opp)
            opponents.pop(idx)

    # Auto-include opponents named by TOML anchors so anchor-flip matching
    # works even when those opponents aren't in the top-N rankings. Only
    # fires when a threshold_registry is loaded (explicit or auto-discovered).
    if threshold_registry is not None:
        _sp_for_opps = threshold_registry.species(args.species)
        if _sp_for_opps is not None:
            _lt_for_opps = _sp_for_opps.leagues.get(args.league.capitalize())
            if _lt_for_opps is not None:
                _toml_opps = set()
                for _a in _lt_for_opps.anchors.values():
                    _opp = getattr(_a, 'opponent', None) or getattr(_a, 'opponent_species', None)
                    if _opp and _opp not in opponents:
                        _toml_opps.add(_opp)
                for _opp in sorted(_toml_opps):
                    try:
                        _opp_fast, _opp_charged = get_default_moveset(
                            _opp, league=args.league)
                        opponents.append(_opp)
                        opp_movesets_full.append((_opp_fast, _opp_charged))
                    except (KeyError, ValueError):
                        logger.warning(f"TOML anchor opponent {_opp} "
                                       f"has no default moveset, skipping")
                if _toml_opps:
                    _added = sorted(_toml_opps & set(opponents))
                    if _added:
                        logger.info(f"  (added {len(_added)} TOML anchor opponent(s): "
                                    f"{', '.join(_added)})")

    # Append attack-weighted opponent variants for any species that has a
    # `<species>_atk_weighted` shared spread defined. This is how RyanSwag-style
    # atk-weighted sweeps surface alongside rank-1 defaults without editing
    # each per-species TOML. See docs/ryanswag_methodology_gap_analysis.md §1 T9.
    opponents, opp_movesets_full, _atk_added = expand_opponents_with_variants(
        opponents, opp_movesets_full, threshold_registry, args.league,
    )
    if _atk_added:
        logger.info(f"  (added {len(_atk_added)} atk-weighted variant(s): "
                    f"{', '.join(_atk_added)})")

    opp_iv_labels = {'pvpoke': 'PvPoke defaults', 'rank1': 'rank 1 (stat product)', 'both': 'both (PvPoke + rank 1)'}
    opp_iv_label = opp_iv_labels.get(args.opp_ivs, args.opp_ivs)
    logger.info(f"  Shield scenario(s): {shield_scenarios}")
    logger.info(f"  Opponent IVs: {opp_iv_label}")
    if thresholds:
        for name, thresh in thresholds.items():
            logger.info(f"  Threshold: {name} - {_threshold_desc(thresh)}")

    # Determine screen opponents
    if args.group:
        screen_opponents = opponents
        screen_opp_movesets = opp_movesets_full
    else:
        screen_n = args.screen_opponents or args.opponents
        screen_opponents = opponents[:screen_n]
        screen_opp_movesets = opp_movesets_full[:screen_n]

    # Phase 1: Screen movesets
    # For screening and the initial sweep, use 'pvpoke' when 'both' is requested
    opp_iv_mode = 'pvpoke' if args.opp_ivs == 'both' else args.opp_ivs
    surviving = screen_movesets(
        args.species, movesets, args.league, args.shadow,
        screen_opponents, screen_opp_movesets, shield_scenarios,
        args.top_movesets, opp_iv_mode=opp_iv_mode,
        threshold_registry=threshold_registry,
    )

    # Phase 2: Full IV sweep for each surviving moveset
    all_moveset_results = []
    main_slayer_iter_result = None  # populated by first moveset's --mirror-slayer pass
    for mi, (fast_id, charged_ids) in enumerate(surviving):
        label = moveset_label(fast_id, charged_ids)
        logger.info(f"  Phase 2 [{mi+1}/{len(surviving)}]: {label}")
        logger.info(f"    Simming 4096 IVs × {len(opponents)} opponents "
                    f"× {len(shield_scenarios)} scenario(s)...")
        t0 = time.time()

        results, n_sims, canonical_scores, canonical_meta = iv_sweep(
            args.species, fast_id, charged_ids, args.league, args.shadow,
            opponents, opp_movesets_full, shield_scenarios,
            opp_iv_mode=opp_iv_mode,
            iv_floor=args.iv_floor,
            log_path=log_path, verbose=args.verbose,
            threshold_registry=threshold_registry,
            reserve_cpus=args.reserve_cpus,
        )

        elapsed = time.time() - t0
        rate = n_sims / elapsed if elapsed > 0 else 0
        logger.info(f"    {n_sims:,} sims in {elapsed:.1f}s ({rate:,.0f} sims/s)")

        # Auto-discover thresholds from the first moveset if none provided
        if thresholds is None and mi == 0:
            auto = auto_discover_thresholds(results)
            if auto:
                thresholds = auto
                logger.info(f"    Auto-discovered {len(thresholds)} threshold tier(s):")
                for name, thresh in thresholds.items():
                    logger.info(f"      {name}: {_threshold_desc(thresh)}")

        # Slayer discovery: always check for mirror slayer thresholds on first moveset
        if mi == 0:
            mirror_idx = None
            for oi, opp_name in enumerate(opponents):
                if opp_name == args.species or opp_name.replace(' (Shadow)', '') == args.species:
                    mirror_idx = oi
                    break
            if mirror_idx is not None:
                slayer_thresh, slayer_scored = discover_slayer_thresholds(
                    results, mirror_idx, len(shield_scenarios), args.species
                )
                if slayer_scored:
                    # Community nicknames for slayer builds. Default = full species name.
                    SLAYER_NICKNAMES = {
                        'Annihilape': 'Ape',
                        'Galarian Stunfisk': 'GFisk',
                        'Stunfisk (Galarian)': 'GFisk',
                    }
                    short = SLAYER_NICKNAMES.get(args.species, args.species)
                    slayer_name = f'{short} Slayer'

                    max_wins = slayer_scored[0][0]
                    n_winners = sum(1 for w, _, _ in slayer_scored if w == max_wins)
                    n_total = len(slayer_scored)
                    n_scen = len(shield_scenarios)

                    if slayer_thresh and any(v > 0 for v in slayer_thresh.values()):
                        logger.info(f"    {slayer_name}: {n_winners}/{n_total} IVs win {max_wins}/{n_scen} mirror scenarios")
                        logger.info(f"      Required floor: {_threshold_desc(slayer_thresh)}")
                        # Cost analysis: best slayer IV's avg score vs best avg score IV
                        top_slayer = slayer_scored[0][2]
                        top_avg_iv = results[0]
                        avg_diff = top_slayer['avg_score'] - top_avg_iv['avg_score']
                        logger.info(f"      Best slayer IV: {top_slayer['atk_iv']}/{top_slayer['def_iv']}/{top_slayer['sta_iv']} "
                                    f"(avg score {top_slayer['avg_score']:.1f}, "
                                    f"vs avg-best {top_avg_iv['avg_score']:.1f}, cost {avg_diff:+.1f})")
                        if thresholds is None:
                            thresholds = {}
                        if slayer_name not in thresholds:
                            new_thresholds = {slayer_name: slayer_thresh}
                            new_thresholds.update(thresholds)
                            thresholds = new_thresholds
                    elif max_wins == n_scen:
                        logger.info(f"    {slayer_name}: all IVs win the mirror - no slayer threshold needed")
                    elif max_wins == 0:
                        logger.info(f"    {slayer_name}: no IV beats the mirror")
                    else:
                        logger.info(f"    {slayer_name}: {n_winners}/{n_total} IVs win {max_wins}/{n_scen} mirror scenarios "
                                    f"but no clear stat floor distinguishes them")

        # Iterative slayer discovery (Nash-style) on the first moveset
        slayer_iter_result = None
        if mi == 0 and args.mirror_slayer and mirror_idx is not None:
            logger.info(f"  Mirror slayer iteration (metric={args.mirror_slayer_metric}, "
                        f"max_rounds={args.mirror_slayer_rounds}):")
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from slayer_cache import SlayerCache, compute_cache_key
            base = get_species(args.species)
            base_stats_dict = {'atk': base['atk'], 'def': base['def'], 'hp': base['hp']}
            fast_moves_db, charged_moves_db = get_moves()
            cache_key = compute_cache_key(
                args.species, args.league, args.shadow,
                fast_moves_db.get(fast_id, {}),
                [charged_moves_db.get(cid, {}) for cid in charged_ids],
                base_stats_dict,
                shield_scenarios=shield_scenarios,
            )
            slayer_cache = SlayerCache(cache_key=cache_key, disk=not args.no_cache)

            # Round 0 opponent: PvPoke default
            try:
                _lv, da, dd, ds = pvpoke_default_ivs(args.species, league=args.league)
                initial_opp_iv = (da, dd, ds)
            except (KeyError, ValueError):
                initial_opp_iv = None

            if initial_opp_iv:
                t_iter = time.time()
                slayer_iter_result = iterative_slayer_discovery(
                    args.species, args.league, args.shadow,
                    fast_id, charged_ids, shield_scenarios,
                    initial_opp_iv,
                    max_rounds=args.mirror_slayer_rounds,
                    top_per_round=args.mirror_slayer_pool,
                    cache=slayer_cache,
                    metric=args.mirror_slayer_metric,
                    iv_floor=args.iv_floor,
                    log_path=log_path, verbose=args.verbose,
                    reserve_cpus=args.reserve_cpus,
                )
                # Early-exit shapes from iterative_slayer_discovery return
                # a dict with only an 'error' key (e.g. when the initial
                # opponent IV is pruned by --species-iv-floor). Convert
                # to an empty-but-valid stub so the downstream slayer
                # processing block runs as a no-op rather than crashing
                # on missing keys ('rounds_run', 'history', etc.).
                if 'error' in slayer_iter_result:
                    logger.warning(f"Slayer iteration skipped: "
                                   f"{slayer_iter_result['error']}")
                    slayer_iter_result = {
                        'history': [], 'final': [],
                        'rounds_run': 0, 'converged': False,
                        'cache_stats': '(skipped)',
                        'resolved_anchors': [],
                        'categories': {},
                    }
                # Stash the metric/rounds for HTML rendering
                slayer_iter_result['metric'] = args.mirror_slayer_metric
                slayer_iter_result['max_rounds_arg'] = args.mirror_slayer_rounds
                slayer_cache.save()
                elapsed_iter = time.time() - t_iter
                logger.info(f"    {slayer_iter_result['rounds_run']} rounds in {elapsed_iter:.1f}s "
                            f"({'converged' if slayer_iter_result['converged'] else 'max rounds'})")
                logger.info(f"    {slayer_iter_result['cache_stats']}")
                # Show per-round top counts
                for ri, top in enumerate(slayer_iter_result['history']):
                    if not top:
                        continue
                    max_w = top[0]['total_wins']
                    n_at_max = sum(1 for r in top if r['total_wins'] == max_w)
                    # How many unique stat profiles (deduped opponents for next round)
                    n_unique = len({(round(r['atk'], 4), round(r['def_'], 4), int(r['hp'])) for r in top})
                    logger.info(f"    Round {ri}: {len(top)} IVs in pool "
                                f"({n_unique} unique stat profiles, "
                                f"{n_at_max} at max wins {max_w}, "
                                f"top avg score: {top[0]['avg_score']:.1f})")

                # Resolve anchors so categorize_slayers can tag each survivor
                # with what it clears. Two layers feed the resolver:
                #   1. Explicit anchors from --thresholds + --anchor-file +
                #      --anchor (already in threshold_registry).
                #   2. Auto-generated fallback anchors (built per-run from
                #      the dive's opponent set + survivor cohort) for any
                #      anchor kind the user did NOT explicitly provide.
                survivors = slayer_iter_result['final']
                resolved = []
                if survivors:
                    try:
                        focal_entry_for_anchors = next(
                            m for m in load_gamemaster()['pokemon']
                            if m['speciesName'] == args.species
                        )
                        focal_types_for_anchors = parse_types(focal_entry_for_anchors)
                        fm_dict = fast_moves_db.get(fast_id) or {}
                        cm_dicts = [charged_moves_db[c] for c in charged_ids
                                    if c in charged_moves_db]
                        moves_for_anchors = []
                        if fm_dict:
                            moves_for_anchors.append(fm_dict)
                        moves_for_anchors.extend(cm_dicts)
                        # The BP scan range should span the full possible
                        # focal atk space for this species, not the cohort
                        # range. With a converged cohort atk range collapses
                        # to almost a single point and Level 3 enumeration
                        # finds nothing - the interesting BPs lie BELOW the
                        # cohort (already cleared by every survivor), and we
                        # want to tag each survivor with which ones it passes.
                        all_ivs = iv_rank(
                            args.species, league=args.league, shadow=args.shadow,
                        )
                        all_atks = [iv['atk'] for iv in all_ivs]
                        atk_min = min(all_atks)
                        atk_max = max(all_atks)
                        all_defs = [iv['def_'] for iv in all_ivs]
                        def_min = min(all_defs)
                        def_max = max(all_defs)

                        # Determine which anchor kinds the user already
                        # provided so the auto-fallback only fills gaps.
                        existing_kinds: set[str] = set()
                        if threshold_registry is not None:
                            sp_explicit = threshold_registry.species(args.species)
                            if sp_explicit is not None:
                                lt_explicit = sp_explicit.leagues.get(
                                    args.league.capitalize()
                                )
                                if lt_explicit is not None:
                                    for a in lt_explicit.anchors.values():
                                        existing_kinds.add(a.kind)

                        survivor_iv_tuples = [r['iv'] for r in survivors]
                        auto_overlay = build_auto_anchors(
                            species=args.species,
                            league=args.league,
                            opponent_species=list(opponents),
                            fast_move_id=fast_id,
                            survivor_ivs=survivor_iv_tuples,
                            existing_anchor_kinds=existing_kinds,
                        )
                        # Merge: auto is the base, explicit overlays it so
                        # any user-provided anchor wins on collision (we
                        # already gate by kind so collisions shouldn't
                        # happen, but defense in depth).
                        if threshold_registry is None:
                            effective_registry = auto_overlay
                        else:
                            effective_registry = auto_overlay.merge(threshold_registry)

                        # Count how many auto vs explicit for the log line
                        n_auto_anchors = 0
                        sp_auto = auto_overlay.species(args.species)
                        if sp_auto is not None:
                            lt_auto = sp_auto.leagues.get(
                                args.league.capitalize()
                            )
                            if lt_auto is not None:
                                n_auto_anchors = len(lt_auto.anchors)

                        resolved = resolve_anchors(
                            effective_registry, args.species, args.league,
                            moves_for_anchors, focal_types_for_anchors,
                            atk_min, atk_max,
                            def_min=def_min, def_max=def_max,
                            focal_shadow=args.shadow,
                        )
                        if resolved:
                            n_parents = len({r.parent for r in resolved})
                            n_auto_parents = len({
                                r.parent for r in resolved
                                if r.parent.startswith('auto_')
                            })
                            logger.info(f"    Resolved {len(resolved)} anchors "
                                        f"({n_parents} parents, "
                                        f"{n_auto_parents} auto-generated)")
                    except Exception as e:
                        logger.warning(f"anchor resolution failed: {e}")
                        resolved = []

                # Stash on the iter_result for HTML rendering
                slayer_iter_result['resolved_anchors'] = resolved

                categories = categorize_slayers(
                    survivors, resolved_anchors=resolved,
                )
                # Build cross-category map (IV -> set of category names)
                iv_categories = {}
                for cn, civs in categories.items():
                    for r in civs:
                        iv_categories.setdefault(r['iv'], set()).add(cn)
                CAT_AB = {'Atk Slayer': 'A', 'Bulk Slayer': 'B', 'CMP Slayer': 'C'}
                logger.info(f"    Final survivors classified into "
                            f"{sum(1 for v in categories.values() if v)} categories:")
                for cat_name, cat_ivs in categories.items():
                    if not cat_ivs:
                        continue
                    # Console view: show top `mirror_slayer_show` per category
                    shown = cat_ivs[:args.mirror_slayer_show]
                    logger.debug(f"      {cat_name} ({len(shown)} of {len(cat_ivs)}):")
                    for r in shown:
                        a, d, s = r['iv']
                        others = sorted(iv_categories.get(r['iv'], set()) - {cat_name})
                        also = ' [+' + ''.join(CAT_AB.get(o, '?') for o in others) + ']' if others else ''
                        # Anchor-tag labels for Atk / CMP rows
                        tag_bits = []
                        for parent, subs in sorted(r.get('_anchor_tags', {}).items()):
                            labels = [a.label or a.name for a in subs]
                            tag_bits.append(f"{parent}[{','.join(labels)}]")
                        tag_str = ' ' + ' '.join(tag_bits) if tag_bits else ''
                        logger.debug(f"        {a:2d}/{d:2d}/{s:2d}  "
                                     f"atk={r['atk']:.2f} def={r['def_']:.2f} hp={r['hp']}  "
                                     f"wins {r['total_wins']}/"
                                     f"{r['n_pairs']*len(shield_scenarios)} "
                                     f"avg {r['avg_score']:.1f}{also}{tag_str}")
                # Stash for HTML rendering
                slayer_iter_result['categories'] = categories
                main_slayer_iter_result = slayer_iter_result

        # Classify by thresholds if provided
        if thresholds:
            for r in results:
                r['_tier'] = classify_iv(r, thresholds)
            tier_counts = {}
            for r in results:
                t = r.get('_tier')
                if t:
                    tier_counts[t] = tier_counts.get(t, 0) + 1
            logger.info(f"    Threshold hits: {tier_counts if tier_counts else 'none'}")

        # Emit the top-20 table as RESULT records so the console output
        # stays column-aligned (no timestamp prefix); the file handler
        # still captures each line with full detail.
        logger.result('')
        logger.result(f"    Top 20 IV spreads by average battle score:")
        hdr = (f"    {'Rank':>4s}  {'IVs':>8s}  {'Lvl':>5s}  {'CP':>4s}  "
               f"{'Atk':>7s}  {'Def':>7s}  {'HP':>3s}  "
               f"{'SP Rank':>7s}  {'Avg Score':>9s}")
        if thresholds:
            hdr += f"  {'Tier':>12s}"
        logger.result(hdr)
        logger.result(f"    {'-' * (70 + (14 if thresholds else 0))}")
        for r in results[:20]:
            line = (f"    {r['battle_rank']:4d}  "
                    f"{r['atk_iv']:2d}/{r['def_iv']:2d}/{r['sta_iv']:2d}  "
                    f"{r['level']:5.1f}  {r['cp']:4d}  "
                    f"{r['atk']:7.2f}  {r['def_']:7.2f}  {r['hp']:3d}  "
                    f"{'#'+str(r['sp_rank']):>7s}  {r['avg_score']:9.1f}")
            if thresholds:
                tier = r.get('_tier', '')
                line += f"  {tier or '':>12s}"
            logger.result(line)
        logger.result('')

        all_moveset_results.append((fast_id, charged_ids, results,
                                     canonical_scores, canonical_meta))

    # HTML output
    if args.html:
        if args.interactive:
            # Interactive mode: embed all data, JS-driven dropdowns.
            # Determine composite (opp_iv, bait) modes to run. The axis is
            # 2D: opp-IVs × bait-shields. Composite modes are encoded as
            # a string ('pvpoke', 'pvpoke:nobait', 'rank1', 'rank1:nobait')
            # so score_arrays key format ``f'{mi}_{mode}'`` doesn't need
            # schema changes.
            if args.opp_ivs == 'both':
                _base_opp_modes = ['pvpoke', 'rank1']
            else:
                _base_opp_modes = [opp_iv_mode]
            if args.bait == 'both':
                _bait_modes = ['bait', 'nobait']
            elif args.bait == 'off':
                _bait_modes = ['nobait']
            else:
                _bait_modes = ['bait']
            opp_iv_modes_to_run = [
                compose_mode(om, bm)
                for om in _base_opp_modes
                for bm in _bait_modes
            ]

            # Force all shield scenarios for interactive mode
            if shield_scenarios == [(1, 1)]:
                logger.info("  Interactive mode: auto-expanding to all 9 shield scenarios")
                shield_scenarios = ALL_NINE
                # Re-run sweeps with all scenarios
                all_moveset_results = []
                for mi, (fast_id, charged_ids) in enumerate(surviving):
                    label = moveset_label(fast_id, charged_ids)
                    scores_by_mode = {}
                    meta = None
                    for mode in opp_iv_modes_to_run:
                        mode_label = mode_pretty_label(mode)
                        logger.info(f"  Interactive sweep [{mi+1}/{len(surviving)}] "
                                    f"{label} ({mode_label}, all shields)...")
                        t0 = time.time()
                        results, n_sims, cs, cm = iv_sweep(
                            args.species, fast_id, charged_ids, args.league, args.shadow,
                            opponents, opp_movesets_full, shield_scenarios,
                            opp_iv_mode=mode,
                            iv_floor=args.iv_floor,
                            log_path=log_path, verbose=args.verbose,
                            threshold_registry=threshold_registry,
                            reserve_cpus=args.reserve_cpus,
                        )
                        elapsed = time.time() - t0
                        rate = n_sims / elapsed if elapsed > 0 else 0
                        logger.info(f"    {n_sims:,} sims in {elapsed:.1f}s ({rate:,.0f} sims/s)")
                        scores_by_mode[mode] = cs
                        if meta is None:
                            meta = cm
                    all_moveset_results.append((fast_id, charged_ids, results,
                                                scores_by_mode, meta))
            else:
                # Already ran with the right scenarios - repack Phase 2
                # results and fill in any additional composite modes
                # (extra opp-IV mode and/or bait mode) that weren't run
                # originally. The cached Phase 2 result corresponds to
                # ``opp_iv_mode`` at bait-on (the Phase 2 default).
                cached_mode = opp_iv_mode  # bait-on, no :nobait suffix
                new_results = []
                for fast_id, charged_ids, results, cs, cm in all_moveset_results:
                    scores_by_mode = {cached_mode: cs}
                    for mode in opp_iv_modes_to_run:
                        if mode in scores_by_mode:
                            continue
                        mode_label = mode_pretty_label(mode)
                        logger.info(f"  Running {moveset_label(fast_id, charged_ids)} "
                                    f"({mode_label})...")
                        t0 = time.time()
                        _, n2, cs2, _ = iv_sweep(
                            args.species, fast_id, charged_ids, args.league, args.shadow,
                            opponents, opp_movesets_full, shield_scenarios,
                            opp_iv_mode=mode,
                            iv_floor=args.iv_floor,
                            log_path=log_path, verbose=args.verbose,
                            threshold_registry=threshold_registry,
                            reserve_cpus=args.reserve_cpus,
                        )
                        elapsed = time.time() - t0
                        logger.info(f"    {n2:,} sims in {elapsed:.1f}s")
                        scores_by_mode[mode] = cs2
                    new_results.append((fast_id, charged_ids, results,
                                        scores_by_mode, cm))
                all_moveset_results = new_results

            # Resolve and run reference moveset
            reference_idx = -1
            ref_moveset = resolve_reference_moveset(
                args.species, args.league, args.shadow, args.reference)
            if ref_moveset:
                ref_fast, ref_charged = ref_moveset
                ref_label = moveset_label(ref_fast, ref_charged)
                # Check if reference is already a surviving moveset
                for mi, entry in enumerate(all_moveset_results):
                    existing_label = moveset_label(entry[0], entry[1])
                    if existing_label == ref_label:
                        reference_idx = mi
                        break
                if reference_idx < 0:
                    # Run reference sweep
                    logger.info(f"  Reference sweep: {ref_label}")
                    ref_scores_by_mode = {}
                    ref_meta = None
                    for mode in opp_iv_modes_to_run:
                        t0 = time.time()
                        ref_results, ref_n, ref_cs, ref_cm = iv_sweep(
                            args.species, ref_fast, ref_charged, args.league, args.shadow,
                            opponents, opp_movesets_full, shield_scenarios,
                            opp_iv_mode=mode,
                            iv_floor=args.iv_floor,
                            log_path=log_path, verbose=args.verbose,
                            threshold_registry=threshold_registry,
                            reserve_cpus=args.reserve_cpus,
                        )
                        elapsed = time.time() - t0
                        rate = ref_n / elapsed if elapsed > 0 else 0
                        logger.info(f"    {ref_n:,} sims in {elapsed:.1f}s ({rate:,.0f} sims/s)")
                        ref_scores_by_mode[mode] = ref_cs
                        if ref_meta is None:
                            ref_meta = ref_cm
                    reference_idx = len(all_moveset_results)
                    all_moveset_results.append((ref_fast, ref_charged, ref_results,
                                                ref_scores_by_mode, ref_meta))

            # Build moveset_data for interactive HTML
            moveset_data = []
            for entry in all_moveset_results:
                fast_id, charged_ids = entry[0], entry[1]
                scores_by_mode = entry[3]
                meta = entry[4]
                moveset_data.append({
                    'label': moveset_label_raw(fast_id, charged_ids),
                    'scores': scores_by_mode,
                    'meta': meta,
                })

            if args.split_movesets and len(moveset_data) > 1:
                # Per-moveset split: emit N files, one per moveset. The
                # filesystem plan is computed up-front so every file
                # knows every sibling's URL for its navigation dropdown.
                split_files = _build_split_file_list(
                    moveset_data, reference_idx, args.html,
                )
                logger.info(f"  Split mode: emitting {len(split_files)} per-moveset HTML files")
                # Precompute analysis on the first file - it always uses
                # moveset_idx=0 scores so the result is identical across
                # all split files. Avoids re-running the expensive anchor
                # aggregator + matchup boundary sweeps N times. The empty
                # dict gets populated by the first call; subsequent calls
                # see it non-empty and skip recomputation.
                _cached_analysis = {}
                for finfo in split_files:
                    mi = finfo['moveset_idx']
                    filtered_md, filtered_ref_idx = _filter_moveset_data_for_split(
                        moveset_data, mi, reference_idx,
                    )
                    split_info = {'files': split_files, 'current': mi}
                    generate_interactive_html(
                        args.species, args.league, filtered_md, finfo['path'],
                        thresholds=thresholds, opponent_label=opponent_label,
                        shield_scenarios=shield_scenarios,
                        opponent_names=opponents,
                        opp_iv_modes=opp_iv_modes_to_run,
                        reference_idx=filtered_ref_idx,
                        standalone=args.standalone,
                        slayer_iter_result=main_slayer_iter_result,
                        cli_args_str=cli_args_str,
                        has_toml_tiers=_toml_tiers_loaded,
                        shadow=args.shadow,
                        split_info=split_info,
                        _precomputed_analysis=_cached_analysis,
                        article_slug=_article_slug,
                        threshold_registry=threshold_registry,
                        species_narrative=_species_narrative,
                        shared_plotly_dir=args.shared_plotly,
                    )
            else:
                if args.split_movesets:
                    logger.warning("--split-movesets: only one moveset surviving - "
                                   "writing a single file")
                generate_interactive_html(
                    args.species, args.league, moveset_data, args.html,
                    thresholds=thresholds, opponent_label=opponent_label,
                    shield_scenarios=shield_scenarios,
                    opponent_names=opponents,
                    opp_iv_modes=opp_iv_modes_to_run,
                    reference_idx=reference_idx,
                    standalone=args.standalone,
                    slayer_iter_result=main_slayer_iter_result,
                    cli_args_str=cli_args_str,
                    has_toml_tiers=_toml_tiers_loaded,
                    shadow=args.shadow,
                    article_slug=_article_slug,
                    threshold_registry=threshold_registry,
                    species_narrative=_species_narrative,
                    shared_plotly_dir=args.shared_plotly,
                )
        else:
            # Static mode (original behavior)
            generate_html(args.species, args.league, all_moveset_results, args.html,
                          thresholds=thresholds, opponent_label=opponent_label,
                          shield_scenarios=shield_scenarios,
                          opponent_names=opponents, opp_iv_mode=opp_iv_mode,
                          standalone=args.standalone,
                          cli_args_str=cli_args_str,
                          shared_plotly_dir=args.shared_plotly)

    logger.info("Done.")


if __name__ == '__main__':
    main()
