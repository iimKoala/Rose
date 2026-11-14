function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function cardHtml(account) {
  const tier = (account.tier || "").trim().toUpperCase();
  const division = (account.division || "").trim();
  const isUnranked = !tier || tier === "UNRANKED";
  const lp = account.lp || 0;
  const tierDisplay = isUnranked ? "UNRANKED" : tier;
  const divisionDisplay = isUnranked ? "" : division;
  const barWidth = ["MASTER", "GRANDMASTER", "CHALLENGER"].includes(tier)
    ? "100%"
    : Math.min(lp, 100) + "%";

  let nameSection;
  if (account.riotId) {
    nameSection = escapeHtml(account.riotId);
  } else {
    nameSection =
      escapeHtml(account.username) +
      '<br><span class="card-subtext">Sign in once to fill in Riot ID and rank</span>';
  }

  let warningHtml = "";
  if (account.loginError === "wrong_login") {
    warningHtml = '<div class="card-warning">Wrong username or password: edit this account</div>';
  }
  let emblemHtml = "";
  if (!isUnranked) {
    emblemHtml +=
      '<img class="card-emblem" src="emblems/' +
      escapeHtml(tier.toLowerCase()) +
      '.png" alt="">';
  } else {
    // unranked: the diamond outline of the logging-in screen (index.html), dimmed in style.css
    emblemHtml +=
      '<svg class="card-emblem unranked" viewBox="0 0 100 100">' +
      '<polygon points="50,5 95,50 50,95 5,50" fill="none" stroke="var(--gold)" stroke-width="2"/></svg>';
  }

  let divisionHtml = "";
  if (divisionDisplay) {
    divisionHtml =
      '<span class="card-division">' + escapeHtml(divisionDisplay) + "</span>";
  }

  let lpHtml = "";
  if (!isUnranked) {
    lpHtml =
      '<div class="card-lp">' +
      escapeHtml(String(lp)) +
      " LP</div>" +
      '<div class="card-lp-bar"><div class="card-lp-fill" style="width:' +
      barWidth +
      '"></div></div>';
  }

  let lastSeasonHtml = "";
  if (account.lastSeason) {
    lastSeasonHtml =
      '<div class="card-meta">Last season: ' +
      escapeHtml(account.lastSeason) +
      "</div>";
  }

  let noteHtml = "";
  if (account.note) {
    noteHtml =
      '<div class="card-note">' + escapeHtml(account.note) + "</div>";
  }

  let regionBadge = "";
  if (account.region) {
    regionBadge =
      '<span class="card-badge">' + escapeHtml(account.region) + "</span>";
  }

  let levelBadge = "";
  if (account.level) {
    levelBadge =
      '<span class="card-badge">Lv ' + escapeHtml(String(account.level)) + "</span>";
  }

  let activeBadge = "";
  if (account.isActive) {
    activeBadge = '<span class="card-badge badge-active">ACTIVE</span>';
  }

  return (
    '<div class="card" data-id="' +
    escapeHtml(String(account.id)) +
    '">' +
    '<button class="card-edit" title="Edit">&#9998;</button>' +
    '<button class="card-remove" title="Remove">&#10005;</button>' +
    '<div class="card-header">' +
    nameSection +
    "</div>" +
    '<div class="card-badges">' +
    regionBadge +
    levelBadge +
    activeBadge +
    "</div>" +
    warningHtml +
    '<div class="card-rank">' +
    emblemHtml +
    '<div class="card-rank-info">' +
    '<div class="card-tier">' +
    escapeHtml(tierDisplay) +
    divisionHtml +
    "</div>" +
    lpHtml +
    "</div>" +
    "</div>" +
    lastSeasonHtml +
    noteHtml +
    '<button class="card-login login-btn">LOG IN</button>' +
    "</div>"
  );
}

