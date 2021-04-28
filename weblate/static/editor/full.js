(function () {
  var EditorBase = WLT.Editor.Base;

  var TM_SERVICE_NAME = "weblate-translation-memory";

  var $window = $(window);

  function FullEditor() {
    EditorBase.call(this);

    this.csrfToken = $("#link-post").find("input").val();

    this.initTranslationForm();
    this.initTabs();
    this.initChecks();
    this.initGlossary();

    /* Copy machinery results */
    this.$editor.on("click", ".js-copy-machinery", (e) => {
      var $el = $(e.target);
      var text = $el.parent().parent().data("raw").text;

      this.$translationArea.replaceValue(text);
      autosize.update(this.$translationArea);
      WLT.Utils.markFuzzy(this.$translationForm);
    });

    /* Copy and save machinery results */
    this.$editor.on("click", ".js-copy-save-machinery", (e) => {
      var $el = $(e.target);
      var text = $el.parent().parent().data("raw").text;

      this.$translationArea.replaceValue(text);
      autosize.update(this.$translationArea);
      WLT.Utils.markTranslated(this.$translationForm);
      submitForm({ target: this.$translationArea });
    });

    Mousetrap.bindGlobal("alt+end", function (e) {
      window.location = $("#button-end").attr("href");
      return false;
    });
    Mousetrap.bindGlobal(
      ["alt+pagedown", "mod+down", "alt+down"],
      function (e) {
        window.location = $("#button-next").attr("href");
        return false;
      }
    );
    Mousetrap.bindGlobal(["alt+pageup", "mod+up", "alt+up"], function (e) {
      window.location = $("#button-prev").attr("href");
      return false;
    });
    Mousetrap.bindGlobal("alt+home", function (e) {
      window.location = $("#button-first").attr("href");
      return false;
    });
    Mousetrap.bindGlobal("mod+o", function (e) {
      $(".source-language-group [data-clone-text]").click();
      return false;
    });
    Mousetrap.bindGlobal("mod+y", function (e) {
      $('input[name="fuzzy"]').click();
      return false;
    });
    Mousetrap.bindGlobal("mod+shift+enter", function (e) {
      $('input[name="fuzzy"]').prop("checked", false);
      return submitForm(e);
    });
    Mousetrap.bindGlobal("mod+e", () => {
      this.$translationArea.get(0).focus();
      return false;
    });
    Mousetrap.bindGlobal("mod+s", function (e) {
      $("#search-dropdown").click();
      $('input[name="q"]').focus();
      return false;
    });
    Mousetrap.bindGlobal("mod+u", function (e) {
      $('.nav [href="#comments"]').click();
      $('textarea[name="comment"]').focus();
      return false;
    });
    Mousetrap.bindGlobal("mod+j", function (e) {
      $('.nav [href="#nearby"]').click();
      return false;
    });
    Mousetrap.bindGlobal("mod+m", function (e) {
      $('.nav [href="#machinery"]').click();
      return false;
    });
  }
  FullEditor.prototype = Object.create(EditorBase.prototype);
  FullEditor.prototype.constructor = FullEditor;

  FullEditor.prototype.initTranslationForm = function () {
    var self = this;

    this.$translationForm = $(".translation-form");

    /* Report source bug */
    this.$translationForm.on("click", ".bug-comment", function () {
      $('.translation-tabs a[href="#comments"]').tab("show");
      $("#id_scope").val("report");
      $([document.documentElement, document.body]).animate(
        {
          scrollTop: $("#comment-form").offset().top,
        },
        1000
      );
      $("#id_comment").focus();
    });

    /* Form persistence. Restores translation form upon comment submission */
    var restoreKey = "translation_autosave";
    var restoreValue = window.localStorage.getItem(restoreKey);
    if (restoreValue !== null) {
      var translationRestore = JSON.parse(restoreValue);

      translationRestore.forEach(function (restoreArea) {
        var target = document.getElementById(restoreArea.id);
        if (target) {
          target.value = restoreArea.value;
          autosize.update(target);
        }
      });
      localStorage.removeItem(restoreKey);
    }

    this.$editor.on("submit", ".auto-save-translation", function () {
      var data = self.$translationArea.map(function () {
        var $this = $(this);

        return {
          id: $this.attr("id"),
          value: $this.val(),
        };
      });

      window.localStorage.setItem(restoreKey, JSON.stringify(data.get()));
    });
  };

  FullEditor.prototype.initTabs = function () {
    /* Store active tab in a cookie */
    $('.translation-tabs a[data-toggle="tab"]').on("shown.bs.tab", function () {
      Cookies.remove("translate-tab", { path: "" });
      Cookies.set("translate-tab", $(this).attr("href"), {
        path: "/",
        expires: 365,
        sameSite: "Lax",
      });
    });

    /* Machinery */
    this.isMachineryLoaded = false;
    this.$editor.on("show.bs.tab", '[data-load="machinery"]', () => {
      if (this.isMachineryLoaded) {
        return;
      }
      this.initMachinery();
    });
  };

  FullEditor.prototype.initMachinery = function () {
    this.isMachineryLoaded = true;
    this.machinery = new Machinery();

    $("#js-translate")
      .data("services")
      .forEach((serviceName) => {
        increaseLoading("machinery");
        this.fetchMachinery(serviceName);
      });

    this.$editor.on("submit", "#memory-search", (e) => {
      var $form = $(e.currentTarget);

      increaseLoading("machinery");
      this.machinery.setState({ translations: [] });
      $("#machinery-translations").empty();
      $.ajax({
        type: "POST",
        url: $form.attr("action"),
        data: $form.serialize(),
        dataType: "json",
        success: (data) => {
          this.processMachineryResults(data);
        },
        error: (jqXHR, textStatus, errorThrown) => {
          this.processMachineryError(jqXHR, textStatus, errorThrown);
        },
      });
      return false;
    });
  };

  FullEditor.prototype.fetchMachinery = function (serviceName) {
    $.ajax({
      type: "POST",
      url: $("#js-translate").attr("href").replace("__service__", serviceName),
      success: (data) => {
        this.processMachineryResults(data);
      },
      error: (jqXHR, textStatus, errorThrown) => {
        this.processMachineryError(jqXHR, textStatus, errorThrown);
      },
      dataType: "json",
      data: {
        csrfmiddlewaretoken: this.csrfToken,
      },
    });
  };

  FullEditor.prototype.processMachineryError = function (
    jqXHR,
    textStatus,
    errorThrown
  ) {
    decreaseLoading("machinery");
    if (jqXHR.state() !== "rejected") {
      addAlert(
        gettext("The request for machine translation has failed:") +
          " " +
          textStatus +
          ": " +
          errorThrown
      );
    }
  };

  FullEditor.prototype.processMachineryResults = function (data) {
    decreaseLoading("machinery");
    if (data.responseStatus !== 200) {
      var msg = interpolate(
        gettext("The request for machine translation using %s has failed:"),
        [data.service]
      );
      addAlert(msg + " " + data.responseDetails);

      return;
    }

    this.machinery.setState({
      translations: [
        ...this.machinery.state.translations,
        ...data.translations,
      ],
      lang: data.lang,
      dir: data.dir,
    });
    this.machinery.render(data.translations);

    // Cancel out browser's `meta+m` and let Mousetrap handle the rest
    document.addEventListener("keydown", function (e) {
      var isMod = WLT.Config.IS_MAC ? e.metaKey : e.ctrlKey;
      if (isMod && e.key.toLowerCase() === "m") {
        e.preventDefault();
        e.stopPropagation();
      }
    });

    var $translationRows = $("#machinery-translations").children("tr");
    $translationRows.each(function (idx) {
      if (idx < 10) {
        var key = WLT.Utils.getNumericKey(idx);

        var title;
        if (WLT.Config.IS_MAC) {
          title = interpolate(gettext("Cmd+M then %s"), [key]);
        } else {
          title = interpolate(gettext("Ctrl+M then %s"), [key]);
        }
        $(this)
          .find(".machinery-number")
          .html(' <kbd title="' + title + '">' + key + "</kbd>");
        Mousetrap.bindGlobal(["mod+m " + key, "mod+m mod+" + key], function () {
          $translationRows.eq(idx).find(".js-copy-machinery").click();
          return false;
        });
      } else {
        $(this).find(".machinery-number").html("");
      }
    });
  };

  FullEditor.prototype.initChecks = function () {
    /* Clicking links (e.g. comments, suggestions)
     * This is inside things to checks, but not a check-item */
    this.$editor.on("click", '.check [data-toggle="tab"]', function (e) {
      var href = $(this).attr("href");

      e.preventDefault();
      $('.nav [href="' + href + '"]').click();
      $window.scrollTop($(".translation-tabs").offset().top);
    });

    var $checks = $(".check-item");
    if (!$checks.length) {
      return;
    }

    /* Check ignoring */
    this.$editor.on("click", ".check-dismiss", (e) => {
      var $el = $(e.currentTarget);
      var url = $el.attr("href");
      var $check = $el.closest(".check");
      var dismiss_all = $check.find("input").prop("checked");
      if (dismiss_all) {
        url = $el.data("dismiss-all");
      }

      $.ajax({
        type: "POST",
        url: url,
        data: {
          csrfmiddlewaretoken: this.csrfToken,
        },
        error: function (jqXHR, textStatus, errorThrown) {
          addAlert(errorThrown);
        },
      });
      if (dismiss_all) {
        $check.remove();
      } else {
        $check.toggleClass("check-dismissed");
      }
      return false;
    });

    /* Check fix */
    this.$editor.on("click", "[data-check-fixup]", (e) => {
      var $el = $(e.currentTarget);
      var fixups = $el.data("check-fixup");
      this.$translationArea.each(function () {
        var $this = $(this);
        $.each(fixups, function (key, value) {
          var re = new RegExp(value[0], value[2]);
          $this.replaceValue($this.val().replace(re, value[1]));
        });
      });
      return false;
    });

    /* Keyboard shortcuts */
    // Cancel out browser's `meta+i` and let Mousetrap handle the rest
    document.addEventListener("keydown", function (e) {
      var isMod = WLT.Config.IS_MAC ? e.metaKey : e.ctrlKey;
      if (isMod && e.key.toLowerCase() === "i") {
        e.preventDefault();
        e.stopPropagation();
      }
    });

    $checks.each(function (idx) {
      var $this = $(this);
      let $number = $(this).find(".check-number");

      if (idx < 10) {
        if ($number.length === 0) {
          return;
        }
        let key = WLT.Utils.getNumericKey(idx);

        var title;
        if (WLT.Config.IS_MAC) {
          title = interpolate(gettext("Press Cmd+I then %s to dismiss this."), [
            key,
          ]);
        } else {
          title = interpolate(
            gettext("Press Ctrl+I then %s to dismiss this."),
            [key]
          );
        }
        $number.html(' <kbd title="' + title + '">' + key + "</kbd>");

        Mousetrap.bindGlobal(
          ["mod+i " + key, "mod+i mod+" + key],
          function (e) {
            $this.find(".check-dismiss-single").click();
            return false;
          }
        );
      } else {
        $number.html("");
      }
    });
  };

  FullEditor.prototype.initGlossary = function () {
    /* Copy from glossary */
    this.$editor.on("click", ".glossary-embed.clickable-row", (e) => {
      /* Avoid copy when clicked on a link */
      if ($(e.target).parents("a").length > 0) {
        return;
      }
      console.log(e.target);
      console.log(e.currentTarget);
      var text = $(e.currentTarget).find(".target").text();

      this.insertIntoTranslation(text);
      e.preventDefault();
    });

    /* Glossary dialog */
    var $glossaryDialog = null;
    this.$editor.on("show.bs.modal", "#add-glossary-form", (e) => {
      $glossaryDialog = $(e.currentTarget);
    });
    this.$editor.on("hidden.bs.modal", "#add-glossary-form", () => {
      this.$translationArea.first().focus();
    });

    /* Inline glossary adding */
    this.$editor.on("submit", ".add-dict-inline", (e) => {
      var $form = $(e.currentTarget);

      increaseLoading("glossary-add");
      $glossaryDialog.modal("hide");
      $.ajax({
        type: "POST",
        url: $form.attr("action"),
        data: $form.serialize(),
        dataType: "json",
        success: (data) => {
          decreaseLoading("glossary-add");
          if (data.responseCode === 200) {
            $("#glossary-terms").html(data.results);
            $form.find("[name=terms]").attr("value", data.terms);
            $form.trigger("reset");
          } else {
            addAlert(data.responseDetails);
          }
        },
        error: function (xhr, textStatus, errorThrown) {
          addAlert(errorThrown);
          decreaseLoading("glossary-add");
        },
      });
      return false;
    });
  };

  FullEditor.prototype.insertIntoTranslation = function (text) {
    this.$translationArea.insertAtCaret($.trim(text));
  };

  class Machinery {
    constructor(initialState = {}) {
      this.state = {
        translations: [],
        lang: null,
        dir: null,
      };
    }

    setState(newState) {
      this.state = { ...this.state, ...newState };
    }

    renderTranslation(el, service) {
      var row = $("<tr/>").attr("class", "js-copy-machinery").data("raw", el);
      row.append(
        $("<td/>")
          .attr("class", "target machinery-text")
          .attr("lang", this.state.lang)
          .attr("dir", this.state.dir)
          .text(el.text)
      );
      row.append($("<td/>").attr("class", "machinery-text").text(el.source));
      row.append(service);

      /* Quality score as bar with the text */
      row.append(
        $("<td class='number'><strong>" + el.quality + "</strong> %</td>")
      );
      /* Translators: Verb for copy operation */
      row.append(
        $(
          "<td>" +
            '<a class="js-copy-machinery btn btn-warning">' +
            gettext("Copy") +
            '<span class="mt-number text-info"></span>' +
            "</a>" +
            "</td>" +
            "<td>" +
            '<a class="js-copy-save-machinery btn btn-primary">' +
            gettext("Copy and save") +
            "</a>" +
            "</td>"
        )
      );

      return row;
    }

    renderService(el) {
      var service = $("<td/>").text(el.service);
      if (typeof el.origin !== "undefined") {
        service.append(" (");
        var origin;
        if (typeof el.origin_detail !== "undefined") {
          origin = $("<abbr/>").text(el.origin).attr("title", el.origin_detail);
        } else if (typeof el.origin_url !== "undefined") {
          origin = $("<a/>").text(el.origin).attr("href", el.origin_url);
        } else {
          origin = el.origin;
        }
        service.append(origin);
        service.append(")");
      }
      return service;
    }

    render(translations) {
      var $translations = $("#machinery-translations");
      translations.forEach((translation) => {
        var service = this.renderService(translation);
        var insertBefore = null;
        var done = false;

        /* This is the merging and insert sort logic */
        $translations.children("tr").each(function (idx) {
          var $this = $(this);
          var base = $this.data("raw");
          if (
            base.text == translation.text &&
            base.source == translation.source
          ) {
            // Add origin to current ones
            var current = $this.children("td:nth-child(3)");
            if (base.quality < translation.quality) {
              service.append("<br/>");
              service.append(current.html());
              $this.remove();
              return false;
            }
            current.append($("<br/>"));
            current.append(service.html());
            done = true;
            return false;
          } else if (base.quality <= translation.quality && !insertBefore) {
            // Insert match before lower quality one
            insertBefore = $this;
          }
        });

        if (!done) {
          var newRow = this.renderTranslation(translation, service);
          if (insertBefore) {
            insertBefore.before(newRow);
          } else {
            $translations.append(newRow);
          }
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    new FullEditor();
  });
})();
