/* Light/dark switch. theme-init.js has already set data-theme on <html>. */
(function () {
  var root = document.documentElement;
  var sw = document.getElementById('theme-switch');
  if (!sw) return;
  function sync() { sw.setAttribute('aria-checked', root.getAttribute('data-theme') === 'dark' ? 'true' : 'false'); }
  sync();
  sw.addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('mlc-theme', next); } catch (e) {}
    sync();
  });
  /* Follow the system only while the reader has not made a choice. */
  try {
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      var saved = null;
      try { saved = localStorage.getItem('mlc-theme'); } catch (x) {}
      if (saved === 'light' || saved === 'dark') return;
      root.setAttribute('data-theme', e.matches ? 'dark' : 'light');
      sync();
    });
  } catch (e) {}
})();
