"""Ship-gate roster single-sourcing (DRY review 2026-08-05 entry 3b).

run_ship_gates.SHIP_GATES is THE roster; the four entry points
(publish_website.sh, overnight_redive.sh, phase2_preship.sh,
verify_overnight.py) must all route through it -- two of them once ran
only the link gate, so a chain printed SUCCESS with dash violations
present. These tests pin the roster contents and the routing.
"""
import ast
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from run_ship_gates import SHIP_GATES  # noqa: E402

_SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def test_roster_has_all_gates():
    names = [g for g, _ in SHIP_GATES]
    assert 'verify_article_links.py' in names
    assert 'verify_no_unicode_dashes.py' in names
    # Wired 2026-08-06: dev-count sentinels render into the published
    # guides, so their drift check ships with everything else.
    assert 'verify_dev_counts.py' in names
    # Wired 2026-08-09 (test-suite review Phase 1): the fast test tier
    # runs on every publish path; no gate ran pytest before this.
    assert 'verify_tests.py' in names


def test_verify_tests_gate_is_loud_without_node(monkeypatch):
    import verify_tests
    monkeypatch.setattr(verify_tests.shutil, 'which', lambda _: None)
    assert verify_tests.main() == 1


def test_verify_tests_gate_runs_the_fast_tier(monkeypatch):
    """With node present, the gate execs pytest -m 'not slow' and
    propagates its return code (subprocess faked -- running the real
    suite from inside itself would recurse)."""
    import verify_tests
    monkeypatch.setattr(verify_tests.shutil, 'which',
                        lambda _: '/usr/bin/node')
    calls = []

    class _R:
        returncode = 0

    def fake_run(argv, **kw):
        calls.append(argv)
        return _R()
    monkeypatch.setattr(verify_tests.subprocess, 'run', fake_run)
    assert verify_tests.main() == 0
    (argv,) = calls
    assert '-m' in argv and 'not slow' in argv and 'pytest' in argv


def test_roster_entries_carry_full_argv():
    # Entries are (script, FULL argv) -- not every gate takes --ship, so
    # nothing may inject it globally (that regression breaks
    # verify_dev_counts). The two site gates must still carry it.
    argv = dict(SHIP_GATES)
    assert '--ship' in argv['verify_article_links.py']
    assert '--ship' in argv['verify_no_unicode_dashes.py']
    assert '--ship' not in argv['verify_dev_counts.py']


def test_roster_gates_exist_on_disk():
    for gate, _ in SHIP_GATES:
        assert (_SCRIPTS / gate).exists(), gate


def test_entry_points_route_through_the_roster():
    for entry in ('publish_website.sh', 'overnight_redive.sh',
                  'phase2_preship.sh'):
        text = (_SCRIPTS / entry).read_text()
        assert 'run_ship_gates.py' in text, entry
        # No entry point may invoke an individual gate directly anymore
        # (comments naming them are fine; command lines are not).
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            assert 'verify_article_links.py' not in stripped, (entry, line)
            assert 'verify_no_unicode_dashes.py' not in stripped, (entry, line)
    # The fourth entry point imports the roster rather than shelling out.
    # Structural (ast), not an import-line substring: verify_overnight's
    # import is function-local, so an isort/wrap/alias must not break this,
    # while DROPPING it must (2026-08-09 test-suite review, Phase 3).
    vo_imports = [n for n in ast.walk(
        ast.parse((_SCRIPTS / 'verify_overnight.py').read_text()))
        if isinstance(n, ast.ImportFrom) and n.module == 'run_ship_gates'
        and any(a.name == 'SHIP_GATES' for a in n.names)]
    assert vo_imports, 'verify_overnight stopped importing the shared roster'
