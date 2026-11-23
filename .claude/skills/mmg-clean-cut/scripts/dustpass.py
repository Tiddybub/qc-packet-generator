#!/usr/bin/env python3
"""Dust pass: one extra lap round every part outline at full cut depth, to sweep out the kerf.

A compression bit packs sawdust into the slot it cuts. After a part's through lap is finished,
the bit traces that same lap once more: same X/Y, same depth, lifting over the tabs exactly as
the through lap does. It removes no wood, so it runs fast (--dust-feed, default 400 ipm).

  where   : right after the through lap of each part outline, inside the same feature (the bit
            is already down in the kerf; no retract, no new plunge)
  what    : a line-for-line copy of the through lap, so tabs, arcs and direction are identical
  feeds   : sideways moves of the copy run at the dust feed; the lifts and drops at the tabs keep
            the feed they had; nothing outside the copy changes speed
  left out: labels, holes, slots, pockets, T-slots, pass 1. Only part outlines that go through.

A part is left alone (with a note) when its through cut does not end in a closed lap at through
depth, or when that lap is already cut twice.
"""
import math
import re

from gcode import parse, move_len

IN = 25.4
FW = re.compile(r'F(-?\d+\.?\d*)')
GW = re.compile(r'G0?[123](?!\d)')
THRU_MAX = 0.3             # a floor at or below this Z goes through the sheet (same as parts.py)
DEFAULT_FEED = 10160.0     # mm/min = 400 ipm
EPS = 0.002                # mm: two positions closer than this are the same point


def _fmt(v):
    return f'F{v:.1f}'


def _geom(m):
    return (m[1],) + tuple(round(v, 3) for v in m[2:])


def _sideways(m):
    return abs(m[5] - m[2]) > 1e-6 or abs(m[6] - m[3]) > 1e-6


def is_part_through(f):
    op = (f['op'] or '').upper()
    return op.startswith(('OUTER', 'ROUGH')) and f['zmin'] <= THRU_MAX


def find_lap(f):
    """(first, last) indexes into f['moves'] of the closed through lap that ends the feature,
    or (None, reason)."""
    mv = f['moves']
    last = len(mv) - 1
    while last >= 0 and (mv[last][1] == 0 or (not _sideways(mv[last]) and mv[last][7] > mv[last][4])):
        last -= 1                                   # trailing lifts / rapids are not part of the lap
    if last < 1:
        return None, 'no cutting moves'
    end = mv[last][5:8]             # may be on top of a tab: a lap can start and end inside one (I9)
    first = None
    for j in range(last, -1, -1):
        m = mv[j]
        if m[1] == 0:
            return None, 'a rapid interrupts the through lap'
        if _sideways(m) and abs(m[7] - m[4]) > 1e-6:
            return None, 'the through cut ramps; no flat closed lap to repeat'
        if max(abs(m[2] - end[0]), abs(m[3] - end[1]), abs(m[4] - end[2])) <= EPS:
            first = j
            break
    if first is None:
        return None, 'the through lap does not close on itself'
    lap = mv[first:last + 1]
    if min(min(m[4], m[7]) for m in lap) > f['zmin'] + 1e-6:
        return None, 'the closed lap at the end never reaches through depth'
    length = sum(move_len(m) for m in lap)
    x0, y0, x1, y1 = f['bbox']
    if length < 2 * max(x1 - x0, y1 - y0) - 1.0:
        return None, f'closed lap is only {length:.0f} mm long, shorter than the part'
    n = len(lap)
    if first - n >= 0 and [_geom(m) for m in mv[first - n:first]] == [_geom(m) for m in lap]:
        return None, 'the through lap is already cut twice'
    return (first, last), None


def feeds_by_line(lines, feats):
    cutting = {m[0] for f in feats for m in f['moves'] if m[1] != 0}
    out, cur = {}, None
    for k, line in enumerate(lines):
        m = FW.search(line)
        if m:
            cur = float(m.group(1))
        if k in cutting:
            out[k] = cur
    return out


