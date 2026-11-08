/* Site-wide behaviour: preferences kept in the learner's own browser. */
(function () {
  "use strict";

  // Loaded in <head>: lets the CSS know that JavaScript is available before the page is drawn.
  document.documentElement.classList.add("js");

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

  /* ---- progress: kept only in this browser -------------------------------- */

  var PKEY = "mlc.progress";
  var RANK = { attempted: 1, correct: 2 };

  function readProgress() {
    try {
      var p = JSON.parse(window.localStorage.getItem(PKEY)) || {};
      p.ex = p.ex || {};
      p.visited = p.visited || {};
      return p;
    } catch (e) {
      return { ex: {}, visited: {} };
    }
  }

  var progress = readProgress();

  function saveProgress() {
    try { window.localStorage.setItem(PKEY, JSON.stringify(progress)); } catch (e) { /* not available */ }
  }

  window.MLC.progress = {
    data: progress,
    exercise: function (id) { return progress.ex[id] || null; },
    /* Record a result; a better result is never replaced by a worse one. */
    setExercise: function (id, status) {
      if ((RANK[status] || 0) >= (RANK[progress.ex[id]] || 0)) progress.ex[id] = status;
      saveProgress();
      return progress.ex[id];
    },
    visit: function (id, url, title) {
      progress.visited[id] = Date.now();
      progress.last = { id: id, url: url, title: title };
      saveProgress();
    },
    /* A passage counts as done when it has been read and every exercise has been tried. */
    passageDone: function (id, exerciseCount) {
      if (!progress.visited[id]) return false;
      for (var n = 1; n <= exerciseCount; n++) if (!progress.ex[id + "#" + n]) return false;
      return true;
    },
    exercisesDone: function (id, exerciseCount) {
      var k = 0;
      for (var n = 1; n <= exerciseCount; n++) if (progress.ex[id + "#" + n]) k++;
      return k;
    },
    reset: function () {
      progress.ex = {}; progress.visited = {}; delete progress.last;
      saveProgress();
    }
  };

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
    document.querySelectorAll(".js-only").forEach(function (el) { el.hidden = false; });
    recordVisit();
    showProgress();
    var reset = document.querySelector("[data-action='reset-progress']");
    if (reset) {
      reset.addEventListener("click", function () {
        if (!window.confirm("Reset your progress? This removes the record of passages read and exercises tried in this browser.")) return;
        window.MLC.progress.reset();
        showProgress();
        document.querySelector("[data-reset-done]").textContent = "Progress reset.";
      });
    }
  });

  document.addEventListener("mlc:progress", function () { showProgress(); });

  function recordVisit() {
    var art = document.querySelector("article[data-passage]");
    if (art) window.MLC.progress.visit(art.getAttribute("data-passage"), window.location.pathname, art.getAttribute("data-title"));
  }

  function showProgress() {
    var P = window.MLC.progress;
    // passage page: exercises tried
    document.querySelectorAll("[data-ex-progress]").forEach(function (el) {
      var n = parseInt(el.getAttribute("data-count"), 10), k = P.exercisesDone(el.getAttribute("data-ex-progress"), n);
      el.hidden = false;
      el.textContent = k === n ? "You have tried all " + n + " exercises." : "Exercises tried: " + k + " of " + n + ".";
    });
    // unit page: each passage
    document.querySelectorAll(".passage-card[data-passage]").forEach(function (card) {
      var id = card.getAttribute("data-passage"), n = parseInt(card.getAttribute("data-exercises"), 10);
      var mark = card.querySelector("[data-progress]");
      var done = P.passageDone(id, n), read = !!P.data.visited[id];
      mark.hidden = !read;
      mark.className = "progress-mark" + (done ? " done" : "");
      mark.textContent = done ? "✓ Done" : read ? "Read · exercises " + P.exercisesDone(id, n) + "/" + n : "";
    });
    // course map: each unit
    document.querySelectorAll(".unit-card[data-unit-passages]").forEach(function (card) {
      var items = JSON.parse(card.getAttribute("data-unit-passages"));
      var done = items.filter(function (it) { return P.passageDone(it[0], it[1]); }).length;
      var started = items.some(function (it) { return P.data.visited[it[0]]; });
      var mark = card.querySelector("[data-progress]");
      mark.hidden = !started;
      mark.className = "progress-mark" + (done === items.length ? " done" : "");
      mark.textContent = done === items.length ? "✓ Done" : done + " of " + items.length + " passages done";
    });
    var cont = document.querySelector("[data-continue]");
    if (cont) {
      var last = P.data.last;
      cont.hidden = !last;
      if (last) {
        var a = cont.querySelector("[data-continue-link]");
        a.href = last.url;
        a.textContent = last.title;
      }
    }
  }

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
