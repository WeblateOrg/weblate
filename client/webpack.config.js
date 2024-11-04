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
  const excludePrefixes = [
    "@sentry",
    "tributejs",
    "@tarekraafat/autocomplete.js",
    "autosize",
  ];
  return genericTransform(
    packages,
    (pkg) => !excludePrefixes.some((prefix) => pkg.name.startsWith(prefix)),
  );
}
function sentryLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("@sentry"));
}
function tributeLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("tributejs"));
}
function autosizeLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("autosize"));
}
// REUSE-IgnoreStart
function autoCompleteLicenseTransform(packages) {
  const pkg = packages.find((pkgsItem) =>
    pkgsItem.name.startsWith("@tarekraafat/autocomplete.js"),
  );
  if (pkg) {
    const author =
      typeof pkg.author === "string"
        ? pkg.author
        : pkg.author?.email
          ? `${pkg.author.name} <${pkg.author.email}>`
          : pkg.author?.name
            ? pkg.author.name
            : "";
    return `SPDX-FileCopyrightText: ${author}\n\nSPDX-License-Identifier: ${pkg.license}`;
  }
  return "";
}
// REUSE-IgnoreEnd

module.exports = {
  entry: {
    main: "./src/main.js",
    sentry: "./src/sentry.js",
    tribute: "./src/tribute.js",
    autoComplete: "./src/autoComplete.js",
    autosize: "./src/autosize.js",
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
        "tribute.js.license": tributeLicenseTransform,
        "autoComplete.js.license": autoCompleteLicenseTransform,
        "autosize.js.license": autosizeLicenseTransform,
      },
    }),
  ],
  output: {
    filename: "[name].js",
    path: path.resolve(__dirname, "../weblate/static/js/vendor"),
  },
};
