#!/usr/bin/env python3
"""Read the label words on a sheet, for writing them again in the straight-line font (blockfont.py).

The skill never guesses a part code (README: "a wrong one is worse than a missing one"). Reading
is done by eye on upright crops, then checked by shape:

  1. sheet: group the label letters into words, turn each word upright and save a contact sheet
     (each word upright, and flipped top to bottom next to it - the CAD mirrors left/right parts)
       python3 -I labelwords.py sheet IN.MMG OUT_PREFIX --stock-in 0.71 --ids 82,83,84,...
     -> OUT_PREFIX.png (read it), OUT_PREFIX.json
  2. Read every word on the contact sheet. Glyph traps (qc-generator README): a dogbone next to a
     label is not an I or J; Q has a tail, O does not; G has a longer hook than C; M upside down
     looks like W - compare with an M that is the right way up on the same sheet.
  3. check: render each reading and compare it with the engraved word in all 8 orientations
       python3 -I labelwords.py check IN.MMG OUT_PREFIX --stock-in 0.71 --read "106=DCM 88=CCB ..."
     -> OUT_PREFIX.words.json for convert.py --label-text. Every word must match clearly
     (match about 0.6 or more, and a clear margin over the next orientation unless every letter
     reads the same upside down: B C D E H I K O X). Words of only such letters keep the
     orientation that is not mirrored, so the new text sits exactly like the old one.
     A word that will not match: leave it out of --read; it is then traced like before.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import gcode
import verify

FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
SAME_UPSIDE_DOWN = set('BCDEHIKOX')


def _vis(f, tool):
    b = f['bbox']; r = tool / 2
    return (b[0] - r, b[1] - r, b[2] + r, b[3] + r)


def group(feats, ids, tool):
    boxes = {i: _vis(feats[i], tool) for i in ids}
    parent = {i: i for i in ids}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for a in ids:
        for b in ids:
            if a < b:
                A, B = boxes[a], boxes[b]
                h = max(min(A[2] - A[0], A[3] - A[1]), min(B[2] - B[0], B[3] - B[1]))
                gx = max(0, max(A[0], B[0]) - min(A[2], B[2])); gy = max(0, max(A[1], B[1]) - min(A[3], B[3]))
                if math.hypot(gx, gy) < 0.45 * h:
                    parent[root(a)] = root(b)
    out = {}
    for i in ids:
        out.setdefault(root(i), []).append(i)
    words = []
    for g in out.values():
        U = (min(boxes[i][0] for i in g), min(boxes[i][1] for i in g), max(boxes[i][2] for i in g), max(boxes[i][3] for i in g))
        words.append({'ids': sorted(g), 'box': [round(v, 3) for v in U]})
    return sorted(words, key=lambda w: (w['box'][1], w['box'][0]))


def word_image(feats, w, top, tool, res=0.25):
    U = w['box']; box = (U[0] - 2, U[1] - 2, U[2] + 2, U[3] + 2)
    return verify.raster([m for i in w['ids'] for m in feats[i]['cut']], box, top, res, tool)


_tmpl = {}


def _letter_score(img):
    """best match of a letter image against A-Z / 0-9 (only used to choose which way is up)"""
    best = 0.0
    for ch in CHARS:
        if ch not in _tmpl:
            f = ImageFont.truetype(FONT, 200)
            im = Image.new('L', (260, 260), 0); ImageDraw.Draw(im).text((20, 0), ch, fill=255, font=f)
            _tmpl[ch] = im.crop(im.getbbox())
        t = _tmpl[ch].resize(img.size)
        a = np.array(img) > 127; b = np.array(t) > 127
        best = max(best, (a & b).sum() / max(1, (a | b).sum()))
    return best


def upright_turn(img):
    """how far (degrees, counter-clockwise) the word is turned on the sheet"""
    best = None
    for rot in (0, 90, 180, 270):
        w = img.rotate(-rot, expand=True)
        cols = (np.array(w) > 127).any(axis=0)
        segs, x = [], 0
        while x < len(cols):
            if cols[x]:
                s = x
                while x < len(cols) and cols[x]:
                    x += 1
                segs.append((s, x))
            x += 1
        sc = []
        for s, e in segs:
            sub = w.crop((s, 0, e, w.height)); sub = sub.crop(sub.getbbox())
            if sub.width >= 0.15 * w.height:
                sc.append(_letter_score(sub))
        if sc and (best is None or sum(sc) / len(sc) > best[0]):
            best = (sum(sc) / len(sc), rot)
    return best[1] if best else 0


def cmd_sheet(a, feats, top):
    ids = [int(x) for x in a.ids.split(',') if x]
    words = group(feats, ids, a.tool_mm)
    tiles = []
    fnt = ImageFont.truetype(FONT, 22)
    for w in words:
        img = word_image(feats, w, top, a.tool_mm)
        w['turn'] = upright_turn(img)
        up = img.rotate(-w['turn'], expand=True)
        s = 70 / max(1, up.height); up = up.resize((max(1, int(up.width * s)), 70))
        t = Image.new('RGB', (2 * up.width + 30, 130), 'white')
        t.paste(ImageOps.invert(up).convert('RGB'), (5, 5)); t.paste(ImageOps.invert(ImageOps.flip(up)).convert('RGB'), (up.width + 25, 5))
        ImageDraw.Draw(t).text((5, 95), f"#{min(w['ids'])}   (right: flipped)", fill=(200, 0, 0), font=fnt)
        tiles.append(t)
    cols = 4; rows = (len(tiles) + cols - 1) // cols
    Wt = max(t.width for t in tiles) if tiles else 10
    sheet = Image.new('RGB', (cols * Wt, max(1, rows) * 130), 'white')
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * Wt, (k // cols) * 130))
    sheet.save(a.out + '.png')
    json.dump(words, open(a.out + '.json', 'w'), indent=1)
    print(f'{len(words)} words; contact sheet {a.out}.png - read each word, then run: check --read "#id=TEXT ..."')


def cmd_check(a, feats, top):
    words = json.load(open(a.out + '.json'))
    reading = dict(x.split('=') for x in a.read.split())
    out, fails = [], 0
    for w in words:
        key = str(min(w['ids']))
        if key not in reading:
            print(f'#{key:>4}  not read - stays traced')
            continue
        text = reading[key].upper()
        img = word_image(feats, w, top, a.tool_mm)
        f = ImageFont.truetype(FONT, 160)
        ref = Image.new('L', (200 * len(text) + 100, 260), 0); ImageDraw.Draw(ref).text((20, 20), text, fill=255, font=f)
        ref = ref.crop(ref.getbbox())
        sc = []
        for rot in (0, 90, 180, 270):
            for mir in (False, True):
                up = img.rotate(-rot, expand=True)
                if mir:
                    up = ImageOps.mirror(up)
                up = up.crop(up.getbbox())
                A = np.array(up) > 127; B = np.array(ref.resize(up.size)) > 127
                sc.append(((A & B).sum() / max(1, (A | B).sum()), rot, mir))
        sc.sort(reverse=True)
        (m1, rot, mir), (m2, rot2, mir2) = sc[0], sc[1]
        symmetric = set(text) <= SAME_UPSIDE_DOWN
        if mir and symmetric and m1 - m2 < 0.03 and not mir2:
            rot, mir = rot2, False                    # reads the same upside down: keep the old direction
        good = m1 >= 0.6 and (m1 - m2 >= 0.02 or symmetric)
        fails += not good
        print(f"#{key:>4} {text:6s} turned {rot:3d}  {'MIRRORED on the sheet' if mir else 'normal               '} "
              f"match {m1:.2f}, next {m2:.2f}  {'OK' if good else 'UNSURE - look again, or leave it out'}")
        out.append({'ids': w['ids'], 'text': text, 'rot': rot, 'box': w['box'], 'was_mirrored': mir})
    json.dump(out, open(a.out + '.words.json', 'w'), indent=1)
    print(f'wrote {a.out}.words.json ({len(out)} words){"; " + str(fails) + " UNSURE - fix before converting" if fails else ""}')
    sys.exit(1 if fails else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['sheet', 'check'])
    ap.add_argument('src'); ap.add_argument('out')
    ap.add_argument('--stock-in', type=float, default=0.71)
    ap.add_argument('--tool-mm', type=float, default=6.0)
    ap.add_argument('--ids', default='', help='sheet: the label letter feature ids (the --extra-labels list)')
    ap.add_argument('--read', default='', help='check: "#id=TEXT" for each word, id = the smallest feature id of the word')
    a = ap.parse_args()
    feats, _ = gcode.parse(gcode.read_lines(a.src))
    top = a.stock_in * 25.4
    (cmd_sheet if a.mode == 'sheet' else cmd_check)(a, feats, top)


if __name__ == '__main__':
    main()
