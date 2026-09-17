"""scripts/prune_unlisted_dives.py: dropped dives leave the site.

Pre-fix state (2026-09-17): the 2026-09-17 pool regeneration dropped three
GL dives (galarian-moltres, shadow-dragonair, shadow-kingdra) from the
registry while their pages stayed under userdata/website; run_website_dives
never removes a directory, build_website_index lists whatever exists, and
publish_website.sh's ``rsync --delete`` only mirrors the local tree -- so the
three would have stayed published. Nothing gated it.
"""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import prune_unlisted_dives as P  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _site(tmp_path, names):
    site = tmp_path / 'website'
    for n in names:
        d = site / n
        d.mkdir(parents=True)
        (d / 'index.html').write_text('<html></html>')
    (site / 'index.html').write_text('<html></html>')
    return site


def test_only_unlisted_dive_shaped_dirs_are_selected(tmp_path):
    site = _site(tmp_path, ['sableye-great-league', 'shadow-kingdra-great-league',
                            'tinkaton-ultra-league', 'articles', 'comparisons',
                            'matchups-ultra', 'guides'])
    gone = P.unlisted_dive_dirs(str(site), ['sableye-great-league', 'tinkaton-ultra-league'])
    assert gone == ['shadow-kingdra-great-league']


def test_non_dive_dirs_are_never_candidates_even_when_unlisted(tmp_path):
    # Positive control for the shape rule: a non-league name is never
    # selected, whatever the registry says.
    site = _site(tmp_path, ['articles', 'matchups', 'x-master-league'])
    assert P.unlisted_dive_dirs(str(site), []) == ['x-master-league']


def test_dry_run_deletes_nothing_and_exits_one(tmp_path, monkeypatch, capsys):
    site = _site(tmp_path, ['sableye-great-league', 'shadow-kingdra-great-league'])
    monkeypatch.setattr(P, 'all_dives', None, raising=False)
    import dive_registry
    monkeypatch.setattr(dive_registry, 'all_dives',
                        lambda: [{'slug': 'sableye-great-league'}])
    rc = P.main(['--site', str(site)])
    assert rc == 1
    assert (site / 'shadow-kingdra-great-league' / 'index.html').exists()
    assert 'shadow-kingdra-great-league' in capsys.readouterr().out


def test_apply_removes_exactly_the_unlisted_dive_dirs(tmp_path, monkeypatch):
    site = _site(tmp_path, ['sableye-great-league', 'shadow-kingdra-great-league',
                            'galarian-moltres-great-league', 'articles'])
    import dive_registry
    monkeypatch.setattr(dive_registry, 'all_dives',
                        lambda: [{'slug': 'sableye-great-league'}])
    rc = P.main(['--site', str(site), '--apply'])
    assert rc == 0
    assert sorted(os.listdir(site)) == ['articles', 'index.html', 'sableye-great-league']


def test_clean_site_exits_zero(tmp_path, monkeypatch):
    site = _site(tmp_path, ['sableye-great-league'])
    import dive_registry
    monkeypatch.setattr(dive_registry, 'all_dives',
                        lambda: [{'slug': 'sableye-great-league'}])
    assert P.main(['--site', str(site)]) == 0


def test_publish_script_gates_on_the_prune_dry_run():
    """The gate is wired into publish_website.sh, honours --skip-verify, and
    names the fix. A positive control keeps the scan honest: the completeness
    gate that precedes it is still there."""
    src = (REPO / 'scripts' / 'publish_website.sh').read_text()
    assert re.search(r'prune_unlisted_dives\.py --site "\$SRC"', src)
    gate = src[src.index('prune_unlisted_dives.py --site'):]
    assert 'prune_unlisted_dives.py --apply' in gate[:600]
    pre = src[:src.index('prune_unlisted_dives.py --site')]
    assert '"$SKIP_VERIFY" = false' in pre[-400:]
    assert 'EXPECTED_DIVES=' in src  # positive control: the earlier gate


@pytest.mark.local_artifacts
def test_live_tree_dry_run_names_the_three_dropped_dives_or_is_clean():
    """On this machine, right after the 2026-09-17 regeneration, the dry run
    lists the three dropped GL dives; once pruned it is clean. Either state
    is acceptable; a registry slug must never be listed."""
    site = REPO / 'userdata' / 'website'
    if not site.is_dir():
        pytest.skip('no local website tree')
    import dive_registry
    slugs = [d['slug'] for d in dive_registry.all_dives()]
    gone = P.unlisted_dive_dirs(str(site), slugs)
    assert not set(gone) & set(slugs)
