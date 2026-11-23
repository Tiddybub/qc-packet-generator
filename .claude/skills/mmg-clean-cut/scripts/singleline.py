#!/usr/bin/env python3
"""Labels cut as ONE line, one bit wide, in the same spot.

User rule (2026-11-19): "Keeping the labels in the same spot. Can you make the labels like just the
size of the bit? ... Like the width. And the badge."

The CAM cuts each label letter as a pocket (an outline plus clearing passes), so its strokes are up
to ~1/2 in wide. Here every letter is cut instead by ONE pass of the bit along the middle of its
strokes, so each stroke is exactly one bit wide:

  shape   : the area the old program cut through the real wood surface
  centres : where the bit centre can go with the whole bit inside that shape (the shape shrunk by
            the bit radius), so the new cut never leaves the old letter
  path    : the centre line of that area; short spurs into corners are removed and line ends are
            stretched to the end of the stroke
  cut     : at the label depth in one pass; straight plunge at the start of each stroke, straight
            up, across above the wood, and straight down at the next one
  badge   : the sheet ID badge (a ring in a corner with the sheet name inside). The ring becomes one
            circle along the middle of the old ring. Its text is traced like any label or, with
            --badge-text, written new (e.g. D1RB) in the single-line font below, as big as fits
            inside the ring (1 in tall at most), centred where the old text was.
"""
import math
from collections import defaultdict

import numpy as np

from gcode import move_pts
import verify

IN = 25.4
RES = 0.1                  # mm per pixel
OFF8 = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
FW_GAP = 5.0               # mm of wood left between two badge letters (bit edge to bit edge)
TEXT_H = IN                # badge text height, at most
RING_GAP = 2.0             # mm between the badge text and the ring
CLOSE = 0.55               # mm: gaps in a letter narrower than twice this are closed before tracing (D1 #187, D7 #97: ~1 mm slivers between the old pocket passes)


# ---------------------------------------------------------------- image helpers
def _erode(mask, r_px):
    """pixels where a disc of radius r_px fits inside mask"""
    r = int(math.ceil(r_px))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    k = (xx * xx + yy * yy <= r_px * r_px + 1e-9).astype(float)
    H, W = mask.shape
    sh = (H + 2 * r + 1, W + 2 * r + 1)
    c = np.fft.irfft2(np.fft.rfft2((~mask).astype(float), sh) * np.fft.rfft2(k, sh), sh)[r:r + H, r:r + W]
    return mask & (c < 0.5)


def _dilate(mask, r_px):
    r = int(math.ceil(r_px))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    k = (xx * xx + yy * yy <= r_px * r_px + 1e-9).astype(float)
    H, W = mask.shape
    sh = (H + 2 * r + 1, W + 2 * r + 1)
    c = np.fft.irfft2(np.fft.rfft2(mask.astype(float), sh) * np.fft.rfft2(k, sh), sh)[r:r + H, r:r + W]
    return c > 0.5


def _chess(mask):
    """chessboard distance (px) to the outside, for every pixel of mask"""
    d = np.zeros(mask.shape, int)
    cur = mask.copy()
    while cur.any():
        d[cur] += 1
        P = np.pad(cur, 1)
        nxt = cur.copy()
        for dy, dx in OFF8:
            nxt &= P[1 + dy:1 + dy + cur.shape[0], 1 + dx:1 + dx + cur.shape[1]]
        cur = nxt
    return d


def _thin(mask):
    """Zhang-Suen thinning"""
    img = mask.astype(np.uint8)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            P = np.pad(img, 1)
            p2, p3, p4 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:]
            p5, p6, p7 = P[2:, 2:], P[2:, 1:-1], P[2:, :-2]
            p8, p9 = P[1:-1, :-2], P[:-2, :-2]
            B = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            if step == 0:
                c1, c2 = p2 * p4 * p6, p4 * p6 * p8
            else:
                c1, c2 = p2 * p4 * p8, p2 * p6 * p8
            rm = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & (c1 == 0) & (c2 == 0)
            if rm.any():
                img[rm] = 0
                changed = True
    return img.astype(bool)


def _nb(S, p):
    return [(p[0] + dy, p[1] + dx) for dy, dx in OFF8 if (p[0] + dy, p[1] + dx) in S]


