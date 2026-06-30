// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

const loading = [];

// DOM helpers replacing former jQuery usage.
function show(element) {
  if (element) {
    element.style.display = "";
  }
}
function hide(element) {
  if (element) {
    element.style.display = "none";
  }
}
function toggleDisplay(element) {
  if (!element) {
    return;
  }
  if (getComputedStyle(element).display === "none") {
    element.style.display = "";
  } else {
    element.style.display = "none";
  }
}
function onReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
  } else {
    callback();
  }
}

// Remove some weird things from location hash
if (
  window.location.hash &&
  (window.location.hash.indexOf('"') > -1 ||
    window.location.hash.indexOf("=") > -1)
) {
  window.location.hash = "";
}

// Loading indicator handler
function increaseLoading(sel) {
  if (!(sel in loading)) {
    loading[sel] = 0;
  }
  if (loading[sel] === 0) {
    show(document.getElementById(`loading-${sel}`));
  }
  loading[sel] += 1;
}

function decreaseLoading(sel) {
  loading[sel] -= 1;
  if (loading[sel] === 0) {
    hide(document.getElementById(`loading-${sel}`));
  }
}

function addAlert(message, kind = "danger", delay = 3000) {
  const toasts = document.getElementById("popup-toasts");
  if (toasts === null) {
    return;
  }
  const supportedKinds = new Set([
    "danger",
    "warning",
    "info",
    "success",
    "primary",
    "secondary",
    "light",
    "dark",
  ]);
  let toastKind = kind === "error" ? "danger" : kind;
  if (!supportedKinds.has(toastKind)) {
    toastKind = "danger";
  }
  const assertiveKinds = new Set(["danger", "warning"]);
  const isAssertive = assertiveKinds.has(toastKind);
  const toast = document.createElement("div");
  toast.classList.add(
    "toast",
    "align-items-center",
    `text-${toastKind}-emphasis`,
    `bg-${toastKind}-subtle`,
    `border-${toastKind}-subtle`,
  );
  toast.setAttribute("role", isAssertive ? "alert" : "status");
  toast.setAttribute("aria-live", isAssertive ? "assertive" : "polite");
  toast.setAttribute("aria-atomic", "true");

  const content = document.createElement("div");
  content.classList.add("d-flex");

  const body = document.createElement("div");
  body.classList.add("toast-body");
  body.append(document.createTextNode(String(message)));

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.classList.add("btn-close", "me-2", "m-auto");
  closeButton.setAttribute("data-bs-dismiss", "toast");
  closeButton.setAttribute("aria-label", gettext("Close"));

  content.append(body, closeButton);
  toast.append(content);
  toast.addEventListener(
    "hidden.bs.toast",
    () => {
      bootstrap.Toast.getInstance(toast)?.dispose();
      toast.remove();
    },
    { once: true },
  );
  toasts.append(toast);

  bootstrap.Toast.getOrCreateInstance(toast, {
    autohide: Boolean(delay),
    delay,
  }).show();
}

