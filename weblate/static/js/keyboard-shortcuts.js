// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  function showShortcutsModal() {
    const modal = document.getElementById("shortcuts-modal");
    if (modal !== null) {
      bootstrap.Modal.getOrCreateInstance(modal).show();
    }
  }

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
    showShortcutsModal();
  });

  document
    .getElementById("shortcuts-btn")
    ?.addEventListener("click", showShortcutsModal);
})();
