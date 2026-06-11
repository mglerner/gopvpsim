"""
Threshold file loader: spreads and anchors for deep-dive categorization.

Reads TOML files matching the schema in docs/threshold_schema.md. Legacy JSON
files (flat {name: {attack, defense, stamina}} format) are also loaded via
`load_legacy_json` and wrapped in a SpeciesThresholds under a caller-provided
league.

Pure data layer — no species lookups, move calculations, or damage formulas
happen here. Anchor resolution into numeric thresholds happens elsewhere, once
the focal species context (moves, types, level, league) is known.
"""
from __future__ import annotations

import json
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union


# ---------------------------------------------------------------------------
# Spread types
# ---------------------------------------------------------------------------

@dataclass
class StatCutoffSpread:
    """A spread described by minimum effective-stat values.

    An IV belongs to this spread iff its effective (atk, def, hp) all meet or
    exceed the corresponding minimum. A value of 0 means "no constraint on this
    stat."
    """
    name: str
    attack: float = 0.0
    defense: float = 0.0
    stamina: float = 0.0
    description: str = ""
    source: str = ""
    deprecated: bool = False

    def contains(self, atk: float, def_: float, hp: int) -> bool:
        if self.attack > 0 and atk < self.attack:
            return False
        if self.defense > 0 and def_ < self.defense:
            return False
        if self.stamina > 0 and hp < self.stamina:
            return False
        return True


@dataclass
class IvListSpread:
    """A spread described by an explicit list of (atk_iv, def_iv, sta_iv) tuples.

    An IV belongs to this spread iff its IV triple is a member of the list.
    """
    name: str
    ivs: tuple[tuple[int, int, int], ...]
    description: str = ""
    source: str = ""
    deprecated: bool = False

    def contains(self, atk_iv: int, def_iv: int, sta_iv: int) -> bool:
        return (atk_iv, def_iv, sta_iv) in self.ivs


Spread = Union[StatCutoffSpread, IvListSpread]


# ---------------------------------------------------------------------------
# Anchor types
# ---------------------------------------------------------------------------

@dataclass
class CmpAnchor:
    """CMP anchor: focal_atk > (or >=) the max effective atk of a named spread.

    The spread reference is resolved against the registry at anchor-resolution
    time. The comparison is strict by default (`>`), configurable to `>=` via
    the `strict` field.
    """
    name: str
    spread: str                       # name of a spread (possibly qualified)
    strict: bool = True
    description: str = ""
    source: str = ""
    display_name: Optional[str] = None  # short label for HTML badges; auto-derived if None

    @property
    def kind(self) -> str:
        return "cmp"


@dataclass
class DamageBreakpointAnchor:
    """Damage-breakpoint anchor: focal clears a damage tier against a named opponent.

    Three precision levels, determined by which fields are set:
      Level 1 (fully explicit): `move` AND `deals_at_least`
      Level 2 (reference-anchored): `above_atk` (optionally with `move`)
      Level 3 (discover-and-tag): none of the above; optionally `moves` filter

    Opponent defense is computed from `opponent_ivs` or `opponent_spread` if
    provided; otherwise from the league's default IVs for the opponent species.
    """
    name: str
    opponent: str
    # Level 1 fields:
    move: Optional[str] = None
    deals_at_least: Optional[int] = None
    # Level 2 field:
    above_atk: Optional[float] = None
    # Level 3 field (optional):
    moves: Optional[tuple[str, ...]] = None
    # Opponent reference defense:
    opponent_ivs: Optional[tuple[int, int, int]] = None
    opponent_spread: Optional[str] = None
    description: str = ""
    source: str = ""
    display_name: Optional[str] = None  # short label for HTML badges; auto-derived if None

    @property
    def kind(self) -> str:
        return "damage_breakpoint"

    @property
    def level(self) -> int:
        if self.move is not None and self.deals_at_least is not None:
            return 1
        if self.above_atk is not None:
            return 2
        return 3


