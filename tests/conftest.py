"""
Shared fixtures for gopvpsim tests.
"""
import pytest
import gopvpsim.data as data_module
import gopvpsim.pokemon as pokemon_module


@pytest.fixture(autouse=True, scope='session')
def _pin_data_cache_ttl():
    """Pin the gamemaster/rankings disk cache for the whole test run.

    A pytest invocation must never REFRESH the on-disk cache: the refresh
    swaps opponent data under everything else sharing the cache — including
    an in-flight overnight dive chain (the documented reproducibility
    hazard). With CACHE_TTL pinned to infinity an existing cache file is
    used as-is regardless of age; a genuinely cold cache still fetches once.
    """
    orig = data_module.CACHE_TTL
    data_module.CACHE_TTL = float('inf')
    yield
    data_module.CACHE_TTL = orig

# ---------------------------------------------------------------------------
# Fake species used in unit tests — not tied to any real gamemaster data.
# base_atk=100, base_def=100, base_sta=100 keep the math easy to check by hand.
# ---------------------------------------------------------------------------

FAKE_BASE_ATK = 100
FAKE_BASE_DEF = 100
FAKE_BASE_STA = 100

MOCK_GAMEMASTER = {
    'pokemon': [
        {
            'speciesName': 'Testmon',
            'baseStats': {
                'atk': FAKE_BASE_ATK,
                'def': FAKE_BASE_DEF,
                'hp':  FAKE_BASE_STA,   # gamemaster uses 'hp' for stamina
            },
        },
    ],
    'moves': [],
}


@pytest.fixture
def mock_gm(monkeypatch):
    """Patch load_gamemaster with fake data and clear the module-level cache."""
    monkeypatch.setattr('gopvpsim.pokemon.load_gamemaster',
                        lambda: MOCK_GAMEMASTER)
    pokemon_module._pokemon_index = None
    yield
    pokemon_module._pokemon_index = None
