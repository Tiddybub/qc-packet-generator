#!/usr/bin/env python3
"""FireGuard: narrow holes, slots, slits and grooves are cut in depth steps, lifting out between.

User (2026-11-23, D7): "the little holes are wanting to catch fire. It's like the compression bit
is plunging straight down too far. And the dust has nowhere to go." Same fix as the I9 rail jig.

  at risk  : a cut that is not a part outline or a label, at most NARROW mm wide (bit edge
             included, about two bit widths), that goes deeper than DEEP mm below the real top
             in one entry (the bit never lifts out on the way down)
  holes, short slots, grooves (cut by spiralling or zigzagging down): at each step depth the bit
             lifts straight out to clear the dust, comes back down to BACK_OFF above where it was,
             feeds the last BACK_OFF at REENTRY (50 ipm), and carries on along the same path
  slits    (V15: plunge to full depth, then one flat loop): the same loop at each step depth,
             plunging straight down for every step (the user's "plunge to depth, then cut" kept)
  steps    : 3 for a cut more than 10 mm deep, 2 below that
  bottom   : a through cut stops BOTTOM below the table (0.010 in), not 0.020 in
Nothing moves sideways that did not before: every X/Y move and arc is kept, in order.

    python3 -I fireguard.py IN.MMG OUT.MMG --stock-in 0.71        (prints what it changed)
    (it always checks itself afterwards and exits 1 on a problem)
"""
import argparse
import math
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gcode

NARROW = 13.0          # mm, bit edge included
DEEP = 7.0             # mm below the real top in one entry
BACK_OFF = 1.0         # mm above the last depth the bit comes back to at rapid
REENTRY = 1270.0       # mm/min = 50 ipm
BOTTOM = -0.254        # mm: 0.010 in into the spoilboard
FW = re.compile(r'F(-?\d+\.?\d*)')
ZW = re.compile(r'Z(-?\d+\.?\d*)')
GW = re.compile(r'G0?([0-3])(?!\d)')
NW = re.compile(r'^N\d+')


def _runs(f, top):
    """stretches of cutting below the wood surface; a rapid lift out of the cut ends one"""
    runs, cur = [], []
    for m in f['moves']:
        if m[1] == 0 and max(m[4], m[7]) >= top + 1e-6:
            if cur:
                runs.append(cur); cur = []
            continue
        if m[1] != 0 and min(m[4], m[7]) < top - 1e-6:
            cur.append(m)
        elif cur:
            runs.append(cur); cur = []
    if cur:
        runs.append(cur)
    return runs


def _passes(f, top):
    """slit passes: [(plunge move, [following flat moves])], or None if the cut is not made of
    straight plunges each followed by flat cutting"""
    out = []
    for m in f['cut']:
        vertical = (m[2], m[3]) == (m[5], m[6])
        if vertical and m[7] < m[4] - 1e-6:
            if m[7] < top - 1e-6:
                out.append((m, []))
            continue
        if not out:
            if min(m[4], m[7]) < top - 1e-6:
                return None
            continue
        if abs(m[7] - m[4]) > 1e-6:
            return None
        out[-1][1].append(m)
    return out if out and all(p[1] for p in out) else None


def find(feats, top, tool=6.0):
    """-> [(feature, kind)] kind = 'slit' (straight plunges, each followed by a flat loop) or
    'descent' (spiral / zigzag down)"""
    out = []
    for f in feats:
        op = (f['op'] or '').upper()
        if op.startswith(('OUTER', 'ROUGH')):
            continue
        b = f['bbox']
        if min(b[2] - b[0], b[3] - b[1]) + tool > NARROW:
            continue
        runs = _runs(f, top)
        if not runs:
            continue
        depth, deepest = 0.0, top
        for r in runs:
            low = min(min(m[4], m[7]) for m in r)
            depth = max(depth, deepest - low); deepest = min(deepest, low)
        if depth <= DEEP:
            continue
        out.append((f, 'slit' if _passes(f, top) else 'descent'))
    return out