@dataclass
class BulkpointAnchor:
    """Bulkpoint anchor: focal *defense* clears a damage tier against a named opponent.

    Symmetric to ``DamageBreakpointAnchor`` but on the def side. Three precision
    levels, determined by which fields are set:
      Level 1 (fully explicit): ``move`` AND ``takes_at_most``
      Level 2 (reference-anchored): ``above_def`` (optionally with ``move``)
      Level 3 (discover-and-tag): none of the above; optionally ``moves`` filter

    Opponent attack is computed from ``opponent_ivs`` or ``opponent_spread`` if
    provided; otherwise from the league's default IVs for the opponent species.
    When ``opponent_spread`` is an IV-list spread, the *highest-attack* member is
    used (worst case for the focal — symmetric to how DamageBreakpointAnchor
    picks the bulkiest member of a defender spread). Pin a specific
    representative with ``opponent_ivs`` if max-atk is not what you want.
    """
    name: str
    opponent: str
    # Level 1 fields:
    move: Optional[str] = None
    takes_at_most: Optional[int] = None
    # Level 2 field:
    above_def: Optional[float] = None
    # Level 3 field (optional):
    moves: Optional[tuple[str, ...]] = None
    # Opponent reference attack:
    opponent_ivs: Optional[tuple[int, int, int]] = None
    opponent_spread: Optional[str] = None
    description: str = ""
    source: str = ""
    display_name: Optional[str] = None  # short label for HTML badges; auto-derived if None

    @property
    def kind(self) -> str:
        return "bulkpoint"

    @property
    def level(self) -> int:
        if self.move is not None and self.takes_at_most is not None:
            return 1
        if self.above_def is not None:
            return 2
        return 3


Anchor = Union[CmpAnchor, DamageBreakpointAnchor, BulkpointAnchor]


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------

@dataclass
class LeagueThresholds:
    league: str
    spreads: dict[str, Spread] = field(default_factory=dict)
    anchors: dict[str, Anchor] = field(default_factory=dict)
    meta: dict[str, str] = field(default_factory=dict)


@dataclass
class SpeciesThresholds:
    species: str
    sources: str = ""
    leagues: dict[str, LeagueThresholds] = field(default_factory=dict)

    def league(self, name: str) -> Optional[LeagueThresholds]:
        return self.leagues.get(name)


