#!/usr/bin/env python3
"""Restyle the labels of a finished program: new size, depth and feed for every label word cut in
the straight-line font (blockfont.py), and slower badge cuts. Nothing else in the file changes.

User (2026-11-23), after the closet test (DD1/DD2 V4) cut clean: "Labels look good change the mmg
clean cut skill to edit the labels to cut this way", then "redo d1-d10".

  words    every stroke cluster in the label cut(s) (the features cut FROM-DEPTH below the real top)
           is read back as straight-line-font letters, with its reading direction and centre. It is
           written again at --scale x the 24 mm grid (1.15 = 27.7 mm letters), same text, same
           centre, same direction, --depth-in deep, cut at --feed-factor x its old cutting feed.
           Each stroke keeps the plunge style: fast to 0.5 mm above depth, the last 0.5 mm at the
           slow feed, cut, lift the first 0.5 mm slowly. The rapids keep the old safe height.
  wood     a word that would come closer than 6 mm (one bit) to any other cut at the new size is
           made only as big as keeps that wood (never smaller than it was); it is printed. A word
           that already had less than 6 mm keeps at least what it had.
  badge    its letters and box keep their size, path and depth; only the feed of every sideways
           move is multiplied by --feed-factor (plunges and lifts keep theirs).
  check    every other cut is line for line the same; the new label cut reads back as the same
           words in the same spots; everything is at the new depth; no feed went up.

    python3 -I labelstyle.py IN.MMG OUT.MMG --stock-in 0.5 [--scale 1.15] [--depth-in 0.21]
           [--feed-factor 0.7] [--from-depth-in 0.18] [--badge-depth-in 0.25]
"""
import argparse
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import gcode
import blockfont

IN = 25.4
FW = re.compile(r'F(-?\d+\.?\d*)')
ZW = re.compile(r'Z(-?\d+\.?\d*)')
NW = re.compile(r'^N\d+')
GROUP = 14.0          # mm: strokes closer than this belong to the same word (letters are 12 mm apart)
MIN_WOOD = 6.0        # mm of wood between any two cuts (one bit width; the user's WOOD RULE)
TOOL = 6.0


def _moving(m):
    return abs(m[5] - m[2]) > 1e-6 or abs(m[6] - m[3]) > 1e-6


def strokes_at(f, z):
    """[(points, [move indices])]: runs of straight feed moves flat at depth z"""
    out, cur = [], None
    for m in f['moves']:
        if m[1] == 1 and _moving(m) and abs(m[4] - z) < 1e-6 and abs(m[7] - z) < 1e-6:
            if cur is None:
                cur = ([(m[2], m[3])], []); out.append(cur)
            cur[0].append((m[5], m[6])); cur[1].append(m[0])
        elif m[1] in (2, 3) and min(m[4], m[7]) < z + 1e-6:
            raise SystemExit(f'labelstyle: label cut {f["id"]} has an arc at depth - not a straight-line-font label, nothing written')
        else:
            cur = None
    return out


