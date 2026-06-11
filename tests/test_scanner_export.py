"""Notable-IVs scanner export (2026-06-11).

Each Notable-IVs card carries a ``data-scanner-json`` attribute holding a
paste-ready gobattlekit user-thresholds fragment in the shared
``check_thresholds`` schema: ``{species: {League: {name: spec}}}`` where
spec is either stat floors (composite cards) or an explicit ``ivs`` list
(matchup cards). Format confirmed from gobattlekit's
``load_user_thresholds`` (JSON file, same schema as DEFAULT_THRESHOLDS).
"""
from __future__ import annotations

import html
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# deep_dive_rendering imports sibling scripts/ modules at import time.
sys.path.insert(0, os.path.join(str(REPO_ROOT), 'scripts'))
_spec = importlib.util.spec_from_file_location(
    "deep_dive_rendering", REPO_ROOT / "scripts" / "deep_dive_rendering.py")
rendering = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(rendering)


def _data_obj():
    return {
        'species': "Farfetch'd (Galarian)",   # apostrophe: escaping stress
        'league': 'great',
        'nIvs': 4,
        'ivA': [0, 1, 2, 3], 'ivD': [15, 14, 13, 12], 'ivS': [15, 14, 13, 12],
        'ivAtk': [100.0, 101.0, 102.0, 103.0],
        'ivDef': [120.0, 119.0, 118.0, 117.0],
        'ivHp': [140, 139, 138, 137],
        'spRanks': [1, 2, 3, 4],
    }


def _extract_payloads(html_text):
    out = []
    for m in re.finditer(r'data-scanner-json="([^"]*)"', html_text):
        out.append(json.loads(html.unescape(m.group(1))))
    return out


def test_composite_card_exports_stat_floors():
    cat = rendering.IVCategory(
        name='Quag Slayer ∩ Top 5%', kind='composite', members=[0, 1],
        source_categories=['Quag Slayer', 'Top 5%'],
        stat_cutoffs={'atk': 101.234, 'def': 0, 'hp': 139},
    )
    out = rendering.render_notable_ivs_section([cat], _data_obj(), 'pvpoke')
    payloads = _extract_payloads(out)
    assert len(payloads) == 1
    spec = payloads[0]["Farfetch'd (Galarian)"]['Great']['Quag Slayer ∩ Top 5%']
    assert spec == {'attack': 101.23, 'defense': 0.0, 'stamina': 139}


def test_matchup_card_exports_explicit_ivs():
    cat = rendering.IVCategory(
        name='Beats Azumarill 1v1', kind='matchup', members=[1, 3],
        matchup_conditions=[{'opponent': 'Azumarill', 'scenario': (1, 1)}],
    )
    out = rendering.render_notable_ivs_section([cat], _data_obj(), 'pvpoke')
    payloads = _extract_payloads(out)
    assert len(payloads) == 1
    spec = payloads[0]["Farfetch'd (Galarian)"]['Great']['Beats Azumarill 1v1']
    assert spec['attack'] == 0 and spec['defense'] == 0 and spec['stamina'] == 0
    assert sorted(spec['ivs']) == [[1, 14, 14], [3, 12, 12]]


def test_oversized_matchup_card_gets_no_button():
    # A truncated scanner list would silently miss owned mons — beyond
    # 300 members the button is omitted rather than wrong.
    big = rendering.IVCategory(
        name='Beats Everyone', kind='matchup', members=list(range(4)) * 100,
        matchup_conditions=[{'opponent': 'X', 'scenario': (1, 1)}],
    )
    out = rendering.render_notable_ivs_section([big], _data_obj(), 'pvpoke')
    assert 'data-scanner-json' not in out