def _one_group(nb):
    seen, st = {nb[0]}, [nb[0]]
    while st:
        q = st.pop()
        for r in nb:
            if r not in seen and max(abs(r[0] - q[0]), abs(r[1] - q[1])) <= 1:
                seen.add(r); st.append(r)
    return len(seen) == len(nb)


def _cleanup(S):
    """remove pixels that are not needed to keep the line 8-connected (staircase corners)"""
    changed = True
    while changed:
        changed = False
        for p in sorted(S):
            nb = _nb(S, p)
            if len(nb) >= 2 and _one_group(nb):
                S.discard(p); changed = True
    return S


def _graph(S):
    """-> nodes (lists of pixels: line ends and junctions), edges [(node a, node b, pixels)]; a = b =
    None for a closed loop with no node on it"""
    deg = {p: len(_nb(S, p)) for p in S}
    nodes, cid = [], {}
    for p in sorted(S):
        if deg[p] == 2 or p in cid:
            continue
        k = len(nodes); cid[p] = k; mem, st = [p], [p]
        while st:
            q = st.pop()
            for r in _nb(S, q):
                if deg[r] != 2 and r not in cid:
                    cid[r] = k; mem.append(r); st.append(r)
        nodes.append(mem)
    edges, done = [], set()
    for k, mem in enumerate(nodes):
        for p in mem:
            for q in _nb(S, p):
                if q in cid or q in done:
                    continue
                path, prev, cur, end = [q], p, q, None
                done.add(q)
                while True:
                    nx = [r for r in _nb(S, cur) if r != prev and r not in path[-2:]]
                    if not nx:
                        break
                    r = next((x for x in nx if x in cid), nx[0])
                    if r in cid:
                        end = cid[r]; break
                    if r in done:
                        break
                    path.append(r); done.add(r); prev, cur = cur, r
                if end is None or (end == k and len(path) < 3):
                    continue
                edges.append((k, end, path))
    for p in sorted(S):
        if p in cid or p in done:
            continue
        path, prev, cur = [p], None, p
        done.add(p)
        while True:
            nx = [r for r in _nb(S, cur) if r != prev and r not in done]
            if not nx:
                break
            prev, cur = cur, nx[0]
            path.append(cur); done.add(cur)
        if len(path) >= 3:
            edges.append((None, None, path))
    return nodes, edges


def _ends(nodes, edges):
    cnt = defaultdict(int)
    for a, b, _ in edges:
        if a is not None:
            cnt[a] += 1; cnt[b] += 1
    return cnt


def _prune(S, dist):
    """remove short spurs that run from a junction into a corner"""
    for _ in range(4):
        nodes, edges = _graph(S)
        cnt = _ends(nodes, edges)
        rm = set()
        for a, b, px in edges:
            if a is None or a == b:
                continue
            for end, other in ((a, b), (b, a)):
                if cnt[end] == 1 and cnt[other] >= 3:
                    hw = max(dist[q] for q in nodes[other]) * RES
                    if len(px) * RES < 1.5 * hw + 1.0:
                        rm |= set(px) | set(nodes[end])
                    break
        if not rm:
            break
        S -= rm
        _cleanup(S)
    return S


# ---------------------------------------------------------------- polylines
def _smooth(pts, w=3):
    if len(pts) < 2 * w + 2:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b = max(0, i - w), min(len(pts), i + w + 1)
        out.append((sum(p[0] for p in pts[a:b]) / (b - a), sum(p[1] for p in pts[a:b]) / (b - a)))
    return out + [pts[-1]]


def _rdp(pts, tol):
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ax, ay = b[0] - a[0], b[1] - a[1]
    L = math.hypot(ax, ay)
    best, k = -1.0, 0
    for i in range(1, len(pts) - 1):
        p = pts[i]
        d = math.dist(p, a) if L == 0 else abs(ax * (a[1] - p[1]) - ay * (a[0] - p[0])) / L
        if d > best:
            best, k = d, i
    if best <= tol:
        return [a, b]
    return _rdp(pts[:k + 1], tol)[:-1] + _rdp(pts[k:], tol)


