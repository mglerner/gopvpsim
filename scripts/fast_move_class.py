"""Fast-move classification for narrative framing.

Per RyanSwag's PvP IV methodology (transcript at
``docs/ryanswag_how_to_deep_dive.txt``) and the post-S5 Oinkologne arc
plan item S5a-4, species whose fast move falls in the "charmer" class
(Charm, Razor Leaf, Waterfall, Dragon Breath, and a few close analogues)
have a shared narrative framing: high damage-per-turn fast moves mean
more fast damage over a matchup and more fast moves survived, so **stat
product generally matters more than extra charge-move damage**. This
flips the usual "push Atk for breakpoints" default on its head.

The classification here is a *default*. Species-level exceptions (e.g.
Shadow Victreebel, whose high shadow-Atk multiplier pushes Razor-Leaf
breakpoint framing even on a charmer fast move) should override via the
threshold TOML, not by editing this list.
"""

# Canonical charmer fast moves by PvPoke id. Kept conservative; expand
# only when RyanSwag's (or equivalent expert) framing explicitly calls
# out the move as a charmer.
CHARMER_FAST_MOVES = frozenset({
    'CHARM',
    'RAZOR_LEAF',
    'WATERFALL',
    'DRAGON_BREATH',
    'FAIRY_WIND',
})


def is_charmer_fast_move(fast_id_or_name):
    """Return True iff the given fast move is in the charmer class.

    Accepts either the PvPoke id (``'DRAGON_BREATH'``, upper snake case)
    or the pretty name (``'Dragon Breath'``). Case-insensitive.
    """
    if not fast_id_or_name:
        return False
    normalized = fast_id_or_name.strip().upper().replace(' ', '_')
    return normalized in CHARMER_FAST_MOVES


def charmer_context_line(species):
    """Return a short narrative context sentence for a charmer species.

    Used at the top of the IV Flavor Guide when the moveset's fast move
    is classified as a charmer. Intentionally short and ASCII-only (no
    em-dashes per ``feedback_no_em_dashes.md``).
    """
    return (
        f'Charm-class fast moves typically favor stat product on {species}: '
        'more attacks in, more fast moves survived, usually outweighs one '
        'extra charge-move damage.'
    )
