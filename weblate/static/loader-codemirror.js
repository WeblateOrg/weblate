(function (CodeMirror) {


    function getUserList(usernameSearch) {
        var userList = [];
        $.ajax({
            type: 'GET',
            url: `/api/users/?username=${usernameSearch}`,
            dataType: 'json',
            async: false,
            success: function (data) {
                userList = data.results.map(function(user) {
                    return {
                        text: user.username,
                        displayText: `${user.full_name} (${user.username})`
                    }
                });
            },
            error: function (jqXHR, textStatus, errorThrown) {
                console.error(errorThrown);
            }
        });
        return userList;
    }

    CodeMirror.registerHelper('hint', 'userSuggestions', function (editor) {
        var cur = editor.getCursor();
        var curLine = editor.getLine(cur.line);
        var tokenType = editor.getTokenTypeAt(cur);

        // Disable user mention inside code
        if(!!tokenType && tokenType.indexOf('comment') !== -1)
            return;

        var end = cur.ch;
        var start = curLine.lastIndexOf('@') + 1;
        // Extract the current word from the current line using 'start' / 'end' value pair
        var curWord = start !== end && curLine.slice(start, end);
        var userMentionList = [];

        if(curWord && curWord.length > 2) {
            // If there is current word set, We can filter out users from the
            // main list and display them
            userMentionList = getUserList(curWord);
        }

        return { list: userMentionList, from: CodeMirror.Pos(cur.line, start), to: CodeMirror.Pos(cur.line, end) };
    });


    var commentArea = document.getElementById('id_comment')
    var codemirror = CodeMirror.fromTextArea(
        commentArea,
        {
            mode: 'text/javascript',
            theme: 'weblate',
            lineNumbers: false,
        }
    );

    // Add weblate bootstrap styling on the textarea
    $('.CodeMirror').addClass('form-control');
    $('.CodeMirror textarea').addClass('form-control');
    codemirror.on("keyup", function (cm, event) {
        if(event.key === "@" || (event.shiftKey && event.keyCode === 50)) {
          CodeMirror.showHint(cm, CodeMirror.hint.userSuggestions, {
            completeSingle: false
          });
        }
    });

    $('#comment-form input[type=submit').on('click', function(e) {
        e.preventDefault();
        $('#comment-form').submit();
    })


}) (CodeMirror);
