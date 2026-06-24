"""
Stat calculation: CP, level, IV, stat product.

All battle stats follow the standard PoGo formulas:
  CP   = floor((base_atk+atk_iv) * sqrt(base_def+def_iv) * sqrt(base_sta+sta_iv) * cpm^2 / 10)
  atk  = (base_atk + atk_iv) * cpm
  def  = (base_def + def_iv) * cpm
  hp   = floor((base_sta + sta_iv) * cpm)

Note: the gamemaster uses 'hp' (not 'sta') for the base stamina stat.

Validate all stat calculations against PvPoke before using battle logic.
"""
import math
from dataclasses import dataclass

from .data import load_gamemaster

# CP multiplier table — source: gamepress.gg/pokemongo/cp-multiplier
CPM = {
    1.0: 0.094,       1.5: 0.1351374318, 2.0: 0.16639787,  2.5: 0.192650919,
    3.0: 0.21573247,  3.5: 0.2365726613, 4.0: 0.25572005,  4.5: 0.2735303812,
    5.0: 0.29024988,  5.5: 0.3060573775, 6.0: 0.3210876,   6.5: 0.3354450362,
    7.0: 0.34921268,  7.5: 0.3624577511, 8.0: 0.3752356,   8.5: 0.387592416,
    9.0: 0.39956728,  9.5: 0.4111935514, 10.0: 0.4225,     10.5: 0.4329264091,
    11.0: 0.44310755, 11.5: 0.4530599591, 12.0: 0.4627984, 12.5: 0.472336093,
    13.0: 0.48168495, 13.5: 0.4908558003, 14.0: 0.49985844, 14.5: 0.508701765,
    15.0: 0.51739395, 15.5: 0.5259425113, 16.0: 0.5343543, 16.5: 0.5426357375,
    17.0: 0.5507927,  17.5: 0.5588305862, 18.0: 0.5667545, 18.5: 0.5745691333,
    19.0: 0.5822789,  19.5: 0.5898879072, 20.0: 0.5974,    20.5: 0.6048236651,
    21.0: 0.6121573,  21.5: 0.6194041216, 22.0: 0.6265671, 22.5: 0.6336491432,
    23.0: 0.64065295, 23.5: 0.6475809666, 24.0: 0.65443563, 24.5: 0.6612192524,
    25.0: 0.667934,   25.5: 0.6745818959, 26.0: 0.6811649, 26.5: 0.6876849038,
    27.0: 0.69414365, 27.5: 0.70054287,  28.0: 0.7068842,  28.5: 0.7131691091,
    29.0: 0.7193991,  29.5: 0.7255756136, 30.0: 0.7317,    30.5: 0.7347410093,
    31.0: 0.7377695,  31.5: 0.7407855938, 32.0: 0.74378943, 32.5: 0.7467812109,
    33.0: 0.74976104, 33.5: 0.7527290867, 34.0: 0.7556855, 34.5: 0.7586303683,
    35.0: 0.76156384, 35.5: 0.7644860647, 36.0: 0.76739717, 36.5: 0.7702972656,
    37.0: 0.7731865,  37.5: 0.7760649616, 38.0: 0.77893275, 38.5: 0.7817900548,
    39.0: 0.784637,   39.5: 0.7874736075, 40.0: 0.7903,    40.5: 0.792803968,
    41.0: 0.79530001, 41.5: 0.797800015,  42.0: 0.8003,    42.5: 0.802799995,
    43.0: 0.8053,     43.5: 0.8078,       44.0: 0.81029999, 44.5: 0.812799985,
    45.0: 0.81529999, 45.5: 0.81779999,   46.0: 0.82029999, 46.5: 0.82279999,
    47.0: 0.82529999, 47.5: 0.82779999,   48.0: 0.83029999, 48.5: 0.83279999,
    49.0: 0.83529999, 49.5: 0.83779999,   50.0: 0.84029999, 50.5: 0.84279999,
    51.0: 0.84529999,
}

LEAGUE_CAPS = {
    'great':  1500,
    'ultra':  2500,
    'master': 10000,
}

LEAGUE_CP = {
    'little': 500,
    'great':  1500,
    'ultra':  2500,
    'master': 10000,
}

# Max power-up level per league.  Best-buddy adds +1 level but only
# one mon can be best-buddied at a time, so the default excludes it
# for GL/UL.  Master League keeps 51 because best-buddy matters more
# in an uncapped format.
LEAGUE_MAX_LEVEL = {
    'little': 51.0,
    'great':  50.0,
    'ultra':  50.0,
    'master': 51.0,
}

