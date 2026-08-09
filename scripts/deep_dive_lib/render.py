"""Analysis-section rendering for the deep-dive page.

Moved verbatim out of ``scripts/deep_dive.py`` by the DRY review 2026-08-05
entry 12 split (TODO.md "Split scripts/deep_dive.py", target 4). The
per-section renderers and the CSS string already live in
``deep_dive_rendering.py``; this module is the orchestrating
``generate_analysis_sections`` plus the tier/narrative helpers it drives.
``deep_dive.py`` keeps a re-export shim for every name defined here, so
existing importers keep working unchanged.

Every HTML fragment moved BYTE-FOR-BYTE: the dive page is the database
(review section G, invariant 25), and a replayed render is bit-diffed
against the pre-split output.
"""
import os
import sys

from gopvpsim.pokemon import Pokemon, get_species, find_pokemon_entry
from gopvpsim.moves import get_moves
from gopvpsim.data import get_default_moveset, parse_types
from gopvpsim.display import pretty_species
from gopvpsim.efficiency import efficient_frontier

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import deep_dive_analysis as analysis
import deep_dive_matchup_clusters as matchup_clusters
import deep_dive_rendering as rendering
from deep_dive_logging import get_logger
from deep_dive_lib.opponents import (
    parse_opponent_spec, resolve_opp_ivs, variant_ivs,
)
from deep_dive_lib.sweep import compute_iv_metadata, moveset_label

logger = get_logger()

# Aliases for extracted analysis functions (deep_dive_analysis.py), mirroring
# the block deep_dive.py keeps for its own remaining callers.
_find_flips = analysis.find_flips
_merge_flip_dicts = analysis.merge_flip_dicts
_build_move_tuples = analysis.build_move_tuples
_aggregate_flips_by_anchor = analysis.aggregate_flips_by_anchor
_synthesize_mirror_tier = analysis.synthesize_mirror_tier
_find_matchup_boundaries = analysis.find_matchup_boundaries
_auto_derive_tiers = analysis.auto_derive_tiers
_scenario_ranks = rendering.scenario_ranks
parse_mode = rendering.parse_mode
parse_energy = rendering.parse_energy
score_key = rendering.score_key


# Dive-card recommendation-spread selection (Phase A v2): pick a variable 2-6
# set. When named anchors resolved, selection is a greedy set-cover over the
# specific opponent break/bulkpoints the lead reference misses (see the
# selection block in generate_analysis_sections). On --no-mirror-slayer dives
# there are no named anchors, so we fall back to DISTINCTNESS over each IV's
# WON-SET (the (scenario, opponent) matchups it wins, score > 500; 500 = tie): a candidate
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
    scores_flat = score_arrays.get(score_key(moveset_idx, opp_iv_mode), [])
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
    # None-on-miss accessor (cached index) in place of the linear
    # gm['pokemon'] scans this used to run -- the ``if entry else []``
    # fallbacks below depend on the miss staying None, not raising
    # (DRY review 2026-08-05 entry 12 / L11).
    focal_entry = find_pokemon_entry(data_obj.get('species', ''))
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
            opp_entry = find_pokemon_entry(opp_clean)
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

    # Second flip reference, card-only: the stat-product #1 (rank1RefIvIdx).
    # The recommendation card shows BOTH "vs stat-product #1" and "vs PvPoke
    # default" lines (Michael, 2026-08-09 -- the old single line was computed
    # vs pvpokeRefIvIdx but mislabeled "vs stat-product #1"). `flips` /
    # `flip_map` above stay pvpoke-ref-only: candidate selection and the
    # results-section consumers are unchanged.
    _sp1_idx = data_obj.get('rank1RefIvIdx')
    if _sp1_idx is None or _sp1_idx < 0:
        _sp1_idx = None
    flips_sp = {}
    if _sp1_idx is not None:
        if _sp1_idx == ref_iv:
            # The primary flips ARE vs the SP-1 spread. This happens when
            # pvpokeRefIvIdx < 0 (IV-floor dive pruned the default; ref_iv
            # fell back to grid index 0) and grid index 0 is the SP #1 --
            # leaving flips_sp empty here made the card print a false
            # "no matchup flips" (adversarial review F1, 2026-08-09,
            # proven reachable via Umbreon --species-iv-floor 0,15,15).
            flips_sp = flips
        else:
            # Include ref_iv itself so the PvPoke-default spread, when it
            # is a card candidate, still gets a "vs stat-product #1" line
            # (review F2 -- the old code left that spread with no flip
            # line at all; live on the two Mimikyu UL pages).
            _sp_test = sorted(set(_sorted_test) | {ref_iv})
            for _mode in all_modes:
                _sf = score_arrays.get(f'{moveset_idx}_{_mode}', [])
                if not _sf:
                    continue
                _, _bm = parse_mode(_mode)
                flips_sp = _merge_flip_dicts(
                    flips_sp,
                    _find_flips(_sf, nIvs, nS, nO, _sp1_idx, _sp_test,
                                scenarios, opponents, bait_mode=_bm))
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
                if scores_flat[base + si * nO + oi] > 500)  # 500=tie (PvPoke)
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
    # and union the results. HSH-Discord-style thresholds are often against
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
            # B4 (HSH Discord review): the guide's "{{dive:tier_count}}"
            # token resolver and any other consumer that wants to count
            # *rendered tier cards* (rather than plot-traced tiers)
            # should use effectiveTierCount, which keeps the General
            # fallback. Visible cards = len(effective_tiers); plot
            # legend entries = len(data['tiers']).
            data_obj['effectiveTierCount'] = len(effective_tiers)
            # D14 (DRY review 2026-08-05): this used to be an inline clone
            # of _recompute_tier_assignments. Same computation, one copy.
            _recompute_tier_assignments(data_obj, plot_tiers)

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
<summary class="dd-h3" style="cursor:pointer">Dive Analysis</summary>
""")

    # -- Matchup-fingerprint clusters (replaced the experimental banding /
    # score-gap cluster block, 2026-07; see deep_dive_matchup_clusters.py) --
    _mc_bait = ('no-bait' if parse_mode(opp_iv_mode)[1] == 'nobait'
                else 'bait-selective')
    analysis_parts.append(matchup_clusters.render_section(
        scores_flat, nIvs, nS, nO, scenarios, opponents, data_obj,
        opp_label, moveset_label, resolved_anchors_top,
        bait_label=_mc_bait))

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
        'flips_sp': flips_sp,
        'sp1_idx': _sp1_idx,
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
