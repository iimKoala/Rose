// ROSE-OtherSkins: which players get a row, and what a row's list offers.
//   node --test test/other_skins_ui.test.cjs
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

// The plugin hands these out when it is loaded by node (in the client there is no "module")
const panel = require(path.join(__dirname, "..", "Pengu Loader", "plugins", "ROSE-OtherSkins", "index.js"));

test("the other players' champions are listed, teammates first, never the user's own", () => {
  const session = {
    localPlayerCellId: 2,
    myTeam: [{ cellId: 0, championId: 103 }, { cellId: 1, championId: 0 }, { cellId: 2, championId: 1 }],
    theirTeam: [{ cellId: 5, championId: 91 }, { cellId: 6, championId: 0 }, { cellId: 7, championId: 126 }],
  };
  assert.deepEqual(panel.readSession(session), [
    { championId: 103, enemy: false },
    { championId: 91, enemy: true },
    { championId: 126, enemy: true },
  ]);
});

test("a champion both teams play gets one row, and a mirror of the user's champion gets none", () => {
  const session = {
    localPlayerCellId: 0,
    myTeam: [{ cellId: 0, championId: 1 }, { cellId: 1, championId: 99 }],
    theirTeam: [{ cellId: 5, championId: 99 }, { cellId: 6, championId: 1 }],
  };
  assert.deepEqual(panel.readSession(session), [{ championId: 99, enemy: false }]);
  assert.deepEqual(panel.readSession({}), []);
});

test("a row's list offers their own skin, no skin, Rose's skins, then the user's custom skins", () => {
  const champion = {
    skins: [{ id: 103001, name: "Dynasty Ahri" }],
    mods: [{ name: "<b>Star</b> Ahri", path: "skins/103000/Star: Ahri.fantome" }],
    choice: { kind: "own" },
  };
  assert.deepEqual(panel.optionsFor(champion), [
    { value: "own", label: "Their own skin", group: "" },
    { value: "default", label: "No skin (default look)", group: "" },
    { value: "skin:103001", label: "Dynasty Ahri", group: "Skins" },
    { value: "custom:skins/103000/Star: Ahri.fantome", label: "<b>Star</b> Ahri", group: "Your custom skins" },
  ]);
  assert.equal(panel.labelOf(champion), "Their own skin");
  assert.equal(panel.labelOf({ ...champion, choice: { kind: "skin", skinId: 103001, modPath: "" } }), "Dynasty Ahri");
  // a pick that is no longer offered (its file was deleted) reads as their own skin
  assert.equal(panel.labelOf({ ...champion, choice: { kind: "skin", skinId: 103999, modPath: "" } }), "Their own skin");
});

test("a pick goes to Rose and comes back as the same pick", () => {
  for (const choice of [
    { kind: "own", skinId: 0, modPath: "" },
    { kind: "default", skinId: 0, modPath: "" },
    { kind: "skin", skinId: 103001, modPath: "" },
    { kind: "custom", skinId: 0, modPath: "skins/103000/Star: Ahri.fantome" }, // a colon in the name stays in the path
  ]) {
    assert.deepEqual(panel.parseValue(panel.valueOf(choice)), choice);
  }
  assert.equal(panel.valueOf(undefined), "own");
});
