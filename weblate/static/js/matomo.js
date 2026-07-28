// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

const matomoTracker = document.getElementById("matomo-tracker");

// biome-ignore lint/suspicious/noAssignInExpressions: keep upstream compatibility
const _paq = (window._paq = window._paq || []);
const customVariables = {
  Language: matomoTracker.dataset.language,
};
if (matomoTracker.dataset.project !== undefined) {
  customVariables.Project = matomoTracker.dataset.project;
}

let trackId = 1;
for (const [key, value] of Object.entries(customVariables)) {
  _paq.push(["setCustomVariable", trackId, key, value, "page"]);
  trackId++;
}
_paq.push(["disableCookies"]);
_paq.push(["trackPageView"]);
_paq.push(["enableLinkTracking"]);
_paq.push(["setTrackerUrl", `${matomoTracker.dataset.url}matomo.php`]);
_paq.push(["setSiteId", matomoTracker.dataset.siteId]);

const matomoScript = document.createElement("script");
matomoScript.async = true;
matomoScript.defer = true;
matomoScript.src = `${matomoTracker.dataset.url}matomo.js`;
const firstScript = document.getElementsByTagName("script")[0];
firstScript.parentNode.insertBefore(matomoScript, firstScript);
