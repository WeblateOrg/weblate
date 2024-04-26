// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

const loading = [];

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
    $(`#loading-${sel}`).show();
  }
  loading[sel] += 1;
}

function decreaseLoading(sel) {
  loading[sel] -= 1;
  if (loading[sel] === 0) {
    $(`#loading-${sel}`).hide();
  }
}

function addAlert(message, kind = "danger", delay = 3000) {
  const alerts = $("#popup-alerts");
  const e = $(
    '<div class="alert alert-dismissible" role="alert"><button type="button" class="close" data-dismiss="alert" aria-label="Close"><span aria-hidden="true">&times;</span></button></div>',
  );
  e.addClass(`alert-${kind}`);
  e.append(new Text(message));
  e.hide();
  alerts.show().append(e);
  e.slideDown(200);
  e.on("closed.bs.alert", () => {
    if (alerts.find(".alert").length === 0) {
      alerts.hide();
    }
  });
  if (delay) {
    e.delay(delay).slideUp(200, function () {
      $(this).alert("close");
    });
  }
}

jQuery.fn.extend({
  insertAtCaret: function (myValue) {
    return this.each(function () {
      if (document.selection) {
        // For browsers like Internet Explorer
        this.focus();
        const sel = document.selection.createRange();

        sel.text = myValue;
        this.focus();
      } else if (this.selectionStart || this.selectionStart === 0) {
        //For browsers like Firefox and Webkit based
        const startPos = this.selectionStart;
        const endPos = this.selectionEnd;
        const scrollTop = this.scrollTop;

        this.value =
          this.value.substring(0, startPos) +
          myValue +
          this.value.substring(endPos, this.value.length);
        this.focus();
        this.selectionStart = startPos + myValue.length;
        this.selectionEnd = startPos + myValue.length;
        this.scrollTop = scrollTop;
      } else {
        this.value += myValue;
        this.focus();
      }
      // Need `bubbles` because some event listeners (like this
      // https://github.com/WeblateOrg/weblate/blob/86d4fb308c9941f32b48f007e16e8c153b0f3fd7/weblate/static/editor/base.js#L50
      // ) are attached to the parent elements.
      this.dispatchEvent(new Event("input", { bubbles: true }));
      this.dispatchEvent(new Event("change", { bubbles: true }));
    });
  },

  replaceValue: function (myValue) {
    return this.each(function () {
      this.value = myValue;
      // Need `bubbles` because some event listeners (like this
      // https://github.com/WeblateOrg/weblate/blob/86d4fb308c9941f32b48f007e16e8c153b0f3fd7/weblate/static/editor/base.js#L50
      // ) are attached to the parent elements.
      this.dispatchEvent(new Event("input", { bubbles: true }));
      this.dispatchEvent(new Event("change", { bubbles: true }));
    });
  },
});

function submitForm(evt, combo, selector) {
  const $target = $(evt.target);
  let $form = $target.closest("form");

  if ($form.length === 0) {
    $form = $(".translation-form");
  }
  if ($form.length > 0) {
    if (typeof selector !== "undefined") {
      $form.find(selector).click();
    } else {
      let submits = $form.find('input[type="submit"]');

      if (submits.length === 0) {
        submits = $form.find('button[type="submit"]');
      }
      if (submits.length > 0) {
        submits[0].click();
      }
    }
  }
  return false;
}
Mousetrap.bindGlobal("mod+enter", submitForm);

function screenshotStart() {
  $("#search-results tbody.unit-listing-body").empty();
  increaseLoading("screenshots");
}

function screenshotFailure() {
  screenshotLoaded({ responseCode: 500 });
}

function screenshotAddString() {
  const pk = this.getAttribute("data-pk");
  const form = $("#screenshot-add-form");

  $("#add-source").val(pk);
  $.ajax({
    type: "POST",
    url: form.attr("action"),
    data: form.serialize(),
    dataType: "json",
    success: () => {
      const list = $("#sources-listing");
      $.get(list.data("href"), (data) => {
        list.find("table").replaceWith(data);
      });
    },
    error: (jqXHR, textStatus, errorThrown) => {
      addAlert(errorThrown);
    },
  });
}

