/**
 * Vantopia QC Packet Generator
 * ----------------------------
 * Web app: fill in customer + model + modules, click Generate,
 * and a QC packet Google Doc is created in the customer's folder.
 *
 * Drive ids and the sign-in live in Config.js (see Config.example.js).
 * Models: Sprinter 144, Sprinter 170, Sprinter 170 EXT, Transit Long,
 *         Transit 148 EXT, Promaster 136, Promaster 159.
 * (144 / Transit Long / 148 EXT have per-drawing labels; the others use
 *  per-sheet labels until they're refined.)
 */

// ======================= CONFIG =======================

// The spice cabinet is offered on every model, but it is NOT one drawing set —
// there are two sheets in Drive and the panels differ. Every model gets the
// checkbox labelled plainly "Spice Cabinet"; only the doc behind it changes.
//   Sprinter Spice Cabinet          -> Sprinter 144 / 170 / 170 EXT
//   Spice Cabinet QC page Promaster -> Promaster 136 / 159
// There is no Transit spice cabinet sheet anywhere in Drive. The two Transit
// models therefore have no spice cabinet checkbox — pointing them at either
// sheet above would print the wrong van's panels. When a Transit sheet exists,
// add SPICE_TRANSIT to DOC_IDS and a group on both Transit models.

/**
 * Each model has a list of module "groups".
 * A group = one checkbox in the form = one labeled set of drawings.
 *   label  : what prints in the page header for those drawings
 *   doc    : key into DOC_IDS (Config.js) for the QC sheet Google Doc. Can
 *            also be an ARRAY of keys when one checkbox covers drawings that live in more
 *            than one sheet — Promaster walls pull the door panels sheet too,
 *            because door panels always ship with the walls and having two
 *            checkboxes for one thing let the shop tick only half of it.
 *            Pages come out in the order the keys are listed.
 *   hashes : md5 (first 10 chars) of the specific drawings to pull from that doc.
 *            null = take ALL drawings in the doc. Applies across all of `doc`
 *            when `doc` is an array.
 *   def    : true = checkbox starts checked (the usual kit contents)
 *   kind   : 'rb' or 'dinette' — a raised bed and a dinette occupy the same
 *            floor space, so the form and the server both refuse to put
 *            both in one packet. See CONFLICTS below.
 */
