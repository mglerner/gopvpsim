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
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

import build_guides as bg  # noqa: E402
from dive_registry import all_dives  # noqa: E402

# Every token guides/*/body.md interpolates off the reference dive's top tier.
# The prose now reads "cuts on <axes>: <rule>" off `top_tier_axes` /
# `top_tier_rule`, which print only the axes the tier actually cuts on, so no
# single dive-shape (bulk tier vs attack tier) is required of the reference.
_TOP_TIER_TOKENS = (
    'top_tier_name',
    'top_tier_axes',
    'top_tier_rule',
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
def test_reference_dive_top_tier_rule_prints_only_real_cutoffs():
    """Guards the prose, not just the token.

    A cutoff of 0 means "this tier does not cut on that axis". It resolves
    fine (so the token test above passes) but renders as a real-looking
    threshold to a human.

    Pre-fix values recorded (2026-09-22 bake, Corviknight GL top tier
    "Aegislash (Shield) Slayer" = atk 112.79 / def 0 / sta 142): the guide
    hardcoded the axes, `top_tier_def_cutoff` resolved to `0`, and the
    rendered page read `The top card - Aegislash (Shield) Slayer - cuts on
    bulk: def &ge; 0 with an HP floor of 142.00`. The atk cutoff the tier
    really carries was not printed at all. No Great League dive in that bake
    had all three cutoffs nonzero, so no reference swap could fix it.
    """
    slug = bg.DEFAULT_REFERENCE['dive_slug']
    if not (REPO / 'userdata' / 'website' / slug / 'index.html').exists():
        pytest.skip(f'no locally built {slug}')
    dive = bg._dive_data(slug)
    rule = bg._resolve_dive_token('top_tier_rule', dive)
    assert rule, f'{slug} top tier resolved no rule at all'

    clauses = re.findall(r'(atk|def|HP) >= ([0-9.]+)', rule)
    assert len(clauses) == len(rule.split(' and ')), (
        f'top_tier_rule {rule!r} has a clause that is not "<axis> >= <value>"')
    assert clauses, f'top_tier_rule {rule!r} names no cutoff'
    zeros = [c for c in clauses if float(c[1]) == 0]
    assert not zeros, (
        f'top_tier_rule {rule!r} prints a zero cutoff {zeros}; a zero means '
        f'the tier does not cut on that axis and must not be rendered')

    # And the sentence the rule lands in must not reintroduce a hardcoded
    # axis: resolve the real guide body and scan the rendered text.
    body = (REPO / 'guides' / 'threshold-tiers' / 'body.md').read_text()
    resolved, unresolved = bg._resolve_tokens(
        body, {}, dive=dive, dev_counts={}, guide_slug='threshold-tiers')
    assert unresolved == [], f'threshold-tiers has unresolved tokens: {unresolved}'
    bad = re.findall(r'(?:atk|def|hp|HP)\s*(?:>=|&ge;|\u2265)\s*0(?![0-9.])',
                     resolved)
    assert not bad, (
        f'rendered threshold-tiers guide prints a zero cutoff: {bad}')
    assert re.search(r'(?:atk|def|HP) >= [0-9.]*[1-9]', resolved), (
        'rendered threshold-tiers guide names no nonzero cutoff -- the '
        'positive control for the scan above')
