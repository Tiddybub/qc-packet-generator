#!/usr/bin/env python3
"""Set the depth of the labels or the sheet badge in a finished program, nothing else.

User (2026-11-23): "the badges aren't coming out correct. We might have to cut the badge a little
bit deeper. Cut the badges at like 0.25."

Every cut whose deepest point is FROM below the real top (the badge: 0.20 in since V10) is moved
down by (TO - FROM): every Z of that cut that is below the real top moves by the same amount, so
the plunge that slows down 0.5 mm above depth still slows down 0.5 mm above the new depth. X/Y,
feeds and every other line stay exactly as they were.

    python3 -I labeldepth.py IN.MMG OUT.MMG --stock-in 0.5 --from-in 0.20 --to-in 0.25
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gcode

IN = 25.4
ZW = re.compile(r'Z(-?\d+\.?\d*)')
NW = re.compile(r'^N\d+')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--stock-in', type=float, required=True)
    ap.add_argument('--from-in', type=float, required=True)
    ap.add_argument('--to-in', type=float, required=True)
    a = ap.parse_args()
    top = a.stock_in * IN
    zf, dz = top - a.from_in * IN, (a.to_in - a.from_in) * IN
    lines = gcode.read_lines(a.src)
    feats, _ = gcode.parse(lines)
    hit = [f for f in feats if abs(f['zmin'] - zf) < 0.002]
    if not hit:
        sys.exit(f'labeldepth: no cut is {a.from_in} in deep - nothing written')
    out = list(lines)
    for f in hit:
        for k in range(f['start'], f['end'] + 1):
            m = ZW.search(out[k])
            if m and float(m.group(1)) < top - 1e-6:
                out[k] = gcode.set_z(out[k], float(m.group(1)) - dz)
    gcode.write_lines(a.dst, out)
    # check: only Z words of those cuts changed; same X/Y path; new deepest = TO
    fb, _ = gcode.parse(gcode.read_lines(a.dst))
    bad = []
    if len(fb) != len(feats):
        bad.append('feature count changed')
    ids = {f['id'] for f in hit}
    for A, B in zip(feats, fb):
        if A['id'] not in ids:
            if [NW.sub('', lines[k]) for k in range(A['start'], A['end'] + 1)] != [NW.sub('', out[k]) for k in range(B['start'], B['end'] + 1)]:
                bad.append(f'cut {A["id"]} changed')
            continue
        xy = lambda F: [(m[1], round(m[2], 3), round(m[3], 3), round(m[5], 3), round(m[6], 3), m[8], m[9]) for m in F['cut']]
        if xy(A) != xy(B):
            bad.append(f'cut {A["id"]} path changed')
        if abs(B['zmin'] - (top - a.to_in * IN)) > 0.002:
            bad.append(f'cut {A["id"]} deepest Z{B["zmin"]:.3f}')
    print(f'labeldepth: {len(hit)} cut(s) from {a.from_in} in to {a.to_in} in deep; '
          f'{"OK" if not bad else "FAIL " + str(bad[:5])}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
