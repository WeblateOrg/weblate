/*
 * Copyright © Michal Čihař <michal@weblate.org>
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

document.querySelectorAll("[data-security-progress]").forEach((container) => {
  const bar = container.querySelector(".progress-bar");
  const count = container.querySelector("[data-security-count]");
  const error = container.querySelector("[data-security-error]");
  if (!bar) return;

  const poll = async () => {
    try {
      const response = await fetch(container.dataset.securityProgress, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok) return;
      const result = await response.json();
      bar.style.width = `${result.progress}%`;
      bar.setAttribute("aria-valuenow", result.progress);
      bar.textContent = `${result.progress}%`;
      count.textContent = interpolate(
        gettext("Processed %(processed)s of %(total)s entries."),
        result,
        true,
      );
      if (result.state === "completed") {
        if (container.querySelector("[data-security-follow]").checked) {
          window.location = result.url;
        }
        return;
      }
      if (result.state === "failed") {
        error.textContent = result.error;
        error.hidden = false;
        return;
      }
    } catch {
      // Keep the manual refresh link available after network interruptions.
    }
    window.setTimeout(poll, 3000);
  };
  window.setTimeout(poll, 3000);
});

document.querySelectorAll("[data-security-select]").forEach((button) => {
  button.addEventListener("click", () => {
    button
      .closest("form")
      .querySelectorAll('input[name="selected"]')
      .forEach((checkbox) => {
        checkbox.checked = button.dataset.securitySelect === "all";
      });
  });
});
