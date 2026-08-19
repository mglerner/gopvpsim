#!/usr/bin/env python
"""Anti-focal (opponent-axis) denial blob for one joint-IV pair.

Config-driven generalization of scripts/thievul_licki_denial.py (S1 of
docs/joint_iv_reuse_plan.md): the focal/opponent identity, the data dir,
the breakpoints slot keys, the closed-form move pair, the named opponent
spreads and the cross-check input all come from a pairs/*.toml file (see
scripts/joint_iv_config.py for the [pair]/[[grids]] schema and the
optional [denial] table below).

Reads the SAME baked grids the rest of the page uses and recomputes every
number from them, then CROSS-CHECKS the recomputation against a research
run's saved marginals when the pair config names one ([denial]
research_npz). Exact agreement is required: a mismatch aborts rather than
shipping a number nobody can reproduce. With no research npz configured
the blob says so (``agrees: null``) rather than claiming agreement.

Denial = the number of focal spreads a given opponent spread BEATS OR
TIES, i.e. ``~won`` -- the grids record "did the focal win" with score >
500 strict, so a tie counts for the opponent. That convention is
quantified in the output.

Three focal populations, because "how many focal spreads does this deny"
has a different answer depending on which ones you expect to meet:
  all<N>   every spread
  top512   the top 512 by stat product (what people actually build)
  bp<n>    the spreads clearing the breakpoint move's breakpoint

Optional [denial] table -- every key has a derived default; the Thievul
configs pin the frozen historical names so the shipped artifacts rebuild
byte-identically:

    [denial]
    out_name = "denial.json"           # artifact basename
    research_npz = "userdata/.../marginals.npz"     # repo-relative
    research_stat_keys = { opp_atk = "...", opp_def = "...",
                           focal_atk = "...", focal_def = "..." }
    generated_from = "scripts/joint_iv_denial.py"   # provenance string
    focal_bp_move = "SUCKER_PUNCH"     # default: primary grid's fast move
    opp_pressure_move = "ROLLOUT"      # default: [pair] opponent_fast
    named_spreads = [{ ivs = [0, 15, 10], note = "rank-1 by stat product" }]

The breakpoints.json slot keys come from [breakpoints] focal_key /
opp_short (same resolution the assemble step uses), and the wall-table
cell is picked on the primary moveset arm ([assemble] primary_grid).

Output: ``<data-dir>/<out_name>``, embedded by the page builder.

Usage: python scripts/joint_iv_denial.py pairs/<pair>.toml
           [--data-dir DIR] [--out PATH]
"""
import argparse
import json
import pathlib
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'src'))

from joint_iv_config import load_pair  # noqa: E402
import worlds_planes as wp  # noqa: E402

from gopvpsim import moves as M  # noqa: E402
from gopvpsim.data import load_gamemaster  # noqa: E402
from gopvpsim.pokemon import CPM, get_pokemon_index  # noqa: E402

SCEN = [f'{sf}-{so}' for sf in range(3) for so in range(3)]
TOP = 512          # the "what people actually build" cohort size
WALL_SCEN = '1-1'  # the shield scenario the wall table is read off


def r(x, n=4):
    return round(float(x), n)


def pretty_move(move_id):
    """Display name for a move id (mirrors build_joint_iv_page's
    _pretty_move, so the page and this blob spell moves the same way)."""
    return ' '.join(w.capitalize() for w in str(move_id).split('_'))


def arm_of(label):
    """Moveset arm slug for a grid label (label minus the bait suffix)."""
    for suffix in ('_bait', '_nobait'):
        if label.endswith(suffix):
            return label[:-len(suffix)]
    return label


def stats_from(entry, ivs, levels):
    cpm = np.array([CPM[float(v)] for v in levels])
    atk = (entry['atk'] + ivs[:, 0]) * cpm
    dfn = (entry['def'] + ivs[:, 1]) * cpm
    hp = np.floor((entry['hp'] + ivs[:, 2]) * cpm).astype(int)
    return atk, dfn, hp


