// Copyright © 2026 Hendrik Leethaus <hendrik@leethaus.de>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const buttons = document.querySelectorAll(".aa-accept-all-btn");
  const confirmDialog = createConfirmDialog();

  const srStatus = document.createElement("div");
  srStatus.className = "visually-hidden";
  srStatus.setAttribute("role", "status");
  srStatus.setAttribute("aria-live", "polite");
  srStatus.setAttribute("aria-atomic", "true");
  document.body.appendChild(srStatus);

  buttons.forEach((btn) => {
    btn.addEventListener("click", async function (e) {
      e.preventDefault();

      const username = this.dataset.username;
      const url = this.dataset.translationUrl;
      const csrfToken = getCsrfToken();

      btn.classList.remove("aa-error");

      if (!csrfToken) {
        showError(
          btn,
          gettext("Security token missing. Please reload the page."),
        );
        return;
      }

      const allBtns = document.querySelectorAll(".aa-accept-all-btn");
      disableAllButtons(allBtns);
      srStatus.textContent = interpolate(
        gettext("Loading suggestion count for %s"),
        [username],
      );

      try {
        const preview = await postBulkAccept(url, csrfToken, {
          username: username,
          preview: "1",
        });

        const confirmed = await confirmBulkAccept(
          confirmDialog,
          username,
          preview.total,
          preview.can_approve,
        );
        if (!confirmed) {
          enableAllButtons(allBtns);
          srStatus.textContent = gettext("Bulk accept cancelled.");
          return;
        }

        srStatus.textContent = interpolate(
          gettext("Scheduling bulk accept for %s"),
          [username],
        );

        const data = await postBulkAccept(url, csrfToken, {
          username: username,
          confirmed: "1",
          return_url: `${window.location.pathname}${window.location.search}${window.location.hash}`,
          ...(confirmed === "approve" ? { approve: "1" } : {}),
        });

        if (data.success) {
          srStatus.textContent = data.message;
          setTimeout(() => location.reload(), data.completed ? 1500 : 100);
        } else {
          showError(btn, data.error || gettext("Unknown error"));
          enableAllButtons(allBtns);
        }
      } catch (err) {
        console.error("Bulk accept error:", err);
        showError(btn, err.message || gettext("Network error"));
        enableAllButtons(allBtns);
      }
    });
  });

  function getCsrfToken() {
    const csrfTokenElement = document.querySelector(
      "[name=csrfmiddlewaretoken]",
    );
    return csrfTokenElement?.value;
  }

  async function postBulkAccept(url, csrfToken, data) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams(data),
    });

    let responseData;
    try {
      responseData = await response.json();
    } catch (_parseError) {
      if (response.ok) {
        throw new Error(gettext("Invalid server response"));
      }
      responseData = {};
    }

    if (!response.ok) {
      throw new Error(
        responseData.error ||
          response.statusText ||
          interpolate(gettext("Server error (%s)"), [response.status]),
      );
    }

    if (
      responseData === null ||
      typeof responseData !== "object" ||
      Array.isArray(responseData)
    ) {
      throw new Error(gettext("Invalid server response"));
    }

    return responseData;
  }

  function confirmBulkAccept(dialog, username, total, canApprove) {
    return new Promise((resolve) => {
      let resolved = false;
      const modal = bootstrap.Modal.getOrCreateInstance(dialog.element);

      if (total === 0) {
        dialog.body.textContent = interpolate(
          gettext(
            "There are no pending suggestions from %s in this translation.",
          ),
          [username],
        );
        dialog.confirmButton.disabled = true;
        dialog.approveButton.disabled = true;
      } else {
        dialog.body.textContent = interpolate(
          ngettext(
            "This will accept %s suggestion from %s in this translation.",
            "This will accept %s suggestions from %s in this translation.",
            total,
          ),
          [total, username],
        );
        dialog.confirmButton.disabled = false;
        dialog.approveButton.disabled = false;
      }
      dialog.approveButton.hidden = !canApprove;

      const finish = (value) => {
        if (resolved) {
          return;
        }
        resolved = true;
        dialog.confirmButton.removeEventListener("click", confirm);
        dialog.approveButton.removeEventListener("click", approve);
        dialog.element.removeEventListener("hidden.bs.modal", cancel);
        resolve(value);
      };

      const confirm = () => {
        finish("accept");
        modal.hide();
      };

      const approve = () => {
        finish("approve");
        modal.hide();
      };

      const cancel = () => {
        finish(false);
      };

      dialog.confirmButton.addEventListener("click", confirm);
      dialog.approveButton.addEventListener("click", approve);
      dialog.element.addEventListener("hidden.bs.modal", cancel);
      modal.show();
    });
  }

  function createConfirmDialog() {
    const element = document.createElement("div");
    element.className = "modal fade";
    element.tabIndex = -1;
    element.setAttribute("role", "dialog");
    element.setAttribute("aria-labelledby", "bulk-accept-suggestions-title");

    const dialog = document.createElement("div");
    dialog.className = "modal-dialog modal-lg";
    dialog.setAttribute("role", "document");

    const content = document.createElement("div");
    content.className = "modal-content";

    const header = document.createElement("div");
    header.className = "modal-header";

    const title = document.createElement("h4");
    title.id = "bulk-accept-suggestions-title";
    title.className = "modal-title";
    title.textContent = gettext("Accept all suggestions?");

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "btn-close";
    closeButton.setAttribute("data-bs-dismiss", "modal");
    closeButton.setAttribute("aria-label", gettext("Close"));

    const body = document.createElement("div");
    body.className = "modal-body";

    const footer = document.createElement("div");
    footer.className = "modal-footer";

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "btn btn-link";
    cancelButton.setAttribute("data-bs-dismiss", "modal");
    cancelButton.textContent = gettext("Cancel");

    const confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.className = "btn btn-primary";
    confirmButton.textContent = gettext("Accept suggestions");

    const approveButton = document.createElement("button");
    approveButton.type = "button";
    approveButton.className = "btn btn-primary";
    approveButton.textContent = gettext("Accept and approve suggestions");

    header.append(title, closeButton);
    footer.append(cancelButton, approveButton, confirmButton);
    content.append(header, body, footer);
    dialog.append(content);
    element.append(dialog);
    document.body.appendChild(element);

    return {
      element: element,
      body: body,
      confirmButton: confirmButton,
      approveButton: approveButton,
    };
  }

  function showError(button, message) {
    const error = interpolate(gettext("Error: %s"), [message]);
    button.classList.add("aa-error");
    button.setAttribute("aria-label", error);
    button.setAttribute("title", error);
    button.setAttribute("aria-busy", "false");
    srStatus.textContent = error;
  }

  function disableAllButtons(buttons) {
    for (const btn of buttons) {
      btn.disabled = true;
      btn.setAttribute("aria-busy", "true");
    }
  }

  function enableAllButtons(buttons) {
    for (const btn of buttons) {
      btn.disabled = false;
      btn.setAttribute("aria-busy", "false");
    }
  }
});
