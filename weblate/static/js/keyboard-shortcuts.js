// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  hotkeys("shift+/", (event) => {
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
