"""Canonical PvPoke attribution, shown on every generated HTML page.

This project stands on PvPoke. The battle simulator in ``battle.py`` is a
Python port of PvPoke's open-source battle logic, and every piece of game
data (the gamemaster, move stats, type chart, and meta rankings) is fetched
from PvPoke. Without PvPoke this project could not exist.

PvPoke (https://pvpoke.com, https://github.com/pvpoke/pvpoke) was created by
Empoleon_Dynamite and is released under the MIT license. Keep the credit
prominent and verbatim across surfaces; it is imported, not re-typed, so the
wording stays consistent everywhere.
"""

PVPOKE_REPO = "https://github.com/pvpoke/pvpoke"
PVPOKE_SITE = "https://pvpoke.com"

# Full attribution paragraph (HTML). Use in about boxes and page footers that
# have room. ASCII only (no em-dashes) so it renders cleanly as UI text.
PVPOKE_ATTRIBUTION_HTML = (
    'This project is built on <a href="https://github.com/pvpoke/pvpoke">PvPoke</a>, '
    'created by Empoleon_Dynamite and released under the MIT license. The battle '
    "simulator here is a Python port of PvPoke's open-source battle logic, and all "
    'game data (the gamemaster, move stats, type chart, and meta rankings) comes '
    'from <a href="https://pvpoke.com">PvPoke</a>. This project would not exist '
    'without it.'
)

# Compact one-line variant for tight footers.
PVPOKE_ATTRIBUTION_SHORT = (
    'Battle engine is a Python port of '
    '<a href="https://github.com/pvpoke/pvpoke">PvPoke</a>; all game data from '
    '<a href="https://pvpoke.com">PvPoke</a> by Empoleon_Dynamite (MIT license). '
    'This project would not exist without it.'
)

# Plain-text variant for non-HTML contexts (console banners, READMEs).
PVPOKE_ATTRIBUTION_TEXT = (
    "Built on PvPoke (pvpoke.com, github.com/pvpoke/pvpoke) by Empoleon_Dynamite, "
    "MIT license. The battle simulator is a Python port of PvPoke's open-source "
    "battle logic and all game data comes from PvPoke. This project would not "
    "exist without it."
)
