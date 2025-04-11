// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

// biome-ignore lint/correctness/noUndeclaredDependencies: is defined
import { init, showReportDialog } from "@sentry/browser";

// Expose only what is needed
const Sentry = {
  init,
  showReportDialog,
};

window.Sentry = Sentry;
