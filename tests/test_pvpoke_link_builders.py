"""pvpoke.com link-builder single-sourcing (DRY review 2026-08-05 entry 8).

Three properties, all of which failed silently before this file existed --
a wrong-but-200 pvpoke URL renders fine, verify_article_links cannot see
it, and only hand-loading a link catches the drift (that is exactly how
the '10000-51' Great-League fallback shipped, fixed 2026-06-21):

1. **Move-segment grammar.** ``pvpoke_links.moveset_segment`` is the one
   builder of the hard-moveset 'FAST-CM1-CM2' segment, including the
   "needs a fast move and two charged moves" guard. The dive's
   ``_opp_link_data`` must route through it (it cannot call
   ``opponent_link_data`` wholesale -- it needs the sim's resolved
   opponent moveset, not the default master one).
2. **URL skeleton parity.** One known (species, ivs, level, shields,
   moveset) tuple, rendered by ``pvpoke_links.battle_url`` and by BOTH
   shipped JS ``cmpBattleUrl`` builders (deep-dive engine, ML guide),
   must produce byte-identical URLs.
3. **generate_article <-> compare_loadouts consolidation.** The five
   link helpers live once, in compare_loadouts; generate_article imports
   them (keeping only its own richer ``_species_id`` fallback).

The node halves skip if node is absent; the pattern mirrors
tests/test_js_mirror_cmp_rule.py.
"""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
_ENGINE_JS = _SCRIPTS / "deep_dive_engine.js"
_ML_PY = _SCRIPTS / "render_iv_envelope_article.py"
_DIVE_PY = _SCRIPTS / "deep_dive.py"

sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_ROOT / "src"))

import pvpoke_links  # noqa: E402
import compare_loadouts  # noqa: E402


