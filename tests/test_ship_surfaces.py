"""Shared ship-surface enumeration (DRY review 2026-08-05 entry 3a).

Both ship gates (verify_article_links, verify_no_unicode_dashes) must
gate exactly what publish_website.sh rsyncs. Their private copies of
the enumeration only picked up index.html at the site root, so
cups.html and support.html shipped with ZERO checks. The enumeration
now lives in ship_surfaces.find_ship_surfaces; this pins the root-glob
fix and that both gates actually route through the shared module.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from ship_surfaces import find_ship_surfaces  # noqa: E402


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('<html></html>')


def test_root_pages_are_gated(tmp_path):
    site = tmp_path / 'website'
    for rel in ('index.html', 'cups.html', 'support.html',
                'guides/index.html', 'guides/iv-flavor-guide/index.html',
                'azumarill-great-league/index.html',
                'azumarill-great-league/index_m1_a_b.html',
                'azumarill-great-league/scores.json.gz'):
        _touch(site / rel)
    got = {str(p.relative_to(site)) for p in find_ship_surfaces(site)}
    assert 'cups.html' in got          # the previously-ungated root pages
    assert 'support.html' in got
    assert 'index.html' in got
    assert 'guides/iv-flavor-guide/index.html' in got
    assert 'azumarill-great-league/index_m1_a_b.html' in got
    assert 'azumarill-great-league/scores.json.gz' not in got


def test_both_gates_use_the_shared_module():
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    for gate in ('verify_article_links.py', 'verify_no_unicode_dashes.py'):
        text = (scripts / gate).read_text()
        assert 'from ship_surfaces import find_ship_surfaces' in text, gate
        # The old private enumeration must be gone.
        assert "sub.rglob('index*.html')" not in text, gate
