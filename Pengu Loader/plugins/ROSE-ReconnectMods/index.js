/**
 * @name Rose-ReconnectMods
 * @author Rose Team
 * @description Reconnect screen: choose which of this game's mods to disable before you reconnect
 */
(function initRoseReconnectMods() {
  "use strict";

  const LOG_PREFIX = "[Rose-ReconnectMods]";
  const BUTTON_CLASS = "rose-reconnect-mods";
  const MENU_ID = "rose-reconnect-mods-menu";
  const ALL = "all"; // the "All Rose mods" row: what Rose's one button did (stop-injection)
  const POLL_MS = 1000;
  const STATUS = {
    applying: "Turning them off... wait before you press Reconnect",
    ready: "Done: press Reconnect",
    failed: "Couldn't turn them all off (see Rose's log). Tick All Rose mods to play without mods",
    "game-running": "The game is still running: close it first, then press again",
    unknown: "Those mods are not on in this game",
  };

  let bridge = null;
  let button = null; // Rose's button on the reconnect screen
  let menu = null; // the open drop-down
  let state = null; // Rose's last answer
  let ticked = new Set(); // ids ticked in the drop-down (ALL for the last row)
  let allOff = false; // "All Rose mods" was applied in this game
  let timer = null;

  function log(message) {
    console.log(`${LOG_PREFIX} ${message}`);
  }

  function waitForBridge() {
    return new Promise((resolve, reject) => {
      let waited = 0;
      const check = () => {
        if (window.__roseBridge) return resolve(window.__roseBridge);
        waited += 50;
        if (waited >= 10000) return reject(new Error("Bridge not available"));
        setTimeout(check, 50);
      };
      check();
    });
  }

  // Ask Rose for this game's mods; with data.disable (a list of ids) it also turns those off
  function askRose(data) {
    return new Promise((resolve, reject) => {
      const requestId = "reconnect_" + Date.now() + "_" + Math.random().toString(36).slice(2);
      const done = (finish, value) => {
        bridge.unsubscribe("reconnect-mods-response", onAnswer);
        clearTimeout(waiting);
        finish(value);
      };
      const onAnswer = (msg) => {
        if (msg.requestId === requestId) done(resolve, msg);
      };
      const waiting = setTimeout(() => done(reject, new Error("Rose didn't answer")), 10000);
      bridge.subscribe("reconnect-mods-response", onAnswer);
      bridge.send({ ...data, type: "reconnect-mods", requestId: requestId });
    });
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text; // mod names come from files: always as text, never as HTML
    return node;
  }

  function closeMenu() {
    clearTimeout(timer);
    if (menu) menu.remove();
    menu = null;
  }

  async function refresh(data) {
    clearTimeout(timer);
    try {
      state = await askRose(data || {});
    } catch (e) {
      state = { active: true, mods: [], status: "", error: e.message };
    }
    if (!menu) return;
    draw();
    // Rose reads the mods and applies a choice in the game session's own thread: ask until it is done
    if (state.active && (state.mods === null || state.status === "applying")) timer = setTimeout(refresh, POLL_MS);
  }

  function row(id, name, off, locked) {
    const label = el("label", "rose-reconnect-row" + (off ? " rose-reconnect-off" : "") + (id === ALL ? " rose-reconnect-all" : ""));
    const box = el("input");
    box.type = "checkbox";
    box.checked = off || ticked.has(id);
    box.disabled = off || locked;
    box.addEventListener("change", () => {
      if (box.checked) ticked.add(id);
      else ticked.delete(id);
    });
    label.appendChild(box);
    label.appendChild(el("span", "", off ? name + " (off)" : name));
    return label;
  }

  function draw() {
    menu.textContent = "";
    menu.appendChild(el("div", "rose-reconnect-title", "Disable mods for this match"));
    if (allOff || !state.active) {
      menu.appendChild(el("div", "rose-reconnect-status", allOff ? "All Rose mods are off: press Reconnect" : "Rose's mods are already off for this match"));
      return;
    }
    if (state.mods === null) {
      menu.appendChild(el("div", "rose-reconnect-status", "Reading this game's mods..."));
      return;
    }
    const applying = state.status === "applying";
    for (const mod of state.mods) menu.appendChild(row(mod.id, mod.name, mod.off, applying));
    menu.appendChild(row(ALL, "All Rose mods", false, applying));
    const apply = el("button", "rose-reconnect-apply", "Disable selected");
    apply.disabled = applying;
    apply.addEventListener("click", applyChoice);
    menu.appendChild(apply);
    const text = state.error || STATUS[state.status] || "";
    if (text) menu.appendChild(el("div", "rose-reconnect-status", text));
  }

  function applyChoice() {
    if (!ticked.size) return;
    if (ticked.has(ALL)) {
      bridge.send({ type: "stop-injection" }); // as Rose's one button did: no mods at all for this match
      allOff = true;
      draw();
      return;
    }
    const ids = [...ticked];
    ticked = new Set();
    refresh({ disable: ids });
  }

  function toggleMenu() {
    if (menu) return closeMenu();
    menu = el("div");
    menu.id = MENU_ID;
    // opens upwards from the button, over the reconnect screen
    const box = button.getBoundingClientRect();
    menu.style.left = Math.round(box.left) + "px";
    menu.style.bottom = Math.round(window.innerHeight - box.top + 6) + "px";
    document.body.appendChild(menu);
    state = { active: true, mods: null, status: "" };
    draw();
    refresh();
  }

  // The client reuses (and detaches) the reconnect screen: add the button once, close the menu when it is gone
  function addButton() {
    const container = document.querySelector(".reconnect-button-container");
    if (!container) {
      if (menu) closeMenu();
      return;
    }
    if (container.querySelector("." + BUTTON_CLASS)) return;
    button = document.createElement("lol-uikit-flat-button");
    button.className = BUTTON_CLASS;
    button.setAttribute("margin-right", "10px");
    button.textContent = "Disable mods ▾";
    button.title = "Choose which of this game's mods to turn off, then reconnect (use this if a mod crashes your game)";
    button.addEventListener("click", toggleMenu);
    container.appendChild(button);
  }

  // A new game starts with every mod on again
  function onPhase(payload) {
    if (["InProgress", "Reconnect", "GameStart"].includes(payload && payload.phase)) return;
    allOff = false;
    ticked = new Set();
    closeMenu();
  }

  const STYLE = `
    .reconnect-button-container .rose-stop-injection { display: none !important; }
    #${MENU_ID} { position: fixed; z-index: 10000; min-width: 260px; max-width: 420px; max-height: 60vh; overflow-y: auto; padding: 10px 12px;
      background: #010a13; border: 1px solid #785a28; color: #f0e6d2; font-family: "LoL Display", "Beaufort for LOL", sans-serif; font-size: 12px; }
    #${MENU_ID} .rose-reconnect-title { margin-bottom: 6px; color: #c8aa6e; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }
    #${MENU_ID} .rose-reconnect-row { display: flex; align-items: center; gap: 8px; padding: 3px 0; cursor: pointer; }
    #${MENU_ID} .rose-reconnect-off { color: #5b5a56; cursor: default; }
    #${MENU_ID} .rose-reconnect-all { margin-top: 4px; padding-top: 6px; border-top: 1px solid #1e2328; }
    #${MENU_ID} .rose-reconnect-apply { margin-top: 8px; padding: 5px 12px; background: #1e2328; border: 1px solid #c8aa6e; color: #cdbe91; cursor: pointer; font: inherit; }
    #${MENU_ID} .rose-reconnect-apply:disabled { opacity: 0.5; cursor: default; }
    #${MENU_ID} .rose-reconnect-status { margin-top: 6px; color: #0acbe6; }
  `;

  async function init() {
    try {
      bridge = await waitForBridge();
    } catch (e) {
      log(`Not started: ${e.message}`);
      return;
    }
    // Rose's one "Disable Rose mods" button is hidden by the style: it is the last row of the drop-down now
    const style = el("style");
    style.textContent = STYLE;
    document.head.appendChild(style);
    bridge.subscribe("phase-change", onPhase);
    addButton();
    new MutationObserver(addButton).observe(document.body, { childList: true, subtree: true });
    log("Started");
  }

  init();
})();
