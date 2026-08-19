#!/usr/bin/env python
"""Pair config loader for the joint IV robustness kit.

One TOML per (focal, opponent) pair drives the whole 6-step pipeline
(bake -> meta -> breakpoints -> assemble -> denial -> page); see
docs/joint_iv_reuse_plan.md section 2. The Thievul-vs-Licki pipeline is
the kit's first config instance (pairs/thievul_lickilicky.toml,
pairs/thievul_lickitung.toml) and must rebuild its shipped artifacts
byte-identically -- that regression is the S1 acceptance test.

Required schema (unknown [pair] keys are an error -- a typo'd optional
key must not silently become a no-op):

    [pair]
    league = "great"
    focal = "Thievul"                # PvPoke speciesName, base form
    focal_shadow = false
    focal_slug = "thievul"           # npz filename prefix / key prefix
    opponent = "Lickilicky"
    opponent_shadow = false
    opponent_slug = "lickilicky"
    opponent_fast = "ROLLOUT"
    opponent_charged = ["BODY_SLAM", "SHADOW_BALL"]
    data_dir = "userdata/thievul_lickilicky"   # repo-relative
    injected_moves = []              # focal move ids legal-injected
                                     # (CD-lag; disclosed on-page)
    # replay_blob = "userdata/replay/....replay.pkl.gz"   # optional

    [[grids]]                        # bake order = list order
    label = "iwpr_bait"
    focal_fast = "SUCKER_PUNCH"
    focal_charged = ["ICY_WIND", "PLAY_ROUGH"]
    bait = true

Step-specific sections ([meta], [breakpoints], [assemble], [denial],
[page]) are validated by their own steps; this loader carries them
through verbatim in ``raw``.
"""
import dataclasses
import pathlib
import tomllib

REPO = pathlib.Path(__file__).resolve().parent.parent
PAIRS_DIR = REPO / 'pairs'

_PAIR_REQUIRED = {
    'league', 'focal', 'focal_shadow', 'focal_slug', 'opponent',
    'opponent_shadow', 'opponent_slug', 'opponent_fast', 'opponent_charged',
    'data_dir', 'injected_moves',
}
_PAIR_OPTIONAL = {'replay_blob'}
_GRID_REQUIRED = {'label', 'focal_fast', 'focal_charged', 'bait'}
_KNOWN_SECTIONS = {'pair', 'grids', 'meta', 'breakpoints', 'assemble',
                   'denial', 'page'}


@dataclasses.dataclass(frozen=True)
class GridSpec:
    label: str
    focal_fast: str
    focal_charged: tuple
    bait: bool


@dataclasses.dataclass(frozen=True)
class PairConfig:
    path: pathlib.Path
    league: str
    focal: str
    focal_shadow: bool
    focal_slug: str
    opponent: str
    opp_shadow: bool
    opp_slug: str
    opp_fast: str
    opp_charged: tuple
    data_dir: pathlib.Path
    injected_moves: tuple
    replay_blob: pathlib.Path | None
    grids: tuple
    raw: dict

    def grid_filename(self, label):
        """npz name for one grid; the thievul configs reproduce the
        shipped names exactly (thievul_iwpr_bait__vs__lickilicky.npz)."""
        return f'{self.focal_slug}_{label}__vs__{self.opp_slug}.npz'

    def section(self, name):
        """A step-specific TOML table ({} when absent)."""
        return self.raw.get(name, {})


