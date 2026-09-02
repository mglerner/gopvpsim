"""The turn-resolution model must be part of both disk cache keys.

`mechanics` ('legacy' | 'new') changes scores, so a 'new'-mechanics column must
never be served to a 'legacy' sweep or vice versa. Before 2026-09-02 the model
was absent from BOTH keys and the callers compensated by force-disabling the
disk cache under `--mechanics new`. That was correct but not affordable: a
new-mechanics dive could never be warm -- every re-dive cold, forever, with no
migration path -- which stopped being an academic concern the moment the
in-game turn system moved.

Both keys follow the same rule as the column-side `policy` field: the BASE
value contributes nothing, so introducing the field invalidated no existing
cached column. That property is the whole reason this could ship without a
cold cache, so it is pinned first and hardest.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

import sweep_cache as swc            # noqa: E402
from slayer_cache import compute_cache_key  # noqa: E402

SWEEP_BASE = dict(
    species='Azumarill', league='great', shadow=False, fast_id='BUBBLE',
    charged_ids=['ICE_BEAM', 'PLAY_ROUGH'], iv_floor=None,
    shield_scenarios=[[0, 0], [1, 1], [2, 2]], bait_mode='bait')

SLAYER_BASE = dict(
    species='Azumarill', league='great', shadow=False,
    fast_move={'moveId': 'BUBBLE'},
    charged_moves=[{'moveId': 'ICE_BEAM'}, {'moveId': 'PLAY_ROUGH'}],
    base_stats={'atk': 112, 'def': 152, 'hp': 225})


def test_sweep_key_legacy_is_byte_identical_to_omitting_it():
    """Introducing the field must not have cold-invalidated the cache.

    ~153,000 committed columns were simmed before this field existed. If the
    default added a key, every one of them would have been orphaned.
    """
    assert swc.focal_key_fields(**SWEEP_BASE) == \
        swc.focal_key_fields(**SWEEP_BASE, mechanics='legacy')
    assert 'mechanics' not in swc.focal_key_fields(**SWEEP_BASE)


def test_slayer_key_legacy_is_byte_identical_to_omitting_it():
    assert compute_cache_key(**SLAYER_BASE) == \
        compute_cache_key(**SLAYER_BASE, mechanics='legacy')


def test_sweep_key_separates_new_from_legacy():
    legacy = swc.focal_key_fields(**SWEEP_BASE, mechanics='legacy')
    new = swc.focal_key_fields(**SWEEP_BASE, mechanics='new')
    assert legacy != new
    assert new['mechanics'] == 'new'


def test_slayer_key_separates_new_from_legacy():
    assert (compute_cache_key(**SLAYER_BASE, mechanics='legacy')
            != compute_cache_key(**SLAYER_BASE, mechanics='new'))


def test_neither_caller_force_disables_the_cache_any_more():
    """The point of keying it was to make a new-mechanics bake cacheable.

    Source-scan with a positive control: a refactor that removed the disable
    AND the key would otherwise pass every test above while silently letting
    a 'new' run collide with legacy columns.
    """
    sweep_src = (REPO / 'scripts' / 'deep_dive_lib' / 'sweep.py').read_text()
    dive_src = (REPO / 'scripts' / 'deep_dive.py').read_text()

    assert "if mechanics != 'legacy':\n        use_sweep_cache = False" not in sweep_src
    assert "args.mechanics == 'legacy'" not in dive_src, (
        'deep_dive still force-disables a disk cache under --mechanics new')

    # positive control: the key IS threaded through both call sites, so the
    # disable is gone because it became unnecessary, not because someone
    # deleted the safety without adding the key
    assert 'mechanics=mechanics' in sweep_src
    assert 'mechanics=args.mechanics' in dive_src


def test_the_key_is_the_only_thing_separating_the_two_models():
    """Everything else about the key must be unchanged by the model.

    Guards against a future edit that keys mechanics by mutating some other
    field (e.g. folding it into `bait` or `league`), which would work but
    would make migrate_cache's predicates unable to reason about it.
    """
    legacy = swc.focal_key_fields(**SWEEP_BASE, mechanics='legacy')
    new = swc.focal_key_fields(**SWEEP_BASE, mechanics='new')
    differing = {k for k in set(legacy) | set(new)
                 if legacy.get(k) != new.get(k)}
    assert differing == {'mechanics'}, differing
