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
// biome-ignore lint/correctness/noUndeclaredDependencies: is defined
import datarangepicker from "daterangepicker";
// biome-ignore lint/correctness/noUndeclaredDependencies: is defined
import jQuery from "jquery";
// biome-ignore lint/correctness/noUndeclaredDependencies: is defined
import moment from "moment";
// biome-ignore lint/correctness/noUndeclaredDependencies: is defined
import slugify from "slugify";

// Definitions in global scope
window.$ = jQuery;
window.jQuery = jQuery;
window.moment = moment;
window.daterangepicker = datarangepicker;
window.slugify = slugify;
