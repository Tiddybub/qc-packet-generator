#!/usr/bin/env python3
"""Give the operations of a program their proper names, so the other scripts can tell them apart.

The converter sorts cuts by the name of the operation they sit under: POCKET (labels, recesses,
T-slots), SLOTS, HOLES, ROUGHING and OUTER CUTS (part outlines). Some exports name every operation
the same (D4: all eight are "OUTER CUTS 2 85 2 6 x"), and then every cut looks like a part outline.

Look at the program first (analyze.py lists every feature with its operation, size and depths),
decide what each operation really is, then:

  python3 relabel.py IN.MMG OUT.MMG --op "OUTER CUTS 2 85 2 6 3=ROUGHING 3" --op "...=POCKET 13" \\
                                    --feature "104-111=SLOTS 4"

  --op "OLD=NEW"       rename an operation comment (OLD must match the whole comment text)
  --feature "IDS=NEW"  put these features (ids from analyze.py, e.g. 3,7,10-14) under NEW; the
                       features after them go back to the operation they were in

Only comment lines are renamed or added. Every other line is kept, in the same order, and the
script checks that before it writes.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gcode import read_lines, write_lines, parse

COMMENT = re.compile(r'^\((.*?)\)\s*$')


def ids(text):
    out = set()
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-')
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--op', action='append', default=[])
    ap.add_argument('--feature', action='append', default=[])
    a = ap.parse_args()
    lines = read_lines(a.src)
    feats, _ = parse(lines)
    rename = dict(x.split('=', 1) for x in a.op)
    seen = {COMMENT.match(l).group(1).strip() for l in lines if COMMENT.match(l)}
    missing = [k for k in rename if k not in seen]
    if missing:
        sys.exit(f'relabel: no operation is named {missing}; the program has {sorted(seen)}')
    override = {}
    for x in a.feature:
        which, name = x.split('=', 1)
        for i in ids(which):
            if not 0 <= i < len(feats):
                sys.exit(f'relabel: there is no feature {i}')
            override[i] = name
    start = {f['start']: f for f in feats}
    out, eff = [], None
    for k, line in enumerate(lines):
        m = COMMENT.match(line)
        if m:
            eff = rename.get(m.group(1).strip(), m.group(1).strip())
            out.append(f'({eff})')
            continue
        f = start.get(k)
        if f is not None:
            want = override.get(f['id'], rename.get(f['op'], f['op']))
            if want != eff:
                out.append(f'({want})'); eff = want
        out.append(line)
    # self-check: nothing but comments changed, and the features are the same cuts
    if [l for l in out if not COMMENT.match(l)] != [l for l in lines if not COMMENT.match(l)]:
        sys.exit('relabel: a cutting line changed - not writing')
    f2, _ = parse(out)
    if len(f2) != len(feats) or any([m[1:] for m in x['moves']] != [m[1:] for m in y['moves']] for x, y in zip(feats, f2)):
        sys.exit('relabel: the features came out different - not writing')
    write_lines(a.dst, out)
    count = {}
    for f in f2:
        count[f['op']] = count.get(f['op'], 0) + 1
    for name, n in count.items():
        print(f'  {name:28s} {n:4d} features')
    print(f'wrote {a.dst}: {len(out) - len(lines)} comment lines added, {len(feats)} features, cutting lines unchanged')


if __name__ == '__main__':
    main()
