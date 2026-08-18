#!/usr/bin/env python
"""Build the standalone Thievul-vs-Lickitung IV-robustness page (LOCAL ONLY).

One-off analysis page for the 2026-08-16 Thievul CD "IV tech" question
(HSH discord: is 6/15/5 the best spread for the Sucker Punch breakpoint
on Lickitung, or do you want 15 HP?). Spec + DATA contract:
``userdata/thievul_licki/DESIGN.md``.

Output: ``userdata/dives/thievul_vs_lickitung_iv_robustness.html`` -- a
fully self-contained offline page (Plotly and POGOCollection inlined, no
network references). It is deliberately NOT under ``userdata/website/``:
that tree is rsynced to pogodives.com with no allowlist.

The builder is INPUT-TOLERANT by design: with ``--allow-missing`` it runs
against whatever exists right now (the 4096x4096 grids take hours to
bake), and every panel whose input is absent renders a VISIBLE "data not
baked yet" placeholder. No placeholder is silent. The final assembly run
re-invokes the same command once all inputs exist.

Inputs (all optional under --allow-missing), from ``--data-dir``:
  manifest.json                          grid provenance
  thievul_<label>__vs__lickitung.npz     packed win grids (x3)
  meta_wins.npz                          per-IV meta wins (A1)
  breakpoints.json                       closed-form damage layer (A2)
  reco.json                              recommendation blob (assembly)

ALL analysis numbers live in the injected ``TL_DATA`` blob; the page JS
(``scripts/thievul_licki_page.js``) only renders them.
"""
import argparse
import base64
import datetime as _dt
import gzip
import hashlib
import json
import os
import pathlib
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'src'))

import worlds_planes as wp  # noqa: E402

from gopvpsim.attribution import PVPOKE_ATTRIBUTION_HTML  # noqa: E402
from gopvpsim.evolution_lines import _load_pre_to_finals  # noqa: E402
from gopvpsim.pokemon import (  # noqa: E402
    CPM, LEAGUE_CAPS, SHADOW_ATK_BONUS, SHADOW_DEF_MULT, get_pokemon_index,
    iv_rank,
)
from gopvpsim.theme import (  # noqa: E402
    data_theme_attr, theme_css, theme_head_script, theme_picker_html,
)
from gopvpsim.user_collection import compute_rank_lookup  # noqa: E402

DATA_DIR = REPO / 'userdata' / 'thievul_licki'
# meta_wins is Thievul vs the DIVE POOL -- it does not depend on which
# Licki we are studying, so a dataset that lacks its own copy falls back
# to the one baked for the Lickitung run.
METAWINS_FALLBACK_DIR = REPO / 'userdata' / 'thievul_licki'
DIVES_DIR = REPO / 'userdata' / 'dives'

FOCAL = 'Thievul'
DEFAULT_OPPONENT = 'Lickitung'
LEAGUE = 'great'
LEAGUE_LABEL = 'Great'
MAX_LEVEL = 50.0
N_IV = 4096
N_SCEN = 9
DEFAULT_GRID_LABELS = ['iwpr_bait', 'iwpr_nobait', 'nsiw_bait']
# Preferred display order; any label the manifest declares but this list
# does not know about is appended (never dropped).
LABEL_ORDER = ['iwpr_bait', 'iwpr_nobait', 'nsiw_bait', 'nsiw_nobait']

# The spread under test, straight from the discord claim (TrainerThomasElg
# / doone, 2026-08-14). This is an INPUT to the analysis (the claim), not a
# result of it -- the page labels it as a claim and reads its coverage from
# the baked grids like any other spread.
CLAIM_IVS = (6, 15, 5)

def grid_to_metawins(label):
    """Grid label -> (A1 moveset key, A1 focal-bait key) in meta_wins.npz.

    The label IS the pair ('nsiw_nobait' -> 'nsiw' + 'nobait'), so a new
    moveset/bait combination needs no table entry here.
    """
    ms, _, bait = label.rpartition('_')
    return (ms, bait) if ms else (label, 'bait')

# Used ONLY when the manifest is absent; otherwise every label's pretty
# name is derived from the manifest's own move lists.
PRETTY_FALLBACK = {
    'iwpr_bait': 'Sucker Punch / Icy Wind + Play Rough, baiting',
    'iwpr_nobait': 'Sucker Punch / Icy Wind + Play Rough, no bait',
    'nsiw_bait': 'Sucker Punch / Night Slash + Icy Wind, baiting',
    'nsiw_nobait': 'Sucker Punch / Night Slash + Icy Wind, no bait',
}

# Root-level website pages link same-directory (the worlds-*.html
# convention), so the link checker can resolve them on disk.
# Frozen artifacts get a standing archive banner, keyed by opponent so a
# rebuild reproduces it byte-for-byte without remembering a CLI flag.
ARCHIVE_NOTE = {
    'lickitung': (
        'Archived 2026-08-17: Lickitung is out of the current Great League '
        'meta; this analysis is kept for reference and will not be '
        'updated.'),
}

# The Community Day move note is STATIC and date-anchored on purpose.
# It used to be derived from whatever gamemaster the build happened to
# load, which made the sentence flip between "not in the move pool at all
# (a projection)" and "elite move" depending on the local cache vintage --
# and after the CD itself (2026-08-16) the projection wording is simply
# false: people have these Thievuls. Nothing here reads the live
# gamemaster; the only gate is whether the BAKE MANIFEST says a grid used
# the move.
CD_MOVE = 'ICY_WIND'
CD_MOVE_NOTE = (
    'MOVE LEGALITY: Icy Wind is the 2026-08-16 Community Day exclusive '
    '(elite move; not obtainable by regular TM). The pinned bake '
    'gamemaster predates the CD, so the move was injected for simulation; '
    'PvPoke upstream added it as an elite move on 2026-08-14.')

MAIN_DIVE_URL = 'thievul-great-league/index.html'
# The two published readings of the community shorthand "Licki". Each page
# links the other with a one-line statement of which species it analyzes.
PUBLISH_SLUG = {
    'lickitung': 'thievul-lickitung-robustness.html',
    'lickilicky': 'thievul-lickilicky-robustness.html',
}
CROSSLINK = {
    'lickilicky': (
        ' "Licki" in the Great League meta means <strong>Lickilicky</strong>'
        ' (Rollout / Body Slam + Shadow Ball), analyzed here; the '
        '<a href="' + PUBLISH_SLUG['lickitung'] + '">Lickitung version</a> '
        'is archived.'),
    'lickitung': (
        ' This analyzes <strong>Lickitung</strong> (Lick / Body Slam + '
        'Power Whip); "Licki" in the Great League meta usually means '
        '<a href="' + PUBLISH_SLUG['lickilicky'] + '">Lickilicky</a>.'),
}

PLOTLY_FILENAME = 'plotly-2.35.2.min.js'
PLOTLY_CACHE_DIR = pathlib.Path.home() / '.cache' / 'gopvpsim'


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f'not JSON serializable: {type(o)}')


def load_manifest(data_dir):
    p = data_dir / 'manifest.json'
    if not p.exists():
        return None
    return json.loads(p.read_text())


def _pretty_move(name):
    return ' '.join(w.capitalize() for w in str(name).split('_'))


