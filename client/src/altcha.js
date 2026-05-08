// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

import * as Altcha from "altcha/i18n";

// Need to manually import and bundle Altcha Argon2ID worker
import argon2idWorkerSource from "altcha/workers/argon2id?source";

const argon2idWorkerUrl = URL.createObjectURL(
  new Blob([argon2idWorkerSource], { type: "text/javascript" }),
);

globalThis.$altcha.algorithms.set(
  "ARGON2ID",
  () => new Worker(argon2idWorkerUrl),
);

window.Altcha = Altcha;
