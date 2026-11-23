#!/usr/bin/env python3
"""Labels rewritten in a single-line engraving font (Hershey Sans, `hershey_futural.jhf`).

User request (2026-11-20): "We need a better font for the labels and badge." The CAM's thick
pocket letters traced down their middle come out wobbly; this writes each label word again in a
proper single-line font: same text, same place, same direction, one bit wide.

  reading  : the text of every word comes from a reading file (labelwords.py makes the contact
             sheets and checks each reading in all 8 orientations); the skill never guesses a code
  place    : inside the box the old word covered (bit edge included), centred, as tall as the old
             letters, made smaller only if it would not fit; turned the way the old word was
  mirrored : words the CAD mirrored (left/right parts) are written readable, same direction
  badge    : the sheet badge text in the same font, as big as fits inside the ring

Font: Hershey Sans 1-stroke ("futural"), from the Hershey fonts (public domain, A. V. Hershey,
US National Bureau of Standards), data taken from the Hershey-Fonts 2.1.0 package (MIT).
"""
import math
import os

FONT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hershey_futural.jhf')
CAP, BASE = -12, 9                 # font units: cap line and base line (y grows downwards)
CAP_UNITS = BASE - CAP             # 21
GAP = 0.6                          # extra space between letters, as a share of the bit diameter
_glyphs = None


def glyphs():
    global _glyphs
    if _glyphs is None:
        rows = open(FONT_FILE).read().splitlines()[1:]
        _glyphs = {}
        for k, row in enumerate(rows):
            body = row[8:]
            pairs = [body[i:i + 2] for i in range(0, len(body) - 1, 2)]
            left, right = ord(pairs[0][0]) - 82, ord(pairs[0][1]) - 82
            strokes, cur = [], []
            for p in pairs[1:]:
                if p == ' R':
                    if cur:
                        strokes.append(cur)
                    cur = []
                    continue
                cur.append((ord(p[0]) - 82, ord(p[1]) - 82))
            if cur:
                strokes.append(cur)
            _glyphs[chr(32 + k)] = (left, right, strokes)
    return _glyphs


def upright(text, cap_mm, tool_mm):
    """strokes of the text standing upright, baseline at y = 0, starting at x = 0 (mm)"""
    G = glyphs()
    u = cap_mm / CAP_UNITS
    x, out = 0.0, []
    for ch in text:
        if ch not in G:
            raise SystemExit(f'font: no letter for {ch!r}')
        left, right, strokes = G[ch]
        for st in strokes:
            out.append([(x + (gx - left) * u, (BASE - gy) * u) for gx, gy in st])
        x += (right - left) * u + GAP * tool_mm
    return out


