"""Dated-snapshot article archiving (docs/article_archive_plan.md).

The pattern: the BARE slug is always the current article; archiving
copies it to "<slug>-<vintage>" and marks the copy. These pin the two
halves that can silently go wrong -- the copy never mutating the
original, and an archived entry never leaking into the LIVE listings
(especially the ML-IV-guide chip row, whose split matches
'-ml-iv-guide' as a substring).
"""
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from archive_article import archive_slug  # noqa: E402
import build_website_index as bwi  # noqa: E402

META = ('title       = "Playing Cramorant"\n'
        'description = "A strategy article."\n'
        'authorship  = "both"\n'
        'landing     = "index.html"\n')


def _make_article(root, slug, meta=META):
    d = root / slug
    d.mkdir(parents=True)
    (d / 'meta.toml').write_text(meta)
    (d / 'index.html').write_text('<html><title>Playing Cramorant</title></html>')
    return d


def test_archive_copies_and_leaves_the_original_untouched(tmp_path):
    src = _make_article(tmp_path, 'cramorant-strategy')
    dest = archive_slug('cramorant-strategy', '2026-08-31',
                        stamp='c431557dcc76', articles_dir=tmp_path)

    assert dest.name == 'cramorant-strategy-2026-08-31'
    assert (dest / 'index.html').exists()
    # The bare slug is what inbound links point at -- it must not move,
    # change, or acquire an [archive] marker.
    assert src.is_dir()
    assert (src / 'meta.toml').read_text() == META

    text = (dest / 'meta.toml').read_text()
    assert '[archive]' in text
    assert 'of      = "cramorant-strategy"' in text
    assert 'vintage = "2026-08-31"' in text
    assert 'stamp   = "c431557dcc76"' in text
    # The copy keeps its authored identity.
    assert 'title       = "Playing Cramorant"' in text


def test_stamp_is_optional(tmp_path):
    _make_article(tmp_path, 'a')
    dest = archive_slug('a', '2026-08-31', articles_dir=tmp_path)
    assert 'stamp' not in (dest / 'meta.toml').read_text()


@pytest.mark.parametrize('vintage', ['2026-8-31', 'today', '20260831', ''])
def test_bad_vintage_refuses(tmp_path, vintage):
    _make_article(tmp_path, 'a')
    with pytest.raises(SystemExit, match='vintage'):
        archive_slug('a', vintage, articles_dir=tmp_path)
    assert not list(tmp_path.glob('a-*'))


def test_bad_stamp_refuses(tmp_path):
    _make_article(tmp_path, 'a')
    with pytest.raises(SystemExit, match='stamp'):
        archive_slug('a', '2026-08-31', stamp='NOTHEX', articles_dir=tmp_path)
    assert not list(tmp_path.glob('a-*'))


def test_refuses_to_re_archive_a_snapshot(tmp_path):
    """Archiving a snapshot would produce '<slug>-<v1>-<v2>' and a second
    [archive] table -- the operator meant the bare slug."""
    _make_article(tmp_path, 'a')
    archive_slug('a', '2026-08-31', articles_dir=tmp_path)
    with pytest.raises(SystemExit, match='already an archived snapshot'):
        archive_slug('a-2026-08-31', '2026-09-08', articles_dir=tmp_path)


def test_refuses_to_clobber_without_force(tmp_path):
    _make_article(tmp_path, 'a')
    archive_slug('a', '2026-08-31', articles_dir=tmp_path)
    with pytest.raises(SystemExit, match='already exists'):
        archive_slug('a', '2026-08-31', articles_dir=tmp_path)
    forced = archive_slug('a', '2026-08-31', articles_dir=tmp_path,
                          force=True)
    assert (forced / 'index.html').exists(), '--force must actually rewrite'


def test_dry_run_writes_nothing(tmp_path):
    _make_article(tmp_path, 'a')
    dest = archive_slug('a', '2026-08-31', articles_dir=tmp_path, dry_run=True)
    assert not dest.exists()


