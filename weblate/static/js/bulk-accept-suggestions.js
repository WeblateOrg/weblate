// Copyright © 2026 Hendrik Leethaus <hendrik@leethaus.de>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const buttons = document.querySelectorAll(".aa-accept-all-btn");

  buttons.forEach((btn) => {
    btn.addEventListener("click", async function (e) {
      e.preventDefault();

      const username = this.dataset.username;
      const url = this.dataset.translationUrl;

      // Get CSRF token and validate it exists
      const csrfTokenElement = document.querySelector(
        "[name=csrfmiddlewaretoken]",
      );
      if (!csrfTokenElement) {
        console.error("CSRF token not found");
        showError(
          btn,
          gettext("Security token missing. Please reload the page."),
          null,
        );
        return;
      }
      const csrfToken = csrfTokenElement.value;

      // Disable all buttons
      const allBtns = document.querySelectorAll(".aa-accept-all-btn");
      for (const b of allBtns) {
        b.disabled = true;
        b.setAttribute("aria-busy", "true");
      }
      // Create screen reader status element
      const srStatus = document.createElement("div");
      srStatus.className = "sr-only";
      srStatus.setAttribute("role", "status");
      srStatus.setAttribute("aria-live", "polite");
      srStatus.setAttribute("aria-atomic", "true");
      document.body.appendChild(srStatus);
      srStatus.textContent = interpolate(
        gettext("Processing bulk accept for %s"),
        [username],
      );

      // Clear button text for status display
      btn.textContent = "";

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "X-CSRFToken": csrfToken,
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: new URLSearchParams({
            username: username,
          }),
        });

        // Check if HTTP request was successful
        if (!response.ok) {
          let errorData;
          try {
            errorData = await response.json();
          } catch {
            errorData = {};
          }
          const errorMessage =
            errorData.error ||
            response.statusText ||
            interpolate(gettext("Server error (%s)"), [response.status]);
          showError(btn, errorMessage, srStatus);

          enableAllButtons(allBtns);
          return;
        }

        let data;
        try {
          data = await response.json();
        } catch (_parseError) {
          showError(btn, gettext("Invalid server response"), srStatus);
          enableAllButtons(allBtns);
          return;
        }

        if (data.success) {
          // Create status display
          const statusDiv = document.createElement("div");
          statusDiv.className = "aa-status";

          const acceptedDiv = document.createElement("div");
          acceptedDiv.className = "aa-accepted-count";
          acceptedDiv.textContent = interpolate(
            ngettext("%s accepted", "%s accepted", data.accepted),
            [data.accepted],
          );

          const progressDiv = document.createElement("div");
          progressDiv.className = "aa-progress";
          const percentage =
            data.total > 0
              ? Math.round((data.accepted / data.total) * 100)
              : 100;
          progressDiv.textContent = `${percentage}%`;

          statusDiv.appendChild(acceptedDiv);
          statusDiv.appendChild(progressDiv);

          // Add "Done" message
          const doneDiv = document.createElement("div");
          doneDiv.className = "aa-done";
          doneDiv.textContent = gettext("Done");
          statusDiv.appendChild(doneDiv);

          btn.appendChild(statusDiv);
          // Announce to screen readers
          srStatus.textContent = interpolate(
            ngettext(
              "Successfully accepted %s suggestion. Page will reload in 2 seconds.",
              "Successfully accepted %s suggestions. Page will reload in 2 seconds.",
              data.accepted,
            ),
            [data.accepted],
          );

          // Reload page after 2 seconds
          setTimeout(() => location.reload(), 2000);
        } else {
          showError(btn, data.error || gettext("Unknown error"), srStatus);
          enableAllButtons(allBtns);
        }
      } catch (err) {
        console.error("Bulk accept error:", err);
        showError(btn, err.message || gettext("Network error"), srStatus);
        enableAllButtons(allBtns);
      }
    });
  });

  // Helper function to show errors
  function showError(button, message, statusElement) {
    button.textContent = interpolate(gettext("Error: %s"), [message]);
    button.classList.add("aa-error");
    button.setAttribute("aria-busy", "false");

    // Announce error to screen readers
    if (statusElement) {
      statusElement.textContent = interpolate(gettext("Error: %s"), [message]);
    }
  }

  // Helper function to re-enable all buttons
  function enableAllButtons(buttons) {
    for (const btn of buttons) {
      btn.disabled = false;
      btn.setAttribute("aria-busy", "false");
    }
  }
});
