// Copyright © Michal Čihař <michal@weblate.org>
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  const form = document.getElementById("pow-form");
  const error = document.getElementById("pow-error");
  const status = document.getElementById("pow-status");
  let worker;
  let timer;
  const fail = () => {
    worker?.terminate();
    clearTimeout(timer);
    // Keep the existing live region present so assistive technology announces
    // the localized failure and recovery instructions.
    status.textContent = error.textContent;
  };
  document
    .getElementById("pow-retry")
    .addEventListener("click", () => location.reload());
  try {
    worker = new Worker(form.dataset.worker);
    worker.onerror = fail;
    worker.onmessage = async ({ data }) => {
      if (data.progress !== undefined) {
        status.textContent = `${data.progress.toLocaleString()}…`;
        return;
      }
      worker.terminate();
      try {
        const response = await fetch(form.dataset.url, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": form.querySelector("input").value,
          },
          body: JSON.stringify(data),
        });
        if (!response.ok) throw new Error("verification failed");
        const result = await response.json();
        // Probe clearance before navigation to avoid a cookie-disabled loop.
        const probe = await fetch(result.redirect, {
          method: "HEAD",
          credentials: "same-origin",
        });
        if (probe.status === 403) throw new Error("clearance rejected");
        location.replace(result.redirect);
      } catch {
        fail();
      }
    };
    timer = setTimeout(fail, Number(form.dataset.timeout));
    worker.postMessage(
      JSON.parse(document.getElementById("pow-challenge").textContent),
    );
  } catch {
    fail();
  }
})();
