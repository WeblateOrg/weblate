// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

// biome-ignore lint/correctness/noInvalidUseBeforeDeclaration: TODO: doesn't work without that
var WLT = WLT || {};

function delegate(roots, eventName, selector, handler, options) {
  const list =
    roots instanceof NodeList || Array.isArray(roots) ? roots : [roots];
  for (const root of list) {
    if (!root) {
      continue;
    }
    root.addEventListener(
      eventName,
      (event) => {
        const match = event.target.closest?.(selector);
        if (match && root.contains(match)) {
          handler.call(match, event);
        }
      },
      options,
    );
  }
}

WLT.Config = (() => ({
  IS_MAC: /Mac|iPod|iPhone|iPad/.test(navigator.platform),
  HAS_REVIEW_WORKFLOW:
    document.querySelectorAll(
      '.translation-form input[name="review"][value="30"]',
    ).length > 0,
}))();

WLT.Utils = (() => ({
  getNumericKey: (idx) => (idx + 1) % 10,

  markFuzzy: (el) => {
    if (!el) {
      return;
    }
    /* Standard workflow */
    for (const input of el.querySelectorAll('input[name="fuzzy"]')) {
      input.checked = true;
    }
    /* Review workflow */
    for (const input of el.querySelectorAll(
      'input[name="review"][value="10"]',
    )) {
      input.checked = true;
    }
  },

  markTranslated: (el) => {
    if (!el) {
      return;
    }
    /* Standard workflow */
    for (const input of el.querySelectorAll('input[name="fuzzy"]')) {
      input.checked = false;
    }
    /* Review workflow */
    for (const input of el.querySelectorAll(
      'input[name="review"][value="20"]',
    )) {
      input.checked = true;
    }
  },

  markApproved: (el) => {
    if (!el) {
      return;
    }
    /* Standard workflow */
    for (const input of el.querySelectorAll('input[name="fuzzy"]')) {
      input.checked = false;
    }
    /* Review workflow */
    for (const input of el.querySelectorAll(
      'input[name="review"][value="30"]',
    )) {
      input.checked = true;
    }
  },

  /**
   * Indicate that the translation has changed
   * by appending a warning before the editor.
   * @param {Event} [e] - The event object (optional)
   * @returns {void}
   */
  indicateChanges: (e) => {
    const editorArea = e
      ? e.target.closest(".translation-editor")
      : document.querySelector(".translator .translation-editor");
    if (!editorArea) {
      return;
    }
    const target = editorArea
      .closest(".translation-item")
      ?.querySelector(".editor-footer");
    if (!target) {
      return;
    }
    const next = target.nextElementSibling;
    if (next?.classList.contains("text-warning")) {
      return;
    }
    const warning = document.createElement("div");
    warning.id = "unsaved-label";
    warning.className = "text-warning float-end";
    warning.textContent = gettext("Unsaved changes!");
    target.insertAdjacentElement("afterend", warning);
    editorArea.classList.add("has-changes");
  },
  /**
   * Check if the translation has any changes
   * @param {Event} [e] - The event object (optional)
   * @returns {boolean}
   */
  editorHasChanges: (e) => {
    const editorArea = e
      ? e.target.closest(".translation-editor")
      : document.querySelector(".translator .translation-editor");
    return editorArea?.classList.contains("has-changes") ?? false;
  },
}))();