# Highest level that exists in the CPM table (the hard ceiling — best-buddy
# can never push past this).
MAX_CPM_LEVEL = max(CPM)


def bestbuddy_caps(league):
    """Return (default_cap, alt_cap) for a league's best-buddy toggle.

    ``default_cap`` is the league's normal max power-up level; ``alt_cap`` is
    one level higher (best-buddy = +1 level), clamped to the CPM table ceiling.
    When ``alt_cap == default_cap`` the toggle is a no-op for the whole league
    (Master/Little, already at 51) and callers should suppress it.
    """
    default_cap = LEAGUE_MAX_LEVEL.get(league, MAX_CPM_LEVEL)
    alt_cap = min(MAX_CPM_LEVEL, default_cap + 1.0)
    return default_cap, alt_cap


# Sorted level list, built once
_LEVELS = sorted(CPM.keys())


def cp(base_atk, base_def, base_sta, atk_iv, def_iv, sta_iv, level):
    """Compute CP at a given level. Minimum CP is 10.

    Shadow status does NOT affect CP — it only affects battle stats.
    CP is always calculated from base stats + IVs, same for shadow and non-shadow.
    """
    cpm = CPM[level]
    raw = (
        (base_atk + atk_iv)
        * math.sqrt(base_def + def_iv)
        * math.sqrt(base_sta + sta_iv)
        * cpm ** 2
        / 10
    )
    return max(10, math.floor(raw))


def battle_stats(base_atk, base_def, base_sta, atk_iv, def_iv, sta_iv, level):
    """Compute battle stats (atk, def, hp) at a given level."""
    cpm = CPM[level]
    return {
        'atk': (base_atk + atk_iv) * cpm,
        'def': (base_def + def_iv) * cpm,
        'hp':  math.floor((base_sta + sta_iv) * cpm),
    }


def stat_product(atk, def_, hp):
    """Compute stat product from battle stats."""
    return atk * def_ * hp


def best_level(base_atk, base_def, base_sta, atk_iv, def_iv, sta_iv,
               *, max_cp, max_level=40.0, min_level=1.0):
    """Return the highest level in [min_level, max_level] at or under max_cp,
    or None if no level in that range fits. min_level supports mons that are
    already powered up: levels can't go down, so a mon above the cap at its
    current level has no legal build for the league."""
    best = None
    for level in _LEVELS:
        if level > max_level:
            break
        if level < min_level:
            continue
        if cp(base_atk, base_def, base_sta, atk_iv, def_iv, sta_iv, level) <= max_cp:
            best = level
    return best


# ---------------------------------------------------------------------------
# Gamemaster access
# ---------------------------------------------------------------------------

_pokemon_index = None
_gm_entry_index = None
_gm_id_index = None


def get_pokemon_index():
    """Return a dict of speciesName -> baseStats from the gamemaster. Cached."""
    global _pokemon_index
    if _pokemon_index is None:
        gm = load_gamemaster()
        _pokemon_index = {mon['speciesName']: mon['baseStats'] for mon in gm['pokemon']}
    return _pokemon_index


def get_pokemon_entry(name: str) -> dict:
    """Return the full gamemaster entry for a species by speciesName."""
    global _gm_entry_index
    if _gm_entry_index is None:
        gm = load_gamemaster()
        _gm_entry_index = {mon['speciesName']: mon for mon in gm['pokemon']}
    return _gm_entry_index[name]


def get_pokemon_entry_by_id(species_id: str) -> dict:
    """Return the full gamemaster entry for a species by speciesId.

    The formChange.alternativeFormId field uses speciesId (e.g. 'aegislash_blade'),
    so this lookup is needed to resolve form change targets.
    """
    global _gm_id_index
    if _gm_id_index is None:
        gm = load_gamemaster()
        _gm_id_index = {mon['speciesId']: mon for mon in gm['pokemon']}
    return _gm_id_index[species_id]


def get_species(name):
    """Return the baseStats dict for a species by name, or raise KeyError."""
    return get_pokemon_index()[name]


# ---------------------------------------------------------------------------
# Pokemon dataclass
# ---------------------------------------------------------------------------

SHADOW_ATK_BONUS = 6 / 5   # ×1.2
SHADOW_DEF_MULT  = 5 / 6   # ×0.8333…


