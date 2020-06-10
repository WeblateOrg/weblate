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
            $el.find('input[name="fuzzy"]').prop('checked', true);
            /* Review workflow */
            $el.find('input[name="review"][value="10"]').prop('checked', true);
        },

        markTranslated: function ($el) {
            /* Standard worflow */
            $el.find('input[name="fuzzy"]').prop('checked', false);
            /* Review workflow */
            $el.find('input[name="review"][value="20"]').prop('checked', true);
        },
    }
})();

WLT.Editor = (function () {
    var lastEditor = null;

    var $document = $(document);

    function EditorBase() {
        var translationAreaSelector =  '.translation-editor';

        this.$editor = $('.js-editor');
        this.$translationArea = $(translationAreaSelector);

        this.$editor.on('change', translationAreaSelector, testChangeHandler);
        this.$editor.on('keypress', translationAreaSelector, testChangeHandler);
        this.$editor.on('keydown', translationAreaSelector, testChangeHandler);
        this.$editor.on('paste', translationAreaSelector, testChangeHandler);
        this.$editor.on('focusin', translationAreaSelector, function () {
            lastEditor = $(this);
        });

        /* Count characters */
        this.$editor.on('keyup', translationAreaSelector, function() {
            var $this = $(this);
            var counter = $this.parent().find('.length-indicator');
            var limit = parseInt(counter.data('max'));
            var length = $this.val().length;
            counter.text(length);
            if (length >= limit) {
                counter.parent().addClass('badge-danger').removeClass('badge-warning');
            } else if (length + 10 >= limit) {
                counter.parent().addClass('badge-warning').removeClass('badge-danger');
            } else {
                counter.parent().removeClass('badge-warning').removeClass('badge-danger');
            }
        });

        /* Copy source text */
        this.$editor.on('click', '.copy-text', function (e) {
            var $this = $(this);

            $this.button('loading');
            $this.closest('.translation-item').find('.translation-editor').val(
                $.parseJSON($this.data('content'))
            ).change();
            autosize.update($('.translation-editor'));
            WLT.Utils.markFuzzy($this.closest('form'));
            $this.button('reset');
            e.preventDefault();
        });

        /* Direction toggling */
        this.$editor.on('change', '.direction-toggle', function () {
            var $this = $(this);

            $this.closest('.translation-item').find('.translation-editor').attr(
                'dir',
                $this.find('input').val()
            );
        });

        /* Special characters */
        this.$editor.on('click', '.specialchar', function (e) {
            var $this = $(this);
            var text = $this.data('value');

            $this.closest('.translation-item').find('.translation-editor').insertAtCaret(text).change();
            autosize.update($('.translation-editor'));
            e.preventDefault();
        });

        this.initHighlight();
        this.init();

        this.$translationArea[0].focus();
    }

    EditorBase.prototype.init = function() {
        /* Autosizing */
        autosize(this.$translationArea);
    };

    EditorBase.prototype.initHighlight = function () {
        var hlSelector = '.hlcheck';
        var hlNumberSelector = '.highlight-number';

        /* Copy from source text highlight check */
        this.$editor.on('click', hlSelector, function (e) {
            var $this = $(this);
            var text = $this.clone();

            text.find(hlNumberSelector).remove();
            text = text.text();
            insertEditor(text, $this);
            e.preventDefault();
        });

        /* and shortcuts */
        for (var i = 1; i < 10; i++) {
            Mousetrap.bindGlobal(
                'mod+' + i,
                function(e) {
                    return false;
                }
            );
        }

        var $hlCheck = $(hlSelector);
        if ($hlCheck.length > 0) {
            $hlCheck.each(function(idx) {
                var $this = $(this);

                if (idx < 10) {
                    let key = WLT.Utils.getNumericKey(idx);

                    var title;
                    if (WLT.Config.IS_MAC) {
                        title = interpolate(gettext('Cmd+%s'), [key]);
                    } else {
                        title = interpolate(gettext('Ctrl+%s'), [key]);
                    }
                    $this.attr('title', title);
                    $this.find(hlNumberSelector).html('<kbd>' + key + '</kbd>');

                    Mousetrap.bindGlobal(
                        'mod+' + key,
                        function(e) {
                            $this.click();
                            return false;
                        }
                    );
                } else {
                    $this.find(hlNumberSelector).html('');
                }
            });
            $(hlNumberSelector).hide();
        }

        Mousetrap.bindGlobal('mod', function (e) {
            $(hlNumberSelector).show();
        }, 'keydown');
        Mousetrap.bindGlobal('mod', function (e) {
            $(hlNumberSelector).hide();
        }, 'keyup');
    };


    function testChangeHandler(e) {
        if (e.key && e.key === 'Tab') {
            return;
        }
        WLT.Utils.markTranslated($(this).closest('form'));
    }

    function insertEditor(text, element) {
        var root;

        /* Find withing root element */
        if (typeof element !== 'undefined') {
            root = element.closest('.zen-unit');
            if (root.length === 0) {
                root = element.closest('.translation-form');
            }
        } else {
            root = $(document);
        }

        var editor = root.find('.translation-editor:focus');
        if (editor.length === 0) {
            editor = root.find(lastEditor);
            if (editor.length === 0) {
                editor = root.find('.translation-editor:first');
            }
        }

        editor.insertAtCaret($.trim(text)).change();
        autosize.update(editor);
    }


    // TODO: move to editor

    /* Translate forms persistence */
    if ($('.translation-form').length > 0 && window.localStorage && window.localStorage.translation_autosave) {
        var translationRestore = JSON.parse(window.localStorage.translation_autosave);

        $.each(translationRestore, function () {
            var target = $('#' + this.id);

            if (target.length > 0) {
                target.val(this.value);
                autosize.update(target);
            }
        });
        localStorage.removeItem('translation_autosave');
    }

    $('.auto-save-translation').on('submit', function () {
        if (window.localStorage) {
            let data = $('.translation-editor').map(function () {
                var $this = $(this);

                return {id: $this.attr('id'), value: $this.val()};
            });

            window.localStorage.translation_autosave = JSON.stringify(data.get());
        }
    });

    /* Report source bug */
    $('.bug-comment').click(function () {
        $('.translation-tabs a[href="#comments"]').tab('show');
        $("#id_scope").val("report");
        $([document.documentElement, document.body]).animate({
            scrollTop: $('#comment-form').offset().top
        }, 1000);
        $("#id_comment").focus();
    });

    // end TODO: move to non-zen editor

    return {
        Base: EditorBase,
    };

})();
