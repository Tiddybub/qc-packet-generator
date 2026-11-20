/**
 * Builds a packet with DocumentApp/DriveApp stubbed out and prints what would
 * land on the cover page. No Drive access, no junk folders — it just records
 * every paragraph the code appends and the font size it set.
 *
 *   node tools/check-cover.js
 *
 * Checks that the wall material is stated exactly once on the cover.
 * Uses src/Config.js when present, otherwise src/Config.example.js.
 */
var fs = require('fs');
var path = require('path');
var vm = require('vm');

var CONFIG_SRC = fs.readFileSync((function () {
  var p = path.join(__dirname, '..', 'src', 'Config.js');
  return fs.existsSync(p) ? p : path.join(__dirname, '..', 'src', 'Config.example.js');
})(), 'utf8');
var DOC_IDS = (function () {
  var ctx = {};
  vm.createContext(ctx);
  vm.runInContext(CONFIG_SRC, ctx);
  return ctx.DOC_IDS;
})();

function makeText() {
  var t = { bold: false, size: null };
  t.setBold = function (v) { t.bold = v; return t; };
  t.setFontSize = function (v) { t.size = v; return t; };
  return t;
}

function run(payload, imagesPerDoc, perDocImages, stale, drop) {
  var opened = [];           // doc ids the code actually read
  var log = [];              // {text, size} in document order
  function para(text) {
    var entry = { text: text, size: null };
    log.push(entry);
    var t = makeText();
    var p = {
      setText: function (v) { entry.text = v; return p; },
      editAsText: function () {
        return {
          setBold: function () { return { setFontSize: function (s) { entry.size = s; } }; }
        };
      },
      appendInlineImage: function () {
        return { setWidth: function () {}, setHeight: function () {} };
      }
    };
    return p;
  }

  var firstPara = para('');
  var body = {
    setAttributes: function () {},
    getParagraphs: function () { return [firstPara]; },
    appendParagraph: function (s) { return para(s); },
    appendPageBreak: function () { log.push({ text: '--- PAGE BREAK ---', size: null }); },
    getImages: function () { return imagesFor(imagesPerDoc, null); }
  };

  // An image's bytes ARE its hash: md5_10 takes the first 10 hex chars, and the
  // stubbed computeDigest below just returns the first 5 bytes. So handing an
  // image the 5 bytes of a hash makes Code.js see exactly that hash. That lets
  // a scenario decide whether a group's hashes match (packet builds) or not
  // (packet is refused).
  function imageWithHash(hex) {
    var bytes = [];
    for (var i = 0; i < 5; i++) bytes.push(parseInt(hex.substr(i * 2, 2), 16));
    return {
      getBlob: function () { return { getBytes: function () { return bytes; } }; },
      getWidth: function () { return 600; },
      getHeight: function () { return 400; }
    };
  }

  // Default: give each doc exactly the drawings its groups ask for, so the
  // happy path builds. `n` extra unhashed drawings are added for hash-free
  // groups, which take everything in the sheet.
  function imagesFor(n, docId) {
    if (stale) {                       // nothing a group asks for is present
      return [imageWithHash('deadbeef00'), imageWithHash('deadbeef01')];
    }
    var wanted = [];
    (payload.groups || []).forEach(function (label) {
      var g = (sandbox.MODELS[payload.model].groups || [])
        .filter(function (x) { return x.label === label; })[0];
      if (!g || !g.hashes) return;
      if (sandbox.docIds(g).indexOf(docId) === -1) return;
      g.hashes.forEach(function (h) { if (wanted.indexOf(h) === -1) wanted.push(h); });
    });
    if (drop) wanted = wanted.filter(function (h) { return drop.indexOf(h) === -1; });
    var out = wanted.map(imageWithHash);
    for (var i = 0; i < n; i++) out.push(imageWithHash('aa00bb00' + (i % 10) + '0'));
    return out;
  }

  var sandbox = {
    DocumentApp: {
      Attribute: { PAGE_WIDTH: 1, PAGE_HEIGHT: 2, MARGIN_TOP: 3, MARGIN_BOTTOM: 4,
                   MARGIN_LEFT: 5, MARGIN_RIGHT: 6 },
      create: function () {
        return {
          getBody: function () { return body; },
          saveAndClose: function () {},
          getId: function () { return 'doc1'; },
          getUrl: function () { return 'https://example/doc1'; }
        };
      },
      // records which docs were opened, and can give each one a different
      // number of drawings so a multi-doc group is provably reading both
      openById: function (id) {
        opened.push(id);
        var n = (perDocImages && perDocImages[id] !== undefined)
          ? perDocImages[id] : imagesPerDoc;
        return { getBody: function () {
          return { getImages: function () { return imagesFor(n, id); } };
        } };
      }
    },
    DriveApp: {
      getFolderById: function () {
        return {
          getFoldersByName: function () { return { hasNext: function () { return false; } }; },
          createFolder: function (n) { return folderStub(n); },
          getUrl: function () { return 'https://example/folder'; },
          getName: function () { return 'stub'; },
          getId: function () { return 'fid'; }
        };
      },
      getFileById: function () { return { moveTo: function () {} }; },
      getRootFolder: function () { return sandbox.DriveApp.getFolderById(); }
    },
    Utilities: {
      DigestAlgorithm: { MD5: 'MD5' },
      computeDigest: function (alg, bytes) { return bytes.slice(0, 5); }
    },
    HtmlService: {}, Logger: { log: function () {} }
  };
  function folderStub(n) {
    return { getUrl: function () { return 'https://example/folder'; },
             getName: function () { return n; }, getId: function () { return 'fid'; } };
  }
  vm.createContext(sandbox);
  vm.runInContext(CONFIG_SRC, sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'src', 'Code.js'), 'utf8'), sandbox);
  sandbox.generatePacket(payload);

  // everything before the first page break is the cover
  var cut = log.findIndex(function (e) { return e.text === '--- PAGE BREAK ---'; });
  return { cover: log.slice(0, cut === -1 ? log.length : cut), all: log, opened: opened };
}