def test_missing_meta_toml_refuses(tmp_path):
    d = tmp_path / 'a'
    d.mkdir()
    (d / 'index.html').write_text('<html><title>T</title></html>')
    with pytest.raises(SystemExit, match='no meta.toml'):
        archive_slug('a', '2026-08-31', articles_dir=tmp_path)


def test_load_entries_surfaces_the_archive_table(tmp_path):
    _make_article(tmp_path, 'a')
    archive_slug('a', '2026-08-31', stamp='c431557dcc76', articles_dir=tmp_path)
    entries = {e['slug']: e for e in bwi.load_entries(tmp_path)}

    assert entries['a']['archive'] is None, 'live entry must not look archived'
    arch = entries['a-2026-08-31']['archive']
    assert arch['vintage'] == '2026-08-31'
    assert arch['stamp'] == 'c431557dcc76'
    assert arch['of'] == 'a'


def test_archived_iv_guide_does_not_leak_into_the_live_chip_row(tmp_path):
    """The guide split matches '-ml-iv-guide' as a SUBSTRING, so
    'florges-ml-iv-guide-2026-08-31' matches it too. Archived entries
    must be removed BEFORE that split or every snapshot floods the row.

    This calls the PRODUCTION splitter (bwi.split_articles), not a local
    copy of it -- an earlier version of this test reimplemented the two
    filters inline, which meant reordering main() broke the feature with
    every test still green.
    """
    _make_article(tmp_path, 'florges-ml-iv-guide')
    archive_slug('florges-ml-iv-guide', '2026-08-31', articles_dir=tmp_path)
    articles = bwi.load_entries(tmp_path)

    archived, iv_guides, live = bwi.split_articles(articles)

    assert [a['slug'] for a in archived] == ['florges-ml-iv-guide-2026-08-31']
    assert [a['slug'] for a in iv_guides] == ['florges-ml-iv-guide']
    assert live == []

    # Positive control for the SUBSTRING hazard itself: absent the
    # archived-first ordering, the naive filter really does catch both, so
    # this pin is guarding a live failure mode rather than an imagined one.
    naive = [a for a in articles if '-ml-iv-guide' in a['slug']]
    assert len(naive) == 2, 'control: substring match should catch both'


