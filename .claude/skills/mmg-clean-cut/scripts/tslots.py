#!/usr/bin/env python3
"""T-slots: find them and slow them down. Nothing about their shape or depth changes.

A T-slot is the knock-down joint pocket: a channel that runs in from the edge of a part and
ends in a head that looks like a three-leaf clover (I1, both ends of part HCD). The CAM cuts
each one nearly through the sheet in ONE pass at the POCKET op's full feed (400 ipm on most
sheets, 630 ipm on I1), which is too aggressive for a 6 mm bit.

  feed        : every cutting move of a T-slot that is in the wood runs at --tslot-feed
  plunge feed : every straight plunge of a T-slot runs at --tslot-plunge-feed
  a feed is only ever lowered, never raised; moves in the air above the sheet keep their feed
  the feed that was in effect after each T-slot is put back, so nothing else changes speed

Only F words are written. X, Y, Z, I, J and the order of the lines are never touched.
"""
import re

from gcode import parse, move_pts

IN = 25.4
FW = re.compile(r'F(-?\d+\.?\d*)')

MIN_DEPTH = 6.0            # mm below the program top: shallower POCKET features are labels / recesses
HEAD = (12.0, 16.5)        # mm: width across the clover head (bounding box, short side)
LENGTH = (28.0, 41.0)      # mm: channel + head (bounding box, long side)
HEAD_RATIO = 1.8           # the bit path is at least this much wider at the head than in the channel

DEFAULT_FEED = 3810.0      # mm/min = 150 ipm
DEFAULT_PLUNGE = 1270.0    # mm/min =  50 ipm