@dataclass
class Pokemon:
    """A Pokemon ready for battle: species + IVs + level."""
    species:  str
    base_atk: float
    base_def: float
    base_sta: int      # gamemaster calls this 'hp'
    atk_iv:   int
    def_iv:   int
    sta_iv:   int
    level:    float
    shadow:   bool = False

    @property
    def atk(self):
        base = (self.base_atk + self.atk_iv) * CPM[self.level]
        return base * SHADOW_ATK_BONUS if self.shadow else base

    @property
    def def_(self):
        base = (self.base_def + self.def_iv) * CPM[self.level]
        return base * SHADOW_DEF_MULT if self.shadow else base

    @property
    def hp(self):
        return math.floor((self.base_sta + self.sta_iv) * CPM[self.level])

    @property
    def cp(self):
        return cp(self.base_atk, self.base_def, self.base_sta,
                  self.atk_iv, self.def_iv, self.sta_iv, self.level)

    @property
    def stat_product(self):
        return stat_product(self.atk, self.def_, self.hp)

    @classmethod
    def at_best_level(cls, species_name, atk_iv, def_iv, sta_iv,
                      *, league='great', max_level=None, shadow=False):
        """Create a Pokemon at the highest level that fits under the league CP cap."""
        base = get_species(species_name)
        base_atk = base['atk']
        base_def = base['def']
        base_sta = base['hp']
        max_cp = LEAGUE_CAPS[league]
        if max_level is None:
            max_level = LEAGUE_MAX_LEVEL.get(league, 51.0)
        level = best_level(base_atk, base_def, base_sta,
                           atk_iv, def_iv, sta_iv,
                           max_cp=max_cp, max_level=max_level)
        if level is None:
            raise ValueError(
                f"{species_name} with IVs {atk_iv}/{def_iv}/{sta_iv} "
                f"exceeds {max_cp} CP even at level 1"
            )
        # Aegislash (Blade) powers up in whole-level increments only,
        # not half-levels — see PvPoke's getFormStats() (newLevel--)
        # and the in-game form-change rule discovered by cascade1185.
        # The standard half-level grid is wrong for Blade as the focal
        # species; round down so the listed CP/stats match what real
        # PvP players actually build.
        if species_name == 'Aegislash (Blade)' and level % 1.0 != 0:
            level -= 0.5
        return cls(species_name, base_atk, base_def, base_sta,
                   atk_iv, def_iv, sta_iv, level, shadow=shadow)


# ---------------------------------------------------------------------------
# IV ranking
# ---------------------------------------------------------------------------

def iv_rank(species_name: str, *, league: str = 'great', max_level: float = None,
            shadow: bool = False) -> list[dict]:
    """
    Return all 4096 IV combinations (0–15 each) for a species, ranked by
    stat product (descending).  Combinations that exceed the CP cap even at
    level 1 are omitted (rare, but possible for very low base-stat mons in
    higher leagues).

    Each entry is a dict:
        rank, atk_iv, def_iv, sta_iv, level, atk, def_, hp, stat_product, cp
    Rank 1 is the highest stat product.
    """
    base = get_species(species_name)
    base_atk = base['atk']
    base_def = base['def']
    base_sta = base['hp']
    max_cp   = LEAGUE_CAPS[league]
    if max_level is None:
        max_level = LEAGUE_MAX_LEVEL.get(league, 51.0)

    shadow_atk_mult = SHADOW_ATK_BONUS if shadow else 1.0
    shadow_def_mult = SHADOW_DEF_MULT  if shadow else 1.0

    # Aegislash (Blade) powers up in whole-level increments only;
    # mirror the rounding from Pokemon.at_best_level.
    _blade_round_down = (species_name == 'Aegislash (Blade)')

    entries = []
    for a in range(16):
        for d in range(16):
            for s in range(16):
                lv = best_level(base_atk, base_def, base_sta, a, d, s,
                                max_cp=max_cp, max_level=max_level)
                if lv is None:
                    continue
                if _blade_round_down and lv % 1.0 != 0:
                    lv -= 0.5
                cpm = CPM[lv]
                atk  = (base_atk + a) * cpm * shadow_atk_mult
                def_ = (base_def + d) * cpm * shadow_def_mult
                hp   = math.floor((base_sta + s) * cpm)
                entries.append({
                    'atk_iv': a, 'def_iv': d, 'sta_iv': s,
                    'level': lv,
                    'atk': atk, 'def_': def_, 'hp': hp,
                    'stat_product': atk * def_ * hp,
                    'cp': cp(base_atk, base_def, base_sta, a, d, s, lv),
                })

    # Sort by stat product descending; break ties by total IV sum descending
    # (when stats are identical due to floor/CPM rounding, the higher-IV
    # spread is preferred — this matches PvPoke's tie-breaking behavior).
    entries.sort(
        key=lambda e: (e['stat_product'], e['atk_iv'] + e['def_iv'] + e['sta_iv']),
        reverse=True,
    )
    for i, e in enumerate(entries):
        e['rank'] = i + 1
    return entries