def test_main_routes_through_the_pinned_splitter(tmp_path, monkeypatch):
    """main() must not re-inline the split -- the ordering is the feature."""
    import ast
    src = pathlib.Path(bwi.__file__).read_text()
    tree = ast.parse(src)
    main_fn = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == 'main')
    calls = [n for n in ast.walk(main_fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == 'split_articles']
    assert calls, 'main() no longer calls split_articles()'
    # And it must not have grown its own copy of the -ml-iv-guide filter.
    # ast.unparse drops comments/formatting, so a comment that merely
    # MENTIONS the pattern cannot trip this -- only real code does.
    body = ast.unparse(main_fn)
    assert '-ml-iv-guide' not in body, (
        'main() re-inlined the guide split; the ordering pin in '
        'split_articles() no longer protects it')


def test_render_index_actually_emits_the_archive_block(tmp_path):
    """load_entries returning the entry is not the same as the page
    linking to it. Without this, deleting the _render_archive_block call
    left every other test green while archived pages shipped unreachable
    -- which dropped_pages structurally cannot catch, because an archived
    dir is never SKIPPED by load_entries."""
    _make_article(tmp_path, 'a')
    archive_slug('a', '2026-08-31', stamp='c431557dcc76', articles_dir=tmp_path)
    entries = bwi.load_entries(tmp_path, href_prefix='articles/')
    archived, iv_guides, live = bwi.split_articles(entries)

    out = bwi.render_index([], live, [], iv_guides=iv_guides,
                           archived=archived)
    assert 'articles/a-2026-08-31/index.html' in out
    assert '2026-08-31' in out
    assert 'c431557dcc76' in out


def test_retired_article_is_not_described_as_superseded(tmp_path):
    """Deleting the bare slug is a supported outcome of the regen triage.
    Saying "see the current version above" when there is none is a
    known-wrong claim on a public page."""
    _make_article(tmp_path, 'a')
    archive_slug('a', '2026-08-31', articles_dir=tmp_path)
    entries = bwi.load_entries(tmp_path, href_prefix='articles/')
    archived, _, live = bwi.split_articles(entries)

    still_live = bwi._render_archive_block(archived, live_slugs=frozenset({'a'}))
    assert 'Superseded' in still_live and 'Retired' not in still_live

    retired = bwi._render_archive_block(archived, live_slugs=frozenset())
    assert 'Retired' in retired and 'Superseded' not in retired


def test_archive_block_sorts_titles_ascending_within_a_vintage(tmp_path):
    """At a rebalance every snapshot shares one vintage, so a single
    reverse=True sort would render the whole block Z-A."""
    for slug, title in (('a', 'Alpha'), ('m', 'Mantine'), ('z', 'Zygarde')):
        _make_article(tmp_path, slug,
                      meta=META.replace('Playing Cramorant', title))
        archive_slug(slug, '2026-08-31', articles_dir=tmp_path)
    entries = bwi.load_entries(tmp_path, href_prefix='articles/')
    archived, _, _ = bwi.split_articles(entries)
    out = bwi._render_archive_block(archived)
    assert out.index('Alpha') < out.index('Mantine') < out.index('Zygarde')


def test_newer_vintages_sort_first(tmp_path):
    _make_article(tmp_path, 'a')
    archive_slug('a', '2026-01-01', articles_dir=tmp_path)
    archive_slug('a', '2026-09-08', articles_dir=tmp_path)
    entries = bwi.load_entries(tmp_path, href_prefix='articles/')
    archived, _, _ = bwi.split_articles(entries)
    out = bwi._render_archive_block(archived)
    assert out.index('2026-09-08') < out.index('2026-01-01')


@pytest.mark.parametrize('slug', ['a/', 'a/b', '', '.', '..'])
def test_slug_must_be_a_bare_directory_name(tmp_path, slug):
    """A trailing slash (what tab-completion produces) made dest land
    INSIDE the live article dir: invisible to load_entries (depth-1) and
    to dropped_pages, but still rsynced live by ship_surfaces' rglob."""
    _make_article(tmp_path, 'a')
    with pytest.raises(SystemExit, match='bare directory name'):
        archive_slug(slug, '2026-08-31', articles_dir=tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ['a']
    assert sorted(p.name for p in (tmp_path / 'a').iterdir()) == [
        'index.html', 'meta.toml']


def test_literal_archive_text_in_a_description_is_not_a_snapshot(tmp_path):
    """The re-archive guard reads parsed TOML, not raw text -- an article
    whose description mentions "[archive]" is still a live article."""
    meta = META.replace('"A strategy article."',
                        '"See the [archive] for older versions."')
    _make_article(tmp_path, 'a', meta=meta)
    dest = archive_slug('a', '2026-08-31', articles_dir=tmp_path)
    assert dest.exists()


def test_archive_block_renders_collapsed_and_only_for_archived(tmp_path):
    _make_article(tmp_path, 'a')
    archive_slug('a', '2026-08-31', stamp='c431557dcc76', articles_dir=tmp_path)
    entries = bwi.load_entries(tmp_path, href_prefix='articles/')
    archived = [e for e in entries if e.get('archive')]

    html = bwi._render_archive_block(archived)
    assert '<details' in html and '<summary>' in html
    assert '2026-08-31' in html
    assert 'c431557dcc76' in html
    assert 'a-2026-08-31/index.html' in html
    # Empty input renders nothing at all -- no stray empty <details>.
    assert bwi._render_archive_block([]) == ''


def test_archived_entry_stays_reachable_from_nav(tmp_path):
    """A rendered page unreachable from the index trips load_entries'
    dropped_pages hard-fail. Archiving must not create one."""
    _make_article(tmp_path, 'a')
    archive_slug('a', '2026-08-31', articles_dir=tmp_path)
    dropped = []
    entries = bwi.load_entries(tmp_path, dropped_pages=dropped)
    assert dropped == []
    assert len(entries) == 2
