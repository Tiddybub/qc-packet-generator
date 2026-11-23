---
name: mmg-clean-cut
description: Fix fuzzy edges on CNC router programs (.MMG / G-code) cut with a compression bit. Labels: one bit-wide line, 0.18 in deep, written in the shop's straight-line font (24 mm letters, no curves, 6 mm of wood between cuts), cut 25 % slower with a slow last 0.5 mm of each plunge. Sheet badge: the sheet name (e.g. D1RB) in a box with clipped corners, 0.25 in deep, box at half feed. Part outlines: exactly three laps - pass 1 at half depth, pass 2 through, then one dust lap at full depth (extra laps the CAM wrote are removed first). Straight plunges instead of ramps, T-slots (the clover-headed joint pockets) at 150 ipm, round through-holes cut from the centre outwards so no loose plug gets sucked into the vacuum, FireGuard (narrow holes, slots and slits cut in depth steps so they do not burn), and a cut simulation that proves no part or label changes shape. Foam sheets get only the hole fix and two dust laps (no tabs, 0.5 in, `--foam`). Use when the user hands over an .MMG file and mentions fuzz, label depth, label font or size, the badge, compression bit, passes, plunging, T-slots, cutting too aggressively, burning or fire, sawdust or debris left in the cut, an extra or cleanup pass, or "do the same as I9".
---

# MMG clean cut

> Normally run through `cnc-sheet-standard` (`scripts/standard.py`), which calls this skill and adds the
> 48 x 96 sheet / zero corner / tabs / label-depth / preview checks.

Rework a CNC program so a **compression bit** leaves clean edges, without changing the shape of
anything. Cutting paths keep their X/Y; Z values change, ramps become straight plunges, an
extra lap outside each part is removed, T-slots are cut at a slower feed, and each part gets one
extra dust lap after its through cut.

**How many times the bit goes round each part: three, in this order.**

1. Pass 1 at half depth.
2. Pass 2 through (the finish lap, as programmed).
3. One dust lap: the through lap traced once more at full depth, 400 ipm. It cuts no wood.

"Extra and repeated laps removed" is about laps the CAM wrote beyond 1 and 2 (a lap outside the
part, a through lap cut twice, in-between depth steps): those go first. The dust lap is the one
repeat the skill then adds on purpose. The two never conflict: CAM repeats out, one dust lap in.
`--no-dust-pass` leaves exactly two laps; foam gets two dust laps.

## Shop defaults (confirm if the user says otherwise)

| Setting | Default | Flag |
|---|---|---|
| Labels | one bit-wide line, same spot and direction (user rule, 2026-11-19) | `--pocket-labels` for the old pocketed letters |
| Label font | the shop's straight-line font (`blockfont.py`): straight lines and 45-degree corners only, no curves. Letters 24 mm (0.95 in) tall, 6 mm of wood between any two cuts. Words are read with `labelwords.py`, never guessed (user, V4 2026-11-21) | `--label-text WORDS.json`; `--label-font hershey` for the curved V1-V3 font |
| Sheet badge | the sheet name in the same font inside a box with clipped corners (no circle), centred where the old badge ring was (user, V4) | `--badge-text D1RB` |
| Real stock thickness | 3/4 in sheets (`*-75in`): 0.71 in (18 mm). 1/2 in sheets (`*-5in`): 0.5 in (user confirmed). Foam: 0.5 in | `--stock-in` |
| Label depth, one pass | 0.18 in (Z13.462 in 0.71 stock; user rule 2026-11-20, was 0.165 in) | `--label-depth-in` |
| Badge depth, one pass | 0.25 in, letters and box (user, 2026-11-23: "Cut the badges at like 0.25"; 0.20 in from V10 to V16) | `--badge-depth-in` |
| Label and badge letter feed | 75 % of the programmed label feed = 300 ipm on 1/2 in sheets, 472 ipm on 3/4 in (user, V11/V12: 25 % slower) | `--label-feed-pct` |
| Badge box feed | 50 % of the programmed label feed = 200 ipm / 315 ipm (user, V10) | `--badge-box-feed-pct` |
| Label and badge plunge | fast to 0.5 mm above depth, the last 0.5 mm at 1/10 of the plunge feed, then cut; the first 0.5 mm of the lift at that slow feed too (user, V9) | `--label-slow-mm` |
| Extra label | a word the drawing shows but the CAM file lacks; only with the text and the spot from the user | `--add-label "DCM@214,2287,90"` |
| Part pass 1 depth | halfway through, so pass 2 isn't too heavy | `--part-pass1 half` or inches |
| Bit | 6 mm compression | `verify.py --tool-mm` |
| Entry | straight plunge to full cutting depth, then move | `--keep-ramps` to keep ramps |
| Plunge feed | the program's own plunge feed (F5080 = 200 ipm in I9) | `--plunge-feed` mm/min |
| T-slot feed | 150 ipm (F3810) in the wood | `--tslot-feed` mm/min |
| T-slot plunge feed | 50 ipm (F1270) | `--tslot-plunge-feed` mm/min |
| Dust pass | one extra lap round each part outline at full depth, 400 ipm (F10160). Foam: two laps | `--dust-feed` mm/min, `--dust-laps`, `--no-dust-pass` |
| Round through-holes | cut from the centre outwards when the CAM's edge lap would free a plug, up to 3 in across | `--hole-max-in`, `--hole-plunge-feed`, `--no-hole-fix` |
| FireGuard | narrow holes, slots, slits and grooves cut in 2-3 depth steps, lifting out between; T-slots and pocketed-out openings (PH-type openings, dog-bone slots) in passes of at most one bit width (6 mm), lifting out between (run both after convert) | `scripts/fireguard.py`, then `scripts/depthpasses.py` |

