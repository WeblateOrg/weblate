// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  const EditorBase = WLT.Editor.Base;

  function ZenEditor() {
    EditorBase.call(this);

    window.addEventListener("scroll", () => {
      const loadingNext = document.getElementById("loading-next");
      const loader = document.getElementById("zen-load");
      if (loadingNext === null || loader === null) {
        return;
      }

      if (
        window.scrollY >=
        document.documentElement.scrollHeight - 2 * window.innerHeight
      ) {
        if (
          document.getElementById("last-section") !== null ||
          getComputedStyle(loadingNext).display !== "none"
        ) {
          return;
        }
        loadingNext.style.display = "";

        const newOffset = 20 + Number.parseInt(loader.dataset.offset, 10);
        loader.dataset.offset = String(newOffset);

        fetch(`${loader.getAttribute("href")}&offset=${newOffset}`, {
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        })
          .then((response) => {
            if (response.status === 409) {
              loader.remove();
              loadingNext.style.display = "none";
              addAlert(
                gettext(
                  "Your previous search results are no longer available. Refresh results to continue.",
                ),
                "info",
              );
              return null;
            }
            if (!response.ok) {
              throw new Error(`HTTP ${response.status}`);
            }
            return response.text();
          })
          .then((data) => {
            if (data === null) {
              return;
            }
            loadingNext.style.display = "none";

            const tfoot = document.querySelector(".zen tfoot");
            tfoot?.insertAdjacentHTML("beforebegin", data);

            this.init();
            initHighlight(document);
            syncSuggestionIndicators();
          })
          .catch((err) => {
            loadingNext.style.display = "none";
            addAlert(err.message);
          });
      }
    });

    /*
     * Ensure current editor is reasonably located in the window
     * - show whole element if moving back
     * - scroll down if in bottom half of the window
     */
    delegate(document, "focusin", ".zen .translation-editor", function () {
      const container = this.closest(".translator")?.closest("tr");
      const current = window.scrollY;
      const tbody = this.closest("tbody");
      if (!tbody) {
        return;
      }
      const rowOffset = tbody.getBoundingClientRect().top + window.scrollY;
      if (rowOffset < current || rowOffset - current > window.innerHeight / 2) {
        // Scroll to view source string
        window.scrollTo({ top: rowOffset, behavior: "smooth" });
        // Stick the editor to the bottom of the screen when out of view
        for (const el of document.querySelectorAll(".sticky-bottom")) {
          el.classList.remove("sticky-bottom"); // Hide previous
        }
        if (container) {
          container.classList.add("sticky-bottom");
          for (const hide of container.querySelectorAll(".hide-sticky")) {
            hide.addEventListener("click", () => {
              container.classList.remove("sticky-bottom");
            });
          }
        }
      }
    });

    hotkeys("ctrl+end,command+end", () => {
      const units = document.querySelectorAll(".zen-unit");
      units[units.length - 1]?.querySelector(".translation-editor")?.focus();
      return false;
    });
    hotkeys("ctrl+home,command+home", () => {
      document
        .querySelector(".zen-unit")
        ?.querySelector(".translation-editor")
        ?.focus();
      return false;
    });
    hotkeys("ctrl+pagedown,command+pagedown", () => {
      const focus = document.activeElement;
      if (!focus || focus === document.body) {
        document
          .querySelector(".zen-unit")
          ?.querySelector(".translation-editor")
          ?.focus();
      } else {
        focus
          .closest(".zen-unit")
          ?.nextElementSibling?.querySelector(".translation-editor")
          ?.focus();
      }
      return false;
    });
    hotkeys("ctrl+pageup,command+pageup", () => {
      const focus = document.activeElement;
      if (!focus || focus === document.body) {
        const units = document.querySelectorAll(".zen-unit");
        units[units.length - 1]?.querySelector(".translation-editor")?.focus();
      } else {
        focus
          .closest(".zen-unit")
          ?.previousElementSibling?.querySelector(".translation-editor")
          ?.focus();
      }
      return false;
    });

    window.addEventListener("beforeunload", (e) => {
      if (document.querySelector(".translation-modified") !== null) {
        e.preventDefault();
        e.returnValue = gettext(
          "There are some unsaved changes, are you sure you want to leave?",
        );
      }
    });
  }
  ZenEditor.prototype = Object.create(EditorBase.prototype);
  ZenEditor.prototype.constructor = ZenEditor;

  ZenEditor.prototype.init = function () {
    EditorBase.prototype.init.call(this);

    /* Minimal height for side-by-side editor */
    const getContentHeight = (el) =>
      Number.parseFloat(getComputedStyle(el).height) || 0;
    for (const translator of document.querySelectorAll(
      ".zen-horizontal .translator",
    )) {
      const tdHeight = getContentHeight(translator);
      const form = translator.querySelector("form");
      const contentHeight = form ? getContentHeight(form) : 0;
      const editors = translator.querySelectorAll(".translation-editor");
      let editorHeight = 0;
      for (const editor of editors) {
        editorHeight += getContentHeight(editor);
      }
      /* There is 10px padding */
      const minHeight =
        (tdHeight - (contentHeight - editorHeight - 10)) / editors.length;
      for (const editor of editors) {
        editor.style.minHeight = `${minHeight}px`;
      }
    }
  };

  /* Handlers */

  const getStatusCell = (root, checksum) =>
    root?.querySelector(`[id="status-${checksum}"]`) ?? null;

  delegate(document, "focusin", ".translation-editor", function () {
    const row = this.closest("tr");
    if (!row) {
      return;
    }
    const checksum = row.querySelector("[name=checksum]")?.value;
    const statusdiv = getStatusCell(row, checksum);
    const focusTimeout = row._focusTimer;
    // Focus returned quickly; cancel pending save
    if (focusTimeout) {
      statusdiv?.classList.remove("unit-state-save-timeout");
      clearTimeout(focusTimeout);
      row._focusTimer = undefined;
    }
  });

  delegate(document, "focusout", ".translation-editor", function () {
    const row = this.closest("tr");
    if (!row) {
      return;
    }
    const checksum = row.querySelector("[name=checksum]")?.value;
    const statusdiv = getStatusCell(row, checksum);
    // Editor lost focus and has changes
    if (this.classList.contains("has-changes")) {
      statusdiv?.classList.add("unit-state-save-timeout");
      const focusTimeout = setTimeout(() => {
        row._focusTimer = undefined;
        handleTranslationChange.call(this);
      }, 1000); // Grace period before saving
      row._focusTimer = focusTimeout;
    }
  });

  // Allow immediate saves for checkbox/radio changes
  delegate(document, "change", ".fuzzy_checkbox", function () {
    handleTranslationChange.call(this);
  });
  delegate(document, "change", ".review_radio", function () {
    handleTranslationChange.call(this);
  });

  function handleTranslationChange() {
    const row = this.closest("tr");
    if (!row) {
      return;
    }
    const checksum = row.querySelector("[name=checksum]")?.value;
    const statusdiv = getStatusCell(row, checksum);
    const form = row.querySelector(".translator form");
    if (!form || !statusdiv) {
      return;
    }
    const payload = new URLSearchParams(new FormData(form)).toString();
    const lastPayload = statusdiv._lastPayload;

    // Guard: skip if a save is already happening
    if (statusdiv.classList.contains("unit-state-saving")) {
      setTimeout(() => {
        handleTranslationChange.call(this); // Reinvoke
      }, 100);
      return;
    }

    // First save
    if (lastPayload === undefined) {
      statusdiv._lastPayload = payload;
    }
    // Guard: skip if nothing has changed
    if (payload === lastPayload) {
      statusdiv.classList.remove("unit-state-save-timeout");
      return;
    }

    row.classList.add("translation-modified");
    statusdiv.classList.add("unit-state-saving");
    statusdiv._lastPayload = payload;

    fetch(form.getAttribute("action"), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        Accept: "application/json",
      },
      body: payload,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        statusdiv.setAttribute(
          "class",
          `unit-state-cell ${data.unit_state_class}`,
        );
        statusdiv.setAttribute("title", data.unit_state_title);

        for (const val of data.messages) {
          addAlert(val.text, val.kind);
        }

        row.classList.remove("translation-modified");
        row.classList.add("translation-saved");
        row.querySelector("#unsaved-label")?.remove();
        for (const el of row.querySelectorAll(".translation-editor")) {
          el.classList.remove("has-changes");
        }

        if (data.translationsum !== "") {
          const sum = row.querySelector("input[name=translationsum]");
          if (sum) {
            sum.value = data.translationsum;
          }
        }

        // Suggestion diffs are against the saved target
        if ("has_suggestions" in data) {
          updateZenSuggestions(row.closest(".zen-unit"), data);
        }
      })
      .catch((err) => {
        addAlert(err.message);
      })
      .finally(() => {
        statusdiv.classList.remove("unit-state-saving");
        statusdiv.classList.remove("unit-state-save-timeout");
        row._saveTimer = undefined;
      });
  }

  /* Suggestions */

  const ACCEPT_MODES = new Set(["accept", "accept_edit", "accept_approve"]);

  const getUnitEditors = (unit) =>
    unit.querySelectorAll(".translator .translation-editor");

  const unitHasChanges = (unit) =>
    unit.querySelector(".translator .translation-editor.has-changes") !== null;

  /* Clone suggestion into the editor of the same unit */
  delegate(
    document,
    "click",
    ".zen-suggestions .js-copy-suggestion",
    function (e) {
      e.preventDefault();
      const unit = this.closest(".zen-unit");
      const editors = unit ? getUnitEditors(unit) : [];
      if (editors.length) {
        WLT.Utils.copySuggestion(this, editors);
      }
    },
  );

  delegate(document, "submit", ".zen-suggestions-form", function (e) {
    e.preventDefault();
    handleSuggestionAction(this, e.submitter);
  });

  function handleSuggestionAction(form, button) {
    if (!button?.name) {
      return;
    }
    const mode = button.name;
    const unit = form.closest(".zen-unit");
    const checksum = form.querySelector("[name=checksum]")?.value;
    const statusdiv = getStatusCell(unit, checksum);
    if (!unit || !statusdiv) {
      return;
    }

    // Guard: wait for a running save to finish
    if (statusdiv.classList.contains("unit-state-saving")) {
      setTimeout(() => {
        handleSuggestionAction(form, button); // Reinvoke
      }, 100);
      return;
    }

    // Guard: accepting overwrites the editor, do not lose pending edits
    if (ACCEPT_MODES.has(mode) && unitHasChanges(unit)) {
      addAlert(
        gettext("Save or discard your changes before accepting a suggestion."),
        "warning",
      );
      return;
    }

    const payload = new URLSearchParams();
    payload.append(
      "csrfmiddlewaretoken",
      form.querySelector("[name=csrfmiddlewaretoken]")?.value ?? "",
    );
    payload.append(
      "unit_id",
      form.querySelector("[name=unit_id]")?.value ?? "",
    );
    payload.append("checksum", checksum);
    payload.append(mode, button.value);
    if (mode === "delete" || mode === "spam") {
      const rejection = button
        .closest(".history-row")
        ?.querySelector("input[name=rejection]");
      payload.append("rejection", rejection?.value ?? "");
    }

    statusdiv.classList.add("unit-state-saving");

    fetch(form.getAttribute("action"), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        Accept: "application/json",
      },
      body: payload.toString(),
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        applyZenUnitData(unit, data);
      })
      .catch((err) => {
        addAlert(err.message);
      })
      .finally(() => {
        statusdiv.classList.remove("unit-state-saving");
      });
  }

  /* Replace the suggestions block of a Zen row with the rendered one */
  function updateZenSuggestions(unit, data) {
    if (!unit) {
      return;
    }
    const container = unit.querySelector(".zen-suggestions-container");
    if (data.has_suggestions) {
      if (container) {
        const suggestionKey = (el) =>
          el.closest(".history-row")?.querySelector("button[value]")?.value;
        const rejections = new Map();
        for (const input of container.querySelectorAll(
          "input[name=rejection]",
        )) {
          if (input.value) {
            rejections.set(suggestionKey(input), input.value);
          }
        }
        const active = container.contains(document.activeElement)
          ? document.activeElement
          : null;
        const activeKey = active ? suggestionKey(active) : undefined;
        const activeName = active?.getAttribute("name");

        container.innerHTML = data.suggestions_html;
        initHighlight(container);

        for (const input of container.querySelectorAll(
          "input[name=rejection]",
        )) {
          const value = rejections.get(suggestionKey(input));
          if (value !== undefined) {
            input.value = value;
          }
        }
        if (activeKey !== undefined && activeName) {
          const row = container
            .querySelector(`button[value="${CSS.escape(activeKey)}"]`)
            ?.closest(".history-row");
          row?.querySelector(`[name="${CSS.escape(activeName)}"]`)?.focus();
        }
      }
    } else {
      unit.querySelector(".zen-suggestions-row")?.remove();
    }
    updateSuggestionsIndicator(unit, data.has_suggestions ? container : null);
  }

  /* Keep the per-string suggestion count in sync */
  function updateSuggestionsIndicator(unit, container) {
    const indicator = unit.querySelector(".zen-suggestions-indicator");
    if (!indicator) {
      return;
    }
    const count = container
      ? container.querySelectorAll(".history-row").length
      : 0;
    if (count === 0) {
      indicator.remove();
      return;
    }
    const text = interpolate(
      ngettext("%s suggestion", "%s suggestions", count),
      [count],
    );
    indicator.title = text;
    indicator.querySelector(".zen-suggestions-count").textContent = count;
    indicator.querySelector(".zen-suggestions-label").textContent = text;
  }

  /* Resync a Zen row from the JSON payload of the zen unit endpoints */
  function applyZenUnitData(unit, data) {
    for (const val of data.messages) {
      addAlert(val.text, val.kind);
    }

    const checksum = data.checksum;

    updateZenSuggestions(unit, data);

    // State cell
    const statusdiv = getStatusCell(unit, checksum);
    if (statusdiv) {
      statusdiv.setAttribute(
        "class",
        `unit-state-cell ${data.unit_state_class}`,
      );
      statusdiv.setAttribute("title", data.unit_state_title);
    }

    // Editor content, only when the target has changed
    if (data.target === null) {
      return;
    }
    const form = unit.querySelector(".translator form");
    const editors = getUnitEditors(unit);
    if (unitHasChanges(unit)) {
      const sum = form?.querySelector("input[name=translationsum]");
      if (sum && sum.value !== data.translationsum) {
        addAlert(
          gettext(
            "The translation was changed while you were editing it, your unsaved changes were kept.",
          ),
          "warning",
        );
      }
      return;
    }
    editors.forEach((el, i) => {
      if (i < data.target.length) {
        replaceValue(el, data.target[i]);
      }
    });
    if (form) {
      // Set checked directly
      const review = form.querySelector(
        `input[name=review][value="${data.review}"]`,
      );
      if (review) {
        review.checked = true;
      }
      const fuzzy = form.querySelector("input[name=fuzzy]");
      if (fuzzy) {
        fuzzy.checked = data.fuzzy;
      }
      const sum = form.querySelector("input[name=translationsum]");
      if (sum) {
        sum.value = data.translationsum;
      }
    }
    for (const el of editors) {
      el.classList.remove("has-changes");
    }
    for (const label of unit.querySelectorAll("#unsaved-label")) {
      label.remove();
    }
    form?.closest("tr")?.classList.remove("translation-modified");
    if (form && statusdiv) {
      statusdiv._lastPayload = new URLSearchParams(
        new FormData(form),
      ).toString();
    }
    if (data.mode === "accept_edit") {
      editors[0]?.focus();
    }
  }

  function fetchZenUnit(form) {
    const unit = form.closest(".zen-unit");
    const url = form.dataset.unitUrl;
    if (!unit || !url) {
      return Promise.resolve();
    }
    const params = new URLSearchParams({
      checksum: form.querySelector("[name=checksum]")?.value ?? "",
      unit_id: form.querySelector("[name=unit_id]")?.value ?? "",
    });
    return fetch(`${url}?${params}`, {
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        Accept: "application/json",
      },
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        applyZenUnitData(unit, data);
      })
      .catch((err) => {
        addAlert(err.message);
      });
  }

  function refreshZenSuggestions() {
    const [first, ...rest] = document.querySelectorAll(".zen-suggestions-form");
    if (!first) {
      return;
    }
    fetchZenUnit(first).then(() => {
      for (const form of rest) {
        fetchZenUnit(form);
      }
    });
  }

  document.addEventListener("weblate:suggestions-changed", () => {
    refreshZenSuggestions();
  });

  /* Suggestions visibility toggle, remembered in local storage */

  const SUGGESTIONS_STORAGE_KEY = "zen-suggestions";

  /* Expose the suggestions visibility on the per-string counts */
  function syncSuggestionIndicators() {
    const expanded = !document
      .querySelector("table.zen")
      ?.classList.contains("zen-hide-suggestions");
    for (const indicator of document.querySelectorAll(
      ".zen-suggestions-indicator",
    )) {
      indicator.setAttribute("aria-expanded", String(expanded));
    }
  }

  function initSuggestionsToggle() {
    const button = document.getElementById("zen-toggle-suggestions");
    const label = document.getElementById("zen-toggle-suggestions-label");
    const table = document.querySelector("table.zen");
    if (!button || !label || !table) {
      return;
    }

    const apply = (visible) => {
      table.classList.toggle("zen-hide-suggestions", !visible);
      syncSuggestionIndicators();
      const text = visible
        ? gettext("Hide suggestions")
        : gettext("Show suggestions");
      label.textContent = text;
      button.title = text;
      button.setAttribute("aria-label", text);
    };

    let visible = false;
    try {
      visible = localStorage.getItem(SUGGESTIONS_STORAGE_KEY) === "shown";
    } catch (_error) {
      /* Local storage can be unavailable, keep suggestions hidden */
    }
    apply(visible);

    const setVisible = (value) => {
      visible = value;
      apply(visible);
      try {
        localStorage.setItem(
          SUGGESTIONS_STORAGE_KEY,
          visible ? "shown" : "hidden",
        );
      } catch (_error) {
        /* Ignore, the toggle still works for this page */
      }
    };

    button.addEventListener("click", () => {
      setVisible(!visible);
    });

    // The per-string count toggles suggestions, moving to those of the string
    // when showing them
    delegate(document, "click", ".zen-suggestions-indicator", function () {
      if (visible) {
        setVisible(false);
        return;
      }
      setVisible(true);
      const container = this.closest(".zen-unit")?.querySelector(
        ".zen-suggestions-container",
      );
      if (container) {
        container.tabIndex = -1;
        container.focus({ preventScroll: true });
        container.scrollIntoView({ block: "nearest" });
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    new ZenEditor();
    initSuggestionsToggle();
  });
})();
