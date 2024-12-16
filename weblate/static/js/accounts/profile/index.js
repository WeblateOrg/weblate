// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

$(document).ready(() => {
  const $profileNotificationSettings = $("#notifications");

  // Open project page on right click
  $profileNotificationSettings.on("contextmenu", (e) => {
    if ($(e.target).closest(".multi-wrapper a").length > 0) {
      const slug = $(e.target).closest(".multi-wrapper a").data("value");
      if (slug) {
        window.location.href = `/projects/${slug}`;
      }
      // Prevent context menu from displaying
      e.preventDefault();
      return true;
    }
  });
});
