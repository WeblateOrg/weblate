// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

import hotkeys from "hotkeys-js";

// Allow shortcuts to fire inside input, textarea, and select elements
// (equivalent to mousetrap-global-bind's bindGlobal behavior).
hotkeys.filter = () => true;

window.hotkeys = hotkeys;
