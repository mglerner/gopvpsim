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
    Pokemon, find_pokemon_entry, get_pokemon_entry, get_species, iv_rank,
    CPM, best_level,
    LEAGUE_CAPS, LEAGUE_MAX_LEVEL, MAX_CPM_LEVEL, bestbuddy_caps,
    cp as calc_cp, pvpoke_default_ivs,
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
    load_gamemaster, load_rankings, get_default_moveset,
    sprite_data_uri, load_group as fetch_group, species_id,
    cup_pretty_name, get_rankings_for, rankings_cache_path,
)
from gopvpsim.moves import parse_types
from gopvpsim.battle import (
    BattlePokemon, simulate,
    pvpoke_dp, pvpoke_simulate_shield, ENERGY_CAP, WIN_RATING,
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
import deep_dive_matchup_clusters as matchup_clusters
import deep_dive_rendering as rendering
import deep_dive_slayer as slayer
import pvpoke_links
from deep_dive_logging import (
    init_logger, worker_log_setup, get_logger,
)
# Extracted deep-dive modules (DRY review 2026-08-05 entry 12 split). Every
# name they took with them is re-exported below at the point it used to be
# defined, so `import deep_dive` keeps resolving all of them. sys.path is set
# up above at IMPORT time, not in main(), because a spawn-mode worker child
# imports deep_dive_lib.sweep directly (review section G, invariant 22).
# The imports ABOVE stay as they are even where the split left them unused in
# this file: `deep_dive.<name>` is a read surface for tests and the analysis /
# patch scripts (deep_dive.get_moves, deep_dive.get_rankings_for, ...), so
# pruning them is a deliberate follow-up, not a side effect of moving code.
from deep_dive_lib import (categories, opponents, render, robustness,
                           score_pack, sweep)

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
    'Cramorant': _form_change_callout(
        'After using <b>Dive</b> or <b>Surf</b>, Cramorant surfaces holding '
        'prey: <b>Gulping</b> form (Arrokuda) above 50% HP, <b>Gorging</b> '
        'form (Pikachu) at 50% or less; it cannot change prey while already '
        'holding one. While it holds prey, any <em>unshielded</em> charged '
        'attack against it triggers <b>Gulp Missile</b>: an automatic, '
        'unshieldable counterattack dealing flat damage equal to 1 + 15% of '
        'the attacker&#39;s maximum HP (unaffected by stats or typing), '
        'debuffing the attacker (-1 defense from Arrokuda, -2 attack from '
        'Pikachu), and returning Cramorant to base form. It fires even if '
        'the triggering attack knocks Cramorant out -- which can turn a '
        'loss into a simultaneous-KO tie. The sim models all of this '
        'natively from the gamemaster form-change data, mirroring PvPoke.'),
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
parse_policy = rendering.parse_policy
compose_mode = rendering.compose_mode
mode_pretty_label = rendering.mode_pretty_label
# Py<->JS wire strings (DRY review 2026-08-05 entry 5): written once in
# deep_dive_rendering, baked into DATA below, read back by the page JS.
score_key = rendering.score_key
scenario_label = rendering.scenario_label
parse_moveset_label = rendering.parse_moveset_label
tier_slug = rendering.tier_slug


# Moved to deep_dive_lib/categories.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
build_iv_categories = categories.build_iv_categories
_FORM_SHADOW_TAGS = categories._FORM_SHADOW_TAGS
_base_opponent = categories._base_opponent
_merge_matchup_variant_dupes = categories._merge_matchup_variant_dupes


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


def meets_threshold(thresh, atk, dfn, hp):
    """THE tier meets-rule (D14, DRY review 2026-08-05 entry 12).

    A threshold is met when every NON-ZERO stat requirement is satisfied as
    a ``>=`` comparison; a zero requirement is "unset" and always passes:
      - attack  >= thresh['attack']  (if > 0)
      - defense >= thresh['defense'] (if > 0)
      - stamina >= thresh['stamina'] (if > 0)

    Callers MUST pass the UNROUNDED effective stats. Classifying on the 2dp
    display-rounded arrays colors spreads the page's own paste-box scanner
    then rejects (Annihilape 0/9/14, def 102.9982 rounded up to the 103.0
    threshold; DRY review 2026-08-05 entry 1).

    ``classify_iv`` and ``classify_tier_indices`` are thin wrappers over
    this -- they differ only in what they return (first NAME vs ALL
    positional indices), never in the rule.
    """
    if thresh['attack'] > 0 and atk < thresh['attack']:
        return False
    if thresh['defense'] > 0 and dfn < thresh['defense']:
        return False
    if thresh['stamina'] > 0 and hp < thresh['stamina']:
        return False
    return True


def classify_iv(result, thresholds):
    """
    Return the name of the most restrictive threshold this IV spread meets,
    or None if it doesn't meet any. Thresholds are checked in order (most
    restrictive first); membership is ``meets_threshold``.
    """
    for name, thresh in thresholds.items():
        if meets_threshold(thresh, result['atk'], result['def_'],
                           result['hp']):
            return name
    return None


def classify_tier_indices(atk, dfn, hp, thresholds):
    """Return positional indices of ALL thresholds this spread meets, in order.

    Same ``meets_threshold`` rule as classify_iv, returning indices for the
    DATA build's iv_all_tiers / iv_tiers arrays.
    """
    return [ti for ti, thresh in enumerate(thresholds.values())
            if meets_threshold(thresh, atk, dfn, hp)]


def sp_rank_array(meta):
    """Return 1-based stat-product ranks for a canonical_meta list.

    ``meta`` entries are the canonical tuples
    ``(atk_iv, def_iv, sta_iv, level, cp, atk, def_, hp)``; the returned
    list is parallel to ``meta`` and becomes ``DATA.spRanks``.

    The sort key MUST match ``gopvpsim.pokemon.iv_rank``
    (src/gopvpsim/pokemon.py:415-421): the UNROUNDED stat product
    descending, ties broken by IV sum descending. That is PvPoke's
    convention, and it is the same convention the page's off-grid
    ``DATA.collection.rankLookup`` carries (built from ``iv_rank`` via
    ``user_collection.compute_rank_lookup``) -- so the on-grid and
    off-grid SP-rank paths in deep_dive_engine.js agree cell for cell.
    (One gap remains, deliberately: on a ``--species-iv-floor`` dive the
    grid is a SUBSET, so these ranks are dense 1..n over the pruned rows
    while ``rankLookup`` stays a global 1..4096 rank. Same convention,
    different scale -- see the comment at deep_dive_engine.js:1270.)

    The ``iv_sp``/``ivSp`` arrays are rounded to 0.1 for DISPLAY only and
    must never be used as the ranking key: rounding creates ties that
    aren't real and then breaks them by enumeration order (lowest a/d/s),
    which is neither PvPoke's answer nor ours (33-81% of rows differed on
    the species we measured, and the rank-1 marker landed on x/15/14
    instead of x/15/15).
    """
    order = sorted(range(len(meta)),
                   key=lambda i: (meta[i][5] * meta[i][6] * meta[i][7],
                                  meta[i][0] + meta[i][1] + meta[i][2]),
                   reverse=True)
    ranks = [0] * len(meta)
    for rank, idx in enumerate(order):
        ranks[idx] = rank + 1
    return ranks


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


# Moved to deep_dive_lib/sweep.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
make_battle_pokemon = sweep.make_battle_pokemon


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

# Moved to deep_dive_lib/render.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
REC_DISTINCTNESS_MIN_SYMDIFF = render.REC_DISTINCTNESS_MIN_SYMDIFF
REC_MAX_SPREADS = render.REC_MAX_SPREADS
REC_STRONG_POOL_N = render.REC_STRONG_POOL_N
REC_NOTABLE_MAX_CLEAR_FRAC = render.REC_NOTABLE_MAX_CLEAR_FRAC
REC_TWO_ONES_MIN_WINRATE_GAP = render.REC_TWO_ONES_MIN_WINRATE_GAP

# Moved to deep_dive_lib/robustness.py (Worlds 2026 robustness split,
# session 2); re-exported here so existing importers keep working. The
# cache alias is the SAME dict object (tests clear it through this name).
_FORM_CHANGE_SPECIES_CACHE = robustness._FORM_CHANGE_SPECIES_CACHE
_species_has_form_change = robustness._species_has_form_change
opp_iv_robustness = robustness.opp_iv_robustness
_opp_robustness_groups = robustness._opp_robustness_groups


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


# Moved to deep_dive_lib/opponents.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
get_top_opponents = opponents.get_top_opponents
resolve_opp_ivs = opponents.resolve_opp_ivs
ATK_WEIGHTED_SUFFIX = opponents.ATK_WEIGHTED_SUFFIX
_OPPONENT_VARIANT_REGISTRY = opponents._OPPONENT_VARIANT_REGISTRY
register_opponent_variant = opponents.register_opponent_variant
parse_opponent_spec = opponents.parse_opponent_spec
build_opp_meta_ranks = opponents.build_opp_meta_ranks
rankings_snapshot_date = opponents.rankings_snapshot_date
_parse_opponent_pool_line = opponents._parse_opponent_pool_line
ACTIVE_VARIANTS_PATH = opponents.ACTIVE_VARIANTS_PATH
_apply_active_variants = opponents._apply_active_variants
_atk_weighted_spread_name = opponents._atk_weighted_spread_name
variant_ivs = opponents.variant_ivs
expand_opponents_with_variants = opponents.expand_opponents_with_variants


# Moved to deep_dive_lib/sweep.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
sim_score = sweep.sim_score
moveset_label = sweep.moveset_label
moveset_label_raw = sweep.moveset_label_raw
_REF_TIE_MARGIN = sweep._REF_TIE_MARGIN
screen_movesets = sweep.screen_movesets


# Moved to deep_dive_lib/sweep.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
_worker_state = sweep._worker_state
compute_iv_metadata = sweep.compute_iv_metadata

slayer.compute_iv_metadata = compute_iv_metadata


# Moved to deep_dive_lib/render.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
base_form_focal = render.base_form_focal


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


# Moved to deep_dive_lib/render.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
form_sibling_trade = render.form_sibling_trade


# Moved to deep_dive_lib/sweep.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
_stat_profile_key = sweep._stat_profile_key
group_ivs_by_stat_profile = sweep.group_ivs_by_stat_profile


# Moved to deep_dive_lib/sweep.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
# BattleSide/build_battle_pair are the D10 core the sweep worker, the
# slayer worker and profile_slayer all construct their pair through;
# SweepConfig (D9) is the run-wide knob block main() passes to iv_sweep.
BattleSide = sweep.BattleSide
build_battle_pair = sweep.build_battle_pair
_METRIC_NAMES = sweep._METRIC_NAMES
_sweep_worker_init = sweep._sweep_worker_init
_sweep_worker = sweep._sweep_worker
SweepConfig = sweep.SweepConfig
iv_sweep = sweep.iv_sweep


# ---------------------------------------------------------------------------
# HTML output with threshold highlighting
# ---------------------------------------------------------------------------

# Colors for threshold tiers - the ordered --tier-1..--tier-8 palette, indexed
# mod 8 (most restrictive first). These flow as theme-aware 'var(--tier-N)'
# STRINGS everywhere (CSS badge renders them as tier-color TEXT on
# var(--surface-2)); the Plotly-marker injection boundary also resolves them to
# DEFAULT_THEME hex via _TIER_VAR_TO_HEX, which since the theme shim landed is
# the FALLBACK rather than the live value: deep_dive_engine.js re-resolves each
# 'var(--tier-N)' against the ACTIVE theme with getComputedStyle at chart-build
# time (see __THEME_FALLBACK_JS__ below). "Other" (no threshold) uses the
# Viridis colorscale.
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

# Non-tier theme tokens the Plotly chrome shim reads (deep_dive_engine.js
# themeColor()). The LIVE value comes from getComputedStyle on the active
# [data-theme] block; this map is the DEFAULT_THEME fallback injected as
# __THEME_FALLBACK_JS__, so a canvas can never fall back to a literal that is
# not a theme.py value (palette_governance.md section 1: _TOKENS is the only
# sanctioned home for palette hex).
#
# Keep this list in sync with the themeColor('--x') call sites in the JS --
# tests/test_plotly_theme_shim.py asserts the two agree in both directions.
_PLOT_THEME_TOKENS = (
    '--surface',       # legend panel fill
    '--surface-2',     # plotting-area fill, hover panel, marker separation ring
    '--border-2',      # grid / zero line / legend border
    '--text',          # global chart font, high-contrast neutral marks
    '--text-muted',    # recessive neutral marks, reference lines, hover border
    '--notable',       # slayer-overlay gold (theme.py names this exact role)
    '--cat-anchors',   # anchor-overlay ring (the anchors category hue)
)
_THEME_FALLBACK_HEX = {
    tok: _THEME_TOKENS[tok][_DEFAULT_THEME_IDX] for tok in _PLOT_THEME_TOKENS
}


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


# Moved to deep_dive_lib/render.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
resolve_reference_moveset = render.resolve_reference_moveset


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



# Moved to deep_dive_lib/render.py (DRY review 2026-08-05 entry 12
# split); re-exported here so existing importers keep working.
_rename_plotly_tiers = render._rename_plotly_tiers
_promote_flavors_to_paste_tiers = render._promote_flavors_to_paste_tiers
_recompute_tier_assignments = render._recompute_tier_assignments
_mirror_synth_scores = render._mirror_synth_scores
_generate_narrative_for_moveset = render._generate_narrative_for_moveset
generate_analysis_sections = render.generate_analysis_sections


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


def rankings_fingerprint(league):
    """Reproducibility fingerprint for a league's PvPoke rankings cache.

    Two dives with identical CLI args can produce different results when the
    underlying rankings cache drifts (see TODO.md "Reproducibility"). This
    returns a dict capturing the drift-sensitive identity of the cache file:
    its path, mtime, a sha256 content hash, the rankings count, and the top-5
    species. Returns ``None`` if the cache file is missing/unreadable.

    Pure read-only (no logging, no mutation) so the same fingerprint can feed
    both the HTML footer and the run-start log.
    """
    import datetime
    import hashlib
    from gopvpsim import data as _gpdata
    cache_path = rankings_cache_path(league)
    if not cache_path.exists():
        return None
    raw = cache_path.read_bytes()
    content_hash = hashlib.sha256(raw).hexdigest()
    mtime = datetime.datetime.fromtimestamp(cache_path.stat().st_mtime)
    rk = _gpdata.load_rankings(league)
    top5 = [r.get('speciesName', r.get('speciesId', '?')) for r in rk[:5]]
    return {
        'cache_path': cache_path,
        'mtime': mtime,
        'mtime_str': mtime.strftime('%Y-%m-%d %H:%M:%S'),
        'content_hash': content_hash,
        'count': len(rk),
        'top5': top5,
    }


def log_run_start_fingerprint(league):
    """Emit the run-start rankings-cache reproducibility log line.

    Wraps :func:`rankings_fingerprint` with the ``logger.info`` emission so a
    dive's log alone pins which rankings vintage it ran against (the HTML
    footer carries the same fingerprint for the rendered page). Returns the
    fingerprint dict (or ``None`` when the cache is missing).
    """
    fp = rankings_fingerprint(league)
    if fp is not None:
        logger.info(
            f"  rankings cache: {fp['cache_path'].name} "
            f"mtime={fp['mtime_str']} sha256={fp['content_hash'][:12]} "
            f"first5={', '.join(fp['top5'])}")
    return fp


# Moved to deep_dive_lib/score_pack.py (DRY review 2026-08-05 entry 12,
# js-py-score-pack), which also owns the JS decoder this is the inverse of --
# encoder and decoder now change together, and the ML IV-guide chain packs
# with the same function. Re-exported here for the existing importers.
_pack_u16 = score_pack.pack_u16


def build_collection_data(species, league, shadow, tier_info, best_buddy):
    """Build the ``DATA.collection`` support blob for the in-page IV scanner.

    Returns the dict that gets attached as ``data_obj['collection']`` (and
    emitted verbatim into the page's ``var DATA = ...``), or ``None`` when
    the focal species isn't in the pokemon index.

    Extracted from ``generate_interactive_html`` so the league-capped
    ``maxLevel`` single-source can be unit-tested without a full render
    (see tests/test_collection_data.py). Two properties are load-bearing:

    * The returned dict's literal key order is part of the rendered bytes
      (replay-vs-original diffing is byte-for-byte) -- don't reorder.
    * ``LEAGUE_MAX_LEVEL`` must be read HERE, at call time: ``main()``
      mutates it in place for ``--max-level``.
    """
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
            max_level=LEAGUE_MAX_LEVEL.get(league, MAX_CPM_LEVEL), shadow=shadow)
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
            if best_buddy.get('noop'):
                # No-op best-buddy: the alt-cap stat-product ranks are provably
                # identical to the default-cap ones (no IV's level changes), so
                # alias rather than re-rank at the alt cap (no extra compute).
                _rank_table_alt = _rank_table
            else:
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
            # Single-source the scanner's level ceiling from the canonical
            # per-league table -- gopvpsim.pokemon.LEAGUES is the one place
            # the numbers live (LEAGUE_MAX_LEVEL is its derived view), so
            # don't restate them here. A bare 51.0 showed GL/UL owned mons
            # one level too high in the IV scanner (best-buddy override only
            # uses this as a fallback, so that path is unaffected).
            'maxLevel':        LEAGUE_MAX_LEVEL.get(league, MAX_CPM_LEVEL),
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
    return _collection_data


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
                              best_buddy=None, slayer_iter_result_l51=None,
                              cup=None, cup_label=None):
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
    # Same per-page reset for opponent anchor ids: each id="opp-<slug>"
    # is emitted once per file by whichever section renders first, so the
    # registry must start empty (otherwise split/replay pages 2+ would
    # suppress every id).
    rendering.reset_opp_anchor_registry()

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

    # Compute stat product ranks (same for all movesets). Ranked off the
    # UNROUNDED meta stats with the IV-sum tiebreak, so DATA.spRanks agrees
    # with the off-grid DATA.collection.rankLookup (iv_rank / PvPoke
    # convention); iv_sp above is the 0.1-rounded DISPLAY array only.
    sp_ranks = sp_rank_array(meta)

    # Classify IVs by threshold tier
    # iv_tiers: primary tier (most restrictive match, for coloring) - -1 = none
    # iv_all_tiers: list of ALL matching tier indices (for filtering and tables)
    iv_tiers = [-1] * n_ivs
    iv_all_tiers = [[] for _ in range(n_ivs)]
    if thresholds:
        for i in range(n_ivs):
            # Classify on the UNROUNDED meta stats; iv_atk/iv_def are the
            # 2dp display arrays and rounding here colored spreads the
            # page's own paste-box scanner rejects (see helper docstring).
            iv_all_tiers[i] = classify_tier_indices(
                meta[i][5], meta[i][6], iv_hp[i], thresholds)
            if iv_all_tiers[i]:
                iv_tiers[i] = iv_all_tiers[i][0]  # most restrictive, for coloring

    # Find canonical IV indices for the reference IV spreads
    # PvPoke default IVs for this species
    pvpoke_ref_iv_idx = -1
    rank1_ref_iv_idx = -1
    try:
        # shadow= matters: ~37 species have divergent shadow defaultIVs
        # (pokemon.py pvpoke_default_ivs); without it a shadow dive's
        # "PvPoke default" reference is the non-shadow spread (review F3
        # 2026-08-09 -- latent, 0 shipped shadow dives diverge today).
        _lv, da, dd, ds = pvpoke_default_ivs(species, league=league,
                                             shadow=shadow)
        for i in range(n_ivs):
            if iv_a[i] == da and iv_d[i] == dd and iv_s[i] == ds:
                pvpoke_ref_iv_idx = i
                break
    except (ValueError, KeyError):
        pass
    # Rank 1 by stat product
    if n_ivs > 0:
        rank1_ref_iv_idx = min(range(n_ivs), key=lambda i: sp_ranks[i])

    # Battle-link data for the "Comparing builds" compare panels: enough for the
    # client to rebuild each per-build-vs-opponent pvpoke.com battle. Faithful to
    # the sim -- opponent (level, IVs) are resolved with the SAME functions
    # iv_sweep uses (variant_ivs / resolve_opp_ivs + Pokemon.at_best_level), once
    # per available opp-IV mode, and the opponent moveset is the sim's resolved
    # one (opp_movesets). Focal speciesId encodes shadow; the client fills focal
    # level (DATA.ivLv / ivL51 by best-buddy toggle) + candidate IVs + active
    # moveset. None -> that piece renders unlinked (best-effort, never fatal).
    # NB: opponent level uses the default league cap (opp_max_level=None); the
    # rare ML opponent-over-level seam is not plumbed into this renderer.
    def _opp_link_data(oi):
        opp_clean, variant, opp_is_shadow = parse_opponent_spec(opponent_names[oi])
        sid = pvpoke_links.species_id(opp_clean, opp_is_shadow)
        ms = opp_movesets[oi] if opp_movesets and oi < len(opp_movesets) else None
        # One move-segment grammar (and one "needs 2 charged moves" guard) for
        # every battle-link builder (DRY review 2026-08-05 entry 8). We pass the
        # sim's resolved moveset rather than calling opponent_link_data, which
        # would re-derive the default master moveset instead.
        moves = pvpoke_links.moveset_segment(ms[0], ms[1]) if ms else None
        if not sid or not moves:
            return None
        vi = variant_ivs(opp_clean, variant, league, threshold_registry)
        by_mode = {}
        for mode in opp_iv_modes:
            oa, od, os_ = vi if vi is not None else resolve_opp_ivs(
                opp_clean, league, opp_is_shadow, mode)
            op = Pokemon.at_best_level(opp_clean, oa, od, os_, league=league,
                                       shadow=opp_is_shadow)
            by_mode[mode] = {'lvl': op.level, 'ivs': [oa, od, os_]}
        return {'id': sid, 'moves': moves, 'byMode': by_mode}

    _fsid = pvpoke_links.species_id(species, shadow)
    focal_link = {'id': _fsid} if _fsid else None
    opp_links = [_opp_link_data(_oi) for _oi in range(n_opponents)]

    data_obj = {
        'species': species,
        'league': league,
        'cpCap': LEAGUE_CAPS[league],
        'focalLink': focal_link,
        'oppLinks': opp_links,
        'nIvs': n_ivs,
        'nScenarios': n_scenarios,
        'nOpponents': n_opponents,
        'scenarios': [[s0, s1] for s0, s1 in shield_scenarios],
        # Canonical '{a}v{b}' label per scenario, baked alongside the tuple
        # so no JS site re-forms it (DRY review 2026-08-05 entry 5). It is
        # the matchup-cluster payload's scenario key, where a divergent
        # form silently disables the cluster overlay.
        'scenarioLabels': [scenario_label(s) for s in shield_scenarios],
        # Level ceilings for this league, from pokemon.bestbuddy_caps /
        # MAX_CPM_LEVEL, so the page JS never hardcodes 50/51 (entry 9).
        # `maxCpm` is the hard CPM-table ceiling used to validate
        # hand-entered levels; `default`/`alt` are the league's
        # non-best-buddy / best-buddy caps.
        'levelCaps': dict(zip(('default', 'alt'), bestbuddy_caps(league)),
                          maxCpm=MAX_CPM_LEVEL),
        # Win/tie boundary, from gopvpsim.battle.WIN_RATING. A rating of
        # EXACTLY this value is a TIE, not a win, so every page-side win test
        # is strictly `>`. The page reads it through winRating()/isWin() in
        # cmp_panels.js; that file's WIN_RATING_FALLBACK literal covers hosts
        # whose blob predates this field, and tests/test_win_boundary.py pins
        # the two together.
        'winRating': WIN_RATING,
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
        # Per-opponent PvPoke meta rank (1=best) or null, parallel to
        # `opponents`. Powers the client-side opponent filter panel: the
        # checkbox list sorts by this (unranked -> end) and the Top 10/20/50
        # buttons select entries with a non-null rank <= N. `rankSnapshot` is
        # the vintage of the rankings these came from, so the UI can label the
        # cut honestly ("top N per PvPoke rankings as of YYYY-MM-DD") rather
        # than implying the pool is live-current (it's a curated snapshot).
        # For a cup dive, meta ranks + snapshot come from the cup rankings, so
        # the top-N buttons mean "top N in the cup" and the banner date is the
        # cup rankings vintage.
        'oppMetaRank': build_opp_meta_ranks(opponent_names, league, cup=cup),
        'rankSnapshot': rankings_snapshot_date(league, cup=cup),
        # Cup identity for a limited-cup dive (None for a normal league dive).
        # `cupLabel` is the human name ("Equinox Cup") the card/page/banner show
        # alongside the snapshot date (keep-as-archive policy).
        'cup': cup,
        'cupLabel': cup_label,
        'referenceIdx': reference_idx,
        'tiers': tier_info,
        # `label` stays the raw 'FAST / CM1, CM2' display string; `fast` +
        # `charged` are the SAME split done once here (parse_moveset_label)
        # so the page's pvpoke-link builder reads move ids straight out of
        # DATA instead of re-splitting the label (entry 5).
        'movesets': [{'label': md['label'], 'prettyLabel': _pretty_moveset(md['label']),
                      'fast': parse_moveset_label(md['label'])[0],
                      'charged': parse_moveset_label(md['label'])[1],
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
        # Same convention as the L50 grid above -- unrounded SP, IV-sum
        # tiebreak; sp_lv is display-only. See sp_rank_array's docstring.
        sp_ranks_lv = sp_rank_array(meta_lvl)
        eff_lv = efficient_frontier(list(zip(atk_lv, def_lv, hp_lv)))
        tiers_lv = [-1] * len(meta_lvl)
        all_tiers_lv = [[] for _ in range(len(meta_lvl))]
        if thresholds:
            for i in range(len(meta_lvl)):
                # THE meets-rule, on UNROUNDED stats -- this was the third
                # (and last) hand-copied chain, and the only one still
                # classifying on the 2dp display arrays, so the L51 view
                # could tier-color a spread the L50 view rejects (found by
                # the D14 adversarial verify, 2026-08-06).
                all_tiers_lv[i] = classify_tier_indices(
                    meta_lvl[i][5], meta_lvl[i][6], hp_lv[i], thresholds)
                if all_tiers_lv[i]:
                    tiers_lv[i] = all_tiers_lv[i][0]
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
            key = score_key(mi, mode)
            score_arrays[key] = md['scores'][mode]
            if _bb_active and md.get('scores_l51') and mode in md['scores_l51']:
                score_arrays[score_key(mi, mode, l51=True)] = md['scores_l51'][mode]
            if md.get('energy') and mode in md['energy']:
                energy_arrays[key] = md['energy'][mode]
                if (_bb_active and md.get('energy_l51')
                        and mode in md['energy_l51']):
                    energy_arrays[score_key(mi, mode, l51=True)] = md['energy_l51'][mode]

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
                scores_base_arrays[score_key(mi, mode)] = sb[mode]

    # (The clusterGaps computation + dashed scatter overlay were retired
    # 2026-07 with the experimental banding/gap-cluster section, replaced by
    # the matchup-fingerprint clusters section in the Dive Analysis block.)

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
            mset_key = score_key(0, opp_iv_modes[0])
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
    shield_desc = ', '.join(scenario_label(s) for s in shield_scenarios)

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
    # Built by the module-level build_collection_data() helper so the
    # league-capped maxLevel single-source is unit-testable without a
    # render (tests/test_collection_data.py).
    _collection_data = build_collection_data(
        species, league, shadow, tier_info, best_buddy)
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

    # Cup dives are mechanically the given league but labeled with the cup name
    # (keep-as-archive policy): the title/H1 read "<Cup> (<League> League)" so
    # no page silently presents as a bare open-league dive.
    # Shared with the dive card's header line (deep_dive_card) so the two
    # renderings of the same fact can't drift.
    from deep_dive_card import cup_label_and_snapshot as _cup_hdr
    _league_title, _snap_txt = _cup_hdr(
        cup_label, f'{league.title()} League',
        rankings_snapshot_date(league, cup=cup) if cup_label else None)

    # Prominent cup banner (archive policy): the cup name + the rankings
    # snapshot date, and an explicit "kept as a dated archive" note so a reader
    # landing on an ended cup's page isn't misled into thinking it's live. Empty
    # string for a normal league dive.
    _cup_banner_html = ''
    if cup_label:
        _cup_banner_html = (
            '<div style="background: var(--surface); '
            'border-left: 3px solid var(--accent); padding: 8px 12px; '
            'margin: 0 0 15px; border-radius: 2px; font-size: 13px; '
            'color: var(--text);">'
            f'<b>{cup_label}</b> &middot; {_snap_txt}. '
            'Limited-time cup meta - this dive is kept as a dated '
            'archive and the cup may not be currently playable. Opponents '
            'use their cup movesets; meta ranks and the Top-N opponent '
            'filter reflect the cup rankings.</div>\n')

    html = f"""<!DOCTYPE html>
{cli_comment}<html {data_theme_attr()}>
<head>
<meta charset="utf-8">
{theme_head_script()}
<title>{species_pretty} {_league_title} IV Dive</title>
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
  /* Panels/table below are single-sourced (they are also emitted by the ML IV
     guide): rendering.CMP_PANEL_CSS, scripts/deep_dive_rendering.py. The dive
     adds no overrides -- its values ARE the shared ones. */
{rendering.CMP_PANEL_CSS}
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
  .dd-toc-bb label {{ display: flex; flex-wrap: wrap; align-items: flex-start;
                      gap: 5px; cursor: pointer; font-size: 0.78rem;
                      color: var(--text); line-height: 1.3; }}
  .dd-toc-bb input {{ margin-top: 2px; }}
  .dd-toc-bb b {{ font-weight: 600; }}
  .dd-toc-bb-note {{ font-size: 0.78rem; color: var(--text-muted); }}
  .dd-toc-bb-noop {{ flex-basis: 100%; font-size: 0.72rem;
                     color: var(--text-muted); }}
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
<h1>{species_pretty} - {_league_title} IV Dive</h1>
{_cup_banner_html}<p class="meta">Opponents: {opp_desc}
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
        # The toggle renders on every GL/UL dive for a consistent UI. When
        # best-buddy provably changes nothing for this mon (_bb_noop), toggling
        # is a true no-op; we say so in the title + a small hint so it reads as
        # honest (not a dead affordance).
        _bb_is_noop = bool(best_buddy.get('noop'))
        _bb_title = (
            "Best-buddy (+1 level) doesn't change any spread for this mon -- "
            "every IV is already CP-capped below L%g, so toggling is a no-op."
            % _bb_alt
            if _bb_is_noop else
            "Recompute the whole dive as if this mon were your best buddy "
            "(+1 level).")
        _bb_hint = (' <span class="dd-toc-bb-noop">(no change for this mon)</span>'
                    if _bb_is_noop else '')
        _bb_nav_ctrl = (
            '<div class="dd-toc-bb">\n'
            f'  <label title="{_bb_esc(_bb_title)}"><input type="checkbox" '
            'id="dd-bb-toggle" '
            'onchange="setBestBuddyLevel(this.checked ? \'51\' : \'50\')"'
            f'{_bb_checked}> <b>Allow best-buddy (L{_bb_alt:g})</b>{_bb_hint}'
            '</label>\n'
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
        for si, scen in enumerate(shield_scenarios):
            sel = ' selected' if n_scenarios == 1 else ''
            html += (f'    <option value="{si}"{sel}>'
                     f'{scenario_label(scen)}</option>\n')
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
        _policy_values = {parse_policy(m) for m in opp_iv_modes}
        if 'pogodives' in _policy_values and 'pvpoke' in _policy_values:
            html += ('  <label>Strategy: '
                     '<select id="policy-sel" onchange="updateView()">\n')
            html += '    <option value="pvpoke">PvPoke default</option>\n'
            html += '    <option value="pogodives">PoGoDives</option>\n'
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
    # Cluster labels are baked per-section (moveset 0, default opp-IV
    # mode) by deep_dive_matchup_clusters; the engine falls back to a
    # neutral trace with a legend note on any other moveset/mode.
    html += '    <option value="cluster">Matchup cluster</option>\n'
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
    if thresholds:
        html += '  <span style="font-size:11px;color:var(--text-muted);margin-left:8px">Threshold tiers (e.g. GH Great / GH Good) are expert stat-cutoff regions defined in <a href="#dd-threshold-tiers" style="color:var(--accent)">Threshold Tiers</a> below. Hover legend to isolate; click to lock.</span>\n'
    html += '</div>\n'

    # ---- Opponent filter panel (client-side subset selector) ----
    # A collapsible, scrollable checkbox list of every opponent, populated by
    # initOppFilter() in the engine JS (ordered by meta rank, unranked last).
    # All-checked by default, so a shipped page's default view is byte-identical
    # in behavior to before this feature. Checking a subset recomputes the
    # scatter / Top-IVs table / histograms over just those opponents; the banner
    # below appears on any partial selection to keep the full-pool sections
    # (card, tiers, Top Picks, narrative) honestly labeled. Convenience buttons
    # select the PvPoke top-10/20/50 by embedded DATA.oppMetaRank.
    html += '<details id="opp-filter-panel" style="margin:6px 0;border:1px solid var(--border);border-radius:4px;padding:6px 10px">\n'
    html += '  <summary style="cursor:pointer;font-size:13px"><b>Filter opponents</b> <span id="opp-filter-summary" style="font-size:11px;color:var(--text-muted)">(all shown)</span></summary>\n'
    html += '  <div style="margin-top:8px">\n'
    html += '    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px">\n'
    html += '      <button type="button" onclick="oppFilterAll()">All</button>\n'
    html += '      <button type="button" onclick="oppFilterNone()">None</button>\n'
    html += '      <button type="button" onclick="oppFilterTopN(10)">Top 10</button>\n'
    html += '      <button type="button" onclick="oppFilterTopN(20)">Top 20</button>\n'
    html += '      <button type="button" onclick="oppFilterTopN(50)">Top 50</button>\n'
    html += '    </div>\n'
    html += ('    <div id="opp-filter-list" style="max-height:220px;overflow-y:auto;'
             'display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));'
             'gap:2px 12px;padding:6px;border:1px solid var(--border);border-radius:4px"></div>\n')
    html += '  </div>\n'
    html += '</details>\n'
    html += ('<div id="opp-filter-banner" style="display:none;margin:8px 0;padding:8px 12px;'
             'border-radius:4px;background:rgba(210,160,40,0.15);'
             'border:1px solid rgba(210,160,40,0.6);font-size:13px;line-height:1.4"></div>\n')

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
    )
    # All-scenarios small-multiples toggle (Michael 2026-08-25): a
    # lazily-rendered 3x3 grid of simplified per-scenario scatters built
    # from the ALREADY-EMBEDDED score arrays -- no page re-render, no
    # state change; the panel matching the Shields dropdown gets a
    # highlight, and clicking a panel selects it. Lives left-aligned in
    # the strip under the plot (before Highlight IVs), with the grid
    # container BELOW the strip so the checkbox doesn't jump when the
    # grid opens.
    if n_scenarios > 1:
        html += ('  <label class="dd-allscen" style="display:flex;'
                 'align-items:center;gap:4px;margin-right:auto">'
                 '<input type="checkbox" id="allscen-toggle" '
                 'onchange="toggleAllScenarios()"> '
                 'Show all shield scenarios</label>\n')
    html += (
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
    if n_scenarios > 1:
        html += ('<div id="allscen-grid" style="display:none;'
                 'grid-template-columns:repeat(3,1fr);gap:6px;margin:8px 0;">'
                 '</div>\n')
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
                _mon = find_pokemon_entry(species)
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
        # Keyed WITHOUT the '@51' suffix on purpose: this dict feeds the
        # L51 render pass, where the best-buddy grids ARE the base grids.
        _sarr51 = {score_key(mi, mode): md['scores_l51'][mode]
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
        # The L51 body is a second, independent copy of the prose, so it needs
        # its own id="opp-<slug>" set: without this reset the first-mention-wins
        # registry (already fully claimed by the L50 pass) suppresses every
        # opponent id in the <template>, and each of its #opp- links dangles
        # once the toggle swaps the template into the host. Legal against the
        # dup-id guard because opponent ids only ever live inside
        # #dd-bb-prose-host / #dd-bb-prose-tmpl, never at document level, so
        # each guard view still sees exactly one copy per slug.
        rendering.reset_opp_anchor_registry()
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
    packed_scores = {key: _pack_u16(arr) for key, arr in score_arrays.items()}
    # Energy grid: same uint16/gzip/base64 pipeline as scores, keyed identically
    # (incl. @51). Empty unless --compare-energy populated energy_arrays, in
    # which case ZERO new bytes are emitted below (byte-identical when off).
    packed_energy = {key: _pack_u16(arr) for key, arr in energy_arrays.items()}
    # Dedup'd tooltip table: renderers register tooltip text as they
    # emit data-t="<sid>" attrs; we dump {sid: text} here and a
    # DOMContentLoaded pass (below) populates el.title from the
    # lookup. Saves ~18 MB on an Oinkologne-shape dive by collapsing
    # 87k repeated title= values to 1.6k unique strings.
    data_obj['tooltips'] = rendering.dump_tooltip_registry()
    # Tier-card anchor slugs, stamped LAST so they reflect the final tier
    # names (the analysis pass renames tiers and stashes the pre-rename name
    # in `original_name`, which is what the card anchor slugs off). The JS
    # paste-box reads these instead of re-deriving the slug (entry 5).
    for _tiers_key in ('tiers', 'pasteTiers'):
        for _t in (data_obj.get(_tiers_key) or []):
            _t['slug'] = tier_slug(_t.get('original_name') or _t.get('name') or '')
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

"""
    # ONE decoder, emitted from deep_dive_lib/score_pack.py -- the module that
    # also owns _pack_u16, so the page's decode and the bake's encode cannot
    # drift (DRY review 2026-08-05 entry 12, js-py-score-pack). The scores and
    # energy blocks were two hand-maintained literals of the same 20 lines.
    html += score_pack.decoder_js('_unpackU16')
    html += score_pack.decode_map_js('SCORES_GZ', 'SCORES', '_scoresReady',
                                     '_unpackU16')
    # Parallel ENERGY decode -- emitted ONLY when --compare-energy embedded a
    # grid (an energy-off dive gets no ENERGY var and no second loop).
    if packed_energy:
        html += score_pack.decode_map_js('ENERGY_GZ', 'ENERGY', '_energyReady',
                                         '_unpackU16')
        html += """\
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
  // Exposed so anything that injects data-t markup into the document AFTER
  // load can re-hydrate it. document.querySelectorAll does NOT descend into
  // <template> content (it is an inert DocumentFragment, not part of the
  // document tree), so the best-buddy L51 prose/card templates are invisible
  // to the pass below; setBestBuddyLevel calls this right after it swaps a
  // template into its host. Idempotent -- re-setting an already-correct
  // title is a no-op.
  window.ddPopulateTooltips = populate;
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

    # Shared compare-table functions (cmpVal/cmpHp/cmpScenLabel/cmpCellLink/
    # cmpBarHtml/cmpCellHtml/cmpUnifiedTable). Injected as a plain <script>
    # BEFORE the engine so its globals exist when the compare widget renders; the
    # ML IV-guide pages load the same file, keeping the table single-sourced. If the file is missing
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
    html += '<p><b>PoGo PvP IV Dive</b> - a stat-threshold analysis tool '
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
        fp = rankings_fingerprint(league)
        if fp is not None:
            top5 = ', '.join(fp['top5'])
            html += '<details class="meta" style="margin-top:8px">'
            html += '<summary>Rankings data fingerprint</summary>'
            html += '<pre style="margin:8px 0;background:var(--surface);'
            html += 'padding:10px;border-radius:4px;color:var(--text);font-size:12px;'
            html += 'white-space:pre-wrap;word-break:break-all">'
            html += f'cache file: {fp["cache_path"]}\n'
            html += f'cache mtime: {fp["mtime_str"]}\n'
            html += f'content sha256: {fp["content_hash"]}\n'
            html += f'rankings count: {fp["count"]}\n'
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
    f-string brace escaping). Ten placeholders inside that file get
    replaced at runtime with the per-dive values below.
    """
    # __TIER_COLORS_JS__ is the Plotly markers' DEFAULT_THEME FALLBACK: resolve
    # each 'var(--tier-N)' to its DEFAULT_THEME hex here (the single injection
    # boundary), and the JS shim re-resolves the parallel __TIER_VARS_JS__
    # entry against the active theme when getComputedStyle is available.
    # t['color'] itself stays 'var(--tier-N)' for the theme-aware
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
    shield_desc_default = scenario_label(shield_scenarios[0])
    opp_desc_escaped = opp_desc.replace("'", "\\'")

    with open(_JS_ENGINE_PATH) as _f:
        body = _f.read()
    substitutions = {
        '__SCENARIO_MODE_DEFAULT__': scenario_mode_default,
        '__OPP_IV_MODE_DEFAULT__': opp_iv_modes[0],
        '__TIER_COLORS_JS__': tier_colors_js,
        '__TIER_VARS_JS__': tier_vars_js,
        '__TIER_NAMES_JS__': tier_names_js,
        '__THEME_FALLBACK_JS__': json.dumps(_THEME_FALLBACK_HEX, sort_keys=True),
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


def article_slug_from_thresholds(species, shadow=False, thresholds_dir=None):
    """Resolve a species' related-article slug from its thresholds TOML.

    `[<Species>.article] slug` in `thresholds/<species>.toml` is the DURABLE
    home of the dive->article link (docs/article_schema.md, "Bidirectional
    link contract"). It is dive metadata, not threshold data, so it is read
    even when no threshold registry is loaded (--no-thresholds) and when
    re-rendering a replay blob baked before the article existed. Returns ''
    when the file, the table, or the key is absent; the renderer separately
    gates emission on the built article dir existing, so a stale slug can
    never produce a dead link.

    (main()'s thresholds auto-discover path reads the same table inline off
    its already-parsed TOML, alongside cd_prep / narrative.)
    """
    _dir = (Path(thresholds_dir) if thresholds_dir
            else Path(__file__).resolve().parent.parent / 'thresholds')
    _stem = species.lower().replace(' ', '_').replace('(', '').replace(')', '')
    if shadow:
        _stem += '_shadow'
    _path = _dir / f'{_stem}.toml'
    if not _path.exists():
        return ''
    try:
        import tomllib as _tomllib
        with open(_path, 'rb') as _f:
            _raw = _tomllib.load(_f)
    except Exception:
        return ''
    _key = species + (' (Shadow)' if shadow else '')
    return _raw.get(_key, {}).get('article', {}).get('slug', '')


def render_dive_html(state):
    """Render the interactive HTML output (split or single) from a
    replayable state dict. Keys mirror generate_interactive_html's
    kwargs plus the few main()/CLI fields the tail needs."""
    # Replay / rebake fallback: a blob baked before its species' article was
    # registered carries article_slug=''. The slug's durable home is the
    # thresholds TOML, so re-resolve it here instead of requiring a
    # hand-injected state['article_slug'] before every re-render
    # (Cramorant, 2026-08-27). Dir-existence gating still applies downstream.
    if not state.get('article_slug'):
        state['article_slug'] = article_slug_from_thresholds(
            state['species'], state.get('shadow', False))
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
                cup=state.get('cup'),
                cup_label=state.get('cup_label'),
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
            cup=state.get('cup'),
            cup_label=state.get('cup_label'),
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
    parser.add_argument('--cup', default=None, metavar='NAME',
                        help='Limited-cup dive (e.g. equinox). A cup dive is '
                             'mechanically the given --league (CP cap, opponent '
                             'IVs, cache keys all stay league-native); --cup is '
                             'a labeling + rankings-source overlay: meta ranks '
                             'and the top-N filter buttons come from the cup '
                             'rankings, and the card/page/replay are labeled '
                             'with the cup name + rankings snapshot date. Pair '
                             'with --opponents-file <cup pool> and '
                             '--no-active-variants.')
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
                        '"auto" (default) computes it for Great + Ultra; '
                        'Master/Little already cap at 51 so the toggle is a '
                        'no-op there. When no IV can actually climb a level the '
                        'toggle still renders (consistent UI) but is a provable '
                        'no-op -- no extra sims are run.')
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
    parser.add_argument('--policy', default='pvpoke',
                        choices=['pvpoke', 'pogodives', 'both'],
                        help="Strategy tier for the FOCAL side: 'pvpoke' "
                             "(default) is PvPoke's simulate-mode DP; "
                             "'pogodives' is the PoGoDives-strat overlay "
                             "(tuned rules where a registered case applies "
                             "-- today Cramorant only -- byte-identical "
                             "pvpoke_dp elsewhere, so non-case sweeps "
                             "alias to the base-tier cache for free); "
                             "'both' runs both tiers and adds a Strategy "
                             "selector to the interactive HTML. See "
                             "docs/cramorant_policy_plan.md. "
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
                             "Energy is persisted as a cache plane alongside "
                             "score (sweep_cache v6), so this serves warm from "
                             "the disk cache just like a score-only run; adds "
                             "~4%% to the HTML. Pass --no-compare-energy to drop "
                             "the energy line (slightly smaller HTML).")
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
                             'responsive. Default 0 (use cpu_count - N workers, '
                             'capped by the sweep chunk count). Applies to both '
                             'the per-moveset sim sweep and the slayer iteration '
                             'pool.')
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
        # narrative, leave threshold_registry None. The [article] slug is
        # orthogonal for the same reason (it's the dive->article link's
        # durable home, not threshold data), so it's read here too - a
        # --no-thresholds dive still gets its article link on a plain CLI
        # rebake (Cramorant, 2026-08-27).
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
        _article_slug = article_slug_from_thresholds(args.species, args.shadow)
        if _article_slug:
            logger.info(f"  Article link: articles/{_article_slug}/")
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
        # Run-start reproducibility log: record the rankings-cache identity
        # (mtime + content hash + first-5 species) at the moment opponents are
        # resolved, so a dive's log alone pins which rankings vintage it used
        # (the HTML footer carries the same fingerprint for the rendered page).
        log_run_start_fingerprint(args.league)
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

    # D9 (DRY review 2026-08-05 entry 12): ONE resolved knob block for every
    # iv_sweep call below (Phase 2, the extra composite modes, the reference
    # sweep, the base-form census, the best-buddy pass). Everything in it is
    # constant for the whole dive; only the moveset, the composite mode, and
    # the two opt-in axes (capture_energy / focal_max_level) vary per call.
    # Both inputs are final by here: log_path is set once at init_logger, and
    # threshold_registry took its last merge in the threshold-loading block.
    sweep_kwargs = SweepConfig.from_args(
        args, log_path=log_path,
        threshold_registry=threshold_registry).as_kwargs()

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
            capture_energy=args.compare_energy,
            **sweep_kwargs,
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
            # The slayer iteration builds its mirror cohort at the league's
            # effective focal level cap (iterative_slayer_discovery passes
            # focal_max_level=None, so build_focal_meta falls back to this
            # global — which --max-level mutates at parse time). Key on it so
            # two runs at different --max-level can't serve each other's stale
            # scores (bug #4, 2026-06-27).
            _slayer_focal_cap = LEAGUE_MAX_LEVEL.get(args.league, MAX_CPM_LEVEL)
            cache_key = compute_cache_key(
                args.species, args.league, args.shadow,
                fast_moves_db.get(fast_id, {}),
                [charged_moves_db.get(cid, {}) for cid in charged_ids],
                base_stats_dict,
                shield_scenarios=shield_scenarios,
                iv_floor=args.iv_floor,
                focal_max_level=_slayer_focal_cap,
            )
            # The slayer cache_key (compute_cache_key) does NOT include the
            # turn-mechanics model, so a 'new'-mechanics run would collide with
            # legacy-cached columns. Mirror the sweep cache's new-mode disable
            # (see iv_sweep, mechanics != 'legacy') rather than widen the key.
            slayer_cache = SlayerCache(
                cache_key=cache_key,
                disk=not args.no_cache and args.mechanics == 'legacy',
                # Scenario fields for the v5 sidecar -> let migrate_cache apply
                # a predicate (e.g. bandaid[910] self-debuff) without unpickling.
                # Slayer is a MIRROR, so the focal moveset IS both sides.
                scenario={'species': args.species, 'league': args.league,
                          'shadow': bool(args.shadow), 'fast': fast_id,
                          'charged': list(charged_ids)})

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
                    mechanics=args.mechanics,
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
                        # Raises on miss exactly like the bare next() this
                        # replaced; the enclosing except turns either into
                        # the "anchor resolution failed" warning.
                        focal_entry_for_anchors = get_pokemon_entry(args.species)
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
        if args.policy == 'both':
            _policy_tiers = ['pvpoke', 'pogodives']
        else:
            _policy_tiers = [args.policy]
        # Policy tier is the INNERMOST loop and the pvpoke tier collapses
        # in compose_mode, so opp_iv_modes_to_run[0] stays the bare base
        # mode -- load-bearing: analysis sections, the anchor overlay and
        # the JS default all read modes[0].
        opp_iv_modes_to_run = [
            compose_mode(om, bm, el, pol)
            for om in _base_opp_modes
            for bm in _bait_modes
            for el in _energy_leads
            for pol in _policy_tiers
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
                    capture_energy=args.compare_energy,
                    **sweep_kwargs,
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
                        capture_energy=args.compare_energy,
                        **sweep_kwargs,
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
                # ONE abbreviation rule (deep_dive_analysis.move_abbr):
                # id-derived, never label-derived -- gamemaster labels
                # truncate ('Weather Ball (Fire)' -> 'WB(') and collide
                # (both AURA_WHEELs read 'Aura Wheel').
                def _mv_abbr(mid):
                    return analysis.move_abbr(mid)
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
                # No capture_energy here on purpose: the census discards
                # everything but the score array.
                _, _bn, _bcs, _, _ = iv_sweep(
                    _base_species, _b_fast, _b_charged, args.league, _base_shadow,
                    opponents, opp_movesets_full, shield_scenarios,
                    opp_iv_mode=mode,
                    **sweep_kwargs,
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
        #   --best-buddy on/off  >  TOML compute  >  league policy (GL + UL on)
        #   --best-buddy-display >  TOML default_display  >  league default cap
        _bb_toml = _read_best_buddy_toml(args.species, args.shadow)
        if args.best_buddy == 'on':
            _bb_want = True
        elif args.best_buddy == 'off':
            _bb_want = False
        elif _bb_toml.get('compute') is not None:
            _bb_want = bool(_bb_toml['compute'])
        else:  # auto: default-on for Great + Ultra; Master/Little no-op
            # Great mirrors Ultra (2026-06-28): the focal best-buddy pass only
            # runs the expensive L51 sweep when it actually changes a spread
            # (_bb_active); CP-capped GL focals just do the cheap metadata no-op
            # check and show the "best-buddy changes nothing here" note.
            _bb_want = args.league in ('great', 'ultra')
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
                        focal_max_level=_bb_alt_cap,
                        capture_energy=args.compare_energy,
                        **sweep_kwargs,
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
        # No-op best-buddy toggle (Michael 2026-06-28: consistent UI -- the
        # toggle appears on every GL/UL page). When best-buddy is wanted for this
        # league but provably changes no IV's level (every IV CP-capped below the
        # alt cap), L51 is byte-identical to L50, so alias the L50 grids as the
        # L51 grids -- ZERO extra sims. The expensive L51 recomputes (the focal
        # sweep above, the slayer cohort below, the collection rankLookupAlt) all
        # stay gated on the *real* _bb_active, so no-op dives cost nothing extra;
        # only the cheap grid aliases + the toggle render are added.
        _bb_noop = bool(_bb_want and _bb_alt_cap != _bb_default_cap
                        and moveset_data and not _bb_active)
        if _bb_noop:
            for md in moveset_data:
                md['scores_l51'] = md['scores']
                md['meta_l51'] = md['meta']
                if md.get('energy'):
                    md['energy_l51'] = md['energy']
        best_buddy = {
            'active': _bb_active or _bb_noop,   # emit flag (drives the toggle)
            'noop': _bb_noop,                   # true => toggling is a no-op
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
        if _bb_noop and main_slayer_iter_result:
            # No-op: the mirror cohort is identical at L51, so alias it (no
            # extra slayer pass) -- keeps the L51-view CMP pill correct.
            main_slayer_iter_result_l51 = main_slayer_iter_result
        elif _bb_active and main_slayer_iter_result and args.mirror_slayer \
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
                    mechanics=args.mechanics,
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
            # Limited-cup labeling (None for a normal league dive). Carried in
            # the replay blob so a cup dive is self-identifying downstream
            # (threshold export routes cup blobs to a non-*_great.toml name).
            'cup': args.cup,
            'cup_label': cup_pretty_name(args.cup),
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
