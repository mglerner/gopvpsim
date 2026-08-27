"""The comparison "About these numbers" block must stay true to the data.

That block is the only ``methodology-details`` paragraph currently rendered
on the live site (the four ``comparisons/*/index.html`` pages), and it used
to hand-type both the sweep dimensions ("4096 focal IVs x 9 shield
scenarios") and the win boundary ("scores at least 500"). The boundary was
simply wrong -- ``load_loadout_data`` counts a win as ``score > 500``, and
``gopvpsim.battle.WIN_RATING`` calls an exact 500 a tie -- and the
dimensions would silently rot the day a dive sweeps a different IV set.

These tests pin the seam: the counts come from the parsed dive, the
boundary sentence agrees with ``WIN_RATING``, and the guide anchor the
paragraph links to really exists in the guide body (``verify_article_links
--ship`` catches a typo too, but only after a full rebuild).
"""
import importlib.util
import re
import sys
from pathlib import Path

import markdown

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDE_BODY = REPO_ROOT / 'guides' / 'how-this-works' / 'body.md'


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    # Register before exec: the module defines a frozen dataclass, and
    # dataclasses resolves annotations through sys.modules[__module__].
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cl = _load('compare_loadouts_under_test', 'scripts/compare_loadouts.py')

import gopvpsim.battle as battle  # noqa: E402  (cl puts src/ on sys.path)


def _loadout(label, species, fast, charged, win_rate, n_ivs, scenarios,
             opponents):
    """A minimal ``load_loadout_data``-shaped dict for the fragment renderer."""
    return {
        'spec': cl.LoadoutSpec(
            label=label, species=species, dive_slug='fake-slug',
            fast_move=fast, charged_moves=charged),
        'path': Path('fake.html'),
        'opp_anchor_ids': set(),
        'win_rate': win_rate,
        'per_scenario_win_rate': [win_rate] * len(scenarios),
        'per_opponent_win_rate': [win_rate] * len(opponents),
        'scenarios': list(scenarios),
        'opponents': list(opponents),
        'opponent_label': 'Great League top cut',
        'pretty_label': f'{fast} / {", ".join(charged)}',
        'n_ivs': n_ivs,
    }


SCENARIOS = ['0-0', '1-1', '2-2']


def _fragment(loadouts=None, include_matchup_delta=False):
    if loadouts is None:
        loadouts = [
            _loadout('Blade', 'Aegislash (Blade)', 'PSYCHO_CUT',
                     ('AERIAL_ACE', 'SHADOW_BALL'), 0.611, 1234, SCENARIOS,
                     ['Azumarill', 'Mimikyu', 'Registeel']),
            _loadout('Shield', 'Aegislash (Shield)', 'PSYCHO_CUT',
                     ('AERIAL_ACE', 'SHADOW_BALL'), 0.484, 1234, SCENARIOS,
                     ['Azumarill', 'Mimikyu']),
        ]
    return cl.build_comparison_fragment(
        loadouts_data=loadouts, league='great', gm=cl.load_gamemaster(),
        title='t', include_matchup_delta=include_matchup_delta)


def test_methodology_counts_come_from_the_parsed_dive():
    frag = _fragment()
    block = re.search(
        r'<details class="methodology-details compare-lead-details">.*?'
        r'</details>', frag, re.S)
    assert block, 'the About-these-numbers block should still render'
    text = block.group(0)
    # Fixture sweeps 1234 IVs x 3 scenarios, and only 2 of the 3 opponents
    # are shared -- none of which is the old hardcoded 4096 x 9.
    assert '1,234 focal IVs x 3 shield scenarios' in text
    assert '2 opponents are common to all loadouts' in text
    assert '4096' not in text and '4,096' not in text


def test_methodology_win_boundary_matches_win_rating():
    text = _fragment()
    assert f'above {battle.WIN_RATING} ({battle.WIN_RATING} is a tie)' in text
    # The old, wrong phrasing counted an exact-500 tie as a win.
    assert 'at least 500' not in text


