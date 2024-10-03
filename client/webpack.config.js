// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

const path = require("node:path");

const TerserPlugin = require("terser-webpack-plugin");
const LicensePlugin = require("webpack-license-plugin");
const copyrightRegex = /Copyright.*\n/;

// REUSE-IgnoreStart
function extractCopyright(pkg) {
  if (pkg.licenseText !== null) {
    const copyrights = pkg.licenseText.match(copyrightRegex);
    if (copyrights !== null) {
      return copyrights.join("");
    }
  }
  return `Copyright ${pkg.author}\n`;
}

function genericTransform(packages, filter) {
  const mainPackages = packages.filter(filter);
  const licenses = [...new Set(mainPackages.map((pkg) => pkg.license))]
    .sort()
    .join(" AND ");

  const copyrights = [...new Set(mainPackages.map(extractCopyright))]
    .sort()
    .join("");
  return `${copyrights}
SPDX-License-Identifier: ${licenses}
`;
}
// REUSE-IgnoreEnd

function mainLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => !pkg.name.startsWith("@sentry"));
}
function sentryLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("@sentry"));
}

module.exports = {
  entry: {
    main: "./src/main.js",
    sentry: "./src/sentry.js",
  },
  mode: "production",
  optimization: {
    minimize: true,
    minimizer: [
      new TerserPlugin({
        extractComments: false,
        terserOptions: {
          format: {
            comments: false,
          },
        },
      }),
    ],
  },
  plugins: [
    new LicensePlugin({
      additionalFiles: {
        "main.js.license": mainLicenseTransform,
        "sentry.js.license": sentryLicenseTransform,
      },
    }),
  ],
  output: {
    filename: "[name].js",
    path: path.resolve(__dirname, "../weblate/static/js/vendor"),
  },
};
