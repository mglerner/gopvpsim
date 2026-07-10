"""Build pvpoke.com single-battle URLs for IV-guide matchup links.

URL format (verified against pvpoke Interface.js / Pokemon.js
generateURLPokeStr + generateURLMoveStr, and by loading sample links):

  https://pvpoke.com/battle/{cp}/{p1}/{p2}/{shields}/{moves1}/{moves2}/

  cp       = "10000"  (master; plain CP, level cap 50 implied. Best-buddy L51 is
             set PER-MON in the poke string's level field, not via a cap suffix.
             NB: a "10000-51" cap suffix makes PvPoke fall back to Great League --
             that was a bug, fixed 2026-06-21.)
  pX       = "{speciesId}-{level}-{atk}-{def}-{hp}-4-4-1-1"
             trailing 4-4-1-1 = no stat buffs (PvPoke stores buff+maxBuffStages,
             default 4), bait on, optimize-timing on.
  shields  = "{focalShields}{oppShields}"  e.g. "21" = focal 2, opp 1.
  movesX   = "{FAST_ID}-{CHARGED1_ID}-{CHARGED2_ID}"  -- the hard-moveset-link
             form (move IDs, not pool indices); PvPoke parses them via
             getMoveById, so it is robust to gamemaster move ordering.

Best-effort: returns None if the gamemaster/speciesId or a moveset can't be
resolved, so the renderer falls back to plain (unlinked) text.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from gopvpsim.data import get_default_moveset, CACHE_DIR

_INDEX = None
_MOVESET = {}


def _index():
    """speciesName(+shadow) -> speciesId, from the cached gamemaster."""
    global _INDEX
    if _INDEX is None:
        idx = {}
        try:
            gm = json.load(open(CACHE_DIR / 'gamemaster.json'))
            for p in gm['pokemon']:
                shadow = 'shadow' in (p.get('tags') or [])
                name = p['speciesName'].replace(' (Shadow)', '').strip()
                idx[(name, shadow)] = p['speciesId']
        except Exception:
            pass
        _INDEX = idx
    return _INDEX


def species_id(display, shadow):
    base = display.replace(' (Shadow)', '').strip()
    idx = _index()
    return idx.get((base, shadow)) or idx.get((base, False))


def _opp_moveset(base, shadow):
    key = (base, shadow)
    if key not in _MOVESET:
        try:
            f, c = get_default_moveset(base, league='master', shadow=shadow)
            _MOVESET[key] = (f, list(c))
        except Exception:
            _MOVESET[key] = None
    return _MOVESET[key]


def _lv(level):
    level = float(level)
    return int(level) if level.is_integer() else level


def _moveset_segment(fast, charged):
    """'FAST-CHARGED1-CHARGED2' move-id segment, or None if under-specified."""
    if not fast or len(charged) < 2:
        return None
    return f"{fast}-{charged[0]}-{charged[1]}"


def focal_link_data(display, shadow, fast, charged):
    """The build-invariant pieces of a focal poke's battle link: its speciesId
    and move segment. IVs/level are per-candidate and filled by the caller (the
    client-side ML-guide compare panels vary them). None if unresolvable."""
    sid = species_id(display, shadow)
    seg = _moveset_segment(fast, charged)
    if not sid or not seg:
        return None
    return {'id': sid, 'moves': seg}


def opponent_link_data(opp_display):
    """The pieces of a meta opponent's battle link: its speciesId and default
    master move segment (opponents are always shown at 15/15/15). Level is filled
    by the caller (it varies by quadrant). None if unresolvable."""
    opp_shadow = '(Shadow)' in opp_display
    opp_base = opp_display.replace(' (Shadow)', '').strip()
    sid = species_id(opp_display, opp_shadow)
    moves = _opp_moveset(opp_base, opp_shadow)
    if not sid or not moves or len(moves[1]) < 2:
        return None
    return {'id': sid, 'moves': f"{moves[0]}-{moves[1][0]}-{moves[1][1]}"}


def battle_url(focal_display, focal_shadow, focal_ivs, focal_level,
               focal_fast, focal_charged, opp_display, opp_level,
               focal_shields, opp_shields):
    """A pvpoke.com battle URL for the focal (custom IVs/level/build) vs the
    opponent (15/15/15, default master moveset), at the given shields. None if
    anything can't be resolved. Composed from the same id/moveset pieces the
    client-side compare-panel links use (focal_link_data/opponent_link_data), so
    the two link paths can't drift on species/moveset resolution."""
    fd = focal_link_data(focal_display, focal_shadow, focal_fast, focal_charged)
    od = opponent_link_data(opp_display)
    if not fd or not od:
        return None
    p1 = f"{fd['id']}-{_lv(focal_level)}-{focal_ivs[0]}-{focal_ivs[1]}-{focal_ivs[2]}-4-4-1-1"
    p2 = f"{od['id']}-{_lv(opp_level)}-15-15-15-4-4-1-1"
    return (f"https://pvpoke.com/battle/10000/{p1}/{p2}/"
            f"{focal_shields}{opp_shields}/{fd['moves']}/{od['moves']}/")
