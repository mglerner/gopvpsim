"""
Fetch and cache PvPoke game data.
"""
import json
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


class NoDataError(Exception):
    """Raised when data cannot be fetched and no cache is available."""
    pass


def _fetch_json(key):
    """Fetch a JSON file from PvPoke, using a local cache.

    Uses cached data if it is less than CACHE_TTL seconds old.
    Falls back to stale cache if the network is unavailable.
    Raises NoDataError if neither network nor cache is available.
    """
    CACHE_DIR.mkdir(exist_ok=True, parents=True)
    cache_file = CACHE_DIR / f"{key}.json"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < CACHE_TTL:
            return json.loads(cache_file.read_text())

    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(URLS[key], context=ssl_context) as r:
            data = json.loads(r.read().decode())
        cache_file.write_text(json.dumps(data))
        return data
    except Exception as e:
        print(f"Fetch error for {key}: {e}")

    if cache_file.exists():
        return json.loads(cache_file.read_text())

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
        KeyError: if species not found in rankings for this league
    """
    index = _get_rankings_index(league)

    # Build the speciesId key PvPoke uses: lowercase, underscored
    species_id = species_name.lower().replace(' ', '_').replace('(', '').replace(')', '')
    if shadow:
        species_id = species_id + '_shadow'

    if species_id not in index:
        raise KeyError(
            f"{species_name!r} {'(Shadow) ' if shadow else ''}"
            f"not found in {league} league rankings. "
            f"Available species can be listed with load_rankings({league!r})."
        )

    moveset = index[species_id]['moveset']
    return moveset[0], moveset[1:]
