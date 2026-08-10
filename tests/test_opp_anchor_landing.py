"""``#opp-<slug>`` must land on the opponent's matchup detail, and must
exist in BOTH best-buddy copies of the prose.

``opp_anchor_id()`` (deep_dive_rendering.py) is first-mention-wins per
output file: the FIRST section to render a given opponent gets
``id="opp-<slug>"`` and every later mention emits nothing. That makes two
things load-bearing that no other test pins:

1. **Claim order inside ``render_results_section``.** The Anchor-Driven
   Matchup Flips bullets are appended to the page AFTER the opponent-threats
   section but used to be *computed* before it, so they claimed the anchor
   for ~2/3 of all opponents and every ``#opp-`` deep link landed on a
   damage-tier bullet inside a collapsed list instead of the opponent's
   matchup row. The fix is purely an ordering one, which means a future edit
   that hoists the computation back up would silently undo it -- the
   duplicate-id guard in ``test_dive_dom_ids.py`` cannot see it, because
   first-mention-wins keeps the ids unique either way.

2. **The per-level registry reset for the best-buddy template.** With best
   buddy active the L51 prose is a second full copy of the body; without a
   reset between the two passes it inherits an exhausted registry and ships
   zero opponent ids, so every ``#opp-`` link dangles after a toggle.

The anchor bullets deliberately keep ``emit_opponent_ids=True`` as the
FALLBACK claimer: ``render_opponent_threats_section`` can return '' (no
spread IVs / no opponents / no scores), and dropping the flag would shrink
the anchored-opponent set that ``generate_article.py`` scrapes to decide
link-vs-plain-text.
"""
import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDERING = REPO_ROOT / 'scripts' / 'deep_dive_rendering.py'

_OPP_ID_RE = re.compile(r'id="opp-(?!filter-)[a-z0-9-]+"')


def _results_section_calls():
    """{callee name: [lineno, ...]} for calls made in render_results_section."""
    tree = ast.parse(RENDERING.read_text())
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)
               and n.name == 'render_results_section'), None)
    assert fn is not None, 'render_results_section not found -- test is stale'
    calls = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.setdefault(node.func.id, []).append(node)
    return calls


def test_anchor_bullets_are_computed_after_the_threats_section():
    """The registry is claimed at COMPUTE time, so the threats section must
    run first for ``#opp-<slug>`` to land on a per-opponent row."""
    calls = _results_section_calls()
    anchor = calls.get('render_anchor_flip_bullets', [])
    threats = calls.get('render_opponent_threats_section', [])
    assert len(anchor) == 1, (
        f'expected exactly 1 render_anchor_flip_bullets call in '
        f'render_results_section, found {len(anchor)}')
    assert len(threats) == 1, (
        f'expected exactly 1 render_opponent_threats_section call in '
        f'render_results_section, found {len(threats)}')
    assert anchor[0].lineno > threats[0].lineno, (
        'render_anchor_flip_bullets is computed BEFORE '
        'render_opponent_threats_section, so the collapsed Anchor-Driven '
        'Matchup Flips list steals id="opp-<slug>" from the per-opponent '
        'rows and every #opp- deep link lands on a damage-tier bullet. '
        'Move the anchor_bullets computation back below the threats call.')


def test_anchor_bullets_remain_the_fallback_claimer():
    """Anti-vacuity for the ordering test above, and a guard on the other
    way to get this wrong: deleting the flag instead of reordering would
    drop every opponent anchor on a dive whose threats section renders
    nothing, silently degrading article opponent cells to plain text."""
    call = _results_section_calls()['render_anchor_flip_bullets'][0]
    flag = next((kw.value for kw in call.keywords
                 if kw.arg == 'emit_opponent_ids'), None)
    assert isinstance(flag, ast.Constant) and flag.value is True, (
        'render_anchor_flip_bullets must keep emit_opponent_ids=True: it is '
        'the fallback anchor claimer when render_opponent_threats_section '
        'returns nothing.')


def test_boundary_bullets_do_not_claim_opponent_anchors():
    """``render_matchup_boundary_bullets`` only renders nested inside tier
    cards now. Enabling its ids would make a tier card the landing spot."""
    tree = ast.parse(RENDERING.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'render_matchup_boundary_bullets'):
            for kw in node.keywords:
                assert kw.arg != 'emit_opponent_ids', (
                    f'render_matchup_boundary_bullets called with '
                    f'emit_opponent_ids at line {node.lineno}; it renders '
                    f'inside tier cards, so it would claim the anchors.')


@pytest.mark.render
def test_best_buddy_template_carries_its_own_opponent_anchors(small_dive_html):
    """The L51 <template> is swapped into the host on toggle, so it needs a
    full set of ``id="opp-"`` targets of its own or every #opp- link on the
    page dangles afterwards."""
    host_start = small_dive_html.find('id="dd-bb-prose-host"')
    tmpl_start = small_dive_html.find('id="dd-bb-prose-tmpl"')
    assert host_start != -1 and tmpl_start != -1, (
        'fixture rendered no best-buddy host/template pair -- this guard is '
        'vacuous without one (see SMALL_DIVE_ARGS).')
    assert host_start < tmpl_start
    host_ids = _OPP_ID_RE.findall(small_dive_html[host_start:tmpl_start])
    tmpl_ids = _OPP_ID_RE.findall(small_dive_html[tmpl_start:])
    assert host_ids, 'no opponent anchors in the live best-buddy prose host'
    assert len(tmpl_ids) == len(host_ids), (
        f'best-buddy template has {len(tmpl_ids)} opponent anchors vs '
        f'{len(host_ids)} in the host. The L51 render pass needs its own '
        f'rendering.reset_opp_anchor_registry() call.')


@pytest.mark.render
def test_opponent_anchors_land_inside_the_threats_section(small_dive_html):
    """End-to-end landing check on the live (L50) copy: when the threats
    section renders, it owns every opponent anchor."""
    host_start = small_dive_html.find('id="dd-bb-prose-host"')
    tmpl_start = small_dive_html.find('id="dd-bb-prose-tmpl"')
    live = small_dive_html[host_start:tmpl_start]
    threats_at = live.find('id="dd-opp-threats"')
    assert threats_at != -1, (
        'fixture rendered no opponent-threats section -- this guard is '
        'vacuous without one.')
    assert _OPP_ID_RE.search(live), 'no opponent anchors in the live prose'
    for m in _OPP_ID_RE.finditer(live):
        assert m.start() > threats_at, (
            f'{m.group(0)} is claimed before the opponent-threats section, '
            f'so the deep link lands outside the opponent matchup detail.')
