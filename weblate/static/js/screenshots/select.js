// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("select-screenshot-modal");
  if (!modal) return;
  const content = document.getElementById("screenshot-picker-content");
  const status = document.getElementById("screenshot-picker-status");
  const add = document.getElementById("screenshot-picker-add");
  let busy = false;
  let query = "";

  function setBusy(value) {
    busy = value;
    content.setAttribute("aria-busy", String(value));
    for (const control of content.querySelectorAll("input, button")) {
      control.disabled = value;
    }
    add.disabled =
      value || !content.querySelector("input[name=screenshot]:checked");
  }

  async function load(page = 1) {
    if (busy) return;
    setBusy(true);
    status.textContent = gettext("Loading screenshots…");
    try {
      const url = new URL(modal.dataset.url, window.location.origin);
      url.searchParams.set("q", query);
      url.searchParams.set("page", page);
      const response = await fetch(url);
      if (!response.ok || response.redirected) throw new Error();
      content.innerHTML = await response.text();
      status.textContent = "";
      if (modal.classList.contains("show")) {
        content.querySelector("input[type=search]").focus();
      }
    } catch (_error) {
      status.textContent = gettext(
        "Could not load screenshots. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  modal.addEventListener("shown.bs.modal", () => load());
  content.addEventListener("change", () => {
    add.disabled =
      busy || !content.querySelector("input[name=screenshot]:checked");
  });
  content.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-page]");
    if (button) load(button.dataset.page);
  });
  content.addEventListener("submit", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (busy) return;
    if (event.target.id === "screenshot-picker-search") {
      query = new FormData(event.target).get("q");
      await load();
      return;
    }
    const data = new FormData(event.target);
    setBusy(true);
    status.textContent = gettext("Adding screenshot…");
    try {
      const response = await fetch(modal.dataset.url, {
        method: "POST",
        body: data,
      });
      const result = await response.json();
      if (!response.ok || !result.success) {
        status.textContent =
          result.error ||
          gettext("Could not add screenshot. Please try again.");
        return;
      }
      window.location.reload();
    } catch (_error) {
      status.textContent = gettext(
        "Could not add screenshot. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  });
});