// Need `bubbles` because some event listeners (like this
// https://github.com/WeblateOrg/weblate/blob/86d4fb308c9941f32b48f007e16e8c153b0f3fd7/weblate/static/editor/base.js#L50
// ) are attached to the parent elements.
function insertAtCaret(element, myValue) {
  if (document.selection) {
    // For browsers like Internet Explorer
    element.focus();
    const sel = document.selection.createRange();

    sel.text = myValue;
    element.focus();
  } else if (element.selectionStart || element.selectionStart === 0) {
    //For browsers like Firefox and Webkit based
    const startPos = element.selectionStart;
    const endPos = element.selectionEnd;
    const scrollTop = element.scrollTop;

    element.value =
      element.value.substring(0, startPos) +
      myValue +
      element.value.substring(endPos, element.value.length);
    element.focus();
    element.selectionStart = startPos + myValue.length;
    element.selectionEnd = startPos + myValue.length;
    element.scrollTop = scrollTop;
  } else {
    element.value += myValue;
    element.focus();
  }
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

// biome-ignore lint/correctness/noUnusedVariables: global helper used by editor/base.js and editor/full.js
function replaceValue(element, myValue) {
  element.value = myValue;
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

function submitForm(evt, _combo, selector) {
  let form = evt.target?.closest("form") ?? null;

  if (form === null) {
    form = document.querySelector(".translation-form");
  }
  if (form !== null) {
    if (typeof selector !== "undefined") {
      form.querySelector(selector)?.click();
    } else {
      const submit =
        form.querySelector('input[type="submit"]') ||
        form.querySelector('button[type="submit"]');
      submit?.click();
    }
  }
  return false;
}
hotkeys("ctrl+enter,command+enter", (e) => {
  return submitForm(e);
});

function screenshotStart() {
  document
    .querySelector("#search-results tbody.unit-listing-body")
    ?.replaceChildren();
  const summary = document.getElementById("screenshots-search-summary");
  if (summary !== null) {
    summary.textContent = "";
  }
  screenshotUpdateBulkControls();
  increaseLoading("screenshots");
}

function screenshotFailure() {
  screenshotLoaded({ responseCode: 500 });
}

function screenshotSelectedSources() {
  return Array.from(
    document.querySelectorAll(
      "#search-results .screenshot-source-select:checked",
    ),
    (element) => element.value,
  );
}

function screenshotAllSources() {
  return Array.from(
    document.querySelectorAll("#search-results .screenshot-source-select"),
    (element) => element.value,
  );
}

function screenshotUpdateBulkControls() {
  const sourceCount = screenshotAllSources().length;
  const selectedCount = screenshotSelectedSources().length;
  const addSelected = document.getElementById("screenshots-add-selected");
  const selectionToggle = document.getElementById(
    "screenshots-toggle-selection",
  );
  if (addSelected !== null) {
    addSelected.disabled = selectedCount === 0;
  }
  if (selectionToggle instanceof HTMLInputElement) {
    selectionToggle.disabled = sourceCount === 0;
    selectionToggle.checked = sourceCount > 0 && selectedCount === sourceCount;
    selectionToggle.indeterminate =
      selectedCount > 0 && selectedCount < sourceCount;
  }
}

function screenshotToggleSelection(checked) {
  const checkboxes = document.querySelectorAll(
    "#search-results .screenshot-source-select",
  );
  for (const checkbox of checkboxes) {
    checkbox.checked = checked;
  }
  screenshotUpdateBulkControls();
}

function screenshotRemoveSources(pks) {
  const rows = new Set();
  for (const pk of pks) {
    for (const element of document.querySelectorAll(
      "#search-results .add-string, #search-results .screenshot-source-select",
    )) {
      if (
        element.getAttribute("data-pk") === String(pk) ||
        element.getAttribute("value") === String(pk)
      ) {
        rows.add(element.closest("tr"));
      }
    }
  }
  for (const row of rows) {
    row?.remove();
  }
  screenshotUpdateBulkControls();
}

async function screenshotRefreshAssignedSources() {
  const list = document.getElementById("sources-listing");
  if (list?.dataset.href === undefined) {
    return;
  }
  const response = await fetch(list.dataset.href, {
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!response.ok) {
    throw new Error(response.statusText);
  }
  const table = list.querySelector("table");
  if (table !== null) {
    table.outerHTML = await response.text();
  }
}

function screenshotBindAddButtons() {
  for (const button of document.querySelectorAll(
    "#search-results .add-string",
  )) {
    button.addEventListener("click", screenshotAddString);
  }
}

async function screenshotAddSources(pks) {
  if (pks.length === 0) {
    return;
  }
  const form = document.getElementById("screenshot-add-form");
  if (form === null) {
    return;
  }
  const formData = new FormData(form);
  formData.delete("source");
  for (const pk of pks) {
    formData.append("source", pk);
  }

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: formData,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!response.ok) {
      throw new Error(response.statusText);
    }
    const data = await response.json();
    await screenshotRefreshAssignedSources();
    if (data.added > 0) {
      screenshotRemoveSources(pks);
    }
    if (data.invalid > 0) {
      addAlert(gettext("Some source strings could not be assigned."));
    }
  } catch (error) {
    addAlert(error instanceof Error ? error.message : error);
  }
}

function screenshotAddString(event) {
  event.preventDefault();
  const pk = this.getAttribute("data-pk");
  if (pk !== null) {
    screenshotAddSources([pk]);
  }
}

function screenshotResultError(severity, message) {
  const columnCount =
    document.querySelectorAll("#search-results thead th").length || 6;
  const body = document.querySelector(
    "#search-results tbody.unit-listing-body",
  );
  if (body === null) {
    return;
  }
  const row = document.createElement("tr");
  row.classList.add(severity);
  const cell = document.createElement("td");
  cell.colSpan = columnCount;
  cell.textContent = message;
  row.append(cell);
  body.replaceChildren(row);
}

function screenshotLoaded(data) {
  decreaseLoading("screenshots");
  const summary = document.getElementById("screenshots-search-summary");
  if (summary !== null) {
    summary.textContent = data.summary || "";
  }
  if (data.responseCode !== 200) {
    screenshotResultError("danger", gettext("Error loading search results!"));
  } else if (data.count === 0) {
    screenshotResultError(
      "warning",
      data.empty || gettext("No new matching source strings found."),
    );
  } else {
    const table = document.querySelector("#search-results table");
    if (table !== null) {
      table.outerHTML = data.results;
    }
    screenshotBindAddButtons();
  }
  screenshotUpdateBulkControls();
}

function getNumber(n) {
  const parsed = Number.parseFloat(n.replace(",", "."));
  if (!Number.isNaN(parsed) && Number.isFinite(parsed)) {
    return parsed;
  }
  return null;
}

function extractText(cell) {
  const value = cell.getAttribute("data-value");
  if (value !== null) {
    return value;
  }
  return cell.textContent;
}

function _compareValues(a, b) {
  if (a === b) {
    return 0;
  }
  if (a > b) {
    return 1;
  }
  return -1;
}

function compareCells(a, b) {
  if (typeof a === "number" && typeof b === "number") {
    return _compareValues(a, b);
  }
  if (a.indexOf("%") !== -1 && b.indexOf("%") !== -1) {
    return _compareValues(
      Number.parseFloat(a.replace(",", ".")),
      Number.parseFloat(b.replace(",", ".")),
    );
  }
  const parsedA = getNumber(a);
  const parsedB = getNumber(b);
  if (parsedA !== null && parsedB !== null) {
    return _compareValues(parsedA, parsedB);
  }
  if (typeof a === "string" && typeof b === "string") {
    return _compareValues(a.toLowerCase(), b.toLowerCase());
  }
  return _compareValues(a, b);
}

function loadTableSorting() {
  document.querySelectorAll("table.sort").forEach((table) => {
    const tbody = table.querySelector("tbody");
    const thead = table.querySelector("thead");
    let thIndex = 0;

    table.querySelectorAll("thead th").forEach((th) => {
      let inverse = 1;

      // handle colspan
      if (th.getAttribute("colspan")) {
        thIndex += Number.parseInt(th.getAttribute("colspan"), 10) - 1;
      }
      // skip empty cells and cells with icon (probably already processed)
      if (
        th.textContent !== "" &&
        !th.classList.contains("sort-init") &&
        !th.classList.contains("sort-skip")
      ) {
        // Store index copy
        const myIndex = thIndex;
        // Add icon, title and class
        th.classList.add("sort-init");
        if (!th.classList.contains("sort-cell")) {
          // Skip statically initialized parts (when server side ordering is supported)
          th.setAttribute("title", gettext("Sort this column"));
          th.classList.add("sort-cell");
          if (th.classList.contains("number")) {
            const icon = document.createElement("span");
            icon.classList.add("sort-icon");
            icon.textContent = " ";
            th.prepend(icon);
          } else {
            th.insertAdjacentHTML(
              "beforeend",
              '<span class="sort-icon"></span>',
            );
          }
        }

        // Click handler
        th.addEventListener("click", function () {
          const sorted = Array.from(tbody.querySelectorAll("tr")).sort(
            (a, b) => {
              let rowA = a;
              let rowB = b;
              const parentA = a.dataset.parent;
              const parentB = b.dataset.parent;
              if (parentA) {
                rowA = tbody.querySelector(`#${CSS.escape(parentA)}`) || rowA;
              }
              if (parentB) {
                rowB = tbody.querySelector(`#${CSS.escape(parentB)}`) || rowB;
              }
              return (
                inverse *
                compareCells(
                  extractText(rowA.querySelectorAll("td,th")[myIndex]),
                  extractText(rowB.querySelectorAll("td,th")[myIndex]),
                )
              );
            },
          );
          for (const row of sorted) {
            tbody.appendChild(row);
          }
          thead.querySelectorAll(".sort-icon").forEach((icon) => {
            icon.classList.remove("sort-down", "sort-up");
          });
          const icon = this.querySelector(".sort-icon");
          if (icon) {
            icon.classList.add(inverse === 1 ? "sort-down" : "sort-up");
          }

          inverse *= -1;
        });
      }
      // Increase index
      thIndex += 1;
    });
  });
}

/* Thin wrappers for django to avoid problems when i18n js can not be loaded */
function gettext(msgid) {
  if (typeof django !== "undefined") {
    return django.gettext(msgid);
  }
  return msgid;
}
function pgettext(context, msgid) {
  if (typeof django !== "undefined") {
    return django.pgettext(context, msgid);
  }
  return msgid;
}
function interpolate(fmt, obj, named) {
  if (typeof django !== "undefined") {
    return django.interpolate(fmt, obj, named);
  }
  return fmt.replace(/%s/g, () => String(obj.shift()));
}

function loadMatrix() {
  const loadingNext = document.getElementById("loading-next");
  const loader = document.getElementById("matrix-load");
  const offset = Number.parseInt(loader.dataset.offset, 10);

  if (
    document.getElementById("last-section") !== null ||
    loadingNext === null ||
    getComputedStyle(loadingNext).display !== "none"
  ) {
    return;
  }
  show(loadingNext);

  loader.dataset.offset = 20 + offset;

  fetch(`${loader.getAttribute("href")}&offset=${offset}`, {
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then((response) => response.text())
    .then((data) => {
      hide(loadingNext);
      document
        .querySelector(".matrix tbody")
        ?.insertAdjacentHTML("beforeend", data);
    });
}

function adjustColspan() {
  document.querySelectorAll("table.autocolspan").forEach((table) => {
    let numOfVisibleCols = Array.from(
      table.querySelectorAll("thead th"),
    ).filter((th) => th.getClientRects().length > 0).length;
    if (numOfVisibleCols === 0) {
      numOfVisibleCols = 3;
    }
    table.querySelectorAll("td.autocolspan").forEach((td) => {
      td.setAttribute("colspan", numOfVisibleCols - 1);
    });
  });
}

function quoteSearch(value) {
  if (value.indexOf(" ") === -1) {
    return value;
  }
  if (value.indexOf('"') === -1) {
    return `"${value}"`;
  }
  if (value.indexOf("'") === -1) {
    return `'${value}'`;
  }
  /* We should do some escaping here */
  return value;
}

// Auto-resize a textarea to fit its content.
// CSS `field-sizing: content` would be cleaner but Firefox doesn't implement it yet
function autosizeTextarea(el) {
  const resize = () => {
    // Reset to 0 so the textarea collapses past any `rows` attribute default
    el.style.height = "0px";
    el.style.height = `${el.scrollHeight}px`;
  };
  el.addEventListener("input", resize);
  resize();
}

function initHighlight(root) {
  if (typeof ResizeObserver === "undefined") {
    return;
  }
  root.querySelectorAll("textarea[name='q']").forEach((input) => {
    const parent = input.parentElement;
    if (parent.classList.contains("editor-wrap")) {
      return;
    }

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        if (!event.repeat) {
          event.target.form.requestSubmit();
        }
        event.preventDefault();
      }
    });

    /* Create wrapper element */
    const wrapper = document.createElement("div");
    wrapper.setAttribute("class", "editor-wrap");

    /* Inject wrapper */
    parent.replaceChild(wrapper, input);

    /* Create highlighter */
    const highlight = document.createElement("div");
    highlight.setAttribute("class", "highlighted-output");
    highlight.setAttribute("role", "status");
    wrapper.appendChild(highlight);

    /* Add input to wrapper */
    wrapper.appendChild(input);

    const syncContent = () => {
      highlight.innerHTML = Prism.highlight(
        input.value,
        Prism.languages.weblatesearch,
        "weblatesearch",
      );
    };
    syncContent();
    input.addEventListener("input", syncContent);

    /* Handle scrolling */
    input.addEventListener("scroll", (_event) => {
      highlight.scrollTop = input.scrollTop;
      highlight.scrollLeft = input.scrollLeft;
    });

    /* Handle resizing */
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.target === input) {
          // match the height and width of the output area to the input area
          highlight.style.height = `${input.offsetHeight}px`;
          highlight.style.width = `${input.offsetWidth}px`;
        }
      }
    });

    resizeObserver.observe(input);
  });
  root.querySelectorAll(".highlight-editor").forEach((editor) => {
    const parent = editor.parentElement;
    const hasFocus = editor === document.activeElement;

    if (parent.classList.contains("editor-wrap")) {
      return;
    }

    const mode = editor.getAttribute("data-mode");

    /* Create wrapper element */
    const wrapper = document.createElement("div");
    wrapper.setAttribute("class", "editor-wrap");

    /* Inject wrapper */
    parent.replaceChild(wrapper, editor);

    /* Create highlighter */
    const highlight = document.createElement("div");
    highlight.setAttribute("class", "highlighted-output");
    if (editor.readOnly) {
      highlight.classList.add("readonly");
    }
    if (editor.disabled) {
      highlight.classList.add("disabled");
    }
    highlight.setAttribute("role", "status");
    if (editor.hasAttribute("dir")) {
      highlight.setAttribute("dir", editor.getAttribute("dir"));
    }
    if (editor.hasAttribute("lang")) {
      highlight.setAttribute("lang", editor.getAttribute("lang"));
    }
    wrapper.appendChild(highlight);

    /* Add editor to wrapper */
    wrapper.appendChild(editor);
    if (hasFocus) {
      editor.focus();
    }

    /* Content synchronisation and highlighting */
    let languageMode = Prism.languages[mode];
    if (editor.classList.contains("translation-editor")) {
      const placeables = editor.getAttribute("data-placeables");
      /* This should match WHITESPACE_REGEX in weblate/trans/templatetags/translations.py */
      const whitespaceRegex = new RegExp(
        [
          "  +|(^) +| +(?=$)| +\n|\n +|\t|",
          "\u00AD|\u1680|\u2000|\u2001|",
          "\u2002|\u2003|\u2004|\u2005|",
          "\u2006|\u2007|\u2008|\u2009|",
          "\u200A|\u202F|\u205F|\u3000",
        ].join(""),
      );
      const newlineRegex = /\n/;
      const nonBreakingSpaceRegex = /\u00A0/;
      const extension = {
        hlspace: {
          pattern: whitespaceRegex,
          lookbehind: true,
        },
        newline: {
          pattern: newlineRegex,
        },
        nbsp: {
          pattern: nonBreakingSpaceRegex,
        },
      };
      if (placeables) {
        extension.placeable = new RegExp(placeables);
      }
      /*
       * We can not use Prism.extend here as we want whitespace highlighting
       * to apply first. The code is borrowed from Prism.util.clone.
       */
      for (const key in languageMode) {
        // biome-ignore lint/suspicious/noPrototypeBuiltins: Firefox < 92 compatibility, Object.hasOwn(languageMode, key) should be used instead
        if (languageMode.hasOwnProperty(key)) {
          extension[key] = Prism.util.clone(languageMode[key]);
        }
      }
      languageMode = extension;
    }
    const syncContent = () => {
      highlight.innerHTML = Prism.highlight(editor.value, languageMode, mode);
    };
    syncContent();
    editor.addEventListener("input", syncContent);

    /* Handle scrolling */
    editor.addEventListener("scroll", (_event) => {
      highlight.scrollTop = editor.scrollTop;
      highlight.scrollLeft = editor.scrollLeft;
    });

    /* Handle resizing */
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.target === editor) {
          // match the height and width of the output area to the input area
          highlight.style.height = `${editor.offsetHeight}px`;
          highlight.style.width = `${editor.offsetWidth}px`;
        }
      }
    });

    resizeObserver.observe(editor);
    autosizeTextarea(editor);
  });
}