var fails = 0;
function scenario(name, payload) {
  var r = run(payload, 1);
  console.log('\n' + name);
  r.cover.forEach(function (e) {
    console.log('   ' + (e.size ? e.size + 'pt' : '   ') + '  ' + e.text);
  });

  var mat = payload.wallMaterial === 'ACM' ? 'ACM' : 'BEADBOARD';
  var hits = r.cover.reduce(function (n, e) {
    return n + (e.text.split(mat).length - 1);
  }, 0);
  var ok = hits === 1;
  console.log('   -> "' + mat + '" appears ' + hits + ' time(s) on the cover  ' +
              (ok ? 'PASS' : 'FAIL (want exactly 1)'));
  if (!ok) fails++;

  var title = r.cover[0];
  var titleOk = title.size === 28;
  console.log('   -> title font ' + title.size + 'pt  ' + (titleOk ? 'PASS' : 'FAIL (want 28)'));
  if (!titleOk) fails++;
}

scenario('Sprinter 144, beadboard, usual kit', {
  customer: 'Test Person', model: 'Sprinter 144',
  groups: ['144 Raised Bed', 'Floors', 'Closet (AD)', 'Walls'],
  wallMaterial: 'Beadboard', dually: false, extras: '', folderId: ''
});

scenario('Sprinter 144, ACM, dually', {
  customer: 'Test Person', model: 'Sprinter 144',
  groups: ['144 Raised Bed', 'Walls'],
  wallMaterial: 'ACM', dually: true, extras: 'No Sink', folderId: ''
});

scenario('Transit 148 EXT, ACM, both wall groups', {
  customer: 'Test Person', model: 'Transit 148 EXT',
  groups: ['148 EXT Raised Bed', 'Floors & Walls', 'Walls'],
  wallMaterial: 'ACM', dually: false, extras: '', folderId: ''
});