def _bb(sts):
    xs = [p[0] for s in sts for p in s]; ys = [p[1] for s in sts for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def cluster(sts):
    n = len(sts); par = list(range(n))

    def root(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    B = [_bb([s]) for s in sts]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = B[i], B[j]
            gx = max(0, max(a[0], b[0]) - min(a[2], b[2])); gy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
            if math.hypot(gx, gy) < GROUP:
                par[root(i)] = root(j)
    groups = {}
    for i in range(n):
        groups.setdefault(root(i), []).append(i)
    return sorted(groups.values(), key=min)


def _canon(strokes):
    return tuple(sorted(min(tuple(st), tuple(st[::-1])) for st in strokes))


_GL = None


def glyph_table():
    """canonical letter shape -> (letter, glyph min x, glyph min y). Identical shapes (0 and O)
    are written the same way, so either letter does."""
    global _GL
    if _GL is None:
        _GL = {}
        for ch, (w, sts) in blockfont.GLYPHS.items():
            xs = [p[0] for s in sts for p in s]; ys = [p[1] for s in sts for p in s]
            key = _canon([[(round(x - min(xs), 1), round(y - min(ys), 1)) for x, y in s] for s in sts])
            _GL.setdefault(key, (ch, min(xs), min(ys)))
    return _GL


def _turn(pts, deg):
    c, s = round(math.cos(math.radians(deg)), 12), round(math.sin(math.radians(deg)), 12)
    return [(x * c - y * s, x * s + y * c) for x, y in pts]


def decode(word):
    """word = list of point lists -> (text, rot, centre (x, y), unit mm) or None"""
    G = glyph_table()
    for rot in (0, 90, 180, 270):
        T = [_turn(s, -rot) for s in word]
        b = _bb(T)
        for div in (20.0, 21.0):                              # 21 if the word has a Q (its tail)
            U = (b[3] - b[1]) / div
            if U <= 0:
                continue
            order = sorted(range(len(T)), key=lambda k: min(p[0] for p in T[k]))
            letters, edge = [], None
            for k in order:
                lo, hi = min(p[0] for p in T[k]), max(p[0] for p in T[k])
                if edge is None or lo > edge + 6 * U:
                    letters.append([k]); edge = hi
                else:
                    letters[-1].append(k); edge = max(edge, hi)
            text, mins, ok = '', [], True
            for lt in letters:
                xs = [p[0] for k in lt for p in T[k]]; ys = [p[1] for k in lt for p in T[k]]
                mx, my = min(xs), min(ys)
                key = _canon([[(round((x - mx) / U, 1), round((y - my) / U, 1)) for x, y in T[k]] for k in lt])
                if key not in G:
                    ok = False; break
                ch, gx, gy = G[key]; text += ch; mins.append((mx, my, gx, gy))
            if not ok:
                continue
            off, origins = 0.0, []
            for ch, (mx, my, gx, gy) in zip(text, mins):
                origins.append((mx - (off + gx) * U, my - gy * U)); off += blockfont.GLYPHS[ch][0] + blockfont.GAP
            if max(math.dist(o, origins[0]) for o in origins) > 0.05:
                continue
            Wn = off - blockfont.GAP
            ox = sum(o[0] for o in origins) / len(origins); oy = sum(o[1] for o in origins) / len(origins)
            c = _turn([(ox + Wn * U / 2, oy + blockfont.CAP * U / 2)], rot)[0]
            return text, rot, c, U
    return None


def _samples(sts, step=0.5):
    out = []
    for s in sts:
        for a, b in zip(s, s[1:]):
            n = max(1, int(math.dist(a, b) / step))
            out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]
    return np.array(out) if out else np.zeros((0, 2))


def _cut_samples(f, top, step=0.5):
    out = []
    for m in f['cut']:
        if m[1] == 0 or min(m[4], m[7]) >= top - 1e-6:
            continue
        p = gcode.move_pts(m)
        for a, b in zip(p, p[1:]):
            n = max(1, int(math.dist(a, b) / step))
            out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]
    return np.array(out) if out else np.zeros((0, 2))


def _wood(P, Q):
    if not len(P) or not len(Q):
        return None
    best = None
    for j in range(0, len(Q), 3000):
        d = np.sqrt(((P[:, None, :] - Q[None, j:j + 3000, :]) ** 2).sum(axis=2)).min()
        best = d if best is None else min(best, d)
    return float(best) - TOOL


def _near(Q, box, reach):
    if not len(Q):
        return Q
    return Q[(Q[:, 0] > box[0] - reach) & (Q[:, 0] < box[2] + reach) & (Q[:, 1] > box[1] - reach) & (Q[:, 1] < box[3] + reach)]


def _style(f, lines, top, z_old):
    """the cut's own plunge / slow / cut feeds, safe height and slow distance"""
    body = [NW.sub('', lines[k]) for k in range(f['start'], f['end'] + 1)]
    safe = {float(ZW.search(l).group(1)) for l in body if l.startswith('G0') and 'X' not in l and 'Y' not in l and ZW.search(l)}
    fast = {(float(ZW.search(l).group(1)), FW.search(l).group(1)) for l in body if l.startswith('G1Z') and FW.search(l)
            and ZW.search(l) and float(ZW.search(l).group(1)) > z_old + 1e-6}
    cut = {FW.search(l).group(1) for l in body if l.startswith('G1') and ('X' in l or 'Y' in l) and FW.search(l)}
    deep = {FW.search(l).group(1) for l in body if l.startswith('G1Z') and FW.search(l) and abs(float(ZW.search(l).group(1)) - z_old) < 1e-6}
    if len(safe) != 1 or len(cut) != 1 or len(deep) != 1 or len({z for z, _ in fast}) != 1 or len({fd for _, fd in fast}) != 2:
        raise SystemExit(f'labelstyle: label cut {f["id"]} is not in the plunge-then-cut style (safe {safe}, cut feed {cut}, '
                         f'plunges {fast}) - nothing written')
    slow_z = next(iter({z for z, _ in fast}))
    pf = max((fd for _, fd in fast), key=float)
    return {'safe': safe.pop(), 'pf': pf, 'ps': deep.pop(), 'cf': cut.pop(), 'slow': round(slow_z - z_old, 3)}


