// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
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