def _grid_pretty(g):
    fast = _pretty_move(g.get('focal_fast') or '?')
    charged = ' + '.join(_pretty_move(c) for c in (g.get('focal_charged') or []))
    return f"{fast} / {charged}, {'baiting' if g.get('bait') else 'no bait'}"


def dataset_spec(manifest, data_dir=None):
    """Everything opponent-specific, DERIVED from manifest.json.

    The page was originally hardcoded to Lickitung; it is now driven by
    the manifest's ``opponent`` so the same builder renders the Lickilicky
    dataset (the community's "Licki") without a second copy of the code.
    Evolution-line membership comes from the gamemaster-backed
    pre-to-finals map, not from a hand-written species list.
    """
    man = manifest or {}
    opponent = man.get('opponent') or DEFAULT_OPPONENT
    focal = man.get('focal') or FOCAL
    grids = man.get('grids') or {}
    # The bake writes grids INCREMENTALLY and rewrites the manifest as each
    # finishes, so mid-bake the manifest lists only what is done. Union it
    # with any declared plan and with the npz files actually on disk, so a
    # grid can never be silently absent from the page's own label list.
    known = set(grids) | set(man.get('planned_grids') or [])
    if data_dir is not None:
        prefix, suffix = f'{focal.lower()}_', f'__vs__{opponent.lower()}.npz'
        for f in pathlib.Path(data_dir).glob(f'{prefix}*{suffix}'):
            known.add(f.name[len(prefix):-len(suffix)])
    if not known:
        known = set(DEFAULT_GRID_LABELS)
    labels = sorted(known, key=lambda lb: (
        LABEL_ORDER.index(lb) if lb in LABEL_ORDER else len(LABEL_ORDER),
        lb))
    files, pretty = {}, {}
    for label in labels:
        g = grids.get(label) or {}
        files[label] = g.get('file') or (
            f'{focal.lower()}_{label}__vs__{opponent.lower()}.npz')
        pretty[label] = (_grid_pretty(g) if g.get('focal_fast')
                         else PRETTY_FALLBACK.get(label, label))

    pre_to_finals = _load_pre_to_finals()

    def line_of(species):
        """The species plus its pre-evolutions and its evolutions."""
        members = {species}
        members.update(pre_to_finals.get(species, []))
        for pre, finals in pre_to_finals.items():
            if species in finals:
                members.add(pre)
        return members

    focal_line, opp_line = line_of(focal), line_of(opponent)
    collection_species = sorted(focal_line | opp_line)
    # Threshold keys are the MATCH TARGETS. A pre-evolution of the analyzed
    # species must NOT be a key: matchMons only walks a CSV row up its
    # evolution line when the scanned species is not itself a key. So a
    # scanned Nickit is evaluated as the Thievul it becomes, and -- on the
    # Lickilicky dataset -- a scanned Lickitung is evaluated as the
    # Lickilicky it becomes. Everything else in the two lines IS a key, so
    # a scanned one is reported as outside the grid rather than dropped.
    def is_pre_evo_of(species, target):
        # pre_to_finals maps a FINAL form to itself ('Thievul' ->
        # ['Thievul']), so identity must be excluded or every species
        # would look like its own pre-evolution.
        return species != target and target in pre_to_finals.get(species, [])

    threshold_species = sorted(
        s for s in collection_species
        if not is_pre_evo_of(s, focal) and not is_pre_evo_of(s, opponent))

    # Species this page actually ANALYZES: a grid species, or something
    # that evolves into one. The rest of the evolution line is read (so a
    # scanned Lickilicky on the Lickitung page is reported rather than
    # dropped) but never ranked -- and the CSV status text must not call
    # those rows "analyzed", which is the contradiction this list fixes.
    analyzed_species = sorted(
        s for s in collection_species
        if s in (focal, opponent)
        or is_pre_evo_of(s, focal) or is_pre_evo_of(s, opponent))

    opp_fast = man.get('opp_fast')
    opp_charged = man.get('opp_charged') or []
    if opp_fast:
        opp_moveset = (
            f"{opponent} {_pretty_move(opp_fast)} / "
            + ' + '.join(_pretty_move(c) for c in opp_charged)
            + (' (always baits)' if man.get('opp_always_baits') else ''))
    else:
        opp_moveset = f'{opponent} (moveset not recorded in the manifest)'
    return {
        'data_dir': str(data_dir) if data_dir is not None else str(DATA_DIR),
        'focal': focal,
        'opponent': opponent,
        'labels': labels,
        'files': files,
        'pretty': pretty,
        'collection_species': collection_species,
        'analyzed_species': analyzed_species,
        'threshold_species': threshold_species,
        'grid_species': [focal, opponent],
        'opp_moveset': opp_moveset,
        'out_name': (f'{focal.lower()}_vs_{opponent.lower()}'
                     f'_iv_robustness.html'),
    }


def move_legality(spec, grids_meta):
    """Which moves used by the embedded grids are NOT in the pinned pool?

    ICY_WIND is the 2026-08-16 Community Day move: the bake injects it
    because ``make_battle_pokemon`` takes move ids directly and has no
    legality guard. Every number computed from such a grid is a POST-CD
    projection, which the page must say out loud. Computed here rather
    than hardcoded, so it stays true for any dataset/gamemaster pair.
    """
    from gopvpsim.data import load_gamemaster
    gm = load_gamemaster()
    entry = None
    for e in gm.get('pokemon', []):
        if e.get('speciesName') == spec['focal']:
            entry = e
            break
    if entry is None:
        return {}
    standard = set(entry.get('fastMoves') or []) | set(
        entry.get('chargedMoves') or [])
    elite = set(entry.get('eliteMoves') or [])
    out = {}
    for label, g in grids_meta.items():
        used = [g.get('focal_fast')] + list(g.get('focal_charged') or [])
        absent = sorted({m for m in used if m and m not in standard
                         and m not in elite})
        # PvPoke lists an elite move in chargedMoves AND eliteMoves --
        # chargedMoves is the full legal pool. So membership in eliteMoves
        # alone is what makes a move event/Elite-TM-only.
        elite_only = sorted({m for m in used if m and m in elite})
        if absent or elite_only:
            out[label] = {'absent': absent, 'elite_only': elite_only}
    return out


def default_moveset_label(spec, grids_meta):
    """The grid label matching PvPoke's own default moveset, if any."""
    try:
        from gopvpsim.data import get_default_moveset
        fast, charged = get_default_moveset(spec['focal'], LEAGUE,
                                            shadow=False)
    except Exception:
        return None, None
    want = (fast, tuple(sorted(charged or ())))
    for label, g in grids_meta.items():
        got = (g.get('focal_fast'),
               tuple(sorted(g.get('focal_charged') or ())))
        if got == want:
            return label, {'fast': fast, 'charged': list(charged or ())}
    return None, {'fast': fast, 'charged': list(charged or ())}


def iv_table(species):
    """Canonical iv_rank-ordered per-spread table (index = rank - 1)."""
    ranked = iv_rank(species, league=LEAGUE, max_level=MAX_LEVEL)
    assert len(ranked) == N_IV, (species, len(ranked))
    return {
        'species': species,
        'ivs': [[r['atk_iv'], r['def_iv'], r['sta_iv']] for r in ranked],
        'level': [r['level'] for r in ranked],
        'cp': [int(r['cp']) for r in ranked],
        'atk': [round(float(r['atk']), 2) for r in ranked],
        'def': [round(float(r['def_']), 2) for r in ranked],
        'hp': [int(r['hp']) for r in ranked],
    }