def test_methodology_guide_anchor_exists_in_the_guide_body():
    frag = _fragment()
    m = re.search(r'href="\.\./\.\./guides/([a-z0-9-]+)/#([a-z0-9-]+)"', frag)
    assert m, 'the block should link out to a guide anchor'
    guide, anchor = m.group(1), m.group(2)
    assert guide == 'how-this-works', guide
    # Same extension set build_guides.py renders guide bodies with, so the
    # generated heading ids match the shipped page.
    rendered = markdown.markdown(
        GUIDE_BODY.read_text(),
        extensions=['extra', 'sane_lists', 'smarty', 'toc'])
    assert f'id="{anchor}"' in rendered, anchor


# --- the OTHER three places the page names the sweep dimensions ----------
# 95fcf74 taught the methodology block to derive them but left the pairwise
# table's two column tooltips and the 3+-loadout abbreviation note spelling
# "4096 focal IVs x 9 shield scenarios" by hand -- so a non-4096 dive would
# have rendered two contradictory counts on one page.


def test_pairwise_column_tooltips_derive_their_own_loadouts_dims():
    """Each column's tooltip describes ITS OWN loadout's sweep.

    The two loadouts here sweep different IV counts (1234 vs 999), which no
    real dive does -- that is the point: it fails both if the counts go back
    to a constant and if one column borrows the other's dims.
    """
    loadouts = [
        _loadout('Blade', 'Aegislash (Blade)', 'PSYCHO_CUT',
                 ('AERIAL_ACE', 'SHADOW_BALL'), 0.611, 1234, SCENARIOS,
                 ['Azumarill', 'Mimikyu']),
        _loadout('Shield', 'Aegislash (Shield)', 'PSYCHO_CUT',
                 ('AERIAL_ACE', 'SHADOW_BALL'), 0.484, 999, SCENARIOS,
                 ['Azumarill', 'Mimikyu']),
    ]
    frag = _fragment(loadouts, include_matchup_delta=True)
    titles = re.findall(r'title="Win rate with ([^"]*)"', frag)
    assert len(titles) == 2, titles
    assert 'Varies all 1,234 focal IVs x 3 shield scenarios;' in titles[0]
    assert 'Varies all 999 focal IVs x 3 shield scenarios;' in titles[1]


def test_abbreviation_note_derives_the_sweep_dims():
    """The 3+-loadout WR legend, the third hand-typed site."""
    loadouts = [
        _loadout(lbl, 'Aegislash (Blade)', 'PSYCHO_CUT',
                 ('AERIAL_ACE', 'SHADOW_BALL'), wr, 1234, SCENARIOS,
                 ['Azumarill', 'Mimikyu'])
        for lbl, wr in (('Blade', 0.61), ('Shield', 0.48), ('Shadow', 0.55))
    ]
    frag = _fragment(loadouts, include_matchup_delta=True)
    note = re.search(r'<details class="abbrev-note">.*?</details>', frag, re.S)
    assert note, 'the 3+-loadout comparison should still render the note'
    assert ('fraction of 1,234 focal IVs x 3 shield scenarios where'
            in note.group(0))


def test_no_rendered_surface_still_hardcodes_4096_x_9():
    """Whole-page pin: the number the fixture never sweeps must not appear.

    Covers both branches (N=2 pairwise and N>=3 all-in-row) so a fourth
    hand-typed site added later trips here rather than shipping.
    """
    three = [
        _loadout(lbl, 'Aegislash (Blade)', 'PSYCHO_CUT',
                 ('AERIAL_ACE', 'SHADOW_BALL'), wr, 1234, SCENARIOS,
                 ['Azumarill', 'Mimikyu'])
        for lbl, wr in (('Blade', 0.61), ('Shield', 0.48), ('Shadow', 0.55))
    ]
    for frag in (_fragment(include_matchup_delta=True),
                 _fragment(three, include_matchup_delta=True)):
        assert '4096' not in frag and '4,096' not in frag
        # ...and the scenario count too: the fixture sweeps 3, not 9.
        assert 'x 9 shield scenarios' not in frag
