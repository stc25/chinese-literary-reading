/* The passage reader: glosses, layouts and translations.
   The page works without this script: layouts are links, glosses are in a
   table, and translations are <details> elements. */
(function () {
  "use strict";

  var reader = document.querySelector(".reader");
  var panel = document.getElementById("gloss-panel");
  var dataEl = document.getElementById("gloss-data");
  if (!reader || !panel || !dataEl) return;

  var glosses = JSON.parse(dataEl.textContent);
  var body = panel.querySelector(".gloss-panel-body");
  var title = panel.querySelector(".gloss-panel-title");
  var current = null;          // the button whose glosses are shown
  var wideQuery = window.matchMedia("(min-width: 48rem)");

  /* ---- glosses ---------------------------------------------------------- */

  function visibleBlock() {
    var view = reader.getAttribute("data-view");
    var orig = reader.querySelector(".text-original");
    return (orig && view !== "modern") ? orig : reader.querySelector(".text-modern");
  }

  function clearHighlight() {
    reader.querySelectorAll(".g.hl, .g.hl-main").forEach(function (el) {
      el.classList.remove("hl", "hl-main");
    });
  }

  function glossIndices(btn) {
    var seen = {}, out = [];
    btn.getAttribute("data-occ").split(" ").forEach(function (id) {
      var gi = parseInt(id.split("-")[0], 10);
      if (!seen[gi]) { seen[gi] = true; out.push(gi); }
    });
    // longest term first; ties keep table order
    out.sort(function (a, b) { return (glosses[b].len - glosses[a].len) || (a - b); });
    return out;
  }

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  function text(tag, cls, s) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    e.textContent = s;
    return e;
  }

  function fillPanel(btn) {
    var list = glossIndices(btn);
    body.innerHTML = "";
    title.textContent = glosses[list[0]].term;
    title.setAttribute("lang", "zh-Hant");
    list.forEach(function (gi, i) {
      var g = glosses[gi];
      var item = el("div", "gloss-item" + (i === 0 ? " gloss-main" : ""));
      if (i > 0) {
        var t = text("p", "gloss-term zh", g.term);
        t.setAttribute("lang", "zh-Hant");
        item.appendChild(t);
      }
      var py = text("p", "gloss-pinyin pinyin", g.pinyin);
      py.setAttribute("lang", "zh-Latn-pinyin");
      item.appendChild(py);
      item.appendChild(el("p", "gloss-text", g.gloss));   // server-rendered, escaped Markdown
      if (g.from) {
        var f = el("p", "gloss-from");
        var fa = text("a", "", "Unit " + g.from.unit + ": " + g.from.title);
        fa.href = g.from.url;
        f.appendChild(document.createTextNode(g.fromLabel || "Glossed earlier, in "));
        f.appendChild(fa);
        f.appendChild(document.createTextNode(g.fromNote !== undefined ? g.fromNote : ". The sense here may differ."));
        item.appendChild(f);
      }
      if (g.ref) {
        var p = el("p", "gloss-ref");
        var a = text("a", "xref", g.refTitle);
        a.href = g.ref;
        a.setAttribute("data-ref", g.ref);
        p.appendChild(document.createTextNode("Grammar: "));
        p.appendChild(a);
        item.appendChild(p);
      }
      body.appendChild(item);
    });
    if (list.length > 1) {
      body.appendChild(text("p", "gloss-note", "This word is part of " + (list.length - 1 === 1 ? "a longer glossed phrase." : "longer glossed phrases.")));
    }
  }

  function highlight(btn) {
    clearHighlight();
    var block = btn.closest(".zh-text");
    btn.getAttribute("data-occ").split(" ").forEach(function (id) {
      block.querySelectorAll('.g[data-occ~="' + id + '"]').forEach(function (e) { e.classList.add("hl"); });
    });
    btn.classList.add("hl-main");
  }

  function position(btn) {
    if (!wideQuery.matches) {
      panel.classList.add("sheet");
      panel.style.left = panel.style.top = "";
      return;
    }
    panel.classList.remove("sheet");
    var r = btn.getBoundingClientRect();
    var pw = panel.offsetWidth, ph = panel.offsetHeight;
    var vw = document.documentElement.clientWidth, vh = window.innerHeight;
    var vertical = reader.getAttribute("data-view").indexOf("vertical") === 0;
    var left, top;
    if (vertical) {
      // beside the column, to the left if there is room
      left = r.left - pw - 8;
      if (left < 8) left = r.right + 8;
      top = Math.min(Math.max(8, r.top), vh - ph - 8);
    } else {
      left = Math.min(Math.max(8, r.left), vw - pw - 8);
      top = r.bottom + 8;
      if (top + ph > vh - 8 && r.top - ph - 8 > 8) top = r.top - ph - 8;
    }
    panel.style.left = (left + window.scrollX) + "px";
    panel.style.top = (top + window.scrollY) + "px";
  }

  function open(btn) {
    if (current) current.setAttribute("aria-expanded", "false");
    current = btn;
    fillPanel(btn);
    highlight(btn);
    btn.setAttribute("aria-expanded", "true");
    panel.hidden = false;
    position(btn);
    panel.focus({ preventScroll: true });
  }

  function close(returnFocus) {
    if (panel.hidden) return;
    panel.hidden = true;
    clearHighlight();
    if (current) {
      current.setAttribute("aria-expanded", "false");
      if (returnFocus) current.focus();
    }
    current = null;
  }

  reader.addEventListener("click", function (e) {
    var btn = e.target.closest(".g");
    if (!btn) return;
    e.stopPropagation();
    if (btn === current && !panel.hidden) { close(false); return; }
    open(btn);
  });

  panel.querySelector(".gloss-panel-close").addEventListener("click", function () { close(true); });

  document.addEventListener("click", function (e) {
    if (!panel.hidden && !panel.contains(e.target) && !e.target.closest(".g")) close(false);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden) { e.preventDefault(); close(true); }
  });

  /* The text is a single Tab stop ("roving tabindex"): one glossed word is
     focusable at a time, and the arrow keys move between words in reading order. */
  function words() {
    return Array.prototype.filter.call(visibleBlock().querySelectorAll(".g"), function (b) {
      return b.offsetParent !== null;  // skip hidden punctuation
    });
  }

  function makeCurrent(btn) {
    reader.querySelectorAll('.g[tabindex="0"]').forEach(function (b) { b.setAttribute("tabindex", "-1"); });
    if (btn) btn.setAttribute("tabindex", "0");
  }

  function resetRoving() {
    var all = words();
    makeCurrent(all[0]);
  }

  reader.addEventListener("focusin", function (e) {
    var btn = e.target.closest(".g");
    if (btn) makeCurrent(btn);
  });

  reader.addEventListener("keydown", function (e) {
    var btn = e.target.closest(".g");
    if (!btn) return;
    var all = words(), i = all.indexOf(btn), j = null;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") j = i + 1;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") j = i - 1;
    else if (e.key === "Home") j = 0;
    else if (e.key === "End") j = all.length - 1;
    if (j === null) return;
    e.preventDefault();
    if (j >= 0 && j < all.length) { makeCurrent(all[j]); all[j].focus(); }
  });

  window.addEventListener("resize", function () { if (current && !panel.hidden) position(current); });

  /* ---- layouts ---------------------------------------------------------- */

  var links = reader.querySelectorAll(".view-switch a[data-view]");

  function setView(view, push) {
    close(false);
    reader.className = reader.className.replace(/\bview-[a-z-]+/, "view-" + view);
    reader.setAttribute("data-view", view);
    links.forEach(function (a) {
      if (a.getAttribute("data-view") === view) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
    resetRoving();
    if (push) {
      var url = new URL(window.location.href);
      url.searchParams.set("view", view);
      url.hash = "";
      window.history.replaceState(null, "", url);
    }
  }

  links.forEach(function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      setView(a.getAttribute("data-view"), true);
    });
  });

  /* ---- translations ----------------------------------------------------- */

  var toggleAll = document.querySelector("[data-action='toggle-all-translations']");
  if (toggleAll) {
    toggleAll.parentNode.hidden = false;
    var paras = document.querySelectorAll(".translations details.translation-para");
    function sync() {
      var allOpen = Array.prototype.every.call(paras, function (d) { return d.open; });
      toggleAll.textContent = allOpen ? "Hide all" : "Show all";
      toggleAll.setAttribute("aria-pressed", allOpen ? "true" : "false");
    }
    toggleAll.addEventListener("click", function () {
      var allOpen = Array.prototype.every.call(paras, function (d) { return d.open; });
      paras.forEach(function (d) { d.open = !allOpen; });
      sync();
    });
    paras.forEach(function (d) { d.addEventListener("toggle", sync); });
    sync();
  }

  resetRoving();
  document.documentElement.classList.add("reader-ready");
})();