def apply(lines, feed=DEFAULT_FEED, say=print, laps=1, skip=()):
    """Returns (new lines, report rows, original lines that needed a feed word put back). Only inserts lines; no existing line is changed unless a
    feed word has to be put back on the first cutting move after a dust lap."""
    feats, _ = parse(lines)
    eff = feeds_by_line(lines, feats)
    todo, rows = [], []
    for f in feats:
        if not is_part_through(f) or f['id'] in skip:
            continue
        span, why = find_lap(f)
        if span is None:
            say(f'dust pass: part {f["id"]} left as is - {why}')
            continue
        lap = f['moves'][span[0]:span[1] + 1]
        # a copied line only means the same move if it names its own G code
        if not all(GW.search(lines[m[0]]) for m in lap):
            say(f'dust pass: part {f["id"]} left as is - its through lap has lines without a G1/G2/G3 word')
            continue
        todo.append((f, lap))
    out = list(lines)
    want = {}                                       # new line index -> feed for dust-lap lines
    src_of = {}                                     # new line index -> original line index
    shift = 0
    marks = []
    for f, lap in sorted(todo, key=lambda t: t[1][-1][0]):
        at = lap[-1][0] + 1 + shift                 # insert right after the lap's last line
        copies = [FW.sub('', lines[m[0]]) for m in lap] * laps
        out[at:at] = copies
        for i in range(len(copies)):
            m = lap[i % len(lap)]
            want[at + i] = feed if _sideways(m) else eff[m[0]]
        marks.append((f['id'], at, len(copies), sum(move_len(m) for m in lap) * laps, len(lap)))
        shift += len(copies)
    # map every original line to its new index
    pos, ins = 0, sorted((at, n) for _, at, n, _, _ in marks)
    new_index = {}
    k_new = 0
    ins_iter = iter(ins); nxt = next(ins_iter, None)
    for k in range(len(lines)):
        while nxt and k_new == nxt[0]:
            k_new += nxt[1]; nxt = next(ins_iter, None)
        new_index[k] = k_new; k_new += 1
    desired = {new_index[k]: v for k, v in eff.items()}
    desired.update(want)
    # write the feed words: every cutting move ends up at exactly its desired feed
    modal = None
    touched = 0
    for k, line in enumerate(out):
        m = FW.search(line)
        if k in desired and desired[k] is not None:
            d = desired[k]
            if m and float(m.group(1)) == d:
                modal = d
            elif m:
                out[k] = FW.sub(_fmt(d), line); modal = d
                touched += k not in want
            elif modal != d:
                out[k] = line + _fmt(d); modal = d
                touched += k not in want
        elif m:
            modal = float(m.group(1))
    # self-check: every original cutting move still runs at the feed it had
    f2, _ = parse(out)
    eff2 = feeds_by_line(out, f2)
    wrong = [k + 1 for k, v in eff.items() if eff2.get(new_index[k]) != v]
    if wrong:
        raise SystemExit(f'dustpass: a feed changed outside the dust lap at lines {wrong[:8]} - not writing')
    for fid, at, n, length, per in marks:
        rows.append({'feature': fid, 'moves': per, 'laps': laps, 'length_mm': round(length, 1)})
        say(f'dust pass: part {fid}: {laps} extra lap{"s" if laps > 1 else ""}, {length:.0f} mm, {n} lines, at F{feed:.0f} ({feed / IN:.0f} ipm)')
    return out, rows, touched


def check(fa, fb, la, lb, rep, top, converted):
    """verify.py. fa/fb = features of the original / converted program; converted = ids of
    features the converter rewrote (labels, parts, T-slots). Returns (ok, text)."""
    rows = rep.get('dust') or []
    feed = rep.get('dust_feed')
    A, B = feeds_by_line(la, fa), feeds_by_line(lb, fb)
    bad_copy, bad_feed, bad_rest, total = [], [], [], 0.0
    for r in rows:
        i, n, k = r['feature'], r['moves'], r.get('laps', 1)
        mb = fb[i]['moves']
        last = len(mb) - 1
        while last >= 0 and (mb[last][1] == 0 or (not _sideways(mb[last]) and mb[last][7] > mb[last][4])):
            last -= 1
        dust, lap = mb[last - n * k + 1:last + 1], mb[last - n * (k + 1) + 1:last - n * k + 1]
        total += sum(move_len(m) for m in dust)
        if len(dust) != n * k or [_geom(m) for m in dust] != [_geom(m) for m in lap] * k:
            bad_copy.append(i); continue
        for d, l in zip(dust, lap * k):
            f = B[d[0]]
            if _sideways(d):
                if abs(f - feed) > 1e-6: bad_feed.append(d[0] + 1)
            elif f != B[l[0]]:
                bad_feed.append(d[0] + 1)
        if i not in converted:
            # untouched feature: without the dust lap it must be the original, move for move
            rest = mb[:last - n * k + 1] + mb[last + 1:]
            ma = fa[i]['moves']
            if len(rest) != len(ma) or any(_geom(x) != _geom(y) or A.get(x[0]) != B.get(y[0])
                                           for x, y in zip(ma, rest) if x[1] != 0):
                bad_rest.append(i)
    ok = not bad_copy and not bad_feed and not bad_rest
    text = (f'dust pass ({len(rows)} parts, {total / 1000:.1f} m at {feed / IN:.0f} ipm): '
            f'extra lap differs from the through lap in {len(bad_copy)}{" " + str(bad_copy[:8]) if bad_copy else ""}; '
            f'lines at the wrong feed {len(bad_feed)}{" " + str(bad_feed[:8]) if bad_feed else ""}; '
            f'parts changed anywhere else {len(bad_rest)}{" " + str(bad_rest[:8]) if bad_rest else ""}'
            f'  -> {"OK" if ok else "FAIL"}')
    return ok, text
