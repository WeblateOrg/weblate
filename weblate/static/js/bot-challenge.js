// Copyright © Michal Čihař <michal@weblate.org>
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  const form = document.getElementById("pow-form");
  const error = document.getElementById("pow-error");
  const status = document.getElementById("pow-status");
  let worker;
  let timer;
  let stopped = false;
  const recoveryKey = "weblate-pow-recovery";
  const resetRecovery = () => {
    try {
      sessionStorage.removeItem(recoveryKey);
    } catch {}
  };
  const fail = (kind = "error") => {
    stopped = true;
    worker?.terminate();
    clearTimeout(timer);
    // Keep the existing live region present so assistive technology announces
    // the localized failure and recovery instructions.
    status.textContent =
      document.getElementById(`pow-${kind}`)?.textContent || error.textContent;
  };
  const expire = () => {
    fail("expired");
    try {
      if (!sessionStorage.getItem(recoveryKey)) {
        sessionStorage.setItem(recoveryKey, "1");
        location.reload();
      }
    } catch {}
  };
  document.getElementById("pow-retry").addEventListener("click", () => {
    resetRecovery();
    location.reload();
  });
  try {
    worker = new Worker(form.dataset.worker);
    worker.onerror = () => fail();
    worker.onmessage = async ({ data }) => {
      if (stopped) return;
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
        if (stopped) return;
        if (response.status === 503) {
          fail("unavailable");
          return;
        }
        const result = await response.json();
        if (stopped) return;
        if (!response.ok) {
          if (response.status === 400 && result.error === "expired_challenge") {
            expire();
          } else {
            const reasons = {
              invalid_solution: "invalid",
              replayed_challenge: "replayed",
              csrf_failed: "csrf",
              verification_unavailable: "unavailable",
            };
            fail(
              Object.hasOwn(reasons, result.error)
                ? reasons[result.error]
                : "error",
            );
          }
          return;
        }
        // Check the cookie without invoking the destination view.
        const probe = await fetch(form.dataset.check, {
          method: "HEAD",
          credentials: "same-origin",
        });
        if (stopped) return;
        if (probe.status !== 204) {
          fail("clearance");
          return;
        }
        clearTimeout(timer);
        stopped = true;
        resetRecovery();
        location.replace(result.redirect);
      } catch {
        if (!stopped) fail();
      }
    };
    timer = setTimeout(expire, Number(form.dataset.timeout));
    worker.postMessage(
      JSON.parse(document.getElementById("pow-challenge").textContent),
    );
  } catch {
    fail();
  }
})();