def emit(strokes, z, st, cf):
    out = []
    for k, s in enumerate(strokes):
        if k:
            out.append(f'G0Z{st["safe"]:.3f}')
        out.append(f'G0X{s[0][0]:.3f}Y{s[0][1]:.3f}')
        out.append(f'G0Z{st["safe"]:.3f}')
        out.append(f'G1Z{z + st["slow"]:.3f}F{st["pf"]}')
        out.append(f'G1Z{z:.3f}F{st["ps"]}')
        for i, (x, y) in enumerate(s[1:]):
            out.append(f'G1X{x:.3f}Y{y:.3f}' + (f'F{cf}' if i == 0 else ''))
        out.append(f'G1Z{z + st["slow"]:.3f}F{st["ps"]}')
    return out


def _fmt(v):
    return f'{v:.1f}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--stock-in', type=float, required=True)
    ap.add_argument('--scale', type=float, default=1.15, help='label letters this many times the 24 mm grid (1.15 = 27.7 mm)')
    ap.add_argument('--depth-in', type=float, default=0.21, help='new label depth below the real top')
    ap.add_argument('--feed-factor', type=float, default=0.7, help='label and badge cutting feeds x this (0.7 = 30 %% slower: 75 %% -> 52.5 %% of the program feed)')
    ap.add_argument('--from-depth-in', type=float, default=0.18, help='the labels are the cuts this deep now')
    ap.add_argument('--badge-depth-in', type=float, default=0.25)
    a = ap.parse_args()
    top = a.stock_in * IN
    z_old, z_new, z_badge = top - a.from_depth_in * IN, top - a.depth_in * IN, top - a.badge_depth_in * IN
    lines = gcode.read_lines(a.src)
    feats, _ = gcode.parse(lines)
    labs = [f for f in feats if abs(f['zmin'] - z_old) < 0.002]
    if not labs:
        sys.exit(f'labelstyle: no cut is {a.from_depth_in} in deep - nothing written')
    # ---- read every word
    words = []                                                   # (feature, old strokes, text, rot, centre)
    for f in labs:
        sts = [s for s, _ in strokes_at(f, f['zmin'])]
        for g in cluster(sts):
            wd = [sts[k] for k in g]
            r = decode(wd)
            if r is None:
                bx = _bb(wd)
                sys.exit(f'labelstyle: the label at X{(bx[0] + bx[2]) / 2:.0f} Y{(bx[1] + bx[3]) / 2:.0f} does not read as '
                         f'straight-line-font letters - nothing written')
            words.append({'f': f, 'old': wd, 'text': r[0], 'rot': r[1], 'c': r[2], 'U': r[3]})
    lab_ids = {f['id'] for f in labs}
    badges = [f for f in feats if f['id'] not in lab_ids and abs(f['zmin'] - z_badge) < 0.002 and _is_badge(f, lines, z_badge)]
    # ---- the rest of the sheet, for the wood check
    others = np.concatenate([q for q in (_cut_samples(f, top) for f in feats if f['id'] not in lab_ids) if len(q)] or [np.zeros((0, 2))])
    for w in words:
        w['old_pts'] = _samples(w['old'])

    def make(w, s):
        return blockfont.at(w['text'], w['c'][0], w['c'][1], w['rot'], blockfont.UNIT * s)

    for w in words:
        w['scale'] = a.scale; w['new'] = make(w, a.scale); w['pts'] = _samples(w['new'])
    for w in words:                                               # wood it had before
        bx = _bb(w['old'])
        q = [_near(others, bx, 60)] + [o['old_pts'] for o in words if o is not w]
        w['old_wood'] = _wood(w['old_pts'], np.concatenate([x for x in q if len(x)] or [np.zeros((0, 2))]))
    for _ in range(6):                                            # grow, then shrink the ones that crowd
        changed = False
        for w in words:
            need = MIN_WOOD if w['old_wood'] is None else min(MIN_WOOD, w['old_wood'])
            bx = _bb(w['new'])
            q = np.concatenate([x for x in [_near(others, bx, 60)] + [o['pts'] for o in words if o is not w] if len(x)] or [np.zeros((0, 2))])
            wd = _wood(w['pts'], q)
            w['wood'] = wd
            if wd is not None and wd < need - 0.01 and w['scale'] > w['U'] / blockfont.UNIT + 1e-6:
                lo = w['U'] / blockfont.UNIT
                s = w['scale']
                while s > lo + 1e-6:
                    s = max(lo, round(s - 0.01, 3))
                    pts = _samples(make(w, s))
                    if _wood(pts, q) >= need - 0.01:
                        break
                w['scale'] = s; w['new'] = make(w, s); w['pts'] = _samples(w['new']); changed = True
        if not changed:
            break
    # ---- write
    out = list(lines)
    rep = {}
    for f in labs:
        st = _style(f, lines, top, f['zmin'])
        cf = _fmt(float(st['cf']) * a.feed_factor)
        ws = [w for w in words if w['f'] is f]                    # in the order they were cut
        new = emit([s for w in ws for s in w['new']], z_new, st, cf)
        rep[f['start']] = (f['end'], new)
    for f in badges:
        for k in range(f['start'], f['end'] + 1):
            l = out[k]
            if l and ('X' in NW.sub('', l) or 'Y' in NW.sub('', l)) and FW.search(l) and not NW.sub('', l).startswith('G0'):
                out[k] = FW.sub('F' + _fmt(float(FW.search(l).group(1)) * a.feed_factor), l)
    res, k = [], 0
    while k < len(out):
        if k in rep:
            res.extend(rep[k][1]); k = rep[k][0] + 1
        else:
            res.append(out[k]); k += 1
    n = 0
    for k, l in enumerate(res):
        if l and not l.startswith('(') and l != '%':
            n += 10
            res[k] = f'N{n}' + NW.sub('', l)
    gcode.write_lines(a.dst, res)
    # ---- report
    for w in words:
        note = ''
        if w['scale'] < a.scale - 1e-6:
            note = f'  SMALLER than asked, to keep the wood it had - tell the user'
        ow = 'none near' if w['old_wood'] is None else f'{w["old_wood"]:.1f}'
        nw = 'none near' if w['wood'] is None else f'{w["wood"]:.1f}'
        print(f'  {w["text"]:6s} at X{w["c"][0]:.0f} Y{w["c"][1]:.0f}, turned {w["rot"]:3d}: {w["U"] * 20:.1f} -> {w["scale"] * blockfont.UNIT * 20:.1f} mm, '
              f'wood {ow} -> {nw} mm{note}')
    ok, text = check(lines, gcode.read_lines(a.dst), top, z_old, z_new, z_badge, words, lab_ids, {f['id'] for f in badges}, a.feed_factor)
    print(f'labelstyle: {len(words)} words, {len(badges)} badge; {text}')
    sys.exit(0 if ok else 1)


