"""Structured IV categories for the deep-dive page.

Moved verbatim out of ``scripts/deep_dive.py`` by the DRY review 2026-08-05
entry 12 split (TODO.md "Split scripts/deep_dive.py", target 1).
``deep_dive.py`` keeps a re-export shim for every name defined here, so
existing importers keep working unchanged.
"""
import os
import sys

from gopvpsim.battle import WIN_RATING

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import deep_dive_analysis as analysis
import deep_dive_rendering as rendering
import deep_dive_slayer as slayer

IVCategory = rendering.IVCategory
parse_mode = rendering.parse_mode
_stat_cutoffs_from_anchors = analysis.stat_cutoffs_from_anchors


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
        win_threshold = matchup_data.get('win_threshold', WIN_RATING)
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
                        if score > win_threshold:  # 500 = tie, not a win
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
