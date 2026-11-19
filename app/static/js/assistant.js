/* The reading assistant's AI steps and questions. The course steps on the page are
   rendered by the server and work without this script. Model output is always
   inserted as text, never as HTML. */
(function () {
  "use strict";

  var result = document.getElementById("result");
  if (!result || !result.getAttribute("data-text")) return;
  var TEXT = result.getAttribute("data-text");
  var API = result.getAttribute("data-api");
  var CSRF = result.getAttribute("data-csrf");
  var history = [];

  document.querySelectorAll(".js-only").forEach(function (el) { el.hidden = false; });

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function zh(tag, cls, text) {
    var e = el(tag, cls, text);
    e.setAttribute("lang", "zh-Hant");
    return e;
  }

  function aiHeader(model) {
    var h = el("p", "ai-label");
    var tag = el("span", "source-tag source-ai", "AI");
    h.appendChild(tag);
    h.appendChild(document.createTextNode(" Suggestion from " + model + ". Check it before you rely on it."));
    return h;
  }

  function call(step, body) {
    body.text = TEXT;
    var ctrl = window.AbortController ? new AbortController() : null;
    if (ctrl) setTimeout(function () { ctrl.abort(); }, 150000);
    return fetch(API + step, {
      method: "POST",
      signal: ctrl ? ctrl.signal : undefined,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return { ok: false, error: "The server returned an unexpected answer." }; });
    }, function (e) {
      if (e && e.name === "AbortError") return { ok: false, error: "The AI service took too long to answer. Please try again, or try a shorter text." };
      return { ok: false, error: "The server could not be reached. Check your connection and try again." };
    }).then(function (d) {
      if (d && typeof d.remaining === "number") {
        var rem = document.querySelector(".remaining");
        rem.textContent = "AI suggestions left today: " + d.remaining + ".";
      }
      return d;
    });
  }

  /* ---- rendering each step ------------------------------------------------ */

  var render = {
    punctuate: function (d, out) {
      out.appendChild(zh("p", "zh ai-punctuated", d.punctuated));
      out.appendChild(el("p", "hint", "Punctuation decides where clauses end: check that each break makes sense."));
    },
    words: function (d, out) {
      if (!d.words.length) { out.appendChild(el("p", "", "The AI gave no glosses for the uncovered words.")); return; }
      var wrap = el("div", "table-wrap"), t = el("table", "ai-words");
      wrap.tabIndex = 0;        // a scrollable region must be reachable by keyboard
      var head = el("tr");
      ["Word", "Pinyin", "Gloss"].forEach(function (h, i) {
        var th = el("th", i === 1 ? "pinyin-col" : "", h); th.scope = "col"; head.appendChild(th);
      });
      var thead = el("thead"); thead.appendChild(head); t.appendChild(thead);
      var tb = el("tbody"), phrases = false;
      d.words.forEach(function (w) {
        var tr = el("tr");
        var wd = zh("td", "zh", w.word);
        if (w.phrase) { wd.appendChild(el("span", "ai-kind ai-check", "phrase")); phrases = true; }
        tr.appendChild(wd);
        var py = el("td", "pinyin pinyin-col", w.pinyin); py.setAttribute("lang", "zh-Latn-pinyin"); tr.appendChild(py);
        tr.appendChild(el("td", "", w.gloss));
        tb.appendChild(tr);
      });
      t.appendChild(tb); wrap.appendChild(t); out.appendChild(wrap);
      if (phrases) out.appendChild(el("p", "hint", "Items marked “phrase” are longer than a word: the AI has explained a whole phrase. Work out its words from the course glossary and a dictionary."));
      if (d.incomplete) out.appendChild(el("p", "ai-error", "Part of the text could not be glossed this time. Try again for the rest."));
    },
    grammar: function (d, out) {
      if (!d.notes.length) { out.appendChild(el("p", "", "The AI gave no notes.")); return; }
      var ul = el("ul", "ai-notes");
      d.notes.forEach(function (n) {
        var li = el("li");
        li.appendChild(zh("span", "zh ai-form", n.form));
        li.appendChild(document.createTextNode(" in "));
        li.appendChild(zh("span", "zh", "「" + n.clause + "」"));
        if (n.grammar_id) {
          li.appendChild(document.createTextNode(" · "));
          var a = el("a", "xref", n.grammar_title);
          a.href = "/grammar/" + encodeURIComponent(n.grammar_id);
          a.setAttribute("data-ref", "/grammar/" + n.grammar_id);
          li.appendChild(a);
        }
        li.appendChild(el("span", "ai-note", n.note));
        ul.appendChild(li);
      });
      out.appendChild(ul);
    },
    names: function (d, out) {
      if (!d.items.length) { out.appendChild(el("p", "", "The AI found no names, titles or allusions.")); return; }
      var ul = el("ul", "ai-names");
      var kinds = { person: "person", place: "place", title: "title", office: "office", book: "book",
                    allusion: "allusion: check the source", other: "" };
      d.items.forEach(function (it) {
        var li = el("li");
        li.appendChild(zh("span", "zh ai-form", it.text));
        if (kinds[it.kind]) li.appendChild(el("span", "ai-kind" + (it.kind === "allusion" ? " ai-check" : ""), kinds[it.kind]));
        li.appendChild(el("span", "ai-note", it.note));
        ul.appendChild(li);
      });
      out.appendChild(ul);
      out.appendChild(el("p", "hint", "Names and allusions are where AI is most often wrong: check them in the reference works listed in the toolkit."));
    },
    translate: function (d, out) {
      out.appendChild(el("p", "ai-translation", d.translation));
      if (d.literal) {
        out.appendChild(el("p", "ai-sub", "Literal:"));
        out.appendChild(el("p", "ai-translation", d.literal));
      }
    }
  };

  function showError(out, msg) {
    var p = el("p", "ai-error", msg);
    p.setAttribute("role", "alert");
    out.appendChild(p);
  }

  document.querySelectorAll("[data-run]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var step = btn.getAttribute("data-run");
      var box = btn.closest(".ai-step");
      var out = box.querySelector(":scope > .ai-out");
      var body = {};
      if (step === "translate") body.literal = !!box.querySelector("[data-literal]") && box.querySelector("[data-literal]").checked;
      out.innerHTML = "";
      var label = btn.innerHTML;
      btn.disabled = true;
      btn.setAttribute("aria-busy", "true");
      out.appendChild(el("p", "ai-working", "Working… this can take up to a minute."));
      call(step, body).then(function (d) {
        out.innerHTML = "";
        btn.removeAttribute("aria-busy");
        if (!d || !d.ok) {
          btn.disabled = false;
          showError(out, (d && d.error) || "Something went wrong.");
          return;
        }
        out.appendChild(aiHeader(d.model));
        render[step](d.data, out);
        btn.hidden = true;            // each step runs once per text, to save the AI allowance
        btn.innerHTML = label;
        var lit = box.querySelector("[data-literal]");
        if (lit) lit.closest("p").hidden = true;
      });
    });
  });

  /* ---- questions ----------------------------------------------------------- */

  var form = document.querySelector(".ask-form");
  if (form) {
    var input = form.querySelector("input");
    var list = document.querySelector(".qa-list");
    var err = form.querySelector(".ai-error");
    var button = form.querySelector("button");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var q = input.value.trim();
      err.textContent = "";
      if (!q) { err.textContent = "Type a question first."; return; }
      button.disabled = true;
      var li = el("li", "qa");
      li.appendChild(el("p", "qa-q", q));
      var a = el("p", "qa-a ai-working", "Working…");
      li.appendChild(a);
      list.appendChild(li);
      call("ask", { question: q, history: history }).then(function (d) {
        button.disabled = false;
        if (!d || !d.ok) {
          li.remove();
          err.textContent = (d && d.error) || "Something went wrong.";
          return;
        }
        a.className = "qa-a";
        a.textContent = "";
        a.appendChild(el("span", "source-tag source-ai", "AI"));
        a.appendChild(document.createTextNode(" " + d.data.answer));
        history.push({ q: q, a: d.data.answer });
        input.value = "";
        if (history.length >= 10) {
          input.disabled = true;
          button.disabled = true;
          err.textContent = "You have asked 10 questions about this text. Analyse it again to start a new conversation.";
        }
      });
    });
  }
})();
