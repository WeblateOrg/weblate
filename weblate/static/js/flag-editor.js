// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

// Tag-based editor for translation flag fields

(() => {
  const flagChoicesPromises = new Map();

  function loadFlagChoices(url) {
    if (!flagChoicesPromises.has(url)) {
      const promise = fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then((response) => (response.ok ? response.json() : { choices: [] }))
        .then((data) => data.choices || [])
        .catch(() => []);
      flagChoicesPromises.set(url, promise);
    }
    return flagChoicesPromises.get(url);
  }

  /*
   * Quote character left open at the end of the string, null when it ends
   * outside of quotes. A comma is a flag separator only outside of quotes.
   */
  function openQuoteChar(value) {
    let quoteChar = null;
    let escaped = false;
    for (const ch of value) {
      if (escaped) {
        escaped = false;
      } else if (ch === "\\") {
        escaped = true;
      } else if (ch === '"' || ch === "'") {
        if (quoteChar === null) {
          quoteChar = ch;
        } else if (quoteChar === ch) {
          quoteChar = null;
        }
      }
    }
    return quoteChar;
  }

  /*
   * Split a flag-text string into individual flag tokens
   */
  function parseFlagInputValue(value) {
    const items = [];
    let current = "";
    let quoteChar = null;
    let escaped = false;
    for (let i = 0; i < value.length; i++) {
      const ch = value[i];
      if (escaped) {
        current += ch;
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        current += ch;
        escaped = true;
        continue;
      }
      if (ch === '"' || ch === "'") {
        if (quoteChar === null) {
          quoteChar = ch;
        } else if (quoteChar === ch) {
          quoteChar = null;
        }
        current += ch;
        continue;
      }
      if (ch === "," && quoteChar === null) {
        const trimmed = current.trim();
        if (trimmed) items.push(trimmed);
        current = "";
        continue;
      }
      current += ch;
    }
    const trimmed = current.trim();
    if (trimmed) items.push(trimmed);
    return items;
  }

  function initFlagEditor(input) {
    if (input.dataset.flagEditorInitialized === "1") {
      return;
    }
    input.dataset.flagEditorInitialized = "1";

    const choicesUrl = input.dataset.flagChoicesUrl;
    if (!choicesUrl || typeof TomSelect === "undefined") {
      return;
    }

    const select = document.createElement("select");
    select.multiple = true;
    select.classList.add("flag-editor-select");
    for (const cls of input.classList) {
      if (cls === "flag-editor") continue;
      select.classList.add(cls);
    }

    /* Pre-populate from current value so existing flags render immediately,
     * without waiting for the catalog fetch to complete. */
    const initialFlags = parseFlagInputValue(input.value || "");
    for (const flag of initialFlags) {
      const opt = document.createElement("option");
      opt.value = flag;
      opt.textContent = flag;
      opt.selected = true;
      select.appendChild(opt);
    }

    input.classList.add("d-none");
    input.setAttribute("aria-hidden", "true");
    input.tabIndex = -1;
    input.parentNode.insertBefore(select, input);

    const customCategory = gettext("Custom");

    const ts = new TomSelect(select, {
      plugins: ["remove_button"],
      persist: false,
      create: (raw) => {
        const trimmed = String(raw || "").trim();
        if (!trimmed) return false;
        return {
          name: trimmed,
          label: trimmed,
          category: customCategory,
          has_value: false,
        };
      },
      createOnBlur: true,
      valueField: "name",
      labelField: "name",
      searchField: ["name", "label"],
      /* While typing the value of a parametrized flag keep matching the
       * base flag name so the known flag stays visible in the dropdown. */
      score: function (search) {
        const colon = search.indexOf(":");
        const base = colon === -1 ? search : search.slice(0, colon);
        return this.getScoreFunction(base);
      },
      optgroupField: "category",
      optgroupLabelField: "category",
      optgroupValueField: "category",
      placeholder: gettext("Add a flag…"),
      hidePlaceholder: false,
      maxOptions: null,
      render: {
        option: (data, esc) => {
          const sample = data.has_value
            ? `${esc(data.name)}:…`
            : esc(data.name);
          const label =
            data.label && data.label !== data.name
              ? ` <span class="text-muted">${esc(data.label)}</span>`
              : "";
          return `<div><code>${sample}</code>${label}</div>`;
        },
        item: (data, esc) => `<div><code>${esc(data.name)}</code></div>`,
        no_results: (data, esc) =>
          `<div class="no-results">${esc(
            interpolate(
              gettext(
                'No matching flag found for "%s"; press Enter to add it as a custom flag.',
              ),
              [data.input],
            ),
          )}</div>`,
        optgroup_header: (data, esc) =>
          `<div class="optgroup-header">${esc(data.category)}</div>`,
      },
    });

    if (ts.control_input) {
      if (input.id) {
        ts.control_input.id = `${input.id}-ts-input`;
        // Re-point the field label at the visible TomSelect control
        const selector =
          typeof CSS !== "undefined" && CSS.escape
            ? `label[for="${CSS.escape(input.id)}"]`
            : `label[for="${input.id}"]`;
        for (const label of document.querySelectorAll(selector)) {
          label.htmlFor = ts.control_input.id;
        }
      }
      // Carry over accessibility metadata
      for (const attr of [
        "aria-label",
        "aria-labelledby",
        "aria-describedby",
      ]) {
        const value = input.getAttribute(attr);
        if (value) {
          ts.control_input.setAttribute(attr, value);
        }
      }
    }

    ts.on("change", () => {
      input.value = ts.items.join(", ");
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });

    /* Intercept selection of a parametrized flag without a value */
    const origAddItem = ts.addItem;
    ts.addItem = function (value, silent) {
      const opt = this.options[value];
      if (opt?.has_value && !String(value).includes(":")) {
        const typed = (this.control_input?.value || "").trim();
        const prefix = `${value}:`;
        if (typed.length > prefix.length && typed.startsWith(prefix)) {
          this.createItem(typed);
          return;
        }
        this.setTextboxValue(prefix);
        this.focus();
        this.refreshOptions(true);
        return;
      }
      const before = this.items.length;
      const result = origAddItem.call(this, value, silent);
      if (this.items.length !== before && this.inputValue().length) {
        this.setTextboxValue();
        this.refreshOptions(this.isFocused);
      }
      return result;
    };

    /* Typing a comma inside a quoted value keeps it as part of the flag
     * instead of starting a new one. */
    const origKeyPress = ts.onKeyPress;
    ts.onKeyPress = function (e) {
      if (e.key === ",") {
        const caret = this.control_input?.selectionStart;
        const typed = this.control_input?.value || "";
        const before =
          typeof caret === "number" ? typed.slice(0, caret) : typed;
        if (openQuoteChar(before) !== null) {
          return;
        }
      }
      origKeyPress.call(this, e);
    };

    /* Split pasted text the same way the flags are parsed, so that commas
     * inside quotes do not split a flag in half. */
    ts.onPaste = function (e) {
      if (this.isInputHidden || this.isLocked) {
        e.preventDefault();
        return;
      }
      /* Wait for the pasted text to appear in the text box */
      setTimeout(() => {
        const flags = parseFlagInputValue(this.inputValue());
        if (flags.length < 2) {
          return;
        }
        for (const flag of flags) {
          if (this.options[flag]) {
            this.addItem(flag);
          } else {
            this.createItem(flag);
          }
        }
      }, 0);
    };

    let editedIndex = null;

    function restoreEditedPosition(value, item) {
      const index = editedIndex;
      editedIndex = null;
      if (index === null) {
        return;
      }
      const from = ts.items.indexOf(value);
      if (from === -1 || from === index) {
        return;
      }
      ts.items.splice(from, 1);
      ts.items.splice(index, 0, value);
      const siblings = ts.controlChildren().filter((child) => child !== item);
      ts.control.insertBefore(item, siblings[index] || ts.control_input);
    }

    ts.on("item_add", restoreEditedPosition);
    ts.on("blur", () => {
      editedIndex = null;
    });

    const origCreateItem = ts.createItem;
    ts.createItem = function (...args) {
      const before = this.items.length;
      const result = origCreateItem.apply(this, args);
      if (this.items.length === before) {
        editedIndex = null;
      }
      return result;
    };

    /* Turn an already added flag back into editable text. */
    function editItem(item) {
      if (!item || ts.isLocked) {
        return false;
      }
      const value = item.dataset.value;
      if (typeof value === "undefined") {
        return false;
      }
      if (ts.inputValue().length) {
        ts.createItem();
      }
      /* After createItem(), which may have shifted this item */
      const index = ts.controlChildren().indexOf(item);
      ts.clearActiveItems();
      ts.removeItem(item);
      ts.inputState();
      ts.setTextboxValue(value);
      ts.focus();
      ts.refreshOptions(true);
      editedIndex = index === -1 ? null : index;
      return true;
    }

    function activeItemsInOrder() {
      return ts
        .controlChildren()
        .filter((item) => item.classList.contains("active"));
    }

    /* Clicking a flag opens it for editing */
    const origItemSelect = ts.onItemSelect;
    ts.onItemSelect = function (evt, item) {
      if (evt && !evt.shiftKey && !evt.ctrlKey && !evt.metaKey) {
        if (editItem(item)) {
          return true;
        }
      }
      return origItemSelect.call(this, evt, item);
    };

    const origKeyDown = ts.onKeyDown;
    ts.onKeyDown = function (e) {
      /* Enter or F2 reopens the selected flag for editing */
      if (
        (e.key === "Enter" || e.key === "F2") &&
        this.activeItems.length === 1 &&
        editItem(this.activeItems[0])
      ) {
        e.preventDefault();
        return;
      }
      /* Ctrl - C to copy flags */
      if (
        (e.ctrlKey || e.metaKey) &&
        !e.shiftKey &&
        e.key?.toLowerCase() === "c" &&
        this.activeItems.length
      ) {
        e.preventDefault();
        copyToClipboard(
          activeItemsInOrder()
            .map((item) => item.dataset.value)
            .join(", "),
        );
        return;
      }
      origKeyDown.call(this, e);
    };

    /* Keyboard navigation for flags */
    ts.moveCaret = (direction) => {
      const items = ts.controlChildren();
      if (!items.length) {
        return;
      }
      const active = activeItemsInOrder();
      let next;
      if (!active.length) {
        if (direction > 0) {
          return;
        }
        next = items.length - 1;
      } else {
        const anchor = direction < 0 ? active[0] : active[active.length - 1];
        next = items.indexOf(anchor) + direction;
        if (next < 0) {
          next = 0;
        }
      }
      ts.clearActiveItems();
      if (next < items.length) {
        ts.setActiveItemClass(items[next]);
      }
      ts.inputState();
    };

    loadFlagChoices(choicesUrl).then((choices) => {
      const groups = new Set();
      for (const choice of choices) {
        groups.add(choice.category);
      }
      for (const group of groups) {
        ts.addOptionGroup(group, { category: group });
      }
      for (const choice of choices) {
        if (!ts.options[choice.name]) {
          ts.addOption(choice);
        }
      }
      ts.refreshOptions(false);
    });
  }

  function initAll() {
    document
      .querySelectorAll("input.flag-editor, textarea.flag-editor")
      .forEach(initFlagEditor);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }

  window.initFlagEditor = initFlagEditor;
})();
