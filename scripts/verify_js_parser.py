#!/usr/bin/env python3
"""
Equivalence harness for the JS port of gopvpsim.user_collection.

Runs Python ``match_mons`` and the browser-side JS ``matchMons`` against
the same Poke Genie fixture + threshold dict, compares row-for-row, and
exits nonzero if they diverge. This is the regression barrier for the
JS port: anytime ``scripts/deep_dive_user_collection.js`` changes, run
this script before committing.

Requires node.js on PATH. The fixture at
``tests/fixtures/poke_genie_export.csv`` is a checked-in export of the
maintainer's collection — if missing, the script explains how to supply one.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'src'))

from gopvpsim.evolution_lines import _load_pre_to_finals  # noqa: E402
from gopvpsim.pokemon import (  # noqa: E402
    CPM, LEAGUE_CAPS, SHADOW_ATK_BONUS, SHADOW_DEF_MULT, get_pokemon_index,
)
from gopvpsim.user_collection import (  # noqa: E402
    compute_rank_lookup, match_mons, parse_csv_text,
)


# The harness league and its level ceiling. Both sides (Python match_mons
# and the JS payload) must receive the SAME league-derived cap, passed
# explicitly — relying on the shared 51.0 defaults hid a league-awareness
# blind spot: with 51.0 hardcoded on both sides the harness passes even if
# one side stops deriving the cap from the league (GL/UL cap at 50.0; see
# docs/reviews/2026-06-28_iv_scanner_maxlevel_strong_pin_design.md).
HARNESS_LEAGUE = 'great'
HARNESS_MAX_LEVEL = 50.0


# Test thresholds — a small but diverse dict that exercises:
#   * attack/defense/stamina floors
#   * the ``ivs`` whitelist branch
#   * the ``onlytop`` rank branch (rank data is absent so this simply
#     excludes every mon, which both sides should agree on)
#   * shadow and non-shadow species
#   * a branching evolution walkup (Eevee → Sylveon)
#   * a pre-evo walkup (Tinkatink → Tinkaton)
TEST_THRESHOLDS = {
    'Tinkaton': {
        'Great': {
            'Any':       {'attack':  90, 'defense':   0, 'stamina':   0},
            'High def':  {'attack':   0, 'defense': 120, 'stamina':   0},
            'Rank cap':  {'attack':   0, 'defense':   0, 'stamina':   0, 'onlytop': 5},
            'IV list':   {'attack':   0, 'defense':   0, 'stamina':   0,
                          'ivs': [[0, 15, 15], [0, 14, 14], [1, 15, 15]]},
        },
    },
    'Medicham': {
        'Great': {
            'Any':       {'attack':   0, 'defense':   0, 'stamina':   0},
        },
    },
    'Azumarill': {
        'Great': {
            'Any':       {'attack':   0, 'defense':   0, 'stamina':   0},
        },
    },
    'Sableye (Shadow)': {
        'Great': {
            'Any':       {'attack':   0, 'defense':   0, 'stamina':   0},
        },
    },
    'Annihilape (Shadow)': {
        'Great': {
            'Any':       {'attack':   0, 'defense':   0, 'stamina':   0},
        },
    },
    'Sylveon': {
        'Great': {
            'Any':       {'attack':   0, 'defense':   0, 'stamina':   0},
        },
    },
}


def canonicalize(obj):
    """Convert a match_mons result to a deterministic, diff-friendly form.

    Numeric fields are normalized to (is_whole_number ? int : rounded
    float), so Python's ``27.0`` and JS's ``27`` compare as equal.
    Python and JS both use IEEE 754 doubles and the computation
    sequence is identical, so in practice they agree bit-for-bit —
    rounding to 6 decimals just insulates us from any future
    hypothetical divergence. Stats dicts, mon dicts, and matched-names
    lists are normalized to sorted order so comparison is
    order-independent.
    """
    # Booleans are an int subclass in Python — handle them first so
    # they don't get coerced to 0/1.
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        r = round(float(obj), 6)
        # Collapse whole numbers to int so JS's integer emission matches.
        if r == int(r):
            return int(r)
        return r
    if isinstance(obj, dict):
        return {k: canonicalize(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [canonicalize(x) for x in obj]
    return obj


def canonicalize_record(rec):
    out = {
        'csv_species':   rec['csv_species'],
        'final_species': rec['final_species'],
        'is_pre_evo':    rec['is_pre_evo'],
        'mon':           canonicalize(rec['mon']),
        'stats':         canonicalize(rec['stats']),
        'matched':       sorted(rec['matched']),
    }
    return out


def canonicalize_results(results):
    """Canonicalize and sort the match_mons output for diffing."""
    out = {}
    for sp in sorted(results.keys()):
        recs = [canonicalize_record(r) for r in results[sp]]
        # Sort within-species by (csv_species, atk/def/sta IV, cp) so the
        # order is deterministic regardless of input order.
        recs.sort(key=lambda r: (
            r['csv_species'],
            r['mon']['atk_iv'], r['mon']['def_iv'], r['mon']['sta_iv'],
            r['mon']['cp'],
        ))
        out[sp] = recs
    return out


def build_pokemon_index_subset(thresholds):
    """Build the {species: {atk,def,hp}} subset the JS needs for matching.

    We only need base stats for species that appear as threshold keys —
    walkup targets are always threshold keys by construction. Keeping
    the subset minimal also keeps the node stdin payload small.
    """
    idx = get_pokemon_index()
    out = {}
    for sp in thresholds:
        if sp in idx:
            entry = idx[sp]
            out[sp] = {'atk': entry['atk'], 'def': entry['def'], 'hp': entry['hp']}
    return out


def build_rank_lookup(thresholds, league=HARNESS_LEAGUE,
                      max_level=HARNESS_MAX_LEVEL):
    """Precompute {species: {shadowKey: {ivKey: rank}}} for JS matchMons.

    For every species in ``thresholds`` that exists in the gamemaster,
    emit the non-shadow rank table and — if the species name ends in
    ``(Shadow)`` — the shadow rank table as well. The shape matches
    what the JS matchMons expects (see rankLookup handling in
    deep_dive_user_collection.js).
    """
    idx = get_pokemon_index()
    out = {}
    for sp in thresholds:
        if sp not in idx:
            continue
        is_shadow_species = sp.endswith('(Shadow)')
        ranked = compute_rank_lookup(
            sp, league=league, max_level=max_level, shadow=is_shadow_species)
        shadow_key = 'shadow' if is_shadow_species else 'normal'
        table = {}
        for (a, d, s), rank in ranked.items():
            table[f'{a},{d},{s}'] = rank
        out[sp] = {shadow_key: table}
    return out


def build_pre_to_finals_subset(thresholds):
    """Build the {preSpecies: [final, ...]} subset the JS needs.

    Only include entries whose final forms appear in the threshold dict,
    so the JS receives the minimal map its walkup will consult.
    """
    full = _load_pre_to_finals()
    keep = set(thresholds.keys())
    subset = {}
    for pre, finals in full.items():
        relevant = [f for f in finals if f in keep]
        if relevant:
            subset[pre] = relevant
    return subset


def run_js(payload):
    """Invoke node with the JS harness and return the parsed JSON output.

    The harness reads the payload from stdin as a single JSON blob
    (so we don't have to worry about quoting or temp files), calls the
    JS matchMons, and writes the result back as JSON on stdout.
    """
    js_path = REPO / 'scripts' / 'deep_dive_user_collection.js'
    # Inline JS runner: load the module, inject constants, run matchMons.
    # Keep this brief — anything substantive belongs in the module itself.
    runner = f'''
const mod = require({json.dumps(str(js_path))});
let raw = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {{ raw += chunk; }});
process.stdin.on('end', () => {{
  const payload = JSON.parse(raw);
  mod.setConstants({{
    cpm:            payload.cpm,
    shadowAtkBonus: payload.shadowAtkBonus,
    shadowDefMult:  payload.shadowDefMult,
  }});
  const mons = mod.parseCsvText(payload.csvText);
  const results = mod.matchMons(mons, payload.thresholds, {{
    league:        payload.league,
    maxLevel:      payload.maxLevel,
    pokemonIndex:  payload.pokemonIndex,
    preToFinals:   payload.preToFinals,
    leagueCaps:    payload.leagueCaps,
    rankLookup:    payload.rankLookup,
  }});
  // Report row counts too so we can catch the parse step diverging
  // independently from the match step.
  const parsedCount = mons.length;
  process.stdout.write(JSON.stringify({{parsedCount, results}}));
}});
'''
    proc = subprocess.run(
        ['node', '-e', runner],
        input=json.dumps(payload),
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write('node harness failed:\n')
        sys.stderr.write(proc.stderr)
        sys.exit(2)
    return json.loads(proc.stdout)


def diff_first(py, js, path=''):
    """Return (path, py_val, js_val) for the first divergence, or None."""
    if type(py) is not type(js):
        # dict vs list vs scalar mismatch
        return (path, py, js)
    if isinstance(py, dict):
        pk = sorted(py.keys())
        jk = sorted(js.keys())
        if pk != jk:
            return (path + ' keys', pk, jk)
        for k in pk:
            d = diff_first(py[k], js[k], path + '/' + str(k))
            if d:
                return d
        return None
    if isinstance(py, list):
        if len(py) != len(js):
            return (path + ' len', len(py), len(js))
        for i in range(len(py)):
            d = diff_first(py[i], js[i], path + '[' + str(i) + ']')
            if d:
                return d
        return None
    if py != js:
        return (path, py, js)
    return None


def main():
    fixture = REPO / 'tests' / 'fixtures' / 'poke_genie_export.csv'
    if not fixture.exists():
        print(f'Fixture not found: {fixture}', file=sys.stderr)
        print('Drop a Poke Genie CSV export there to run the harness.',
              file=sys.stderr)
        print('(The fixture is gitignored — personal collection data.)',
              file=sys.stderr)
        return 2

    csv_text = fixture.read_text(encoding='utf-8-sig')

    # Python side.
    py_mons = parse_csv_text(csv_text)
    py_results = match_mons(py_mons, TEST_THRESHOLDS, league=HARNESS_LEAGUE,
                            max_level=HARNESS_MAX_LEVEL)
    py_canon = canonicalize_results(py_results)
    print(f'Python: parsed {len(py_mons)} mons, '
          f'matched {sum(len(v) for v in py_results.values())} across '
          f'{len(py_results)} species')

    # JS side.
    payload = {
        'csvText':        csv_text,
        'thresholds':     TEST_THRESHOLDS,
        'pokemonIndex':   build_pokemon_index_subset(TEST_THRESHOLDS),
        'preToFinals':    build_pre_to_finals_subset(TEST_THRESHOLDS),
        'rankLookup':     build_rank_lookup(TEST_THRESHOLDS),
        'cpm':            {str(k): v for k, v in CPM.items()},
        'shadowAtkBonus': SHADOW_ATK_BONUS,
        'shadowDefMult':  SHADOW_DEF_MULT,
        'leagueCaps':     LEAGUE_CAPS,
        'league':         HARNESS_LEAGUE,
        'maxLevel':       HARNESS_MAX_LEVEL,
    }
    js_out = run_js(payload)
    js_results = js_out['results']
    js_canon = canonicalize_results(js_results)
    print(f'JS:     parsed {js_out["parsedCount"]} mons, '
          f'matched {sum(len(v) for v in js_results.values())} across '
          f'{len(js_results)} species')

    # Parse-count sanity check first — a mismatch here means the CSV
    # parsers diverged and the matching diff would be noise.
    if len(py_mons) != js_out['parsedCount']:
        print(f'\nFAIL: parse count mismatch '
              f'(py={len(py_mons)} vs js={js_out["parsedCount"]})',
              file=sys.stderr)
        return 1

    # Deep-diff the canonicalized results.
    diff = diff_first(py_canon, js_canon)
    if diff is None:
        total = sum(len(v) for v in py_canon.values())
        print(f'\nPASS: Python and JS agree on all {total} matched records '
              f'across {len(py_canon)} species.')
        return 0

    path, py_val, js_val = diff
    print(f'\nFAIL at {path}', file=sys.stderr)
    print(f'  python: {py_val!r}', file=sys.stderr)
    print(f'  js:     {js_val!r}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