var MODELS = {
  'Sprinter 144': {
    groups: [
      // "144 Raised Bed" doc, 9 drawings: 0-3 + 6-7 bed, 4-5 closet, 8 floor.
      { label: '144 Raised Bed',  doc: 'S144_RAISED_BED',
        hashes: ['19ad57eb0d','b22e7b381f','73c82daf5d','14e2e0455f','58093af2db','dfb82b28dc'],
        def: true, kind: 'rb' },
      // One "Floors" checkbox, two sheets. The floor panels live in the raised
      // bed sheet and the hole-grid panel lives in the walls sheet, so this
      // used to be two checkboxes ("Floors" and "Hex Flooring") that both read
      // as floors on the form. They always ship together, so they are one.
      { label: 'Floors',
        doc: ['S144_RAISED_BED',
              'S144_WALLS'],
        hashes: ['0456f7eaf6','1d57e7875c'], def: true },
      { label: 'Closet (AD)',     doc: 'S144_RAISED_BED',
        hashes: ['2c28cbe624','6359033d76'], def: true },
      // "144 Walls" doc, 2 drawings: 0 wall panels, 1 the hole-grid floor panel.
      { label: 'Walls',           doc: 'S144_WALLS',
        hashes: ['fd7152dfc4'], def: true, wall: true },
      { label: 'Window Combo (AO)', doc: 'SPRINTER_WINDOW_COMBO', hashes: null, def: false },
      { label: 'Pantry Combo (AH)', doc: 'SPRINTER_PANTRY_COMBO', hashes: null, def: false },
      { label: 'Island (BF)',       doc: 'S144_ISLAND', hashes: null, def: false },
      { label: 'Dinette',           doc: 'S144_DINETTE', hashes: null, def: false, kind: 'dinette' },
      { label: 'Toilet Closet (AQ1/AQ2)', doc: 'SPRINTER_TOILET_CLOSET', hashes: null, def: false },
      { label: 'Spice Cabinet',     doc: 'SPICE_SPRINTER', hashes: null, def: false }
    ]
  },
  'Sprinter 170': {
    groups: [
      // "170 RB Base QC Sheet", 8 drawings: 0-3 + 5-6 bed, 4 and 7 the closet.
      // The two closet drawings are byte-identical to the ones in the 144 sheet
      // — it is the same universal AD closet — which is how they were told apart.
      { label: '170 Raised Bed',    doc: 'S170_RAISED_BED',
        hashes: ['73bcd196a3','b69866d13f','f2d81ecd11','b5aae8a751','9959188220','b38bf2808d'],
        def: true, kind: 'rb' },
      { label: 'Closet (AD)',       doc: 'S170_RAISED_BED',
        hashes: ['2c28cbe624','6359033d76'], def: false },
      { label: 'Floors',            doc: 'S170_FLOORS', hashes: null, def: true },
      { label: 'Walls & Ceiling',   doc: 'S170_WALLS', hashes: null, def: true, wall: true },
      { label: 'Dinette',           doc: 'S170_DINETTE', hashes: null, def: false, kind: 'dinette' },
      { label: 'Island (AF)',       doc: 'S170_ISLAND', hashes: null, def: false },
      { label: 'Window Combo (AO)', doc: 'SPRINTER_WINDOW_COMBO', hashes: null, def: false },
      { label: 'Pantry Combo (AH)', doc: 'SPRINTER_PANTRY_COMBO', hashes: null, def: false },
      { label: 'Toilet Closet (AQ1/AQ2)', doc: 'SPRINTER_TOILET_CLOSET', hashes: null, def: false },
      { label: 'Spice Cabinet',     doc: 'SPICE_SPRINTER', hashes: null, def: false }
    ]
  },
  'Sprinter 170 EXT': {
    groups: [
      // "170 ext RB QC", 8 drawings: 0-6 bed, 7 the floor panels (last page).
      { label: '170 EXT Raised Bed', doc: 'S170EXT_RAISED_BED',
        hashes: ['3edd2d7c6c','8935000ef3','62f1e5d412','2098b9dfff','3e58aa0523','eaa4f028b9','6dfb7b903c'],
        def: true, kind: 'rb' },
      { label: 'Floors (EA)',       doc: 'S170EXT_RAISED_BED',
        hashes: ['43f2efed2d'], def: true },
      { label: 'Walls & Ceiling (EB)', doc: 'S170EXT_WALLS', hashes: null, def: true, wall: true },
      { label: 'Dinette (170)',     doc: 'S170_DINETTE', hashes: null, def: false, kind: 'dinette' },
      { label: 'Island (AF)',       doc: 'S170_ISLAND', hashes: null, def: false },
      { label: 'Window Combo (AO)', doc: 'SPRINTER_WINDOW_COMBO', hashes: null, def: false },
      { label: 'Pantry Combo (AH)', doc: 'SPRINTER_PANTRY_COMBO', hashes: null, def: false },
      { label: 'Toilet Closet (AQ1/AQ2)', doc: 'SPRINTER_TOILET_CLOSET', hashes: null, def: false },
      { label: 'Spice Cabinet',     doc: 'SPICE_SPRINTER', hashes: null, def: false }
    ]
  },
  'Promaster 136': {
    groups: [
      { label: '136 Raised Bed',    doc: 'PM136_RAISED_BED', hashes: null, def: true, kind: 'rb' },
      { label: 'Walls — Door Panels Included',
        doc: ['PM136_WALLS',
              'PROMASTER_DOOR_PANELS'], hashes: null, def: true, wall: true },
      { label: 'Floors',            doc: 'PM136_FLOORS', hashes: null, def: true },
      { label: 'Dinette',           doc: 'PM136_DINETTE', hashes: null, def: false, kind: 'dinette' },
      { label: 'Toilet Closet (IQ1/IQ2)', doc: 'PROMASTER_TOILET_CLOSET', hashes: null, def: false },
      { label: 'Closet (AD)',       doc: 'PM136_CLOSET', hashes: null, def: false },
      { label: 'Pantry / Combo (FF)', doc: 'PROMASTER_PANTRY_COMBO', hashes: null, def: false },
      { label: 'Midshelf (FI)',     doc: 'PROMASTER_MIDSHELF', hashes: null, def: false },
      { label: 'Spice Cabinet',     doc: 'SPICE_PROMASTER', hashes: null, def: false }
    ]
  },
  'Promaster 159': {
    groups: [
      { label: '159 Raised Bed',    doc: 'PM159_RAISED_BED', hashes: null, def: true, kind: 'rb' },
      { label: 'Walls & Ceiling (IB) — Door Panels Included',
        doc: ['PM159_WALLS',
              'PROMASTER_DOOR_PANELS'], hashes: null, def: true, wall: true },
      { label: 'Floors',            doc: 'PM159_FLOORS', hashes: null, def: true },
      { label: 'Dinette',           doc: 'PM159_DINETTE', hashes: null, def: false, kind: 'dinette' },
      { label: 'Closet (AD)',  doc: 'PM159_CLOSET', hashes: null, def: false },
      { label: 'Toilet Closet (IQ1/IQ2)', doc: 'PROMASTER_TOILET_CLOSET', hashes: null, def: false },
      { label: 'Pantry / Combo (FF)', doc: 'PROMASTER_PANTRY_COMBO', hashes: null, def: false },
      { label: 'Midshelf (FI)',     doc: 'PROMASTER_MIDSHELF', hashes: null, def: false },
      { label: 'Spice Cabinet',     doc: 'SPICE_PROMASTER', hashes: null, def: false }
    ]
  },
  'Transit Long': {
    groups: [
      { label: '148 Long Raised Bed', doc: 'TL_RAISED_BED', hashes: null, def: true, kind: 'rb' },
      { label: 'Closet (DD)',   doc: 'TL_CLOSET', hashes: null, def: true },
      { label: 'Walls (CB)',    doc: 'TL_WALLS', hashes: null, def: true, wall: true },
      { label: 'Floor (CA)',    doc: 'TL_FLOOR', hashes: null, def: false },
      { label: 'Dinette',       doc: 'TL_DINETTE', hashes: null, def: false, kind: 'dinette' },
      { label: 'Pantry Combo (CD)', doc: 'TRANSIT_PANTRY_COMBO', hashes: null, def: false },
      { label: 'Window Pantry (CO)', doc: 'TRANSIT_WINDOW_PANTRY', hashes: null, def: false },
      { label: 'Toilet Closet (DQ)', doc: 'TRANSIT_TOILET_CLOSET', hashes: null, def: false }
    ]
  },
  'Transit 148 EXT': {
    groups: [
      // 11 drawings: 0-8 bed, 9-10 closet. The closet pair and four of the bed
      // drawings never changed, which pinned the split exactly.
      { label: '148 EXT Raised Bed', doc: 'T148EXT_RAISED_BED',
        hashes: ['29d3e94db0','185ee91d69','67f80966da','92d89bf629','3634d7da9b','1f584025ab',
                 'a71fcaa898','081f61eda2','e92fdf3633'], def: true, kind: 'rb' },
      { label: 'Closet (DD)',   doc: 'T148EXT_RAISED_BED',
        hashes: ['79f6a7909f','4eede8fd14'], def: false },
      { label: 'Floors & Walls', doc: 'T148EXT_FLOORS_WALLS', hashes: null, def: true, wall: true },
      { label: 'Walls',          doc: 'T148EXT_WALLS', hashes: null, def: false, wall: true },
      { label: 'Window Combo (CO)', doc: 'TRANSIT_WINDOW_PANTRY', hashes: null, def: false },
      { label: 'Dinette',        doc: 'T148EXT_DINETTE', hashes: null, def: false, kind: 'dinette' },
      { label: 'Island / Combo (DF)', doc: 'T148EXT_ISLAND', hashes: null, def: false },
      { label: 'Pantry Combo (CD)',   doc: 'TRANSIT_PANTRY_COMBO', hashes: null, def: false },
      { label: 'Toilet Closet (DQ)',  doc: 'TRANSIT_TOILET_CLOSET', hashes: null, def: false }
    ]
  }
};

