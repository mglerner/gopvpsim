"""One even-shield scenario set for every surface that follows the convention.

The XehrFelrose convention the ML IV guide, the owned-collection breakdown,
and the dive's matchup-cluster section all use is "even shields only" -- both
sides bring the same count, so the comparison isolates the spread rather than
the shield read. That set was written out three times
(``iv_envelope_analysis.EVEN_SHIELDS``, ``owned_breakdown.EVEN_SHIELDS``,
``deep_dive_matchup_clusters.EVEN_SHIELD_PAIRS``) and agreed only by luck:
dropping 2-2 meant editing three files, and a missed one silently sims a
different scenario set with no error. It now lives in
``deep_dive_lib.shields``.

Identity (``is``), not equality: equality still passes against a fresh copy,
which is exactly the failure mode the consolidation removes.
"""
import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(SCRIPTS))

from deep_dive_lib.shields import EVEN_SHIELDS  # noqa: E402

from tests.conftest import load_deep_dive  # noqa: E402


def test_even_shields_is_the_xehrfelrose_convention():
    assert EVEN_SHIELDS == ((0, 0), (1, 1), (2, 2))


def test_even_shields_is_immutable():
    """It is handed out as a default argument in more than one module."""
    assert isinstance(EVEN_SHIELDS, tuple)
    assert all(isinstance(p, tuple) for p in EVEN_SHIELDS)


def test_matchup_clusters_uses_the_shared_set():
    spec = importlib.util.spec_from_file_location(
        "deep_dive_matchup_clusters", SCRIPTS / "deep_dive_matchup_clusters.py")
    mc = importlib.util.module_from_spec(spec)
    sys.modules["deep_dive_matchup_clusters"] = mc
    spec.loader.exec_module(mc)
    assert mc.EVEN_SHIELD_PAIRS is EVEN_SHIELDS


def test_owned_breakdown_uses_the_shared_set():
    load_deep_dive()      # owned_breakdown does `from deep_dive import ...`
    import owned_breakdown as ob
    assert ob.EVEN_SHIELDS is EVEN_SHIELDS
    # bottle_cap_advisor.py imports the name from here, so the re-export is
    # load-bearing, not incidental.
    assert "EVEN_SHIELDS" in (SCRIPTS / "bottle_cap_advisor.py").read_text()


def test_iv_envelope_uses_the_shared_set():
    load_deep_dive()
    import iv_envelope_analysis as iva
    assert iva.EVEN_SHIELDS is EVEN_SHIELDS


# Modules that STILL open-code the triple. Each is outside the file set of
# the consolidation that created shields.py, so swapping them is a separate
# change; this set may only shrink. Nothing here is wrong today -- they agree
# by value -- but each is a place the convention can silently diverge.
KNOWN_OPEN_CODED = {
    "deep_dive.py",                      # EVEN_THREE, a --shields default
    "deep_dive_rendering.py",            # _target_scens
    "export_owned_breakdown_bundle.py",  # EVEN (a set)
    "harness_grid.py",                   # shield_pairs
    "verify_signature_dedup.py",         # EVEN
}


def test_open_coded_even_shield_triples_only_shrink():
    """Monotone guard: the (0,0)/(1,1)/(2,2) literal may leave, never spread.

    The three modules this consolidation covered are absent from the known
    set, so re-introducing a copy in any of them trips this.
    """
    pat = re.compile(r"\(0,\s*0\)\s*,\s*\(1,\s*1\)\s*,\s*\(2,\s*2\)")
    found = {p.name for p in SCRIPTS.rglob("*.py")
             if p.name != "shields.py" and pat.search(p.read_text())}
    assert found <= KNOWN_OPEN_CODED, \
        f"new open-coded even-shield set: {found - KNOWN_OPEN_CODED}"
