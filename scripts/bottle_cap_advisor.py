#!/usr/bin/env python
"""Gold Bottle Cap advisor -- scan an owned collection and rank which mons would
most benefit from having their IVs perfected.

A Gold Bottle Cap RAISES IVs to any value >= the current value; it can never
lower an IV. So the honest "best you can reach" for a given mon is the
highest-stat-product spread whose every IV is >= that mon's current IV -- NOT
the global rank-1 (which in Great/Ultra League is a low-attack spread you often
can't reach by boosting up). A 15/15/15 Great-League mon therefore correctly
shows ZERO benefit: its only reachable target is itself.

Unit of analysis is (species, league), not the individual mon, because a cap is
a scarce resource and you only need one good copy of a species. For each meta
species you own we compare:
  * best CURRENT copy  -- the owned spread with the highest stat product as-is
  * best CAPPED copy   -- the best spread reachable by capping SOME owned copy
and report the gain. If you already own the reachable-optimal copy the gain is
zero (a cap here is wasted).

Two layers:
  1. Analytic scan (fast, whole box): stat-product rank of best-current vs
     best-capped, via pokemon.iv_rank. Covers every meta species you own.
  2. Simulation (shortlist only): re-sim best-current vs best-capped against the
     league pool (owned_breakdown convention: pool opponents at 15/15/15, even
     shields) for the concrete matchup-win gain.

FLAGS (never-ship-unflagged): the capped target is the stat-product-optimal
reachable spread -- the project-wide 'rank-1' convention -- not an exhaustive
matchup-win optimum (intractable at box scale). Meta scope is the top
--meta-top species by PvPoke score per league; owned mons of lower-ranked
species are not scanned. Shadow copies are ranked on their own shadow IV table
and annotated with the base species' (non-shadow) meta rank.
"""
import argparse
import os
import sys
from collections import defaultdict
from multiprocessing import Pool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gopvpsim.pokemon import iv_rank, LEAGUE_MAX_LEVEL, LEAGUE_CAPS
from gopvpsim.data import load_rankings, get_default_moveset
from gopvpsim.user_collection import parse_csv, get_species_name
from gopvpsim.evolution_lines import get_final_forms

from owned_breakdown import load_pool, won_set, EVEN_SHIELDS, DEFAULT_POOLS

LEAGUES = ('great', 'ultra', 'master')
LEAGUE_TAG = {'great': 'GL', 'ultra': 'UL', 'master': 'ML'}


def meta_rank_table(league):
    """{speciesName: meta_rank} sorted by PvPoke overall score (rank 1 = best)."""
    ranked = sorted(load_rankings(league), key=lambda e: e['score'], reverse=True)
    return {e['speciesName']: i + 1 for i, e in enumerate(ranked)}


class IvTable:
    """Cached iv_rank result for one (species, league, shadow): rank + stat
    product per spread, and a reachable-best query."""
    def __init__(self, species, league, shadow):
        self.entries = iv_rank(species, league=league, shadow=shadow)
        self.rank_of = {}
        self.sp_of = {}
        for e in self.entries:
            key = (e['atk_iv'], e['def_iv'], e['sta_iv'])
            self.rank_of[key] = e['rank']
            self.sp_of[key] = e['stat_product']

    def reachable_best(self, iv):
        """Best (lowest-rank) spread with every IV >= iv. entries are sorted by
        rank ascending, so the first match is the answer. Returns None if the
        starting spread itself isn't a valid capped entry (over-CP at L1)."""
        a0, d0, h0 = iv
        if iv not in self.rank_of:
            return None
        for e in self.entries:  # rank-ascending
            if e['atk_iv'] >= a0 and e['def_iv'] >= d0 and e['sta_iv'] >= h0:
                return (e['atk_iv'], e['def_iv'], e['sta_iv'])
        return iv  # itself always qualifies; loop always hits it


def collect_owned(csv_path):
    """{(final_species, shadow): set(iv tuples)} over the whole box, walking
    evolutions (IVs carry through) and every possible final form."""
    owned = defaultdict(set)
    for m in parse_csv(csv_path):
        base = get_species_name(m['name'], m['form'], False)
        iv = (m['atk_iv'], m['def_iv'], m['sta_iv'])
        for final in get_final_forms(base):
            owned[(final, m['is_shadow'])].add(iv)
    return owned


