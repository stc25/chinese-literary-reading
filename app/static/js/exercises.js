/* Interactive exercises. Without this script every exercise still has its answer
   in a <details> element. Results are saved in this browser only (site.js). */
(function () {
  "use strict";

  var P = window.MLC && window.MLC.progress;
  var LETTER = /[\p{L}\p{N}]/u;
  var ASCII = { ",": "，", ".": "。", ";": "；", ":": "：", "?": "？", "!": "！", "(": "（", ")": "）" };
  var STATUS_TEXT = { correct: "✓ Correct", attempted: "Tried" };

  function showStatus(li, status) {
    var el = li.querySelector("[data-status]");
    if (!el || !status) return;
    el.hidden = false;
    el.textContent = STATUS_TEXT[status] || "";
    el.className = "exercise-status status-" + status;
  }

  function record(li, status) {
    var id = li.getAttribute("data-ex");
    var best = P ? P.setExercise(id, status) : status;
    showStatus(li, best);
    document.dispatchEvent(new CustomEvent("mlc:progress"));
  }

  function feedback(li, html, kind) {
    var el = li.querySelector(".exercise-feedback");
    el.innerHTML = html;
    el.className = "exercise-feedback" + (kind ? " fb-" + kind : "");
  }

  /* ---- choice ------------------------------------------------------------ */

  function setupChoice(li, form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var inputs = form.querySelectorAll("input");
      var chosen = 0, wrong = 0, missed = 0;
      inputs.forEach(function (inp) {
        var item = inp.closest("li");
        var mark = item.querySelector(".option-mark");
        var correct = inp.hasAttribute("data-correct");
        item.classList.remove("opt-right", "opt-wrong", "opt-missed");
        mark.textContent = "";
        if (inp.checked) chosen++;
        if (inp.checked && correct) { item.classList.add("opt-right"); mark.textContent = "✓"; }
        else if (inp.checked && !correct) { item.classList.add("opt-wrong"); mark.textContent = "✗"; wrong++; }
        else if (!inp.checked && correct && inp.type === "checkbox") { missed++; }
      });
      if (!chosen) { feedback(li, "Choose an answer first.", "info"); return; }
      if (!wrong && !missed) {
        feedback(li, "<strong>Correct.</strong>", "right");
        li.querySelector("details.answer").open = true;
        record(li, "correct");
      } else {
        var msg = wrong ? "Not quite. Try again, or show the answer." : "Some correct answers are missing. Try again.";
        feedback(li, msg, "wrong");
        record(li, "attempted");
      }
    });
    form.addEventListener("change", function () {
      form.querySelectorAll("li").forEach(function (item) {
        item.classList.remove("opt-right", "opt-wrong");
        item.querySelector(".option-mark").textContent = "";
      });
    });
  }

  /* ---- written answers --------------------------------------------------- */

  function setupWritten(li) {
    li.querySelectorAll("[data-self]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        record(li, btn.getAttribute("data-self"));
        feedback(li, btn.getAttribute("data-self") === "correct" ? "Well done." : "Noted. Come back to it later.", "info");
      });
    });
  }

  /* ---- punctuation ------------------------------------------------------- */

  /* Split a string into its letters and the punctuation in each gap:
     gaps[0] is before the first letter, gaps[i] after letter i. */
  function parse(s) {
    var letters = [], gaps = [""];
    Array.from(s).forEach(function (c) {
      if (LETTER.test(c)) { letters.push(c); gaps.push(""); }
      else if (!/\s/.test(c)) gaps[gaps.length - 1] += ASCII[c] || c;
    });
    return { letters: letters, gaps: gaps };
  }

  var BREAKS = /[，。、；：？！…—]/;   // marks that divide the text; quotation marks alone do not
  function hasBreak(g) { return BREAKS.test(g); }

  function esc(s) {
    return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }

  /* Compare a learner's punctuation with the answer, gap by gap. Exposed for testing. */
  function comparePunctuation(learner, answer) {
    var L = parse(learner), A = parse(answer);
    if (L.letters.join("") !== A.letters.join("")) return { ok: false };
    var right = 0, missed = 0, extra = 0, total = 0, html = "";
    for (var i = 0; i < A.gaps.length; i++) {
      var a = A.gaps[i], l = L.gaps[i], ab = hasBreak(a), lb = hasBreak(l);
      if (ab) total++;
      if (ab && lb) { right++; html += '<span class="pm pm-right" title="Correct">' + esc(l) + "</span>"; }
      else if (ab) { missed++; html += '<span class="pm pm-missed" title="Missing: ' + esc(a) + '">' + esc(a) + "</span>"; }
      else if (lb) { extra++; html += '<span class="pm pm-extra" title="Not needed here">' + esc(l) + "</span>"; }
      else if (a) html += esc(a);   // quotation marks only
      if (i < A.letters.length) html += esc(A.letters[i]);
    }
    return { ok: true, right: right, missed: missed, extra: extra, total: total, html: html };
  }

  function setupPunctuate(li, form) {
    var input = form.querySelector("textarea");
    var answer = JSON.parse(form.querySelector(".punct-answer").textContent);
    var result = form.querySelector(".punct-result");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var r = comparePunctuation(input.value, answer);
      if (!r.ok) {
        result.innerHTML = "";
        feedback(li, "The characters have changed. Only add punctuation; use <em>Start again</em> to restore the text.", "wrong");
        return;
      }
      var perfect = !r.missed && !r.extra;
      var summary = (perfect ? "<strong>All " + r.total + " breaks are right.</strong>" :
        "You placed " + r.right + " of " + r.total + " breaks." +
        (r.missed ? " " + r.missed + " missing." : "") + (r.extra ? " " + r.extra + " not needed." : ""));
      feedback(li, "", "");
      result.innerHTML = '<p class="punct-summary ' + (perfect ? "fb-right" : "fb-wrong") + '">' + summary + "</p>" +
        '<p class="punct-compare zh" lang="zh-Hant">' + r.html + "</p>" +
        (perfect ? "" : '<p class="hint punct-legend"><span class="pm pm-right">，</span> right · <span class="pm pm-missed">，</span> missing · <span class="pm pm-extra">，</span> not needed. The exact mark is not checked: compare with the answer.</p>');
      record(li, perfect ? "correct" : "attempted");
    });
    form.querySelector("[data-action='reset-text']").addEventListener("click", function () {
      input.value = input.getAttribute("data-text");
      result.innerHTML = "";
      feedback(li, "", "");
      input.focus();
    });
  }

  /* ---- set up ------------------------------------------------------------ */

  document.querySelectorAll(".exercise").forEach(function (li) {
    li.querySelectorAll(".js-only").forEach(function (el) { el.hidden = false; });
    var form = li.querySelector(".exercise-form");
    var type = li.getAttribute("data-type");
    if (type === "choice" && form) setupChoice(li, form);
    else if (type === "punctuate" && form) setupPunctuate(li, form);
    else setupWritten(li);
    if (P) showStatus(li, P.exercise(li.getAttribute("data-ex")));
  });

  window.MLC = window.MLC || {};
  window.MLC.comparePunctuation = comparePunctuation;
})();
