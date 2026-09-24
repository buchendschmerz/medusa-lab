"""Hand-made sprite sheet (colour codes: see :mod:`medusa.pixelart.palette`).

Characters are chibi researchers seen from the front, sitting behind a desk.
Role codes (``H`` hair, ``U`` clothes, ``A`` accessory ...) are recoloured per
agent, so one head/body serves every lab member.
"""

from __future__ import annotations

# ----------------------------------------------------------------------------- character
HEAD = (
    "...KKKKKK...",
    "..KHHHHHHK..",
    ".KHHhhHHHHK.",
    "KHHhHHHHHHHK",
    "KHHHHHHHHHHK",
    "KHHsHHHHsHHK",
    "KHssssssssHK",
    "KHsKssssKsHK",
    "KHsKssssKsHK",
    ".KspsssspsK.",
    "..KssmmssK..",
    "...KKKKKK...",
)

# eyes closed (blink / sleep): a short line instead of the 2px-tall eye
HEAD_BLINK_PATCH = {(3, 7): "s", (8, 7): "s", (2, 8): "K", (4, 8): "s", (7, 8): "s", (9, 8): "K"}
# happy squint ^^ + open mouth
HEAD_HAPPY_PATCH = {(3, 7): "K", (3, 8): "s", (2, 8): "K", (4, 8): "K",
                    (8, 7): "K", (8, 8): "s", (7, 8): "K", (9, 8): "K",
                    (5, 10): "m", (6, 10): "m"}
# worried: eyebrows up, small mouth
HEAD_WORRY_PATCH = {(2, 6): "K", (9, 6): "K", (5, 10): "s", (6, 10): "m"}
# looking right (towards the props): pupils shift one pixel
HEAD_LOOK_RIGHT_PATCH = {(3, 7): "s", (3, 8): "s", (4, 7): "K", (4, 8): "K",
                         (8, 7): "s", (8, 8): "s", (9, 7): "K", (9, 8): "K"}

BODY = (
    "....KSSK....",
    "..KUUWWUUK..",
    ".KUUUWWUUUK.",
    "KUUUUUUUUUUK",
    "KUuUUUUUUuUK",
    "KUuUUUUUUuUK",
    "KUuUUUUUUuUK",
)

# Arms/hands relative to the body's top-left corner.
HANDS_REST = {"left": (1, 7), "right": (9, 7)}

# ----------------------------------------------------------------------------- accessories
HAT_SCOUT = (  # pith helmet (placed at head x-1, y-3)
    ".....aAAAa....",
    "...aAAAAAAAa..",
    "..aAAAAAAAAAa.",
    "aaaaaaaaaaaaaa",
)
GLASSES_ROUND = (  # thin round frames, placed at head x, y+6
    "..KKK..KKK..",
    ".KW..KKW..K.",
    ".K...KK...K.",
    "..KKK..KKK..",
)
GLASSES_HALF = (  # half-moon reading glasses (reviewer), placed at head x, y+8
    "..K.KKKK.K..",
    "..KKK..KKK..",
)
HEADPHONES = (  # placed at head x-1, y-1
    "...kkkkkkkk...",
    "..k........k..",
    ".k..........k.",
    ".k..........k.",
    ".k..........k.",
    "AA..........AA",
    "AA..........AA",
    "AA..........AA",
    "aA..........Aa",
)
BERET = (  # placed at head x, y-2
    "......a.....",
    "..AAAAAAAa..",
    ".AAAAAAAAAAa",
    "AAAAAAAAAAa.",
)
TIE_RED = (  # reviewer's tie, placed at body x+5, y+1
    "RR",
    "rR",
    "RR",
    ".R",
)

