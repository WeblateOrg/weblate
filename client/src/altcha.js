// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

import * as Altcha from "altcha/i18n";

import "altcha/workers/argon2id?url";

function getArgon2idWorkerUrl() {
  const meta = document.querySelector('meta[name="argon2id-worker-url"]');
  if (!meta) throw new Error("argon2id-worker-url meta tag missing");
  return meta.content;
}

function createArgon2idWorker() {
  // Resolve to an absolute URL so it works from inside the blob worker below.
  const url = new URL(getArgon2idWorkerUrl(), document.baseURI).href;
  // Workers must be same-origin; pull the script in via importScripts, which is
  // allowed to load cross-origin scripts.
  const blob = new Blob([`importScripts(${JSON.stringify(url)});`], {
    type: "text/javascript",
  });
  const blobUrl = URL.createObjectURL(blob);
  const worker = new Worker(blobUrl);
  URL.revokeObjectURL(blobUrl);
  return worker;
}

globalThis.$altcha.algorithms.set("ARGON2ID", createArgon2idWorker);

window.Altcha = Altcha;