def is_tslot(f, ptop):
    """ptop = the stock top the program assumes (gcode.program_top)"""
    if not (f['op'] or '').upper().startswith('POCKET') or f.get('kind') == 'label':
        return False
    if ptop - f['zmin'] < MIN_DEPTH:
        return False
    x0, y0, x1, y1 = f['bbox']
    w, h = x1 - x0, y1 - y0
    short, long_ = min(w, h), max(w, h)
    if not (HEAD[0] <= short <= HEAD[1] and LENGTH[0] <= long_ <= LENGTH[1]):
        return False
    # a plain slot is the same width all along; a T-slot is wide at the head, narrow in the channel
    along = 1 if h >= w else 0
    lo = (x0, y0)[along]
    bins = [[] for _ in range(8)]
    for m in f['cut']:
        if min(m[4], m[7]) >= ptop:
            continue
        for p in move_pts(m):
            k = min(7, int((p[along] - lo) / long_ * 8))
            bins[k].append(p[1 - along])
    spans = sorted(max(b) - min(b) for b in bins if b)
    if len(spans) < 5:
        return False
    return spans[-1] >= HEAD_RATIO * max(spans[len(spans) // 2], 0.5)


def find(feats, ptop, extra=(), exclude=()):
    return [f['id'] for f in feats if (is_tslot(f, ptop) or f['id'] in extra) and f['id'] not in exclude]


def feeds_by_line(lines, feats=None):
    """{line index: feed in effect} for every cutting move (G1/G2/G3) of every feature"""
    if feats is None:
        feats, _ = parse(lines)
    cutting = {m[0] for f in feats for m in f['moves'] if m[1] != 0}
    out, cur = {}, None
    for k, line in enumerate(lines):
        m = FW.search(line)
        if m:
            cur = float(m.group(1))
        if k in cutting:
            out[k] = cur
    return out


def _fmt(v):
    return f'F{v:.1f}'


def wanted(m, f_in, top, feed, plunge):
    """feed a T-slot move should run at. m = a gcode.parse move, top = real stock top"""
    z0, z1 = m[4], m[7]
    moving = abs(m[5] - m[2]) > 1e-6 or abs(m[6] - m[3]) > 1e-6
    if min(z0, z1) >= top - 1e-6:
        return f_in                                   # in the air above the sheet
    if not moving:
        if z1 >= z0:
            return f_in                               # straight lift: not cutting
        return plunge if f_in is None else min(f_in, plunge)
    return feed if f_in is None else min(f_in, feed)


def apply(lines, ids, top, feed=DEFAULT_FEED, plunge=DEFAULT_PLUNGE):
    """Returns (new lines, number of T-slot lines whose feed was lowered). Line count is unchanged."""
    feats, _ = parse(lines)
    ts = {m[0]: m for i in ids for m in feats[i]['moves'] if m[1] != 0}
    cutting = {m[0] for f in feats for m in f['moves'] if m[1] != 0}
    before = feeds_by_line(lines, feats)
    out, f_in, f_out, lowered = [], None, None, 0
    for k, line in enumerate(lines):
        m = FW.search(line)
        if m:
            f_in = float(m.group(1))
        if k in ts:
            want = wanted(ts[k], f_in, top, feed, plunge)
            body = FW.sub('', line)
            if want is not None and want != f_out:
                body += _fmt(want); f_out = want
            if want != f_in:
                lowered += 1
            out.append(body)
        else:
            if m:
                f_out = f_in
            elif k in cutting and f_in is not None and f_out != f_in:
                line += _fmt(f_in); f_out = f_in      # put the old feed back after a T-slot
            out.append(line)
    # self-check: outside the T-slots every cutting move runs at exactly the feed it had before
    after = feeds_by_line(out)
    wrong = [k + 1 for k in before if k not in ts and before[k] != after.get(k)]
    if wrong:
        raise SystemExit(f'tslots: feed changed outside a T-slot at lines {wrong[:8]} - not writing')
    return out, lowered


def check(fa, fb, la, lb, rep, top):
    """verify.py: T-slots keep their exact path, run no faster than asked; untouched features keep
    their feeds. fa/fb = parsed features, la/lb = lines (original, converted). Returns (ok, text)."""
    ids = rep.get('tslots') or []
    feed, plunge = rep.get('tslot_feed'), rep.get('tslot_plunge_feed')
    A, B = feeds_by_line(la, fa), feeds_by_line(lb, fb)
    moved, fast, top_cut, top_plunge = [], [], 0.0, 0.0
    for i in ids:
        ma = [m for m in fa[i]['moves'] if m[1] != 0]; mb = [m for m in fb[i]['moves'] if m[1] != 0]
        if len(ma) != len(mb) or any(x[1:] != y[1:] for x, y in zip(ma, mb)):
            moved.append(i); continue
        for m in mb:
            if min(m[4], m[7]) >= top - 1e-6:
                continue
            moving = abs(m[5] - m[2]) > 1e-6 or abs(m[6] - m[3]) > 1e-6
            f = B[m[0]]
            if moving:
                top_cut = max(top_cut, f)
                if f > feed + 1e-6: fast.append(m[0] + 1)
            elif m[7] < m[4]:
                top_plunge = max(top_plunge, f)
                if f > plunge + 1e-6: fast.append(m[0] + 1)
    converted = set(rep['labels']) | {x for p in rep['parts'] for x in p['pass1'] + [p['outer']]} | set(ids)
    converted |= {r['feature'] for r in rep.get('dust') or []}      # dust laps are checked by dustpass.check
    converted |= {r['feature'] for r in rep.get('holes') or []}     # centre-out holes are checked by holes.check
    drift = []
    for i in range(len(fa)):
        if i in converted:
            continue
        ma = [m for m in fa[i]['moves'] if m[1] != 0]; mb = [m for m in fb[i]['moves'] if m[1] != 0]
        if len(ma) != len(mb) or any(A[x[0]] != B[y[0]] for x, y in zip(ma, mb)):
            drift.append(i)
    ok = not moved and not fast and not drift
    text = (f'T-slots ({len(ids)}): path changed in {len(moved)}; fastest cut F{top_cut:.0f} '
            f'({top_cut / IN:.0f} ipm, limit {feed / IN:.0f}), fastest plunge F{top_plunge:.0f} '
            f'({top_plunge / IN:.0f} ipm, limit {plunge / IN:.0f}); lines over the limit {len(fast)}'
            f'{" " + str(fast[:8]) if fast else ""}; other features whose feed changed {len(drift)}'
            f'{" " + str(drift[:8]) if drift else ""}  -> {"OK" if ok else "FAIL"}')
    return ok, text