def load_grid(data_dir, label, spec):
    p = data_dir / spec['files'][label]
    if not p.exists():
        return None
    z = np.load(p)
    won = wp.unpack_won(z['won_packed'], tuple(z['won_shape']))
    if won.shape != (N_IV, N_IV, N_SCEN):
        raise SystemExit(
            f'ABORT: {p.name} has shape {won.shape}, expected '
            f'({N_IV}, {N_IV}, {N_SCEN}) -- a partial/smoke bake must not '
            f'be rendered as if it were the full grid')
    return won, z


def check_axis_order(z, focal_tbl, opp_tbl, label):
    """The npz axes must match the page tables -- order AND levels.

    The IV check catches a reordered axis. The LEVEL check additionally
    catches a gamemaster whose stats moved under us: the npz stores the
    per-spread levels computed at BAKE time, so comparing them to the
    freshly computed table proves the rendered per-spread values still
    describe the same builds the grids were simulated with.
    """
    fi = np.asarray(z['focal_ivs'], dtype=int)
    oi = np.asarray(z['opp_ivs'], dtype=int)
    if not np.array_equal(fi, np.array(focal_tbl['ivs'], dtype=int)):
        raise SystemExit(f'ABORT: {label} focal_ivs are not in iv_rank order')
    if not np.array_equal(oi, np.array(opp_tbl['ivs'], dtype=int)):
        raise SystemExit(f'ABORT: {label} opp_ivs are not in iv_rank order')
    for key, tbl, side in (('focal_levels', focal_tbl, 'focal'),
                           ('opp_levels', opp_tbl, 'opponent')):
        if key not in getattr(z, 'files', []):
            continue
        baked = np.asarray(z[key], dtype=float)
        now = np.array(tbl['level'], dtype=float)
        if not np.allclose(baked, now):
            n = int((baked != now).sum())
            raise SystemExit(
                f'ABORT: {label} {side} per-spread LEVELS differ from the '
                f'baked arrays ({n} of {len(now)} rows). The gamemaster '
                f'this build is reading is not the one the grids were '
                f'simulated with, and the rendered stats would describe '
                f'different builds than the numbers.')


def coverage_counts(won):
    """cov['all'] / cov['top512']: flat [4096*9] uint16 counts (i*9 + si)."""
    all_c = won.sum(axis=1, dtype=np.int32)          # (4096, 9)
    top_c = won[:, :512, :].sum(axis=1, dtype=np.int32)
    assert all_c.max() <= N_IV and top_c.max() <= 512
    return ([int(v) for v in all_c.reshape(-1)],
            [int(v) for v in top_c.reshape(-1)])


def won_slice_b64(won, si):
    """base64(gzip(packbits(won[:, :, si]))) -- the JS decode contract."""
    packed = np.packbits(np.ascontiguousarray(won[:, :, si]),
                         axis=None, bitorder='big')
    return base64.b64encode(
        gzip.compress(packed.tobytes(), 6)).decode('ascii')


def load_meta_wins(data_dir, focal_tbl, grid_labels, *, oppiv='pvpoke'):
    """Read A1's meta_wins.npz into the page's meta_wins blob.

    A1 emits ``wins__<moveset>__<oppiv>__<bait>__<scenario>`` arrays (plus
    ties / mirror_win) in iv_rank order. We expose the arrays for the
    three grids this page renders, keyed by GRID label so the Pareto axis
    follows the grid/scenario dropdowns, and keep the DESIGN.md contract
    key ``wins_11`` (landing build, 1-1) as the labeled fallback.

    The iv_rank-order conversion A1 performed is VERIFIED here against the
    page's own iv_rank table -- a silent axis mismatch would corrupt every
    Pareto read-out.
    """
    p = data_dir / 'meta_wins.npz'
    if not p.exists():
        # Opponent-independent (Thievul vs the dive pool), so a dataset
        # without its own copy borrows the one already baked.
        p = METAWINS_FALLBACK_DIR / 'meta_wins.npz'
        if not p.exists():
            return None
    z = np.load(p, allow_pickle=True)
    if 'iv_rank_ivs' not in z:
        raise SystemExit('ABORT: meta_wins.npz has no iv_rank_ivs array, so '
                         'its axis order cannot be verified')
    if not np.array_equal(np.asarray(z['iv_rank_ivs'], dtype=int),
                          np.array(focal_tbl['ivs'], dtype=int)):
        raise SystemExit('ABORT: meta_wins.npz iv_rank_ivs does not match '
                         'this build\'s iv_rank order for Thievul')
    # NB: SCENARIO labels ('0-0'..'2-2'), deliberately named apart from the
    # GRID labels parameter -- shadowing the two silently emptied the
    # per-grid wins dict once already.
    scen_labels = [str(s) for s in z['scenario_labels']] \
        if 'scenario_labels' in z \
        else [f'{sf}-{so}' for sf in range(3) for so in range(3)]
    wins, ties, found = {}, {}, []
    for label in grid_labels:
        ms, bait = grid_to_metawins(label)
        per_scen, per_scen_t = {}, {}
        for sl in scen_labels:
            k = f'wins__{ms}__{oppiv}__{bait}__{sl}'
            kt = f'ties__{ms}__{oppiv}__{bait}__{sl}'
            if k in z:
                per_scen[sl] = [int(v) for v in np.asarray(z[k]).reshape(-1)]
            if kt in z:
                per_scen_t[sl] = [int(v) for v in np.asarray(z[kt]).reshape(-1)]
        if per_scen:
            wins[label] = per_scen
            ties[label] = per_scen_t
            found.append(label)
    contract_key = f'wins__iwpr__{oppiv}__bait__1-1'
    wins_11 = ([int(v) for v in np.asarray(z[contract_key]).reshape(-1)]
               if contract_key in z else None)
    prov = str(z['provenance']) if 'provenance' in z else ''
    return {
        'pool_n': int(z['pool_n']) if 'pool_n' in z else None,
        'oppiv': oppiv,
        'scenario_labels': scen_labels,
        'wins': wins,
        'ties': ties,
        'wins_11': wins_11,
        'wins_11_key': contract_key,
        'grids_covered': found,
        'provenance': prov,
        'note': (
            'Meta wins are vs the shipped dive pool ('
            + (str(int(z['pool_n'])) if 'pool_n' in z else '?')
            + ' entries, Thievul mirror included) at the dive\'s own '
            'opponent IVs (' + oppiv + ') and movesets, with the opponent '
            'always baiting; ties (score exactly 500) are not counted as '
            'wins. NOTE the two sides: the "baiting / no bait" in a GRID '
            'label is the ' + FOCAL + '\'s policy, while the opponent in '
            'every grid always baits.'),
    }


def load_json(path):
    if path is None or not pathlib.Path(path).exists():
        return None
    return json.loads(pathlib.Path(path).read_text())


