(function () {
    var EditorBase = WLT.Editor.Base;

    function FullEditor() {
        EditorBase.call(this);

        Mousetrap.bindGlobal('alt+end', function(e) {window.location = $('#button-end').attr('href'); return false;});
        Mousetrap.bindGlobal('alt+pagedown', function(e) {window.location = $('#button-next').attr('href'); return false;});
        Mousetrap.bindGlobal('alt+pageup', function(e) {window.location = $('#button-prev').attr('href'); return false;});
        Mousetrap.bindGlobal('alt+home', function(e) {window.location = $('#button-first').attr('href'); return false;});
        Mousetrap.bindGlobal('mod+o', function(e) {$('.translation-item .copy-text').click(); return false;});
        Mousetrap.bindGlobal('mod+y', function(e) {$('input[name="fuzzy"]').click(); return false;});
        Mousetrap.bindGlobal(
            'mod+shift+enter',
            function(e) {$('input[name="fuzzy"]').prop('checked', false); return submitForm(e);}
        );
        Mousetrap.bindGlobal(
            'mod+e',
            function(e) {
                $('.translation-editor').get(0).focus();
                return false;
            }
        );
        Mousetrap.bindGlobal(
            'mod+s',
            function(e) {
                $('#search-dropdown').click();
                $('input[name="q"]').focus();
                return false;
            }
        );
        Mousetrap.bindGlobal(
            'mod+u',
            function(e) {
                $('.nav [href="#comments"]').click();
                $('textarea[name="comment"]').focus();
                return false;
            }
        );
        Mousetrap.bindGlobal(
            'mod+j',
            function(e) {
                $('.nav [href="#nearby"]').click();
                return false;
            }
        );
        Mousetrap.bindGlobal(
            'mod+m',
            function(e) {
                $('.nav [href="#machine"]').click();
                return false;
            }
        );
    }
    FullEditor.prototype = Object.create(EditorBase.prototype);
    FullEditor.prototype.constructor = FullEditor;

    document.addEventListener('DOMContentLoaded', function () {
        new FullEditor();
    });

})();