def _is_badge(f, lines, z_badge):
    """the badge: a cut at the badge depth in the plunge-then-cut style (fast plunge, slow last
    part), whose letters read in the straight-line font"""
    try:
        sts = [s for s, _ in strokes_at(f, z_badge)]
    except SystemExit:
        return False
    if len(sts) < 3:
        return False
    box = max(sts, key=lambda s: _bb([s])[2] - _bb([s])[0])
    return decode([s for s in sts if s is not box]) is not None


def check(la, lb, top, z_old, z_new, z_badge, words, lab_ids, badge_ids, factor):
    fa, _ = gcode.parse(la); fb, _ = gcode.parse(lb)
    if len(fa) != len(fb):
        return False, f'feature count changed {len(fa)} -> {len(fb)}  -> FAIL'
    strip = lambda L, f: [NW.sub('', L[k]) for k in range(f['start'], f['end'] + 1)]
    bad = []
    for A, B in zip(fa, fb):
        if A['id'] in lab_ids:
            if abs(B['zmin'] - z_new) > 1e-6:
                bad.append(f'label cut {A["id"]} deepest Z{B["zmin"]:.3f}')
            sts = [s for s, _ in strokes_at(B, z_new)]
            got = []
            for g in cluster(sts):
                r = decode([sts[k] for k in g])
                if r is None:
                    bad.append(f'label cut {A["id"]}: a word does not read back'); continue
                got.append((r[0], r[1], r[2]))
            want = [(w['text'], w['rot'], w['c']) for w in words if w['f']['id'] == A['id']]
            for t, r, c in want:
                if not any(t == t2 and r == r2 and math.dist(c, c2) < 0.01 for t2, r2, c2 in got):
                    bad.append(f'"{t}" not found again at X{c[0]:.0f} Y{c[1]:.0f}')
            if len(got) != len(want):
                bad.append(f'label cut {A["id"]}: {len(got)} words, wanted {len(want)}')
        elif A['id'] in badge_ids:
            sa, sb = strip(la, A), strip(lb, B)
            if [FW.sub('', l) for l in sa] != [FW.sub('', l) for l in sb]:
                bad.append(f'badge {A["id"]}: something other than a feed changed')
            for x, y in zip(sa, sb):
                fx, fy = FW.search(x), FW.search(y)
                if fx and fy and fx.group(1) != fy.group(1) and abs(float(fy.group(1)) - round(float(fx.group(1)) * factor, 1)) > 0.05:
                    bad.append(f'badge {A["id"]}: feed {fx.group(1)} -> {fy.group(1)}')
        elif strip(la, A) != strip(lb, B):
            bad.append(f'cut {A["id"]} changed')
    ok = not bad
    return ok, (f'check: every other cut line for line the same, the words read back in the same spots at Z{z_new:.3f}, '
                f'badge feeds x{factor}{"" if ok else " - " + "; ".join(bad[:6])}  -> {"OK" if ok else "FAIL"}')


if __name__ == '__main__':
    main()