// no wall modules ordered -> the material should not be mentioned at all
console.log('\nSprinter 144, no wall modules ordered');
var r4 = run({ customer: 'Test Person', model: 'Sprinter 144',
               groups: ['Dinette', 'Toilet Closet (AQ1/AQ2)'],
               wallMaterial: 'ACM', dually: false, extras: '', folderId: '' }, 1);
r4.cover.forEach(function (e) { console.log('   ' + (e.size ? e.size + 'pt' : '   ') + '  ' + e.text); });
var silent = r4.cover.every(function (e) { return e.text.indexOf('ACM') === -1; });
console.log('   -> material omitted when no walls ordered  ' + (silent ? 'PASS' : 'FAIL'));
if (!silent) fails++;

// wall page headers must still name the material — that is where it identifies
// the specific drawing, so it is not a duplicate
console.log('\nWall page headers still carry the material');
var r5 = run({ customer: 'Test Person', model: 'Sprinter 144',
               groups: ['Walls', 'Floors'],
               wallMaterial: 'ACM', dually: false, extras: '', folderId: '' }, 1);
var headers = r5.all.filter(function (e) { return /Test Person — /.test(e.text); });
headers.forEach(function (h) { console.log('   ' + h.text); });
var wallHeader = headers.some(function (h) { return /Walls — ACM$/.test(h.text); });
var floorHeader = headers.some(function (h) { return /Floors$/.test(h.text); });
console.log('   -> wall header names ACM  ' + (wallHeader ? 'PASS' : 'FAIL'));
console.log('   -> non-wall header does not  ' + (floorHeader ? 'PASS' : 'FAIL'));
if (!wallHeader || !floorHeader) fails++;

// Promaster walls must pull the door panels sheet too. Give the two docs
// different drawing counts so the page total proves both were read.
console.log('\nPromaster 159 walls pulls the door panels sheet');
var WALLS = DOC_IDS.PM159_WALLS;
var PANELS = DOC_IDS.PROMASTER_DOOR_PANELS;
var r6 = run({ customer: 'Test Person', model: 'Promaster 159',
               groups: ['Walls & Ceiling (IB) — Door Panels Included'],
               wallMaterial: 'ACM', dually: false, extras: '', folderId: '' },
             1, (function () { var o = {}; o[WALLS] = 3; o[PANELS] = 2; return o; })());
// count page headers only — the cover title line also contains the label
var wallPages = r6.all.filter(function (e) {
  return /^Test Person — Walls & Ceiling/.test(e.text);
}).length;
console.log('   docs opened: ' + r6.opened.join(', '));
console.log('   drawing pages produced: ' + wallPages + ' (3 walls + 2 door panels)');
var bothRead = r6.opened.indexOf(WALLS) !== -1 && r6.opened.indexOf(PANELS) !== -1;
console.log('   -> both sheets read  ' + (bothRead ? 'PASS' : 'FAIL'));
console.log('   -> all 5 drawings printed  ' + (wallPages === 5 ? 'PASS' : 'FAIL'));
if (!bothRead || wallPages !== 5) fails++;

// --- the stale-hash failure from a real order, reproduced ---
// Sprinter 144 "Walls" and "Hex Flooring" are two hash-split groups sharing the
// doc "144 Walls". That doc was re-exported, every hash went stale, and the old
// fallback made BOTH groups print every drawing in it -- so Hex Flooring came
// out showing the walls. Simulate by giving the doc drawings whose hashes match
// nothing in MODELS.
console.log('\nStale hashes must refuse the packet, not print the wrong drawings');
var staleRun = null, staleErr = null;
try {
  staleRun = run({ customer: 'Test Person', model: 'Sprinter 144',
                   groups: ['144 Raised Bed', 'Floors', 'Closet (AD)', 'Walls'],
                   wallMaterial: 'Beadboard', dually: false, extras: '', folderId: '' },
                 2, null, true);
} catch (e) { staleErr = e; }