def centerline(f, top, tool_mm=6.0):
    """-> (strokes [[(x, y) mm, ...]], note). Empty strokes when the bit does not fit in the letter."""
    b = f['bbox']
    m = tool_mm + 2.0
    box = (b[0] - m, b[1] - m, b[2] + m, b[3] + m)
    shape = np.array(verify.raster(f['cut'], box, top, RES, tool_mm)) > 0
    if not shape.any():
        return [], 'nothing cut through the wood surface'
    # hairline gaps between the old pocket passes are drawing artefacts (the passes overlap in the
    # wood): close anything narrower than 2 x CLOSE first
    shape = _erode(_dilate(shape, CLOSE / RES), CLOSE / RES) | shape
    E = _erode(shape, tool_mm / 2 / RES)
    if not E.any():
        return [], 'the bit does not fit inside the letter'
    dist = _chess(E)
    S = {(int(y), int(x)) for y, x in zip(*np.nonzero(_thin(E)))}
    _cleanup(S)
    _prune(S, dist)
    nodes, edges = _graph(S)
    cnt = _ends(nodes, edges)
    H, W = E.shape
    # verify.raster draws a point at x into pixel floor((x - x0) / RES): pixel c holds x0 + (c + 0.5) * RES
    to_mm = lambda p: (box[0] + (p[1] + 0.5) * RES, box[3] - (p[0] + 0.5) * RES)
    cen = [(sum(q[0] for q in n) / len(n), sum(q[1] for q in n) / len(n)) for n in nodes]

    def stretch(path):
        """carry a free line end on in its own direction while the bit still fits"""
        if len(path) < 4:
            return path
        p0, p1 = path[-1], path[-min(len(path), 15)]
        vy, vx = p0[0] - p1[0], p0[1] - p1[1]
        L = math.hypot(vy, vx)
        if L == 0:
            return path
        vy, vx = vy / L, vx / L
        last = None
        for t in range(1, 200):
            y, x = int(round(p0[0] + vy * t)), int(round(p0[1] + vx * t))
            if not (0 <= y < H and 0 <= x < W) or not E[y, x]:
                break
            last = (p0[0] + vy * t, p0[1] + vx * t)
        return path + [last] if last is not None and math.dist(last, p0) > 2 else path

    def fits(pts):
        for p, q in zip(pts, pts[1:] or pts):
            n = max(1, int(math.dist(p, q) / RES))
            for t in range(n + 1):
                x = p[0] + (q[0] - p[0]) * t / n; y = p[1] + (q[1] - p[1]) * t / n
                c, r = int(math.floor((x - box[0]) / RES)), int(math.floor((box[3] - y) / RES))
                if not (0 <= r < H and 0 <= c < W) or not E[r, c]:
                    return False
        return True

    def tidy(pts):
        # smoothed where the bit still fits everywhere; otherwise the traced pixels as they are
        sm = _rdp(_smooth(pts), 0.04)
        return sm if fits(sm) else _rdp(pts, 0.03)

    polys = []
    for a, bb, px in edges:
        if a is None:
            pts = [to_mm(p) for p in px + px[:1]]
            polys.append((None, None, tidy(pts)))
            continue
        path = [cen[a]] + px + [cen[bb]]
        if cnt[bb] == 1:
            path = stretch(path)
        if cnt[a] == 1:
            path = stretch(path[::-1])[::-1]
        pts = [to_mm(p) for p in path]
        polys.append((a, bb, tidy(pts)))
    # a letter that thinned to a single node (a dot): one plunge
    for k, n in enumerate(nodes):
        if cnt[k] == 0:
            polys.append((k, k, [to_mm(cen[k])]))
    strokes = _walks(polys, [to_mm(c) for c in cen], (f['cut'][0][2], f['cut'][0][3]))
    return strokes, f'{len(strokes)} stroke{"s" if len(strokes) != 1 else ""}'


