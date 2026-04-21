#!/usr/bin/env python
"""Measure a deep-dive HTML file's byte budget.

Reports uncompressed size, gzip-6 size, line count, and the major
repetition-driven buckets (title= attrs, class= attrs, inline plotly,
DATA script block). Used to verify S12 reduction work against a
baseline.

Usage:
    python scripts/measure_html_size.py path/to/dive.html [path/to/other.html ...]

Designed to be diffed between before/after S12 runs. Exit 0 always;
output is the numbers themselves.
"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path


def measure(path: Path) -> dict:
    b = path.read_bytes()
    total = len(b)

    gz = gzip.compress(b, compresslevel=6)

    titles = re.findall(rb'title="[^"]*"', b)
    title_bytes = sum(len(t) for t in titles)
    title_counter = Counter(titles)

    classes = re.findall(rb'class="[^"]*"', b)
    class_bytes = sum(len(c) for c in classes)
    class_counter = Counter(classes)

    # Plotly.js blob (detects the inlined minified bundle's opening banner)
    plotly_match = re.search(rb'<script>/\*\*\s*\* plotly.js v', b)
    plotly_bytes = 0
    if plotly_match:
        end = b.find(b'</script>', plotly_match.start())
        if end > 0:
            plotly_bytes = end + len(b'</script>') - plotly_match.start()

    # DATA+logic script: the one containing SCORES_GZ
    scores_gz_idx = b.find(b'SCORES_GZ')
    data_block_bytes = 0
    if scores_gz_idx > 0:
        # Walk back to find opening <script>
        script_start = b.rfind(b'<script>', 0, scores_gz_idx)
        script_end = b.find(b'</script>', scores_gz_idx)
        if script_start > 0 and script_end > 0:
            data_block_bytes = script_end + len(b'</script>') - script_start

    line_count = b.count(b'\n') + 1
    span_count = b.count(b'<span')
    tr_count = b.count(b'<tr')
    td_count = b.count(b'<td')

    return {
        'path': path,
        'total': total,
        'gzip6': len(gz),
        'lines': line_count,
        'titles_total': len(titles),
        'titles_unique': len(title_counter),
        'title_bytes': title_bytes,
        'classes_total': len(classes),
        'classes_unique': len(class_counter),
        'class_bytes': class_bytes,
        'plotly_bytes': plotly_bytes,
        'data_block_bytes': data_block_bytes,
        'spans': span_count,
        'trs': tr_count,
        'tds': td_count,
    }


def fmt_bytes(n: int) -> str:
    if n >= 1_000_000:
        return f'{n / 1024 / 1024:>7.2f} MB'
    if n >= 1_000:
        return f'{n / 1024:>7.1f} KB'
    return f'{n:>7d}  B'


def print_row(label: str, m: dict, keys: list[tuple[str, str]]):
    cells = [label.ljust(42)]
    for key, fmt in keys:
        v = m[key]
        if fmt == 'bytes':
            cells.append(fmt_bytes(v))
        elif fmt == 'pct':
            cells.append(f'{v * 100:>5.1f}%')
        else:
            cells.append(f'{v:>10,}')
    print(' '.join(cells))


def main(args: list[str]):
    if not args:
        print('usage: measure_html_size.py path.html [path.html ...]', file=sys.stderr)
        return 1
    for p in args:
        path = Path(p)
        if not path.exists():
            print(f'no such file: {p}', file=sys.stderr)
            continue
        m = measure(path)
        print(f'=== {path} ===')
        print(f'  total:          {fmt_bytes(m["total"])}  ({m["lines"]:,} lines)')
        print(f'  gzip -6:        {fmt_bytes(m["gzip6"])}  ({m["gzip6"] / m["total"] * 100:.1f}% ratio)')
        print(f'  title= attrs:   {fmt_bytes(m["title_bytes"])}  ({m["titles_total"]:,} total, {m["titles_unique"]:,} unique)  {m["title_bytes"] / m["total"] * 100:>5.1f}% of file')
        print(f'  class= attrs:   {fmt_bytes(m["class_bytes"])}  ({m["classes_total"]:,} total, {m["classes_unique"]:,} unique)  {m["class_bytes"] / m["total"] * 100:>5.1f}% of file')
        print(f'  inline plotly:  {fmt_bytes(m["plotly_bytes"])}  ({m["plotly_bytes"] / m["total"] * 100:>5.1f}% of file)')
        print(f'  DATA+scores JS: {fmt_bytes(m["data_block_bytes"])}  ({m["data_block_bytes"] / m["total"] * 100:>5.1f}% of file)')
        # tooltip-dedup projected savings
        if m['titles_unique']:
            # assume 3-char base62 IDs on the ref side + 30% JSON-overhead on the table
            unique_bytes = sum(len(k) for k in Counter(re.findall(rb'title="[^"]*"', path.read_bytes())).keys())
            projected_refs = m['titles_total'] * 12  # `data-t="iK"` ~ 12 bytes
            projected_table = int(unique_bytes * 1.3) + 500
            projected_savings = m['title_bytes'] - projected_refs - projected_table
            print(f'  R1 dedup est:   save {fmt_bytes(max(0, projected_savings))}  ({projected_savings / m["total"] * 100:+.1f}% of file)')
        if m['plotly_bytes']:
            print(f'  R2 plotly est:  save {fmt_bytes(m["plotly_bytes"])}  ({-m["plotly_bytes"] / m["total"] * 100:+.1f}% of file)')
        print()

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
