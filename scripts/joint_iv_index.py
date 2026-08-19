#!/usr/bin/env python
"""LOCAL index of built joint-IV robustness pages.

Scans pairs/*.toml, and for every pair whose page exists in
userdata/dives/ emits one card: the pair, its sensitive/saturated/
hopeless scenario split per grid, the headline breakpoint fact, and the
named picks -- everything read from the pair's own reco.json /
breakpoints.json (no hand-authored numbers). Output is
userdata/dives/joint_iv_index.html, LOCAL ONLY (same publish guard as
the pages; the index links same-directory files).

Usage: python scripts/joint_iv_index.py
"""
import datetime
import html
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'scripts'))

from joint_iv_config import load_pair  # noqa: E402

DIVES = REPO / 'userdata' / 'dives'


def esc(s):
    return html.escape(str(s), quote=False)


def card(cfg):
    data = cfg.data_dir
    focal = cfg.focal + (' (Shadow)' if cfg.focal_shadow else '')
    opp = cfg.opponent + (' (Shadow)' if cfg.opp_shadow else '')
    out_name = (f'{cfg.focal.lower()}{"_shadow" if cfg.focal_shadow else ""}'
                f'_vs_{cfg.opponent.lower()}'
                f'{"_shadow" if cfg.opp_shadow else ""}_iv_robustness.html')
    page = DIVES / out_name
    if not page.exists():
        return None
    reco_p = data / 'reco.json'
    rows = [f'<h3><a href="{out_name}">{esc(focal)} vs {esc(opp)}</a></h3>']
    if reco_p.exists():
        reco = json.loads(reco_p.read_text())
        for label, pg in sorted(reco.get('per_grid_scenarios', {}).items()):
            if label == 'rule':
                continue
            if not isinstance(pg, dict) or 'sensitive' not in pg:
                continue
            rows.append(
                f'<p class="sc"><code>{esc(label)}</code> '
                f'sensitive: <strong>{esc(", ".join(pg["sensitive"]) or "none")}'
                f'</strong>; saturated-win: {esc(", ".join(pg["saturated_win"]) or "none")}; '
                f'hopeless: {esc(", ".join(pg["hopeless"]) or "none")}</p>')
        picks = [f'{esc(c["title"])}: '
                 f'{"/".join(str(v) for v in c["spread"]["ivs"])} '
                 f'(rank {c["rank"]})'
                 for c in reco.get('cards', [])[:4]]
        if picks:
            rows.append('<p class="pk">' + ' &middot; '.join(picks) + '</p>')
    return '\n'.join(rows)


def main():
    cards = []
    for toml in sorted((REPO / 'pairs').glob('*.toml')):
        try:
            cfg = load_pair(toml)
        except Exception:
            continue
        c = card(cfg)
        if c:
            cards.append(c)
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    body = '\n<hr>\n'.join(cards)
    out = DIVES / 'joint_iv_index.html'
    out.write_text(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>joint-IV robustness pages (local index)</title>
<style>
 body {{ max-width: 900px; margin: 24px auto; font-family: -apple-system,
        sans-serif; line-height: 1.5; padding: 0 16px; }}
 .sc, .pk {{ font-size: 14px; margin: 4px 0; }}
 .pk {{ color: #555; }}
 hr {{ border: none; border-top: 1px solid #ccc; margin: 18px 0; }}
</style></head><body>
<h1>Joint-IV robustness pages (LOCAL index)</h1>
<p>Generated {ts} by scripts/joint_iv_index.py. {len(cards)} page(s).
Local only -- nothing here is published.</p>
<hr>
{body}
</body></html>
""")
    print(f'wrote {out} ({len(cards)} pages)')


if __name__ == '__main__':
    main()
