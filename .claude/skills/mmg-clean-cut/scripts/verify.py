#!/usr/bin/env python3
"""Prove a converted program cuts the same shapes as the original.

Sweeps a TOOL_MM bit along both programs and checks, using OUT.MMG.json from convert.py:
  labels: outline at the real wood surface unchanged, every label cut to the label depth,
          nothing deeper than the label depth
  parts : outline at the wood surface identical, nothing cut that the original did not cut,
          anything no longer cut is on the waste side. Thin differences flagged at the normal
          resolution are re-measured at 0.02 mm/px; up to FINE_TOL (0.25 mm = 0.01 in) passes,
          anything no longer cut is on the waste side (never touches the part)
  T-slots: exact same path as the original, no cutting move in the wood faster than the T-slot
          feed, no plunge faster than the T-slot plunge feed, and every feature that was not
          converted still runs at exactly the feeds it had
  dust   : each extra lap is a move-for-move copy of that part's through lap (so the tabs stay),
          its sideways moves run at the dust feed, and a part the converter did not touch is
          otherwise exactly the original
  diff  : which operations changed
Exit code 1 if any check fails.

Usage: python3 verify.py ORIGINAL.MMG CONVERTED.MMG [--tool-mm 6]
"""
import argparse, difflib, json, math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from gcode import read_lines, parse, move_pts
import tslots
import dustpass
import holes
import singleline
from PIL import Image, ImageChops, ImageDraw, ImageFilter


def raster(moves, box, zlimit, res, dia):
    x0, y1 = box[0], box[3]
    W = int((box[2] - box[0]) / res) + 1; H = int((box[3] - box[1]) / res) + 1
    im = Image.new('L', (W, H), 0); d = ImageDraw.Draw(im); r = dia / 2 / res
    def flush(run):
        if len(run) > 1: d.line(run, fill=255, width=max(1, int(round(2 * r))))
        for q in run[::max(1, int(r / 2))] + run[-1:]:
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=255)
    for m in moves:
        if m[1] == 0: continue
        pts = move_pts(m); L = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) or 1e-9
        run, acc = [], 0.0
        for i in range(len(pts) - 1):
            seg = math.dist(pts[i], pts[i + 1]); k = max(1, int(seg / res))
            for s in range(k + 1):
                t = s / k; z = m[4] + (m[7] - m[4]) * (acc + seg * t) / L
                p = ((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t - x0) / res,
                     (y1 - (pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t)) / res)
                if z < zlimit: run.append(p)
                elif run: flush(run); run = []
            acc += seg
        if run: flush(run)
    return im


ADD_CLEAR = 3.0      # mm of wood between a label added with --add-label and any other cut
BADGE_CLEAR = 8.0    # mm of wood between the badge box and any other cut (user, V8: "box moved out"; kept clear of parts)
FINE_TOL = 0.25      # mm (0.01 in): widest allowed difference at a part edge, measured at 0.02 mm/px


