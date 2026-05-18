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

globalThis.$altcha.algorithms.set(
  "ARGON2ID",
  () => new Worker(getArgon2idWorkerUrl()),
);

window.Altcha = Altcha;
