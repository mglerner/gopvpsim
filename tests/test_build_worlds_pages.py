"""build_worlds_pages: hub + cheat-sheet rendering contracts.

Synthetic planes/meta (portable; no dependency on the gitignored real
plane blobs). Pins the same contracts the site gates enforce: root pages
use same-directory links only (test_website_index_slugs precedent), no
em/en dashes in rendered text, the banned row renders, and refusal paths
refuse loudly.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

import worlds_planes as wp  # noqa: E402
import worlds_render_data as wrd  # noqa: E402
import build_worlds_pages as bwp  # noqa: E402

SCEN = [(a, b) for a in range(3) for b in range(3)]

META = {
    'format': 'open GL 1500 + Play! banned list',
    'mechanics': 'legacy (old system; Worlds-confirmed)',
    'usage_recent_cutoff': '2026-03',
    'usage_events_recent': 16,
    'usage_teams_recent': 1801,
    'badge_usage_top': 25,
    'badge_rank_top': 30,
    'moveset_modal_min_pct': 60.0,
    'reject_top_n': 55,
    'entries': [
        {'name': 'Alpha', 'species': 'Alpha', 'species_id': 'alpha',
         'shadow': False, 'badge': 'PLAYED', 'badge_rule': 'MODEL',
         'current_rank': 2,
         'usage_recent_pct': 30.0, 'fast_move': 'Fast A',
         'charged_moves': ['CM One', 'CM Two'], 'fast_move_id': 'FAST_A',
         'charged_move_ids': ['CM_ONE', 'CM_TWO'],
         'moveset_source': 'modal', 'moveset_modal_pct': 90.0,
         'moveset_n': 100, 'default_disagrees': False},
        {'name': 'Beta (Shadow)', 'species': 'Beta', 'species_id':
         'beta_shadow', 'shadow': True, 'badge': 'FORCED',
         'forced_reason': 'Editorial include for testing.',
         'current_rank': 53, 'usage_recent_pct': 0.6,
         'fast_move': 'Fast B', 'charged_moves': ['CM Three'],
         'fast_move_id': 'FAST_B', 'charged_move_ids': ['CM_THREE'],
         'moveset_source': 'default', 'moveset_modal_pct': 50.0,
         'moveset_n': 5, 'default_disagrees': True},
    ],
    'rejects': [
        {'name': 'Gamma', 'species_id': 'gamma', 'banned': False,
         'usage_rank': 21, 'current_rank': 44, 'usage_recent_pct': 9.0,
         'reason': 'below cut'},
        {'name': 'Mimikyu', 'species_id': 'mimikyu', 'banned': True,
         'usage_rank': None, 'current_rank': 1, 'usage_recent_pct': 0.0,
         'reason': 'Banned at Worlds.'},
    ],
}

MANIFEST = {'engine': 'eng123', 'gamemaster': 'gm456',
            'worlds_code': 'wc789',
            'entries': {'k': {'baked': '2026-08-10'}}}


@pytest.fixture
def cells(tmp_path):
    planes = tmp_path / 'planes'
    won = np.zeros((2, 4, 9), dtype=bool)
    won[:, :, 0] = True            # 0-0 green
    won[:, (0, 1), 2] = True       # 0-2 amber
    # alpha->beta differs by bait mode (scenario 1-2 flips no-bait);
    # beta->alpha is bait-independent -- so one sheet shows two grids
    # and the other shows the collapsed single grid.
    won_nb = won.copy()
    won_nb[:, :, 5] = True
    for f, o in (('alpha', 'beta_shadow'), ('beta_shadow', 'alpha')):
        for bait in (True, False):
            w = won_nb if (f == 'alpha' and not bait) else won
            score = np.where(w, 700, 300).astype(np.uint16)
            arrs = wp.plane_arrays(
                w, score, focal_ivs=[(0, 15, 15), (12, 1, 15)],
                focal_levels=[24.0, 25.5],
                opp_ivs=[(0, 15, 14), (1, 15, 11), (4, 1, 12),
                         (15, 15, 15)],
                opp_levels=[24.0, 24.0, 25.0, 22.5], scenarios=SCEN,
                top512_mask=[True, True, True, False],
                atkband_mask=[True, False, True, True])
            wp.write_plane(wp.plane_filename(f, o, bait), arrs, planes)
    return wrd.build_all_cells(META['entries'], planes)


def _no_dashes(html_text):
    assert '—' not in html_text and '–' not in html_text


def test_hub_contracts(cells):
    html_text = bwp.render_hub(META, cells, MANIFEST, slug_map={})
    assert '../' not in html_text                     # same-directory links
    assert 'worlds-alpha.html' in html_text
    assert 'worlds-beta_shadow.html' in html_text
    assert 'badge-banned">BANNED' in html_text        # Mimikyu row
    assert 'Mimikyu' in html_text
    assert 'badge-played">PLAYED' in html_text
    assert 'badge-forced">FORCED' in html_text
    assert 'pair-amber' in html_text                  # IV-decided outline
    assert 'went live in-game 2026-06-02' in html_text  # resolved date
    assert 'Turin' in html_text                         # post-rebalance split
    assert 'Internationals are excluded' in html_text
    assert 'human decision' in html_text              # editorial membership
    assert '(rule: MODEL)' in html_text               # badge_rule divergence
    assert 'Deliberately not built' in html_text
    assert 'eng123' in html_text and 'gm456' in html_text
    _no_dashes(html_text)


def test_cheat_sheet_contracts(cells):
    html_text = bwp.render_cheat_sheet(META['entries'][0], META, cells,
                                       MANIFEST, slug_map={})
    assert '../' not in html_text
    assert 'worlds-beta_shadow.html' in html_text     # opponent cross-link
    assert 'sc-green' in html_text and 'sc-amber' in html_text \
        and 'sc-red' in html_text                     # non-trivial strips
    assert 'IVs decide: 0-2' in html_text
    # Amber tooltips print exact counts, never a rounded 0%/100%
    # (adversarial-verify finding): 0-2 beats rows 0,1 of the 3-row
    # top512 cohort.
    assert 'beats 2 of 3 spreads' in html_text
    # W/L/? letters make the outcome color-independent.
    assert '>W</span>' in html_text and '>L</span>' in html_text \
        and '>?</span>' in html_text
    # PvPoke-style 3x3 grids (Michael 2026-08-10): 4-column grid with
    # 0/1/2 axis labels. alpha->beta DIFFERS by bait mode, so this
    # sheet shows both grids, never the collapsed form.
    assert 'class="g9"' in html_text
    assert html_text.count('class="gcap"') == 2       # bait + no-bait caps
    assert '>bait</span>' in html_text and '>no-bait</span>' in html_text
    assert 'bait-independent' not in html_text
    assert '<span class="glab">0</span>' in html_text
    # Badges moved off the rows/heading into the provenance tail
    # (Michael 2026-08-11). Pin the MARKUP absence (the shared CSS
    # still defines .badge-* rules for the hub).
    assert 'class="badge ' not in html_text
    assert 'Selection provenance' in html_text
    assert 'badged <strong>PLAYED</strong>' in html_text
    assert '(the mechanical rule says MODEL' in html_text
    # Per-row dig-in expansion: full Tier-1 slice counts as text.
    assert '<details class="digin">' in html_text
    assert '2/3' in html_text                         # exact count cell
    # No pair page exists in the fixture -> the dig-in says deferred,
    # never a dead link.
    assert 'deferred by the Tier-2 bake budget' in html_text
    assert 'worlds-pair-' not in html_text
    # Closest-scenario readout: fixture's mixed scenario 0-2 has band
    # -200..+200 (contains zero -> maximally close), beating the
    # all-win +200..+200 scenarios in both modes.
    assert 'closest scenario (score margin)' in html_text
    assert 'closest: 0-2 (bait) -200..+200' in html_text
    assert 'FOCAL side only' in html_text             # no-bait disclosure
    assert 'worlds.html' in html_text                 # back link
    _no_dashes(html_text)
    # FORCED provenance renders on the forced entry's own sheet, and
    # beta->alpha is bait-independent -> ONE collapsed grid per row
    # with the unioned-margin tooltip.
    forced = bwp.render_cheat_sheet(META['entries'][1], META, cells,
                                    MANIFEST, slug_map={})
    assert 'Editorial include for testing.' in forced
    assert forced.count('class="gcap"') == 1
    assert '>bait-independent</span>' in forced
    assert 'across both modes' in forced
    assert 'badged <strong>FORCED</strong>' in forced


def test_dive_slug_map_links_only_existing_dirs(tmp_path):
    (tmp_path / 'alpha-great-league').mkdir()
    (tmp_path / 'alpha-great-league' / 'index.html').write_text('x')
    m = bwp.dive_slug_map(META['entries'], tmp_path)
    assert m == {'alpha': 'alpha-great-league/index.html'}


def test_build_refuses_on_missing_cells(tmp_path, monkeypatch):
    """Partial planes must refuse, not render a silently partial page."""
    planes = tmp_path / 'planes'
    planes.mkdir(parents=True)
    manifest = {**MANIFEST}
    wp.save_manifest(manifest, planes)
    monkeypatch.setattr(wp, 'stamp_mismatches', lambda m: [])
    monkeypatch.setattr(wrd, 'load_meta', lambda p: META)
    with pytest.raises(SystemExit) as e:
        bwp.build(website_dir=tmp_path / 'site', planes_dir=planes,
                  meta_path='unused')
    assert 'missing' in str(e.value)


def test_build_refuses_on_stamp_mismatch(tmp_path, monkeypatch):
    planes = tmp_path / 'planes'
    planes.mkdir(parents=True)
    wp.save_manifest({**MANIFEST}, planes)
    monkeypatch.setattr(wp, 'stamp_mismatches',
                        lambda m: [('engine', 'old', 'new')])
    monkeypatch.setattr(wrd, 'load_meta', lambda p: META)
    with pytest.raises(SystemExit) as e:
        bwp.build(website_dir=tmp_path / 'site', planes_dir=planes,
                  meta_path='unused')
    assert 'vintage' in str(e.value) or 'stamp' in str(e.value)
