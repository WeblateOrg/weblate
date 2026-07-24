// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  const EditorBase = WLT.Editor.Base;

  const _tmServiceName = "weblate-translation-memory";

  // Shared two-step keyboard sequence state.
  // Only one sequence can be pending at a time — starting a new one cancels
  // the previous.
  const _seqState = { name: null, timer: null };

  function _seqStart(name) {
    clearTimeout(_seqState.timer);
    _seqState.name = name;
    _seqState.timer = setTimeout(() => {
      _seqState.name = null;
    }, 2000);
  }

  function _seqMatch(name) {
    if (_seqState.name === name) {
      clearTimeout(_seqState.timer);
      _seqState.name = null;
      return true;
    }
    return false;
  }

  // Machinery rows store their raw payload as JSON in a data attribute so that
  // it survives DOM operations without relying on jQuery's data cache.
  function setRawData(row, data) {
    row.dataset.raw = JSON.stringify(data);
  }

  function getRawData(row) {
    return row?.dataset.raw ? JSON.parse(row.dataset.raw) : undefined;
  }

  // Direct `<tr>` children of an element (equivalent to jQuery `.children("tr")`).
  function childRows(el) {
    return Array.from(el.children).filter((child) => child.matches("tr"));
  }

  function FullEditor() {
    EditorBase.call(this);

    this.csrfToken = document.querySelector("#link-post input")?.value;

    this.initTranslationForm();
    this.initTabs();
    this.initChecks();
    this.initGlossary();
    this.initSuggestions();

    const copyMachinery = (row, mark) => {
      const raw = getRawData(row);
      if (!raw) {
        return;
      }
      for (const pluralForm of raw.plural_forms) {
        const area = this.translationArea[pluralForm];
        if (area) {
          replaceValue(area, raw.text);
        }
      }
      mark(this.translationForm);
    };

    /* Copy machinery results */
    delegate(this.editors, "click", ".js-copy-machinery", (e) => {
      copyMachinery(e.target.closest("tr"), WLT.Utils.markFuzzy);
    });

    /* Copy and save machinery results */
    delegate(this.editors, "click", ".js-copy-save-machinery", (e) => {
      copyMachinery(e.target.closest("tr"), WLT.Utils.markTranslated);
      submitForm({ target: this.translationArea[0] });
    });

    /* Copy, approve and save machinery results */
    delegate(this.editors, "click", ".js-copy-approve-save-machinery", (e) => {
      copyMachinery(e.target.closest("tr"), WLT.Utils.markApproved);
      submitForm({ target: this.translationArea[0] });
    });

    /* Delete machinery results */
    delegate(this.editors, "click", ".js-delete-machinery", (e) => {
      const deleteButton = e.target.closest(".js-delete-machinery");
      const self = this;

      /* Delete Url dialog */
      let deleteEntriesDialog = null;
      delegate(
        self.editors,
        "shown.bs.modal",
        "#delete-url-modal",
        function () {
          deleteEntriesDialog = this;
          const modalBody = deleteEntriesDialog.querySelector(".modal-body");
          modalBody.replaceChildren();
          const text = getRawData(deleteButton.closest("tr")).text;
          modalBody.append(self.machinery.renderDeleteUrls(text));
        },
      );

      delegate(self.editors, "hidden.bs.modal", "#delete-url-modal", () => {
        deleteEntriesDialog = null;
      });

      delegate(self.editors, "submit", ".delete-url-form", function (ev) {
        ev.preventDefault();
        const deleteEntries = this.querySelectorAll(
          "input.form-check-input:checked",
        );
        if (deleteEntriesDialog === null) {
          return;
        }
        bootstrap.Modal.getInstance(deleteEntriesDialog)?.hide();

        for (const entry of deleteEntries) {
          if (entry.id) {
            self.removeTranslationEntry(entry.id);
          }
        }
      });
    });

    hotkeys("alt+end", () => {
      const button = document.getElementById("button-end");
      if (button?.href) {
        window.location = button.href;
      }
      return false;
    });
    hotkeys("alt+pagedown,ctrl+down,command+down,alt+down", () => {
      const button = document.getElementById("button-next");
      if (button?.href) {
        window.location = button.href;
      }
      return false;
    });
    hotkeys("alt+pageup,ctrl+up,command+up,alt+up", () => {
      const button = document.getElementById("button-prev");
      if (button?.href) {
        window.location = button.href;
      }
      return false;
    });
    hotkeys("alt+home", () => {
      const button = document.getElementById("button-first");
      if (button?.href) {
        window.location = button.href;
      }
      return false;
    });
    hotkeys("ctrl+o,command+o", () => {
      document
        .querySelector(".source-language-group [data-clone-value]")
        ?.click();
      return false;
    });
    hotkeys("ctrl+y,command+y", () => {
      document.querySelector('input[name="fuzzy"]')?.click();
      return false;
    });
    hotkeys("ctrl+shift+enter,command+shift+enter", (e) => {
      const fuzzy = document.querySelector('input[name="fuzzy"]');
      if (fuzzy) fuzzy.checked = false;
      return submitForm(e);
    });
    hotkeys("alt+enter", (e) => {
      return submitForm(e, null, 'button[name="suggest"]');
    });
    hotkeys("ctrl+e,command+e", () => {
      this.translationArea[0]?.focus();
      return false;
    });
    hotkeys("ctrl+s,command+s", () => {
      document.getElementById("search-dropdown")?.click();
      document.querySelector('textarea[name="q"]')?.focus();
      return false;
    });
    hotkeys("ctrl+u,command+u", () => {
      document.querySelector('.nav [data-bs-target="#comments"]')?.click();
      document.querySelector('textarea[name="comment"]')?.focus();
      return false;
    });
    hotkeys("ctrl+j,command+j", () => {
      document.querySelector('.nav [data-bs-target="#nearby"]')?.click();
      return false;
    });
    hotkeys("ctrl+m,command+m", () => {
      document.querySelector('.nav [data-bs-target="#machinery"]')?.click();
      return false;
    });
  }
  FullEditor.prototype = Object.create(EditorBase.prototype);
  FullEditor.prototype.constructor = FullEditor;

  FullEditor.prototype.initTranslationForm = function () {
    this.translationForm = document.querySelector(".translation-form");

    /* Report source bug */
    delegate(this.translationForm, "click", ".bug-comment", () => {
      bootstrap.Tab.getOrCreateInstance(
        document.querySelector(
          '.translation-tabs a[data-bs-target="#comments"]',
        ),
      ).show();
      const scope = document.getElementById("id_scope");
      if (scope) {
        scope.value = "report";
      }
      document
        .getElementById("comment-form")
        ?.scrollIntoView({ behavior: "smooth" });
      document.getElementById("id_comment")?.focus();
    });

    delegate(this.translationForm, "click", ".add-alternative-post", (e) => {
      e.preventDefault();
      const elm = document.createElement("input");
      elm.type = "hidden";
      elm.name = "add_alternative";
      elm.value = "1";
      this.translationForm.append(elm);
      this.translationForm.requestSubmit();
    });

    /* Form persistence. Restores translation form upon comment submission */
    const restoreKey = "translation_autosave";
    const restoreValue = localStorage.getItem(restoreKey);
    if (restoreValue !== null) {
      const translationRestore = JSON.parse(restoreValue);

      translationRestore.forEach((restoreArea) => {
        const target = document.getElementById(restoreArea.id);
        if (target) {
          target.value = restoreArea.value;
          target.dispatchEvent(new Event("input", { bubbles: true }));
        }
      });
      localStorage.removeItem(restoreKey);
    }

    delegate(this.editors, "submit", ".auto-save-translation", () => {
      const data = Array.from(this.translationArea, (area) => ({
        id: area.id,
        value: area.value,
      }));

      localStorage.setItem(restoreKey, JSON.stringify(data));
    });
  };

  FullEditor.prototype.initTabs = function () {
    /* Store active tab in a local storage */
    for (const tab of document.querySelectorAll(
      '.translation-tabs a[data-bs-toggle="tab"]',
    )) {
      tab.addEventListener("shown.bs.tab", function () {
        const current = localStorage.getItem("translate-tab");
        const desired = this.getAttribute("data-bs-target");

        if (current !== desired) {
          localStorage.setItem("translate-tab", desired);
        }
      });
    }

    /* Machinery */
    this.isMachineryLoaded = false;
    delegate(this.editors, "show.bs.tab", '[data-load="machinery"]', () => {
      if (this.isMachineryLoaded) {
        return;
      }
      this.initMachinery();
    });

    /* The active tab is restored before the listener above is registered, load it now in that case. */
    const machineryTab = document.querySelector('[data-load="machinery"]');
    if (machineryTab?.classList.contains("active")) {
      if (this.isMachineryLoaded) {
        return;
      }
      this.initMachinery();
    }
  };

  FullEditor.prototype.initMachinery = function () {
    this.isMachineryLoaded = true;
    this.machinery = new Machinery();
    this.initMachineryHotkeys();

    const services = JSON.parse(
      document.getElementById("js-translate").dataset.services,
    );
    services.forEach((serviceName) => {
      increaseLoading("machinery");
      this.fetchMachinery(serviceName);
    });

    delegate(this.editors, "submit", "#memory-search", (e) => {
      const form = e.target.closest("#memory-search");
      e.preventDefault();

      increaseLoading("machinery");
      this.machinery.setState({ translations: [] });
      document.getElementById("machinery-translations").replaceChildren();
      fetch(form.getAttribute("action"), {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
        body: new URLSearchParams(new FormData(form)),
      })
        .then((response) => response.json())
        .then((data) => {
          this.processMachineryResults(data);
        })
        .catch((error) => {
          this.processMachineryError(error);
        });
      return false;
    });
  };

  FullEditor.prototype.initMachineryHotkeys = () => {
    hotkeys("ctrl+m,command+m", () => {
      _seqStart("machinery");
      return false;
    });

    hotkeys("1,2,3,4,5,6,7,8,9,0", (e) => {
      if (!_seqMatch("machinery")) {
        return;
      }

      const rows = childRows(document.getElementById("machinery-translations"));
      for (const row of rows) {
        if (row.dataset.machineryKey === e.key) {
          const copyButton = row.querySelector(".js-copy-machinery");
          if (copyButton) {
            copyButton.click();
            return false;
          }
          break;
        }
      }
    });
  };

  FullEditor.prototype.removeTranslationEntry = function (deleteUrl) {
    fetch(deleteUrl, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRFToken": this.csrfToken },
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        addAlert(gettext("Translation memory entry removed."), "success");
      })
      .catch((error) => {
        addAlert(error.message);
      });
  };

  FullEditor.prototype.fetchMachinery = function (serviceName) {
    const url = document
      .getElementById("js-translate")
      .getAttribute("href")
      .replace("__service__", serviceName);
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        Accept: "application/json",
      },
      body: new URLSearchParams({ csrfmiddlewaretoken: this.csrfToken }),
    })
      .then((response) => response.json())
      .then((data) => {
        this.processMachineryResults(data);
      })
      .catch((error) => {
        this.processMachineryError(error);
      });
  };

  FullEditor.prototype.processMachineryError = (error) => {
    decreaseLoading("machinery");
    addAlert(
      `${gettext("The request for machine translation has failed:")} ${
        error.message
      }`,
    );
  };

  FullEditor.prototype.processMachineryResults = function (data) {
    decreaseLoading("machinery");
    if (data.responseStatus !== 200) {
      const msg = interpolate(
        gettext("The request for machine translation using %s has failed:"),
        [data.service],
      );
      addAlert(`${msg} ${data.responseDetails}`);

      return;
    }

    this.machinery.setState({
      translations: [
        ...this.machinery.state.translations,
        ...data.translations,
      ],
      weblateTranslationMemory: new Set(),
      lang: data.lang,
      dir: data.dir,
    });
    this.machinery.render(data.translations);

    const translationRows = childRows(
      document.getElementById("machinery-translations"),
    );

    translationRows.forEach((row, idx) => {
      const numberEl = row.querySelector(".machinery-number");
      if (idx < 10) {
        const key = String(WLT.Utils.getNumericKey(idx));

        let title;
        if (WLT.Config.IS_MAC) {
          title = interpolate(gettext("Cmd+M then %s"), [key]);
        } else {
          title = interpolate(gettext("Ctrl+M then %s"), [key]);
        }
        row.setAttribute("data-machinery-key", key);
        if (numberEl) {
          const kbd = document.createElement("kbd");
          kbd.setAttribute("title", title);
          kbd.textContent = key;
          numberEl.replaceChildren(kbd);
        }
      } else {
        row.removeAttribute("data-machinery-key");
        if (numberEl) {
          numberEl.replaceChildren();
        }
      }
    });
  };

  FullEditor.prototype.initChecks = function () {
    /* Clicking links (e.g. comments, suggestions)
     * This is inside things to checks, but not a check-item */
    delegate(
      this.editors,
      "click",
      '.check [data-bs-toggle="tab"]',
      function (e) {
        const target = this.getAttribute("data-bs-target");

        e.preventDefault();
        document.querySelector(`.nav [data-bs-target="${target}"]`)?.click();
        const tabs = document.querySelector(".translation-tabs");
        if (tabs) {
          window.scrollTo(0, tabs.getBoundingClientRect().top + window.scrollY);
        }
      },
    );

    const checks = document.querySelectorAll(".check-item");
    if (checks.length === 0) {
      return;
    }

    /* Check ignoring */
    delegate(this.editors, "click", ".check-dismiss", (e) => {
      e.preventDefault();
      const el = e.target.closest(".check-dismiss");
      let url = el.getAttribute("href");
      const check = el.closest(".check");
      const dismissAll = check.querySelector("input")?.checked;
      if (dismissAll) {
        url = el.dataset.dismissAll;
      }

      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
        body: new URLSearchParams({ csrfmiddlewaretoken: this.csrfToken }),
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          return response.json();
        })
        .then((data) => {
          if (dismissAll) {
            const { extra_flags, all_flags } = data;
            const extraFlags = document.getElementById("id_extra_flags");
            if (extraFlags) {
              extraFlags.value = extra_flags;
            }
            const allFlags = document.getElementById("unit_all_flags");
            if (allFlags) {
              allFlags.textContent = all_flags;
              allFlags.classList.add("flags-updated");
            }
          }
        })
        .catch((error) => {
          addAlert(error.message);
        });
      if (dismissAll) {
        check.remove();
      } else {
        check.classList.toggle("check-dismissed");
      }
    });

    /* Automatically translated dismissal */
    delegate(
      this.editors,
      "click",
      ".dismiss-automatically-translated",
      (e) => {
        e.preventDefault();
        const el = e.target.closest(".dismiss-automatically-translated");
        const url = el.getAttribute("href");
        const check = el.closest(".check");

        fetch(url, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            Accept: "application/json",
          },
          body: new URLSearchParams({ csrfmiddlewaretoken: this.csrfToken }),
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error(`HTTP ${response.status}`);
            }
            const listGroup = check.closest(".list-group");
            check.remove();

            // Hide the entire "Things to check" panel if no checks remain
            if (
              listGroup &&
              listGroup.querySelectorAll(".list-group-item").length === 0
            ) {
              listGroup.closest(".panel")?.remove();
            }
          })
          .catch((error) => {
            addAlert(error.message);
          });
      },
    );

    /* Check fix */
    delegate(this.editors, "click", "[data-check-fixup]", (e) => {
      const el = e.target.closest("[data-check-fixup]");
      const fixups = JSON.parse(el.dataset.checkFixup);
      this.translationArea.forEach((area, plural) => {
        for (const value of fixups) {
          if (value[0] === "regex") {
            const re = new RegExp(value[1], value[3]);
            replaceValue(area, area.value.replace(re, value[2]));
          } else if (value[0] === "plurals") {
            replaceValue(area, value[1][plural]);
          } else {
            addAlert(`Unknown fixup: ${value}`);
          }
        }
      });
      return false;
    });

    /* Keyboard shortcuts */
    // Two-step sequence: Ctrl/Cmd+I then a digit key dismisses a check
    const checkActions = {};

    checks.forEach((check, idx) => {
      const numberEl = check.querySelector(".check-number");

      if (idx < 10) {
        if (!numberEl) {
          return;
        }
        const key = WLT.Utils.getNumericKey(idx);

        let title;
        if (WLT.Config.IS_MAC) {
          title = interpolate(gettext("Press Cmd+I then %s to dismiss this."), [
            key,
          ]);
        } else {
          title = interpolate(
            gettext("Press Ctrl+I then %s to dismiss this."),
            [key],
          );
        }
        const kbd = document.createElement("kbd");
        kbd.title = title;
        kbd.textContent = key;
        numberEl.replaceChildren(kbd);

        checkActions[key] = () => {
          check.querySelector(".check-dismiss-single")?.click();
        };
      } else {
        if (numberEl) numberEl.textContent = "";
      }
    });

    hotkeys("ctrl+i,command+i", () => {
      _seqStart("checks");
      return false;
    });

    hotkeys("1,2,3,4,5,6,7,8,9,0", (e) => {
      if (_seqMatch("checks") && checkActions[e.key]) {
        checkActions[e.key]();
        return false;
      }
    });
  };

  FullEditor.prototype.initGlossary = function () {
    /* Copy from glossary */
    delegate(this.editors, "click", ".glossary-embed", (e) => {
      const currentTarget = e.target.closest(".glossary-embed");
      /* Avoid copy when clicked on a link */
      const link = e.target.closest("a");
      if (link && link !== currentTarget) {
        return;
      }

      let text = currentTarget.querySelector(".target")?.textContent ?? "";
      if (currentTarget.classList.contains("warning")) {
        text = currentTarget.querySelector(".source")?.textContent ?? "";
      }

      this.insertIntoTranslation(text.trim());
      e.preventDefault();
    });

    /* Glossary dialog */
    const glossaryDialog = document.getElementById("add-glossary-form");
    glossaryDialog?.addEventListener("show.bs.modal", (e) => {
      /* Prefill adding to glossary with current string */
      if (e.target.hasAttribute("data-shown")) {
        return;
      }
      /* Relies on clone source implementation */
      const cloneElement = document.querySelector(
        ".source-language-group [data-clone-value]",
      );
      if (cloneElement !== null) {
        const source = cloneElement.getAttribute("data-clone-value");
        const termSource = document
          .getElementById("div_id_add_term_source")
          .querySelector("textarea");
        const termTarget = document
          .getElementById("div_id_add_term_target")
          .querySelector("textarea");
        if (source.length < 200) {
          termSource.value = source;
          termTarget.value = document.querySelector(
            ".translation-editor",
          ).value;
        }
        termSource.dispatchEvent(new Event("input"));
        termTarget.dispatchEvent(new Event("input"));
      }
      e.target.setAttribute("data-shown", true);
    });
    delegate(this.editors, "hidden.bs.modal", "#add-glossary-form", () => {
      this.translationArea[0]?.focus();
    });

    /* Inline glossary adding */
    delegate(document, "submit", ".add-dict-inline", (e) => {
      const form = e.target.closest(".add-dict-inline");

      increaseLoading("glossary-add");
      bootstrap.Modal.getOrCreateInstance(glossaryDialog)?.hide();
      fetch(form.getAttribute("action"), {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
        body: new URLSearchParams(new FormData(form)),
      })
        .then((response) => response.json())
        .then((data) => {
          decreaseLoading("glossary-add");
          if (data.responseCode === 200) {
            const terms = document.getElementById("glossary-terms");
            if (terms) {
              terms.innerHTML = data.results;
            }
            const termsInput = form.querySelector("[name=terms]");
            if (termsInput) {
              termsInput.setAttribute("value", data.terms);
            }
            form.reset();
          } else {
            addAlert(data.responseDetails);
          }
        })
        .catch((error) => {
          addAlert(error.message);
          decreaseLoading("glossary-add");
        });
      e.preventDefault();
      return false;
    });
  };

  FullEditor.prototype.initSuggestions = function () {
    /* Clone suggestion to translation */
    delegate(this.editors, "click", ".js-copy-suggestion", (e) => {
      e.preventDefault();
      const btn = e.target.closest(".js-copy-suggestion");

      // Inject data into translation fields (plural-aware)
      this.translationArea.forEach((el, i) => {
        const text = btn.getAttribute(`data-text-${i}`);

        // Prevent overwriting with empty/undefined data
        if (text !== null && text !== "") {
          replaceValue(el, text);
        }
      });

      this.translationArea[0]?.focus();
    });
  };

  FullEditor.prototype.insertIntoTranslation = function (text) {
    for (const area of this.translationArea) {
      insertAtCaret(area, text.trim());
    }
  };

  class Machinery {
    constructor(_initialState = {}) {
      this.state = {
        translations: [],
        weblateTranslationMemory: new Set(),
        lang: null,
        dir: null,
      };
    }

    setState(newState) {
      this.state = { ...this.state, ...newState };
    }

    renderTranslation(el, service) {
      el.plural_forms = [el.plural_form];
      const row = document.createElement("tr");
      setRawData(row, el);

      const target = document.createElement("td");
      target.className = "target machinery-text";
      target.setAttribute("lang", this.state.lang);
      target.setAttribute("dir", this.state.dir);
      target.innerHTML = el.html;
      row.append(target);

      const diff = document.createElement("td");
      diff.className = "machinery-text";
      diff.innerHTML = el.diff;
      row.append(diff);

      const sourceDiff = document.createElement("td");
      sourceDiff.className = "machinery-text";
      sourceDiff.innerHTML = el.source_diff;
      row.append(sourceDiff);

      row.append(service);

      /* Quality score as bar with the text */
      const qualityCell = document.createElement("td");
      qualityCell.className = "number";
      if (el.show_quality) {
        const quality = document.createElement("strong");
        quality.textContent = String(el.quality);
        qualityCell.append(quality, " %");
      }
      row.append(qualityCell);

      /* Translators: Verb for copy operation */
      row.insertAdjacentHTML(
        "beforeend",
        `<td><a class="js-copy-machinery btn btn-warning">${gettext(
          "Clone to translation",
        )}<span class="mt-number text-info"></span></a></td><td><a class="js-copy-save-machinery btn btn-info">${gettext(
          "Accept",
        )}</a></td>`,
      );

      if (WLT.Config.HAS_REVIEW_WORKFLOW) {
        row.insertAdjacentHTML(
          "beforeend",
          `<td><a class="js-copy-approve-save-machinery btn btn-warning">${gettext(
            "Accept and approve",
          )}</a></td>`,
        );
      } else {
        row.insertAdjacentHTML("beforeend", "<td></td>");
      }

      if (this.state.weblateTranslationMemory.has(el.text)) {
        row.insertAdjacentHTML(
          "beforeend",
          `<td><a class="js-delete-machinery btn btn-danger" data-bs-toggle="modal" data-bs-target="#delete-url-modal">${gettext(
            "Delete entry",
          )}</a></td>`,
        );
      } else {
        row.insertAdjacentHTML("beforeend", "<td></td>");
      }

      return row;
    }

    renderService(el) {
      const service = document.createElement("td");
      service.textContent = el.service;
      if (typeof el.origin !== "undefined") {
        service.append(" (");
        let origin;
        if (typeof el.origin_detail !== "undefined") {
          origin = document.createElement("abbr");
          origin.textContent = el.origin;
          origin.setAttribute("title", el.origin_detail);
        } else if (typeof el.origin_url !== "undefined") {
          const originUrl = WLT.URLs.getHttpUrl(el.origin_url);
          if (originUrl === null) {
            origin = document.createTextNode(String(el.origin));
          } else {
            origin = document.createElement("a");
            origin.textContent = el.origin;
            origin.setAttribute("href", originUrl);
          }
        } else {
          origin = document.createTextNode(String(el.origin));
        }
        if (el.delete_url) {
          this.state.weblateTranslationMemory.add(el.text);
        }
        service.append(origin);
        service.append(")");
      }
      return service;
    }

    renderDeleteUrls(text) {
      const translations = this.state.translations;
      const modalBody = document.createElement("label");

      translations.forEach((translation) => {
        if (
          text === translation.text &&
          typeof translation.delete_url !== "undefined"
        ) {
          const inputElement = document.createElement("input");
          inputElement.className = "form-check-input";
          inputElement.type = "checkbox";
          inputElement.value = "";
          inputElement.id = translation.delete_url;
          inputElement.checked = true;
          const labelElement = document.createElement("label");
          labelElement.className = "form-check-label";
          labelElement.setAttribute("for", translation.delete_url);
          labelElement.textContent = translation.origin;
          const divElement = document.createElement("div");
          divElement.className = "form-check";
          divElement.append(inputElement, labelElement);
          modalBody.append(divElement);
        }
      });
      return modalBody;
    }

    render(translations) {
      const translationsEl = document.getElementById("machinery-translations");
      translations.forEach((translation) => {
        const service = this.renderService(translation);
        let insertBefore = null;
        let done = false;

        /* This is the merging and insert sort logic */
        for (const row of childRows(translationsEl)) {
          const base = getRawData(row);
          if (
            base.text === translation.text &&
            base.source === translation.source
          ) {
            // Add plural
            if (!base.plural_forms.includes(translation.plural_form)) {
              base.plural_forms.push(translation.plural_form);
              setRawData(row, base);
            }
            // Add origin to current ones
            const current = row.querySelector("td:nth-child(4)");
            if (base.quality < translation.quality) {
              service.insertAdjacentHTML("beforeend", "<br/>");
              service.insertAdjacentHTML("beforeend", current.innerHTML);
              row.remove();
              break;
            }
            current.insertAdjacentHTML("beforeend", "<br/>");
            current.insertAdjacentHTML("beforeend", service.innerHTML);
            done = true;
            break;
          }
          if (base.quality <= translation.quality && !insertBefore) {
            // Insert match before lower quality one
            insertBefore = row;
          }
        }

        if (!done) {
          const newRow = this.renderTranslation(translation, service);
          if (insertBefore) {
            insertBefore.before(newRow);
          } else {
            translationsEl.append(newRow);
          }
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    new FullEditor();
  });
})();
