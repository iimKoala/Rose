/**
 * @name Rose-OtherSkins
 * @author Rose Team
 * @description Champ select: pick the skin another player's champion shows on your screen
 */
(function initRoseOtherSkins() {
  "use strict";

  const LOG_PREFIX = "[Rose-OtherSkins]";
  const PANEL_ID = "rose-other-skins-panel";
  const POLL_MS = 1500;
  const POSITION_KEY = "rose-other-skins-position";
  const COLLAPSED_KEY = "rose-other-skins-collapsed";
  const OWN = "own"; // the player's own skin: Rose changes nothing
  const DEFAULT = "default"; // no skin: the champion's default look
  const SKIN = "skin"; // a skin Rose has
  const CUSTOM = "custom"; // one of the user's custom skins

  let bridge = null;
  let players = []; // the other players' picks champ select shows now: [{ championId, enemy }]
  const champions = {}; // champion id -> { name, skins: [{ id, name }], mods: [{ name, path }], choice, note }
  let open = 0; // the champion whose list is open
  let collapsed = false;
  let position = null; // where the user dragged the panel: { left, top } in pixels; null = the default place

  function log(message) {
    console.log(`${LOG_PREFIX} ${message}`);
  }

  // The other players' champions, teammates first. A champion both teams play is listed once: a pick is for
  // the champion, so it covers every player on it. The user's own champion is never listed.
  function readSession(session) {
    const me = (session.myTeam || []).find((player) => player.cellId === session.localPlayerCellId);
    const mine = me ? me.championId : 0;
    const seen = [];
    const add = (player, enemy) => {
      const id = player.championId;
      if (id > 0 && id !== mine && !seen.some((other) => other.championId === id)) seen.push({ championId: id, enemy: enemy });
    };
    (session.myTeam || []).filter((player) => player !== me).forEach((player) => add(player, false));
    (session.theirTeam || []).forEach((player) => add(player, true));
    return seen;
  }

  // A pick as one text, for the list's rows: "own", "default", "skin:103015", "custom:skins/103000/Name.fantome"
  function valueOf(choice) {
    if (!choice || choice.kind === OWN) return OWN;
    if (choice.kind === SKIN) return `${SKIN}:${choice.skinId}`;
    if (choice.kind === CUSTOM) return `${CUSTOM}:${choice.modPath}`;
    return DEFAULT;
  }

  function parseValue(value) {
    const at = value.indexOf(":");
    const kind = at < 0 ? value : value.slice(0, at);
    const rest = at < 0 ? "" : value.slice(at + 1);
    return { kind: kind, skinId: kind === SKIN ? Number(rest) : 0, modPath: kind === CUSTOM ? rest : "" };
  }

  // What a champion's list offers, in its order: [{ value, label, group }]
  function optionsFor(champion) {
    const options = [
      { value: OWN, label: "Their own skin", group: "" },
      { value: DEFAULT, label: "No skin (default look)", group: "" },
    ];
    for (const skin of champion.skins || []) options.push({ value: `${SKIN}:${skin.id}`, label: skin.name, group: "Skins" });
    for (const mod of champion.mods || []) options.push({ value: `${CUSTOM}:${mod.path}`, label: mod.name, group: "Your custom skins" });
    return options;
  }

  function labelOf(champion) {
    const value = valueOf(champion.choice);
    const found = optionsFor(champion).find((option) => option.value === value);
    return found ? found.label : "Their own skin";
  }

  // What the test reads (node --test test/other_skins_ui.test.cjs); in the client there is no "module"
  if (typeof module === "object" && module && module.exports) {
    module.exports = { readSession, valueOf, parseValue, optionsFor, labelOf };
    return;
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

  function askRose(type, data) {
    return new Promise((resolve, reject) => {
      const requestId = "others_" + Date.now() + "_" + Math.random().toString(36).slice(2);
      const done = (finish, value) => {
        bridge.unsubscribe(`${type}-response`, onAnswer);
        clearTimeout(timer);
        finish(value);
      };
      const onAnswer = (msg) => {
        if (msg.requestId === requestId) done(resolve, msg);
      };
      const timer = setTimeout(() => done(reject, new Error("Rose didn't answer")), 10000);
      bridge.subscribe(`${type}-response`, onAnswer);
      bridge.send({ ...data, type: type, requestId: requestId });
    });
  }

  async function client(path) {
    const response = await fetch(path);
    return response.ok ? response.json() : null;
  }

  // A champion's name and skin names from the client, and from Rose which of them it has, the user's custom
  // skins of that champion, and what is picked now
  async function loadChampion(id) {
    const champion = { name: "", skins: [], mods: [], choice: { kind: OWN }, note: "Reading its skins..." };
    champions[id] = champion;
    try {
      const data = (await client(`/lol-game-data/assets/v1/champions/${id}.json`)) || {};
      const names = {};
      for (const skin of data.skins || []) names[skin.id] = skin.name;
      champion.name = data.name || `Champion ${id}`;
      const answer = await askRose("other-skins-list", { championIds: [id] });
      const mine = (answer.champions || {})[id] || { skins: [], mods: [], choice: { kind: OWN } };
      champion.skins = mine.skins.map((skinId) => ({ id: skinId, name: names[skinId] || `Skin ${skinId % 1000}` }));
      champion.mods = mine.mods;
      champion.choice = mine.choice;
      champion.note = "";
    } catch (e) {
      champion.name = champion.name || `Champion ${id}`;
      champion.note = e.message;
    }
    render();
  }

  async function pick(id, value) {
    const champion = champions[id];
    if (!champion) return;
    open = 0;
    champion.note = "Saving...";
    render();
    try {
      const answer = await askRose("other-skin-set", { championId: id, ...parseValue(value) });
      champion.choice = answer.choice || { kind: OWN };
      champion.note = answer.ok ? "" : "Rose could not use that skin";
    } catch (e) {
      champion.note = e.message;
    }
    render();
  }

  async function poll() {
    try {
      const phase = await client("/lol-gameflow/v1/gameflow-phase");
      const session = phase === "ChampSelect" ? await client("/lol-champ-select/v1/session") : null;
      if (!session) {
        // Champ select is over. The picks stay in Rose for the game that starts; the next champ select
        // starts without any (Rose forgets them there), so nothing is kept here either
        players = [];
        for (const id of Object.keys(champions)) delete champions[id];
        open = 0;
        render();
        return;
      }
      const seen = readSession(session);
      // A champion nobody plays any more (a swap, another pick) loses its pick
      for (const old of players) {
        const champion = champions[old.championId];
        if (!seen.some((player) => player.championId === old.championId)) {
          if (champion && champion.choice.kind !== OWN) askRose("other-skin-set", { championId: old.championId, kind: OWN }).catch(() => {});
          delete champions[old.championId];
        }
      }
      const changed = seen.map((player) => player.championId).join() !== players.map((player) => player.championId).join();
      players = seen;
      for (const player of seen) if (!champions[player.championId]) loadChampion(player.championId);
      if (changed) render();
    } catch (e) {
      log(`Champ select read failed: ${e.message}`);
    }
  }

  function place(panel) {
    if (!position) return;
    panel.style.left = position.left + "px";
    panel.style.top = position.top + "px";
    panel.style.right = "auto"; // its default place is against the right edge
  }

  function remember(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      log(`Not saved: ${e.message}`);
    }
  }

  // Drag the panel by its title bar; the place is remembered
  function startDrag(event, panel) {
    if (event.target.tagName === "BUTTON") return;
    const box = panel.getBoundingClientRect();
    const grabX = event.clientX - box.left;
    const grabY = event.clientY - box.top;
    const move = (e) => {
      position = {
        left: Math.min(Math.max(0, e.clientX - grabX), window.innerWidth - 60),
        top: Math.min(Math.max(0, e.clientY - grabY), window.innerHeight - 30),
      };
      place(panel);
    };
    const stop = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", stop);
      remember(POSITION_KEY, position);
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", stop);
    event.preventDefault();
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text; // a custom skin's name comes from its file: always as text, never as HTML
    return node;
  }

  // The list under a player's row. Built from plain elements, as the reconnect screen's: nothing here relies
  // on the client drawing a native drop-down
  function list(id, champion) {
    const box = el("div", "rose-others-list");
    const current = valueOf(champion.choice);
    let group = "";
    for (const option of optionsFor(champion)) {
      if (option.group !== group) {
        group = option.group;
        box.appendChild(el("div", "rose-others-group", group));
      }
      const line = el("button", "rose-others-option" + (option.value === current ? " rose-others-on" : ""), option.label);
      line.addEventListener("click", () => pick(id, option.value));
      box.appendChild(line);
    }
    return box;
  }

  function render() {
    let panel = document.getElementById(PANEL_ID);
    if (!players.length) {
      if (panel) panel.remove();
      return;
    }
    if (!panel) {
      panel = el("div");
      panel.id = PANEL_ID;
      place(panel);
      document.body.appendChild(panel);
    }
    // Drawing again must not scroll an open list back to its top
    const oldList = panel.querySelector(".rose-others-list");
    const scrolled = oldList ? oldList.scrollTop : 0;
    panel.textContent = "";
    panel.className = collapsed ? "rose-others-collapsed" : "";

    const head = el("div", "rose-others-head");
    head.addEventListener("mousedown", (event) => startDrag(event, panel));
    head.appendChild(el("span", "rose-others-title", "Other players' skins"));
    const toggle = el("button", "rose-others-button", collapsed ? "+" : "–");
    toggle.addEventListener("click", () => {
      collapsed = !collapsed;
      remember(COLLAPSED_KEY, collapsed);
      render();
    });
    head.appendChild(toggle);
    panel.appendChild(head);
    if (collapsed) return;

    for (const player of players) {
      const champion = champions[player.championId];
      if (!champion) continue;
      const row = el("div", "rose-others-row");
      const image = el("img", "rose-others-icon" + (player.enemy ? " rose-others-enemy" : ""));
      image.src = `/lol-game-data/assets/v1/champion-icons/${player.championId}.png`;
      row.appendChild(image);
      row.appendChild(el("span", "rose-others-name", champion.name));
      const picked = el("button", "rose-others-pick" + (champion.choice.kind !== OWN ? " rose-others-on" : ""), labelOf(champion) + " ▾");
      picked.addEventListener("click", () => {
        open = open === player.championId ? 0 : player.championId;
        render();
      });
      row.appendChild(picked);
      panel.appendChild(row);
      if (champion.note) panel.appendChild(el("div", "rose-others-note", champion.note));
      if (open === player.championId) panel.appendChild(list(player.championId, champion));
    }
    panel.appendChild(el("div", "rose-others-note", "Only you see these. A pick covers every player on that champion."));
    const newList = panel.querySelector(".rose-others-list");
    if (newList) newList.scrollTop = scrolled;
  }

  const STYLE = `
    #${PANEL_ID} { position: fixed; top: 96px; right: 16px; width: 300px; z-index: 9000;
      background: #010a13; border: 1px solid #785a28; color: #f0e6d2; font: 12px "LoL Display", "Segoe UI", sans-serif; padding: 8px 10px; }
    #${PANEL_ID}.rose-others-collapsed { width: 190px; }
    #${PANEL_ID} .rose-others-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; cursor: move; user-select: none; }
    #${PANEL_ID} .rose-others-title { color: #c8aa6e; letter-spacing: 0.05em; text-transform: uppercase; font-size: 11px; }
    #${PANEL_ID} .rose-others-button { background: #1e2328; border: 1px solid #785a28; color: #c8aa6e; cursor: pointer; min-width: 26px; height: 24px; }
    #${PANEL_ID} .rose-others-row { display: flex; align-items: center; gap: 6px; margin-top: 6px; }
    #${PANEL_ID} .rose-others-icon { width: 24px; height: 24px; border: 1px solid #0ac8b9; }
    #${PANEL_ID} .rose-others-icon.rose-others-enemy { border-color: #e84057; }
    #${PANEL_ID} .rose-others-name { width: 78px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    #${PANEL_ID} .rose-others-pick { flex: 1; min-width: 0; height: 24px; background: #1e2328; border: 1px solid #3c3c41; color: #a09b8c;
      cursor: pointer; font: inherit; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    #${PANEL_ID} .rose-others-pick:hover, #${PANEL_ID} .rose-others-button:hover { border-color: #c8aa6e; color: #f0e6d2; }
    #${PANEL_ID} .rose-others-pick.rose-others-on { border-color: #c8aa6e; color: #f0e6d2; }
    #${PANEL_ID} .rose-others-list { max-height: 220px; overflow-y: auto; margin-top: 2px; border: 1px solid #785a28; background: #0a1428; }
    #${PANEL_ID} .rose-others-group { padding: 4px 8px 2px; color: #c8aa6e; font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
    #${PANEL_ID} .rose-others-group:empty { display: none; }
    #${PANEL_ID} .rose-others-option { display: block; width: 100%; padding: 4px 8px; background: none; border: 0; color: #f0e6d2;
      cursor: pointer; font: inherit; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    #${PANEL_ID} .rose-others-option:hover { background: #1e2d3d; }
    #${PANEL_ID} .rose-others-option.rose-others-on { color: #c8aa6e; }
    #${PANEL_ID} .rose-others-note { margin-top: 6px; color: #a09b8c; font-size: 11px; }
  `;

  async function init() {
    try {
      bridge = await waitForBridge();
    } catch (e) {
      log(`Not started: ${e.message}`);
      return;
    }
    try {
      const saved = JSON.parse(localStorage.getItem(POSITION_KEY) || "null");
      if (saved && typeof saved.left === "number" && typeof saved.top === "number") position = saved;
      collapsed = JSON.parse(localStorage.getItem(COLLAPSED_KEY) || "false") === true;
    } catch (e) {
      position = null;
    }
    const style = el("style");
    style.textContent = STYLE;
    document.head.appendChild(style);
    setInterval(poll, POLL_MS);
    log("Started");
  }

  init();
})();
