"""
Tests for the client-side opponent-filter bake support in ``deep_dive.py``:

- ``build_opp_meta_ranks`` -- per-opponent PvPoke meta rank (1=best) parallel to
  the opponents list, resolved by speciesId so shadows rank separately and
  registered moveset-variants inherit the base species' rank.
- ``rankings_snapshot_date`` -- the vintage label for those ranks.
- A structural parity tripwire pinning the ``DATA.oppMetaRank`` /
  ``DATA.rankSnapshot`` contract between the Python embedder and the JS reader
  (same spirit as tests/test_js_score_key_parity.py).

Pure-Python only; nothing here spins up a sim. The synthetic-rankings tests are
hermetic (monkeypatched ``load_rankings`` + ``species_id``); a separate live
smoke test exercises the real wiring and skips if the rankings cache/network is
unavailable.
"""
from __future__ import annotations

import datetime
import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEEP_DIVE_PATH = REPO_ROOT / "scripts" / "deep_dive.py"
ENGINE_JS_PATH = REPO_ROOT / "scripts" / "deep_dive_engine.js"

_spec = importlib.util.spec_from_file_location("deep_dive", DEEP_DIVE_PATH)
deep_dive = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(deep_dive)


@pytest.fixture(autouse=True)
def _isolate_variant_registry():
    """Fresh moveset-variant registry per test so cross-test leaks can't hide bugs."""
    saved = dict(deep_dive._OPPONENT_VARIANT_REGISTRY)
    deep_dive._OPPONENT_VARIANT_REGISTRY.clear()
    yield
    deep_dive._OPPONENT_VARIANT_REGISTRY.clear()
    deep_dive._OPPONENT_VARIANT_REGISTRY.update(saved)


# ---- build_opp_meta_ranks: hermetic (synthetic rankings) --------------------

_FAKE_RANKINGS = [
    {"speciesId": "azumarill", "speciesName": "Azumarill"},
    {"speciesId": "medicham", "speciesName": "Medicham"},
    {"speciesId": "medicham_shadow", "speciesName": "Medicham (Shadow)"},
    {"speciesId": "forretress", "speciesName": "Forretress"},
]


def _fake_species_id(name, *, shadow=False):
    """Deterministic stand-in mirroring how the real species_id slugs names."""
    sid = name.lower().replace(" (shadow)", "").replace(" ", "_").replace("'", "")
    return sid + ("_shadow" if shadow else "")


@pytest.fixture
def _synthetic_rankings(monkeypatch):
    monkeypatch.setattr(deep_dive, "load_rankings", lambda league: _FAKE_RANKINGS)
    monkeypatch.setattr(deep_dive, "species_id", _fake_species_id)


def test_rank_is_one_indexed_list_position(_synthetic_rankings):
    ranks = deep_dive.build_opp_meta_ranks(["Azumarill", "Medicham"], "great")
    assert ranks == [1, 2]  # list position + 1


def test_shadow_gets_its_own_ranked_position(_synthetic_rankings):
    # 'Medicham (Shadow)' must resolve to the *_shadow entry (rank 3), NOT the
    # non-shadow Medicham (rank 2). This is the whole point of speciesId keying.
    ranks = deep_dive.build_opp_meta_ranks(
        ["Medicham", "Medicham (Shadow)"], "great")
    assert ranks == [2, 3]


def test_unranked_opponent_is_none(_synthetic_rankings):
    ranks = deep_dive.build_opp_meta_ranks(["Azumarill", "Bogusmon"], "great")
    assert ranks == [1, None]


def test_moveset_variant_inherits_base_rank(_synthetic_rankings):
    # A registered moveset-variant ('Forretress (Bug Bite)') parses back to base
    # 'Forretress', so it must inherit Forretress's rank (4), and both variants
    # of one species share that rank -> a Top-N cut includes both.
    deep_dive.register_opponent_variant("Forretress (Bug Bite)", "Forretress", False)
    ranks = deep_dive.build_opp_meta_ranks(
        ["Forretress", "Forretress (Bug Bite)"], "great")
    assert ranks == [4, 4]


def test_output_is_parallel_to_input_length(_synthetic_rankings):
    names = ["Azumarill", "Bogusmon", "Medicham (Shadow)", "Medicham"]
    assert len(deep_dive.build_opp_meta_ranks(names, "great")) == len(names)


def test_empty_pool_returns_empty(_synthetic_rankings):
    assert deep_dive.build_opp_meta_ranks([], "great") == []


def test_rankings_unavailable_yields_all_none(monkeypatch):
    def _boom(league):
        raise RuntimeError("no network, no cache")
    monkeypatch.setattr(deep_dive, "load_rankings", _boom)
    ranks = deep_dive.build_opp_meta_ranks(["Azumarill", "Medicham"], "great")
    assert ranks == [None, None]  # defensive: never crash the dive


# ---- rankings_snapshot_date -------------------------------------------------

def test_snapshot_date_is_iso_or_none():
    # Real call: either None (cache file un-stat-able) or a valid ISO date.
    snap = deep_dive.rankings_snapshot_date("great")
    if snap is not None:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", snap), snap
        # Round-trips as a real date.
        datetime.date.fromisoformat(snap)


def test_snapshot_date_none_when_cache_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(deep_dive, "_RANKINGS_CACHE_DIR", tmp_path)
    assert deep_dive.rankings_snapshot_date("great") is None


# ---- live smoke test (real rankings + real species_id) ----------------------

def test_live_wiring_resolves_real_ranks():
    """Exercise the real load_rankings + species_id path end-to-end. Skips if
    the rankings can't be loaded (offline with a cold cache)."""
    try:
        rankings = deep_dive.load_rankings("great")
    except Exception:
        pytest.skip("great-league rankings unavailable (offline, cold cache)")
    if not rankings:
        pytest.skip("empty rankings")
    n = len(rankings)
    ranks = deep_dive.build_opp_meta_ranks(["Azumarill", "Bogus Unranked Mon"], "great")
    assert ranks[0] is not None and 1 <= ranks[0] <= n  # Azumarill is GL-ranked
    assert ranks[1] is None                             # obviously not ranked


# ---- structural parity: DATA.oppMetaRank / DATA.rankSnapshot contract -------

def test_bake_emits_and_js_reads_the_same_data_keys():
    """The Python embedder writes 'oppMetaRank'/'rankSnapshot' into data_obj and
    the JS reads DATA.oppMetaRank/DATA.rankSnapshot. A rename on one side alone
    would silently disable the filter panel -- pin both."""
    py = DEEP_DIVE_PATH.read_text()
    js = ENGINE_JS_PATH.read_text()
    assert "'oppMetaRank':" in py
    assert "'rankSnapshot':" in py
    assert "DATA.oppMetaRank" in js
    assert "DATA.rankSnapshot" in js