def _walks(polys, node_xy, start):
    """join the lines into as few bit-down runs as possible, nearest first"""
    unused = set(range(len(polys)))
    inc = defaultdict(list)
    for i, (a, b, _) in enumerate(polys):
        if a is not None:
            inc[a].append(i)
            if b != a:
                inc[b].append(i)
    out, cur, heading = [], start, None
    while unused:
        live = lambda n: [j for j in inc[n] if j in unused]
        cands = []
        for n in inc:
            k = len(live(n))
            if k:
                cands.append((k % 2 == 0, math.dist(node_xy[n], cur), 'n', n))
        for i in unused:
            if polys[i][0] is None:
                j = min(range(len(polys[i][2])), key=lambda t: math.dist(polys[i][2][t], cur))
                cands.append((True, math.dist(polys[i][2][j], cur), 'l', (i, j)))
        _, _, kind, what = min(cands, key=lambda c: (c[0], c[1]))
        if kind == 'l':
            i, j = what
            pts = polys[i][2][:-1]
            run = pts[j:] + pts[:j] + [pts[j]]
            unused.discard(i)
            out.append(run); cur = run[-1]
            continue
        n = what
        run = [node_xy[n]]
        while True:
            opts = live(n)
            if not opts:
                break
            def turn(j):
                a, b, pts = polys[j]
                seq = pts if a == n else pts[::-1]
                if heading is None or len(seq) < 2:
                    return 0
                d = (seq[1][0] - seq[0][0], seq[1][1] - seq[0][1])
                return -(d[0] * heading[0] + d[1] * heading[1]) / (math.hypot(*d) * math.hypot(*heading) + 1e-9)
            j = min(opts, key=turn)
            a, b, pts = polys[j]
            seq = pts if a == n else pts[::-1]
            run += seq[1:]
            unused.discard(j)
            n = b if a == n else a
            if len(run) >= 2:
                heading = (run[-1][0] - run[-2][0], run[-1][1] - run[-2][1])
        heading = None
        out.append(run); cur = run[-1]
    return [r for r in out if r]


# ---------------------------------------------------------------- the sheet badge
def _ring_fit(f):
    """(centre, r_min, r_max) if f is cut as a ring - possibly flattened on one side (D3: 140 x 132 mm,
    cut short where it meets the sheet margin) - else None"""
    x0, y0, x1, y1 = f['bbox']
    w, h = x1 - x0, y1 - y0
    D = max(w, h)
    if not (90 <= D <= 220 and min(w, h) >= 0.8 * D):
        return None
    pts = [p for m in f['cut'] for p in move_pts(m)]
    best = None
    for c in (((x0 + x1) / 2, (y0 + y1) / 2), ((x0 + x1) / 2, y1 - D / 2), ((x0 + x1) / 2, y0 + D / 2),
              (x1 - D / 2, (y0 + y1) / 2), (x0 + D / 2, (y0 + y1) / 2)):
        r = [math.dist(p, c) for p in pts]
        if max(r) <= D / 2 + 1.0 and min(r) >= 0.6 * max(r) and (best is None or min(r) / max(r) > best[1] / best[2]):
            best = (c, min(r), max(r))
    return best


def find_badge(feats):
    """the sheet ID badge: a POCKET cut as a ring (90-220 mm across) and the POCKET cuts inside it.
    If there are several rings, the one nearest the bottom-right corner. The ring may be cut in more
    than one piece (D10: outer lap + inner clearing); every POCKET piece that lies within the ring's
    band belongs to it. -> dict or None"""
    rings = []
    for f in feats:
        if (f['op'] or '').upper().startswith('POCKET'):
            fit = _ring_fit(f)
            if fit:
                rings.append((f,) + fit)
    if not rings:
        return None
    mx = max(f['bbox'][2] for f in feats); my = min(f['bbox'][1] for f in feats)
    f, c, ri, ro = min(rings, key=lambda t: math.dist(t[1], (mx, my)))
    pockets = [g for g in feats if g is not f and (g['op'] or '').upper().startswith('POCKET')]
    parts = []
    for g in pockets:
        r = [math.dist(p, c) for m in g['cut'] for p in move_pts(m)]
        if min(r) >= 0.6 * ro and max(r) <= ro + 1.0:
            parts.append(g)
    ri = min([ri] + [min(math.dist(p, c) for m in g['cut'] for p in move_pts(m)) for g in parts])
    corners = lambda b: ((b[0], b[1]), (b[2], b[3]), (b[0], b[3]), (b[2], b[1]))
    letters = [g['id'] for g in pockets if g not in parts and all(math.dist(p, c) < ri for p in corners(g['bbox']))]
    tb = [feats[i]['bbox'] for i in letters]
    tc = ((min(b[0] for b in tb) + max(b[2] for b in tb)) / 2, (min(b[1] for b in tb) + max(b[3] for b in tb)) / 2) if tb else c
    x0, y0, x1, y1 = f['bbox']
    allb = [f['bbox']] + [g['bbox'] for g in parts]
    U = (min(b[0] for b in allb), min(b[1] for b in allb), max(b[2] for b in allb), max(b[3] for b in allb))
    return {'ring': f['id'], 'parts': [g['id'] for g in parts], 'letters': letters, 'cx': c[0], 'cy': c[1],
            'r_in': ri, 'r_out': ro, 'text_c': tc, 'complete': abs((U[2] - U[0]) - (U[3] - U[1])) < 3,
            'cut': f['cut'] + [m for g in parts for m in g['cut']], 'bbox': U}


