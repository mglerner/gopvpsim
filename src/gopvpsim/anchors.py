"""
Anchor resolution: turn TOML anchor declarations into concrete threshold checks.

Given a ThresholdRegistry plus focal species context (moves, types, league) and
an atk range to scan over, this module produces a list of ResolvedAnchor
objects. Each ResolvedAnchor has a single numeric threshold and a `passes()`
check — the deep-dive categorizer just asks "which ResolvedAnchors does this
focal IV pass?" and tags it with the set of names.

Level 3 damage_breakpoint anchors expand into a *family* of ResolvedAnchors
(one per discovered (move, tier) breakpoint). All sub-anchors share the same
`parent` name so they can be grouped in the HTML output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .breakpoints import atk_for_damage, breakpoints as scan_breakpoints
from .data import load_gamemaster, parse_types
from .moves import damage as calc_damage, get_moves
from .pokemon import (
    LEAGUE_CAPS, SHADOW_ATK_BONUS, SHADOW_DEF_MULT,
    Pokemon, best_level, battle_stats, get_species, pvpoke_default_ivs,
)
from .thresholds import (
    CmpAnchor, DamageBreakpointAnchor, IvListSpread, LeagueThresholds,
    SpeciesThresholds, StatCutoffSpread, ThresholdRegistry,
)


# ---------------------------------------------------------------------------
# ResolvedAnchor
# ---------------------------------------------------------------------------

@dataclass
class ResolvedAnchor:
    """A concrete, numeric threshold check derived from a TOML anchor.

    Each ResolvedAnchor has exactly one threshold and one comparison. Level 3
    BP anchors expand into multiple ResolvedAnchors with the same `parent`
    name and `parent_display_name`.
    """
    name: str                            # unique identifier
    parent: str                          # original TOML anchor name
    kind: str                            # "cmp" or "damage_breakpoint"
    threshold_atk: float                 # focal atk must be > (or >=) this
    strict: bool = True                  # True = strict `>`, False = `>=`
    label: str = ""                      # short human-readable label
    description: str = ""
    parent_display_name: str = ""        # short HTML badge label for the parent

    # Extra metadata for damage_breakpoint anchors:
    move_id: Optional[str] = None
    damage: Optional[int] = None
    opponent: Optional[str] = None

    def passes(self, focal_atk: float) -> bool:
        if self.strict:
            return focal_atk > self.threshold_atk
        return focal_atk >= self.threshold_atk


# ---------------------------------------------------------------------------
# Display-name derivation
# ---------------------------------------------------------------------------

def derive_display_name(parent_name: str) -> str:
    """Derive a short HTML badge label from a TOML anchor name.

    Used as the fallback when a TOML anchor doesn't set ``display_name``
    explicitly. Rules applied in order; an ``auto_`` prefix is stripped first
    so auto-generated anchors get the same short labels as hand-written ones.

      auto_X         → X (then re-derive)
      cmp_vs_X       → cmp:X
      X_bp_any       → X
      X_bp_above_Y   → X↑Y
      X_bp_Y         → X:Y
      (else)         → unchanged

    Examples:
      cresselia_bp_any            → cresselia
      lickitung_bp_above_lurgan   → lickitung↑lurgan
      cmp_vs_lurgan               → cmp:lurgan
      lickitung_bp_counter_5      → lickitung:counter_5
      auto_lickitung_bp_any       → lickitung
      auto_cmp_vs_cohort          → cmp:cohort
    """
    name = parent_name
    if name.startswith("auto_"):
        name = name[len("auto_"):]
    if name.startswith("cmp_vs_"):
        return "cmp:" + name[len("cmp_vs_"):]
    if name.endswith("_bp_any"):
        return name[: -len("_bp_any")]
    if "_bp_above_" in name:
        head, tail = name.split("_bp_above_", 1)
        return f"{head}\u2191{tail}"
    if "_bp_" in name:
        head, tail = name.split("_bp_", 1)
        return f"{head}:{tail}"
    return name


# ---------------------------------------------------------------------------
# Helper: spread → max effective atk (for CMP anchors)
# ---------------------------------------------------------------------------

def _spread_max_atk(
    spread, focal_species: str, league: str, *, shadow: bool = False
) -> Optional[float]:
    """Return the maximum effective atk over the members of a spread, when
    interpreted as IV combos of the focal species.

    For a StatCutoffSpread, returns the attack-cutoff field directly (which IS
    the threshold already).
    For an IvListSpread, computes the effective atk of each member at the
    focal species' best level under the league CP cap and returns the max.
    """
    if isinstance(spread, StatCutoffSpread):
        if spread.attack > 0:
            return spread.attack
        return None

    assert isinstance(spread, IvListSpread)
    best = None
    for (a_iv, d_iv, s_iv) in spread.ivs:
        try:
            mon = Pokemon.at_best_level(
                focal_species, a_iv, d_iv, s_iv,
                league=league, shadow=shadow,
            )
        except (KeyError, ValueError):
            continue
        atk = mon.atk
        if best is None or atk > best:
            best = atk
    return best


# ---------------------------------------------------------------------------
# Helper: opponent effective defense (for BP anchors)
# ---------------------------------------------------------------------------

def _opponent_ref(
    opponent_species: str,
    league: str,
    *,
    ivs: Optional[tuple[int, int, int]] = None,
    shadow: bool = False,
) -> Optional[tuple[float, list[str]]]:
    """Return (effective_def, types) for the opponent species under the given
    league, using either explicit IVs or PvPoke's defaults.

    Returns None if the opponent can't be resolved (not in gamemaster, can't
    fit under the CP cap, etc.).
    """
    try:
        if ivs is None:
            _lv, a_iv, d_iv, s_iv = pvpoke_default_ivs(opponent_species, league=league)
        else:
            a_iv, d_iv, s_iv = ivs
        mon = Pokemon.at_best_level(
            opponent_species, a_iv, d_iv, s_iv, league=league, shadow=shadow,
        )
    except (KeyError, ValueError):
        return None

    gm = load_gamemaster()
    entry = next((m for m in gm['pokemon']
                  if m['speciesName'] == opponent_species), None)
    if entry is None:
        return None
    types = parse_types(entry)
    return (mon.def_, types)


# ---------------------------------------------------------------------------
# CMP anchor resolution
# ---------------------------------------------------------------------------

def _resolve_cmp_anchor(
    anchor: CmpAnchor,
    registry: ThresholdRegistry,
    species: str,
    league_lower: str,
    league_toml: str,
    *,
    focal_shadow: bool = False,
) -> Optional[ResolvedAnchor]:
    spread = registry.get_spread(species, league_toml, anchor.spread)
    if spread is None:
        return None
    threshold = _spread_max_atk(spread, species, league_lower, shadow=focal_shadow)
    if threshold is None:
        return None
    display = anchor.display_name or derive_display_name(anchor.name)
    return ResolvedAnchor(
        name=anchor.name,
        parent=anchor.name,
        kind="cmp",
        threshold_atk=threshold,
        strict=anchor.strict,
        label=anchor.name,
        description=anchor.description,
        parent_display_name=display,
    )


# ---------------------------------------------------------------------------
# Damage breakpoint anchor resolution
# ---------------------------------------------------------------------------

def _select_moves(anchor: DamageBreakpointAnchor,
                  focal_moves: list[dict]) -> list[dict]:
    """Filter focal_moves according to the anchor's move / moves field."""
    if anchor.move is not None:
        return [m for m in focal_moves if m['moveId'] == anchor.move]
    if anchor.moves is not None:
        allowed = set(anchor.moves)
        return [m for m in focal_moves if m['moveId'] in allowed]
    return list(focal_moves)