def _ext(strokes):
    xs = [p[0] for s in strokes for p in s]; ys = [p[1] for s in strokes for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def _turn(strokes, rot, cx, cy):
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    return [[(cx + x * c - y * s, cy + x * s + y * c) for x, y in st] for st in strokes]


def in_box(text, box, rot, tool_mm=6.0, max_cap=None):
    """the text in the old word's box (visible extent, bit edge included), turned rot degrees
    counter-clockwise like the old word, as tall as fits. -> (strokes, cap height mm)"""
    x0, y0, x1, y1 = box
    W, H = (x1 - x0, y1 - y0) if rot % 180 == 0 else (y1 - y0, x1 - x0)
    cap = H - tool_mm
    if max_cap:
        cap = min(cap, max_cap)
    for _ in range(60):
        st = upright(text, cap, tool_mm)
        ex = _ext(st)
        if ex[2] - ex[0] + tool_mm <= W + 1e-6 and ex[3] - ex[1] + tool_mm <= H + 1e-6:
            break
        cap *= 0.97
    else:
        raise SystemExit(f'font: "{text}" does not fit its box')
    mx, my = (ex[0] + ex[2]) / 2, (ex[1] + ex[3]) / 2
    st = [[(x - mx, y - my) for x, y in s] for s in st]
    return _turn(st, rot, (x0 + x1) / 2, (y0 + y1) / 2), cap


def in_circle(text, cx, cy, radius, tool_mm=6.0, max_cap=30.0):
    """the badge text centred at (cx, cy), every bit edge within radius. -> (strokes, cap mm)"""
    cap = max_cap
    for _ in range(80):
        st = upright(text, cap, tool_mm)
        ex = _ext(st)
        mx, my = (ex[0] + ex[2]) / 2, (ex[1] + ex[3]) / 2
        st = [[(cx + x - mx, cy + y - my) for x, y in s] for s in st]
        if max(math.dist(p, (cx, cy)) for s in st for p in s) + tool_mm / 2 <= radius:
            return st, cap
        cap *= 0.97
    raise SystemExit(f'font: badge text "{text}" does not fit inside the ring')


# ---------------------------------------------------------------- smooth curves, cut as arcs
# The Hershey letters are drawn on a coarse grid: their curves are short straight pieces whose
# corners sit on whole grid units. At 1 in and more that shows as small wobbles, and hundreds of
# tiny moves make the machine stutter. User (2026-11-20): "The letters need to have no jitter."
# So every curved run is smoothed (cubic B-spline through the grid points, ends kept) and then cut
# as true arcs (G2/G3) where an arc fits within ARC_TOL, straight lines (G1) where a line does.
# Real corners (the stroke turns by more than CORNER_DEG) stay sharp.
CORNER_DEG = 40.0
LONG_UNITS = 4.0           # font units: a straight piece at least this long; where two meet it is a corner
JOIN_DEG = 12.0            # ... if they turn by more than this (Y: arm into stem)
ARC_TOL = 0.02             # mm: how far the cut may stray from the smoothed curve
SAMPLE = 0.25              # mm between points on the smoothed curve before arc fitting


def _turn_deg(a, b, c):
    v1 = (b[0] - a[0], b[1] - a[1]); v2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cosv = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cosv))


def _bspline(P):
    """open uniform cubic B-spline with the end points kept, sampled every SAMPLE mm"""
    if len(P) < 3:
        return list(P)
    C = [P[0], P[0]] + list(P) + [P[-1], P[-1]]
    out = [P[0]]
    for i in range(len(C) - 3):
        p0, p1, p2, p3 = C[i:i + 4]
        L = math.dist(p1, p2) + 1e-9
        n = max(2, int(L / SAMPLE) + 1)
        for k in range(1, n + 1):
            t = k / n; t2 = t * t; t3 = t2 * t
            b0 = (1 - t) ** 3 / 6; b1 = (3 * t3 - 6 * t2 + 4) / 6; b2 = (-3 * t3 + 3 * t2 + 3 * t + 1) / 6; b3 = t3 / 6
            out.append((b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0], b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]))
    out[-1] = P[-1]
    return out


def _periodic(P):
    """closed cubic B-spline through a loop of points (no seam), sampled every SAMPLE mm"""
    n = len(P); out = []
    for i in range(n):
        p0, p1, p2, p3 = P[i - 1], P[i], P[(i + 1) % n], P[(i + 2) % n]
        m = max(2, int(math.dist(p1, p2) / SAMPLE) + 1)
        for k in range(m):
            t = k / m; t2 = t * t; t3 = t2 * t
            b0 = (1 - t) ** 3 / 6; b1 = (3 * t3 - 6 * t2 + 4) / 6; b2 = (-3 * t3 + 3 * t2 + 3 * t + 1) / 6; b3 = t3 / 6
            out.append((b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0], b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]))
    return out + [out[0]]


def _corner(a, b, c, unit):
    t = _turn_deg(a, b, c)
    if t > CORNER_DEG:
        return True
    return unit is not None and t > JOIN_DEG and min(math.dist(a, b), math.dist(b, c)) >= LONG_UNITS * unit


