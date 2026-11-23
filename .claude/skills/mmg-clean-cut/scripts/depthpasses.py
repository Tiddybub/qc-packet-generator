#!/usr/bin/env python3
"""FireGuard for T-slots and pocket-outs: no pass takes more than one bit width (6 mm), and the
bit lifts out between passes.

User (2026-11-23, cutting D8 V17): "The tslots on D8 are not fixed." Then: "Fix the tslots on the
other nine sheets." Then, with the PH part's long opening circled on the drawing: "This spot on D8
cut PH cuts too aggressive."

FireGuard (fireguard.py) only looks at cuts up to 13 mm wide. These are wider, and the bit cuts
them buried, never lifting out on the way down:
  T-slots (20 mm across the head)
      D8, D6             one straight plunge 0.38-0.59 in deep, then the whole slot at full depth
      the other sheets   2 or 3 depth levels (0.16-0.36 in each) in one go, no lift
  pocket-outs (an opening or a blind pocket the CAM clears with laps at ONE depth)
      D8 PH opening      a steep spiral straight down 0.71 in in 86 mm of travel, then 1.3 m of
                         laps at full depth, all at 630 ipm
      the same on 3/4 and 1 in holes, the 21 x 43 mm slots and the blind 15 x 56 / 22 x 30 mm pockets

Which cuts (targets):
  - every T-slot (tslots.py);
  - every OPENING that is pocketed out: a cut that is not a part outline or a label, goes down in
    one entry, goes through the sheet, is not a round hole, clears its whole area (no slug left
    standing), and reaches its depth by a steep way down (a straight plunge, or a ramp steeper
    than 1 in 10) more than 6 mm below the level before. On D8 that is the PH opening and the
    four dog-bone slots by CL.
  - NOT: a lap round the outline of an opening (it leaves the slug standing, like a part outline;
    the finishing lap after a pocket-out is one of these and only shaves a skin).
  - NOT, unless --all-pockets: round through holes (3/4 in, 1 in ...) and blind pockets cut the
    same way. The user was shown all 26 such cuts on D8 and said "Just fix red" (the openings).
A helix that winds down gently round an opening is always left alone: it never takes more than
about a bit width per turn.

What is done to them:
  - The programmed cut is split where it starts down to its next depth level (a level = a depth
    the bit laps at). Each level's stretch is one pass.
  - A level that takes off more than MAX_LAYER (6 mm = one bit width, 0.236 in) is cut in 2 to 4
    equal passes of its own stretch: the same moves, never deeper than that pass's depth. Its
    last pass is the programmed one, line for line.
  - Between passes the bit lifts straight out, and goes straight back down where the next pass
    starts (the cut is already open there) at 50 ipm at most.
Nothing moves sideways that did not before, nothing is cut deeper or anywhere new, no feed is
raised, no other cut is touched.

    python3 -I depthpasses.py IN.MMG OUT.MMG --stock-in 0.71      (checks itself, exits 1 on a problem)
"""
import argparse
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gcode
import tslots
from analyze import classify

FW = re.compile(r'F(-?\d+\.?\d*)')
ZW = re.compile(r'Z(-?\d+\.?\d*)')
GW = re.compile(r'G0?[0-3](?!\d)')
NW = re.compile(r'^N\d+')
MAX_LAYER = 6.0        # mm (0.236 in): the most one pass may take off = one bit width
SAFE = 2.54            # mm above the real top the bit lifts to between passes (as fireguard.py)
LEVEL_MM = 25.0        # mm of flat cutting at one depth that makes it a level
DEEP = 7.0             # mm: cuts shallower than this in all are left alone (fireguard.DEEP; labels, the badge)
STEEP = 0.1            # way down steeper than 1 in 10 = the laps at the level cut the whole layer at once
REENTRY = 1270.0       # mm/min = 50 ipm: the most the bit feeds back down an open cut
THROUGH = 0.3          # mm: a cut that reaches this Z or lower goes through the sheet


def _entries(f, top):
    """stretches of feed moves below the wood surface; a rapid above the wood ends one"""
    runs, cur = [], []
    for m in f['moves']:
        if m[1] == 0:
            if cur and max(m[4], m[7]) >= top + 1e-6:
                runs.append(cur); cur = []
            continue
        if min(m[4], m[7]) < top - 1e-6:
            cur.append(m)
    if cur:
        runs.append(cur)
    return runs


def _feeds(lines):
    out, cur = {}, None
    for k, l in enumerate(lines):
        m = FW.search(l)
        if m:
            cur = float(m.group(1))
        out[k] = cur
    return out


