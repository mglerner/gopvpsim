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

from gopvpsim.pokemon import (Pokemon, get_species, find_pokemon_entry,
                              mega_level_from_tags)
from gopvpsim.moves import get_moves
from gopvpsim.data import get_default_moveset
from gopvpsim.moves import parse_types
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


# ---- Per-pass memo for the aggregator and the boundary finder -------------
# One level pass renders moveset 0's narrative (_generate_narrative_for_
# moveset) and then its analysis (generate_analysis_sections). Both ran
# aggregate_flips_by_anchor with IDENTICAL inputs for every opp-IV mode, and
# find_matchup_boundaries ran THREE times per (mode, sweep) -- the narrative,
# the analysis's census and the analysis's boundary list (2026-09-25 bake
# attribution, R2 + R4). The caller (deep_dive._render_level_body) hands both
# functions one fresh dict per pass as ``pass_memo``; None (every other
# caller) computes directly, exactly as before.
#
# An entry is reused only when the inputs are the same objects (scores list,
# anchor list, data_obj and its ivAtk/ivDef/ivHp lists -- compared with
# ``is``; the entry holds strong references so an id can never be recycled)
# and the same values (nIvs, nS, nO, scenarios, opponents, sweep -- the call
# sites build those separately). Every consumer gets its own copy of each
# record: callers set rec['bait_modes'] / rec['energy_modes'] and merge them
# across modes, so a shared record would leak one consumer's modes into the
# other.

def _pass_memo_get(pass_memo, key, same_objs, same_vals, compute):
    hit = pass_memo.get(key)
    if (hit is None or len(hit[0]) != len(same_objs)
            or any(a is not b for a, b in zip(hit[0], same_objs))
            or hit[1] != same_vals):
        hit = pass_memo[key] = (same_objs, same_vals, compute())
    return hit[2]


def _memo_inputs(scores_flat, data_obj, nIvs, nS, nO, scenarios, opponents,
                 *extra_objs):
    objs = (scores_flat, data_obj, data_obj.get('ivAtk'),
            data_obj.get('ivDef'), data_obj.get('ivHp')) + extra_objs
    vals = (nIvs, nS, nO, [tuple(s) for s in scenarios], list(opponents))
    return objs, vals


def _copy_flip_record(rec):
    out = dict(rec)                       # 'anchor' stays the SAME object
    out['scenarios'] = list(rec['scenarios'])
    out['passing_ivs'] = list(rec['passing_ivs'])
    return out


def _memo_aggregate_flips(pass_memo, key, scores_flat, nIvs, nS, nO,
                          resolved_anchors, data_obj, scenarios, opponents,
                          debug_stats=None):
    """aggregate_flips_by_anchor through the per-pass memo (see above)."""
    if pass_memo is None:
        return _aggregate_flips_by_anchor(
            scores_flat, nIvs, nS, nO, resolved_anchors, data_obj,
            scenarios, opponents, debug_stats=debug_stats)

    def compute():
        stats: dict = {}
        recs = _aggregate_flips_by_anchor(
            scores_flat, nIvs, nS, nO, resolved_anchors, data_obj,
            scenarios, opponents, debug_stats=stats)
        return recs, stats
    objs, vals = _memo_inputs(scores_flat, data_obj, nIvs, nS, nO,
                              scenarios, opponents, resolved_anchors)
    recs, stats = _pass_memo_get(pass_memo, key, objs, vals, compute)
    if debug_stats is not None:
        debug_stats.update(stats)
    return [_copy_flip_record(r) for r in recs]


def _memo_matchup_boundaries(pass_memo, key, scores_flat, nIvs, nS, nO,
                             data_obj, scenarios, opponents, sweep_stat):
    """find_matchup_boundaries through the per-pass memo (see above)."""
    if pass_memo is None:
        return _find_matchup_boundaries(
            scores_flat, nIvs, nS, nO, data_obj, scenarios, opponents,
            sweep_stat=sweep_stat)
    objs, vals = _memo_inputs(scores_flat, data_obj, nIvs, nS, nO,
                              scenarios, opponents)
    mbs = _pass_memo_get(
        pass_memo, key, objs, vals + (sweep_stat,),
        lambda: _find_matchup_boundaries(
            scores_flat, nIvs, nS, nO, data_obj, scenarios, opponents,
            sweep_stat=sweep_stat))
    return [dict(mb, scenarios=list(mb['scenarios'])) for mb in mbs]


