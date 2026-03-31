"""
Shared fixtures for gopvpsim tests.
"""
import pytest
import gopvpsim.pokemon as pokemon_module

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
