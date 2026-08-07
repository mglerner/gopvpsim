"""Ship-gate roster single-sourcing (DRY review 2026-08-05 entry 3b).

run_ship_gates.SHIP_GATES is THE roster; the four entry points
(publish_website.sh, overnight_redive.sh, phase2_preship.sh,
verify_overnight.py) must all route through it -- two of them once ran
only the link gate, so a chain printed SUCCESS with dash violations
present. These tests pin the roster contents and the routing.
"""
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
    vo = (_SCRIPTS / 'verify_overnight.py').read_text()
    assert 'from run_ship_gates import SHIP_GATES' in vo