def analyze(csv_path, meta_top):
    """Per (species, league, shadow) analytic opportunity. Returns a list of
    dicts sorted later; simulation is layered on afterward."""
    owned = collect_owned(csv_path)
    out = []
    for league in LEAGUES:
        meta = meta_rank_table(league)
        top = {sp for sp, r in meta.items() if r <= meta_top}
        for (species, shadow), ivs in owned.items():
            if species not in top:
                continue
            tbl = IvTable(species, league, shadow)
            valid = [iv for iv in ivs if iv in tbl.rank_of]
            if not valid:
                continue
            # best current copy (lowest rank as-is)
            best_now = min(valid, key=lambda iv: tbl.rank_of[iv])
            # best copy reachable by capping some owned copy
            capped = []
            for iv in valid:
                tgt = tbl.reachable_best(iv)
                if tgt is not None:
                    capped.append((iv, tgt))
            src, target = min(capped, key=lambda st: tbl.rank_of[st[1]])
            sp_now = tbl.sp_of[best_now]
            sp_cap = tbl.sp_of[target]
            # Resolve the default moveset here so a clone-slug rankings wart
            # (e.g. 'Golisopod'/'Cradily' absent from UL rankings) marks the row
            # instead of crashing a sim worker. Analytic fields don't need it.
            try:
                fast, charged = get_default_moveset(species, league=league,
                                                    shadow=shadow)
                moveset = (fast, list(charged))
            except Exception:
                moveset = None
            out.append({
                'species': species, 'league': league, 'shadow': shadow,
                'meta_rank': meta.get(species),
                'n_owned': len(ivs),
                'best_now': best_now, 'rank_now': tbl.rank_of[best_now],
                'cap_src': src, 'target': target, 'rank_cap': tbl.rank_of[target],
                'sp_gain_pct': 100.0 * (sp_cap - sp_now) / sp_now,
                'moveset': moveset,
                'sim': None,  # filled for the shortlist
            })
    return out


_POOL_CACHE = {}  # per-worker-process league -> opponents


def simulate_row(row):
    """Concrete matchup-win gain: wins(target) - wins(best_now) vs the pool.
    Pure function of `row` (a process-global pool cache keeps it fast); returns
    the row with its 'sim' field filled, so it is safe as a Pool worker."""
    league, species, shadow = row['league'], row['species'], row['shadow']
    fast, charged = row['moveset']
    ceiling = LEAGUE_MAX_LEVEL.get(league, 51.0)
    if league not in _POOL_CACHE:
        _POOL_CACHE[league] = load_pool(DEFAULT_POOLS[league], league)
    opps = _POOL_CACHE[league]
    kw = dict(shadow=shadow, opponents=opps, league=league,
              my_level=ceiling, opp_level=ceiling, shieldset=EVEN_SHIELDS)
    won_now = won_set(species, fast, charged, row['best_now'], **kw)
    won_cap = won_set(species, fast, charged, row['target'], **kw)
    gained = sorted(f"{d} {s[0]}-{s[1]}" for (d, s) in (won_cap - won_now))
    row['sim'] = {'wins_now': len(won_now), 'wins_cap': len(won_cap),
                  'total': len(opps) * len(EVEN_SHIELDS),
                  'delta': len(won_cap) - len(won_now), 'gained': gained}
    return row


def _ivs(t):
    return '/'.join(map(str, t))


