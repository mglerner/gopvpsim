"""Moveset rules for the website dive registry (dive_registry "MOVESET RULES").

Pre-fix state (recorded 2026-09-11, before the rules): DIVE_OVERRIDES held 42
per-slug ``top_movesets`` values (35 of them 1); Sableye rendered 1 moveset
and Shadow Sableye 4, so the two pages shared no moveset; Cradily / Shadow
Cradily were 1 vs 5. ``build_command`` emitted no union flags.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import dive_registry as dr  # noqa: E402
import run_website_dives as rwd  # noqa: E402
from deep_dive_lib.sweep import union_movesets  # noqa: E402


@pytest.fixture(scope='module')
def dives():
    return dr.all_dives()


def _by_slug(dives, slug):
    hits = [d for d in dives if d['slug'] == slug]
    assert len(hits) == 1, slug
    return hits[0]


# ---- rule 1: one moveset count for every dive --------------------------------

def test_no_dive_carries_a_per_slug_moveset_count(dives):
    # Pre-fix: 42 overrides set top_movesets (35 of them 1).
    assert not any('top_movesets' in v for v in dr.DIVE_OVERRIDES.values())
    assert not any('top_movesets' in d for d in dives)
    assert not any('top_movesets' in e for e in dr.EXTRA_DIVES)


def test_every_command_uses_the_one_default_count(dives):
    for d in dives:
        cmd = rwd.build_command(d, dives)
        assert cmd[cmd.index('--top-movesets') + 1] == str(dr.DEFAULT_TOP_MOVESETS), d['slug']


def test_shadow_sableye_is_no_longer_pinned_to_foul_play_pairs():
    # The pin existed to cap the 2026-06-02 three-dive collapse at 4 pages;
    # under rule 1 the screen picks its own top set, and the pin would keep
    # the shadow page from pairing with the unpinned plain page (rule 3).
    ovr = dr.DIVE_OVERRIDES['shadow-sableye-great-league']
    assert 'extra_args' not in ovr
    assert ovr['reference'] == 'SHADOW_CLAW,DRAIN_PUNCH,FOUL_PLAY'


# ---- rule 3: shadow/plain pairs ---------------------------------------------

def test_sableye_pair_resolves_both_ways(dives):
    plain = _by_slug(dives, 'sableye-great-league')
    shadow = _by_slug(dives, 'shadow-sableye-great-league')
    assert dr.pair_partner(plain, dives) is shadow
    assert dr.pair_partner(shadow, dives) is plain


def test_cradily_pairs_despite_the_plain_side_fast_pin(dives):
    # One side pinned, the other unpinned: still a pair (the shadow page
    # gains the Acid set; the plain page gains the shadow screen's set).
    plain = _by_slug(dives, 'cradily-great-league')
    shadow = _by_slug(dives, 'shadow-cradily-great-league')
    assert dr.pair_partner(plain, dives) is shadow
    assert dr.pair_partner(shadow, dives) is plain


def test_forretress_fast_move_pages_pair_only_like_with_like(dives):
    # Shadow Forretress is not in the GL pool, so the only shadow Forretress
    # GL page is the EXTRA_DIVES bug-bite one. It must pair with the plain
    # bug-bite page (same --fast pin) and NOT with the volt-switch page,
    # which is left without a partner.
    vs = _by_slug(dives, 'forretress-volt-switch-great-league')
    bb = _by_slug(dives, 'forretress-bug-bite-great-league')
    bb_sh = _by_slug(dives, 'forretress-shadow-bug-bite-great-league')
    assert dr.pair_partner(bb, dives) is bb_sh
    assert dr.pair_partner(bb_sh, dives) is bb
    assert dr.pair_partner(vs, dives) is None


def test_every_pair_is_symmetric_and_unique(dives):
    n_pairs = 0
    for d in dives:
        p = dr.pair_partner(d, dives)
        if p is None:
            continue
        n_pairs += 1
        assert dr.pair_partner(p, dives) is d, (d['slug'], p['slug'])
        assert bool(p.get('shadow')) != bool(d.get('shadow'))
    # Floor set below today's count (2 x 30 pairs on 2026-09-11); a registry
    # that silently stopped pairing would trip this.
    assert n_pairs >= 40


def test_union_flags_mirror_the_partner_pins(dives):
    plain = _by_slug(dives, 'sableye-great-league')
    shadow = _by_slug(dives, 'shadow-sableye-great-league')
    c_plain = rwd.build_command(plain, dives)
    c_shadow = rwd.build_command(shadow, dives)
    assert c_plain[c_plain.index('--union-with-form') + 1] == 'shadow'
    assert c_shadow[c_shadow.index('--union-with-form') + 1] == 'plain'
    # Shadow Sableye's reference is pinned; the plain page must screen the
    # partner under THAT reference to reproduce the shadow page's set.
    assert c_plain[c_plain.index('--union-reference') + 1] == 'SHADOW_CLAW,DRAIN_PUNCH,FOUL_PLAY'
    assert c_shadow[c_shadow.index('--union-reference') + 1] == 'auto'
    assert '--union-fast' not in c_plain and '--union-fast' not in c_shadow
    # Cradily: the plain side is pinned, so the shadow command carries its pins.
    c_cr_sh = rwd.build_command(_by_slug(dives, 'shadow-cradily-great-league'), dives)
    assert c_cr_sh[c_cr_sh.index('--union-fast') + 1] == 'ACID'
    assert c_cr_sh[c_cr_sh.index('--union-charged') + 1] == 'GRASS_KNOT,ROCK_TOMB'


def test_unpaired_dive_gets_no_union_flags(dives):
    solo = _by_slug(dives, 'tinkaton-great-league')
    assert dr.pair_partner(solo, dives) is None
    assert '--union-with-form' not in rwd.build_command(solo, dives)


def test_build_command_without_registry_list_is_unchanged(dives):
    # Callers that pass only the dive (older call shape) get no union flags.
    plain = _by_slug(dives, 'sableye-great-league')
    assert '--union-with-form' not in rwd.build_command(plain)


# ---- the union itself --------------------------------------------------------

def test_union_keeps_own_order_and_appends_partner_only_sets():
    own = [('SHADOW_CLAW', ['DRAIN_PUNCH', 'FOUL_PLAY']),
           ('SHADOW_CLAW', ['FOUL_PLAY', 'POWER_GEM'])]
    partner = [('SHADOW_CLAW', ['POWER_GEM', 'FOUL_PLAY']),   # same set, other order
               ('FEINT_ATTACK', ['FOUL_PLAY']),
               ('SHADOW_CLAW', ['DAZZLING_GLEAM', 'FOUL_PLAY'])]
    out = union_movesets(own, partner)
    assert out[:2] == own
    assert out[2:] == [('FEINT_ATTACK', ['FOUL_PLAY']),
                       ('SHADOW_CLAW', ['DAZZLING_GLEAM', 'FOUL_PLAY'])]


def test_union_with_empty_partner_is_identity():
    own = [('SHADOW_CLAW', ['DRAIN_PUNCH', 'FOUL_PLAY'])]
    assert union_movesets(own, []) == own
