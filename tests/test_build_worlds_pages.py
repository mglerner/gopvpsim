"""build_worlds_pages: hub + cheat-sheet rendering contracts.

Synthetic planes/meta (portable; no dependency on the gitignored real
plane blobs). Pins the same contracts the site gates enforce: root pages
use same-directory links only (test_website_index_slugs precedent), no
em/en dashes in rendered text, the banned row renders, and refusal paths
refuse loudly.
"""
import json
import re
import shutil
import subprocess
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
    # Emphasis inversion (Michael 2026-08-18): the OLD scheme outlined
    # the IV-decided cells and left the settled ones bare. Now the
    # settled cells are dimmed and the IV-decided cells are bare, so
    # the old marker must be gone and the new one present.
    assert 'pair-amber' not in html_text
    assert 'pair-dim' in html_text
    # Layout: matrix before the meta table, provenance last.
    assert (html_text.index('<h2>Robustness matrix</h2>')
            < html_text.index('<table class="matrix">')
            < html_text.index('<figcaption class="matrix-cap">')
            < html_text.index('<h2>The meta ('))
    assert (html_text.index('<h2>The meta (')
            < html_text.index('<div class="prov">'))
    # Dimmed cells are clickable and carry the popover payload.
    assert 'class="ndbtn"' in html_text and 'id="ndpop"' in html_text
    assert 'data-sheet="worlds-' in html_text
    assert 'https://pvpoke.com/battle/1500/' in html_text
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


def test_hub_popover_deep_links_resolve_on_the_cheat_sheets(cells):
    """The hub's dimmed-cell popover deep-links into a cheat-sheet row;
    the row id must actually be stamped there. Pre-2026-08-18 there was
    no such id at all, so this fails without the anchor change."""
    hub = bwp.render_hub(META, cells, MANIFEST, slug_map={})
    refs = set(re.findall(r'data-sheet="([^"]+)"', hub))
    assert refs, 'no popover deep links emitted (fixture went trivial)'
    sheets = {bwp.sheet_filename(e['species_id']):
              bwp.render_cheat_sheet(e, META, cells, MANIFEST, slug_map={})
              for e in META['entries']}
    for ref in refs:
        fname, _, frag = ref.partition('#')
        assert fname in sheets, ref
        assert f'id="{frag}"' in sheets[fname], ref


def test_pvpoke_battle_url_shape_and_refusal():
    """GL 1500, bare species ids (PvPoke's own defaults apply), and NO
    link at all for an id PvPoke's battle rewrite cannot match."""
    assert (bwp.pvpoke_battle_url('lickilicky', 'quagsire_shadow')
            == 'https://pvpoke.com/battle/1500/lickilicky/quagsire_shadow/11/')
    assert bwp.pvpoke_battle_url('porygon2', 'quagsire') is None
    assert bwp.pvpoke_battle_url('quagsire', 'nidoran-female') is None


POPOVER_RUNNER = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

function El(cls, attrs) {
  return {
    cls: cls, attrs: attrs || {}, hidden: false, style: {}, offsetWidth: 300,
    textContent: '', href: undefined, focused: 0, handlers: {},
    getAttribute: function (k) { return k in this.attrs ? this.attrs[k] : null; },
    removeAttribute: function () { this.href = undefined; },
    getBoundingClientRect: function () { return {left: 100, bottom: 50, width: 20}; },
    focus: function () { this.focused++; },
    contains: function (x) { return x === this; },
    addEventListener: function (t, f) { this.handlers[t] = f; },
    closest: function (sel) { return sel === '.' + this.cls ? this : null; }
  };
}
var els = {};
['ndpop', 'ndpop-msg', 'ndpop-sheet', 'ndpop-pv', 'ndpop-x'].forEach(function (i) {
  els[i] = El('x');
});
els['ndpop'].hidden = true;
var docH = {};
global.document = {
  getElementById: function (i) { return els[i] || null; },
  addEventListener: function (t, f) { docH[t] = f; },
  documentElement: {clientWidth: 1200}
};
global.window = {pageXOffset: 0, pageYOffset: 10};
eval(src);

function btn(kind, pv) {
  var a = {'data-kind': kind, 'data-f': 'Alpha', 'data-o': 'Beta (Shadow)',
           'data-sheet': 'worlds-alpha.html#vs-beta_shadow'};
  if (pv) { a['data-pv'] = pv; }
  return El('ndbtn', a);
}
function click(t) { docH.click({target: t, preventDefault: function () {}}); }
var out = {};
var clean = btn('clean', 'https://pvpoke.com/battle/1500/alpha/beta_shadow/11/');
click(clean);
out.clean = {hidden: els['ndpop'].hidden, msg: els['ndpop-msg'].textContent,
             sheet: els['ndpop-sheet'].href, sheetText: els['ndpop-sheet'].textContent,
             pv: els['ndpop-pv'].href, pvHidden: els['ndpop-pv'].hidden,
             left: els['ndpop'].style.left, top: els['ndpop'].style.top};
