// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  function ProjectStringsBrowser() {
    Mousetrap.bindGlobal("right", (_e) => {
      const nextButton = $("#button-next");
      const nextLocation = nextButton.attr("href");
      if (nextButton.length > 0 && !nextButton.hasClass("disabled")) {
        if (nextLocation !== undefined) {
          window.location.href = nextLocation;
        }
      }
      return false;
    });
    Mousetrap.bindGlobal("left", (_e) => {
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
