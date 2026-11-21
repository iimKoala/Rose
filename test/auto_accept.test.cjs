// ROSE-AutoAccept: when the match found window is accepted, and the top bar button that turns it on and off.
//   node --test test/auto_accept.test.cjs
// No client: the plugin runs here against a stand-in page, storage and client API.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const FILE = path.join(__dirname, "..", "Pengu Loader", "plugins", "ROSE-AutoAccept", "index.js");
const PHASE = "/lol-gameflow/v1/gameflow-phase";
const READY_CHECK = "/lol-matchmaking/v1/ready-check";
const FOUND = { state: "InProgress", playerResponse: "None" };

// What the plugin hands out when node loads it (in the client there is no "module")
const pure = require(FILE);

class El {
  constructor() {
    Object.assign(this, { id: "", className: "", style: {}, children: [], handlers: {}, textContent: "" });
  }
  setAttribute() {}
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  addEventListener(name, handler) {
    this.handlers[name] = handler;
  }
  find(wanted) {
    for (const child of this.children) {
      const found = wanted(child) ? child : child.find(wanted);
      if (found) return found;
    }
    return null;
  }
  querySelector(selector) {
    return this.find((one) => one.className.split(" ").includes(selector.slice(1)));
  }
}

// The plugin as the client runs it. *client*: {phase, check, accept} is what the client answers (they can be changed
// between ticks); *stored*: what localStorage holds (null: nothing yet); *bar*: false for a client whose top bar
// is not drawn yet
function start(client, stored = "1", bar = true) {
  const calls = [];
  const storage = stored === null ? {} : { "rose-auto-accept": stored };
  const menu = bar ? new El() : null;
  let tick = null;
  const answer = (ok, status, body) => ({ ok, status, json: async () => body });
  vm.runInNewContext(fs.readFileSync(FILE, "utf8"), {
    console: { log() {} },
    setInterval: (callback) => {
      tick = callback;
    },
    localStorage: { getItem: (key) => (key in storage ? storage[key] : null), setItem: (key, value) => (storage[key] = value) },
    document: {
      createElement: () => new El(),
      getElementById: (id) => (menu ? menu.find((one) => one.id === id) : null),
      querySelector: (selector) => (selector === ".main-nav-bar .right-nav-menu" ? menu : null),
    },
    fetch: async (url, options) => {
      calls.push(`${(options && options.method) || "GET"} ${url}`);
      if (url === PHASE) return answer(true, 200, client.phase);
      if (url === READY_CHECK) return client.check ? answer(true, 200, client.check) : answer(false, 404, {});
      if (url === READY_CHECK + "/accept") return answer(client.accept === undefined || client.accept < 300, client.accept || 204, null);
      throw new Error(`the plugin asked for ${url}`);
    },
  });
  return {
    calls,
    storage,
    menu,
    accepts: () => calls.filter((one) => one === `POST ${READY_CHECK}/accept`).length,
    async tick() {
      tick();
      await new Promise(setImmediate); // the plugin does not wait for its own look: let it finish
    },
  };
}

test("a match is accepted only when it is on, the check is running and nobody answered", () => {
  assert.equal(pure.shouldAccept(true, FOUND), true);
  assert.equal(pure.shouldAccept(false, FOUND), false);
  assert.equal(pure.shouldAccept(true, { state: "InProgress", playerResponse: "Declined" }), false);
  assert.equal(pure.shouldAccept(true, { state: "InProgress", playerResponse: "Accepted" }), false);
  assert.equal(pure.shouldAccept(true, { state: "Invalid", playerResponse: "None" }), false);
  assert.equal(pure.shouldAccept(true, null), false);
  assert.equal(pure.shouldAccept("1", FOUND), false, "only a real true is on");
});

test("it is off until the user turns it on, and then asks the client nothing", async () => {
  for (const stored of [null, "0", "true"]) {
    const plugin = start({ phase: "ReadyCheck", check: FOUND }, stored);
    await plugin.tick();
    assert.deepEqual(plugin.calls, [], `stored ${stored}`);
  }
});

test("outside a ready check only the phase is asked: the ready check would answer 404 every second", async () => {
  for (const phase of ["None", "Lobby", "Matchmaking", "ChampSelect", "InProgress"]) {
    const plugin = start({ phase, check: FOUND });
    await plugin.tick();
    assert.deepEqual(plugin.calls, [`GET ${PHASE}`], phase);
  }
});

test("a match found is accepted once, and the next one again", async () => {
  const client = { phase: "ReadyCheck", check: FOUND };
  const plugin = start(client);
  await plugin.tick();
  await plugin.tick(); // the client has not caught up yet: still "None"
  assert.equal(plugin.accepts(), 1);

  client.check = { state: "InProgress", playerResponse: "Accepted" };
  await plugin.tick();
  client.check = FOUND; // someone declined, the queue found another match
  await plugin.tick();
  assert.equal(plugin.accepts(), 2);
});

test("an accept the client refused is tried again at the next look", async () => {
  const client = { phase: "ReadyCheck", check: FOUND, accept: 500 };
  const plugin = start(client);
  await plugin.tick();
  await plugin.tick();
  assert.equal(plugin.accepts(), 2);
});

test("the user's own answer is left alone", async () => {
  const plugin = start({ phase: "ReadyCheck", check: { state: "InProgress", playerResponse: "Declined" } });
  await plugin.tick();
  assert.equal(plugin.accepts(), 0);
});

test("the top bar button shows the state and turns it on and off", async () => {
  const plugin = start({ phase: "Lobby" }, "0");
  await plugin.tick();
  const button = plugin.menu.find((one) => one.id === "rose-auto-accept-nav-item");
  assert.ok(button, "the button is in the top bar's right menu");
  const tooltip = button.querySelector(".menu-item-tooltip");
  const icon = button.querySelector(".menu-item-icon");
  assert.equal(tooltip.textContent, pure.tooltipFor(false));
  const offColor = icon.style.backgroundColor;

  button.handlers.click();
  assert.equal(plugin.storage["rose-auto-accept"], "1");
  assert.equal(tooltip.textContent, "Auto accept: on (click to turn off)");
  assert.notEqual(icon.style.backgroundColor, offColor);

  button.handlers.click();
  assert.equal(plugin.storage["rose-auto-accept"], "0");
  assert.equal(tooltip.textContent, "Auto accept: off (click to turn on)");

  await plugin.tick();
  await plugin.tick();
  assert.equal(plugin.menu.children.length, 1, "one button, however often it looks");
});

test("a client whose top bar is not drawn yet is waited for", async () => {
  const plugin = start({ phase: "Lobby" }, "1", false);
  await plugin.tick(); // must not throw
  assert.deepEqual(plugin.calls, [`GET ${PHASE}`]);
});
