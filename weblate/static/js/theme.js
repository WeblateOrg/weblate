// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  const root = document.documentElement;
  const theme = root.getAttribute("data-bs-theme");
  if (theme && theme !== "auto") {
    return;
  }
  const query = window.matchMedia("(prefers-color-scheme: dark)");
  const apply = () => {
    root.setAttribute("data-bs-theme", query.matches ? "dark" : "light");
  };
  apply();
  query.addEventListener("change", apply);
})();
