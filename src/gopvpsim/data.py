"""
Fetch and cache PvPoke game data.
"""
import json
import os
import pathlib
import ssl
import time
import urllib.request

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


def load_rankings(league):
    """Load rankings for a given league: 'great', 'ultra', or 'master'."""
    if league not in ("great", "ultra", "master"):
        raise ValueError(f"Unknown league: {league!r}")
    return _fetch_json(league)


# ---------------------------------------------------------------------------
# Rankings index (cached)
# ---------------------------------------------------------------------------

_rankings_index = {}  # league -> {speciesId -> ranking entry}


def _get_rankings_index(league):
    """Return a dict of speciesId -> ranking entry for a league. Cached."""
    if league not in _rankings_index:
        rankings = load_rankings(league)
        _rankings_index[league] = {r['speciesId']: r for r in rankings}
    return _rankings_index[league]


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


def get_default_moveset(species_name, league='great', shadow=False):
    """Return (fast_move_id, [charged_move_ids]) from PvPoke's rankings.

    PvPoke's rankings files contain a 'moveset' field for each species:
    [FAST_MOVE, CHARGED1, CHARGED2].  This is the default moveset shown
    on pvpoke.com/battle/ when no moves are specified.

    Args:
        species_name: e.g. 'Medicham', 'Azumarill'
        league: 'great', 'ultra', or 'master'
        shadow: if True, look up the shadow variant (e.g. 'medicham_shadow')

    Returns:
        (fast_move_id, [charged_move_id, ...])

    Raises:
        KeyError: if species not found in rankings for this league and
            not present in the _DEFAULT_MOVESET_FALLBACK escape hatch.
    """
    index = _get_rankings_index(league)

    # Resolve the speciesId via the gamemaster mapping (handles
    # apostrophes/periods/hyphens the old naive slug mangled — those
    # species raised KeyError despite being ranked).
    sid = species_id(species_name, shadow=shadow)

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