WLT.Editor = (() => {
  let lastEditor = null;

  function EditorBase() {
    const translationAreaSelector = ".translation-editor";

    this.editors = document.querySelectorAll(".js-editor");
    /* Only insert actual translation editor, not a popup for adding variant */
    this.translationArea = document.querySelector(
      ".translator .translation-editor",
    );

    delegate(this.editors, "input", translationAreaSelector, (e) => {
      WLT.Utils.markTranslated(e.target.closest("form"));
      WLT.Utils.indicateChanges(e);
    });

    delegate(this.editors, "focusin", translationAreaSelector, function () {
      lastEditor = this;
    });

    /* Count characters */
    delegate(this.editors, "input", translationAreaSelector, (e) => {
      const textarea = e.target;
      const editor = textarea.parentElement.parentElement;
      const counter = editor.querySelector(".length-indicator");
      const classToggle = editor.classList;

      const limit = Number.parseInt(counter.getAttribute("data-max"), 10);
      const length = textarea.value.length;

      counter.textContent = length;
      if (length > limit) {
        classToggle.remove("has-warning");
        classToggle.add("has-error");
      } else if (length > limit - 10) {
        classToggle.add("has-warning");
        classToggle.remove("has-error");
      } else {
        classToggle.remove("has-warning");
        classToggle.remove("has-error");
      }
    });

    /* Copy source text */
    delegate(this.editors, "click", "[data-clone-value]", function (e) {
      const cloneText = this.getAttribute("data-clone-value");

      const row =
        this.closest(".zen-unit") ||
        this.closest(".translator") ||
        document.querySelector(".translator");
      const editors = row ? row.querySelectorAll(".translation-editor") : [];
      if (editors.length === 1) {
        replaceValue(editors[0], cloneText);
      } else {
        addAlert(gettext("Please select target plural by clicking."), "info");
        for (const editor of editors) {
          editor.classList.add("editor-click-select");
        }

        const cleanup = () => {
          for (const editor of editors) {
            editor.classList.remove("editor-click-select");
            editor.removeEventListener("click", onEditorClick);
          }
          document.removeEventListener("click", onDocClick);
        };
        const onEditorClick = function (ev) {
          replaceValue(this, cloneText);
          cleanup();
          ev.preventDefault();
          ev.stopPropagation();
        };
        const onDocClick = (ev) => {
          cleanup();
          ev.preventDefault();
        };
        for (const editor of editors) {
          editor.addEventListener("click", onEditorClick);
        }
        document.addEventListener("click", onDocClick);
      }
      WLT.Utils.markFuzzy(this.closest("form"));
      WLT.Utils.indicateChanges(e);
      e.preventDefault();
      e.stopPropagation();
    });

    /* Direction toggling */
    delegate(this.editors, "change", ".direction-toggle", function (e) {
      const direction = this.querySelector("input")?.value;
      const container = this.closest(".translation-item");
      if (!container) {
        return;
      }
      for (const el of container.querySelectorAll(".translation-editor")) {
        el.setAttribute("dir", direction);
      }
      for (const el of container.querySelectorAll(".highlighted-output")) {
        el.setAttribute("dir", direction);
      }
      WLT.Utils.indicateChanges(e);
    });

    /* Special characters */
    delegate(this.editors, "click", ".specialchar", function (e) {
      const text = this.getAttribute("data-value");
      const editor = this.closest(".translation-item")?.querySelector(
        ".translation-editor",
      );
      if (editor) {
        insertAtCaret(editor, text);
      }
      e.preventDefault();
      WLT.Utils.indicateChanges(e);
    });

    // Disable insertion and copy buttons for read only strings
    for (const translator of document.querySelectorAll(".translator")) {
      const firstEditor = translator.querySelector(".translation-editor");
      if (firstEditor?.hasAttribute("readonly")) {
        // Apply to zen unit or the entire document
        // the latter also disables insertion from related strings
        const root = translator.closest(".zen-unit") || document;
        for (const el of root.querySelectorAll(".specialchar")) {
          el.setAttribute("disabled", "");
        }
        for (const el of root.querySelectorAll("[data-clone-value]")) {
          el.setAttribute("disabled", "");
        }
        for (const el of root.querySelectorAll(".hlcheck")) {
          el.classList.add("disabled");
        }
      }
    }

    this.initHighlight();
    this.init();

    this.translationArea?.focus();

    // Show confirmation dialog if changes have been made
    // when leaving the page
    addEventListener("beforeunload", (e) => {
      if (WLT.Utils.editorHasChanges()) {
        e.preventDefault();
        return true; // Backwards compatibility
      }
    });

    // Skip confirmation
    delegate(this.editors, "click", ".skip", (e) => {
      if (WLT.Utils.editorHasChanges(e)) {
        if (
          !confirm(
            gettext("You have unsaved changes. Are you sure you want to skip?"),
          )
        ) {
          e.preventDefault();
        }
      }
    });

    // Remove unsaved changes warning when submitting
    for (const editor of this.editors) {
      editor.addEventListener("submit", () => {
        for (const el of document.querySelectorAll(
          ".translator .translation-editor",
        )) {
          el.classList.remove("has-changes");
        }
      });
    }
  }

  EditorBase.prototype.init = () => {};

  EditorBase.prototype.initHighlight = function () {
    const hlSelector = ".hlcheck";
    const hlNumberSelector = ".highlight-number";

    /* Copy from source text highlight check */
    delegate(this.editors, "click", hlSelector, function (e) {
      // Do not insert if highlighted element is disabled
      if (!this.classList.contains("disabled")) {
        insertEditor(this.getAttribute("data-value"), this);
      }
      e.preventDefault();
      WLT.Utils.indicateChanges(e);
    });

    /* and shortcuts */
    for (let i = 1; i < 10; i++) {
      hotkeys(`ctrl+${i},command+${i}`, () => false);
    }

    const hlChecks = document.querySelectorAll(hlSelector);
    if (hlChecks.length > 0) {
      hlChecks.forEach((el, idx) => {
        if (idx < 10) {
          const key = WLT.Utils.getNumericKey(idx);

          let title;
          if (WLT.Config.IS_MAC) {
            title = interpolate(gettext("Cmd+%s"), [key]);
          } else {
            title = interpolate(gettext("Ctrl+%s"), [key]);
          }
          el.setAttribute("title", title);
          const numberEl = el.querySelector(hlNumberSelector);
          if (numberEl) {
            const kbd = document.createElement("kbd");
            kbd.textContent = key;
            numberEl.replaceChildren(kbd);
          }

          hotkeys(`ctrl+${key},command+${key}`, () => {
            el.click();
            return false;
          });
        } else {
          const numberEl = el.querySelector(hlNumberSelector);
          if (numberEl) {
            numberEl.replaceChildren();
          }
        }
      });
      for (const el of document.querySelectorAll(hlNumberSelector)) {
        el.style.display = "none";
      }
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "Control" || e.key === "Meta") {
        for (const el of document.querySelectorAll(hlNumberSelector)) {
          el.style.display = "";
        }
      }
    });
    document.addEventListener("keyup", (e) => {
      if (e.key === "Control" || e.key === "Meta") {
        for (const el of document.querySelectorAll(hlNumberSelector)) {
          el.style.display = "none";
        }
      }
    });
  };

  function insertEditor(text, element) {
    let root;

    /* Find within root element */
    if (element) {
      root =
        element.closest(".zen-unit") ||
        element.closest(".translation-form") ||
        document;
    } else {
      root = document;
    }

    let editor = root.querySelector(".translation-editor:focus");
    if (!editor) {
      if (lastEditor && root.contains(lastEditor)) {
        editor = lastEditor;
      } else {
        editor = root.querySelector(".translation-editor");
      }
    }

    if (editor) {
      insertAtCaret(editor, text);
    }
  }

  return {
    Base: EditorBase,
  };
})();