def _resolve_bp_anchor(
    anchor: DamageBreakpointAnchor,
    registry: ThresholdRegistry,
    species: str,
    league_lower: str,
    league_toml: str,
    focal_moves: list[dict],
    focal_types: list[str],
    atk_min: float,
    atk_max: float,
) -> list[ResolvedAnchor]:
    """Resolve a damage_breakpoint anchor into one or more ResolvedAnchors."""
    # Opponent ref def
    opp_ivs = anchor.opponent_ivs
    if opp_ivs is None and anchor.opponent_spread is not None:
        opp_spread = registry.get_spread(species, league_toml, anchor.opponent_spread)
        if isinstance(opp_spread, IvListSpread) and opp_spread.ivs:
            # Use the bulkiest (highest def) member of the spread. We compute
            # each member's effective def and take the max.
            best_def = None
            best_iv = None
            for iv in opp_spread.ivs:
                try:
                    mon = Pokemon.at_best_level(
                        anchor.opponent, iv[0], iv[1], iv[2], league=league_lower,
                    )
                except (KeyError, ValueError):
                    continue
                if best_def is None or mon.def_ > best_def:
                    best_def = mon.def_
                    best_iv = iv
            opp_ivs = best_iv

    opp = _opponent_ref(anchor.opponent, league_lower, ivs=opp_ivs)
    if opp is None:
        return []
    opp_def, opp_types = opp
    moves = _select_moves(anchor, focal_moves)
    if not moves:
        return []

    level = anchor.level
    parent_display = anchor.display_name or derive_display_name(anchor.name)

    if level == 1:
        # Exactly one move, with deals_at_least set. Threshold = smallest atk
        # at which calc_damage >= deals_at_least.
        move = moves[0]
        threshold = atk_for_damage(
            anchor.deals_at_least, opp_def, move, focal_types, opp_types,
        )
        # Unreachable within our atk range? still return it; passes() will be False.
        label = f"{move['moveId'].lower()}→{anchor.deals_at_least}"
        return [ResolvedAnchor(
            name=anchor.name,
            parent=anchor.name,
            kind="damage_breakpoint",
            threshold_atk=threshold,
            strict=False,   # >=: "deals at least N"
            label=label,
            description=anchor.description,
            parent_display_name=parent_display,
            move_id=move['moveId'],
            damage=anchor.deals_at_least,
            opponent=anchor.opponent,
        )]

    if level == 2:
        # Find the smallest atk > above_atk at which ANY move's damage to opp
        # steps up. We scan each selected move and pick the earliest threshold.
        best = None  # (threshold, move, new_dmg)
        for move in moves:
            # Find all breakpoints strictly greater than above_atk
            bps = scan_breakpoints(
                move, focal_types, opp_def, opp_types, anchor.above_atk, atk_max,
            )
            # The first bp at atk_threshold == above_atk is the current tier;
            # we want the NEXT one up. scan_breakpoints returns thresholds in
            # order; filter for strictly greater than above_atk.
            for bp in bps:
                if bp.atk_threshold > anchor.above_atk:
                    if best is None or bp.atk_threshold < best[0]:
                        best = (bp.atk_threshold, move, bp.damage)
                    break
        if best is None:
            return []
        threshold, move, dmg = best
        label = f"{move['moveId'].lower()}→{dmg}"
        return [ResolvedAnchor(
            name=anchor.name,
            parent=anchor.name,
            kind="damage_breakpoint",
            threshold_atk=threshold,
            strict=False,
            label=label,
            description=anchor.description,
            parent_display_name=parent_display,
            move_id=move['moveId'],
            damage=dmg,
            opponent=anchor.opponent,
        )]

    # Level 3: enumerate every breakpoint for every selected move in the range.
    resolved: list[ResolvedAnchor] = []
    for move in moves:
        bps = scan_breakpoints(move, focal_types, opp_def, opp_types,
                               atk_min, atk_max)
        for bp in bps:
            move_slug = move['moveId'].lower()
            label = f"{move_slug}→{bp.damage}"
            sub_name = f"{anchor.name}::{label}"
            resolved.append(ResolvedAnchor(
                name=sub_name,
                parent=anchor.name,
                kind="damage_breakpoint",
                threshold_atk=bp.atk_threshold,
                strict=False,
                label=label,
                description=anchor.description,
                parent_display_name=parent_display,
                move_id=move['moveId'],
                damage=bp.damage,
                opponent=anchor.opponent,
            ))
    return resolved


