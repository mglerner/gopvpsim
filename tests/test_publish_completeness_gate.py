"""The publish completeness gate must count DIVE pages, and must not lie
about what --partial does.

Two holes found by the 2026-09-20 pre-dive grid, both in the one gate that
stands between a half-finished bake and ``rsync --delete`` against the live
site:

1. ACTUAL_DIVES was ``find $SRC -mindepth 2 -maxdepth 2 -name index.html``,
   which counts every depth-2 page -- including ``guides/``, ``matchups/``
   and ``matchups-ultra/``, which are not dives.  On this tree that is 3
   phantom dives padding the count, so the gate reads 135 when 132 dive
   pages exist against an expected 136.  A gate whose numerator and
   denominator count different things is a gate that can pass while the
   thing it guards is false.

2. The gate's own failure message offered ``--partial (safe, pulls live
   content down first)``.  It does neither.  The pull-down was in an early
   draft of 986cc01 and Michael dropped it; the commit message says so and
   the code comment says so ("It does not pull anything down"), but the
   message a human reads at the exact moment they are deciding whether to
   mirror an incomplete site over the live one was never updated.  Under
   --partial, rsync still runs with --delete, so every page the bake has
   not reached yet is REMOVED from pogodives.com.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = (REPO / 'scripts' / 'publish_website.sh').read_text()


def test_actual_dives_counts_only_registry_dive_dirs():
    """The numerator must be dive pages, not every depth-2 index.html."""
    start = SRC.index('ACTUAL_DIVES=')
    expr = SRC[start:SRC.index('\nif ', start)]
    assert 'maxdepth 2 -name index.html' not in expr, (
        'counts guides/ and matchups*/ as dives; numerator and denominator '
        'must count the same thing')
    assert 'dive_registry' in expr or 'prune_unlisted_dives' in expr, (
        'the count must be driven by the registry slug list')


def test_partial_bypass_message_does_not_claim_a_pull_down():
    """--partial relaxes gates only; it never pulls live content down."""
    assert 'pulls live content down' not in SRC
    # positive control: the bypass is still offered, so this test cannot
    # pass merely because the message was deleted wholesale.
    assert '--partial' in SRC
    assert 'refusing to publish an INCOMPLETE site' in SRC


def test_partial_bypass_message_says_deletion_still_happens():
    """A human reading the failure must learn the one fact that decides it."""
    start = SRC.index('bypass: --partial')
    # Only the bypass advice itself, not the surrounding gate prose (which
    # already mentions --delete and would mask a silent message).
    block = SRC[start:SRC.index('--skip-verify', start)]
    assert re.search(r'--delete|removed from the live site', block), (
        'the --partial bypass line must say rsync --delete still removes the '
        'pages the bake has not reached')
