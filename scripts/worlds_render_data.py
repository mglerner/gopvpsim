#!/usr/bin/env python
"""Worlds 2026 renderer data layer: planes -> matrix / cheat-sheet rows.

Plan: docs/worlds_prep_plan.md (products 2 + 3). This module is a
READ-ONLY consumer of ``worlds/planes/`` -- it is deliberately OUTSIDE
``worlds_planes._WORLDS_SOURCE_FILES`` (a renderer edit must not cold a
Tier-1 plane bake; same boundary as worlds_tier0.py).

Vocabulary (docs/concepts.md + the plan):

* A CELL is one ordered (focal, opponent) direction of a pair. Per
  cell the planes hold won/score over (2 focal probe spreads x cohort
  x 9 shield scenarios) x 2 bait modes.
* ``frac`` is the fraction of the opponent's cohort spreads the focal
  probe spread beats, per scenario -- the plan's "fraction of the
  opponent's plausible IV spreads beaten, per shield scenario (never
  aggregated to one number)".
* Classification is STRICT: GREEN iff frac == 1.0, RED iff frac == 0.0,
  AMBER otherwise (IV-decided). No epsilon: a 511/512 cell IS
  IV-decided -- that single losing spread is exactly what a breakpoint
  chaser plays for, and the session-1 go/no-go probe counted amber the
  same way.
* A cell's ``amber`` flag is True if ANY (probe spread, cohort,
  scenario, bait) slice is amber -- the matrix links such pairs to the
  session-4 detail pages.

The headline slice shown in matrix cells and cheat-sheet rows is
(rank-1-SP probe spread, top-512-SP cohort, bait on) -- PvPoke-default
conventions -- with the other slices carried alongside, labeled, never
silently pooled (cohorts overlap: a top-512 row can also be in the
atk-band cohort; pooling would double-count it).
"""
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

import worlds_planes as wp

SPREAD_TAGS = ('rank1', 'maxatk512')   # focal probe spreads, plane axis 0
COHORTS = ('top512', 'atkband')        # mask names, plane axis 1 selectors
HEADLINE = {'spread': 'rank1', 'cohort': 'top512', 'bait': True}


def load_meta(path=wp.META_TOML):
    with open(path, 'rb') as f:
        return tomllib.load(f)


@dataclass
class CellSlice:
    """One (spread, cohort, bait) slice of a cell: per-scenario stats."""
    frac: np.ndarray          # (9,) fraction of cohort beaten per scenario
    wins: np.ndarray          # (9,) count of cohort spreads beaten (exact --
                              # renderers print "beats N of n", never a
                              # rounded % that can collapse 511/512 to 100%)
    n: int                    # cohort size
    margin_lo: np.ndarray     # (9,) min signed margin over cohort
    margin_hi: np.ndarray     # (9,) max signed margin over cohort

    @property
    def status(self):
        """Per-scenario 'green'/'amber'/'red' (strict)."""
        return ['green' if f == 1.0 else 'red' if f == 0.0 else 'amber'
                for f in self.frac]