def distinct_grids(data, manifest):
    """Grid labels, with byte-identical duplicates collapsed to the first."""
    seen, out = {}, []
    for label, g in sorted(manifest['grids'].items()):
        p = data / g['file']
        h = hash(p.read_bytes()) if p.exists() else None
        if h is not None and h in seen:
            continue
        seen[h] = label
        out.append(label)
    return out


def verify_constants(focal_move, opp_move, t_types, o_types,
                     t_atk, t_def, o_atk, o_def):
    """Derive the two closed-form constants from the damage function.

    K is defined by dmg = floor(K * atk / def) + 1, so K = 2 * (the damage
    at atk == def == 1 ... ) is not directly readable; instead we recover K
    from the engine by evaluating damage() on a grid and solving. The
    sample points are drawn from the pair's ACTUAL stat ranges (min /
    median / max), so the floor-boundary check stays relevant for every
    pair instead of only the one the constants were first written for.
    """
    fast_moves, charged_moves = M.get_moves()

    def samples(arr):
        return (float(arr.min()), float(np.median(arr)), float(arr.max()))

    def k_of(move_id, attacker_types, defender_types, atk_arr, def_arr):
        mv = fast_moves.get(move_id) or charged_moves[move_id]
        power = mv['power']
        # dmg = floor(K*atk/def)+1 with K = 0.5*BONUS*power*eff*stab
        eff = M.type_effectiveness(mv['type'], defender_types)
        st = M.stab(mv['type'], attacker_types)
        k = 0.5 * M.BONUS * power * eff * st
        # confirm against the engine itself on a sample
        for atk in samples(atk_arr):
            for dfn in samples(def_arr):
                want = int(np.floor(k * atk / dfn)) + 1
                got = M.damage(power, atk, dfn, mv['type'],
                               attacker_types, defender_types)
                if want != got:
                    raise SystemExit(
                        f'ABORT: closed form disagrees with moves.damage for '
                        f'{move_id} at atk={atk} def={dfn}: {want} != {got}')
        return k

    return {
        focal_move.lower(): k_of(focal_move, t_types, o_types, t_atk, o_def),
        opp_move.lower(): k_of(opp_move, o_types, t_types, o_atk, t_def),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('pair', help='pairs/<pair>.toml config path')
    ap.add_argument('--data-dir', default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args(argv)
    cfg = load_pair(args.pair)
    den_cfg = cfg.section('denial')

    data = pathlib.Path(args.data_dir) if args.data_dir else cfg.data_dir
    out_name = den_cfg.get('out_name', 'denial.json')
    out_path = pathlib.Path(args.out) if args.out else (data / out_name)

    FOCAL, OPPONENT = cfg.focal, cfg.opponent

    # The primary moveset arm decides which grid the wall table describes;
    # the assemble step owns the choice, this step follows it.
    primary_grid = cfg.section('assemble').get('primary_grid',
                                               cfg.grids[0].label)
    primary_arm = arm_of(primary_grid)
    by_label = {g.label: g for g in cfg.grids}
    if primary_grid not in by_label:
        raise SystemExit(f'ABORT: [assemble] primary_grid {primary_grid!r} is '
                         f'not a configured grid label')
    sp_move = den_cfg.get('focal_bp_move', by_label[primary_grid].focal_fast)
    roll_move = den_cfg.get('opp_pressure_move', cfg.opp_fast)
    sp_key, roll_key = sp_move.lower(), roll_move.lower()
    sp_name, roll_name = pretty_move(sp_move), pretty_move(roll_move)

    manifest = json.loads((data / 'manifest.json').read_text())
    bp = json.loads((data / 'breakpoints.json').read_text())
    # breakpoints.json spells the focal offense block and the opponent half
    # of its key names per-pair; both are FROZEN SLOT names there (see its
    # meta.schema_note), so they are resolved from the config, never read
    # back out of the file's keys.
    bp_cfg = cfg.section('breakpoints')
    focal_key = bp_cfg.get('focal_key', f'{cfg.focal_slug}_offense')
    opp_short = bp_cfg.get('opp_short', cfg.opp_slug)
    # [breakpoints] focal_key is spelled BOTH ways across the kit -- the
    # assemble step reads it as the whole block name ('<slug>_offense'),
    # the breakpoints step as the bare slug it suffixes. Accept either
    # rather than making the pair config's spelling decide which steps run.
    if focal_key not in bp and f'{focal_key}_offense' in bp:
        focal_key = f'{focal_key}_offense'
    if focal_key not in bp:
        raise SystemExit(
            f'ABORT: breakpoints.json has no {focal_key!r} block (has '
            f'{sorted(k for k in bp if k.endswith("_offense"))}); set '
            f'[breakpoints] focal_key in {cfg.path.name}')
    if sp_move not in bp[focal_key]['moves']:
        raise SystemExit(
            f'ABORT: breakpoints.json {focal_key} has no {sp_move} block; '
            f'set [denial] focal_bp_move in {cfg.path.name}')
    sp = bp[focal_key]['moves'][sp_move]
    tier_key = f'tier_vs_rank1_{opp_short}_by_spread'
    bp_key = f'breakpoint_vs_rank1_{opp_short}'
    if tier_key not in sp or bp_key not in sp:
        raise SystemExit(
            f'ABORT: breakpoints.json {focal_key}.moves.{sp_move} has no '
            f'{tier_key!r}/{bp_key!r}; set [breakpoints] opp_short in '
            f'{cfg.path.name}')
    sp_tier = np.asarray(sp[tier_key])
    hi_tier = sp[bp_key]['hi_tier']
    bp_mask = sp_tier >= hi_tier

    grids = distinct_grids(data, manifest)
    print(f'distinct grids: {grids}')

    idx = get_pokemon_index()
    t_entry, o_entry = idx[FOCAL], idx[OPPONENT]
    # Types come from the gamemaster entry, not the stat index.
    gm = load_gamemaster()
    by_name = {e['speciesName']: e for e in gm['pokemon']}

    def types_of(name):
        return [x for x in (by_name[name].get('types') or [])
                if x and x != 'none']

    t_types, o_types = types_of(FOCAL), types_of(OPPONENT)
    print(f'{FOCAL} types {t_types} | {OPPONENT} types {o_types}')

    z0 = np.load(data / manifest['grids'][grids[0]]['file'])
    o_ivs, o_lv = np.asarray(z0['opp_ivs']), np.asarray(z0['opp_levels'])
    t_ivs, t_lv = np.asarray(z0['focal_ivs']), np.asarray(z0['focal_levels'])
    o_atk, o_def, o_hp = stats_from(o_entry, o_ivs, o_lv)
    t_atk, t_def, t_hp = stats_from(t_entry, t_ivs, t_lv)

    N = int(t_ivs.shape[0])
    if sp_tier.shape[0] != N:
        raise SystemExit(f'ABORT: the breakpoints tier array is '
                         f'{sp_tier.shape[0]} long but the grids carry '
                         f'{N} focal spreads')
    # Population keys carry their own size, so a blob can never claim a
    # cohort it does not have.
    ALL_P, TOP_P = f'all{N}', f'top{TOP}'
    BP_P = f'bp{int(bp_mask.sum())}'
    POPS = [ALL_P, TOP_P, BP_P]
    if N < TOP or len(set(POPS)) != len(POPS):
        raise SystemExit(f'ABORT: degenerate population set {POPS} at N={N} '
                         f'-- the three cohorts must be distinct keys')

    pops = {
        ALL_P: np.ones(N, bool),
        TOP_P: np.concatenate([np.ones(TOP, bool), np.zeros(N - TOP, bool)]),
        BP_P: bp_mask,
    }
    pop_n = {p: int(m.sum()) for p, m in pops.items()}

    # ---- denial marginals, recomputed from the grids ----
    den, ties = {}, {}
    for g in grids:
        z = np.load(data / manifest['grids'][g]['file'])
        won = wp.unpack_won(z['won_packed'], tuple(z['won_shape']))
        score = np.asarray(z['score'])
        ties[g] = {
            'cells': int((score == 500).sum()),
            'frac_of_cells': r((score == 500).sum() / score.size, 8),
            'by_scenario': {SCEN[si]: int((score[:, :, si] == 500).sum())
                            for si in range(9)},
            'vs_bp_clearing': int((score[bp_mask] == 500).sum()),
        }
        den[g] = {}
        for p, mask in pops.items():
            wins = np.zeros((N, 9), np.int64)
            for i in range(0, N, 512):
                sub = mask[i:i + 512]
                if sub.any():
                    wins += won[i:i + 512][sub].sum(axis=0, dtype=np.int64)
            den[g][p] = (pop_n[p] - wins).astype(np.int32)
        del won, score, z

    # ---- CROSS-CHECK against the research run (exact) ----
    research = den_cfg.get('research_npz')
    research = (REPO / research) if research else None
    if research is not None:
        try:
            research_label = str(research.relative_to(REPO))
        except ValueError:
            research_label = str(research)
    else:
        research_label = None
    stat_key_cfg = den_cfg.get('research_stat_keys', {})
    stat_keys = [
        (stat_key_cfg.get('opp_atk', f'{cfg.opp_slug}_atk'), o_atk),
        (stat_key_cfg.get('opp_def', f'{cfg.opp_slug}_def'), o_def),
        (stat_key_cfg.get('focal_atk', f'{cfg.focal_slug}_atk'), t_atk),
        (stat_key_cfg.get('focal_def', f'{cfg.focal_slug}_def'), t_def),
    ]
    xcheck = {'file': research_label, 'compared': 0, 'mismatches': []}
    if research is not None and research.exists():
        R = np.load(research, allow_pickle=True)
        for g in grids:
            for p in POPS:
                key = f'denial__{g}__{p}'
                if key not in R:
                    xcheck['mismatches'].append(f'{key}: absent upstream')
                    continue
                same = np.array_equal(np.asarray(R[key], dtype=np.int64),
                                      den[g][p].astype(np.int64))
                xcheck['compared'] += 1
                if not same:
                    d = np.asarray(R[key]) - den[g][p]
                    xcheck['mismatches'].append(
                        f'{key}: {int((d != 0).sum())} cell(s) differ, '
                        f'max |delta| {int(np.abs(d).max())}')
        for name, mine in stat_keys:
            if name in R and not np.allclose(np.asarray(R[name]), mine):
                xcheck['mismatches'].append(f'{name}: stat array differs')
                xcheck['compared'] += 1
            elif name in R:
                xcheck['compared'] += 1
        if xcheck['mismatches']:
            raise SystemExit(
                'ABORT: recomputed denial does not match the research run:\n  '
                + '\n  '.join(xcheck['mismatches']))
        xcheck['agrees'] = True
        print(f"cross-check vs research npz: {xcheck['compared']} array(s), "
              f'exact agreement')
    else:
        xcheck['agrees'] = None
        xcheck['note'] = 'research npz not present; nothing to compare against'

    # ---- IV-sensitive cells (computed, not listed) ----
    # A cell counts as IV-sensitive when the denial range spans at least
    # MATERIAL_FRAC of the population. Without a threshold, cells whose
    # range is 2-14 spreads out of 4096 (decided for every practical
    # purpose) dilute the composite; with it, the set is stated and
    # reproducible rather than hand-picked.
    MATERIAL_FRAC = 0.01
    cells, marginal = [], []
    for g in grids:
        for si, sc in enumerate(SCEN):
            d_all = den[g][ALL_P][:, si]
            span = int(d_all.max()) - int(d_all.min())
            if span == 0:
                continue
            if span < MATERIAL_FRAC * pop_n[ALL_P]:
                marginal.append({
                    'grid': g, 'scenario': sc, 'span': span,
                    'span_pct_of_pop': r(100.0 * span / pop_n[ALL_P], 3),
                })
                continue
            row = {'grid': g, 'scenario': sc}
            for p in POPS:
                d = den[g][p][:, si]
                row[p] = {
                    'min': int(d.min()), 'max': int(d.max()),
                    'mean': r(d.mean(), 2), 'pop_n': pop_n[p],
                    'n_zero': int((d == 0).sum()),
                    'n_full': int((d == pop_n[p]).sum()),
                }
            sd = den[g][ALL_P][:, si].astype(float)
            row['drivers'] = {
                'corr_def': r(np.corrcoef(sd, o_def)[0, 1], 3),
                'corr_atk': r(np.corrcoef(sd, o_atk)[0, 1], 3),
                'corr_hp': r(np.corrcoef(sd, o_hp)[0, 1], 3),
            }
            cells.append(row)
    sens = [(c['grid'], c['scenario']) for c in cells]
    print(f'{len(cells)} IV-sensitive cell(s); {len(marginal)} varying but '
          f'below the {MATERIAL_FRAC:.0%} materiality threshold')

    # ---- closed forms, constants verified against moves.damage ----
    K = verify_constants(sp_move, roll_move, t_types, o_types,
                         t_atk, t_def, o_atk, o_def)
    k_sp, k_roll = K[sp_key], K[roll_key]
    base_tier = hi_tier - 1
    # dmg = floor(K*atk/def) + 1, so reaching hi_tier needs
    # floor(K*atk/def) >= hi_tier - 1, i.e. def <= K*atk/(hi_tier-1).
    # "Walled" (held to base_tier) is therefore def > K*atk/base_tier --
    # dividing by hi_tier instead is an off-by-one that makes the wall look
    # far easier than it is.
    wall_factor = k_sp / base_tier
    roll_hi = int(np.floor(k_roll * o_atk.max() / t_def.min()) + 1)
    roll_lo = int(np.floor(k_roll * o_atk.min() / t_def.max()) + 1)
    roll_factor = (roll_hi - 1) / k_roll  # atk >= factor * def for the top tier

    wall_def = float(o_def.max())
    n_walled = int((o_def.max() > wall_factor * t_atk).sum())
    # CROSS-CHECK the closed form against the grid: the spreads sitting on
    # the best defense step must wall exactly the focal spreads that do NOT
    # clear the breakpoint (the empirical denial in the wall cell).
    # The breakpoint population is defined against the RANK-1 opponent, so
    # that is the defense the closed form must be checked at.
    n_sub_bp = int((~bp_mask).sum())
    rank1_def = float(o_def[0])
    n_by_closed_form = int((rank1_def > wall_factor * t_atk).sum())
    best_step = float(o_def.max())
    n_at_best_step = int((best_step > wall_factor * t_atk).sum())
    closed = {
        sp_key: {
            'K': r(k_sp), 'hi_tier': int(hi_tier), 'base_tier': int(base_tier),
            'identity': (f'{FOCAL} {sp_name} damage = '
                         f'floor(K * {FOCAL.lower()}_atk / '
                         f'{OPPONENT.lower()}_def) + 1'),
            'wall_condition': (f'{OPPONENT.lower()}_def > {r(wall_factor, 4)} '
                               f'x {FOCAL.lower()}_atk holds {sp_name} to '
                               f'{base_tier} instead of {hi_tier}'),
            'wall_factor': r(wall_factor, 6),
            'max_opponent_def': r(wall_def, 3),
            'focal_atk_range': [r(t_atk.min(), 3), r(t_atk.max(), 3)],
            'n_focal_walled_by_max_def': n_walled,
            'frac_focal_walled_by_max_def': r(n_walled / N, 4),
            'walls_median_focal': bool(wall_def > wall_factor
                                       * float(np.median(t_atk))),
            'rank1_opponent_def': r(rank1_def, 3),
            'n_focal_walled_by_rank1_def': n_by_closed_form,
            'n_focal_below_breakpoint': n_sub_bp,
            'closed_form_matches_breakpoint_set': bool(
                n_by_closed_form == n_sub_bp),
            'max_def_walls_n_focal': n_at_best_step,
            'max_def_walls_frac': r(n_at_best_step / N, 4),
        },
        roll_key: {
            'K': r(k_roll), 'tiers': [roll_lo, roll_hi],
            'identity': (f'{OPPONENT} {roll_name} damage = floor(K * '
                         f'{OPPONENT.lower()}_atk / {FOCAL.lower()}_def) + 1'),
            'top_tier_condition': (f'{OPPONENT.lower()}_atk >= '
                                   f'{r(roll_factor, 5)} x '
                                   f'{FOCAL.lower()}_def lands '
                                   f'{roll_hi} instead of {roll_lo}'),
            'factor': r(roll_factor, 6),
            'opponent_atk_range': [r(o_atk.min(), 3), r(o_atk.max(), 3)],
        },
    }

    if n_by_closed_form != n_sub_bp:
        raise SystemExit(
            f'ABORT: the wall closed form says the rank-1 {OPPONENT} '
            f'defense walls {n_by_closed_form} {FOCAL} spreads, but '
            f'{n_sub_bp} spreads sit below the {sp_name} breakpoint. '
            f'Those must be the same set.')

    # defense-step (wall) table: the distinct defense values that matter,
    # with the denial they actually buy in the wall cell
    wall_cell = None
    for g, sc in sens:
        if arm_of(g) == primary_arm and sc == WALL_SCEN:
            wall_cell = (g, sc)
            break
    wall_rows = []
    if wall_cell:
        g, sc = wall_cell
        si = SCEN.index(sc)
        d = {p: den[g][p][:, si] for p in POPS}
        best = int(d[ALL_P].max())
        at_best = np.flatnonzero(d[ALL_P] == best)
        for i in at_best[:12]:
            wall_rows.append({
                'rank': int(i) + 1,
                'ivs': [int(x) for x in o_ivs[i]],
                'level': float(o_lv[i]),
                'cp': int(_cp(o_entry, o_ivs[i], o_lv[i])),
                'def': r(o_def[i], 3), 'atk': r(o_atk[i], 3),
                'hp': int(o_hp[i]),
                'denies': {p: int(d[p][i]) for p in POPS},
            })
    else:
        # Honest absence, not a silent empty section: the page renders
        # wall_table.cell = null visibly, and this says why on the console.
        print(f'WARNING: no IV-sensitive {primary_arm}* cell at {WALL_SCEN}; '
              f'the wall table ships empty')
    rollout_rows = []
    for label, dfn in (('the rank-1 ' + FOCAL, float(t_def[0])),
                       ('the median ' + FOCAL, float(np.median(t_def))),
                       ('every ' + FOCAL + ' spread', float(t_def.max()))):
        need = roll_factor * dfn
        rollout_rows.append({
            'target': label, 'focal_def': r(dfn, 3),
            'opponent_atk_needed': r(need, 3),
            'n_opponent_qualifying': int((o_atk >= need).sum()),
        })

    # ---- ranked builds: composite over the sensitive cells ----
    frac = {p: np.zeros(N) for p in POPS}
    for p in POPS:
        for g, sc in sens:
            frac[p] += den[g][p][:, SCEN.index(sc)] / pop_n[p]
        frac[p] /= len(sens)
    comp = sum(frac[p] for p in POPS) / len(POPS)
    order = np.argsort(-comp, kind='stable')
    sp_rank_pct = (o_atk * o_def * o_hp) / float((o_atk * o_def * o_hp).max())

    def build_row(i, note=''):
        return {
            'rank': int(i) + 1,
            'ivs': [int(x) for x in o_ivs[i]],
            'level': float(o_lv[i]), 'cp': int(_cp(o_entry, o_ivs[i], o_lv[i])),
            'atk': r(o_atk[i], 3), 'def': r(o_def[i], 3), 'hp': int(o_hp[i]),
            'stat_product_pct': r(100 * sp_rank_pct[i], 1),
            'composite': r(comp[i], 4),
            'per_cell': {f'{g}|{sc}': {
                p: r(100.0 * den[g][p][i, SCEN.index(sc)] / pop_n[p], 1)
                for p in POPS} for g, sc in sens},
            'note': note,
        }

    ranked = [build_row(int(i)) for i in order[:25]]

    # Robustness of the ranking to the cell-set choice: recompute the
    # composite over EVERY varying cell (threshold dropped) and report
    # whether the top build survives. The research report used a
    # hand-picked 9-cell set; this says out loud whether that choice
    # matters.
    all_cells = sens + [(m['grid'], m['scenario']) for m in marginal]
    frac2 = {p: np.zeros(N) for p in POPS}
    for p in POPS:
        for g, sc in all_cells:
            frac2[p] += den[g][p][:, SCEN.index(sc)] / pop_n[p]
        frac2[p] /= len(all_cells)
    comp2 = sum(frac2[p] for p in POPS) / len(POPS)
    top2 = int(np.argmax(comp2))
    robustness = {
        'threshold_cells': len(sens),
        'all_varying_cells': len(all_cells),
        'top_build_thresholded': [int(x) for x in o_ivs[int(order[0])]],
        'top_build_all_varying': [int(x) for x in o_ivs[top2]],
        'same_top_build': bool(top2 == int(order[0])),
    }
    named_rows = []
    for spec in den_cfg.get('named_spreads', []):
        ivs, note = spec['ivs'], spec['note']
        hit = np.flatnonzero((o_ivs[:, 0] == ivs[0]) & (o_ivs[:, 1] == ivs[1])
                             & (o_ivs[:, 2] == ivs[2]))
        if hit.size:
            row = build_row(int(hit[0]), note)
            row['composite_rank'] = int(
                np.flatnonzero(order == hit[0])[0]) + 1
            named_rows.append(row)
        else:
            print(f'WARNING: [denial] named_spreads {ivs} matches no '
                  f'{OPPONENT} spread; dropped')
    named_rows.sort(key=lambda x: x['composite_rank'])

    blob = {
        'meta': {
            'focal': FOCAL, 'opponent': OPPONENT,
            'definition': ('Denial = the number of ' + FOCAL + ' spreads a '
                           + OPPONENT + ' spread BEATS OR TIES. The grids '
                           'record "did ' + FOCAL + ' win" with score > 500 '
                           'strict, so a tie counts for ' + OPPONENT + '.'),
            'populations': {p: pop_n[p] for p in POPS},
            'population_notes': {
                ALL_P: 'every ' + FOCAL + ' IV spread',
                TOP_P: (f'the top {TOP} by stat product (what people build)'),
                BP_P: (f'the spreads clearing the {sp_name} '
                       'breakpoint vs the rank-1 ' + OPPONENT),
            },
            'grids': grids,
            'scenarios': SCEN,
            'cross_check': xcheck,
            'generated_from': den_cfg.get(
                'generated_from',
                str(pathlib.Path(__file__).resolve().relative_to(REPO))),
        },
        'sensitive_cells': cells,
        'marginal_cells': marginal,
        'materiality_threshold_pct': r(100 * MATERIAL_FRAC, 2),
        'ranking_robustness': robustness,
        'closed_form': closed,
        'wall_table': {'cell': (f'{wall_cell[0]}|{wall_cell[1]}'
                                if wall_cell else None),
                       'rows': wall_rows},
        f'{roll_key}_ladder': rollout_rows,
        'ranked_builds': ranked,
        'named_builds': named_rows,
        'composite_rule': {
            'cells': [f'{g}|{sc}' for g, sc in sens],
            'formula': ('mean over the IV-sensitive cells of '
                        'denial / population size, then averaged over the '
                        'three ' + FOCAL + ' populations'),
            'caveat': ('a MODELING CHOICE: equal weight per cell and per '
                       'population, not a meta-weighted score'),
            'cell_selection': (f'cells whose denial range spans at least '
                               f'{100 * MATERIAL_FRAC:.0f}% of the '
                               f'population; cells that vary by less are '
                               f'listed separately and excluded'),
        },
        'ties': ties,
        'caveats': [
            'Denial counts ties for ' + OPPONENT + ' (see the definition); '
            'the tie load is quantified per grid above.',
            'There is NO ' + OPPONENT + '-vs-meta grid in this analysis: '
            'the cost of a denial build is proxied by stat-product rank '
            'only. A build that denies ' + FOCAL + ' well may be materially '
            'worse against the rest of the meta. This ranks anti-' + FOCAL
            + ' value, not overall ' + OPPONENT + ' quality.',
        ],
    }
    out_path.write_text(json.dumps(blob, indent=1))
    print(f'wrote {out_path} '
          f'({len(ranked)} ranked, {len(named_rows)} named, '
          f'{len(cells)} sensitive cells)')
    return 0


def _cp(entry, ivs, level):
    cpm = CPM[float(level)]
    a = (entry['atk'] + int(ivs[0])) * cpm
    d = (entry['def'] + int(ivs[1])) * cpm
    s = (entry['hp'] + int(ivs[2])) * cpm
    return max(10, int((a * (d ** 0.5) * (s ** 0.5)) / 10))


if __name__ == '__main__':
    sys.exit(main())