def pvpoke_default_ivs(species_name: str, league: str = 'great',
                       level_cap: float = 50.0) -> tuple:
    """
    Return (level, atk_iv, def_iv, sta_iv) using PvPoke's default IV selection.

    Reads the pre-computed defaultIVs from the gamemaster JSON, exactly as
    PvPoke does at runtime.  For league='master' always returns 15/15/15.
    For level_cap=40, uses the l40 variant when available (e.g. Medicham in
    Great League).

    league: 'little' (500 CP), 'great' (1500), 'ultra' (2500), 'master' (10000)
    """
    cap = LEAGUE_CP.get(league)
    if cap is None:
        raise ValueError(f"Unknown league {league!r}. Use 'little', 'great', 'ultra', or 'master'.")

    if cap == 10000:
        return (level_cap, 15, 15, 15)

    entry = get_pokemon_entry(species_name)
    default_ivs = entry.get('defaultIVs', {})
    key = f'cp{cap}'

    combo = default_ivs.get(f'{key}l40') if level_cap == 40 else None
    if combo is None:
        combo = default_ivs.get(key)
    if combo is None:
        raise ValueError(
            f"No defaultIVs[{key!r}] for {species_name!r} in the gamemaster."
        )

    level, atk_iv, def_iv, sta_iv = combo
    return (float(level), int(atk_iv), int(def_iv), int(sta_iv))


# ---------------------------------------------------------------------------
# compute_default_ivs — mirrors PvPoke's generateDefaultIVsByPokemon() dev tool
# ---------------------------------------------------------------------------

# Legendaries whose level cap is NOT 40 in PvPoke (they can be powered past 40)
_LEVEL_CAP_EXCLUSIONS = frozenset([
    "melmetal",
    "thundurus_incarnate", "thundurus_therian",
    "landorus_incarnate",  "landorus_therian",
    "tornadus_incarnate",  "tornadus_therian",
    "rayquaza",
])

# Hard-coded overrides from PvPoke's generateDefaultIVsByPokemon switch block.
# Applied after the algorithm runs, keyed by speciesId → cp-key → (level, a, d, s).
_DEFAULT_IV_EXCEPTIONS: dict[str, dict[str, tuple]] = {
    'trevenant':       {'cp1500': (22,    3,  13, 12)},
    'dhelmise':        {'cp1500': (20,    1,   4,  4)},
    'medicham':        {'cp1500': (49,    7,  15, 14)},
    'lokix':           {'cp2500': (47.5, 11,  15, 15)},
    'regidrago':       {'cp1500': (20,    2,   4,  4)},
    'aegislash_blade': {'cp1500': (22,    4,  14, 15), 'cp2500': (38, 15, 15, 15)},
}


def _iv_combo_best_level(
    base_atk, base_def, base_sta,
    atk_iv, def_iv, hp_iv,
    cap, level_cap, level_floor,
):
    """
    Find the best level for an IV combo under cap, mimicking PvPoke's
    step-up / step-back loop in generateIVCombinations().
    Returns (level, cp) or (None, None) if the combo can't fit.
    """
    level = level_floor
    calc_cp = 0
    while level < level_cap and calc_cp < cap:
        level += 0.5
        calc_cp = cp(base_atk, base_def, base_sta, atk_iv, def_iv, hp_iv, level)
    if calc_cp > cap:
        level -= 0.5
        calc_cp = cp(base_atk, base_def, base_sta, atk_iv, def_iv, hp_iv, level)
    if calc_cp <= cap:
        return level, calc_cp
    return None, None


def _generate_iv_combinations(
    base_atk, base_def, base_sta, cap, level_cap, iv_floor, level_floor=1.0,
):
    """
    Return all IV combos (each IV in [iv_floor..15]) under cap at level_cap,
    sorted by stat product descending. Mirrors PvPoke's generateIVCombinations().

    Iteration order hp→def→atk (all 15 down to floor) matches PvPoke;
    Python's stable sort preserves this for ties.
    """
    combos = []
    for hp_iv in range(15, iv_floor - 1, -1):
        for def_iv in range(15, iv_floor - 1, -1):
            for atk_iv in range(15, iv_floor - 1, -1):
                level, _ = _iv_combo_best_level(
                    base_atk, base_def, base_sta, atk_iv, def_iv, hp_iv,
                    cap, level_cap, level_floor,
                )
                if level is None:
                    continue
                cpm_val = CPM[level]
                combos.append({
                    'level':  level,
                    'atk_iv': atk_iv,
                    'def_iv': def_iv,
                    'sta_iv': hp_iv,
                    'stat_product': (
                        (base_atk + atk_iv) * cpm_val
                        * (base_def + def_iv) * cpm_val
                        * math.floor((base_sta + hp_iv) * cpm_val)
                    ),
                })
    combos.sort(key=lambda c: c['stat_product'], reverse=True)
    return combos