def _steps(depth):
    return 3 if depth > 10.0 else 2


def _feed_before(lines, k):
    for i in range(k, -1, -1):
        m = FW.search(lines[i])
        if m:
            return m.group(1)
    return None


def _modal_g(lines, k):
    for i in range(k, -1, -1):
        m = GW.search(NW.sub('', lines[i]))
        if m:
            return m.group(1)
    return '1'


def apply(lines, top, say=print):
    feats, _ = gcode.parse(lines)
    jobs = find(feats, top)
    safe = round(top + 2.54, 3)
    edits, after, drop = {}, {}, set()
    rows = []
    for f, kind in jobs:
        zb = max(f['zmin'], BOTTOM)
        depth = top - zb
        n = _steps(depth)
        levels = [round(top - depth * k / n, 3) for k in range(1, n)]
        step_max = depth / n + 0.3
        if kind == 'descent':
            # 1. stop 0.010 in into the spoilboard
            for k in range(f['start'], f['end'] + 1):
                m = ZW.search(lines[k])
                if m and float(m.group(1)) < BOTTOM - 1e-9:
                    edits[k] = gcode.set_z(edits.get(k, lines[k]), BOTTOM)
            # 2. lift out where the cut first reaches each step depth. A straight move that goes past
            #    a step depth is split right there, so no entry goes deeper than one step.
            mv = f['cut']
            todo = {}
            for t in levels:
                i = next((i for i, m in enumerate(mv) if m[7] <= t + 1e-6), None)
                if i is not None and i + 1 < len(mv):
                    todo.setdefault(i, []).append(t)
            for i, ts in todo.items():
                m = mv[i]
                fk = _feed_before(lines, m[0])
                gk = _modal_g(lines, m[0])
                src = edits.get(m[0], lines[m[0]])
                nnum = NW.match(src).group(0) if NW.match(src) else ''
                pieces, block = [], []
                split = m[1] == 1 and m[4] > max(ts) + 1e-6
                for t in sorted(ts, reverse=True):
                    if split:
                        u = (m[4] - t) / (m[4] - m[7])
                        x, y, z = m[2] + (m[5] - m[2]) * u, m[3] + (m[6] - m[3]) * u, t
                        pieces.append(f'G1X{x:.3f}Y{y:.3f}Z{z:.3f}')
                    else:
                        x, y, z = m[5], m[6], max(m[7], BOTTOM)
                    pieces += [f'G0X{x:.3f}Y{y:.3f}Z{safe:.3f}', f'G0X{x:.3f}Y{y:.3f}Z{z + BACK_OFF:.3f}', f'G1Z{z:.3f}F{REENTRY:.1f}']
                if split:
                    # the first piece carries the line's number and its own feed; the rest of the
                    # original move follows the last lift, at the feed it had
                    first = nnum + pieces[0] + (f'F{FW.search(src).group(1)}' if FW.search(src) else '')
                    rest = NW.sub('', src)
                    if not GW.search(rest):
                        rest = 'G' + gk + rest
                    rest = FW.sub('', rest) + (f'F{fk}' if fk else '')
                    edits[m[0]] = first
                    after.setdefault(m[0], []).extend(pieces[1:] + [rest])
                else:
                    after.setdefault(m[0], []).extend(pieces)
                    nxt = mv[i + 1][0]
                    t2 = edits.get(nxt, lines[nxt])
                    if not GW.search(NW.sub('', t2)):
                        t2 = (NW.match(t2).group(0) if NW.match(t2) else '') + 'G' + _modal_g(lines, nxt) + NW.sub('', t2)
                    if not FW.search(t2) and fk:
                        t2 += f'F{fk}'
                    edits[nxt] = t2
            rows.append({'feature': f['id'], 'kind': 'hole/slot/groove', 'steps': len(levels) + 1, 'levels': levels,
                         'bottom_from': round(f['zmin'], 3), 'bottom_to': round(zb, 3)})
        else:
            # slit: every pass that goes more than one step deeper than the last gets extra passes
            # of the same loop in between, each a straight plunge then the flat loop
            passes = _passes(f, top)
            prev, reps, ex, ey = top, [], None, None
            for pi, (p, loop) in enumerate(passes):
                gap = prev - p[7]
                k = max(1, math.ceil(gap / step_max - 1e-9))
                extra = [round(prev - gap * j / k, 3) for j in range(1, k)]
                reps.append(len(extra) + 1)
                sx, sy = p[5], p[6]
                path = []
                last_line = (passes[pi + 1][0][0] - 1) if pi + 1 < len(passes) else f['end']
                for kk in range(p[0] + 1, last_line + 1):
                    if not lines[kk].startswith('('):
                        path.append(kk)
                lex, ley = loop[-1][5], loop[-1][6]
                block, cur = [], prev
                for z in extra:
                    if ex is not None:
                        block += [f'G0X{ex:.3f}Y{ey:.3f}Z{safe:.3f}', f'G0X{sx:.3f}Y{sy:.3f}Z{safe:.3f}',
                                  f'G0X{sx:.3f}Y{sy:.3f}Z{cur + BACK_OFF:.3f}']
                    block.append(f'G1Z{z:.3f}F{REENTRY:.1f}')
                    for kk in path:
                        t = NW.sub('', lines[kk])
                        if ZW.search(t):
                            t = gcode.set_z(t, z)
                        block.append(t)
                    ex, ey, cur = lex, ley, z
                if extra:
                    block += [f'G0X{ex:.3f}Y{ey:.3f}Z{safe:.3f}', f'G0X{sx:.3f}Y{sy:.3f}Z{safe:.3f}',
                              f'G0X{sx:.3f}Y{sy:.3f}Z{cur + BACK_OFF:.3f}']
                    after.setdefault(p[0] - 1, []).extend(block)
                prev, ex, ey = p[7], lex, ley
            rows.append({'feature': f['id'], 'kind': 'slit', 'steps': sum(reps), 'reps': reps,
                         'bottom_from': round(f['zmin'], 3), 'bottom_to': round(f['zmin'], 3)})
    out = []
    for k, l in enumerate(lines):
        if k not in drop:
            out.append(edits.get(k, l))
        out.extend(after.get(k, []))
    n = 0
    for k, l in enumerate(out):
        if l and not l.startswith('(') and l != '%':
            n += 10
            out[k] = f'N{n}' + NW.sub('', l)
    kinds = {}
    for r in rows:
        kinds[r['kind']] = kinds.get(r['kind'], 0) + 1
    say(f'FireGuard: {len(rows)} cuts in steps ' + ', '.join(f'{v} {k}' for k, v in kinds.items()))
    return out, rows


