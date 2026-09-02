"""The three Mega League editions must route as three cups over ONE rankings file.

PvPoke's cup <-> format cardinality is not 1:1 and this is the first place it
bites. The gamemaster has:

  * ONE cup named "mega", whose title is literally "All Pokemon" -- its roster
    is NOT restricted to megas;
  * THREE formats over it -- Mega Great / Ultra / Master League at cp
    1500 / 2500 / 10000;
  * ONE rankings directory, rankings/mega/overall/rankings-<cp>.json.

Our registry key has to be per-league (``dive_league`` holds one league, and
``cup_slug_suffix`` would collide across the three), so the three keys carry a
``rankings_cup`` pointing back at the single "mega" cup.
"""
import pytest

from gopvpsim.data import (CUP_REGISTRY, cup_dive_league, cup_pretty_name,
                           cup_rankings_key, cup_slug_suffix,
                           get_default_moveset, get_rankings_for,
                           load_gamemaster, rankings_cache_path)

MEGA_CUPS = {
    'megagreat':  ('great',  1500,  'Mega Great League'),
    'megaultra':  ('ultra',  2500,  'Mega Ultra League'),
    'megamaster': ('master', 10000, 'Mega Master League'),
}


@pytest.mark.parametrize('key', sorted(MEGA_CUPS))
def test_registry_row_matches_the_gamemaster_format(key):
    """Display name and CP come from PvPoke's own formats array, not from us."""
    league, cp, title = MEGA_CUPS[key]
    assert cup_dive_league(key) == league
    assert cup_pretty_name(key) == title
    assert cup_rankings_key(key) == 'mega'
    assert cup_slug_suffix(key) == f'{key}-cup'

    fmts = [f for f in load_gamemaster().get('formats', [])
            if f.get('cup') == 'mega' and f.get('cp') == cp]
    assert len(fmts) == 1, f'expected one mega format at cp {cp}, got {fmts}'
    assert fmts[0]['title'] == title, fmts[0]['title']


def test_all_three_editions_share_one_rankings_cup_and_cache_path():
    """One upstream file per CP, reached through three of our keys."""
    for key, (league, cp, _) in MEGA_CUPS.items():
        assert rankings_cache_path(league, key).name == f'rankings_mega_{cp}.json'
    # the bare "mega" key still works and lands on the same file
    assert rankings_cache_path('ultra', 'mega').name == 'rankings_mega_2500.json'
    # ...and the three do NOT collide with each other, because the CP differs
    paths = {rankings_cache_path(lg, k).name for k, (lg, _, _) in MEGA_CUPS.items()}
    assert len(paths) == 3, paths


@pytest.mark.parametrize('key', sorted(MEGA_CUPS))
def test_rankings_resolve_and_carry_megas(key):
    league, cp, _ = MEGA_CUPS[key]
    r = get_rankings_for(league, cup=key)
    assert len(r) > 100, len(r)
    megas = [e for e in r if '_mega' in e['speciesId']
             or e['speciesId'].endswith('_primal')]
    assert len(megas) >= 40, len(megas)
    # ...and the file is NOT a mega-only roster: its title is "All Pokemon"
    assert len(r) > 5 * len(megas), (
        'the mega rankings look mega-only; the cup is titled "All Pokemon" '
        'and should carry the whole meta as opponents')


def test_supermegas_get_three_charged_moves_through_the_real_path():
    """get_default_moveset returns THREE charged moves for a mega-move holder.

    This is the path a dive actually takes, so it is the one that has to be
    right -- the fourth element of PvPoke's moveset array is the `*_PLUS` move.
    """
    fast, charged = get_default_moveset('Skarmory (Mega)', league='great',
                                        cup='megagreat')
    assert fast == 'AIR_SLASH'
    assert len(charged) == 3, charged
    assert charged[-1].endswith('_PLUS'), charged

    # positive control: an ordinary species in the SAME cup still gets two
    _, azu = get_default_moveset('Azumarill', league='great', cup='megagreat')
    assert len(azu) == 2, azu


def test_gl_excludes_are_honoured_upstream():
    """Five species are banned at 1500 only; recorded so a roster build knows.

    Asserted against the gamemaster rather than a hand list, so it tracks
    upstream. This is a fact-pin, not a behaviour test -- we do not yet build
    mega rosters, and whoever does must apply it.
    """
    cups = [c for c in load_gamemaster().get('cups', []) if c.get('name') == 'mega']
    assert len(cups) == 1, cups
    excl = cups[0].get('exclude') or []
    banned = {v for e in excl if 1500 in (e.get('leagues') or [])
              for v in (e.get('values') or [])}
    assert 'mewtwo_mega_x' in banned and 'mewtwo_mega_y' in banned, banned
    assert len(banned) >= 5, banned


def test_mega_editions_are_reported_live_not_archived():
    """Regression: keying active formats by cup alone collapsed all three.

    All three share cup=='mega', so a cup-keyed dict kept only the last and
    the other two rendered a false "archived snapshot" line on the cup index.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from build_website_index import _cup_active_formats, _cup_status_line

    af = _cup_active_formats()
    mega = {k: v for k, v in af.items() if k[0] == 'mega'}
    assert len(mega) == 3, f'expected 3 live mega formats, got {mega}'
    for key in MEGA_CUPS:
        line = _cup_status_line(key, af)
        assert 'archived snapshot' not in line, f'{key}: {line}'
        assert 'Currently active' in line, f'{key}: {line}'


def test_every_registered_cup_has_a_resolvable_rankings_key():
    """Guard the indirection: no cup may point at a rankings key we cannot use."""
    for key in CUP_REGISTRY:
        rk = cup_rankings_key(key)
        assert isinstance(rk, str) and rk, key
        # a rankings_cup, when set, must itself be a registered cup
        info = CUP_REGISTRY[key]
        if info.rankings_cup:
            assert info.rankings_cup in CUP_REGISTRY, (key, info.rankings_cup)