@dataclass
class Cell:
    """One ordered (focal, opponent) direction, all slices."""
    focal_id: str
    opp_id: str
    scenarios: list = field(default_factory=list)   # [(sf, so)] * 9
    slices: dict = field(default_factory=dict)      # (spread, cohort, bait) ->
                                                    # CellSlice
    missing: bool = False
    # Scenario indices proven IV-decided by a FULL Tier-2 grid (any
    # non-constant scenario over all 4096 focal spreads x the opponent
    # cohort) on a pair the two-probe Tier-1 screen called clean -- the
    # 2026-08-19 FN audit's ground truth. Filled by _apply_grid_amber.
    grid_scenarios: list = field(default_factory=list)

    @property
    def headline(self):
        return self.slices.get(
            (HEADLINE['spread'], HEADLINE['cohort'], HEADLINE['bait']))

    @property
    def amber(self):
        """IV-decided anywhere: any slice with a within-cohort mix, OR a
        focal-axis flip (see spread_flip_scenarios -- the two probe
        spreads landing on OPPOSITE uniform outcomes is IV-decided even
        though each slice alone looks settled; gap found designing the
        Tier-2 screen, 2026-08-10)."""
        return (any('amber' in s.status for s in self.slices.values())
                or bool(self.spread_flip_scenarios())
                or bool(self.grid_scenarios))

    def spread_flip_scenarios(self):
        """Scenario indices where, for some (cohort, bait), the rank1
        and maxatk512 probe spreads land on OPPOSITE uniform outcomes
        (one beats the whole cohort, the other beats none) -- pure
        focal-IV decidedness that the within-cohort amber test cannot
        see. A mixed slice is already amber, so only the 0-vs-1 case is
        new information."""
        idx = set()
        for cohort in ('top512', 'atkband'):
            for bait in (True, False):
                a = self.slices.get(('rank1', cohort, bait))
                b = self.slices.get(('maxatk512', cohort, bait))
                if a is None or b is None:
                    continue
                for i in range(len(a.frac)):
                    fa, fb = float(a.frac[i]), float(b.frac[i])
                    if {fa, fb} == {0.0, 1.0}:
                        idx.add(i)
        return sorted(idx)

    def amber_scenarios(self):
        """Sorted scenario indices that are IV-decided in ANY slice (the
        cheat-sheet flag: WHERE the IVs decide) -- within-cohort mixes
        plus focal-axis spread flips."""
        idx = set()
        for s in self.slices.values():
            for i, st in enumerate(s.status):
                if st == 'amber':
                    idx.add(i)
        idx.update(self.spread_flip_scenarios())
        idx.update(self.grid_scenarios)
        return sorted(idx)

    def amber_origins(self):
        """{scenario index: sorted origin tags} for every flagged
        scenario -- WHICH corner of the tested IV space makes it
        IV-decided (Michael 2026-08-26, so a flag that disagrees with
        the displayed strip can explain itself). Tags:

          'headline'        mixed in a displayed rank1/top512 slice
                            (either bait mode -- the strip shows it)
          'atkband'         mixed vs the high-attack cohort (rank1 probe)
          'maxatk'          mixed under the max-attack probe (top512)
          'maxatk+atkband'  mixed only with both deviations at once
          'spread-flip'     the two probe spreads land on OPPOSITE
                            uniform outcomes (see spread_flip_scenarios)
          'grid'            full-grid Tier-2 evidence on a probe-clean
                            pair (see grid_scenarios)
        """
        out = {}
        for (spread, cohort, _bait), s in self.slices.items():
            for i, st in enumerate(s.status):
                if st != 'amber':
                    continue
                if spread == 'rank1' and cohort == 'top512':
                    tag = 'headline'
                elif spread == 'rank1':
                    tag = 'atkband'
                elif cohort == 'top512':
                    tag = 'maxatk'
                else:
                    tag = 'maxatk+atkband'
                out.setdefault(i, set()).add(tag)
        for i in self.spread_flip_scenarios():
            out.setdefault(i, set()).add('spread-flip')
        for i in self.grid_scenarios:
            out.setdefault(i, set()).add('grid')
        return {i: sorted(v) for i, v in out.items()}

    def probe_missed(self):
        """True when this direction is amber ONLY through full-grid
        evidence -- the probe screen alone called it settled."""
        return (bool(self.grid_scenarios)
                and not any('amber' in s.status
                            for s in self.slices.values())
                and not self.spread_flip_scenarios())


def _cell_from_plane(plane, focal_id, opp_id):
    won = plane['won']                     # (2, n, 9) bool
    marg = wp.margin(plane['score'])       # (2, n, 9) int32
    scen = [tuple(s) for s in plane['scenarios'].tolist()]
    masks = {'top512': plane['top512_mask'], 'atkband': plane['atkband_mask']}
    out = {}
    for si, stag in enumerate(SPREAD_TAGS):
        for ctag, mask in masks.items():
            n = int(mask.sum())
            if n == 0:
                continue
            w = won[si][mask]              # (n, 9)
            m = marg[si][mask]
            out[(stag, ctag)] = (w.mean(axis=0), w.sum(axis=0), n,
                                 m.min(axis=0), m.max(axis=0))
    return scen, out


