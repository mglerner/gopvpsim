"""One stylesheet for the shared compare panels, emitted by both hosts.

DRY review 2026-08-05, entry 15 (``js-py-cmp-css``). ``scripts/cmp_panels.js``
builds the compare table for TWO pages -- the deep dive
(``scripts/deep_dive.py``) and the ML / IV guide
(``scripts/render_iv_envelope_article.py``) -- but each page carried its own
hand-maintained copy of the ``.cmp-*`` rules, the guide's headed "Ported from
the deep-dive's .cmp-* rules". A class added to the JS, or a rule retuned on
one page, silently styled only one of them.

Now both hosts splice ``deep_dive_rendering.CMP_PANEL_CSS``. This pins:

* every ``.cmp-*`` class the shared JS emits is styled in the shared block
  (so a new class in the JS cannot be styled on one page only);
* both hosts really emit that text -- the guide by calling ``style()``, the
  dive by reading the page it actually renders;
* neither host keeps a second copy: the dive styles no shared class locally,
  and the guide's local block only OVERRIDES classes the shared block defines
  (em sizing, cancelling the article's generic table paint, the scroll fade).

Coverage boundary: this checks which selectors exist, not what they look
like. Two rules with the same selector and different values still pass -- but
that can now only happen through the guide's deliberate override block, which
the last test keeps to classes the shared block already defines.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from deep_dive_rendering import CMP_PANEL_CSS   # noqa: E402
import render_iv_envelope_article as guide      # noqa: E402

CMP_PANELS_JS = SCRIPTS / 'cmp_panels.js'
DEEP_DIVE_PY = SCRIPTS / 'deep_dive.py'

_CLASS_RE = re.compile(r'cmp-[a-z0-9-]+')
# A CSS rule start inside the dive's f-string CSS: a selector containing a
# .cmp- class, up to its opening (doubled) brace. Not line-anchored, so
# several rules on one line (".cmp-good {{...}} .cmp-mid {{...}}") each match.
# The dive's inline JS is in the same f-string and also doubles its braces,
# but no '{{' there is preceded by a '.cmp-' selector.
_DIVE_RULE_RE = re.compile(r'([^\n{}]*\.cmp-[a-z0-9-]+[^\n{}]*?)\{\{')


def _js_classes():
    """Class names the shared compare-panel JS puts on elements."""
    return {m.group(0) for m in _CLASS_RE.finditer(CMP_PANELS_JS.read_text())}


def _styled_classes(css):
    """Class names the given CSS text writes a rule for."""
    styled = set()
    for m in re.finditer(r'([^{}]*)\{', css):
        styled |= {c for c in _CLASS_RE.findall(m.group(1))}
    return styled


def test_js_class_scan_finds_the_expected_scale():
    """Anti-vacuity: if the scan stops matching, the guard below turns into
    a no-op that passes. The review counted 21 classes; the floor leaves
    room for deletions without churn."""
    classes = _js_classes()
    assert len(classes) >= 18, f'only {len(classes)} cmp classes: {sorted(classes)}'


def test_every_shared_js_class_is_styled_in_the_shared_block():
    styled = _styled_classes(CMP_PANEL_CSS)
    missing = sorted(_js_classes() - styled)
    assert not missing, f'cmp_panels.js emits unstyled classes: {missing}'


def test_guide_emits_the_shared_block_verbatim():
    assert CMP_PANEL_CSS in guide.style()


def test_dive_splices_the_shared_block():
    assert '{rendering.CMP_PANEL_CSS}' in DEEP_DIVE_PY.read_text()


def test_dive_emits_the_shared_block_verbatim(small_dive_html):
    """The one check on the page that actually ships. Source-level splicing
    could still be defeated by an f-string that never reaches the <style>."""
    assert CMP_PANEL_CSS in small_dive_html


def test_dive_keeps_no_local_copy_of_a_shared_rule():
    """The dive's own CSS may style the candidate-picker widget
    (.cmp-section, .cmp-card, ...) but must not restyle anything the shared
    block owns -- that is how the two copies drifted in the first place."""
    local = set()
    for m in _DIVE_RULE_RE.finditer(DEEP_DIVE_PY.read_text()):
        local |= set(_CLASS_RE.findall(m.group(1)))
    clash = sorted(local & _styled_classes(CMP_PANEL_CSS))
    assert not clash, f'deep_dive.py re-styles shared classes: {clash}'


def test_guide_overrides_only_restyle_shared_classes():
    """The guide's local block is for page-specific tweaks ON TOP of the
    shared rules. A class it styles that the shared block does not define is
    a fork -- the same class would then be styled on one page only."""
    local_css = guide.style().replace(CMP_PANEL_CSS, '')
    shared = _styled_classes(CMP_PANEL_CSS)
    forked = sorted(_styled_classes(local_css) - shared)
    assert not forked, f'guide-only cmp classes: {forked}'
