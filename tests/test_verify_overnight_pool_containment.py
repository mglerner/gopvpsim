"""Opponent-pool completeness guard in scripts/verify_overnight.py.

deep_dive.py resolves every pool line's default moveset and, on a
KeyError/ValueError from get_default_moveset, logs "skipping <name>: ..."
and drops the entry. So a species deranked out of a league's rankings
disappears from every dive in that league with nothing but a WARNING --
and until now only Great League had any pool guard at all (three marker
species), while Ultra/Master/cup dives had none.

A count assertion cannot catch this: the mirror entry, TOML anchor
opponents, atk-weighted variants and active_variants.toml all APPEND to
the opponent list, so measured slack (+3..+11) absorbs several silent
drops. The sound assertion is name-set containment against the dive's
own opponents_file, which is rankings-free and therefore cannot
self-drop the way a recomputed expected count would.

These tests pin missing_pool_entries()'s parsing (plain names, ' (Shadow)'
forms, and inline `| fast=` / `| charged=` override lines), and -- the
part that actually guards against drift -- check the real repo pools
against real rendered dives, so a change to either the pool parser or
the dive renderer's display-name spelling shows up here.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_overnight as vo  # noqa: E402

# missing_pool_entries() resolves `| fast=` / `| charged=` override lines
# through analysis.pretty_name, which reads the gamemaster -- so every test
# here needs a warm pvpoke cache, same as the rest of the integration set.
pytestmark = pytest.mark.integration

POOL_LINES = """\
# a comment line, plus a blank line below

