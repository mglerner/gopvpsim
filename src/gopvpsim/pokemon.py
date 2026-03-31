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

# Sorted level list, built once
_LEVELS = sorted(CPM.keys())


def cp(base_atk, base_def, base_sta, atk_iv, def_iv, sta_iv, level):
    """Compute CP at a given level. Minimum CP is 10."""
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
               *, max_cp, max_level=40.0):
    """Return the highest level at or under max_cp, or None if level 1 already exceeds it."""
    best = None
    for level in _LEVELS:
        if level > max_level:
            break
        if cp(base_atk, base_def, base_sta, atk_iv, def_iv, sta_iv, level) <= max_cp:
            best = level
    return best


# ---------------------------------------------------------------------------
# Gamemaster access
# ---------------------------------------------------------------------------

_pokemon_index = None


def get_pokemon_index():
    """Return a dict of speciesName -> baseStats from the gamemaster. Cached."""
    global _pokemon_index
    if _pokemon_index is None:
        gm = load_gamemaster()
        _pokemon_index = {mon['speciesName']: mon['baseStats'] for mon in gm['pokemon']}
    return _pokemon_index


def get_species(name):
    """Return the baseStats dict for a species by name, or raise KeyError."""
    return get_pokemon_index()[name]


# ---------------------------------------------------------------------------
# Pokemon dataclass
# ---------------------------------------------------------------------------

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

    @property
    def atk(self):
        return (self.base_atk + self.atk_iv) * CPM[self.level]

    @property
    def def_(self):
        return (self.base_def + self.def_iv) * CPM[self.level]

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
                      *, league='great', max_level=51.0):
        """Create a Pokemon at the highest level that fits under the league CP cap."""
        base = get_species(species_name)
        base_atk = base['atk']
        base_def = base['def']
        base_sta = base['hp']
        max_cp = LEAGUE_CAPS[league]
        level = best_level(base_atk, base_def, base_sta,
                           atk_iv, def_iv, sta_iv,
                           max_cp=max_cp, max_level=max_level)
        if level is None:
            raise ValueError(
                f"{species_name} with IVs {atk_iv}/{def_iv}/{sta_iv} "
                f"exceeds {max_cp} CP even at level 1"
            )
        return cls(species_name, base_atk, base_def, base_sta,
                   atk_iv, def_iv, sta_iv, level)
