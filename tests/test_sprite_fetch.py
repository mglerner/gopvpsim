"""Dive-card sprite lookup (gopvpsim.data.sprite_data_uri).

The 2026-09-26 chain printed 'Sprite fetch error for cramorant.png: HTTP
Error 404: Not Found' once per split page (15 lines over Cramorant's three
dives; Spidops the same, 5). Not a naming bug:
the slug and URL follow the same pokemondb GO pattern as every species whose
sprite loads, pokemondb's GO set just has no Cramorant, and the HOME
fallback supplied the sprite (the rendered Cramorant GL/UL pages embed
cramorant-home.png). The noise was a bare print() from _fetch_bytes on
every card render, and the card renders once per split page.

Pre-fix (until 2026-09-27): two sprite_data_uri('Cramorant') calls printed
that line twice to stdout and tried the dead GO URL twice. Now: one WARNING
through the caller's logger, no stdout, one GO attempt per process.
No network: urlopen is faked and CACHE_DIR points at tmp_path.
"""
import io
import urllib.error
import urllib.request

import pytest

from gopvpsim import data

GO = 'https://img.pokemondb.net/sprites/go/normal/{}.png'
HOME = 'https://img.pokemondb.net/sprites/home/normal/{}.png'


def test_cramorant_urls_follow_the_pattern_of_a_sprite_that_loads():
    """Azumarill's GO sprite loads (azumarill.png is embedded in its
    rendered page); Cramorant's first URL is the same pattern with its own
    slug, i.e. the 404 is not a slug / filename construction bug."""
    azu = data._sprite_sources('Azumarill')
    cram = data._sprite_sources('Cramorant')
    assert azu[0] == ('azumarill.png', GO.format('azumarill'))
    assert cram[0] == ('cramorant.png', GO.format('cramorant'))
    assert cram[1] == ('cramorant-home.png', HOME.format('cramorant'))


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.fixture
def fake_net(tmp_path, monkeypatch):
    """urlopen that 404s every URL in ``missing`` and serves the URL as
    bytes otherwise; records every requested URL."""
    monkeypatch.setattr(data, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(data, '_SPRITE_MEMO', {})
    state = {'missing': set(), 'calls': []}

    def urlopen(req, context=None, timeout=None):
        url = req.full_url
        state['calls'].append(url)
        if url in state['missing']:
            raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
        return _Resp(url.encode())

    monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
    return state


def test_a_go_set_404_warns_once_and_never_prints(fake_net, capsys):
    fake_net['missing'] = {GO.format('cramorant')}
    warnings = []
    first = data.sprite_data_uri('Cramorant', warn=warnings.append)
    second = data.sprite_data_uri('Cramorant', warn=warnings.append)
    assert first and first == second
    assert first.startswith('data:image/png;base64,')
    assert capsys.readouterr().out == ''
    assert len(warnings) == 1, warnings
    assert '404' in warnings[0]
    assert 'sprite from ' + HOME.format('cramorant') in warnings[0]
    assert fake_net['calls'].count(GO.format('cramorant')) == 1


def test_no_sprite_at_all_degrades_to_none_with_one_warning(fake_net,
                                                            capsys):
    fake_net['missing'] = {GO.format('cramorant'), HOME.format('cramorant')}
    warnings = []
    assert data.sprite_data_uri('Cramorant', warn=warnings.append) is None
    assert data.sprite_data_uri('Cramorant', warn=warnings.append) is None
    assert capsys.readouterr().out == ''
    assert len(warnings) == 1 and 'typing-colored' in warnings[0], warnings


def test_a_loading_sprite_is_silent(fake_net, capsys):
    """Positive control: the GO pattern that works stays warning-free."""
    warnings = []
    assert data.sprite_data_uri('Azumarill', warn=warnings.append)
    assert warnings == [] and capsys.readouterr().out == ''
    assert fake_net['calls'] == [GO.format('azumarill')]


def test_a_network_failure_with_a_stale_copy_says_so(fake_net, tmp_path):
    """The 09-26 chain also hit DNS failures (tinkaton / virizion /
    zygarde-complete); _fetch_bytes then serves the expired cached copy,
    and the warning must say so rather than imply a fresh fetch."""
    (tmp_path / 'sprites').mkdir()
    old = tmp_path / 'sprites' / 'tinkaton.png'
    old.write_bytes(b'stale')
    import os
    os.utime(old, (0, 0))   # far past CACHE_TTL
    fake_net['missing'] = {GO.format('tinkaton')}
    warnings = []
    uri = data.sprite_data_uri('Tinkaton', warn=warnings.append)
    assert uri and uri.endswith('c3RhbGU=')   # base64(b'stale')
    assert len(warnings) == 1 and 'stale cached copy' in warnings[0]


def test_default_warn_goes_to_the_module_logger(fake_net, caplog):
    fake_net['missing'] = {GO.format('cramorant')}
    with caplog.at_level('WARNING', logger='gopvpsim.data'):
        assert data.sprite_data_uri('Cramorant')
    assert [r.levelname for r in caplog.records] == ['WARNING']
