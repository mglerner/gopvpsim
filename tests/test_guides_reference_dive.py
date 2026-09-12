"""The reader guides' worked example must point at a dive we still bake.

Regression test for the publish blocker found 2026-09-12. `build_guides.py`
carried `DEFAULT_REFERENCE = {... 'oinkologne-female-great-league'}`, a plain
string with nothing tying it to the dive registry. The Twilight Trails
dive-list rebuild retired that dive, so every `dive:top_tier_*` token resolved
to None, `build_guides.py` hard-failed on unresolved tokens, and
`publish_website.sh` aborted before rsync -- with the failure surfacing as an
opaque token list rather than "your reference dive no longer exists".

Pre-fix value recorded: `_dive_data('oinkologne-female-great-league')` returned
None, and `_resolve_dive_token('top_tier_name', None)` returned None.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

import build_guides as bg  # noqa: E402
from dive_registry import all_dives  # noqa: E402

# Every token guides/*/body.md interpolates off the reference dive's top tier.
# The prose in guides/threshold-tiers/body.md reads "cuts on bulk: def >= X
# with an HP floor of Y", so BOTH cutoffs must be non-None -- a dive whose top
# tier has no HP floor renders "an HP floor of `0`".
_TOP_TIER_TOKENS = (
    'top_tier_name',
    'top_tier_def_cutoff',
    'top_tier_sta_cutoff',
    'top_tier_clear_count',
    'iv_space_size',
    'tier_count',
)


def test_reference_dive_is_in_the_dive_registry():
    """The slug must name a dive the chain actually bakes."""
    slug = bg.DEFAULT_REFERENCE['dive_slug']
    slugs = {d['slug'] for d in all_dives()}
    assert slug in slugs, (
        f'guides reference dive {slug!r} is not in the dive registry, so the '
        f'chain will not bake it and every dive: token will resolve to None')


@pytest.mark.local_artifacts
def test_reference_dive_resolves_every_top_tier_token():
    """The built dive must carry threshold tiers, not just exist.

    Registry membership is necessary but not sufficient: a dive baked with
    --no-thresholds has `movesets[0]['tiers'] == []`, and the resolver's
    `if not tiers: return None` then fails every top_tier_* token.
    """
    slug = bg.DEFAULT_REFERENCE['dive_slug']
    if not (REPO / 'userdata' / 'website' / slug / 'index.html').exists():
        pytest.skip(f'no locally built {slug}')
    dive = bg._dive_data(slug)
    assert dive is not None, f'{slug} built but _dive_data returned None'
    unresolved = [t for t in _TOP_TIER_TOKENS
                  if bg._resolve_dive_token(t, dive) is None]
    assert unresolved == [], (
        f'{slug} cannot fill {unresolved} -- build_guides.py will hard-fail '
        f'on unresolved tokens and block the publish')


@pytest.mark.local_artifacts
def test_reference_dive_top_tier_has_a_real_hp_floor():
    """Guards the prose, not just the token.

    A sta_cutoff of 0 resolves fine (so the test above passes) but renders
    "with an HP floor of `0`", which reads as a bug to a human. Altaria and
    Azumarill both resolve every token yet carry sta 0; Corviknight was chosen
    over them for exactly this reason.
    """
    slug = bg.DEFAULT_REFERENCE['dive_slug']
    if not (REPO / 'userdata' / 'website' / slug / 'index.html').exists():
        pytest.skip(f'no locally built {slug}')
    dive = bg._dive_data(slug)
    for token in ('top_tier_def_cutoff', 'top_tier_sta_cutoff'):
        value = bg._resolve_dive_token(token, dive)
        assert value is not None and float(value) > 0, (
            f'{slug} top tier has {token}={value}; the threshold-tiers guide '
            f'prose names both a def cutoff and an HP floor')