Programs are metric, Z0 = spoilboard / bottom of stock. The CAM assumes nominal stock (0.75 in:
clearance Z24.130; 0.5 in: clearance Z17.780); real Baltic birch is metric (18 mm / 12 mm), which is
why shallow labels came out fuzzy. Pick `--stock-in` from the file name / the top analyze reports.
**Entry**: straight plunges (user confirmed for I9 and again for I1-I8). `--keep-ramps` only if asked.

## Foam (user rules, 2026-11-19)

"No tabs in foam ... foam is .5. Foam is simpler cuts. Add the dust lap only." Later the same day:
"do a second dust lap, the foam", and holes from the centre (see Round through-holes below).

For a foam file:

```
python3 -I scripts/convert.py IN.MMG OUT.MMG --foam
```

- `--foam` does two things and nothing else, with 0.5 in stock:
  - **two dust laps** round each panel outline;
  - **round through-holes from the centre outwards**, in one depth level.
- Labels, passes, plunges and T-slots stay exactly as programmed. The job is not moved.
- **Never add tabs to foam, and never report missing tabs on foam as a problem.**
- It is a foam file when "Foam" is in the name or the user says so. If unsure, ask.
- Tell the user the plan first if they ask for it. Then check the result without the cut simulation:
  the panel's own cut is unchanged line for line and the dust laps are exact copies of its lap; each
  hole's edge lap is the original lap and no move at cutting height leaves the hole (`holes.check`).
- Name the result `<name>-Dust2.MMG` unless the user gives a name. Send each file with its preview.