/**
 * Pairs of `kind` tags that cannot both appear in one packet. A raised bed and
 * a dinette are the same floor space, so the van gets one or the other. The
 * form greys out the other side as soon as one is ticked; generatePacket()
 * checks again in case the form is bypassed.
 */
var CONFLICTS = [
  { a: 'rb', b: 'dinette', message: 'A raised bed and a dinette cannot go in the same van — pick one.' }
];

/** Returns the CONFLICTS entry broken by this set of groups, or null. */
function findConflict(groups) {
  for (var i = 0; i < CONFLICTS.length; i++) {
    var c = CONFLICTS[i];
    var hasA = false, hasB = false;
    groups.forEach(function (g) {
      if (g.kind === c.a) hasA = true;
      if (g.kind === c.b) hasB = true;
    });
    if (hasA && hasB) return c;
  }
  return null;
}

var CHECKLIST = [
  '-Rails', '-Hardware Bags', '-Threaded Inserts in Countertops',
  '-Nylon Bushing Fit Check (For Raised Bed Models)*',
  '-Foam Insulation Sheets (For Flooring Option)*',
  '-Divider Strips*', '-Aluminum Extrusions*',
  '      • Angle', '      • Flat Bar', '      • Floor Threshold',
  '-Lagun Hardware*', '-Cushions*', '-Pre-Built Pieces*'
];

