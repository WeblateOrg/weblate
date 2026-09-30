// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("bulk-edit-form");

  if (form === null) {
    return;
  }

  const submit = document.getElementById("bulk-edit-submit");
  const counter = document.getElementById("bulk-edit-selection-count");
  const toggle = document.getElementById("bulk-edit-toggle-selection");
  const selectedUnits = document.getElementById("bulk-edit-selected-units");

  function allCheckboxes() {
    return document.querySelectorAll(".table-embed-units .bulk-edit-select");
  }

  function selectedCheckboxes() {
    return document.querySelectorAll(
      ".table-embed-units .bulk-edit-select:checked",
    );
  }

  function updateControls() {
    const total = allCheckboxes().length;
    const checked = selectedCheckboxes();
    const selected = checked.length;

    if (selectedUnits !== null) {
      selectedUnits.value = Array.from(
        checked,
        (checkbox) => checkbox.value,
      ).join(",");
    }
    if (submit !== null) {
      submit.disabled = selected === 0;
    }
    if (counter !== null) {
      counter.textContent =
        selected === 0
          ? gettext("No strings selected")
          : interpolate(
              ngettext("%s string selected", "%s strings selected", selected),
              [selected],
            );
    }
    if (toggle instanceof HTMLInputElement) {
      toggle.disabled = total === 0;
      toggle.checked = total > 0 && selected === total;
      toggle.indeterminate = selected > 0 && selected < total;
    }
  }

  function toggleSelection(checked) {
    for (const checkbox of allCheckboxes()) {
      checkbox.checked = checked;
    }
    updateControls();
  }

  document.addEventListener("change", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    if (
      event.target instanceof HTMLInputElement &&
      event.target.id === "bulk-edit-toggle-selection"
    ) {
      toggleSelection(event.target.checked);
    } else if (event.target.matches(".table-embed-units .bulk-edit-select")) {
      updateControls();
    }
  });

  form.addEventListener("submit", (event) => {
    if (selectedCheckboxes().length === 0) {
      event.preventDefault();
      updateControls();
    }
  });

  // Browsers can restore checkbox state on back navigation
  updateControls();
});
