"""The overnight verifier's cup-dive glob must key on data.cup_slug_suffix.

``data.cup_slug_suffix``'s docstring promises that the slug PRODUCER
(run_website_dives), the index ROUTER (build_website_index) and "the overnight
verifier's glob" all key on one spelling of ``<cup>-cup``. The verifier used to
re-spell the literal ``'*-cup'`` instead, so a suffix change would have moved
two of the three consumers and silently left the freshness check globbing for
directories that no longer exist -- a check that finds nothing reports green.

These tests pin the derivation and, more importantly, the BEHAVIOUR: the glob
still matches a real cup dive slug (including a multi-word species) and still
does not match a league dive.
"""
import fnmatch
import sys
from pathlib import Path

from gopvpsim.data import cup_slug_suffix

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_overnight as vo  # noqa: E402


def test_cup_glob_is_derived_from_the_helper():
    """Not a re-spelled literal: change the helper, the glob follows."""
    assert cup_slug_suffix("*") in vo.CUP_DIR_GLOB
    assert vo.CUP_DIR_GLOB == f'*-{cup_slug_suffix("*")}'


def test_cup_glob_is_not_a_bare_literal_in_the_source():
    """The literal the helper exists to delete must not come back."""
    src = (REPO_ROOT / "scripts" / "verify_overnight.py").read_text()
    assert "glob('*-cup')" not in src
    assert 'glob("*-cup")' not in src


def test_cup_glob_matches_real_cup_slugs():
    """Slugs built the way run_website_dives builds them."""
    for species in ("clodsire", "galarian-corsola", "shadow-alolan-ninetales"):
        for cup in ("equinox", "love"):
            slug = f"{species}-{cup_slug_suffix(cup)}"
            assert fnmatch.fnmatch(slug, vo.CUP_DIR_GLOB), slug


def test_cup_glob_does_not_match_league_dives():
    """League dirs come in via the separate '*-league' glob; no double-count."""
    for slug in ("azumarill-great-league", "galarian-corsola-ultra-league",
                 "articles", "comparisons", "guides"):
        assert not fnmatch.fnmatch(slug, vo.CUP_DIR_GLOB), slug