function screenshotResultError(severity, message) {
  $("#search-results tbody.unit-listing-body").html(
    $("<tr/>")
      .addClass(severity)
      .html($('<td colspan="4"></td>').text(message)),
  );
}

function screenshotLoaded(data) {
  decreaseLoading("screenshots");
  if (data.responseCode !== 200) {
    screenshotResultError("danger", gettext("Error loading search results!"));
  } else if (data.results.length === 0) {
    screenshotResultError(
      "warning",
      gettext("No new matching source strings found."),
    );
  } else {
    $("#search-results table").replaceWith(data.results);
    $("#search-results").find(".add-string").click(screenshotAddString);
  }
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
  return $.text(cell);
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
  const parsed_a = getNumber(a);
  const parsed_b = getNumber(b);
  if (parsed_a !== null && parsed_b !== null) {
    return _compareValues(parsed_a, parsed_b);
  }
  if (typeof a === "string" && typeof b === "string") {
    return _compareValues(a.toLowerCase(), b.toLowerCase());
  }
  return _compareValues(a, b);
}

function loadTableSorting() {
  $("table.sort").each(function () {
    const table = $(this);
    const tbody = table.find("tbody");
    const thead = table.find("thead");
    let thIndex = 0;

    $(this)
      .find("thead th")
      .each(function () {
        const th = $(this);
        let inverse = 1;

        // handle colspan
        if (th.attr("colspan")) {
          thIndex += Number.parseInt(th.attr("colspan"), 10) - 1;
        }
        // skip empty cells and cells with icon (probably already processed)
        if (
          th.text() !== "" &&
          !th.hasClass("sort-init") &&
          !th.hasClass("sort-skip")
        ) {
          // Store index copy
          const myIndex = thIndex;
          // Add icon, title and class
          th.addClass("sort-init");
          if (!th.hasClass("sort-cell")) {
            // Skip statically initialized parts (when server side ordering is supported)
            th.attr("title", gettext("Sort this column"))
              .addClass("sort-cell")
              .append('<span class="sort-icon" />');
          }

          // Click handler
          th.click(function () {
            tbody
              .find("tr")
              .sort((a, b) => {
                let $a = $(a);
                let $b = $(b);
                const a_parent = $a.data("parent");
                const b_parent = $b.data("parent");
                if (a_parent) {
                  $a = tbody.find(`#${a_parent}`);
                }
                if (b_parent) {
                  $b = tbody.find(`#${b_parent}`);
                }
                return (
                  inverse *
                  compareCells(
                    extractText($a.find("td,th")[myIndex]),
                    extractText($b.find("td,th")[myIndex]),
                  )
                );
              })
              .appendTo(tbody);
            thead.find(".sort-icon").removeClass("sort-down sort-up");
            if (inverse === 1) {
              $(this).find(".sort-icon").addClass("sort-down");
            } else {
              $(this).find(".sort-icon").addClass("sort-up");
            }

            inverse = inverse * -1;
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

function load_matrix() {
  const $loadingNext = $("#loading-next");
  const $loader = $("#matrix-load");
  const offset = Number.parseInt($loader.data("offset"));

  if ($("#last-section").length > 0 || $loadingNext.css("display") !== "none") {
    return;
  }
  $loadingNext.show();

  $loader.data("offset", 20 + offset);

  $.get(`${$loader.attr("href")}&offset=${offset}`, (data) => {
    $loadingNext.hide();
    $(".matrix tbody").append(data);
  });
}

function adjustColspan() {
  $("table.autocolspan").each(function () {
    const $this = $(this);
    let numOfVisibleCols = $this.find("thead th:visible").length;
    if (numOfVisibleCols === 0) {
      numOfVisibleCols = 3;
    }
    $this.find("td.autocolspan").attr("colspan", numOfVisibleCols - 1);
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

function initHighlight(root) {
  if (typeof ResizeObserver === "undefined") {
    return;
  }
  // biome-ignore lint/complexity/noForEach: TODO
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
    input.addEventListener("scroll", (event) => {
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
  // biome-ignore lint/complexity/noForEach: TODO
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
      const whitespace_regex = new RegExp(
        [
          "  +|(^) +| +(?=$)| +\n|\n +|\t|",
          "\u00A0|\u00AD|\u1680|\u2000|\u2001|",
          "\u2002|\u2003|\u2004|\u2005|",
          "\u2006|\u2007|\u2008|\u2009|",
          "\u200A|\u202F|\u205F|\u3000",
        ].join(""),
      );
      const extension = {
        hlspace: {
          pattern: whitespace_regex,
          lookbehind: true,
        },
      };
      if (placeables) {
        extension.placeable = RegExp(placeables);
      }
      /*
       * We can not use Prism.extend here as we want whitespace highlighting
       * to apply first. The code is borrowed from Prism.util.clone.
       */
      for (const key in languageMode) {
        if (Object.hasOwn(languageMode, key)) {
          extension[key] = Prism.util.clone(languageMode[key]);
        }
      }
      languageMode = extension;
    }
    const syncContent = () => {
      highlight.innerHTML = Prism.highlight(editor.value, languageMode, mode);
      autosize.update(editor);
    };
    syncContent();
    editor.addEventListener("input", syncContent);

    /* Handle scrolling */
    editor.addEventListener("scroll", (event) => {
      console.log(event);
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
    /* Autosizing */
    autosize(editor);
  });
}

$(function () {
  const $window = $(window);
  const $document = $(document);

  adjustColspan();
  $window.resize(adjustColspan);
  $document.on("shown.bs.tab", adjustColspan);

  /* AJAX loading of tabs/pills */
  $document.on(
    "show.bs.tab",
    '[data-toggle="tab"][data-href], [data-toggle="pill"][data-href]',
    (e) => {
      const $target = $(e.target);
      let $content = $($target.attr("href"));
      if ($target.data("loaded")) {
        return;
      }
      if ($content.find(".panel-body").length > 0) {
        $content = $content.find(".panel-body");
      }
      $content.load($target.data("href"), (responseText, status, xhr) => {
        if (status !== "success") {
          const msg = gettext("Error while loading page:");
          $content.text(
            `${msg} ${xhr.statusText} (${xhr.status}): ${responseText}`,
          );
        }
        $target.data("loaded", 1);
        loadTableSorting();
      });
    },
  );

  if ($("#form-activetab").length > 0) {
    $document.on("show.bs.tab", '[data-toggle="tab"]', (e) => {
      const $target = $(e.target);
      $("#form-activetab").attr("value", $target.attr("href"));
    });
  }

  /* Form automatic submission */
  $("form.autosubmit select").change(() => {
    $("form.autosubmit").submit();
  });

  let activeTab;

  /* Load correct tab */
  if (location.hash !== "") {
    /* From URL hash */
    const separator = location.hash.indexOf("__");
    if (separator !== -1) {
      activeTab = $(
        `.nav [data-toggle=tab][href="${location.hash.substr(0, separator)}"]`,
      );
      if (activeTab.length) {
        activeTab.tab("show");
      }
    }
    activeTab = $(`.nav [data-toggle=tab][href="${location.hash}"]`);
    if (activeTab.length) {
      activeTab.tab("show");
      window.scrollTo(0, 0);
    } else {
      const anchor = document.getElementById(location.hash.substr(1));
      if (anchor !== null) {
        anchor.scrollIntoView();
      }
    }
  } else if (
    $(".translation-tabs").length > 0 &&
    Cookies.get("translate-tab")
  ) {
    /* From cookie */
    activeTab = $(`[data-toggle=tab][href="${Cookies.get("translate-tab")}"]`);
    if (activeTab.length) {
      activeTab.tab("show");
    }
  }

  /* Add a hash to the URL when the user clicks on a tab */
  $('a[data-toggle="tab"]').on("shown.bs.tab", function (e) {
    history.pushState(null, null, $(this).attr("href"));
    /* Remove focus on rows */
    $(".selectable-row").removeClass("active");
  });

  /* Navigate to a tab when the history changes */
  window.addEventListener("popstate", (e) => {
    if (location.hash !== "") {
      activeTab = $(`[data-toggle=tab][href="${location.hash}"]`);
    } else {
      activeTab = Array();
    }
    if (activeTab.length) {
      activeTab.tab("show");
    } else {
      $(".nav-tabs a:first").tab("show");
    }
  });

  /* Activate tab with error */
  const formErrors = $("div.has-error");
  if (formErrors.length > 0) {
    const tab = formErrors.closest("div.tab-pane");
    if (tab.length > 0) {
      $(`[data-toggle=tab][href="#${tab.attr("id")}"]`).tab("show");
    }
  }

  /* Announcement discard */
  $(".alert").on("close.bs.alert", function () {
    const $this = $(this);
    const $form = $("#link-post");

    const action = this.getAttribute("data-action");

    if (action) {
      $.ajax({
        type: "POST",
        url: action,
        data: {
          csrfmiddlewaretoken: $form.find("input").val(),
          id: this.getAttribute("data-id"),
        },
        error: (jqXHR, textStatus, errorThrown) => {
          addAlert(errorThrown);
        },
      });
    }
  });

  /* Widgets selector */
  $(".select-tab").on("change", function (e) {
    $(this).parent().find(".tab-pane").removeClass("active");
    $(`#${$(this).val()}`).addClass("active");
  });

  /* Code samples (on widgets page) */
  $(".code-example").focus(function () {
    $(this).select();
  });

  /* Table sorting */
  loadTableSorting();

  /* Matrix mode handling */
  if ($(".matrix").length > 0) {
    load_matrix();
    $window.scroll(() => {
      if ($window.scrollTop() >= $document.height() - 2 * $window.height()) {
        load_matrix();
      }
    });
  }

  /* Social auth disconnect */
  $("a.disconnect").click(function (e) {
    e.preventDefault();
    $("form#disconnect-form").attr("action", $(this).attr("href")).submit();
  });

  $(".dropdown-menu")
    .find("form")
    .click((e) => {
      e.stopPropagation();
    });

  $document.on("click", ".link-post", function () {
    const $form = $("#link-post");
    const $this = $(this);

    $form.attr("action", $this.attr("data-href"));
    $.each($this.data("params"), (name, value) => {
      const elm = $("<input>")
        .attr("type", "hidden")
        .attr("name", name)
        .attr("value", value);
      $form.append(elm);
    });
    $form.submit();
    return false;
  });
  $(".link-auto").click();
  $document.on("click", ".thumbnail", function () {
    const $this = $(this);
    $("#imagepreview").attr("src", $this.attr("href"));
    $("#screenshotModal").text($this.attr("title"));

    const detailsLink = $("#modalDetailsLink");
    detailsLink.attr("href", this.getAttribute("data-details-url"));
    if (this.getAttribute("data-can-edit")) {
      detailsLink.text(detailsLink.getAttribute("data-edit-text"));
    }

    $("#imagemodal").modal("show");
    return false;
  });
  /* Screenshot management */
  $("#screenshots-search,#screenshots-auto").click(function () {
    const $this = $(this);

    screenshotStart();
    $.ajax({
      type: "POST",
      url: this.getAttribute("data-href"),
      data: $this.parent().serialize(),
      dataType: "json",
      success: screenshotLoaded,
      error: screenshotFailure,
    });
    return false;
  });

  /* Avoid double submission of non AJAX forms */
  $("form:not(.double-submission)").on("submit", function (e) {
    const $form = $(this);

    if ($form.data("submitted") === true) {
      // Previously submitted - don't submit again
      e.preventDefault();
    } else {
      // Mark it so that the next submit can be ignored
      $form.data("submitted", true);
    }
  });
  /* Reset submitted flag when leaving the page, so that it is not set when going back in history */
  $window.on("pagehide", () => {
    $("form:not(.double-submission)").data("submitted", false);
  });

  /* Client side form persistence */
  const $forms = $("[data-persist]");
  if ($forms.length > 0 && window.localStorage) {
    /* Load from local storage */
    $forms.each(function () {
      const $this = $(this);
      let storedValue = window.localStorage[$this.data("persist")];
      if (storedValue) {
        storedValue = JSON.parse(storedValue);
        $.each(storedValue, (key, value) => {
          const target = $this.find(`[name=${key}]`);
          if (target.is(":checkbox")) {
            target.prop("checked", value);
          } else {
            target.val(value);
          }
        });
      }
    });
    /* Save on submit */
    $forms.submit(function (e) {
      const data = {};
      const $this = $(this);

      $this.find(":checkbox").each(function () {
        const $this = $(this);

        data[$this.attr("name")] = $this.prop("checked");
      });
      $this.find("select").each(function () {
        const $this = $(this);

        data[$this.attr("name")] = $this.val();
      });
      window.localStorage[$this.data("persist")] = JSON.stringify(data);
    });
  }

  /* Focus first input in modal */
  $(document).on("shown.bs.modal", (event) => {
    const button = $(event.relatedTarget); // Button that triggered the modal
    const target = button.data("focus");
    if (target) {
      /* Modal context focusing */
      $(target).focus();
    } else {
      $("input:visible:enabled:first", event.target).focus();
    }
  });

  /* Copy to clipboard */
  $("[data-clipboard-text]").on("click", function (e) {
    navigator.clipboard
      .writeText(this.getAttribute("data-clipboard-text"))
      .then(
        () => {
          const text =
            this.getAttribute("data-clipboard-message") ||
            gettext("Text copied to clipboard.");
          addAlert(text, "info");
        },
        () => {
          addAlert(gettext("Please press Ctrl+C to copy."), "danger");
        },
      );
    e.preventDefault();
  });

  /* Auto translate source select */
  const select_auto_source = $('input[name="auto_source"]');
  if (select_auto_source.length > 0) {
    select_auto_source.on("change", () => {
      if ($('input[name="auto_source"]:checked').val() === "others") {
        $("#auto_source_others").show();
        $("#auto_source_mt").hide();
      } else {
        $("#auto_source_others").hide();
        $("#auto_source_mt").show();
      }
    });
    select_auto_source.trigger("change");
  }

  /* Override all multiple selects */
  $("select[multiple]").multi({
    enable_search: true,
    search_placeholder: gettext("Search…"),
    non_selected_header: gettext("Available:"),
    selected_header: gettext("Chosen:"),
  });

  /* Slugify name */
  slugify.extend({ ".": "-" });
  $('input[name="slug"]').each(function () {
    const $slug = $(this);
    const $form = $slug.closest("form");
    $form
      .find('input[name="name"]')
      .on("change keypress keydown keyup paste", function () {
        $slug.val(
          slugify($(this).val(), { remove: /[^\w\s-]+/g }).toLowerCase(),
        );
      });
  });

  /* Component update progress */
  $("[data-progress-url]").each(function () {
    const $progress = $(this);
    const $pre = $progress.find("pre");
    const $bar = $progress.find(".progress-bar");
    const url = $progress.data("progress-url");
    const $form = $("#link-post");

    $pre.animate({ scrollTop: $pre.get(0).scrollHeight });

    const progress_completed = () => {
      $bar.width("100%");
      if ($("#progress-redirect").prop("checked")) {
        window.location = $("#progress-return").attr("href");
      }
    };

    const progress_interval = setInterval(() => {
      $.ajax({
        url: url,
        type: "get",
        error: (XMLHttpRequest, textStatus, errorThrown) => {
          if (XMLHttpRequest.status === 404) {
            clearInterval(progress_interval);
            progress_completed();
          }
        },
        success: (data) => {
          $bar.width(`${data.progress}%`);
          $pre.text(data.log);
          $pre.animate({ scrollTop: $pre.get(0).scrollHeight });
          if (data.completed) {
            clearInterval(progress_interval);
            progress_completed();
          }
        },
      });
    }, 1000);

    $("#terminate-task-button").click((e) => {
      fetch(url, {
        method: "DELETE",
        headers: {
          Accept: "application/json",
          "X-CSRFToken": $form.find("input").val(),
        },
      }).then((data) => {
        window.location = $("#progress-return").attr("href");
      });
      e.preventDefault();
    });
  });

  /* Generic messages progress */
  $("[data-task]").each(function () {
    const $message = $(this);
    const $bar = $message.find(".progress-bar");

    const task_interval = setInterval(() => {
      $.get($message.data("task"), (data) => {
        $bar.width(`${data.progress}%`);
        if (data.completed) {
          clearInterval(task_interval);
          $message.text(data.result.message);
        }
      });
    }, 1000);
  });

  /* Disable invalid file format choices */
  $(".invalid-format").each(function () {
    $(this).parent().find("input").attr("disabled", "1");
  });

  // Show the correct toggle button
  if ($(".sort-field").length) {
    const sort_name = $("#query-sort-dropdown span.search-label").text();
    const sort_dropdown_value = $(".sort-field li a")
      .filter(function () {
        return $(this).text() === sort_name;
      })
      .data("sort");
    const sort_value = $("#id_sort_by").val();
    const $label = $(this).find("span.search-icon");
    if (sort_dropdown_value) {
      if (
        sort_value.replace("-", "") === sort_dropdown_value.replace("-", "") &&
        sort_value !== sort_dropdown_value
      ) {
        $label.toggle();
      }
    }
  }

  /* Branch loading */
  $(".branch-loader select[name=component]").change(function () {
    const $this = $(this);
    const $form = $this.closest("form");
    const branches = $form.data("branches");
    const $select = $form.find("select[name=branch]");
    $select.empty();
    $.each(branches[$this.val()], (key, value) => {
      $select.append($("<option></option>").attr("value", value).text(value));
    });
  });

  /* Click to edit position inline. Disable when clicked outside or pressed ESC */
  $("#position-input").on("click", function () {
    const $form = $(this).closest("form");
    $("#position-input").hide();
    $form.find("input[name=offset]").prop("disabled", false);
    $("#position-input-editable").show();
    $("#position-input-editable-input").attr("type", "number").focus();
    document.addEventListener("click", clickedOutsideEditableInput);
    document.addEventListener("keyup", pressedEscape);
  });
  const clickedOutsideEditableInput = (event) => {
    if (
      !$.contains($("#position-input-editable")[0], event.target) &&
      event.target !== $("#position-input")[0]
    ) {
      $("#position-input").show();
      $("#position-input-editable-input").attr("type", "hidden");
      $("#position-input-editable").hide();
      document.emoveEventListener("click", clickedOutsideEditableInput);
      document.removeEventListener("keyup", pressedEscape);
    }
  };
  const pressedEscape = (event) => {
    if (event.key === "Escape" && event.target !== $("#position-input")[0]) {
      $("#position-input").show();
      $("#position-input-editable-input").attr("type", "hidden");
      $("#position-input-editable").hide();
      document.removeEventListener("click", clickedOutsideEditableInput);
      document.removeEventListener("keyup", pressedEscape);
    }
  };

  /* Advanced search */
  $(".search-group li a").click(function () {
    const $this = $(this);
    const $group = $this.closest(".search-group");
    const $button = $group.find("button.search-field");

    $button.attr("data-field", $this.data("field"));

    if ($group.hasClass("sort-field")) {
      $group.find("input[name=sort_by]").val($this.data("sort"));
      if ($this.closest(".result-page-form").length) {
        $this.closest("form").submit();
      }
    }

    if ($group.hasClass("query-field")) {
      $group.find("textarea[name=q]").val($this.data("field"));
      if ($this.closest(".result-page-form").length) {
        const $form = $this.closest("form");
        $form.find("input[name=offset]").prop("disabled", true);
        $form.submit();
      }
    }
    $this.closest("ul").dropdown("toggle");
    return false;
  });
  $(".query-sort-toggle").click(function () {
    const $this = $(this);
    const $input = $this.closest(".search-group").find("input[name=sort_by]");
    const sort_params = $input.val().split(",");
    sort_params.forEach((param, index) => {
      if (param.indexOf("-") !== -1) {
        sort_params[index] = param.replace("-", "");
      } else {
        sort_params[index] = `-${param}`;
      }
    });
    $input.val(sort_params.join(","));
    if ($this.closest(".result-page-form").length) {
      $this.closest("form").submit();
    }
  });
  $(".search-group input")
    .not("#id_q,#id_position,#id_term,#position-input-editable-input")
    .on("keydown", function (event) {
      if (event.key === "Enter") {
        $(this).closest(".input-group").find(".search-add").click();
        event.preventDefault();
        return false;
      }
    });
  $("#id_q").on("input", function (event) {
    const $form = $(this).closest("form");
    $form.find("input[name=offset]").prop("disabled", true);
  });
  $(".search-add").click(function () {
    const group = $(this).closest(".search-group");
    const button = group.find("button.search-field");
    const input = group.find("input");

    if (input.length === 0) {
      $("#id_q").insertAtCaret(` ${button.attr("data-field")} `);
    } else if (input.val() !== "") {
      let prefix = "";
      if (group.find("#is-exact input[type=checkbox]").is(":checked")) {
        prefix = "=";
      }
      $("#id_q").insertAtCaret(
        ` ${button.attr("data-field")}${prefix}${quoteSearch(input.val())} `,
      );
    }
  });
  $(".search-insert").click(function () {
    $("#id_q").insertAtCaret(` ${$(this).closest("tr").find("code").text()} `);
  });

  /* Clickable rows */
  $("tr[data-href]").click(function () {
    window.location = $(this).data("href");
  });

  /* ZIP import - autofill name and slug */
  $("#id_zipcreate_zipfile,#id_doccreate_docfile,#id_image").change(
    function () {
      const $form = $(this).closest("form");
      const target = $form.find("input[name=name]");
      if (this.files.length > 0 && target.val() === "") {
        const name = this.files[0].name;
        target.val(name.substring(0, name.lastIndexOf(".")));
        target.change();
      }
    },
  );

  /* Alert when creating a component */
  $("#form-create-component-branch,#form-create-component-vcs").submit(() => {
    addAlert(
      gettext("Weblate is now scanning the repository, please be patient."),
      "info",
      0,
    );
  });

  /* Username autocompletion */
  const tribute = new Tribute({
    trigger: "@",
    requireLeadingSpace: true,
    menuShowMinLength: 2,
    searchOpts: {
      pre: "​",
      post: "​",
    },
    noMatchTemplate: () => "",
    menuItemTemplate: (item) => {
      const link = document.createElement("a");
      link.innerText = item.string;
      return link.outerHTML;
    },
    values: (text, callback) => {
      $.ajax({
        type: "GET",
        url: `/api/users/?username=${text}`,
        dataType: "json",
        success: (data) => {
          const userMentionList = data.results.map((user) => ({
            value: user.username,
            key: `${user.full_name} (${user.username})`,
          }));
          callback(userMentionList);
        },
        error: (jqXHR, textStatus, errorThrown) => {
          console.error(errorThrown);
        },
      });
    },
  });
  tribute.attach(document.querySelectorAll(".markdown-editor"));
  // biome-ignore lint/complexity/noForEach: TODO
  document.querySelectorAll(".markdown-editor").forEach((editor) => {
    editor.addEventListener("tribute-active-true", (e) => {
      $(".tribute-container").addClass("open");
      $(".tribute-container ul").addClass("dropdown-menu");
    });
  });

  /* forset fields adding */
  $(".add-multifield").on("click", function () {
    const updateElementIndex = (el, prefix, ndx) => {
      const id_regex = new RegExp(`(${prefix}-(\\d+|__prefix__))`);
      const replacement = `${prefix}-${ndx}`;
      if ($(el).prop("for")) {
        $(el).prop("for", $(el).prop("for").replace(id_regex, replacement));
      }
      if (el.id) {
        el.id = el.id.replace(id_regex, replacement);
      }
      if (el.name) {
        el.name = el.name.replace(id_regex, replacement);
      }
    };
    const $this = $(this);
    const $form = $this.parents("form");
    const prefix = $this.data("prefix");
    const blank = $form.find(".multiFieldEmpty");
    const row = blank.clone();
    const totalForms = $(`#id_${prefix}-TOTAL_FORMS`);
    row.removeClass(["multiFieldEmpty", "hidden"]).addClass("multiField");
    row.find("*").each(function () {
      updateElementIndex(this, prefix, totalForms.val());
    });

    row.insertBefore(blank);
    totalForms.val(Number.parseInt(totalForms.val(), 10) + 1);

    return false;
  });

  /* Textarea highlighting */
  Prism.languages.none = {};
  initHighlight(document);

  $(".replace-preview input[type='checkbox']").on("change", function () {
    $(this).closest("tr").toggleClass("warning", this.checked);
  });

  /* Suggestion rejection */
  $(".rejection-reason").on("keydown", function (event) {
    if (event.key === "Enter") {
      $(this).closest("form").find("[name='delete']").click();
      event.preventDefault();
      return false;
    }
  });

  /* Notifications removal */
  // biome-ignore lint/complexity/noForEach: TODO
  document
    .querySelectorAll(".nav-pills > li > a > button.close")
    .forEach((button) => {
      button.addEventListener("click", (e) => {
        const link = button.parentElement;
        // biome-ignore lint/complexity/noForEach: TODO
        document
          .querySelectorAll(`${link.getAttribute("href")} select`)
          .forEach((select) => select.remove());
        //      document.getElementById(link.getAttribute("href").substring(1)).remove();
        link.parentElement.remove();
        /* Activate watched tab */
        $("a[href='#notifications__1']").tab("show");
        addAlert(
          gettext(
            "Notification settings removed, please do not forget to save the changes.",
          ),
          "info",
        );
      });
    });

  /* User autocomplete */
  // biome-ignore lint/complexity/noForEach: TODO
  document
    .querySelectorAll(".user-autocomplete")
    .forEach((autoCompleteInput) => {
      const autoCompleteJS = new autoComplete({
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
              if (autoCompleteInput.value.length) autoCompleteJS.start();
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
      class: "autoComplete dropdown-menu",
    },
    resultItem: {
      class: "autoComplete_result",
      element: (item, data) => {
        item.textContent = "";
        const child = document.createElement("a");
        child.setAttribute("href", data.value.url);
        child.textContent = `${data.value.name} `;
        const category = document.createElement("span");
        category.setAttribute("class", "badge");
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
          if (siteSearch.input.value.length) siteSearch.start();
        },
      },
    },
  });

  /* Workflow customization form */
  // biome-ignore lint/complexity/noForEach: TODO
  document.querySelectorAll("#id_workflow-enable").forEach((enableInput) => {
    enableInput.addEventListener("click", () => {
      if (!enableInput.checked) {
        document.getElementById("workflow-enable-target").style.visibility =
          "hidden";
        document.getElementById("workflow-enable-target").style.opacity = 0;
      } else {
        document.getElementById("workflow-enable-target").style.visibility =
          "visible";
        document.getElementById("workflow-enable-target").style.opacity = 1;
      }
    });
    enableInput.dispatchEvent(new Event("click"));
  });

  /* Move current translation into the view */
  $('a[data-toggle="tab"][href="#nearby"]').on("shown.bs.tab", (e) => {
    document.querySelector("#nearby .current_translation").scrollIntoView({
      block: "nearest",
      inline: "nearest",
      behavior: "smooth",
    });
  });

  // biome-ignore lint/complexity/noForEach: TODO
  document.querySelectorAll("[data-visibility]").forEach((toggle) => {
    toggle.addEventListener("click", (event) => {
      // biome-ignore lint/complexity/noForEach: TODO
      document
        .querySelectorAll(toggle.getAttribute("data-visibility"))
        .forEach((element) => {
          element.classList.toggle("visible");
        });
    });
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
});
