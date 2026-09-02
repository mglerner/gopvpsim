"""The product default is the turn system the game actually runs.

Changed 2026-09-02 (Michael): the legacy turn system is gone from the live
game, so a dive that models it describes a game nobody can play. Modelling the
current ruleset approximately beats modelling a dead one exactly.

The flip is deliberately at the PRODUCT boundary (the CLIs that generate
published numbers), not at `gopvpsim.battle.simulate`'s signature. That is not
timidity -- it is what keeps the verification asset intact:

  * The ~92 legacy-pinned assertions across tests/ check our engine against
    PvPoke ground truth. They are what proves the port is faithful.
  * PvPoke master still runs the LEGACY turn system, so that check is only
    meaningful under `mechanics='legacy'`.
  * Re-baselining them to `new` would make them pin OUR OWN unvalidated
    model's output with no oracle behind it -- a suite that can only confirm
    we still do whatever we currently do.

So `simulate()`'s default stays legacy until PvPoke's turn-system work merges
and the re-port lands; at that point both flip together and the oracle becomes
meaningful again. Sequence recorded in TODO.md.
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


def test_the_oracle_harness_stays_on_legacy():
    """It answers "is our PORT faithful?", and PvPoke master is legacy.

    Flipping this one would take it from 0 mismatches to 57 (measured) and
    destroy the only instrument that verifies the port. It flips when PvPoke's
    turn-system work merges, not before.
    """
    assert _argparse_default('scripts/audit_oracle_harness.py') == 'legacy', (
        'the oracle harness follows PvPoke master, which still runs the '
        'legacy turn system; flipping it makes the audit self-referential')


def test_simulate_signature_default_is_still_legacy_on_purpose():
    """Pinned so the reason is recorded, not so the value is sacred.

    See this module's docstring: re-baselining the legacy-pinned suite to
    `new` would make it pin our own unvalidated output. When the re-port lands
    this test changes together with those fixtures.
    """
    import inspect
    from gopvpsim.battle import simulate
    assert inspect.signature(simulate).parameters['mechanics'].default == 'legacy'


def test_both_models_carry_a_caveat():
    """Neither setting is simply correct, so neither may be silent.

    `new` being the default makes its caveat MORE important, not less -- it is
    now what someone gets without asking.
    """
    for model in ('legacy', 'new'):
        msg = mechanics_caveat(model)
        assert msg and len(msg) > 80, model
        assert 'UNVALIDATED' in msg or 'no longer runs' in msg, model
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
