#!/usr/bin/env python3
"""Fetch a Dracoviz championship-series tournament roster dump to JSON.

Dracoviz exposes a public JSON endpoint at
``https://www.dracoviz.com/api/tournament/?searchType=tm&tm=<slug>``
returning one record per submitted team: player handle, country,
``final_rank``, match/game win-loss, and a 6-mon ``roster`` with per-mon
name, form, CP, fast move, two charged moves, and shadow flag.

The endpoint requires a site-wide ``x_authorization`` header. The token
below is embedded in Dracoviz's public Gatsby bundle (anyone who opens
DevTools on dracoviz.com can read it), so it's a rate-limit / anti-
hotlink token, not a user secret. If Dracoviz rotates it, set
``DRACOVIZ_AUTH`` in the environment to override.

Usage::

    python scripts/fetch_dracoviz_tournament.py 2026-orlando
    python scripts/fetch_dracoviz_tournament.py 2026-houston --out /tmp/x.json

Default output: ``docs/tournament_data/cs_<slug>.json`` (dashes in the
slug become underscores).
"""
import argparse
import os
import sys
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DEFAULT_AUTH = 'Basic R50wRuaO7J'


def fetch(slug, out_path):
    url = f'https://www.dracoviz.com/api/tournament/?searchType=tm&tm={slug}'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'pogo-simulator/fetch_dracoviz_tournament',
        'Accept': 'application/json',
        'Referer': f'https://www.dracoviz.com/{slug}/',
        'x_authorization': os.environ.get('DRACOVIZ_AUTH', _DEFAULT_AUTH),
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(body)
    print(f'Wrote {len(body)} bytes to {out_path}')


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('slug', help='Tournament slug, e.g. "2026-orlando"')
    p.add_argument('--out', help='Output path (default: docs/tournament_data/cs_<slug>.json)')
    args = p.parse_args()

    if args.out:
        out = args.out
    else:
        fn = 'cs_' + args.slug.replace('-', '_') + '.json'
        out = os.path.join(REPO, 'docs', 'tournament_data', fn)
    fetch(args.slug, out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
