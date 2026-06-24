"""Best-buddy / Level-51 toggle (Phase 2, 2026-06-24).

Pins the load-bearing invariants of the best-buddy feature:

- The level math (bestbuddy_caps) and the metadata-time no-op suppression.
- focal_max_level raises ONLY the focal cap; the sweep cache key distinguishes
  L50 from L51; an IV whose level does NOT move keeps a byte-identical score
  column (so best-buddy is a true no-op where it changes nothing).
- The opponent over-level seam (opp_max_level).
- The per-species [Species.best_buddy] TOML read.
"""
import importlib.util
import multiprocessing
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Load deep_dive.py as a module under the canonical name (shared contract with
# test_sweep_cache.py / test_energy_lead.py: a single shared module object so
# multiprocessing worker pickling resolves).
if "deep_dive" in sys.modules:
    deep_dive = sys.modules["deep_dive"]
else:
    _spec = importlib.util.spec_from_file_location(
        "deep_dive", REPO_ROOT / "scripts" / "deep_dive.py")
    deep_dive = importlib.util.module_from_spec(_spec)
    sys.modules["deep_dive"] = deep_dive
    _spec.loader.exec_module(deep_dive)

import sweep_cache  # noqa: E402

from gopvpsim.pokemon import bestbuddy_caps, Pokemon, MAX_CPM_LEVEL  # noqa: E402
from gopvpsim.data import get_default_moveset  # noqa: E402

RESERVE = max(0, multiprocessing.cpu_count() - 2)


# ---------------------------------------------------------------------------
# Level math + no-op suppression
# ---------------------------------------------------------------------------

def test_bestbuddy_caps_master_is_suppressed():
    """Master/Little already cap at 51 -> alt == default -> toggle suppressed."""
    for league in ('master', 'little'):
        default, alt = bestbuddy_caps(league)
        assert default == alt == MAX_CPM_LEVEL

def test_bestbuddy_caps_great_ultra_open():
    for league in ('great', 'ultra'):
        default, alt = bestbuddy_caps(league)
        assert (default, alt) == (50.0, 51.0)


def _levels(species, league, cap):
    meta = deep_dive.compute_iv_metadata(species, league, focal_max_level=cap)
    return [m['level'] for m in meta]

def test_no_op_detection_capped_species():
    """A high-base-stat GL species CP-caps far below 50 even at 0/0/0, so NO IV
    can move at L51 -> best-buddy is a genuine no-op (Mewtwo GL maxes ~L14)."""
    d, a = bestbuddy_caps('great')
    assert _levels('Mewtwo', 'great', d) == _levels('Mewtwo', 'great', a)

def test_no_op_detection_level_capped_species():
    """A weak UL species reaches L50 under the cap, so raising to L51 moves IVs."""
    d, a = bestbuddy_caps('ultra')
    lv_d = _levels('Wobbuffet', 'ultra', d)
    lv_a = _levels('Wobbuffet', 'ultra', a)
    assert any(x != y for x, y in zip(lv_d, lv_a))


# ---------------------------------------------------------------------------
# Sweep cache key
# ---------------------------------------------------------------------------

def test_focal_key_distinguishes_l50_l51():
    base = dict(species='Mimikyu', league='ultra', shadow=False,
                fast_id='SHADOW_CLAW', charged_ids=['SHADOW_SNEAK'],
                iv_floor=None, shield_scenarios=[(1, 1)], bait_mode='bait')
    k50 = sweep_cache.focal_key_fields(**base, focal_max_level=50.0)
    k51 = sweep_cache.focal_key_fields(**base, focal_max_level=51.0)
    assert k50 != k51
    assert k50['focal_max_level'] == 50.0 and k51['focal_max_level'] == 51.0


# ---------------------------------------------------------------------------
# iv_sweep: focal-only level cap
# ---------------------------------------------------------------------------

def _sweep(species, league, focal_max_level=None, opp_max_level=None,
           iv_floor=(14, 14, 14), opponent='Azumarill'):
    om = get_default_moveset(opponent, league)
    fm = get_default_moveset(species, league)
    return deep_dive.iv_sweep(
        species, fm[0], fm[1], league, False,
        [opponent], [om], [(0, 0), (1, 1)],
        iv_floor=iv_floor, reserve_cpus=RESERVE,
        focal_max_level=focal_max_level, opp_max_level=opp_max_level)

def test_no_op_sweep_is_byte_identical():
    """Best-buddy at GL for a CP-capped species is a true no-op end to end:
    the L51 canonical scores equal the L50 ones exactly."""
    _, _, cs50, cm50 = _sweep('Azumarill', 'great', focal_max_level=50.0)
    _, _, cs51, cm51 = _sweep('Azumarill', 'great', focal_max_level=51.0)
    assert cm50 == cm51            # same per-IV levels/stats
    assert cs50 == cs51            # same scores

def test_unchanged_iv_keeps_score_column():
    """Invariant: an IV whose best level does NOT move between L50 and L51 must
    have a byte-identical score column; only level-moving IVs may differ."""
    n_scen = 2
    r50, _, cs50, cm50 = _sweep('Mimikyu', 'ultra', focal_max_level=50.0,
                                iv_floor=(13, 13, 13))
    r51, _, cs51, cm51 = _sweep('Mimikyu', 'ultra', focal_max_level=51.0,
                                iv_floor=(13, 13, 13))
    n = len(cm50)
    assert n == len(cm51) and len(cs50) == len(cs51)
    width = len(cs50) // n          # scores per IV (n_scen * n_opp)
    moved = unchanged = 0
    for i in range(n):
        lvl50, lvl51 = cm50[i][3], cm51[i][3]
        col50 = cs50[i * width:(i + 1) * width]
        col51 = cs51[i * width:(i + 1) * width]
        if lvl50 == lvl51:
            assert col50 == col51, f"unchanged IV {cm50[i][:3]} changed score"
            unchanged += 1
        else:
            moved += 1
    # The fixture must actually exercise the moving branch to be meaningful.
    assert moved > 0


# ---------------------------------------------------------------------------
# Opponent over-level seam
# ---------------------------------------------------------------------------

def test_opp_max_level_seam_raises_opponent_level():
    """opp_max_level lifts a level-capped opponent above its league default."""
    default = Pokemon.at_best_level('Wobbuffet', 0, 15, 15, league='ultra')
    raised = Pokemon.at_best_level('Wobbuffet', 0, 15, 15, league='ultra',
                                   max_level=51.0)
    assert raised.level > default.level


# ---------------------------------------------------------------------------
# TOML persistence read
# ---------------------------------------------------------------------------

def test_read_best_buddy_toml_absent_is_empty():
    """A species with no threshold TOML (or no [best_buddy] table) -> {}."""
    assert deep_dive._read_best_buddy_toml('Wobbuffet', False) == {}
