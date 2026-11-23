#!/usr/bin/env python3
"""The shop's label font: straight lines and 45-degree corners only, no curves (user, V4 2026-11-21).

User (2026-11-23): "the labels should be smaller ... we changed that circle ... we don't have the
curves". This is the font of the ClaudeV4-V17 D-sheet files. The letter shapes below were read
back from those files, stroke for stroke (D1-D10 ClaudeV16: 68 words and 10 badges), so a sheet
converted here gets exactly the letters the user approved.

  grid     : every letter is drawn on whole grid units, 20 units tall, 12 wide (I 0, 1 4, L 11, M 14)
  size     : 1 unit = 1.2045 mm -> letters 24.09 mm (0.95 in) tall; the user's "24 mm"
  spacing  : 10 units between letters = 12 mm between cut centres = 6 mm of wood with the 6 mm bit
  badge    : the sheet name in a box with clipped corners (no circle): the box line is 14 units
             (16.9 mm) from the letters all round, corners clipped 6 units (7.2 mm)
  not cut yet: J N T W X Z are drawn here in the same style but have never been on a sheet.
             Say so the first time one is used.
"""
import math

UNIT = 1.2045            # mm per grid unit
CAP = 20                 # letter height, units
GAP = 10                 # between letters, units
BOX_MARGIN = 14          # badge box line to the letters, units
BOX_CLIP = 6             # badge box corner clip, units
NOT_CUT_YET = set('JNTWXZ')

_O = [[(4, 20), (8, 20), (12, 16), (12, 4), (8, 0), (4, 0), (0, 4), (0, 16), (4, 20)]]
GLYPHS = {      # letter: (width, strokes), in units, baseline y = 0
    '0': (12, _O),
    '1': (4, [[(0, 16), (4, 20), (4, 0)]]),
    '2': (12, [[(0, 16), (4, 20), (8, 20), (12, 16), (12, 12), (0, 0), (12, 0)]]),
    '3': (12, [[(0, 20), (8, 20), (12, 16), (12, 14), (8, 10), (4, 10)], [(8, 10), (12, 6), (12, 4), (8, 0), (0, 0)]]),
    '4': (12, [[(0, 20), (0, 9), (12, 9)], [(12, 20), (12, 0)]]),
    '5': (12, [[(12, 20), (0, 20), (0, 10), (8, 10), (12, 6), (12, 4), (8, 0), (0, 0)]]),
    '6': (12, [[(10, 20), (4, 20), (0, 16), (0, 4), (4, 0), (8, 0), (12, 4), (12, 6), (8, 10), (0, 10)]]),
    '7': (12, [[(0, 20), (12, 20), (4, 0)]]),
    '8': (12, [[(4, 10), (0, 14), (0, 16), (4, 20), (8, 20), (12, 16), (12, 14), (8, 10), (4, 10), (0, 6), (0, 4), (4, 0),
                (8, 0), (12, 4), (12, 6), (8, 10)]]),
    '9': (12, [[(12, 10), (4, 10), (0, 14), (0, 16), (4, 20), (8, 20), (12, 16), (12, 4), (8, 0), (2, 0)]]),
    'A': (12, [[(0, 0), (0, 16), (4, 20), (8, 20), (12, 16), (12, 0)], [(0, 8), (12, 8)]]),
    'B': (12, [[(0, 0), (0, 20), (9, 20), (11, 18), (11, 12), (9, 10), (0, 10)], [(9, 10), (10, 10), (12, 8), (12, 2), (10, 0), (0, 0)]]),
    'C': (12, [[(12, 20), (4, 20), (0, 16), (0, 4), (4, 0), (12, 0)]]),
    'D': (12, [[(0, 20), (8, 20), (12, 16), (12, 4), (8, 0), (0, 0), (0, 20)]]),
    'E': (12, [[(12, 20), (0, 20), (0, 0), (12, 0)], [(0, 10), (9, 10)]]),
    'F': (12, [[(12, 20), (0, 20), (0, 0)], [(0, 10), (9, 10)]]),
    'G': (12, [[(12, 20), (4, 20), (0, 16), (0, 4), (4, 0), (12, 0), (12, 10), (9, 10)]]),
    'H': (12, [[(0, 20), (0, 0)], [(12, 20), (12, 0)], [(0, 10), (12, 10)]]),
    'I': (0, [[(0, 20), (0, 0)]]),
    'K': (12, [[(0, 20), (0, 0)], [(12, 20), (0, 8)], [(4, 12), (12, 0)]]),
    'L': (11, [[(0, 20), (0, 0), (11, 0)]]),
    'M': (14, [[(0, 0), (0, 20), (7, 12), (14, 20), (14, 0)]]),
    'O': (12, _O),
    'P': (12, [[(0, 0), (0, 20), (8, 20), (12, 16), (12, 13), (8, 9), (0, 9)]]),
    'Q': (12, _O + [[(7, 5), (13, -1)]]),            # the tail ends 1 unit below the line and 1 past the width
    'R': (12, [[(0, 0), (0, 20), (8, 20), (12, 16), (12, 13), (8, 9), (0, 9)], [(8, 9), (12, 5), (12, 0)]]),
    'S': (12, [[(12, 20), (4, 20), (0, 16), (0, 14), (4, 10), (8, 10), (12, 6), (12, 4), (8, 0), (0, 0)]]),
    'U': (12, [[(0, 20), (0, 4), (4, 0), (8, 0), (12, 4), (12, 20)]]),
    'V': (12, [[(0, 20), (6, 0), (12, 20)]]),
    'Y': (12, [[(0, 20), (6, 10), (12, 20)], [(6, 10), (6, 0)]]),
    # ---- same style, never cut on a sheet yet (NOT_CUT_YET)
    'J': (12, [[(12, 20), (12, 4), (8, 0), (4, 0), (0, 4), (0, 6)]]),
    'N': (12, [[(0, 0), (0, 20), (12, 0), (12, 20)]]),
    'T': (12, [[(0, 20), (12, 20)], [(6, 20), (6, 0)]]),
    'W': (14, [[(0, 20), (0, 0), (7, 8), (14, 0), (14, 20)]]),
    'X': (12, [[(0, 0), (12, 20)], [(0, 20), (12, 0)]]),
    'Z': (12, [[(0, 20), (12, 20), (0, 0), (12, 0)]]),
}