def segments(stroke, unit=None):
    """a stroke split at its corners -> [('line', [a, b]) | ('curve', smoothed points)].
    unit = mm per font unit (cap height / 21)"""
    pts = [p for k, p in enumerate(stroke) if k == 0 or math.dist(p, stroke[k - 1]) > 1e-9]
    if len(pts) < 3:
        return [('line', pts)] if len(pts) == 2 else []
    closed = len(pts) > 3 and math.dist(pts[0], pts[-1]) < 1e-6
    if closed:
        loop = pts[:-1]; n = len(loop)
        corner = [i for i in range(n) if _corner(loop[i - 1], loop[i], loop[(i + 1) % n], unit)]
        if not corner:
            return [('curve', _periodic(loop))]
        k = corner[0]
        pts = loop[k:] + loop[:k] + [loop[k]]          # start the loop at a real corner
    cuts = [0] + [i for i in range(1, len(pts) - 1) if _corner(pts[i - 1], pts[i], pts[i + 1], unit)] + [len(pts) - 1]
    out = []
    for a, b in zip(cuts, cuts[1:]):
        seg = pts[a:b + 1]
        out.append(('line', seg) if len(seg) == 2 else ('curve', _bspline(seg)))
    return out


def smooth(stroke, unit=None):
    """the stroke as one point list with its curves smoothed (for drawing and fitting checks)"""
    out = []
    for kind, seg in segments(stroke, unit):
        out += seg if not out else seg[1:]
    return out


def _circle(a, b, c):
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-9:
        return None
    ux = ((a[0] ** 2 + a[1] ** 2) * (b[1] - c[1]) + (b[0] ** 2 + b[1] ** 2) * (c[1] - a[1]) + (c[0] ** 2 + c[1] ** 2) * (a[1] - b[1])) / d
    uy = ((a[0] ** 2 + a[1] ** 2) * (c[0] - b[0]) + (b[0] ** 2 + b[1] ** 2) * (a[0] - c[0]) + (c[0] ** 2 + c[1] ** 2) * (b[0] - a[0])) / d
    return ux, uy


def _line_ok(P, i, j, tol):
    a, b = P[i], P[j]
    ax, ay = b[0] - a[0], b[1] - a[1]
    L = math.hypot(ax, ay)
    if L < 1e-9:
        return False
    return all(abs(ax * (a[1] - p[1]) - ay * (a[0] - p[0])) / L <= tol for p in P[i + 1:j])


def _arc_ok(P, i, j, tol):
    k = (i + j) // 2
    c = _circle(P[i], P[k], P[j])
    if c is None:
        return None
    r = math.dist(c, P[i])
    if r > 2000 or any(abs(math.dist(c, p) - r) > tol for p in P[i:j + 1]):
        return None
    # one direction all the way, less than a full turn
    cr = [(P[t][0] - c[0]) * (P[t + 1][1] - c[1]) - (P[t][1] - c[1]) * (P[t + 1][0] - c[0]) for t in range(i, j)]
    if not (all(x > 0 for x in cr) or all(x < 0 for x in cr)):
        return None
    sweep = sum(abs(math.atan2(x, (P[t][0] - c[0]) * (P[t + 1][0] - c[0]) + (P[t][1] - c[1]) * (P[t + 1][1] - c[1])))
                for t, x in zip(range(i, j), cr))
    if sweep > math.radians(300):
        return None
    return c, cr[0] < 0


def _fit(P, tol):
    out, i = [], 0
    while i < len(P) - 1:
        best = (i + 1, None)
        j = i + 2
        while j < len(P):
            if _line_ok(P, i, j, tol):
                best = (j, None); j += 1; continue
            arc = _arc_ok(P, i, j, tol) if j - i >= 4 else None
            if arc is None:
                if j - i < 4:
                    j += 1; continue                    # too few points to judge yet
                break
            best = (j, arc); j += 1
        j, arc = best
        out.append(P[j] if arc is None else (P[j][0], P[j][1], arc[0][0], arc[0][1], arc[1]))
        i = j
    return out


def to_moves(stroke, unit=None, tol=ARC_TOL):
    """stroke -> [start point, moves...]: (x, y) straight moves and (x, y, cx, cy, clockwise) arcs.
    Arcs are fitted only inside a smooth run, never across a corner."""
    segs = segments(stroke, unit)
    if not segs:
        return [stroke[0]]
    out = [segs[0][1][0]]
    for kind, seg in segs:
        out += [seg[-1]] if kind == 'line' else _fit(seg, tol)
    return out


def full_circle(cx, cy, r):
    """one closed ring as two half-circle arcs back to back (one G2 cannot go all the way round)"""
    return [(cx + r, cy), (cx - r, cy, cx, cy, True), (cx + r, cy, cx, cy, True)]
