// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

const path = require("node:path");

const TerserPlugin = require("terser-webpack-plugin");
const LicensePlugin = require("webpack-license-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

// Regular expression to match copyright lines
const copyrightRegex = /Copyright.*\n/;

// REUSE-IgnoreStart
// Function to extract copyright information from a package
function extractCopyright(pkg) {
  if (pkg.licenseText !== null) {
    const copyrights = pkg.licenseText.match(copyrightRegex);
    if (copyrights !== null) {
      return copyrights.join("");
    }
  }
  return `Copyright ${pkg.author}\n`;
}

// Generic function to transform package information
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
// License transform function for global packages used in main.js
function mainLicenseTransform(packages) {
  const excludePrefixes = [
    "@sentry",
    "tributejs",
    "@tarekraafat/autocomplete.js",
    "autosize",
    "multi.js",
    "mousetrap",
    "prismjs",
    "@altcha",
    "altcha",
    "source-",
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

function multiJsLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("multi.js"));
}

function prismJsLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("prismjs"));
}

function altchaLicenseTransform(packages) {
  return genericTransform(
    packages,
    (pkg) => pkg.name.startsWith("altcha") || pkg.name.startsWith("@altcha"),
  );
}

function fontsLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("source-"));
}

// REUSE-IgnoreStart
function mousetrapLicenseTransform(packages) {
  const pkg = packages.find((pkg) => pkg.name.startsWith("mousetrap"));
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

// Webpack configuration
module.exports = {
  entry: {
    main: "./src/main.js",
    sentry: "./src/sentry.js",
    tribute: "./src/tribute.js",
    autoComplete: "./src/autoComplete.js",
    autosize: "./src/autosize.js",
    multi: "./src/multi.js",
    mousetrap: "./src/mousetrap.js",
    prismjs: "./src/prismjs.js",
    altcha: "./src/altcha.js",
    "fonts/fonts": "./src/fonts.js",
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
  module: {
    rules: [
      {
        test: /\.css$/,
        use: [MiniCssExtractPlugin.loader, "css-loader"],
      },
      {
        test: /\.(woff|woff2|eot|otf)$/i,
        type: "asset/resource",
        generator: {
          filename: "fonts/font-source/[name][ext]",
        },
      },
      {
        test: /\.(ttf)$/i,
        type: "asset/resource",
        generator: {
          filename: "fonts/font-source/TTF/[name][ext]",
        },
      },
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
        "multi.js.license": multiJsLicenseTransform,
        "multi.css.license": multiJsLicenseTransform,
        "mousetrap.js.license": mousetrapLicenseTransform,
        "prismjs.js.license": prismJsLicenseTransform,
        "altcha.js.license": altchaLicenseTransform,
        "fonts/fonts.js.license": fontsLicenseTransform,
        "fonts/fonts.css.license": fontsLicenseTransform,
      },
    }),
    new MiniCssExtractPlugin({
      filename: "[name].css",
    }),
  ],
  output: {
    filename: "[name].js",
    path: path.resolve(__dirname, "../weblate/static/js/vendor"),
  },
};
