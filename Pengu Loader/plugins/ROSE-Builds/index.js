/**
 * @name Rose-Builds
 * @author Rose Team
 * @description Champ select builds from onetricks.gg: the top 3 players' runes, spells and items, imported for you
 */
(function initRoseBuilds() {
  "use strict";

  const LOG_PREFIX = "[Rose-Builds]";
  const PANEL_ID = "rose-builds-panel";
  const POLL_MS = 1500;
  const AUTO = -1; // "versus": let Rose guess the lane opponent
  const GENERAL = 0; // "versus": the player's usual build
  const LANE_NAMES = { top: "Top", jungle: "Jungle", mid: "Mid", bot: "Bot", supp: "Support" };
  const POSITION_KEY = "rose-builds-position";
  const IMPORT_PARTS = [["runes", "Runes"], ["spells", "Spells"], ["items", "Items"]]; // one button each
  const NEEDS = [["armor", "Armour"], ["magicResist", "Magic res."], ["damage", "Damage"]]; // situational items the top players build
  const ROLES = [["top", "Top"], ["jungle", "Jungle"], ["middle", "Mid"], ["bottom", "Bot"], ["utility", "Support"]]; // as champ select names them

  let bridge = null;
  let game = { championId: 0, lane: "", enemyIds: [] }; // what champ select shows now
  // where the three sets of arrows are (buildIndex 0: Rose picks the build), and the role the user picked ("": champ select's own)
  let choice = { playerIndex: 0, versus: AUTO, buildIndex: 0, lane: "" };
  let state = null; // Rose's last answer
  let busy = false;
  let again = false; // something changed while Rose was answering: ask once more
  let collapsed = false;
  let imported = {}; // part -> what Rose answered when it imported that part of the build on screen
  let position = null; // where the user dragged the panel: { left, top } in pixels; null = the default place
  const icons = { perks: {}, items: {}, spells: {} }; // id -> { name, iconPath }, from the client's own game data

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

  // Ask Rose for the panel's state; reading the site can take a few seconds
  function askRose(data) {
    return new Promise((resolve, reject) => {
      const requestId = "builds_" + Date.now() + "_" + Math.random().toString(36).slice(2);
      const done = (finish, value) => {
        bridge.unsubscribe("builds-get-response", onAnswer);
        clearTimeout(timer);
        finish(value);
      };
      const onAnswer = (msg) => {
        if (msg.requestId === requestId) done(resolve, msg);
      };
      const timer = setTimeout(() => done(reject, new Error("Rose didn't answer")), 30000);
      bridge.subscribe("builds-get-response", onAnswer);
      bridge.send({ ...data, type: "builds-get", requestId: requestId });
    });
  }

  async function client(path) {
    const response = await fetch(path);
    return response.ok ? response.json() : null;
  }

  async function loadIcons() {
    const sources = { perks: "/lol-game-data/assets/v1/perks.json", items: "/lol-game-data/assets/v1/items.json", spells: "/lol-game-data/assets/v1/summoner-spells.json" };
    for (const kind of Object.keys(sources)) {
      try {
        for (const entry of (await client(sources[kind])) || []) icons[kind][entry.id] = entry;
      } catch (e) {
        log(`No ${kind} icons: ${e.message}`);
      }
    }
  }

  // My locked champion, my lane and the enemy champions shown so far
  function readSession(session) {
    const me = (session.myTeam || []).find((player) => player.cellId === session.localPlayerCellId);
    if (!me) return { championId: 0, lane: "", enemyIds: [] };
    const picks = (session.actions || []).flat().filter((action) => action.type === "pick" && action.actorCellId === me.cellId);
    // Modes without a pick turn (ARAM) give the champion straight away
    const locked = picks.length ? picks.some((action) => action.completed) : me.championId > 0;
    return {
      championId: locked ? me.championId : 0,
      lane: me.assignedPosition || "",
      enemyIds: (session.theirTeam || []).map((player) => player.championId).filter((id) => id > 0),
    };
  }

  async function poll() {
    try {
      const phase = await client("/lol-gameflow/v1/gameflow-phase");
      const session = phase === "ChampSelect" ? await client("/lol-champ-select/v1/session") : null;
      const seen = session ? readSession(session) : { championId: 0, lane: "", enemyIds: [] };
      const newChampion = seen.championId !== game.championId;
      const changed = newChampion || seen.lane !== game.lane || seen.enemyIds.join() !== game.enemyIds.join();
      game = seen;
      if (!seen.championId) {
        state = null;
        choice.lane = ""; // the next champ select starts on its own role again
        render();
        return;
      }
      if (newChampion) choice = { playerIndex: 0, versus: AUTO, buildIndex: 0, lane: choice.lane };
      if (changed) refresh();
    } catch (e) {
      log(`Champ select read failed: ${e.message}`);
    }
  }

  // Ask Rose for the build the arrows point at. Rose imports only the parts whose button the user pressed
  // (the user, Nov 11: "it shouldn't just auto import"; Nov 13: "a button for each, rune, summoner spells, and build").
  async function refresh(parts) {
    if (busy) {
      again = true;
      return;
    }
    busy = true;
    if (!parts) imported = {}; // another build is coming on screen: nothing of it is imported yet
    render();
    const asked = game.championId;
    try {
      const answer = await askRose({ championId: game.championId, lane: choice.lane || game.lane, enemyIds: game.enemyIds, playerIndex: choice.playerIndex, versus: choice.versus, buildIndex: choice.buildIndex, import: parts || [] });
      if (asked === game.championId) {
        state = answer;
        Object.assign(imported, answer.imported || {});
      }
    } catch (e) {
      if (asked === game.championId) state = { success: false, error: e.message };
    }
    busy = false;
    render();
    if (again) {
      again = false;
      refresh();
    }
  }

  function stepPlayer(step) {
    if (!state || !state.success) return;
    const count = state.players.length;
    choice.playerIndex = (state.playerIndex + step + count) % count;
    choice.buildIndex = 0; // another player has other builds
    refresh();
  }

  // The opponent arrows go through "usual build" and every enemy that makes sense in this lane
  function stepVersus(step) {
    if (!state || !state.success) return;
    const options = [GENERAL].concat(state.opponents);
    const at = Math.max(0, options.indexOf(state.versus));
    choice.versus = options[(at + step + options.length) % options.length];
    choice.buildIndex = 0; // picking an opponent asks for the build against it again
    refresh();
  }

  // The build arrows go through "automatic" (the usual build, or the one against the opponent) and the player's
  // other builds, which the site tells apart by the first item built. A build picked here stands in for the matchup's.
  function stepBuild(step) {
    if (!state || !state.success) return;
    const count = (state.builds || []).length + 1;
    choice.buildIndex = ((state.buildIndex || 0) + step + count) % count;
    refresh();
  }

  // The role buttons: champ select's own role, unless the user picks another (a swap, or a pick for another lane)
  function pickRole(lane) {
    choice = { playerIndex: 0, versus: AUTO, buildIndex: 0, lane: lane === game.lane ? "" : lane };
    refresh();
  }

  function place(panel) {
    if (!position) return;
    panel.style.left = position.left + "px";
    panel.style.top = position.top + "px";
    panel.style.transform = "none";
  }

  // Drag the panel by its title bar (the user, Nov 11: "window should be draggable"); the place is remembered
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
      try {
        localStorage.setItem(POSITION_KEY, JSON.stringify(position));
      } catch (e) {
        log(`The panel's place was not saved: ${e.message}`);
      }
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", stop);
    event.preventDefault();
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text; // names come from a web page: always as text, never as HTML
    return node;
  }

  function arrow(label, onClick) {
    const button = el("button", "rose-builds-arrow", label);
    button.addEventListener("click", onClick);
    return button;
  }

  function icon(kind, id) {
    const entry = icons[kind][id];
    if (!entry || !entry.iconPath) return el("span", "rose-builds-missing", String(id));
    const image = el("img", "rose-builds-icon");
    image.src = entry.iconPath;
    image.title = entry.name || "";
    return image;
  }

  function row(label, nodes) {
    const line = el("div", "rose-builds-row");
    line.appendChild(el("span", "rose-builds-label", label));
    nodes.forEach((node) => line.appendChild(node));
    return line;
  }

  function championIcon(id) {
    const image = el("img", "rose-builds-icon");
    image.src = `/lol-game-data/assets/v1/champion-icons/${id}.png`;
    return image;
  }

  function render() {
    let panel = document.getElementById(PANEL_ID);
    if (!game.championId) {
      if (panel) panel.remove();
      return;
    }
    if (!panel) {
      panel = el("div");
      panel.id = PANEL_ID;
      place(panel);
      document.body.appendChild(panel);
    }
    panel.textContent = "";
    panel.className = collapsed ? "rose-builds-collapsed" : "";

    const head = el("div", "rose-builds-head");
    head.addEventListener("mousedown", (event) => startDrag(event, panel));
    head.appendChild(el("span", "rose-builds-title", "Builds · onetricks.gg"));
    const toggle = el("button", "rose-builds-arrow", collapsed ? "+" : "–");
    toggle.addEventListener("click", () => {
      collapsed = !collapsed;
      render();
    });
    head.appendChild(toggle);
    panel.appendChild(head);
    if (collapsed) return;

    const roles = el("div", "rose-builds-row");
    roles.appendChild(el("span", "rose-builds-label", "Role"));
    for (const [lane, label] of ROLES) {
      const button = el("button", "rose-builds-role" + (lane === (choice.lane || game.lane) ? " rose-builds-role-on" : ""), label);
      button.addEventListener("click", () => pickRole(lane));
      roles.appendChild(button);
    }
    panel.appendChild(roles);

    if (!state) {
      panel.appendChild(el("div", "rose-builds-note", "Reading the top players' builds..."));
      return;
    }
    if (!state.success) {
      panel.appendChild(el("div", "rose-builds-error", state.error || "No build"));
      return;
    }
    const player = state.players[state.playerIndex];
    const who = el("div", "rose-builds-who");
    who.appendChild(arrow("◀", () => stepPlayer(-1)));
    const name = el("div", "rose-builds-player");
    name.appendChild(el("div", "rose-builds-name", player.name));
    name.appendChild(el("div", "rose-builds-rank", `#${state.playerIndex + 1} of ${state.players.length} · ${player.tier} ${player.lp} LP · ${player.region} · ${LANE_NAMES[player.lane] || "?"} · ${Math.round(player.winrate)}% in ${player.games} games`));
    who.appendChild(name);
    who.appendChild(arrow("▶", () => stepPlayer(1)));
    panel.appendChild(who);

    const versus = el("div", "rose-builds-who");
    versus.appendChild(arrow("◀", () => stepVersus(-1)));
    const against = el("div", "rose-builds-versus");
    if (state.versus) {
      against.appendChild(el("span", "", "vs "));
      against.appendChild(championIcon(state.versus));
    } else {
      against.appendChild(el("span", "", state.opponents.length ? "Usual build (arrows: pick your lane opponent)" : "Usual build"));
    }
    versus.appendChild(against);
    versus.appendChild(arrow("▶", () => stepVersus(1)));
    panel.appendChild(versus);

    const others = state.builds || [];
    if (others.length) {
      const builds = el("div", "rose-builds-who");
      builds.appendChild(arrow("◀", () => stepBuild(-1)));
      const which = el("div", "rose-builds-versus");
      const picked = others[(state.buildIndex || 0) - 1];
      if (picked) {
        which.appendChild(el("span", "", `Build ${state.buildIndex} of ${others.length} · first item `));
        which.appendChild(icon("items", picked.firstItem));
        which.appendChild(el("span", "", ` · ${Math.round(picked.share * 100)}% of games`));
      } else {
        which.appendChild(el("span", "", `Automatic build (arrows: ${others.length} by first item)`));
      }
      builds.appendChild(which);
      builds.appendChild(arrow("▶", () => stepBuild(1)));
      panel.appendChild(builds);
    }

    const build = state.build;
    panel.appendChild(row("Runes", build.perks.concat(build.shards).map((id) => icon("perks", id))));
    panel.appendChild(row("Spells", build.spells.map((id) => icon("spells", id))));
    panel.appendChild(row("Start", build.startItems.map((id) => icon("items", id))));
    panel.appendChild(row("Build", build.path.concat(build.boots ? [build.boots] : []).map((id) => icon("items", id))));
    panel.appendChild(row("Skills", [el("span", "", build.skillOrder || "?")]));

    for (const [need, label] of NEEDS) {
      const items = (build.situational || {})[need] || [];
      if (items.length) panel.appendChild(row(label, items.map((id) => icon("items", id))));
    }

    if (state.note) panel.appendChild(el("div", "rose-builds-note", state.note));
    if (busy) panel.appendChild(el("div", "rose-builds-note", "Updating..."));
    const buttons = el("div", "rose-builds-row");
    buttons.appendChild(el("span", "rose-builds-label", "Import"));
    for (const [part, label] of IMPORT_PARTS) {
      const button = el("button", "rose-builds-import", (imported[part] && imported[part].ok ? "✓ " : "") + label);
      button.disabled = busy;
      button.addEventListener("click", () => refresh([part]));
      buttons.appendChild(button);
    }
    panel.appendChild(buttons);
    for (const part of Object.values(imported)) {
      panel.appendChild(el("div", part.ok ? "rose-builds-done" : "rose-builds-error", part.text));
    }
  }

  const STYLE = `
    #${PANEL_ID} { position: fixed; top: 96px; left: 50%; transform: translateX(-50%); width: 430px; z-index: 9000;
      background: rgba(1, 10, 19, 0.94); border: 1px solid #785a28; color: #f0e6d2; font: 12px "LoL Display", "Segoe UI", sans-serif; padding: 8px 10px; }
    #${PANEL_ID}.rose-builds-collapsed { width: 190px; }
    #${PANEL_ID} .rose-builds-head, #${PANEL_ID} .rose-builds-who { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    #${PANEL_ID} .rose-builds-head { cursor: move; user-select: none; }
    #${PANEL_ID} .rose-builds-who { margin-top: 6px; }
    #${PANEL_ID} .rose-builds-title { color: #c8aa6e; letter-spacing: 0.05em; text-transform: uppercase; font-size: 11px; }
    #${PANEL_ID} .rose-builds-player, #${PANEL_ID} .rose-builds-versus { flex: 1; text-align: center; min-width: 0; }
    #${PANEL_ID} .rose-builds-name { font-size: 14px; color: #f0e6d2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    #${PANEL_ID} .rose-builds-rank { color: #a09b8c; font-size: 11px; }
    #${PANEL_ID} .rose-builds-arrow { background: #1e2328; border: 1px solid #785a28; color: #c8aa6e; cursor: pointer; min-width: 26px; height: 24px; }
    #${PANEL_ID} .rose-builds-arrow:hover { border-color: #c8aa6e; color: #f0e6d2; }
    #${PANEL_ID} .rose-builds-import { flex: 1; height: 26px; background: #1e2328; border: 1px solid #c8aa6e;
      color: #f0e6d2; cursor: pointer; text-transform: uppercase; letter-spacing: 0.05em; font: inherit; }
    #${PANEL_ID} .rose-builds-import:disabled { opacity: 0.5; cursor: default; }
    #${PANEL_ID} .rose-builds-import:hover { background: #32281e; }
    #${PANEL_ID} .rose-builds-role { flex: 1; height: 22px; background: #1e2328; border: 1px solid #3c3c41; color: #a09b8c; cursor: pointer; font: inherit; }
    #${PANEL_ID} .rose-builds-role:hover { border-color: #785a28; color: #f0e6d2; }
    #${PANEL_ID} .rose-builds-role-on { border-color: #c8aa6e; color: #f0e6d2; }
    #${PANEL_ID} .rose-builds-row { display: flex; align-items: center; gap: 4px; margin-top: 6px; }
    #${PANEL_ID} .rose-builds-label { width: 62px; color: #a09b8c; }
    #${PANEL_ID} .rose-builds-icon { width: 26px; height: 26px; border: 1px solid #3c3c41; vertical-align: middle; }
    #${PANEL_ID} .rose-builds-missing { color: #a09b8c; }
    #${PANEL_ID} .rose-builds-note { margin-top: 6px; color: #a09b8c; }
    #${PANEL_ID} .rose-builds-done { margin-top: 4px; color: #0acbe6; }
    #${PANEL_ID} .rose-builds-error { margin-top: 4px; color: #e84057; }
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
    } catch (e) {
      position = null;
    }
    const style = el("style");
    style.textContent = STYLE;
    document.head.appendChild(style);
    await loadIcons();
    setInterval(poll, POLL_MS);
    log("Started");
  }

  init();
})();
