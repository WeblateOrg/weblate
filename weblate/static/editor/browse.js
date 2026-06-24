// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  function ProjectStringsBrowser() {
    hotkeys("right", () => {
      const nextButton = document.getElementById("button-next");
      const nextLocation = nextButton?.getAttribute("href");
      if (nextButton && !nextButton.classList.contains("disabled")) {
        if (nextLocation !== null && nextLocation !== undefined) {
          window.location.href = nextLocation;
        }
      }
      return false;
    });
    hotkeys("left", () => {
      const prevButton = document.getElementById("button-prev");
      const prevLocation = prevButton?.getAttribute("href");
      if (prevButton && !prevButton.classList.contains("disabled")) {
        if (prevLocation !== null && prevLocation !== undefined) {
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
