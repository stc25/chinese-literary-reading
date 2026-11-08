/* Site-wide behaviour: preferences kept in the learner's own browser. */
(function () {
  "use strict";

  var KEY = "mlc.prefs";

  function readPrefs() {
    try {
      return JSON.parse(window.localStorage.getItem(KEY)) || {};
    } catch (e) {
      return {};
    }
  }

  function writePrefs(prefs) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(prefs));
    } catch (e) { /* storage unavailable: preferences last for this page only */ }
  }

  var prefs = readPrefs();
  window.MLC = window.MLC || {};
  window.MLC.prefs = prefs;
  window.MLC.savePrefs = function () { writePrefs(prefs); };

  var root = document.documentElement;

  function applyPinyin() {
    root.classList.toggle("show-pinyin", !!prefs.pinyin);
    var btn = document.querySelector("[data-action='toggle-pinyin']");
    if (btn) {
      btn.setAttribute("aria-pressed", prefs.pinyin ? "true" : "false");
      btn.querySelector(".state").textContent = prefs.pinyin ? "on" : "off";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.querySelector("[data-action='toggle-pinyin']");
    if (btn) {
      btn.hidden = false;
      btn.addEventListener("click", function () {
        prefs.pinyin = !prefs.pinyin;
        writePrefs(prefs);
        applyPinyin();
      });
    }
    applyPinyin();
  });

  applyPinyin();

  /* ---- tooltips: summaries of grammar and toolkit pages --------------------- */

  var summariesUrl = document.currentScript && document.currentScript.getAttribute("data-summaries");
  var summaries = null;      // a promise, fetched on first use
  var tip = null, tipFor = null, hideTimer = null;

  function loadSummaries() {
    if (!summaries) {
      summaries = fetch(summariesUrl, { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : {}; })
        .catch(function () { return {}; });
    }
    return summaries;
  }

  function ensureTip() {
    if (!tip) {
      tip = document.createElement("div");
      tip.id = "xref-tip";
      tip.className = "xref-tip";
      tip.setAttribute("role", "tooltip");
      tip.hidden = true;
      tip.addEventListener("mouseenter", function () { clearTimeout(hideTimer); });
      tip.addEventListener("mouseleave", scheduleHide);
      document.body.appendChild(tip);
    }
    return tip;
  }

  function showTip(link) {
    clearTimeout(hideTimer);
    var ref = link.getAttribute("data-ref");
    loadSummaries().then(function (data) {
      var item = data[ref];
      if (!item) return;
      var t = ensureTip();
      t.innerHTML = "";
      var h = document.createElement("strong");
      h.textContent = item.title;
      var p = document.createElement("span");
      p.innerHTML = item.summary;     // server-rendered, escaped Markdown
      t.appendChild(h);
      t.appendChild(document.createElement("br"));
      t.appendChild(p);
      t.hidden = false;
      tipFor = link;
      link.setAttribute("aria-describedby", "xref-tip");
      var r = link.getBoundingClientRect();
      var w = t.offsetWidth, vw = document.documentElement.clientWidth;
      var left = Math.min(Math.max(8, r.left), vw - w - 8);
      var top = r.bottom + 6;
      if (top + t.offsetHeight > window.innerHeight - 8) top = r.top - t.offsetHeight - 6;
      t.style.left = (left + window.scrollX) + "px";
      t.style.top = (top + window.scrollY) + "px";
    });
  }

  function hideTip() {
    if (tip) tip.hidden = true;
    if (tipFor) tipFor.removeAttribute("aria-describedby");
    tipFor = null;
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hideTip, 150);
  }

  function xref(e) {
    return e.target.closest ? e.target.closest("a[data-ref]") : null;
  }

  if (summariesUrl && window.fetch) {
    document.addEventListener("mouseover", function (e) { var a = xref(e); if (a) showTip(a); });
    document.addEventListener("mouseout", function (e) { var a = xref(e); if (a) scheduleHide(); });
    document.addEventListener("focusin", function (e) { var a = xref(e); if (a) showTip(a); });
    document.addEventListener("focusout", function (e) { var a = xref(e); if (a) hideTip(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") hideTip(); });
  }
})();