const TIERS = ["CHALLENGER","GRANDMASTER","MASTER","DIAMOND","EMERALD","PLATINUM","GOLD","SILVER","BRONZE","IRON"];
const DIVISIONS = ["I","II","III","IV"];
const TIER_COLORS = {
  Iron: "#6b6461", Bronze: "#8c513a", Silver: "#8a9aa6", Gold: "#c8aa6e",
  Platinum: "#4e9996", Emerald: "#2dbb7f", Diamond: "#576bce",
  Master: "#9d48e0", Grandmaster: "#cd4545", Challenger: "#f4c874", Unranked: "#5b5a56"
};

var cardEls = new Map();
var allAccounts = [];
var loginAccount, spinTween, pulseTween, innerSpinTween;
var editingId = null;
var removingId = null;

function openForm(account) {
  var form = document.getElementById("account-form");
  var title = document.getElementById("form-title");
  var usernameEl = document.getElementById("form-username");
  var passwordEl = document.getElementById("form-password");
  var regionEl = document.getElementById("form-region");
  var noteEl = document.getElementById("form-note");
  var errorEl = document.getElementById("form-error");

  if (account) {
    title.textContent = "EDIT ACCOUNT";
    editingId = account.id;
    usernameEl.value = account.username || "";
    regionEl.value = account.region || "NA";
    noteEl.value = account.note || "";
    passwordEl.placeholder = "Leave blank to keep the saved password";
  } else {
    title.textContent = "ADD ACCOUNT";
    editingId = null;
    usernameEl.value = "";
    regionEl.value = "NA";
    noteEl.value = "";
    passwordEl.placeholder = "";
  }
  passwordEl.value = "";
  errorEl.textContent = "";
  form.classList.add("open");
}

function closeForm() {
  var form = document.getElementById("account-form");
  form.classList.remove("open");
  document.getElementById("form-password").value = "";
  editingId = null;
}

async function saveAccount(values) {
  if (inWindow()) {
    var r = await window.pywebview.api.save_account(editingId || "", values.username, values.password, values.region, values.note);
    if (!r.ok) { document.getElementById("form-error").textContent = r.error; return; }
  }
  closeForm();
  if (inWindow()) { loadAccounts(); }
}

function findAccountById(id) {
  for (var i = 0; i < allAccounts.length; i++) {
    if (allAccounts[i].id === id) return allAccounts[i];
  }
  return null;
}

function applyFilters(animate) {
  var search = (document.getElementById("search").value || "").toLowerCase();
  var region = document.getElementById("region").value;
  var sort = document.getElementById("sort").value;

  var filtered = allAccounts.filter(function(acc) {
    if (region && acc.region !== region) return false;
    if (search) {
      var riotId = (acc.riotId || "").toLowerCase();
      var username = (acc.username || "").toLowerCase();
      var note = (acc.note || "").toLowerCase();
      if (riotId.indexOf(search) === -1 && username.indexOf(search) === -1 && note.indexOf(search) === -1) {
        return false;
      }
    }
    return true;
  });

  filtered.sort(function(a, b) {
    if (sort === "rank") return rankScore(b) - rankScore(a);
    if (sort === "name") return ((a.riotId || a.username) || "").localeCompare((b.riotId || b.username) || "");
    if (sort === "level") return (b.level || 0) - (a.level || 0);
    return rankScore(b) - rankScore(a);
  });

  var grid = document.getElementById("grid");

  if (animate) {
    var state = Flip.getState(".card");
  }

  allAccounts.forEach(function(acc) {
    var cardEl = cardEls.get(acc.id);
    if (cardEl) cardEl.style.display = "none";
  });
  filtered.forEach(function(acc) {
    var cardEl = cardEls.get(acc.id);
    if (cardEl) { cardEl.style.display = ""; grid.appendChild(cardEl); }
  });

  if (animate) {
    Flip.from(state, { duration: 0.35, ease: "power2.out", absolute: true, onEnter: function(els) { return gsap.fromTo(els, { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.25 }); }, onLeave: function(els) { return gsap.to(els, { opacity: 0, scale: 0.9, duration: 0.2 }); } });
  }

  document.getElementById("account-count").textContent = filtered.length + " of " + allAccounts.length + " accounts";
}

