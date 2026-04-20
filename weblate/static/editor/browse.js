// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  function ProjectStringsBrowser() {
    hotkeys("right", (e) => {
      const nextButton = $("#button-next");
      const nextLocation = nextButton.attr("href");
      if (nextButton.length > 0 && !nextButton.hasClass("disabled")) {
        if (nextLocation !== undefined) {
          e.preventDefault();
          window.location.href = nextLocation;
        }
      }
    });
    hotkeys("left", (e) => {
      const prevButton = $("#button-prev");
      const prevLocation = prevButton.attr("href");
      if (prevButton.length > 0 && !prevButton.hasClass("disabled")) {
        if (prevLocation !== undefined) {
          e.preventDefault();
          window.location.href = prevLocation;
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    new ProjectStringsBrowser();
  });
})();