Azumarill
Malamar (Shadow)
Forretress | fast=BUG_BITE
"""


@pytest.fixture
def pool(tmp_path):
    p = tmp_path / "pool.txt"
    p.write_text(POOL_LINES)
    return p


def _rendered_names():
    """Display names the pool file above should resolve to."""
    return ["Azumarill", "Malamar (Shadow)", "Forretress (Bug Bite)"]


def test_full_pool_is_contained(pool):
    # Extra opponents (mirror entry, anchors, variants) are fine -- this
    # is containment, not equality.
    opponents = _rendered_names() + ["Sableye (Shadow)", "Medicham"]
    assert vo.missing_pool_entries(opponents, pool) == []


def test_dropped_entry_is_reported_by_display_name(pool):
    opponents = [n for n in _rendered_names() if n != "Malamar (Shadow)"]
    assert vo.missing_pool_entries(opponents, pool) == ["Malamar (Shadow)"]


def test_dropped_override_entry_is_reported_with_its_suffix(pool):
    """The override line's expected display carries the pretty move name.

    This is the spelling deep_dive's renderer uses for the same line, so
    a drift between the two would surface as a phantom "missing" entry.
    """
    opponents = [n for n in _rendered_names() if "Forretress" not in n]
    assert vo.missing_pool_entries(opponents, pool) == ["Forretress (Bug Bite)"]
    # A bare 'Forretress' must NOT satisfy the override entry.
    assert vo.missing_pool_entries(opponents + ["Forretress"], pool) == [
        "Forretress (Bug Bite)"]


def test_comments_and_blank_lines_are_skipped(pool):
    # Nothing from the '#' line or the blank line leaks into the result.
    assert vo.missing_pool_entries([], pool) == _rendered_names()


def test_malformed_line_raises_rather_than_passing_silently(tmp_path):
    p = tmp_path / "bad.txt"
    p.write_text("Azumarill | fastBUG_BITE\n")
    with pytest.raises(ValueError):
        vo.missing_pool_entries(["Azumarill"], p)


def test_dive_pool_map_covers_every_dive_with_a_pool_file():
    from run_website_dives import DIVES

    pools = vo.dive_pool_map()
    declared = [d for d in DIVES if d.get("opponents_file")]
    # Compare against the DIVES entry count, not the slug set: dive_pool_map
    # is keyed by slug, so a duplicate slug silently last-wins and only a
    # count of the source entries can catch it.
    assert len(pools) == len(declared)
    for path in pools.values():
        assert path.exists(), f"declared pool file missing: {path}"


@pytest.mark.local_artifacts
def test_real_dives_contain_their_declared_pools():
    """Cross-path check: real pool files vs real rendered opponent lists.

    Skips dives that have not been rendered on this machine. Guards the
    pool parser and the renderer against drifting apart -- notably for
    the cup pools, whose lines are all `| fast= | charged=` overrides.
    """
    website = REPO_ROOT / "userdata" / "website"
    pools = vo.dive_pool_map()
    checked = 0
    for slug, pool_path in sorted(pools.items()):
        index = website / slug / "index.html"
        if not index.exists() or not pool_path.exists():
            continue
        opps = vo.extract_opponents(index)
        if opps is None:
            continue
        assert vo.missing_pool_entries(opps, pool_path) == [], slug
        checked += 1
    if not checked:
        pytest.skip("no rendered dives on this machine")


def test_default_markers_are_in_the_committed_gl_pool():
    """The pool markers must be species the current GL pool actually carries;
    otherwise the morning gate prints one false "markers missing" line per
    fresh dive (2026-09-22: 76 of them, for Sylveon and Primeape, which left
    the pool in the 2026-09-17 regeneration). Pre-fix DEFAULT_MARKERS =
    ['Sylveon', 'Primeape', 'Umbreon']."""
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'scripts'))
    import verify_overnight as vo
    pool = {ln.strip() for ln in (root / 'opponent_pools' / 'gl_top50_plus_cs.txt')
            .read_text().splitlines() if ln.strip() and not ln.startswith('#')}
    missing = [m for m in vo.DEFAULT_MARKERS if m not in pool]
    assert missing == [], missing
    assert len(vo.DEFAULT_MARKERS) >= 2


def test_a_marker_with_a_form_qualifier_is_matched_in_a_rendered_dive():
    """The markers check has to match the names a dive actually renders.

    Pre-fix (2026-09-22) check [3/5] compared ``o.split(' (')[0] == m``,
    which strips the FORM qualifier as well as the moveset annotation. The
    09-22 marker refresh moved DEFAULT_MARKERS to species that carry one --
    'Charjabug (Shadow)', 'Forretress (Shadow)', 'Oinkologne (Female)' --
    and every one of them became unmatchable: the gate printed the same 76
    "markers missing" lines the refresh was meant to clear, now for three
    different species that were present in every list.
    """
    rendered = ['Umbreon', 'Charjabug', 'Charjabug (Shadow)',
                'Forretress (Shadow)', 'Forretress (Bug Bite)',
                'Forretress (Shadow) (Bug Bite)', 'Diggersby',
                'Oinkologne (Female)']
    assert vo.missing_markers(rendered, vo.DEFAULT_MARKERS) == []
    # A moveset annotation on the marker itself still matches ...
    assert vo.missing_markers(['Umbreon (Foul Play)'], ['Umbreon']) == []
    # ... and a marker nothing names is still reported.
    assert vo.missing_markers(rendered, ['Sylveon']) == ['Sylveon']
    # Positive control on the pre-fix rule: it is the parenthetical markers
    # it could not see.
    prefix_only = [m for m in vo.DEFAULT_MARKERS
                   if not any(o.split(' (')[0] == m for o in rendered)]
    assert prefix_only == ['Charjabug (Shadow)', 'Forretress (Shadow)',
                           'Oinkologne (Female)']


@pytest.mark.local_artifacts
@pytest.mark.slow
def test_every_marker_is_found_in_a_real_rendered_dive():
    """The end of the chain the two tests above only cover in halves: the
    committed pool, the renderer's display names, and the matcher, on the
    dive dirs this machine actually has.

    Slow by measurement, not by caution: it reads every Great League dive's
    index.html (76 files, ~20 MB each) to find DATA.opponents, which is
    minutes of I/O -- too much for the fast tier the ship gate runs. The
    matcher itself is pinned hermetically by the test above."""
    website = REPO_ROOT / 'userdata' / 'website'
    checked = 0
    for index in sorted(website.glob('*-great-league/index.html')):
        opps = vo.extract_opponents(index)
        if opps is None:
            continue
        assert vo.missing_markers(opps, vo.DEFAULT_MARKERS) == [], index.parent.name
        checked += 1
    if not checked:
        pytest.skip('no rendered Great League dives on this machine')
