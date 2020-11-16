(function () {
  var EditorBase = WLT.Editor.Base;

  var $window = $(window);
  var $document = $(document);

  function ZenEditor() {
    EditorBase.call(this);

    $window.scroll(() => {
      var $loadingNext = $("#loading-next");
      var loader = $("#zen-load");

      if ($window.scrollTop() >= $document.height() - 2 * $window.height()) {
        if (
          $("#last-section").length > 0 ||
          $loadingNext.css("display") !== "none"
        ) {
          return;
        }
        $loadingNext.show();

        loader.data("offset", 20 + parseInt(loader.data("offset"), 10));

        $.get(
          loader.attr("href") + "&offset=" + loader.data("offset"),
          (data) => {
            $loadingNext.hide();

            $(".zen tfoot").before(data);

            this.init();
          }
        );
      }
    });

    $document.on("change", ".fuzzy_checkbox", handleTranslationChange);
    $document.on("change", ".review_radio", handleTranslationChange);

    Mousetrap.bindGlobal("mod+end", function (e) {
      $(".zen-unit:last").find(".translation-editor:first").focus();
      return false;
    });
    Mousetrap.bindGlobal("mod+home", function (e) {
      $(".zen-unit:first").find(".translation-editor:first").focus();
      return false;
    });
    Mousetrap.bindGlobal("mod+pagedown", function (e) {
      var focus = $(":focus");

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
    Mousetrap.bindGlobal("mod+pageup", function (e) {
      var focus = $(":focus");

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

    $window.on("beforeunload", function () {
      if ($(".translation-modified").length > 0) {
        return gettext(
          "There are some unsaved changes, are you sure you want to leave?"
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
      if (this.ZenInitDone) {
        return;
      }
      var $this = $(this);
      var tdHeight = $this.height();
      var editorHeight = 0;
      var contentHeight = $this.find("form").height();
      var $editors = $this.find(".translation-editor");
      $editors.each(function (idx, textarea) {
        var codemirror = textarea.CodeMirror;
        var $editor = $(codemirror.getWrapperElement());
        /* Calculate editor height */
        editorHeight += $editor.height();

        /*
         * Ensure current editor is reasonably located in the window
         * - show whole element if moving back
         * - scroll down if in bottom half of the window
         */
        codemirror.on("focus", function () {
          var current = $window.scrollTop();
          var rowOffset = $editor.closest("tbody").offset().top;
          if (
            rowOffset < current ||
            rowOffset - current > $window.height() / 2
          ) {
            $([document.documentElement, document.body]).animate(
              {
                scrollTop: rowOffset,
              },
              100
            );
          }
        });

        codemirror.on("blur", handleTranslationChange);
      });

      $editors.each(function (idx, textarea) {
        let height =
          (tdHeight - (contentHeight - editorHeight)) / $editors.length;
        textarea.CodeMirror.getScrollerElement().style.minHeight =
          height + "px";
      });
      this.ZenInitDone = true;
    });
  };

  /* Handlers */

  function handleTranslationChange(cm) {
    var $this;
    if (typeof cm.getWrapperElement !== "undefined") {
      let doc = cm.getDoc();
      if (doc.isClean()) {
        return;
      }
      doc.markClean();
      $this = $(cm.getWrapperElement());
    } else {
      $this = $(this);
    }
    var $row = $this.closest("tr");
    var checksum = $row.find("[name=checksum]").val();

    /* Wait until previous operation on this field is completed */
    if ($("#loading-" + checksum).is(":visible")) {
      setTimeout(function () {
        $this.trigger("change");
      }, 100);
      return;
    }

    $row.addClass("translation-modified");

    var form = $row.find("form");
    var statusdiv = $("#status-" + checksum).hide();
    var loadingdiv = $("#loading-" + checksum).show();
    $.ajax({
      type: "POST",
      url: form.attr("action"),
      data: form.serialize(),
      dataType: "json",
      error: function (jqXHR, textStatus, errorThrown) {
        addAlert(errorThrown);
      },
      success: function (data) {
        loadingdiv.hide();
        statusdiv.show();
        if (data.unit_flags.length > 0) {
          $(statusdiv.children()[0]).attr(
            "class",
            "state-icon " + data.unit_flags.join(" ")
          );
        }
        $.each(data.messages, function (i, val) {
          addAlert(val.text);
        });
        $row.removeClass("translation-modified").addClass("translation-saved");
        if (data.translationsum !== "") {
          $row.find("input[name=translationsum]").val(data.translationsum);
        }
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    new ZenEditor();
  });
})();
