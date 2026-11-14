/**
 * @name Rose-AccountSwitcher
 * @author Rose Team
 * @description Account switching panel for Rose - quickly switch between saved League accounts
 */
(function initAccountSwitcher() {
  "use strict";

  const LOG_PREFIX = "[Rose-AccountSwitcher]";
  const PANEL_ID = "rose-account-panel";
  const FLYOUT_ID = "rose-account-flyout";
  const NAV_ITEM_ID = "rose-account-nav-item";

  // State
  let bridge = null;
  let accounts = [];
  let activeAccountId = null;
  let panelOpen = false;
  let panelElement = null;

  // Logging
  function log(level, message) {
    const consoleMethod = level === "error" ? console.error : level === "warn" ? console.warn : console.log;
    consoleMethod(`${LOG_PREFIX} ${message}`);
  }

  // Wait for bridge to be available
  function waitForBridge() {
    return new Promise((resolve, reject) => {
      const timeout = 10000;
      const interval = 50;
      let elapsed = 0;
      const check = () => {
        if (window.__roseBridge) return resolve(window.__roseBridge);
        elapsed += interval;
        if (elapsed >= timeout) return reject(new Error("Bridge not available"));
        setTimeout(check, interval);
      };
      check();
    });
  }

  // Send message to backend and wait for response
  function sendRequest(type, data = {}) {
    return new Promise((resolve, reject) => {
      const requestId = "req_" + Date.now() + "_" + Math.random().toString(36).slice(2);

      // Set up one-time listener for the response
      const handler = (msg) => {
        if (msg.type === type + "-response" && msg.requestId === requestId) {
          bridge.unsubscribe(type + "-response", handler);
          resolve(msg);
        }
      };
      bridge.subscribe(type + "-response", handler);

      // Send the request
      const payload = { ...data, type: type, requestId: requestId };
      try {
        bridge.send(payload);
      } catch (e) {
        bridge.unsubscribe(type + "-response", handler);
        reject(e);
      }

      // Timeout after 5 seconds
      setTimeout(() => {
        bridge.unsubscribe(type + "-response", handler);
        reject(new Error("Request timeout"));
      }, 5000);
    });
  }

  // The letter on an account's round avatar: the first of its Riot ID ("?" before Rose has seen it signed in)
  function getInitial(riotId) {
    return riotId ? riotId.charAt(0).toUpperCase() : "?";
  }

  // Nav bar icons, drawn as masks in the client's gold like its own icons
  const ACCOUNT_ICON = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><circle cx='8' cy='7.5' r='3.5'/><path d='M1 20c0-3.9 3.1-6.5 7-6.5s7 2.6 7 6.5z'/><path d='M16 6.5h6m-2.5-2.5 2.5 2.5-2.5 2.5M22 13.5h-6m2.5-2.5-2.5 2.5 2.5 2.5' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/></svg>";
  const STORE_ICON = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M5 8h14l1.2 12a1.2 1.2 0 0 1-1.2 1.3H5a1.2 1.2 0 0 1-1.2-1.3z'/><path d='M8.5 10V6.5a3.5 3.5 0 0 1 7 0V10' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round'/></svg>";
  const STORE_NAV_ITEM_ID = "rose-modstore-nav-item";

  // One nav bar button (icon, tooltip, click), placed after *afterEl*, or after Rose's own item
  function createNavButton(id, tooltipText, svg, onClick, afterEl) {
    const existing = document.getElementById(id);
    if (existing) return existing;
    const rightMenu = document.querySelector(".main-nav-bar .right-nav-menu");
    if (!rightMenu) return null;

    const item = document.createElement("lol-uikit-navigation-item");
    item.id = id;
    item.className = "main-navigation-menu-item rose-account-nav";
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
    icon.style.webkitMaskImage = 'url("data:image/svg+xml,' + encodeURIComponent(svg) + '")';
    icon.style.webkitMaskSize = "contain";
    icon.style.webkitMaskRepeat = "no-repeat";
    icon.style.webkitMaskPosition = "center";
    icon.style.background = "#c8aa6e";

    const tooltip = document.createElement("div");
    tooltip.className = "menu-item-tooltip";
    tooltip.textContent = tooltipText;
    tooltip.style.display = "none";

    iconWrapper.appendChild(icon);
    item.appendChild(iconWrapper);
    item.appendChild(tooltip);
    item.addEventListener("click", onClick);
    item.addEventListener("mouseenter", () => {
      tooltip.style.display = "block";
    });
    item.addEventListener("mouseleave", () => {
      tooltip.style.display = "none";
    });

    const anchor = afterEl || rightMenu.querySelector("lol-uikit-navigation-item.Rose");
    if (anchor && anchor.parentNode === rightMenu) {
      rightMenu.insertBefore(item, anchor.nextSibling);
    } else {
      rightMenu.appendChild(item);
    }
    log("info", tooltipText + " navigation icon created");
    return item;
  }

  // The Account Switcher and Mod store buttons in the client nav bar
  function createNavIcon() {
    const accountItem = createNavButton(NAV_ITEM_ID, "Account Switcher", ACCOUNT_ICON, () => {
      if (panelOpen) {
        closeAccountPanel();
      } else {
        openAccountPanel();
      }
    });
    createNavButton(STORE_NAV_ITEM_ID, "Mod store", STORE_ICON, () => {
      sendRequest("mod-store-open")
        .then((msg) => {
          if (!msg.success) log("warn", "Mod store didn't open: " + (msg.error || "unknown"));
        })
        .catch((e) => log("warn", "Mod store didn't open: " + e.message));
    }, accountItem);
  }

  // Create the panel container and flyout
  function createPanel() {
    // Remove existing panel if any
    const existing = document.getElementById(PANEL_ID);
    if (existing) existing.remove();

    // Create panel container
    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.style.position = "fixed";
    panel.style.top = "0";
    panel.style.left = "0";
    panel.style.width = "100%";
    panel.style.height = "100%";
    panel.style.zIndex = "10000";
    panel.style.pointerEvents = "none";

    // Backdrop for click-outside-to-close
    const backdrop = document.createElement("div");
    backdrop.className = "backdrop";
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) closeAccountPanel();
    });
    panel.appendChild(backdrop);

    // Flyout frame
    let flyoutFrame;
    try {
      flyoutFrame = document.createElement("lol-uikit-flyout-frame");
      flyoutFrame.id = FLYOUT_ID;
      flyoutFrame.className = "flyout";
      flyoutFrame.setAttribute("orientation", "bottom");
      flyoutFrame.setAttribute("animated", "true");
      flyoutFrame.setAttribute("show", "true");
    } catch (e) {
      log("debug", "Could not create custom element, using div fallback", e);
      flyoutFrame = document.createElement("div");
      flyoutFrame.id = FLYOUT_ID;
      flyoutFrame.className = "flyout";
    }

    // Position below the nav icon, centered horizontally
    const navItem = document.getElementById(NAV_ITEM_ID);
    if (navItem) {
      const rect = navItem.getBoundingClientRect();
      flyoutFrame.style.position = "absolute";
      flyoutFrame.style.overflow = "visible";
      flyoutFrame.style.top = `${rect.bottom + 45}px`;
      flyoutFrame.style.left = `${rect.left + rect.width / 2}px`;
      flyoutFrame.style.transform = "translateX(-50%)";
      flyoutFrame.style.zIndex = "10001";
      flyoutFrame.style.pointerEvents = "all";
    }

    // Prevent click from closing
    flyoutFrame.addEventListener("click", (e) => e.stopPropagation());

    // Flyout content wrapper
    const flyoutContent = document.createElement("div");
    flyoutContent.className = "lc-flyout-content";
    flyoutContent.style.width = "100%";
    flyoutContent.style.display = "flex";
    flyoutContent.style.flexDirection = "column";

    // Render the UI content
    renderContent(flyoutContent);

    flyoutFrame.appendChild(flyoutContent);
    panel.appendChild(flyoutFrame);
    document.body.appendChild(panel);
    panelElement = panel;
  }

  // Render the account switching UI
  function renderContent(container) {
    container.innerHTML = "";
    renderListView(container);
  }

  // Render the account list view
  function renderListView(container) {
    // Header
    const header = document.createElement("div");
    header.className = "account-header";

    const title = document.createElement("h2");
    title.textContent = "Account Switcher";
    header.appendChild(title);

    const count = document.createElement("span");
    count.className = "account-count";
    count.textContent = `${accounts.length} account${accounts.length !== 1 ? "s" : ""}`;
    header.appendChild(count);

    container.appendChild(header);

    // Account list or empty state
    if (accounts.length === 0) {
      const empty = document.createElement("div");
      empty.className = "account-empty";

      const icon = document.createElement("div");
      icon.className = "empty-icon";
      icon.textContent = "\uD83C\uDF39"; // Rose emoji

      const text = document.createElement("div");
      text.textContent = "No accounts saved yet. Add your first account to get started.";

      empty.appendChild(icon);
      empty.appendChild(text);
      container.appendChild(empty);
    } else {
      const listContainer = document.createElement("div");
      listContainer.className = "account-list-container";

      let idx = 0;
      for (const acc of accounts) {
        const item = document.createElement("div");
        item.className = "account-item" + (acc.isActive ? " active" : "");
        item.style.setProperty("--i", Math.min(idx, 10));
        idx++;

        // Avatar
        let avatar;
        if (acc.tier) {
          avatar = document.createElement("img");
          avatar.src = "/fe/lol-static-assets/images/ranked-emblem/emblem-" + acc.tier.toLowerCase() + ".png";
          avatar.className = "account-emblem"; // 36px, with the letter avatar's spacing (css/styles.css)
          avatar.onerror = function () {
            this.remove();
            const fallback = document.createElement("div");
            fallback.className = "account-avatar";
            fallback.textContent = getInitial(acc.riotId);
            item.insertBefore(fallback, item.firstChild);
          };
        } else {
          avatar = document.createElement("div");
          avatar.className = "account-avatar";
          avatar.textContent = getInitial(acc.riotId);
        }

        // Info
        const info = document.createElement("div");
        info.className = "account-info";

        const name = document.createElement("div");
        name.className = "account-summoner-name";
        name.textContent = acc.riotId || "New account";
        info.appendChild(name);

        // Region and active badge row
        const regionRow = document.createElement("div");
        regionRow.style.display = "flex";
        regionRow.style.alignItems = "center";
        regionRow.style.gap = "8px";

        if (acc.region) {
          const region = document.createElement("span");
          region.className = "account-region";
          region.textContent = acc.region;
          regionRow.appendChild(region);
        }

        if (acc.isActive) {
          const badge = document.createElement("span");
          badge.className = "active-badge";
          badge.textContent = "Active";
          regionRow.appendChild(badge);
        }

        info.appendChild(regionRow);

        // Rank and LP
        const rankDiv = document.createElement("div");
        rankDiv.className = "account-rank";
        if (!acc.riotId) {
          rankDiv.textContent = "Sign in once to fill in Riot ID and rank";
        } else if (acc.tier) {
          rankDiv.textContent = `${acc.tier} ${acc.division || ""} ${acc.lp !== undefined ? acc.lp + " LP" : ""}`;
        } else {
          rankDiv.textContent = "Unranked";
        }
        info.appendChild(rankDiv);

        // Level and note
        const meta = document.createElement("div");
        meta.className = "account-meta";

        if (acc.level) {
          const level = document.createElement("span");
          level.className = "account-level";
          level.textContent = `Level ${acc.level}`;
          meta.appendChild(level);
        }

        if (acc.note) {
          const note = document.createElement("span");
          note.className = "account-note";
          note.textContent = acc.note;
          meta.appendChild(note);
        }

        info.appendChild(meta);

        // Delete button
        const deleteBtn = document.createElement("button");
        deleteBtn.className = "account-btn-danger";
        deleteBtn.textContent = "\u2716";
        deleteBtn.title = "Remove account";
        deleteBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          removeAccount(acc, item);
        });

        item.appendChild(avatar);
        item.appendChild(info);
        item.appendChild(deleteBtn);

        // Click to switch
        item.addEventListener("click", () => switchAccount(acc));

        listContainer.appendChild(item);
      }

      container.appendChild(listContainer);
    }

    // Status area for switch/remove feedback
    const statusArea = document.createElement("div");
    statusArea.id = "account-status-area";
    container.appendChild(statusArea);

    // Action buttons
    const actions = document.createElement("div");
    actions.className = "account-actions";

    const manageBtn = document.createElement("button");
    manageBtn.className = "account-btn account-btn-primary";
    manageBtn.textContent = "Manage accounts";
    manageBtn.addEventListener("click", () => {
      sendRequest("account-open-manager", {}).catch((e) => log("error", "Could not open Rose's account window: " + e.message));
    });

    const closeBtn = document.createElement("button");
    closeBtn.className = "account-btn account-btn-secondary";
    closeBtn.textContent = "Close";
    closeBtn.addEventListener("click", () => closeAccountPanel());

    actions.appendChild(manageBtn);
    actions.appendChild(closeBtn);
    container.appendChild(actions);
  }



  // Switch to an account
  async function switchAccount(account) {
    if (account.isActive) return;
    if (!confirm("Switch to " + (account.riotId || "this account") + "? League will close and sign in again.")) return;
    const flyoutContent = document.querySelector("#" + FLYOUT_ID + " .lc-flyout-content");

    // Show loading state
    if (flyoutContent) {
      const existingStatus = document.getElementById("account-status-area");
      if (existingStatus) {
        existingStatus.innerHTML = '<div class="status-message status-success"><span class="loading-spinner"></span> Switching account...</div>';
      }
    }

    try {
      const response = await sendRequest("account-switch", { id: account.id });

      if (response.success) {
        log("info", "Switched to account: " + (account.riotId || account.id));

        // Refresh list and close panel after a brief delay
        setTimeout(async () => {
          await loadAccounts();
          const content = document.querySelector("#" + FLYOUT_ID + " .lc-flyout-content");
          if (content) renderContent(content);

          // Close the panel after showing success briefly
          setTimeout(() => closeAccountPanel(), 800);
        }, 500);
      } else {
        showStatus(document.getElementById("account-status-area"), response.error || "Failed to switch", "error");
      }
    } catch (e) {
      log("error", "Error switching account: " + e.message);
      showStatus(document.getElementById("account-status-area"), "Connection error. Is Rose running?", "error");
    }
  }

  // Remove an account
  async function removeAccount(account, item) {
    if (!confirm("Remove " + (account.riotId || "this account") + "?")) return;

    try {
      const response = await sendRequest("account-remove", { id: account.id });

      if (response.success) {
        log("info", "Removed account: " + (account.riotId || account.id));

        if (item) {
          item.style.overflow = "hidden";
          const animation = item.animate([{ opacity: 1, height: item.offsetHeight + "px" }, { opacity: 0, height: "0px", paddingTop: "0px", paddingBottom: "0px", marginBottom: "0px" }], { duration: 180, easing: "ease-in" });
          await animation.finished;
        }

        await loadAccounts();
        const flyoutContent = document.querySelector("#" + FLYOUT_ID + " .lc-flyout-content");
        if (flyoutContent) renderContent(flyoutContent);
      } else {
        showStatus(document.getElementById("account-status-area"), response.error || "Failed to remove", "error");
      }
    } catch (e) {
      log("error", "Error removing account: " + e.message);
    }
  }

  // Show status message in the status area
  function showStatus(container, message, type) {
    if (!container) return;

    const msgEl = document.createElement("div");
    msgEl.className = "status-message status-" + type;
    msgEl.textContent = message;

    container.innerHTML = "";
    container.appendChild(msgEl);

    // Auto-dismiss success messages after 3 seconds
    if (type === "success") {
      setTimeout(() => {
        if (msgEl.parentNode) msgEl.remove();
      }, 3000);
    }
  }

  // Load accounts from backend
  async function loadAccounts() {
    try {
      const response = await sendRequest("account-list");

      if (response.accounts !== undefined) {
        accounts = response.accounts || [];
        activeAccountId = response.activeAccountId || null;

        // Update nav icon with account count badge
        updateNavBadge();
      }
    } catch (e) {
      log("error", "Failed to load accounts: " + e.message);
    }
  }

  // Update the navigation icon badge with account count
  function updateNavBadge() {
    const navItem = document.getElementById(NAV_ITEM_ID);
    if (!navItem) return;

    // Remove existing badge
    const existingBadge = navItem.querySelector(".account-badge");
    if (existingBadge) existingBadge.remove();

    if (accounts.length > 0) {
      const badge = document.createElement("div");
      badge.className = "account-badge";
      badge.style.cssText = `
        position: absolute;
        top: -4px;
        right: -4px;
        width: 16px;
        height: 16px;
        background: #c8aa6e;
        color: #010a13;
        font-size: 9px;
        font-weight: bold;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
      `;
      badge.textContent = accounts.length > 9 ? "9+" : String(accounts.length);

      const iconWrapper = navItem.querySelector(".menu-item-icon")?.parentElement || navItem;
      iconWrapper.style.position = "relative";
      iconWrapper.appendChild(badge);
    }
  }

  // Open the account panel
  async function openAccountPanel() {
    if (panelOpen) return;

    panelOpen = true;

    // Mark nav item as active
    const navItem = document.getElementById(NAV_ITEM_ID);
    if (navItem) navItem.setAttribute("active", "true");

    await loadAccounts();
    createPanel();
  }

  // Close the account panel
  function closeAccountPanel() {
    if (!panelOpen) return;

    panelOpen = false;

    const navItem = document.getElementById(NAV_ITEM_ID);
    if (navItem) navItem.removeAttribute("active");

    if (panelElement) {
      panelElement.classList.add("closing");
      const ref = panelElement;
      panelElement = null;
      setTimeout(() => {
        ref.remove();
      }, 140);
    }
  }

  // Handle incoming bridge messages
  function handleBridgeMessage(msg) {
    // Account list response is handled by sendRequest promise
    // But we can also listen for push updates
    if (msg.type === "account-list-response") {
      accounts = msg.accounts || [];
      activeAccountId = msg.activeAccountId || null;

      // If panel is open, refresh the view
      if (panelOpen) {
        const flyoutContent = document.querySelector("#" + FLYOUT_ID + " .lc-flyout-content");
        if (flyoutContent) renderContent(flyoutContent);
      }
    }
  }

  // Inject CSS styles into the page
  function injectStyles() {
    if (document.getElementById("rose-account-switcher-styles")) return;

    const style = document.createElement("style");
    style.id = "rose-account-switcher-styles";
    
    // Try to load CSS from local server, fallback to inline styles
    const port = window.__roseBridge ? window.__roseBridge.port : 50000;
    fetch(`http://127.0.0.1:${port}/plugin/ROSE-AccountSwitcher/css/styles.css`, { cache: "no-store" })
      .then((r) => r.text())
      .then((cssText) => { style.textContent = cssText; })
      .catch(() => {
        // Fallback: minimal inline styles if fetch fails
        style.textContent = `
          #rose-account-panel { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 10000; pointer-events: none; }
          #rose-account-flyout { min-width: 380px !important; max-width: 420px !important; background: transparent !important; color: #cdbe91; font-family: "Beaufort for LOL", serif; display: flex !important; flex-direction: column !important; align-items: center !important; }
          #rose-account-flyout lc-flyout-content, #rose-account-flyout .lc-flyout-content { background: #010a13 !important; border-radius: 4px !important; padding: 20px !important; width: 100% !important; box-sizing: border-box !important; border: 1px solid rgba(200, 170, 110, 0.3) !important; }
          .account-item { display: flex; align-items: center; padding: 10px 12px; margin-bottom: 4px; border-radius: 4px; cursor: pointer; transition: background 0.15s ease; }
          .account-item:hover { background: rgba(200, 170, 110, 0.08); }
          .account-item.active { background: rgba(200, 170, 110, 0.12); border-color: rgba(200, 170, 110, 0.3); }
        `;
      });

    document.head.appendChild(style);
  }

  // Main initialization
  async function init() {
    try {
      bridge = await waitForBridge();
      log("info", "Bridge connected, initializing AccountSwitcher");

      // Inject CSS styles
      injectStyles();

      // Subscribe to account-related messages
      bridge.subscribe("account-list-response", handleBridgeMessage);

      // Create the navigation icon
      createNavIcon();

      // If nav item already exists (plugin loaded after client is ready)
      if (!document.getElementById(NAV_ITEM_ID)) {
        let attempts = 0;
        const maxAttempts = 30;
        const interval = setInterval(() => {
          attempts++;
          if (document.querySelector(".right-nav-menu")) {
            createNavIcon();
            clearInterval(interval);
          }
          if (attempts >= maxAttempts) {
            clearInterval(interval);
          }
        }, 1000);
      }

      log("info", "AccountSwitcher initialized");
    } catch (e) {
      log("error", "Failed to initialize AccountSwitcher: " + e.message);
    }
  }

  // Start initialization when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
