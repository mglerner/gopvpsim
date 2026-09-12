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

def _mechanics_help(path):
    """The `help=` string on the --mechanics add_argument, read via ast.

    ast rather than a raw regex because the help is an implicitly-concatenated
    multi-line string literal, which a line-oriented regex reads only the first
    fragment of -- and the first fragment is exactly where the stale
    "legacy (default)" claim lived.
    """
    import ast
    tree = ast.parse((REPO / path).read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and getattr(node.func, 'attr', None) == 'add_argument'
                and node.args
                and getattr(node.args[0], 'value', None) == '--mechanics'):
            for kw in node.keywords:
                if kw.arg == 'help':
                    return ast.literal_eval(kw.value)
    raise AssertionError(f'no --mechanics help found in {path}')


@pytest.mark.parametrize('path', [
    'scripts/battle.py',
    'scripts/deep_dive.py',
    'scripts/audit_oracle_harness.py',
])
def test_mechanics_help_does_not_contradict_its_own_default(path):
    """Help text that names the wrong default is a lie the user reads first.

    scripts/battle.py said "legacy (default)" for six weeks after the default
    flipped to new (2026-09-09), so `--help` told everyone the opposite of what
    the tool does. The argparse `default=` is the ground truth; this pins the
    prose to it.

    Positive control: the length floor fails if the help is emptied or the ast
    walk silently returns something trivial, so this cannot pass vacuously.
    """
    help_text = _mechanics_help(path)
    assert len(help_text) > 50, 'help text is missing or trivial'
    default = _argparse_default(path)
    other = 'legacy' if default == 'new' else 'new'
    assert f'{other} (default)' not in help_text, (
        f'{path} --help calls {other!r} the default, but argparse uses '
        f'{default!r}')

@pytest.mark.parametrize('path', [
    'scripts/battle.py',
    'scripts/deep_dive.py',
])
def test_mechanics_help_oracle_count_matches_the_canonical_caveat(path):
    """A stale validation COUNT is the failure the default-check misses.

    deep_dive.py's help claimed `new` was "still UNVALIDATED (104/243 oracle
    cells disagree ... unmerged new-mechanics branch)" for three days after the
    2026-09-09 merge made it 237/243 matching. Both halves were wrong and
    test_mechanics_help_does_not_contradict_its_own_default passed the whole
    time, because the DEFAULT was named correctly.

    scripts/mechanics_notice.py is the canonical wording, so any oracle-cell
    count appearing in a --mechanics help string must agree with it. Pins the
    numbers, not the prose: rewording either is free, disagreeing is not.
    """
    import re
    help_text = _mechanics_help(path)
    canonical = mechanics_caveat('new')
    canon_nums = set(re.findall(r'\b(\d{2,3})\b(?=\s*(?:of|/)\s*243)',
                                canonical))
    assert canon_nums, 'no "N of 243" figure found in mechanics_notice'
    help_nums = set(re.findall(r'\b(\d{2,3})\b(?=\s*(?:of|/)\s*243)',
                               help_text))
    if not help_nums:
        pytest.skip(f'{path} help cites no oracle-cell count')
    assert help_nums <= canon_nums, (
        f'{path} --help cites oracle counts {sorted(help_nums - canon_nums)} '
        f'of 243, which mechanics_notice.py does not; it says '
        f'{sorted(canon_nums)}. Update the help or the caveat so they agree.')
