// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  function ProjectStringsBrowser() {
    hotkeys("right", () => {
      const nextButton = $("#button-next");
      const nextLocation = nextButton.attr("href");
      if (nextButton.length > 0 && !nextButton.hasClass("disabled")) {
        if (nextLocation !== undefined) {
          window.location.href = nextLocation;
        }
      }
      return false;
    });
    hotkeys("left", () => {
      const prevButton = $("#button-prev");
      const prevLocation = prevButton.attr("href");
      if (prevButton.length > 0 && !prevButton.hasClass("disabled")) {
        if (prevLocation !== undefined) {
          window.location.href = prevLocation;
        }
      }
      return false;
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    new ProjectStringsBrowser();
  });
})();
