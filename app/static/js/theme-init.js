/* Resolve the theme before first paint: the saved choice, else the operating system's setting.
   Loaded synchronously in <head> (an external file, because the CSP allows no inline scripts). */
(function () {
  var t = 'light';
  try {
    t = localStorage.getItem('mlc-theme');
    if (t !== 'light' && t !== 'dark') t = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch (e) {}
  document.documentElement.setAttribute('data-theme', t);
})();
