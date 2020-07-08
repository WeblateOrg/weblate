(function (CodeMirror) {
    var currentRequest = null;

    function getUserList(usernameSearch, from, to, callback) {
        currentRequest = $.ajax({
            type: 'GET',
            url: `/api/users/?username=${usernameSearch}`,
            dataType: 'json',
            beforeSend : function() {
                if (currentRequest !== null) {
                    currentRequest.abort();
                }
            },
            success: function (data) {
                var userMentionList = data.results.map(function(user) {
                    return {
                        text: user.username,
                        displayText: `${user.full_name} (${user.username})`
                    }
                });
                callback({
                    list: userMentionList,
                    from: from,
                    to: to
                });
            },
            error: function (jqXHR, textStatus, errorThrown) {
                console.error(errorThrown);
            }
        });
    }

    CodeMirror.registerHelper('hint', 'userSuggestions', function (editor, callback) {
        var cur = editor.getCursor();
        var curLine = editor.getLine(cur.line);

        var end = cur.ch;
        var start = curLine.lastIndexOf('@') + 1;
        // Extract the current word from the current line using 'start' / 'end' value pair
        var curWord = start !== end && curLine.slice(start, end);

        if(curWord && curWord.length > 2) {
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


    $('textarea.codemirror-markdown').each(function(idx) {

        var codemirror = CodeMirror.fromTextArea(
            this,
            {
                mode: 'text/x-markdown',
                theme: 'weblate',
                lineNumbers: false,
            }
        );

        codemirror.on('change', function (cm, event) {
            cm.save()
        });

        codemirror.on('keydown', function (cm, event) {
            if(event.key === '@') {
                CodeMirror.showHint(cm, CodeMirror.hint.userSuggestions, {
                    completeSingle: false
                });
            }
        });
    });

    // Add weblate bootstrap styling on the textarea
    $('.CodeMirror').addClass('form-control');
    $('.CodeMirror textarea').addClass('form-control');


}) (CodeMirror);
