"""Python <-> JS parity for the two match_mons rules the manual harness
could not see.

``scripts/verify_js_parser.py`` is the real equivalence harness, but it
runs against a gitignored personal Poke Genie export, so it cannot gate
anything in CI. These tests reuse its helpers against a small synthetic
CSV and pin the two rules DRY review 2026-08-05 flagged:

* entry 10 -- the gender rule. The JS ``matchMons`` honored only a
  caller-global ``requireGender`` while Python ``match_mons`` filters
  per TARGET species, so a male Lechonk counted as an owned Oinkologne
  (Female). The harness structurally could not see it: no
  gender-differentiated species was in its threshold dict.
* entry 9 -- the level ceilings. Both ports used to default
  ``maxLevel`` to a league-blind 51.0; GL/UL cap at 50 (best buddy is
  +1 level and only one mon can hold it).

Node half skips if node is absent (pattern from
tests/test_js_mirror_cmp_rule.py).
"""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from gopvpsim.pokemon import CPM, LEAGUE_CAPS, LEAGUE_MAX_LEVEL
from gopvpsim.user_collection import ivs_to_stats_at_cap

_REPO = Path(__file__).resolve().parents[1]
_JS = _REPO / "scripts" / "deep_dive_user_collection.js"

needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")


_HARNESS = None