// ======================= WEB APP =======================

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Vantopia QC Packet Generator')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Called by the sign-in screen. Credentials live in Config.js. */
function checkLogin(user, pass) {
  return String(user || '').trim().toLowerCase() === String(APP_USERNAME).toLowerCase() &&
         String(pass || '').trim().toLowerCase() === String(APP_PASSWORD).toLowerCase();
}

/** Called by the form to populate the model/module choices. */
function getConfig() {
  var out = { models: {}, conflicts: CONFLICTS };
  Object.keys(MODELS).forEach(function (m) {
    out.models[m] = MODELS[m].groups.map(function (g) {
      return { label: g.label, def: !!g.def, wall: !!g.wall, kind: g.kind || null };
    });
  });
  return out;
}

/**
 * Called by the form to fill the "existing folder" dropdown: every customer
 * folder already sitting in Customers, alphabetical, case-insensitive.
 * Names are trimmed for display but the folder is always targeted by id.
 */
function listCustomerFolders() {
  var out = [];
  var it = DriveApp.getFolderById(CUSTOMERS_FOLDER_ID).getFolders();
  while (it.hasNext()) {
    var f = it.next();
    out.push({ id: f.getId(), name: f.getName().trim() });
  }
  out.sort(function (a, b) {
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  });
  return out;
}

/**
 * Main entry: build the packet.
 * payload = { customer, model, groups: [labels...], extras: "free text for title line",
 *             folderId: "" to make/reuse a folder named after the customer,
 *                       or the id of an existing folder to drop the packet into }
 * Returns { url, name, folderUrl }
 */