# ---------------------------------------------------------------------------
# collection blob (POGOCollection injection)
# ---------------------------------------------------------------------------
def build_collection(spec):
    idx = get_pokemon_index()
    pokemon_index = {}
    for sp in spec['collection_species']:
        for name in (sp, f'{sp} (Female)'):
            if name in idx:
                e = idx[name]
                pokemon_index[name] = {'atk': e['atk'], 'def': e['def'],
                                       'hp': e['hp']}
    keep = set(spec['collection_species'])
    pre_to_finals = {}
    for pre, finals in _load_pre_to_finals().items():
        if pre not in keep:
            continue
        rel = [f for f in finals if f in keep]
        if rel:
            pre_to_finals[pre] = rel
    # Any-match thresholds: the page uses matchMons purely as a
    # species/evolution matcher, then indexes the analyzed grids by the IV
    # triple itself. Zero floors so nothing is filtered out here.
    thresholds = {
        sp: {LEAGUE_LABEL: {'Any': {'attack': 0, 'defense': 0, 'stamina': 0}}}
        for sp in spec['threshold_species'] if sp in idx
    }
    rank_lookup = {}
    for sp in spec['grid_species']:
        table = compute_rank_lookup(sp, league=LEAGUE, max_level=MAX_LEVEL,
                                    shadow=False)
        rank_lookup[sp] = {'normal': {f'{a},{d},{s}': r
                                      for (a, d, s), r in table.items()}}
    return {
        'league': LEAGUE,
        'leagueLabel': LEAGUE_LABEL,
        'leagueCap': LEAGUE_CAPS[LEAGUE],
        'leagueCaps': LEAGUE_CAPS,
        'maxLevel': MAX_LEVEL,
        'requireGender': None,
        'shadowAtkBonus': SHADOW_ATK_BONUS,
        'shadowDefMult': SHADOW_DEF_MULT,
        'cpm': {str(k): v for k, v in CPM.items()},
        'pokemonIndex': pokemon_index,
        'preToFinals': pre_to_finals,
        'thresholds': thresholds,
        'rankLookup': rank_lookup,
        'focalSpecies': spec['focal'],
        'oppSpecies': spec['opponent'],
        'collectionSpecies': spec['collection_species'],
        'analyzedSpecies': spec['analyzed_species'],
    }


# ---------------------------------------------------------------------------
# assets
# ---------------------------------------------------------------------------
def plotly_source():
    cached = PLOTLY_CACHE_DIR / PLOTLY_FILENAME
    if cached.exists():
        return cached.read_text()
    import deep_dive
    data = deep_dive._download_plotly_with_retry()
    if data is None:
        raise SystemExit(
            'ABORT: Plotly is not in the local cache and could not be '
            'downloaded; the page must be self-contained offline, so a CDN '
            'reference is not an acceptable fallback here')
    PLOTLY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data.decode()


PAGE_CSS = """
  body { margin: 0 auto; padding: 24px 20px 60px; max-width: 1180px;
         background: var(--bg); color: var(--text);
         font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                      Helvetica, Arial, sans-serif; line-height: 1.5; }
  h1 { color: var(--title); margin: 0 0 6px; font-size: 26px; }
  h2 { color: var(--heading); margin: 34px 0 6px; font-size: 20px;
       border-bottom: 1px solid var(--border); padding-bottom: 4px; }
  h3 { color: var(--heading); margin: 20px 0 6px; font-size: 16px; }
  h4 { color: var(--heading); margin: 16px 0 4px; font-size: 14px; }
  h5 { color: var(--text-muted); margin: 12px 0 3px; font-size: 13px;
       text-transform: none; }
  a { color: var(--accent); }
  .tl-banner-ai { background: var(--callout-bg); color: var(--callout-fg);
       border-left: 4px solid var(--callout-ai); padding: 10px 14px;
       margin: 12px 0; font-size: 14px; }
  .tl-banner-ai strong { color: var(--callout-strong); }
  .tl-intro { font-size: 15px; margin: 8px 0 2px; }
  .tl-archive { background: var(--surface); border-left: 4px solid
       var(--flip); color: var(--flip); padding: 8px 14px; margin: 10px 0;
       font-size: 14px; }
  .tl-methodology { margin: 34px 0 0; border: 1px solid var(--border);
       border-radius: 4px; padding: 8px 14px; background: var(--surface); }
  .tl-methodology > summary { cursor: pointer; color: var(--heading);
       font-size: 16px; font-weight: 600; }
  .tl-banner-ai { padding: 8px 14px; margin: 8px 0; font-size: 13.5px; }
  .tl-prov { color: var(--text-muted); font-size: 12.5px; margin: 6px 0 0;
       font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .tl-missing { border-left: 4px solid var(--flip); color: var(--flip);
       background: var(--surface); padding: 10px 14px; margin: 10px 0;
       font-size: 14px; }
  .tl-missing strong { color: var(--flip); }
  .tl-rail { border-left: 3px solid var(--border-2); color: var(--text-muted);
       padding: 4px 12px; margin: 6px 0; font-size: 13px; }
  .tl-note { color: var(--text-muted); font-size: 13px; margin: 6px 0; }
  .tl-warn { color: var(--flip); font-size: 13px; }
  .tl-ctl { display: flex; flex-wrap: wrap; gap: 14px; align-items: end;
       background: var(--surface); border: 1px solid var(--border);
       border-radius: 4px; padding: 12px 14px; margin: 14px 0; }
  .tl-ctl label { display: block; font-size: 12px; color: var(--text-muted); }
  .tl-ctl select, .tl-ctl input, textarea {
       padding: 4px 6px; background: var(--surface-2); color: var(--text);
       border: 1px solid var(--border-2); border-radius: 4px;
       font-family: inherit; font-size: 13px; }
  button { padding: 4px 12px; background: var(--surface-2); color: var(--text);
       border: 1px solid var(--border-2); border-radius: 4px; cursor: pointer;
       font-size: 13px; }
  button:hover { background: var(--border-2); }
  .tl-plot { width: 100%; height: 520px; }
  /* Both axes are the same 4096 ranks, so the data area wants to be near
     square: at ~840px of data width (1180 body - 2x150 axis gutters) this
     height puts a 16-rank hover band at ~2.5px instead of ~2.1px. Raising
     this one number is what buys a thicker band -- see the note in
     thievul_licki_page.js onHeatHover. */
  .tl-heat { width: 100%; height: 760px; }
  /* 3 rows of ~250px small multiples plus title/legend chrome. */
  .tl-plot-grid { height: 830px; }
  .tl-tldr-headline { flex: 1 1 100%; margin: 0 0 2px; font-size: 14.5px;
       color: var(--text); }
  .tl-tldr-qual { color: var(--flip); font-size: 12.5px; }
  .tl-satblock { flex: 1 1 100%; background: var(--surface);
       border: 1px solid var(--border); border-left: 4px solid var(--accent);
       border-radius: 4px; padding: 8px 14px; margin: 4px 0 2px;
       font-size: 13px; color: var(--text-muted); }
  .tl-satblock strong { color: var(--text); }
  .tl-satblock ul { margin: 4px 0 0; padding-left: 18px; }
  .tl-satblock li.tl-sat-current { color: var(--text); }
  .tl-verdict-denial { background: var(--surface);
       border: 1px solid var(--border); border-left: 4px solid var(--accent);
       border-radius: 4px; padding: 10px 14px; margin: 12px 0; }
  .tl-verdict-denial h4 { margin: 0 0 4px; }
  .tl-chip { display: inline-block; padding: 1px 7px; border-radius: 9px;
       font-size: 11.5px; white-space: nowrap; border: 1px solid; }
  .tl-chip-ok { color: var(--win); border-color: var(--win);
       background: var(--cell-win-bg); }
  .tl-chip-warn { color: var(--flip); border-color: var(--flip);
       background: var(--cell-loss-bg); }
  table.tl tr.tl-user-top td { background: var(--cell-win-bg);
       box-shadow: inset 3px 0 0 var(--notable); }
  .tl-user-empty { border: 1px dashed var(--border-2); border-radius: 4px;
       padding: 8px 12px; margin: 8px 0 0; }
  textarea#tl-csv { min-height: 58px; }
  .tl-tldr .tl-card { flex: 1 1 210px; padding: 10px 14px; }
  .tl-tldr .tl-card h4 { margin: 0 0 2px; }
  .tl-tldr-metrics { margin-top: 6px; display: flex; flex-wrap: wrap;
       gap: 10px 18px; }
  .tl-tldr-num { display: block; font-size: 19px; color: var(--text);
       font-variant-numeric: tabular-nums; }
  .tl-tldr-lab { display: block; font-size: 11.5px;
       color: var(--text-muted); }
  .tl-scroll { overflow-x: auto; max-height: 420px; overflow-y: auto;
       border: 1px solid var(--border); border-radius: 4px; }
  table.tl { border-collapse: collapse; width: 100%; font-size: 13px;
       font-variant-numeric: tabular-nums; }
  table.tl th, table.tl td { border-bottom: 1px solid var(--border);
       padding: 4px 8px; text-align: left; white-space: nowrap; }
  table.tl th { color: var(--text-muted); font-weight: 600;
       position: sticky; top: 0; background: var(--surface); }
  .tl-verdict { background: var(--surface); border: 1px solid var(--border);
       border-left: 4px solid var(--notable); border-radius: 4px;
       padding: 10px 14px; margin: 10px 0; }
  .tl-verdict-claim { font-weight: 600; color: var(--text); }
  .tl-verdict-call { color: var(--notable); font-size: 15px; margin: 4px 0; }
  .tl-verdict-detail { color: var(--text-muted); font-size: 13px; }
  .tl-cards { display: flex; flex-wrap: wrap; gap: 14px; }
  .tl-card { background: var(--surface); border: 1px solid var(--border);
       border-radius: 4px; padding: 12px 16px; flex: 1 1 300px; }
  .tl-card-sub { color: var(--text-muted); font-size: 13px; }
  .tl-card-spread { color: var(--notable); font-size: 15px;
       font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .tl-card-caveat { color: var(--flip); font-size: 12.5px; }
  .tl-card ul { margin: 6px 0 0; padding-left: 18px; font-size: 13.5px; }
  textarea#tl-csv { width: 100%; min-height: 90px; }
  footer.tl-foot { margin-top: 40px; border-top: 1px solid var(--border);
       padding-top: 12px; color: var(--text-muted); font-size: 12.5px; }
"""