@dataclass
class ThresholdRegistry:
    """All loaded species plus the shared cross-species bucket.

    The shared bucket lives under `by_species["shared"]` as a pseudo-species.
    Lookups that can't find a name on a species fall back to shared.
    """
    by_species: dict[str, SpeciesThresholds] = field(default_factory=dict)

    def species(self, name: str) -> Optional[SpeciesThresholds]:
        return self.by_species.get(name)

    def get_spread(self, species: str, league: str, name: str) -> Optional[Spread]:
        """Resolve a spread name: try the species first, then shared."""
        for bucket in (species, "shared"):
            sp = self.by_species.get(bucket)
            if sp is None:
                continue
            lt = sp.leagues.get(league)
            if lt is None:
                continue
            if name in lt.spreads:
                return lt.spreads[name]
        return None

    def get_anchor(self, species: str, league: str, name: str) -> Optional[Anchor]:
        for bucket in (species, "shared"):
            sp = self.by_species.get(bucket)
            if sp is None:
                continue
            lt = sp.leagues.get(league)
            if lt is None:
                continue
            if name in lt.anchors:
                return lt.anchors[name]
        return None

    def merge(self, overlay: "ThresholdRegistry") -> "ThresholdRegistry":
        """Return a new registry with `overlay` merged on top of self.

        Merge semantics: overlay wins on collision at the spread/anchor level,
        not at the species level (so overlaying a new anchor on Annihilape does
        not wipe out existing Annihilape spreads). Shared-bucket entries merge
        the same way.
        """
        out = ThresholdRegistry()
        # Start with a deep-ish copy of self
        for sp_name, sp in self.by_species.items():
            out.by_species[sp_name] = SpeciesThresholds(
                species=sp.species,
                sources=sp.sources,
                leagues={
                    ln: LeagueThresholds(
                        league=lt.league,
                        spreads=dict(lt.spreads),
                        anchors=dict(lt.anchors),
                        meta=dict(lt.meta),
                    )
                    for ln, lt in sp.leagues.items()
                },
            )
        # Apply overlay
        for sp_name, sp in overlay.by_species.items():
            dst_sp = out.by_species.get(sp_name)
            if dst_sp is None:
                # New species — copy wholesale
                out.by_species[sp_name] = SpeciesThresholds(
                    species=sp.species,
                    sources=sp.sources,
                    leagues={
                        ln: LeagueThresholds(
                            league=lt.league,
                            spreads=dict(lt.spreads),
                            anchors=dict(lt.anchors),
                            meta=dict(lt.meta),
                        )
                        for ln, lt in sp.leagues.items()
                    },
                )
                continue
            # Merge leagues
            if sp.sources:
                dst_sp.sources = sp.sources  # overlay wins on sources too
            for ln, lt in sp.leagues.items():
                dst_lt = dst_sp.leagues.get(ln)
                if dst_lt is None:
                    dst_sp.leagues[ln] = LeagueThresholds(
                        league=lt.league,
                        spreads=dict(lt.spreads),
                        anchors=dict(lt.anchors),
                        meta=dict(lt.meta),
                    )
                    continue
                dst_lt.spreads.update(lt.spreads)
                dst_lt.anchors.update(lt.anchors)
                dst_lt.meta.update(lt.meta)
        return out


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

class ThresholdError(ValueError):
    """Raised when a threshold file fails validation."""
    pass


def _require(cond: bool, msg: str, *, path: str) -> None:
    if not cond:
        raise ThresholdError(f"{path}: {msg}")


def _iv_tuple(raw, *, path: str) -> tuple[int, int, int]:
    _require(
        isinstance(raw, (list, tuple)) and len(raw) == 3,
        f"expected 3-element IV array, got {raw!r}",
        path=path,
    )
    out = []
    for i, v in enumerate(raw):
        _require(
            isinstance(v, int) and 0 <= v <= 15,
            f"IV component [{i}] must be int in 0..15, got {v!r}",
            path=path,
        )
        out.append(int(v))
    return (out[0], out[1], out[2])


def _parse_spread(name: str, raw: dict, *, path: str) -> Spread:
    description = raw.get("description", "")
    source = raw.get("source", "")
    deprecated = bool(raw.get("deprecated", False))

    has_ivs = "ivs" in raw
    has_stat = any(k in raw for k in ("attack", "defense", "stamina"))

    _require(
        has_ivs ^ has_stat,
        f"spread {name!r} must have either 'ivs' or stat-cutoff "
        f"fields (attack/defense/stamina), not both and not neither",
        path=path,
    )

    if has_ivs:
        raw_ivs = raw["ivs"]
        _require(
            isinstance(raw_ivs, (list, tuple)) and len(raw_ivs) > 0,
            f"spread {name!r} 'ivs' must be a non-empty list",
            path=path,
        )
        ivs = tuple(_iv_tuple(entry, path=f"{path}:{name}.ivs[{i}]")
                    for i, entry in enumerate(raw_ivs))
        return IvListSpread(
            name=name, ivs=ivs,
            description=description, source=source, deprecated=deprecated,
        )

    # Stat-cutoff form
    def _num(key: str) -> float:
        v = raw.get(key, 0)
        _require(
            isinstance(v, (int, float)),
            f"spread {name!r}.{key} must be a number, got {v!r}",
            path=path,
        )
        return float(v)

    return StatCutoffSpread(
        name=name,
        attack=_num("attack"),
        defense=_num("defense"),
        stamina=_num("stamina"),
        description=description, source=source, deprecated=deprecated,
    )


