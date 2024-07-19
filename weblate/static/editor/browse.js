// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  function ProjectStringsBrowser() {
    Mousetrap.bindGlobal("right", (e) => {
      const nextButton = $("#button-next");
      const nextLocation = nextButton.attr("href");
      if (nextButton.length && !nextButton.hasClass("disabled")) {
        if (nextLocation !== undefined) {
          window.location.href = nextLocation;
        }
      }
      return false;
    });
    Mousetrap.bindGlobal("left", (e) => {
      const prevButton = $("#button-prev");
      const prevLocation = prevButton.attr("href");
      if (prevButton.length && !prevButton.hasClass("disabled")) {
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
