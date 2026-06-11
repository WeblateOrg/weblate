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
      return origAddItem.call(this, value, silent);
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
