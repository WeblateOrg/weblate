// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  // Match the "?" character directly rather than binding via hotkeys-js
  document.addEventListener("keydown", (event) => {
    if (event.key !== "?") {
      return;
    }
    const target = event.target || event.srcElement;
    const tagName = target.tagName.toLowerCase();
    if (
      tagName === "input" ||
      tagName === "textarea" ||
      target.isContentEditable
    ) {
      return;
    }
    event.preventDefault();
    $("#shortcuts-modal").modal("show");
  });

  $("#shortcuts-btn").on("click", () => {
    $("#shortcuts-modal").modal("show");
  });
})();