def _parse_bulkpoint_anchor(
    name: str, raw: dict, *, path: str, description: str, source: str = "",
) -> "BulkpointAnchor":
    """Parse a bulkpoint anchor — symmetric to the damage_breakpoint branch."""
    opponent = raw.get("opponent")
    _require(
        isinstance(opponent, str) and opponent,
        f"bulkpoint anchor {name!r} must have an 'opponent' field",
        path=path,
    )

    move = raw.get("move")
    takes_at_most = raw.get("takes_at_most")
    above_def = raw.get("above_def")
    moves = raw.get("moves")
    opponent_ivs_raw = raw.get("opponent_ivs")
    opponent_spread = raw.get("opponent_spread")

    if move is not None:
        _require(isinstance(move, str), f"{name}.move must be a string", path=path)
    if takes_at_most is not None:
        _require(isinstance(takes_at_most, int),
                 f"{name}.takes_at_most must be an int", path=path)
    if above_def is not None:
        _require(isinstance(above_def, (int, float)),
                 f"{name}.above_def must be a number", path=path)
        above_def = float(above_def)
    if moves is not None:
        _require(
            isinstance(moves, (list, tuple)) and all(isinstance(m, str) for m in moves),
            f"{name}.moves must be a list of strings",
            path=path,
        )
        moves = tuple(moves)

    # Mutual exclusion: takes_at_most ⇔ Level 1, above_def ⇔ Level 2.
    _require(
        not (takes_at_most is not None and above_def is not None),
        f"bulkpoint anchor {name!r} cannot specify both "
        f"'takes_at_most' (Level 1) and 'above_def' (Level 2)",
        path=path,
    )
    if takes_at_most is not None:
        _require(
            move is not None,
            f"bulkpoint anchor {name!r} specifies 'takes_at_most' "
            f"(Level 1) but no 'move' — both are required",
            path=path,
        )
    if moves is not None:
        _require(
            move is None and takes_at_most is None and above_def is None,
            f"bulkpoint anchor {name!r} 'moves' filter is only "
            f"valid in Level 3 (no 'move'/'takes_at_most'/'above_def')",
            path=path,
        )

    _require(
        not (opponent_ivs_raw is not None and opponent_spread is not None),
        f"bulkpoint anchor {name!r} cannot specify both "
        f"'opponent_ivs' and 'opponent_spread'",
        path=path,
    )
    opponent_ivs = None
    if opponent_ivs_raw is not None:
        opponent_ivs = _iv_tuple(opponent_ivs_raw, path=f"{path}:{name}.opponent_ivs")
    if opponent_spread is not None:
        _require(isinstance(opponent_spread, str),
                 f"{name}.opponent_spread must be a string", path=path)

    display_name = raw.get("display_name")
    if display_name is not None:
        _require(isinstance(display_name, str),
                 f"{name}.display_name must be a string", path=path)

    return BulkpointAnchor(
        name=name,
        opponent=opponent,
        move=move,
        takes_at_most=takes_at_most,
        above_def=above_def,
        moves=moves,
        opponent_ivs=opponent_ivs,
        opponent_spread=opponent_spread,
        description=description,
        source=source,
        display_name=display_name,
    )