# ---------------------------------------------------------------------------
# Public: resolve_anchors
# ---------------------------------------------------------------------------

def resolve_anchors(
    registry: ThresholdRegistry,
    species: str,
    league: str,
    focal_moves: list[dict],
    focal_types: list[str],
    atk_min: float,
    atk_max: float,
    *,
    focal_shadow: bool = False,
) -> list[ResolvedAnchor]:
    """Resolve every anchor for (species, league) into concrete threshold checks.

    focal_moves: list of move dicts as returned by get_moves()[0] / [1] for the
      specific moveset being analyzed. Each dict must have 'moveId', 'power',
      and 'type' fields.
    focal_types: list of focal species type strings (e.g. ['fighting', 'ghost']).
    atk_min, atk_max: the survivor atk range (used for Level 3 BP enumeration).
    league: the lowercase league name (e.g. 'great', 'ultra') matching the
      pokemon / data modules' convention. The TOML files key league tables
      by capitalized names (e.g. 'Great'), and we normalize that here.
    """
    league_lower = league.lower()
    league_toml = league_lower.capitalize()

    sp = registry.species(species)
    if sp is None:
        return []
    lt = sp.league(league_toml)
    if lt is None:
        return []

    resolved: list[ResolvedAnchor] = []
    for name, anchor in lt.anchors.items():
        if isinstance(anchor, CmpAnchor):
            r = _resolve_cmp_anchor(
                anchor, registry, species, league_lower, league_toml,
                focal_shadow=focal_shadow,
            )
            if r is not None:
                resolved.append(r)
        elif isinstance(anchor, DamageBreakpointAnchor):
            resolved.extend(_resolve_bp_anchor(
                anchor, registry, species, league_lower, league_toml,
                focal_moves, focal_types, atk_min, atk_max,
            ))
    return resolved


