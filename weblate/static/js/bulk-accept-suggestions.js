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
        showError(btn, "Security token missing. Please reload the page.");
        return;
      }
      const csrfToken = csrfTokenElement.value;

      // Disable all buttons
      const allBtns = document.querySelectorAll(".aa-accept-all-btn");
      for (const b of allBtns) {
        b.disabled = true;
      }

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
          const errorData = await response.json().catch(() => ({}));
          const errorMessage =
            errorData.error || `Server error (${response.status})`;
          showError(btn, errorMessage);
          enableAllButtons(allBtns);
          return;
        }

        const data = await response.json();

        if (data.success) {
          // Create status display
          const statusDiv = document.createElement("div");
          statusDiv.className = "aa-status";

          const acceptedDiv = document.createElement("div");
          acceptedDiv.className = "aa-accepted-count";
          acceptedDiv.textContent = `${data.accepted} accepted`;

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
          doneDiv.textContent = "Done";
          statusDiv.appendChild(doneDiv);

          btn.appendChild(statusDiv);

          // Reload page after 2 seconds
          setTimeout(() => location.reload(), 2000);
        } else {
          showError(btn, data.error || "Unknown error");
          enableAllButtons(allBtns);
        }
      } catch (err) {
        console.error("Bulk accept error:", err);
        showError(btn, err.message || "Network error");
        enableAllButtons(allBtns);
      }
    });
  });

  // Helper function to show errors
  function showError(button, message) {
    button.textContent = `Error: ${message}`;
    button.classList.add("aa-error");
  }

  // Helper function to re-enable all buttons
  function enableAllButtons(buttons) {
    for (const btn of buttons) {
      btn.disabled = false;
    }
  }
});