BODY_TEMPLATE = """
<h1>{focal} vs {opponent}: how much do IVs actually matter?</h1>
<noscript><div class="tl-missing"><strong>This page needs JavaScript.</strong>
Every panel is computed in your browser from a data blob embedded in this
file - nothing is pre-rendered, so with JavaScript disabled the sections
below stay empty. No data is sent anywhere either way.</div></noscript>
{archive_block}
<div class="tl-banner-ai"><strong>Human-guided, AI-generated
(Claude).</strong> <a href="#tl-methodology">Methodology, honesty notes and
disclosures</a>.</div>
<p class="tl-intro">{intro}</p>

<h2>Controls</h2>
<div class="tl-ctl">
  <div><label for="tl-grid">Grid (moveset / bait)</label>
    <select id="tl-grid"></select></div>
  <div><label for="tl-scenario">Shield scenario</label>
    <select id="tl-scenario"></select></div>
  <div><label for="tl-cohort">{opponent} cohort</label>
    <select id="tl-cohort"></select></div>
  <div id="tl-cohort-custom" style="display:none">
    <label for="tl-cohort-custom-input">Custom ranks / IVs
      (e.g. 1-50, 15/15/14)</label>
    <input id="tl-cohort-custom-input" type="text" size="26"></div>
</div>
<!-- The three rails that change how EVERY number below is read (what a
     tie is, that the cohort is a choice, what the meta axis is bound to)
     live here, always visible. The rest stay in the collapsed
     methodology section at the foot of the page. -->
<div id="tl-rails"></div>

<h2>Your IVs: which one should you build?</h2>
<p class="tl-note">Runs entirely in your browser; nothing is uploaded.
Paste your Poke Genie CSV (or pick the file) and your mons are ranked
below. Only {collection_species} rows are read.</p>
<div class="tl-ctl">
  <div><label for="tl-manual-species">Species (what each one feeds)</label>
    <select id="tl-manual-species">
      <option value="thievul">{focal} - ranked in the table below</option>
      <option value="licki">{opponent} - {licki_scope}</option>
    </select></div>
  <div><label for="tl-manual-a">Atk IV</label>
    <select id="tl-manual-a"></select></div>
  <div><label for="tl-manual-d">Def IV</label>
    <select id="tl-manual-d"></select></div>
  <div><label for="tl-manual-s">Sta IV</label>
    <select id="tl-manual-s"></select></div>
  <div><label for="tl-basis">Build basis (which moveset you will run)</label>
    <select id="tl-basis"></select></div>
  <div><button id="tl-manual-add">Add spread</button></div>
  <div><button id="tl-user-clear">Clear all</button></div>
  <div><label for="tl-csv-file">Poke Genie CSV file</label>
    <input id="tl-csv-file" type="file" accept=".csv,text/csv"></div>
</div>
<div id="tl-manual-status"></div>
<textarea id="tl-csv" placeholder="...or paste your Poke Genie CSV export
here"></textarea>
<p><button id="tl-csv-load">Load pasted CSV</button></p>
<div id="tl-csv-status"></div>
<div id="tl-user-list"></div>

<h2>The short version</h2>
<div id="tl-tldr" class="tl-cards tl-tldr"></div>
<p class="tl-note" id="tl-tldr-link"></p>

<h2>Every matchup at once: 4096 {focal} x 4096 {opponent}</h2>
<div class="tl-ctl">
  <div><label><input id="tl-heat-named" type="checkbox" checked>
    show named builds</label></div>
  <div class="tl-note">Hover a cell to outline it across the view. At the
    default zoom a cell covers a BAND of ranks, not one spread -- the
    caption under the plot states the current band size, which narrows to a
    single spread as you zoom in.</div>
</div>
<div id="tl-heat"></div>
<p class="tl-note" id="tl-heat-note"></p>

<h2>Coverage vs attack: is there a cliff?</h2>
<div class="tl-ctl">
  <div><label for="tl-cliff-color">Colour by</label>
    <select id="tl-cliff-color"></select></div>
</div>
<div id="tl-cliff"></div>
<p class="tl-note" id="tl-cliff-note"></p>

<h2>Off the frontier: attack vs stat-product rank</h2>
<div id="tl-frontier"></div>
<p class="tl-note" id="tl-frontier-note"></p>

<h2>Coverage: which {focal} spreads beat the most {opponent}</h2>
<div class="tl-ctl">
  <div><label for="tl-cov-view">View</label>
    <select id="tl-cov-view"></select></div>
</div>
<div id="tl-scatter"></div>
<p class="tl-note" id="tl-scatter-note"></p>

<h2>Pareto: {opponent} coverage vs the rest of the meta</h2>
<div id="tl-pareto"></div>
<p class="tl-note" id="tl-pareto-note"></p>

<h2>Drill-down: one {opponent} spread at a time</h2>
<div class="tl-ctl">
  <div><label for="tl-drill-licki">{opponent} (rank or a/d/s)</label>
    <input id="tl-drill-licki" type="text" value="1" size="10"></div>
  <div><label for="tl-drill-thievul">Your {focal} (rank or a/d/s)</label>
    <input id="tl-drill-thievul" type="text" value="1" size="10"></div>
  <div><label for="tl-drill-mine">Your {opponent} spreads</label>
    <select id="tl-drill-mine"></select></div>
  <div><button id="tl-drill-go">Update</button></div>
</div>
<div id="tl-drill-out"></div>

<h2>Mechanism: breakpoints, bulk, and the two claims</h2>
<div id="tl-mech"></div>

<h2>Recommendations</h2>
<div id="tl-reco" class="tl-cards"></div>

{denial_section}
<details id="tl-methodology" class="tl-methodology" open>
<summary>Methodology, honesty notes and disclosures</summary>
<p class="tl-prov">{provenance}</p>
{missing_block}
<div id="tl-banner"></div>
</details>

<footer class="tl-foot">
<p>{attribution}</p>
<p>One-off analysis page, generated for the {focal} Community Day. Built by
<code>scripts/build_thievul_licki_page.py</code> from
<code>{data_dir}</code>; contract in
<code>{design_doc}</code>{design_note}.</p>
</footer>
"""


