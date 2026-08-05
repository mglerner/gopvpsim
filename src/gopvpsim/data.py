"""
Fetch and cache PvPoke game data.
"""
import json
import os
import pathlib
import ssl
import time
import urllib.request
from typing import NamedTuple

import certifi

CACHE_DIR = pathlib.Path.home() / "Documents" / "gopvpsim_cache"
CACHE_TTL = 86400  # refresh once a day

BASE_URL = "https://raw.githubusercontent.com/pvpoke/pvpoke/refs/heads/master/src/data"
URLS = {
    "gamemaster": f"{BASE_URL}/gamemaster.json",
    "great":      f"{BASE_URL}/rankings/all/overall/rankings-1500.json",
    "ultra":      f"{BASE_URL}/rankings/all/overall/rankings-2500.json",
    "master":     f"{BASE_URL}/rankings/all/overall/rankings-10000.json",
}

# PvPoke custom groups (matrix battle quick-fill).
# Key pattern: "group_<name>" in the cache.
GROUP_URL_TEMPLATE = f"{BASE_URL}/groups/{{}}.json"

# League display name -> CP cap used in PvPoke's rankings-<cp>.json filenames.
_LEAGUE_CP = {"great": 1500, "ultra": 2500, "master": 10000}

# Limited-cup rankings live under rankings/<cup>/overall/rankings-<cp>.json
# (the same schema as the "all" overall rankings). Key pattern in the cache:
# "rankings_<cup>_<cp>".
CUP_RANKINGS_URL_TEMPLATE = (
    f"{BASE_URL}/rankings/{{cup}}/overall/rankings-{{cp}}.json")

# ---------------------------------------------------------------------------
# Limited-cup registry
# ---------------------------------------------------------------------------
# ONE table for every limited cup this project knows about, so the cup facts
# stop being re-typed per layer. Consumers:
#   * load_cup_rankings' known-cup check (below)
#   * the cup label baked into dive pages / dive cards (scripts/deep_dive.py)
#   * the `<species>-<cup>-cup` website slug suffixes the index routes on
#     (scripts/build_website_index.py, scripts/run_website_dives.py)
#
# ``dive_league`` is the cup's mechanical CP league, and is set ONLY for cups
# this project actually publishes dives for -- the website slug map is derived
# from exactly those. None means "we know PvPoke ranks this cup, but this
# project has no dive plumbing for it"; naming a league would be a guess.
#
# ``display_name`` is the human-facing cup name. None means "no verified
# official name here", and cup_pretty_name() derives "<Key> Cup" instead --
# the point being that the derivation lives in ONE place. Before this table
# the same missing name rendered as "Bastille Cup" on a dive page and
# "Bastille" on the cup index.
#
# Membership doubles as the rankings allow-list: it only gates
# load_cup_rankings' loud failure message (an unknown cup names the valid set
# instead of a bare 404). A cup here but without a file for the requested CP
# still fails loudly via _fetch_json's NoDataError. Cups that alias/hide
# rankings (e.g. 'championshipseries' aliases 'all') are intentionally absent.
# Refresh against ../pvpoke/src/data/rankings/*/overall/ when adding cups.
class CupInfo(NamedTuple):
    dive_league: str | None
    display_name: str | None


CUP_REGISTRY = {
    # Cups with dive plumbing (league + verified display name).
    "equinox": CupInfo("great", "Equinox Cup"),
    # Cups PvPoke publishes rankings for, with no dive plumbing here.
    **{c: CupInfo(None, None) for c in (
        "bastille", "bayou", "bfretro", "battlefrontiermaster", "catch",
        "classic", "copadiluvio", "cosy", "coupedusillage",
        "ligaultra", "little", "mega", "naic2026", "premier", "remix",
        "retro", "spellcraft", "summer", "sunshine", "tsuki",
    )},
}

# Backwards-compatible alias: the set of cups with published rankings is
# exactly the registry's keys.
_CUPS_WITH_RANKINGS = frozenset(CUP_REGISTRY)


def cup_pretty_name(cup):
    """Human display name for a cup key ('equinox' -> 'Equinox Cup').

    Returns None for a falsy cup (the "this is not a cup dive" case, so
    callers can pass an optional cup straight through). Unregistered cups and
    registered ones with no verified name derive "<Key> Cup" -- one derivation
    for every layer, instead of each renderer inventing its own fallback.
    """
    if not cup:
        return None
    info = CUP_REGISTRY.get(cup)
    if info is not None and info.display_name:
        return info.display_name
    return f"{cup.capitalize()} Cup"