def _moving(m):
    return abs(m[5] - m[2]) > 1e-6 or abs(m[6] - m[3]) > 1e-6


def _segments(W):
    """one stretch of the cut per depth level -> [(first index, end index, floor Z)]"""
    flat = {}
    for m in W:
        if _moving(m) and abs(m[7] - m[4]) < 1e-6:
            flat[round(m[7], 3)] = flat.get(round(m[7], 3), 0.0) + gcode.move_len(m)
    levels = sorted((z for z, L in flat.items() if L >= LEVEL_MM), reverse=True)
    segs, start, k, seen = [], 0, 0, 0.0
    for idx, m in enumerate(W):
        if k < len(levels) - 1:
            if _moving(m) and abs(m[7] - m[4]) < 1e-6 and abs(m[7] - levels[k]) < 1e-6:
                seen += gcode.move_len(m)
            elif seen >= LEVEL_MM and m[7] < levels[k] - 0.05:
                segs.append((start, idx)); start, k, seen = idx, k + 1, 0.0
    segs.append((start, len(W)))
    out = [(a, b, min(min(m[4], m[7]) for m in W[a:b])) for a, b in segs]
    if any(out[i][2] >= out[i - 1][2] - 0.05 for i in range(1, len(out))):      # not a plain step-down: one stretch
        out = [(0, len(W), min(min(m[4], m[7]) for m in W))]
    return out


def _steep(W, segs, top):
    """True if some level more than MAX_LAYER below the one before is reached by a steep way down"""
    prev = top
    for i0, i1, floor in segs:
        t = prev - floor
        way = 0.0
        for m in W[i0:i1]:
            if _moving(m) and abs(m[7] - m[4]) < 1e-6 and abs(m[7] - floor) < 0.7:
                break                                          # the first lap at the level
            if _moving(m) and m[7] < m[4] - 1e-6:
                way += gcode.move_len(m)
        if t > MAX_LAYER and t >= STEEP * way:
            return True
        prev = floor
    return False


def _round(W, f):
    """True if the cut is a round hole: square box and no point outside its circle"""
    b = f['bbox']; w, h = b[2] - b[0], b[3] - b[1]
    if abs(w - h) > 0.6:
        return False
    cx, cy, r = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, max(w, h) / 2
    return all(math.hypot(q[0] - cx, q[1] - cy) <= r + 0.3 for m in W for q in gcode.move_pts(m))


def _clears(W, f, tool=6.0, res=0.5):
    """True if the cut clears its whole area (a pocket-out): no island of uncut wood is left inside
    it. A lap round the outline of an opening leaves the slug standing: that is not a pocket-out."""
    from PIL import Image, ImageDraw
    b = f['bbox']
    x0, y0 = b[0] - tool, b[1] - tool
    im = Image.new('L', (int((b[2] - b[0] + 2 * tool) / res) + 3, int((b[3] - b[1] + 2 * tool) / res) + 3), 0)
    d = ImageDraw.Draw(im); r = tool / 2 / res
    for m in W:
        pts = [((x - x0) / res, (y - y0) / res) for x, y in gcode.move_pts(m)]
        if len(pts) > 1:
            d.line(pts, fill=255, width=int(round(2 * r)))
        for q in pts:
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=255)
    ImageDraw.floodfill(im, (0, 0), 128)
    return im.histogram()[0] * res * res < 4.0             # mm2 of wood left standing inside


def targets(feats, ptop, top, all_pockets=False):
    """-> {feature id: kind} the cuts this step changes.
    'T-slot'   every T-slot
    'opening'  a pocket-out that goes through the sheet and is not a round hole: the PH opening,
               the dog-bone slots (user, 2026-11-23: "Just fix red then do that for the rest of the sheets")
    'hole' / 'pocket'  round through holes and blind pockets cut the same way: only with
               all_pockets (the user was shown them on D8 and chose to leave them)"""
    out = {i: 'T-slot' for i in tslots.find(feats, ptop)}
    for f in feats:
        op = (f['op'] or '').upper()
        if f['id'] in out or op.startswith(('OUTER', 'ROUGH')) or f.get('kind') == 'label':
            continue
        runs = _entries(f, top)
        if len(runs) != 1:
            continue
        low = min(min(m[4], m[7]) for m in runs[0])
        if top - low <= DEEP or not _steep(runs[0], _segments(runs[0]), top) or not _clears(runs[0], f):
            continue
        kind = 'pocket' if low > THROUGH else ('hole' if _round(runs[0], f) else 'opening')
        if kind == 'opening' or all_pockets:
            out[f['id']] = kind
    return out