function fakeMode() { return location.protocol === "file:" || location.search.indexOf("fake") !== -1; }
function inWindow() {
  return !!(window.pywebview && window.pywebview.api) && !fakeMode();
}
function showToast(text, isError) {
  var t = document.getElementById("toast");
  t.textContent = text;
  t.classList.toggle("error", !!isError);
  gsap.killTweensOf(t);
  gsap.fromTo(t, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.2 });
  gsap.to(t, { opacity: 0, duration: 0.4, delay: 5 });
}
function rankScore(a) {
  const tierIdx = TIERS.indexOf((a.tier || "").trim().toUpperCase());
  if (tierIdx === -1) return -1;
  const divIdx = Math.max(DIVISIONS.indexOf((a.division || "").trim()), 0);
  return (TIERS.length - tierIdx) * 100000 + (DIVISIONS.length - divIdx) * 10000 + (a.lp || 0);
}

function render(accounts) {
  allAccounts = [...accounts];
  var grid = document.getElementById("grid");
  grid.innerHTML = "";
  cardEls.clear();
  var keepRegion = document.getElementById("region").value;
  var sorted = [...accounts].sort((a, b) => rankScore(b) - rankScore(a));
  for (var i = 0; i < sorted.length; i++) {
    var container = document.createElement("div");
    container.innerHTML = cardHtml(sorted[i]);
    var cardEl = container.firstElementChild;
    cardEls.set(sorted[i].id, cardEl);
    grid.appendChild(cardEl);
  }
  var rankList = document.getElementById("rank-list");
  rankList.innerHTML = "";
  var counts = {};
  for (var j = 0; j < sorted.length; j++) {
    var t = (sorted[j].tier || "").trim().toUpperCase();
    if (!t || t === "UNRANKED") t = "UNRANKED";
    counts[t] = (counts[t] || 0) + 1;
  }
  for (var k = 0; k < TIERS.length; k++) {
    var tierName = TIERS[k];
    var display = tierName.charAt(0) + tierName.slice(1).toLowerCase();
    var count = counts[tierName] || 0;
    var color = TIER_COLORS[display] || TIER_COLORS.Unranked;
    var li = document.createElement("li");
    li.className = "rank-distribution-item";
    li.innerHTML = '<span class="tier-diamond" style="background:' + color + '"></span><span class="tier-name"></span><span class="tier-count"></span>';
    li.querySelector(".tier-name").textContent = display;
    li.querySelector(".tier-count").textContent = count;
    rankList.appendChild(li);
  }
  var unranked = counts["UNRANKED"] || 0;
  var li2 = document.createElement("li");
  li2.className = "rank-distribution-item";
  li2.innerHTML = '<span class="tier-diamond" style="background:' + TIER_COLORS.Unranked + '"></span><span class="tier-name"></span><span class="tier-count"></span>';
  li2.querySelector(".tier-name").textContent = "Unranked";
  li2.querySelector(".tier-count").textContent = unranked;
  rankList.appendChild(li2);
  document.getElementById("account-count").textContent = accounts.length + " accounts";
  applyFilters(false);
  var regions = {};
  for (var m = 0; m < accounts.length; m++) {
    if (accounts[m].region) regions[accounts[m].region] = true;
  }
  var regionEl = document.getElementById("region");
  regionEl.innerHTML = "<option value=\"\">All regions</option>";
  var sortedRegions = Object.keys(regions).sort();
  for (var n = 0; n < sortedRegions.length; n++) {
    var opt = document.createElement("option");
    opt.value = sortedRegions[n];
    opt.textContent = sortedRegions[n];
    regionEl.appendChild(opt);
  }
  if (keepRegion && regionEl.querySelector('option[value="' + keepRegion + '"]')) {
    regionEl.value = keepRegion;
  }
}