def upright(text, unit=UNIT):
    """-> (strokes in mm, width in mm): the text standing upright, baseline at y = 0, starting at x = 0.
    The width is the nominal one (letter widths + gaps): a Q's tail is not counted."""
    x, out = 0.0, []
    for k, ch in enumerate(text.upper()):
        if ch not in GLYPHS:
            raise SystemExit(f'label font: no letter for {ch!r} - draw it in blockfont.GLYPHS first (straight lines only)')
        w, strokes = GLYPHS[ch]
        for st in strokes:
            out.append([((x + gx) * unit, gy * unit) for gx, gy in st])
        x += w + (GAP if k < len(text) - 1 else 0)
    return out, x * unit


def _ext(strokes):
    xs = [p[0] for s in strokes for p in s]; ys = [p[1] for s in strokes for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def _turn(strokes, rot, cx, cy):
    c, s = round(math.cos(math.radians(rot)), 12), round(math.sin(math.radians(rot)), 12)
    return [[(cx + x * c - y * s, cy + x * s + y * c) for x, y in st] for st in strokes]


def in_box(text, box, rot, tool_mm=6.0, scale=1.0):
    """the word centred where the old word was (its box = what the old word covered, bit edge
    included), turned rot degrees counter-clockwise like the old word. 24 mm tall (times scale:
    convert.py --label-scale); smaller only if it would not fit inside the old word.
    -> (strokes, letter height mm)"""
    x0, y0, x1, y1 = box
    W, H = (x1 - x0, y1 - y0) if rot % 180 == 0 else (y1 - y0, x1 - x0)
    unit = UNIT * scale
    for _ in range(80):
        st, w = upright(text, unit)
        ex = _ext(st)
        if ex[2] - ex[0] + tool_mm <= W + 1e-6 and ex[3] - ex[1] + tool_mm <= H + 1e-6:
            break
        unit *= 0.97
    else:
        raise SystemExit(f'label font: "{text}" does not fit where the old word was')
    st = [[(x - w / 2, y - CAP * unit / 2) for x, y in s] for s in st]
    return _turn(st, rot, (x0 + x1) / 2, (y0 + y1) / 2), CAP * unit


def at(text, cx, cy, rot=0, unit=UNIT):
    """a word centred at (cx, cy), turned rot degrees counter-clockwise (a label the CAM file does
    not have: convert.py --add-label). -> strokes"""
    st, w = upright(text, unit)
    st = [[(x - w / 2, y - CAP * unit / 2) for x, y in s] for s in st]
    return _turn(st, rot, cx, cy)


def badge(text, cx, cy, unit=UNIT):
    """the sheet name centred at (cx, cy) inside a box with clipped corners.
    -> (letter strokes, the box as one closed stroke, (x0, y0, x1, y1) of the box line)"""
    st, w = upright(text, unit)
    h = CAP * unit
    st = [[(cx + x - w / 2, cy + y - h / 2) for x, y in s] for s in st]
    m, c = BOX_MARGIN * unit, BOX_CLIP * unit
    x0, y0, x1, y1 = cx - w / 2 - m, cy - h / 2 - m, cx + w / 2 + m, cy + h / 2 + m
    box = [(x0 + c, y1), (x1 - c, y1), (x1, y1 - c), (x1, y0 + c), (x1 - c, y0), (x0 + c, y0), (x0, y0 + c), (x0, y1 - c), (x0 + c, y1)]
    return st, box, (x0, y0, x1, y1)


def not_cut_yet(text):
    return sorted(set(text.upper()) & NOT_CUT_YET)
