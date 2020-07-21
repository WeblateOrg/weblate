var _paq = (window._paq = window._paq || []);
var _track_id = 1;
var _track_params = JSON.parse(
  document.getElementById("matomo-tracker").dataset.params
);
for (const [key, value] of Object.entries(_track_params)) {
  _paq.push(["setCustomVariable", _track_id, key, value, "page"]);
  _track_id++;
}
_paq.push(["disableCookies"]);
_paq.push(["trackPageView"]);
_paq.push(["enableLinkTracking"]);
(function () {
  _paq.push(["setTrackerUrl", "{{ matomo_url|escapejs }}matomo.php"]);
  _paq.push(["setSiteId", "{{ matomo_site_id|escapejs }}"]);
  var d = document,
    g = d.createElement("script"),
    s = d.getElementsByTagName("script")[0];
  g.type = "text/javascript";
  g.async = true;
  g.defer = true;
  g.src = "{{ matomo_url|escapejs }}matomo.js";
  s.parentNode.insertBefore(g, s);
})();