def _pick_default_combo(
    base_atk, base_def, base_sta, tags, level_floor,
    cap, level_cap, near_cap_cp,
):
    """
    Run generateDefaultIVCombo() for one league/level_cap pair:
    choose the IV floor, generate combos, return the result at the appropriate rank.
    """
    iv_floor = 4
    if near_cap_cp < cap:
        iv_floor = 12   # near-cap: assume lucky-trade-eligible IVs (floor 12)
    if 'legendary' in tags and 'shadow' in tags:
        iv_floor = 6

    combos = _generate_iv_combinations(
        base_atk, base_def, base_sta, cap, level_cap, iv_floor, level_floor,
    )
    if not combos:
        # Retry without level floor (PvPoke's fallback)
        combos = _generate_iv_combinations(
            base_atk, base_def, base_sta, cap, level_cap, iv_floor, 1.0,
        )
    if not combos:
        return None

    # Rank index: 1 (rank 2) for regular; 31 (rank 32) for legendary/untradeable;
    # 249 (rank 250) for shadow legendary.
    idx = 1
    if 'untradeable' in tags:
        idx = 31
    if 'legendary' in tags:
        idx = 31
    if 'shadow' in tags and 'legendary' in tags:
        idx = 249

    if idx >= len(combos):
        idx = len(combos) // 2

    c = combos[idx]
    return (float(c['level']), int(c['atk_iv']), int(c['def_iv']), int(c['sta_iv']))


def compute_default_ivs(species_name: str, league: str = 'great',
                        level_cap: float = 50.0) -> tuple:
    """
    Compute PvPoke's default IVs from scratch, mimicking generateDefaultIVsByPokemon().

    Implements the algorithm PvPoke's dev tool uses to pre-compute defaultIVs
    in gamemaster.json.  Useful for verification or for custom Pokemon not in
    the gamemaster.

    NOTE: The current PvPoke source uses iv_floor=4 in generateDefaultIVCombo().
    However, the gamemaster.json was generated with an older version of the
    algorithm that appears to have used iv_floor=2 for many Pokemon.  Expect
    small differences (~3–5%) between this function and pvpoke_default_ivs()
    for common non-legendary Pokemon.  pvpoke_default_ivs() is always authoritative.

    Returns (level, atk_iv, def_iv, sta_iv).
    league:    'little' (500), 'great' (1500), 'ultra' (2500), 'master' (10000)
    level_cap: 40 to compute the l40 variant (e.g. for level-40-capped formats)
    """
    cap = LEAGUE_CP.get(league)
    if cap is None:
        raise ValueError(
            f"Unknown league {league!r}. Use 'little', 'great', 'ultra', or 'master'."
        )
    if cap == 10000:
        return (level_cap, 15, 15, 15)

    entry      = get_pokemon_entry(species_name)
    base       = entry['baseStats']
    base_atk   = base['atk']
    base_def   = base['def']
    base_sta   = base['hp']
    tags       = set(entry.get('tags', []))
    level_floor = float(entry.get('levelFloor', 1))
    species_id  = entry['speciesId']
    cp_key      = f'cp{cap}'

    # Hard-coded exceptions apply only to the standard (non-l40) case
    if level_cap != 40:
        exc = _DEFAULT_IV_EXCEPTIONS.get(species_id, {}).get(cp_key)
        if exc is not None:
            return (float(exc[0]), int(exc[1]), int(exc[2]), int(exc[3]))

    # near-cap CP: level 35 for l40 variant, level 45 for standard
    near_level  = 35.0 if level_cap == 40 else 45.0
    near_cap_cp = cp(base_atk, base_def, base_sta, 15, 15, 15, near_level)

    max_cp_at_cap = cp(base_atk, base_def, base_sta, 15, 15, 15, level_cap)
    if max_cp_at_cap <= cap:
        return (float(level_cap), 15, 15, 15)

    result = _pick_default_combo(
        base_atk, base_def, base_sta, tags, level_floor,
        cap, level_cap, near_cap_cp,
    )
    return result if result is not None else (1.0, 0, 0, 0)
