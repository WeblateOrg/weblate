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
    this.$translationArea = $(translationAreaSelector);

    /* Copy source text */
    this.$editor.on("click", ".copy-text", function (e) {
      var $this = $(this);
      e.preventDefault();

      var text = JSON.parse(this.getAttribute("data-content"));

      this.closest(".translation-item")
        .querySelector(".translation-editor")
        .CodeMirror.getDoc()
        .setValue(text);

      WLT.Utils.markFuzzy($this.closest("form"));
    });

    /* Direction toggling */
    this.$editor.on("change", ".direction-toggle", (e) => {
      e.target
        .closest(".translation-item")
        .querySelector(".translation-editor")
        .CodeMirror.setOption("direction", e.target.value);
    });

    /* Special characters */
    this.$editor.on("click", ".specialchar", function (e) {
      e.preventDefault();

      var text = this.getAttribute("data-value");
      this.closest(".translation-item")
        .querySelector(".translation-editor")
        .CodeMirror.replaceSelection(text);
    });

    this.initHighlight();
    this.init();

    this.$translationArea[0].CodeMirror.focus();
  }

  EditorBase.prototype.init = function () {
    $(".translation-editor").each((idx, textarea) => {
      if (textarea.CodeMirror) {
        return;
      }
      let codemirror = CodeMirror.weblateEditor(textarea, "");
      codemirror.addOverlay({
        token: function (stream) {
          if (stream.match("  ")) {
            return "doublespace";
          }
          stream.next();
          stream.skipTo(" ") || stream.skipToEnd();
        },
      });

      codemirror.on("change", () => {
        WLT.Utils.markTranslated($(textarea).closest("form"));
      });
      codemirror.on("focus", (cm) => {
        lastEditor = cm.getWrapperElement();
      });
    });
  };

  EditorBase.prototype.initHighlight = function () {
    var hlSelector = ".hlcheck";
    var hlNumberSelector = ".highlight-number";

    /* Copy from source text highlight check */
    this.$editor.on("click", hlSelector, function (e) {
      var $this = $(this);
      var text = $this.clone();

      text.find(hlNumberSelector).remove();
      text = text.text();
      this.insertEditor(text, $this);
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

  EditorBase.prototype.insertEditor = function (text, element) {
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

    var editor = root.find(".CodeMirror-focused");
    if (editor.length === 0) {
      editor = root.find(lastEditor);
      if (editor.length === 0) {
        editor = root.find(".CodeMirror:first");
      }
    }

    editor[0].CodeMirror.replaceSelection($.trim(text));
  };

  return {
    Base: EditorBase,
  };
})();
