"""The product default is the turn system the game actually runs.

Changed 2026-09-02 (Michael) for the CLIs; extended 2026-09-09 to
`simulate()` itself and the oracle harness once PvPoke merged its
new-mechanics work to master.

The 2026-09-02 version of this module argued that `simulate()`'s default had
to STAY legacy, because the ~92 legacy-pinned assertions check our engine
against PvPoke ground truth and PvPoke master still ran the legacy turn
system. That reasoning was correct and it EXPIRED on 2026-09-09: master now
runs the new system, so legacy-pinned oracle comparisons measure a dead model
against a live one.

Keeping legacy as the library default had also become actively dangerous.
Seven scripts call `simulate()` without passing `mechanics` and inherit the
default -- including `build_matchup_web.py`, which renders a PUBLISHED
cross-species page. They were all silently modelling a ruleset nobody can
play, with nothing to warn them.

Cost of the flip, measured: the fast tier goes 104 -> 187 failures. Those 83
are legacy-pinned expectations that now need re-deriving against the merged
reference, which is tracked as its own step rather than hidden here.
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

from mechanics_notice import mechanics_caveat  # noqa: E402


def _argparse_default(path, opt='--mechanics'):
    """The `default=` on an add_argument call, read from source."""
    src = (REPO / path).read_text()
    m = re.search(re.escape(f"add_argument('{opt}'") + r".*?default='(\w+)'",
                  src, re.S)
    assert m, f'no {opt} default found in {path}'
    return m.group(1)


@pytest.mark.parametrize('path', [
    'scripts/deep_dive.py',
    'scripts/battle.py',
])
def test_product_clis_default_to_the_live_turn_system(path):
    """A dive must model the game people can actually play."""
    assert _argparse_default(path) == 'new', (
        f'{path} still defaults to the retired turn system')


def test_the_oracle_harness_follows_pvpoke_master():
    """It answers "is our PORT faithful?", and PvPoke master is now NEW.

    Flipped 2026-09-09 when the turn-system work merged to master. Keeping it
    on legacy would compare our dead model against their live one, which
    measures nothing. This is the condition the old version of this test named
    as its own flip trigger.
    """
    assert _argparse_default('scripts/audit_oracle_harness.py') == 'new', (
        'the oracle harness follows PvPoke master, which now runs the new '
        'turn system; leaving it on legacy compares two different rulesets')


def test_simulate_signature_defaults_to_the_live_turn_system():
    """The library default, not just the CLIs.

    Flipped 2026-09-09. Leaving it at legacy made it a SILENT TRAP: seven
    scripts call simulate() without passing mechanics (build_matchup_web,
    joint_iv_breakpoints, owned_breakdown, energy_probe, etm_iv_floor_sweep,
    check_sableye_energy_lead, cramorant_policy_lab), so each was quietly
    modelling a ruleset nobody can play. build_matchup_web is the worst of
    them -- it renders a PUBLISHED cross-species page.
    """
    import inspect
    from gopvpsim.battle import simulate
    assert inspect.signature(simulate).parameters['mechanics'].default == 'new'


def test_both_models_carry_a_caveat():
    """Both still need saying, but for opposite reasons now.

    `new` is correct-but-not-perfect (6 open Aegislash cells); `legacy` is a
    dead ruleset. Neither may be silent, and the `new` caveat matters most
    because it is what someone gets without asking.
    """
    new = mechanics_caveat('new')
    assert new and '237' in new and 'Aegislash' in new, (
        'the new-model caveat must name the actual open divergence, not a '
        'stale count -- it claimed 104 mismatches until 2026-09-09')
    legacy = mechanics_caveat('legacy')
    assert legacy and 'does not run it' in legacy
    assert mechanics_caveat('nonsense') is None


def test_the_new_default_cannot_collide_with_cached_legacy_columns():
    """A bake under the new default must not serve legacy-simmed columns.

    This is the interaction that makes the flip safe: `mechanics` is in both
    disk cache keys, so the ~153,000 committed legacy columns are keyed
    distinctly from anything the new default produces.
    """
    import sweep_cache as swc
    from slayer_cache import compute_cache_key
    base = dict(species='Azumarill', league='great', shadow=False,
                fast_id='BUBBLE', charged_ids=['ICE_BEAM'], iv_floor=None,
                shield_scenarios=[[1, 1]], bait_mode='bait')
    assert (swc.focal_key_fields(**base, mechanics='new')
            != swc.focal_key_fields(**base, mechanics='legacy'))
    sbase = dict(species='Azumarill', league='great', shadow=False,
                 fast_move={'moveId': 'BUBBLE'},
                 charged_moves=[{'moveId': 'ICE_BEAM'}],
                 base_stats={'atk': 1, 'def': 1, 'hp': 1})
    assert (compute_cache_key(**sbase, mechanics='new')
            != compute_cache_key(**sbase, mechanics='legacy'))
