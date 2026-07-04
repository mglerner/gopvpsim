"""
Tests for gopvpsim.data — fetch and cache layer.

All tests here require network access (or a warm cache) and are marked
'integration'. Run with: pytest -m integration
"""
import pytest
from gopvpsim.data import load_gamemaster, load_rankings, get_default_moveset, NoDataError


@pytest.mark.integration
def test_load_gamemaster_has_pokemon():
    gm = load_gamemaster()
    assert 'pokemon' in gm
    assert len(gm['pokemon']) > 0

@pytest.mark.integration
def test_load_gamemaster_has_moves():
    gm = load_gamemaster()
    assert 'moves' in gm
    assert len(gm['moves']) > 0

@pytest.mark.integration
def test_load_gamemaster_pokemon_has_expected_fields():
    gm = load_gamemaster()
    mon = gm['pokemon'][0]
    assert 'speciesName' in mon
    assert 'baseStats' in mon
    assert {'atk', 'def', 'hp'} <= set(mon['baseStats'].keys())

@pytest.mark.integration
def test_load_gamemaster_moves_have_energy_fields():
    gm = load_gamemaster()
    move = gm['moves'][0]
    assert 'energyGain' in move or 'energy' in move

@pytest.mark.integration
@pytest.mark.parametrize("league", ["great", "ultra", "master"])
def test_load_rankings_returns_list(league):
    rankings = load_rankings(league)
    assert isinstance(rankings, list)
    assert len(rankings) > 0

@pytest.mark.integration
def test_load_rankings_has_rating():
    rankings = load_rankings("great")
    assert 'rating' in rankings[0]

def test_load_rankings_invalid_league_raises():
    with pytest.raises(ValueError):
        load_rankings("kiddie")


# ---------------------------------------------------------------------------
# load_cup_rankings + cup-aware get_default_moveset (Phase 2 top-N/cup plan)
# ---------------------------------------------------------------------------

def test_load_cup_rankings_unknown_cup_raises_and_lists_valid():
    """Fails LOUDLY for a cup with no rankings, naming the valid cups."""
    from gopvpsim.data import load_cup_rankings
    with pytest.raises(ValueError) as ei:
        load_cup_rankings('nonesuch', 1500)
    msg = str(ei.value)
    assert 'nonesuch' in msg
    assert 'equinox' in msg          # the valid-cup list is included


@pytest.mark.integration
def test_load_cup_rankings_equinox():
    from gopvpsim.data import load_cup_rankings
    r = load_cup_rankings('equinox', 1500)
    assert isinstance(r, list) and len(r) > 0
    assert r[0]['speciesName'] == 'Mantine'   # cup #1
    assert 'moveset' in r[0]


@pytest.mark.integration
def test_default_moveset_cup_uses_cup_build():
    """cup=... sources the cup moveset for a species ranked in the cup."""
    fast, charged = get_default_moveset('Mantine', league='great', cup='equinox')
    assert fast == 'WING_ATTACK'
    assert charged == ['TWISTER', 'WATER_PULSE']


@pytest.mark.integration
def test_default_moveset_cup_falls_back_to_overall_league():
    """A species not legal/ranked in the cup falls back to the overall-league
    moveset rather than raising (decided policy)."""
    # Azumarill (Water/Fairy) is not an Equinox type, so it's unranked in the
    # cup; the fallback returns its open-GL build.
    cup_fast, cup_charged = get_default_moveset('Azumarill', league='great',
                                                cup='equinox')
    gl_fast, gl_charged = get_default_moveset('Azumarill', league='great')
    assert (cup_fast, cup_charged) == (gl_fast, gl_charged)


# ---------------------------------------------------------------------------
# get_default_moveset
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_default_moveset_medicham_great():
    fast, charged = get_default_moveset('Medicham', league='great')
    assert fast == 'PSYCHO_CUT'
    assert set(charged) == {'ICE_PUNCH', 'DYNAMIC_PUNCH'}


@pytest.mark.integration
def test_default_moveset_azumarill_great():
    fast, charged = get_default_moveset('Azumarill', league='great')
    assert fast == 'BUBBLE'
    assert len(charged) == 2


@pytest.mark.integration
def test_default_moveset_shadow():
    fast, charged = get_default_moveset('Quagsire', league='great', shadow=True)
    assert fast == 'MUD_SHOT'
    assert len(charged) >= 1


