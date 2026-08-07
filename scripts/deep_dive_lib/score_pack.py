"""Packed uint16 grids: ONE Python encoder and ONE JS decoder template.

Both shipped chains embed large integer grids inline in HTML as
``base64(gzip(little-endian uint16))``:

* the deep dive -- ``SCORES_GZ`` (battle scores) and, under
  ``--compare-energy``, ``ENERGY_GZ`` (post-match leftover energy);
* the ML IV guide -- ``CMPDATA.grids`` / ``CMPDATA.energy_grids``,
  written by ``iv_envelope_analysis.py`` and decoded by the compare
  panels ``render_iv_envelope_article.py`` emits.

Before the DRY review 2026-08-05 (entry 12, ``js-py-score-pack``) that
wire format was written out five times: two Python encoders
(``deep_dive._pack_u16``, ``iv_envelope_analysis.pack_scores``) and
three JS decoders as hand-maintained string literals (scores, energy,
``decodeGrid``). Changing the packing -- widening to uint32, switching
compression -- meant editing five sites, and missing one decodes
garbage on a shipped page with no error. Everything now routes through
this module.

The format is a determinism contract (June 2026 review section G,
invariant 23): values are clamped into ``[0, 65535]``, packed
little-endian, gzip'd at level 9 with ``mtime=0`` (the gzip header's
default timestamp made byte-identical data produce different HTML
run-to-run -- caught by replay-vs-original diffing, arc S4), then
base64'd for inline embedding.

Stdlib only, and deliberately importable on its own: the ML-guide
renderer must not have to import the ~8k-line ``deep_dive`` module just
to spell its decoder. That also keeps it outside the
``opponents -> sweep -> render`` import chain described in the package
docstring -- ``score_pack`` depends on nothing in the package.
"""
import base64
import gzip
import struct

# One decoder body. ``__FN__`` is substituted, not formatted, so the JS
# braces stay readable (an f-string / str.format template would have to
# double every one of them).
_DECODER_JS = """\
async function __FN__(b64) {
  var bin = Uint8Array.from(atob(b64), function(c) { return c.charCodeAt(0); });
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
  return Array.from(new Uint16Array(merged.buffer));
}
"""

# The "decode every blob in this object" loop the dive wraps around the
# decoder. Sequential ``await`` on purpose: the grids are decoded once at
# load and the page's readiness promise must not resolve early.
_DECODE_MAP_JS = """\
var __DST__ = {};
var __READY__ = (async function() {
  for (var key in __SRC__) {
    __DST__[key] = await __FN__(__SRC__[key]);
  }
})();
"""


def pack_u16(values):
    """Pack a numeric sequence as gzip'd little-endian uint16, base64'd.

    The inverse of :func:`decoder_js`'s output. Values are clamped into
    ``[0, 65535]`` and truncated toward zero; ``mtime=0`` keeps the
    output byte-stable run-to-run.
    """
    clamped = [max(0, min(65535, int(v))) for v in values]
    raw = struct.pack(f'<{len(clamped)}H', *clamped)
    gz = gzip.compress(raw, compresslevel=9, mtime=0)
    return base64.b64encode(gz).decode('ascii')


def _indent(text, prefix):
    """Prefix every non-empty line (blank lines stay blank -- no trailing
    whitespace in the emitted page)."""
    if not prefix:
        return text
    return ''.join(prefix + ln if ln.strip() else ln
                   for ln in text.splitlines(keepends=True))


def decoder_js(fn_name, indent=''):
    """JS source for one async ``fn_name(b64) -> Array`` decoder.

    ``fn_name`` is a parameter because the two chains want different
    names at different scopes: the dive declares a page-global
    ``_unpackU16``, the ML guide a ``decodeGrid`` local to its setup
    IIFE (whose two call sites predate this helper).
    """
    return _indent(_DECODER_JS.replace('__FN__', fn_name), indent)


def decode_map_js(packed_var, target_var, ready_var, fn_name, indent=''):
    """JS source that decodes every value of ``packed_var`` into
    ``target_var``, exposing ``ready_var`` as the completion promise.

    ``decoder_js(fn_name)`` must already have been emitted into the same
    scope. Emitted once per grid the dive ships (scores, energy).
    """
    return _indent(
        _DECODE_MAP_JS
        .replace('__SRC__', packed_var)
        .replace('__DST__', target_var)
        .replace('__READY__', ready_var)
        .replace('__FN__', fn_name),
        indent)
