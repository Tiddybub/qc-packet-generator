#!/usr/bin/env python3
"""Round through-holes are cut from the centre outwards, so no loose plug is left.

User rule (2026-11-19): "anything that's a hole that's cut all the way through, that will cut out a
circular hole, needs to start cutting from the center ... we don't ever want whole circles being
cut out because they get stuck in the CNC vacuum where the bit is."

A round hole that the CAM cuts as one lap round its edge frees a plug. This rewrites the entry of
such a hole: the bit plunges at the centre, opens the hole in rings no wider than 3/4 of the bit,
then runs the CAM's own edge lap. The edge lap is kept line for line, so the hole's size and
position cannot change, and every new move stays inside the hole.

  which holes : a feature that goes through, ends in ONE closed, flat, full-circle lap with no tab
                lifts, sits inside a part, has nothing inside it, would free a plug (lap radius
                more than the bit radius) and is no bigger than --hole-max-in (default 3 in).
                Anything else is left alone; a round hole that is skipped is reported.
  depth       : foam - one level, straight to through depth.
                wood - two levels (half depth, then through), like the part outlines.
  feeds       : rings run at the edge lap's own feed; the centre plunge at --hole-plunge-feed
                (default: the lap feed in foam, 50 ipm in wood).
Round PARTS are never touched: a part is not inside another part, or has features inside it.
"""
import math
import re

from gcode import parse, move_pts, move_len
import dustpass

IN = 25.4
FW = re.compile(r'F(-?\d+\.?\d*)')
NW = re.compile(r'^N\d+')
THRU_MAX = 0.3
DEFAULT_MAX_DIA = 3.0 * IN
STEPOVER = 0.75            # ring spacing as a share of the bit diameter
ROUND_TOL = 0.03           # mm: how far a lap point may sit off the circle
WOOD_PLUNGE = 1270.0       # 50 ipm


def _side(m):
    return abs(m[5] - m[2]) > 1e-6 or abs(m[6] - m[3]) > 1e-6


def _circle(lap):
    pts = [p for m in lap for p in move_pts(m)]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    rs = [math.dist(p, (cx, cy)) for p in pts]
    r = sum(rs) / len(rs)
    return cx, cy, r, max(abs(x - r) for x in rs), pts


def _inside(pt, poly):
    x, y = pt; n = len(poly); c = False
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def find(feats, tool_mm=6.0, max_dia=DEFAULT_MAX_DIA, say=None):
    """round through-holes that would free a plug -> list of dicts"""
    out = []
    thru = [f for f in feats if f['zmin'] <= THRU_MAX]
    laps = {}
    for f in thru:
        span, _ = dustpass.find_lap(f)
        if span:
            laps[f['id']] = f['moves'][span[0]:span[1] + 1]
    for f in thru:
        if f.get('kind') == 'label' or f['id'] not in laps:
            continue
        lap = laps[f['id']]
        if any(not _side(m) for m in lap):
            continue                                  # lifts over tabs: not a plain hole
        cx, cy, r, dev, pts = _circle(lap)
        L = sum(move_len(m) for m in lap)
        if dev > ROUND_TOL or abs(L - 2 * math.pi * r) > 0.02 * 2 * math.pi * r + 0.5:
            continue                                  # not one full circle
        if r <= tool_mm / 2 + 0.25:
            continue                                  # the bit covers the middle: no plug
        first = next(i for i, m in enumerate(f['moves']) if m is lap[0])
        if any(m[1] != 0 and max(math.dist(p, (cx, cy)) for p in move_pts(m)) > r + ROUND_TOL
               for m in f['moves'][:first]):
            continue                                  # the cut comes in from outside the circle
        # inside a part, and nothing inside it
        holder = None
        for g in thru:
            if g is f or g['id'] not in laps:
                continue
            b = g['bbox']
            if b[0] < cx - r and b[1] < cy - r and b[2] > cx + r and b[3] > cy + r:
                poly = [p for m in laps[g['id']] for p in move_pts(m)]
                if _inside((cx, cy), poly):
                    holder = g['id']; break
        if holder is None:
            continue                                  # free-standing circle: that is a round part
        if any(g is not f and math.dist(((g['bbox'][0] + g['bbox'][2]) / 2, (g['bbox'][1] + g['bbox'][3]) / 2),
                                        (cx, cy)) < r for g in feats):
            continue                                  # something is cut inside it: a part, not a hole
        if 2 * r + tool_mm > max_dia + 1e-6:
            if say:
                say(f'round hole {f["id"]}: {(2 * r + tool_mm) / IN:.2f} in across, bigger than the '
                    f'{max_dia / IN:.1f} in limit - left as is (it will free a {(2 * r - tool_mm) / IN:.2f} in plug)')
            continue
        out.append({'id': f['id'], 'cx': cx, 'cy': cy, 'r': r, 'first': first, 'n': len(lap), 'in_part': holder,
                    'cw': sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1)) < 0})
    return out