Reference: `IAA_Foam`, `IAB_Foam`, `IAC_Foam`, `IAD_Foam` (2026-11-19). Each is one OUTER CUTS op: one
panel and two 1 in holes, cut through in a single pass, no tabs. The holes came in as a long spiral
down the edge plus one edge lap, which freed a 0.53 in foam plug ("they leave a little chunk of
foam"). Now: plunge at the centre at the lap's 200 ipm, two rings out, then the same edge lap.
Delivered as `IA?_Foam-Dust2.MMG` (the first version, `-Dust`, had one dust lap and the old holes).
Told the user once, and they were fine with both: these files are programmed for a 0.69 in sheet and
travel between cuts at Z22.5 (0.89 in above the table), which is fine for 0.5 in foam but would drag
through thicker foam; and with no tabs the panel is loose when the extra laps run.

## What it changes

- **Labels**: one pass at the label depth (0.18 in), one bit wide. A label is
  - any shallow engraving in a POCKET op (text, arrows, marks on the parts), and
  - the **sheet ID badge**: the name engraved on the sheet scrap in the bottom-right corner
    (I9, B2, D1RB ...): engraving outside every part and within 300 mm of that corner.
  User rule, 2026-11-19: "Keeping the labels in the same spot. Can you make the labels like just
  the size of the bit? ... Like the width. And the badge."
- **Label words: the straight-line font** (`scripts/blockfont.py` + `scripts/labelwords.py`; user,
  V4 2026-11-21, and 2026-11-23: "the labels should be smaller ... we don't have the curves"):
  - Every label WORD is written again: same text, centred where the old word was, same direction.
  - Straight lines and 45-degree corners only. No arcs, no curves, no smoothing: a letter is a
    few G1 moves, so there is nothing to jitter.
  - Size: letters 24 mm (0.95 in) tall, always. They sit on a grid of 20 units x 1.2045 mm.
    Letters are 12 units wide (I 0, 1 4, L 11, M 14) and 10 units apart, which is 12 mm between
    cut centres = 6 mm of wood between any two cuts with the 6 mm bit.
  - Smaller only when the word would not fit inside the old word. convert then prints `SMALLER`:
    tell the user (less than 6 mm of wood between cuts).
  - The letter shapes were read back from the user's own ClaudeV16 files (68 words, 10 badges),
    so the skill writes exactly the letters the user approved: 0-9 A B C D E F G H I K L M O P Q
    R S U V Y. J N T W X Z are drawn in the same style but have never been cut: convert prints a
    note when one is used. Tell the user and show the preview.
  - The text comes from a reading, never a guess: `labelwords.py sheet` makes a contact sheet of
    every word upright and flipped; read it by eye; `labelwords.py check --read "id=TEXT ..."` proves
    each reading in all 8 orientations and writes the `--label-text` file. A word you cannot read
    for sure: leave it out; it is traced instead (below). Tell the user which.
  - Mirrored words (the CAD mirrors left/right parts: D2 DCM, D7 DCG/DCF, D8 ACV/CL/PD) are
    written readable, facing the same way. Words of letters that read the same upside down
    (B C D E H I K O X) keep the old direction.
  - `--add-label "TEXT@X,Y,ROT"` adds a word the CAM file does not have (D2's second DCM, D3's
    DAE): centred at X,Y mm, ROT 0 reads left to right, 90 bottom to top. Only when the user gives
    the text and the spot (qc-generator README: never invent a part code). It is cut together with
    a `--label-text` word; verify checks it keeps 3 mm of wood from every other cut.
  - verify: each word stays inside the box the old word covered (bit edge included), at the label
    depth, nothing deeper, and no cut of a word feature is outside a word box.
- **Sheet badge: the name in a box** (user, V4, V7, V8; 2026-11-23: "we changed that circle"):
  - Always give `--badge-text` (the sheet's name, e.g. `D1RB`). The old ring and the old letters
    are removed. There is no circle any more.
  - Letters like the labels: 24 mm tall, same font, same spacing.
  - The box line is 14 units (16.9 mm) from the letters on every side, corners clipped 6 units
    (7.2 mm): 118 x 58 mm for D1RB, 128 x 58 mm for D2RB-D9RB, 145 x 58 mm for D10RB.
  - Centred where the old ring was. The old ring (a POCKET ring 90-220 mm across, the one nearest
    the bottom-right corner) is found by its shape, even when a part's box covers that corner (D7),
    when it is cut in pieces (D10: outer lap + inner clearing) or cut short on one side (D3).
  - 0.25 in deep, letters and box, one pass (user, 2026-11-23: "the badges aren't coming out
    correct ... Cut the badges at like 0.25").
  - verify: at the badge depth, nothing deeper, nothing outside the box line, and at least 8 mm of
    wood between the badge and the nearest other cut.
  - Without `--badge-text` the old ring and letters are traced as one line each (old behaviour) and
    convert says so. Don't deliver that: ask for the sheet name.
- **Label and badge feeds and plunges** (user, V9-V12: the bit was tearing the letters):
  - Letters (labels and badge) run at 75 % of the programmed label feed: 300 ipm on 1/2 in sheets
    (F7620), 472 ipm on 3/4 in sheets (F12000).
  - The badge box runs at 50 %: 200 ipm (F5080) / 315 ipm (F8000).
  - Every stroke: rapid to above its start, plunge at the plunge feed to 0.5 mm above depth, feed
    the last 0.5 mm at 1/10 of the plunge feed, cut the stroke, lift the first 0.5 mm at that slow
    feed, rapid up. Plunge first, then cut: never moving sideways while going down.
  - The feed after the label is left as it was.
- **Changing only a depth in a finished file** (`scripts/labeldepth.py`): moves every Z of the cuts
  that are `--from-in` deep to `--to-in`, keeping the slow last 0.5 mm, and proves that nothing else
  in the file changed. Used for V17: `labeldepth.py V16.MMG V17.MMG --stock-in 0.5 --from-in 0.20
  --to-in 0.25` (it found the badge on each sheet). Use it when the user wants the badge or the
  labels deeper or shallower and nothing else touched.
- **Traced labels** (arrows, marks, and words nobody could read; `scripts/singleline.py`):
  - The CAM pockets each letter, so its strokes are up to ~1/2 in wide. A traced label is cut by
    one pass of the bit along the middle of its strokes: each stroke is exactly one bit wide.
  - The letter shape is what the old program cut through the real wood surface. The bit centre only
    goes where the whole bit fits inside that shape, so nothing is cut outside the old letter.
    Hairline slivers (< 1.1 mm) the old pocket passes left inside a letter count as letter.
  - Short spurs into corners are removed; line ends are carried on to the end of the stroke. The
    line is smoothed only where the bit still fits everywhere along it (D7 #97 poked out at a bend).
  - Same depth, feed and plunge rules as the font words.
  - A letter the bit does not fit in is cut as a pocket the old way, with a printed note.
- **Older label styles, only when the user asks for them**:
  - `--label-font hershey`: Hershey Sans 1-stroke (`hershey_futural.jhf`, `HERSHEY-FONTS-NOTICE.txt`,
    `scripts/fontlabels.py`), curves smoothed and cut as G2/G3 arcs, as tall as the old letters,
    badge text inside the old ring cut as one circle. This is ClaudeV1-V3. The user replaced it in
    V4: the curves did not cut cleanly and the letters were too big.
  - `--pocket-labels`: the CAM's pocketed letters at the label depth (files before 2026-11-19).
    Pocket mode only: if a label was cut in several step-downs, only the first step's path is kept.
- **Parts**: every outline ends up as pass 1 at half depth + pass 2 = the finish lap through
  (unchanged), then the one dust lap (see **Dust pass**). Every other lap the CAM wrote is removed.
  Layouts recognised (`scripts/parts.py`):
  - **A** pass-1 lap and through cut are separate features with the same outline: ROUGHING +
    OUTER CUTS (I6-I9), or an onion-skin OUTER op + a through OUTER op (I5). Pass-1 Z rescaled.
  - **A, several pass-1 levels**: the pass-1 feature steps down more than once (Jack Drain: 2 laps at
    Z11.43, a ramp, 2 laps at Z3.81). Pass 1 keeps only its first lap, moved to half depth.
  - **Repeated through lap**: the through lap is cut twice on the same path at the same depth,
    tabs included (Jack Drain). The repeat is removed only if every point of it lies on the first
    lap at the same Z.
  - **A, the pass-1 lap already lifts over the tabs** (DD1 closet, 2026-11-23: the pass-1 feature
    laps at Z5.05, 0.51 in deep, rising to Z5.588 over each tab, then steps down to Z0.508 with the
    same lifts). Still one lap for pass 1: a lap may rise up to 6.5 mm on the way round. It moves
    to half depth, the second level goes, the through lap and its tabs stay.
  - **B** one feature: ramp, lap at a pass-1 floor, ramp, through laps (I2-I4). Same result.
  - **C** one feature with a single through lap (I1): a copy of it at the pass-1 depth is inserted
    first, then the bit lifts to its plunge height, goes back to the start and runs the original.
  - **B3** one feature cut in three depth steps (D7-D10, 3/4 in: laps at Z11.43, laps at Z3.81
    with tab lifts, then the through laps; each level is lapped twice). Pass 1 = ONE lap at the
    first level, moved to half depth. The middle laps and both ramps are removed. The bit lifts
    straight out, rapids above the wood to the start of the closed through lap and plunges there.
    A repeated through lap is dropped (same test as above). Tabs keep their height when the middle
    lap lifted over them. A lap may close part-way along an arc, or start and end on a tab top.
  - A ramp point that happens to sit exactly at the tab height is not a tab lift and is never
    moved (D5 round part: the outline spirals down past the tab height).
  - **A+** like A, but the depth steps between pass 1 and the through lap are features of their
    own (D8 #210/211/213, D9: a lap at Z10.16, laps at Z5.334 and Z0.508, the through lap). The
    first is pass 1, the ones in between are removed whole, the through lap stays. Removed features
    are listed in the report (`removed_features`) and verify lines the two programs up around them.
  - **A, the through cut laps part-way down first** (D8 #200/#212: pass 1 is its own feature, but
    the through feature laps at Z3.81 with tab lifts and spirals down before its through laps).
    Those laps go: the bit rapids at clearance height to the start of the through laps and plunges
    there, like B3. Tabs stay when the removed laps lifted over them.
  - anything else (e.g. a spiral that winds down with no laps, I2 feature 201) is left as is.
  An extra through lap that runs *outside* the part is removed when a full finish lap follows it
  and it runs off the finish path. Its end is found by, in order: it returns to its ramp end (I9);
  it returns to where the cut first reaches through depth (I3); its point closest to that, with one
  lap left after it, joined by a short (< 1.5 mm) connector (I4, I8). verify proves it was waste.
- **Label ramps**: stretched from the plunge height (gentle) unless that would push a stretch of
  ramp that ran through air (CAM assumed thicker stock) into real wood outside the label's old
  outline; then only the in-wood part of the ramp is deepened (I1).
- **Straight plunges** in everything converted: the bit never moves X/Y while Z is changing in the
  wood. A ramp-in that starts above the wood becomes a rapid to where the ramp ended + a straight
  plunge. A ramp-in that starts inside the wood (pass 2 from the pass-1 floor, tab exits): in labels,
  or where the lap cuts that stretch again later, plunge at the ramp start and follow its path at
  depth; otherwise lift out, rapid to the ramp end, plunge there. A ramp-out becomes a straight lift.
- **Tabs** keep the thickness the old program actually produced: if the old pass 1 cut straight
  across the tabs (no lifts), tab tops go down to the old pass-1 floor; if it lifted over them,
  tabs stay. `--programmed-tabs` keeps the CAM tab height instead.
- **T-slots** are cut slower (user request, 2026-11-17: "they're too aggressive and they need to be
  cut slower"). A T-slot is the knock-down joint pocket: a channel that runs in from the edge of a
  part and ends in a head shaped like a three-leaf clover, about 14 mm across the head and
  31-39 mm long. It is **not** the dog-bone rectangle. Reference: I1, both ends of part HCD.
  - The CAM cuts each one nearly through the sheet in one pass at the POCKET op's full feed
    (400 ipm on most sheets, 630 ipm on I1). The skill writes 150 ipm for every T-slot move in
    the wood and 50 ipm for its plunge, then puts the old feed back for whatever comes next.
  - Only F words change. Same path, same depth, still one pass. A feed is never raised.
  - How they are found (`scripts/tslots.py`): a POCKET feature that is not a label, at least 6 mm
    deep, 12-16.5 mm x 28-41 mm, whose bit path is much wider at the head than in the channel.
    The plain short bars next to FCC on I2 (9 x 36 mm, no clover) are not T-slots.
  - `--extra-tslots` / `--not-tslots` with feature ids if the user says something is or isn't
    one; `--no-tslots` leaves them at the program feed (gives the pre-2026-11-17 output).
  - If slower alone is not enough, the next step the user was offered is two passes. Ask first.
- **Dust pass** (user request, 2026-11-18: the compression bit "is leaving too much sawdust debris
  behind ... one more extra pass around the outline, a quick one ... with the bit at full cut
  depth, pretty much just tracing it"). Right after each part's through lap the bit traces that
  lap once more (`scripts/dustpass.py`):
  - It is a line-for-line copy of the through lap: same X/Y, same depth, same lifts over the tabs,
    so every tab stays. It cuts no wood. No retract and no new plunge: the bit is already there.
  - Sideways moves of the extra lap run at 400 ipm. The drops after each tab keep their feed.
    Nothing outside the extra lap changes speed.
  - Part outlines only (ROUGHING / OUTER features that go through). Labels, holes, slots, pockets
    and T-slots do not get one. The user was asked about the through slots and did not ask for them.
  - A through lap can start and end on top of a tab (I9 parts 167 and 170); the copy then starts there too.
  - A part is left alone, with a printed note, when its through cut does not end in a closed flat
    lap, or when that lap is already cut twice (so running it again never adds a third lap).
  - This is the one deliberate repeated lap. Repeats the CAM wrote are still removed first.
  - `--no-dust-pass` leaves it out. It adds about 1 minute per 10 m of outline.
- **Line numbers** are renumbered N10, N20 ... (no gaps; inserted lines get numbers).
- **Round through-holes** (user rule, 2026-11-19, for wood and foam alike: "anything that's a hole
  that's cut all the way through, that will cut out a circular hole, needs to start cutting from
  the center ... we don't ever want whole circles being cut out because they get stuck in the CNC
  vacuum where the bit is"). `scripts/holes.py`:
  - Which holes: a feature that goes through and ends in one closed, flat, full-circle lap with no
    tab lifts, sits inside a part, has nothing cut inside it, would free a plug (lap radius more
    than the bit radius), and is no more than 3 in across. Small holes the bit already covers
    (the 1/4 to 7/16 in spiral holes) are not touched.
  - What changes: the bit plunges at the hole's centre and opens it in rings no wider than 3/4 of
    the bit, then runs the CAM's own edge lap, kept line for line. Size and position cannot change.
  - Depth: foam, one level. Wood, two levels (half depth, then through), with a 50 ipm plunge.
  - Converted holes get no dust lap: nothing is left in them to sweep.
  - A round PART is never touched: it is not inside another part, or it has features inside it.
  - A round hole that is skipped (bigger than the limit, or an entry the script does not know) is
    printed. Tell the user: it will still free a plug.
  - **The wood path (two levels) has not been run on a real file yet.** Only foam has. The first
    time a wood file has such a hole, read the `round hole` lines, look at it in the preview, make
    sure verify's round-holes line says OK, and tell the user it is the first one.
- **FireGuard: narrow cuts in depth steps** (named by the user; 2026-11-23, D7: "the little holes are wanting to
  catch fire ... plunging straight down too far. And the dust has nowhere to go"). `scripts/fireguard.py`:
  - At risk: a cut that is not a part outline or label, at most 13 mm wide (bit edge included,
    about two bit widths), that goes more than 7 mm deeper in one entry (the bit never lifts out).
    Typical: 1/4-1/2 in holes spiralled straight down, short slots zigzagged down, narrow grooves,
    and slits cut at full depth in one pass.
  - Holes / slots / grooves (spiral or zigzag down): 3 depth steps (2 for cuts under 10 mm deep).
    At each step depth the bit lifts straight out to clear the dust, rapids back to 1 mm above
    where it was, feeds the last 1 mm at 50 ipm and carries on along the same path. A straight move
    that passes a step depth is split right there. Through cuts stop 0.010 in into the spoilboard.
  - Slits (straight plunge, then a flat loop): every pass that goes more than one step deeper gets
    extra passes of the same loop in between, each still a straight plunge then the loop.
  - `fireguard.py IN OUT --stock-in` checks itself: same X/Y path in order, nothing deeper, lifts
    between steps, no faster feed, every other line unchanged. Running it again finds 0 at risk.
  - Run FireGuard on every new file after convert.py, and on old files when asked for a fire check.
  - **T-slots and openings in depth passes** (`scripts/depthpasses.py`). FireGuard's 13 mm width
    limit skips these, yet the bit cuts them buried and never lifts out on the way down. That was
    a miss in the rule, and the "0 at risk" check shared it. The user found both at the machine:
    - T-slots (2026-11-23, cutting D8 V17: "The tslots on D8 are not fixed", then "Fix the tslots
      on the other nine sheets"). The CAM cuts them with one straight plunge 0.38-0.59 in deep and
      one pass at full depth (D6, D8), or 2-3 depth levels of 0.16-0.36 in each in one go.
    - Openings (2026-11-23, the PH part's long opening circled on the drawing: "This spot on D8
      cut PH cuts too aggressive ... The dog bone slots next to the label CL also"). The CAM
      clears the whole opening: a steep spiral straight down to full depth (0.71 in in 86 mm of
      travel), then laps at full depth, all at 630 ipm, in one pass.
    - Rule for both: no pass takes off more than one bit width (6 mm, 0.236 in), and the bit
      lifts straight out between passes.
    - How: the programmed cut is split where it starts down to its next depth level. A level
      thicker than 6 mm is cut in 2 to 4 equal passes of its own stretch: the same moves, never
      deeper than that pass's depth; its last pass is the programmed one line for line. Between
      passes the bit lifts out and goes straight back down the open cut at 50 ipm at most.
    - Same path, same shape, same final depth, same feeds. No other cut is touched.
    - Which openings: a cut that is not a part outline or a label, goes down in one entry, goes
      through the sheet, is not a round hole, clears its whole area (no slug left standing) and
      gets to its depth by a steep way down (straight plunge, or a ramp steeper than 1 in 10).
    - **Left alone on the user's word.** The user was shown all 26 cuts of this kind on D8 (the
      5 openings in red; 8 round holes and 13 blind pockets in orange) and answered: "Just fix red
      then do that for the rest of the sheets and add it to mmg clean cut skill." So round through
      holes (3/4 in, 1 in ...) and blind pockets that are cut to depth in one level stay as
      programmed. `--all-pockets` steps them too: only when the user asks.
    - Also left alone: a lap round the outline of an opening (the slug stays standing, like a
      part outline; D6 has two 203 x 381 mm ones), and helixes that wind down gently.
    - **Show first.** Before changing cuts the user has not named, send a picture of the sheet
      with those cuts marked and wait (user, same day: "Show me what you're going to fix before
      you fix it"). Red = what was named, orange = the same kind elsewhere.
    - It checks itself: every pass follows the programmed moves and is never deeper, every
      programmed move ends at its programmed depth, no pass over 6 mm, no feed raised, every
      other cut line for line the same.
    - Run it right after fireguard.py, always.
    - Reference: V18, 192 T-slots (D1 26 in 2 passes; D3 40, D4 16, D5 8 in 3; D6 28 in 2; D7 18
      and D9 16 in 3-4; D8 32 in 3; D10 8 in 4; D2 none). V19, 107 openings (D1 3, D2 45, D3 33,
      D5 3, D6 3 in 3 passes; D7 3 and D8 5 in 4; D10 12 in 5; D4 and D9 none). A cut simulation
      of every changed cut showed the same shape and the same floor as before.
  - **Not covered, tell the user if they ask about rough or burning cuts**: round holes and blind
    pockets cut to depth in one level (see above), and wider cuts that spiral or ramp down gently.
  - Reference: D1-D10 V16 (2026-11-23), 519 cuts on the V15 files, 0 left after.
- **Untouched**: other holes, slots, deep pockets, every feed outside the T-slots, everything else.

## Workflow

Scripts are in `scripts/` next to this file. Run them with `python3 -I` (needs Pillow and numpy).

0. **All operations named the same?** Some exports put every cut under one op name (D4: eight ops all
   called `OUTER CUTS 2 85 2 6 x`), so labels, T-slots and holes all look like part outlines. Look at
   the analyze table (op, size, depths), decide what each op really is, and rename the ops first:
   ```
   python3 -I scripts/relabel.py IN.MMG FIXED.MMG --op "OUTER CUTS 2 85 2 6 3=ROUGHING 3" \
       --op "OUTER CUTS 2 85 2 6 13=POCKET 13" --feature "108-115=SLOTS 4"
   ```
   Only comment lines change; it checks that every cutting line is the same before writing.
   Convert and verify FIXED.MMG against itself, and say what was renamed.

1. **Map the program**
   ```
   python3 -I scripts/analyze.py IN.MMG OUT_DIR --stock-in 0.71
   ```
   Prints the assumed stock top, operations and features, and writes `OUT_DIR/<name>_map.png`:
   red = labels (the sheet ID badge is listed as `sheet-id`), blue = part outlines, orange =
   T-slots (their count and ids are printed). Show the map.
   - Use `--extra-labels` / `--not-labels` with feature ids only if the user says something is or
     isn't a label.
   - If the stock top it reports looks wrong, stop and check before converting.

2. **Read the label words, then convert**
   ```
   python3 -I scripts/labelwords.py sheet IN.MMG WORK/NAME --stock-in 0.71 --ids <label letter ids>
   (read every word on WORK/NAME.png)
   python3 -I scripts/labelwords.py check IN.MMG WORK/NAME --stock-in 0.71 --read "106=DCM 88=CCB ..."
   python3 -I scripts/convert.py IN.MMG OUT.MMG --stock-in 0.71 --label-text WORK/NAME.words.json \
       --badge-text D7RB [--extra-labels ids] [--add-label "TEXT@X,Y,ROT"] [--keep-ramps]
   ```
   Always pass `--label-text` and `--badge-text`: that is what gives the straight-line font and the
   box badge. Read every `left as is`, `SMALLER` and `never been cut` line and tell the user.
   Also writes `OUT.MMG.json`, which records what was changed and is needed by verify.

3. **Verify. Never deliver a program that fails.**
   ```
   python3 -I scripts/verify.py IN.MMG OUT.MMG --tool-mm 6
   ```
   Must end with `ALL CHECKS PASSED`:
   - labels: nothing cut outside the old letter (one-pixel specks along a one-bit-wide stroke are
     drawing noise), cut to label depth, nothing deeper; it prints how much of the old letter area
     is still cut
   - badge: at the badge depth (0.25 in), nothing deeper, nothing outside its box line, at least
     8 mm of wood to the nearest other cut. Font words: inside the old word's box, at label depth.
     Added labels: at least 3 mm of wood to the nearest other cut
   - parts: outline identical (under 0.4 mm drawing noise), no new cuts, anything no longer cut is
     on the waste side. Where the old step-down ramps cut a chord across a corner that the old
     finish lap does not (D10 #195, 0.28 mm), the part is compared with the old flat moves only
   - straight plunges: no move changes Z while moving X/Y in the wood
   - T-slots: exact same path as before, nothing in the wood faster than the T-slot feed, no
     plunge faster than the T-slot plunge feed, and no other feature changed speed
   - round holes: the edge lap is the original lap, the cut starts by plunging at the centre, no
     move at cutting height leaves the hole, nothing goes deeper than before, the rings leave no
     uncut wood
   - dust pass: each extra lap is a move-for-move copy of that part's through lap and runs at the
     dust feed; a part the converter did not otherwise touch is exactly the original apart from it
   - operation summary (compared without line numbers): only part ops and label POCKETs changed
   If it fails, find out why (look at the per-part line, render the area) and fix the script.
   Do not tune a threshold to make it pass.

4. **FireGuard**
   ```
   python3 -I scripts/fireguard.py OUT.MMG STEP.MMG --stock-in 0.71
   python3 -I scripts/depthpasses.py STEP.MMG FINAL.MMG --stock-in 0.71
   ```
   Each prints every cut it changed, checks itself and exits 1 on a problem. Deliver FINAL.MMG.
   Run the `cnc-sheet-standard` sheet check and preview on FINAL.MMG.

5. **Deliver**: save to `cnc-renders/<job>/` with the map picture, commit and push, send the
   program to the user. Name delivered programs `<original name>-Depthchange.MMG`
   (e.g. `I1-5in-Depthchange.MMG`); send several together in one message, never zipped. Report in a short table: labels changed (count, depth), parts (pass 1 Z,
   pass 2 Z, extra laps removed), T-slots (count, feed), dust laps (count, metres), the tab decision, and anything left alone and why.

## Machine: RichAuto controller

- Files must be `.MMG` (it refused `.nc`/`.tap`). Keep names short (the I-sheet names, ~23
  characters, work; a 55-character name was refused).
- Keep the I-sheet layout: first line `N10M03`, no header comments, no G21/G90/G17/G94, no `S` word,
  short op comments like `(POCKET 68)`, `%` as the last line. Programs from other sources (e.g. the
  Joey window frame) need `cnc-renders/joey/richauto_format.py` to match it; motion lines stay as is.

## Watch-outs to tell the user

- Pass 2 cuts about half the sheet thickness in one go; suggest watching the first part.
- Holes and slots keep the path the CAM wrote (spiral / ramped): the user decided to keep them.
  Two things do change, both the user's own rules: round through-holes that would free a plug are
  cut from the centre out, and FireGuard adds lifts between depth steps in narrow ones. Deep
  pockets are left unchanged, apart from the T-slot feed.
- The badge is 0.25 in deep: half of a 1/2 in sheet. It is on the scrap, not on a part.
- T-slots take longer now: each one runs at 150 ipm instead of 400-630. If they still cut rough,
  rerun with a lower `--tslot-feed` (for example 2540 = 100 ipm).
- Straight plunges use the program's plunge feed (200 ipm in I9) for the full depth: about 4 mm
  for labels, about 9 mm for each part pass. If the bit struggles, rerun with a lower
  `--plunge-feed` (for example 1270 = 50 ipm).

## Reference job

I9 (`cnc-renders/i9/`): 42 labels + the I9 sheet badge, 9 parts in two passes (Z8.890 then
Z-0.254), tabs kept at Z3.81, straight plunges everywhere converted. Made with:
`python3 -I scripts/convert.py I9-75in.MMG out.MMG` and it passes verify.

I1-I8 (`cnc-renders/i1-i8/`): straight plunges, 0.5 in stock for I1-I5, 0.71 in for I6-I8.
Layouts: I1 = C, I2-I4 = B, I5-I8 = A. Left as is: I2 feature 201 (spiral), extra lap of I4 part 123.

T-slots found (2026-11-17): I1 18, I2 32, I3 16, I4 10, I5 17, I6 2, I7 35, I8 18, I9 4. The
`-Depthchange.MMG` files delivered on 2026-11-09 were made before this and still have the fast
T-slots. To slow the T-slots in an already converted file without redoing anything else:
`python3 -I scripts/convert.py IN.MMG OUT.MMG --stock-in 0.5 --no-labels --no-parts --keep-ramps --no-dust-pass`.

Dust pass (2026-11-18): first made for `I9test-75in.MMG` (an I9 that was already in two passes):
9 parts, 646 lines added, 16.7 m of extra lap at 400 ipm, delivered as `I9-75in-DustPass.MMG`.
To add only the dust pass to an already converted file:
`python3 -I scripts/convert.py IN.MMG OUT.MMG --stock-in 0.71 --no-labels --no-parts --keep-ramps --no-tslots`.
That job was checked by comparing the files line by line (the new file minus the added lines is
the original).

ID1 / ID2 (2026-11-18, from `ID1-75in_1.MMG` and `ID2-5IN_1.MMG`): the first full run with the dust
pass. verify passed on both: labels, parts, straight plunges, T-slots and dust laps.
- ID1 (0.71 in): 16 labels, 9 parts (pass 1 Z3.81 -> Z8.89), 10 T-slots, 9 dust laps (15.7 m).
- ID2 (0.5 in): 15 labels, 29 parts (pass 1 Z3.81 -> Z6.223, two of them layout C), 30 T-slots,
  29 dust laps (35.1 m).
- **Their labels were not found automatically.** The programmer now cuts label letters 0.160 in
  below the CAM top, which is deeper than the 3.2 mm label limit in `analyze.py`, so they came up as
  pockets. They needed `--extra-labels` (ID1 ids 10-25, ID2 ids 28-42). In real 18 mm stock the ID1
  letters were only 0.120 in deep. On every new file, look at the shallow POCKET features that are
  letters before converting.
- One cutout on each sheet is left as is: a ROUGHING lap at Z3.81 whose through cut is in the SLOTS
  op (ID1 feature 8, a 5.8 x 14.8 in opening; ID2 feature 27, 17.3 x 6.3 in). Slots are not converted
  and get no dust lap. Tell the user.
- Delivered as `ID1-75in-DepthFix3.MMG` and `ID2-5in-DepthFix3.MMG` (`-Depthchange` would make the ID1
  name 24 characters).

DD1 / DD2 (2026-11-23, Transit DD closet: `DD1-75in-Transit Closet.MMG`, `DD2-5in-TransitCloset.MMG`
from Drive folder "Transit DD Closet Unit"): the first new sheets run through the whole V19 recipe.
- Labels came in 0.01-0.10 in deep (programmer error). Words read: DD1 ADD, ADK x2, DDE x2; DD2 DDB,
  FUSES, DDA, DDC. DD1 has two single marks like a C on its side that could not be read for sure:
  left out of `--label-text`, so traced. The user was told. Badges DD1 / DD2 (three letters:
  box 92 x 58 and 101 x 58 mm).
- DD1 9 parts (the layout above), DD2 27 parts (layout A). T-slots DD1 9, DD2 30. FireGuard DD1
  113, DD2 36. Openings DD1 2, DD2 2. verify, FireGuard, depth passes and the sheet check all OK.
- Named `DD1.75-ClaudeV1.MMG` and `DD2.5-ClaudeV1.MMG`; a new "Claude" folder made inside the closet
  folder on the user's word, with a README (DD1 zipped: 3.8 MB).

D1-D10 (2026-11-19, the "RB" sheets, older `-Depth_Fix` / `-DepthFix` exports): D1-D6 are 1/2 in,
D7-D10 are 3/4 in. All ten pass verify with single-line labels and the new badge text `D<n>RB`.
- Text labels sit 0.15-0.16 in below the real top and were not found automatically: passed with
  `--extra-labels` (single-level POCKET features 0.14-0.23 in deep, under 60 mm). D7's letters are
  0.24-0.29 in deep in their own op (POCKET 106).
- Shallow grooves that are not letters were left as programmed (`--not-labels`): D1 4 (0.043 in),
  D3 14 (0.083-0.125 in), D8 10 (dashes); the user was told. D2: one 7 x 33 mm slot by the badge.
- D4 needed `relabel.py` (see step 0). D7-D10 are layout B3; some outlines on D8/D9 are A+.
- Named `D<n>RB.5-ClaudeV1.MMG` (1/2 in) and `D<n>RB.75-ClaudeV1.MMG` (3/4 in), the user's naming.
- ClaudeV2, renamed ClaudeV3 in Drive on request (2026-11-20): labels and badge in the Hershey font, label depth 0.18 in. Words read:
  D1 AKB AKC AKE DCC DCK DCK DCP; D2 DCL DCM; D3 DFC DFC CCM; D4 FUSES DFA DFE; D5 DCC; D6 DHC DHC
  CCO DHD DHD; D7 DCM DCM CCB CCB DCQ DCG DCG CY ADK ADK DCF; D8 DCB DCB ACV ACV PE PE PF PF PG PG
  CL CL PD PD PH DHA; D9 DCI DFD DFD DCF DHA DCM x4; D10 DFG ACE x4 DHB DHB DFF DFB.
- Copies go in Drive: Model D - Transit 148 ext / 148 ext RB / Claude (with a README of the
  changes). Files over 3.1 MB cannot be uploaded from a session: upload them zipped and say so.
- Versions V4-V15 were made by the user with their own tools (repo Tiddybub/mmg-cleanup-skill:
  tools/labels.js, tools/deramp.js): V4 straight-line font, 24 mm labels, badge in a box; V5 D2
  second DCM; V6 D3 DAE; V7 badge letters 24 mm; V8 badge box moved out; V9 plunge first, then
  cut; V10 badge 0.20 in, box at half feed; V11/V12 labels and badge 25 % slower; V15 slits plunge
  to depth, then cut. Always start from the newest ClaudeV<n> files in the Drive Claude folder,
  not from older copies here, and read that version's README first.
- V16 (2026-11-23): FireGuard on the V15 files, 519 cuts.
- V17 (2026-11-23): badge 0.25 in deep (`labeldepth.py` on the V16 files; only the badge's Z
  words changed).
- V18 (2026-11-23): T-slots in depth passes (the first form of `depthpasses.py`, then called
  tslotsteps.py, on the V17 files). D8 was made first, on the user's word ("Just do D8 first"),
  with 3 equal passes each the whole path lifted by the same amount; the other nine followed the
  same day with the level-aware version. D8 passes the same check and was left as delivered.
- V19 (2026-11-23): pocketed-out openings in depth passes (`depthpasses.py` on the V18 files).
  D8 first (PH opening + 4 dog-bone slots by CL), then the other sheets. D4 and D9 have none:
  their V19 is byte for byte their V18.
- **The user's own rule list** is `SKILL.md` in their repo Tiddybub/mmg-cleanup-skill ("ALL OF
  TIM'S RULES"). Read it before writing a Drive README or pushing to GitHub. From it:
  - README: the credit line in capitals near the top, and the same credit with the date on every
    "what changed" heading (rule 5); say whether the version has been cut on the router (rule 8).
  - GitHub: commits carry the repo owner's name and no co-author or AI lines (rule 6).
  - This skill is kept there too (`mmg-clean-cut/`, `cnc-sheet-standard/`), next to `tools/*.js`.
- **Only the newest version stays in the Drive Claude folder** (user rule, 2026-11-20: "it only
  needs to be Claude V3 files in there ... every time you update, remove all old versions").
  Every update: upload the new set and its README, then move every older ClaudeV<n> file, zip
  and README in that folder to the Drive trash. Never touch the originals in the parent folder.

Standing rule from the user (2026-11-17): do not test or run anything on their files without being
asked. Running the skill on a file they hand over includes its verify step; anything beyond that
(regression runs on other sheets, trial conversions) needs their say-so first.
