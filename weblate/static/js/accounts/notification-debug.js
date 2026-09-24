// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const overviewTab = document.getElementById("overview-tab");

  function highlightSubscription(row) {
    document
      .querySelectorAll(".notification-subscription-highlight")
      .forEach((previous) => {
        previous.classList.remove("notification-subscription-highlight");
      });
    row.classList.add("notification-subscription-highlight");
    row.focus({ preventScroll: true });
    row.scrollIntoView({ block: "center" });
    history.replaceState(null, "", `#${row.id}`);
  }

  function showSubscription(row) {
    if (!overviewTab) {
      return;
    }
    if (overviewTab.classList.contains("active")) {
      highlightSubscription(row);
    } else {
      overviewTab.addEventListener(
        "shown.bs.tab",
        () => highlightSubscription(row),
        { once: true },
      );
      bootstrap.Tab.getOrCreateInstance(overviewTab).show();
    }
  }

  document
    .querySelectorAll("a[data-notification-subscription]")
    .forEach((link) => {
      link.addEventListener("click", (event) => {
        const row = document.getElementById(link.hash.slice(1));
        if (!row || !overviewTab) {
          return;
        }
        event.preventDefault();
        showSubscription(row);
      });
    });

  function showLinkedSubscription() {
    if (location.hash.startsWith("#overview__notification-subscription-")) {
      const row = document.getElementById(location.hash.slice(1));
      if (row) {
        showSubscription(row);
      }
    }
  }

  window.addEventListener("popstate", showLinkedSubscription);
  showLinkedSubscription();
});