def apply(lines, top, say=print, all_pockets=False):
    feats, _ = gcode.parse(lines)
    ptop = gcode.program_top(lines)
    classify(feats, ptop)
    eff = _feeds(lines)
    swap, rows = {}, []
    for i, what in sorted(targets(feats, ptop, top, all_pockets).items()):
        f = feats[i]
        runs = _entries(f, top)
        if len(runs) != 1:
            continue                                           # already in passes
        W = runs[0]
        a, b = W[0][0], W[-1][0]
        first = W[0]
        if [m[0] for m in W] != list(range(a, b + 1)) or any(not GW.search(NW.sub('', lines[k])) for k in range(a, b + 1)):
            say(f'{what} {i}: its cut is not one unbroken run of G1/G2/G3 lines - left as is'); continue
        if first[4] < top - 1e-6:
            say(f'{what} {i}: does not come in from above the wood - left as is'); continue
        segs = _segments(W)
        safe, pf = top + SAFE, min(eff[a], REENTRY)
        new, passes, layers, prev, cur_xy = [], 0, [], top, None
        for si, (i0, i1, floor) in enumerate(segs):
            t = prev - floor
            p = max(1, math.ceil((t - 1e-6) / MAX_LAYER))
            sx, sy, sz = W[i0][2], W[i0][3], W[i0][4]
            for j in range(1, p + 1):
                clamp = prev - t * j / p
                if cur_xy is not None:                         # lift straight out, go over where this pass starts
                    new.append(f'G0X{cur_xy[0]:.3f}Y{cur_xy[1]:.3f}Z{safe:.3f}')
                    if (round(cur_xy[0], 3), round(cur_xy[1], 3)) != (round(sx, 3), round(sy, 3)):
                        new.append(f'G0X{sx:.3f}Y{sy:.3f}Z{safe:.3f}')
                    if si > 0 or (_moving(W[i0]) and sz < safe - 1e-6):
                        new.append(f'G1Z{sz:.3f}F{pf:.1f}')    # back down (open cut, or air) to where this stretch starts
                for t_i, k in enumerate(range(a + i0, a + i1)):
                    l = NW.sub('', lines[k])
                    m = ZW.search(l)
                    if j < p and m and float(m.group(1)) < clamp:
                        l = gcode.set_z(l, clamp)
                    if t_i == 0 and not FW.search(l):          # a pass states its own feed
                        l += f'F{eff[k]:.1f}'
                    new.append(l)
                layers.append(round(t / p, 3)); passes += 1
                cur_xy = (W[i1 - 1][5], W[i1 - 1][6])
            prev = floor
        if passes == 1:
            continue
        swap[a] = (b, new)
        rows.append({'feature': i, 'what': what, 'passes': passes, 'levels': len(segs), 'most': max(layers), 'depth': round(top - prev, 3)})
    out, k = [], 0
    while k < len(lines):
        if k in swap:
            out.extend(swap[k][1]); k = swap[k][0] + 1
        else:
            out.append(lines[k]); k += 1
    n = 0
    for k, l in enumerate(out):                    # renumber N10, N20 ... (the added lines need numbers)
        if l and not l.startswith('(') and l != '%':
            n += 10
            out[k] = f'N{n}' + NW.sub('', l)
    for what in ('T-slot', 'opening') + (('hole', 'pocket') if all_pockets else ()):
        kinds = {}
        for r in rows:
            if r['what'] == what:
                kinds[(r['levels'], r['passes'])] = kinds.get((r['levels'], r['passes']), 0) + 1
        n_w = sum(kinds.values())
        say(f'{what}s: {n_w} changed: ' + '; '.join(f'{v} with {lv} depth level{"s" if lv > 1 else ""} now in {p} passes' for (lv, p), v in sorted(kinds.items()))
            if n_w else f'{what}s: none to change')
    for r in rows:
        if r['what'] != 'T-slot':
            bx = feats[r['feature']]['bbox']
            say(f'   {r["what"]} {r["feature"]}: {feats[r["feature"]]["op"]}, {bx[2] - bx[0] + 6:.0f} x {bx[3] - bx[1] + 6:.0f} mm at X{(bx[0] + bx[2]) / 2:.0f} Y{(bx[1] + bx[3]) / 2:.0f}, '
                f'{r["depth"] / 25.4:.2f} in deep: {r["passes"]} passes, {r["most"] / 25.4:.3f} in at most')
    return out, rows