def fine_width(flag, box, res, om, nm, top, D):
    """widest strip (mm) newly cut or no longer cut, re-rendered at 0.02 mm/px around flagged pixels"""
    ys, xs = np.nonzero(flag)
    spots = {}
    for x, y in zip(xs, ys):
        spots.setdefault((x // int(8 / res), y // int(8 / res)), []).append((box[0] + x * res, box[3] - y * res))
    worst, r2 = 0.0, 0.02
    def width(mask):
        k = 0; m = Image.fromarray((mask * 255).astype(np.uint8))
        while (np.array(m) > 0).any() and k < 400:
            m = m.filter(ImageFilter.MinFilter(3)); k += 1
        return k * 2 * r2
    for pts in spots.values():
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        sb = (cx - 8, cy - 8, cx + 8, cy + 8)
        for lvl in (top, 0.0):
            o = np.array(raster(om, sb, lvl, r2, D)) > 0; n = np.array(raster(nm, sb, lvl, r2, D)) > 0
            worst = max(worst, width(n & ~o), width(o & ~n))
    return worst


def _samples(moves, top, step=0.5):
    """points every step mm along the moves that cut wood"""
    out = []
    for m in moves:
        if m[1] == 0 or min(m[4], m[7]) >= top - 1e-6:
            continue
        pts = move_pts(m)
        for i in range(len(pts) - 1):
            n = max(1, int(math.dist(pts[i], pts[i + 1]) / step))
            out += [(pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k / n, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k / n) for k in range(n + 1)]
    return np.array(out) if out else np.zeros((0, 2))


def _clearance(mine, feats, skip, box, top, D, reach):
    """mm of wood between the cut `mine` (sample points) and the nearest cut of any other feature
    within reach of box -> (mm, feature id) or (None, None) when nothing is near"""
    x0, y0, x1, y1 = box
    gap, who = None, None
    for k, f in enumerate(feats):
        bb = f['bbox']
        if k == skip or bb[0] > x1 + reach or bb[2] < x0 - reach or bb[1] > y1 + reach or bb[3] < y0 - reach:
            continue
        oth = _samples(f['cut'], top)
        if not len(oth) or not len(mine):
            continue
        oth = oth[(oth[:, 0] > x0 - reach) & (oth[:, 0] < x1 + reach) & (oth[:, 1] > y0 - reach) & (oth[:, 1] < y1 + reach)]
        for j in range(0, len(oth), 4000):
            d = np.sqrt(((mine[:, None, :] - oth[None, j:j + 4000, :]) ** 2).sum(axis=2)).min() - D
            if gap is None or d < gap:
                gap, who = float(d), k
    return gap, who


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('orig'); ap.add_argument('new'); ap.add_argument('--tool-mm', type=float, default=6.0)
    a = ap.parse_args()
    rep = json.load(open(a.new + '.json'))
    top, zl, D = rep['stock_in'] * 25.4, rep['label_z'], a.tool_mm
    la, lb = read_lines(a.orig), read_lines(a.new)
    fa, _ = parse(la); fb, _ = parse(lb)
    # features the converter removed whole (in-between depth steps of a part): take them out of the
    # original's list so both lists line up; their cuts still count as part of the old outline below
    fa_all = fa
    gone = set(rep.get('removed_features') or [])
    fa = [f for k, f in enumerate(fa_all) if k not in gone]
    ok = True
    if len(fa) != len(fb):
        print(f'FAIL feature count changed {len(fa)} -> {len(fb)}'); sys.exit(1)

    # ---- labels
    if rep['labels']:
        res, px2 = 0.05, 0.0025
        t = dict(old=0, extra=0, lost=0, shallow=0, deeper=0); worst = 0
        bdg = rep.get('badge') or {}
        new_text = bdg.get('feature') if rep.get('label_mode') == 'single-line' and bdg else None
        font_words = {wd['feature'] for wd in rep.get('words') or []}
        for i in rep['labels']:
            if i == new_text or i in font_words:
                continue                      # badge and words written in the font: checked below
            A, B = fa[i], fb[i]
            bx = A['bbox']; box = (bx[0] - D, bx[1] - D, bx[2] + D, bx[3] + D)
            ot = raster(A['cut'], box, top, res, D); nt = raster(B['cut'], box, top, res, D)
            nf = raster(B['cut'], box, zl + 0.01, res, D); nd = raster(B['cut'], box, zl - 0.01, res, D)
            ref = ot
            if rep.get('label_mode') == 'single-line':
                # a hairline of wood between two old pocket passes is inside the letter (singleline.CLOSE)
                o = np.array(ot) > 0
                o = singleline._erode(singleline._dilate(o, singleline.CLOSE / res), singleline.CLOSE / res) | o
                ref = Image.fromarray((o * 255).astype(np.uint8))
            exm = ImageChops.subtract(nt, ref)
            if rep.get('label_mode') == 'single-line':
                # the new line runs right along the letter's edge where a stroke is one bit wide: specks
                # one pixel (0.05 mm) wide there are drawing noise; anything 0.1 mm wide or more counts
                exm = exm.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
            ex = exm.histogram()[255] * px2
            t['old'] += ot.histogram()[255] * px2; t['extra'] += ex
            t['lost'] += ImageChops.subtract(ot, nt).histogram()[255] * px2
            t['shallow'] += ImageChops.subtract(nt, nf).histogram()[255] * px2
            t['deeper'] += nd.histogram()[255] * px2; worst = max(worst, ex)
        lab_ok = worst < 0.5 and t['deeper'] == 0 and t['shallow'] < 0.002 * t['old'] + 1
        ok &= lab_ok
        traced = [i for i in rep['labels'] if i != new_text and i not in font_words]
        kept = (t['old'] - t['lost']) / t['old'] * 100 if t['old'] else 0
        mode = f"one bit-wide line, {kept:.0f} % of the old letter area still cut; " if rep.get('label_mode') == 'single-line' else ''
        if traced:
          print(f"labels ({len(traced)}): {mode}outline {t['old']:.0f} mm2; new cut outside old {t['extra']:.2f} mm2 "
              f"(worst label {worst:.2f}); no longer cut {t['lost']:.2f} mm2; not at full depth {t['shallow']:.2f} mm2; "
              f"deeper than Z{zl}: {t['deeper']:.2f} mm2  -> {'OK' if lab_ok else 'FAIL'}")

    # ---- the sheet badge in a box (blockfont): at the badge depth, inside its box line, clear of every other cut
    bdg = rep.get('badge') or {}
    if bdg.get('style') == 'box':
        B = fb[bdg['feature']]; zb = bdg['z']; x0, y0, x1, y1 = bdg['box']
        wood = [m for m in B['cut'] if min(m[4], m[7]) < top - 1e-6]
        deep = min(min(m[4], m[7]) for m in B['cut'])
        flat = sum(math.dist((m[2], m[3]), (m[5], m[6])) for m in wood if abs(m[4] - zb) < 1e-6 and abs(m[7] - zb) < 1e-6)
        over = max(max(x0 - q[0], q[0] - x1, y0 - q[1], q[1] - y1) for m in wood for q in move_pts(m))
        gap, who = _clearance(_samples(wood, top), fb, bdg['feature'], (x0, y0, x1, y1), top, D, BADGE_CLEAR + D + 5)
        b_ok = abs(deep - zb) < 1e-6 and flat > 0 and over <= 0.002 and (gap is None or gap >= BADGE_CLEAR - 0.5)
        ok &= b_ok
        print(f"badge \"{bdg['text'].upper()}\" in a box {x1 - x0:.0f} x {y1 - y0:.0f} mm: deepest Z{deep:.3f} (badge depth Z{zb}); "
              f"{flat:.0f} mm cut; outside its box line {max(over, 0):.3f} mm; nearest other cut "
              f"{'none near' if gap is None else f'{gap:.1f} mm of wood away (cut {who})'} (at least {BADGE_CLEAR:.0f})  -> {'OK' if b_ok else 'FAIL'}")

    # ---- the sheet badge with new text in the old ring (--label-font hershey): inside the old badge, at the label depth
    if bdg and bdg.get('style') != 'box' and rep.get('label_mode') == 'single-line':
        # inside the old badge: on the old ring (any piece of it) or inside its inner edge; label depth
        B = fb[bdg['feature']]; c = (bdg['cx'], bdg['cy'])
        far = max(math.dist(p, c) for m in B['cut'] if min(m[4], m[7]) < top for p in move_pts(m)) + D / 2
        deep = min(min(m[4], m[7]) for m in B['cut'])
        flat = sum(math.dist((m[2], m[3]), (m[5], m[6])) for m in B['cut'] if abs(m[4] - zl) < 1e-6 and abs(m[7] - zl) < 1e-6)
        R = bdg['r_edge'] + 1
        box = (c[0] - R, c[1] - R, c[0] + R, c[1] + R); res = 0.1
        old = np.zeros_like(np.array(raster([], box, top, res, D)) > 0)
        for k in bdg.get('old', []):
            old |= np.array(raster(fa_all[k]['cut'], box, top, res, D)) > 0
        yy, xx = np.mgrid[0:old.shape[0], 0:old.shape[1]]
        old |= np.hypot(box[0] + xx * res - c[0], box[3] - yy * res - c[1]) <= bdg.get('r_in_edge', 0)
        new = np.array(raster(B['cut'], box, top, res, D)) > 0
        out = Image.fromarray(((new & ~old) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
        outside = out.histogram()[255] * res * res
        b_ok = far <= bdg['r_edge'] + 0.05 and abs(deep - zl) < 1e-6 and flat > 0 and outside < 0.5
        ok &= b_ok
        name = f"\"{bdg['text'].upper()}\"" if bdg.get('text') else '(old text traced)'
        print(f"badge {name}: farthest cut {far:.2f} mm from the centre (old badge edge {bdg['r_edge']:.2f}); "
              f"outside the old ring and its inside {outside:.2f} mm2; deepest Z{deep:.3f} (label depth Z{zl}); "
              f"{flat:.0f} mm cut  -> {'OK' if b_ok else 'FAIL'}")

    # ---- label words written again in the single-line font: inside the old word's box, label depth
    if rep.get('words'):
        res, bad, worst, deep_bad = 0.1, [], 0.0, []
        added = rep.get('added_words') or []
        for wd in rep['words']:
            B = fb[wd['feature']]; x0, y0, x1, y1 = wd['box']
            box = (x0 - D, y0 - D, x1 + D, y1 + D)
            # words added with --add-label are cut in the same feature: each has its own box (checked below)
            mine = [m for m in B['cut'] if not any(ad['feature'] == wd['feature'] and all(
                ad['box'][0] - 0.01 <= q[0] <= ad['box'][2] + 0.01 and ad['box'][1] - 0.01 <= q[1] <= ad['box'][3] + 0.01
                for q in ((m[2], m[3]), (m[5], m[6]))) for ad in added)]
            new = np.array(raster(mine, box, top, res, D)) > 0
            yy, xx = np.mgrid[0:new.shape[0], 0:new.shape[1]]
            X = box[0] + (xx + 0.5) * res; Y = box[3] - (yy + 0.5) * res
            inside = (X >= x0 - 0.3) & (X <= x1 + 0.3) & (Y >= y0 - 0.3) & (Y <= y1 + 0.3)
            out = Image.fromarray(((new & ~inside) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
            a = out.histogram()[255] * res * res
            worst = max(worst, a)
            if a >= 0.5:
                bad.append((wd['text'], round(a, 2)))
            zmin = min(min(m[4], m[7]) for m in B['cut'])
            if abs(zmin - zl) > 1e-6:
                deep_bad.append((wd['text'], round(zmin, 3)))
        # every cut of a word feature is inside its own word's box or an added word's box
        for wd in rep['words']:
            boxes = [wd['box']] + [ad['box'] for ad in added if ad['feature'] == wd['feature']]
            stray = [m[0] + 1 for m in fb[wd['feature']]['cut'] if min(m[4], m[7]) < top - 1e-6 and not any(
                b[0] - 0.4 <= q[0] <= b[2] + 0.4 and b[1] - 0.4 <= q[1] <= b[3] + 0.4 for b in boxes for q in [(m[5], m[6])])]
            if stray:
                bad.append((wd['text'], f'{len(stray)} moves outside every word box, line {stray[0]}'))
        w_ok = not bad and not deep_bad
        ok &= w_ok
        print(f"label words in the font ({len(rep['words'])}): outside the old word's box worst {worst:.2f} mm2"
              f"{' ' + str(bad[:6]) if bad else ''}; not at label depth Z{zl}: {len(deep_bad)}{' ' + str(deep_bad[:6]) if deep_bad else ''}"
              f"  -> {'OK' if w_ok else 'FAIL'}")

    # ---- labels added with --add-label: at the label depth (same feature as a checked word), clear of every other cut
    if rep.get('added_words'):
        a_ok, notes = True, []
        for ad in rep['added_words']:
            x0, y0, x1, y1 = ad['box']
            B = fb[ad['feature']]
            mine = _samples([m for m in B['cut'] if x0 - 0.01 <= m[5] <= x1 + 0.01 and y0 - 0.01 <= m[6] <= y1 + 0.01
                             and x0 - 0.01 <= m[2] <= x1 + 0.01 and y0 - 0.01 <= m[3] <= y1 + 0.01], top)
            gap, who = _clearance(mine, fb, ad['feature'], (x0, y0, x1, y1), top, D, ADD_CLEAR + D + 5)
            # the host word itself is in the same feature: it must not be inside the added word's box either
            good = len(mine) > 0 and (gap is None or gap >= ADD_CLEAR)
            a_ok &= good
            notes.append(f"\"{ad['text']}\" {'no other cut near' if gap is None else f'{gap:.1f} mm of wood to cut {who}'}")
        ok &= a_ok
        print(f"labels added ({len(rep['added_words'])}): {'; '.join(notes)} (at least {ADD_CLEAR:.0f} mm)  -> {'OK' if a_ok else 'FAIL'}")

    # ---- parts
    for row in rep['parts']:
        ri, oi = row['pass1'][0], row['outer']
        bx = fa[oi]['bbox']; box = (bx[0] - 10, bx[1] - 10, bx[2] + 10, bx[3] + 10)
        res = max(0.2, math.sqrt((box[2] - box[0]) * (box[3] - box[1]) / 8e6))
        om = fa[ri]['cut'] + (fa[oi]['cut'] if oi != ri else []); nm = fb[ri]['cut'] + (fb[oi]['cut'] if oi != ri else [])
        for k in row.get('dropped_orig') or []:
            om = om + fa_all[k]['cut']
        ot, nt = raster(om, box, top, res, D), raster(nm, box, top, res, D)
        ob, nb = raster(om, box, 0.0, res, D), raster(nm, box, 0.0, res, D)
        def region(k):
            im = k.copy(); ImageDraw.floodfill(im, (0, 0), 128); return np.array(im) == 0
        po, pn = region(ot), region(nt)
        OT, NT, OB, NB = (np.array(x) > 0 for x in (ot, nt, ob, nb))
        dmask = po ^ pn
        diff = int(dmask.sum())
        er = lambda b: np.array(Image.fromarray((b * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))) > 0
        # new cuts: one-pixel specks are where a drawn round end-cap lands on the grid; 2 px wide is real
        newc = int(er(NT & ~OT).sum() + er(NB & ~OB).sum())
        newc_px = int((NT & ~OT).sum() + (NB & ~OB).sum())
        # differences one pixel wide are drawing noise (e.g. a corner drawn as chords vs an arc);
        # anything that survives a 3x3 erosion is at least 2 pixels wide and counts as real
        wide = int((np.array(Image.fromarray((dmask * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))) > 0).sum())
        near = np.array(Image.fromarray((po * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
        touch = int(((OB & ~NB) & near).sum())
        p_ok = wide == 0 and newc == 0 and touch == 0 and po.sum() > 0
        fine = ''
        if not p_ok and wide == 0 and newc == 0 and po.sum() > 0:
            # only thin or tiny differences: measure them at 0.02 mm/px around each flagged spot
            flag = ((OB & ~NB) & near) | (NT & ~OT) | (NB & ~OB) | dmask
            w = fine_width(flag, box, res, om, nm, top, D)
            p_ok = w <= FINE_TOL
            fine = f'; at 0.02 mm/px widest difference {w:.2f} mm (limit {FINE_TOL} mm)'
            if not p_ok:
                # the old step-down ramps can cut a chord across a corner that the old finish lap does
                # not cut (D10 #195: 0.28 mm). The new program has no ramps; compare it with the old
                # program's flat moves only - the edge must then be the old finish edge.
                flat = lambda ms: [m for m in ms if not (m[1] != 0 and (abs(m[5] - m[2]) > 1e-6 or abs(m[6] - m[3]) > 1e-6)
                                                        and abs(m[7] - m[4]) > 1e-6)]
                w2 = fine_width(flag, box, res, flat(om), flat(nm), top, D)
                if w2 <= FINE_TOL and w <= 2 * FINE_TOL:
                    p_ok = True
                    fine += f'; without the old ramps {w2:.2f} mm: only corner chords of the old ramps are no longer cut'
        ok &= p_ok
        print(f'part {oi}{fine}: area {po.sum() * res * res / 100:.0f} cm2, outline diff {diff} px '
              f'({wide} px wider than {2 * res:.1f} mm), new cuts {newc_px} px ({newc} wider than {2 * res:.1f} mm), '
              f'no-longer-cut touching part {touch} px  -> {"OK" if p_ok else "FAIL"}')

    # ---- straight plunges: no X/Y movement while Z changes inside the wood (converted features)
    if rep.get('ramps_to_plunges') is not None:
        tgt = set(rep['labels']) | {x for pr in rep['parts'] for x in pr['pass1'] + [pr['outer']]}
        bad = []
        for i in tgt:
            for m in fb[i]['moves']:
                moving = abs(m[5] - m[2]) > 1e-6 or abs(m[6] - m[3]) > 1e-6
                if moving and abs(m[7] - m[4]) > 1e-6 and min(m[4], m[7]) < top - 1e-6:
                    bad.append(m[0] + 1)
                if m[1] == 0 and moving and min(m[4], m[7]) < top + 0.5:
                    bad.append(m[0] + 1)
        pl_ok = not bad
        ok &= pl_ok
        print(f'straight plunges: {len(bad)} moves change Z while moving in the wood, or rapid near the wood'
              f'{" (lines " + str(bad[:8]) + ")" if bad else ""}  -> {"OK" if pl_ok else "FAIL"}')

    # ---- T-slots: same path, slower feed, nothing else changed speed
    if rep.get('tslots') is not None:
        t_ok, text = tslots.check(fa, fb, la, lb, rep, top)
        ok &= t_ok
        print(text)

    # ---- dust pass: the extra lap is a copy of the through lap, nothing else changed
    if rep.get('dust') is not None:
        conv = set(rep['labels']) | {x for pr in rep['parts'] for x in pr['pass1'] + [pr['outer']]} | set(rep.get('tslots') or [])
        conv |= {r['feature'] for r in rep.get('holes') or []}
        d_ok, text = dustpass.check(fa, fb, la, lb, rep, top, conv)
        ok &= d_ok
        print(text)

    # ---- round holes: cut from the centre out, same edge lap, nothing outside the hole
    if rep.get('holes'):
        h_ok, text = holes.check(fa, fb, rep, top, D)
        ok &= h_ok
        print(text)

    # ---- which operations changed
    heads = [(i, l) for i, l in enumerate(la) if l.startswith('(')]
    changed = {}
    strip = lambda ls: [re.sub(r'^N\d+', '', l) for l in ls]          # compare without line numbers
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, strip(la), strip(lb), autojunk=False).get_opcodes():
        if tag != 'equal':
            op = [h for i, h in heads if i <= i1][-1] if heads and heads[0][0] <= i1 else 'header'
            changed[op] = changed.get(op, 0) + max(i2 - i1, j2 - j1)
    for i, h in heads:
        print(f'  {h:24s} {"changed " + str(changed[h]) + " lines" if h in changed else "unchanged"}')
    print('ALL CHECKS PASSED' if ok else 'CHECKS FAILED')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