def load_pair(path):
    path = pathlib.Path(path).resolve()
    with open(path, 'rb') as f:
        raw = tomllib.load(f)

    unknown_sections = set(raw) - _KNOWN_SECTIONS
    if unknown_sections:
        raise ValueError(f'{path}: unknown top-level sections '
                         f'{sorted(unknown_sections)}')
    pair = raw.get('pair')
    if not isinstance(pair, dict):
        raise ValueError(f'{path}: missing [pair] table')
    missing = _PAIR_REQUIRED - set(pair)
    if missing:
        raise ValueError(f'{path}: [pair] missing keys {sorted(missing)}')
    unknown = set(pair) - _PAIR_REQUIRED - _PAIR_OPTIONAL
    if unknown:
        raise ValueError(f'{path}: [pair] unknown keys {sorted(unknown)}')

    grids_raw = raw.get('grids')
    if not grids_raw:
        raise ValueError(f'{path}: at least one [[grids]] entry required')
    grids = []
    for i, g in enumerate(grids_raw):
        missing = _GRID_REQUIRED - set(g)
        unknown = set(g) - _GRID_REQUIRED
        if missing or unknown:
            raise ValueError(f'{path}: [[grids]] #{i} missing '
                             f'{sorted(missing)} unknown {sorted(unknown)}')
        grids.append(GridSpec(label=g['label'], focal_fast=g['focal_fast'],
                              focal_charged=tuple(g['focal_charged']),
                              bait=bool(g['bait'])))
    labels = [g.label for g in grids]
    if len(set(labels)) != len(labels):
        raise ValueError(f'{path}: duplicate grid labels {labels}')

    blob = pair.get('replay_blob')
    return PairConfig(
        path=path,
        league=pair['league'],
        focal=pair['focal'],
        focal_shadow=bool(pair['focal_shadow']),
        focal_slug=pair['focal_slug'],
        opponent=pair['opponent'],
        opp_shadow=bool(pair['opponent_shadow']),
        opp_slug=pair['opponent_slug'],
        opp_fast=pair['opponent_fast'],
        opp_charged=tuple(pair['opponent_charged']),
        data_dir=REPO / pair['data_dir'],
        injected_moves=tuple(pair['injected_moves']),
        replay_blob=(REPO / blob) if blob else None,
        grids=tuple(grids),
        raw=raw,
    )


def preflight_moveset_legality(cfg):
    """Abort unless every configured move id is either in the species'
    pinned-gamemaster pool or explicitly declared in injected_moves (and
    every injected id exists in the global moves db and is actually
    used). Mirrors worlds_bake.preflight_moveset_legality: a typo'd move
    id in an automated pair run must fail loudly, never sim garbage; a
    DEAD injection (declared but unused) is an error too, so stale
    injections get retired with the CD lag."""
    from gopvpsim.data import load_gamemaster
    from gopvpsim.moves import get_moves

    fast_db, charged_db = get_moves()
    gm = load_gamemaster()
    by_name = {e['speciesName']: e for e in gm['pokemon']}

    for mid in cfg.injected_moves:
        if mid not in fast_db and mid not in charged_db:
            raise SystemExit(f'ABORT: injected move {mid} not in the '
                             'gamemaster moves db at all')

    def pool(species):
        e = by_name[species]
        return set(e.get('fastMoves') or []) | \
            set(e.get('chargedMoves') or []) | set(e.get('eliteMoves') or [])

    focal_pool = pool(cfg.focal) | set(cfg.injected_moves)
    used_focal = set()
    for g in cfg.grids:
        used_focal.add(g.focal_fast)
        used_focal.update(g.focal_charged)
    illegal = used_focal - focal_pool
    if illegal:
        raise SystemExit(
            f'ABORT: focal {cfg.focal} moves {sorted(illegal)} are neither '
            f'in the pinned gamemaster pool nor declared injected_moves')
    dead = set(cfg.injected_moves) - used_focal
    if dead:
        raise SystemExit(f'ABORT: injected_moves {sorted(dead)} declared '
                         'but not used by any grid (dead injection)')

    opp_used = {cfg.opp_fast} | set(cfg.opp_charged)
    opp_illegal = opp_used - pool(cfg.opponent)
    if opp_illegal:
        raise SystemExit(f'ABORT: opponent {cfg.opponent} moves '
                         f'{sorted(opp_illegal)} not in the pinned '
                         'gamemaster pool (opponent-side injection is not '
                         'supported)')


def default_publish_slug(cfg):
    """The website filename a pair's page publishes under (the [page]
    publish_slug override wins; shadow carries into the name)."""
    page = cfg.raw.get('page', {})
    return page.get('publish_slug') or (
        f'{cfg.focal.lower()}{"-shadow" if cfg.focal_shadow else ""}'
        f'-{cfg.opponent.lower()}'
        f'{"-shadow" if cfg.opp_shadow else ""}-robustness.html')