function generatePacket(payload) {
  var customer = (payload.customer || '').trim();
  if (!customer) throw new Error('Please enter a customer name.');
  var model = MODELS[payload.model];
  if (!model) throw new Error('Unknown model: ' + payload.model);
  var wanted = payload.groups || [];
  var groups = model.groups.filter(function (g) { return wanted.indexOf(g.label) !== -1; });
  if (!groups.length) throw new Error('Pick at least one module.');
  var clash = findConflict(groups);
  if (clash) throw new Error(clash.message);

  // Wall material: BEADBOARD or ACM. Same drawings/part codes either way —
  // only the toolpath differs — so it prints as a suffix on every wall page.
  var wallMat = (payload.wallMaterial === 'ACM') ? 'ACM' : 'BEADBOARD';
  var isDually = !!payload.dually;

  // Title line: "Name, Model[, DUALLY][, wall material], Module1, Module2[, extras]"
  // The material sits next to DUALLY as a property of the van, stated once,
  // instead of being suffixed onto each wall module — models with two wall
  // groups (Transit 148 EXT) used to print it twice. Page headers still carry
  // the suffix, because there it identifies that one drawing.
  var anyWalls = groups.some(function (g) { return g.wall; });
  var parts = [customer, payload.model];
  if (isDually) parts.push('DUALLY');
  if (anyWalls) parts.push(wallMat);
  parts = parts.concat(groups.map(function (g) { return g.label; }));
  if (payload.extras && payload.extras.trim()) parts.push(payload.extras.trim());
  var titleLine = parts.join(', ');

  // 1. Pick the destination folder.
  //    folderId set        -> add this packet to that existing customer folder
  //    folderId empty      -> make (or reuse) a folder named after the customer
  //    anything goes wrong -> fall back to "Vantopia QC Packet Generator" folder
  //                           so a built packet is never lost
  var folder = null;
  try {
    if (payload.folderId) {
      folder = DriveApp.getFolderById(payload.folderId);
    } else {
      var parent = DriveApp.getFolderById(CUSTOMERS_FOLDER_ID);
      var it = parent.getFoldersByName(customer);
      folder = it.hasNext() ? it.next() : parent.createFolder(customer);
    }
  } catch (e) {
    folder = null;
  }
  if (!folder) {
    try {
      var p2 = DriveApp.getFolderById(CUSTOMERS_FOLDER_ID);
      var fb = p2.getFoldersByName('Vantopia QC Packet Generator');
      folder = fb.hasNext() ? fb.next() : p2.createFolder('Vantopia QC Packet Generator');
    } catch (e2) {
      var root = DriveApp.getRootFolder();
      var fb2 = root.getFoldersByName('Vantopia QC Packet Generator');
      folder = fb2.hasNext() ? fb2.next() : root.createFolder('Vantopia QC Packet Generator');
    }
  }

  // 2. New doc
  var doc = DocumentApp.create(titleLine);
  var body = doc.getBody();
  var att = {};
  att[DocumentApp.Attribute.PAGE_WIDTH] = 792;   // 11" landscape
  att[DocumentApp.Attribute.PAGE_HEIGHT] = 612;  // 8.5"
  att[DocumentApp.Attribute.MARGIN_TOP] = 26;
  att[DocumentApp.Attribute.MARGIN_BOTTOM] = 18;
  att[DocumentApp.Attribute.MARGIN_LEFT] = 28;
  att[DocumentApp.Attribute.MARGIN_RIGHT] = 28;
  body.setAttributes(att);
  var MAX_W = 792 - 28 * 2;   // usable width in points
  var MAX_H = 612 - 26 - 18 - 30; // usable height (leave room for the label line)

  // Title page line
  var t = body.getParagraphs()[0];
  t.setText(titleLine);
  t.editAsText().setBold(true).setFontSize(28);

  // Big bold DUALLY banner on the front page
  if (isDually) {
    var du = body.appendParagraph('DUALLY');
    du.editAsText().setBold(true).setFontSize(30);
  }
  // No separate WALL MATERIAL line: the title line above already states it once.
  // Page 1 is a cover page (customer, dually, everything ordered) — the
  // drawings start on page 2 so the banner always has room.

  // 3. Resolve every group's drawings BEFORE writing anything, and refuse to
  //    build a packet we know is wrong. See resolveGroups() for why.
  var imgCache = {}; // docId -> [{blob, w, h, hash}]
  var picked = resolveGroups(imgCache, groups);

  groups.forEach(function (g, gi) {
    var use = picked[gi];

    use.forEach(function (im, ii) {
      body.appendPageBreak();
      var head = customer + ' — ' + g.label;
      if (g.wall) head += ' — ' + wallMat;
      if (isDually) head += ' — DUALLY';
      var lbl = body.appendParagraph(head);
      lbl.editAsText().setBold(true).setFontSize(11);
      var p = body.appendParagraph('');
      var pic = p.appendInlineImage(im.blob);
      var w = im.w, h = im.h;
      var scale = Math.min(MAX_W / w, MAX_H / h, 1);
      pic.setWidth(Math.floor(w * scale));
      pic.setHeight(Math.floor(h * scale));
    });
  });

  // 4. Checklist
  body.appendPageBreak();
  var ch = body.appendParagraph(customer + ' — Final QC Checklist');
  ch.editAsText().setBold(true).setFontSize(11);
  var h = body.appendParagraph('Final QC Checklist: (Some Optional*):');
  h.editAsText().setBold(true);
  CHECKLIST.forEach(function (line) { body.appendParagraph(line); });

  doc.saveAndClose();

  // 5. Move into the customer folder
  DriveApp.getFileById(doc.getId()).moveTo(folder);

  return { url: doc.getUrl(), name: titleLine, folderUrl: folder.getUrl() };
}

