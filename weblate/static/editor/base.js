var WLT = WLT || {};

WLT.Config = (function () {
  return {
    IS_MAC: /Mac|iPod|iPhone|iPad/.test(navigator.platform),
  };
})();

WLT.Utils = (function () {
  return {
    getNumericKey: function (idx) {
      return (idx + 1) % 10;
    },

    markFuzzy: function ($el) {
      /* Standard worflow */
      $el.find('input[name="fuzzy"]').prop("checked", true);
      /* Review workflow */
      $el.find('input[name="review"][value="10"]').prop("checked", true);
    },

    markTranslated: function ($el) {
      /* Standard worflow */
      $el.find('input[name="fuzzy"]').prop("checked", false);
      /* Review workflow */
      $el.find('input[name="review"][value="20"]').prop("checked", true);
    },
  };
})();

WLT.Editor = (function () {
  var lastEditor = null;

  function EditorBase() {
    var translationAreaSelector = ".translation-editor";

    this.$editor = $(".js-editor");
    /* Only insert actual translation editor, not a popup for adding variant */
    this.$translationArea = $(".translator .translation-editor");

    this.$editor.on("input", translationAreaSelector, (e) => {
      WLT.Utils.markTranslated($(e.target).closest("form"));
    });

    this.$editor.on("focusin", translationAreaSelector, function () {
      lastEditor = $(this);
    });

    /* Count characters */
    this.$editor.on("input", translationAreaSelector, (e) => {
      var textarea = e.target;
      var editor = textarea.parentElement.parentElement;
      var counter = editor.querySelector(".length-indicator");
      var classToggle = editor.classList;

      var limit = parseInt(counter.getAttribute("data-max"));
      var length = textarea.value.length;

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
    this.$editor.on("click", "[data-clone-text]", function (e) {
      var $this = $(this);
      var cloneText = $this.data("clone-text");

      var row = $this.closest(".zen-unit");
      if (row.length === 0) {
        row = $this.closest(".translator");
      }
      var editors = row.find(".translation-editor");
      var $document = $(document);
      if (editors.length == 1) {
        editors.replaceValue(cloneText);
      } else {
        addAlert(
          gettext("Please select target plural by clicking."),
          (kind = "info")
        );
        editors.addClass("editor-click-select");
        editors.click(function () {
          $(this).replaceValue(cloneText);
          editors.removeClass("editor-click-select");
          editors.off("click");
          $document.off("click");
          return false;
        });
        $document.on("click", function () {
          editors.removeClass("editor-click-select");
          editors.off("click");
          $document.off("click");
          return false;
        });
      }
      WLT.Utils.markFuzzy($this.closest("form"));
      return false;
    });

    /* Direction toggling */
    this.$editor.on("change", ".direction-toggle", function () {
      var $this = $(this);
      var direction = $this.find("input").val();
      var container = $this.closest(".translation-item");

      container.find(".translation-editor").attr("dir", direction);
      container.find(".highlighted-output").attr("dir", direction);
    });

    /* Special characters */
    this.$editor.on("click", ".specialchar", function (e) {
      var $this = $(this);
      var text = $this.data("value");

      $this
        .closest(".translation-item")
        .find(".translation-editor")
        .insertAtCaret(text);
      e.preventDefault();
    });

    this.initHighlight();
    this.init();

    this.$translationArea[0].focus();
  }

  EditorBase.prototype.init = function () {};

  EditorBase.prototype.initHighlight = function () {
    var hlSelector = ".hlcheck";
    var hlNumberSelector = ".highlight-number";

    /* Copy from source text highlight check */
    this.$editor.on("click", hlSelector, function (e) {
      var $this = $(this);
      var text = $this.clone();

      text.find(hlNumberSelector).remove();
      text = text.text();
      insertEditor(text, $this);
      e.preventDefault();
    });

    /* and shortcuts */
    for (var i = 1; i < 10; i++) {
      Mousetrap.bindGlobal("mod+" + i, function (e) {
        return false;
      });
    }

    var $hlCheck = $(hlSelector);
    if ($hlCheck.length > 0) {
      $hlCheck.each(function (idx) {
        var $this = $(this);

        if (idx < 10) {
          let key = WLT.Utils.getNumericKey(idx);

          var title;
          if (WLT.Config.IS_MAC) {
            title = interpolate(gettext("Cmd+%s"), [key]);
          } else {
            title = interpolate(gettext("Ctrl+%s"), [key]);
          }
          $this.attr("title", title);
          $this.find(hlNumberSelector).html("<kbd>" + key + "</kbd>");

          Mousetrap.bindGlobal("mod+" + key, function (e) {
            $this.click();
            return false;
          });
        } else {
          $this.find(hlNumberSelector).html("");
        }
      });
      $(hlNumberSelector).hide();
    }

    Mousetrap.bindGlobal(
      "mod",
      function (e) {
        $(hlNumberSelector).show();
      },
      "keydown"
    );
    Mousetrap.bindGlobal(
      "mod",
      function (e) {
        $(hlNumberSelector).hide();
      },
      "keyup"
    );
  };

  function insertEditor(text, element) {
    var root;

    /* Find withing root element */
    if (typeof element !== "undefined") {
      root = element.closest(".zen-unit");
      if (root.length === 0) {
        root = element.closest(".translation-form");
      }
    } else {
      root = $(document);
    }

    var editor = root.find(".translation-editor:focus");
    if (editor.length === 0) {
      editor = root.find(lastEditor);
      if (editor.length === 0) {
        editor = root.find(".translation-editor:first");
      }
    }

    editor.insertAtCaret($.trim(text));
  }

  return {
    Base: EditorBase,
  };
})();
