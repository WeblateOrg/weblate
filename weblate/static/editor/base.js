var WLT = WLT || {};

WLT.Editor = (function () {
    var machineTranslationLoaded = false;
    var translationMemoryLoaded = false;
    var lastEditor = null;

    var IS_MAC = /Mac|iPod|iPhone|iPad/.test(navigator.platform);

    var $window = $(window);
    var $document = $(document);

    function getNumericKey(idx) {
        var ret = idx + 1;

        if (ret === 10) {
            return '0';
        }
        return ret;
    }

    function markFuzzy(elm) {
        /* Standard worflow */
        elm.find('input[name="fuzzy"]').prop('checked', true);
        /* Review workflow */
        elm.find('input[name="review"][value="10"]').prop('checked', true);
    }

    function markTranslated(elm) {
        /* Standard worflow */
        elm.find('input[name="fuzzy"]').prop('checked', false);
        /* Review workflow */
        elm.find('input[name="review"][value="20"]').prop('checked', true);
    }

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
            markFuzzy($this.closest('form'));
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

        this.init();

        this.$translationArea[0].focus();
    }

    EditorBase.prototype.init = function() {
        /* Autosizing */
        autosize($('.translation-editor'));
    };


    function testChangeHandler(e) {
        if (e.key && e.key === 'Tab') {
            return;
        }
        markTranslated($(this).closest('form'));
    }

    function processMachineTranslation(data, scope) {
        decreaseLoading(scope);
        if (data.responseStatus === 200) {
            data.translations.forEach(function (el, idx) {
                var newRow = $('<tr/>').data('raw', el);
                var done = false;
                var $machineTranslations = $('#' + scope + '-translations');
                var service;

                newRow.append($('<td/>').attr('class', 'target mt-text').attr('lang', data.lang).attr('dir', data.dir).text(el.text));
                newRow.append($('<td/>').attr('class', 'mt-text').text(el.source));
                if (scope === "mt") {
                    service = $('<td/>').text(el.service);
                    if (typeof el.origin !== 'undefined') {
                        service.append(' (');
                        var origin;
                        if (typeof el.origin_detail !== 'undefined') {
                            origin = $('<abbr/>').text(el.origin).attr('title', el.origin_detail);
                        } else if (typeof el.origin_url !== 'undefined') {
                            origin = $('<a/>').text(el.origin).attr('href', el.origin_url);
                        } else {
                            origin = el.origin;
                        }
                        service.append(origin);
                        service.append(')');
                        // newRow.append($('<td/>').text(interpolate('%s (%s)', [el.service, ])));
                    }
                } else {
                    service = $('<td/>').text(el.origin);
                }
                newRow.append(service);
                /* Quality score as bar with the text */
                newRow.append($(
                    '<td>' +
                    '<div class="progress" title="' + el.quality + ' / 100">' +
                    '<div class="progress-bar ' +
                    ( el.quality >= 70 ? 'progress-bar-success' : el.quality >= 50 ? 'progress-bar-warning' : 'progress-bar-danger' ) + '"' +
                    ' role="progressbar" aria-valuenow="' + el.quality + '"' +
                    ' aria-valuemin="0" aria-valuemax="100" style="width: ' + el.quality + '%;"></div>' +
                    '</div>' +
                    '</td>'
                ));
                /* Translators: Verb for copy operation */
                newRow.append($(
                    '<td>' +
                    '<a class="copymt btn btn-warning">' +
                    gettext('Copy') +
                    '<span class="mt-number text-info"></span>' +
                    '</a>' +
                    '</td>' +
                    '<td>' +
                    '<a class="copymt-save btn btn-primary">' +
                    gettext('Copy and save') +
                    '</a>' +
                    '</td>'
                ));
                $machineTranslations.children('tr').each(function (idx) {
                    var $this = $(this);
                    var base = $this.data('raw');
                    if (base.text == el.text && base.source == el.source) {
                        // Add origin to current ones
                        var current = $this.children('td:nth-child(3)');
                        current.append($("<br/>"));
                        current.append(service.html());
                        done = true;
                        return false;
                    } else if (base.quality <= el.quality) {
                        // Insert match before lower quality one
                        $this.before(newRow);
                        done = true;
                        return false;
                    }
                });
                if (! done) {
                    $machineTranslations.append(newRow);
                }
            });
            $('a.copymt').click(function () {
                var text = $(this).parent().parent().find('.target').text();

                $('.translation-editor').val(text).change();
                autosize.update($('.translation-editor'));
                markFuzzy($('.translation-form'));
            });
            $('a.copymt-save').click(function () {
                var text = $(this).parent().parent().find('.target').text();

                $('.translation-editor').val(text).change();
                autosize.update($('.translation-editor'));
                markTranslated($('.translation-form'));
                submitForm({target:$('.translation-editor')});
            });

            for (var i = 1; i < 10; i++) {
                Mousetrap.bindGlobal(
                    'mod+m ' + i,
                    function() {
                        return false;
                    }
                );
            }

            var $machineTranslations = $('#' + scope + '-translations');

            $machineTranslations.children('tr').each(function (idx) {
                if (idx < 10) {
                    var key = getNumericKey(idx);

                    var title;
                    if (IS_MAC) {
                        title = interpolate(gettext('Cmd+M then %s'), [key]);
                    } else {
                        title = interpolate(gettext('Ctrl+M then %s'), [key]);
                    }
                    $(this).find('.mt-number').html(
                        ' <kbd title="' + title + '">' + key + '</kbd>'
                    );
                    Mousetrap.bindGlobal(
                        'mod+m ' + key,
                        function() {
                            $($('#' + scope + '-translations').children('tr')[idx]).find('a.copymt').click();
                            return false;
                        }
                    );
                } else {
                    $(this).find('.mt-number').html('');
                }
            });

        } else {
            var msg = interpolate(
                gettext('The request for machine translation using %s has failed:'),
                [data.service]
            );

            addAlert(msg + ' ' + data.responseDetails);
        }
    }

    function failedMachineTranslation(jqXHR, textStatus, errorThrown, scope) {
        decreaseLoading(scope);
        if (jqXHR.state() !== 'rejected') {
            addAlert(gettext('The request for machine translation has failed:') + ' ' + textStatus + ': ' + errorThrown);
        }
    }

    function loadMachineTranslations(data, textStatus) {
        var $form = $('#link-post');
        decreaseLoading('mt');
        data.forEach(function (el, idx) {
            increaseLoading('mt');
            $.ajax({
                type: 'POST',
                url: $('#js-translate').attr('href').replace('__service__', el),
                success: function (data) {processMachineTranslation(data, 'mt');},
                error: function (jqXHR, textStatus, errorThrown) {
                    failedMachineTranslation(jqXHR, textStatus, errorThrown, 'mt');
                },
                dataType: 'json',
                data: {
                    csrfmiddlewaretoken: $form.find('input').val(),
                },
            });
        });
    }

    function insertEditor(text, element)
    {
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

    /* Machine translation */
    $document.on('show.bs.tab', '[data-load="mt"]', function (e) {
        if (machineTranslationLoaded) {
            return;
        }
        machineTranslationLoaded = true;
        increaseLoading('mt');
        $.ajax({
            url: $('#js-mt-services').attr('href'),
            success: loadMachineTranslations,
            error: failedMachineTranslation,
            dataType: 'json'
        });
    });

    /* Translation memory */
    $document.on('show.bs.tab', '[data-load="memory"]', function (e) {
        if (translationMemoryLoaded) {
            return;
        }
        translationMemoryLoaded = true;
        increaseLoading('memory');
        var $form = $('#link-post');
        $.ajax({
            type: 'POST',
            url: $('#js-translate').attr('href').replace('__service__', 'weblate-translation-memory'),
            success: function (data) {processMachineTranslation(data, 'memory');},
            error: function (jqXHR, textStatus, errorThrown) {
                failedMachineTranslation(jqXHR, textStatus, errorThrown, 'memory');
            },
            dataType: 'json',
            data: {
                csrfmiddlewaretoken: $form.find('input').val(),
            },
        });
    });

    $('#memory-search').submit(function () {
        var form = $(this);

        increaseLoading('memory');
        $('#memory-translations').empty();
        $.ajax({
            type: 'POST',
            url: form.attr('action'),
            data: form.serialize(),
            dataType: 'json',
            success: function (data) {processMachineTranslation(data, 'memory');},
            error: function (jqXHR, textStatus, errorThrown) {
                failedMachineTranslation(jqXHR, textStatus, errorThrown, 'memory');
            },
        });
        return false;
    });

    /* Store active translation tab in cookie */
    $('.translation-tabs a[data-toggle="tab"]').on('shown.bs.tab', function(e) {
        Cookies.remove('translate-tab', { path: '' });
        Cookies.set('translate-tab', $(this).attr('href'), { path: '/', expires: 365 });
    });

    /* Check ignoring */
    $('.check-dismiss').click(function () {
        var $this = $(this);
        var $form = $('#link-post');

        $.ajax({
            type: 'POST',
            url: $this.attr('href'),
            data: {
                csrfmiddlewaretoken: $form.find('input').val(),
            },
            error: function (jqXHR, textStatus, errorThrown) {
                addAlert(errorThrown);
            },
        });
        if ($this.hasClass("check-dismiss-all")) {
            $this.closest('.check').remove();
        } else {
            $this.closest('.check').toggleClass("check-dismissed");
        }
        return false;
    });

    /* Check fix */
    $('[data-check-fixup]').click(function (e) {
        var fixups = $(this).data('check-fixup');
        $('.translation-editor').each(function () {
            var $this = $(this);
            $.each(fixups, function (key, value) {
                var re = new RegExp(value[0], value[2]);
                $this.val($this.val().replace(re, value[1]));
            });
        });
        return false;
    });

    /* Check link clicking */
    $document.on('click', '.check [data-toggle="tab"]', function (e) {
        var href = $(this).attr('href');

        e.preventDefault();
        $('.nav [href="' + href + '"]').click();
        $window.scrollTop($(href).offset().top);
    });

    /* Copy from dictionary */
    $document.on('click', '.glossary-embed', function (e) {
        var text = $(this).find('.target').text();

        insertEditor(text);
        e.preventDefault();
    });

    /* Copy from source text highlight check */
    $document.on('click', '.hlcheck', function (e) {
        var text = $(this).clone();

        text.find('.highlight-number').remove();
        text=text.text();
        insertEditor(text, $(this));
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

    if ($('.hlcheck').length>0) {
        $('.hlcheck').each(function(idx) {
            var $this = $(this);

            if (idx < 10) {
                let key = getNumericKey(idx);

                var title;
                if (IS_MAC) {
                    title = interpolate(gettext('Cmd+%s'), [key]);
                } else {
                    title = interpolate(gettext('Ctrl+%s'), [key]);
                }
                $(this).attr('title', title);
                $(this).find('.highlight-number').html('<kbd>' + key + '</kbd>');

                Mousetrap.bindGlobal(
                    'mod+' + key,
                    function(e) {
                        $this.click();
                        return false;
                    }
                );
            } else {
                $this.find('.highlight-number').html('');
            }
        });
        $('.highlight-number').hide();
    }
    Mousetrap.bindGlobal('mod', function (e) {
        $('.highlight-number').show();
    }, 'keydown');
    Mousetrap.bindGlobal('mod', function (e) {
        $('.highlight-number').hide();
    }, 'keyup');

    if (document.querySelectorAll('.check-item').length > 0) {
        // Cancel out browser's `meta+i` and let Mousetrap handle the rest
        document.addEventListener('keydown', function (e) {
            var isMod = IS_MAC ? e.metaKey : e.ctrlKey;
            if (isMod && e.key.toLowerCase() === 'i') {
                e.preventDefault();
                e.stopPropagation();
            }
        });
    }

    $('.check-item').each(function(idx) {
        var $this = $(this);

        if (idx < 10) {
            let key = getNumericKey(idx);

            var title;
            if (IS_MAC) {
                title = interpolate(gettext('Press Cmd+I then %s to dismiss this.'), [key]);
            } else {
                title = interpolate(gettext('Press Ctrl+I then %s to dismiss this.'), [key]);
            }
            $(this).find('.check-number').html(
                ' <kbd title="' + title + '">' + key + '</kbd>'
            );

            Mousetrap.bindGlobal(
                'mod+i ' + key,
                function(e) {
                    $this.find('.check-dismiss-single').click();
                    return false;
                }
            );
        } else {
            $(this).find('.check-number').html('');
        }
    });

    /* Inline dictionary adding */
    $('.add-dict-inline').submit(function () {
        var form = $(this);

        increaseLoading('glossary-add');
        $.ajax({
            type: 'POST',
            url: form.attr('action'),
            data: form.serialize(),
            dataType: 'json',
            success: function (data) {
                decreaseLoading('glossary-add');
                if (data.responseCode === 200) {
                    $('#glossary-words').html(data.results);
                    form.find('[name=words]').attr('value', data.words);
                }
                $('.translation-editor:first').focus();
                form.trigger('reset');
            },
            error: function (xhr, textStatus, errorThrown) {
                addAlert(errorThrown);
                decreaseLoading('glossary-add');
            }
        });
        $('#add-glossary-form').modal('hide');
        return false;
    });

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