document.addEventListener("DOMContentLoaded", function() {
  gsap.registerPlugin(Flip);
  function startPage() {
    if (fakeMode()) {
      render(window.FAKE_ACCOUNTS || []);
    } else if (window.pywebview && window.pywebview.api && window.pywebview.api.list_accounts) {
      loadAccounts();
    } else {
      window.addEventListener("pywebviewready", function () { loadAccounts(); }, { once: true });
    }
  }
  startPage();
  window.addEventListener("focus", function () { if (inWindow()) loadAccounts(); });
  document.getElementById("search").addEventListener("input", function() { applyFilters(true); });
  document.getElementById("region").addEventListener("change", function() { applyFilters(true); });
  document.getElementById("sort").addEventListener("change", function() { applyFilters(true); });
  document.getElementById("add-account").addEventListener("click", function() {
    openForm(null);
  });
  document.getElementById("form-cancel").addEventListener("click", function() {
    closeForm();
  });
  document.getElementById("form-save").addEventListener("click", function() {
    var username = (document.getElementById("form-username").value || "").trim();
    var password = document.getElementById("form-password").value;
    var region = document.getElementById("form-region").value;
    var note = (document.getElementById("form-note").value || "").trim();
    saveAccount({ username: username, password: password, region: region, note: note });
  });
  document.getElementById("account-form").addEventListener("click", function(e) {
    if (e.target === document.getElementById("account-form")) {
      closeForm();
    }
  });
  document.getElementById("confirm-no").addEventListener("click", function() {
    document.getElementById("confirm-box").classList.remove("open");
  });
  document.getElementById("confirm-box").addEventListener("click", function(e) {
    if (e.target === document.getElementById("confirm-box")) {
      document.getElementById("confirm-box").classList.remove("open");
    }
  });
  document.getElementById("confirm-yes").addEventListener("click", function() {
    var id = removingId;
    removingId = null;
    document.getElementById("confirm-box").classList.remove("open");
    var cardEl = cardEls.get(id);
    if (fakeMode()) {
      if (cardEl) {
        gsap.to(cardEl, { opacity: 0, scale: 0.9, duration: 0.25, onComplete: function() {
          for (var i = 0; i < allAccounts.length; i++) {
            if (allAccounts[i].id === id) { allAccounts.splice(i, 1); break; }
          }
          render(allAccounts);
        }});
      }
    } else if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.remove_account(id).then(function(r) {
        if (r.ok && cardEl) {
          gsap.to(cardEl, { opacity: 0, scale: 0.9, duration: 0.25, onComplete: loadAccounts });
        } else { loadAccounts(); }
      });
    }
  });
  document.getElementById("grid").addEventListener("click", function(e) {
    var removeBtn = e.target.closest(".card-remove");
    if (removeBtn) {
      var card = removeBtn.closest(".card");
      var accId = card.getAttribute("data-id");
      var acc = findAccountById(accId);
      if (!acc) return;
      removingId = acc.id;
      var riotId = acc.riotId || acc.username || "Unknown";
      document.getElementById("confirm-text").textContent = "Remove " + riotId + "? Its saved password is deleted too.";
      document.getElementById("confirm-box").classList.add("open");
      return;
    }
    var editBtn = e.target.closest(".card-edit");
    if (editBtn) {
      var card = editBtn.closest(".card");
      var accId = card.getAttribute("data-id");
      var acc = findAccountById(accId);
      if (acc) openForm(acc);
      return;
    }
    var card = e.target.closest(".card");
    if (!card) return;
    var loginBtn = e.target.closest(".login-btn");
    if (loginBtn) {
      e.stopPropagation();
      var accId = card.getAttribute("data-id");
      var acc = null;
      for (var i = 0; i < allAccounts.length; i++) {
        if (allAccounts[i].id === accId) { acc = allAccounts[i]; break; }
      }
      if (!acc) return;
      if (fakeMode()) {
        showLogin(acc);
        var steps = LOGIN_STEPS;
        for (var s = 0; s < steps.length; s++) {
          (function(idx) {
            setTimeout(function() { setStep(steps[idx]); }, (idx + 1) * 1500);
          })(s);
        }
        setTimeout(function() { finishLogin(true, "Signed in. League is starting."); }, steps.length * 1500 + 500);
        return;
      }
      if (!acc.hasPassword) { openForm(acc); document.getElementById("form-error").textContent = "Add a password first"; return; }
      showLogin(acc); window.pywebview.api.log_in(acc.id); return;
    }
    var cards = document.querySelectorAll(".card");
    for (var i = 0; i < cards.length; i++) cards[i].classList.remove("selected");
    card.classList.add("selected");
  });
  document.getElementById("login-close").addEventListener("click", function() {
    hideLogin();
    if (inWindow()) loadAccounts();
  });
  document.getElementById("btn-min").addEventListener("click", function() { if (window.pywebview) window.pywebview.api.minimize(); });
  document.getElementById("btn-max").addEventListener("click", function() { if (window.pywebview) window.pywebview.api.toggle_maximize(); });
  document.getElementById("btn-close").addEventListener("click", function() { if (window.pywebview) window.pywebview.api.close(); });
  document.getElementById("export-link").addEventListener("click", async function(e) {
    e.preventDefault();
    if (!inWindow()) { showToast("Export works in Rose's account window"); return; }
    var r = await window.pywebview.api.export_accounts();
    if (r.cancelled) return;
    if (!r.ok) { showToast(r.error, true); return; }
    showToast("Exported " + r.count + " accounts to " + r.path + ". It contains passwords: keep it private.");
  });
  document.getElementById("import-link").addEventListener("click", function(e) {
    e.preventDefault();
    if (!inWindow()) { showToast("Import works in Rose's account window"); return; }
    document.getElementById("import-error").textContent = "";
    document.getElementById("import-box").classList.add("open");
  });
  document.getElementById("import-cancel").addEventListener("click", function() {
    document.getElementById("import-box").classList.remove("open");
  });
  document.getElementById("import-go").addEventListener("click", async function() {
    var r = await window.pywebview.api.import_accounts(document.getElementById("import-region").value);
    if (r.cancelled) return;
    if (!r.ok) { document.getElementById("import-error").textContent = r.error; return; }
    document.getElementById("import-box").classList.remove("open");
    showToast("Imported " + r.added + " accounts" + (r.skipped ? ", skipped " + r.skipped + " (list in " + r.skippedFile + ")" : ""));
    loadAccounts();
  });
  document.getElementById("store-link").addEventListener("click", async function(e) {
    e.preventDefault();
    if (!inWindow()) { showToast("The mod store opens from Rose's account window"); return; }
    window.pywebview.api.open_mod_store();
    showToast("Opening the mod store...");
  });
});

