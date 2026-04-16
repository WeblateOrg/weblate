// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const presetSelect = document.querySelector("#addon-ui-preset");
  const presetData = document.querySelector("#addon-ui-presets");

  if (!presetSelect || !presetData) {
    return;
  }

  let presets;
  try {
    presets = JSON.parse(presetData.textContent);
  } catch (_error) {
    return;
  }

  const presetMap = new Map(presets.map((preset) => [preset.id, preset]));
  const description = document.querySelector("#addon-ui-preset-description");
  const fieldNames = [
    "match",
    "name_template",
    "base_file_template",
    "new_base_template",
    "intermediate_template",
    "language_regex",
  ];

  function updateDescription(preset) {
    if (!description) {
      return;
    }
    if (!preset?.description) {
      description.textContent = "";
      description.classList.add("d-none");
      return;
    }
    description.textContent = preset.description;
    description.classList.remove("d-none");
  }

  presetSelect.addEventListener("change", () => {
    const preset = presetMap.get(presetSelect.value);
    updateDescription(preset);
    if (!preset) {
      return;
    }

    fieldNames.forEach((name) => {
      const input = document.querySelector(`#id_${name}`);
      if (!input || !(name in preset.values)) {
        return;
      }
      input.value = preset.values[name];
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
});
