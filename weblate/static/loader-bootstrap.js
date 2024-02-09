// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

var loading = [];

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
    $("#loading-" + sel).show();
  }
  loading[sel] += 1;
}

function decreaseLoading(sel) {
  loading[sel] -= 1;
  if (loading[sel] === 0) {
    $("#loading-" + sel).hide();
  }
}

function addAlert(message, kind = "danger", delay = 3000) {
  var alerts = $("#popup-alerts");
  var e = $(
    '<div class="alert alert-dismissible" role="alert"><button type="button" class="close" data-dismiss="alert" aria-label="Close"><span aria-hidden="true">&times;</span></button></div>',
  );
  e.addClass("alert-" + kind);
  e.append(new Text(message));
  e.hide();
  alerts.show().append(e);
  e.slideDown(200);
  e.on("closed.bs.alert", function () {
    if (alerts.find(".alert").length == 0) {
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
        let sel = document.selection.createRange();

        sel.text = myValue;
        this.focus();
      } else if (this.selectionStart || this.selectionStart === 0) {
        //For browsers like Firefox and Webkit based
        let startPos = this.selectionStart;
        let endPos = this.selectionEnd;
        let scrollTop = this.scrollTop;

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
  var $target = $(evt.target);
  var $form = $target.closest("form");

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
  var pk = this.getAttribute("data-pk");
  var form = $("#screenshot-add-form");

  $("#add-source").val(pk);
  $.ajax({
    type: "POST",
    url: form.attr("action"),
    data: form.serialize(),
    dataType: "json",
    success: function () {
      var list = $("#sources-listing");
      $.get(list.data("href"), function (data) {
        list.find("table").replaceWith(data);
      });
    },
    error: function (jqXHR, textStatus, errorThrown) {
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

function isNumber(n) {
  return !isNaN(parseFloat(n)) && isFinite(n);
}

function extractText(cell) {
  var value = cell.getAttribute("data-value");
  if (value !== null) {
    return value;
  }
  return $.text(cell);
}

function compareCells(a, b) {
  if (typeof a === "number" && typeof b === "number") {
  } else if (a.indexOf("%") !== -1 && b.indexOf("%") !== -1) {
    a = parseFloat(a.replace(",", "."));
    b = parseFloat(b.replace(",", "."));
  } else if (isNumber(a) && isNumber(b)) {
    a = parseFloat(a.replace(",", "."));
    b = parseFloat(b.replace(",", "."));
  } else if (typeof a === "string" && typeof b === "string") {
    a = a.toLowerCase();
    b = b.toLowerCase();
  }
  if (a == b) {
    return 0;
  }
  if (a > b) {
    return 1;
  }
  return -1;
}

function loadTableSorting() {
  $("table.sort").each(function () {
    var table = $(this),
      tbody = table.find("tbody"),
      thead = table.find("thead"),
      thIndex = 0;

    $(this)
      .find("thead th")
      .each(function () {
        var th = $(this),
          inverse = 1;

        // handle colspan
        if (th.attr("colspan")) {
          thIndex += parseInt(th.attr("colspan"), 10) - 1;
        }
        // skip empty cells and cells with icon (probably already processed)
        if (
          th.text() !== "" &&
          !th.hasClass("sort-init") &&
          !th.hasClass("sort-skip")
        ) {
          // Store index copy
          let myIndex = thIndex;
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
              .sort(function (a, b) {
                var $a = $(a),
                  $b = $(b);
                var a_parent = $a.data("parent"),
                  b_parent = $b.data("parent");
                if (a_parent) {
                  $a = tbody.find("#" + a_parent);
                }
                if (b_parent) {
                  $b = tbody.find("#" + b_parent);
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
  return fmt.replace(/%s/g, function () {
    return String(obj.shift());
  });
}

function load_matrix() {
  var $loadingNext = $("#loading-next");
  var $loader = $("#matrix-load");
  var offset = parseInt($loader.data("offset"));

  if ($("#last-section").length > 0 || $loadingNext.css("display") !== "none") {
    return;
  }
  $loadingNext.show();

  $loader.data("offset", 20 + offset);

  $.get($loader.attr("href") + "&offset=" + offset, function (data) {
    $loadingNext.hide();
    $(".matrix tbody").append(data);
  });
}

function adjustColspan() {
  $("table.autocolspan").each(function () {
    var $this = $(this);
    var numOfVisibleCols = $this.find("thead th:visible").length;
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
    return '"' + value + '"';
  }
  if (value.indexOf("'") === -1) {
    return "'" + value + "'";
  }
  /* We should do some escaping here */
  return value;
}

function initHighlight(root) {
  if (typeof ResizeObserver === "undefined") {
    return;
  }
  root.querySelectorAll("textarea[name='q']").forEach((input) => {
    var parent = input.parentElement;
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
    var wrapper = document.createElement("div");
    wrapper.setAttribute("class", "editor-wrap");

    /* Inject wrapper */
    parent.replaceChild(wrapper, input);

    /* Create highlighter */
    var highlight = document.createElement("div");
    highlight.setAttribute("class", "highlighted-output");
    highlight.setAttribute("role", "status");
    wrapper.appendChild(highlight);

    /* Add input to wrapper */
    wrapper.appendChild(input);

    var syncContent = function () {
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
      for (let entry of entries) {
        if (entry.target === input) {
          // match the height and width of the output area to the input area
          highlight.style.height = input.offsetHeight + "px";
          highlight.style.width = input.offsetWidth + "px";
        }
      }
    });

    resizeObserver.observe(input);
  });
  root.querySelectorAll(".highlight-editor").forEach(function (editor) {
    var parent = editor.parentElement;
    var hasFocus = editor == document.activeElement;

    if (parent.classList.contains("editor-wrap")) {
      return;
    }

    var mode = editor.getAttribute("data-mode");

    /* Create wrapper element */
    var wrapper = document.createElement("div");
    wrapper.setAttribute("class", "editor-wrap");

    /* Inject wrapper */
    parent.replaceChild(wrapper, editor);

    /* Create highlighter */
    var highlight = document.createElement("div");
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
    var languageMode = Prism.languages[mode];
    if (editor.classList.contains("translation-editor")) {
      let placeables = editor.getAttribute("data-placeables");
      /* This should match WHITESPACE_REGEX in weblate/trans/templatetags/translations.py */
      let whitespace_regex = new RegExp(
        [
          "  +|(^) +| +(?=$)| +\n|\n +|\t|",
          "\u00A0|\u00AD|\u1680|\u2000|\u2001|",
          "\u2002|\u2003|\u2004|\u2005|",
          "\u2006|\u2007|\u2008|\u2009|",
          "\u200A|\u202F|\u205F|\u3000",
        ].join(""),
      );
      let extension = {
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
      for (var key in languageMode) {
        if (languageMode.hasOwnProperty(key)) {
          extension[key] = Prism.util.clone(languageMode[key]);
        }
      }
      languageMode = extension;
    }
    var syncContent = function () {
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
      for (let entry of entries) {
        if (entry.target === editor) {
          // match the height and width of the output area to the input area
          highlight.style.height = editor.offsetHeight + "px";
          highlight.style.width = editor.offsetWidth + "px";
        }
      }
    });

    resizeObserver.observe(editor);
    /* Autosizing */
    autosize(editor);
  });
}

$(function () {
  var $window = $(window),
    $document = $(document);

  adjustColspan();
  $window.resize(adjustColspan);
  $document.on("shown.bs.tab", adjustColspan);

  /* AJAX loading of tabs/pills */
  $document.on(
    "show.bs.tab",
    '[data-toggle="tab"][data-href], [data-toggle="pill"][data-href]',
    function (e) {
      var $target = $(e.target);
      var $content = $($target.attr("href"));
      if ($target.data("loaded")) {
        return;
      }
      if ($content.find(".panel-body").length > 0) {
        $content = $content.find(".panel-body");
      }
      $content.load($target.data("href"), function (responseText, status, xhr) {
        if (status !== "success") {
          var msg = gettext("Error while loading page:");
          $content.text(
            msg +
              " " +
              xhr.statusText +
              " (" +
              xhr.status +
              "): " +
              responseText,
          );
        }
        $target.data("loaded", 1);
        loadTableSorting();
      });
    },
  );

  if ($("#form-activetab").length > 0) {
    $document.on("show.bs.tab", '[data-toggle="tab"]', function (e) {
      var $target = $(e.target);
      $("#form-activetab").attr("value", $target.attr("href"));
    });
  }

  /* Form automatic submission */
  $("form.autosubmit select").change(function () {
    $("form.autosubmit").submit();
  });

  var activeTab;

  /* Load correct tab */
  if (location.hash !== "") {
    /* From URL hash */
    var separator = location.hash.indexOf("__");
    if (separator != -1) {
      activeTab = $(
        '.nav [data-toggle=tab][href="' +
          location.hash.substr(0, separator) +
          '"]',
      );
      if (activeTab.length) {
        activeTab.tab("show");
      }
    }
    activeTab = $('.nav [data-toggle=tab][href="' + location.hash + '"]');
    if (activeTab.length) {
      activeTab.tab("show");
      window.scrollTo(0, 0);
    } else {
      let anchor = document.getElementById(location.hash.substr(1));
      if (anchor !== null) {
        anchor.scrollIntoView();
      }
    }
  } else if (
    $(".translation-tabs").length > 0 &&
    Cookies.get("translate-tab")
  ) {
    /* From cookie */
    activeTab = $(
      '[data-toggle=tab][href="' + Cookies.get("translate-tab") + '"]',
    );
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
  window.addEventListener("popstate", function (e) {
    if (location.hash !== "") {
      activeTab = $('[data-toggle=tab][href="' + location.hash + '"]');
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
  var formErrors = $("div.has-error");
  if (formErrors.length > 0) {
    var tab = formErrors.closest("div.tab-pane");
    if (tab.length > 0) {
      $('[data-toggle=tab][href="#' + tab.attr("id") + '"]').tab("show");
    }
  }

  /* Announcement discard */
  $(".alert").on("close.bs.alert", function () {
    var $this = $(this);
    var $form = $("#link-post");

    var action = this.getAttribute("data-action");

    if (action) {
      $.ajax({
        type: "POST",
        url: action,
        data: {
          csrfmiddlewaretoken: $form.find("input").val(),
          id: this.getAttribute("data-id"),
        },
        error: function (jqXHR, textStatus, errorThrown) {
          addAlert(errorThrown);
        },
      });
    }
  });

  /* Widgets selector */
  $(".select-tab").on("change", function (e) {
    $(this).parent().find(".tab-pane").removeClass("active");
    $("#" + $(this).val()).addClass("active");
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
    $window.scroll(function () {
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
    .click(function (e) {
      e.stopPropagation();
    });

  $document.on("click", ".link-post", function () {
    var $form = $("#link-post");
    var $this = $(this);

    $form.attr("action", $this.attr("data-href"));
    $.each($this.data("params"), function (name, value) {
      var elm = $("<input>")
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
    var $this = $(this);
    $("#imagepreview").attr("src", $this.attr("href"));
    $("#screenshotModal").text($this.attr("title"));

    var detailsLink = $("#modalDetailsLink");
    detailsLink.attr("href", this.getAttribute("data-details-url"));
    if (this.getAttribute("data-can-edit")) {
      detailsLink.text(detailsLink.getAttribute("data-edit-text"));
    }

    $("#imagemodal").modal("show");
    return false;
  });
  /* Screenshot management */
  $("#screenshots-search,#screenshots-auto").click(function () {
    var $this = $(this);

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
    var $form = $(this);

    if ($form.data("submitted") === true) {
      // Previously submitted - don't submit again
      e.preventDefault();
    } else {
      // Mark it so that the next submit can be ignored
      $form.data("submitted", true);
    }
  });
  /* Reset submitted flag when leaving the page, so that it is not set when going back in history */
  $window.on("pagehide", function () {
    $("form:not(.double-submission)").data("submitted", false);
  });

  /* Client side form persistence */
  var $forms = $("[data-persist]");
  if ($forms.length > 0 && window.localStorage) {
    /* Load from local storage */
    $forms.each(function () {
      var $this = $(this);
      var storedValue = window.localStorage[$this.data("persist")];
      if (storedValue) {
        storedValue = JSON.parse(storedValue);
        $.each(storedValue, function (key, value) {
          var target = $this.find("[name=" + key + "]");
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
      var data = {};
      var $this = $(this);

      $this.find(":checkbox").each(function () {
        var $this = $(this);

        data[$this.attr("name")] = $this.prop("checked");
      });
      $this.find("select").each(function () {
        var $this = $(this);

        data[$this.attr("name")] = $this.val();
      });
      window.localStorage[$this.data("persist")] = JSON.stringify(data);
    });
  }

  /* Focus first input in modal */
  $(document).on("shown.bs.modal", function (event) {
    var button = $(event.relatedTarget); // Button that triggered the modal
    var target = button.data("focus");
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
          var text =
            this.getAttribute("data-clipboard-message") ||
            gettext("Text copied to clipboard.");
          addAlert(text, (kind = "info"));
        },
        () => {
          addAlert(gettext("Please press Ctrl+C to copy."), (kind = "danger"));
        },
      );
    e.preventDefault();
  });

  /* Auto translate source select */
  var select_auto_source = $('input[name="auto_source"]');
  if (select_auto_source.length > 0) {
    select_auto_source.on("change", function () {
      if ($('input[name="auto_source"]:checked').val() == "others") {
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
    var $slug = $(this);
    var $form = $slug.closest("form");
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
    var $progress = $(this);
    var $pre = $progress.find("pre"),
      $bar = $progress.find(".progress-bar"),
      url = $progress.data("progress-url");
    var $form = $("#link-post");

    $pre.animate({ scrollTop: $pre.get(0).scrollHeight });

    var progress_completed = function () {
      $bar.width("100%");
      if ($("#progress-redirect").prop("checked")) {
        window.location = $("#progress-return").attr("href");
      }
    };

    var progress_interval = setInterval(function () {
      $.ajax({
        url: url,
        type: "get",
        error: function (XMLHttpRequest, textStatus, errorThrown) {
          if (XMLHttpRequest.status == 404) {
            clearInterval(progress_interval);
            progress_completed();
          }
        },
        success: function (data) {
          $bar.width(data.progress + "%");
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
    var $message = $(this);
    var $bar = $message.find(".progress-bar");

    var task_interval = setInterval(function () {
      $.get($message.data("task"), function (data) {
        $bar.width(data.progress + "%");
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
    var sort_name = $("#query-sort-dropdown span.search-label").text();
    var sort_dropdown_value = $(".sort-field li a")
      .filter(function () {
        return $(this).text() == sort_name;
      })
      .data("sort");
    var sort_value = $("#id_sort_by").val();
    var $label = $(this).find("span.search-icon");
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
    var $this = $(this);
    var $form = $this.closest("form");
    var branches = $form.data("branches");
    var $select = $form.find("select[name=branch]");
    $select.empty();
    $.each(branches[$this.val()], function (key, value) {
      $select.append($("<option></option>").attr("value", value).text(value));
    });
  });

  /* Click to edit position inline. Disable when clicked outside or pressed ESC */
  $("#position-input").on("click", function () {
    var $form = $(this).closest("form");
    $("#position-input").hide();
    $form.find("input[name=offset]").prop("disabled", false);
    $("#position-input-editable").show();
    $("#position-input-editable-input").attr("type", "number").focus();
    document.addEventListener("click", clickedOutsideEditableInput);
    document.addEventListener("keyup", pressedEscape);
  });
  var clickedOutsideEditableInput = function (event) {
    if (
      !$.contains($("#position-input-editable")[0], event.target) &&
      event.target != $("#position-input")[0]
    ) {
      $("#position-input").show();
      $("#position-input-editable-input").attr("type", "hidden");
      $("#position-input-editable").hide();
      document.emoveEventListener("click", clickedOutsideEditableInput);
      document.removeEventListener("keyup", pressedEscape);
    }
  };
  var pressedEscape = function (event) {
    if (event.key == "Escape" && event.target != $("#position-input")[0]) {
      $("#position-input").show();
      $("#position-input-editable-input").attr("type", "hidden");
      $("#position-input-editable").hide();
      document.removeEventListener("click", clickedOutsideEditableInput);
      document.removeEventListener("keyup", pressedEscape);
    }
  };

  /* Advanced search */
  $(".search-group li a").click(function () {
    var $this = $(this);
    var $group = $this.closest(".search-group");
    var $button = $group.find("button.search-field");

    $button.attr("data-field", $this.data("field"));
    var $title = $this.find("span.title");
    var text = $this.text();
    if ($title.length) {
      text = $title.text();
    }
    $group.find("span.search-label").text(text);

    if ($group.hasClass("sort-field")) {
      $group.find("input[name=sort_by]").val($this.data("sort"));
      if ($this.closest(".result-page-form").length) {
        $this.closest("form").submit();
      }
    }

    if ($group.hasClass("query-field")) {
      $group.find("textarea[name=q]").val($this.data("field"));
      if ($this.closest(".result-page-form").length) {
        var $form = $this.closest("form");
        $form.find("input[name=offset]").prop("disabled", true);
        $form.submit();
      }
    }
    $this.closest("ul").dropdown("toggle");
    return false;
  });
  $(".query-sort-toggle").click(function () {
    var $this = $(this);
    var $input = $this.closest(".search-group").find("input[name=sort_by]");
    var sort_params = $input.val().split(",");
    sort_params.forEach(function (param, index) {
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
    var $form = $(this).closest("form");
    $form.find("input[name=offset]").prop("disabled", true);
  });
  $(".search-add").click(function () {
    var group = $(this).closest(".search-group");
    var button = group.find("button.search-field");
    var input = group.find("input");

    if (input.length === 0) {
      $("#id_q").insertAtCaret(" " + button.attr("data-field") + " ");
    } else if (input.val() !== "") {
      var prefix = "";
      if (group.find("#is-exact input[type=checkbox]").is(":checked")) {
        prefix = "=";
      }
      $("#id_q").insertAtCaret(
        " " +
          button.attr("data-field") +
          prefix +
          quoteSearch(input.val()) +
          " ",
      );
    }
  });
  $(".search-insert").click(function () {
    $("#id_q").insertAtCaret(
      " " + $(this).closest("tr").find("code").text() + " ",
    );
  });

  /* Clickable rows */
  $("tr[data-href]").click(function () {
    window.location = $(this).data("href");
  });

  /* ZIP import - autofill name and slug */
  $("#id_zipcreate_zipfile,#id_doccreate_docfile,#id_image").change(
    function () {
      var $form = $(this).closest("form");
      var target = $form.find("input[name=name]");
      if (this.files.length > 0 && target.val() === "") {
        var name = this.files[0].name;
        target.val(name.substring(0, name.lastIndexOf(".")));
        target.change();
      }
    },
  );

  /* Alert when creating a component */
  $("#form-create-component-branch,#form-create-component-vcs").submit(
    function () {
      addAlert(
        gettext("Weblate is now scanning the repository, please be patient."),
        (kind = "info"),
        (delay = 0),
      );
    },
  );

  /* Username autocompletion */
  var tribute = new Tribute({
    trigger: "@",
    requireLeadingSpace: true,
    menuShowMinLength: 2,
    searchOpts: {
      pre: "​",
      post: "​",
    },
    noMatchTemplate: function () {
      return "";
    },
    menuItemTemplate: function (item) {
      let link = document.createElement("a");
      link.innerText = item.string;
      return link.outerHTML;
    },
    values: (text, callback) => {
      $.ajax({
        type: "GET",
        url: `/api/users/?username=${text}`,
        dataType: "json",
        success: function (data) {
          var userMentionList = data.results.map(function (user) {
            return {
              value: user.username,
              key: `${user.full_name} (${user.username})`,
            };
          });
          callback(userMentionList);
        },
        error: function (jqXHR, textStatus, errorThrown) {
          console.error(errorThrown);
        },
      });
    },
  });
  tribute.attach(document.querySelectorAll(".markdown-editor"));
  document.querySelectorAll(".markdown-editor").forEach((editor) => {
    editor.addEventListener("tribute-active-true", function (e) {
      $(".tribute-container").addClass("open");
      $(".tribute-container ul").addClass("dropdown-menu");
    });
  });

  /* forset fields adding */
  $(".add-multifield").on("click", function () {
    const updateElementIndex = function (el, prefix, ndx) {
      const id_regex = new RegExp("(" + prefix + "-(\\d+|__prefix__))");
      const replacement = prefix + "-" + ndx;
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
    var $this = $(this);
    var $form = $this.parents("form");
    var prefix = $this.data("prefix");
    var blank = $form.find(".multiFieldEmpty");
    var row = blank.clone();
    var totalForms = $("#id_" + prefix + "-TOTAL_FORMS");
    row.removeClass(["multiFieldEmpty", "hidden"]).addClass("multiField");
    row.find("*").each(function () {
      updateElementIndex(this, prefix, totalForms.val());
    });

    row.insertBefore(blank);
    totalForms.val(parseInt(totalForms.val(), 10) + 1);

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
  document
    .querySelectorAll(".nav-pills > li > a > button.close")
    .forEach((button) => {
      button.addEventListener("click", (e) => {
        let link = button.parentElement;
        document
          .querySelectorAll(link.getAttribute("href") + " select")
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
  document
    .querySelectorAll(".user-autocomplete")
    .forEach((autoCompleteInput) => {
      let autoCompleteJS = new autoComplete({
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
            let child = document.createElement("a");
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
  let siteSearch = new autoComplete({
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
        let child = document.createElement("a");
        child.setAttribute("href", data.value.url);
        child.textContent = `${data.value.name} `;
        let category = document.createElement("span");
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

  /* Move current translation into the view */
  $('a[data-toggle="tab"][href="#nearby"]').on("shown.bs.tab", function (e) {
    document.querySelector("#nearby .current_translation").scrollIntoView({
      block: "nearest",
      inline: "nearest",
      behavior: "smooth",
    });
  });

  document.querySelectorAll("[data-visibility]").forEach((toggle) => {
    toggle.addEventListener("click", (event) => {
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