def _parse_anchor(name: str, raw: dict, *, path: str) -> Anchor:
    kind = raw.get("kind")
    _require(
        kind in ("cmp", "damage_breakpoint", "bulkpoint"),
        f"anchor {name!r} has unknown or missing kind {kind!r} "
        f"(expected 'cmp', 'damage_breakpoint', or 'bulkpoint')",
        path=path,
    )
    description = raw.get("description", "")
    source = raw.get("source", "")

    if kind == "cmp":
        spread = raw.get("spread")
        _require(
            isinstance(spread, str) and spread,
            f"cmp anchor {name!r} must have a 'spread' field (string)",
            path=path,
        )
        strict = raw.get("strict", True)
        _require(
            isinstance(strict, bool),
            f"cmp anchor {name!r}.strict must be bool, got {strict!r}",
            path=path,
        )
        display_name = raw.get("display_name")
        if display_name is not None:
            _require(isinstance(display_name, str),
                     f"{name}.display_name must be a string", path=path)
        return CmpAnchor(name=name, spread=spread, strict=strict,
                         description=description, source=source,
                         display_name=display_name)

    if kind == "bulkpoint":
        return _parse_bulkpoint_anchor(name, raw, path=path,
                                       description=description, source=source)

    # damage_breakpoint
    opponent = raw.get("opponent")
    _require(
        isinstance(opponent, str) and opponent,
        f"damage_breakpoint anchor {name!r} must have an 'opponent' field",
        path=path,
    )

    move = raw.get("move")
    deals_at_least = raw.get("deals_at_least")
    above_atk = raw.get("above_atk")
    moves = raw.get("moves")
    opponent_ivs_raw = raw.get("opponent_ivs")
    opponent_spread = raw.get("opponent_spread")

    # Normalize move field types
    if move is not None:
        _require(isinstance(move, str), f"{name}.move must be a string", path=path)
    if deals_at_least is not None:
        _require(isinstance(deals_at_least, int),
                 f"{name}.deals_at_least must be an int", path=path)
    if above_atk is not None:
        _require(isinstance(above_atk, (int, float)),
                 f"{name}.above_atk must be a number", path=path)
        above_atk = float(above_atk)
    if moves is not None:
        _require(
            isinstance(moves, (list, tuple)) and all(isinstance(m, str) for m in moves),
            f"{name}.moves must be a list of strings",
            path=path,
        )
        moves = tuple(moves)

    # Mutual exclusion: deals_at_least implies Level 1, above_atk implies Level 2.
    # Can't specify both.
    _require(
        not (deals_at_least is not None and above_atk is not None),
        f"damage_breakpoint anchor {name!r} cannot specify both "
        f"'deals_at_least' (Level 1) and 'above_atk' (Level 2)",
        path=path,
    )
    # Level 1 needs both move and deals_at_least
    if deals_at_least is not None:
        _require(
            move is not None,
            f"damage_breakpoint anchor {name!r} specifies 'deals_at_least' "
            f"(Level 1) but no 'move' — both are required",
            path=path,
        )
    # moves filter is only meaningful in Level 3 (no specific move/tier/above_atk)
    if moves is not None:
        _require(
            move is None and deals_at_least is None and above_atk is None,
            f"damage_breakpoint anchor {name!r} 'moves' filter is only "
            f"valid in Level 3 (no 'move'/'deals_at_least'/'above_atk')",
            path=path,
        )

    # Opponent ref def: mutually exclusive
    _require(
        not (opponent_ivs_raw is not None and opponent_spread is not None),
        f"damage_breakpoint anchor {name!r} cannot specify both "
        f"'opponent_ivs' and 'opponent_spread'",
        path=path,
    )
    opponent_ivs = None
    if opponent_ivs_raw is not None:
        opponent_ivs = _iv_tuple(opponent_ivs_raw, path=f"{path}:{name}.opponent_ivs")
    if opponent_spread is not None:
        _require(isinstance(opponent_spread, str),
                 f"{name}.opponent_spread must be a string", path=path)

    display_name = raw.get("display_name")
    if display_name is not None:
        _require(isinstance(display_name, str),
                 f"{name}.display_name must be a string", path=path)

    return DamageBreakpointAnchor(
        name=name,
        opponent=opponent,
        move=move,
        deals_at_least=deals_at_least,
        above_atk=above_atk,
        moves=moves,
        opponent_ivs=opponent_ivs,
        opponent_spread=opponent_spread,
        description=description,
        source=source,
        display_name=display_name,
    )