# Dive-card spread selection. The card names the "Which one to build?"
# section's own builds (deep_dive_which_build.card_specs) -- one spread per
# named build, then the standouts -- and this cap is the hard ceiling on how
# many it renders. The Phase-A pole seeding + greedy named-coverage fill it
# replaced (and the REC_STRONG_POOL_N / REC_NOTABLE_MAX_CLEAR_FRAC /
# REC_DISTINCTNESS_MIN_SYMDIFF knobs that tuned it) were retired on
# 2026-09-17: a stat-extreme rule no other surface on the page used.
REC_MAX_SPREADS = 6

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
                                    *, species=None, focal_shadow=False,
                                    pass_memo=None):
    """Generate narrative HTML for one moveset.

    Computes matchup boundaries (and optionally anchor-flip records if
    resolved_anchors are provided), auto-derives tiers, and renders the
    SwagTips-style IV Flavor Guide zone.

    ``pass_memo`` is the per-pass memo shared with generate_analysis_sections
    (see _pass_memo_get); None computes everything directly.

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
            _recs = _memo_aggregate_flips(
                pass_memo, ('agg', moveset_idx, _mode),
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
            _mbs = _memo_matchup_boundaries(
                pass_memo, ('mb', moveset_idx, _mode, _sweep),
                _scores, nIvs, nS, nO,
                data_obj, scenarios, opponents, _sweep,
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
                               base_form_info=None,
                               card_builds=None,
                               card_builds_pinned=False,
                               clusters_sink=None,
                               pass_memo=None):
    """Generate the full analysis HTML for injection into the interactive page.

    Returns (css_str, results_html_str, analysis_html_str).
    results_html is always visible ("Deep Dive Results").
    analysis_html goes behind the toggle ("Deep Dive Analysis").

    ``clusters_sink``, when a dict, receives the rendered "Matchup clusters"
    section under ``'html'`` INSTEAD of it being appended to analysis_html.
    Michael's 2026-09-17 round-7 decision moved that section to the top of
    the page (directly under "Which one to build?"), and the caller owns the
    placement because the slot it fills is emitted long before this pass
    runs. With no sink the section stays where it was, first inside the
    Dive Analysis collapsible.

    ``card_builds`` is the dive card's spread list taken from the "Which one
    to build?" builds (``deep_dive_which_build.card_specs``): one entry per
    named build plus the standouts, each with its title, its guarantee
    sentence, its rarest guaranteed cells and its short name. It is the ONLY
    spread-selection rule on the page: it feeds the card, the scatter's "Spec
    Card Spreads" overlay (``data_obj['recIvs']``) and the opponent-threat
    chips (``data_obj['recNames']``) alike, so all three name the same
    spreads for the same reasons. The three stat-extreme POLES it replaced --
    and the style taxonomy that labelled them -- were retired on 2026-09-17.
    When it is empty (a moveset with no decision cells, an old blob, or a
    dive with no replay blob) all three fall back to the composite-score top
    picks, labelled "Top pick #N" -- never to a pole.

    ``card_builds_pinned`` says the builds were computed on a DIFFERENT
    grid than the one this pass renders (the best-buddy L51 pass reuses the
    league-cap builds, because the section itself is rendered once, at the
    cap). The card then prints one line saying so, rather than silently
    disagreeing with the section below it.

    When ``anchor_passing_sink`` is a dict, it gets populated with
    ``{anchor_id: [passing_iv_idx, ...]}`` for every anchor-flip bullet
    rendered, so the interactive HTML can embed the map as DATA and
    light up "which of your IVs hit this breakpoint" annotations after
    the user loads their CSV. Populated as a side effect - callers who
    just want HTML can leave it at None.

    ``pass_memo`` is the per-pass memo shared with the moveset's narrative
    (see _pass_memo_get); None computes everything directly.
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
    focal_moves = _build_move_tuples(
        moveset_label, fast_db, charged_db,
        mega_level_from_tags((focal_entry or {}).get('tags')))

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
                # Same tuple grammar as the focal side -- built by the one
                # helper rather than re-spelled here, so a per-move field
                # (the Mega Bonus is the first) cannot land on one side only.
                opp_moves_list = analysis.move_tuples_from_ids(
                    opp_fast, opp_charged, fast_db, charged_db,
                    mega_level_from_tags(
                        (opp_entry or {}).get('tags')))
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

    # ---- The spreads the card, the scatter overlay and the threat chips
    # name. ------------------------------------------------------------------
    # They are the "Which one to build?" section's own builds (``card_builds``
    # = deep_dive_which_build.card_specs: one spread per named build, then the
    # standouts). Resolved further down, once the census helpers exist.
    #
    # This RETIRES the three stat-extreme POLES -- balanced lead, max-effective
    # -attack, max-effective-defense -- and the style taxonomy that labelled
    # them ("Attack Weight", "High Defense", "High HP", "Matchup Hunter",
    # "Generalist", "Balanced", "Bait Robust", "Max Bulk"). They were a
    # selection rule no other surface on the page used, so the card and the
    # section named different spreads for different reasons, and the scatter's
    # "Spec Card Spreads" overlay marked spreads the card did not show
    # (2026-09-17 round 5, item 1).
    _anchor_mode = bool(resolved_anchors_top)

    by_iv = {rc['iv']: rc for rc in rec_candidates}

    # A build spread can sit outside the top-50 strong pool (rec_candidates) --
    # the bulk side routinely does -- and then has no rc dict. Those IVs ARE
    # simulated (data_obj['ivAtk'/'ivDef'/'ivHp'] span the full valid grid), so
    # _ensure_rc fabricates a minimal rc (flip counts, composite score) and any
    # spread flows into the card uniformly.
    def _ensure_rc(iv):
        rc = by_iv.get(iv)
        if rc is not None:
            return rc
        g, l, net = flip_map.get(iv, (0, 0, 0))
        rng = (max(scene_ranks[si][iv] for si in range(nS))
               - min(scene_ranks[si][iv] for si in range(nS)))
        score = -avg_ranks[iv] + net * 3 - rng * 0.001
        rc = {'iv': iv, 'avg_rank': avg_ranks[iv], 'avg_score': avg_scores[iv],
              'gains': g, 'losses': l, 'net': net, 'range': rng,
              'score': score}
        by_iv[iv] = rc
        return rc

    # Lead / balanced reference = rank-1 BATTLE SCORE (ranked[0]) -- our headline
    # metric. Decision (Michael 2026-06-22): we pitch battle score as a better
    # metric than stat product, so our "#1" must BE the battle-score #1, not the
    # rank-1 stat-product IV. Fall back to the top composite candidate if
    # (defensively) ranked[0] is outside the strong pool. It is NOT a card
    # spread any more (the builds name those); it stays the page's reference
    # spread for the two-#1s blurb and the single-IV win rate below.
    _spranks = data_obj.get('spRanks') or []  # used by the two-#1s blurb below
    lead_iv = ranked[0] if ranked and ranked[0] in by_iv else rec_candidates[0]['iv']

    # CENSUS coverage source for the card labels: the full set of matchup-flip
    # boundaries (atk sweep -> breakpoints, def sweep -> bulkpoints) across the
    # WHOLE opponent pool, not just the curated resolved anchors. The resolved
    # anchors are a small TOML/mirror-slayer set (~3 breakpoint opponents for
    # Corviknight); the card census wants EVERY opponent a spread clears a
    # guaranteed break/bulkpoint against (cf. Dragapult-Sim's "18 guaranteed
    # breakpoints"). Computed once here, deduped per (opponent, stat,
    # threshold); _census_cover(iv) then asks, per spread, which opponents that
    # spread's atk/def clears. The card's spreads come from the builds; only
    # these LABELS are census.
    _census_boundaries = []
    _cb_seen = set()
    for _mode in all_modes:
        _scores = score_arrays.get(f'{moveset_idx}_{_mode}', [])
        if not _scores:
            continue
        for _sweep in ('def', 'atk'):
            for mb in _memo_matchup_boundaries(
                    pass_memo, ('mb', moveset_idx, _mode, _sweep),
                    _scores, nIvs, nS, nO, data_obj, scenarios, opponents,
                    _sweep):
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

    # ---- the card's spreads, from the builds (2026-09-16 item 6; the only
    # selection rule after the 2026-09-17 pole retirement) --------------------
    # Each spec names an IV TRIPLE; the index is resolved against THIS page's
    # own arrays, so a card spread is always a spread this file embeds (the
    # best-buddy pass resolves the league-cap triples against its own L51
    # grid, which is what pins the two passes to the same spreads). Every
    # spread gets the same rc dict shape (_ensure_rc fabricates one for an IV
    # outside the top-50 strong pool) plus the census coverage, so the card's
    # breakpoint / bulkpoint / shadow-boost lines are computed as before.
    _triple_idx = {}
    for _i in range(nIvs):
        _triple_idx.setdefault(
            (data_obj['ivA'][_i], data_obj['ivD'][_i], data_obj['ivS'][_i]),
            _i)
    _card_recs, _card_extras, _card_names = [], {}, []
    for _spec in (card_builds or []):
        _iv = _triple_idx.get(tuple(int(x) for x in _spec['iv']))
        if _iv is None:
            logger.warning(
                f"  dive card: build spread {_spec['iv']} is not on this "
                f"page's grid; that card is omitted")
            continue
        _rc = dict(_ensure_rc(_iv))
        _rc['style'] = _spec['title']
        _card_recs.append(_rc)
        _card_names.append(_spec.get('short') or _spec['title'])
        _card_extras[_iv] = {'guarantee': _spec.get('guarantee', ''),
                             'cells': list(_spec.get('cells') or [])}

    # Fallback for a page with NO builds (a moveset with no decision cells, an
    # old blob, or a dive with no replay blob at all): the composite-score top
    # picks, filtered by the same strict-dominance guard the extra card
    # spreads always carried -- never a stat-extreme pole, which is what this
    # path used to be. They are labelled by their composite rank, because the
    # style taxonomy that named them is retired.
    _eff_mask = efficient_frontier(
        list(zip(data_obj['ivAtk'], data_obj['ivDef'], data_obj['ivHp'])))
    if _card_recs:
        chosen_recs, chosen_names = _card_recs, _card_names
    else:
        chosen_recs, chosen_names = [], []
        for rc in rec_candidates:
            if len(chosen_recs) >= REC_MAX_SPREADS:
                break
            if not _eff_mask[rc['iv']]:
                continue          # strictly dominated -> never headline it
            rc = dict(rc)
            rc['style'] = f"Top pick #{len(chosen_recs) + 1}"
            chosen_recs.append(rc)
            chosen_names.append(rc['style'])

    # Attach ABSOLUTE, CENSUS per-spread coverage for the card:
    # cover_breakpoints / cover_bulkpoints list EVERY distinct opponent (per
    # kind) for which this spread clears a guaranteed break/bulkpoint -- the
    # full matchup-boundary census (cf. Dragapult-Sim's "18 guaranteed
    # breakpoints" line), NOT the small curated resolved-anchor set.
    # n_breakpoint_opps / n_bulkpoint_opps are the headline census counts.
    # Absolute (not differential vs any reference), so each spread's own
    # coverage shows in full.
    if _anchor_mode:
        for rc in chosen_recs:
            bp, blk = _census_cover(rc['iv'])
            rc['cover_breakpoints'] = bp
            rc['cover_bulkpoints'] = blk
            rc['n_breakpoint_opps'] = len(bp)
            rc['n_bulkpoint_opps'] = len(blk)
            # Item 5: breakpoints the BOOST newly guarantees -- opponents this
            # spread clears a breakpoint against as a shadow/variant but NOT as
            # the base form. set difference of display-name sets (per spread).
            if _base_census_cover is not None:
                base_bp, _ = _base_census_cover(rc['iv'])
                rc['n_breakpoint_newly'] = len(set(bp) - set(base_bp))
    # NOTE: do NOT rebind rec_candidates -- it stays the full composite-sorted
    # list so the dive-page "Top Picks" HTML (render_results_section) and the
    # headline-mon default keep their pre-Phase-A behavior.

    # Store the chosen IV indices so the JS engine can render them as a
    # distinct overlay trace ("Spec Card Spreads") on the scatter plot. Fed by
    # the card's own spreads, so the red points and the card agree -- before
    # the pole retirement the overlay marked the poles while the card showed
    # the builds (2026-09-17 round 5, item 1b).
    data_obj['recIvs'] = [rc['iv'] for rc in chosen_recs]
    # The card titles' short forms ("Build 1", "Most matchups won", ...),
    # parallel to recIvs, for the opponent-threats "which build wins" chips.
    # Replaces the retired ``recStyles`` (the pole taxonomy).
    data_obj['recNames'] = list(chosen_names)

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
            _recs = _memo_aggregate_flips(
                pass_memo, ('agg', moveset_idx, _mode),
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
            _mbs = _memo_matchup_boundaries(
                pass_memo, ('mb', moveset_idx, _mode, _sweep),
                _scores, nIvs, nS, nO,
                data_obj, scenarios, opponents, _sweep,
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
        avg_scores=avg_scores,
        slayer_iter_result=slayer_iter_result,
        opp_info_cache=opp_info_cache, focal_moves=focal_moves,
        focal_types=focal_types, ref_atk=ref_atk, ref_def=ref_def,
        ref_iv=ref_iv, opp_iv_mode=opp_iv_mode,
        scores_flat=scores_flat, nS=nS, nO=nO, scenarios=scenarios,
        opponents=opponents, anchor_passing_sink=anchor_passing_sink,
        has_toml_tiers=has_toml_tiers, ranked=ranked,
        hp_list=hp_list, nIvs=nIvs,
        has_bait_axis=has_bait_axis,
        builds_pinned=bool(card_builds_pinned and _card_recs),
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
    # The Build-criteria presets, so the section can carry one combined
    # "all scenarios" partition per preset (2026-09-16). The table itself
    # lives with the builds module -- one definition of the three presets on
    # the page -- and is passed in rather than imported there, which would
    # make the clusters module depend on the module that depends on IT.
    import deep_dive_builds as _builds
    _mc_presets = [(k, tag, scens) for k, _lbl, scens, tag in _builds.PRESETS]
    _mc_html = matchup_clusters.render_section(
        scores_flat, nIvs, nS, nO, scenarios, opponents, data_obj,
        opp_label, moveset_label, resolved_anchors_top,
        bait_label=_mc_bait, presets=_mc_presets)
    if clusters_sink is None:
        analysis_parts.append(_mc_html)
    else:
        clusters_sink['html'] = _mc_html

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
    # The page's REFERENCE spread: the battle-score #1 (``lead_iv``). It used
    # to be read off chosen_recs[0], which WAS the battle-score #1 while the
    # card was pole-seeded; after the pole retirement chosen_recs[0] is Build
    # 1's most-winning member, so the reference is named directly rather than
    # silently following the card's first spread (2026-09-17 round 5).
    _rec_idx = lead_iv if rec_candidates else (ranked[0] if ranked else 0)
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
    # SCORE, so the page's reference IV (_rec_idx == lead_iv == ranked[0]) is
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
        'card_extras': _card_extras,
        'builds_pinned': bool(card_builds_pinned and _card_recs),
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
