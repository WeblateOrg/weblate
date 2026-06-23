// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

document.addEventListener("DOMContentLoaded", () => {
  const eventFilters = document.querySelectorAll("[data-addon-event-filter]");
  const events = document.querySelector("[data-addon-events]");

  if (!eventFilters.length || !(events instanceof HTMLSelectElement)) {
    return;
  }

  const eventsContainer = events.closest("#div_id_events");
  const customEventsValue = eventFilters[0].dataset.addonCustomEventsValue;

  function updateEventsState() {
    const checkedFilter = document.querySelector(
      "[data-addon-event-filter]:checked",
    );
    const customEventsSelected = checkedFilter?.value === customEventsValue;
    events.disabled = !customEventsSelected;
    if (eventsContainer) {
      eventsContainer.hidden = !customEventsSelected;
    }

    if (events.tomselect) {
      if (customEventsSelected) {
        events.tomselect.enable();
      } else {
        events.tomselect.disable();
      }
    }
  }

  eventFilters.forEach((eventFilter) => {
    eventFilter.addEventListener("change", updateEventsState);
  });
  updateEventsState();
});
