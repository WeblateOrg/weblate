// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

(() => {
  const EditorBase = WLT.Editor.Base;

  const $window = $(window);
  const $document = $(document);

  function ZenEditor() {
    EditorBase.call(this);

    $window.scroll(() => {
      const $loadingNext = $("#loading-next");
      const loader = $("#zen-load");

      if ($window.scrollTop() >= $document.height() - 2 * $window.height()) {
        if (
          $("#last-section").length > 0 ||
          $loadingNext.css("display") !== "none"
        ) {
          return;
        }
        $loadingNext.show();

        loader.data("offset", 20 + Number.parseInt(loader.data("offset"), 10));

        $.get(
          `${loader.attr("href")}&offset=${loader.data("offset")}`,
          (data) => {
            $loadingNext.hide();

            $(".zen tfoot").before(data);

            this.init();
            initHighlight(document);
          },
        );
      }
    });

    /*
     * Ensure current editor is reasonably located in the window
     * - show whole element if moving back
     * - scroll down if in bottom half of the window
     */
    $document.on("focus", ".zen .translation-editor", function () {
      const editor = $(this);
      const container = editor.closest(".translator").closest("tr");
      const current = $window.scrollTop();
      const rowOffset = $(this).closest("tbody").offset().top;
      if (rowOffset < current || rowOffset - current > $window.height() / 2) {
        // Scroll to view source string
        $([document.documentElement, document.body]).animate(
          {
            scrollTop: rowOffset,
          },
          100,
        );
        // Stick the editor to the bottom of the screen when out of view
        $(".sticky-bottom").removeClass("sticky-bottom"); // Hide previous
        container?.addClass("sticky-bottom");
        container.find(".hide-sticky").on("click", () => {
          container.removeClass("sticky-bottom");
        });
      }
    });

    Mousetrap.bindGlobal("mod+end", (_e) => {
      $(".zen-unit:last").find(".translation-editor:first").focus();
      return false;
    });
    Mousetrap.bindGlobal("mod+home", (_e) => {
      $(".zen-unit:first").find(".translation-editor:first").focus();
      return false;
    });
    Mousetrap.bindGlobal("mod+pagedown", (_e) => {
      const focus = $(":focus");

      if (focus.length === 0) {
        $(".zen-unit:first").find(".translation-editor:first").focus();
      } else {
        focus
          .closest(".zen-unit")
          .next()
          .find(".translation-editor:first")
          .focus();
      }
      return false;
    });
    Mousetrap.bindGlobal("mod+pageup", (_e) => {
      const focus = $(":focus");

      if (focus.length === 0) {
        $(".zen-unit:last").find(".translation-editor:first").focus();
      } else {
        focus
          .closest(".zen-unit")
          .prev()
          .find(".translation-editor:first")
          .focus();
      }
      return false;
    });

    $window.on("beforeunload", () => {
      if ($(".translation-modified").length > 0) {
        return gettext(
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
    $(".zen-horizontal .translator").each(function () {
      const $this = $(this);
      const tdHeight = $this.height();
      let editorHeight = 0;
      const contentHeight = $this.find("form").height();
      const $editors = $this.find(".translation-editor");
      $editors.each(function () {
        const $editor = $(this);
        editorHeight += $editor.height();
      });
      /* There is 10px padding */
      $editors.css(
        "min-height",
        `${
          (tdHeight - (contentHeight - editorHeight - 10)) / $editors.length
        }px`,
      );
    });
  };

  /* Handlers */

  $document.on("focusin", ".translation-editor", function () {
    const $this = $(this);
    const $row = $this.closest("tr");
    const checksum = $row.find("[name=checksum]").val();
    const statusdiv = $(`#status-${checksum}`);
    const focusTimeout = $row.data("focus-timer");
    // Focus returned quickly; cancel pending save
    if (focusTimeout) {
      statusdiv.removeClass("unit-state-save-timeout");
      clearTimeout(focusTimeout);
      $row.removeData("focus-timer");
    }
  });

  $document.on("focusout", ".translation-editor", function () {
    const $this = $(this);
    const $row = $this.closest("tr");
    const checksum = $row.find("[name=checksum]").val();
    const statusdiv = $(`#status-${checksum}`);
    // Editor lost focus and has changes
    if ($this.hasClass("has-changes")) {
      statusdiv.addClass("unit-state-save-timeout");
      const focusTimeout = setTimeout(() => {
        $row.removeData("focus-timer");
        handleTranslationChange.call($this[0]);
      }, 1000); // Grace period before saving
      $row.data("focus-timer", focusTimeout);
    }
  });

  // Allow immediate saves for checkbox/radio changes
  $document.on("change", ".fuzzy_checkbox", handleTranslationChange);
  $document.on("change", ".review_radio", handleTranslationChange);

  function handleTranslationChange() {
    const $this = $(this);
    const $row = $this.closest("tr");
    const checksum = $row.find("[name=checksum]").val();
    const statusdiv = $(`#status-${checksum}`);
    const form = $row.find("form");
    const payload = form.serialize();
    const lastPayload = statusdiv.data("last-payload");

    // Guard: skip if a save is already happening
    if (statusdiv.hasClass("unit-state-saving")) {
      setTimeout(() => {
        handleTranslationChange.call($this[0]); // Reinvoke
      }, 100);
      return;
    }

    // First save
    if (lastPayload === undefined) {
      statusdiv.data("last-payload", payload);
    }
    // Guard: skip if nothing has changed
    if (payload === lastPayload) {
      statusdiv.removeClass("unit-state-save-timeout");
      return;
    }

    $row.addClass("translation-modified");
    statusdiv.addClass("unit-state-saving");
    statusdiv.data("last-payload", payload);
    $.ajax({
      type: "POST",
      url: form.attr("action"),
      data: payload,
      dataType: "json",
      error: (_jqXhr, _textStatus, errorThrown) => {
        addAlert(errorThrown);
      },
      success: (data) => {
        statusdiv.attr("class", `unit-state-cell ${data.unit_state_class}`);
        statusdiv.attr("title", data.unit_state_title);

        $.each(data.messages, (_i, val) => {
          addAlert(val.text, val.kind);
        });

        $row.removeClass("translation-modified").addClass("translation-saved");
        $row.find("#unsaved-label").remove();
        $row.find(".translation-editor").removeClass("has-changes");

        if (data.translationsum !== "") {
          $row.find("input[name=translationsum]").val(data.translationsum);
        }
      },
      complete: () => {
        statusdiv.removeClass("unit-state-saving");
        statusdiv.removeClass("unit-state-save-timeout");
        $row.removeData("save-timer");
      },
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    new ZenEditor();
  });
})();
