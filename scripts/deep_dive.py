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
import tomllib
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gopvpsim.pokemon import (
    Pokemon, get_pokemon_entry, get_species, iv_rank, CPM, best_level,
    LEAGUE_CAPS, LEAGUE_MAX_LEVEL, cp as calc_cp, pvpoke_default_ivs,
)
from gopvpsim.moves import get_moves, type_effectiveness, stab
from gopvpsim.attribution import PVPOKE_ATTRIBUTION_HTML, support_footer_html
from gopvpsim.theme import (
    GRUVBOX_CREDIT_HTML,
    DEFAULT_THEME,
    _THEME_ORDER,
    _TOKENS as _THEME_TOKENS,
    data_theme_attr,
    theme_css,
    theme_head_script,
    theme_picker_html,
)
from gopvpsim.data import (
    load_gamemaster, load_rankings, get_default_moveset, parse_types,
    sprite_data_uri, load_group as fetch_group,
)
from gopvpsim.battle import (
    BattlePokemon, simulate,
    pvpoke_dp, pvpoke_simulate_shield,
)
from gopvpsim.formchange import attach_form_change
from gopvpsim.thresholds import (
    ThresholdRegistry, load_file as load_threshold_file, as_legacy_dict,
)
from gopvpsim.anchors import (
    resolve_anchors, ResolvedAnchor, build_auto_anchors,
    derive_short_name,
)
from gopvpsim.display import apply_dive_title_override, pretty_species
from gopvpsim.efficiency import efficient_frontier
sys.path.insert(0, os.path.dirname(__file__))
import deep_dive_analysis as analysis
import deep_dive_rendering as rendering
import deep_dive_slayer as slayer
from deep_dive_logging import (
    init_logger, worker_log_setup, get_logger,
)

logger = get_logger()


# ---------------------------------------------------------------------------
# Form-change explainer notes
# ---------------------------------------------------------------------------
# Rendered near the top of a form-changing species' dive page so a reader
# understands the dive's STARTING form and how the form switches in battle.
# Keyed by focal speciesName. Kept qualitative on purpose (no per-form stat
# numbers) so nothing here can drift out of sync with the sim. Extend for
# Mimikyu / Morpeko when those dives want a note. This is code, not a
# thresholds/articles ship-mode narrative TOML.
def _form_change_callout(body_html: str) -> str:
    return (
        '<div style="background:var(--callout-bg);color:var(--callout-fg);'
        'padding:12px 16px;border-radius:0;margin:10px 0;'
        'border:1px solid var(--callout-auto)">'
        f'<b>Form change:</b> {body_html}</div>\n'
    )


_FORM_CHANGE_NOTES = {
    'Aegislash (Shield)': _form_change_callout(
        'This dive is the real Aegislash. It <b>starts in Shield</b> form '
        '(bulky, very low attack) using a zero-damage fast move that only '
        'builds energy, then swaps to <b>Blade</b> form (glassy, high attack) '
        'on its first charged move for the rest of the fight. If it uses a '
        'shield it reverts to Shield form. The sim models this natively from '
        'the gamemaster form-change data.'),
    'Aegislash (Blade)': _form_change_callout(
        'The real Aegislash always <em>starts</em> a battle in Shield form and '
        'only becomes Blade after its first charged move. This dive is a '
        'hypothetical that <b>starts in Blade</b> form (glassy, high attack) '
        'from turn one, to isolate Blade-form offense: a starting state you '
        'cannot reach in an actual battle. The form change is still live: if '
        'it shields, it reverts to Shield form. For the realistic build, see '
        'the Aegislash (Shield) dive.'),
    'Mimikyu': _form_change_callout(
        'Mimikyu starts in its <b>Disguise</b> form. The first unshielded '
        'charged move it takes is absorbed (reduced to 1 damage), busting the '
        'disguise; from then on Mimikyu is in <b>Busted</b> form with a '
        'permanent -1 defense for the rest of the battle. This dive simulates '
        'the Disguise-intact start, with the bust modeled natively from the '
        'gamemaster form-change data.'),
    'Mimikyu (Busted)': _form_change_callout(
        'The real Mimikyu always <em>starts</em> a battle in its Disguise '
        'form; only after the disguise is busted by the first unshielded '
        'charged hit does it enter <b>Busted</b> form with a permanent -1 '
        'defense. This dive is a hypothetical that <b>starts in Busted</b> '
        'form from turn one (the -1 defense applied immediately), to isolate '
        'the post-bust state -- a starting state you cannot reach in an '
        'actual battle. For the realistic Disguise-intact start, see the '
        'Mimikyu dive.'),
}


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
# Threshold classification
# ---------------------------------------------------------------------------

discover_slayer_thresholds = slayer.discover_slayer_thresholds


iterative_slayer_discovery = slayer.iterative_slayer_discovery


build_slayer_archetypes = slayer.build_slayer_archetypes

IVCategory = rendering.IVCategory
parse_mode = rendering.parse_mode
parse_energy = rendering.parse_energy
compose_mode = rendering.compose_mode
mode_pretty_label = rendering.mode_pretty_label


