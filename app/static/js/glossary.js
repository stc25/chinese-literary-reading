/* Live filtering of the glossary. Without JavaScript the search form reloads the page. */
(function () {
  "use strict";
  var input = document.getElementById("gloss-q");
  var count = document.querySelector(".search-count");
  if (!input) return;
  var rows = Array.prototype.slice.call(document.querySelectorAll(".glossary-table tbody tr"));
  var groups = Array.prototype.slice.call(document.querySelectorAll(".gloss-group"));
  var nav = document.querySelector(".letter-nav");

  function plain(s) {
    return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ü/g, "v").replace(/\s+/g, "");
  }

  var timer = null;
  function filter() {
    var q = input.value.trim();
    var pq = plain(q), lq = q.toLowerCase();
    var shown = 0;
    rows.forEach(function (tr) {
      var hay = tr.getAttribute("data-search");
      var ok = !q || hay.indexOf(q) !== -1 || hay.indexOf(pq) !== -1 || hay.indexOf(lq) !== -1;
      tr.hidden = !ok;
      if (ok) shown++;
    });
    groups.forEach(function (sec) {
      sec.hidden = !sec.querySelector("tbody tr:not([hidden])");
    });
    if (nav) nav.hidden = !!q;
    count.textContent = shown + (shown === 1 ? " entry" : " entries") + (q ? " matching “" + q + "”" : "");
  }

  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(filter, 120);
  });
  input.form.addEventListener("submit", function (e) {
    e.preventDefault();
    filter();
    var url = new URL(window.location.href);
    if (input.value.trim()) url.searchParams.set("q", input.value.trim()); else url.searchParams.delete("q");
    window.history.replaceState(null, "", url);
  });
})();