def cup_dive_league(cup):
    """Mechanical CP league for a cup this project publishes dives for.

    None for an unregistered cup or one with no dive plumbing -- callers that
    route dives (website index, dive runner) treat None as "not routable".
    """
    info = CUP_REGISTRY.get(cup)
    return info.dive_league if info is not None else None


def cup_slug_suffix(cup):
    """Website dive-slug suffix for a cup: 'equinox' -> 'equinox-cup'.

    A cup dive's directory slug is FLAT ``<species>-<cup>-cup`` (the cup
    implies league/CP). The slug PRODUCER (scripts/run_website_dives.py), the
    index ROUTER (scripts/build_website_index.py) and the overnight verifier's
    glob all key on this one shape, so it is spelled out here once.
    """
    return f"{cup}-cup"


class NoDataError(Exception):
    """Raised when data cannot be fetched and no cache is available."""
    pass


def _fetch_json(key, url=None):
    """Fetch a JSON file from PvPoke, using a local cache.

    Uses cached data if it is less than CACHE_TTL seconds old; a corrupt
    fresh cache (truncated write, partial download) falls through to a
    refetch instead of raising. Falls back to stale cache if the network
    is unavailable. The cache write is atomic (tmp + os.replace) so a
    crash mid-write can never leave a truncated file for the next reader.
    Raises NoDataError if neither network nor cache is available.

    ``url`` defaults to ``URLS[key]``; pass it explicitly for keys that
    aren't in the static table (custom groups).
    """
    CACHE_DIR.mkdir(exist_ok=True, parents=True)
    cache_file = CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < CACHE_TTL:
            try:
                return json.loads(cache_file.read_text())
            except (json.JSONDecodeError, OSError) as e:
                print(f"Corrupt cache for {key} ({e}); refetching")

    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(url or URLS[key], context=ssl_context) as r:
            data = json.loads(r.read().decode())
        tmp = cache_file.with_name(cache_file.name + ".tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, cache_file)
        return data
    except Exception as e:
        print(f"Fetch error for {key}: {e}")

    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # stale cache is corrupt too — fall through to the error

    raise NoDataError(
        f"Could not fetch '{key}' and no cached data is available. "
        f"Please connect to the internet and try again."
    )


def load_gamemaster():
    """Load the PvPoke gamemaster data."""
    return _fetch_json("gamemaster")


def parse_types(mon: dict) -> list[str]:
    """Extract a Pokemon's type list from a gamemaster entry, filtering placeholder 'none' values.

    Single-type Pokemon are stored as e.g. ['steel', 'none'] in PvPoke's gamemaster.
    """
    types = mon.get('types', [mon.get('type1', 'normal')])
    if isinstance(types, str):
        types = [types]
    return [t for t in types if t and t != 'none']


def _fetch_bytes(key, url, subdir="sprites", ttl=CACHE_TTL):
    """Binary sibling of _fetch_json: TTL-cache an arbitrary asset under
    CACHE_DIR/<subdir>/<key>. Returns bytes, or None on any failure
    (callers degrade gracefully rather than crash a render). Reuses the
    same certifi SSL context + atomic tmp+os.replace write + stale
    fallback as _fetch_json, but reads/writes bytes (no JSON parse)."""
    d = CACHE_DIR / subdir
    d.mkdir(exist_ok=True, parents=True)
    cache_file = d / key
    if cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < ttl:
            try:
                return cache_file.read_bytes()
            except OSError:
                pass
    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        # Some sprite CDNs (pokemondb) 403 the default Python-urllib UA.
        req = urllib.request.Request(
            url, headers={'User-Agent': 'Mozilla/5.0 (gopvpsim sprite fetch)'})
        # timeout so a hung sprite CDN can't stall the dive render path
        # (the except below turns a timeout into the graceful None fallback).
        with urllib.request.urlopen(req, context=ssl_context, timeout=10) as r:
            data = r.read()
        tmp = cache_file.with_name(cache_file.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, cache_file)
        return data
    except Exception as e:  # noqa: BLE001
        print(f"Sprite fetch error for {key}: {e}")
    if cache_file.exists():
        try:
            return cache_file.read_bytes()
        except OSError:
            pass
    return None


def sprite_data_uri(species_name, shadow=False):
    """Return a self-contained ``data:image/png;base64,...`` URI for the
    species' Pokemon-GO sprite, or None if it can't be fetched (the dive
    card then degrades to a typing-colored CSS block).

    Shadow forms reuse the base sprite (the card adds a CSS flame badge),
    so the shadow flag is accepted for symmetry but does not change the
    asset. Sprites are sourced from PokeMiners-derived open GO sprites
    served by pokemondb (PvPoke's own repo does not expose raw sprite
    URLs) and cached locally under CACHE_DIR/sprites/ for reproducibility.
    Best-effort: for non-base forms the speciesId-derived slug may not match
    pokemondb's path, in which case the fetch 404s and the caller degrades to
    the typing-colored CSS block (returns None here).
    """
    slug = species_id(species_name, shadow=False).replace('_', '-')
    data = _fetch_bytes(
        f"{slug}.png",
        f"https://img.pokemondb.net/sprites/go/normal/{slug}.png",
    )
    if not data:
        return None
    import base64
    return "data:image/png;base64," + base64.b64encode(data).decode('ascii')


def load_rankings(league):
    """Load rankings for a given league: 'great', 'ultra', or 'master'."""
    if league not in ("great", "ultra", "master"):
        raise ValueError(f"Unknown league: {league!r}")
    return _fetch_json(league)


def load_cup_rankings(cup, cp):
    """Load PvPoke overall rankings for a limited cup at a CP cap.

    Same JSON schema as ``load_rankings`` (a list of entries carrying
    ``speciesId`` / ``speciesName`` / ``moveset``), fetched from
    ``rankings/<cup>/overall/rankings-<cp>.json`` and cached under
    ``rankings_<cup>_<cp>`` (shares ``_fetch_json``'s TTL / atomic-write /
    stale-fallback behavior). ``load_group`` is the sibling precedent.

    Fails LOUDLY for a cup with no published rankings: an unknown cup name
    raises ValueError listing the known cups; a known cup with no file for
    the requested CP raises NoDataError from the fetch.
    """
    if cup not in _CUPS_WITH_RANKINGS:
        raise ValueError(
            f"No published rankings for cup {cup!r}. "
            f"Known cups: {', '.join(sorted(_CUPS_WITH_RANKINGS))}.")
    return _fetch_json(
        f"rankings_{cup}_{cp}",
        url=CUP_RANKINGS_URL_TEMPLATE.format(cup=cup, cp=cp))


def get_rankings_for(league, cup=None):
    """Rankings list for a league, or for a limited cup at that league's CP cap.

    The public one-call form of the "cup wins, else the open league" branch
    every caller used to re-type (each one importing the private ``_LEAGUE_CP``
    to build the cup's CP argument). ``cup=None`` is the open-league meta.
    Raises KeyError for an unknown league, and load_cup_rankings' loud
    ValueError / NoDataError for an unknown or unpublished cup.
    """
    if cup is not None:
        return load_cup_rankings(cup, _LEAGUE_CP[league])
    return load_rankings(league)


def rankings_cache_path(league, cup=None):
    """Local cache file backing ``get_rankings_for(league, cup)``.

    The file's mtime is the honest "rankings as of" vintage a renderer can
    stat; it exists only after the first successful fetch. Pure path
    construction (no I/O), so a missing file is the caller's OSError to
    handle. Raises KeyError for an unknown league.
    """
    if cup is not None:
        return CACHE_DIR / f"rankings_{cup}_{_LEAGUE_CP[league]}.json"
    return CACHE_DIR / f"{league}.json"


# ---------------------------------------------------------------------------
# Rankings index (cached)
# ---------------------------------------------------------------------------

_rankings_index = {}  # (league, cup) -> {speciesId -> ranking entry}


def _get_rankings_index(league, cup=None):
    """Return a dict of speciesId -> ranking entry. Cached per (league, cup).

    ``cup=None`` uses the league's overall ("all") rankings; a cup name uses
    that cup's rankings at the league's CP cap.
    """
    key = (league, cup)
    if key not in _rankings_index:
        if cup is None:
            rankings = load_rankings(league)
        else:
            rankings = load_cup_rankings(cup, _LEAGUE_CP[league])
        _rankings_index[key] = {r['speciesId']: r for r in rankings}
    return _rankings_index[key]


def load_group(group_name):
    """Load a PvPoke custom group (e.g. 'championshipseries').

    Fetches from GitHub and caches locally, same as gamemaster/rankings
    (shares ``_fetch_json``'s TTL / corrupt-cache / stale-fallback /
    atomic-write behavior). Returns the raw JSON list of group entries.
    """
    return _fetch_json(f"group_{group_name}",
                       url=GROUP_URL_TEMPLATE.format(group_name))


# Explicit per-species fallback movesets for species absent from PvPoke's
# rankings JSON. PvPoke ranks certain form-change Pokemon under only one
# form even though both forms are battle-legal as opponents (e.g. it ranks
# Aegislash (Shield) but not Aegislash (Blade) — Blade is the in-battle
# transform state). Without a fallback, the opponent loader in
# scripts/deep_dive.py rejects such opponents as "not found in <league>
# league rankings" and silently skips them, leaving holes in matchup
# matrices. Each entry pins the canonical PvPoke moveset for the missing
# form. Add entries here when a new "rankings-orphan" focal surfaces;
# blast radius is intentionally narrow (only get_default_moveset() reads
# this dict, and only when the primary lookup misses).
#
# Keyed by ``(speciesId, league)`` (lowercase, underscored speciesId,
# string league) and valued by ``(fast_move_id, [charged_move_id, ...])``.
_DEFAULT_MOVESET_FALLBACK = {
    # Aegislash (Blade) GL — canonical PvPoke moveset for the Blade form,
    # matches the --reference used by the Aegislash (Blade) GL focal dive
    # in scripts/run_website_dives.py. Falls back here when Shadow Sableye
    # / Forretress / etc. dives need to sim against Blade as an opponent.
    ('aegislash_blade', 'great'): ('PSYCHO_CUT', ['SHADOW_BALL', 'GYRO_BALL']),
}


_species_id_index = None  # speciesName -> speciesId, built from the gamemaster


def species_id(species_name, *, shadow=False):
    """Resolve a display speciesName to PvPoke's speciesId.

    Prefers the gamemaster's own speciesName -> speciesId mapping, which
    is exact for every name PvPoke knows — including the ones a naive
    slug mangles: "Farfetch'd (Galarian)" -> farfetchd_galarian,
    "Mr. Mime" -> mr_mime, "Ho-Oh" -> ho_oh, "Sirfetch'd" -> sirfetchd.
    Falls back to the historical lowercase/underscore/strip-parens slug
    only for names absent from the gamemaster.

    shadow=True appends '_shadow' unless the resolved id already carries
    it (names with an explicit ' (Shadow)' suffix resolve directly to
    their shadow entry).
    """
    global _species_id_index
    if _species_id_index is None:
        gm = load_gamemaster()
        _species_id_index = {p['speciesName']: p['speciesId']
                             for p in gm['pokemon']}
    sid = _species_id_index.get(species_name)
    if sid is None:
        sid = (species_name.lower().replace(' ', '_')
               .replace('(', '').replace(')', ''))
    if shadow and not sid.endswith('_shadow'):
        sid += '_shadow'
    return sid


def get_default_moveset(species_name, league='great', shadow=False, cup=None):
    """Return (fast_move_id, [charged_move_ids]) from PvPoke's rankings.

    PvPoke's rankings files contain a 'moveset' field for each species:
    [FAST_MOVE, CHARGED1, CHARGED2].  This is the default moveset shown
    on pvpoke.com/battle/ when no moves are specified.

    Args:
        species_name: e.g. 'Medicham', 'Azumarill'
        league: 'great', 'ultra', or 'master'
        shadow: if True, look up the shadow variant (e.g. 'medicham_shadow')
        cup: limited-cup name (e.g. 'equinox'); when set, the cup's moveset
            wins and the overall-league moveset is the fallback for a species
            unranked in the cup (cup rankings cover fewer species than the
            overall meta). The ``_DEFAULT_MOVESET_FALLBACK`` escape hatch is
            keyed by league only and ignores the cup dimension (cup dives
            don't need form-orphan overrides).

    Returns:
        (fast_move_id, [charged_move_id, ...])

    Raises:
        KeyError: if species not found in rankings for this league and
            not present in the _DEFAULT_MOVESET_FALLBACK escape hatch.
    """
    # Resolve the speciesId via the gamemaster mapping (handles
    # apostrophes/periods/hyphens the old naive slug mangled — those
    # species raised KeyError despite being ranked).
    sid = species_id(species_name, shadow=shadow)

    # Cup moveset wins; fall through to the overall-league moveset when the
    # species is unranked in the cup (decided policy, plan Decision 6).
    if cup is not None:
        cup_index = _get_rankings_index(league, cup=cup)
        if sid in cup_index:
            moveset = cup_index[sid]['moveset']
            return moveset[0], moveset[1:]

    index = _get_rankings_index(league)
    if sid in index:
        moveset = index[sid]['moveset']
        return moveset[0], moveset[1:]

    # Primary lookup missed — try the explicit-fallback dict before raising.
    fallback = _DEFAULT_MOVESET_FALLBACK.get((sid, league))
    if fallback is not None:
        return fallback[0], list(fallback[1])

    raise KeyError(
        f"{species_name!r} {'(Shadow) ' if shadow else ''}"
        f"not found in {league} league rankings. "
        f"Available species can be listed with load_rankings({league!r})."
    )