@pytest.mark.integration
def test_default_moveset_returns_valid_moves():
    """Ensure returned move IDs exist in the gamemaster's move list."""
    from gopvpsim.moves import get_moves
    fast_moves, charged_moves = get_moves()
    fast, charged = get_default_moveset('Medicham', league='great')
    assert fast in fast_moves, f"Fast move {fast!r} not in gamemaster"
    for cid in charged:
        assert cid in charged_moves, f"Charged move {cid!r} not in gamemaster"


def test_default_moveset_unknown_species_raises():
    with pytest.raises(KeyError):
        get_default_moveset('FakemonXYZ', league='great')


def test_default_moveset_invalid_league_raises():
    with pytest.raises(ValueError):
        get_default_moveset('Medicham', league='kiddie')


# ---------------------------------------------------------------------------
# _fetch_json cache robustness (2026-06-11 review finding L5)
# ---------------------------------------------------------------------------

def _patch_fetch_env(monkeypatch, tmp_path, payload):
    """Point the cache at tmp_path and fake the network to return payload."""
    import json as _json
    import io
    import gopvpsim.data as data

    monkeypatch.setattr(data, 'CACHE_DIR', tmp_path)

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, context=None):
        return _FakeResponse(_json.dumps(payload).encode())

    monkeypatch.setattr(data.urllib.request, 'urlopen', fake_urlopen)
    return data


# ---------------------------------------------------------------------------
# species_id resolution (2026-06-11 review finding L3)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_species_id_handles_punctuated_names():
    """The old naive slug mangled apostrophes/periods/hyphens, so these
    ranked species raised KeyError from get_default_moveset and were
    silently skipped (with a warning) by the dive pool loader."""
    from gopvpsim.data import species_id
    assert species_id("Farfetch'd (Galarian)") == 'farfetchd_galarian'
    assert species_id('Mr. Mime') == 'mr_mime'
    assert species_id('Ho-Oh') == 'ho_oh'
    assert species_id("Sirfetch'd") == 'sirfetchd'
    # Shadow handling: explicit suffix resolves directly; the flag
    # appends without double-suffixing.
    assert species_id('Quagsire (Shadow)') == 'quagsire_shadow'
    assert species_id('Quagsire', shadow=True) == 'quagsire_shadow'
    assert species_id('Quagsire (Shadow)', shadow=True) == 'quagsire_shadow'
    # Unknown names fall back to the historical slug (no crash).
    assert species_id('Fakemon (Weird)') == 'fakemon_weird'


@pytest.mark.integration
def test_default_moveset_punctuated_names_resolve():
    from gopvpsim.data import get_default_moveset
    for name in ("Farfetch'd (Galarian)", "Sirfetch'd", "Mr. Mime"):
        fast, charged = get_default_moveset(name, league='great')
        assert isinstance(fast, str) and fast
        assert isinstance(charged, list) and charged


def test_corrupt_fresh_cache_falls_through_to_refetch(monkeypatch, tmp_path):
    # A fresh-but-corrupt cache file used to raise JSONDecodeError before
    # the network path was ever tried.
    data = _patch_fetch_env(monkeypatch, tmp_path, {'ok': 1})
    cache_file = tmp_path / 'testkey.json'
    cache_file.write_text('{"truncated": ')   # fresh mtime, corrupt body
    result = data._fetch_json('testkey', url='https://example.invalid/x.json')
    assert result == {'ok': 1}
    # The corrupt file was healed by the (atomic) rewrite.
    import json as _json
    assert _json.loads(cache_file.read_text()) == {'ok': 1}


def test_fetch_writes_no_tmp_residue(monkeypatch, tmp_path):
    data = _patch_fetch_env(monkeypatch, tmp_path, {'ok': 2})
    data._fetch_json('testkey2', url='https://example.invalid/x.json')
    assert (tmp_path / 'testkey2.json').exists()
    assert not list(tmp_path.glob('*.tmp'))


def test_corrupt_stale_cache_with_no_network_raises_nodata(monkeypatch, tmp_path):
    import gopvpsim.data as data
    monkeypatch.setattr(data, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(data, 'CACHE_TTL', -1)   # force the stale path

    def dead_urlopen(url, context=None):
        raise OSError('no network')

    monkeypatch.setattr(data.urllib.request, 'urlopen', dead_urlopen)
    (tmp_path / 'testkey3.json').write_text('{"truncated": ')
    with pytest.raises(data.NoDataError):
        data._fetch_json('testkey3', url='https://example.invalid/x.json')
