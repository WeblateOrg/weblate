// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  Mousetrap.bindGlobal("?", (_event) => {
    $("#shortcuts-modal").modal("show");
    return false;
  });
})();
