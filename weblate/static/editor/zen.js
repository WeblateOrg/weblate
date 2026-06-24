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
            if (!response.ok) {
              throw new Error(`HTTP ${response.status}`);
            }
            return response.text();
          })
          .then((data) => {
            loadingNext.style.display = "none";

            const tfoot = document.querySelector(".zen tfoot");
            tfoot?.insertAdjacentHTML("beforebegin", data);

            this.init();
            initHighlight(document);
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

  delegate(document, "focusin", ".translation-editor", function () {
    const row = this.closest("tr");
    if (!row) {
      return;
    }
    const checksum = row.querySelector("[name=checksum]")?.value;
    const statusdiv = document.getElementById(`status-${checksum}`);
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
    const statusdiv = document.getElementById(`status-${checksum}`);
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
    const statusdiv = document.getElementById(`status-${checksum}`);
    const form = row.querySelector("form");
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

  document.addEventListener("DOMContentLoaded", () => {
    new ZenEditor();
  });
})();
