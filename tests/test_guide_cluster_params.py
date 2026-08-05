"""The matchup-clusters guide quotes cluster knobs, never hand-typed copies.

``scripts/deep_dive_matchup_clusters.py`` owns the sharp-marginal window, the
K range, the silhouette epsilon and the weak-separation cutoff. The guide body
reaches them through ``{{mc:...}}`` tokens resolved by
``scripts/build_guides.py``; these tests pin that seam so a knob change can't
leave the guide (or the in-page note) quoting a dead number.
"""
import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDE_BODY = REPO_ROOT / 'guides' / 'matchup-clusters' / 'body.md'


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bg = _load('build_guides_under_test', 'scripts/build_guides.py')
mc = _load('mc_under_test', 'scripts/deep_dive_matchup_clusters.py')


def _resolve(body):
    return bg._resolve_tokens(body, {}, dive=None, dev_counts={},
                              guide_slug='matchup-clusters')


def test_mc_tokens_resolve_to_the_module_constants():
    body = ('{{mc:sharp_lo_pct}}|{{mc:sharp_hi_pct}}|{{mc:kmin}}|'
            '{{mc:kmax}}|{{mc:sil_epsilon}}|{{mc:weak_sil}}')
    resolved, unresolved = _resolve(body)
    assert unresolved == []
    p = mc.cluster_params()
    assert resolved == '|'.join([
        p['sharp_lo_pct'], p['sharp_hi_pct'], p['kmin'],
        p['kmax'], p['sil_epsilon'], p['weak_sil']])
    # and those strings really are the constants, not a second hand-typed set
    assert p['sharp_lo_pct'] == f'{mc.SHARP_LO * 100:g}'
    assert p['sharp_hi_pct'] == f'{mc.SHARP_HI * 100:g}'
    assert p['kmin'] == str(mc.KMIN) and p['kmax'] == str(mc.KMAX)
    assert p['sil_epsilon'] == f'{mc.SIL_EPSILON:g}'
    assert p['weak_sil'] == f'{mc.WEAK_SIL:.2f}'


def test_unknown_mc_token_is_reported_unresolved():
    resolved, unresolved = _resolve('{{mc:no_such_knob}}')
    assert unresolved == ['matchup-clusters:mc:no_such_knob']
    assert '{{mc:no_such_knob}}' in resolved   # left intact for the hard-fail


def test_guide_body_mc_tokens_all_resolve():
    body = GUIDE_BODY.read_text()
    used = set(re.findall(r'\{\{\s*(mc:[^}]+?)\s*\}\}', body))
    assert used, 'the guide should quote the knobs through mc: tokens'
    _, unresolved = _resolve(body)
    assert [u for u in unresolved if u.startswith('matchup-clusters:mc:')] == []


def test_guide_body_does_not_hand_type_the_knob_values():
    body = GUIDE_BODY.read_text()
    for literal in ('2% and 98%', '(2 through 6)', '(0.03)', 'below 0.30'):
        assert literal not in body, (
            f'{literal!r} is a hand-typed copy of a cluster knob; use an '
            'mc: token so it tracks deep_dive_matchup_clusters.py')