def apply(lines, top, tool_mm=6.0, max_dia=DEFAULT_MAX_DIA, two_levels=True, plunge_feed=None, say=print):
    """Returns (new lines, report rows). top = real stock top (mm)."""
    feats, _ = parse(lines)
    eff = dustpass.feeds_by_line(lines, feats)
    rows, jobs = [], []
    for h in find(feats, tool_mm, max_dia, say):
        f = feats[h['id']]; mv = f['moves']; lap = mv[h['first']:h['first'] + h['n']]
        zt = f['zmin']
        # layout this script knows: rapid to the start, straight drop to a height above the stock, then the cut
        if not (len(mv) > 2 and mv[0][1] == 0 and mv[1][1] == 1 and not _side(mv[1]) and mv[1][7] >= top + 0.5
                and h['first'] >= 2 and all(m[1] != 0 for m in mv[1:h['first']])):
            say(f'round hole {h["id"]}: entry not in the usual layout - left as is (it will free a plug); tell the user')
            continue
        approach_line, approach_z = lines[mv[1][0]], mv[1][7]
        lap_feed = eff[lap[0][0]]
        pf = plunge_feed or (WOOD_PLUNGE if two_levels else lap_feed)
        cx, cy, r = round(h['cx'], 3), round(h['cy'], 3), h['r']
        sx, sy = lap[0][2], lap[0][3]
        ux, uy = (sx - h['cx']) / r, (sy - h['cy']) / r
        n = max(1, math.ceil(r / (STEPOVER * tool_mm) - 1e-9))
        radii = [r * k / n for k in range(1, n)]
        levels = [round((top + zt) / 2, 3), zt] if two_levels and top - zt > 1.0 else [zt]
        g = 'G2' if h['cw'] else 'G3'
        new = [f'N0G0X{cx:.3f}Y{cy:.3f}', approach_line]
        for li, z in enumerate(levels):
            if li:
                new += [f'N0G0Z{approach_z:.3f}', f'N0G0X{cx:.3f}Y{cy:.3f}']
            new.append(f'N0G1Z{z:.3f}F{pf:.1f}')
            feed_set = False
            for rk in radii + ([r] if z != zt else []):       # upper levels also cut the edge circle
                px, py = round(h['cx'] + rk * ux, 3), round(h['cy'] + rk * uy, 3)
                qx, qy = round(h['cx'] - rk * ux, 3), round(h['cy'] - rk * uy, 3)
                new.append(f'N0G1X{px:.3f}Y{py:.3f}' + ('' if feed_set else f'F{lap_feed:.1f}'))
                feed_set = True
                new.append(f'N0{g}X{qx:.3f}Y{qy:.3f}I{cx - px:.3f}J{cy - py:.3f}')
                new.append(f'N0{g}X{px:.3f}Y{py:.3f}I{cx - qx:.3f}J{cy - qy:.3f}')
            if z == zt:
                new.append(f'N0G1X{sx:.3f}Y{sy:.3f}' + ('' if feed_set else f'F{lap_feed:.1f}'))
        first_lap_line = lines[lap[0][0]]
        if not FW.search(first_lap_line):
            first_lap_line += f'F{lap_feed:.1f}'             # the edge lap keeps the feed it had
        jobs.append((mv[0][0], lap[0][0], new + [first_lap_line]))
        rows.append({'feature': h['id'], 'cx': cx, 'cy': cy, 'r': round(r, 3), 'lap_moves': h['n'],
                     'hole_in': round((2 * r + tool_mm) / IN, 3), 'plug_in': round((2 * r - tool_mm) / IN, 3),
                     'rings': len(radii), 'levels': levels, 'plunge_feed': pf, 'in_part': h['in_part']})
        say(f'round hole {h["id"]}: {(2 * r + tool_mm) / IN:.2f} in across (would free a {(2 * r - tool_mm) / IN:.2f} in plug) '
            f'-> plunge at the centre, {len(radii)} ring(s) out, then the same edge lap; levels Z{levels}')
    out = list(lines)
    for a, b, new in sorted(jobs, reverse=True):
        out[a:b + 1] = new                                    # from the positioning rapid to the first lap line
    return out, rows


