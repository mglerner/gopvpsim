"""Worker pools in the link and dash scanners (2026-09-25, plan item R5).

verify_article_links / verify_no_unicode_dashes scan files in a worker
pool. main() with --jobs 1 (the serial in-process path) and --jobs 3 must
print byte-identical reports on hand-written pages that trip the
detectors. The real-tree parity check (790 files, 691,888 hrefs) was a
one-off diff of old-vs-new --ship output at commit time; see the commit
message.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import verify_article_links  # noqa: E402
import verify_no_unicode_dashes as vnud  # noqa: E402

EM = chr(0x2014)  # em dash


def _pages(tmp_path):
    """Seven pages, several of which trip each detector."""
    pages = []
    for i in range(7):
        p = tmp_path / f'p{i}.html'
        body = (f'<html><body><p id="here{i}">page {i}</p>'
                f'<a href="#here{i}">ok</a>'
                f'<a href="p{(i + 1) % 7}.html#here{(i + 1) % 7}">ok</a>')
        if i % 2:
            body += f'<a href="p{i}.html#gone">bad</a><a href="nope.html">x</a>'
            body += f'<p>dash {EM} here</p>'
        if i % 3 == 0:
            body += f'<img alt="alt {EM} text">'
        p.write_text(body + '</body></html>')
        pages.append(p)
    return pages


def _run_main(module, monkeypatch, capsys, args):
    monkeypatch.setattr(sys, 'argv', ['x', *map(str, args)])
    rc = module.main()
    return rc, capsys.readouterr().out


@pytest.mark.parametrize('module', [verify_article_links, vnud],
                         ids=['links', 'dashes'])
@pytest.mark.parametrize('quiet', [False, True])
def test_scanner_pool_report_matches_serial(module, quiet, tmp_path,
                                            monkeypatch, capsys):
    pages = _pages(tmp_path)
    extra = ['-q'] if quiet else []
    rc1, out1 = _run_main(module, monkeypatch, capsys,
                          [*pages, *extra, '--jobs', '1'])
    rc3, out3 = _run_main(module, monkeypatch, capsys,
                          [*pages, *extra, '--jobs', '3'])
    assert (rc3, out3) == (rc1, out1)
    # Non-trivial: the detectors fired, so "both empty" cannot pass.
    assert rc1 == 1
    assert out1.count('\n  ') >= 3


def test_dash_pool_stops_at_unreadable_file_like_serial(
        tmp_path, monkeypatch, capsys):
    pages = _pages(tmp_path)
    bad = tmp_path / 'bad.html'
    bad.mkdir()  # read_text() on a directory raises
    paths = [*pages[:3], bad, *pages[3:]]
    rc1, out1 = _run_main(vnud, monkeypatch, capsys, [*paths, '--jobs', '1'])
    rc3, out3 = _run_main(vnud, monkeypatch, capsys, [*paths, '--jobs', '3'])
    assert (rc3, out3) == (rc1, out1)
    assert rc1 == 1
    assert out1.rstrip().splitlines()[-1].startswith(f'{bad}: could not read')
    assert 'p3.html' not in out1