def _load_generate_article():
    spec = importlib.util.spec_from_file_location(
        "generate_article", _SCRIPTS / "generate_article.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _node(program):
    res = subprocess.run(["node", "-e", program], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


# ---------------------------------------------------------------- 1. segment

def test_moveset_segment_guard():
    assert pvpoke_links.moveset_segment(
        "BUBBLE", ["ICE_BEAM", "PLAY_ROUGH"]) == "BUBBLE-ICE_BEAM-PLAY_ROUGH"
    # Under-specified builds have no valid segment -> caller renders plain text.
    assert pvpoke_links.moveset_segment("BUBBLE", ["ICE_BEAM"]) is None
    assert pvpoke_links.moveset_segment("", ["ICE_BEAM", "PLAY_ROUGH"]) is None
    assert pvpoke_links.moveset_segment(None, []) is None


def test_opponent_link_data_uses_the_shared_segment(monkeypatch):
    monkeypatch.setattr(pvpoke_links, "_INDEX", {("Medicham", False): "medicham"})
    monkeypatch.setattr(pvpoke_links, "_MOVESET",
                        {("Medicham", False): ("COUNTER", ["ICE_PUNCH", "PSYCHIC"])})
    assert pvpoke_links.opponent_link_data("Medicham") == {
        "id": "medicham", "moves": "COUNTER-ICE_PUNCH-PSYCHIC"}
    # One charged move -> no link, same guard as moveset_segment.
    monkeypatch.setattr(pvpoke_links, "_MOVESET",
                        {("Medicham", False): ("COUNTER", ["ICE_PUNCH"])})
    assert pvpoke_links.opponent_link_data("Medicham") is None


def test_dive_opp_link_data_routes_through_the_shared_segment():
    src = _DIVE_PY.read_text()
    m = re.search(r"\n    def _opp_link_data\(oi\):\n(.*?)\n\n", src, re.S)
    assert m, "_opp_link_data not found in deep_dive.py"
    body = m.group(1)
    assert "pvpoke_links.moveset_segment(" in body
    # The inline f-string reconstruction is what drifted; it must be gone.
    assert not re.search(r"\{ms\[0\]\}-\{ms\[1\]\[0\]\}", body)


# ------------------------------------------------------------ 2. URL skeleton

# One known tuple, rendered three ways. Master (cp 10000), focal on custom
# IVs/level, opponent at 15/15/15 -- the shape every compare-panel cell links.
_FOCAL_ID = "azumarill"
_OPP_ID = "medicham"
_FOCAL_MOVES = "BUBBLE-ICE_BEAM-PLAY_ROUGH"
_OPP_MOVES = "COUNTER-ICE_PUNCH-PSYCHIC"
_BUILD = {"a": 15, "d": 14, "s": 13}
_FOCAL_LEVEL = 50
_OPP_LEVEL = 50
_SHIELDS = (2, 1)

_EXPECTED = (
    "https://pvpoke.com/battle/10000/"
    "azumarill-50-15-14-13-4-4-1-1/medicham-50-15-15-15-4-4-1-1/"
    "21/BUBBLE-ICE_BEAM-PLAY_ROUGH/COUNTER-ICE_PUNCH-PSYCHIC/"
)


def _python_url(monkeypatch, focal_level=_FOCAL_LEVEL):
    monkeypatch.setattr(pvpoke_links, "_INDEX", {
        ("Azumarill", False): _FOCAL_ID, ("Medicham", False): _OPP_ID})
    monkeypatch.setattr(pvpoke_links, "_MOVESET", {
        ("Medicham", False): ("COUNTER", ["ICE_PUNCH", "PSYCHIC"])})
    return pvpoke_links.battle_url(
        "Azumarill", False, (_BUILD["a"], _BUILD["d"], _BUILD["s"]),
        float(focal_level), "BUBBLE", ["ICE_BEAM", "PLAY_ROUGH"],
        "Medicham", float(_OPP_LEVEL), _SHIELDS[0], _SHIELDS[1])


def _engine_builder_js():
    m = re.search(
        r"window\.cmpBattleUrl = function\(oi, si, build\) \{.*?\n\};",
        _ENGINE_JS.read_text(), re.S)
    assert m, "engine cmpBattleUrl not found"
    return m.group(0)


def _ml_builder_js():
    m = re.search(
        r"window\.cmpBattleUrl = function\(oi, si, build, quad\) \{.*?\n  \};",
        _ML_PY.read_text(), re.S)
    assert m, "ML-guide cmpBattleUrl not found"
    return m.group(0)


def test_python_url_skeleton(monkeypatch):
    assert _python_url(monkeypatch) == _EXPECTED


def test_python_url_drops_the_trailing_zero_on_whole_levels(monkeypatch):
    # JS levels arrive as numbers (50, 40.5); Python must format the same way
    # or the two link paths disagree on every whole-level build.
    assert "azumarill-40.5-" in _python_url(monkeypatch, focal_level=40.5)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_engine_js_url_matches_python(monkeypatch):
    data = {
        "cpCap": "10000",
        "focalLink": {"id": _FOCAL_ID},
        "oppLinks": [{"id": _OPP_ID, "moves": _OPP_MOVES,
                      "byMode": {"pvpoke": {"lvl": _OPP_LEVEL,
                                            "ivs": [15, 15, 15]}}}],
        "scenarios": [[_SHIELDS[0], _SHIELDS[1]]],
        "movesets": [{"fast": "BUBBLE", "charged": ["ICE_BEAM", "PLAY_ROUGH"]}],
        "ivLv": [_FOCAL_LEVEL],
        "ivL51": {"ivLv": [51]},
    }
    build = dict(_BUILD, iv=0)
    program = (
        "var window = {};\n"
        f"var DATA = {json.dumps(data)};\n"
        "var state = { movesetIdx: 0, oppIvMode: 'pvpoke' };\n"
        "function atL51View() { return false; }\n"
        + _engine_builder_js() + "\n"
        f"console.log(window.cmpBattleUrl(0, 0, {json.dumps(build)}));\n"
    )
    assert _node(program) == _python_url(monkeypatch)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_ml_guide_js_url_matches_python(monkeypatch):
    cmpdata = {
        "focalLink": {"id": _FOCAL_ID, "moves": _FOCAL_MOVES},
        "oppLinks": [{"id": _OPP_ID, "moves": _OPP_MOVES}],
        "quadrant_levels": {"nobb_vs_nonbb": [_FOCAL_LEVEL, _OPP_LEVEL]},
        "scenarios": [[_SHIELDS[0], _SHIELDS[1]]],
    }
    program = (
        "var window = {};\n"
        f"var CMPDATA = {json.dumps(cmpdata)};\n"
        + _ml_builder_js() + "\n"
        f"console.log(window.cmpBattleUrl(0, 0, {json.dumps(_BUILD)}, "
        "'nobb_vs_nonbb'));\n"
    )
    assert _node(program) == _python_url(monkeypatch)


# ------------------------------------------------ 3. article/compare sharing

def test_generate_article_imports_the_shared_builders():
    ga = _load_generate_article()
    for name in ("pvpoke_single_battle_url", "pvpoke_multi_battle_url",
                 "_resolve_opponent"):
        assert getattr(ga, name) is getattr(compare_loadouts, name), name
    # The local copies are gone (not merely shadowed by the import).
    src = (_SCRIPTS / "generate_article.py").read_text()
    for name in ("_species_move_pools", "_pvpoke_move_segment",
                 "pvpoke_multi_battle_url", "pvpoke_single_battle_url",
                 "_resolve_opponent_for_url"):
        assert not re.search(r"^def %s\(" % name, src, re.M), name


def test_dead_multi_url_helper_is_gone():
    assert not hasattr(compare_loadouts, "_pvpoke_multi_url")


def test_generate_article_keeps_its_species_id_fallback():
    ga = _load_generate_article()
    gm = {"pokemon": [{"speciesName": "Oinkologne (Female)",
                       "speciesId": "oinkologne_female"}]}
    # Display-name match (both variants have this)...
    assert ga._species_id(gm, "Oinkologne (Female)") == "oinkologne_female"
    # ...plus the speciesId-shaped fallback compare_loadouts' variant lacks.
    assert ga._species_id(gm, "oinkologne female") == "oinkologne_female"
    assert compare_loadouts._species_id(gm, "oinkologne female") is None


def test_shared_move_segment_index_encoding():
    gm = {"pokemon": [{"speciesId": "azumarill",
                       "fastMoves": ["BUBBLE", "ROCK_SMASH"],
                       "chargedMoves": ["ICE_BEAM", "PLAY_ROUGH", "HYDRO_PUMP"]}]}
    # fast 0-based, charged 1-based, both into the id-sorted pools.
    assert compare_loadouts._pvpoke_move_segment(
        gm, "azumarill", "BUBBLE", ["ICE_BEAM", "PLAY_ROUGH"]) == "0-2-3"
    # Unreleased / off-pool moves fall back to the moveId string.
    assert compare_loadouts._pvpoke_move_segment(
        gm, "azumarill", "MUD_SLAP", ["ICE_BEAM"]) == "MUD_SLAP-2-0"
    assert compare_loadouts._pvpoke_move_segment(
        gm, "nosuchmon", "BUBBLE", ["ICE_BEAM", "PLAY_ROUGH"]) is None


def test_shared_url_builders_round_trip():
    gm = {"pokemon": [
        {"speciesId": "azumarill", "fastMoves": ["BUBBLE"],
         "chargedMoves": ["ICE_BEAM", "PLAY_ROUGH"]},
        {"speciesId": "medicham", "fastMoves": ["COUNTER"],
         "chargedMoves": ["ICE_PUNCH", "PSYCHIC"]},
    ]}
    assert compare_loadouts.pvpoke_multi_battle_url(
        gm, "azumarill", "great", (1, 1), "BUBBLE",
        ["ICE_BEAM", "PLAY_ROUGH"]) == (
        "https://pvpoke.com/battle/multi/1500/all/azumarill/11/0-1-2/2-1/")
    assert compare_loadouts.pvpoke_single_battle_url(
        gm, "great", (1, 1),
        focal_species_id="azumarill", focal_fast_id="BUBBLE",
        focal_charged_ids=["ICE_BEAM", "PLAY_ROUGH"],
        opp_species_id="medicham", opp_fast_id="COUNTER",
        opp_charged_ids=["ICE_PUNCH", "PSYCHIC"]) == (
        "https://pvpoke.com/battle/1500/azumarill/medicham/11/0-1-2/0-1-2/")
    assert compare_loadouts.pvpoke_multi_battle_url(
        gm, "azumarill", "nosuchleague", (1, 1), "BUBBLE",
        ["ICE_BEAM", "PLAY_ROUGH"]) is None


def test_opponent_resolver_shapes():
    assert compare_loadouts._resolve_opponent("Steelix") == (
        "steelix", "Steelix", False)
    assert compare_loadouts._resolve_opponent("Steelix (Shadow)") == (
        "steelix_shadow", "Steelix", True)
    assert compare_loadouts._resolve_opponent("Medicham (atk-weighted)") == (
        "medicham", "Medicham", False)
