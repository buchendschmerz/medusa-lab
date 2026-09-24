"""Colour palette for the Medusa Lab pixel art.

Sprites are drawn with single-character colour codes. ``BASE`` holds the
shared colours; each room/agent overrides a few "role" codes (hair ``H``,
clothes ``U``, accessory ``A``, wall ``X`` ...) so one sprite sheet can be
re-coloured per agent.
"""

from __future__ import annotations

from collections.abc import Mapping

Color = str | None

BASE: dict[str, Color] = {
    ".": None,       # transparent
    " ": None,
    # ink & neutrals
    "K": "#1a1423",  # outline / near black
    "k": "#3d3448",  # dark shade
    "g": "#6e6378",  # mid gray
    "G": "#a89fb0",  # light gray
    "W": "#f7f3e9",  # paper white
    "w": "#d9d0bf",  # paper shade
    # skin
    "s": "#f5c8a4",
    "S": "#d99a78",
    "p": "#f29191",  # blush
    "m": "#a8404f",  # mouth
    # accents (status hues follow the dataviz status palette)
    "R": "#d03b3b", "r": "#ff8a80",
    "O": "#eb6834", "o": "#ffb37a",
    "Y": "#fab219", "y": "#ffe699",
    "L": "#0ca30c", "l": "#8ee68e",
    "B": "#2a78d6", "b": "#86b6ef",
    "C": "#1baf7a", "c": "#7de8c1",
    "V": "#6a4fd6", "v": "#b8a8ff",
    "M": "#e87ba4",
    # screens
    "T": "#0b1a14",  # terminal background
    "t": "#3cff8f",  # terminal text
    "Q": "#12223b",  # monitor bezel glow
    # wood & floor
    "F": "#3a2519", "f": "#5a3a27", "D": "#7a5036", "d": "#a37453", "e": "#c79a72",
    # night sky (window)
    "N": "#141a33", "n": "#fff4c2",
    # chalkboard
    "j": "#1f3d2e", "J": "#2e5a44",
}

# Room/agent role colours: H hair, h hair highlight, U clothes, u clothes shade,
# A accessory, a accessory shade, X wall, x wall trim/pattern, Z name-plate.
ROLES: dict[str, dict[str, Color]] = {
    "scout": {"H": "#5b3a29", "h": "#7d5238", "U": "#d9722e", "u": "#a8531f",
              "A": "#c9a86a", "a": "#8f7443", "X": "#3a2a24", "x": "#46332b", "Z": "#eb6834"},
    "analyst": {"H": "#5a3d9a", "h": "#7d5fc4", "U": "#eeeaf6", "u": "#b9b1cf",
                "A": "#6a4fd6", "a": "#4a36a0", "X": "#27213f", "x": "#30294d", "Z": "#6a4fd6"},
    "coder": {"H": "#1f1b24", "h": "#3a3342", "U": "#1f8f67", "u": "#166b4d",
              "A": "#e6e0ee", "a": "#8a8198", "X": "#15232a", "x": "#1b2d36", "Z": "#1baf7a"},
    "writer": {"H": "#e3b35a", "h": "#f5d18a", "U": "#2f6fc2", "u": "#21528f",
               "A": "#233a66", "a": "#172745", "X": "#1c2743", "x": "#243152", "Z": "#2a78d6"},
    "reviewer": {"H": "#b8b3c4", "h": "#dcd8e6", "U": "#3b3346", "u": "#2a2433",
                 "A": "#d03b3b", "a": "#9c2626", "X": "#36202b", "x": "#432735", "Z": "#d03b3b"},
    "director": {"H": "#2f7a52", "h": "#4fb07c", "U": "#7a3d8f", "u": "#5a2b6a",
                 "A": "#fab219", "a": "#c98500", "X": "#1d2a24", "x": "#25362e", "Z": "#e87ba4"},
    "chrome": {"X": "#141220", "x": "#1e1b2e"},
}

# Status tones (dataviz status palette + a neutral and an active accent).
TONES: dict[str, str] = {
    "idle": "#6e6378",
    "active": "#2a78d6",
    "wait": "#fab219",
    "done": "#0ca30c",
    "error": "#d03b3b",
}


def palette_for(role: str | None = None, extra: Mapping[str, Color] | None = None) -> dict[str, Color]:
    pal = dict(BASE)
    if role:
        pal.update(ROLES[role])
    if extra:
        pal.update(extra)
    return pal


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def mix(a: str, b: str, t: float) -> str:
    """Linear blend of two hex colours (t=0 -> a, t=1 -> b)."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex(tuple(round(x + (y - x) * t) for x, y in zip(ra, rb, strict=True)))  # type: ignore[arg-type]


def luminance(color: str) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in hex_to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ink_on(color: str) -> str:
    """Black or white ink, whichever reads better on ``color``."""
    return BASE["K"] if luminance(color) > 0.35 else BASE["W"]  # type: ignore[return-value]
