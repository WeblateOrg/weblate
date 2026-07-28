// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

const googleAnalyticsTracker = document.getElementById(
  "google-analytics-tracker",
);

window.GoogleAnalyticsObject = "ga";
if (typeof window.ga !== "function") {
  const queue = [];
  const ga = (...args) => {
    queue.push(args);
  };
  ga.q = queue;
  ga.l = Date.now();
  window.ga = ga;
}

const analyticsScript = document.createElement("script");
analyticsScript.async = true;
analyticsScript.src = "https://www.google-analytics.com/analytics.js";
document.head.append(analyticsScript);

window.ga("create", googleAnalyticsTracker.dataset.trackingId, "auto");

const pageView = {
  dimension1: googleAnalyticsTracker.dataset.language,
};
if (googleAnalyticsTracker.dataset.project !== undefined) {
  pageView.dimension2 = googleAnalyticsTracker.dataset.project;
}
window.ga("send", "pageview", pageView);