def render(rows, min_sp):
    lines = []
    shown = [r for r in rows if r['sp_gain_pct'] > min_sp]
    shown.sort(key=lambda r: (-(r['sim']['delta'] if r['sim'] else -1),
                              -r['sp_gain_pct']))
    n_sim = sum(1 for r in shown if r['sim'])
    lines.append(f"{len(shown)} bottle-cap opportunities (stat-product gain "
                 f"> {min_sp}%); {n_sim} simulated for matchup-win gain.")
    lines.append("A cap RAISES IVs only; target = highest-stat-product spread "
                 "with every IV >= a copy you own. dWins = matchups the target "
                 "wins minus your best current copy wins.")
    lines.append("ML: target is 15/15/15, which weakly dominates -- dWins >= 0 "
                 "and is exact. GL/UL: target maximizes BULK; under the CP cap "
                 "that can shift level/attack and LOSE CMP/breakpoints (dWins < "
                 "0), and a non-bulk-max cap could sometimes do better (not "
                 "searched). Trust the dWins column, not dSP%.")
    lines.append("")
    hdr = (f"{'Species':<26}{'Lg':<4}{'#Rk':<5}{'Own':<4}"
           f"{'Best now':<16}{'Cap -> target':<20}{'dSP%':<8}{'dWins':<16}")
    lines.append(hdr)
    lines.append('-' * len(hdr))
    for r in shown:
        sh = ' (S)' if r['shadow'] else ''
        name = (r['species'] + sh)[:25]
        now = f"{_ivs(r['best_now'])} r{r['rank_now']}"
        cap = f"{_ivs(r['cap_src'])}->{_ivs(r['target'])}"
        if r['sim']:
            s = r['sim']
            dw = f"{s['delta']:+d} ({s['wins_now']}->{s['wins_cap']})" if s['delta'] \
                else f"0 ({s['wins_now']}/{s['total']})"
        elif r['moveset'] is None:
            dw = '~ (no moveset)'
        else:
            dw = '~ (not simmed)'
        lines.append(f"{name:<26}{LEAGUE_TAG[r['league']]:<4}"
                     f"{str(r['meta_rank']):<5}{r['n_owned']:<4}"
                     f"{now:<16}{cap:<20}{r['sp_gain_pct']:>5.1f}%  {dw:<16}")
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('csv', help='PokeGenie CSV export')
    ap.add_argument('--meta-top', type=int, default=150,
                    help='only scan species ranked <= this by PvPoke score per '
                    'league (default 150; Pachirisu is GL #136)')
    ap.add_argument('--min-sp', type=float, default=0.5,
                    help='hide opportunities below this stat-product gain %% '
                    '(default 0.5)')
    ap.add_argument('--sim-top', type=int, default=0,
                    help='cap simulation to the top N by SP gain for speed '
                    '(0 = simulate every shown opportunity; unsimmed rows are '
                    'marked so the win-gain ranking stays honest)')
    ap.add_argument('--no-sim', action='store_true',
                    help='analytic stat-product scan only, skip simulation')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 2),
                    help='parallel simulation workers (default cpu_count-2)')
    ap.add_argument('--league', choices=LEAGUES,
                    help='restrict to one league (default: all three)')
    a = ap.parse_args()

    rows = analyze(a.csv, a.meta_top)
    if a.league:
        rows = [r for r in rows if r['league'] == a.league]

    skipped = sorted({f"{r['species']} {LEAGUE_TAG[r['league']]}"
                      for r in rows
                      if r['moveset'] is None and r['sp_gain_pct'] > a.min_sp})
    if skipped:
        print(f"NOTE: no default moveset (clone-slug rankings gap) -- analytic "
              f"only, not simulated: {', '.join(skipped)}", file=sys.stderr)

    if not a.no_sim:
        to_sim = sorted([r for r in rows if r['sp_gain_pct'] > a.min_sp
                         and r['moveset'] is not None],
                        key=lambda r: -r['sp_gain_pct'])
        if a.sim_top > 0:
            to_sim = to_sim[:a.sim_top]
        print(f"Simulating {len(to_sim)} opportunities on {a.jobs} workers "
              f"(matchup wins vs the league pool)...", file=sys.stderr)
        if a.jobs > 1 and len(to_sim) > 1:
            with Pool(a.jobs) as pool:
                done = pool.map(simulate_row, to_sim)
        else:
            done = [simulate_row(r) for r in to_sim]
        # graft sim results back onto the corresponding rows (Pool returns copies)
        sim_by_key = {(r['species'], r['league'], r['shadow']): r['sim']
                      for r in done}
        for r in rows:
            r['sim'] = sim_by_key.get((r['species'], r['league'], r['shadow']),
                                      r['sim'])

    print(render(rows, a.min_sp))


if __name__ == '__main__':
    main()