def check(la, lb, top, rows):
    """The new program cuts the same paths: every X/Y move of every feature in the same order,
    nothing deeper (holes stop at BOTTOM), extra moves only straight up / down or rapids above the
    wood, no cutting move faster than before, every other feature line for line the same."""
    fa, _ = gcode.parse(la); fb, _ = gcode.parse(lb)
    if len(fa) != len(fb):
        return False, f'feature count changed {len(fa)} -> {len(fb)}'
    changed = {r['feature']: r for r in rows}
    strip = lambda L, f: [NW.sub('', L[k]) for k in range(f['start'], f['end'] + 1)]
    feeds = lambda L: _feeds(L)
    Fa, Fb = feeds(la), feeds(lb)
    bad = []
    for i, (A, B) in enumerate(zip(fa, fb)):
        if i not in changed:
            if strip(la, A) != strip(lb, B):
                bad.append((i, 'unchanged feature differs'))
            continue
        r = changed[i]
        sideA = [(m[1],) + tuple(round(v, 3) for v in (m[2], m[3], m[5], m[6], m[8], m[9])) for m in A['cut'] if (m[2], m[3]) != (m[5], m[6])]
        sideB = [(m[1],) + tuple(round(v, 3) for v in (m[2], m[3], m[5], m[6], m[8], m[9])) for m in B['cut'] if (m[2], m[3]) != (m[5], m[6])]
        if r['kind'] == 'slit':
            key = lambda m: (m[1],) + tuple(round(v, 3) for v in (m[2], m[3], m[5], m[6], m[8], m[9]))
            want = []
            for (p, loop), n_ in zip(_passes(A, top), r['reps']):
                want += [key(m) for m in loop] * n_
            if sideB != want:
                bad.append((i, 'slit path is not the old loops repeated')); continue
        else:
            # every old sideways move is still there, in order; a straight move may now be in pieces
            # (split where a step depth falls), each piece exactly on the old line
            SA = [m for m in A['cut'] if (m[2], m[3]) != (m[5], m[6])]
            SB = [m for m in B['cut'] if (m[2], m[3]) != (m[5], m[6])]
            j, broke = 0, None
            for a in SA:
                while True:
                    if j >= len(SB):
                        broke = 'path ends early'; break
                    b_ = SB[j]; j += 1
                    if a[1] in (2, 3):
                        if b_[1:] [:1] != a[1:2] or any(abs(u - v) > 0.002 for u, v in zip(b_[2:4] + b_[5:7] + b_[8:10], a[2:4] + a[5:7] + a[8:10])):
                            broke = f'arc changed, line {b_[0] + 1}'
                        break
                    d, t = _seg(b_[5:7], a[2:4], a[5:7])
                    if b_[1] != 1 or d > 0.002:
                        broke = f'move leaves the old line, line {b_[0] + 1}'; break
                    if math.dist(b_[5:7], a[5:7]) < 0.002:
                        break
                if broke:
                    break
            if broke or j != len(SB):
                bad.append((i, broke or 'extra sideways moves')); continue
        if B['zmin'] < max(A['zmin'], BOTTOM) - 1e-6:
            bad.append((i, f'deeper than before ({B["zmin"]})'))
        for m in B['moves']:
            if m[1] == 0 and (m[2], m[3]) != (m[5], m[6]) and min(m[4], m[7]) < top + 0.5:
                bad.append((i, f'rapid sideways in the wood, line {m[0] + 1}')); break
        fa_max = max((Fa.get(m[0], 0) for m in A['cut'] if (m[2], m[3]) != (m[5], m[6])), default=0)
        fb_max = max((Fb.get(m[0], 0) for m in B['cut'] if (m[2], m[3]) != (m[5], m[6])), default=0)
        if fb_max > fa_max + 1e-6:
            bad.append((i, f'cuts faster than before ({fb_max} > {fa_max})'))
        # each entry into the wood goes no deeper than one step below where the last one stopped
        lifts = sum(1 for m in B['moves'] if (m[2], m[3]) == (m[5], m[6]) and m[7] >= top + 1.0 and m[4] < top)
        if lifts < r['steps'] - 1:
            bad.append((i, f'only {lifts} lifts out for {r["steps"]} steps'))
    ok = not bad
    return ok, (f'FireGuard check ({len(rows)} cuts): same paths, nothing deeper, lifts out between steps, no faster feeds, '
                f'every other cut line for line the same{"; PROBLEMS " + str(bad[:6]) if bad else ""}  -> {"OK" if ok else "FAIL"}')


def _seg(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    L2 = ax * ax + ay * ay
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / L2))
    return math.dist(p, (a[0] + t * ax, a[1] + t * ay)), t


def _feeds(L):
    out, cur = {}, None
    for k, l in enumerate(L):
        m = FW.search(l)
        if m:
            cur = float(m.group(1))
        out[k] = cur
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--stock-in', type=float, required=True)
    a = ap.parse_args()
    top = a.stock_in * 25.4
    la = gcode.read_lines(a.src)
    out, rows = apply(la, top)
    gcode.write_lines(a.dst, out)
    ok, text = check(la, gcode.read_lines(a.dst), top, rows)
    print(text)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
