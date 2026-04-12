#!/usr/bin/env python3
"""Patch existing dive HTML files to use gzip score encoding.

Reads SCORES_B64 (uint16 → base64), re-encodes as SCORES_GZ
(uint16 → gzip → base64), and replaces the inline JS decoder.
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

    # Detect source format
    if 'SCORES_B64' in html:
        source_format = 'b64'
    elif 'SCORES_GZ' in html and 'JSON.parse' in html:
        source_format = 'json_gz'  # old JSON-based gzip, needs re-encoding
    elif 'SCORES_GZ' in html:
        print(f"  {path}: already using uint16+gzip, skipping")
        return
    else:
        print(f"  {path}: no score data found, skipping")
        return

    # --- 1. Extract and re-encode score arrays ---
    if source_format == 'b64':
        m = re.search(r'var SCORES_B64 = ({.*?});\s*\n', html, re.DOTALL)
        if not m:
            print(f"  {path}: could not parse SCORES_B64, skipping")
            return
        scores_src = json.loads(m.group(1))
        packed_gz = {}
        for key, b64_str in scores_src.items():
            # Source is already uint16 little-endian; just gzip the raw bytes
            raw = base64.b64decode(b64_str)
            gz = gzip.compress(raw, compresslevel=9)
            packed_gz[key] = base64.b64encode(gz).decode('ascii')
    else:
        # source_format == 'json_gz': decode JSON scores, re-encode as uint16
        m = re.search(r'var SCORES_GZ = ({.*?});\s*\n', html, re.DOTALL)
        if not m:
            print(f"  {path}: could not parse SCORES_GZ, skipping")
            return
        scores_src = json.loads(m.group(1))
        packed_gz = {}
        for key, b64_str in scores_src.items():
            gz_bytes = base64.b64decode(b64_str)
            raw_json = gzip.decompress(gz_bytes)
            scores = json.loads(raw_json)
            raw = struct.pack(f'<{len(scores)}H', *scores)
            gz = gzip.compress(raw, compresslevel=9)
            packed_gz[key] = base64.b64encode(gz).decode('ascii')

    # --- 2. Replace score declaration + decoder with new version ---
    if source_format == 'b64':
        old_block = re.search(
            r'var SCORES_B64 = \{.*?\};\s*\n'
            r'var SCORES = \{\};\s*\n'
            r'\(function\(\) \{.*?\}\)\(\);\s*\n',
            html, re.DOTALL,
        )
    else:
        # Match SCORES_GZ + the old JSON.parse decoder (including the
        # comment block and async IIFE).
        old_block = re.search(
            r'var SCORES_GZ = \{.*?\};\s*\n'
            r'.*?'  # comment block + decoder
            r'var SCORES = \{\};\s*\n'
            r'var _scoresReady = \(async function.*?\}\)\(\);\s*\n',
            html, re.DOTALL,
        )
    if not old_block:
        print(f"  {path}: could not find decoder block, skipping")
        return

    new_block = f'var SCORES_GZ = {json.dumps(packed_gz)};\n'
    new_block += """
// -------------------------------------------------------------------
// How SCORES_GZ works (for the curious / paranoid):
//
// Each value in SCORES_GZ is a base64 string that encodes gzip-
// compressed battle-simulation scores.  The pipeline that created it:
//
//   Python side (scripts/deep_dive.py):
//     1. Simulate every IV spread vs every opponent in every shield
//        scenario.  Each sim produces an integer score 0-1000.
//     2. Pack the scores as little-endian unsigned 16-bit integers
//        (2 bytes each, same byte order your browser uses natively).
//     3. Gzip-compress the packed bytes (shrinks ~5-8x).
//     4. Base64-encode the gzip output so it can live inside HTML
//        (browsers can't embed raw binary in a <script> tag).
//
//   JS side (right here, runs when the page loads):
//     1. Base64-decode each string back to raw bytes.
//     2. Gzip-decompress via the browser's built-in DecompressionStream.
//     3. Interpret the result as a Uint16Array (the original scores).
//     4. Copy into a plain Array so the rest of the page can use it.
//
// Nothing is hidden or obfuscated -- the compression is purely to keep
// file sizes manageable (a full deep dive with 60+ opponents would be
// ~100 MB uncompressed).  You can verify the scores by running the
// same deep_dive.py command shown in the footer of this page and
// comparing the output.
// -------------------------------------------------------------------

var SCORES = {};
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
    var total = chunks.reduce(function(s, c) { return s + c.byteLength; }, 0);
    var merged = new Uint8Array(total);
    var offset = 0;
    for (var i = 0; i < chunks.length; i++) {
      merged.set(chunks[i], offset);
      offset += chunks[i].byteLength;
    }
    SCORES[key] = Array.from(new Uint16Array(merged.buffer));
  }
})();
"""
    html = html[:old_block.start()] + new_block + html[old_block.end():]

    # --- 3. Wrap engine script in async IIFE (if not already wrapped) ---
    if 'await _scoresReady' not in html:
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

    old_size = sum(len(v) for v in scores_src.values())
    new_size = sum(len(v) for v in packed_gz.values())
    print(f"  {path}: patched ({old_size:,} -> {new_size:,} bytes score data, "
          f"{new_size/old_size*100:.1f}%)")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python scripts/patch_dive_gzip.py FILE [FILE ...]")
        sys.exit(1)

    for path in sys.argv[1:]:
        patch_file(path)
