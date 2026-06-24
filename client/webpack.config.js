// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

const path = require("node:path");

const TerserPlugin = require("terser-webpack-plugin");
const webpack = require("webpack");
const LicensePlugin = require("webpack-license-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

// Regular expression to match copyright lines
const copyrightRegex = /Copyright.*\n/;
const ossLicensesJson = "oss-licenses.json";

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
    "@tarekraafat/autocomplete.js",
    "tom-select",
    "hotkeys-js",
    "prismjs",
    "@altcha",
    "altcha",
    "source-",
    "bootstrap",
    "@orchidjs",
  ];
  return genericTransform(
    packages,
    (pkg) => !excludePrefixes.some((prefix) => pkg.name.startsWith(prefix)),
  );
}

function sentryLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("@sentry"));
}

function prismJsLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("prismjs"));
}

function bootstrapLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("bootstrap"));
}

function hotkeysLicenseTransform(packages) {
  return genericTransform(packages, (pkg) => pkg.name.startsWith("hotkeys-js"));
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
function tomSelectLicenseTransform(packages) {
  const pkg = packages.find((pkgsItem) =>
    pkgsItem.name.startsWith("tom-select"),
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
function altchaLicenseTransform() {
  const pkg = require(
    path.join(__dirname, "node_modules", "altcha", "package.json"),
  );
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
// REUSE-IgnoreEnd

class RemoveOssLicensesJsonPlugin {
  apply(compiler) {
    compiler.hooks.thisCompilation.tap(
      "RemoveOssLicensesJsonPlugin",
      (compilation) => {
        compilation.hooks.processAssets.tap(
          {
            name: "RemoveOssLicensesJsonPlugin",
            stage: webpack.Compilation.PROCESS_ASSETS_STAGE_REPORT,
          },
          () => {
            if (compilation.getAsset(ossLicensesJson)) {
              compilation.deleteAsset(ossLicensesJson);
            }
          },
        );
      },
    );
  }
}

// Webpack configuration
module.exports = {
  entry: {
    main: "./src/main.js",
    sentry: "./src/sentry.js",
    autoComplete: "./src/autoComplete.js",
    "tom-select": "./src/tom-select.js",
    hotkeys: "./src/hotkeys.js",
    prismjs: "./src/prismjs.js",
    altcha: "./src/altcha.js",
    bootstrap5: "./src/bootstrap5.js",
    bootstrap5_rtl: "./src/bootstrap5_rtl.css",
  },
  mode: "production",
  optimization: {
    minimize: true,
    minimizer: [
      new TerserPlugin({
        exclude: /argon2id\.js$/,
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
        resourceQuery: /^\?url$/,
        type: "asset/resource",
        generator: {
          filename: "[name][ext]",
        },
      },
    ],
  },
  plugins: [
    new LicensePlugin({
      outputFilename: ossLicensesJson,
      additionalFiles: {
        "main.js.license": mainLicenseTransform,
        "sentry.js.license": sentryLicenseTransform,
        "autoComplete.js.license": autoCompleteLicenseTransform,
        "tom-select.js.license": tomSelectLicenseTransform,
        "../../styles/vendor/tom-select.css.license": tomSelectLicenseTransform,
        "hotkeys.js.license": hotkeysLicenseTransform,
        "prismjs.js.license": prismJsLicenseTransform,
        "altcha.js.license": altchaLicenseTransform,
        "argon2id.js.license": altchaLicenseTransform,
        "bootstrap5.js.license": bootstrapLicenseTransform,
        "bootstrap5_rtl.js.license": bootstrapLicenseTransform,
        "../../styles/vendor/bootstrap5.css.license": bootstrapLicenseTransform,
        "../../styles/vendor/bootstrap5_rtl.css.license":
          bootstrapLicenseTransform,
      },
    }),
    new RemoveOssLicensesJsonPlugin(),
    new MiniCssExtractPlugin({
      filename: "../../styles/vendor/[name].css",
    }),
  ],
  output: {
    filename: "[name].js",
    path: path.resolve(__dirname, "../weblate/static/js/vendor"),
  },
};