click(clean);                       // second click on the same cell toggles off
out.toggled = els['ndpop'].hidden;
var deferred = btn('deferred', null);
click(deferred);
out.deferred = {msg: els['ndpop-msg'].textContent, pvHidden: els['ndpop-pv'].hidden};
click(El('other'));                 // click elsewhere dismisses
out.outsideDismissed = els['ndpop'].hidden;
click(clean);
docH.keydown({key: 'Escape'});
out.escDismissed = els['ndpop'].hidden;
out.refocused = clean.focused;
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_popover_script_behavior(tmp_path):
    """Exercise the hub popover script in node against a minimal DOM
    shim. Pre-2026-08-18 clicking a non-IV-decided matrix cell did
    nothing at all, so every assertion here is new behavior."""
    js = re.search(r'<script>(.*?)</script>', bwp.POPOVER_HTML, re.S).group(1)
    (tmp_path / 'pop.js').write_text(js)
    (tmp_path / 'run.js').write_text(POPOVER_RUNNER)
    proc = subprocess.run(['node', str(tmp_path / 'run.js'),
                           str(tmp_path / 'pop.js')],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out['clean']['hidden'] is False
    assert 'not IV-decided in any tested slice' in out['clean']['msg']
    assert out['clean']['sheet'] == 'worlds-alpha.html#vs-beta_shadow'
    assert 'Alpha vs Beta (Shadow)' in out['clean']['sheetText']
    assert out['clean']['pv'] == \
        'https://pvpoke.com/battle/1500/alpha/beta_shadow/11/'
    assert out['clean']['pvHidden'] is False
    assert out['clean']['left'] and out['clean']['top']
    assert out['toggled'] is True
    # A pair with no detail page is NOT always a settled pair; the
    # deferred case must not be told it is settled.
    assert 'deferred by the Tier-2 bake budget' in out['deferred']['msg']
    assert 'not IV-decided' not in out['deferred']['msg']
    # No pvpoke id we can link -> the link is hidden, never left stale.
    assert out['deferred']['pvHidden'] is True
    assert out['outsideDismissed'] is True
    assert out['escDismissed'] is True
    assert out['refocused'] >= 1          # Escape returns focus to the cell


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


def test_cheat_sheet_grid_links_to_pair_page(cells):
    """The 3x3 grid block itself links to the pair page when one exists
    (Michael 2026-08-14 -- pre-fix only the dig-in paragraph linked).
    The no-links case is pinned above ('worlds-pair-' absent)."""
    links = {frozenset(('alpha', 'beta_shadow')):
             'worlds-pair-alpha--beta_shadow.html'}
    html_text = bwp.render_cheat_sheet(META['entries'][0], META, cells,
                                       MANIFEST, slug_map={}, links=links)
    anchor = ('<a class="gridlink" '
              'href="worlds-pair-alpha--beta_shadow.html">')
    assert anchor in html_text
    i = html_text.find(anchor)
    seg = html_text[i:html_text.find('</a>', i)]
    assert 'class="g9"' in seg                       # grid inside anchor


# ---------------------------------------------------------------------------
# CD move-injection disclosure (2026-08-18, Thievul / Icy Wind)
# ---------------------------------------------------------------------------

def _meta_with_injection():
    """META with an injection declared on the SECOND entry only, so the
    per-entry / site-wide split can be told apart."""
    import copy
    m = copy.deepcopy(META)
    m['entries'][1].update({
        'injected_move_ids': ['CM_THREE'],
        'injected_moves': ['CM Three'],
        'injection_note': 'Pinned gamemaster predates the CD; upstream lists '
                          'it. Synthetic note for the test.',
    })
    return m


def test_injection_disclosure_is_absent_without_a_declaration(cells):
    """Positive control for the pins below: with no injected_move_ids
    anywhere, none of the three disclosure surfaces say anything. (A
    scan that can't tell present from absent is a dead scan.)"""
    sheet = bwp.render_cheat_sheet(META['entries'][1], META, cells,
                                   MANIFEST, slug_map={})
    hub = bwp.render_hub(META, cells, MANIFEST, slug_map={})
    for text in (sheet, hub):
        assert 'Move injection' not in text
        assert 'injected' not in text
    assert bwp.injected_entries(META) == []


def test_injection_disclosed_on_its_own_sheet_hub_and_provenance(cells):
    m = _meta_with_injection()
    injected, other = m['entries'][1], m['entries'][0]
    assert [e['species_id'] for e in bwp.injected_entries(m)] == ['beta_shadow']

    # 1. the affected entry's own cheat sheet carries the FULL note
    sheet = bwp.render_cheat_sheet(injected, m, cells, MANIFEST, slug_map={})
    assert '<strong>Move injection: CM Three.</strong>' in sheet
    assert 'Synthetic note for the test.' in sheet
    assert 'CM Three injected: the pinned sim gamemaster predates the CD' \
        in sheet

    # 2. an UNAFFECTED entry's sheet does not claim its own injection,
    #    but still carries the site-wide provenance sentence (the
    #    injected mon is its opponent in half these numbers).
    other_sheet = bwp.render_cheat_sheet(other, m, cells, MANIFEST,
                                         slug_map={})
    assert 'Move injection: ' not in other_sheet
    assert 'Community Day move injected for Beta (Shadow) (CM Three)' \
        in other_sheet

    # 3. the hub meta table marks the moveset cell, and its provenance
    #    line carries the same sentence.
    hub = bwp.render_hub(m, cells, MANIFEST, slug_map={})
    assert 'CM Three injected: the pinned sim gamemaster predates the CD' \
        in hub
    assert 'Community Day move injected for Beta (Shadow) (CM Three)' in hub


def test_injection_disclosure_survives_on_the_real_meta():
    """Boundary pin against the SHIPPED meta, not the synthetic one: any
    entry meta.toml declares must be disclosed by name on its sheet."""
    import tomllib
    meta = tomllib.load(open(wp.META_TOML, 'rb'))
    inj = bwp.injected_entries(meta)
    assert inj, 'no injections declared -- retire this test with the table'
    for e in inj:
        block = bwp.injection_html(e)
        assert '<strong>Move injection:' in block
        assert e['injection_note'] in block
        for name in e['injected_moves']:
            assert name in block
        assert bwp.injection_chip(e).count(name) == 1