# ----------------------------------------------------------------------------- icons & bubbles
BUBBLE = (  # speech bubble (text area: x+2..x+8, y+1..y+5)
    ".KKKKKKKKK.",
    "KWWWWWWWWWK",
    "KWWWWWWWWWK",
    "KWWWWWWWWWK",
    "KWWWWWWWWWK",
    "KWWWWWWWWWK",
    ".KKKKKKKKK.",
    "..KWK......",
    "..KK.......",
    "..K........",
)
BUBBLE_THINK = (  # thought bubble with trailing circles
    ".KKKKKKKKK.",
    "KWWWWWWWWWK",
    "KWWWWWWWWWK",
    "KWWWWWWWWWK",
    "KWWWWWWWWWK",
    "KWWWWWWWWWK",
    ".KKKKKKKKK.",
    "..KWK......",
    "...K.......",
    ".KW........",
)
ZZZ = (  # "Zz"
    "WWWW...",
    "...W...",
    "..W....",
    ".W.WWW.",
    "WWWW.W.",
    "....W..",
    "...WWW.",
)
BULB_ON = (
    ".yYy.",
    "yYYYy",
    "yYYYy",
    ".yYy.",
    ".GgG.",
    "..g..",
)
BULB_OFF = (
    ".GgG.",
    "GgggG",
    "GgggG",
    ".GgG.",
    ".GkG.",
    "..k..",
)
SPARKLE = (
    "..y..",
    "..Y..",
    "yYWYy",
    "..Y..",
    "..y..",
)
SPARKLE_SMALL = (
    ".y.",
    "yWy",
    ".y.",
)
SWEAT = (
    ".b",
    "bb",
    "bB",
)
CHECK = (
    "......L",
    ".....LL",
    "L...LL.",
    "LL.LL..",
    ".LLL...",
    "..L....",
)
CROSS = (
    "R...R",
    ".R.R.",
    "..R..",
    ".R.R.",
    "R...R",
)
BUG = (
    "K...K",
    ".KRK.",
    "KRRRK",
    ".RKR.",
    "KRRRK",
    ".K.K.",
)
MAGNIFIER = (
    ".KKK...",
    "KbWbK..",
    "KWbbK..",
    "KbbbK..",
    ".KKKd..",
    "....dd.",
    ".....dd",
)
COFFEE = (
    ".w.w.",
    "w.w..",
    "WWWW.",
    "WwwWW",
    "WwwW.",
    ".WW..",
)
COFFEE_STEAM_B = (
    "w.w..",
    ".w.w.",
    "WWWW.",
    "WwwWW",
    "WwwW.",
    ".WW..",
)
SPINNER = (  # ring; one segment is highlighted per frame (see scenes._spinner)
    ".GGG.",
    "G...G",
    "G...G",
    "G...G",
    ".GGG.",
)
SPINNER_SEGMENTS = (((1, 0), (2, 0), (3, 0)), ((4, 1), (4, 2), (4, 3)),
                    ((1, 4), (2, 4), (3, 4)), ((0, 1), (0, 2), (0, 3)))
PENCIL = (
    "....yK",
    "...yYy",
    "..yYy.",
    ".eYy..",
    "Kke...",
)
RED_PEN = (
    "....rK",
    "...rRr",
    "..rRr.",
    ".RRr..",
    "RR....",
)

# ----------------------------------------------------------------------------- mascot
SNAKE_A = (  # coiled Medusa snake, tongue in
    "..cCC...",
    ".cCKCC..",
    ".CCCCC..",
    "..CCC...",
    ".cCCCCc.",
    "CCccccCC",
    ".CCCCCC.",
)
SNAKE_B = (  # tongue out
    "..cCC.R.",
    ".cCKCCR.",
    ".CCCCC..",
    "..CCC...",
    ".cCCCCc.",
    "CCccccCC",
    ".CCCCCC.",
)

# ----------------------------------------------------------------------------- pipeline icons (7x7)
STAGE_ICONS: dict[str, tuple[str, ...]] = {
    "theme": (
        ".......",
        "WWWWWWW",
        "WW...WW",
        "W.W.W.W",
        "W..W..W",
        "W.....W",
        "WWWWWWW",
    ),
    "scout": (
        ".WWW...",
        "W...W..",
        "W...W..",
        "W...W..",
        ".WWWW..",
        "....WW.",
        ".....WW",
    ),
    "analyst": (
        "..WWW..",
        ".W...W.",
        ".W...W.",
        "..W.W..",
        "..WWW..",
        "..WWW..",
        "...W...",
    ),
    "coder": (
        "WWWWWWW",
        "W.....W",
        "W.W...W",
        "W..W..W",
        "W.W.WWW",
        "WWWWWWW",
        "..WWW..",
    ),
    "writer": (
        ".....WW",
        "....WWW",
        "...WWW.",
        "..WWW..",
        ".WWW...",
        "WWW....",
        "W......",
    ),
    "review": (
        "WWWWW..",
        "W...W..",
        "W.W.W..",
        "W...WW.",
        "W.W.W.W",
        "W...WWW",
        "WWWWW..",
    ),
    "publish": (
        "...W...",
        "..WWW..",
        "..W.W..",
        "..WWW..",
        ".WWWWW.",
        "WW.W.WW",
        "...W...",
    ),
}