var LOGIN_STEPS = [
  "Closing League",
  "Starting the Riot Client",
  "Signing out of the Riot Client",
  "Filling in the sign-in",
  "Waiting for the sign-in",
  "Starting League"
];

window.showLogin = function(account) {
  loginAccount = account;
  var name = account.riotId || account.username || "";
  document.getElementById("login-name").textContent = name;
  document.getElementById("login-title").textContent = "LOGGING IN";
  document.getElementById("login-message").textContent = "";
  document.getElementById("login-message").style.color = "";
  document.getElementById("login-close").classList.remove("visible");
  document.getElementById("login-close").style.display = "";
  document.getElementById("login-close").style.opacity = "";
  var stepEls = document.querySelectorAll(".login-step");
  for (var i = 0; i < stepEls.length; i++) {
    stepEls[i].classList.remove("done", "current");
  }
  document.getElementById("login-progress").style.width = "0%";
  var diamond = document.getElementById("login-diamond");
  var emblem = document.getElementById("login-emblem");
  gsap.set(emblem, { filter: "drop-shadow(0 0 0px rgba(200,170,110,0))" });
  emblem.style.display = "none";
  diamond.style.display = "";
  gsap.killTweensOf(diamond);
  if (spinTween) spinTween.kill();
  if (pulseTween) pulseTween.kill();
  if (innerSpinTween) innerSpinTween.kill();
  gsap.set(diamond, { rotation: 0, scale: 1 });
  gsap.set("#login-diamond-inner", { rotation: 0 });
  document.getElementById("login-diamond-inner").style.display = "";
  document.querySelector(".login-diamond-wrap").style.display = "";
  spinTween = gsap.to(diamond, { rotation: 360, duration: 4, ease: "none", repeat: -1 });
  pulseTween = gsap.to(diamond, { scale: 1.08, yoyo: true, repeat: -1, duration: 1.2, ease: "sine.inOut" });
  innerSpinTween = gsap.to("#login-diamond-inner", { rotation: -360, duration: 3, ease: "none", repeat: -1 });
  var overlay = document.getElementById("login-screen");
  overlay.style.display = "flex";
  gsap.fromTo(overlay, { opacity: 0 }, { opacity: 1, duration: 0.3 });
};

