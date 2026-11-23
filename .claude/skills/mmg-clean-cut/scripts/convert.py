#!/usr/bin/env python3
"""Clean-cut conversion for a compression bit.

  labels : one bit-wide line, one pass at --label-depth-in (default 0.21 in) below the real stock top.
           Words read with labelwords.py (--label-text) are written again in the straight-line font
           (blockfont.py): 27.7 mm letters (--label-scale 1.15), no curves, same spot and direction.
           Other labels are traced along the middle of the old letter (singleline.py).
           Every stroke runs at --label-feed-pct (52.5 %) of the programmed label feed, plunges fast to
           --label-slow-mm (0.5 mm) above depth and feeds the rest at 1/10 of the plunge feed.
  badge  : --badge-text D1RB: the sheet name in the same font inside a box with clipped corners,
           centred where the old badge ring was, --badge-depth-in (default 0.25 in) deep; the box
           runs at --badge-box-feed-pct (35 %).
           (--pocket-labels: the old pocketed letters; --label-font hershey: the curved font and ring of V1-V3.)
  parts  : outline in two passes. Pass 1 = the roughing lap (same path as the finish lap) at
           --part-pass1 (default: halfway through). Pass 2 = the finish lap through, unchanged.
           An extra outer-cut lap that runs outside the part (returns to the ramp-end point
           before the finish lap) is removed. Tabs keep the thickness the old program really
           left (old roughing floor) unless --programmed-tabs.
  plunges: in every converted feature the bit plunges straight down to cutting depth, then moves
           (ramp-ins become a rapid above the wood + straight plunge; ramp-outs become straight lifts).
  T-slots: the clover-headed joint pockets are cut slower (--tslot-feed, default 3810 mm/min =
           150 ipm; plunge --tslot-plunge-feed, default 1270 = 50 ipm). Only their F words change:
           same path, same depth, still one pass. See tslots.py.
  dust   : after each part's through lap the bit traces that lap once more at full depth, lifting
           over the tabs, to sweep the sawdust out of the kerf (--dust-feed, default 10160 mm/min =
           400 ipm; it cuts no wood). Part outlines only. --dust-laps N for more than one
           (foam gets 2). See dustpass.py.
  holes  : a round through-hole that the CAM cuts as one lap round its edge (which frees a plug)
           is cut from the centre outwards instead; its edge lap is kept as is. See holes.py.

Usage: python3 convert.py IN.MMG OUT.MMG [--stock-in 0.71] [--label-depth-in 0.21] [--badge-depth-in 0.25]
           [--label-text WORDS.json] [--badge-text D1RB] [--label-feed-pct 52.5] [--badge-box-feed-pct 35] [--label-scale 1.15]
           [--extra-labels 103,104] [--not-labels 7,8] [--part-pass1 half|<in>]
           [--no-labels] [--no-parts] [--programmed-tabs] [--keep-ramps] [--plunge-feed 5080]
           [--tslot-feed 3810] [--tslot-plunge-feed 1270] [--extra-tslots 36,48] [--not-tslots 7]
           [--no-tslots] [--dust-feed 10160] [--no-dust-pass]
           [--dust-laps 1] [--no-hole-fix] [--hole-max-in 3] [--hole-plunge-feed MM/MIN]
           [--foam]   foam sheets: holes from the centre out and 2 dust laps, nothing else
                      (0.5 in foam, no tabs, simple cuts)
Writes OUT.MMG and OUT.MMG.json (what was changed; used by verify.py).
"""
import argparse, bisect, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math
from gcode import read_lines, write_lines, parse, floors, program_top, set_z, ZWORD, move_pts, move_len
from analyze import classify
import noramp
import parts
import tslots
import dustpass
import holes
import verify
import singleline
import fontlabels
import blockfont
from PIL import ImageChops

IN = 25.4


