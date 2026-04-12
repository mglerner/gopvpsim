#!/usr/bin/env python3
"""Patch existing dive HTML files to use gzip score encoding.

Reads SCORES_B64 (uint16 → base64), re-encodes as SCORES_GZ
(JSON → gzip → base64), and replaces the inline JS decoder.
Also wraps the engine script in an async IIFE with await _scoresReady
and adds window.updateView for onchange handler compatibility.

Usage:
    python scripts/patch_dive_gzip.py FILE [FILE ...]

Patches files in-place. Idempotent — skips files already using SCORES_GZ.
"""
import base64
import gzip
import json
import re
import struct
import sys


def patch_file(path):
    with open(path) as f:
        html = f.read()

    if 'SCORES_GZ' in html:
        print(f"  {path}: already patched, skipping")
        return

    if 'SCORES_B64' not in html:
        print(f"  {path}: no SCORES_B64 found, skipping")
        return

    # --- 1. Extract and re-encode score arrays ---
    m = re.search(r'var SCORES_B64 = ({.*?});\s*\n', html, re.DOTALL)
    if not m:
        print(f"  {path}: could not parse SCORES_B64, skipping")
        return

    scores_b64 = json.loads(m.group(1))
    packed_gz = {}
    for key, b64_str in scores_b64.items():
        raw = base64.b64decode(b64_str)
        n_values = len(raw) // 2
        scores = list(struct.unpack(f'<{n_values}H', raw))
        json_bytes = json.dumps(scores).encode('utf-8')
        gz = gzip.compress(json_bytes, compresslevel=9)
        packed_gz[key] = base64.b64encode(gz).decode('ascii')

    # --- 2. Replace SCORES_B64 declaration + decoder with SCORES_GZ version ---
    old_block = re.search(
        r'var SCORES_B64 = \{.*?\};\s*\n'
        r'var SCORES = \{\};\s*\n'
        r'\(function\(\) \{.*?\}\)\(\);\s*\n',
        html, re.DOTALL,
    )
    if not old_block:
        print(f"  {path}: could not find old decoder block, skipping")
        return

    new_block = f'var SCORES_GZ = {json.dumps(packed_gz)};\n'
    new_block += """var SCORES = {};
var _scoresReady = (async function() {
  for (var key in SCORES_GZ) {
    var bin = Uint8Array.from(atob(SCORES_GZ[key]), function(c) { return c.charCodeAt(0); });
    var ds = new DecompressionStream('gzip');
    var writer = ds.writable.getWriter();
    writer.write(bin);
    writer.close();
    var chunks = [];
    var reader = ds.readable.getReader();
    while (true) {
      var r = await reader.read();
      if (r.done) break;
      chunks.push(r.value);
    }
    var blob = new Blob(chunks);
    var text = await blob.text();
    SCORES[key] = JSON.parse(text);
  }
})();
"""
    html = html[:old_block.start()] + new_block + html[old_block.end():]

    # --- 3. Wrap engine script in async IIFE ---
    # The engine is the last <script>...</script> block. Find it by
    # searching backwards from the end for the block containing
    # "function updateView(".
    script_blocks = list(re.finditer(
        r'<script>\n(.*?)</script>',
        html, re.DOTALL,
    ))
    for m in reversed(script_blocks):
        if 'function updateView(' in m.group(1):
            inner = m.group(1)
            if 'window.updateView' not in inner:
                inner = inner.replace(
                    '// ---- Init ----\n',
                    '// ---- Init ----\n'
                    'window.updateView = updateView;\n',
                )
            wrapped = (
                '<script>\n'
                '(async function() {\n'
                'await _scoresReady;\n'
                + inner
                + '\n})();\n'
                '</script>'
            )
            html = html[:m.start()] + wrapped + html[m.end():]
            break

    with open(path, 'w') as f:
        f.write(html)

    old_size = sum(len(v) for v in scores_b64.values())
    new_size = sum(len(v) for v in packed_gz.values())
    print(f"  {path}: patched ({old_size:,} -> {new_size:,} bytes score data, "
          f"{new_size/old_size*100:.1f}%)")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python scripts/patch_dive_gzip.py FILE [FILE ...]")
        sys.exit(1)

    for path in sys.argv[1:]:
        patch_file(path)
