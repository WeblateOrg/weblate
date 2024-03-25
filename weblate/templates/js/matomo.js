// biome-ignore lint/style/noVar: keep upstream compatibility
// biome-ignore lint/suspicious/noAssignInExpressions: keep upstream compatibility
var _paq = (window._paq = window._paq || []);
let _track_id = 1;
const _track_params = JSON.parse(
  document.getElementById("matomo-tracker").dataset.params,
);
for (const [key, value] of Object.entries(_track_params)) {
  _paq.push(["setCustomVariable", _track_id, key, value, "page"]);
  _track_id++;
}
_paq.push(["disableCookies"]);
_paq.push(["trackPageView"]);
_paq.push(["enableLinkTracking"]);
(() => {
  _paq.push(["setTrackerUrl", "{{ matomo_url|escapejs }}matomo.php"]);
  _paq.push(["setSiteId", "{{ matomo_site_id|escapejs }}"]);
  const g = document.createElement("script");
  g.type = "text/javascript";
  g.async = true;
  g.defer = true;
  g.src = "{{ matomo_url|escapejs }}matomo.js";
  const s = document.getElementsByTagName("script")[0];
  s.parentNode.insertBefore(g, s);
})();