def missing_block_html(missing):
    if not missing:
        return ('<div class="tl-rail">All declared inputs are present in '
                'this build.</div>')
    items = ''.join(f'<li>{m}</li>' for m in missing)
    return ('<div class="tl-missing"><strong>Incomplete build: '
            f'{len(missing)} input(s) missing.</strong> The panels that '
            f'need them show a placeholder instead of a number.'
            f'<ul>{items}</ul></div>')


def build_data(data_dir, *, allow_missing, won_labels, won_scenarios,
               breakpoints_path, reco_path):
    missing = []
    manifest = load_manifest(data_dir)
    if manifest is None:
        missing.append('manifest.json (grid provenance: engine + gamemaster '
                       'hashes, sim counts)')

    spec = dataset_spec(manifest, data_dir)
    try:
        import sweep_cache
        gm_now = sweep_cache.gamemaster_hash()
    except Exception:
        gm_now = None
    gm_baked = (manifest or {}).get('gamemaster')
    if won_labels is None:
        won_labels = set(spec['labels'])
    focal_tbl = iv_table(spec['focal'])
    opp_tbl = iv_table(spec['opponent'])

    cov = {}
    won_b64 = {}
    grids_meta = {}
    grid_hashes = {}
    total_sims = manifest.get('total_sims') if manifest else None
    for label in spec['labels']:
        loaded = load_grid(data_dir, label, spec)
        if loaded is None:
            missing.append(
                f"{spec['files'][label]} "
                f"({spec['pretty'][label]}) -- still baking")
            continue
        won, z = loaded
        check_axis_order(z, focal_tbl, opp_tbl, label)
        # Two grids can come out BYTE-IDENTICAL for a real reason (e.g. when
        # the cheaper charged move is also the higher-DPE one, baiting and
        # not baiting pick the same move every time). That is fine, but the
        # page must not let a reader treat them as independent evidence, so
        # identical grids are detected here and disclosed in the notes.
        grid_hashes[label] = hashlib.md5(
            np.ascontiguousarray(z['won_packed']).tobytes()).hexdigest()[:12]
        all_c, top_c = coverage_counts(won)
        cov[label] = {'all': all_c, 'top512': top_c}
        gm = (manifest or {}).get('grids', {}).get(label, {})
        grids_meta[label] = {
            'pretty': spec['pretty'][label],
            'focal_fast': gm.get('focal_fast'),
            'focal_charged': gm.get('focal_charged'),
            'bait': gm.get('bait'),
            'shape': list(won.shape),
        }
        if label in won_labels:
            won_b64[label] = {}
            for si in won_scenarios:
                won_b64[label][str(si)] = won_slice_b64(won, si)
            nbytes = sum(len(v) for v in won_b64[label].values())
            print(f'  {label}: {len(won_b64[label])} win-bitmap slice(s), '
                  f'{nbytes / 1e6:.1f} MB base64')
        del won

    dup_groups = {}
    for lb, h in grid_hashes.items():
        dup_groups.setdefault(h, []).append(lb)
    duplicates = [sorted(g) for g in dup_groups.values() if len(g) > 1]

    if not cov and not allow_missing:
        raise SystemExit('ABORT: no grids found (pass --allow-missing to '
                         'build a placeholder page anyway)')

    meta_wins = load_meta_wins(data_dir, focal_tbl, spec['labels'])
    if meta_wins is None:
        missing.append('meta_wins.npz (per-IV meta wins vs the dive pool) '
                       '-- the Pareto panel needs it')
    breakpoints = load_json(breakpoints_path)
    if breakpoints is None:
        missing.append('breakpoints.json (closed-form damage/bulk layer) -- '
                       'the mechanism section and the damage-tier coloring '
                       'need it')
    denial = load_json(data_dir / 'licki_denial.json')
    reco = load_json(reco_path)
    if reco is None:
        missing.append('reco.json (recommendation blob, computed in the '
                       'assembly phase)')

    scenarios = [f'{sf}-{so}' for sf in range(3) for so in range(3)]
    notes = [
        'meta_wins is measured against the shipped dive pool at the dive\'s '
        'own opponent IVs and movesets -- it is not a full-meta ladder '
        'simulation. Which shield scenario it reports FOLLOWS the controls; '
        'the meta-wins rail below states the binding actually in effect.',
        f"Every {spec['opponent']} here is {spec['opp_moveset']}.",
    ]
    if gm_now and gm_baked and gm_now != gm_baked:
        notes.append(
            f'GAMEMASTER DRIFT: the grids were baked against gamemaster '
            f'{gm_baked}; this page was built while the local gamemaster '
            f'was {gm_now}. The per-spread IVs and levels stored in the '
            f'baked grids were re-verified against this build\'s tables and '
            f'match exactly, so every simulated number still describes the '
            f'same builds. Move-legality statements below reflect '
            f'{gm_now}, NOT the pinned bake gamemaster.')
    if duplicates and len(cov) - sum(len(g) - 1 for g in duplicates) == 1:
        notes.append(
            'After collapsing identical grids, this build contains only ONE '
            'distinct grid, so it establishes NOTHING about moveset or bait '
            'robustness.')
    if not won_b64:
        notes.append('No per-spread win bitmap is embedded in this build, '
                     'so the drill-down and the narrow cohorts are '
                     'unavailable; the pre-aggregated coverage counts are '
                     'unaffected.')

    named_builds = [
        {'label': '6/15/5 (discord claim)', 'ivs': list(CLAIM_IVS)},
        {'label': 'rank 1 (stat product)',
         'ivs': list(focal_tbl['ivs'][0])},
    ]

    for grp in duplicates:
        notes.append(
            'IDENTICAL GRIDS: ' + ' and '.join(spec['pretty'][g] for g in grp)
            + ' produced BYTE-IDENTICAL win data, so they are one grid, not '
            'two independent ones. Agreement between them is not evidence of '
            'moveset/bait robustness: no matchup outcome changes when you '
            'switch between them. (The meta-wins axis is a different '
            'measurement -- it is computed per grid against the dive pool '
            'and DOES differ between the two labels -- so the Pareto x '
            'axis and the meta column can move even though every '
            'win/loss in this analysis is identical.)')

    # Diagnostic only -- printed for the operator, never rendered, and no
    # longer part of TL_DATA, so the published bytes do not depend on which
    # gamemaster vintage happens to be cached at build time.
    injected = move_legality(spec, grids_meta)
    if injected:
        print(f'  note: move-legality probe vs the CURRENTLY LOADED '
              f'gamemaster flags {sorted(injected)} '
              f'(diagnostic only; the page ships the static CD note)')
    uses_cd_move = any(
        CD_MOVE == g.get('focal_fast')
        or CD_MOVE in (g.get('focal_charged') or [])
        for g in grids_meta.values())
    if uses_cd_move:
        notes.append(CD_MOVE_NOTE)
    # (The cliff rule disclosure is GENERATED by the page app from the
    # same function that renders the sentence -- see cliffRuleText() in
    # scripts/thievul_licki_page.js. Hand-written parallel prose here is
    # exactly what drifted.)
    dm_label, dm_moves = default_moveset_label(spec, grids_meta)
    if dm_label:
        notes.append(
            f"PvPoke's own default {spec['focal']} moveset for this league "
            f"is {_pretty_move(dm_moves['fast'])} / "
            + ' + '.join(_pretty_move(m) for m in dm_moves['charged'])
            + f" -- the {spec['pretty'][dm_label]} grid. Conclusions that "
            'hold on one moveset need not hold on another; the summary at '
            'the top of the page reports each grid separately.')
    elif dm_moves:
        notes.append(
            f"PvPoke's own default {spec['focal']} moveset "
            f"({_pretty_move(dm_moves['fast'])} / "
            + ' + '.join(_pretty_move(m) for m in dm_moves['charged'])
            + ') is NOT among the embedded grids, so this page says '
            'nothing about how these conclusions behave on it.')

    meta = {
        'generated': _dt.datetime.now(_dt.timezone.utc)
                        .strftime('%Y-%m-%d %H:%M UTC'),
        'engine': (manifest or {}).get('engine'),
        'gamemaster': gm_baked,
        'gamemaster_now': gm_now,
        'mechanics': (manifest or {}).get('mechanics'),
        'total_sims': total_sims,
        'matchup_cells': len(cov) * N_IV * N_IV * N_SCEN,
        'grid_hashes': grid_hashes,
        'duplicate_grids': duplicates,
        'default_moveset_label': dm_label,
        'default_moveset': dm_moves,
        'wall_seconds': (manifest or {}).get('wall_seconds'),
        'scenarios': scenarios,
        'grids': grids_meta,
        'movesets': dict(spec['pretty']),
        'opp_moveset': spec['opp_moveset'],
        'focal': spec['focal'], 'opponent': spec['opponent'],
        'league': LEAGUE,
        'provenance': (
            'Human-guided, AI-generated (Claude). Motivating question: '
            'HSH discord 2026-08-14/16 '
            '("thievul iv tech? it seems very sensitive"; "6/15/5" as the '
            'best Sucker Punch breakpoint spread on "Licki"; "do you not '
            f'want 15 hp"). Analyzed opponent on this page: '
            f"{spec['opponent']}."),
        'notes': notes,
        'named_builds': named_builds,
        'missing': missing,
    }
    data = {
        'meta': meta,
        'thievul': focal_tbl,
        'licki': opp_tbl,
        'cov': cov,
        'meta_wins': meta_wins,
        'won_b64': won_b64,
        'breakpoints': breakpoints,
        'reco': reco,
        'collection': build_collection(spec),
    }
    # Only datasets with a denial analysis carry the key at all, so the
    # archived page's blob does not gain a null it never uses.
    if denial is not None:
        data['licki_denial'] = denial
    return data, missing, spec


