// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

/**
 * Imports to project wide dependencies goes in here
 * This file build in weblate/static/js/vendor/main.js
 * is loaded before any other file in the project so
 * you can use it to import dependencies that are used
 * in multiple places in the project
 */

// Imports
import jQuery from "jquery";

// Definitions in global scope
window.$ = jQuery;
window.jQuery = jQuery;
