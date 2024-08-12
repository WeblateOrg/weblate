// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

const path = require("node:path");

module.exports = {
  entry: {
    main: "./src/main.js",
    sentry: "./src/sentry.js",
  },
  mode: "production",
  output: {
    filename: "[name].js",
    path: path.resolve(__dirname, "../weblate/static/js/vendor"),
  },
};
