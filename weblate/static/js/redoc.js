// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

const redocContainer = document.getElementById("redoc-container");
const redocSettings = JSON.parse(redocContainer.dataset.settings);

window.Redoc.init(
  redocContainer.dataset.schemaUrl,
  redocSettings,
  redocContainer,
);
