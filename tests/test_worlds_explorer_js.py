"""IV-explorer Python<->JS parity + damage-constant absence scan.

Parity is against the ENGINE, not a mirrored readout: for each sampled
(species, IVs, level) the JS ladder read-out (tier reached / tier
taken) must equal worlds_tier0.staged_damage evaluated directly at the
same effective stats -- so a wrong cutoff in the DATA blob, a wrong
comparison in JS, or stat-math drift all fail the same test. Stats are
compared bit-exact (both sides are binary64 with identical operand
order).

The scan half pins the design decision that closed the damage-constant
drift class: worlds_iv_explorer.js contains NO numeric damage
constants at all (float32 family or exact), and delegates stat math to
POGOCollection (spelling pinned). Positive control per testing policy.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_win_boundary import strip_js  # noqa: E402

JS_PATH = REPO / 'scripts' / 'worlds_iv_explorer.js'
POGO_JS = REPO / 'scripts' / 'deep_dive_user_collection.js'

needs_node = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node not installed')

CASES = [
    # (species_id, a, d, s, level-or-None)
    ('tinkaton', 1, 14, 14, None),          # its rank-1 SP spread
    ('tinkaton', 12, 6, 11, None),          # DragapultSim's atk build
    ('quagsire_shadow', 0, 14, 14, None),   # shadow, auto level
    ('lickilicky', 15, 15, 15, 20.0),       # manual level, hundo
    ('mantine', 0, 15, 7, None),            # the deny anchor spread
    ('fearow', 15, 0, 0, 25.5),             # glassy manual half-level
]


@pytest.fixture(scope='module')
def data_blob():
    import worlds_explorer_data as wed
    return wed.build_data()


@pytest.fixture(scope='module')
def js_results(data_blob, tmp_path_factory):
    if shutil.which('node') is None:
        pytest.skip('node not installed')
    tmp = tmp_path_factory.mktemp('explorer')
    data_file = tmp / 'data.json'
    data_file.write_text(json.dumps(data_blob))
    runner = f"""
const fs = require('fs');
const POGO = require({json.dumps(str(POGO_JS))});
const WorldsIV = require({json.dumps(str(JS_PATH))});
const DATA = JSON.parse(fs.readFileSync({json.dumps(str(data_file))}));
WorldsIV.init(DATA, POGO);
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = cases.map(c => WorldsIV.evaluate(c[0], c[1], c[2], c[3], c[4]));
process.stdout.write(JSON.stringify(out));
"""
    proc = subprocess.run(['node', '-e', runner],
                          input=json.dumps(CASES),
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _py_stats(data_blob, sid, a, d, s, level):
    """Python reference via the library's own path (the same one
    iv_rank/user_collection use), NOT a re-derivation."""
    from gopvpsim.pokemon import (Pokemon, battle_stats, effective_stats,
                                  get_species)
    e = data_blob['entries'][sid]
    if level is None:
        pk = Pokemon.at_best_level(e['species'], a, d, s, league='great',
                                   shadow=e['shadow'])
        atk, def_ = pk.atk, pk.def_
        return pk.level, atk, def_, pk.hp
    base = get_species(e['species'])
    st = battle_stats(base['atk'], base['def'], base['hp'], a, d, s, level)
    atk, def_ = effective_stats(st['atk'], st['def'], e['shadow'])
    return level, atk, def_, st['hp']


@needs_node
def test_stats_parity_bit_exact(data_blob, js_results):
    for case, js in zip(CASES, js_results):
        sid, a, d, s, level = case
        lv, atk, def_, hp = _py_stats(data_blob, sid, a, d, s, level)
        assert js['level'] == lv, case
        assert js['attack'] == atk, case      # bit-exact, no approx
        assert js['defense'] == def_, case
        assert js['stamina'] == hp, case


@needs_node
def test_ladder_readouts_match_engine_damage(data_blob, js_results):
    import worlds_tier0 as t0
    from gopvpsim.moves import get_moves
    fast_db, charged_db = get_moves()
    moves = {**fast_db, **charged_db}
    n_checked = 0
    tiers_seen = set()
    oor_seen = 0
    for case, js in zip(CASES, js_results):
        sid, a, d, s, level = case
        _lv, atk, def_, _hp = _py_stats(data_blob, sid, a, d, s, level)
        me = data_blob['entries'][sid]
        # Out-of-range flags must fire exactly when the stat leaves the
        # baked ladder range (the Fearow @25.5 silent-clamp case).
        assert js['atkOutOfRange'] == (
            not me['atk_range'][0] <= atk <= me['atk_range'][1]), case
        assert js['defOutOfRange'] == (
            not me['def_range'][0] <= def_ <= me['def_range'][1]), case
        for opp_id, verdict in js['opponents'].items():
            opp = data_blob['entries'][opp_id]
            if verdict.get('excluded'):
                assert opp['excluded'] or me['excluded']
                continue
            if verdict['bp'] is None:
                assert js['atkOutOfRange'], case
                oor_seen += 1
            if verdict['bulk'] is None:
                assert js['defOutOfRange'], case
                oor_seen += 1
            for row in verdict['bp'] or []:
                want = t0.staged_damage(dict(moves[row['move']]), atk,
                                        opp['anchor']['def'],
                                        me['types'], opp['types'])
                assert row['tier'] == want, (case, opp_id, row)
                n_checked += 1
                tiers_seen.add(want)
            for row in verdict['bulk'] or []:
                want = t0.staged_damage(dict(moves[row['move']]),
                                        opp['anchor']['atk'], def_,
                                        opp['types'], me['types'])
                assert row['taken'] == want, (case, opp_id, row)
                n_checked += 1
                tiers_seen.add(want)
    # Non-triviality (testing policy): many comparisons, varied tiers,
    # and the out-of-range path actually exercised (the Fearow case).
    assert n_checked >= 500
    assert len(tiers_seen) >= 10
    assert oor_seen >= 1


@needs_node
def test_excluded_pairs_marked(js_results):
    # Every case must mark the Aegislash opponent excluded, never a
    # silent ladder.
    for js in js_results:
        assert js['opponents']['aegislash_shield'] == {'excluded': True}


def test_js_has_no_damage_constants():
    """The whole point of the baked-cutoff design: no damage constant
    may appear in the explorer JS. Tolerant scan + positive control."""
    import re
    stripped = strip_js(JS_PATH.read_text())
    banned = ['0.5', '1.3', '1.6', '1.2999999', '1.2000000', '1.6000000',
              '0.390625', '0.625']
    hits = []
    for tok in re.findall(r'(?<![\w.])\d+\.\d+(?![\w])', stripped):
        if any(tok.startswith(b) for b in banned):
            hits.append(tok)
    # '1.0' appears legitimately (identity multipliers); the banned list
    # deliberately excludes it.
    assert not hits, hits
    # Positive control: the scanner sees a planted constant.
    planted = stripped + '\nvar BONUS = 1.2999999523162841796875;'
    assert any(t.startswith('1.2999999')
               for t in re.findall(r'(?<![\w.])\d+\.\d+(?![\w])', planted))
    # Delegation pin: stat math goes through POGOCollection, not a
    # local reimplementation.
    assert 'ivsToStatsAtCap' in stripped
    assert 'setConstants' in stripped