def ids(s):
    return {int(x) for x in s.split(',') if x.strip()} if s else set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--stock-in', type=float, default=None, help='real thickness in inches; default 0.71, or 0.5 with --foam')
    ap.add_argument('--foam', action='store_true', help='foam sheet: add the dust lap only; labels, passes, plunges and T-slots are left exactly as programmed')
    ap.add_argument('--label-depth-in', type=float, default=0.21)    # user 2026-11-23: deeper than the bit's 0.2 in up-cut tip (0.18 from 2026-11-20, 0.165 before)
    ap.add_argument('--pocket-labels', action='store_true', help='cut labels as pockets like the CAM did (old rule) instead of one bit-wide line')
    ap.add_argument('--label-text', default=None, help='JSON list of label words [{"ids": [...], "text": "DCM", "rot": 0, "box": [x0, y0, x1, y1]}] '
                    '(labelwords.py): each word is written again in the single-line font (fontlabels.py)')
    ap.add_argument('--badge-text', default=None, help='write this text in the sheet badge instead of the old text, e.g. D1RB')
    ap.add_argument('--add-label', action='append', default=[], metavar='TEXT@X,Y,ROT',
                    help='a label the drawing shows but the CAM file does not have: TEXT centred at X,Y mm, turned ROT degrees '
                         '(0 = reads left to right, 90 = reads bottom to top). Only when the user gives the text and the spot. Can be repeated')
    ap.add_argument('--label-font', choices=['block', 'hershey'], default='block',
                    help='block (default): the straight-line font, 24 mm letters, badge in a box (blockfont.py, user V4-V17). '
                         'hershey: the older curved font with the badge ring (files up to ClaudeV3)')
    ap.add_argument('--label-scale', type=float, default=1.15, help='label words this many times the 24 mm grid size: 1.15 = 27.7 mm letters, '
                    'the standard since the closet test cut clean (user 2026-11-23). The badge stays 24 mm')
    ap.add_argument('--badge-depth-in', type=float, default=0.25)    # user 2026-11-23: "Cut the badges at like 0.25" (was 0.20, before that the label depth)
    ap.add_argument('--label-feed-pct', type=float, default=52.5, help='labels and badge letters: percent of the programmed label feed (52.5 = 210 ipm on a 400 ipm program, 331 on a 630 ipm one; was 75 until 2026-11-23)')
    ap.add_argument('--badge-box-feed-pct', type=float, default=35.0, help='the badge box: percent of the programmed label feed (35 = 140 / 220 ipm; was 50 until 2026-11-23)')
    ap.add_argument('--label-slow-mm', type=float, default=0.5, help='each stroke: the last this-many mm of the plunge and the first of the lift run at 1/10 of the plunge feed; 0 = off')
    ap.add_argument('--tool-mm', type=float, default=6.0, help='bit diameter (mm)')
    ap.add_argument('--extra-labels', default='')
    ap.add_argument('--not-labels', default='')
    ap.add_argument('--part-pass1', default='half')
    ap.add_argument('--no-labels', action='store_true')
    ap.add_argument('--no-parts', action='store_true')
    ap.add_argument('--programmed-tabs', action='store_true')
    ap.add_argument('--keep-ramps', action='store_true', help='keep ramp entries instead of straight plunges')
    ap.add_argument('--plunge-feed', default=None, help='feed (mm/min) for straight plunges; default = the program plunge feed')
    ap.add_argument('--tslot-feed', type=float, default=tslots.DEFAULT_FEED, help='feed (mm/min) for T-slots in the wood; 3810 = 150 ipm')
    ap.add_argument('--tslot-plunge-feed', type=float, default=tslots.DEFAULT_PLUNGE, help='feed (mm/min) for T-slot plunges; 1270 = 50 ipm')
    ap.add_argument('--extra-tslots', default='')
    ap.add_argument('--not-tslots', default='')
    ap.add_argument('--no-tslots', action='store_true', help='leave T-slots at the program feed')
    ap.add_argument('--dust-feed', type=float, default=dustpass.DEFAULT_FEED, help='feed (mm/min) for the extra dust lap round each part; 10160 = 400 ipm')
    ap.add_argument('--no-dust-pass', action='store_true', help='no extra lap round the parts')
    ap.add_argument('--dust-laps', type=int, default=None, help='how many extra laps round each part; default 1, or 2 with --foam')
    ap.add_argument('--no-hole-fix', action='store_true', help='leave round through-holes as the CAM cut them (they free a plug)')
    ap.add_argument('--hole-max-in', type=float, default=3.0, help='biggest round hole (inches across) that is cut from the centre out')
    ap.add_argument('--hole-plunge-feed', type=float, default=None, help='feed (mm/min) for the plunge at a hole centre; default 1270 in wood, the lap feed in foam')
    a = ap.parse_args()
    if a.foam:
        # user rule 2026-11-19: foam is 0.5 in, has no tabs and is cut simply - only the dust lap is added
        a.no_labels = a.no_parts = a.keep_ramps = a.no_tslots = True
    if a.stock_in is None:
        a.stock_in = 0.5 if a.foam else 0.71
    if a.dust_laps is None:
        a.dust_laps = 2 if a.foam else 1

    lines = read_lines(a.src)
    feats, _ = parse(lines)
    ptop = program_top(lines)
    classify(feats, ptop)
    top = a.stock_in * IN
    z_label = round(top - a.label_depth_in * IN, 3)
    z_badge = round(top - a.badge_depth_in * IN, 3)
    edits, drop = {}, set()
    report = {'stock_in': a.stock_in, 'label_z': z_label, 'program_top': ptop, 'labels': [], 'parts': []}

    def remap_fn(moves, fn):
        for m in moves:
            line = edits.get(m[0], lines[m[0]])
            mz = ZWORD.search(line)
            if mz:
                z = float(mz.group(1)); z2 = fn(z)
                if abs(z2 - z) > 1e-9:
                    edits[m[0]] = set_z(line, z2)

    def remap(moves, A, old, new):
        k = (A - new) / (A - old)
        for m in moves:
            line = edits.get(m[0], lines[m[0]])
            mz = ZWORD.search(line)
            if not mz:
                continue
            z = float(mz.group(1))
            if z < A - 1e-9:
                edits[m[0]] = set_z(line, A - (A - z) * k)

    inserts = {}
    # ---------------- labels
    report['label_mode'] = 'pocket' if a.pocket_labels else 'single-line'
    report['label_style'] = {'font': a.label_font, 'feed_pct': a.label_feed_pct, 'box_feed_pct': a.badge_box_feed_pct,
                             'slow_mm': a.label_slow_mm, 'badge_z': z_badge}
    report['badge_removed'] = []
    report['word_removed'] = []
    report['words'] = []
    words = {}
    for w in (json.load(open(a.label_text)) if a.label_text else []):
        for i in w['ids']:
            words[i] = w
    if not a.no_labels:
        excl = ids(a.not_labels)
        badge = None if a.pocket_labels else singleline.find_badge(feats)
        if a.badge_text and not badge:
            raise SystemExit('--badge-text: no badge ring found on this sheet - nothing written')
        extra = ids(a.extra_labels) | (({badge['ring']} | set(badge['letters']) | set(badge['parts'])) - excl if badge else set())
        chosen = [f for f in feats if (f['kind'] == 'label' or f['id'] in extra) and f['id'] not in excl]
        if badge:
            report['badge'] = {'feature': badge['ring'], 'old': [badge['ring']] + badge['parts'] + badge['letters'],
                               'r_in_edge': round(badge['r_in'] - a.tool_mm / 2, 3), 'text': a.badge_text, 'cx': round(badge['cx'], 3),
                               'cy': round(badge['cy'], 3), 'r_edge': round(badge['r_out'] + a.tool_mm / 2, 3)}
        for f in chosen:
            if not a.pocket_labels:
                # ---- one bit-wide line along the middle of each letter (singleline.py)
                if badge and (f['id'] in badge['parts'] or (a.badge_text and f['id'] in badge['letters'])):
                    for ln in range(f['start'], f['end'] + 1):
                        if not lines[ln].startswith('('):
                            drop.add(ln)
                    report['badge_removed'].append(f['id'])
                    print(f'label {f["id"]:3d}: ' + ('piece of the badge ring' if f['id'] in badge['parts'] else 'old badge text')
                          + ', removed (cut with the ring now)')
                    continue
                w = words.get(f['id'])
                if w and f['id'] != min(w['ids']):
                    for ln in range(f['start'], f['end'] + 1):
                        if not lines[ln].startswith('('):
                            drop.add(ln)
                    report['word_removed'].append(f['id'])
                    print(f'label {f["id"]:3d}: part of the word "{w["text"]}", removed (the word is cut with feature {min(w["ids"])})')
                    continue
                z_this, spct = z_label, None
                if w and a.label_font == 'block':
                    strokes, cap = blockfont.in_box(w['text'], tuple(w['box']), w['rot'], a.tool_mm, a.label_scale)
                    note = f'"{w["text"]}" in the straight-line font, {cap:.1f} mm tall, turned {w["rot"]} deg'
                    if cap < blockfont.CAP * blockfont.UNIT * a.label_scale - 0.01:
                        note += f' - SMALLER than the {blockfont.CAP * blockfont.UNIT * a.label_scale:.1f} mm asked for, to fit the old word: tell the user'
                    if cap < blockfont.CAP * blockfont.UNIT - 0.01:
                        note += ' - SMALLER than 24 mm: less than 6 mm of wood between cuts, tell the user'
                    if blockfont.not_cut_yet(w['text']):
                        note += f' - letter(s) {" ".join(blockfont.not_cut_yet(w["text"]))} have never been cut in this font: look at the preview, tell the user'
                    report['words'].append({'feature': f['id'], 'old': sorted(w['ids']), 'box': w['box'], 'text': w['text']})
                elif w:
                    pts, cap = fontlabels.in_box(w['text'], tuple(w['box']), w['rot'], a.tool_mm)
                    strokes = [fontlabels.to_moves(s, cap / fontlabels.CAP_UNITS) for s in pts]
                    note = f'"{w["text"]}" in the single-line font, {cap / IN:.2f} in tall, turned {w["rot"]} deg'
                    report['words'].append({'feature': f['id'], 'old': sorted(w['ids']), 'box': w['box'], 'text': w['text']})
                elif badge and f['id'] == badge['ring'] and a.badge_text and a.label_font == 'block':
                    # the sheet name in a box with clipped corners, centred where the old ring was (user, V4)
                    letters, boxst, ext = blockfont.badge(a.badge_text, badge['cx'], badge['cy'])
                    strokes = letters + [boxst]
                    spct = [None] * len(letters) + [a.badge_box_feed_pct]
                    z_this = z_badge
                    report['badge'].update({'style': 'box', 'z': z_badge, 'box': [round(v, 3) for v in ext]})
                    note = (f'badge "{a.badge_text.upper()}" in the straight-line font inside a box '
                            f'{(ext[2] - ext[0]):.0f} x {(ext[3] - ext[1]):.0f} mm, {a.badge_depth_in} in deep; box at {a.badge_box_feed_pct:.0f} % feed')
                    if blockfont.not_cut_yet(a.badge_text):
                        note += f' - letter(s) {" ".join(blockfont.not_cut_yet(a.badge_text))} have never been cut in this font: tell the user'
                elif badge and f['id'] == badge['ring']:
                    rm = (badge['r_in'] + badge['r_out']) / 2
                    strokes = [fontlabels.full_circle(badge['cx'], badge['cy'], rm)] if badge['complete'] else singleline.ring(badge, top, a.tool_mm)
                    note = 'badge ring as one line'
                    if a.label_font == 'block':
                        note += ' (no --badge-text: give the sheet name to get the box badge)'
                    if a.badge_text:
                        pts, cap = fontlabels.in_circle(a.badge_text.upper(), badge['cx'], badge['cy'], rm - a.tool_mm / 2 - singleline.RING_GAP, a.tool_mm)
                        strokes += [fontlabels.to_moves(s, cap / fontlabels.CAP_UNITS) for s in pts]
                        note += f' + "{a.badge_text.upper()}" in the single-line font, {cap / IN:.2f} in tall'
                else:
                    strokes, note = singleline.centerline(f, top, a.tool_mm)
                if strokes:
                    for ln in range(f['start'], f['end'] + 1):
                        if not lines[ln].startswith('('):
                            drop.add(ln)
                    inserts.setdefault(f['start'], []).extend(
                        singleline.emit(lines, f, strokes, top, z_this, a.plunge_feed, a.label_feed_pct, a.label_slow_mm, spct))
                    report['labels'].append(f['id'])
                    print(f'label {f["id"]:3d}: one bit-wide line at Z{z_this}; {note}')
                    continue
                print(f'label {f["id"]:3d}: {note} - cut as a pocket instead')
            fl = floors(f, ptop)
            if not fl:
                print(f'label {f["id"]}: no cutting depth found, skipped'); continue
            first, A = fl[0], f['plunge']
            if A <= first:
                print(f'label {f["id"]}: plunge height {A} not above floor {first}, skipped'); continue
            mv = f['cut']
            cut = next((i for i, m in enumerate(mv) if min(m[4], m[7]) < first - 1e-6), len(mv))
            for m in mv[cut:]:
                drop.add(m[0])
            keepm = mv[:cut]
            # Preferred: stretch the ramp from its plunge height (gentle). That can push a stretch of
            # ramp that ran through air (the CAM assumed thicker stock) into the real wood. If that would
            # cut anything outside the label's old outline, stretch only what was already in the wood.
            kA = (A - z_label) / (A - first)
            fA = lambda z: z if z >= A - 1e-9 else A - (A - z) * kA
            mode = 'ramp from plunge height'
            if A > top:
                kT = (top - z_label) / (top - first)
                fT = lambda z: z if z >= top - 1e-9 else top - (top - z) * kT
                newA = [m[:4] + (fA(m[4]),) + m[5:7] + (fA(m[7]),) + m[8:] for m in keepm]
                bx = f['bbox']; box = (bx[0] - 6, bx[1] - 6, bx[2] + 6, bx[3] + 6)
                old_s = verify.raster(mv, box, top, 0.05, 6.0)
                new_s = verify.raster(newA, box, top, 0.05, 6.0)
                extra = ImageChops.subtract(new_s, old_s).histogram()[255] * 0.0025
                if extra > 0.05:
                    remap_fn(keepm, fT)
                    mode = f'in-wood part of the ramp only ({extra:.2f} mm2 would have been new)'
                else:
                    remap_fn(keepm, fA)
            else:
                remap(keepm, A, first, z_label)
            report['labels'].append(f['id'])
            print(f'label {f["id"]:3d}: floor Z{first} -> Z{z_label}'
                  + (f', removed {len(mv) - cut} deeper step-down moves' if cut < len(mv) else '')
                  + ('' if mode == 'ramp from plunge height' else f'; {mode}'))

    # ---------------- labels the CAM file does not have (user, V5/V6: "D2 second DCM", "D3 DAE")
    report['added_words'] = []
    if a.add_label and not a.no_labels:
        fw = {wd['feature'] for wd in report['words']}
        host = next((f for f in feats if f['id'] in fw), None)
        if host is None:
            raise SystemExit('--add-label: the new word is cut together with a --label-text word, and this sheet has none - nothing written')
        for spec in a.add_label:
            try:
                text, pos = spec.rsplit('@', 1); ax, ay, arot = (float(v) for v in pos.split(','))
            except ValueError:
                raise SystemExit(f'--add-label {spec!r}: write it as TEXT@X,Y,ROT, e.g. DCM@214,2287,90')
            st = blockfont.at(text, ax, ay, arot)
            ex = blockfont._ext(st); r = a.tool_mm / 2
            inserts[host['start']].extend(
                singleline.emit(lines, host, st, top, z_label, a.plunge_feed, a.label_feed_pct, a.label_slow_mm))
            report['added_words'].append({'feature': host['id'], 'text': text.upper(), 'rot': arot,
                                          'box': [round(ex[0] - r, 3), round(ex[1] - r, 3), round(ex[2] + r, 3), round(ex[3] + r, 3)]})
            print(f'label added: "{text.upper()}" centred at X{ax:g} Y{ay:g}, turned {arot:g} deg, cut with feature {host["id"]}'
                  + (f' - letter(s) {" ".join(blockfont.not_cut_yet(text))} have never been cut in this font: tell the user' if blockfont.not_cut_yet(text) else ''))

    # ---------------- parts
    if not a.no_parts:
        report['parts'] = parts.convert_parts(feats, lines, ptop, top, a.part_pass1, a.programmed_tabs,
                                              edits, drop, inserts, print, a.plunge_feed)

    out = []
    for i, l in enumerate(lines):
        if i not in drop:
            out.append(edits.get(i, l))
        out.extend(inserts.get(i, []))

    # A feature that was removed whole (an in-between depth step of a part) makes every later
    # feature move up one. From here on the report and all ids are in the NEW numbering.
    removed = sorted({i for r in report['parts'] for i in r.get('dropped', [])} | set(report['badge_removed']) | set(report['word_removed']))
    nid = lambda i: i - bisect.bisect_left(removed, i)
    for r in report['parts']:
        r['dropped_orig'] = r.pop('dropped', [])
    if removed:
        report['removed_features'] = removed
        report['labels'] = [nid(i) for i in report['labels'] if i not in removed]
        if report.get('badge'):
            report['badge']['feature'] = nid(report['badge']['feature'])
        for wd in report['words'] + report['added_words']:
            wd['feature'] = nid(wd['feature'])
        for r in report['parts']:
            r['ids_orig'] = r['ids']
            r['ids'] = [nid(i) for i in r['ids'] if i not in removed]
            r['pass1'] = [nid(i) for i in r['pass1']]
            r['outer'] = nid(r['outer'])
        print(f'features {removed} removed whole; later feature ids move up')

    # ---------------- straight plunges: no X/Y movement while Z changes in the converted features
    if not a.keep_ramps:
        targets = sorted(set(report['labels']) | {x for p in report['parts'] for x in p['pass1'] + [p['outer']]})
        out, n_in, n_out, warns = noramp.apply(out, targets, top, a.plunge_feed, labels=set(report['labels']))
        for w in warns:
            print('  note:', w)
        report['ramps_to_plunges'] = n_in; report['ramp_outs_to_lifts'] = n_out
        report['plunge_feed'] = a.plunge_feed or 'program plunge feed'
        print(f'straight plunges: {n_in} ramp-ins replaced, {n_out} ramp-outs replaced')
    # ---------------- T-slots: slower feed, nothing else (after the steps above, so line ids are final)
    if not a.no_tslots:
        ts = [nid(i) for i in tslots.find(feats, ptop, ids(a.extra_tslots), ids(a.not_tslots)) if i not in removed]
        out, lowered = tslots.apply(out, ts, top, a.tslot_feed, a.tslot_plunge_feed)
        report['tslots'] = ts; report['tslot_feed'] = a.tslot_feed; report['tslot_plunge_feed'] = a.tslot_plunge_feed
        print(f'T-slots: {len(ts)} slowed to F{a.tslot_feed:.0f} ({a.tslot_feed / IN:.0f} ipm), '
              f'plunge F{a.tslot_plunge_feed:.0f} ({a.tslot_plunge_feed / IN:.0f} ipm); '
              f'{lowered} lines, path and depth unchanged' + (f'; ids {ts}' if ts else ''))
    # ---------------- round through-holes: from the centre outwards, so no plug comes loose
    hole_ids = set()
    if not a.no_hole_fix:
        out, hrows = holes.apply(out, top, max_dia=a.hole_max_in * IN, two_levels=not a.foam,
                                 plunge_feed=a.hole_plunge_feed, say=print)
        report['holes'] = hrows
        hole_ids = {r['feature'] for r in hrows}
        print(f'round holes: {len(hrows)} cut from the centre out')
    # ---------------- dust pass: trace each part's through lap once more (last, so nothing above sees it)
    if not a.no_dust_pass:
        out, rows, _ = dustpass.apply(out, a.dust_feed, print, laps=a.dust_laps, skip=hole_ids)
        report['dust'] = rows; report['dust_feed'] = a.dust_feed
        print(f'dust pass: {len(rows)} parts get {a.dust_laps} extra lap{"s" if a.dust_laps > 1 else ""} at F{a.dust_feed:.0f} ({a.dust_feed / IN:.0f} ipm), '
              f'{sum(r["length_mm"] for r in rows) / 1000:.1f} m in all')
    # ---------------- renumber N10, N20 ... (inserted lines need numbers; removes gaps)
    n = 0
    for k, l in enumerate(out):
        if l and not l.startswith('(') and l != '%':
            n += 10
            out[k] = f'N{n}' + re.sub(r'^N\d+', '', l)
    write_lines(a.dst, out)
    report['lines_removed'] = len(drop); report['lines_edited'] = len(edits)
    report['lines_inserted'] = sum(len(v) for v in inserts.values())
    json.dump(report, open(a.dst + '.json', 'w'), indent=1)
    print(f'wrote {a.dst}: {len(report["labels"])} labels, {len(report["parts"])} parts, '
          f'{len(report.get("tslots", []))} T-slots slowed, {len(report.get("holes", []))} round holes from the centre, {len(report.get("dust", []))} parts with dust laps, '
          f'{len(edits)} lines edited, {len(drop)} lines removed, {report["lines_inserted"]} lines inserted')


if __name__ == '__main__':
    main()