def render_page(data, missing, spec):
    blob = json.dumps(data, separators=(',', ':'), default=_jsonable)
    pogo_js = (REPO / 'scripts' / 'deep_dive_user_collection.js').read_text()
    page_js = (REPO / 'scripts' / 'thievul_licki_page.js').read_text()
    m = data['meta']
    sims = m['total_sims']
    cells = m.get('matchup_cells') or 0
    sim_txt = ('n/a' if sims is None else
               f"{sims:,} deduplicated engine calls covering "
               f"{cells:,} matchup cells"
               if cells else f"{sims:,} deduplicated engine calls")
    dups = m.get('duplicate_grids') or []
    dup_txt = ''
    if dups and cells:
        dup_cells = sum(len(g) - 1 for g in dups) * N_IV * N_IV * N_SCEN
        pct = 100.0 * dup_cells / cells
        pretty = {k: v.get('pretty', k) for k, v in
                  (m.get('grids') or {}).items()}
        dup_txt = (' -- but '
                   + '; '.join(' and '.join(pretty.get(x, x) for x in g)
                               for g in dups)
                   + f' are byte-identical, so {pct:.0f}% of those cells '
                     f'are duplicates of another grid; the intro at the '
                     f'top of the page quotes the DISTINCT total, '
                     f'{cells - dup_cells:,}')
    prov = (f"generated {m['generated']} | engine {m['engine'] or 'n/a'} | "
            f"gamemaster {m['gamemaster'] or 'n/a'} | "
            f"mechanics {m.get('mechanics') or 'n/a'} | "
            f"{sim_txt}{dup_txt} | grids embedded: "
            f"{', '.join(sorted(data['cov'])) or 'none'}")
    rel = str(spec['data_dir'])
    try:
        rel = str(pathlib.Path(spec['data_dir']).resolve()
                  .relative_to(REPO)) + '/'
    except Exception:
        pass
    design = rel + 'DESIGN.md'
    design_note = ''
    if not (pathlib.Path(spec['data_dir']) / 'DESIGN.md').exists():
        # The annotation goes NEXT TO the <code> path, never inside it --
        # inside, "(shared contract)" reads as part of the filename.
        design = 'userdata/thievul_licki/DESIGN.md'
        design_note = ' (shared contract)'
    n_grids = len(data['cov'])
    cells = m.get('matchup_cells') or 0
    # ONE line. Everything else that used to live up here now sits in the
    # collapsible methodology section at the bottom.
    # Duplicate grids are NOT extra work: quoting the raw product
    # overstated the Lickilicky page by 25%. The headline uses the
    # distinct count and says so when they differ.
    duplicates = m.get('duplicate_grids') or []
    n_distinct = n_grids - sum(len(g) - 1 for g in duplicates)
    distinct_cells = n_distinct * N_IV * N_IV * N_SCEN
    pretty_of = {k: v.get('pretty', k) for k, v in
                 (m.get('grids') or {}).items()}
    dup_clause = (
        f" ({n_grids} grids were baked, but "
        + '; '.join(' and '.join(pretty_of.get(x, x) for x in g)
                    for g in duplicates)
        + " are byte-identical, so they count once)"
        if duplicates else "")
    grid_word = 'grid' if n_distinct == 1 else 'grids'
    intro = (
        f"{N_IV:,} x {N_IV:,} IV spreads x {N_SCEN} shield scenarios x "
        f"{n_distinct} distinct moveset/bait {grid_word} = "
        f"{distinct_cells:,} simulated matchups{dup_clause}, "
        f"for the {spec['focal']} Community Day. "
        f"<a href=\"{MAIN_DIVE_URL}\">{spec['focal']}'s main Great League "
        f"dive</a>."
        + (CROSSLINK.get(spec['opponent'].lower(), ''))
    )
    archive = ARCHIVE_NOTE.get(spec['opponent'].lower())
    # An archived page states it will not be updated, so a section whose
    # input is absent is OMITTED rather than shipped as an eternal
    # "not baked yet" placeholder.
    has_denial = data.get('licki_denial') is not None
    denial_section = (
        f"<h2>The other side: anti-{spec['focal']} {spec['opponent']} "
        f"tech</h2>\n<div id=\"tl-denial\"></div>\n"
        if has_denial or not archive else '')
    archive_block = (f'<div class="tl-archive"><strong>{archive}</strong>'
                     f'</div>' if archive else '')
    body = BODY_TEMPLATE.format(
        provenance=prov,
        missing_block=missing_block_html(missing),
        collection_species=', '.join(spec['collection_species']),
        focal=spec['focal'],
        opponent=spec['opponent'],
        data_dir=rel,
        design_doc=design,
        design_note=design_note,
        intro=intro,
        archive_block=archive_block,
        denial_section=denial_section,
        licki_scope=('heatmap overlay, drill-down and the anti-'
                     + spec['focal'] + ' section' if has_denial
                     else 'heatmap overlay and drill-down'),
        attribution=PVPOKE_ATTRIBUTION_HTML,
    )
    return f"""<!DOCTYPE html>
<html {data_theme_attr()}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{theme_head_script()}
<title>{spec['focal']} vs {spec['opponent']} - IV robustness{
    ' (archived)' if ARCHIVE_NOTE.get(spec['opponent'].lower()) else ''}</title>
<style>{theme_css()}{PAGE_CSS}</style>
</head>
<body>
{theme_picker_html()}
{body}
<script>{plotly_source()}</script>
<script>{pogo_js}</script>
<script>var TL_DATA = {blob};</script>
<script>{page_js}</script>
</body>
</html>
"""