def build_cell(focal_id, opp_id, planes_dir=wp.PLANES_DIR):
    """Assemble one Cell from its two bait-mode planes. A missing plane
    yields ``missing=True`` (rendered as such, never silently skipped --
    the never-present-known-wrong rule)."""
    cell = Cell(focal_id=focal_id, opp_id=opp_id)
    for bait in (True, False):
        plane = wp.read_plane(wp.plane_filename(focal_id, opp_id, bait),
                              planes_dir)
        if plane is None:
            cell.missing = True
            continue
        scen, slices = _cell_from_plane(plane, focal_id, opp_id)
        cell.scenarios = scen
        for (stag, ctag), (frac, wins, n, lo, hi) in slices.items():
            cell.slices[(stag, ctag, bait)] = CellSlice(
                frac=frac, wins=wins, n=n, margin_lo=lo, margin_hi=hi)
    return cell


def build_all_cells(entries, planes_dir=wp.PLANES_DIR):
    """{(focal_id, opp_id): Cell} for every ordered direction, with
    full-grid amber evidence folded in (_apply_grid_amber) so every
    consumer -- hub, cheat sheets, pair pages, worklists, verify --
    agrees on ONE amber set."""
    ids = [e['species_id'] for e in entries]
    cells = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            for focal, opp in ((a, b), (b, a)):
                cells[(focal, opp)] = build_cell(focal, opp, planes_dir)
    _apply_grid_amber(cells)
    return cells


def _apply_grid_amber(cells):
    """Fold FULL-grid IV-decidedness into cells the probe screen called
    clean. Only grids for non-Tier-1-amber pairs are read (the audit's
    73-pair set), so the pass costs ~seconds, not a 1,900-grid sweep. A
    scenario counts when its outcome is non-constant over ALL 4096
    focal spreads x the opponent cohort -- the widest honest reading,
    and the one that catches the max-attack breakpoint chasers the
    2026-08-19 probe expansion flagged."""
    import numpy as np
    import worlds_tier2 as t2
    manifest = t2.load_manifest()
    if manifest is None:
        return
    tier1_amber = {tuple(sorted(k)) for k, c in cells.items()
                   if not c.missing and c.amber}
    for key, ent in manifest.get('entries', {}).items():
        focal, opp, _bait = key.rsplit('|', 2)
        cell = cells.get((focal, opp))
        if cell is None or cell.missing:
            continue
        if tuple(sorted((focal, opp))) in tier1_amber:
            continue
        grid = t2.read_grid(ent['file'])
        if grid is None:
            continue
        won = grid['won']
        for si in range(won.shape[2]):
            sl = won[:, :, si]
            if sl.any() and not sl.all() and si not in cell.grid_scenarios:
                cell.grid_scenarios.append(si)
        cell.grid_scenarios.sort()


def matrix_summary(cells, entries):
    """Renderer-ready matrix: per ordered direction the headline
    per-scenario status plus the pair-level amber flag."""
    ids = [e['species_id'] for e in entries]
    rows = {}
    for f in ids:
        for o in ids:
            if f == o:
                continue
            cell = cells.get((f, o))
            if cell is None or cell.missing or cell.headline is None:
                rows[(f, o)] = {'missing': True}
                continue
            h = cell.headline
            rows[(f, o)] = {
                'missing': False,
                'frac': [float(x) for x in h.frac],
                'status': h.status,
                'amber': cell.amber,
                'amber_scenarios': cell.amber_scenarios(),
                'n': h.n,
            }
    return rows


def coverage_check(cells, entries):
    """(n_missing, missing_keys) -- the renderer refuses to ship a page
    that silently omits a pair (ML-completeness-style)."""
    missing = sorted(k for k, c in cells.items() if c.missing)
    return len(missing), missing
