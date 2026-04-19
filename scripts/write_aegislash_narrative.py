#!/usr/bin/env python3
"""Emit a first-draft Aegislash form-change guide article (GL or UL).

Usage:
    python scripts/write_aegislash_narrative.py {great,ultra}

Writes:
    userdata/website/articles/aegislash-form-change-guide-{gl,ul}/index.html
    userdata/website/articles/aegislash-form-change-guide-{gl,ul}/meta.toml

This is a **first-draft** generator. Unlike the Oinkologne CD article
(which goes through scripts/generate_article.py with an expert-authored
source TOML), the Aegislash form-change guide is auto-templated and
flagged for human review before ship. The real Aegislash narrative home
long-term is the dive-side threshold TOML blocks
(thresholds/aegislash_{blade,shield}.toml [Species.intro / .meta_role /
.verdict]), which Session 3 of the Shape 2 arc will populate.

The output is a simple landing page that links to the two per-form deep
dives (Blade + Shield) and the Blade-vs-Shield win-rate comparison page.
A banner at the top marks every section as auto-generated.
"""
from __future__ import annotations

import argparse
import html
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / 'userdata' / 'website'
ARTICLES_DIR = WEBSITE_DIR / 'articles'

LEAGUE_INFO = {
    'great': {
        'suffix': 'gl',
        'display': 'Great League',
        'cp_cap': 1500,
        'blade_slug': 'aegislash-blade-great-league',
        'shield_slug': 'aegislash-shield-great-league',
        'comparison_slug': 'aegislash-blade-vs-shield',
        'shield_fast': 'Psycho Cut (charge-only fast move, 0 power)',
        'shield_charged': 'Shadow Ball, Gyro Ball',
    },
    'ultra': {
        'suffix': 'ul',
        'display': 'Ultra League',
        'cp_cap': 2500,
        'blade_slug': 'aegislash-blade-ultra-league',
        'shield_slug': 'aegislash-shield-ultra-league',
        'comparison_slug': 'aegislash-blade-vs-shield-ul',
        'shield_fast': 'Psycho Cut (charge-only fast move, 0 power)',
        'shield_charged': 'Shadow Ball, Flash Cannon',
    },
}


REVIEW_BANNER = (
    '<div style="background:#fff3cd;border:2px solid #ffc107;'
    'padding:12px 16px;margin:16px 0;border-radius:4px;">'
    '<strong>First-draft auto-generated article.</strong> '
    'Every section below is templated output, not expert analysis. '
    'Review and rewrite before shipping. The canonical Aegislash '
    'narrative home (long-term) is the per-form deep-dive Species '
    'blocks, not this article.'
    '</div>'
)


def build_html(league: str) -> str:
    info = LEAGUE_INFO[league]
    title = f'Aegislash Form-Change Guide: {info["display"]}'
    blade_href = f'../../{info["blade_slug"]}/index.html'
    shield_href = f'../../{info["shield_slug"]}/index.html'
    compare_href = f'../../comparisons/{info["comparison_slug"]}/index.html'

    sections = textwrap.dedent(f'''\
        <h2>Form change in one paragraph</h2>
        <p>Aegislash starts every battle in Shield form
        (atk&nbsp;97 / def&nbsp;272 / hp&nbsp;155) with a zero-power
        fast move that purely generates energy. The first charged
        move triggers a stat-and-move swap to Blade form
        (atk&nbsp;272 / def&nbsp;97 / hp&nbsp;155) for the remainder
        of the battle. The sim models this via
        <code>src/gopvpsim/formchange.py</code> using the gamemaster
        <code>formChange</code> field; no policy toggle is required.</p>

        <h2>Per-form deep dives</h2>
        <ul>
          <li><a href="{html.escape(shield_href)}">
              Aegislash (Shield) - {html.escape(info["display"])} deep dive</a>
              - canonical path (starts Shield, transforms on first
              charged move). Fast: {html.escape(info["shield_fast"])};
              charged: {html.escape(info["shield_charged"])}.</li>
          <li><a href="{html.escape(blade_href)}">
              Aegislash (Blade) - {html.escape(info["display"])} deep dive</a>
              - hypothetical always-Blade profile (Aegislash (Blade)
              as its own species; no form change). Useful as a
              counter-factual to quantify how much performance comes
              from the Shield-start rather than the Blade stats.</li>
        </ul>

        <h2>Blade vs Shield pairwise comparison</h2>
        <p>The pairwise win-rate fragment comparing the canonical
        Shield-path against the hypothetical always-Blade loadout
        lives at
        <a href="{html.escape(compare_href)}">the Blade-vs-Shield
        comparison page</a>. That page reads the two dive HTMLs and
        computes per-matchup deltas using the same moveset on both
        loadouts, so the delta isolates form-change effect (not
        moveset choice).</p>

        <h2>Sections to author before ship</h2>
        <ul>
          <li><strong>Meta role.</strong> What types Aegislash
          punishes, what punishes it, how the form change shapes
          team-slot decisions. Numbers from the dives; framing from
          the author.</li>
          <li><strong>Verdict.</strong> Investment recommendation
          calibrated to the {html.escape(info["display"])} meta,
          Elite TM cost, and the form-change mechanic's
          counter-play surface.</li>
          <li><strong>IV targeting.</strong> Whether to prioritize
          Shield-form bulk (usual target) or Blade-form
          attack-breakpoints, with numbers pulled from the dives'
          Notable IVs cards.</li>
          <li><strong>Timing / shield interaction.</strong> Because
          the form change is triggered by the first charged move,
          shield decisions and bait dynamics differ from other
          species. Worth a dedicated subsection.</li>
        </ul>
    ''')

    return textwrap.dedent(f'''\
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <title>{html.escape(title)}</title>
          <style>
            body {{ max-width: 920px; margin: 24px auto; padding: 0 16px;
                   font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                                Roboto, sans-serif; line-height: 1.5; }}
            h1 {{ margin-bottom: 0.2em; }}
            h2 {{ margin-top: 1.6em; }}
            code {{ background: #f3f3f3; padding: 1px 4px; border-radius: 3px; }}
            ul li {{ margin-bottom: 0.5em; }}
          </style>
        </head>
        <body>
        <h1>{html.escape(title)}</h1>
        {REVIEW_BANNER}
        {sections}
        </body>
        </html>
    ''')


def build_meta_toml(league: str) -> str:
    info = LEAGUE_INFO[league]
    title = f'Aegislash Form-Change Guide: {info["display"]}'
    return textwrap.dedent(f'''\
        title       = "{title}"
        description = "First-draft auto-generated Aegislash Shield/Blade form-change guide for {info['display']}. Links to the per-form deep dives and the Blade-vs-Shield comparison page. Needs expert review before ship."
        authorship  = "auto"
        landing     = "index.html"
    ''')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('league', choices=sorted(LEAGUE_INFO.keys()))
    args = parser.parse_args()

    info = LEAGUE_INFO[args.league]
    slug = f'aegislash-form-change-guide-{info["suffix"]}'
    out_dir = ARTICLES_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / 'index.html').write_text(build_html(args.league))
    (out_dir / 'meta.toml').write_text(build_meta_toml(args.league))

    print(f'Wrote {out_dir}/index.html + meta.toml')
    return 0


if __name__ == '__main__':
    sys.exit(main())