def check(la, lb, top, rows):
    """Independent of how the passes were built. Every pass of a changed T-slot is a run of the
    programmed moves in their order (same X/Y, same arcs), never deeper than programmed; every
    programmed move is cut, and the last time at its programmed depth; no pass takes more than
    MAX_LAYER; no feed is raised; rapids only above the wood; every other cut is unchanged."""
    fa, _ = gcode.parse(la); fb, _ = gcode.parse(lb)
    if len(fa) != len(fb):
        return False, f'depth passes check: feature count changed {len(fa)} -> {len(fb)}  -> FAIL'
    Fa, Fb = _feeds(la), _feeds(lb)
    changed = {r['feature']: r for r in rows}
    strip = lambda L, f: [NW.sub('', L[k]) for k in range(f['start'], f['end'] + 1)]
    sig = lambda m: (m[1], round(m[2], 3), round(m[3], 3), round(m[5], 3), round(m[6], 3), m[8], m[9])
    bad, worst, npass = [], 0.0, 0
    for A, B in zip(fa, fb):
        r = changed.get(A['id'])
        if r is None:
            if strip(la, A) != strip(lb, B):
                bad.append(f'cut {A["id"]} changed')
            continue
        ra, rb = _entries(A, top), _entries(B, top)
        if len(ra) != 1 or len(rb) != r['passes']:
            bad.append(f'cut {A["id"]}: {len(rb)} entries, wanted {r["passes"]}'); continue
        old = ra[0]; osig = [sig(m) for m in old]
        pf = Fa[old[0][0]]
        last, deepest, at = {}, top, 0
        for k, run in enumerate(rb, 1):
            rs = [sig(m) for m in run]
            hit = None
            for lead in (0, 1):                               # a pass may start with one straight plunge of its own
                if lead and (_moving(run[0]) or len(run) < 2):
                    break
                body = rs[lead:]
                for i0 in range(at, len(osig) - len(body) + 1):
                    if osig[i0:i0 + len(body)] == body and all(
                            run[lead + q][4] >= min(old[i0 + q][4], top) - 0.002 and run[lead + q][7] >= old[i0 + q][7] - 0.002 for q in range(len(body))):
                        hit = (lead, i0); break
                if hit:
                    break
            if hit is None:
                bad.append(f'cut {A["id"]} pass {k}: not a run of the programmed moves, or deeper than programmed'); break
            lead, i0 = hit
            at = i0 if i0 + len(rs) - lead < len(osig) else at
            if lead and Fb[run[0][0]] > pf + 1e-6:
                bad.append(f'cut {A["id"]} pass {k}: plunge at F{Fb[run[0][0]]}')
            for q in range(len(rs) - lead):
                mo, mn = old[i0 + q], run[lead + q]
                if Fb[mn[0]] > Fa[mo[0]] + 1e-6:
                    bad.append(f'cut {A["id"]} pass {k}: feed raised to F{Fb[mn[0]]}')
                last[i0 + q] = abs(mn[7] - mo[7]) < 0.002 and (mo[4] >= top or abs(mn[4] - mo[4]) < 0.002)
            low = min(min(m[4], m[7]) for m in run)
            worst = max(worst, deepest - low); deepest = min(deepest, low); npass += 1
        else:
            if len(last) != len(old) or not all(last.values()):
                bad.append(f'cut {A["id"]}: {len(old) - sum(last.values())} programmed moves not cut at their programmed depth')
        for m in B['moves']:                      # rapids only straight up, or sideways above the wood
            if m[1] == 0 and _moving(m) and min(m[4], m[7]) < top + 0.5:
                bad.append(f'cut {A["id"]}: rapid sideways near the wood, line {m[0] + 1}')
    if worst > MAX_LAYER + 0.01:
        bad.append(f'a pass takes {worst:.2f} mm, more than {MAX_LAYER}')
    ok = not bad
    return ok, (f'depth passes check ({len(rows)} cuts, {npass} passes): every pass follows the programmed moves and is never deeper, '
                f'every programmed move ends at its programmed depth, most new wood in one pass {worst / 25.4:.3f} in, no feed raised, '
                f'every other cut line for line the same{"" if ok else " - " + "; ".join(bad[:6])}  -> {"OK" if ok else "FAIL"}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--stock-in', type=float, required=True)
    ap.add_argument('--all-pockets', action='store_true', help='also step round through holes and blind pockets that are cut '
                    'to depth in one level (the user chose to leave them on D8; only when asked)')
    a = ap.parse_args()
    top = a.stock_in * 25.4
    la = gcode.read_lines(a.src)
    out, rows = apply(la, top, all_pockets=a.all_pockets)
    gcode.write_lines(a.dst, out)
    ok, text = check(la, gcode.read_lines(a.dst), top, rows)
    print(text)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
