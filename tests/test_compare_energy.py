"""--compare-energy capture (Phase 2): post-match energy for the compare widget.

iv_sweep gains capture_energy=False; when True it returns a 5th value
canonical_energy (the focal's leftover energy per matchup, 0..100), parallel to
canonical_scores, via the same signature-dedup fan-out. When False the 5th value
is None and the score path is byte-identical.
"""
import importlib.util
import multiprocessing
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

if "deep_dive" in sys.modules:
    deep_dive = sys.modules["deep_dive"]
else:
    _spec = importlib.util.spec_from_file_location(
        "deep_dive", REPO_ROOT / "scripts" / "deep_dive.py")
    deep_dive = importlib.util.module_from_spec(_spec)
    sys.modules["deep_dive"] = deep_dive
    _spec.loader.exec_module(deep_dive)

from gopvpsim.data import get_default_moveset  # noqa: E402

RESERVE = max(0, multiprocessing.cpu_count() - 2)


def _sweep(capture):
    om = get_default_moveset('Azumarill', 'great')
    fm = get_default_moveset('Mimikyu', 'great')
    return deep_dive.iv_sweep(
        'Mimikyu', fm[0], fm[1], 'great', False,
        ['Azumarill'], [om], [(0, 0), (1, 1)],
        iv_floor=(13, 13, 13), reserve_cpus=RESERVE, capture_energy=capture)


def test_capture_energy_parallel_and_sane():
    _, _, cs, _, ce = _sweep(True)
    assert ce is not None
    assert len(ce) == len(cs)                  # one energy per matchup, same order
    assert all(0 <= e <= 100 for e in ce)      # leftover energy is clamped 0..100


def test_off_path_none_and_scores_byte_identical():
    _, _, cs_on, _, ce_on = _sweep(True)
    _, _, cs_off, _, ce_off = _sweep(False)
    assert ce_off is None                       # no energy captured when off
    assert ce_on is not None
    assert cs_on == cs_off                       # capturing energy must not move scores
