// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

$(document).ready(() => {
  const $profileNotificationSettings = $("#notifications");
  const $container = $profileNotificationSettings.find("#div_id_watched");
  const $selectElement = $profileNotificationSettings.find("#id_watched");

  // Make elements link-like except click behavior
  makeElementsLinkLike($container);
  // Watch the container when elements are added and removed
  const watchedContainerMutationObserver = new MutationObserver(() => {
    makeElementsLinkLike($container);
  });

  watchedContainerMutationObserver.observe($container[0], {
    childList: true,
    subtree: true,
  });

  /**
   * Iterate over all 'a' elements in parentElement, and if the element has
   * 'data-value' attribute, change its `href` to point to project page, and
   * prevent default click action.
   *
   * @param {Object} parentElement - The parent element to search for 'a'
   *                                  elements.
   */
  function makeElementsLinkLike(parentElement) {
    const slugs = JSON.parse($selectElement.attr("data-project-slugs"));
    parentElement.find("a").each((_index, element) => {
      const $element = $(element);
      const dataValue = $element.attr("data-value");
      if (dataValue) {
        // Encode the data value to prevent unsafe HTML injection
        const projectSlug = encodeURIComponent(slugs[dataValue]);
        $element.attr("href", `/projects/${projectSlug}/`);
        $element.on("click", (event) => event.preventDefault());
      }
    });
  }
});