/**
 * Work out which drawings each group should print, and refuse the whole packet
 * if any group cannot be resolved exactly.
 *
 * This used to be forgiving: a group whose hashes matched nothing fell back to
 * "every drawing in the doc", on the theory that too many pages beats a blank
 * packet. On a real Sprinter 144 order that produced a
 * packet where `Hex Flooring` printed the wall drawings — because `Walls` and
 * `Hex Flooring` are two hash-split groups sharing the doc `144 Walls`, that
 * doc was re-exported on 2026-05-08, and BOTH groups then fell back to
 * everything in it. Partial misses were worse still: the raised bed silently
 * printed only the drawings whose hashes still matched, so the packet looked
 * complete and wasn't.
 *
 * A QC packet exists so the shop can check cut product against the order. One
 * that is wrong or quietly short is worse than one that refuses to build, so
 * both cases are now hard errors naming exactly what to fix. Every group is
 * checked before anything is written, so one attempt reports every problem
 * instead of stopping at the first.
 */
function resolveGroups(cache, groups) {
  var out = [];
  var problems = [];

  groups.forEach(function (g) {
    var imgs = docIds(g).reduce(function (acc, id) {
      return acc.concat(getDocImages(cache, id));
    }, []);
    var where = '"' + g.label + '"';

    if (!imgs.length) {
      problems.push(where + ' — its sheet has no drawings in it (' + docIds(g).join(', ') + ')');
      out.push([]);
      return;
    }
    if (g.hashes === null) {       // take everything in the sheet
      out.push(imgs);
      return;
    }

    var have = {};
    imgs.forEach(function (im) { have[im.hash] = im; });
    var found = [], missing = [];
    g.hashes.forEach(function (h) {
      if (have[h]) found.push(have[h]); else missing.push(h);
    });

    if (missing.length) {
      problems.push(where + ' — ' + missing.length + ' of ' + g.hashes.length +
                    ' drawings are no longer in its sheet (' + missing.join(', ') + ')');
    }
    out.push(found);
  });

  if (problems.length) {
    throw new Error(
      'The drawing list is out of date, so this packet would be wrong. Nothing was created.\n\n' +
      problems.join('\n') + '\n\n' +
      'This happens when a QC sheet is re-exported — the drawings get new checksums. ' +
      'Run debugListHashes() from the Apps Script editor to print the current ones, ' +
      'then update the hashes in MODELS.');
  }
  return out;
}