onReady(() => {
  adjustColspan();
  window.addEventListener("resize", adjustColspan);
  document.addEventListener("shown.bs.tab", adjustColspan);

  /* Color theme management */
  const theme = document.querySelector("body").getAttribute("data-theme");
  if (
    (theme === "auto") &
    (window.matchMedia("(prefers-color-scheme: dark)").matches === true)
  ) {
    document.documentElement.setAttribute("data-bs-theme", "dark");
  }

  /* AJAX loading of tabs/pills */
  const loadTabContent = async (target, content) => {
    try {
      const response = await fetch(target.dataset.href, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const text = await response.text();
      if (!response.ok) {
        throw new Error(`${response.statusText} (${response.status})`);
      }
      content.innerHTML = text;
    } catch (error) {
      const msg = gettext("Error while loading page:");
      const alert = document.createElement("div");
      alert.className = "alert alert-danger";
      alert.setAttribute("role", "alert");
      alert.textContent = `${msg} ${error.message}`;
      content.replaceChildren(alert);
    }
    target.dataset.loaded = "1";
    loadTableSorting();
  };
  document.addEventListener("show.bs.tab", (e) => {
    const target = e.target;
    if (
      !target.matches(
        '[data-bs-toggle="tab"][data-href], [data-bs-toggle="pill"][data-href]',
      )
    ) {
      return;
    }
    if (target.dataset.loaded) {
      return;
    }
    let content = document.querySelector(target.getAttribute("data-bs-target"));
    if (content === null) {
      return;
    }
    const cardBody = content.querySelector(".card-body");
    if (cardBody !== null) {
      content = cardBody;
    }
    loadTabContent(target, content);
  });

  if (document.getElementById("form-activetab") !== null) {
    document.addEventListener("show.bs.tab", (e) => {
      if (e.target.matches('[data-toggle="tab"]')) {
        document
          .getElementById("form-activetab")
          .setAttribute("value", e.target.getAttribute("href"));
      }
    });
  }

  /* Form automatic submission */
  document.querySelectorAll("form.autosubmit select").forEach((select) => {
    select.addEventListener("change", () => {
      document.querySelectorAll("form.autosubmit").forEach((form) => {
        form.requestSubmit();
      });
    });
  });

  let activeTab;

  /* Load correct tab */
  if (location.hash !== "") {
    /* From URL hash */
    const separator = location.hash.indexOf("__");
    if (separator !== -1) {
      activeTab = document.querySelector(
        `.nav [data-bs-toggle=tab][data-bs-target="${location.hash.substr(0, separator)}"]`,
      );
      if (activeTab !== null) {
        bootstrap.Tab.getOrCreateInstance(activeTab).show();
        activeTab.closest(".dropdown-menu")?.classList.remove("show");
      }
    }
    activeTab = document.querySelector(
      `.nav [data-bs-toggle=tab][data-bs-target="${location.hash}"]`,
    );
    if (activeTab !== null) {
      bootstrap.Tab.getOrCreateInstance(activeTab).show();
      activeTab.closest(".dropdown-menu")?.classList.remove("show");
      window.scrollTo(0, 0);
    } else {
      const anchor = document.getElementById(location.hash.substr(1));
      if (anchor !== null) {
        anchor.scrollIntoView();
      }
    }
  } else if (
    document.querySelector(".translation-tabs") !== null &&
    localStorage.getItem("translate-tab")
  ) {
    /* From local storage */
    activeTab = document.querySelector(
      `[data-bs-toggle=tab][data-bs-target="${localStorage.getItem("translate-tab")}"]`,
    );
    if (activeTab !== null) {
      bootstrap.Tab.getOrCreateInstance(activeTab).show();
    }
  }

  /* Add a hash to the URL when the user clicks on a tab */
  document.querySelectorAll('a[data-bs-toggle="tab"]').forEach((tab) => {
    tab.addEventListener("shown.bs.tab", function (_e) {
      history.pushState(null, null, this.getAttribute("data-bs-target"));
      /* Remove focus on rows */
      document.querySelectorAll(".selectable-row").forEach((row) => {
        row.classList.remove("active");
      });
    });
  });

  /* Navigate to a tab when the history changes */
  window.addEventListener("popstate", (_e) => {
    let tab = null;
    if (location.hash !== "") {
      tab = document.querySelector(
        `[data-bs-toggle=tab][data-bs-target="${location.hash}"]`,
      );
    }
    if (tab !== null) {
      bootstrap.Tab.getOrCreateInstance(tab).show();
    } else {
      const firstNav = document.querySelector(".nav-tabs a");
      if (firstNav !== null) {
        bootstrap.Tab.getOrCreateInstance(firstNav).show();
      }
    }
  });

  /* Activate tab with error */
  const firstFormError = document.querySelector("div.has-error");
  if (firstFormError !== null) {
    const tab = firstFormError.closest("div.tab-pane");
    if (tab !== null) {
      const trigger = document.querySelector(
        `[data-bs-toggle=tab][data-bs-target="#${tab.id}"]`,
      );
      if (trigger !== null) {
        bootstrap.Tab.getOrCreateInstance(trigger).show();
      }
    }
  }

  /* Announcement discard */
  document.querySelectorAll(".alert").forEach((alertElement) => {
    alertElement.addEventListener("close.bs.alert", function () {
      const form = document.getElementById("link-post");
      const action = this.getAttribute("data-action");

      if (action) {
        const csrfInput = form?.querySelector("input");
        fetch(action, {
          method: "POST",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: new URLSearchParams({
            csrfmiddlewaretoken: csrfInput ? csrfInput.value : "",
            id: this.getAttribute("data-id"),
          }),
        })
          .then((response) => {
            if (!response.ok) {
              addAlert(response.statusText);
            }
          })
          .catch((error) => {
            addAlert(error instanceof Error ? error.message : error);
          });
      }
    });
  });

  /* Code samples (on widgets page) */
  document.querySelectorAll(".code-example").forEach((element) => {
    element.addEventListener("focus", function () {
      this.select();
    });
  });

  /* Table sorting */
  loadTableSorting();

  /* Matrix mode handling */
  if (document.querySelector(".matrix") !== null) {
    loadMatrix();
    window.addEventListener("scroll", () => {
      if (
        window.scrollY >=
        document.documentElement.scrollHeight - 2 * window.innerHeight
      ) {
        loadMatrix();
      }
    });
  }

  /* Social auth disconnect */
  document.querySelectorAll("a.disconnect").forEach((link) => {
    link.addEventListener("click", function (e) {
      e.preventDefault();
      const form = document.getElementById("disconnect-form");
      if (form !== null) {
        form.setAttribute("action", this.getAttribute("href"));
        form.submit();
      }
    });
  });

  document.querySelectorAll(".dropdown-menu form").forEach((form) => {
    form.addEventListener("click", (e) => {
      e.stopPropagation();
    });
  });

  document.addEventListener("click", (e) => {
    const link = e.target.closest(".link-post");
    if (link === null) {
      return;
    }
    e.preventDefault();
    const form = document.getElementById("link-post");
    form.setAttribute("action", link.getAttribute("data-href"));
    const params = link.dataset.params ? JSON.parse(link.dataset.params) : {};
    for (const [name, value] of Object.entries(params)) {
      const elm = document.createElement("input");
      elm.setAttribute("type", "hidden");
      elm.setAttribute("name", name);
      elm.setAttribute("value", value);
      form.appendChild(elm);
    }
    form.submit();
  });
  document.querySelectorAll(".link-auto").forEach((link) => {
    link.click();
  });
  document.addEventListener("click", (e) => {
    const thumbnail = e.target.closest(".thumbnail");
    if (thumbnail === null) {
      return;
    }
    e.preventDefault();
    const preview = document.getElementById("imagepreview");
    if (preview !== null) {
      preview.setAttribute("src", thumbnail.getAttribute("href"));
    }
    const modalTitle = document.getElementById("screenshotModal");
    if (modalTitle !== null) {
      modalTitle.textContent = thumbnail.getAttribute("title");
    }

    const detailsLink = document.getElementById("modalDetailsLink");
    const detailsUrl = thumbnail.getAttribute("data-details-url");
    if (detailsLink !== null) {
      if (detailsUrl) {
        detailsLink.setAttribute("href", detailsUrl);
        show(detailsLink);
        if (thumbnail.getAttribute("data-can-edit")) {
          detailsLink.textContent = detailsLink.getAttribute("data-edit-text");
        }
      } else {
        // No details for generic images (static pages) — hide the button
        hide(detailsLink);
      }
    }

    const modal = document.getElementById("imagemodal");
    if (modal !== null) {
      bootstrap.Modal.getOrCreateInstance(modal).show();
    }
  });
  /* Screenshot management */
  async function screenshotLoadResults(url, form) {
    screenshotStart();
    try {
      const response = await fetch(url, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok) {
        screenshotFailure();
        return;
      }
      screenshotLoaded(await response.json());
    } catch (_error) {
      screenshotFailure();
    }
  }
  for (const button of document.querySelectorAll("#screenshots-auto")) {
    button.addEventListener("click", function (event) {
      event.preventDefault();
      const url = this.getAttribute("data-href");
      const form = this.closest("form");
      if (url === null || form === null) {
        screenshotFailure();
        return;
      }
      void screenshotLoadResults(url, form);
    });
  }
  document
    .getElementById("screenshots-search-form")
    ?.addEventListener("submit", function (event) {
      event.preventDefault();
      const url = this.getAttribute("data-href");
      if (url === null) {
        screenshotFailure();
        return;
      }
      void screenshotLoadResults(url, this);
    });
  document.addEventListener("change", (event) => {
    if (
      event.target instanceof Element &&
      event.target.matches("#search-results .screenshot-source-select")
    ) {
      screenshotUpdateBulkControls();
    }
    if (
      event.target instanceof HTMLInputElement &&
      event.target.id === "screenshots-toggle-selection"
    ) {
      screenshotToggleSelection(event.target.checked);
    }
  });
  document
    .getElementById("screenshots-add-selected")
    ?.addEventListener("click", (event) => {
      event.preventDefault();
      screenshotAddSources(screenshotSelectedSources());
    });
  /* Avoid double submission of non AJAX forms */
  let submittedForms = new WeakSet();
  document.querySelectorAll("form:not(.double-submission)").forEach((form) => {
    form.addEventListener("submit", (e) => {
      if (submittedForms.has(form)) {
        // Previously submitted - don't submit again
        e.preventDefault();
      } else {
        // Mark it so that the next submit can be ignored
        submittedForms.add(form);
      }
    });
  });
  /* Reset submitted flag when leaving the page, so that it is not set when going back in history */
  window.addEventListener("pagehide", () => {
    submittedForms = new WeakSet();
  });

  /* Client side form persistence */
  const persistForms = document.querySelectorAll("[data-persist]");
  if (persistForms.length > 0 && window.localStorage) {
    /* Load from local storage */
    persistForms.forEach((form) => {
      const storedRaw = window.localStorage[form.dataset.persist];
      if (storedRaw) {
        const storedValue = JSON.parse(storedRaw);
        for (const [key, value] of Object.entries(storedValue)) {
          if (!key) {
            continue;
          }
          const selector = `[name="${CSS.escape(key)}"]`;
          form.querySelectorAll(selector).forEach((target) => {
            if (target.type === "checkbox") {
              target.checked = value;
            } else {
              target.value = value;
            }
          });
        }
      }
    });
    /* Save on submit */
    persistForms.forEach((form) => {
      form.addEventListener("submit", (_e) => {
        const data = {};
        form.querySelectorAll("input[type=checkbox]").forEach((checkbox) => {
          if (checkbox.name) {
            data[checkbox.name] = checkbox.checked;
          }
        });
        form.querySelectorAll("select").forEach((select) => {
          if (select.name) {
            data[select.name] = select.value;
          }
        });
        window.localStorage[form.dataset.persist] = JSON.stringify(data);
      });
    });
  }

  /* Focus first input in modal */
  document.addEventListener("shown.bs.modal", (event) => {
    const button = event.relatedTarget; // Button that triggered the modal
    const target = button?.dataset.focus;
    if (target) {
      /* Modal context focusing */
      document.querySelector(target)?.focus();
    } else {
      for (const input of event.target.querySelectorAll("input")) {
        if (!input.disabled && input.offsetParent !== null) {
          input.focus();
          break;
        }
      }
    }
  });

  /* Copy to clipboard */
  document.addEventListener("click", (e) => {
    const element = e.target.closest("[data-clipboard-value]");
    if (element === null) {
      return;
    }
    e.preventDefault();
    try {
      navigator.clipboard
        .writeText(element.getAttribute("data-clipboard-value"))
        .then(
          () => {
            const text =
              element.getAttribute("data-clipboard-message") ||
              gettext("Text copied to clipboard.");
            addAlert(text, "info");
          },
          () => {
            addAlert(gettext("Please press Ctrl+C to copy."), "danger");
          },
        );
    } catch (error) {
      addAlert(gettext("Error copying to clipboard."), "danger");
      console.log(error);
    }
  });

  /* Auto translate source select */
  const autoSourceInputs = document.querySelectorAll(
    'input[name="auto_source"]',
  );
  if (autoSourceInputs.length > 0) {
    const updateAutoSource = () => {
      const checked = document.querySelector(
        'input[name="auto_source"]:checked',
      );
      if (checked !== null && checked.value === "others") {
        show(document.getElementById("auto_source_others"));
        hide(document.getElementById("auto_source_mt"));
      } else {
        hide(document.getElementById("auto_source_others"));
        show(document.getElementById("auto_source_mt"));
      }
    };
    autoSourceInputs.forEach((input) => {
      input.addEventListener("change", updateAutoSource);
    });
    updateAutoSource();
  }

  const findElements = (root, selector) => {
    const elements = [];
    if (root instanceof Element && root.matches(selector)) {
      elements.push(root);
    }
    elements.push(...root.querySelectorAll(selector));
    return elements;
  };

  const initializeMultipleSelects = (root = document) => {
    findElements(root, "select[multiple]").forEach((el) => {
      if (el.tomselect) {
        return;
      }
      const options = {
        plugins: ["remove_button", "checkbox_options"],
        placeholder: el.dataset.placeholder || gettext("Search…"),
        hidePlaceholder: el.dataset.hidePlaceholder === "true",
        persist: false,
        create: false,
        allowEmptyOption: true,
      };
      new TomSelect(el, options);
    });
  };

  const initializeProjectMembershipControls = (root = document) => {
    findElements(root, ".project-membership-team-toggle").forEach((el) => {
      if (el.dataset.membershipToggleInitialized === "true") {
        return;
      }
      el.dataset.membershipToggleInitialized = "true";
      const limitField = document.getElementById(el.dataset.limitTarget);
      const updateLimitField = () => {
        if (!limitField) {
          return;
        }
        limitField.disabled = !el.checked;
        if (!limitField.tomselect) {
          return;
        }
        if (el.checked) {
          limitField.tomselect.enable();
        } else {
          limitField.tomselect.disable();
        }
      };
      el.addEventListener("change", updateLimitField);
      updateLimitField();
    });
  };

  /* Override all multiple selects */
  initializeMultipleSelects();

  /* Searchable single selects */
  document.querySelectorAll("select.searchable-select").forEach((el) => {
    if (el.tomselect) {
      return;
    }
    new TomSelect(el, {
      placeholder: gettext("Search…"),
      hidePlaceholder: true,
      persist: false,
      create: false,
      allowEmptyOption: true,
      maxOptions: null,
    });
  });

  const getControlValue = (control) => {
    if (control.tomselect) {
      return control.tomselect.getValue();
    }
    return control.value;
  };
  const setControlValue = (control, value) => {
    if (control.tomselect) {
      control.tomselect.setValue(value, true);
    } else {
      control.value = value;
    }
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const setControlDisabled = (control, disabled) => {
    control.disabled = disabled;
    if (!control.tomselect) {
      return;
    }
    if (disabled) {
      control.tomselect.disable();
    } else {
      control.tomselect.enable();
    }
  };

  document.querySelectorAll(".site-default-field-button").forEach((button) => {
    const container = button.closest(".mb-3");
    const control = container?.querySelector("[data-site-default-value]");
    if (!control) {
      return;
    }
    button.addEventListener("click", () => {
      const inheritedSetting = button.closest("[data-inherited-setting]");
      const inheritCheckbox = inheritedSetting?.querySelector(
        ".inherited-setting-toggle input[type=checkbox]",
      );
      if (inheritCheckbox?.checked) {
        inheritCheckbox.checked = false;
        inheritCheckbox.dispatchEvent(new Event("change", { bubbles: true }));
      }
      setControlValue(control, control.dataset.siteDefaultValue || "");
    });
  });

  document.querySelectorAll("[data-inherited-setting]").forEach((el) => {
    const checkbox = el.querySelector(
      ".inherited-setting-toggle input[type=checkbox]",
    );
    const controls = Array.from(
      el.querySelectorAll(
        ".inherited-setting-field input, .inherited-setting-field select, .inherited-setting-field textarea",
      ),
    ).filter(
      (control) =>
        !(control instanceof HTMLInputElement && control.type === "hidden"),
    );
    if (!checkbox) {
      return;
    }

    const updateInheritedSetting = (syncValue) => {
      const disabled = checkbox.checked;
      el.classList.toggle("is-inherited", disabled);
      controls.forEach((control) => {
        if (syncValue) {
          if (disabled) {
            control.dataset.overrideValue = getControlValue(control);
            setControlValue(control, control.dataset.inheritedValue || "");
          } else {
            setControlDisabled(control, false);
            setControlValue(control, control.dataset.overrideValue || "");
          }
        }
        setControlDisabled(control, disabled);
      });
    };
    checkbox.addEventListener("change", () => updateInheritedSetting(true));
    updateInheritedSetting(false);
  });

  initializeProjectMembershipControls();

  const projectUserGroupsModal = document.getElementById(
    "project-user-groups-modal",
  );
  if (projectUserGroupsModal) {
    const modalBody = projectUserGroupsModal.querySelector(".modal-body");
    const modalTitle = projectUserGroupsModal.querySelector(".modal-title");
    const submitButton = projectUserGroupsModal.querySelector(
      "input[type='submit']",
    );
    const formCache = new Map();

    const renderProjectUserGroupsForm = (url, html) => {
      if (projectUserGroupsModal.dataset.activeUrl !== url) {
        return;
      }
      modalBody.innerHTML = html;
      initializeMultipleSelects(modalBody);
      initializeProjectMembershipControls(modalBody);
      submitButton.disabled = false;
    };

    projectUserGroupsModal.addEventListener("show.bs.modal", (event) => {
      const trigger = event.relatedTarget;
      const url = trigger?.dataset.href;
      if (!url) {
        return;
      }
      projectUserGroupsModal.dataset.activeUrl = url;
      modalTitle.textContent = trigger.dataset.modalTitle || "";
      submitButton.disabled = true;
      modalBody.textContent =
        modalBody.dataset.loadingText || gettext("Loading…");

      if (formCache.has(url)) {
        renderProjectUserGroupsForm(url, formCache.get(url));
        return;
      }

      fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`${response.statusText} (${response.status})`);
          }
          return response.text();
        })
        .then((html) => {
          formCache.set(url, html);
          renderProjectUserGroupsForm(url, html);
        })
        .catch((error) => {
          if (projectUserGroupsModal.dataset.activeUrl !== url) {
            return;
          }
          const alert = document.createElement("div");
          alert.className = "alert alert-danger";
          alert.role = "alert";
          const errorText =
            modalBody.dataset.errorText || gettext("Error while loading form:");
          alert.textContent = `${errorText} ${error.message}`;
          modalBody.textContent = "";
          modalBody.append(alert);
        });
    });

    projectUserGroupsModal.addEventListener("hidden.bs.modal", () => {
      delete projectUserGroupsModal.dataset.activeUrl;
    });
  }

  /* Slugify name */
  slugify.extend({ ".": "-" });
  document.querySelectorAll('input[name="slug"]').forEach((slug) => {
    const form = slug.closest("form");
    form.querySelectorAll('input[name="name"]').forEach((nameInput) => {
      for (const eventName of [
        "change",
        "keypress",
        "keydown",
        "keyup",
        "paste",
      ]) {
        nameInput.addEventListener(eventName, () => {
          slug.value = slugify(nameInput.value, {
            remove: /[^\w\s-]+/g,
          }).toLowerCase();
        });
      }
    });
  });

  /* Component update progress */
  document.querySelectorAll("[data-progress-url]").forEach((progress) => {
    const pre = progress.querySelector("pre");
    const bar = progress.querySelector(".progress-bar");
    const url = progress.dataset.progressUrl;
    const linkPost = document.getElementById("link-post");

    if (pre !== null) {
      pre.scrollTop = pre.scrollHeight;
    }

    const progressCompleted = () => {
      if (bar !== null) {
        bar.style.width = "100%";
      }
      if (document.getElementById("progress-redirect")?.checked) {
        window.location = document
          .getElementById("progress-return")
          .getAttribute("href");
      }
    };

    const progressInterval = setInterval(async () => {
      try {
        const response = await fetch(url, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!response.ok) {
          if (response.status === 404) {
            clearInterval(progressInterval);
            progressCompleted();
          }
          return;
        }
        const data = await response.json();
        if (bar !== null) {
          bar.style.width = `${data.progress}%`;
        }
        if (pre !== null) {
          pre.textContent = data.log;
          pre.scrollTop = pre.scrollHeight;
        }
        if (data.completed) {
          clearInterval(progressInterval);
          progressCompleted();
        }
      } catch (_error) {
        /* Ignore transient network errors and retry on the next tick */
      }
    }, 1000);

    document
      .getElementById("terminate-task-button")
      ?.addEventListener("click", (e) => {
        fetch(url, {
          method: "DELETE",
          headers: {
            Accept: "application/json",
            "X-CSRFToken": linkPost.querySelector("input").value,
          },
        }).then((_data) => {
          window.location = document
            .getElementById("progress-return")
            .getAttribute("href");
        });
        e.preventDefault();
      });
  });

  /* Generic messages progress */
  const progressBars = document.querySelectorAll(".progress-bar");
  document.querySelectorAll("[data-task]").forEach((message) => {
    const bar = message.querySelector(".progress-bar");
    const messageText = message.querySelector(".task-message");
    const warnings = message.querySelector(".task-warnings");
    if (bar !== null) {
      bar.setAttribute("data-completed", "0");
    }

    const progressCompleted = () => {
      if (bar !== null) {
        bar.setAttribute("data-completed", "1");
      }
      clearInterval(taskInterval);
      if (
        document.getElementById("progress-redirect")?.checked &&
        Array.from(progressBars.values()).every((element) => {
          return element.getAttribute("data-completed") === "1";
        })
      ) {
        window.location = document
          .getElementById("progress-return")
          .getAttribute("href");
      }
    };

    const taskInterval = setInterval(
      async () => {
        try {
          const response = await fetch(message.dataset.task, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
          });
          if (!response.ok) {
            if (response.status === 404) {
              progressCompleted();
            }
            return;
          }
          const data = await response.json();
          if (bar !== null) {
            bar.style.width = `${data.progress}%`;
          }
          if (data.completed) {
            const result = data.result ?? {};
            progressCompleted();
            if (result.message) {
              if (messageText !== null) {
                messageText.textContent = result.message;
              }
            } else if (typeof result === "string" && result) {
              if (messageText !== null) {
                messageText.textContent = result;
              }
            }
            if (result.url) {
              window.location = result.url;
            }
            if (result.warnings?.length && warnings !== null) {
              warnings.replaceChildren();
              result.warnings.forEach((warning) => {
                const div = document.createElement("div");
                div.className = "text-warning mt-2";
                div.textContent = warning;
                warnings.appendChild(div);
              });
            }
          }
        } catch (_error) {
          /* Ignore transient network errors and retry on the next tick */
        }
      },
      1000 * Math.max(progressBars.length / 5, 1),
    );
  });

  /* Disable invalid file format choices */
  document.querySelectorAll(".invalid-format").forEach((element) => {
    element.parentElement.querySelectorAll("input").forEach((input) => {
      input.setAttribute("disabled", "1");
    });
  });

  // Show the correct toggle button
  if (document.querySelector(".sort-field") !== null) {
    const sortLabel = document.querySelector(
      "#query-sort-dropdown span.search-label",
    );
    const sortName = sortLabel !== null ? sortLabel.textContent : "";
    const sortLink = Array.from(
      document.querySelectorAll(".sort-field li a"),
    ).find((link) => link.textContent === sortName);
    const sortDropdownValue = sortLink?.dataset.sort;
    const sortByElement = document.getElementById("id_sort_by");
    const sortValue = sortByElement !== null ? sortByElement.value : "";
    if (sortDropdownValue) {
      if (
        sortValue.replace("-", "") === sortDropdownValue.replace("-", "") &&
        sortValue !== sortDropdownValue
      ) {
        document.querySelectorAll("span.search-icon").forEach(toggleDisplay);
      }
    }
  }

  function updateSearchSortBy() {
    const sortByElement = document.getElementById("id_sort_by");
    const sortValue = sortByElement !== null ? sortByElement.value : "";
    const link = Array.from(document.querySelectorAll(".sort-field li a")).find(
      (element) => element.dataset.sort === sortValue,
    );
    const label = link ? link.textContent : "";
    if (label !== "") {
      const sortLabel = document.querySelector(
        "#query-sort-dropdown span.search-label",
      );
      if (sortLabel !== null) {
        sortLabel.textContent = gettext(label);
      }
    }
  }
  const sortByLabelObserver = new MutationObserver(updateSearchSortBy);
  const sortByElement = document.getElementById("id_sort_by");
  if (sortByElement !== null) {
    sortByLabelObserver.observe(sortByElement, { attributes: true });
  }

  /* Branch loading */
  document
    .querySelectorAll(".branch-loader select[name=component]")
    .forEach((select) => {
      select.addEventListener("change", () => {
        const form = select.closest("form");
        const branches = JSON.parse(form.dataset.branches);
        const branchSelect = form.querySelector("select[name=branch]");
        branchSelect.replaceChildren();
        for (const value of branches[select.value] || []) {
          const option = document.createElement("option");
          option.setAttribute("value", value);
          option.textContent = value;
          branchSelect.appendChild(option);
        }
      });
    });

  /* Click to edit position inline. Disable when clicked outside or pressed ESC */
  const positionInputs = document.querySelectorAll(".position-input");
  const positionInputEditables = document.querySelectorAll(
    ".position-input-editable",
  );
  const positionInputEditableInput = document.getElementById(
    "position-input-editable-input",
  );
  const clickedOutsideEditableInput = (event) => {
    // Check if clicked outside of the input and the editable input
    if (
      ![...positionInputs].includes(event.target) &&
      event.target.id !== "position-input-editable-input"
    ) {
      positionInputs.forEach(show);
      positionInputEditableInput?.setAttribute("type", "hidden");
      positionInputEditables.forEach(hide);
      document.removeEventListener("click", clickedOutsideEditableInput);
      document.removeEventListener("keyup", pressedEscape);
    }
  };
  const pressedEscape = (event) => {
    if (event.key === "Escape" && event.target !== positionInputs[0]) {
      positionInputs.forEach(show);
      positionInputEditableInput?.setAttribute("type", "hidden");
      positionInputEditables.forEach(hide);
      document.removeEventListener("click", clickedOutsideEditableInput);
      document.removeEventListener("keyup", pressedEscape);
    }
  };
  positionInputs.forEach((positionInput) => {
    positionInput.addEventListener("click", function (event) {
      event.preventDefault();
      const form = this.closest("form");
      positionInputs.forEach(hide);
      form.querySelectorAll("input[name=offset]").forEach((input) => {
        input.disabled = false;
      });
      positionInputEditables.forEach(show);
      positionInputEditableInput?.setAttribute("type", "number");
      if (positionInputs.length > 1) {
        const input = event.target.parentElement?.querySelector(
          "#position-input-editable-input",
        );
        if (input !== null && input !== undefined) {
          input.focus();
          input.select();
        }
      } else if (positionInputEditableInput !== null) {
        positionInputEditableInput.focus();
        positionInputEditableInput.select();
      }
      document.addEventListener("click", clickedOutsideEditableInput);
      document.addEventListener("keyup", pressedEscape);
    });
  });

  /* Advanced search */
  document.querySelectorAll(".search-group li a").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const group = link.closest(".search-group");
      const button = group.querySelector("button.search-field");

      if (button !== null) {
        button.setAttribute("data-field", link.dataset.field ?? "");
      }

      const title = link.querySelector("span.title");
      const text = title !== null ? title.textContent : link.textContent;
      const labelAuto = group.querySelector("span.search-label-auto");
      if (labelAuto !== null) {
        labelAuto.textContent = text;
      }

      if (group.classList.contains("sort-field")) {
        const sortByInput = group.querySelector("input[name=sort_by]");
        if (sortByInput !== null) {
          sortByInput.value = link.dataset.sort ?? "";
        }
        if (link.closest(".result-page-form") !== null) {
          link.closest("form").submit();
        }
      }

      if (group.classList.contains("query-field")) {
        if (
          document.querySelector(".search-toolbar") === null &&
          link.closest(".result-page-form") !== null
        ) {
          const textarea = group.querySelector("textarea[name=q]");
          textarea.value = link.dataset.field ?? "";
          textarea.dispatchEvent(new Event("change", { bubbles: true }));
          const form = link.closest("form");
          form.querySelectorAll("input[name=offset]").forEach((input) => {
            input.disabled = true;
          });
          form.submit();
        } else {
          insertAtCaret(
            group.querySelector("textarea[name=q]"),
            ` ${link.dataset.field} `,
          );
        }
      }
      const dropdownToggle = link
        .closest(".dropdown, .btn-group")
        ?.querySelector('[data-bs-toggle="dropdown"]');
      if (dropdownToggle) {
        bootstrap.Dropdown.getOrCreateInstance(dropdownToggle).hide();
      }
    });
  });
  document.querySelectorAll(".query-sort-toggle").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const input = toggle
        .closest(".search-group")
        .querySelector("input[name=sort_by]");
      const sortParams = input.value.split(",");
      sortParams.forEach((param, index) => {
        if (param.indexOf("-") !== -1) {
          sortParams[index] = param.replace("-", "");
        } else {
          sortParams[index] = `-${param}`;
        }
      });
      input.value = sortParams.join(",");
      // Toggle active class on icons
      toggle.querySelectorAll(".search-icon").forEach((icon) => {
        icon.classList.toggle("active");
      });
      // Ensure only one icon is active at a time
      const asc = toggle.querySelector(".search-icon.asc");
      const desc = toggle.querySelector(".search-icon.desc");
      if (asc !== null) {
        asc.classList.toggle("active", !desc?.classList.contains("active"));
      }
      if (desc !== null) {
        desc.classList.toggle("active", !asc?.classList.contains("active"));
      }
      if (toggle.closest(".result-page-form") !== null) {
        toggle.closest("form").submit();
      }
    });
  });
  document.querySelectorAll(".search-group input").forEach((input) => {
    if (
      [
        "id_q",
        "id_position",
        "id_term",
        "position-input-editable-input",
      ].includes(input.id)
    ) {
      return;
    }
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        input.closest(".input-group")?.querySelector(".search-add")?.click();
        event.preventDefault();
      }
    });
  });
  const idQInput = document.getElementById("id_q");
  if (idQInput !== null) {
    idQInput.addEventListener("input", () => {
      idQInput
        .closest("form")
        .querySelectorAll("input[name=offset]")
        .forEach((input) => {
          input.disabled = true;
        });
    });
  }
  document.querySelectorAll(".search-add").forEach((searchAdd) => {
    searchAdd.addEventListener("click", () => {
      const group = searchAdd.closest(".search-group");
      const button = group.querySelector("button.search-field");
      const input = group.querySelector("input");
      const idQ = document.getElementById("id_q");

      if (input === null) {
        insertAtCaret(idQ, ` ${button.getAttribute("data-field")} `);
      } else if (input.value !== "") {
        let prefix = "";
        const exact = group.querySelector("#is-exact input[type=checkbox]");
        if (exact?.checked) {
          prefix = "=";
        }
        insertAtCaret(
          idQ,
          ` ${button.getAttribute("data-field")}${prefix}${quoteSearch(input.value)} `,
        );
      }
    });
  });
  document.querySelectorAll(".search-insert").forEach((searchInsert) => {
    searchInsert.addEventListener("click", () => {
      const code = searchInsert.closest("tr").querySelector("code");
      insertAtCaret(
        document.getElementById("id_q"),
        ` ${code !== null ? code.textContent : ""} `,
      );
    });
  });

  /* Clickable rows */
  document.querySelectorAll("tr[data-href]").forEach((row) => {
    row.addEventListener("click", () => {
      window.location = row.dataset.href;
    });
  });

  /* ZIP import - autofill name and slug */
  document
    .querySelectorAll("#id_zipcreate_zipfile,#id_doccreate_docfile,#id_image")
    .forEach((fileInput) => {
      fileInput.addEventListener("change", function () {
        const form = this.closest("form");
        const target = form.querySelector("input[name=name]");
        if (this.files.length > 0 && target.value === "") {
          const name = this.files[0].name;
          target.value = name.substring(0, name.lastIndexOf("."));
          target.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
    });

  /* Alert when creating a component */
  document
    .querySelectorAll(
      "#form-create-component-branch,#form-create-component-vcs",
    )
    .forEach((form) => {
      form.addEventListener("submit", () => {
        addAlert(
          gettext("Weblate is now scanning the repository, please be patient."),
          "info",
          0,
        );
      });
    });

  /* Username @-mention autocompletion in markdown textareas */
  const positionMentionDropdown = (editor, list) => {
    if (!list) {
      return;
    }
    const rect = editor.getBoundingClientRect();
    const cs = getComputedStyle(editor);
    const lineHeight = Number.parseFloat(cs.lineHeight) || 20;
    const paddingTop = Number.parseFloat(cs.paddingTop) || 0;
    const before = editor.value.substring(0, editor.selectionStart);
    const linesBefore = (before.match(/\n/g) || []).length;
    const yOffset =
      paddingTop + (linesBefore + 1) * lineHeight - editor.scrollTop;
    list.style.top = `${rect.top + yOffset}px`;
    list.style.left = `${rect.left}px`;
  };
  document.querySelectorAll(".markdown-editor").forEach((editor) => {
    const mentionRegex = /(?:^|\s)@(\S+)$/;
    const mentionAutoComplete = new autoComplete({
      selector: () => editor,
      wrapper: false,
      data: {
        keys: ["full_name"],
        src: async (query) => {
          const response = await fetch(
            `/api/users/?username=${encodeURIComponent(query)}&is_active=1`,
          );
          const data = await response.json();
          return data.results.map((user) => ({
            username: user.username,
            full_name: `${user.full_name} (${user.username})`,
          }));
        },
      },
      query: (val) => {
        const before = val.substring(0, editor.selectionStart);
        const match = before.match(mentionRegex);
        return match ? match[1] : "";
      },
      trigger: (query) => query.length >= 2,
      submit: true,
      resultsList: {
        class: "autoComplete dropdown-menu shadow mention-dropdown",
      },
      resultItem: {
        class: "autoComplete_result",
        element: (item, data) => {
          item.textContent = "";
          const child = document.createElement("a");
          child.textContent = data.value.full_name;
          child.classList.add("dropdown-item");
          item.appendChild(child);
        },
        selected: "autoComplete_selected",
        highlight: false,
      },
      events: {
        input: {
          open: () => positionMentionDropdown(editor, mentionAutoComplete.list),
          results: () =>
            positionMentionDropdown(editor, mentionAutoComplete.list),
          selection(event) {
            const username = event.detail.selection.value.username;
            const caret = editor.selectionStart;
            const before = editor.value.substring(0, caret);
            const after = editor.value.substring(caret);
            const match = before.match(/@\S*$/);
            if (!match) {
              return;
            }
            const tokenStart = caret - match[0].length;
            editor.value = `${editor.value.substring(0, tokenStart)}@${username}${after}`;
            const newCaret = tokenStart + username.length + 1;
            editor.selectionStart = editor.selectionEnd = newCaret;
            editor.focus();
            editor.dispatchEvent(new Event("input", { bubbles: true }));
          },
        },
      },
    });

    editor.addEventListener(
      "keydown",
      (event) => {
        if (!mentionAutoComplete.isOpen) {
          return;
        }
        if (event.key === "Enter" && mentionAutoComplete.cursor >= 0) {
          event.preventDefault();
          return;
        }
        if (event.key !== "Escape") {
          return;
        }
        event.stopImmediatePropagation();
        event.preventDefault();
        editor.setAttribute("aria-expanded", "false");
        editor.setAttribute("aria-activedescendant", "");
        mentionAutoComplete.list?.setAttribute("hidden", "");
        mentionAutoComplete.isOpen = false;
      },
      true,
    );
  });

  /* forset fields adding */
  document.querySelectorAll(".add-multifield").forEach((addField) => {
    addField.addEventListener("click", (event) => {
      event.preventDefault();
      const updateElementIndex = (el, prefix, ndx) => {
        const idRegex = new RegExp(`(${prefix}-(\\d+|__prefix__))`);
        const replacement = `${prefix}-${ndx}`;
        if (el.htmlFor) {
          el.htmlFor = el.htmlFor.replace(idRegex, replacement);
        }
        if (el.id) {
          el.id = el.id.replace(idRegex, replacement);
        }
        if (el.name) {
          el.name = el.name.replace(idRegex, replacement);
        }
      };
      const form = addField.closest("form");
      const prefix = addField.dataset.prefix;
      const blank = form.querySelector(".multiFieldEmpty");
      const row = blank.cloneNode(true);
      const totalForms = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
      row.classList.remove("multiFieldEmpty", "hidden");
      row.classList.add("multiField");
      row.querySelectorAll("*").forEach((el) => {
        updateElementIndex(el, prefix, totalForms.value);
      });

      blank.parentNode.insertBefore(row, blank);
      totalForms.value = Number.parseInt(totalForms.value, 10) + 1;
    });
  });

  /* Textarea highlighting */
  Prism.languages.none = {};
  initHighlight(document);

  document
    .querySelectorAll(".replace-preview input[type='checkbox']")
    .forEach((checkbox) => {
      checkbox.addEventListener("change", function () {
        this.closest("tr").classList.toggle("warning", this.checked);
      });
    });

  /* Suggestion rejection */
  document.querySelectorAll(".rejection-reason").forEach((element) => {
    element.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        this.closest("form").querySelector("[name='delete']")?.click();
        event.preventDefault();
      }
    });
  });

  /* Notifications removal */
  document
    .querySelectorAll(".nav-pills > li > a > button.btn-close")
    .forEach((button) => {
      button.addEventListener("click", (_e) => {
        const link = button.parentElement;
        document
          .querySelectorAll(`${link.getAttribute("data-bs-target")} select`)
          .forEach((select) => {
            select.remove();
          });
        //      document.getElementById(link.getAttribute("href").substring(1)).remove();
        /* Activate watched tab */
        const watched = document.querySelector(
          'a[data-bs-target="#notifications__1"',
        );
        bootstrap.Tab.getOrCreateInstance(watched).show();
        link.parentElement.remove();
        addAlert(
          gettext(
            "Notification settings removed, please do not forget to save the changes.",
          ),
          "info",
          3000,
        );
      });
    });

  /* User autocomplete */
  document
    .querySelectorAll(".user-autocomplete")
    .forEach((autoCompleteInput) => {
      const autoCompleteJs = new autoComplete({
        selector: () => {
          return autoCompleteInput;
        },
        debounce: 300,
        resultsList: {
          class: "autoComplete dropdown-menu",
        },
        resultItem: {
          class: "autoComplete_result",
          element: (item, data) => {
            item.textContent = "";
            const child = document.createElement("a");
            child.textContent = data.value.full_name;
            item.appendChild(child);
          },
          selected: "autoComplete_selected",
        },
        data: {
          keys: ["username"],
          src: async (query) => {
            try {
              // Fetch Data from external Source
              const source = await fetch(`/api/users/?username=${query}`);
              // Data should be an array of `Objects` or `Strings`
              const data = await source.json();
              return data.results.map((user) => {
                return {
                  username: user.username,
                  full_name: `${user.full_name} (${user.username})`,
                };
              });
            } catch (error) {
              return error;
            }
          },
        },
        events: {
          input: {
            focus() {
              if (autoCompleteInput.value.length > 0) {
                autoCompleteJs.start();
              }
            },
            selection(event) {
              const feedback = event.detail;
              autoCompleteInput.blur();
              const selection =
                feedback.selection.value[feedback.selection.key];
              autoCompleteInput.value = selection;
            },
          },
        },
      });
    });

  /* Site-wide search */
  const siteSearch = new autoComplete({
    /*name: "sitewide-search",*/
    selector: "#sitewide-search",
    debounce: 300,
    resultsList: {
      class: "autoComplete dropdown-menu shadow",
    },
    resultItem: {
      class: "autoComplete_result",
      element: (item, data) => {
        item.textContent = "";
        const child = document.createElement("a");
        child.setAttribute("href", data.value.url);
        child.textContent = `${data.value.name} `;
        child.classList.add("dropdown-item");
        const category = document.createElement("span");
        category.setAttribute("class", "badge");
        category.classList.add("text-bg-secondary");
        category.textContent = data.value.category;
        child.appendChild(category);
        item.appendChild(child);
      },
      selected: "autoComplete_selected",
    },
    data: {
      keys: ["name"],
      src: async (query) => {
        try {
          const source = await fetch(`/api/search/?q=${query}`);
          const data = await source.json();
          return data;
        } catch (error) {
          return error;
        }
      },
    },
    events: {
      input: {
        focus() {
          if (siteSearch.input.value.length > 0) {
            siteSearch.start();
          }
        },
      },
    },
  });

  /* Workflow customization form */
  document.querySelectorAll("#id_workflow-enable").forEach((enableInput) => {
    enableInput.addEventListener("click", () => {
      if (enableInput.checked) {
        document.getElementById("workflow-enable-target").style.visibility =
          "visible";
        document.getElementById("workflow-enable-target").style.opacity = 1;
      } else {
        document.getElementById("workflow-enable-target").style.visibility =
          "hidden";
        document.getElementById("workflow-enable-target").style.opacity = 0;
      }
    });
    enableInput.dispatchEvent(new Event("click"));
  });

  /* Move current translation into the view */
  document
    .querySelectorAll('a[data-bs-toggle="tab"][data-bs-target="#nearby"]')
    .forEach((tab) => {
      tab.addEventListener("shown.bs.tab", (_e) => {
        document.querySelector("#nearby .current_translation")?.scrollIntoView({
          block: "nearest",
          inline: "nearest",
          behavior: "smooth",
        });
      });
    });

  document.querySelectorAll("[data-visibility]").forEach((toggle) => {
    toggle.addEventListener("click", (_event) => {
      document
        .querySelectorAll(toggle.getAttribute("data-visibility"))
        .forEach((element) => {
          element.classList.toggle("visible");
        });
    });
  });

  /* Date range picker for period inputs */
  document.querySelectorAll("input[name='period']").forEach((input) => {
    new DateRangePicker(input);
  });

  /* Singular or plural new unit switcher */
  const setContextValue = (toSelector, fromSelector) => {
    const to = document.querySelector(`${toSelector} input[name='context']`);
    const from = document.querySelector(
      `${fromSelector} input[name='context']`,
    );
    if (to !== null && from !== null) {
      to.value = from.value;
    }
  };
  document
    .querySelectorAll("input[name='new-unit-form-type']")
    .forEach((typeInput) => {
      typeInput.addEventListener("change", function () {
        const refreshInput = (el, value) => {
          el.value = value;
          el.dispatchEvent(new CustomEvent("input"));
        };
        const transferTextareaInputs = (fromId, toId) => {
          document
            .querySelectorAll(`${toId} textarea`)
            .forEach((toTextArea) => {
              document
                .querySelectorAll(`${fromId} textarea`)
                .forEach((fromTextArea) => {
                  if (fromTextArea.name === toTextArea.name) {
                    refreshInput(toTextArea, fromTextArea.value);
                  }
                });
            });
        };
        const selected = this.value;
        if (selected === "singular") {
          document
            .querySelectorAll("input[name='new-unit-form-type']")
            .forEach((input) => {
              input.removeAttribute("checked");
            });
          const showSingular = document.querySelector(
            "#new-singular #show-singular",
          );
          if (showSingular !== null) {
            showSingular.checked = true;
          }
          setContextValue("#new-singular", "#new-plural");
          transferTextareaInputs("#new-plural", "#new-singular");
          document.querySelector("#new-plural")?.classList.add("hidden");
          document.querySelector("#new-singular")?.classList.remove("hidden");
        } else if (selected === "plural") {
          document
            .querySelectorAll("input[name='new-unit-form-type']")
            .forEach((input) => {
              input.removeAttribute("checked");
            });
          const showPlural = document.querySelector("#new-plural #show-plural");
          if (showPlural !== null) {
            showPlural.checked = true;
          }
          setContextValue("#new-plural", "#new-singular");
          transferTextareaInputs("#new-singular", "#new-plural");
          document.querySelector("#new-singular")?.classList.add("hidden");
          document.querySelector("#new-plural")?.classList.remove("hidden");
        }
      });
    });

  /* WebAuthn registration completion in profile */
  document.addEventListener("otp_webauthn.register_complete", (event) => {
    const id = event.detail.id;
    const deviceInput = document.querySelector(
      "input[name=passkey-device-name]",
    );
    const _csrfToken = document.querySelector(
      "input[name=csrfmiddlewaretoken]",
    );

    const action = deviceInput.getAttribute("data-href").replace("000000", id);

    const form = document.getElementById("link-post");

    form.setAttribute("action", action);
    const elm = document.createElement("input");
    elm.setAttribute("type", "hidden");
    elm.setAttribute("name", "name");
    elm.setAttribute("value", deviceInput.value);
    form.appendChild(elm);
    form.submit();
  });

  /* Allow styling of auth icons that we ship */
  document.querySelectorAll(".auth-image").forEach((el) => {
    const src = el.getAttribute("src");
    if (src !== null) {
      if (
        src.endsWith("password.svg") ||
        src.endsWith("email.svg") ||
        src.endsWith("twitter.svg") ||
        src.endsWith("github.svg")
      ) {
        el.classList.add("auth-image-filter");
      }
    }
  });

  /* Warn users that they do not want to use developer console in most cases */
  console.log(
    "%c%s",
    "color: red; font-weight: bold; font-size: 50px; font-family: sans-serif; -webkit-text-stroke: 1px black;",
    pgettext("Alert to user when opening browser developer console", "Stop!"),
  );
  console.log(
    "%c%s",
    "font-size: 20px; font-family: sans-serif",
    gettext(
      "This is a browser feature intended for developers. If someone told you to copy-paste something here, they are likely trying to compromise your Weblate account.",
    ),
  );
  console.log(
    "%c%s",
    "font-size: 20px; font-family: sans-serif",
    gettext("See https://en.wikipedia.org/wiki/Self-XSS for more information."),
  );

  /* Display relevant file_format_params field in Component forms */
  const form_auto_ids = ["id", "id_scratchcreate"];
  const file_format_params_fields_ids = form_auto_ids.map((id) => {
    return `#div_${id}_file_format_params`;
  });

  function displayRelevantFileFormatParams(form, selectedFileFormat) {
    if (form === null) {
      return;
    }
    if (selectedFileFormat) {
      file_format_params_fields_ids.forEach((fieldId) => {
        show(form.querySelector(fieldId));
      });
      let displayFieldLabel = false;
      form.querySelectorAll(".file-format-param").forEach((param) => {
        const fileFormats = param
          .querySelector(".file-format-param-field")
          ?.getAttribute("fileformats")
          ?.split(" ");
        if (
          fileFormats &&
          (fileFormats.includes(selectedFileFormat) ||
            fileFormats.includes("*"))
        ) {
          show(param);
          displayFieldLabel = true;
        } else {
          hide(param);
        }
      });
      // hide the field if no matching file format parameter is visible
      file_format_params_fields_ids.forEach((fieldId) => {
        const field = form.querySelector(fieldId);
        if (displayFieldLabel) {
          show(field);
        } else {
          hide(field);
        }
      });
    } else {
      file_format_params_fields_ids.forEach((fieldId) => {
        hide(form.querySelector(fieldId));
      });
    }
  }

  form_auto_ids
    .map((id) => {
      return `#${id}_file_format`;
    })
    .forEach((fieldSelector) => {
      const field = document.querySelector(fieldSelector);
      if (field === null) {
        return;
      }
      const fileFormatForm = field.closest("form");
      displayRelevantFileFormatParams(fileFormatForm, field.value);

      field.addEventListener("change", function () {
        displayRelevantFileFormatParams(fileFormatForm, this.value);
      });
    });

  document.querySelector("#string-add")?.addEventListener("click", (_e) => {
    const tab = document.querySelector("[data-bs-target='#new'");
    bootstrap.Tab.getOrCreateInstance(tab).show();
    tab.closest(".dropdown-menu").classList.remove("show");
  });

  /* Datetime formatting */
  const dateFormatter = new Intl.DateTimeFormat(document.documentElement.lang, {
    timeStyle: "medium",
    dateStyle: "short",
  });
  document.querySelectorAll(".naturaltime").forEach((timespan) => {
    const timestamp = Date.parse(timespan.getAttribute("data-datetime"));
    const difference = (Date.now() - timestamp) / 1000;
    let value = "";
    if (Math.abs(difference) < 2) {
      value = gettext("just now");
    } else if (difference > 0) {
      if (difference < 60) {
        const seconds = Math.floor(difference);
        value = interpolate(
          ngettext("%s second ago", "%s seconds ago", seconds),
          [seconds],
        );
      } else if (difference < 60 * 60) {
        const minutes = Math.floor(difference / 60);
        if (minutes === 1) {
          value = gettext("a minute ago");
        } else {
          value = interpolate(
            ngettext("%s minute ago", "%s minutes ago", minutes),
            [minutes],
          );
        }
      } else if (difference < 60 * 60 * 24) {
        const hours = Math.floor(difference / (60 * 60));
        if (hours === 1) {
          value = gettext("an hour ago");
        } else {
          value = interpolate(ngettext("%s hour ago", "%s hours ago", hours), [
            hours,
          ]);
        }
      }
    }
    if (value === "") {
      value = dateFormatter.format(new Date(timestamp));
    }
    timespan.textContent = value;
  });

  /* Filter category select options based on selected project for component links */
  document.querySelectorAll("[data-link-category-select]").forEach((source) => {
    const target = document.querySelector(source.dataset.linkCategorySelect);
    if (target === null) {
      return;
    }

    let categoriesMap;
    try {
      categoriesMap = JSON.parse(
        source.getAttribute("data-link-category-map") || "{}",
      );
    } catch (e) {
      console.error("Could not parse link category map", e);
      return;
    }

    const firstOption = target.querySelector("option");
    const emptyLabel = firstOption?.textContent || "---------";

    const updateTarget = () => {
      const key = source.value;
      target.replaceChildren();
      const emptyOption = document.createElement("option");
      emptyOption.value = "";
      emptyOption.textContent = emptyLabel;
      target.appendChild(emptyOption);
      const items = categoriesMap[key] || [];
      for (const item of items) {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = item.name;
        target.appendChild(option);
      }
    };
    source.addEventListener("change", updateTarget);

    // Filter initial state
    updateTarget();
  });
});