def parse_scenarios(text):
    if text in (None, '', 'all'):
        return list(range(N_SCEN))
    out = []
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        v = int(part)
        if not 0 <= v < N_SCEN:
            raise SystemExit(f'ABORT: scenario index {v} out of range 0..8')
        out.append(v)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data-dir', default=str(DATA_DIR),
                    help='dataset directory; the opponent, grid labels and '
                         'output filename all derive from its manifest.json')
    ap.add_argument('--out', default=None,
                    help='output path (default: userdata/dives/'
                         '<focal>_vs_<opponent>_iv_robustness.html)')
    ap.add_argument('--allow-missing', action='store_true',
                    help='build even when inputs are absent; every affected '
                         'panel renders a visible placeholder')
    ap.add_argument('--won-labels', default='all',
                    help="comma list of grid labels to embed the full win "
                         "bitmap for, or 'all' / 'none'")
    ap.add_argument('--won-scenarios', default='all',
                    help="comma list of scenario indices (si = sf*3+so) to "
                         "embed bitmaps for, or 'all'")
    ap.add_argument('--publish-out', default=None,
                    help='ALSO write a publish copy here. This is the ONLY '
                         'way to write under userdata/website/ (the default '
                         'output path keeps the hard guard); passing it is '
                         'a deliberate, logged decision to publish.')
    ap.add_argument('--publish', action='store_true',
                    help='shorthand for --publish-out '
                         'userdata/website/<the dataset\'s publish slug>')
    ap.add_argument('--breakpoints', default=None)
    ap.add_argument('--reco', default=None)
    args = ap.parse_args(argv)

    data_dir = pathlib.Path(args.data_dir)
    if args.won_labels == 'all':
        won_labels = None          # resolved to the dataset's own labels
    elif args.won_labels == 'none':
        won_labels = set()
    else:
        won_labels = {s.strip() for s in args.won_labels.split(',') if s.strip()}
    won_scenarios = parse_scenarios(args.won_scenarios)

    bp_path = args.breakpoints or (data_dir / 'breakpoints.json')
    reco_path = args.reco or (data_dir / 'reco.json')

    data, missing, spec = build_data(
        data_dir, allow_missing=args.allow_missing, won_labels=won_labels,
        won_scenarios=won_scenarios, breakpoints_path=bp_path,
        reco_path=reco_path)
    if missing and not args.allow_missing:
        raise SystemExit(
            'ABORT: missing inputs (pass --allow-missing to build a page '
            'with visible placeholders):\n  - ' + '\n  - '.join(missing))

    html = render_page(data, missing, spec)
    out = pathlib.Path(args.out) if args.out else (DIVES_DIR
                                                   / spec['out_name'])
    # Publish safety: resolve symlinks and '..' BEFORE testing the path, so
    # userdata/dives/x -> userdata/website/x (or a '..' walk into it) cannot
    # slip a LOCAL-ONLY page into the rsynced tree.
    real = os.path.realpath(str(out.parent)) + os.sep + out.name
    if 'userdata/website' in real.replace(os.sep, '/'):
        raise SystemExit('ABORT: this page is LOCAL ONLY and must not be '
                         f'written under userdata/website/ (resolved to '
                         f'{real})')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    size_mb = len(html) / 1e6
    print(f'wrote {out} ({size_mb:.2f} MB)')
    if size_mb > 40:
        print(f'  WARNING: {size_mb:.0f} MB is heavy for a browser to parse. '
              f'Trim with --won-labels / --won-scenarios (the aggregated '
              f'coverage panels do not need the bitmaps).')
    if missing:
        print(f'  {len(missing)} missing input(s), rendered as visible '
              f'placeholders:')
        for m in missing:
            print(f'    - {m}')

    # ---- publish copy (explicit opt-in only) ----
    pub = args.publish_out
    if args.publish and not pub:
        slug = PUBLISH_SLUG.get(spec['opponent'].lower())
        if slug is None:
            raise SystemExit(
                f"ABORT: no publish slug is defined for opponent "
                f"{spec['opponent']}; pass --publish-out explicitly")
        pub = str(REPO / 'userdata' / 'website' / slug)
    if pub:
        if missing:
            raise SystemExit(
                'ABORT: refusing to publish a page with '
                f'{len(missing)} missing input(s) -- a placeholder must not '
                'ship. Fix the inputs or drop --publish/--publish-out.')
        pub_path = pathlib.Path(pub)
        pub_path.parent.mkdir(parents=True, exist_ok=True)
        pub_path.write_text(html)
        print(f'  PUBLISH COPY WRITTEN: {pub_path}')
        print('    ^ this is inside the rsynced website tree and WILL go '
              'public on the next publish run. The default output path '
              'still refuses to write there; --publish-out is the '
              'deliberate override.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