/** A group's Google Doc ids, resolved through DOC_IDS (Config.js). */
function docIds(g) {
  var keys = Object.prototype.toString.call(g.doc) === '[object Array]' ? g.doc : [g.doc];
  return keys.map(function (k) {
    if (!DOC_IDS[k]) throw new Error('No document id for "' + k + '" — add it to DOC_IDS in Config.js.');
    return DOC_IDS[k];
  });
}

/** Read all inline images of a Google Doc, with sizes + md5 prefix. Cached per run. */
function getDocImages(cache, docId) {
  if (cache[docId]) return cache[docId];
  var src = DocumentApp.openById(docId);
  var list = src.getBody().getImages().map(function (im) {
    var blob = im.getBlob();
    return { blob: blob, w: im.getWidth(), h: im.getHeight(), hash: md5_10(blob.getBytes()) };
  });
  cache[docId] = list;
  return list;
}

function md5_10(bytes) {
  var d = Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, bytes);
  var hex = d.map(function (b) { return ('0' + ((b + 256) % 256).toString(16)).slice(-2); }).join('');
  return hex.substring(0, 10);
}

/**
 * Maintenance helper (run from the script editor, View > Logs):
 * opens every doc referenced by MODELS and reports the ones that are missing,
 * empty, or whose configured hashes no longer match any drawing in them.
 * Run this after anyone re-exports a QC sheet — generatePacket() refuses any
 * packet that includes a group with stale hashes.
 */
function debugCheckDocs() {
  var bad = 0;
  Object.keys(MODELS).forEach(function (m) {
    MODELS[m].groups.forEach(function (g) {
      var where = m + ' / ' + g.label;
      var imgs = [];
      var broke = false;
      docIds(g).forEach(function (id) {
        var part;
        try {
          part = DocumentApp.openById(id).getBody().getImages();
        } catch (e) {
          Logger.log('MISSING  %s -> %s (%s)', where, id, e.message);
          bad++; broke = true;
          return;
        }
        if (!part.length) {
          Logger.log('EMPTY    %s -> %s has no drawings', where, id);
          bad++; broke = true;
          return;
        }
        imgs = imgs.concat(part);
      });
      if (broke || !imgs.length) return;
      if (g.hashes) {
        var have = imgs.map(function (im) { return md5_10(im.getBlob().getBytes()); });
        var missing = g.hashes.filter(function (h) { return have.indexOf(h) === -1; });
        if (missing.length === g.hashes.length) {
          Logger.log('STALE    %s -> none of its %s hashes match the %s drawings in the doc',
                     where, g.hashes.length, imgs.length);
          bad++;
        } else if (missing.length) {
          Logger.log('PARTIAL  %s -> %s of %s hashes gone: %s',
                     where, missing.length, g.hashes.length, missing.join(', '));
          bad++;
        }
      }
    });
  });
  Logger.log(bad ? bad + ' group(s) need attention' : 'All groups resolve cleanly.');
}

/**
 * Maintenance helper (run from the script editor, View > Logs):
 * prints every image hash in every configured doc, so the hash maps
 * can be updated when drawings change.
 */
function debugListHashes() {
  var seen = {};
  Object.keys(MODELS).forEach(function (m) {
    MODELS[m].groups.forEach(function (g) {
      docIds(g).forEach(function (id) {
        if (seen[id]) return;
        seen[id] = true;
        var src = DocumentApp.openById(id);
        Logger.log('--- %s (%s)', src.getName(), id);
        src.getBody().getImages().forEach(function (im, i) {
          Logger.log('%s: %s  (%sx%s)', i, md5_10(im.getBlob().getBytes()), im.getWidth(), im.getHeight());
        });
      });
    });
  });
}
