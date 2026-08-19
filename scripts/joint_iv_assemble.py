#!/usr/bin/env python
"""Assemble reco.json for one joint-IV pair (kit step 4).

Config-driven generalization of scripts/thievul_licki_assemble.py (S1 of
docs/joint_iv_reuse_plan.md): the focal/opponent identity, the moveset
arms, the display labels, the breakpoint slot keys and every pair-
specific card and note come from a pairs/*.toml file (schema:
scripts/joint_iv_config.py, plus the [assemble] table documented below).
The Thievul configs reproduce the shipped reco.json byte-identically --
that regression is the S1 acceptance test.

Synthesis layer: joins the baked 4096x4096 win grids (the authority on
fight outcomes), the dive-derived meta win counts, and the closed-form
breakpoint layer into auto-computed recommendation cards. Every number
in every card is computed here from the inputs -- no hand-authored
results:

    direnv exec . python scripts/joint_iv_assemble.py pairs/<pair>.toml
    direnv exec . python scripts/joint_iv_assemble.py <pair> --out PATH

Conventions (match DESIGN.md): both grid axes in iv_rank order; a win is
score > 500 strict (ties lose); scenario si = sf*3 + so. A moveset "arm"
is a grid label minus its _bait/_nobait suffix.

Optional [assemble] table (every key has a generic default; the Thievul
configs pin the historical strings so the rebuild is byte-identical):

    primary_grid       grid label the picks are computed on
                       (default: the first [[grids]] entry)
    moveset_pretty     arm slug -> display label
                       (default: move-id initials, "SP/IW+PR")
    meta_wins          repo-relative meta_wins.npz
                       (default: <data_dir>/meta_wins.npz)
    opp_display_short  short opponent name used in card titles
                       (default: the manifest opponent name)
    pvpoke_default_arm arm slug PvPoke recommends (default: none, and
                       the secondary card makes no PvPoke claim)
    pvpoke_default_ivs [a, d, s] PvPoke's matchup page simulates
    extra_cards        [{title, subtitle, ivs, label}] named-spread
                       cards (community questions etc); these carry
                       authored prose, so there is NO generic default
    cross_moveset_note emit the IV-conditional moveset finding
    injection_note     disclosure sentence for cfg.injected_moves
                       (default: derived; omitted when nothing is
                       injected)

Honesty rules baked in after the 2026-08-16 adversarial verification of
the first (Thievul vs Lickitung) page:
- Scenario classification is explicit and three-way, with the rule
  stated in the blob: saturated_win (every one of the 16.7M cells is a
  win), hopeless (no spread reaches >5% top-512 coverage -- IVs can't
  save you), sensitive (everything else). Computed PER GRID; the
  headline never generalizes across movesets.
- Every metric key carries its moveset+bait label; cards show every
  moveset arm side by side (the community claims may assume either
  build: for Thievul, PvPoke's recommended set is SP/NS+IW and our dive
  landing build is SP/IW+PR).
- "Best" picks disclose the full tiebreak chain and the count tied on
  the primary metric.
- Scenario priority for picks is a FIXED, stated order (even-shield
  fights first, then common asymmetries), filtered to each grid's
  sensitive scenarios -- not a hidden optimization choice.
"""
import argparse
import decimal
import hashlib
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from deep_dive_analysis import move_abbr, pretty_name  # noqa: E402
from joint_iv_config import load_pair  # noqa: E402
import worlds_planes as wp  # noqa: E402

from gopvpsim.pokemon import iv_rank  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
SCEN = ['0-0', '0-1', '0-2', '1-0', '1-1', '1-2', '2-0', '2-1', '2-2']
# The shield scenario the meta-win extraction is keyed on (npz key
# wins__<arm>__pvpoke__bait__<META_SCEN>) and reported in card lines.
META_SCEN = '1-1'
SI_11 = SCEN.index(META_SCEN)
MW_KEY = f'meta_wins_{META_SCEN.replace("-", "")}'
# Stated pick-priority over scenarios (filtered to sensitive ones per
# grid): the even-shield fights people actually plan around, then the
# common asymmetries, then the rest.
SCEN_PRIORITY = ['1-1', '0-0', '2-2', '1-0', '2-1', '0-1', '1-2', '2-0',
                 '0-2']
HOPELESS_MAX_COV = 0.05  # top-512 coverage no spread exceeds -> hopeless
GRID_SUFFIXES = ('_bait', '_nobait')