def ring(badge, top=None, tool_mm=6.0):
    """the badge ring as one line along its middle: a full circle when the old ring is whole; traced
    like a letter when it is cut short on one side, so the line never leaves the old ring"""
    if not badge['complete']:
        strokes, _ = centerline({'cut': badge['cut'], 'bbox': badge['bbox']}, top, tool_mm)
        return strokes
    cx, cy, r = badge['cx'], badge['cy'], (badge['r_in'] + badge['r_out']) / 2
    n = 72
    return [[(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]]


def _arc(cx, cy, r, a0, a1, step=10.0):
    n = max(2, int(abs(a1 - a0) / step) + 1)
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / (n - 1))),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / (n - 1)))) for k in range(n)]


# single-line font, 1 unit tall, drawn from the bottom-left corner
GLYPHS = {
    'D': [[(0, 0), (0, 1), (0.3, 1)] + _arc(0.3, 0.7, 0.3, 90, 0) + _arc(0.3, 0.3, 0.3, 0, -90) + [(0, 0)]],
    'R': [[(0, 0), (0, 1), (0.3, 1)] + _arc(0.3, 0.75, 0.25, 90, -90) + [(0, 0.5), (0.3, 0.5), (0.6, 0)]],
    'B': [[(0, 0), (0, 1), (0.27, 1)] + _arc(0.27, 0.75, 0.25, 90, -90) + [(0, 0.5), (0.3, 0.5)]
          + _arc(0.3, 0.25, 0.25, 90, -90) + [(0, 0)]],
    '0': [[(0, 0.3), (0, 0.7)] + _arc(0.3, 0.7, 0.3, 180, 0) + _arc(0.3, 0.3, 0.3, 0, -180)],
    '1': [[(0, 0.75), (0.25, 1), (0.25, 0)]],
    '2': [_arc(0.3, 0.7, 0.3, 165, -35) + [(0, 0), (0.6, 0)]],
    '3': [_arc(0.3, 0.75, 0.25, 155, -90) + _arc(0.3, 0.25, 0.25, 90, -155)],
    '4': [[(0.45, 0), (0.45, 1), (0, 0.3), (0.6, 0.3)]],
    '5': [[(0.55, 1), (0.08, 1), (0.05, 0.55)] + _arc(0.3, 0.3, 0.3, 125, -145)],
    '6': [[(0.5, 1)] + _arc(0.65, 0.3, 0.65, 112, 180) + _arc(0.3, 0.3, 0.3, 180, -180)],
    '7': [[(0, 1), (0.6, 1), (0.2, 0)]],
    '8': [_arc(0.3, 0.76, 0.24, -90, 270) + _arc(0.3, 0.26, 0.26, 90, -270)],
    '9': [_arc(0.3, 0.7, 0.3, 0, 360) + _arc(-0.05, 0.7, 0.65, 0, -68)],
}


def text(s, badge, tool_mm=6.0):
    """the badge text in the single-line font, centred where the old text was, as big as fits
    (TEXT_H at most) inside the new ring with RING_GAP to spare"""
    s = s.upper()
    bad = [ch for ch in s if ch not in GLYPHS]
    if bad:
        raise SystemExit(f'--badge-text: no single-line letter for {bad}; the font has {"".join(sorted(GLYPHS))}')
    cx, cy = badge['text_c']
    r_ring = (badge['r_in'] + badge['r_out']) / 2
    limit = r_ring - tool_mm / 2 - RING_GAP - tool_mm / 2         # farthest a text bit centre may go
    widths = [max(x for st in GLYPHS[ch] for x, _ in st) for ch in s]
    H = TEXT_H
    while H > 10:
        adv = [w * H + tool_mm + FW_GAP for w in widths]
        total = sum(adv) - tool_mm - FW_GAP
        x, out = cx - total / 2, []
        for ch, a in zip(s, adv):
            for st in GLYPHS[ch]:
                out.append([(x + px * H, cy - H / 2 + py * H) for px, py in st])
            x += a
        if max(math.dist(p, (badge['cx'], badge['cy'])) for st in out for p in st) <= limit:
            return out
        H *= 0.95
    raise SystemExit(f'--badge-text "{s}" does not fit inside the badge ring')