# ---------------------------------------------------------------------------
# Auto-anchor synthesis
# ---------------------------------------------------------------------------

# Sentinel spread name for the auto-generated mirror cohort.
AUTO_COHORT_SPREAD_NAME = "__auto_cohort__"


def build_auto_anchors(
    species: str,
    league: str,
    opponent_species: list[str],
    *,
    fast_move_id: Optional[str] = None,
    survivor_ivs: Optional[list[tuple[int, int, int]]] = None,
    existing_anchor_kinds: Optional[set[str]] = None,
) -> ThresholdRegistry:
    """Build a synthetic registry overlay containing auto-generated anchors.

    Used to populate the Atk Slayer and CMP Slayer category boxes when the
    user hasn't written any explicit anchors of those kinds. The result is a
    standalone ThresholdRegistry that should be merged with the user's
    explicit registry (if any) before resolution.

    Auto-Atk-Slayer (one Level 3 ``damage_breakpoint`` anchor per opponent):
        Fires when ``"damage_breakpoint" not in existing_anchor_kinds``.
        For each species name in ``opponent_species``, creates a bare
        Level 3 anchor named ``auto_<opponent_lower>_bp_any`` enumerating
        every breakpoint over all focal moves (fast + charged). The
        ``fast_move_id`` parameter is accepted for forward-compat but
        ignored — restricting to fast moves only would silently disable
        auto-Atk for low-power-fast-move species (e.g. Annihilape with
        Low Kick power 5). Charged-move BP families are noisier but the
        filter panel + per-row tag abbreviation make the volume tolerable;
        users who want explicit fast-move-only behavior can hand-write a
        ``moves = ["FAST_MOVE_ID"]`` anchor in the TOML to override.

    Auto-CMP-Slayer (one ``cmp`` anchor against the survivor cohort):
        Fires when ``"cmp" not in existing_anchor_kinds`` and
        ``survivor_ivs`` is non-empty. Computes the 75th-percentile
        effective attack over the (deduped) survivor pool, wraps it in a
        synthetic ``StatCutoffSpread`` named ``__auto_cohort__``, and
        creates a non-strict ``CmpAnchor`` named ``auto_cmp_vs_cohort``
        against it. Interpretation: "your effective attack is in the top
        quartile of the converged mirror cohort — you'd win or tie CMP
        against most opponents your iteration produced."

        Why top-quartile and not "strictly beat max": the focal IV is
        itself a member of the cohort, so "strictly above max" is
        unreachable (you can never beat yourself). Top-quartile is the
        meaningful interpretation that always populates the category and
        matches the old categorize_slayers heuristic, now grounded in the
        actual converged survivor pool rather than the unfiltered 4096-IV
        space.

    Args:
        species: focal species name (top-level TOML table key).
        league: lowercase league name (e.g. "great"). The TOML key is
            derived as the capitalized form.
        opponent_species: list of opponent species names from the dive's
            opponent set. Order is preserved in the auto-anchor list.
        fast_move_id: optional moveId of the focal's fast move; when set,
            auto-Atk anchors are restricted to this move only.
        survivor_ivs: optional list of (atk_iv, def_iv, sta_iv) tuples from
            the slayer iteration's converged cohort. Required for auto-CMP.
        existing_anchor_kinds: set of kinds the user already provided
            explicitly. Auto-generation is skipped for these kinds, so
            explicit user input always wins.

    Returns:
        A ThresholdRegistry containing the synthetic spreads and anchors.
        Empty (no species entries) if neither fallback fired.
    """
    existing = existing_anchor_kinds or set()
    league_toml = league.lower().capitalize()
    lt = LeagueThresholds(league=league_toml)

    if "damage_breakpoint" not in existing and opponent_species:
        seen_opponents: set[str] = set()
        for opp in opponent_species:
            if opp in seen_opponents:
                continue
            seen_opponents.add(opp)
            slug = opp.lower().replace(' ', '_').replace('(', '').replace(')', '')
            anchor_name = f"auto_{slug}_bp_any"
            description = (
                f"Auto-generated Level 3 BP anchor against {opp}. "
                f"Enumerates every (move, tier) breakpoint over all focal "
                f"moves in the survivor atk range."
            )
            lt.anchors[anchor_name] = DamageBreakpointAnchor(
                name=anchor_name,
                opponent=opp,
                description=description,
            )

    if "cmp" not in existing and survivor_ivs:
        # Dedupe IV tuples and compute effective attacks for the focal species.
        unique_ivs: list[tuple[int, int, int]] = []
        seen: set[tuple[int, int, int]] = set()
        for iv in survivor_ivs:
            t = (int(iv[0]), int(iv[1]), int(iv[2]))
            if t in seen:
                continue
            seen.add(t)
            unique_ivs.append(t)

        cohort_atks: list[float] = []
        for iv in unique_ivs:
            try:
                mon = Pokemon.at_best_level(
                    species, iv[0], iv[1], iv[2], league=league.lower(),
                )
            except (KeyError, ValueError):
                continue
            cohort_atks.append(mon.atk)

        if cohort_atks:
            cohort_atks.sort()
            # 75th percentile (lower-bound index): top quartile by atk.
            p75_idx = min(len(cohort_atks) - 1, int(0.75 * len(cohort_atks)))
            p75_threshold = cohort_atks[p75_idx]

            lt.spreads[AUTO_COHORT_SPREAD_NAME] = StatCutoffSpread(
                name=AUTO_COHORT_SPREAD_NAME,
                attack=p75_threshold,
                description=(
                    f"Auto-generated mirror cohort threshold: 75th-percentile "
                    f"effective attack ({p75_threshold:.2f}) over the "
                    f"converged survivor pool of {len(cohort_atks)} unique IVs."
                ),
            )
            lt.anchors["auto_cmp_vs_cohort"] = CmpAnchor(
                name="auto_cmp_vs_cohort",
                spread=AUTO_COHORT_SPREAD_NAME,
                strict=False,   # >=: top quartile by atk (including ties)
                description=(
                    "Auto-generated CMP anchor: focal effective attack in the "
                    "top quartile of the converged survivor pool. The focal "
                    "IV is a member of its own cohort, so 'strictly beat max' "
                    "is unreachable; top-quartile is the meaningful "
                    "interpretation."
                ),
            )

    if not lt.anchors:
        return ThresholdRegistry()

    sp = SpeciesThresholds(species=species, leagues={league_toml: lt})
    return ThresholdRegistry(by_species={species: sp})


# ---------------------------------------------------------------------------
# Public: tag an IV with the set of anchors it passes
# ---------------------------------------------------------------------------

def tag_iv(focal_atk: float,
           resolved: list[ResolvedAnchor]) -> dict[str, list[ResolvedAnchor]]:
    """Return the subset of resolved anchors the IV passes, grouped by parent.

    Returns a dict of {parent_name: [ResolvedAnchor, ...]}. A parent appears in
    the result only if at least one of its ResolvedAnchors passes.
    """
    out: dict[str, list[ResolvedAnchor]] = {}
    for r in resolved:
        if r.passes(focal_atk):
            out.setdefault(r.parent, []).append(r)
    return out