def _parse_league_table(raw: dict, *, path: str, league_name: str) -> LeagueThresholds:
    lt = LeagueThresholds(league=league_name)

    spreads_raw = raw.get("spreads", {})
    _require(isinstance(spreads_raw, dict),
             f"{league_name}.spreads must be a table", path=path)
    for sname, sraw in spreads_raw.items():
        _require(isinstance(sraw, dict),
                 f"spread {sname!r} must be a table", path=path)
        lt.spreads[sname] = _parse_spread(sname, sraw, path=path)

    anchors_raw = raw.get("anchors", {})
    _require(isinstance(anchors_raw, dict),
             f"{league_name}.anchors must be a table", path=path)
    for aname, araw in anchors_raw.items():
        _require(isinstance(araw, dict),
                 f"anchor {aname!r} must be a table", path=path)
        lt.anchors[aname] = _parse_anchor(aname, araw, path=path)

    meta_raw = raw.get("meta", {})
    _require(isinstance(meta_raw, dict),
             f"{league_name}.meta must be a table", path=path)
    lt.meta = {k: str(v) for k, v in meta_raw.items()}

    return lt


_KNOWN_LEAGUE_NAMES = {"Little", "Great", "Ultra", "Master"}


def _parse_species_table(name: str, raw: dict, *, path: str) -> SpeciesThresholds:
    sp = SpeciesThresholds(species=name)
    sources = raw.get("sources", "")
    _require(isinstance(sources, str),
             f"{name}.sources must be a string", path=path)
    sp.sources = sources

    for key, val in raw.items():
        if key == "sources":
            continue
        if not isinstance(val, dict):
            continue
        # Leagues are any sub-tables whose names match the known list OR any
        # sub-table that contains 'spreads'/'anchors'/'meta'. We lean permissive
        # so future leagues (e.g., 'Little') work without a schema change.
        if key in _KNOWN_LEAGUE_NAMES or any(
            k in val for k in ("spreads", "anchors", "meta")
        ):
            # Normalize case-variant league keys: the resolver only ever
            # queries the canonical capitalization, so '[Tinkaton.great]'
            # used to parse fine and then silently never resolve a single
            # anchor — the worst kind of authoring typo.
            canon = key.capitalize()
            if canon != key and canon in _KNOWN_LEAGUE_NAMES:
                key = canon
            sp.leagues[key] = _parse_league_table(val, path=path, league_name=key)

    return sp


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------

def load_toml(path: str | Path) -> ThresholdRegistry:
    """Load a TOML threshold file and return a ThresholdRegistry."""
    path = Path(path)
    with open(path, "rb") as f:
        data = tomllib.load(f)

    registry = ThresholdRegistry()
    for top_key, top_val in data.items():
        if not isinstance(top_val, dict):
            continue
        sp = _parse_species_table(top_key, top_val, path=str(path))
        registry.by_species[top_key] = sp
    return registry


def load_legacy_json(path: str | Path, *, species: str,
                     league: str = "Great") -> ThresholdRegistry:
    """Load a legacy JSON threshold file (flat {name: {attack, defense, stamina}}).

    Wraps the entries as stat-cutoff spreads under a synthetic species/league.
    Produces no anchors — the legacy format has no anchor concept.
    """
    path = Path(path)
    with open(path) as f:
        data = json.load(f)

    lt = LeagueThresholds(league=league)
    for name, thresh in data.items():
        if not isinstance(thresh, dict):
            raise ThresholdError(
                f"{path}: legacy entry {name!r} must be an object"
            )
        for key in ("attack", "defense", "stamina"):
            if key not in thresh:
                raise ThresholdError(
                    f"{path}: legacy entry {name!r} missing key {key!r}"
                )
        lt.spreads[name] = StatCutoffSpread(
            name=name,
            attack=float(thresh["attack"]),
            defense=float(thresh["defense"]),
            stamina=float(thresh["stamina"]),
        )

    sp = SpeciesThresholds(species=species, leagues={league: lt})
    registry = ThresholdRegistry(by_species={species: sp})
    return registry


