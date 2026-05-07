// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const presetButtons = document.querySelectorAll(
    "[data-addon-discovery-preset]",
  );
  const presetData = document.querySelector("#addon-ui-presets");

  if (!presetButtons.length || !presetData) {
    return;
  }

  let presets;
  try {
    presets = JSON.parse(presetData.textContent);
  } catch (_error) {
    return;
  }

  const presetMap = new Map(presets.map((preset) => [preset.id, preset]));
  const fieldNames = [
    "match",
    "file_format",
    "name_template",
    "base_file_template",
    "new_base_template",
    "intermediate_template",
    "language_regex",
  ];
  function flashChangedField(input) {
    input.classList.remove("flags-updated");
    void input.offsetWidth;
    input.classList.add("flags-updated");
    input.addEventListener(
      "animationend",
      (event) => {
        if (event.target !== input || event.animationName !== "flags-updated") {
          return;
        }
        input.classList.remove("flags-updated");
      },
      { once: true },
    );
  }

  function applyPreset(preset) {
    fieldNames.forEach((name) => {
      const input = document.querySelector(`#id_${name}`);
      if (!input || !(name in preset.values)) {
        return;
      }
      if (input.value === preset.values[name]) {
        return;
      }
      input.value = preset.values[name];
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      flashChangedField(input);
    });
  }

  presetButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const preset = presetMap.get(button.dataset.addonDiscoveryPreset);
      if (!preset) {
        return;
      }
      applyPreset(preset);
    });
  });
});