def tie_line(n, metric, tiebreak=None):
    """The 'N spreads tie on ...' line, in ONE place.

    The page recovers these facts by regex when a card ships no structured
    ``tie`` block (joint_iv_page.js ``tieText``), so this string is a
    cross-file contract: pluralising it once silently cost the TL;DR band
    its 'one of N tied' caveat. tests/test_thievul_tie_roundtrip.py feeds
    this function's output through the real JS parser.
    """
    return (f'{n} spread{"" if n == 1 else "s"} tie on {metric}'
            + (f'; tiebreak chain: {tiebreak}' if tiebreak else ''))


def pct1(v):
    """One decimal, rounded the way the page's JS rounds it.

    Python's format() rounds half-to-even and JS toFixed rounds half-up,
    which disagree on the 8 attainable coverage values that land exactly on
    x.x5 (6.25 -> "6.2" vs "6.3"). The page renders the same quantity from
    the raw counts, so this side must follow ITS rule or the two print
    different numbers for one value.
    """
    return str(decimal.Decimal(repr(float(v))).quantize(
        decimal.Decimal('0.1'), rounding=decimal.ROUND_HALF_UP))


def fmt_ivs(ivs):
    return f'{ivs[0]}/{ivs[1]}/{ivs[2]}'


def arm_of(label):
    """Grid label -> moveset arm slug ('nsiw_nobait' -> 'nsiw')."""
    for suf in GRID_SUFFIXES:
        if label.endswith(suf):
            return label[:-len(suf)]
    return label


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pair', help='pairs/<pair>.toml config path')
    ap.add_argument('--out', default=None, metavar='PATH',
                    help='write the blob here instead of '
                         '<data_dir>/reco.json')
    args = ap.parse_args()
    cfg = load_pair(args.pair)
    asm = cfg.section('assemble')
    data = cfg.data_dir

    manifest = json.loads((data / 'manifest.json').read_text())
    opp_name = manifest['opponent']
    bp = json.loads((data / 'breakpoints.json').read_text())
    # The config names the focal; the blobs were baked from some config.
    # Disagreement means data_dir points at another pair's dataset, which
    # would silently label every number in the page with the wrong
    # species -- so it is a hard stop, not a warning.
    for blob, name in ((manifest, 'manifest.json'), (bp['meta'],
                                                     'breakpoints.json')):
        assert blob['focal'] == cfg.focal, (name, 'focal', blob['focal'])
        assert blob['opponent'] == cfg.opponent, (name, 'opponent',
                                                  blob['opponent'])
        assert blob['league'] == cfg.league, (name, 'league', blob['league'])

    # meta_wins is opponent-independent (focal vs the dive pool), so a
    # pair may point at another pair's copy (both Thievul pairs share the
    # Lickitung-dir blob).
    mw_path = (REPO / asm['meta_wins']) if 'meta_wins' in asm \
        else data / 'meta_wins.npz'
    # ABSENT meta_wins is an honest state (the focal's dive replay may
    # not contain this arm's moveset cube -- Quagsire (Shadow) 2026-08-19,
    # exit-3 skip in joint_iv_run): the reco degrades to MATCHUP-ONLY
    # picks and says so, rather than inventing a meta axis.
    mw = np.load(mw_path) if mw_path.exists() else None
    ranked = iv_rank(cfg.focal, league=cfg.league, shadow=cfg.focal_shadow)

    won = {}
    for label, ginfo in manifest['grids'].items():
        z = np.load(data / ginfo['file'])
        w = wp.unpack_won(z['won_packed'], tuple(z['won_shape']))
        assert w.shape == (4096, 4096, 9), (label, w.shape)
        assert list(w.shape) == list(ginfo['shape']), (label, ginfo['shape'])
        won[label] = w

    # Moveset arms in [[grids]] order, restricted to what actually baked.
    arms, arm_grid = [], {}
    for g in cfg.grids:
        arm = arm_of(g.label)
        if g.label in won and arm not in arm_grid:
            arms.append(arm)
            arm_grid[arm] = g
    # Display label per arm: config first, else the move-id initials.
    pretty_cfg = asm.get('moveset_pretty', {})
    moveset_of = {
        arm: pretty_cfg.get(arm, f'{move_abbr(g.focal_fast)}/'
                            + '+'.join(move_abbr(c) for c in g.focal_charged))
        for arm, g in arm_grid.items()}

    def arm_pretty(arm):
        return moveset_of.get(arm, arm)

    def arm_short(arm):
        """The charged half of the label ('SP/NS+IW' -> 'NS+IW')."""
        p = arm_pretty(arm)
        return p.split('/', 1)[1] if '/' in p else p

    def grid_pretty(label):
        bait = manifest['grids'][label]['bait']
        return (f'{arm_pretty(arm_of(label))}, '
                f'{"baiting" if bait else "no bait"}')

    # Per-grid scenario classification (the rule is in the blob) -------
    per_grid = {}
    for label, w in won.items():
        cls = {'saturated_win': [], 'hopeless': [], 'sensitive': []}
        detail = {}
        for si in range(9):
            sl = w[:, :, si]
            c512 = sl[:, :512].mean(axis=1)
            detail[SCEN[si]] = {
                'win_frac_all': round(float(sl.mean()), 4),
                'cov512_min': round(float(c512.min()) * 100, 2),
                'cov512_max': round(float(c512.max()) * 100, 2),
                'n_spreads_full_cov512': int((c512 == 1.0).sum()),
            }
            if sl.all():
                cls['saturated_win'].append(SCEN[si])
            elif c512.max() <= HOPELESS_MAX_COV:
                cls['hopeless'].append(SCEN[si])
            else:
                cls['sensitive'].append(SCEN[si])
        per_grid[label] = {
            **cls, 'detail': detail, 'pretty': grid_pretty(label),
            'rule': (f'saturated_win: every one of the '
                     f'{w.shape[0] * w.shape[1]:,} cells '
                     f'is a {cfg.focal} win; hopeless: no {cfg.focal} spread '
                     f'beats more than {HOPELESS_MAX_COV:.0%} of the '
                     'top-512 cohort (IV choice cannot save the '
                     'scenario); sensitive: everything else'),
        }

    primary = asm.get('primary_grid', cfg.grids[0].label)
    if primary not in won:
        raise SystemExit(f'ABORT: primary grid {primary} not in the manifest')
    primary_arm = arm_of(primary)
    sens = [s for s in SCEN_PRIORITY
            if s in per_grid[primary]['sensitive']]
    pick_scens = sens[:3] if sens else [META_SCEN]
    pick_sis = [SCEN.index(s) for s in pick_scens]

    cov512 = {label: {si: won[label][:, :512, si].mean(axis=1)
                      for si in range(9)} for label in won}
    meta = {}
    if mw is not None:
        for ms in arms:
            key = f'wins__{ms}__pvpoke__bait__{META_SCEN}'
            if key in mw:
                meta[ms] = mw[key].astype(int)
        if 'pool_n' not in mw:
            raise SystemExit(f'ABORT: {mw_path} has no pool_n; the meta '
                             'line would have to invent a denominator')
        if primary_arm not in meta:
            raise SystemExit(f'ABORT: no meta wins for the primary arm '
                             f'{primary_arm} in {mw_path}')
    has_meta = primary_arm in meta
    pool_n = int(mw['pool_n']) if has_meta else None
    meta_pri = meta[primary_arm] if has_meta else None

    # Breakpoint slot keys, spelled the same way joint_iv_breakpoints.py
    # spells them when it WRITES the blob (focal_key/opp_short are slug
    # prefixes; the table is f'{focal_key}_offense'). The shipped Thievul
    # blobs keep the Lickitung-era spellings on BOTH pairs, so these are
    # config, not derived from the current opponent.
    bp_sec = cfg.section('breakpoints')
    focal_key = f"{bp_sec.get('focal_key', cfg.focal_slug)}_offense"
    opp_short = bp_sec.get('opp_short', cfg.opp_slug)
    if focal_key not in bp:
        raise SystemExit(f'ABORT: breakpoints.json has no {focal_key!r} '
                         'table; set [breakpoints].focal_key (present: '
                         f'{sorted(k for k in bp if k.endswith("_offense"))})')
    # The HEADLINE move is whichever entry the breakpoint layer built the
    # per-spread tier table for (the breakpoints step may auto-pick a
    # charged move when the fast move is tier-flat -- Corviknight's Sand
    # Attack, 2026-08-19). Located structurally, exactly the way the page
    # JS locates it, so the two layers can never disagree.
    tier_field = f'tier_vs_rank1_{opp_short}_by_spread'
    headline_ids = [mid for mid, entry in bp[focal_key]['moves'].items()
                    if tier_field in entry]
    if len(headline_ids) != 1:
        raise SystemExit(f'ABORT: expected exactly one {focal_key} move '
                         f'carrying {tier_field!r}, found {headline_ids}; '
                         'set [breakpoints].opp_short to the slot spelling '
                         'the blob actually uses')
    fast_id = headline_ids[0]
    fast_bp = bp[focal_key]['moves'][fast_id]
    sp_tier = np.array(fast_bp[tier_field])
    # The tier that "clears the breakpoint", from the breakpoint layer --
    # a literal here would render a false claim on any other pair.
    hi_tier = int(fast_bp[f'breakpoint_vs_rank1_{opp_short}']['hi_tier'])
    tier_key = f'{move_abbr(fast_id).lower()}_tier_vs_rank1_{opp_short}'
    opp_display_short = asm.get('opp_display_short', opp_name)

    def metrics(i):
        out = {tier_key: int(sp_tier[i]),
               MW_KEY: {ms: int(meta[ms][i]) for ms in meta}}
        # ALL nine scenarios per grid, not just the primary grid's pick
        # list: a card that states its own tiebreak chain (the secondary
        # arm's card ranks on its own scenarios first) must be able to
        # show the number it ranked on.
        for label in won:
            # Rounded ONCE, at render time. Storing 2dp here and printing
            # 1dp downstream is a double round: 72.8515625 -> 72.85 ->
            # "72.8%", while the page's own 1dp render of the raw value is
            # "72.9%". 6dp is exact enough for the 1/512 and 1/4096 steps
            # to round identically on both sides.
            out[label] = {
                SCEN[si]: round(float(cov512[label][si][i]) * 100, 6)
                for si in range(len(SCEN))}
            out[label]['pretty'] = grid_pretty(label)
        return out

    def find(a, d, s):
        for i, r in enumerate(ranked):
            if (r['atk_iv'], r['def_iv'], r['sta_iv']) == (a, d, s):
                return i
        raise KeyError((a, d, s))

    def spread_row(i):
        r = ranked[i]
        return {'ivs': [r['atk_iv'], r['def_iv'], r['sta_iv']],
                'rank': i + 1, 'level': r['level'], 'cp': r['cp'],
                'atk': round(r['atk'], 4), 'def': round(r['def_'], 4),
                'hp': r['hp']}

    # Picks, with disclosed tiebreaks ---------------------------------
    pick_cols = [cov512[primary][si] for si in pick_sis]
    tiebreak = (' > '.join(f'{s} coverage' for s in pick_scens)
                + (f' > meta wins ({arm_pretty(primary_arm)}, {META_SCEN})'
                   if has_meta else '')
                + ' > stat-product rank')
    # np.lexsort: LAST key is primary, so list from weakest to strongest.
    keys = ([np.arange(4096)] + ([-meta_pri] if has_meta else [])
            + [-c for c in reversed(pick_cols)])
    order = np.lexsort(tuple(keys))
    i_smash = int(order[0])
    n_tied_smash = int((pick_cols[0] >= pick_cols[0][i_smash] - 1e-12).sum())

    # Best meta among spreads with full top-512 coverage at every
    # sensitive pick scenario (primary grid).
    full_mask = np.ones(4096, dtype=bool)
    for c in pick_cols:
        full_mask &= (c == 1.0)
    if full_mask.any():
        cand = np.flatnonzero(full_mask)
        if has_meta:
            i_bal = int(cand[np.argmax(meta_pri[cand])])
            _cost = int(meta_pri.max()) - int(meta_pri[i_bal])
            bal_note = (f'{len(cand)} spreads have 100% top-512 coverage '
                        f'at {", ".join(pick_scens)}; this is the best '
                        f'meta record among them '
                        f'({int((meta_pri[cand] == meta_pri[i_bal]).sum())} '
                        f'tied at that record'
                        + (f'; {_cost}W below the max-meta pick' if _cost
                           else '') + ')')
        else:
            i_bal = int(cand[0])
            bal_note = (f'{len(cand)} spreads have 100% top-512 coverage '
                        f'at {", ".join(pick_scens)}; no dive-derived meta '
                        'data exists for this arm, so this is the best '
                        'stat-product rank among them')
    else:
        i_bal, bal_note = i_smash, 'no spread is full-coverage at all pick scenarios'
    bal_is_real = bool(full_mask.any())

    if has_meta:
        max_meta = int(meta_pri.max())
        at_max = np.flatnonzero(meta_pri == max_meta)
        i_meta_best = int(at_max[np.argmax(pick_cols[0][at_max])])

    # Best build under each OTHER arm, judged on ITS OWN sensitive
    # scenarios -- readers running a different moveset deserve a pick
    # computed for it, not the primary arm's leftovers.
    pvpoke_arm = asm.get('pvpoke_default_arm')
    sec_cards = []
    for arm in arms:
        if arm == primary_arm:
            continue
        # The arm's grid at the primary grid's bait policy: comparing a
        # baiting pick against a no-bait one would be a different fight.
        sec = next((g.label for g in cfg.grids
                    if arm_of(g.label) == arm and g.label in won
                    and manifest['grids'][g.label]['bait']
                    == manifest['grids'][primary]['bait']), None)
        if sec is None:
            continue
        ns_sens = [s for s in SCEN_PRIORITY
                   if s in per_grid[sec]['sensitive']]
        ns_scens = ns_sens[:3] if ns_sens else [META_SCEN]
        ns_cols = [cov512[sec][SCEN.index(s)] for s in ns_scens]
        ns_keys = [np.arange(4096)]
        ns_tiebreak = ' > '.join(f'{s} coverage' for s in ns_scens)
        # No silent fallback to the PRIMARY arm's meta counts: an arm with
        # no meta row is ranked without the meta tiebreak, and says so.
        if arm in meta:
            ns_keys.append(-meta[arm])
            ns_tiebreak += f' > meta wins ({arm_pretty(arm)}, {META_SCEN})'
        ns_tiebreak += ' > stat-product rank'
        ns_keys += [-c for c in reversed(ns_cols)]
        i_ns = int(np.lexsort(tuple(ns_keys))[0])
        n_tied_ns = int((ns_cols[0] >= ns_cols[0][i_ns] - 1e-12).sum())
        short = arm_short(arm)
        is_pvpoke = (arm == pvpoke_arm)
        sec_cards.append(
            (f'Best build if you run {short}'
             + (' (PvPoke default)' if is_pvpoke else ''),
             f'Computed on the {arm_pretty(arm)} grid\'s own sensitive '
             f'scenarios ({", ".join(ns_scens)}); for readers '
             + ('following PvPoke\'s default moveset' if is_pvpoke
                else f'running {short}')
             + f'. Tiebreak: {ns_tiebreak}', i_ns,
             [tie_line(n_tied_ns,
                       f'{ns_scens[0]} coverage under {short}')], [],
             sec, ns_scens,
             {'n_tied': n_tied_ns,
              'metric': f'{ns_scens[0]} coverage under {short}',
              'tiebreak': ns_tiebreak}))

    named = [
        (f'The {opp_display_short} smasher',
         # "Best X, Y, Z record" implied best at ALL THREE; the pick is
         # lexicographic and can be 0% on a later scenario (Wigglytuff
         # smasher: 92% at 1-1, 0% at 2-2 -- 2026-08-19 review blocker).
         f'Best record vs {opp_name} in priority order '
         f'{" > ".join(pick_scens)} '
         f'({grid_pretty(primary)}); tiebreak: {tiebreak}',
         i_smash,
         [tie_line(n_tied_smash,
                   f'the primary metric ({pick_scens[0]} top-512 '
                   f'coverage)', tiebreak)],
         (['Optimized purely for this matchup; check the meta line before '
           'committing dust.']
          + ([] if full_mask.any() else
             ['No spread reaches full top-512 coverage at every pick '
              'scenario -- even the best build loses winnable-looking '
              'cells here.'])
          + ([f'Beats only {pct1(float(pick_cols[0][i_smash]) * 100)}% of '
              f'the top-512 at {pick_scens[0]} -- a contested-at-best '
              'scenario, not a farm.']
             if float(pick_cols[0][i_smash]) <= 0.40 else [])),
         primary, pick_scens,
         {'n_tied': n_tied_smash,
          'metric': f'{pick_scens[0]} top-512 coverage',
          'tiebreak': tiebreak}),
    ]
    if bal_is_real:
        # Only when a full-coverage set actually exists -- the fallback
        # (i_bal == i_smash) made the merged card claim 'Full coverage'
        # for a 28%-coverage spread (2026-08-19 verify high). The
        # fallback's information (no spread is full-coverage) travels as
        # a smasher caveat instead.
        named.append(
            (('IV tech without meta cost'
              if int(meta_pri[i_bal]) == int(meta_pri.max())
              else 'Full coverage, best meta record') if has_meta
             else 'Full coverage, cheapest build', bal_note, i_bal, [], []))
    if has_meta:
        # The tie count is in this card's subtitle prose too; it also
        # travels STRUCTURALLY so the band never has to parse it (the one
        # card that shipped without a tie block).
        named.append(
            ('Max meta wins', f'Best overall-meta spread -- one of '
             f'{len(at_max)} tied at {max_meta}W ({grid_pretty(primary)}, '
             f'{META_SCEN}); among the tie, best {pick_scens[0]} coverage '
             'shown',
             i_meta_best, [], [], primary, None,
             {'n_tied': int(len(at_max)),
              'metric': f'meta wins ({grid_pretty(primary)}, '
                        f'{META_SCEN})'}))
    for k, sec_card in enumerate(sec_cards):
        named.insert(3 + k, sec_card)
    # Named-spread cards (community questions, the shipped landing build,
    # PvPoke's default spread): authored titles/subtitles, since the
    # claims they answer are pair-specific and cannot be templated
    # honestly. The IVs are looked up, so the card body is still computed.
    extra_cards = asm.get('extra_cards', [])
    for spec in extra_cards:
        ivs = tuple(spec['ivs'])
        named.append((spec['title'], spec['subtitle'], find(*ivs), [], []))

    # Byte-identical win grids, grouped (see the collapse in card()).
    grid_groups = []
    _seen = {}
    for label in sorted(won):
        key = hashlib.md5(np.ascontiguousarray(won[label])).hexdigest()
        if key in _seen:
            grid_groups[_seen[key]].append(label)
        else:
            _seen[key] = len(grid_groups)
            grid_groups.append([label])

    def card(title, subtitle, i, extra, caveats, scens=None, tie=None):
        # A card prints the SAME scenarios its own tiebreak chain ranked
        # on -- a secondary-arm card is chosen on that arm's sensitive
        # scenarios, so printing the primary grid's set underneath it
        # would be a different question than the one it answered.
        scens = list(scens or pick_scens)
        m = metrics(i)
        r = ranked[i]
        lines = [
            f'IVs {fmt_ivs(spread_row(i)["ivs"])} -- SP rank '
            f'#{i + 1}, L{r["level"]}, CP {r["cp"]}, atk {r["atk"]:.2f} / '
            f'def {r["def_"]:.2f} / hp {r["hp"]}',
        ]
        # BYTE-IDENTICAL grids collapse to one line naming both: two
        # lines of identical digits read as a rendering bug, and the
        # duplication is a property of the data (a bait grid can be
        # byte-identical to its no-bait twin), not a finding. Grids that
        # merely happen to agree at THESE scenarios still get their own
        # line -- "=" here means the whole 4096x4096x9 grid is the same.
        for group in grid_groups:
            # ONE decimal, matching the page's COV_DP: the band and the
            # verdict table render these same stored values, and the 2dp
            # repr here made one quantity print two ways.
            covs = ', '.join(f'{s}: {pct1(m[group[0]][s])}%' for s in scens)
            pretty = ' = '.join(m[la]['pretty'] for la in group)
            lines.append(f'[{pretty}] top-512 coverage -- {covs}')
        if m[MW_KEY]:
            mw_line = ' / '.join(
                f'{arm_pretty(ms)} {m[MW_KEY][ms]}W'
                for ms in sorted(m[MW_KEY]))
            lines.append(f'Meta at {META_SCEN}, of {pool_n} dive-pool '
                         f'matchups (baiting): {mw_line}')
        else:
            lines.append('No dive-derived meta data for this arm (the '
                         'focal dive replay lacks this moveset cube); '
                         'matchup-only pick.')
        lines.append(f'{pretty_name(fast_id)} does {m[tier_key]} '
                     f'damage vs the rank-1 {opp_name} ({hi_tier} = clears '
                     'the breakpoint)')
        return {'title': title, 'subtitle': subtitle,
                'spread': spread_row(i), 'rank': i + 1,
                'lines': lines + extra, 'metrics': m,
                'scenarios': scens,
                # STRUCTURED tie facts. The page used to recover these by
                # regex from the prose line below, which broke the moment
                # the sentence was pluralised; the prose stays for the
                # card body, but the band reads these fields.
                'tie': tie,
                'caveats': caveats}

    def card_with_grid(spec):
        c = card(*spec[:5], scens=(spec[6] if len(spec) > 6 else None),
                 tie=(spec[7] if len(spec) > 7 else None))
        # Every card states the grid it was computed on, structurally --
        # the page no longer has to guess it from the subtitle.
        c['grid'] = spec[5] if len(spec) > 5 else primary
        c['basis_pretty'] = grid_pretty(c['grid'])
        return c

    cards = [card_with_grid(n) for n in named]

    # Two cards can select the SAME spread (on Lickilicky the smasher and
    # the no-meta-cost pick are both 5/9/7). Shipping them twice with
    # identical numbers reads as a rendering bug, so they are merged into
    # one card that states both roles.
    merged, by_rank = [], {}
    for c in cards:
        key = (c['rank'], c['grid'])
        if key in by_rank:
            first = by_rank[key]
            if c['title'] not in first['title']:
                first['title'] = f"{first['title']} (also: {c['title']})"
            for extra_line in c['lines']:
                if extra_line not in first['lines']:
                    first['lines'].append(extra_line)
            if c.get('subtitle') and c['subtitle'] not in first['subtitle']:
                first['subtitle'] = (first['subtitle'].rstrip('.')
                                     + '. Also the pick for: '
                                     + c['subtitle'])
            continue
        by_rank[key] = c
        merged.append(c)
    cards = merged

    # The PAGE defaults to the first secondary-arm grid, so the band must
    # lead with the card computed on it; leading with a primary-arm card
    # made the first numbers a reader sees belong to a moveset no panel
    # below was showing.
    default_grid = sec_cards[0][5] if sec_cards else primary
    cards.sort(key=lambda c: 0 if c.get('grid') == default_grid else 1)

    # Opponent-cohort level facts DERIVED from the baked npz (the first
    # version hardcoded Lickitung's "L44.5-50 XL" here; the independent
    # verification caught it rendered falsely on the Lickilicky page).
    opp_levels = np.load(
        data / manifest['grids'][primary]['file'])['opp_levels']
    lv_lo, lv_hi = float(opp_levels.min()), float(opp_levels.max())
    xl_note = (' -- XL-candy territory (above L40)' if lv_lo > 40.0
               else '')
    cohort_note = (
        f'Coverage cohort for cards is the top-512 {opp_name} spreads by '
        f'stat product; every {opp_name} spread in the 4096 denominator '
        f'is the CP-capped best build for its IVs, L{lv_lo:g}-L{lv_hi:g}'
        f'{xl_note}.')

    notes = [
        'All cards are auto-computed from the baked grids, the dive '
        'replay extraction, and the closed-form breakpoint layer. '
        'Human-guided, AI-generated; no hand-authored numbers.',
        'A "win" is pvpoke score > 500 strict; ties count as losses.',
        cohort_note,
        (f'Meta wins are vs the shipped dive pool ({pool_n} matchups '
         'incl. counter-slayers and the mirror) with PvPoke opponent IVs, '
         f'focal baiting, at {META_SCEN} shields.') if has_meta else
        ('NO dive-derived meta data exists for this pair (the focal dive '
         'replay lacks this moveset cube), so every pick here is '
         'MATCHUP-ONLY: nothing on this page weighs performance against '
         'the rest of the meta.'),
    ]
    if cfg.injected_moves:
        notes.append(asm.get('injection_note') or (
            f'{", ".join(cfg.injected_moves)} '
            f'{"is" if len(cfg.injected_moves) == 1 else "are"} injected '
            'into the legal move pool for the sim (the pinned gamemaster '
            f'predates the move). Mechanics: {manifest["mechanics"]}.'))

    # Cross-moveset finding (computed, only for grids present) ---------
    if asm.get('cross_moveset_note') and sec_cards:
        sec = sec_cards[0][5]
        sec_arm = arm_of(sec)
        clears = sp_tier >= hi_tier
        c_iw = cov512[primary][SI_11]
        c_ns = cov512[sec][SI_11]
        ns_better = c_ns > c_iw
        n_ns_better = int(ns_better.sum())
        n_ns_better_missing = int((ns_better & ~clears).sum())
        miss_word = ('all of them breakpoint-missing'
                     if n_ns_better_missing == n_ns_better else
                     f'{n_ns_better_missing} of them breakpoint-missing')
        # The "PvPoke's default is one of them" clause is a CLAIM, so it
        # is checked against the same array before it is printed rather
        # than asserted in prose (the original shipped it unverified).
        pv_ivs = asm.get('pvpoke_default_ivs')
        pv_clause = ''
        extra_ch = [c for c in arm_grid[sec_arm].focal_charged
                    if c not in arm_grid[primary_arm].focal_charged]
        if pv_ivs and len(extra_ch) == 1 and bool(ns_better[find(*pv_ivs)]):
            pv_clause = (f' -- PvPoke\'s default {fmt_ivs(pv_ivs)} is one '
                         f'of them, which is why its matchup page prefers '
                         f'{pretty_name(extra_ch[0])}')
        notes.append(
            f'Moveset is IV-conditional at {META_SCEN}: for all '
            f'{int(clears.sum())} breakpoint-clearing spreads '
            f'{arm_pretty(primary_arm)} '
            f'is better-or-equal (mean {c_iw[clears].mean()*100:.1f}% vs '
            f'{c_ns[clears].mean()*100:.1f}% top-512 coverage); '
            f'{arm_short(sec_arm)} is '
            f'better for only {n_ns_better} spreads, {miss_word}'
            f'{pv_clause}.')

    reco = {
        'opponent': opp_name,
        'primary_grid': primary,
        'primary_grid_pretty': grid_pretty(primary),
        'pick_scenarios': pick_scens,
        'scenario_priority_rule': ('picks are ranked over the sensitive '
                                   'scenarios of the primary grid in the '
                                   'fixed order ' + ', '.join(SCEN_PRIORITY)),
        'per_grid_scenarios': per_grid,
        'pool_n': pool_n,
        'cards': cards,
        'pareto_axes': [f'meta wins at {META_SCEN} ({grid_pretty(primary)})',
                        f'{pick_scens[0]} top-512 coverage pct '
                        f'({grid_pretty(primary)})'],
        'pareto': [],
        'notes': notes,
        'named_builds': [
            {'label': f'#{i + 1} {fmt_ivs(spread_row(i)["ivs"])} ({t})',
             'rank': i + 1}
            for t, i in ([('smasher', i_smash)]
                         + ([(('no-meta-cost' if int(meta_pri[i_bal])
                               == int(meta_pri.max()) else 'full-coverage')
                              if has_meta else 'full-coverage', i_bal)]
                            if bal_is_real else [])
                         + ([('max meta', i_meta_best)] if has_meta else [])
                         + [(f'{arm_short(arm_of(c[5]))} pick', c[2])
                            for c in sec_cards]
                         + [(spec.get('label', fmt_ivs(spec['ivs'])),
                             find(*spec['ivs']))
                            for spec in extra_cards])],
    }

    # Pareto on (meta, primary pick-scenario coverage) -----------------
    if has_meta:
        pts = np.stack([meta_pri, pick_cols[0]], axis=1)
        for i in range(4096):
            dominated = ((pts[:, 0] >= pts[i, 0]) & (pts[:, 1] >= pts[i, 1])
                         & ((pts[:, 0] > pts[i, 0])
                            | (pts[:, 1] > pts[i, 1])))
            if not dominated.any():
                reco['pareto'].append(
                    {**spread_row(i), MW_KEY: int(meta_pri[i]),
                     'primary_cov512': round(float(pick_cols[0][i]) * 100,
                                             2)})
        reco['pareto'].sort(key=lambda e: -e[MW_KEY])

    out = pathlib.Path(args.out) if args.out else data / 'reco.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reco, indent=1))
    print(f'wrote {out} ({out.stat().st_size:,} bytes)')
    print(f'primary grid {primary}; pick scenarios {pick_scens}')
    for label, pg in per_grid.items():
        print(f'  {label}: saturated {pg["saturated_win"]} hopeless '
              f'{pg["hopeless"]} sensitive {pg["sensitive"]}')
    for c in cards:
        m = c['metrics']
        covs = ' '.join(f'{s}={m[primary][s]}' for s in pick_scens)
        print(f'-- {c["title"]}: #{c["rank"]} '
              f'{fmt_ivs(c["spread"]["ivs"])} {covs} '
              f'meta={m[MW_KEY]}')


if __name__ == '__main__':
    main()
