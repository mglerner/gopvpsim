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

from .breakpoints import (
    atk_for_damage, breakpoints as scan_breakpoints,
    def_for_damage, bulkpoints as scan_bulkpoints,
)
from .data import load_gamemaster, parse_types
from .moves import damage as calc_damage, get_moves
from .pokemon import (
    LEAGUE_CAPS, SHADOW_ATK_BONUS, SHADOW_DEF_MULT,
    Pokemon, best_level, battle_stats, get_species, pvpoke_default_ivs,
)
from .thresholds import (
    BulkpointAnchor, CmpAnchor, DamageBreakpointAnchor, IvListSpread,
    LeagueThresholds, SpeciesThresholds, StatCutoffSpread, ThresholdRegistry,
)


# ---------------------------------------------------------------------------
# ResolvedAnchor
# ---------------------------------------------------------------------------

@dataclass
class ResolvedAnchor:
    """A concrete, numeric threshold check derived from a TOML anchor.

    Each ResolvedAnchor has exactly one threshold and one comparison. Level 3
    BP / bulkpoint anchors expand into multiple ResolvedAnchors with the same
    ``parent`` name and ``parent_display_name``.

    ``target_stat`` selects which focal stat is compared against
    ``threshold_value``. ``cmp`` and ``damage_breakpoint`` anchors target the
    focal *attack* (``"atk"``); ``bulkpoint`` anchors target the focal
    *defense* (``"def"``).
    """
    name: str                            # unique identifier
    parent: str                          # original TOML anchor name
    kind: str                            # "cmp" | "damage_breakpoint" | "bulkpoint"
    threshold_value: float               # focal stat must be > (or >=) this
    target_stat: str = "atk"             # "atk" or "def"
    strict: bool = True                  # True = strict `>`, False = `>=`
    label: str = ""                      # short human-readable label
    description: str = ""
    source: str = ""                     # expert attribution (e.g. "acidicArisen")
    parent_display_name: str = ""        # short HTML badge label for the parent

    # Extra metadata for damage_breakpoint / bulkpoint anchors:
    move_id: Optional[str] = None
    damage: Optional[int] = None
    opponent: Optional[str] = None

    def passes(self, focal_atk: float, focal_def: float) -> bool:
        v = focal_atk if self.target_stat == "atk" else focal_def
        if self.strict:
            return v > self.threshold_value
        return v >= self.threshold_value


# ---------------------------------------------------------------------------
# Display-name derivation
# ---------------------------------------------------------------------------

def derive_display_name(parent_name: str) -> str:
    """Derive a short HTML badge label from a TOML anchor name.

    Used as the fallback when a TOML anchor doesn't set ``display_name``
    explicitly. Rules applied in order; an ``auto_`` prefix is stripped first
    so auto-generated anchors get the same short labels as hand-written ones.

      auto_X           → X (then re-derive)
      cmp_vs_X         → cmp:X
      X_brkp_any       → X
      X_brkp_above_Y   → X↑Y
      X_brkp_Y         → X:Y
      X_blkp_any       → X bulk
      X_blkp_above_Y   → X bulk↑Y
      X_blkp_Y         → X bulk:Y
      (else)           → unchanged

    The ``brkp`` / ``blkp`` short forms are intentionally distinct: ``bp``
    would be ambiguous between *breakpoint* and *bulkpoint* now that both
    anchor kinds exist. Bulkpoint badges also get a trailing " bulk" so the
    two kinds are doubly distinguishable in the Bulk Slayer card (where they
    can appear together).

    Examples:
      cresselia_brkp_any            → cresselia
      lickitung_brkp_above_lurgan   → lickitung↑lurgan
      cmp_vs_lurgan                 → cmp:lurgan
      lickitung_brkp_counter_5      → lickitung:counter_5
      auto_lickitung_brkp_any       → lickitung
      auto_cmp_vs_cohort            → cmp:cohort
      mirror_blkp_any               → mirror bulk
      auto_lickitung_blkp_any       → lickitung bulk
      mirror_blkp_above_lurgan      → mirror bulk↑lurgan
    """
    from .display import pretty_species_from_slug

    name = parent_name
    if name.startswith("auto_"):
        name = name[len("auto_"):]
    if name.startswith("cmp_vs_"):
        return "cmp:" + name[len("cmp_vs_"):]
    # Head is always an opponent species slug; tail (after ``_brkp_`` /
    # ``_blkp_``) is usually a non-species identifier (spread name, move
    # token, "any") and stays as-is. The head goes through
    # ``pretty_species_from_slug`` so the anchor badge follows the same
    # "Shadow X" / "Galarian X" / "Oinkologne (Male)" convention used
    # everywhere else on the dive page.
    if name.endswith("_blkp_any"):
        head = name[: -len("_blkp_any")]
        return f"{pretty_species_from_slug(head)} bulk"
    if "_blkp_above_" in name:
        head, tail = name.split("_blkp_above_", 1)
        return f"{pretty_species_from_slug(head)} bulk\u2191{tail}"
    if "_blkp_" in name:
        head, tail = name.split("_blkp_", 1)
        return f"{pretty_species_from_slug(head)} bulk:{tail}"
    if name.endswith("_brkp_any"):
        return pretty_species_from_slug(name[: -len("_brkp_any")])
    if "_brkp_above_" in name:
        head, tail = name.split("_brkp_above_", 1)
        return f"{pretty_species_from_slug(head)}\u2191{tail}"
    if "_brkp_" in name:
        head, tail = name.split("_brkp_", 1)
        return f"{pretty_species_from_slug(head)}:{tail}"
    return name


