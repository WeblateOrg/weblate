// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

const sentryFeedback = document.getElementById("sentry-feedback");

window.Sentry.init({ dsn: sentryFeedback.dataset.dsn });

const reportDialogOptions = {
  eventId: sentryFeedback.dataset.eventId,
};
if (sentryFeedback.dataset.userName !== undefined) {
  reportDialogOptions.user = {
    name: sentryFeedback.dataset.userName,
    email: sentryFeedback.dataset.userEmail,
  };
}
window.Sentry.showReportDialog(reportDialogOptions);
