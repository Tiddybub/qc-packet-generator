/**
 * Offline checks for src/Code.js. No Drive access — this loads the file with
 * the Apps Script globals stubbed out and exercises the pure logic:
 * the raised-bed/dinette rule, and a consistency audit of MODELS.
 *
 *   node tools/check-config.js
 *
 * Exits non-zero if a hard check fails. Audit notes are printed but do not
 * fail the run — some of them are open questions, not bugs.
 *
 * Uses src/Config.js when present, otherwise src/Config.example.js.
 */
var fs = require('fs');
var path = require('path');
var vm = require('vm');

var srcPath = path.join(__dirname, '..', 'src', 'Code.js');
var cfgPath = path.join(__dirname, '..', 'src', 'Config.js');
if (!fs.existsSync(cfgPath)) cfgPath = path.join(__dirname, '..', 'src', 'Config.example.js');
var sandbox = {
  DriveApp: {}, DocumentApp: { Attribute: {} }, HtmlService: {},
  Utilities: { DigestAlgorithm: {} }, Logger: { log: function () {} },
  console: console
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(cfgPath, 'utf8'), sandbox);
vm.runInContext(fs.readFileSync(srcPath, 'utf8'), sandbox);

var MODELS = sandbox.MODELS;
var CONFLICTS = sandbox.CONFLICTS;
var findConflict = sandbox.findConflict;
var getConfig = sandbox.getConfig;

var fails = [];
var notes = [];
function check(name, cond, detail) {
  console.log((cond ? '  PASS  ' : '  FAIL  ') + name + (detail ? '  — ' + detail : ''));
  if (!cond) fails.push(name);
}

// ---------- 1. raised bed vs dinette ----------
console.log('\nRAISED BED / DINETTE RULE');
Object.keys(MODELS).forEach(function (m) {
  var gs = MODELS[m].groups;
  var rb = gs.filter(function (g) { return g.kind === 'rb'; });
  var din = gs.filter(function (g) { return g.kind === 'dinette'; });

  check(m + ': has a raised bed group', rb.length > 0,
    rb.map(function (g) { return g.label; }).join(' + '));
  check(m + ': has a dinette group', din.length > 0,
    din.map(function (g) { return g.label; }).join(' + '));

  if (rb.length && din.length) {
    check(m + ': raised bed + dinette together is refused',
      findConflict([rb[0], din[0]]) !== null);
    check(m + ': raised bed alone is allowed',
      findConflict([rb[0]]) === null);
    check(m + ': dinette alone is allowed',
      findConflict([din[0]]) === null);
    // the whole default kit must not trip the rule
    check(m + ': default kit is allowed',
      findConflict(gs.filter(function (g) { return g.def; })) === null);
  }
});

// ---------- 2. wording ----------
console.log('\nWORDING');
var badLabels = [];
Object.keys(MODELS).forEach(function (m) {
  MODELS[m].groups.forEach(function (g) {
    if (/\bRB\b|\bRV\b/.test(g.label)) badLabels.push(m + ' / ' + g.label + '  (RB or RV)');
    if (/cabinetry/i.test(g.label)) badLabels.push(m + ' / ' + g.label + '  (cabinetry)');
  });
});
check('no label still says RB, RV or Cabinetry', badLabels.length === 0, badLabels.join('; '));

// ---------- 3. getConfig contract ----------
console.log('\nFORM CONTRACT');
var cfg = getConfig();
check('getConfig returns models + conflicts',
  !!cfg.models && Array.isArray(cfg.conflicts));
var labelsMatch = Object.keys(MODELS).every(function (m) {
  return cfg.models[m].every(function (g, i) { return g.label === MODELS[m].groups[i].label; });
});
check('every label the form sends back matches a group', labelsMatch);
var kindsSent = Object.keys(MODELS).every(function (m) {
  return cfg.models[m].every(function (g, i) {
    return (g.kind || null) === (MODELS[m].groups[i].kind || null);
  });
});
check('kind tags reach the form', kindsSent);

// ---------- 4. audit ----------
console.log('\nAUDIT');
Object.keys(MODELS).forEach(function (m) {
  var seen = {};
  MODELS[m].groups.forEach(function (g) {
    if (seen[g.label]) notes.push(m + ': duplicate checkbox label "' + g.label + '"');
    seen[g.label] = true;
  });
  var byDoc = {};
  MODELS[m].groups.forEach(function (g) {
    if (g.hashes) return;                     // hash-split groups share a doc on purpose
    sandbox.docIds(g).forEach(function (d) {
      (byDoc[d] = byDoc[d] || []).push(g.label);
    });
  });
  Object.keys(byDoc).forEach(function (d) {
    if (byDoc[d].length > 1) {
      notes.push(m + ': "' + byDoc[d].join('" and "') + '" pull every drawing from the same doc ' +
                 d + ' — ticking both duplicates those pages');
    }
  });
});

// two checkboxes in one model carrying the same part code — usually means the
// same panels can be ordered twice under two names
Object.keys(MODELS).forEach(function (m) {
  var byCode = {};
  MODELS[m].groups.forEach(function (g) {
    var code = (g.label.match(/\(([^)]+)\)/) || [])[1];
    if (code) (byCode[code] = byCode[code] || []).push(g.label);
  });
  Object.keys(byCode).forEach(function (c) {
    if (byCode[c].length > 1) {
      notes.push(m + ': "' + byCode[c].join('" and "') + '" both carry part code ' + c);
    }
  });
});

// two hash-filtered groups in one model pulling the same drawing twice
Object.keys(MODELS).forEach(function (m) {
  var gs = MODELS[m].groups;
  for (var i = 0; i < gs.length; i++) {
    for (var j = i + 1; j < gs.length; j++) {
      if (gs[i].doc !== gs[j].doc) continue;
      if (!gs[i].hashes || !gs[j].hashes) continue;
      var dup = gs[i].hashes.filter(function (h) { return gs[j].hashes.indexOf(h) !== -1; });
      if (dup.length) {
        notes.push(m + ': "' + gs[i].label + '" and "' + gs[j].label + '" share drawing(s) ' +
                   dup.join(', ') + ' — ticking both prints them twice');
      }
    }
  }
});

// same label, different doc, across models — a sign one of them is wrong
var labelDocs = {};
Object.keys(MODELS).forEach(function (m) {
  MODELS[m].groups.forEach(function (g) {
    (labelDocs[g.label] = labelDocs[g.label] || [])
      .push({ model: m, doc: sandbox.docIds(g).join('+') });
  });
});
Object.keys(labelDocs).forEach(function (l) {
  var docs = {};
  labelDocs[l].forEach(function (e) { (docs[e.doc] = docs[e.doc] || []).push(e.model); });
  if (Object.keys(docs).length > 1 && labelDocs[l].length > 1) {
    var desc = Object.keys(docs).map(function (d) {
      return docs[d].join('/') + ' -> ' + d.slice(0, 12) + '…';
    }).join(' , ');
    notes.push('label "' + l + '" points at different docs per model: ' + desc);
  }
});

// labels carrying no part code
Object.keys(MODELS).forEach(function (m) {
  MODELS[m].groups.forEach(function (g) {
    if (!/\(/.test(g.label)) notes.push('no part code on label: ' + m + ' / ' + g.label);
  });
});

if (notes.length) {
  console.log('  ' + notes.length + ' item(s) to look at:');
  notes.forEach(function (n) { console.log('    - ' + n); });
} else {
  console.log('  nothing flagged');
}

console.log('\n' + (fails.length ? fails.length + ' CHECK(S) FAILED' : 'ALL CHECKS PASSED'));
process.exit(fails.length ? 1 : 0);
