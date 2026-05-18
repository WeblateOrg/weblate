// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

import * as Altcha from "altcha/i18n";

import argon2idWorkerUrl from "altcha/workers/argon2id?url";

globalThis.$altcha.algorithms.set(
  "ARGON2ID",
  () => new Worker(argon2idWorkerUrl),
);

window.Altcha = Altcha;
