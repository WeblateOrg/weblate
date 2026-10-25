// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const applyAll = document.getElementById("bulk-apply-all");
  if (applyAll === null) {
    return;
  }
  function updateSelection() {
    for (const checkbox of document.querySelectorAll(".bulk-preview-select")) {
      checkbox.disabled = applyAll.checked;
    }
  }
  applyAll.addEventListener("change", updateSelection);
  updateSelection();
});