def _opp_short(opp_slug: str) -> str:
    """Compress an opponent slug to a short, recognisable badge prefix.

    Rules:
      - Take the first 3 letters of the base species name (lowercased)
      - Append "s" if the species is the Shadow form
      - Append "g" if it's the Galarian form (similarly for other regional
        suffixes that survive in slug form)

    Examples:
      "lickitung"          -> "lic"
      "quagsire"           -> "qua"
      "quagsire_shadow"    -> "quas"
      "altaria_shadow"     -> "alts"
      "corsola_galarian"   -> "corg"
      "stunfisk_galarian"  -> "stug"
      "annihilape"         -> "ann"
      "mirror"             -> "mir"

    The result is intentionally lossy — the long form is preserved in the
    HTML hover tooltip and the filter panel.
    """
    s = opp_slug.lower()
    suffix = ""
    for tail, marker in (
        ("_shadow", "s"),
        ("_galarian", "g"),
        ("_alolan", "a"),
        ("_hisuian", "h"),
        ("_paldean", "p"),
    ):
        if s.endswith(tail):
            s = s[: -len(tail)]
            suffix = marker
            break
    return s[:3] + suffix


def derive_short_name(parent_name: str) -> str:
    """Derive an ULTRA-short HTML badge label for table cells.

    Used in survivor table tag cells where horizontal space is at a premium.
    Most badges land at 3-6 characters. The longer form (from
    ``derive_display_name``) is preserved in the hover tooltip and the
    filter panel so the abbreviation stays decipherable.

    Rules:
      auto_X            → X (then re-derive)
      cmp_vs_X          → c:<3-char-X>
      <opp>_brkp_any    → <opp_short>
      <opp>_brkp_above_<ref>  → <opp_short>↑<3-char-ref>
      <opp>_brkp_<tail>       → <opp_short>:<tail>
      <opp>_blkp_any    → <opp_short>b           (b suffix = bulkpoint)
      <opp>_blkp_above_<ref>  → <opp_short>b↑<3-char-ref>
      <opp>_blkp_<tail>       → <opp_short>b:<tail>
      (else)            → unchanged

    Examples:
      cresselia_brkp_any            → cre
      lickitung_brkp_above_lurgan   → lic↑lur
      cmp_vs_lurgan                 → c:lur
      auto_quagsire_shadow_brkp_any → quas
      mirror_blkp_any               → mirb
      mirror_blkp_above_lurgan      → mirb↑lur
      lickitung_blkp_any            → licb
    """
    name = parent_name
    if name.startswith("auto_"):
        name = name[len("auto_"):]
    if name.startswith("cmp_vs_"):
        return "c:" + name[len("cmp_vs_") :][:3]
    if name.endswith("_blkp_any"):
        return _opp_short(name[: -len("_blkp_any")]) + "b"
    if "_blkp_above_" in name:
        head, tail = name.split("_blkp_above_", 1)
        return f"{_opp_short(head)}b\u2191{tail[:3]}"
    if "_blkp_" in name:
        head, tail = name.split("_blkp_", 1)
        return f"{_opp_short(head)}b:{tail}"
    if name.endswith("_brkp_any"):
        return _opp_short(name[: -len("_brkp_any")])
    if "_brkp_above_" in name:
        head, tail = name.split("_brkp_above_", 1)
        return f"{_opp_short(head)}\u2191{tail[:3]}"
    if "_brkp_" in name:
        head, tail = name.split("_brkp_", 1)
        return f"{_opp_short(head)}:{tail}"
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
# Helper: opponent effective attack (for bulkpoint anchors)
# ---------------------------------------------------------------------------