def load_file(path: str | Path, *, species: Optional[str] = None,
              league: str = "Great") -> ThresholdRegistry:
    """Load a threshold file, auto-detecting TOML vs JSON by extension.

    For legacy JSON files, `species` is required (used as the top-level key in
    the returned registry).
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".toml":
        return load_toml(path)
    if suffix == ".json":
        if species is None:
            raise ThresholdError(
                f"{path}: loading legacy JSON requires an explicit species name"
            )
        return load_legacy_json(path, species=species, league=league)
    raise ThresholdError(
        f"{path}: unrecognized extension {suffix!r} (expected .toml or .json)"
    )


# ---------------------------------------------------------------------------
# Legacy flat-dict adapter
# ---------------------------------------------------------------------------

def as_legacy_dict(registry: ThresholdRegistry, species: str,
                   league: str = "Great") -> dict:
    """Flatten the stat-cutoff spreads of one species/league into the legacy
    `{name: {attack, defense, stamina}}` dict format, so existing tier-coloring
    code paths (classify_iv, generate_html tier rendering) keep working.

    IV-list spreads are *skipped* — they can't be represented as stat cutoffs.
    Callers that need IV-list membership should use the registry directly.
    """
    sp = registry.species(species)
    if sp is None:
        return {}
    lt = sp.league(league)
    if lt is None:
        return {}
    out: dict[str, dict] = {}
    for name, spread in lt.spreads.items():
        if isinstance(spread, StatCutoffSpread):
            out[name] = {
                "attack": spread.attack,
                "defense": spread.defense,
                "stamina": spread.stamina,
                "source": spread.source,
                "description": spread.description,
            }
    return out


# ---------------------------------------------------------------------------
# Inline anchor-spec parser (for --anchor CLI flag)
# ---------------------------------------------------------------------------

def parse_inline_anchor(spec: str) -> tuple[str, Anchor]:
    """Parse an inline --anchor spec of the form
        "name:key=value,key=value,..."
    Returns (name, anchor). Raises ThresholdError on malformed input.

    Supported keys mirror the TOML schema. Special encodings:
      - ivs=15/3/2;15/2/4;...   (for inline cmp anchor cohorts; see below)
      - moves=COUNTER;LOW_KICK  (semicolons, to avoid colliding with comma field separator)
      - opponent_ivs=0/15/15

    For inline cmp anchors, the `ivs=` value encodes a throwaway anonymous
    spread injected under a generated name, and the anchor's `spread` field is
    set to point at it. The caller (CLI glue) is responsible for adding the
    anonymous spread to the registry before resolving the anchor.
    """
    if ":" not in spec:
        raise ThresholdError(
            f"--anchor spec missing name: expected 'name:key=value,...', got {spec!r}"
        )
    name, body = spec.split(":", 1)
    name = name.strip()
    if not name:
        raise ThresholdError(f"--anchor spec has empty name in {spec!r}")

    fields: dict[str, object] = {}
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ThresholdError(
                f"--anchor {name!r}: expected key=value, got {part!r}"
            )
        key, val = part.split("=", 1)
        key = key.strip()
        val = val.strip()

        if key == "ivs":
            iv_list = []
            for iv in val.split(";"):
                iv = iv.strip()
                if not iv:
                    continue
                components = iv.split("/")
                if len(components) != 3:
                    raise ThresholdError(
                        f"--anchor {name!r}: bad ivs entry {iv!r} "
                        f"(expected a/d/s)"
                    )
                try:
                    iv_list.append(tuple(int(c) for c in components))
                except ValueError:
                    raise ThresholdError(
                        f"--anchor {name!r}: non-int ivs entry {iv!r}"
                    )
            fields["ivs"] = iv_list
        elif key == "moves":
            fields["moves"] = [m.strip() for m in val.split(";") if m.strip()]
        elif key == "opponent_ivs":
            components = val.split("/")
            if len(components) != 3:
                raise ThresholdError(
                    f"--anchor {name!r}: bad opponent_ivs {val!r} (expected a/d/s)"
                )
            try:
                fields["opponent_ivs"] = [int(c) for c in components]
            except ValueError:
                raise ThresholdError(
                    f"--anchor {name!r}: non-int opponent_ivs {val!r}"
                )
        elif key in ("deals_at_least", "takes_at_most"):
            try:
                fields[key] = int(val)
            except ValueError:
                raise ThresholdError(
                    f"--anchor {name!r}: {key} must be int, got {val!r}"
                )
        elif key in ("above_atk", "above_def"):
            try:
                fields[key] = float(val)
            except ValueError:
                raise ThresholdError(
                    f"--anchor {name!r}: {key} must be number, got {val!r}"
                )
        elif key == "strict":
            fields[key] = val.lower() in ("1", "true", "yes", "on")
        else:
            fields[key] = val

    kind = fields.get("kind")
    if kind is None:
        raise ThresholdError(
            f"--anchor {name!r}: missing 'kind' (cmp or damage_breakpoint)"
        )

    # For inline cmp anchors that specify ivs directly, we need to inject an
    # anonymous spread. Return a sentinel spread alongside the anchor — the CLI
    # glue will wire it up. We do this by returning a CmpAnchor whose `spread`
    # field points at a synthetic name, with the IV list attached via a
    # side-channel attribute on the dict.
    if kind == "cmp" and "ivs" in fields:
        synthetic_spread = f"__inline__{name}"
        raw = {
            "kind": "cmp",
            "spread": synthetic_spread,
            "strict": fields.get("strict", True),
            "description": fields.get("description", ""),
        }
        anchor = _parse_anchor(name, raw, path="<inline>")
        # Attach the ivs for the CLI glue to pick up
        anchor._inline_ivs = fields["ivs"]  # type: ignore[attr-defined]
        return name, anchor

    # Otherwise, pass through _parse_anchor which handles validation uniformly.
    return name, _parse_anchor(name, fields, path="<inline>")


# ---------------------------------------------------------------------------
# Module CLI: dump a loaded file for debugging
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python -m gopvpsim.thresholds <file.toml|file.json> [species]",
              file=sys.stderr)
        return 2
    path = argv[1]
    species = argv[2] if len(argv) > 2 else None
    try:
        reg = load_file(path, species=species)
    except ThresholdError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for sp_name, sp in reg.by_species.items():
        print(f"[{sp_name}]")
        if sp.sources:
            print(f"  sources: {sp.sources[:80]}{'...' if len(sp.sources) > 80 else ''}")
        for ln, lt in sp.leagues.items():
            print(f"  {ln}:")
            for sname, spread in lt.spreads.items():
                if isinstance(spread, StatCutoffSpread):
                    print(f"    spread {sname}: atk>={spread.attack} "
                          f"def>={spread.defense} sta>={spread.stamina}")
                else:
                    print(f"    spread {sname}: {len(spread.ivs)} IVs")
            for aname, anchor in lt.anchors.items():
                if isinstance(anchor, CmpAnchor):
                    print(f"    anchor {aname}: cmp vs spread {anchor.spread}"
                          f" ({'strict' if anchor.strict else 'non-strict'})")
                elif isinstance(anchor, BulkpointAnchor):
                    lvl = anchor.level
                    print(f"    anchor {aname}: bulkpoint L{lvl} "
                          f"vs {anchor.opponent}")
                else:
                    lvl = anchor.level
                    print(f"    anchor {aname}: damage_breakpoint L{lvl} "
                          f"vs {anchor.opponent}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
