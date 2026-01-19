// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  Mousetrap.bindGlobal("?", (event) => {
    const target = event.target || event.srcElement;
    const tagName = target.tagName.toLowerCase();
    if (
      tagName === "input" ||
      tagName === "textarea" ||
      target.isContentEditable
    ) {
      return true;
    }
    $("#shortcuts-modal").modal("show");
    return false;
  });

  $("#shortcuts-btn").on("click", () => {
    $("#shortcuts-modal").modal("show");
  });
})();