def build_iv_categories(data_obj, slayer_categories=None,
                        iv_idx_by_triple=None, matchup_data=None):
    """Build the unified ``list[IVCategory]`` for a deep-dive run.

    Inputs:
        data_obj: the JS-bound data object (already populated with tiers,
            ivAllTiers, ivAtk/ivDef/ivHp, nIvs, ivA/ivD/ivS).
        slayer_categories: dict from ``build_slayer_archetypes``. May be None
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
    # Iterate build_slayer_archetypes output and lift each non-empty bucket
    # into an IVCategory. The slayer survivors carry the rich
    # _anchor_tags dict that we want to preserve as member_meta so the
    # renderer can show which specific anchors fired per IV.
    if slayer_categories:
        SLAYER_KIND_DESC = {
            'Anchors-First Slayer': 'IVs that clear the maximum achievable '
                                    'number of counted anchor parents '
                                    '(break/bulkpoints first), ranked by '
                                    'mirror CMP among the survivors.',
            'CMP-First Slayer': 'The max-attack "lab mon" spreads — win '
                                'Charge Move Priority first; the anchor '
                                'checklist reports what each clears vs '
                                'sacrifices.',
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
    # "Anchors-First Slayer member with mirror wins 45/132, also clears
    # Top 5% (HP≥139)".
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

    categories = _merge_matchup_variant_dupes(categories)

    return categories


# Form/shadow parentheticals that mark a genuinely distinct opponent and
# must NEVER be folded into a base species. Anything else in a trailing
# parenthetical (Bug Bite, Close Combat+Rage Fist, atk-weighted, ...) is an
# alt-moveset / weighting variant and IS foldable -- but only when stripping
# it yields a name that another opponent in the same pool actually uses.
_FORM_SHADOW_TAGS = frozenset({
    'Shadow', 'Blade', 'Shield', 'Galarian', 'Female', 'Male', 'Super',
    'Alolan', 'Hisuian', 'Origin', 'Altered', 'Incarnate', 'Therian',
    'Standard', 'Zen',
})


def _base_opponent(opp, all_opps):
    """Fold a trailing alt-moveset/weighting parenthetical off an opponent
    name, but only when the stripped stem is itself a present opponent.

    ``Medicham (atk-weighted)`` -> ``Medicham`` (when plain ``Medicham`` is in
    the pool); ``Aegislash (Blade)`` stays put (form tag); ``Quagsire (Shadow)
    (Aqua Tail+Stone Edge)`` -> ``Quagsire (Shadow)`` (keeps the Shadow form,
    drops the moveset tag).
    """
    import re
    cur = opp
    while True:
        m = re.match(r'^(.*) \(([^()]+)\)$', cur)
        if not m:
            break
        stem, tag = m.group(1), m.group(2)
        if tag in _FORM_SHADOW_TAGS:
            break
        if stem in all_opps:
            cur = stem
            continue
        break
    return cur


def _merge_matchup_variant_dupes(categories):
    """Collapse sibling-opponent-variant matchup cards that are exact stat
    duplicates.

    Two matchup categories merge only when they share the same base opponent
    (variant tag stripped), the same shield scenario, the same bait mode, and
    the *identical* winning-IV set. That guarantees we never merge across
    different IVs or different base opponents -- the merged card is the same
    matchup, just simmed against an alt-moveset/weighting sibling of the
    opponent. The surviving card lists every merged variant in its
    ``matchup_conditions`` so no provenance is lost.

    Non-matchup categories pass through untouched and in place.
    """
    matchups = [c for c in categories if c.kind == 'matchup']
    if len(matchups) < 2:
        return categories

    all_opps = {c.matchup_conditions[0]['opponent']
                for c in matchups if c.matchup_conditions}

    # Bucket by the merge key; preserve first-seen order for stable output.
    buckets: dict = {}
    order: list = []
    for c in matchups:
        cond = c.matchup_conditions[0] if c.matchup_conditions else {}
        key = (_base_opponent(cond.get('opponent', ''), all_opps),
               tuple(cond.get('scenario', ())),
               cond.get('bait'),
               tuple(c.members))
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(c)

    merged_by_first: dict = {}
    for key in order:
        group = buckets[key]
        first = group[0]
        if len(group) == 1:
            merged_by_first[id(first)] = first
            continue
        # Collapse onto the first card; rename to the base opponent and list
        # every variant in matchup_conditions (so matchup_subtitle surfaces
        # them) and in the description.
        base_opp = key[0]
        variants = [g.matchup_conditions[0]['opponent'] for g in group]
        conds = [dict(g.matchup_conditions[0]) for g in group]
        scen = first.matchup_conditions[0]['scenario']
        scen_label = f'{scen[0]}v{scen[1]}'
        opp_iv_label = ('rank 1'
                        if first.matchup_conditions[0].get('opponent_ivs')
                        == 'rank1' else 'PvPoke default')
        merged = IVCategory(
            name=f'Beats {opp_iv_label} {base_opp} in the {scen_label}',
            kind='matchup',
            members=first.members,
            description=(
                f'IVs whose battle score meets the win threshold against '
                f'{opp_iv_label} {base_opp} in the {scen_label} shield '
                f'scenario. Identical winning spreads across these opponent '
                f'movesets/weightings: {", ".join(variants)}.'
            ),
            matchup_conditions=conds,
            member_meta=first.member_meta,
        )
        merged_by_first[id(first)] = merged

    # Reassemble: keep non-matchups in place; emit each bucket's (possibly
    # merged) card at the position of its first card, drop the trailing
    # duplicates.
    first_ids = {id(buckets[key][0]) for key in order}
    out: list = []
    for c in categories:
        if c.kind != 'matchup':
            out.append(c)
        elif id(c) in first_ids:
            out.append(merged_by_first[id(c)])
    return out


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


def _read_best_buddy_toml(species, shadow):
    """Read ``[<Species>.best_buddy]`` from the species threshold TOML.

    Returns ``{'compute': bool, 'default_display': int}`` with only the keys
    present in the file (empty dict if no file / table). Independent of the
    threshold registry -- a raw tomllib read mirroring the cd_prep / article
    pattern, so the best-buddy intent persists per species across re-dives.
    """
    slug = species.lower().replace(' ', '_').replace('(', '').replace(')', '')
    if shadow:
        slug += '_shadow'
    path = Path(__file__).resolve().parent.parent / 'thresholds' / f'{slug}.toml'
    if not path.exists():
        return {}
    key = species + (' (Shadow)' if shadow else '')
    try:
        with open(path, 'rb') as f:
            raw = tomllib.load(f)
        bb = raw.get(key, {}).get('best_buddy', {})
        out = {}
        if 'compute' in bb:
            out['compute'] = bool(bb['compute'])
        if 'default_display' in bb:
            out['default_display'] = int(bb['default_display'])
        return out
    except Exception:  # noqa: BLE001
        return {}


# Ship default for the dive-card opponent-IV robustness cohort (top-N
# stat-product IVs per opponent). Single source for the argparse default and
# the render_dive_html .get fallbacks (an old replay blob lacks the key).
DEFAULT_CARD_ROBUST_K = 512

# Dive-card recommendation-spread selection (Phase A v2): pick a variable 2-6
# set. When named anchors resolved, selection is a greedy set-cover over the
# specific opponent break/bulkpoints the lead reference misses (see the
# selection block in generate_analysis_sections). On --no-mirror-slayer dives
# there are no named anchors, so we fall back to DISTINCTNESS over each IV's
# WON-SET (the (scenario, opponent) matchups it wins, score >= 500): a candidate
# joins only if its won-set differs from every already-chosen spread by at least
# REC_DISTINCTNESS_MIN_SYMDIFF cells (symmetric difference). Symmetric
# difference, not net-new wins, is what collapses near-twins -- twins trade one
# matchup for another, so they add ~0 net-new wins but differ by only a cell or
# two. The two poles (rank-1 stat-product lead + attack/CMP pole) are always
# seeded, giving a floor of 2.
REC_DISTINCTNESS_MIN_SYMDIFF = 3
REC_MAX_SPREADS = 6

# Phase A.1 dive-card coverage tuning (Dragapult-Sim "OPTIMAL IVS" style).
#   REC_STRONG_POOL_N  -- battle-ranked top-N used as the "strong pool" for the
#                         rarity gate. It must be wide enough to include the
#                         deeply-bulky IVs the bulk pole sits on (those trade
#                         away too much battle score to reach the top ~50), so
#                         the high def-side bulkpoint tiers are present in the
#                         tier universe and counted honestly. Capped to nIvs.
#   REC_NOTABLE_MAX_CLEAR_FRAC -- a named (opponent, kind, threshold) tier is
#                         "notable" only if at most this fraction of the strong
#                         pool clears it. The Level-3 *_blkp_any anchors expand
#                         into a near-continuum of tiers per opponent, so a bulky
#                         IV clears every opponent's trivial LOWEST tier; without
#                         the gate the bulk pole "covers" everyone and
#                         differentiates nothing. Tuned on Tinkaton GL to surface
#                         the hard meta bulkpoints (Azumarill 143.03, G-Corsola
#                         143.04, Medicham 141.66) on the bulk pole and the hard
#                         breakpoints (Jellicent, Annihilape) on the attack pole,
#                         while the broad battle-#1 lead keeps no notable tier.
REC_STRONG_POOL_N = 512
REC_NOTABLE_MAX_CLEAR_FRAC = 0.25
# The "Why this IV?" two-#1s blurb only earns card space when the rank-1 stat
# product IV wins MEANINGFULLY MORE matchups than our battle-score #1 (the
# counterintuitive "why not the hundo?" case). Below this win-rate gap the two
# are interchangeable (Tinkaton/Shadow Corviknight are both within ~1%) and the
# blurb is suppressed.
REC_TWO_ONES_MIN_WINRATE_GAP = 0.03

_FORM_CHANGE_SPECIES_CACHE: dict = {}


def _species_has_form_change(species_name):
    """True if the species' gamemaster entry (looked up by EXACT name)
    declares a formChange, so its effective stats are NOT a safe dedup key
    (the alt form's stats are non-linear in raw IVs + level). Cached;
    defaults False on lookup miss.

    Exactness caveat: this keys on the supplied form NAME. It is correct for
    today's meta only because the sole opponent whose alt-form stats actually
    diverge (Aegislash) is pool-named by a formChange-bearing form
    ('Aegislash (Shield)'/'(Blade)' both carry formChange). Morpeko's pool
    name 'Morpeko (Hangry)' lacks formChange and so returns False here, but
    that is harmless: its two forms share identical baseStats, so effective-
    stat dedup is exact for it anyway. A FUTURE stat-divergent toggle/set
    species whose pool name lacks the formChange key would be silently
    misgrouped -- resolve to the base speciesId and check both forms if that
    ever ships."""
    if species_name in _FORM_CHANGE_SPECIES_CACHE:
        return _FORM_CHANGE_SPECIES_CACHE[species_name]
    gm = load_gamemaster()
    mon = next((m for m in gm['pokemon']
                if m['speciesName'] == species_name), None)
    has = bool(mon and mon.get('formChange'))
    _FORM_CHANGE_SPECIES_CACHE[species_name] = has
    return has


def opp_iv_robustness(focal_species, focal_fast, focal_charged, focal_shadow,
                      focal_ivs, opponent, opp_fast, opp_charged, opp_shadow,
                      league, shield_scenarios, k=512, dedup='signature',
                      mechanics='legacy', focal_max_level=None):
    """Opponent-IV robustness for ONE fixed focal IV vs ONE opponent.

    Sweeps the opponent across its top-``k`` stat-product IV spreads (the
    "top-512 ranks" robustness notion: do we beat this opponent regardless
    of which good IV it rolled?), groups those IVs into sets that fight
    bit-identical battles vs the fixed focal (``dedup``), sims one
    representative per group over every ``shield_scenarios`` pair, and
    weights each group by its size.

    ``dedup`` (see _opp_robustness_groups): 'signature' (default, exact
    damage-signature dedup, ~1.5x fewer sims than no-dedup on a top-512
    cohort), 'profile' (effective-stat dedup), or 'none' (one sim per IV,
    the test reference).

    Returns ``(weighted_wins, weighted_total)`` floats (caller sums across
    opponents and divides), or ``None`` if the opponent has no valid IVs.
    A win is focal ``pvpoke_score(0) > 500`` (>500 = focal won; 500 = tie).
    Opponents are built via make_battle_pokemon (raw IVs + shadow flag),
    so shadow multipliers are applied exactly once and form-change
    transforms (Aegislash) are wired up like the oracle path.

    Caveat (signature dedup): deep_dive_signature's CMP column uses
    effective atk, but the engine decides CMP on the unboosted cmp_atk
    (2026-06-13 fix). For shadow-MISMATCHED focal/opponent pairs the two can
    disagree in a narrow CMP band, so a rare IV could mis-group. Verified
    bit-identical to no-dedup on representative shadow + non-shadow cases
    (test_opp_iv_robustness_signature_dedup_is_exact); for a headline summary
    a 1-in-k misgroup shifts the % by <0.2% (invisible at integer display).
    See TODO "deep_dive_signature CMP predates cmp_atk" -- it may also touch
    the focal sweep.
    """
    from gopvpsim.pokemon import iv_rank
    ranked = iv_rank(opponent, league=league, shadow=opp_shadow)
    if not ranked:
        return None
    ranked = ranked[:k]
    a0, d0, s0 = focal_ivs
    focal_bp = make_battle_pokemon(focal_species, focal_fast, focal_charged,
                                   league, 2, a0, d0, s0, shadow=focal_shadow,
                                   max_level=focal_max_level)
    groups = _opp_robustness_groups(
        focal_bp, focal_species, focal_fast, focal_charged, focal_shadow,
        focal_ivs, opponent, opp_fast, opp_charged, opp_shadow, league, ranked,
        dedup=dedup, focal_max_level=focal_max_level)
    wins = 0.0
    total = 0.0
    for members in groups:
        rep = ranked[members[0]]
        w = len(members)
        opp_bp = make_battle_pokemon(
            opponent, opp_fast, opp_charged, league, 2,
            rep['atk_iv'], rep['def_iv'], rep['sta_iv'], shadow=opp_shadow)
        for sf, so in shield_scenarios:
            focal_bp.reset_for_battle(sf, opponent=opp_bp)
            opp_bp.reset_for_battle(so, opponent=focal_bp)
            res = simulate(focal_bp, opp_bp,
                           charged_policy_0=pvpoke_dp, charged_policy_1=pvpoke_dp,
                           mechanics=mechanics)
            total += w
            if res.pvpoke_score(0) > 500:
                wins += w
    return wins, total


def _opp_robustness_groups(focal_bp, focal_species, focal_fast, focal_charged,
                           focal_shadow, focal_ivs, opponent, opp_fast,
                           opp_charged, opp_shadow, league, ranked,
                           dedup='signature', focal_max_level=None):
    """Group the opponent's top-k IVs (``ranked``) into sets that fight
    bit-identical battles vs the fixed focal, so one representative sim
    covers each set. Returns a list of member-position lists (indexing
    ``ranked``).

    ``dedup``:
      'signature' - exact damage-signature dedup (deep_dive_signature) for
        fixed-form opponents; collapses the top-512 cohort hard. Form-change
        opponents always fall back to per-IV (their alt-form stats are
        non-linear in raw IVs+level, and the signature CMP column predates
        the cmp_atk fix -- see opp_iv_robustness docstring).
      'profile'   - effective-stat dedup (the conservative original).
      'none'      - one group per IV (the no-dedup reference for tests).
    """
    n = len(ranked)
    if dedup == 'none' or _species_has_form_change(opponent):
        return [[i] for i in range(n)]
    if dedup == 'profile':
        groups, _ = group_ivs_by_stat_profile(ranked, per_iv=False)
        return list(groups.values())
    # signature dedup
    import deep_dive_signature as _sig
    league_cp = LEAGUE_CAPS[league]
    fast_db, charged_db = get_moves()
    gm = load_gamemaster()
    opp_mon = next((m for m in gm['pokemon']
                    if m['speciesName'] == opponent), None)
    focal_mon = next((m for m in gm['pokemon']
                      if m['speciesName'] == focal_species), None)
    if opp_mon is None or focal_mon is None:
        return [[i] for i in range(n)]
    profile_list = [(None, r['atk'], r['def_'], r['hp'],
                     r['atk_iv'], r['def_iv'], r['sta_iv'], r['level'])
                    for r in ranked]
    swept = _sig.build_focal_side(
        opp_mon, parse_types(opp_mon), dict(fast_db[opp_fast]),
        [dict(charged_db[c]) for c in opp_charged],
        profile_list, league_cp, opp_shadow)
    focal_pk = Pokemon.at_best_level(focal_species, *focal_ivs,
                                     league=league, shadow=focal_shadow,
                                     max_level=focal_max_level)
    fixed = _sig.build_opp_side({
        'types': parse_types(focal_mon),
        'fm': dict(fast_db[focal_fast]),
        'cms': [dict(charged_db[c]) for c in focal_charged],
        'atk': focal_bp.atk, 'def_': focal_bp.def_,
        'mon': focal_mon, 'ivs': tuple(focal_ivs), 'level': focal_pk.level,
        'shadow': focal_shadow,
    }, league_cp)
    return [members for _rep, members in _sig.signature_groups(swept, fixed)]


def _compute_card_robustness(species, focal_fast, focal_charged, focal_shadow,
                             focal_ivs, league, opponent_names,
                             shield_scenarios, opp_movesets=None,
                             k=DEFAULT_CARD_ROBUST_K, mechanics='legacy',
                             focal_max_level=None):
    """Aggregate opp_iv_robustness for ONE focal IV across the curated pool.

    When ``opp_movesets`` (parallel to ``opponent_names``, each a
    ``(fast_id, [charged_ids])`` tuple) is supplied, reuse the dive's
    ALREADY-resolved opponent loadouts -- base species via
    parse_opponent_spec + that resolved moveset -- so EVERY opponent the dive
    simmed is covered, including the self-mirror and annotated alt-move
    variants (the card's single-IV and robustness numbers then share a
    denominator). Without it, falls back to get_default_moveset(base), which
    skips unresolvable names (legacy callers / old replay blobs). Returns
    {'frac','pool','k','scenarios'} or None if nothing resolved.
    """
    from gopvpsim.data import get_default_moveset
    wins = total = 0.0
    n_ok = 0
    _movesets = (opp_movesets if opp_movesets is not None
                 else [None] * len(opponent_names))
    for name, ms in zip(opponent_names, _movesets):
        try:
            if ms is not None:
                base, _variant, oshadow = parse_opponent_spec(name)
                of, oc = ms
            else:
                base, oshadow = name, False
                if base.endswith(' (Shadow)'):
                    base, oshadow = base[:-len(' (Shadow)')], True
                of, oc = get_default_moveset(base, league=league, shadow=oshadow)
            r = opp_iv_robustness(species, focal_fast, focal_charged,
                                  focal_shadow, focal_ivs, base, of, oc,
                                  oshadow, league, shield_scenarios, k=k,
                                  mechanics=mechanics,
                                  focal_max_level=focal_max_level)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"  card robustness: skipping {name} ({e})")
            r = None
        if not r:
            continue
        w, t = r
        wins += w
        total += t
        n_ok += 1
    if not n_ok or total == 0:
        return None
    return {'frac': wins / total, 'pool': n_ok, 'k': k,
            'scenarios': len(shield_scenarios)}


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

# Moveset-variant opponents (e.g. 'Forretress (Bug Bite)' for a fast-move
# override) get a registry entry at pool-load time so parse_opponent_spec
# can recover the base species. Keyed by display name -> (base, is_shadow).
# Populated by _parse_opponent_pool_line / _apply_active_variants in the main
# process before workers spawn; workers consume opp_cache (pre-resolved) and
# never call parse_opponent_spec directly.
_OPPONENT_VARIANT_REGISTRY = {}


def register_opponent_variant(display_name, base_species, is_shadow):
    """Register a moveset-variant opponent so parse_opponent_spec resolves
    the display name back to its base species + shadow flag.

    Idempotent: re-registering with identical fields is a no-op; conflicts
    raise ValueError so a typo can't silently shadow an earlier entry.
    """
    existing = _OPPONENT_VARIANT_REGISTRY.get(display_name)
    payload = (base_species, is_shadow)
    if existing is not None and existing != payload:
        raise ValueError(
            f"opponent variant {display_name!r} already registered as "
            f"{existing}, cannot reregister as {payload}"
        )
    _OPPONENT_VARIANT_REGISTRY[display_name] = payload


def parse_opponent_spec(opp_name):
    """Split an opponents-list entry into (species, variant, is_shadow).

    Handles four forms:
      'Medicham'                       -> ('Medicham', None,             False)
      'Medicham (Shadow)'              -> ('Medicham', None,             True)
      'Medicham (atk-weighted)'        -> ('Medicham', 'atk_weighted',   False)
      'Forretress (Bug Bite)'          -> ('Forretress','moveset_variant',False)
        (only when registered via register_opponent_variant; otherwise the
        parenthetical falls through and the whole string is treated as a
        speciesName so genuine PvPoke forms like '(Galarian)' still work)

    Shadow + atk-weighted in the same entry is not supported (no meta-relevant
    opponent today is both).
    """
    if opp_name in _OPPONENT_VARIANT_REGISTRY:
        base, is_shadow = _OPPONENT_VARIANT_REGISTRY[opp_name]
        return base, 'moveset_variant', is_shadow
    variant = None
    name = opp_name
    if name.endswith(ATK_WEIGHTED_SUFFIX):
        name = name[:-len(ATK_WEIGHTED_SUFFIX)]
        variant = 'atk_weighted'
    is_shadow = name.endswith(' (Shadow)')
    if is_shadow:
        name = name[:-len(' (Shadow)')]
    return name, variant, is_shadow


def _parse_opponent_pool_line(line):
    """Parse one non-comment, non-blank line from an opponents-file.

    Format:
        SPECIES                              # default moveset (PvPoke)
        SPECIES | fast=ID                    # fast-move override
        SPECIES | charged=A,B                # charged-only override
        SPECIES | fast=ID | charged=A,B      # full moveset override

    SPECIES is the PvPoke speciesName, optionally with a trailing ' (Shadow)'.
    Override keys are case-sensitive ('fast', 'charged'); unknown keys raise.
    Whitespace around the '|' separator and around 'key=value' is tolerated.

    Returns:
        (display_name, base_species, is_shadow, fast_override, charged_override)
        where fast_override / charged_override are None when not present.
        Display name auto-generated for entries with overrides:
            'Forretress | fast=BUG_BITE'           -> 'Forretress (Bug Bite)'
            'Forretress (Shadow) | fast=BUG_BITE'  -> 'Forretress (Shadow) (Bug Bite)'

    Raises ValueError on malformed input.
    """
    parts = [p.strip() for p in line.split('|')]
    species_with_form = parts[0]
    if not species_with_form:
        raise ValueError(f"empty species name in pool line: {line!r}")

    overrides = {}
    for kv in parts[1:]:
        if '=' not in kv:
            raise ValueError(f"override {kv!r} missing '=' (expected key=value)")
        k, v = kv.split('=', 1)
        k, v = k.strip(), v.strip()
        if not k or not v:
            raise ValueError(f"empty key or value in override {kv!r}")
        if k in overrides:
            raise ValueError(f"duplicate override key {k!r} in {line!r}")
        overrides[k] = v

    fast_override = overrides.pop('fast', None)
    charged_str = overrides.pop('charged', None)
    charged_override = (
        [c.strip() for c in charged_str.split(',') if c.strip()]
        if charged_str else None
    )
    if overrides:
        raise ValueError(f"unknown override key(s) {sorted(overrides)} in {line!r}")

    is_shadow = species_with_form.endswith(' (Shadow)')
    base_species = (species_with_form[:-len(' (Shadow)')]
                    if is_shadow else species_with_form)

    if fast_override is None and charged_override is None:
        return species_with_form, base_species, is_shadow, None, None

    suffix_parts = []
    if fast_override is not None:
        suffix_parts.append(analysis.pretty_name(fast_override))
    if charged_override is not None:
        suffix_parts.append('+'.join(
            analysis.pretty_name(c) for c in charged_override))
    display = f"{species_with_form} ({' / '.join(suffix_parts)})"
    return display, base_species, is_shadow, fast_override, charged_override


# ---- Active alt-moveset opponent variants (TOML, project-wide) ----

ACTIVE_VARIANTS_PATH = Path(__file__).resolve().parents[1] / (
    'opponent_pools/active_variants.toml')


def _apply_active_variants(opponents, opp_movesets_full, league, toml_path=None,
                           skip=False):
    """Append project-wide alt-moveset opponent variants from a TOML file.

    Skipping rules:
    - ``skip=True`` → no-op (returns []).
    - File missing → no-op (returns []).
    - Variant whose ``(base_species, is_shadow)`` doesn't match any opponent
      already in the pool → skipped silently. Lets a single TOML cover
      multiple leagues without manual scoping (a Forretress (BB) entry
      auto-skips on a UL pool that doesn't include Forretress).
    - Variant display name already in ``opponents`` (e.g. from inline
      pipe-syntax) → skipped.

    Mutates ``opponents`` and ``opp_movesets_full`` in place. Registers each
    appended variant via ``register_opponent_variant`` so
    ``parse_opponent_spec`` can recover the base species downstream.

    Returns: list of display names actually appended.
    """
    if skip:
        return []
    if toml_path is None:
        toml_path = ACTIVE_VARIANTS_PATH
    toml_path = Path(toml_path)
    if not toml_path.exists():
        return []

    with open(toml_path, 'rb') as f:
        data = tomllib.load(f)

    # Index existing pool by (base_species, is_shadow) so a variant only
    # appends when its base form is already a meta opponent.
    base_present = set()
    for opp_name in opponents:
        base, _, is_shadow = parse_opponent_spec(opp_name)
        base_present.add((base, is_shadow))

    applied = []
    for v in data.get('variants', []):
        species = v.get('species')
        if not species:
            logger.warning(f"active_variants.toml: skipping entry without 'species'")
            continue
        is_shadow = bool(v.get('shadow', False))
        fast_ov = v.get('fast')
        charged_ov = v.get('charged')
        if fast_ov is None and charged_ov is None:
            logger.warning(f"active_variants.toml: {species} entry has no "
                           f"'fast' or 'charged' override, skipping")
            continue
        if (species, is_shadow) not in base_present:
            continue  # base form not in this pool; quietly skip

        try:
            d_fast, d_charged = get_default_moveset(
                species, league=league, shadow=is_shadow)
        except (KeyError, ValueError) as _e:
            logger.warning(f"active_variants.toml: {species} not in "
                           f"{league} rankings, skipping ({_e})")
            continue
        fast_id = fast_ov if fast_ov is not None else d_fast
        charged_ids = (
            list(charged_ov) if charged_ov is not None else list(d_charged))

        species_with_form = f"{species} (Shadow)" if is_shadow else species
        suffix_parts = []
        if fast_ov is not None:
            suffix_parts.append(analysis.pretty_name(fast_ov))
        if charged_ov is not None:
            suffix_parts.append('+'.join(
                analysis.pretty_name(c) for c in charged_ov))
        display = f"{species_with_form} ({' / '.join(suffix_parts)})"

        if display in opponents:
            continue  # already there from inline pipe-syntax

        opponents.append(display)
        opp_movesets_full.append((fast_id, charged_ids))
        register_opponent_variant(display, species, is_shadow)
        applied.append(display)

    return applied


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

slayer.compute_iv_metadata = compute_iv_metadata


def base_form_focal(species, shadow):
    """Resolve the "base form" of a boosted/variant focal, for the dive-card
    "N newly guaranteed vs base form" census (item 5).

    Returns ``(base_species, base_shadow, base_display)`` when a base form
    exists and the gate applies, else ``None``. Gate (deliberately narrow):

      * SHADOW focal  -> base is the same species, non-shadow. The x1.2 atk /
        x0.833 def boost reshapes win/loss MEMBERSHIP, so the base set is a
        real re-sim, not a scalar of the shadow set.
      * FEMALE sex-variant focal (``"X (Female)"``, e.g. Oinkologne) -> base
        is the male sibling ``"X"`` (different base stats -> a real re-sim).

    NOT gated: a male focal (it IS the base form), Alolan / Galarian / Kanto
    regional forms (those are their own species with no shared "base" the
    reader thinks of as the boost-off comparison).
    """
    if shadow:
        return (species, False, pretty_species(species))
    if species.endswith(' (Female)'):
        base = species[:-len(' (Female)')]
        try:
            get_species(base)
        except KeyError:
            return None
        return (base, False, pretty_species(base))
    return None


def _form_damage_census(species, shadow, league, focal_moves, focal_types,
                        iv, opp_info_cache, opp_names):
    """UNUSED, superseded. Per-opponent RAW-damage break/bulkpoint sets.

    Formerly fed ``form_sibling_trade``'s spanning bar, but the raw-damage
    set-difference over-counts badly: the shadow's +20% atk beats the
    non-shadow on ~every opponent and the -16.7% def loses on ~every opponent,
    so the bar read "whole pool minus a few immunities" (the 73-vs-73 bug,
    2026-06-24). The bar now uses the ANCHOR-based newly-guaranteed census
    (the same basis as the per-spread ``n_breakpoint_newly``), computed at the
    render call site. Kept for reference; no live callers.

    Pure damage calc (the floor(0.5*1.3*Power*Atk/Def*Eff*STAB)+1 formula,
    NO win sim) at a single representative IV spread ``iv = (atk_iv, def_iv,
    sta_iv)``, evaluated under the league CP cap. Formerly set-differenced a
    focal form against its sibling for ``form_sibling_trade``.

    Returns ``(bp, blk)`` where:
      * ``bp[opp_display]``  = max integer damage this form's BEST-damaging move
        deals to that opponent (the breakpoint reach against it).
      * ``blk[opp_display]`` = max integer damage that opponent's BEST-damaging
        move deals to this form (the incoming hit the form takes; a HIGHER
        def form takes LESS, so a smaller number is the bulkier outcome).

    Both keyed by the pretty opponent display name. The caller compares two
    forms' dicts: focal does +1 damage where ``bp_focal[X] > bp_sibling[X]``
    (a newly-guaranteed breakpoint); focal takes -1 where
    ``blk_focal[X] < blk_sibling[X]`` (a bulkpoint the focal holds and the
    sibling gives up).
    """
    from gopvpsim.moves import damage as calc_damage

    a_iv, d_iv, s_iv = iv
    try:
        mon = Pokemon.at_best_level(species, a_iv, d_iv, s_iv,
                                    league=league, shadow=shadow)
    except (KeyError, ValueError):
        return {}, {}
    focal_atk, focal_def = mon.atk, mon.def_

    bp, blk = {}, {}
    for name in opp_names:
        info = opp_info_cache.get(name)
        if info is None:
            continue
        _osp, _ovar, _oshadow = parse_opponent_spec(name)
        # Keep the shadow qualifier so the bar's opp link matches the dive
        # anchor: a shadow-only pool entry ("Dusknoir (Shadow)") must stay
        # "Shadow Dusknoir" -> #opp-dusknoir-shadow, not bare "dusknoir".
        disp = pretty_species(f'{_osp} (Shadow)' if _oshadow else _osp)
        opp_atk, opp_def, opp_types = info['atk'], info['def_'], info['types']
        # Outgoing: best integer damage any focal move does to this opponent.
        out_best = None
        for (_mid, power, mtype) in focal_moves:
            d = calc_damage(power, focal_atk, opp_def, mtype,
                            focal_types, opp_types)
            if out_best is None or d > out_best:
                out_best = d
        if out_best is not None:
            bp[disp] = max(bp.get(disp, 0), out_best)
        # Incoming: worst integer damage any of the opponent's moves does to
        # the focal at this def. (Max over moves = the threat hit the bulkpoint
        # is measured against.)
        in_worst = None
        for (_mid, power, mtype) in info.get('moves', []):
            d = calc_damage(power, opp_atk, focal_def, mtype,
                            opp_types, focal_types)
            if in_worst is None or d > in_worst:
                in_worst = d
        if in_worst is not None:
            blk[disp] = in_worst if disp not in blk else min(blk[disp], in_worst)
    return bp, blk


def form_sibling_trade(species, focal_shadow, breakpoints_gained,
                       bulkpoints_lost):
    """Form-level "newly guaranteed vs sibling form" break/bulkpoint trade.

    Dragapult-Sim-style FORM trade (shadow<->non-shadow, Female<->Male), shown
    once per dive as a thin spanning bar. The break/bulkpoint sets are the
    ANCHOR-based newly-guaranteed sets, rolled up to the FORM level by the
    caller (the union across the recommended spreads of the per-spread census
    coverage minus the base form's coverage -- exactly the basis behind the
    per-spread ``rc['n_breakpoint_newly']`` numbers). They are passed in here
    so this function only resolves the sibling identity + render direction; it
    does NOT re-derive anything from raw per-opponent damage.

    For a SHADOW focal the sibling is the bare non-shadow species (so a
    pre-release shadow constructed ahead of the gamemaster still gets a bar --
    the gate is ``focal_shadow``, not a gamemaster shadow marker). For a Female
    focal the sibling is the Male base species. Gated via ``base_form_focal``;
    returns ``None`` for a no-sibling species (e.g. Tinkaton).

    ``breakpoints_gained`` = opponents the boosted focal newly guarantees a
    breakpoint against (vs the base form); ``bulkpoints_lost`` = bulkpoints the
    base form holds that the boosted focal gives up. Both are already-sorted
    pretty display-name lists matching the dive anchors, so the bar's opponent
    links land on the right ``#opp-*`` slugs.

    The inverse direction (a BARE, shadow-eligible focal whose sibling is its
    own shadow form -- e.g. the non-shadow Corviknight dive) has no second sim
    pass for the shadow sibling baked into the blob, so the anchor census is not
    available there. That bar is omitted (return ``None``); the shadow-boost
    trade story already lives on the shadow dive's bar.

    Returns a dict (or ``None``):
        {'sibling_display', 'focal_display', 'focal_is_boosted',
         'breakpoints_gained': [opp, ...], 'bulkpoints_lost': [opp, ...]}
    """
    sib = base_form_focal(species, focal_shadow)
    if sib is None:
        # No base sibling: either a bare shadow-eligible focal (inverse
        # direction, no shadow-sibling census in the blob -> omit) or a
        # no-sibling species (Tinkaton). Either way, no anchor-based bar.
        return None
    sib_species, sib_shadow, sib_display = sib

    focal_display = pretty_species(
        f'{species} (Shadow)' if focal_shadow else species)
    return {
        'sibling_display': sib_display,
        'focal_display': focal_display,
        'focal_is_boosted': True,
        'breakpoints_gained': list(breakpoints_gained),
        'bulkpoints_lost': list(bulkpoints_lost),
    }


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


def _sweep_worker_init(species, focal_types, fm_template, cms_template,
                       opp_cache, shield_scenarios, focal_bait=True,
                       log_path=None, verbose=False,
                       focal_mon=None, league_cp=1500, focal_shadow=False,
                       focal_energy=0, mechanics='legacy', capture_energy=False):
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
    _worker_state['capture_energy'] = capture_energy
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
    capture_energy = ws.get('capture_energy', False)

    results = {}
    energy_results = {} if capture_energy else None
    n_sims = 0
    for (profile_key, atk_stat, def_stat, hp_stat, a_iv, d_iv, s_iv, lv), oi in pair_chunk:
        opp = opp_cache[oi]
        # One BattlePokemon pair per (profile, opponent), reset between
        # scenarios — keeps the damage/DP caches warm across the
        # shield-scenario axis instead of rebuilding them per sim.
        bp0 = BattlePokemon(
            species=species, types=focal_types,
            atk=atk_stat, def_=def_stat, max_hp=hp_stat,
            shadow=focal_shadow,
            fast_move=dict(fm_template),
            charged_moves=[dict(cm) for cm in cms_template],
        )
        # Energy-lead axis: reset_for_battle re-applies initial_energy
        # before every scenario, so setting it once here covers the
        # whole shield-scenario loop below.
        bp0.initial_energy = focal_energy
        attach_form_change(bp0, focal_mon, a_iv, d_iv, s_iv, lv,
                           league_cp, focal_shadow)
        bp1 = BattlePokemon(
            species=opp['species'], types=opp['types'],
            atk=opp['atk'], def_=opp['def_'], max_hp=opp['hp'],
            shadow=opp['shadow'],
            fast_move=dict(opp['fm']),
            charged_moves=[dict(cm) for cm in opp['cms']],
        )
        attach_form_change(bp1, opp['mon'], *opp['ivs'], opp['level'],
                           league_cp, opp['shadow'])
        scores = []
        energies = [] if capture_energy else None
        for s_focal, s_opp in shield_scenarios:
            bp0.reset_for_battle(s_focal, opponent=bp1)
            bp1.reset_for_battle(s_opp, opponent=bp0)
            result = simulate(bp0, bp1,
                              charged_policy_0=focal_policy,
                              charged_policy_1=pvpoke_dp,
                              mechanics=mechanics)
            scores.append(result.pvpoke_score(0))
            if capture_energy:
                # Focal's leftover energy (0..100) at battle end -- the post-match
                # state for the compare widget's "banks N charged moves" line.
                energies.append(result.energy_remaining[0])
            n_sims += 1
        results[(profile_key, oi)] = scores
        if capture_energy:
            energy_results[(profile_key, oi)] = energies
    # Branch the return shape so the off path is byte-identical: callers that
    # don't capture energy keep unpacking the historical (results, n_sims).
    if capture_energy:
        return results, energy_results, n_sims
    return results, n_sims


def iv_sweep(species, fast_id, charged_ids, league, shadow,
             opponents, opp_movesets, shield_scenarios, opp_iv_mode='pvpoke',
             iv_floor=None, log_path=None, verbose=False,
             threshold_registry=None, reserve_cpus=0, signature_dedup=True,
             use_sweep_cache=False, mechanics='legacy',
             focal_max_level=None, opp_max_level=None, capture_energy=False):
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

    gm = load_gamemaster()
    focal_mon = next(m for m in gm['pokemon'] if m['speciesName'] == species)
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
        _cap = 100 - min(cm['energy'] for cm in cms_template)
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
        opp_mon = next(m for m in gm['pokemon'] if m['speciesName'] == opp_clean)
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
    cached_cols = {}  # oi -> ndarray (n_ivs, n_scenarios)
    # The sweep cache key (sweep_cache.focal_key_fields) does NOT include the
    # turn-mechanics model, so a 'new'-mechanics run would collide with any
    # legacy-cached columns. The 'new' model is experimental; disable the
    # persistent cache for it rather than widen the cache-key schema (which
    # CLAUDE.md flags as coordination-sensitive).
    if mechanics != 'legacy':
        use_sweep_cache = False
    # The disk cache stores only the float64 SCORE column; it carries no energy.
    # Capturing energy must therefore bypass the cache (fresh sims supply both),
    # exactly like the 'new'-mechanics disable above. capture_energy is opt-in
    # and rare, so paying the full sim cost is fine.
    if capture_energy:
        use_sweep_cache = False
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
                n_ivs_total, len(shield_scenarios))
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
    n_workers = min(max(1, multiprocessing.cpu_count() - reserve_cpus), 16)
    n_chunks_target = 100
    chunk_size = max(1, (len(pair_list) + n_chunks_target - 1) // n_chunks_target)
    chunks = [pair_list[i:i+chunk_size] for i in range(0, len(pair_list), chunk_size)]

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
                      focal_energy, mechanics, capture_energy),
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
    # every profile in its signature group.
    pair_scores = {}
    pair_energy = {} if capture_energy else None
    n_sims = 0
    for chunk_res in chunk_results:
        # Worker return shape branches on capture_energy (see _sweep_worker).
        if capture_energy:
            pair_res, pair_en, chunk_sims = chunk_res
            pair_energy.update(pair_en)
        else:
            pair_res, chunk_sims = chunk_res
        pair_scores.update(pair_res)
        n_sims += chunk_sims

    profile_per_opp = {}
    profile_energy_per_opp = {} if capture_energy else None
    for oi, groups in groups_by_opp.items():
        for rep_pos, members in groups:
            scores = pair_scores[(profile_list[rep_pos][0], oi)]
            energies = (pair_energy[(profile_list[rep_pos][0], oi)]
                        if capture_energy else None)
            for pos in members:
                per_opp = profile_per_opp.setdefault(profile_list[pos][0], {})
                for si, sc in enumerate(scores):
                    per_opp[(si, oi)] = sc
                if capture_energy:
                    e_per_opp = profile_energy_per_opp.setdefault(
                        profile_list[pos][0], {})
                    for si, en in enumerate(energies):
                        e_per_opp[(si, oi)] = en

    # Fill cache-hit columns: all IVs in a profile share effective
    # stats, hence identical battles, so the profile's first IV index
    # reads the stored per-IV column exactly.
    iv_idx_by_profile = None
    if cached_cols:
        iv_idx_by_profile = {pk: idxs[0]
                             for pk, idxs in profile_to_indices.items()}
        for oi, col in cached_cols.items():
            for pk, rep_idx in iv_idx_by_profile.items():
                per_opp = profile_per_opp.setdefault(pk, {})
                for si in range(len(shield_scenarios)):
                    per_opp[(si, oi)] = float(col[rep_idx, si])

    # Persist freshly simmed columns (expanded to per-IV order).
    if sweep_cache is not None and missing_ois:
        import numpy as _np
        import sweep_cache as swc
        for oi in missing_ois:
            opp = opp_cache[oi]
            col = _np.empty((n_ivs_total, len(shield_scenarios)),
                            dtype=_np.float64)
            for pk, idxs in profile_to_indices.items():
                scores = [profile_per_opp[pk][(si, oi)]
                          for si in range(len(shield_scenarios))]
                col[idxs, :] = scores
            sweep_cache.put_column(
                swc.column_key_fields(opp['species'], opp['shadow'],
                                      opp['ivs'], opp['level'],
                                      opp['fast_id'], opp['charged_ids']),
                col)

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

    by_sp = sorted(results, key=lambda r: r['stat_product'], reverse=True)
    for i, r in enumerate(by_sp):
        r['sp_rank'] = i + 1

    return results, n_sims, canonical_scores, canonical_meta, canonical_energy


# ---------------------------------------------------------------------------
# HTML output with threshold highlighting
# ---------------------------------------------------------------------------

# Colors for threshold tiers - the ordered --tier-1..--tier-8 palette, indexed
# mod 8 (most restrictive first). These flow as theme-aware 'var(--tier-N)'
# STRINGS everywhere (CSS badge renders them as tier-color TEXT on
# var(--surface-2)); only the Plotly-marker injection boundary resolves them to
# DEFAULT_THEME hex via _TIER_VAR_TO_HEX (Plotly canvas can't read CSS vars; the
# deferred JS shim will make that theme-aware later). "Other" (no threshold) uses
# the Viridis colorscale.
THRESHOLD_COLORS = [f'var(--tier-{i})' for i in range(1, 9)]

# var->hex resolver for the single Plotly-marker injection boundary. Built from
# the SAME theme.py _TOKENS values at the DEFAULT_THEME column so badge == marker.
_DEFAULT_THEME_IDX = _THEME_ORDER.index(DEFAULT_THEME)
_TIER_VAR_TO_HEX = {
    f'var(--tier-{i})': _THEME_TOKENS[f'--tier-{i}'][_DEFAULT_THEME_IDX]
    for i in range(1, 9)
}
# Mirror tier shares the same var->hex resolution path (deep_dive_analysis
# emits 'var(--tier-mirror)'); resolve it here so no raw var string leaks into
# the Plotly-marker injection (__TIER_COLORS_JS__).
_TIER_VAR_TO_HEX['var(--tier-mirror)'] = (
    _THEME_TOKENS['--tier-mirror'][_DEFAULT_THEME_IDX])


PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"
PLOTLY_FILENAME = "plotly-2.35.2.min.js"
PLOTLY_DOWNLOAD_TIMEOUT = 60        # seconds per attempt
PLOTLY_DOWNLOAD_BACKOFF = (1, 5, 15)  # retry sleep schedule (3 attempts total)
PLOTLY_CACHE_DIR = Path.home() / '.cache' / 'gopvpsim'


def _download_plotly_with_retry():
    """Fetch plotly.min.js bytes with timeout + retry-with-backoff.

    Returns:
        bytes on success; ``None`` on persistent failure (callers
        should fall back to the CDN ``<script src>`` reference).

    Bounded-time semantics: each attempt has a 60s socket timeout, so
    a slow CDN can't block the dive indefinitely. The three attempts
    are spaced 1s / 5s / 15s apart, total worst-case ~3 minutes before
    giving up — enough to ride out brief network hiccups (DNS flake,
    transient TCP reset, CDN edge-node issue) without committing to
    an indefinite wait.

    Surfaced 2026-06-03 / 2026-06-04 overnight chain: an internet
    outage during the Jumpluff GL render killed the dive with
    ``socket.gaierror`` ("nodename nor servname provided"). Original
    code had no timeout, no retry, no fallback — single transient
    network event lost the entire dive run.
    """
    import urllib.request
    import urllib.error
    import ssl
    import socket
    import time
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    last_err = None
    for attempt, backoff in enumerate(PLOTLY_DOWNLOAD_BACKOFF, start=1):
        try:
            with urllib.request.urlopen(
                    PLOTLY_CDN, context=ctx,
                    timeout=PLOTLY_DOWNLOAD_TIMEOUT) as r:
                return r.read()
        except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
            last_err = e
            if attempt < len(PLOTLY_DOWNLOAD_BACKOFF):
                logger.warning(
                    f"  Plotly.js download attempt {attempt} failed: {e}; "
                    f"retrying in {backoff}s")
                time.sleep(backoff)
            else:
                logger.warning(
                    f"  Plotly.js download attempt {attempt} failed: {e}; "
                    f"giving up after {len(PLOTLY_DOWNLOAD_BACKOFF)} attempts")
    logger.warning(
        f"  Plotly.js fetch failed persistently ({last_err}); the dive HTML "
        f"will fall back to the CDN <script src> reference (online-only). "
        f"Re-render later from the cached scores if you need standalone.")
    return None


def _plotly_bytes_cached():
    """Return plotly.min.js bytes, preferring the local version-keyed cache.

    ``PLOTLY_CDN`` pins an exact version, so the cache file (keyed by
    ``PLOTLY_FILENAME`` under ``PLOTLY_CACHE_DIR``) can never go stale:
    bumping the pinned version changes the filename, which misses the
    cache and forces a fresh download. Returns ``None`` when the cache
    is cold and the download fails persistently (callers fall back to
    the CDN ``<script src>`` reference).
    """
    cache_path = Path(PLOTLY_CACHE_DIR) / PLOTLY_FILENAME
    if cache_path.exists():
        return cache_path.read_bytes()
    logger.info(f"  Plotly.js cache cold; downloading to {cache_path}")
    data = _download_plotly_with_retry()
    if data is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix('.tmp')
        tmp.write_bytes(data)
        tmp.replace(cache_path)  # atomic: a killed run can't leave a torn cache
    return data


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

    Robustness: both embedding paths source bytes from
    ``_plotly_bytes_cached`` — a local version-keyed cache backed by
    ``_download_plotly_with_retry`` (60s timeout/attempt, 1s/5s/15s
    backoff). On a cold cache with persistent download failure it
    returns None — callers then fall back to the plain CDN
    ``<script src>`` reference so the dive still ships (just
    online-only instead of offline-portable).
    """
    if shared_plotly_dir is not None:
        shared = Path(shared_plotly_dir)
        shared.mkdir(parents=True, exist_ok=True)
        plotly_path = shared / PLOTLY_FILENAME
        if not plotly_path.exists():
            logger.info(f"  Writing Plotly.js to shared dir: {plotly_path}")
            plotly_bytes = _plotly_bytes_cached()
            if plotly_bytes is None:
                return f'<script src="{PLOTLY_CDN}"></script>'
            plotly_path.write_bytes(plotly_bytes)
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
    plotly_bytes = _plotly_bytes_cached()
    if plotly_bytes is None:
        return f'<script src="{PLOTLY_CDN}"></script>'
    return f'<script>{plotly_bytes.decode()}</script>'


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
_synthesize_mirror_tier = analysis.synthesize_mirror_tier
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
            'color': f.get('tier_color') or 'var(--text-muted)',
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


def _mirror_synth_scores(score_arrays, moveset_idx):
    """Score array for mirror-tier synthesis: prefer the bait-on pvpoke
    mode, else fall back to any available mode for this moveset.

    A rank1-only or bait-off dive never has a bare '{mi}_pvpoke' key
    (compose_mode yields 'pvpoke:nobait' / 'rank1...'), and the hardcoded
    lookup silently skipped synthesis for those dives.
    """
    key = f'{moveset_idx}_pvpoke'
    scores = score_arrays.get(key)
    if scores:
        return scores
    prefix = f'{moveset_idx}_'
    for k in sorted(score_arrays):
        if k.startswith(prefix) and score_arrays[k]:
            logger.info(f"  [mirror-synth] mode {key!r} absent; "
                        f"falling back to {k!r}")
            return score_arrays[k]
    return None


def _generate_narrative_for_moveset(data_obj, score_arrays, moveset_idx,
                                    scenarios, opponents, opp_iv_modes,
                                    has_toml_tiers, resolved_anchors=None,
                                    *, species=None, focal_shadow=False):
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
    _energy_values = {parse_energy(m) for m in opp_iv_modes}
    has_energy_axis = len(_energy_values) > 1
    opp_label = data_obj.get('oppLabel', 'opponent')

    # Compute anchor-flip records if we have resolved anchors
    anchor_flip_records = []
    if resolved_anchors:
        _seen = {}
        for _mode in opp_iv_modes:
            bait_mode = parse_mode(_mode)[1]
            energy_mode = parse_energy(_mode)
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
                rec['energy_modes'] = {energy_mode}
                dedup_key = (rec['anchor'].name, rec['opponent'],
                             frozenset(tuple(s) for s in rec['scenarios']))
                if dedup_key in _seen:
                    _seen[dedup_key]['bait_modes'] |= rec['bait_modes']
                    _seen[dedup_key]['energy_modes'] |= rec['energy_modes']
                else:
                    _seen[dedup_key] = rec
                    anchor_flip_records.append(rec)

    # Compute matchup boundaries (always available, no anchors needed)
    all_matchup_boundaries = []
    _mb_seen = {}
    for _mode in opp_iv_modes:
        bait_mode = parse_mode(_mode)[1]
        energy_mode = parse_energy(_mode)
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
                mb['energy_modes'] = {energy_mode}
                dedup_key = (mb['opponent'], mb['stat'], mb['threshold'],
                             mb.get('hp_threshold'),
                             frozenset(tuple(s) for s in mb['scenarios']))
                if dedup_key in _mb_seen:
                    _mb_seen[dedup_key]['bait_modes'] |= mb['bait_modes']
                    _mb_seen[dedup_key]['energy_modes'] |= mb['energy_modes']
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
        # Mirror-tier synthesis (mirror to the line ~2140 code path):
        # ensure the per-moveset IV Flavor Guide also surfaces a
        # "<species> Mirror Bulk" tier if no existing tier covers it.
        # See synthesize_mirror_tier docstring for the relaxed-gate
        # rationale. Append-only. Skipped when species was not
        # threaded through (older callers).
        if species:
            _mirror_scores = _mirror_synth_scores(score_arrays, moveset_idx)
            if _mirror_scores:
                _mirror_tier = _synthesize_mirror_tier(
                    species=species,
                    scores_flat=_mirror_scores,
                    nIvs=nIvs, nS=nS, nO=nO,
                    data_obj=data_obj,
                    scenarios=scenarios,
                    opponents=opponents,
                    resolved_anchors=resolved_anchors or [],
                    existing_tiers=effective_tiers,
                    focal_shadow=focal_shadow,
                )
                if _mirror_tier:
                    effective_tiers = list(effective_tiers) + [_mirror_tier]

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
                               moveset0_flavors_for_rename=None,
                               focal_shadow=False,
                               scores_base_arrays=None,
                               base_form_info=None):
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
        except Exception as e:
            # Skip opponents we can't resolve, but never silently: a
            # missing entry here silently drops the opponent from
            # breakpoint narration and flip annotations (e.g. the replay
            # variant-registry gap surfaced exactly this way).
            logger.warning(f"  opp_info_cache: could not resolve "
                           f"{opp_name!r} ({type(e).__name__}: {e}); "
                           f"narration for this opponent will be omitted")

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

    # ---- Coverage selection: 3 poles + greedy fill of NAMED spreads ----------
    # Phase A.1 (Dragapult-Sim "OPTIMAL IVS" style). We seed THREE poles --
    # balanced lead (battle-score #1), attack pole (max effective atk), and bulk
    # pole (max effective DEF) -- then greedily fill extra spreads that clear a
    # notable named opponent tier no chosen spread covers yet. Each chosen spread
    # is LABELED with the NOTABLE named opponent tiers it ABSOLUTELY clears (not
    # differential vs the lead), so the card reads "Bulkpoints Azumarill,
    # Medicham, G-Corsola" on the bulk pole and "Breakpoints Jellicent,
    # Annihilape" on the attack pole, while the broad lead keeps few/none.
    #
    # Signature granularity (root-cause fix): per IV we record the set of
    # (opponent_display, kind, round(threshold_value, 2)) tiers it clears, read
    # straight off resolved_anchors_top via ResolvedAnchor.passes(). The
    # threshold component is load-bearing -- the Level-3 *_blkp_any anchors
    # expand into a near-continuum of tiers per opponent, so a HIGH bulkpoint
    # must differ from a LOW one or a bulky IV "covers" every opponent through
    # each one's trivial lowest tier.
    #
    # Rarity gate: a tier is "notable" only if at most REC_NOTABLE_MAX_CLEAR_FRAC
    # of the strong pool (ranked[:REC_STRONG_POOL_N]) clears it. The strong pool
    # is WIDE on purpose -- the bulk pole sits on deeply-bulky IVs that never
    # reach the top ~50, so a narrow pool would omit the high def-side tiers from
    # the universe entirely.
    #
    # CMP/mirror anchors have opponent=None; they name no opponent, so they are
    # the attack pole's story (seeded by atk_iv), not named coverage. On
    # --no-mirror-slayer dives resolved_anchors_top is empty: the named universe
    # is empty, no notable tiers exist, and we fall back to the v1 won-set
    # symdiff distinctness with generic labels (no crash, no named bullets).
    _anchor_mode = bool(resolved_anchors_top)

    by_iv = {rc['iv']: rc for rc in rec_candidates}

    # The bulk pole is usually a deeply-bulky IV that trades away too much battle
    # score to rank in the top-50 strong pool (rec_candidates), so it lacks an rc
    # dict. Those IVs ARE simulated -- data_obj['ivAtk'/'ivDef'/'ivHp'] span the
    # full valid grid (range(nIvs)). _ensure_rc fabricates a minimal rc (style,
    # flip counts, composite score) so any pole IV flows into chosen_recs / the
    # card uniformly.
    _pop_atk20 = sum(data_obj['ivAtk'][i] for i in ranked[:20]) / 20
    _pop_def20 = sum(data_obj['ivDef'][i] for i in ranked[:20]) / 20
    _pop_hp20 = sum(data_obj['ivHp'][i] for i in ranked[:20]) / 20

    def _ensure_rc(iv):
        rc = by_iv.get(iv)
        if rc is not None:
            return rc
        g, l, net = flip_map.get(iv, (0, 0, 0))
        rng = (max(scene_ranks[si][iv] for si in range(nS))
               - min(scene_ranks[si][iv] for si in range(nS)))
        score = -avg_ranks[iv] + net * 3 - rng * 0.001
        atk, def_, hp = (data_obj['ivAtk'][iv], data_obj['ivDef'][iv],
                         data_obj['ivHp'][iv])
        # Pole IVs are stat extremes; label by the stat that most exceeds the
        # top-20 population mean (largest relative excess wins) so the max-def
        # bulk pole reads "Max Bulk" rather than tripping the atk check first.
        _exc = {'Attack Weight': atk - _pop_atk20,
                'Max Bulk': def_ - _pop_def20,
                'High HP': hp - _pop_hp20}
        _style, _ex = max(_exc.items(), key=lambda kv: kv[1])
        if _ex <= 0.5:
            style = 'Generalist' if rng < 500 else 'Balanced'
        else:
            style = _style
        rc = {'iv': iv, 'avg_rank': avg_ranks[iv], 'avg_score': avg_scores[iv],
              'gains': g, 'losses': l, 'net': net, 'range': rng,
              'score': score, 'style': style}
        by_iv[iv] = rc
        return rc

    # Lead / balanced reference = rank-1 BATTLE SCORE (ranked[0]) -- our headline
    # metric. Decision (Michael 2026-06-22): we pitch battle score as a better
    # metric than stat product, so our "#1" must BE the battle-score #1, not the
    # rank-1 stat-product IV. Fall back to the top composite candidate if
    # (defensively) ranked[0] is outside the strong pool.
    _spranks = data_obj.get('spRanks') or []  # used by the two-#1s blurb below
    lead_iv = ranked[0] if ranked and ranked[0] in by_iv else rec_candidates[0]['iv']

    # Finer per-IV coverage signature: the set of (opponent_display, kind,
    # threshold) tiers this IV clears. Only NAMED-opponent kinds
    # (damage_breakpoint / bulkpoint) enter the signature; cmp/mirror anchors
    # (opponent=None) are excluded. Reads the full ivAtk/ivDef arrays, so it
    # works for ANY iv index (the bulk pole may be outside rec_candidates).
    # Defined BEFORE pole selection so the poles can count NOTABLE-only coverage.
    _cov_cache: dict = {}

    def _named_cover(iv):
        c = _cov_cache.get(iv)
        if c is None:
            atk, dfn = data_obj['ivAtk'][iv], data_obj['ivDef'][iv]
            c = _cov_cache[iv] = frozenset(
                (pretty_species(a.opponent), a.kind, round(a.threshold_value, 2))
                for a in resolved_anchors_top
                if a.opponent and a.passes(atk, dfn))
        return c

    # CENSUS coverage source for the card labels: the full set of matchup-flip
    # boundaries (atk sweep -> breakpoints, def sweep -> bulkpoints) across the
    # WHOLE opponent pool, not just the curated resolved anchors. The resolved
    # anchors (_named_cover) are a small TOML/mirror-slayer set (~3 breakpoint
    # opponents for Corviknight); the card census wants EVERY opponent a spread
    # clears a guaranteed break/bulkpoint against (cf. Dragapult-Sim's "18
    # guaranteed breakpoints"). Computed once here, deduped per (opponent, stat,
    # threshold); _census_cover(iv) then asks, per spread, which opponents that
    # spread's atk/def clears. Selection above stays anchor/notable-based; only
    # these LABELS go census.
    _census_boundaries = []
    _cb_seen = set()
    for _mode in all_modes:
        _scores = score_arrays.get(f'{moveset_idx}_{_mode}', [])
        if not _scores:
            continue
        for _sweep in ('def', 'atk'):
            for mb in _find_matchup_boundaries(
                    _scores, nIvs, nS, nO, data_obj, scenarios, opponents,
                    sweep_stat=_sweep):
                _k = (mb['opponent'], mb['stat'], mb['threshold'])
                if _k in _cb_seen:
                    continue
                _cb_seen.add(_k)
                _census_boundaries.append(mb)
    _census_cache: dict = {}

    def _census_cover(iv):
        """(breakpoint_opps, bulkpoint_opps) the spread at ``iv`` clears: distinct
        opponent display names where atk >= an atk-boundary threshold (breakpoint)
        or def >= a def-boundary threshold (bulkpoint). Sorted."""
        c = _census_cache.get(iv)
        if c is None:
            atk, dfn = data_obj['ivAtk'][iv], data_obj['ivDef'][iv]
            bp, blk = set(), set()
            for mb in _census_boundaries:
                if mb['stat'] == 'atk' and atk >= mb['threshold']:
                    bp.add(pretty_species(mb['opponent']))
                elif mb['stat'] == 'def' and dfn >= mb['threshold']:
                    blk.add(pretty_species(mb['opponent']))
            c = _census_cache[iv] = (sorted(bp), sorted(blk))
        return c

    # Item 5: BASE-FORM breakpoint census. For a shadow (or Female-sex) focal,
    # build the SAME census against the base form's own sim + effective stats,
    # so we can report "N breakpoints newly guaranteed by the boost". The base
    # set is NOT scalable from the shadow set (the x1.2/x0.833 boost reshapes
    # win/loss membership), so the base scores come from a real second sim pass
    # baked at dive time (deep_dive.main's base-form pass -> scores_base_arrays).
    # Graceful degrade: missing scores_base_arrays (old blobs) -> empty census
    # -> n_breakpoint_newly stays 0 -> the card sentence is omitted.
    _base_census_cover = None
    if scores_base_arrays and base_form_info:
        try:
            _bm = compute_iv_metadata(
                base_form_info['species'], league,
                shadow=base_form_info.get('shadow', False))
        except Exception:
            _bm = []
        # IV enumeration must line up index-for-index with data_obj / the base
        # score grid. Shadow shares base stats with its non-shadow form so the
        # skip-set is identical; a sex sibling with a different skip-set length
        # would mis-index, so we only proceed on an exact length match.
        if len(_bm) == nIvs:
            _base_ivAtk = [m['atk'] for m in _bm]
            _base_ivDef = [m['def_'] for m in _bm]
            _base_ivHp = [m['hp'] for m in _bm]
            _base_data_obj = dict(data_obj)
            _base_data_obj['ivAtk'] = _base_ivAtk
            _base_data_obj['ivDef'] = _base_ivDef
            _base_data_obj['ivHp'] = _base_ivHp
            _base_boundaries = []
            _bb_seen = set()
            for _mode in all_modes:
                _bscores = scores_base_arrays.get(f'{moveset_idx}_{_mode}', [])
                if not _bscores:
                    continue
                for _sweep in ('def', 'atk'):
                    for mb in _find_matchup_boundaries(
                            _bscores, nIvs, nS, nO, _base_data_obj,
                            scenarios, opponents, sweep_stat=_sweep):
                        _k = (mb['opponent'], mb['stat'], mb['threshold'])
                        if _k in _bb_seen:
                            continue
                        _bb_seen.add(_k)
                        _base_boundaries.append(mb)
            _base_census_cache: dict = {}

            def _base_census_cover(iv):
                """Base-form (breakpoint_opps, bulkpoint_opps) the spread clears,
                using the base form's effective stats + its own boundaries."""
                c = _base_census_cache.get(iv)
                if c is None:
                    atk, dfn = _base_ivAtk[iv], _base_ivDef[iv]
                    bp, blk = set(), set()
                    for mb in _base_boundaries:
                        if mb['stat'] == 'atk' and atk >= mb['threshold']:
                            bp.add(pretty_species(mb['opponent']))
                        elif mb['stat'] == 'def' and dfn >= mb['threshold']:
                            blk.add(pretty_species(mb['opponent']))
                    c = _base_census_cache[iv] = (sorted(bp), sorted(blk))
                return c

    # Rarity-gated NOTABLE tiers: built over the WIDE strong pool so the bulk
    # pole's high def-side tiers are present and counted. A tier is notable iff
    # at most REC_NOTABLE_MAX_CLEAR_FRAC of the strong pool clears it. Reused for
    # the pole coverage (atk/bulk poles count NOTABLE-only), the greedy fill
    # universe AND the absolute per-spread labels below.
    notable_tiers: set = set()
    _tier_clearers: dict = {}
    if _anchor_mode:
        _strong = ranked[:min(REC_STRONG_POOL_N, nIvs)]
        for siv in _strong:
            for t in _named_cover(siv):
                _tier_clearers[t] = _tier_clearers.get(t, 0) + 1
        _gate = REC_NOTABLE_MAX_CLEAR_FRAC * len(_strong)
        notable_tiers = {t for t, c in _tier_clearers.items() if c <= _gate}

    if _anchor_mode:
        # Attack pole = max BREAKPOINT COVERAGE, tie-broken by BULK (def then hp)
        # -- the "Focused" attack spread (cf. Dragapult-Sim's "Ninetales Focused"
        # 11/12/5: a buildable line that still hits the key breakpoints, NOT a
        # max-atk glass cannon). Symmetric to the bulk pole: don't atk-max PAST
        # the hardest breakpoint; among IVs clearing the same breakpoint tiers,
        # prefer the bulkier one. The meta breakpoints sit just above the top-50
        # atk ceiling, so coverage is computed over the FULL grid. Falls back to
        # raw max-atk when no breakpoints resolve. Coverage counts only NOTABLE
        # breakpoint tiers (the rarity-gated hard ones), so the pole stops
        # atk-maxing once the MEANINGFUL breakpoints are cleared and banks
        # def/HP from there -- a truer buildable "Focused" spread where the
        # notable breakpoints sit below the atk ceiling, while staying glassy
        # where they sit near max atk.
        def _atk_cover(iv):
            return sum(1 for (_opp, kind, _thr) in (_named_cover(iv) & notable_tiers)
                       if kind == 'damage_breakpoint')
        # Use the coverage selection only when NOTABLE breakpoints exist; with
        # none, _atk_cover is uniformly 0 and would collapse to max-def, so fall
        # through to the plain max-atk pole instead.
        if any(t[1] == 'damage_breakpoint' for t in notable_tiers):
            # Final tie-break on atk so we never headline a strictly-dominated
            # spread: among IVs tied on (breakpoint-coverage, def, hp) -- e.g. a
            # below-cap species where 0/15/15 and 1/15/15 share def+hp at max
            # level -- prefer the higher-atk one (the crowned, efficient-frontier
            # member). breakpoint-coverage is monotonic in atk, so this can only
            # raise atk among equals, never trade away a breakpoint.
            atk_iv = max(range(nIvs),
                         key=lambda iv: (_atk_cover(iv), data_obj['ivDef'][iv],
                                         data_obj['ivHp'][iv], data_obj['ivAtk'][iv]))
        else:
            atk_iv = max(range(nIvs), key=lambda iv: (data_obj['ivAtk'][iv],
                                                      data_obj['ivDef'][iv],
                                                      data_obj['ivHp'][iv]))
        # Bulk pole = max BULKPOINT COVERAGE, tie-broken by HP (Michael's
        # refinement, 2026-06-22). Don't def-max PAST the hardest bulkpoint:
        # among IVs that clear the same set of bulkpoint tiers, prefer the
        # higher-HP one, so the pole isn't a needless 0-HP glass spread unless
        # that exact def is REQUIRED to clear a bulkpoint. (HP raises CP -> lowers
        # level -> lowers def, so banking HP costs def; we bank it only up to the
        # point it would drop a bulkpoint.) Def is the bulkpoint-bearing stat; HP
        # has no bulkpoint mechanic, so it's free to maximize once coverage is
        # fixed. Falls back to raw max-def when no bulkpoints resolve. _ensure_rc
        # gives each pole an rc dict.
        # Coverage counts only NOTABLE bulkpoint tiers (rarity-gated), so the
        # pole banks HP once the meaningful bulkpoints are cleared.
        def _bulk_cover(iv):
            return sum(1 for (_opp, kind, _thr) in (_named_cover(iv) & notable_tiers)
                       if kind == 'bulkpoint')
        # Coverage selection only when NOTABLE bulkpoints exist; else max-def.
        if any(t[1] == 'bulkpoint' for t in notable_tiers):
            # Final tie-break on atk (same rationale as the attack pole above):
            # without it, a below-cap species ties 0/15/15 and 1/15/15 on
            # (bulkpoint-coverage, hp, def) and max() returns the first by index
            # -- the lower-atk, strictly-dominated, un-crowned spread (the
            # 2026-06-24 UL Mimikyu card bug). bulkpoint-coverage is monotonic in
            # def/hp, so adding atk last only breaks pure ties, never costs a
            # bulkpoint.
            bulk_iv = max(range(nIvs),
                          key=lambda iv: (_bulk_cover(iv), data_obj['ivHp'][iv],
                                          data_obj['ivDef'][iv], data_obj['ivAtk'][iv]))
        else:
            bulk_iv = max(range(nIvs),
                          key=lambda iv: (data_obj['ivDef'][iv],
                                          data_obj['ivHp'][iv],
                                          data_obj['ivAtk'][iv]))
        _ensure_rc(atk_iv)
        _ensure_rc(bulk_iv)
    else:
        # No-anchor fallback: no named meta to reach for, so keep the prior
        # behavior -- the atk pole stays the highest-atk IV in the strong pool
        # (always has an rc), no bulk pole, generic labels.
        atk_iv = max(by_iv, key=lambda iv: (data_obj['ivAtk'][iv],
                                            by_iv[iv]['score']))
        bulk_iv = None

    # Won-set fallback signature (drives selection only when no anchors).
    _won_cache: dict = {}

    def _won_set(iv):
        w = _won_cache.get(iv)
        if w is None:
            base = iv * nS * nO
            w = _won_cache[iv] = frozenset(
                (si, oi) for si in range(nS) for oi in range(nO)
                if scores_flat[base + si * nO + oi] >= 500)
        return w

    chosen_ivs = []

    def _admit(iv):
        if iv not in chosen_ivs:
            chosen_ivs.append(iv)

    # Seed three poles unconditionally (floor >= 2 after collapsing coincident
    # poles). Each pole is a distinct teambuilding choice; they bypass every
    # gate. The bulk pole only fires in anchor mode (it has no named story
    # otherwise).
    _admit(lead_iv)
    _admit(atk_iv)
    if _anchor_mode:
        _admit(bulk_iv)

    # Strict-dominance guard for the EXTRA-spread fill below: never admit a
    # spread that another reachable IV weakly-dominates on (atk, def, hp) -- it
    # would headline a wasted-IV target (e.g. Aegislash (Shield)'s 'Bait Robust'
    # 0/9/14, dominated by 0/9/15). Same Pareto test as the crown marker
    # (efficiency.efficient_frontier), so an extra spread is admitted only if it
    # would be crowned. The three poles above are EXEMPT: they are seeded
    # unconditionally as distinct teambuilding extremes, and their atk tie-break
    # already keeps them on the frontier.
    _eff_mask = efficient_frontier(
        list(zip(data_obj['ivAtk'], data_obj['ivDef'], data_obj['ivHp'])))

    if _anchor_mode:
        # Greedy fill of EXTRA spreads (beyond the 3 poles) over the notable-tier
        # universe not yet covered by the chosen set. Tie-breaks: prefer the
        # candidate whose new tiers are HARDEST (fewest strong-pool clearers),
        # then higher composite score. Near-twins fall out for free (same tiers
        # -> zero marginal gain). Stops on cap, full coverage, or zero gain.
        covered: set = set()
        for iv in chosen_ivs:
            covered |= (_named_cover(iv) & notable_tiers)
        while len(chosen_ivs) < REC_MAX_SPREADS and (notable_tiers - covered):
            best = None  # ((gain, -hardness, score), iv, new_tiers)
            for rc in rec_candidates:
                iv = rc['iv']
                if iv in chosen_ivs:
                    continue
                if not _eff_mask[iv]:
                    continue  # strictly dominated -> never headline it
                new_tiers = (_named_cover(iv) & notable_tiers) - covered
                if not new_tiers:
                    continue
                hardness = sum(_tier_clearers[t] for t in new_tiers)
                key = (len(new_tiers), -hardness, rc['score'])
                if best is None or key > best[0]:
                    best = (key, iv, new_tiers)
            if best is None:
                break  # nothing left adds a notable tier -> saturated
            _admit(best[1])
            covered |= best[2]
    else:
        # No anchors: v1-style won-set symdiff distinctness, generic labels.
        for rc in rec_candidates:
            if len(chosen_ivs) >= REC_MAX_SPREADS:
                break
            iv = rc['iv']
            if iv in chosen_ivs:
                continue
            if not _eff_mask[iv]:
                continue  # strictly dominated -> never headline it
            if min(len(_won_set(iv) ^ _won_set(c)) for c in chosen_ivs) \
                    >= REC_DISTINCTNESS_MIN_SYMDIFF:
                _admit(iv)

    # Attach ABSOLUTE, CENSUS per-spread coverage for the card:
    # cover_breakpoints / cover_bulkpoints list EVERY distinct opponent (per
    # kind) for which this spread clears a guaranteed break/bulkpoint -- the
    # full matchup-boundary census (cf. Dragapult-Sim's "18 guaranteed
    # breakpoints" line), NOT the small curated resolved-anchor set and NOT
    # rarity-gated. Selection above stays anchor/notable-based (the poles bank
    # def/HP off the rarity-hard tiers); only these card LABELS go census.
    # n_breakpoint_opps / n_bulkpoint_opps are the headline census counts.
    # Absolute (not differential vs the lead), so each pole's own coverage shows
    # in full.
    if _anchor_mode:
        for iv in chosen_ivs:
            bp, blk = _census_cover(iv)
            rc = by_iv[iv]
            rc['cover_breakpoints'] = bp
            rc['cover_bulkpoints'] = blk
            rc['n_breakpoint_opps'] = len(bp)
            rc['n_bulkpoint_opps'] = len(blk)
            # Item 5: breakpoints the BOOST newly guarantees -- opponents this
            # spread clears a breakpoint against as a shadow/variant but NOT as
            # the base form. set difference of display-name sets (per spread).
            if _base_census_cover is not None:
                base_bp, _ = _base_census_cover(iv)
                rc['n_breakpoint_newly'] = len(set(bp) - set(base_bp))

    # Reorder chosen rc dicts so the lead (rank-1 battle-score) spread leads
    # (card headline / _rec_idx read chosen_recs[0]), then by composite score.
    chosen_recs = [by_iv[lead_iv]] + sorted(
        (by_iv[iv] for iv in chosen_ivs if iv != lead_iv),
        key=lambda rc: rc['score'], reverse=True)
    # NOTE: do NOT rebind rec_candidates -- it stays the full composite-sorted
    # list so the dive-page "Top Picks" HTML (render_results_section) and the
    # headline-mon default keep their pre-Phase-A behavior. Only the two
    # card/scatter sinks below read the chosen 2-6 set.

    # Store the chosen recommended IV indices so the JS engine can render them
    # as a distinct overlay trace on the scatter plot.
    data_obj['recIvs'] = [rc['iv'] for rc in chosen_recs]
    # Role labels (Balanced / Max Bulk / Attack Weight / ...) parallel to recIvs,
    # for the opponent-threats "which build wins" chips.
    data_obj['recStyles'] = [rc.get('style', '') for rc in chosen_recs]

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
        # Mirror-tier synthesis: when the focal species is in the
        # opponent pool, synthesize a "<species> Mirror Bulk" / "Mirror
        # Atk" tier from the auto-anchor's mirror data using a mean-
        # score gate (passing-cohort mean >= 500 AND > failing-cohort
        # mean, in majority of scenarios). Article-era "Species Mirror
        # Bulk" framing — the standard 75/25 anchor-flip partition gate
        # filters mirror anchors out because the cohort can win on
        # average without 75%+ per-IV win rates. See
        # `synthesize_mirror_tier` docstring for the gate rationale.
        # Append-only; no existing tier is removed or replaced.
        _focal_species = data_obj.get('species') or ''
        _mirror_scores = (_mirror_synth_scores(score_arrays, moveset_idx)
                          if _focal_species else None)
        if _mirror_scores:
            # Optional state pickle for offline iteration on the synth
            # gate. Set DUMP_SYNTH_STATE=/path/to/file.pkl on the dive
            # invocation; the dump fires once per (moveset, focal-
            # species) pair. See cleanup pain point #2 in
            # `project_post_ship_cleanup_pain_points.md` — this is the
            # smallest-possible replay-from-saved-state mode for the
            # mirror-tier synthesis pass; a generalized version could
            # cover other analytical passes too.
            try:
                import os as _os
                if _os.environ.get('DUMP_SYNTH_STATE'):
                    import pickle as _pkl
                    _dump_path = _os.environ.get('DUMP_SYNTH_STATE')
                    with open(_dump_path, 'wb') as _f:
                        _pkl.dump({
                            'species': _focal_species,
                            'scores_flat': _mirror_scores,
                            'nIvs': nIvs, 'nS': nS, 'nO': nO,
                            'data_obj': data_obj,
                            'scenarios': scenarios,
                            'opponents': opponents,
                            'resolved_anchors': resolved_anchors_top,
                            'existing_tiers': effective_tiers,
                        }, _f)
                    logger.info(f"  [mirror-synth] state dumped to {_dump_path}")
            except Exception as _e:
                logger.warning(f"  [mirror-synth] state dump failed: {_e}")
            _mirror_tier = _synthesize_mirror_tier(
                species=_focal_species,
                scores_flat=_mirror_scores,
                nIvs=nIvs, nS=nS, nO=nO,
                data_obj=data_obj,
                scenarios=scenarios,
                opponents=opponents,
                resolved_anchors=resolved_anchors_top,
                existing_tiers=effective_tiers,
                focal_shadow=focal_shadow,
            )
            if _mirror_tier:
                effective_tiers = list(effective_tiers) + [_mirror_tier]
                logger.info(f"  Synthesized mirror tier: "
                            f"{_mirror_tier['name']} "
                            f"({_mirror_tier['desc']})")
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
            # B4 (mercuryish review): the guide's "{{dive:tier_count}}"
            # token resolver and any other consumer that wants to count
            # *rendered tier cards* (rather than plot-traced tiers)
            # should use effectiveTierCount, which keeps the General
            # fallback. Visible cards = len(effective_tiers); plot
            # legend entries = len(data['tiers']).
            data_obj['effectiveTierCount'] = len(effective_tiers)
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
    # Narrative generation is done per-moveset in the main HTML assembly
    # loop (_generate_narrative_for_moveset). The placeholder marker is
    # now emitted directly by render_results_section as the IV
    # Recommendations section intro (B1), so no injection is needed here.

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
  <label style="font-size:12px;color:var(--text-muted)"><input type="checkbox" id="alpha-chk"
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

    # ---- Dive-card context (consumed by deep_dive_card.build_card_model) ----
    # Stash the non-recomputable analysis locals on data_obj so the card
    # renderer can read them after this returns. Includes the cheap
    # single-IV win-rate and best/worst matchups (both need the scores_flat
    # layout, which lives here). The caller MUST pop '_cardCtx' before the
    # DATA blob is JSON-serialized -- flips carry sets (bait_modes).
    _rec_idx = (chosen_recs[0]['iv'] if chosen_recs
                else (ranked[0] if ranked else 0))
    # Card win-rates span ALL shield scenarios (incl. asymmetric 0-1/1-2/2-1
    # etc.) -- the asymmetric matchups are the whole point of this card
    # style. The single-IV number here and the opponent-IV robustness number
    # in the renderer both use the same full scenario set.
    _siv_w = _siv_t = 0
    _opp_sum = [0.0] * nO
    for _oi in range(nO):
        for _si in range(nS):
            _v = scores_flat[_rec_idx * nS * nO + _si * nO + _oi]
            _opp_sum[_oi] += _v
            _siv_t += 1
            if _v > 500:
                _siv_w += 1
    _opp_avg = [(_opp_sum[oi] / nS if nS else 0.0) for oi in range(nO)]
    _names = opponent_names or [f'opp{oi}' for oi in range(nO)]
    _order = sorted(range(nO), key=lambda oi: _opp_avg[oi])
    _key_losses = [(_names[oi], _opp_avg[oi]) for oi in _order[:3]
                   if _opp_avg[oi] < 500]
    _key_wins = [(_names[oi], _opp_avg[oi])
                 for oi in reversed(_order) if _opp_avg[oi] > 500][:3]

    # Two-#1s explainer (Michael 2026-06-22): our headline metric is BATTLE
    # SCORE, so the lead/headline IV (_rec_idx == chosen_recs[0] == ranked[0]) is
    # the rank-1 battle-score spread. When the rank-1 STAT PRODUCT IV is a
    # *different* spread -- and especially the notable case where it wins MORE
    # matchups than our battle-score #1 -- we owe the reader an explanation, since
    # we pitch battle score as the better metric. Surface a blurb only when the
    # two #1s actually diverge (significance-gated).
    _two_ones = None
    _sp1 = next((i for i in range(nIvs)
                 if _spranks and i < len(_spranks) and _spranks[i] == 1), None)
    if _sp1 is not None and _sp1 != _rec_idx and nS and nO:
        # Win COUNTS (matchups > 500) for each #1. Gate the blurb on a MEANINGFUL
        # gap: only when the stat-product #1 wins notably MORE matchups than our
        # battle-score #1 (the confusing "why not the hundo?" case); near-ties are
        # suppressed.
        _bs_wins = _siv_w  # battle-#1 == _rec_idx; count computed above
        _sp_wins = sum(1 for _si in range(nS) for _oi in range(nO)
                       if scores_flat[_sp1 * nS * nO + _si * nO + _oi] > 500)
        if (_sp_wins - _bs_wins) >= REC_TWO_ONES_MIN_WINRATE_GAP * nS * nO:
            def _ivstr(iv):
                return (f"{data_obj['ivA'][iv]}/{data_obj['ivD'][iv]}/"
                        f"{data_obj['ivS'][iv]}")

            def _opp_avgs(iv):
                base = iv * nS * nO
                return [sum(scores_flat[base + _si * nO + _oi]
                            for _si in range(nS)) / nS for _oi in range(nO)]
            # "Picking up": opponents the stat-product #1 wins on average that
            # battle-#1 gives up. Per-opponent avg over all 9 shields. Names raw;
            # the card prettifies.
            _bs_oavg = _opp_avgs(_rec_idx)
            _sp_oavg = _opp_avgs(_sp1)
            _onames = opponent_names or [f'opp{_oi}' for _oi in range(nO)]
            _gives_up = sorted((oi for oi in range(nO)
                                if _sp_oavg[oi] > 500 >= _bs_oavg[oi]),
                               key=lambda oi: _sp_oavg[oi] - _bs_oavg[oi],
                               reverse=True)
            _two_ones = {
                'bs_iv': _ivstr(_rec_idx), 'bs_wins': _bs_wins,
                'bs_score': round(avg_scores[_rec_idx]),
                'sp_iv': _ivstr(_sp1), 'sp_wins': _sp_wins,
                'sp_score': round(avg_scores[_sp1]),
                'total': nS * nO,
                'sp_wins_more': True,
                'gives_up': [_onames[oi] for oi in _gives_up[:3]],
                'gives_up_n': len(_gives_up),
            }
    # Form-level "newly guaranteed vs sibling form" break/bulkpoint trade
    # (Dragapult-Sim style), shown once per dive as a spanning bar. Built from
    # the SAME anchor-based census as the per-spread "N newly guaranteed"
    # numbers (rc['n_breakpoint_newly'] above), rolled up to the FORM level:
    # the UNION across the recommended spreads of (focal census - base census)
    # for breakpoints, and the symmetric (base census - focal census) for
    # bulkpoints. This is the decisive-coverage basis, NOT the old raw-damage
    # census (which over-counted to ~the whole pool -- the 73-vs-73 bug). The
    # bar's opponent names are pretty display names matching the dive anchors,
    # so the bar links land on the right #opp-* slugs.
    #
    # Optional future upgrade: report breakpoints guaranteed across each
    # opponent's TOP-512 IVs (Dragapult-Sim's footnote) instead of the
    # default-IV point estimate; our per-spread point estimate already tracks
    # their number closely, so this stays a point estimate for now.
    _sibling_trade = None
    try:
        _bp_gained, _blk_lost = set(), set()
        if _anchor_mode and _base_census_cover is not None:
            for _rc in chosen_recs:
                _iv = _rc['iv']
                _f_bp, _f_blk = _census_cover(_iv)
                _b_bp, _b_blk = _base_census_cover(_iv)
                _bp_gained |= (set(_f_bp) - set(_b_bp))
                _blk_lost |= (set(_b_blk) - set(_f_blk))
        _sibling_trade = form_sibling_trade(
            data_obj.get('species', ''), focal_shadow,
            sorted(_bp_gained), sorted(_blk_lost))
    except Exception as e:
        logger.warning(f"  sibling-trade census failed ({type(e).__name__}: "
                       f"{e}); form trade bar omitted")

    data_obj['_cardCtx'] = {
        'two_number_ones': _two_ones,
        'sibling_trade': _sibling_trade,
        'rec_candidates': chosen_recs,
        'rec_idx': _rec_idx,
        'flips': flips,
        'flip_map': flip_map,
        'has_bait_axis': has_bait_axis,
        'opp_label': opp_label,
        'key_wins': _key_wins,
        'key_losses': _key_losses,
        'single_iv_winrate': {
            'frac': (_siv_w / _siv_t if _siv_t else 0.0),
            'pool': nO, 'scenarios': nS},
        # Item 5: base-form label for the "N newly guaranteed vs base form"
        # card sentence. None (old blobs / non-gated focals) -> sentence omitted.
        'base_form': (base_form_info if _base_census_cover is not None else None),
    }

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


def _remove_stale_split_siblings(base_html_path, written_paths):
    """Delete ``{stem}_m*{ext}`` siblings left over from a previous dive.

    A re-dive whose moveset enumeration changed (rankings churn, a
    different ``--top-movesets``) writes differently-named split files,
    so the old ones survive as orphans carrying outdated data. Downstream
    consumers read every sibling in the directory — generate_article.py's
    freshness gate refuses to run on mixed vintages (this killed the
    2026-06-11 overnight chain) and publish would ship the stale pages.
    """
    import glob as _glob
    import os as _os
    directory = _os.path.dirname(base_html_path) or '.'
    stem, ext = _os.path.splitext(_os.path.basename(base_html_path))
    keep = {_os.path.abspath(p) for p in written_paths}
    pattern = _os.path.join(directory, _glob.escape(stem) + f'_m[0-9]*{ext}')
    for p in sorted(_glob.glob(pattern)):
        if _os.path.abspath(p) not in keep:
            _os.remove(p)
            logger.info(f"  Removed stale split sibling: "
                        f"{_os.path.basename(p)}")


def generate_interactive_html(species, league, moveset_data, html_path,
                              thresholds=None, opponent_label=None,
                              shield_scenarios=None, opponent_names=None,
                              opp_iv_modes=None, reference_idx=-1,
                              standalone=False, slayer_iter_result=None,
                              cli_args_str=None, has_toml_tiers=False,
                              shadow=False, split_info=None,
                              article_slug='',
                              threshold_registry=None,
                              species_narrative=None,
                              shared_plotly_dir=None,
                              card_out_path=None,
                              card_robust_k=DEFAULT_CARD_ROBUST_K,
                              opp_movesets=None, mechanics='legacy',
                              best_buddy=None, slayer_iter_result_l51=None):
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

    # Shadow focal: re-derive the legacy stat-cutoff thresholds from the
    # registry under the shadow-suffixed species key. A shadow / constructed
    # focal must only inherit tiers authored for "<Species> (Shadow)" - never
    # the non-shadow base species' tiers. The base species' gobattlekit-default
    # expert cutoffs (e.g. HomeSliceHenry / SwagTips def floors) are numerically
    # invalid for the shadow form (x1.2 atk / x0.833 def shift the floors) and
    # would falsely credit those experts with analyzing an unreleased mon. If
    # the registry has no shadow-authored spreads, the result is empty and the
    # Expert-Analysis zone is correctly absent (pre-release). Authored shadow
    # spreads (e.g. Drapion (Shadow), Quagsire (Shadow)) are preserved because
    # they live under the shadow key. Runs on replay blobs too, where the
    # leak is baked into `thresholds` but the registry still exposes the
    # (wrong) base-species key, so the shadow-key lookup drops it.
    if shadow and threshold_registry is not None:
        thresholds = as_legacy_dict(
            threshold_registry, f'{species} (Shadow)', league.capitalize(),
        ) or None

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

    # orgodemir's "efficient IV" frontier (u/orgodemir,
    # reddit.com/r/TheSilphArena/comments/yxzg7f/): an IV spread is efficient
    # iff no OTHER spread dominates it on all three scaled stats (>= on each,
    # strictly > on at least one). Threshold-independent, so compute the global
    # frontier once over the displayed (rounded) ivAtk/ivDef/ivHp arrays and
    # reuse everywhere. For a shadow dive these are shadow-boosted, so the
    # frontier lives in shadow-effective space (correct).
    iv_efficient = efficient_frontier(list(zip(iv_atk, iv_def, iv_hp)))

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
        # Parallel-aligned display strings: same order as `opponents`,
        # each name rewritten via `pretty_species` so shadow/regional
        # tags read as a leading prefix ("Shadow Forretress" instead
        # of "Forretress (Shadow)") and the bare male form picks up
        # a "(Male)" qualifier when a Female sibling exists. JS code
        # uses this for display; `opponents` stays in gamemaster
        # format for any lookup-by-name path. Tag suffixes that
        # `pretty_species` doesn't recognize (e.g. "(atk-weighted)")
        # pass through unchanged.
        'opponentsDisplay': [
            pretty_species(_n) for _n in opponent_names
        ],
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
        'movesets': [{'label': md['label'], 'prettyLabel': _pretty_moveset(md['label']),
                      **({'energyMoves': md['energy_moves']}
                         if md.get('energy_moves') is not None else {})}
                     for md in moveset_data],
        # Reference IV indices (for matchup diff in hover text)
        'pvpokeRefIvIdx': pvpoke_ref_iv_idx,
        'rank1RefIvIdx': rank1_ref_iv_idx,
        # IV metadata
        'ivA': iv_a, 'ivD': iv_d, 'ivS': iv_s,
        'ivLv': iv_lv, 'ivCp': iv_cp,
        'ivAtk': iv_atk, 'ivDef': iv_def, 'ivHp': iv_hp,
        'ivEfficient': iv_efficient,
        'ivSp': iv_sp, 'spRanks': sp_ranks, 'ivTiers': iv_tiers, 'ivAllTiers': iv_all_tiers,
    }

    # ---- Best-buddy / L51 level metadata (only when the toggle is active) ----
    # The level-dependent IV arrays at the alt cap, parallel to the top-level
    # (L50) ones. ivA/ivD/ivS are level-invariant (same IV set) so they are NOT
    # duplicated; the JS reads them straight from the top level for both views.
    # When best-buddy is inactive nothing is emitted, so a feature-off dive is
    # byte-identical.
    def _level_meta_arrays(meta_lvl):
        """JS-facing level-dependent arrays for one level's canonical_meta."""
        a_lv = [m[3] for m in meta_lvl]
        c_lv = [m[4] for m in meta_lvl]
        atk_lv = [round(m[5], 2) for m in meta_lvl]
        def_lv = [round(m[6], 2) for m in meta_lvl]
        hp_lv = [m[7] for m in meta_lvl]
        sp_lv = [round(m[5] * m[6] * m[7], 1) for m in meta_lvl]
        sp_sorted_lv = sorted(range(len(meta_lvl)), key=lambda i: sp_lv[i], reverse=True)
        sp_ranks_lv = [0] * len(meta_lvl)
        for _r, _idx in enumerate(sp_sorted_lv):
            sp_ranks_lv[_idx] = _r + 1
        eff_lv = efficient_frontier(list(zip(atk_lv, def_lv, hp_lv)))
        tiers_lv = [-1] * len(meta_lvl)
        all_tiers_lv = [[] for _ in range(len(meta_lvl))]
        if thresholds:
            for i in range(len(meta_lvl)):
                for ti, (_tn, th) in enumerate(thresholds.items()):
                    ok = True
                    if th['attack'] > 0 and atk_lv[i] < th['attack']:
                        ok = False
                    if th['defense'] > 0 and def_lv[i] < th['defense']:
                        ok = False
                    if th['stamina'] > 0 and hp_lv[i] < th['stamina']:
                        ok = False
                    if ok:
                        all_tiers_lv[i].append(ti)
                        if tiers_lv[i] == -1:
                            tiers_lv[i] = ti
        rank1_lv = min(range(len(meta_lvl)), key=lambda i: sp_ranks_lv[i]) if meta_lvl else -1
        return {
            'ivLv': a_lv, 'ivCp': c_lv,
            'ivAtk': atk_lv, 'ivDef': def_lv, 'ivHp': hp_lv,
            'ivSp': sp_lv, 'spRanks': sp_ranks_lv,
            'ivEfficient': eff_lv, 'ivTiers': tiers_lv, 'ivAllTiers': all_tiers_lv,
            'rank1RefIvIdx': rank1_lv,
        }

    _bb_active = bool(best_buddy and best_buddy.get('active')
                      and moveset_data and moveset_data[0].get('meta_l51'))
    # Only surface to the client when there's something to show -- an active
    # toggle, or a "best-buddy changes nothing here" note. A plain dive with the
    # toggle off (or league no-op) emits nothing, so it stays byte-identical.
    if _bb_active or (best_buddy and best_buddy.get('note')):
        # Carry the toggle metadata (and the no-op note) to the client even
        # when inactive, so the UI can show "best-buddy changes nothing here".
        data_obj['bestBuddy'] = {
            'active': _bb_active,
            'defaultDisplay': best_buddy.get('default_display'),
            'defaultCap': best_buddy.get('default_cap'),
            'altCap': best_buddy.get('alt_cap'),
            'note': best_buddy.get('note'),
        }
    if _bb_active:
        data_obj['ivL51'] = _level_meta_arrays(moveset_data[0]['meta_l51'])

    # Score arrays: one per (moveset_idx, opp_iv_mode). When best-buddy is
    # active each moveset also carries an L51 grid, keyed '{mi}_{mode}@51'.
    # energy_arrays mirrors score_arrays EXACTLY (same keys incl. @51), but only
    # when --compare-energy populated md['energy']; empty otherwise -> embeds
    # nothing (byte-identical).
    score_arrays = {}
    energy_arrays = {}
    for mi, md in enumerate(moveset_data):
        for mode in opp_iv_modes:
            key = f'{mi}_{mode}'
            score_arrays[key] = md['scores'][mode]
            if _bb_active and md.get('scores_l51') and mode in md['scores_l51']:
                score_arrays[f'{key}@51'] = md['scores_l51'][mode]
            if md.get('energy') and mode in md['energy']:
                energy_arrays[key] = md['energy'][mode]
                if (_bb_active and md.get('energy_l51')
                        and mode in md['energy_l51']):
                    energy_arrays[f'{key}@51'] = md['energy_l51'][mode]

    # Item 5: base-form score arrays (only the movesets that carry a
    # 'scores_base' -- currently moveset 0 on shadow/Female-sex focals).
    # Old replay blobs lack the key entirely, so this stays empty and the
    # downstream census line is silently omitted (graceful degrade).
    scores_base_arrays = {}
    base_form_info = None
    for mi, md in enumerate(moveset_data):
        sb = md.get('scores_base')
        if not sb:
            continue
        if base_form_info is None:
            base_form_info = md.get('base_form')
        for mode in opp_iv_modes:
            if mode in sb:
                scores_base_arrays[f'{mi}_{mode}'] = sb[mode]

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
    # slayer archetype (Anchors-First / CMP-First) from
    # build_slayer_archetypes. Rendered as a separate legend entry on the
    # scatter plot with a distinct marker shape (star-diamond) so users
    # can see what avg-score trade a "slayer-quality" spread costs vs the
    # avg-score-optimal cluster. Archetype membership is a different
    # optimization target than avg score (anchor coverage / CMP first),
    # so the two often don't coincide - visualizing the gap is the point.
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
    # Best-buddy view needs a LIKE-FOR-LIKE cohort so the CMP pill compares
    # best-buddy attack vs a best-buddy cohort -- not an L50.5/51 attack against
    # an L50 cohort (wrong in the sub-IV band where the half-level CPM tips the
    # simultaneous-charge tiebreak).
    #   (b) authoritative: a cohort re-converged at the best-buddy cap (both
    #       mirror sides best-buddied) -- slayer_iter_result_l51.
    #   (a) fallback: recompute the L50-converged survivors' attack at the cap
    #       (no re-convergence) if the L51 slayer pass is unavailable.
    if _bb_active and mirror_cohort_atk:
        _alt = best_buddy.get('alt_cap')
        _c51 = []
        if slayer_iter_result_l51 and slayer_iter_result_l51.get('final'):
            _c51 = sorted(
                float(s['atk']) for s in slayer_iter_result_l51['final']
                if s.get('atk') is not None)
        if not _c51:
            for s in slayer_iter_result['final']:
                iv = s.get('iv')
                if iv is None:
                    continue
                _c51.append(Pokemon.at_best_level(
                    species, iv[0], iv[1], iv[2],
                    league=league, max_level=_alt, shadow=shadow).atk)
            _c51 = sorted(_c51)
        data_obj['mirrorCohortAtk51'] = _c51

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
    #   * winsMirror: mirror-match wins vs the slayer iteration's final
    #     opponent population. DENSE since the 2026-06 redesign — the
    #     iteration's last round scores every focal IV, exported as
    #     'all_scores' (triple -> (total_wins, frac_wins, avg_score,
    #     n_pairs)). Falls back to the sparse final-pool data for old
    #     replay blobs that predate all_scores.
    mirror_wins_by_idx: dict = {}
    mirror_wins_max = 0
    if slayer_iter_result and slayer_iter_result.get('all_scores'):
        for iv_triple, mw in slayer_iter_result['all_scores'].items():
            idx = iv_idx_by_triple.get(tuple(iv_triple))
            if idx is None:
                continue
            wins = mw[0]
            mirror_wins_by_idx[idx] = wins
            if wins > mirror_wins_max:
                mirror_wins_max = wins
    elif slayer_iter_result and slayer_iter_result.get('final'):
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
        _bait_meta = ' | <b style="color:var(--title)">Bait: OFF</b>'
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
    # Gender filter: when the focal species is gender-differentiated
    # (Oinkologne / Meowstic / Indeedee), CSV mons that resolve to a
    # final form via evolution walkup (e.g. Lechonk → Oinkologne or
    # Oinkologne (Female)) need to be filtered by their CSV-recorded
    # gender so the wrong-gender form doesn't false-positive on the
    # focal dive. PvPoke's gamemaster ships Lechonk's evolutions list
    # as ['oinkologne', 'oinkologne'] (both Male) so the female form
    # only reaches the matcher via the sibling-form pass in
    # evolution_lines._build_evolution_lines.
    _require_gender = None
    if _collection_species_key.endswith(' (Female)'):
        _require_gender = 'female'
    elif f'{_collection_species_key} (Female)' in _pkidx:
        _require_gender = 'male'
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
        # Best-buddy: an off-grid mon's stat-product rank differs at the alt cap
        # (level-capped IVs climb past the default), so bake a parallel alt-cap
        # table the JS uses in the L51 view. On-grid mons already read the
        # toggle-aware DATA.spRanks; this only matters for OFF-grid mons (IV
        # triples this dive didn't simulate -- only possible on a --species-iv-
        # floor dive), e.g. a raid-only mon dived with a floor, later scanned
        # from a wild-release event with low IVs, before a re-dive.
        _rank_table_alt = None
        if best_buddy and best_buddy.get('active') and best_buddy.get('alt_cap'):
            _ranked_alt = _rank_lookup(
                _collection_species_key, league=league,
                max_level=best_buddy['alt_cap'], shadow=shadow)
            _rank_table_alt = {f'{a},{d},{s}': r
                               for (a, d, s), r in _ranked_alt.items()}
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
            'requireGender':   _require_gender,
        }
        if _rank_table_alt is not None:
            _collection_data['rankLookupAlt'] = {
                _collection_species_key: {_rank_shadow_key: _rank_table_alt}}
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

    # Display-rename: focal species name in the title and H1 banner
    # goes through pretty_species so "Forretress (Shadow)" reads as
    # "Shadow Forretress", "Oinkologne" gets a "(Male)" suffix when
    # there's a Female sibling, etc. The internal `species` variable
    # stays in gamemaster format for any lookup. Shadow is tracked
    # via a separate flag; reconstruct the gamemaster-format name
    # before pretty_species so shadow-form dives render correctly.
    _species_for_display = f'{species} (Shadow)' if shadow else species
    species_pretty = apply_dive_title_override(pretty_species(_species_for_display))

    html = f"""<!DOCTYPE html>
{cli_comment}<html {data_theme_attr()}>
<head>
<meta charset="utf-8">
{theme_head_script()}
<title>{species_pretty} {league.title()} League IV Deep Dive</title>
{plotly_tag}
<style>{theme_css()}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 20px; background: var(--bg); color: var(--text); }}
  h1 {{ color: var(--title); }}
  .meta {{ color: var(--text-muted); font-size: 13px; margin-bottom: 15px; }}
  details.meta {{ cursor: pointer; }}
  details.meta summary {{ color: var(--text-muted); font-size: 13px; }}
  .controls {{ background: var(--surface); padding: 10px 14px; border-radius: 2px;
               margin-bottom: 15px; display: flex; gap: 18px; align-items: center;
               flex-wrap: wrap; }}
  .controls label {{ font-size: 13px; color: var(--text-muted); }}
  .controls select {{ background: var(--surface-2); color: var(--text); border: 1px solid var(--border-2);
                      padding: 4px 8px; border-radius: 2px; font-size: 13px; }}
  .plot-container {{ margin-bottom: 20px; }}
  .summary {{ background: var(--surface); padding: 12px; border-radius: 2px;
              margin-bottom: 20px; font-size: 13px; overflow-x: auto; }}
  .summary table {{ border-collapse: collapse; width: 100%; }}
  .summary th, .summary td {{ text-align: left; padding: 3px 8px;
                               border-bottom: 1px solid var(--border); }}
  .summary td {{ white-space: nowrap; }}
  .summary th {{ color: var(--title); white-space: normal; vertical-align: bottom; }}
  .tier-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
                 font-size: 11px; font-weight: bold; }}
  .threshold-info {{ background: var(--surface); padding: 10px; border-radius: 2px;
                     margin-bottom: 15px; font-size: 13px; }}
  .threshold-info span {{ font-weight: bold; }}
  .methodology {{ color: var(--text-muted); font-size: 12px; max-width: 800px;
                  margin: 10px 0 30px 0; line-height: 1.6; }}
  details.collection-panel {{ background: var(--surface); padding: 10px 14px;
                              border-radius: 2px; margin-bottom: 15px; }}
  details.collection-panel > summary {{ cursor: pointer; color: var(--text);
                                         font-size: 13px; }}
  .collection-body {{ margin-top: 10px; }}
  .collection-instructions {{ font-size: 12px; color: var(--text-muted);
                              margin-bottom: 8px; line-height: 1.5; }}
  #collection-csv {{ width: 100%; background: var(--surface-2); color: var(--text);
                     border: 1px solid var(--border-2); border-radius: 2px;
                     padding: 6px 8px; font-size: 11px;
                     font-family: monospace; resize: vertical;
                     box-sizing: border-box; }}
  .collection-buttons {{ display: flex; gap: 8px; align-items: center;
                         margin-top: 8px; flex-wrap: wrap; }}
  .collection-buttons button {{ background: var(--surface-2); color: var(--text);
                                border: 1px solid var(--border-2); border-radius: 2px;
                                padding: 4px 10px; font-size: 12px;
                                cursor: pointer; }}
  .collection-buttons button:hover {{ background: var(--border-2); }}
  .collection-matches {{ margin-top: 12px; }}
  .collection-matches h5 {{ margin: 8px 0 4px 0; font-size: 12px;
                             color: var(--text); font-weight: 600; }}
  .collection-matches table {{ border-collapse: collapse; font-size: 11px;
                                color: var(--text); width: auto; }}
  .collection-matches th, .collection-matches td {{ padding: 2px 10px 2px 0;
                                                     text-align: left; }}
  /* Body cells stay on one line by default (keeps numeric columns tidy);
     headers wrap so long labels like "Top-Mirror CMP %" don't blow the
     column width out. Column widths are set by the body cells. */
  .collection-matches td {{ white-space: nowrap; }}
  .collection-matches th {{ color: var(--text-muted); font-weight: 500;
                             border-bottom: 1px solid var(--border);
                             white-space: normal;
                             vertical-align: bottom; }}
  /* Opt-in wrap class for prose-heavy columns (Slayer type, Also in).
     Applied via the extras 'cls' hint so only the targeted columns wrap.
     No word-break override so "Jirachi" stays "Jirachi", not "Jir\\nachi". */
  .collection-matches td.wrap {{ white-space: normal; max-width: 22em; }}
  .collection-matches tr.lucky td {{ color: var(--tie); }}
  .collection-matches tr.shadow td {{ color: var(--accent); }}
  .collection-matches td.rank {{ color: var(--accent); font-weight: 600; }}
  .collection-matches td.rank-sp {{ color: var(--text-muted); }}
  .collection-matches tr.matches-hidden-row {{ display: none; }}
  .matches-toggle-btn {{ background: var(--surface-2); color: var(--accent);
                         border: 1px solid var(--border-2); border-radius: 2px;
                         padding: 3px 10px; font-size: 11px; cursor: pointer;
                         margin: 4px 0 8px 0; }}
  .matches-toggle-btn:hover {{ background: var(--border-2); }}
  span.user-anchor-hits {{ font-size: 11px; font-style: italic;
                           margin-left: 6px; }}
  /* "Compare candidates" widget */
  .cmp-section {{ background:var(--surface); border:1px solid var(--border); border-radius:2px;
    padding:6px 16px 14px; margin:14px 0; }}
  .cmp-section.cmp-wide {{ width:96vw; max-width:1560px; position:relative;
    left:50%; transform:translateX(-50%); }}
  .cmp-summary {{ cursor:pointer; font-size:0.95rem; padding:6px 0; }}
  .cmp-note {{ font-size:0.78rem; color:var(--text-muted); font-weight:400; }}
  .cmp-entry {{ display:flex; flex-wrap:wrap; gap:7px; align-items:center;
    font-size:0.82rem; color:var(--text); margin:6px 0 4px; }}
  .cmp-entry input {{ width:46px; font-size:0.82rem; }}
  .cmp-entry button {{ font-size:0.78rem; padding:3px 10px; border-radius:2px;
    border:1px solid var(--border-2); background:var(--surface-2); color:var(--text); cursor:pointer; }}
  .cmp-entry button.cmp-clear {{ border-color:var(--loss); }}
  .cmp-cap {{ color:var(--text-muted); font-size:0.74rem; margin-left:4px; }}
  .cmp-status {{ font-size:0.74rem; }}
  .cmp-empty {{ font-size:0.82rem; color:var(--text-muted); margin:8px 2px; }}
  .cmp-cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:10px; margin:12px 0; }}
  .cmp-card {{ background:var(--surface-2); border:1px solid var(--border-2); border-radius:2px; padding:10px 12px; }}
  .cmp-iv {{ font-size:1.15rem; font-weight:800; color:var(--heading); display:flex;
    justify-content:space-between; align-items:center; }}
  .cmp-x {{ background:none; border:none; color:var(--text-muted); font-size:1.05rem; cursor:pointer;
    line-height:1; padding:0 2px; }}
  .cmp-x:hover {{ color:var(--loss); }}
  .cmp-sub {{ font-size:0.73rem; color:var(--text-muted); margin:2px 0 4px; }}
  .cmp-row {{ display:flex; justify-content:space-between; font-size:0.8rem;
    border-top:1px solid var(--border-2); padding:4px 0; }}
  .cmp-row b {{ color:var(--text); }}
  .cmp-good {{ color:var(--win); }} .cmp-mid {{ color:var(--tie); }} .cmp-bad {{ color:var(--loss); }}
  .cmp-pill {{ display:inline-block; font-size:0.68rem; padding:1px 7px; border-radius:4px;
    background:var(--surface-2); color:var(--energy); margin-top:6px; }}
  .cmp-pill-lose {{ color:var(--tie); }}
  .cmp-panel {{ background:var(--surface-2); border:1px solid var(--border-2); border-radius:2px;
    padding:11px 14px; margin:0 0 14px; }}
  .cmp-panel h4 {{ margin:0 0 3px; font-size:0.86rem; }}
  .cmp-flip-h {{ color:var(--flip); }} .cmp-marg-h {{ color:var(--accent-2); }}
  .cmp-psub {{ font-size:0.74rem; color:var(--text-muted); margin:0 0 9px; }}
  .cmp-tbl {{ border-collapse:collapse; width:100%; font-size:0.82rem; }}
  .cmp-tbl th, .cmp-tbl td {{ text-align:left; padding:5px 9px;
    border-bottom:1px solid var(--bar-track); white-space:nowrap; }}
  .cmp-tbl th {{ color:var(--text-muted); font-weight:600; font-size:0.74rem; }}
  .cmp-m {{ color:var(--text); }}
  .cmp-win {{ color:var(--win); font-weight:700; }}
  .cmp-lose {{ color:var(--loss); font-weight:700; }}
  .cmp-tie {{ color:var(--tie); font-weight:700; }}
  .cmp-flip {{ color:var(--flip); }}
  .cmp-more {{ color:var(--text-muted); font-size:0.76rem; font-style:italic;
    cursor:pointer; text-decoration:underline dotted; }}
  .cmp-more:hover {{ color:var(--text); }}
  .cmp-tbl tr.cmp-xtra {{ display:none; }}
  .cmp-tbl.cmp-all tr.cmp-xtra {{ display:table-row; }}
  .cmp-bar {{ display:inline-block; vertical-align:middle; width:64px; height:9px;
    background:var(--bar-track); border-radius:2px; overflow:hidden; margin-right:6px; }}
  .cmp-bar > span {{ display:block; height:100%; background:var(--win); }}
  .cmp-bar.lo > span {{ background:var(--tie); }}
  .cmp-bar.loss {{ display:flex; justify-content:flex-end; }}
  .cmp-bar.loss > span {{ flex:none; background:var(--loss); }}
  .cmp-hpv {{ font-size:0.76rem; color:var(--text-muted); }}
  .cmp-env {{ font-size:0.72rem; color:var(--energy); }}
  .cmp-leg {{ font-size:0.72rem; color:var(--text-muted); margin-top:5px; }}
  /* Section sidenav. Mirrors the ML IV-guide pages
     (scripts/render_iv_envelope_article.py): sticky side column at wide
     widths, horizontal bar at the top of the content below the 820px
     breakpoint. The .layout wrapper begins AFTER the dive card so the
     infographic stays the first content block; at narrow width the nav
     stacks under the card (it is the first child of .layout), never
     above it. */
  .dd-layout {{ display: flex; gap: 28px; align-items: flex-start; }}
  /* Compact sticky side-nav: short, readable labels (full phrase on hover via
     title=). Width HUGS the content (fit-content) instead of a fixed column, so
     the box is exactly as wide as its longest item (the header, or the
     best-buddy label when shown) + padding -- no dead space -- and reclaims the
     rest of the left gutter for the main content. max-width caps it defensively. */
  nav.dd-toc {{ position: sticky; top: 14px;
                flex: 0 0 auto; width: fit-content; max-width: 200px;
                font-size: 12px; line-height: 1.25; background: var(--surface);
                border-radius: 2px; padding: 9px 11px;
                max-height: calc(100vh - 28px); overflow-y: auto; }}
  nav.dd-toc strong {{ color: var(--title); display: block; margin-bottom: 5px;
                       font-size: 11px;
                       letter-spacing: .04em; }}
  nav.dd-toc a {{ display: block; color: var(--accent); padding: 1px 0;
                  text-decoration: none; }}
  nav.dd-toc a:hover {{ text-decoration: underline; }}
  /* Best-buddy toggle: a distinct separated block below the jump links. */
  .dd-toc-bb {{ margin-top: 8px; padding-top: 7px;
                border-top: 1px solid var(--border-2); }}
  .dd-toc-bb label {{ display: flex; align-items: flex-start; gap: 5px;
                      cursor: pointer; font-size: 0.78rem; color: var(--text);
                      line-height: 1.3; }}
  .dd-toc-bb input {{ margin-top: 2px; }}
  .dd-toc-bb b {{ font-weight: 600; }}
  .dd-toc-bb-note {{ font-size: 0.78rem; color: var(--text-muted); }}
  .dd-main {{ flex: 1; min-width: 0; }}
  @media (max-width: 820px) {{
    .dd-layout {{ flex-direction: column; }}
    /* In column mode width is the cross axis; align-items:flex-start (from
       the row-mode rule) would size .dd-main to its max-content width and
       overflow the viewport, so Plotly tracks an inflated container. Pin it
       to the container width so #plot and all Plotly SVGs follow the viewport. */
    .dd-main {{ width: 100%; }}
    /* Collapsed into the main column: span the FULL width (override the
       hug-content fit-content + max-width cap from the wide-mode rule, and use
       border-box so 100% + padding doesn't overflow), flow the links onto one
       row that wraps only when very skinny, and STICK to the top on scroll
       (top:0) so the section jumps stay reachable. align-items must be reset to
       stretch -- the wide-mode .dd-layout uses flex-start, which in a column
       flex would otherwise size the nav to its content instead of full width. */
    .dd-layout {{ align-items: stretch; }}
    nav.dd-toc {{ position: sticky; top: 0; z-index: 5;
                  flex: none; width: 100%; max-width: none;
                  box-sizing: border-box; max-height: none; overflow: visible;
                  display: flex; flex-wrap: wrap; gap: 2px 16px;
                  align-items: center; }}
    nav.dd-toc strong {{ width: 100%; margin-bottom: 2px; }}
    nav.dd-toc a {{ display: inline-block; padding: 2px 0; }}
    .dd-toc-bb {{ width: 100%; }}
  }}
</style>
</head>
<body>
{theme_picker_html()}
<h1>{species_pretty} - {league.title()} League IV Deep Dive</h1>
<p class="meta">Opponents: {opp_desc}
| Shield scenario(s): {shield_desc} | Policy: pvpoke_dp{_bait_meta}</p>
<!-- DIVE_CARD_SLOT -->
<!-- DD_LAYOUT_OPEN -->
"""

    # Form-change explainer near the top, for form-changing focal species
    # (Aegislash today). Keyed by focal speciesName; silent no-op otherwise.
    _fc_note = _FORM_CHANGE_NOTES.get(species)
    if _fc_note:
        html += _fc_note

    # Related article link (bidirectional link contract: docs/article_schema.md).
    # Gate emission on the built article dir EXISTING: a retired/deleted article
    # (built dir removed, but article_slug still baked in older replay blobs) must
    # not leave a dead ../articles/<slug>/ link on a blob re-render.
    # (oinkologne-cd-2026-05 retirement, 2026-06-25.)
    _articles_dir = (Path(html_path).resolve().parent.parent / 'articles' / article_slug) if article_slug else None
    if article_slug and _articles_dir.exists():
        _article_link = f'../articles/{article_slug}/'
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
            _border_color = 'var(--callout-expert)'  # gold
        elif _authorship == 'both':
            _link_label = 'Analysis'
            _border_color = 'var(--callout-both)'  # green
        else:
            _link_label = 'Related Article'
            _border_color = 'var(--callout-auto)'  # blue
        html += (
            '<div style="background:var(--callout-bg);color:var(--callout-fg);'
            'padding:12px 16px;border-radius:0;'
            f'margin:10px 0;border:1px solid {_border_color}">'
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

    # Best-buddy / L51 toggle -- rendered into the page sidenav (built farther
    # below) so it stays reachable while scrolled down. When best-buddy is a
    # no-op for this species/league, the nav shows the explanatory note instead.
    # setBestBuddyLevel() lives in deep_dive_engine.js. ``_bb_nav_ctrl`` is
    # injected into ``_nav_html``.
    _bb_nav_ctrl = ''
    if _bb_active:
        from html import escape as _bb_esc  # noqa: F401
        _bb_alt = best_buddy.get('alt_cap')
        _bb_checked = (' checked'
                       if int(best_buddy.get('default_display') or 0) == int(_bb_alt)
                       else '')
        _bb_nav_ctrl = (
            '<div class="dd-toc-bb">\n'
            '  <label title="Recompute the whole dive as if this mon were your '
            'best buddy (+1 level)."><input type="checkbox" id="dd-bb-toggle" '
            'onchange="setBestBuddyLevel(this.checked ? \'51\' : \'50\')"'
            f'{_bb_checked}> <b>Allow best-buddy (L{_bb_alt:g})</b></label>\n'
            '</div>\n')
    elif best_buddy and best_buddy.get('note'):
        from html import escape as _bb_esc
        _bb_nav_ctrl = (
            '<div class="dd-toc-bb dd-toc-bb-note">'
            f'{_bb_esc(best_buddy["note"])}</div>\n')

    # Controls
    html += '<div class="controls" id="dd-scatter">\n'
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
        html += ('  <span style="font-size:11px;color:var(--text-muted)">'
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
        _energy_values = sorted({parse_energy(m) for m in opp_iv_modes})
        if len(_energy_values) > 1:
            html += ('  <label>Energy lead: '
                     '<select id="energy-sel" onchange="updateView()">\n')
            for _ev in _energy_values:
                if _ev == 0:
                    _ev_label = 'None (cold start)'
                else:
                    _ev_label = (f'+{_ev} fast move'
                                 f'{"s" if _ev > 1 else ""}')
                html += f'    <option value="{_ev}">{_ev_label}</option>\n'
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
    html += '  <span id="cluster-toggle-wrapper" style="display:none"><label style="font-size:12px;color:var(--text-muted)"><input type="checkbox" id="cluster-chk" onchange="updateView()" style="margin-left:12px"> Show clusters</label></span>\n'
    if thresholds:
        html += '  <span style="font-size:11px;color:var(--text-muted);margin-left:8px">Threshold tiers (e.g. GH Great / GH Good) are expert stat-cutoff regions defined in <a href="#dd-threshold-tiers" style="color:var(--accent)">Threshold Tiers</a> below. Hover legend to isolate; click to lock.</span>\n'
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
            '<span style="font-size:11px;color:var(--text-muted)">'
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
            '      <label style="font-size:12px;color:var(--text-muted)">'
            '<input type="checkbox" id="collection-only-chk"> Show only my mons'
            '</label>\n'
            '      <span id="collection-status" '
            'style="font-size:12px;color:var(--text-muted);margin-left:6px"></span>\n'
            '    </div>\n'
            '    <div class="collection-manual" '
            'style="margin-top:10px;border-top:1px solid var(--border-2);padding-top:10px">\n'
            '      <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">\n'
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
            'style="margin-top:6px;font-size:12px;color:var(--text)"></div>\n'
            '    </div>\n'
            '    <div id="collection-matches" class="collection-matches"></div>\n'
            '  </div>\n'
            '</details>\n'
        )
    else:
        # No collection data: the focal isn't matchable yet (a shadow /
        # pre-release / constructed focal whose gamemaster key carries no
        # rank lookup). Emit a one-line placeholder so the section doesn't
        # silently vanish - readers know the paste-box returns post-release.
        html += (
            '<div id="collection-panel" class="collection-panel" '
            'style="padding:10px 14px">\n'
            f'  <b>Check my collection</b> <span style="font-size:12px;'
            f'color:var(--text-muted)">- Collection check returns once {species_pretty} '
            'is ranked (post-release).</span>\n'
            '</div>\n'
        )

    # "Compare candidates" widget -- a separate, bounded N-way comparison of
    # focal IV spreads YOU enter (manual; no auto "top N"). Small until used;
    # breaks out toward full-bleed as candidates accumulate (JS adds .cmp-wide).
    # All compute is client-side off the embedded grid (no new sims). Always
    # emitted -- it only needs DATA.iv* + the score grid, which every dive has.
    #
    # INTENTIONAL UI divergence from the ML IV-guides: this dive widget uses
    # per-stat Atk/Def/HP + Lvl spinners (the dive sweeps a real level range and
    # the focal can be shadow, so a candidate needs a level), while the guide's
    # "Check my IVs" box (render_iv_envelope_article.py) is a comma-separated
    # paste-box -- a guide is fixed L50/L51 Master with no shadow toggle, so
    # there is nothing per-candidate to twiddle. Both feed the SAME shared
    # cmp_panels.js flip/margin panels; only the input affordance differs.
    html += (
        '<details id="cmp-section" class="cmp-section" open>\n'
        '  <summary class="cmp-summary"><b>Compare candidates</b> '
        '<span class="cmp-note">- up to 7 of your IV spreads, side by '
        'side: wins, mirror, and the close calls that decide the build</span>'
        '</summary>\n'
        '  <div class="cmp-entry">\n'
        '    <b style="color:var(--accent)">Add a spread:</b>\n'
        '    Atk <input id="cmp-a" type="number" min="0" max="15" value="15">\n'
        '    Def <input id="cmp-d" type="number" min="0" max="15" value="15">\n'
        '    HP <input id="cmp-s" type="number" min="0" max="15" value="15">\n'
        '    <button id="cmp-add" type="button">+ Add</button>\n'
        '    <button type="button" class="cmp-clear" onclick="cmpClear()">'
        'Clear all</button>\n'
        '    <span id="cmp-cap" class="cmp-cap">0 / 7 added</span>\n'
        '    <span id="cmp-status" class="cmp-status"></span>\n'
        '  </div>\n'
        '  <div id="cmp-body"></div>\n'
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
        'gap:4px;margin:6px 20px 0 0;font-size:12px;color:var(--text)">\n'
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
        'style="font-size:11px;color:var(--text-muted);margin-left:8px"></span>\n'
        '</div>\n'
    )
    # Top-IVs table controls. Sit immediately above the table they
    # affect (the #summary div). The "Sort by" UX is column-header
    # clicks (see _summarySortClick in deep_dive_engine.js); only the
    # row-count selector lives here.
    html += '<div class="summary-controls" style="margin:10px 0 4px 0;font-size:0.9rem;color:var(--text)">\n'
    html += '  <b style="color:var(--accent)">Top IVs</b>\n'
    html += '  <label style="margin-left:12px">Rows: <select id="summary-n-sel" onchange="updateSummaryTable()">\n'
    html += '    <option value="10">10</option>\n'
    html += '    <option value="25">25</option>\n'
    html += '    <option value="50">50</option>\n'
    html += '    <option value="100">100</option>\n'
    html += '  </select></label>\n'
    html += ('  <span style="margin-left:10px;font-size:11px;color:var(--text-muted)">'
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
    html += ('<h3 style="color:var(--accent-2);margin:0 0 6px 0;'
             'font-size:1.0rem">Battle-Rating Distribution</h3>\n')
    html += ('<p style="font-size:12px;color:var(--text-muted);margin:0 0 10px 0">'
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
            f'  <div style="text-align:center;color:var(--text);'
            f'margin:0 0 4px 0;font-size:0.9rem">{_pretty}</div>\n'
            f'  <div class="dd-histogram-plot" '
            'style="height:260px"></div>\n'
            f'  <div class="dd-histogram-caption" '
            'style="text-align:center;margin:6px 0 0 0;font-size:12px;'
            'color:var(--text)"></div>\n'
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
    # Shadow focal: strip expert-source attribution from any resolved anchor
    # unless the registry carries thresholds authored for "<Species> (Shadow)".
    # A shadow / constructed focal that resolved its anchors against the
    # non-shadow base species' registry (e.g. the auto-discover bug, or an old
    # replay blob baked before the fix) inherits that base species'
    # gobattlekit-default expert credit (HomeSliceHenry / SwagTips). The
    # anchors' numeric thresholds are still valid shadow-form sims, so we keep
    # them - but demote them to the simulation zone by clearing the false
    # attribution, so the Expert Analysis header never credits those experts
    # with an unreleased mon. Legitimately shadow-authored anchors (registry
    # has the "<Species> (Shadow)" key) keep their sources.
    if shadow and _resolved_anchors:
        _has_shadow_authored = (
            threshold_registry is not None
            and threshold_registry.species(f'{species} (Shadow)') is not None
        )
        if not _has_shadow_authored:
            for _a in _resolved_anchors:
                if getattr(_a, 'source', None):
                    _a.source = ''
    import time as _time
    import deep_dive_card as _ddcard

    def _render_level_body(dobj, sarr, *, write_card_out, robust_max_level,
                           base_scores, base_info):
        """Render one level's prose sections + dive card from
        (data_obj, score_arrays). Mutates ``dobj`` (narrative flavors / tier
        renames, pops _cardCtx). Returns
        ``(results_html, analysis_html, card_section, analysis_css, sink)``.
        The caller decides what to do with the css/sink and how to inject the
        card -- the level-default pass keeps the historical behavior; the
        best-buddy pass goes into a <template> for the toggle. ``write_card_out``
        gates the standalone --card-out file (level-default only);
        ``robust_max_level`` is the focal cap for the opponent-IV robustness
        sim (None = league default; the alt cap for the L51 card)."""
        _n0 = _time.time()
        ms0_nar, ms0_flavors = _generate_narrative_for_moveset(
            dobj, sarr, 0, scenarios_list, opponent_names or [],
            opp_iv_modes or [dobj.get('oppIvModes', ['pvpoke'])[0]],
            has_toml_tiers, resolved_anchors=_resolved_anchors,
            species=species, focal_shadow=shadow)
        logger.info(f"  Moveset 0 narrative (pre-render for rename) in "
                    f"{_time.time() - _n0:.1f}s")
        sink = {}
        a_css, r_html, an_html = generate_analysis_sections(
            dobj, sarr, 0, opp_iv_modes[0], shield_scenarios, opponent_names,
            slayer_iter_result=slayer_iter_result, has_toml_tiers=has_toml_tiers,
            anchor_passing_sink=sink, threshold_registry=threshold_registry,
            moveset0_flavors_for_rename=ms0_flavors, focal_shadow=shadow,
            scores_base_arrays=base_scores, base_form_info=base_info)
        if split_info is not None:
            _expected = f"Moveset: {_pretty_moveset(dobj['movesets'][0]['label'])}"
            assert _expected in r_html, (
                f"split-mode analysis subheader mismatch: expected '{_expected}' "
                f"in the Deep Dive Results section of {html_path}")
        # Stash the anchor-passing sets on dobj here (before narratives /
        # pasteTiers) so the embedded DATA key order matches the historical
        # single-pass layout exactly.
        dobj['anchorFlipSets'] = sink
        # Per-moveset narrative zones (moveset 0 reuses the pre-render).
        nblocks = []
        n_ms = len(dobj.get('movesets', [{}]))
        for mi in range(n_ms):
            if mi == 0:
                nh = ms0_nar
            else:
                nh, _ = _generate_narrative_for_moveset(
                    dobj, sarr, mi, scenarios_list, opponent_names or [],
                    opp_iv_modes or [dobj.get('oppIvModes', ['pvpoke'])[0]],
                    has_toml_tiers, resolved_anchors=None,
                    species=species, focal_shadow=shadow)
            if nh:
                vis = 'block' if mi == 0 else 'none'
                nblocks.append(
                    f'<div class="dd-narrative-moveset" data-moveset="{mi}" '
                    f'style="display:{vis}">\n{nh}\n</div>')
        if ms0_flavors and 'tiers' in dobj:
            _rename_plotly_tiers(dobj, ms0_flavors)
        if ms0_flavors:
            _promote_flavors_to_paste_tiers(dobj, ms0_flavors)
        if nblocks:
            nc = '\n'.join(nblocks)
            if '<!-- NARRATIVE_ZONE_PLACEHOLDER -->' in r_html:
                r_html = r_html.replace('<!-- NARRATIVE_ZONE_PLACEHOLDER -->', nc, 1)
            else:
                _sm = '<div class="dd-sim-zone">'
                if _sm in r_html:
                    r_html = r_html.replace(_sm, nc + _sm, 1)
        # Dive card from the analysis context stashed on dobj.
        cctx = dobj.pop('_cardCtx', None)
        card_section = ''
        if cctx is not None:
            try:
                _gm = load_gamemaster()
                _mon = next((m for m in _gm['pokemon']
                             if m['speciesName'] == species), None)
                _types = parse_types(_mon) if _mon else []
                _sprite = sprite_data_uri(species, shadow=shadow)
            except Exception as _e:  # noqa: BLE001
                logger.warning(f"  dive card: type/sprite lookup failed ({_e})")
                _types, _sprite = [], None
            _is_landing = split_info is None or split_info.get('current', 0) == 0
            _robust = None
            if card_out_path and _is_landing and dobj.get('movesets'):
                _ri = cctx['rec_idx']
                _label = dobj['movesets'][0].get('label', '')
                if ' / ' in _label:
                    _ff, _cc = _label.split(' / ', 1)
                    logger.info("  dive card: computing opponent-IV robustness "
                                f"(top-{card_robust_k}, {len(shield_scenarios)} "
                                "shield scenarios)...")
                    _robust = _compute_card_robustness(
                        species, _ff.strip(),
                        [c.strip() for c in _cc.split(',')], shadow,
                        (dobj['ivA'][_ri], dobj['ivD'][_ri], dobj['ivS'][_ri]),
                        league, opponent_names or [], shield_scenarios,
                        opp_movesets=opp_movesets, k=card_robust_k,
                        mechanics=mechanics, focal_max_level=robust_max_level)
            _cm = _ddcard.build_card_model(
                dobj, cctx, types=_types, shadow=shadow,
                robust_winrate=_robust, sprite_uri=_sprite,
                has_author_notes=rendering.narrative_has_human_content(
                    species_narrative))
            card_section = _ddcard.render_card_html(_cm, standalone=False)
            if write_card_out and card_out_path and _is_landing:
                try:
                    _co = os.path.abspath(card_out_path)
                    os.makedirs(os.path.dirname(_co) or '.', exist_ok=True)
                    with open(_co, 'w') as _f:
                        _f.write(_ddcard.render_card_html(_cm, standalone=True))
                    logger.info(f"  Dive card written to {card_out_path}")
                except OSError as _e:  # noqa: BLE001
                    logger.warning(f"  dive card: could not write "
                                   f"{card_out_path}: {_e}")
        return r_html, an_html, card_section, a_css, sink

    # Snapshot a CLEAN L51 data_obj + score arrays BEFORE the level-default
    # pass mutates data_obj (tier renames, pasteTiers, _cardCtx). Done here so
    # the L51 prose runs on the original tiers, not the renamed ones.
    import copy as _copy
    _dobj51 = _sarr51 = None
    if _bb_active:
        _dobj51 = _copy.deepcopy(data_obj)
        _dobj51.update(_dobj51.pop('ivL51'))   # override level-dependent arrays
        _dobj51.pop('bestBuddy', None)
        _sarr51 = {f'{mi}_{mode}': md['scores_l51'][mode]
                   for mi, md in enumerate(moveset_data)
                   if md.get('scores_l51')
                   for mode in opp_iv_modes if mode in md['scores_l51']}

    # ---- Level-default pass: drives the embedded DATA + scatter ----
    results_html, analysis_html, _card50_html, analysis_css, _sink50 = \
        _render_level_body(
            data_obj, score_arrays, write_card_out=True, robust_max_level=None,
            base_scores=scores_base_arrays, base_info=base_form_info)
    # (anchorFlipSets was set on data_obj inside the helper, matching the
    # historical key order in the embedded DATA blob.)
    # Inject analysis CSS into the style block (replace closing tag we already emitted)
    html = html.replace('</style>\n</head>', analysis_css + '\n</style>\n</head>', 1)

    # ---- Best-buddy (L51) pass: rendered into <template>s for the toggle ----
    _results51 = _analysis51 = _card51_html = ''
    if _bb_active:
        _results51, _analysis51, _card51_html, _, _ = _render_level_body(
            _dobj51, _sarr51, write_card_out=False,
            robust_max_level=best_buddy.get('alt_cap'),
            base_scores=None, base_info=None)

    # ---- Dive card injection (host + optional L51 template for the toggle) ----
    if _card50_html:
        if _bb_active:
            _card_block = (
                f'<div id="dd-bb-card-host" class="dd-bb-host">{_card50_html}</div>'
                f'<template id="dd-bb-card-tmpl">{_card51_html}</template>')
        else:
            _card_block = _card50_html
        html = html.replace('<!-- DIVE_CARD_SLOT -->', _card_block, 1)
        html = html.replace('</style>\n</head>',
                            _ddcard.CARD_CSS + '\n</style>\n</head>', 1)

    # Drop the marker if no card was injected (card disabled) so no stray
    # comment ships.
    html = html.replace('<!-- DIVE_CARD_SLOT -->', '', 1)

    # Results section is always visible; analysis is behind a toggle. When the
    # best-buddy toggle is active the L50 prose is live and the L51 prose rides
    # in an inert <template> (its element ids don't collide); the JS swaps the
    # host's innerHTML between the two on toggle.
    if _bb_active:
        html += (f'<div id="dd-bb-prose-host" class="dd-bb-host">'
                 f'{results_html}{analysis_html}</div>'
                 f'<template id="dd-bb-prose-tmpl">'
                 f'{_results51}{_analysis51}</template>')
    else:
        html += results_html
        html += analysis_html

    # ---- Section sidenav (mirrors the ML IV-guide pages) ----
    # Candidate nav items in the on-page section order. Each entry is only
    # emitted when its target id is actually present in the assembled body
    # (e.g. #dd-opp-threats / #dd-slayer-builds are absent on some dives),
    # so every href resolves to a real anchor (zero dangling links). The
    # .dd-layout wrapper begins right after the dive card so the
    # infographic stays the first content block; at narrow widths the nav
    # stacks under the card, never above it.
    # (sid, short label for the compact nav, full phrase for the hover title).
    # 'IV Recommendations' -> 'Recs' (not 'IV picks') so only 'IV finder' keeps
    # the 'IV' prefix -- no two-row scan collision.
    _nav_candidates = [
        ('dd-scatter', 'Scatter', 'Scatter &amp; controls'),
        ('dd-recommendations', 'Recs', 'IV Recommendations'),
        ('dd-opp-threats', 'Threats', 'Threats where your build matters'),
        ('dd-notable-ivs', 'IV finder', 'Per-matchup IV finder'),
        ('dd-stat-thresholds', 'Thresholds', 'Key Matchup Thresholds'),
        ('dd-slayer-builds', 'Mirror / Slayer', 'Mirror / Slayer builds'),
    ]
    _nav_links = ''.join(
        f'<a href="#{sid}" title="{full}">{label}</a>\n'
        for sid, label, full in _nav_candidates
        if f'id="{sid}"' in html
    )
    _nav_html = (f'<nav class="dd-toc"><strong>On this page</strong>\n'
                 f'{_nav_links}{_bb_nav_ctrl}</nav>\n')
    # Open the flex layout right after the card (DD_LAYOUT_OPEN marker) and
    # close it just before the embedded-data script below.
    html = html.replace('<!-- DD_LAYOUT_OPEN -->',
                        f'<div class="dd-layout">\n{_nav_html}'
                        '<main class="dd-main">', 1)
    html += '</main>\n</div>\n'

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
        # mtime=0: the gzip header embeds a timestamp by default, which
        # made byte-identical data produce different HTML run-to-run
        # (caught by replay-vs-original diffing, arc S4).
        gz = gzip.compress(raw, compresslevel=9, mtime=0)
        packed_scores[key] = base64.b64encode(gz).decode('ascii')
    # Energy grid: same uint16/gzip/base64 pipeline as scores, keyed identically
    # (incl. @51). Empty unless --compare-energy populated energy_arrays, in
    # which case ZERO new bytes are emitted below (byte-identical when off).
    packed_energy = {}
    for key, arr in energy_arrays.items():
        clamped = [max(0, min(65535, int(v))) for v in arr]
        raw = struct.pack(f'<{len(clamped)}H', *clamped)
        gz = gzip.compress(raw, compresslevel=9, mtime=0)
        packed_energy[key] = base64.b64encode(gz).decode('ascii')
    # Dedup'd tooltip table: renderers register tooltip text as they
    # emit data-t="<sid>" attrs; we dump {sid: text} here and a
    # DOMContentLoaded pass (below) populates el.title from the
    # lookup. Saves ~18 MB on an Oinkologne-shape dive by collapsing
    # 87k repeated title= values to 1.6k unique strings.
    data_obj['tooltips'] = rendering.dump_tooltip_registry()
    html += f'<script>var DATA = {json.dumps(data_obj)};\n'
    html += f'var SCORES_GZ = {json.dumps(packed_scores)};\n'
    if packed_energy:
        html += f'var ENERGY_GZ = {json.dumps(packed_energy)};\n'
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
"""
    # Parallel ENERGY decoder -- emitted ONLY when --compare-energy embedded a
    # grid (keeps an energy-off dive byte-identical: no var, no decoder).
    if packed_energy:
        html += """
var ENERGY = {};
var _energyReady = (async function() {
  for (var key in ENERGY_GZ) {
    var bin = Uint8Array.from(atob(ENERGY_GZ[key]), function(c) { return c.charCodeAt(0); });
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
    ENERGY[key] = Array.from(new Uint16Array(merged.buffer));
  }
})();
// Re-render the compare widget once energy is decoded, so the margin panel
// picks up the "+N energy" detail even if candidates were added during decode.
_energyReady.then(function() { if (window.cmpRender) window.cmpRender(); });
"""
    html += """
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

    # Shared compare-panel functions (cmpVal/cmpHp/cmpScenLabel/cmpFlipPanel/
    # cmpMarginPanel). Injected as a plain <script> BEFORE the engine so its
    # globals exist when the compare widget renders; the ML IV-guide pages load
    # the same file, keeping the panels single-sourced. If the file is missing
    # the engine falls back gracefully only insofar as the compare widget errors
    # on use -- but it is committed alongside the engine, so this is belt-and-braces.
    _cmp_js_path = os.path.join(os.path.dirname(__file__), 'cmp_panels.js')
    try:
        with open(_cmp_js_path) as _cmpf:
            html += '<script>\n' + _cmpf.read() + '\n</script>\n'
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
    html += ('<p style="margin-top:30px;color:var(--text-muted);font-size:12px">'
             'New here? The <a href="../guides/">Reader\'s Guide</a> '
             'explains tier cards, envelope shapes, and the IV flavor '
             'guide in plain language.</p>\n')

    # About / Credits section
    # Always-visible PvPoke attribution (the collapsible credits below
    # add detail, but the core credit must show without a click).
    html += ('<p style="margin-top:30px;border-top:1px solid var(--border);'
             'padding-top:12px;font-size:0.85rem;color:var(--text-muted);'
             'line-height:1.6">' + PVPOKE_ATTRIBUTION_HTML + '</p>\n')
    html += ('<p style="margin-top:6px;font-size:0.78rem;color:var(--text-muted)">'
             + GRUVBOX_CREDIT_HTML + '</p>\n')
    html += '<details class="meta" style="margin-top:10px;border-top:1px solid var(--border);padding-top:10px">'
    html += '<summary>About &amp; Credits</summary>'
    html += '<div style="margin:8px 0;font-size:0.85rem;color:var(--text-muted);line-height:1.6">'
    html += '<p><b>PoGo PvP IV Deep Dive</b> - a stat-threshold analysis tool '
    html += 'for Pokemon GO PvP IVs.</p>'
    html += '<p><b>Data &amp; Simulation Reference</b></p>'
    html += '<ul style="margin:4px 0 8px 20px">'
    html += '<li><b>PvPoke</b> (pvpoke.com) - this project is built on PvPoke. '
    html += "Our battle simulator is a Python port of PvPoke's open-source battle "
    html += 'logic, and all game data (gamemaster.json, move stats, type chart, '
    html += 'and meta rankings) comes from PvPoke. PvPoke is by Empoleon_Dynamite '
    html += 'and is MIT-licensed: github.com/pvpoke/pvpoke. This project would not '
    html += 'exist without it.</li>'
    html += '<li><b>RyanSwag</b> - mirror slayer IV framework '
    html += '(the inspiration for the slayer-archetype analysis).</li>'
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
        html += '<details class="meta" style="margin-top:30px;border-top:1px solid var(--border);padding-top:10px">'
        html += '<summary>Run parameters (CLI invocation)</summary>'
        html += '<pre style="margin:8px 0;background:var(--surface);'
        html += 'padding:10px;border-radius:4px;color:var(--text);font-size:12px;'
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
            html += '<pre style="margin:8px 0;background:var(--surface);'
            html += 'padding:10px;border-radius:4px;color:var(--text);font-size:12px;'
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

    # Sitewide support / credits footer. A dive lives at <dive>/index.html, one
    # level below the website root, so support.html resolves at ../support.html.
    html += support_footer_html('../')

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
    f-string brace escaping). Nine placeholders inside that file get
    replaced at runtime with the per-dive values below.
    """
    # __TIER_COLORS_JS__ feeds Plotly markers, which can't read CSS vars; resolve
    # each 'var(--tier-N)' to its DEFAULT_THEME hex here (the single injection
    # boundary). t['color'] itself stays 'var(--tier-N)' for the theme-aware
    # badges. Non-var literals (e.g. the mirror-tier hex) pass through unchanged.
    # Guard the injection boundary: every tier color must resolve, either via
    # _TIER_VAR_TO_HEX or as a literal '#hex'. An unmapped tier color would
    # silently leak a raw 'var(...)' string into the Plotly hex array; fail
    # LOUD instead.
    for t in tier_info:
        _c = t['color']
        if _c not in _TIER_VAR_TO_HEX and not (
                isinstance(_c, str) and _c.startswith('#')):
            raise ValueError(
                f"Tier {t['name']!r} color {_c!r} does not resolve: not in "
                f"_TIER_VAR_TO_HEX and not a literal '#hex'. An unmapped tier "
                f"color would leak a raw var string into the Plotly hex array "
                f"(__TIER_COLORS_JS__).")
    tier_colors_js = json.dumps(
        [_TIER_VAR_TO_HEX.get(t['color'], t['color']) for t in tier_info])
    # __TIER_VARS_JS__ feeds the theme-aware summary-table tier badges: the RAW
    # 'var(--tier-N)' strings, in the SAME order over the SAME tier_info as
    # __TIER_COLORS_JS__. The badge reads tierVars[i] (theme-aware) which thus
    # parallels the Plotly marker's tierColors[i] (resolved hex) for every tier
    # -- including the mirror tier -- with no index reconstruction.
    tier_vars_js = json.dumps([t['color'] for t in tier_info])
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
        '__TIER_VARS_JS__': tier_vars_js,
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


# ---------------------------------------------------------------------------
# Replay-from-saved-state (arc S4)
# ---------------------------------------------------------------------------
# The HTML render tail is factored out of main() and driven by a plain
# state dict so the exact same code path serves two callers: the live
# dive (which dumps the state right after sims complete) and
# scripts/replay_analysis.py (which loads the dump and re-renders after
# renderer/analysis code changes, without re-simming).

def dump_replay_state(state, path=None):
    """Pickle+gzip the render-input state; return the path (or None).

    Best-effort: a dump failure must never kill a completed dive, so
    errors degrade to a warning. Default path is under userdata/replay/
    (gitignored, never published by publish_website.sh).
    """
    import gzip
    import pickle
    from datetime import datetime
    try:
        # The variant registry is process-local state populated by pool
        # loading in main(); a replay process never runs that, so without
        # it parse_opponent_spec mis-reads variant display names
        # ('Forretress (Bug Bite)') and their opp-info entries silently
        # vanish from the replayed render (review finding D4).
        state = {**state,
                 'opponent_variant_registry': dict(_OPPONENT_VARIANT_REGISTRY)}
        if path is None:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            slug = (state['species'].replace(' ', '_')
                    .replace('(', '').replace(')', ''))
            shadow_tag = '_shadow' if state.get('shadow') else ''
            path = os.path.join(
                'userdata', 'replay',
                f"{ts}_{slug}_{state['league']}{shadow_tag}.replay.pkl.gz")
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with gzip.open(path, 'wb', compresslevel=4) as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
        return path
    except Exception as e:
        logger.warning(f"replay state dump failed ({e}); dive output is "
                       f"unaffected, but this run can't be replayed")
        return None


def load_replay_state(path):
    """Load a replay state blob written by dump_replay_state.

    Restores the process-local opponent-variant registry from the blob
    so the replayed render resolves variant display names exactly like
    the live dive did. Blobs from before 2026-06-11 carry no registry;
    they load fine, and a variant opponent then logs the opp_info_cache
    warning instead of silently disappearing.
    """
    import gzip
    import pickle
    with gzip.open(path, 'rb') as f:
        state = pickle.load(f)
    # Transport bookkeeping, not render state: restore the global and
    # remove the key so the returned dict matches what the caller dumped.
    reg = state.pop('opponent_variant_registry', None)
    if reg:
        _OPPONENT_VARIANT_REGISTRY.clear()
        _OPPONENT_VARIANT_REGISTRY.update(reg)
    return state


def render_dive_html(state):
    """Render the interactive HTML output (split or single) from a
    replayable state dict. Keys mirror generate_interactive_html's
    kwargs plus the few main()/CLI fields the tail needs."""
    moveset_data = state['moveset_data']
    reference_idx = state['reference_idx']
    if state['split_movesets'] and len(moveset_data) > 1:
        # Per-moveset split: emit N files, one per moveset. The
        # filesystem plan is computed up-front so every file
        # knows every sibling's URL for its navigation dropdown.
        split_files = _build_split_file_list(
            moveset_data, reference_idx, state['html_path'],
        )
        logger.info(f"  Split mode: emitting {len(split_files)} per-moveset HTML files")
        # Each file computes its own analysis sections: the
        # filtered moveset_data puts THIS file's moveset at index
        # 0, so the anchor aggregator + boundary sweeps genuinely
        # differ per file. (A cross-file analysis cache lived here
        # 2026-04-12..06-10 on the wrong premise that the results
        # were identical — every non-landing split file shipped
        # moveset-0's analysis. If split render time ever hurts,
        # re-optimize INSIDE generate_analysis_sections with
        # moveset-keyed caching, never by sharing rendered HTML
        # across files.)
        for finfo in split_files:
            mi = finfo['moveset_idx']
            filtered_md, filtered_ref_idx = _filter_moveset_data_for_split(
                moveset_data, mi, reference_idx,
            )
            split_info = {'files': split_files, 'current': mi}
            generate_interactive_html(
                state['species'], state['league'], filtered_md, finfo['path'],
                thresholds=state['thresholds'],
                opponent_label=state['opponent_label'],
                shield_scenarios=state['shield_scenarios'],
                opponent_names=state['opponent_names'],
                opp_iv_modes=state['opp_iv_modes'],
                reference_idx=filtered_ref_idx,
                standalone=state['standalone'],
                slayer_iter_result=state['slayer_iter_result'],
                cli_args_str=state['cli_args_str'],
                has_toml_tiers=state['has_toml_tiers'],
                shadow=state['shadow'],
                split_info=split_info,
                article_slug=state['article_slug'],
                threshold_registry=state['threshold_registry'],
                species_narrative=state['species_narrative'],
                shared_plotly_dir=state['shared_plotly_dir'],
                card_out_path=state.get('card_path'),
                card_robust_k=state.get('card_robust_k', DEFAULT_CARD_ROBUST_K),
                opp_movesets=state.get('opp_movesets'),
                mechanics=state.get('mechanics', 'legacy'),
                best_buddy=state.get('best_buddy'),
                slayer_iter_result_l51=state.get('slayer_iter_result_l51'),
            )
        _remove_stale_split_siblings(
            state['html_path'], [f['path'] for f in split_files])
    else:
        if state['split_movesets']:
            logger.warning("--split-movesets: only one moveset surviving - "
                           "writing a single file")
        _remove_stale_split_siblings(state['html_path'], [])
        generate_interactive_html(
            state['species'], state['league'], moveset_data, state['html_path'],
            thresholds=state['thresholds'],
            opponent_label=state['opponent_label'],
            shield_scenarios=state['shield_scenarios'],
            opponent_names=state['opponent_names'],
            opp_iv_modes=state['opp_iv_modes'],
            reference_idx=reference_idx,
            standalone=state['standalone'],
            slayer_iter_result=state['slayer_iter_result'],
            cli_args_str=state['cli_args_str'],
            has_toml_tiers=state['has_toml_tiers'],
            shadow=state['shadow'],
            article_slug=state['article_slug'],
            threshold_registry=state['threshold_registry'],
            species_narrative=state['species_narrative'],
            shared_plotly_dir=state['shared_plotly_dir'],
            card_out_path=state.get('card_path'),
            card_robust_k=state.get('card_robust_k', DEFAULT_CARD_ROBUST_K),
            opp_movesets=state.get('opp_movesets'),
            mechanics=state.get('mechanics', 'legacy'),
            best_buddy=state.get('best_buddy'),
            slayer_iter_result_l51=state.get('slayer_iter_result_l51'),
        )


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
    parser.add_argument('--max-level', type=float, default=None, metavar='LVL',
                        help='Override the league max level for BOTH focal and '
                        'opponents (e.g. 50 for "regular" vs the default 51 '
                        'best-buddy in Master, where the CP cap never binds). '
                        'Default: the league default in LEAGUE_MAX_LEVEL.')
    parser.add_argument('--best-buddy', choices=['auto', 'on', 'off'],
                        default='auto',
                        help='Compute a second focal sweep one level higher '
                        '(best-buddy = +1 level) so the dive can toggle between '
                        'the league-default level and best-buddy L51. '
                        '"auto" (default) computes it for Ultra; Great is '
                        'opt-in via "on"; Master/Little already cap at 51 so '
                        'the toggle is a no-op there. Suppressed automatically '
                        'when no IV can actually climb a level.')
    parser.add_argument('--best-buddy-display', type=int, choices=[50, 51],
                        default=None,
                        help='Which level the dive opens on when the best-buddy '
                        'toggle is active (default: the league-default level, '
                        'i.e. 50 for Great/Ultra).')
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
                             '"Tinkaton" or "Altaria (Shadow)". Per-line '
                             'moveset overrides are also supported via '
                             '`Forretress | fast=BUG_BITE` syntax — see '
                             '_parse_opponent_pool_line. Movesets without '
                             'overrides are resolved via PvPoke default.')
    parser.add_argument('--no-active-variants', action='store_true',
                        help='Skip the opponent_pools/active_variants.toml '
                             'auto-merge. Default behavior reads that file '
                             '(if present) and appends each variant whose '
                             'base species is already in the loaded opponent '
                             'pool, so e.g. Forretress (Bug Bite) appears '
                             'alongside the default Forretress without '
                             'editing every dive\'s pool file. Use this flag '
                             'to reproduce a clean baseline pool.')
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
    parser.add_argument('--card-out', default=None, metavar='PATH',
                        help='Also write a self-contained, screenshot-able '
                             '"dive card" (compact spec sheet) to PATH. '
                             'Triggers the opponent-IV robustness headline '
                             '(a short extra sim over the curated pool).')
    parser.add_argument('--card-robust-k', type=int, default=DEFAULT_CARD_ROBUST_K, metavar='N',
                        help='Opponent-IV cohort size for the card robustness '
                             'headline: each opponent is swept across its top-N '
                             'stat-product IVs across ALL shield scenarios '
                             '(default 512, the ship value). Lower it (e.g. 32) '
                             'for fast smoke iterations -- it samples fewer '
                             'opponent IVs without dropping any shield scenario.')
    parser.add_argument('--interactive', action='store_true',
                        help='Generate interactive HTML with dropdowns for moveset, '
                             'shield scenario, and opp IV mode switching. '
                             'Runs all shield scenarios and reference moveset. '
                             'Implied by --html (the former static HTML mode '
                             'was removed 2026-06-12).')
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
                             '(Nash-style mirror match iteration). Produces the '
                             'mirror opponent population behind the Slayer Builds '
                             'archetypes (Anchors-First / CMP-First) and the mirror '
                             'CMP/wins columns. Results are cached on disk for fast '
                             're-runs. ENABLED by default; pass --no-mirror-slayer '
                             'to skip.')
    parser.add_argument('--mirror-slayer-metric', default='all',
                        choices=['all', 'even', 'even-strict'],
                        help='Slayer iteration metric (graded: per-opponent credit '
                             'is fractional, with avg-score tiebreak): "all" credits '
                             'scenarios won / 9 (default), "even" only 0v0/1v1/2v2, '
                             '"even-strict" full credit only when ALL 3 even '
                             'scenarios are won.')
    parser.add_argument('--mirror-slayer-rounds', type=int, default=4,
                        help='Max rounds for mirror slayer iteration (default 4). '
                             'Set to 1 for "beat the typical opponent" mode (no '
                             'Nash iteration).')
    parser.add_argument('--mirror-slayer-pool', type=int, default=30,
                        help='Number of survivors to keep per iteration round '
                             '(default 30). Honored exactly except on exact '
                             'metric ties. Larger = broader mirror population '
                             'for the CMP/wins columns.')
    parser.add_argument('--mirror-slayer-show', type=int, default=20,
                        help='Number of IVs in the CMP-First Slayer archetype '
                             'and shown per category in console output '
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
    parser.add_argument('--energy-lead', default='off',
                        choices=['off', 'on'],
                        help="Energy-lead sim axis (safe-switch / closer "
                             "carry-over): 'on' additionally sweeps the "
                             "focal with 1 and 2 fast moves of stored "
                             "energy (capped at the reachable bound for "
                             "the moveset), adds an Energy lead selector "
                             "to the interactive HTML, and annotates "
                             "energy-gated matchup flips. Opponent always "
                             "starts at 0. Triples compute time. "
                             "Interactive mode only. Default: off.")
    parser.add_argument('--compare-energy', action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Capture the focal's POST-MATCH energy per matchup "
                             "and embed it (parallel to scores) so the 'Compare "
                             "my candidates' widget shows the banked-energy line "
                             "('+N energy', ~N charged moves). Default: ON. "
                             "NOTE: it bypasses the sweep disk cache (the cache "
                             "holds only scores), so a re-run pays full sim time "
                             "instead of cache hits; adds ~4%% to the HTML. Pass "
                             "--no-compare-energy to drop it (smaller, cacheable).")
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
    parser.add_argument('--no-signature-dedup', action='store_true',
                        help='Disable per-opponent damage-signature dedup in '
                             'the IV sweep (sim every stat profile vs every '
                             'opponent). The dedup is provably exact; this '
                             'flag exists for verification runs '
                             '(scripts/verify_signature_dedup.py) and debugging.')
    parser.add_argument('--no-sweep-cache', action='store_true',
                        help='Disable the per-opponent-column sweep disk '
                             'cache (~/.cache/gopvpsim/sweep/). The key '
                             'includes engine source + gamemaster hashes, '
                             'so hits are bit-identical; this flag forces '
                             'a fresh sim for timing runs and debugging.')
    parser.add_argument('--no-replay-dump', action='store_true',
                        help='Skip writing the replay state blob '
                             '(userdata/replay/) that lets '
                             'scripts/replay_analysis.py re-render this '
                             'dive\'s HTML without re-simming.')
    parser.add_argument('--mechanics', choices=['legacy', 'new'], default='legacy',
                        help='Turn-resolution model. legacy (default) = the '
                             'pre-2026-06-23 system used for all published '
                             'dives. new = the 2026-06-23 PvP turn system '
                             '(EXPERIMENTAL / UNVALIDATED: PvPoke has not '
                             'implemented it, so there is no reference to '
                             'cross-check against, and the sweep disk cache '
                             'is disabled for it).')

    args = parser.parse_args()

    if args.mechanics == 'new':
        logger.warning(
            'mechanics=new is EXPERIMENTAL / UNVALIDATED -- it models the '
            '2026-06-23 PvP turn system, which PvPoke has not implemented. '
            'There is no reference to cross-check against; treat the output '
            'as experimental.')

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
    if args.card_out:
        _card_parent = os.path.dirname(os.path.abspath(args.card_out))
        if _card_parent:
            try:
                os.makedirs(_card_parent, exist_ok=True)
            except OSError as _e:
                parser.error(
                    f'Cannot create --card-out directory '
                    f'{_card_parent!r}: {_e}'
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

    # --max-level: override the league's max build level for BOTH focal and
    # opponents. Every mon-build site (compute_iv_metadata's focal grid,
    # iv_sweep's opp_cache, generate_analysis_sections' opp rebuild, the
    # collection rank lookup, and the library's own at_best_level/iv_rank
    # defaults) reads LEAGUE_MAX_LEVEL.get(league, ...), and they ALL run in
    # the main process during setup/render -- workers only consume the
    # precomputed stat dicts. So mutating the entry once here, before any
    # build, cleanly threads the override through all of them. Only meaningful
    # where the CP cap doesn't bind (Master), so the level is what sets stats.
    if args.max_level is not None:
        if args.max_level not in CPM:
            parser.error(
                f'--max-level {args.max_level} is not a valid level (must be a '
                f'half-level in [1.0, 51.0], e.g. 50 or 51)')
        LEAGUE_MAX_LEVEL[args.league] = args.max_level

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
        # Copy-paste monitor recipes for a second terminal (Michael's
        # standing ask on every dive kick).
        logger.info("Monitor: watch -c -n 5 scripts/chain_status.py "
                    "--chain single   (or: tail -f userdata/logs/latest.log)")

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

    # Static (non-interactive) HTML mode was deleted in the 2026-06-12 S7
    # cleanup — it had been broken (NameError) since well before, with
    # nobody noticing. --html now implies --interactive.
    if args.html and not args.interactive:
        logger.info("  --html implies --interactive (static HTML mode "
                    "was removed)")
        args.interactive = True

    # Interactive mode always renders all 9 scenarios, so expand BEFORE any
    # simulation — Phase 2, threshold auto-discovery, the mirror-slayer
    # iteration, and the slayer archetypes must all see the same scenario
    # set the page displays. (Until 2026-06-11 the expansion happened after
    # Phase 2, so the slayer iteration and archetype tables were computed
    # on the 1v1 scenario only, and the graded round metric degenerated to
    # 0/1 — the tie-explosion fix's pool cap was blown ~40x.)
    if args.interactive and shield_scenarios == [(1, 1)]:
        logger.info("  Interactive mode: expanding to all 9 shield scenarios")
        shield_scenarios = ALL_NINE

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
    # Species key for all registry / raw-TOML lookups. A shadow focal's
    # tables are keyed "<Species> (Shadow)", so it never matches (and never
    # inherits) the non-shadow base species' tiers, narrative, or anchors.
    _thr_species = args.species + (' (Shadow)' if args.shadow else '')
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
            _sp = _raw_toml.get(_thr_species, {})
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
        if args.shadow:
            _species_lower += '_shadow'
        _narr_toml = Path(__file__).resolve().parent.parent / 'thresholds' / f'{_species_lower}.toml'
        if _narr_toml.exists():
            try:
                import tomllib as _tomllib
                with open(_narr_toml, 'rb') as _f:
                    _raw_toml = _tomllib.load(_f)
                _sp = _raw_toml.get(_thr_species, {})
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
        # so the user doesn't have to remember --thresholds every run. A
        # shadow focal discovers thresholds/<species>_shadow.toml instead,
        # whose tables are keyed "<Species> (Shadow)" - so it never inherits
        # the non-shadow base species' (gobattlekit-default) expert tiers.
        _species_lower = args.species.lower().replace(' ', '_').replace('(', '').replace(')', '')
        if args.shadow:
            _species_lower += '_shadow'
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
                _article_table = _raw_toml.get(_thr_species, {}).get('article', {})
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
                _sp = _raw_toml.get(_thr_species, {})
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
            _cd_prep = _raw_toml.get(_thr_species, {}).get('cd_prep', {})
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
            threshold_registry, _thr_species, args.league.capitalize(),
        ) or None
        if thresholds:
            _toml_tiers_loaded = True
        n_spreads = len(thresholds) if thresholds else 0
        n_anchors = 0
        sp = threshold_registry.species(_thr_species)
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
    if args.group:
        group_entries = load_group(args.group)
        focal_in_opponents = False
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
        # Read a custom opponent list from a text file. One opponent per
        # non-blank, non-comment line. See `_parse_opponent_pool_line` for
        # the per-line format (bare speciesName, or pipe-delimited overrides
        # like 'Forretress | fast=BUG_BITE'). Focal species appended for
        # mirror analysis if not already present.
        path = args.opponents_file
        opponents = []
        opp_movesets_full = []
        n_variants = 0
        with open(path) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith('#'):
                    continue
                try:
                    display, base, is_shadow, fast_ov, charged_ov = (
                        _parse_opponent_pool_line(line))
                except ValueError as _e:
                    logger.warning(f"skipping malformed pool line: {_e}")
                    continue

                # Resolve missing pieces from the PvPoke default moveset.
                if fast_ov is None or charged_ov is None:
                    try:
                        d_fast, d_charged = get_default_moveset(
                            base, league=args.league, shadow=is_shadow)
                    except (KeyError, ValueError) as _e:
                        logger.warning(f"skipping {display}: {_e}")
                        continue
                else:
                    d_fast, d_charged = None, None
                fast_id = fast_ov if fast_ov is not None else d_fast
                charged_ids = (
                    list(charged_ov) if charged_ov is not None else list(d_charged))

                opponents.append(display)
                opp_movesets_full.append((fast_id, charged_ids))
                if fast_ov is not None or charged_ov is not None:
                    register_opponent_variant(display, base, is_shadow)
                    n_variants += 1

        # The mirror entry must match the focal's FORM: a shadow focal's
        # mirror is '<species> (Shadow)' (shadow stats + shadow-rankings
        # moveset). Appending the plain name would sim a chimera mirror
        # (shadow moveset on non-shadow stats).
        _mirror_name = args.species + (' (Shadow)' if args.shadow else '')
        if _mirror_name not in opponents:
            try:
                focal_fast, focal_charged = get_default_moveset(
                    args.species, league=args.league, shadow=args.shadow)
            except (KeyError, ValueError) as _e:
                # Unranked focal (e.g. a pre-release shadow): no rankings
                # default for the self-mirror. Fall back to the focal's
                # EXPLICIT moveset so the mirror still sims (constructed stats
                # + focal moveset) instead of being silently dropped. The
                # mirror's IVs resolve fine -- resolve_opp_ivs uses the ranked
                # BASE species, only the shadow-form moveset lookup fails.
                if args.fast and args.charged:
                    focal_fast = args.fast
                    focal_charged = [c.strip() for c in args.charged.split(',')]
                    logger.info(f"  (mirror {_mirror_name}: no rankings default, "
                                f"using explicit focal moveset)")
                else:
                    focal_fast = None
                    logger.warning(f"could not append focal species for mirror: {_e}")
            if focal_fast is not None:
                opponents.append(_mirror_name)
                opp_movesets_full.append((focal_fast, focal_charged))
                logger.info(f"  (added {_mirror_name} to opponents for mirror analysis)")
        opponent_label = (f"Custom pool from {os.path.basename(path)} "
                          f"({len(opponents)} mons)")
        if n_variants:
            opponent_label += f", incl. {n_variants} moveset variant(s)"
        logger.info(f"  {len(opponents)} opponents from {path}"
                    + (f" (+{n_variants} moveset variant(s))"
                       if n_variants else ""))
    else:
        opponents = get_top_opponents(args.league, args.opponents)
        # Always include focal species for mirror analysis (append if not in
        # top N). Form-matched: a shadow focal's mirror is the shadow entry.
        _mirror_name = args.species + (' (Shadow)' if args.shadow else '')
        if _mirror_name not in opponents:
            opponents.append(_mirror_name)
            logger.info(f"  (added {_mirror_name} to opponents for mirror analysis)")
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
        _sp_for_opps = threshold_registry.species(_thr_species)
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

    # Apply project-wide alt-moveset opponent variants from
    # opponent_pools/active_variants.toml (e.g. Forretress (Bug Bite) so
    # every dive sees both fast-move forms without per-pool edits). Skipped
    # via --no-active-variants for clean-baseline reproductions.
    _active_added = _apply_active_variants(
        opponents, opp_movesets_full, args.league,
        skip=args.no_active_variants,
    )
    if _active_added:
        logger.info(f"  (added {len(_active_added)} active alt-moveset "
                    f"variant(s) from active_variants.toml: "
                    f"{', '.join(_active_added)})")

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
    # Resolve the reference (meta) moveset up front so the screen can prefer it
    # for the landing slot on a near-tie. Deterministic lookup, no sim.
    _ref_for_screen = resolve_reference_moveset(
        args.species, args.league, args.shadow, args.reference)
    surviving = screen_movesets(
        args.species, movesets, args.league, args.shadow,
        screen_opponents, screen_opp_movesets, shield_scenarios,
        args.top_movesets, opp_iv_mode=opp_iv_mode,
        threshold_registry=threshold_registry,
        mechanics=args.mechanics,
        reference_moveset=_ref_for_screen,
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

        results, n_sims, canonical_scores, canonical_meta, canonical_energy = iv_sweep(
            args.species, fast_id, charged_ids, args.league, args.shadow,
            opponents, opp_movesets_full, shield_scenarios,
            opp_iv_mode=opp_iv_mode,
            iv_floor=args.iv_floor,
            log_path=log_path, verbose=args.verbose,
            threshold_registry=threshold_registry,
            reserve_cpus=args.reserve_cpus,
            signature_dedup=not args.no_signature_dedup,
            use_sweep_cache=not args.no_sweep_cache,
            mechanics=args.mechanics,
            capture_energy=args.compare_energy,
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
            # Prefer the form-matched mirror entry (shadow focal -> shadow
            # opponent); fall back to a form-stripped match so a plain
            # focal still finds a shadow-only pool entry.
            _mirror_name = args.species + (' (Shadow)' if args.shadow else '')
            mirror_idx = None
            for oi, opp_name in enumerate(opponents):
                if opp_name == _mirror_name:
                    mirror_idx = oi
                    break
            if mirror_idx is None:
                for oi, opp_name in enumerate(opponents):
                    if opp_name.replace(' (Shadow)', '') == args.species:
                        mirror_idx = oi
                        break
            if mirror_idx is not None:
                slayer_thresh, slayer_scored = discover_slayer_thresholds(
                    results, mirror_idx, len(shield_scenarios)
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
                iv_floor=args.iv_floor,
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

                # Resolve anchors so build_slayer_archetypes can tag each IV
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
                            sp_explicit = threshold_registry.species(_thr_species)
                            if sp_explicit is not None:
                                lt_explicit = sp_explicit.leagues.get(
                                    args.league.capitalize()
                                )
                                if lt_explicit is not None:
                                    for a in lt_explicit.anchors.values():
                                        existing_kinds.add(a.kind)

                        survivor_iv_tuples = [r['iv'] for r in survivors]
                        auto_overlay = build_auto_anchors(
                            species=_thr_species,
                            league=args.league,
                            opponent_species=list(opponents),
                            fast_move_id=fast_id,
                            survivor_ivs=survivor_iv_tuples,
                            existing_anchor_kinds=existing_kinds,
                            shadow=args.shadow,
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
                        sp_auto = auto_overlay.species(_thr_species)
                        if sp_auto is not None:
                            lt_auto = sp_auto.leagues.get(
                                args.league.capitalize()
                            )
                            if lt_auto is not None:
                                n_auto_anchors = len(lt_auto.anchors)

                        resolved = resolve_anchors(
                            effective_registry, _thr_species, args.league,
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

                categories = build_slayer_archetypes(
                    results, resolved_anchors=resolved,
                    iter_result=slayer_iter_result,
                    cmp_first_n=args.mirror_slayer_show,
                )
                # Build cross-category map (IV -> set of category names)
                iv_categories = {}
                for cn, civs in categories.items():
                    for r in civs:
                        iv_categories.setdefault(r['iv'], set()).add(cn)
                CAT_AB = {'Anchors-First Slayer': 'AF', 'CMP-First Slayer': 'CF'}
                logger.info(f"    IV space classified into "
                            f"{sum(1 for v in categories.values() if v)} "
                            f"archetypes: "
                            + ', '.join(f"{cn} ({len(civs)})"
                                        for cn, civs in categories.items()
                                        if civs))
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
                        tag_bits = []
                        for parent, subs in sorted(r.get('_anchor_tags', {}).items()):
                            labels = [a.label or a.name for a in subs]
                            tag_bits.append(f"{parent}[{','.join(labels)}]")
                        tag_str = ' ' + ' '.join(tag_bits) if tag_bits else ''
                        cmp_str = (f" cmp {r['top_mirror_cmp']:.0f}%"
                                   if r.get('top_mirror_cmp') is not None else '')
                        logger.debug(f"        {a:2d}/{d:2d}/{s:2d}  "
                                     f"atk={r['atk']:.2f} def={r['def_']:.2f} hp={r['hp']}  "
                                     f"anchors {r['n_parents_cleared']}/"
                                     f"{r['n_counted_parents']}{cmp_str} "
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
                                     canonical_scores, canonical_meta,
                                     canonical_energy))

    # HTML output
    if args.html:
        # Interactive HTML (the only mode since the 2026-06-12 S7
        # cleanup deleted static generate_html).
        # Interactive mode: embed all data, JS-driven dropdowns.
        # Determine composite (opp_iv, bait, energy) modes to run. The
        # axis is 3D: opp-IVs × bait-shields × energy-lead. Composite
        # modes are encoded as a string ('pvpoke', 'pvpoke:nobait',
        # 'rank1:e1', 'rank1:nobait:e2', ...) so score_arrays key
        # format ``f'{mi}_{mode}'`` doesn't need schema changes.
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
        # Energy-lead values are fast-move MULTIPLES (0 = cold start);
        # iv_sweep converts to raw energy per moveset and caps at the
        # reachable bound, so the mode strings stay uniform across
        # movesets with different fast moves.
        _energy_leads = [0, 1, 2] if args.energy_lead == 'on' else [0]
        opp_iv_modes_to_run = [
            compose_mode(om, bm, el)
            for om in _base_opp_modes
            for bm in _bait_modes
            for el in _energy_leads
        ]

        # Scenario expansion for interactive mode happens BEFORE Phase 2
        # (see the parse block after format_cli_args), so Phase 2 already
        # ran with the right scenarios. Repack its results and fill in
        # any additional composite modes (extra opp-IV mode and/or bait
        # mode) that weren't run originally. The cached Phase 2 result
        # corresponds to ``opp_iv_mode`` at bait-on (the Phase 2 default).
        cached_mode = opp_iv_mode  # bait-on, no :nobait suffix
        new_results = []
        for fast_id, charged_ids, results, cs, cm, ce in all_moveset_results:
            scores_by_mode = {cached_mode: cs}
            energy_by_mode = {cached_mode: ce} if ce is not None else None
            for mode in opp_iv_modes_to_run:
                if mode in scores_by_mode:
                    continue
                mode_label = mode_pretty_label(mode)
                logger.info(f"  Running {moveset_label(fast_id, charged_ids)} "
                            f"({mode_label})...")
                t0 = time.time()
                _, n2, cs2, _, ce2 = iv_sweep(
                    args.species, fast_id, charged_ids, args.league, args.shadow,
                    opponents, opp_movesets_full, shield_scenarios,
                    opp_iv_mode=mode,
                    iv_floor=args.iv_floor,
                    log_path=log_path, verbose=args.verbose,
                    threshold_registry=threshold_registry,
                    reserve_cpus=args.reserve_cpus,
                    signature_dedup=not args.no_signature_dedup,
                    use_sweep_cache=not args.no_sweep_cache,
                    mechanics=args.mechanics,
                    capture_energy=args.compare_energy,
                )
                elapsed = time.time() - t0
                logger.info(f"    {n2:,} sims in {elapsed:.1f}s")
                scores_by_mode[mode] = cs2
                if energy_by_mode is not None:
                    energy_by_mode[mode] = ce2
            new_results.append((fast_id, charged_ids, results,
                                scores_by_mode, cm, energy_by_mode))
        all_moveset_results = new_results

        # Resolve and run reference moveset
        reference_idx = -1
        ref_moveset = resolve_reference_moveset(
            args.species, args.league, args.shadow, args.reference)
        if ref_moveset:
            ref_fast, ref_charged = ref_moveset
            ref_label = moveset_label(ref_fast, ref_charged)
            # Check if reference is already a surviving moveset.
            # Compare canonical (fast, sorted-charged) tuples, NOT label
            # strings: screened movesets carry sorted charged pairs but
            # --reference / rankings order is arbitrary, and a label
            # mismatch on the same pair re-sweeps the reference AND
            # emits a duplicate moveset page (2026-06-02 incident,
            # previously patched only by a comment-enforced ordering
            # convention in run_website_dives.py).
            ref_key = (ref_fast, tuple(sorted(ref_charged)))
            for mi, entry in enumerate(all_moveset_results):
                if (entry[0], tuple(sorted(entry[1]))) == ref_key:
                    reference_idx = mi
                    break
            if reference_idx < 0:
                # Run reference sweep
                logger.info(f"  Reference sweep: {ref_label}")
                ref_scores_by_mode = {}
                ref_energy_by_mode = {} if args.compare_energy else None
                ref_meta = None
                for mode in opp_iv_modes_to_run:
                    t0 = time.time()
                    ref_results, ref_n, ref_cs, ref_cm, ref_ce = iv_sweep(
                        args.species, ref_fast, ref_charged, args.league, args.shadow,
                        opponents, opp_movesets_full, shield_scenarios,
                        opp_iv_mode=mode,
                        iv_floor=args.iv_floor,
                        log_path=log_path, verbose=args.verbose,
                        threshold_registry=threshold_registry,
                        reserve_cpus=args.reserve_cpus,
                        signature_dedup=not args.no_signature_dedup,
                        use_sweep_cache=not args.no_sweep_cache,
                        mechanics=args.mechanics,
                        capture_energy=args.compare_energy,
                    )
                    elapsed = time.time() - t0
                    rate = ref_n / elapsed if elapsed > 0 else 0
                    logger.info(f"    {ref_n:,} sims in {elapsed:.1f}s ({rate:,.0f} sims/s)")
                    ref_scores_by_mode[mode] = ref_cs
                    if ref_energy_by_mode is not None:
                        ref_energy_by_mode[mode] = ref_ce
                    if ref_meta is None:
                        ref_meta = ref_cm
                reference_idx = len(all_moveset_results)
                all_moveset_results.append((ref_fast, ref_charged, ref_results,
                                            ref_scores_by_mode, ref_meta,
                                            ref_energy_by_mode))

        # Build moveset_data for interactive HTML
        moveset_data = []
        for entry in all_moveset_results:
            fast_id, charged_ids = entry[0], entry[1]
            scores_by_mode = entry[3]
            meta = entry[4]
            energy_by_mode = entry[5] if len(entry) > 5 else None
            _md = {
                'label': moveset_label_raw(fast_id, charged_ids),
                'scores': scores_by_mode,
                'meta': meta,
            }
            if energy_by_mode is not None:
                # mode -> flat energy list (same shape/order as 'scores'); plus
                # per-move energy so the compare widget can break leftover energy
                # into fast-move-equivalents + fractions of each charged move.
                _fm_db, _cm_db = get_moves()
                _md['energy'] = energy_by_mode
                # Multi-word -> initials (Shadow Sneak -> SS); single word ->
                # first 3 letters (Crunch -> CRU) so it's never a lone letter.
                def _mv_abbr(mid):
                    _w = _pretty_name(mid).split()
                    return (''.join(x[0] for x in _w).upper() if len(_w) > 1
                            else (_w[0][:3].upper() if _w else '?'))
                _md['energy_moves'] = {
                    'fast': {'abbr': _mv_abbr(fast_id),
                             'gain': _fm_db[fast_id].get('energyGain', 0)},
                    'charged': [{'abbr': _mv_abbr(cid), 'cost': _cm_db[cid]['energy']}
                                for cid in charged_ids],
                }
            moveset_data.append(_md)

        # ---- Item 5: base-form sim pass (shadow / Female-sex focals only) ----
        # The dive card's "N newly guaranteed vs base form" line needs a SECOND
        # focal sim at base stats over the SAME opponents + scenarios + modes +
        # 4096 IV grid. The shadow boost (or sibling base stats) reshapes
        # win/loss MEMBERSHIP, so the base census can't be scaled from the
        # shadow set -- it's a real re-sim. Only moveset 0 feeds the card, so
        # we re-sim only that moveset. Opponents are unchanged, so the existing
        # opponent cache / sweep machinery is reused (no opponent re-sim).
        _base_focal = base_form_focal(args.species, args.shadow)
        if _base_focal and moveset_data:
            _base_species, _base_shadow, _base_disp = _base_focal
            _b_fast, _b_charged = all_moveset_results[0][0], all_moveset_results[0][1]
            logger.info(f"  Base-form census pass: {_base_disp} "
                        f"(item 5; reuses opponent cache)")
            _base_scores_by_mode = {}
            for mode in opp_iv_modes_to_run:
                t0 = time.time()
                _, _bn, _bcs, _, _ = iv_sweep(
                    _base_species, _b_fast, _b_charged, args.league, _base_shadow,
                    opponents, opp_movesets_full, shield_scenarios,
                    opp_iv_mode=mode,
                    iv_floor=args.iv_floor,
                    log_path=log_path, verbose=args.verbose,
                    threshold_registry=threshold_registry,
                    reserve_cpus=args.reserve_cpus,
                    signature_dedup=not args.no_signature_dedup,
                    use_sweep_cache=not args.no_sweep_cache,
                    mechanics=args.mechanics,
                )
                logger.info(f"    base {_bn:,} sims in {time.time() - t0:.1f}s "
                            f"({mode_pretty_label(mode)})")
                _base_scores_by_mode[mode] = _bcs
            moveset_data[0]['scores_base'] = _base_scores_by_mode
            moveset_data[0]['base_form'] = {
                'species': _base_species, 'shadow': _base_shadow,
            }

        # ---- Best-buddy / L51 pass: a second focal sweep one level higher ----
        # When best-buddy is enabled and actually changes some IV's level, run
        # the WHOLE sweep again at the alt cap (focal-only -- opponents stay at
        # their league level, so opponent columns are reused). Both grids are
        # carried on moveset_data so the dive can toggle the entire view (card +
        # scatter + prose) between league-default and best-buddy L51. The
        # base-form census pass above is the template (reuses the opponent cache).
        from gopvpsim.pokemon import bestbuddy_caps as _bestbuddy_caps
        _bb_default_cap, _bb_alt_cap = _bestbuddy_caps(args.league)
        # Per-species [Species.best_buddy] TOML override (persists across
        # re-dives, like cd_prep). Resolution precedence (high -> low):
        #   --best-buddy on/off  >  TOML compute  >  league policy (UL on, GL opt-in)
        #   --best-buddy-display >  TOML default_display  >  league default cap
        _bb_toml = _read_best_buddy_toml(args.species, args.shadow)
        if args.best_buddy == 'on':
            _bb_want = True
        elif args.best_buddy == 'off':
            _bb_want = False
        elif _bb_toml.get('compute') is not None:
            _bb_want = bool(_bb_toml['compute'])
        else:  # auto: default-on for Ultra; Great opt-in; Master/Little no-op
            _bb_want = args.league == 'ultra'
        _bb_active = False
        _bb_note = None
        if _bb_want and _bb_alt_cap != _bb_default_cap and moveset_data:
            # Cheap metadata-time no-op check: if no IV's level moves between the
            # two caps, best-buddy changes nothing -- skip the second sweep.
            _md_def = compute_iv_metadata(args.species, args.league,
                                          shadow=args.shadow, iv_floor=args.iv_floor,
                                          focal_max_level=_bb_default_cap)
            _md_alt = compute_iv_metadata(args.species, args.league,
                                          shadow=args.shadow, iv_floor=args.iv_floor,
                                          focal_max_level=_bb_alt_cap)
            _bb_active = any(a['level'] != b['level']
                             for a, b in zip(_md_def, _md_alt))
            if not _bb_active:
                _bb_note = (
                    f"Best-buddy doesn't change any spread for "
                    f"{pretty_species(args.species)} in {args.league.title()} "
                    f"League -- every IV is already CP-capped below level "
                    f"{_bb_alt_cap:g}.")
        if _bb_active:
            logger.info(f"  Best-buddy pass: focal at L{_bb_alt_cap:g} "
                        f"(everything-toggles; reuses opponent cache)")
            for mi, md in enumerate(moveset_data):
                _bb_f, _bb_c = all_moveset_results[mi][0], all_moveset_results[mi][1]
                _bb_scores = {}
                _bb_energy = {} if args.compare_energy else None
                _bb_meta = None
                for mode in opp_iv_modes_to_run:
                    t0 = time.time()
                    _br, _bn51, _bcs51, _bcm51, _bce51 = iv_sweep(
                        args.species, _bb_f, _bb_c, args.league, args.shadow,
                        opponents, opp_movesets_full, shield_scenarios,
                        opp_iv_mode=mode,
                        iv_floor=args.iv_floor,
                        log_path=log_path, verbose=args.verbose,
                        threshold_registry=threshold_registry,
                        reserve_cpus=args.reserve_cpus,
                        signature_dedup=not args.no_signature_dedup,
                        use_sweep_cache=not args.no_sweep_cache,
                        mechanics=args.mechanics,
                        focal_max_level=_bb_alt_cap,
                        capture_energy=args.compare_energy,
                    )
                    logger.info(f"    L{_bb_alt_cap:g} {_bn51:,} sims in "
                                f"{time.time() - t0:.1f}s ({mode_pretty_label(mode)})")
                    _bb_scores[mode] = _bcs51
                    if _bb_energy is not None:
                        _bb_energy[mode] = _bce51
                    if _bb_meta is None:
                        _bb_meta = _bcm51
                md['scores_l51'] = _bb_scores
                md['meta_l51'] = _bb_meta
                if _bb_energy is not None:
                    md['energy_l51'] = _bb_energy
        # default display level: CLI > TOML > league default cap.
        if args.best_buddy_display is not None:
            _bb_display = int(args.best_buddy_display)
        elif _bb_toml.get('default_display') is not None:
            _bb_display = int(_bb_toml['default_display'])
        else:
            _bb_display = int(_bb_default_cap)
        best_buddy = {
            'active': _bb_active,
            'default_display': _bb_display,
            'default_cap': _bb_default_cap,
            'alt_cap': _bb_alt_cap,
            'note': _bb_note,
        }

        # (b) Re-converge the mirror cohort AT the best-buddy cap, so the compare
        # widget's CMP pill is like-for-like in best-buddy view (both mirror
        # sides best-buddied) rather than a best-buddy attack vs an L50 cohort.
        # One extra slayer pass, only when best-buddy is active and the L50
        # --mirror-slayer pass actually ran. cache=None: these are distinct
        # (best-buddy-level) sims, kept out of the L50 slayer cache.
        main_slayer_iter_result_l51 = None
        if _bb_active and main_slayer_iter_result and args.mirror_slayer \
                and all_moveset_results:
            try:
                _lv, _da, _dd, _ds = pvpoke_default_ivs(args.species,
                                                        league=args.league)
                _bb_init_opp = (_da, _dd, _ds)
            except (KeyError, ValueError):
                _bb_init_opp = None
            if _bb_init_opp:
                _bb_f0, _bb_c0 = all_moveset_results[0][0], all_moveset_results[0][1]
                logger.info(f"  Mirror slayer re-convergence at L{_bb_alt_cap:g} "
                            f"(best-buddy cohort for the compare-widget CMP pill)...")
                _t_bb = time.time()
                main_slayer_iter_result_l51 = iterative_slayer_discovery(
                    args.species, args.league, args.shadow,
                    _bb_f0, _bb_c0, shield_scenarios, _bb_init_opp,
                    max_rounds=args.mirror_slayer_rounds,
                    top_per_round=args.mirror_slayer_pool,
                    cache=None,
                    metric=args.mirror_slayer_metric,
                    iv_floor=args.iv_floor,
                    log_path=log_path, verbose=args.verbose,
                    reserve_cpus=args.reserve_cpus,
                    focal_max_level=_bb_alt_cap,
                )
                logger.info(f"    L{_bb_alt_cap:g} cohort in "
                            f"{time.time() - _t_bb:.1f}s")

        # All render inputs are now in hand: snapshot them so
        # scripts/replay_analysis.py can re-render this dive after
        # renderer/analysis code changes without re-simming.
        state = {
            'species': args.species,
            'league': args.league,
            'shadow': args.shadow,
            'html_path': args.html,
            'split_movesets': args.split_movesets,
            'standalone': args.standalone,
            'shared_plotly_dir': args.shared_plotly,
            'moveset_data': moveset_data,
            'thresholds': thresholds,
            'opponent_label': opponent_label,
            'shield_scenarios': shield_scenarios,
            'opponent_names': opponents,
            'opp_iv_modes': opp_iv_modes_to_run,
            'reference_idx': reference_idx,
            'slayer_iter_result': main_slayer_iter_result,
            'slayer_iter_result_l51': main_slayer_iter_result_l51,
            'cli_args_str': cli_args_str,
            'has_toml_tiers': _toml_tiers_loaded,
            'article_slug': _article_slug,
            'threshold_registry': threshold_registry,
            'species_narrative': _species_narrative,
            'card_path': args.card_out,
            'card_robust_k': args.card_robust_k,
            'opp_movesets': opp_movesets_full,
            'mechanics': args.mechanics,
            'best_buddy': best_buddy,
        }
        if not args.no_replay_dump:
            _replay_path = dump_replay_state(state)
            if _replay_path:
                logger.info(f"  Replay state: {_replay_path}")
                logger.info(f"    (re-render without re-simming: "
                            f"python scripts/replay_analysis.py "
                            f"{_replay_path})")
        render_dive_html(state)

    logger.info("Done.")


if __name__ == '__main__':
    main()