def check(fa, fb, rep, top, tool_mm=6.0):
    """verify.py: fa/fb = features of the original / converted program. Returns (ok, text)."""
    rows = rep.get('holes') or []
    bad = []
    for h in rows:
        i = h['feature']; A, B = fa[i], fb[i]
        c, r, n = (h['cx'], h['cy']), h['r'], h['lap_moves']
        why = None
        geo = lambda m: (m[1],) + tuple(round(v, 3) for v in m[2:])
        la = [m for m in A['moves'] if m[1] != 0]; lb = [m for m in B['moves'] if m[1] != 0]
        # trailing straight lifts are not part of the lap
        while la and not _side(la[-1]) and la[-1][7] > la[-1][4]: la.pop()
        while lb and not _side(lb[-1]) and lb[-1][7] > lb[-1][4]: lb.pop()
        if [geo(m) for m in la[-n:]] != [geo(m) for m in lb[-n:]]:
            why = 'edge lap is not the original lap'
        for m in B['moves']:
            far = max(math.dist(p, c) for p in (move_pts(m) if m[1] in (2, 3) else [(m[2], m[3]), (m[5], m[6])]))
            # a rapid that stays above the sheet may come from anywhere (it travels to the hole)
            if far > r + ROUND_TOL and not (m[1] == 0 and min(m[4], m[7]) >= top + 0.5):
                why = why or f'a move leaves the hole (line {m[0] + 1})'
            if min(m[4], m[7]) < A['zmin'] - 1e-6:
                why = why or f'cuts deeper than before (line {m[0] + 1})'
            if m[1] == 0 and min(m[4], m[7]) < top + 0.5:
                why = why or f'rapid inside the stock (line {m[0] + 1})'
        cutting = [m for m in B['moves'] if m[1] != 0 and min(m[4], m[7]) < top - 1e-6]
        if not cutting or _side(cutting[0]) or math.dist((cutting[0][5], cutting[0][6]), c) > 0.002:
            why = why or 'does not start by plunging at the centre'
        radii = sorted({round(math.dist((m[5], m[6]), c), 2) for m in cutting
                        if abs(m[7] - A['zmin']) < 1e-6 and abs(m[4] - A['zmin']) < 1e-6} | {0.0})
        if any(b - a > tool_mm - 0.5 for a, b in zip(radii, radii[1:])) or abs(radii[-1] - r) > 0.05:
            why = why or f'rings leave uncut wood (ring radii {radii})'
        if why:
            bad.append((i, why))
    ok = not bad
    return ok, (f'round holes ({len(rows)}): cut from the centre out, edge lap unchanged, nothing outside the hole'
                f'{"; PROBLEMS " + str(bad[:6]) if bad else ""}  -> {"OK" if ok else "FAIL"}')