def _harness():
    """Import scripts/verify_js_parser.py as a module (not on sys.path)."""
    global _HARNESS
    if _HARNESS is None:
        path = _REPO / "scripts" / "verify_js_parser.py"
        spec = importlib.util.spec_from_file_location("verify_js_parser", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _HARNESS = mod
    return _HARNESS


# Poke Genie writes the gender column as the Mars/Venus glyphs; escaped
# here so this file stays ASCII.
_M = "\u2642"
_F = "\u2640"

# Male / female / blank-gender Lechonks (all evolve to BOTH Oinkologne
# forms in the gamemaster's reverse index) plus a Tinkaton control, which
# has no '(Female)' sibling and must therefore be gender-blind.
_GENDER_CSV = (
    "Name,Form,Gender,CP,Atk IV,Def IV,Sta IV,Level Min,Shadow/Purified,Lucky\n"
    f"Lechonk,,{_M},500,5,11,15,20.0,0,0\n"
    f"Lechonk,,{_F},500,4,13,8,20.0,0,0\n"
    "Lechonk,,,500,7,7,7,20.0,0,0\n"
    f"Tinkaton,,{_M},1488,0,14,14,25.5,0,0\n"
    f"Tinkaton,,{_F},1488,0,14,14,25.5,0,0\n"
)

# Rows that straddle the Great League ceiling: 50.0 is reachable, 50.5 is
# past it, and power-ups are one-way. With a 51.0 default both survive.
# Lechonk is matched as ITSELF here (not walked up to Oinkologne, whose
# GL-optimal level is 20) -- its own optimal GL level is exactly the
# ceiling, which is what makes 50 vs 51 observable.
_CEILING_CSV = (
    "Name,Form,Gender,CP,Atk IV,Def IV,Sta IV,Level Min,Shadow/Purified,Lucky\n"
    f"Lechonk,,{_M},600,15,15,15,50.0,0,0\n"
    f"Lechonk,,{_M},600,15,15,15,50.5,0,0\n"
)

_PERMISSIVE = {"Great": {"Any": {"attack": 0, "defense": 0, "stamina": 0}}}
_GENDER_THRESHOLDS = {
    "Oinkologne": _PERMISSIVE,
    "Oinkologne (Female)": _PERMISSIVE,
    "Tinkaton": _PERMISSIVE,
}
_MALE_THRESHOLDS = {"Oinkologne": _PERMISSIVE}
_CEILING_THRESHOLDS = {"Lechonk": _PERMISSIVE}


def _both_sides(csv_text, thresholds, max_level, require_gender=None):
    """Run Python match_mons and JS matchMons on the same input.

    Returns (py_canonical, js_canonical). ``require_gender`` is the
    JS-only caller-global narrowing; the Python side pre-filters the mon
    list to match, which is what that option means.
    """
    h = _harness()
    mons = h.parse_csv_text(csv_text)
    if require_gender:
        mons = h.gender_prefiltered(mons, require_gender)
    py = h.match_mons(mons, thresholds, league=h.HARNESS_LEAGUE,
                      max_level=max_level)
    payload = h.build_payload(csv_text, require_gender=require_gender,
                              thresholds=thresholds, max_level=max_level)
    js = h.run_js(payload)["results"]
    return h.canonicalize_results(py), h.canonicalize_results(js)


def _species_ivs(canon, species):
    return sorted(
        (r["mon"]["atk_iv"], r["mon"]["def_iv"], r["mon"]["sta_iv"])
        for r in canon.get(species, [])
    )


# ---------------------------------------------------------------------------
# entry 10 -- the per-target gender rule
# ---------------------------------------------------------------------------

@needs_node
@pytest.mark.integration
def test_gender_rule_agrees_and_is_not_vacuous():
    py, js = _both_sides(_GENDER_CSV, _GENDER_THRESHOLDS,
                         LEAGUE_MAX_LEVEL["great"])
    assert py == js
    # Non-vacuity: the rule must actually be splitting these rows, or the
    # equality above would pass on two matchers that both ignore gender.
    assert _species_ivs(py, "Oinkologne (Female)") == [(4, 13, 8), (7, 7, 7)]
    assert _species_ivs(py, "Oinkologne") == [(5, 11, 15), (7, 7, 7)]
    # Tinkaton has no '(Female)' sibling -> gender-blind, both rows match.
    assert len(py["Tinkaton"]) == 2


@needs_node
@pytest.mark.integration
def test_bare_male_target_alone_still_rejects_female():
    """The male branch keys off the '(Female)' sibling existing in the
    POKEMON INDEX, not in the threshold dict -- Python reads the full
    gamemaster index, so a JS caller handed a threshold-only subset would
    silently go permissive here."""
    py, js = _both_sides(_GENDER_CSV, _MALE_THRESHOLDS,
                         LEAGUE_MAX_LEVEL["great"])
    assert py == js
    assert _species_ivs(py, "Oinkologne") == [(5, 11, 15), (7, 7, 7)]


@needs_node
@pytest.mark.integration
def test_require_gender_matches_python_prefilter():
    """opts.requireGender is the one deliberate JS-only extension: an
    extra caller-global narrowing on top of the per-target rule."""
    py, js = _both_sides(_GENDER_CSV, _GENDER_THRESHOLDS,
                         LEAGUE_MAX_LEVEL["great"], require_gender="female")
    assert py == js
    # The male 5/11/15 row is gone from BOTH targets -- the narrowing drops
    # the mon, not just the mismatched target. The blank-gender row is
    # permissive on both sides and still reaches both.
    assert _species_ivs(py, "Oinkologne") == [(7, 7, 7)]
    assert _species_ivs(py, "Oinkologne (Female)") == [(4, 13, 8), (7, 7, 7)]


# ---------------------------------------------------------------------------
# entry 9 -- league-derived level ceilings
# ---------------------------------------------------------------------------

@needs_node
@pytest.mark.integration
def test_match_mons_default_max_level_agrees():
    """Both ports resolve maxLevel=None from the league (great -> 50.0)."""
    py, js = _both_sides(_CEILING_CSV, _CEILING_THRESHOLDS, None)
    assert py == js
    assert [r["stats"]["level"] for r in py["Lechonk"]] == [50]
    # Explicit best-buddy cap still reaches 51 on both sides.
    py_bb, js_bb = _both_sides(_CEILING_CSV, _CEILING_THRESHOLDS, 51.0)
    assert py_bb == js_bb
    # (Both rows now build to 51: the 50.0 row can still power up to it.)
    assert [r["stats"]["level"] for r in py_bb["Lechonk"]] == [51, 51]


@needs_node
def test_ivs_to_stats_at_cap_default_ceiling_agrees():
    """ivsToStatsAtCap has no league argument, so both ports derive the
    ceiling from the CP cap. No gamemaster needed: base stats are passed
    in directly."""
    program = """
const mod = require(%s);
let raw = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { raw += c; });
process.stdin.on('end', () => {
  const p = JSON.parse(raw);
  mod.setConstants({ cpm: p.cpm });
  const out = p.cases.map(c => mod.ivsToStatsAtCap(100, 100, 100, 15, 15, 15,
    (c.maxCp != null) ? { maxCp: c.maxCp } : {}).level);
  process.stdout.write(JSON.stringify(out));
});
""" % json.dumps(str(_JS))
    cases = [{"maxCp": None}, {"maxCp": LEAGUE_CAPS["ultra"]},
             {"maxCp": LEAGUE_CAPS["master"]}]
    payload = {"cpm": {str(k): v for k, v in CPM.items()}, "cases": cases}
    proc = subprocess.run(["node", "-e", program], input=json.dumps(payload),
                          capture_output=True, text=True, check=True)
    js_levels = json.loads(proc.stdout)

    py_levels = [
        ivs_to_stats_at_cap(100, 100, 100, 15, 15, 15)["level"],
        ivs_to_stats_at_cap(100, 100, 100, 15, 15, 15,
                            max_cp=LEAGUE_CAPS["ultra"])["level"],
        ivs_to_stats_at_cap(100, 100, 100, 15, 15, 15,
                            max_cp=LEAGUE_CAPS["master"])["level"],
    ]
    assert js_levels == py_levels
    # Pin the values too: the defaults must be league-derived, not 51.0.
    assert py_levels == [LEAGUE_MAX_LEVEL["great"], LEAGUE_MAX_LEVEL["ultra"],
                         LEAGUE_MAX_LEVEL["master"]] == [50.0, 50.0, 51.0]
