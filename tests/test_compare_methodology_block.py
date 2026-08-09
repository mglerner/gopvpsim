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


def _fragment():
    scenarios = ['0-0', '1-1', '2-2']
    loadouts = [
        _loadout('Blade', 'Aegislash (Blade)', 'PSYCHO_CUT',
                 ('AERIAL_ACE', 'SHADOW_BALL'), 0.611, 1234, scenarios,
                 ['Azumarill', 'Mimikyu', 'Registeel']),
        _loadout('Shield', 'Aegislash (Shield)', 'PSYCHO_CUT',
                 ('AERIAL_ACE', 'SHADOW_BALL'), 0.484, 1234, scenarios,
                 ['Azumarill', 'Mimikyu']),
    ]
    return cl.build_comparison_fragment(
        loadouts_data=loadouts, league='great', gm=cl.load_gamemaster(),
        title='t', include_matchup_delta=False)


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