def _opponent_atk_ref(
    opponent_species: str,
    league: str,
    *,
    ivs: Optional[tuple[int, int, int]] = None,
    shadow: bool = False,
) -> Optional[tuple[float, list[str]]]:
    """Return ``(effective_atk, types)`` for the opponent species under the
    given league, using either explicit IVs or PvPoke's defaults.

    The bulkpoint resolver uses this to compute the worst-case incoming damage
    against a focal defender — symmetric to ``_opponent_ref`` (which returns
    effective defense for the breakpoint resolver).

    Returns ``None`` if the opponent can't be resolved (not in gamemaster,
    can't fit under the CP cap, etc.).
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
    return (mon.atk, types)


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
        threshold_value=threshold,
        target_stat="atk",
        strict=anchor.strict,
        label=anchor.name,
        description=anchor.description,
        source=anchor.source,
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
            threshold_value=threshold,
            target_stat="atk",
            strict=False,   # >=: "deals at least N"
            label=label,
            description=anchor.description,
            source=anchor.source,
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
            threshold_value=threshold,
            target_stat="atk",
            strict=False,
            label=label,
            description=anchor.description,
            source=anchor.source,
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
                threshold_value=bp.atk_threshold,
                target_stat="atk",
                strict=False,
                label=label,
                description=anchor.description,
                source=anchor.source,
                parent_display_name=parent_display,
                move_id=move['moveId'],
                damage=bp.damage,
                opponent=anchor.opponent,
            ))
    return resolved


# ---------------------------------------------------------------------------
# Bulkpoint anchor resolution
# ---------------------------------------------------------------------------

def _select_moves_bulk(anchor: BulkpointAnchor,
                       focal_moves: list[dict]) -> list[dict]:
    """Filter focal_moves according to the bulkpoint anchor's move / moves field.

    Note: focal_moves here is the *opponent's threat moves* — the moves we're
    measuring incoming damage from. The deep_dive caller passes the focal
    species' own movepool because the bulkpoint sweep examines "what does
    this opponent's moves do to the focal", and we look up the opponent's
    threat moves separately. In practice the resolver pulls the opponent's
    fast + charged moves from the gamemaster (see _resolve_bulkpoint_anchor).
    """
    if anchor.move is not None:
        return [m for m in focal_moves if m['moveId'] == anchor.move]
    if anchor.moves is not None:
        allowed = set(anchor.moves)
        return [m for m in focal_moves if m['moveId'] in allowed]
    return list(focal_moves)


def _opponent_threat_moves(opponent_species: str) -> list[dict]:
    """Return the union of fast + charged move dicts for an opponent species.

    Used by the bulkpoint resolver as the set of incoming threat moves to scan.
    Returns an empty list if the species or any move can't be resolved.
    """
    gm = load_gamemaster()
    entry = next((m for m in gm['pokemon']
                  if m['speciesName'] == opponent_species), None)
    if entry is None:
        return []
    fast_db, charged_db = get_moves()
    out: list[dict] = []
    for mid in entry.get('fastMoves', []):
        mv = fast_db.get(mid)
        if mv is not None:
            out.append(mv)
    for mid in entry.get('chargedMoves', []):
        mv = charged_db.get(mid)
        if mv is not None:
            out.append(mv)
    return out


def _resolve_bulkpoint_anchor(
    anchor: BulkpointAnchor,
    registry: ThresholdRegistry,
    species: str,
    league_lower: str,
    league_toml: str,
    focal_types: list[str],
    def_min: float,
    def_max: float,
) -> list[ResolvedAnchor]:
    """Resolve a bulkpoint anchor into one or more ResolvedAnchors.

    Symmetric to ``_resolve_bp_anchor`` but on the def side. Computes the
    opponent's effective attack (worst-case via opponent_spread → max-atk
    member, or pinned via opponent_ivs), then for each candidate threat move
    finds the def thresholds at which incoming damage steps down.

    Returns an empty list if the caller didn't supply a usable focal def
    range (``def_max <= def_min`` or ``def_min == 0``). This lets call sites
    that don't care about bulkpoint anchors omit the def range without
    crashing — the bulkpoint scan needs strictly positive defenses to avoid
    a divide-by-zero in the damage formula.
    """
    if def_max <= def_min or def_min <= 0:
        return []

    # Resolve opponent reference IVs (if a spread was given, pick max-atk).
    opp_ivs = anchor.opponent_ivs
    if opp_ivs is None and anchor.opponent_spread is not None:
        opp_spread = registry.get_spread(species, league_toml, anchor.opponent_spread)
        if isinstance(opp_spread, IvListSpread) and opp_spread.ivs:
            best_atk = None
            best_iv = None
            for iv in opp_spread.ivs:
                try:
                    mon = Pokemon.at_best_level(
                        anchor.opponent, iv[0], iv[1], iv[2], league=league_lower,
                    )
                except (KeyError, ValueError):
                    continue
                if best_atk is None or mon.atk > best_atk:
                    best_atk = mon.atk
                    best_iv = iv
            opp_ivs = best_iv

    opp = _opponent_atk_ref(anchor.opponent, league_lower, ivs=opp_ivs)
    if opp is None:
        return []
    opp_atk, opp_types = opp

    # Threat moves come from the opponent's movepool, then filtered by the
    # anchor's move / moves field.
    threat_moves = _opponent_threat_moves(anchor.opponent)
    moves = _select_moves_bulk(anchor, threat_moves)
    if not moves:
        return []

    level = anchor.level
    parent_display = anchor.display_name or derive_display_name(anchor.name)

    if level == 1:
        # Exactly one move with takes_at_most set. The smallest def at which
        # damage drops to ≤ takes_at_most is def_for_damage(takes_at_most+1, ...)
        # — that's the threshold strictly above which incoming damage is at
        # most takes_at_most. We use strict (>) comparison.
        move = moves[0]
        threshold = def_for_damage(
            anchor.takes_at_most + 1, opp_atk, move, opp_types, focal_types,
        )
        label = f"{move['moveId'].lower()}\u2264{anchor.takes_at_most}"
        return [ResolvedAnchor(
            name=anchor.name,
            parent=anchor.name,
            kind="bulkpoint",
            threshold_value=threshold,
            target_stat="def",
            strict=True,   # def > threshold → damage <= takes_at_most
            label=label,
            description=anchor.description,
            source=anchor.source,
            parent_display_name=parent_display,
            move_id=move['moveId'],
            damage=anchor.takes_at_most,
            opponent=anchor.opponent,
        )]

    if level == 2:
        # Find the smallest def > above_def at which ANY threat move's damage
        # to the focal steps DOWN. Scan each threat move and pick the earliest.
        best = None  # (threshold, move, new_dmg)
        for move in moves:
            bps = scan_bulkpoints(
                move, opp_atk, opp_types, focal_types, anchor.above_def, def_max,
            )
            for bp in bps:
                if bp.def_threshold > anchor.above_def:
                    if best is None or bp.def_threshold < best[0]:
                        best = (bp.def_threshold, move, bp.damage)
                    break
        if best is None:
            return []
        threshold, move, dmg = best
        label = f"{move['moveId'].lower()}\u2264{dmg}"
        return [ResolvedAnchor(
            name=anchor.name,
            parent=anchor.name,
            kind="bulkpoint",
            threshold_value=threshold,
            target_stat="def",
            strict=True,
            label=label,
            description=anchor.description,
            source=anchor.source,
            parent_display_name=parent_display,
            move_id=move['moveId'],
            damage=dmg,
            opponent=anchor.opponent,
        )]

    # Level 3: enumerate every bulkpoint for every threat move in the def range.
    resolved: list[ResolvedAnchor] = []
    for move in moves:
        bps = scan_bulkpoints(move, opp_atk, opp_types, focal_types,
                              def_min, def_max)
        for bp in bps:
            move_slug = move['moveId'].lower()
            label = f"{move_slug}\u2264{bp.damage}"
            sub_name = f"{anchor.name}::{label}"
            resolved.append(ResolvedAnchor(
                name=sub_name,
                parent=anchor.name,
                kind="bulkpoint",
                threshold_value=bp.def_threshold,
                target_stat="def",
                strict=True,
                label=label,
                description=anchor.description,
                source=anchor.source,
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
    def_min: float = 0.0,
    def_max: float = 0.0,
    focal_shadow: bool = False,
) -> list[ResolvedAnchor]:
    """Resolve every anchor for (species, league) into concrete threshold checks.

    focal_moves: list of move dicts as returned by get_moves()[0] / [1] for the
      specific moveset being analyzed. Each dict must have 'moveId', 'power',
      and 'type' fields. Used for damage_breakpoint resolution; bulkpoint
      anchors instead pull the *opponent's* threat moves from the gamemaster.
    focal_types: list of focal species type strings (e.g. ['fighting', 'ghost']).
    atk_min, atk_max: the survivor atk range (used for Level 3 BP enumeration).
    def_min, def_max: the survivor def range (used for Level 3 bulkpoint
      enumeration). Defaults to 0/0; pass real values when bulkpoint anchors
      are present.
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
        elif isinstance(anchor, BulkpointAnchor):
            resolved.extend(_resolve_bulkpoint_anchor(
                anchor, registry, species, league_lower, league_toml,
                focal_types, def_min, def_max,
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

    Auto-Bulk-Slayer (one Level 3 ``bulkpoint`` anchor per opponent):
        Fires when ``"bulkpoint" not in existing_anchor_kinds`` and
        ``opponent_species`` is non-empty. For each opponent, creates a bare
        Level 3 ``BulkpointAnchor`` named ``auto_<opponent_lower>_blkp_any``
        enumerating every bulkpoint over all of the opponent's threat moves
        in the survivor def range. Independent of the BP/CMP gates so a TOML
        with only damage_breakpoint anchors still gets bulkpoint coverage.

    Auto-Atk-Slayer (one Level 3 ``damage_breakpoint`` anchor per opponent):
        Fires when ``"damage_breakpoint" not in existing_anchor_kinds``.
        For each species name in ``opponent_species``, creates a bare
        Level 3 anchor named ``auto_<opponent_lower>_brkp_any`` enumerating
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
            anchor_name = f"auto_{slug}_brkp_any"
            description = (
                f"Auto-generated Level 3 breakpoint anchor against {opp}. "
                f"Enumerates every (move, tier) breakpoint over all focal "
                f"moves in the survivor atk range."
            )
            lt.anchors[anchor_name] = DamageBreakpointAnchor(
                name=anchor_name,
                opponent=opp,
                description=description,
            )

    if "bulkpoint" not in existing and opponent_species:
        seen_opponents_blkp: set[str] = set()
        for opp in opponent_species:
            if opp in seen_opponents_blkp:
                continue
            seen_opponents_blkp.add(opp)
            slug = opp.lower().replace(' ', '_').replace('(', '').replace(')', '')
            anchor_name = f"auto_{slug}_blkp_any"
            description = (
                f"Auto-generated Level 3 bulkpoint anchor against {opp}. "
                f"Enumerates every (move, tier) bulkpoint over all of the "
                f"opponent's threat moves in the survivor def range."
            )
            lt.anchors[anchor_name] = BulkpointAnchor(
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

def tag_iv(focal_atk: float, focal_def: float,
           resolved: list[ResolvedAnchor]) -> dict[str, list[ResolvedAnchor]]:
    """Return the subset of resolved anchors the IV passes, grouped by parent.

    Returns a dict of ``{parent_name: [ResolvedAnchor, ...]}``. A parent appears
    in the result only if at least one of its ResolvedAnchors passes. Both the
    focal effective attack and defense must be supplied so atk-side anchors
    (cmp, damage_breakpoint) and def-side anchors (bulkpoint) can be evaluated
    in the same call.
    """
    out: dict[str, list[ResolvedAnchor]] = {}
    for r in resolved:
        if r.passes(focal_atk, focal_def):
            out.setdefault(r.parent, []).append(r)
    return out
