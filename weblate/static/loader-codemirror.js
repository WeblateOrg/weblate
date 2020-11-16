(function (CodeMirror) {
  var currentRequest = null;

  function getUserList(usernameSearch, from, to, callback) {
    currentRequest = $.ajax({
      type: "GET",
      url: `/api/users/?username=${usernameSearch}`,
      dataType: "json",
      beforeSend: function () {
        if (currentRequest !== null) {
          currentRequest.abort();
        }
      },
      success: function (data) {
        var userMentionList = data.results.map(function (user) {
          return {
            text: user.username,
            displayText: `${user.full_name} (${user.username})`,
          };
        });
        callback({
          list: userMentionList,
          from: from,
          to: to,
        });
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error(errorThrown);
      },
    });
  }

  CodeMirror.registerHelper("hint", "userSuggestions", function (
    editor,
    callback
  ) {
    var cur = editor.getCursor();
    var curLine = editor.getLine(cur.line);

    var end = cur.ch;
    var start = curLine.lastIndexOf("@") + 1;
    // Extract the current word from the current line using 'start' / 'end' value pair
    var curWord = start !== end && curLine.slice(start, end);

    if (curWord && curWord.length > 2) {
      // If there is current word set, We can filter out users from the
      // main list and display them
      getUserList(
        curWord,
        CodeMirror.Pos(cur.line, start),
        CodeMirror.Pos(cur.line, end),
        callback
      );
    }
  });

  CodeMirror.hint.userSuggestions.async = true;

  CodeMirror.weblateEditor = (textarea, mode) => {
    var maxLength = parseInt(textarea.getAttribute("maxlength"));
    var counter = textarea.parentElement.querySelector(".length-indicator");
    var direction;
    if (textarea.hasAttribute("dir")) {
      direction = textarea.getAttribute("dir");
    } else {
      direction = document.getElementsByTagName("html")[0].getAttribute("dir");
    }
    var codemirror = CodeMirror.fromTextArea(textarea, {
      mode: mode,
      theme: "weblate",
      lineNumbers: false,
      lineWrapping: true,
      viewportMargin: Infinity,
      autoRefresh: true,
      extraKeys: { Tab: false },
      direction: direction,
    });
    var classToggle = textarea.parentElement.classList;

    codemirror.on("change", () => {
      codemirror.save();
      var length = textarea.value.length;

      /* Check maximal length limit */
      if (maxLength) {
        if (length > maxLength) {
          classToggle.remove("has-warning");
          classToggle.add("has-error");
        } else if (length > maxLength - 10) {
          classToggle.add("has-warning");
          classToggle.remove("has-error");
        } else {
          classToggle.remove("has-warning");
          classToggle.remove("has-error");
        }
      }

      /* Update chars counter */
      if (counter) {
        counter.textContent = length;
      }
    });
    CodeMirror.signal(codemirror, "change");

    if (mode === "text/x-markdown") {
      codemirror.on("keydown", function (cm, event) {
        if (event.key === "@") {
          CodeMirror.showHint(cm, CodeMirror.hint.userSuggestions, {
            completeSingle: false,
          });
        }
      });
    }

    // Add weblate bootstrap styling on the textarea
    codemirror.getWrapperElement().classList.add("form-control");

    textarea.CodeMirror = codemirror;

    return codemirror;
  };

  $("textarea.codemirror-markdown").each((idx, textarea) => {
    CodeMirror.weblateEditor(textarea, "text/x-markdown");
  });
})(CodeMirror);