# ---------------------------------------------------------------- G-code
def _feed_at(lines, k):
    import re
    for i in range(k, -1, -1):
        m = re.search(r'F(-?\d+\.?\d*)', lines[i])
        if m:
            return m.group(1)
    return None


def _pct(feed, pct):
    """a feed word value scaled to pct percent, written like the program writes feeds"""
    return f'{float(feed) * pct / 100:.1f}'


def emit(lines, f, strokes, top, z, plunge_feed=None, feed_pct=None, slow_mm=0.0, stroke_pct=None):
    """G-code for the strokes, replacing feature f. The feed in effect after it stays as it was.
    feed_pct  : cut the strokes at this percent of the old label's cutting feed (75 = 25 % slower)
    stroke_pct: the same for single strokes, a list as long as strokes (None = feed_pct); the badge
                box runs at 50
    slow_mm   : plunge at the plunge feed to slow_mm above the depth, feed the last slow_mm at 1/10
                of the plunge feed, and lift the first slow_mm at that feed too (user, V9-V12:
                "plunge first, then cut"; the bit was tearing the letters when it hit depth fast)"""
    pl = next((m for m in f['cut'] if m[1] == 1 and (m[2], m[3]) == (m[5], m[6]) and m[7] < m[4]), None)
    xy = next((m for m in f['cut'] if (abs(m[5] - m[2]) > 1e-6 or abs(m[6] - m[3]) > 1e-6) and min(m[4], m[7]) < top), None)
    pf = plunge_feed or (_feed_at(lines, pl[0]) if pl else None) or _feed_at(lines, f['end'])
    cf0 = _feed_at(lines, xy[0]) if xy else _feed_at(lines, f['end'])
    end_f = _feed_at(lines, f['end'])
    safe = f['plunge'] if f['plunge'] >= top + 0.5 else top + 2.54
    ps = _pct(pf, 10) if slow_mm else None
    out, last_f = [], None
    for k, st in enumerate(strokes):
        pct = (stroke_pct[k] if stroke_pct and stroke_pct[k] else feed_pct)
        cf = _pct(cf0, pct) if pct else cf0
        if k:
            out.append(f'G0Z{safe:.3f}')
        out.append(f'G0X{st[0][0]:.3f}Y{st[0][1]:.3f}')
        if k == 0:
            out.append(f'G0Z{safe:.3f}')
        if slow_mm:
            out.append(f'G1Z{z + slow_mm:.3f}F{pf}')
            out.append(f'G1Z{z:.3f}F{ps}'); last_f = ps
        else:
            out.append(f'G1Z{z:.3f}F{pf}'); last_f = pf
        prev = (round(st[0][0], 3), round(st[0][1], 3))
        for item in st[1:]:
            q = (round(item[0], 3), round(item[1], 3))
            if q == prev:
                continue
            if len(item) == 5:                       # arc: (x, y, centre x, centre y, clockwise)
                i, j = item[2] - prev[0], item[3] - prev[1]
                out.append(f'{"G2" if item[4] else "G3"}X{q[0]:.3f}Y{q[1]:.3f}I{i:.3f}J{j:.3f}' + (f'F{cf}' if last_f != cf else ''))
            else:
                out.append(f'G1X{q[0]:.3f}Y{q[1]:.3f}' + (f'F{cf}' if last_f != cf else ''))
            last_f = cf; prev = q
        if slow_mm:
            out.append(f'G1Z{z + slow_mm:.3f}F{ps}'); last_f = ps
    if end_f is not None and last_f != end_f:
        out.append(f'G1Z{safe:.3f}F{end_f}')          # leave the feed as the old cut left it
    return out
