// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const profileForm = document.getElementById("profile-active-tab")?.form;
  if (profileForm) {
    // Validate the active pane on submission so hidden required fields cannot
    // block saving another tab before its submit handler runs.
    profileForm.noValidate = true;
    const requestedTab = profileForm.dataset.activeTab || window.location.hash;
    if (requestedTab) {
      const tab = [
        ...document.querySelectorAll('.nav [data-bs-toggle="tab"]'),
      ].find((element) => element.dataset.bsTarget === requestedTab);
      if (tab) {
        bootstrap.Tab.getOrCreateInstance(tab).show();
      }
    }
    profileForm.addEventListener(
      "submit",
      (event) => {
        const activePane = profileForm.querySelector(
          ".tab-content > .tab-pane.active",
        );
        document.getElementById("profile-active-tab").value = activePane
          ? `#${activePane.id}`
          : "";
        if (activePane && !event.submitter?.formNoValidate) {
          for (const control of activePane.querySelectorAll(
            "input, select, textarea",
          )) {
            if (control.form === profileForm && !control.reportValidity()) {
              event.preventDefault();
              // Keep shared submit handlers from marking an invalid attempt as
              // submitted and blocking the next attempt after it is corrected.
              event.stopImmediatePropagation();
              break;
            }
          }
        }
      },
      { capture: true },
    );
  }

  const profileNotificationSettings = document.getElementById("notifications");
  const container =
    profileNotificationSettings?.querySelector("#div_id_watched");
  const selectElement =
    profileNotificationSettings?.querySelector("#id_watched");

  if (
    container === null ||
    container === undefined ||
    selectElement === null ||
    selectElement === undefined
  ) {
    return;
  }

  // Make elements link-like except click behavior
  makeElementsLinkLike(container);
  // Watch the container when elements are added and removed
  const watchedContainerMutationObserver = new MutationObserver(() => {
    makeElementsLinkLike(container);
  });

  watchedContainerMutationObserver.observe(container, {
    childList: true,
    subtree: true,
  });

  /**
   * Iterate over all 'a' elements in parentElement, and if the element has
   * 'data-value' attribute, change its `href` to point to project page, and
   * prevent default click action.
   *
   * @param {Element} parentElement - The parent element to search for 'a'
   *                                  elements.
   */
  function makeElementsLinkLike(parentElement) {
    const slugs = JSON.parse(selectElement.getAttribute("data-project-slugs"));
    if (slugs === undefined || slugs === null) {
      return;
    }
    for (const element of parentElement.querySelectorAll("a")) {
      const dataValue = element.getAttribute("data-value");
      if (dataValue) {
        // Encode the data value to prevent unsafe HTML injection
        const projectSlug = encodeURIComponent(slugs[dataValue]);
        element.setAttribute("href", `/projects/${projectSlug}/`);
        element.addEventListener("click", (event) => event.preventDefault());
      }
    }
  }
});
