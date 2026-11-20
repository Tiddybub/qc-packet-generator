# QC Packet Generator

A Google Apps Script web app used at Vantopia, a camper-van kit maker, to build the
quality-control paperwork for each customer order. You pick a customer, a van model and the
modules that were ordered, and it assembles a Google Doc of the matching CNC cut drawings
and saves it in that customer's Drive folder. The shop floor uses the packet to check cut
parts against what was actually ordered.

## Features

- **Cover page** with the customer, model, a large DUALLY banner when applicable, the wall
  material, and a title line listing every module ordered.
- **One drawing per page**, each with a bold header saying exactly what is on it
  (`Customer — Module — ACM — DUALLY`).
- **Seven van models** (Sprinter 144 / 170 / 170 EXT, Transit Long / 148 EXT,
  Promaster 136 / 159), each with its own module checkboxes and default kit.
- **Layout conflicts**: a raised bed and a dinette use the same floor space, so ticking
  one greys out the other in the form, and the server refuses the combination as well.
- **Beadboard / ACM toggle**: both materials share the same drawings, so the material is
  a label. Wall pages carry the suffix; the cover states it once.
- **New or existing folder**: create (or reuse) a folder named after the customer, or add
  a packet to an existing folder picked from a dropdown.
- **Stale-drawing guard**: drawings are matched by checksum. If a QC sheet is re-exported
  and a drawing no longer matches, the packet is refused with a list of what to fix,
  rather than built short or with the wrong pages.
- **Final checklist page** of hardware and extras to verify before shipping.

## Stack

- Google Apps Script (V8 runtime): `HtmlService`, `DocumentApp`, `DriveApp`
- Plain HTML/CSS/JS front end in a single `Index.html`
- [clasp](https://github.com/google/clasp) for pushing and deploying
- Node.js for the offline checks in `tools/`

## Setup

```bash
npm install -g @google/clasp
clasp login
cp .clasp.json.example .clasp.json          # put your script id in it
cp src/Config.example.js src/Config.js      # fill in folder id, sign-in, doc ids
```

`clasp push` needs the Apps Script API switched on at
https://script.google.com/home/usersettings.

`.clasp.json`, `~/.clasprc.json` and `src/Config.js` are gitignored. `.claspignore` keeps
`Config.example.js` out of the pushed project so it cannot override the real config.

## Deploying

```bash
clasp push                                            # updates the code, not the live app
clasp deploy -i <DEPLOYMENT_ID> -d "what changed"     # makes it live
```

Always deploy with `-i` against the existing deployment. Leaving it off creates a second
deployment with a different URL. `clasp deployments` lists what exists.

The web app runs as the deploying user with access set to "Anyone", so a shop tablet can
open it without a Google account. A shared username and password (from `Config.js`,
checked server-side) gates the form; treat it as a convenience gate, not real security.

## Configuration

### `src/Config.js`

| Name | Purpose |
|---|---|
| `CUSTOMERS_FOLDER_ID` | Drive folder that holds one sub-folder per customer |
| `APP_USERNAME`, `APP_PASSWORD` | Shared sign-in for the form (case-insensitive) |
| `DOC_IDS` | Google Doc id of each QC sheet, keyed by the names used in `MODELS` |

Apps Script shares one global scope across files, so these are plain top-level `var`s.
`Code.js` only reads them inside functions, so file load order does not matter.

### `MODELS` in `src/Code.js`

Each model has a list of groups. One group is one checkbox and one labelled set of drawings:

```js
{ label:  'Walls (CB)',
  doc:    'TL_WALLS',        // key into DOC_IDS, or an array of keys
  hashes: null,              // null = every drawing in the sheet
  def:    true,              // ticked by default
  wall:   true,              // gets the BEADBOARD / ACM suffix
  kind:   undefined }        // 'rb' or 'dinette' for conflicting groups
```

- `label` is both the printed header and the value the form sends back, so rename it
  everywhere at once.
- `doc` can be an array when one checkbox covers drawings from more than one sheet (the
  Promaster walls also pull the door panel sheet). Pages follow the listed order.
- `hashes` is a list of 10-character MD5 prefixes of the image bytes, used to pick
  specific drawings out of a shared sheet.

`CONFLICTS` lists `kind` pairs that cannot share a packet. To add another exclusive pair,
tag the groups with a new `kind` and add a row; the form reads the rules from
`getConfig()`.

`CHECKLIST` is the last page. Lines starting with `-` are items; `*` marks optional ones.

## Part codes

The letters in parentheses on each label are the part codes engraved into the panels.
The first letter is the model series, the second the module:

| 1st | Series | 2nd | Module |
|---|---|---|---|
| A | Sprinter shared cabinetry / closet | A | Floors |
| B | Sprinter 144 walls and floors | B | Walls |
| C | Transit Long | C | Cabinetry |
| D | Transit 148 EXT | D | Closet |
| E | Sprinter 170 EXT | F | Furniture / island |
| F | Promaster misc | Q | Toilet closet |
| H | Promaster 136 | | |
| I | Promaster 159 | | |

`BB` is never used on a label because it reads as "beadboard" on the shop floor. Labels
with no code are deliberate: where the drawings themselves disagree, no code is printed
rather than a wrong one.

## Checks

Offline, no Drive access (Apps Script globals are stubbed):

```bash
node tools/check-config.js   # raised bed / dinette rule, form contract, label wording, config audit
node tools/check-cover.js    # runs generatePacket() against stubs and prints the cover page
```

Both use `src/Config.js` if it exists, otherwise `src/Config.example.js`.

From the Apps Script editor (needs Drive access):

- `debugCheckDocs()` reports any configured sheet that is missing, empty, or whose hashes
  no longer match.
- `debugListHashes()` prints the hash of every drawing in every configured sheet, for
  updating `MODELS` after a sheet is re-exported.

## Project structure

```
src/appsscript.json     manifest: runtime, web app access
src/Code.js             server code: MODELS, packet builder, maintenance helpers
src/Config.example.js   config template (copy to Config.js)
src/Index.html          front end: sign-in, order form, results
tools/check-config.js   offline config and rule checks
tools/check-cover.js    offline packet build with stubbed Drive/Docs
.clasp.json.example     clasp project template
.claspignore            keeps the config template out of clasp push
```