window.setStep = function(message) {
  var stepIndex = -1;
  for (var i = 0; i < LOGIN_STEPS.length; i++) {
    if (message.startsWith(LOGIN_STEPS[i])) { stepIndex = i; break; }
  }
  if (stepIndex < 0) return;
  var stepEls = document.querySelectorAll(".login-step");
  for (var i = 0; i < stepEls.length; i++) {
    stepEls[i].classList.remove("done", "current");
    if (i < stepIndex) stepEls[i].classList.add("done");
    else if (i === stepIndex) stepEls[i].classList.add("current");
  }
  var total = LOGIN_STEPS.length;
  var pct = Math.round(((stepIndex + 1) / total) * 100);
  gsap.to("#login-progress", { width: pct + "%", duration: 0.4 });
  var currentEl = stepEls[stepIndex];
  if (currentEl) {
    gsap.fromTo(currentEl, { x: -6, opacity: 0.5 }, { x: 0, opacity: 1, duration: 0.3, ease: "power2.out" });
    currentEl.style.color = "var(--gold)";
  }
};

window.finishLogin = function(ok, message) {
  if (spinTween) spinTween.kill();
  if (pulseTween) pulseTween.kill();
  if (innerSpinTween) innerSpinTween.kill();
  var diamond = document.getElementById("login-diamond");
  var emblem = document.getElementById("login-emblem");
  if (ok) {
    var tier = (loginAccount.tier || "").trim().toUpperCase();
    if (tier && tier !== "UNRANKED") {
      gsap.set(diamond, { rotation: 0, scale: 1 });
      diamond.style.display = "none";
      document.getElementById("login-diamond-inner").style.display = "none";
      document.querySelector(".login-diamond-wrap").style.display = "none";
      emblem.src = "emblems/" + tier.toLowerCase() + ".png";
      emblem.style.display = "block";
      gsap.fromTo(emblem, { scale: 0.6 }, { scale: 1, duration: 0.5, ease: "back.out(1.7)" });
      gsap.fromTo(emblem, { filter: "drop-shadow(0 0 0px rgba(200,170,110,0))" }, { filter: "drop-shadow(0 0 24px rgba(200,170,110,0.55))", duration: 0.8, ease: "power2.out" });
    }
    document.getElementById("login-title").textContent = "YOU'RE IN!";
    var stepEls = document.querySelectorAll(".login-step");
    for (var i = 0; i < stepEls.length; i++) stepEls[i].classList.add("done");
    gsap.to("#login-progress", { width: "100%", duration: 0.4 });
  } else {
    gsap.set(diamond, { rotation: 0, scale: 1 });
    emblem.style.display = "none";
    document.getElementById("login-title").textContent = "COULDN'T SIGN IN";
  }
  document.getElementById("login-message").textContent = message;
  if (!ok) document.getElementById("login-message").style.color = "var(--danger)";
  var closeBtn = document.getElementById("login-close");
  closeBtn.style.display = "inline-block";
  gsap.to(closeBtn, { opacity: 1, duration: 0.3 });
};

function hideLogin() {
  var emblem = document.getElementById("login-emblem");
  gsap.set(emblem, { filter: "drop-shadow(0 0 0px rgba(200,170,110,0))" });
  var overlay = document.getElementById("login-screen");
  gsap.to(overlay, { opacity: 0, duration: 0.3, onComplete: function() {
    overlay.style.display = "none";
    var closeBtn = document.getElementById("login-close");
    closeBtn.style.display = "";
    closeBtn.style.opacity = "";
  }});
}

async function loadAccounts() {
  var accounts = await window.pywebview.api.list_accounts();
  render(accounts || []);
}
