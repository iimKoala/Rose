/**
 * @name Rose-AutoAccept
 * @author Rose Team
 * @description Accepts the match found window for you; a button in the top bar turns it on and off
 */
(function initRoseAutoAccept() {
  "use strict";

  const LOG_PREFIX = "[Rose-AutoAccept]";
  const STORAGE_KEY = "rose-auto-accept";
  const NAV_ITEM_ID = "rose-auto-accept-nav-item";
  const POLL_MS = 1000;
  const READY_CHECK = "/lol-matchmaking/v1/ready-check";
  const PHASE = "/lol-gameflow/v1/gameflow-phase";
  const COLOR_ON = "#c8aa6e";
  const COLOR_OFF = "#5b5a56";
  const ICON = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M9.5 17.6 4.4 12.5l1.9-1.9 3.2 3.2 8.2-8.2 1.9 1.9z'/></svg>";

  function shouldAccept(on, check) {
    if (on !== true) return false;
    if (!check || typeof check !== "object") return false;
    if (check.state !== "InProgress") return false;
    if (check.playerResponse !== "None") return false;
    return true;
  }

  function tooltipFor(on) {
    if (on === true) return "Auto accept: on (click to turn off)";
    return "Auto accept: off (click to turn on)";
  }

  if (typeof module === "object" && module && module.exports) {
    module.exports = { shouldAccept, tooltipFor };
    return;
  }

  let answered = false;

  function isOn() {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch (e) {
      return false;
    }
  }

  function setOn(on) {
    try {
      localStorage.setItem(STORAGE_KEY, on ? "1" : "0");
    } catch (e) {
      return;
    }
    paint();
  }

  function paint() {
    const item = document.getElementById(NAV_ITEM_ID);
    if (!item) return;
    const icon = item.querySelector(".menu-item-icon");
    const tooltip = item.querySelector(".menu-item-tooltip");
    const on = isOn();
    if (icon) icon.style.backgroundColor = on ? COLOR_ON : COLOR_OFF;
    if (tooltip) tooltip.textContent = tooltipFor(on);
  }

  function ensureButton() {
    if (document.getElementById(NAV_ITEM_ID)) return;
    const rightMenu = document.querySelector(".main-nav-bar .right-nav-menu");
    if (!rightMenu) return;

    const item = document.createElement("lol-uikit-navigation-item");
    item.id = NAV_ITEM_ID;
    item.className = "main-navigation-menu-item rose-auto-accept-nav";
    item.setAttribute("margin-right", "10px");

    const iconWrapper = document.createElement("div");
    iconWrapper.style.display = "flex";
    iconWrapper.style.alignItems = "center";
    iconWrapper.style.justifyContent = "center";
    iconWrapper.style.width = "100%";
    iconWrapper.style.height = "100%";

    const icon = document.createElement("div");
    icon.className = "menu-item-icon";
    icon.style.width = "24px";
    icon.style.height = "24px";
    icon.style.webkitMaskImage = 'url("data:image/svg+xml,' + encodeURIComponent(ICON) + '")';
    icon.style.webkitMaskSize = "contain";
    icon.style.webkitMaskRepeat = "no-repeat";
    icon.style.webkitMaskPosition = "center";

    const tooltip = document.createElement("div");
    tooltip.className = "menu-item-tooltip";
    tooltip.style.display = "none";

    iconWrapper.appendChild(icon);
    item.appendChild(iconWrapper);
    item.appendChild(tooltip);

    item.addEventListener("click", () => {
      setOn(!isOn());
      log(isOn() ? "Auto accept on" : "Auto accept off");
    });

    item.addEventListener("mouseenter", () => {
      tooltip.style.display = "block";
    });
    item.addEventListener("mouseleave", () => {
      tooltip.style.display = "none";
    });

    rightMenu.appendChild(item);
    paint();
  }

  // What the client answers to one GET, or null when it fails or the client says no (a 404...)
  async function ask(url) {
    try {
      const response = await fetch(url);
      return response.ok ? await response.json() : null;
    } catch (e) {
      return null;
    }
  }

  async function look() {
    // The phase always answers; the ready check answers 404 outside one, and once a second that fills the client's log
    const phase = await ask(PHASE);
    const check = phase === "ReadyCheck" ? await ask(READY_CHECK) : null;
    if (!shouldAccept(true, check)) { answered = false; return; }
    if (answered) return;
    answered = true;
    try {
      const response = await fetch(READY_CHECK + "/accept", { method: "POST" });
      if (response.ok === false) { throw new Error("the client answered " + response.status); }
      log("Match accepted");
    } catch (e) {
      answered = false;
      log("Could not accept: " + e.message);
    }
  }

  // shortcut: asks the client once a second while on, switch to the client's event socket if this ever shows as load
  function tick() {
    ensureButton();
    if (isOn()) look();
  }

  function log(message) {
    console.log(`${LOG_PREFIX} ${message}`);
  }

  setInterval(tick, POLL_MS);
  log("Started");
})();
