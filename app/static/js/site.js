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
})();