if (staleErr) {
  console.log('   refused, with:');
  staleErr.message.split('\n').forEach(function (l) { if (l.trim()) console.log('     ' + l); });
  var namesBoth = /Walls/.test(staleErr.message) && /Floors/.test(staleErr.message);
  var namesBed  = /144 Raised Bed/.test(staleErr.message);
  var tellsFix  = /debugListHashes/.test(staleErr.message);
  console.log('   -> names both clashing groups  ' + (namesBoth ? 'PASS' : 'FAIL'));
  console.log('   -> names the short raised bed  ' + (namesBed ? 'PASS' : 'FAIL'));
  console.log('   -> says how to fix it          ' + (tellsFix ? 'PASS' : 'FAIL'));
  if (!namesBoth || !namesBed || !tellsFix) fails++;
} else {
  var wallsPages = staleRun.all.filter(function (e) { return /— Walls/.test(e.text); }).length;
  var hexPages   = staleRun.all.filter(function (e) { return /Floors/.test(e.text); }).length;
  console.log('   -> FAIL: built anyway (' + wallsPages + ' walls pages, ' +
              hexPages + ' hex pages from the same drawings)');
  fails++;
}

// The other half of the same report: the raised bed "didn't come all the way
// in". Only some of its hashes had gone stale, so the old code printed the ones
// that still matched and dropped the rest without saying anything -- a packet
// that looks complete and isn't. Must now refuse, and say how many are missing.
console.log('\nPartly-stale hashes must refuse too, not quietly drop pages');
var partErr = null, partRun = null;
try {
  partRun = run({ customer: 'Test Person', model: 'Sprinter 144',
                  groups: ['144 Raised Bed'],
                  wallMaterial: 'Beadboard', dually: false, extras: '', folderId: '' },
                0, null, false, ['14e2e0455f', '58093af2db', 'dfb82b28dc']);
} catch (e) { partErr = e; }

if (partErr) {
  var line = partErr.message.split('\n').filter(function (l) { return /Raised Bed/.test(l); })[0];
  console.log('   refused, with: ' + (line || '').trim());
  var says3of6 = /3 of 6/.test(partErr.message);
  console.log('   -> reports 3 of 6 missing  ' + (says3of6 ? 'PASS' : 'FAIL'));
  if (!says3of6) fails++;
} else {
  var bedPages = partRun.all.filter(function (e) { return /144 Raised Bed/.test(e.text); }).length - 1;
  console.log('   -> FAIL: built anyway with only ' + bedPages + ' of 6 drawings');
  fails++;
}

// a group with no hashes at all is still allowed to take the whole sheet
console.log('\nHash-free groups still take every drawing');
var r7 = run({ customer: 'Test Person', model: 'Sprinter 170',
               groups: ['Floors'], wallMaterial: 'Beadboard',
               dually: false, extras: '', folderId: '' }, 3);
var floorPages = r7.all.filter(function (e) { return /^Test Person — Floors/.test(e.text); }).length;
console.log('   -> 3 drawings -> ' + floorPages + ' pages  ' + (floorPages === 3 ? 'PASS' : 'FAIL'));
if (floorPages !== 3) fails++;

// the server must still refuse raised bed + dinette
console.log('\nServer refuses raised bed + dinette');
try {
  run({ customer: 'T', model: 'Sprinter 144',
        groups: ['144 Raised Bed', 'Dinette'],
        wallMaterial: 'Beadboard', dually: false, extras: '', folderId: '' }, 1);
  console.log('   FAIL — it built the packet anyway');
  fails++;
} catch (e) {
  console.log('   PASS — ' + e.message);
}

console.log('\n' + (fails ? fails + ' FAILURE(S)' : 'ALL COVER CHECKS PASSED'));
process.exit(fails ? 1 : 0);
