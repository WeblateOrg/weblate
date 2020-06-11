(function () {
    var EditorBase = WLT.Editor.Base;

    var $window = $(window);

    function FullEditor() {
        EditorBase.call(this);

        var self = this;

        this.initTranslationForm();
        this.initTabs();
        this.initChecks();
        this.initGlossary();

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
                self.$translationArea.get(0).focus();
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

    FullEditor.prototype.initTranslationForm = function () {
        var self = this;

        this.$translationForm = $('.translation-form');

        /* Report source bug */
        this.$translationForm.on('click', '.bug-comment', function () {
            $('.translation-tabs a[href="#comments"]').tab('show');
            $("#id_scope").val("report");
            $([document.documentElement, document.body]).animate({
                scrollTop: $('#comment-form').offset().top
            }, 1000);
            $("#id_comment").focus();
        });


        /* Form persistence. Restores translation form upon comment submission */
        if (window.localStorage.translation_autosave) {
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

        this.$editor.on('submit', '.auto-save-translation', function () {
            var data = self.$translationArea.map(function () {
                var $this = $(this);

                return {
                    id: $this.attr('id'),
                    value: $this.val(),
                };
            });

            window.localStorage.translation_autosave = JSON.stringify(data.get());
        });
    };

    FullEditor.prototype.initTabs = function () {
        this.isMTLoaded = false;
        this.isTMLoaded = false;

        /* Store active tab in a cookie */
        $('.translation-tabs a[data-toggle="tab"]').on('shown.bs.tab', function () {
            Cookies.remove('translate-tab', { path: '' });
            Cookies.set('translate-tab', $(this).attr('href'), { path: '/', expires: 365 });
        });

        /* Machine translation */
        this.$editor.on('show.bs.tab', '[data-load="mt"]', function (e) {
            if (this.isMTLoaded) {
                return;
            }
            this.isMTLoaded = true;
            increaseLoading('mt');
            $.ajax({
                url: $('#js-mt-services').attr('href'),
                success: loadMachineTranslations,
                error: failedMachineTranslation,
                dataType: 'json'
            });
        });

        /* Translation memory */
        this.$editor.on('show.bs.tab', '[data-load="memory"]', function (e) {
            if (this.isTMLoaded) {
                return;
            }
            this.isTMLoaded = true;
            increaseLoading('memory');
            var $form = $('#link-post');
            $.ajax({
                type: 'POST',
                url: $('#js-translate').attr('href').replace('__service__', 'weblate-translation-memory'),
                success: function (data) {
                    processMachineTranslation(data, 'memory');
                },
                error: function (jqXHR, textStatus, errorThrown) {
                    failedMachineTranslation(jqXHR, textStatus, errorThrown, 'memory');
                },
                dataType: 'json',
                data: {
                    csrfmiddlewaretoken: $form.find('input').val(),
                },
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
                    success: function (data) {
                        processMachineTranslation(data, 'memory');
                    },
                    error: function (jqXHR, textStatus, errorThrown) {
                        failedMachineTranslation(jqXHR, textStatus, errorThrown, 'memory');
                    },
                });
                return false;
            });
        });
    };

    FullEditor.prototype.initChecks = function () {
        var $checks = $('.check-item');
        if (!$checks.length) {
            return;
        }

        var self = this;

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
            self.$translationArea.each(function () {
                var $this = $(this);
                $.each(fixups, function (key, value) {
                    var re = new RegExp(value[0], value[2]);
                    $this.val($this.val().replace(re, value[1]));
                });
            });
            return false;
        });

        /* Keyboard shortcuts */
        // Cancel out browser's `meta+i` and let Mousetrap handle the rest
        document.addEventListener('keydown', function (e) {
            var isMod = WLT.Config.IS_MAC ? e.metaKey : e.ctrlKey;
            if (isMod && e.key.toLowerCase() === 'i') {
                e.preventDefault();
                e.stopPropagation();
            }
        });

        $checks.each(function(idx) {
            var $this = $(this);

            if (idx < 10) {
                let key = WLT.Utils.getNumericKey(idx);

                var title;
                if (WLT.Config.IS_MAC) {
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

        /* Clicking links (e.g. comments, suggestions) */
        this.$editor.on('click', '.check [data-toggle="tab"]', function (e) {
            var href = $(this).attr('href');

            e.preventDefault();
            $('.nav [href="' + href + '"]').click();
            $window.scrollTop($(href).offset().top);
        });
    };

    FullEditor.prototype.initGlossary = function () {
        var self = this;

        /* Copy from glossary */
        this.$editor.on('click', '.glossary-embed', function (e) {
            var text = $(this).find('.target').text();

            self.insertIntoTranslation(text);
            e.preventDefault();
        });

        /* Inline glossary adding */
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
                    self.$translationArea.first().focus();
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

    };

    FullEditor.prototype.insertIntoTranslation = function (text) {
        this.$translationArea.insertAtCaret($.trim(text)).change();
    };

    function loadMachineTranslations(data, textStatus) {
        var $form = $('#link-post');
        decreaseLoading('mt');
        data.forEach(function (el, idx) {
            increaseLoading('mt');
            $.ajax({
                type: 'POST',
                url: $('#js-translate').attr('href').replace('__service__', el),
                success: function (data) {
                    processMachineTranslation(data, 'mt');
                },
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

    function failedMachineTranslation(jqXHR, textStatus, errorThrown, scope) {
        decreaseLoading(scope);
        if (jqXHR.state() !== 'rejected') {
            addAlert(gettext('The request for machine translation has failed:') + ' ' + textStatus + ': ' + errorThrown);
        }
    }

    // TODO: move some logic to the class so that $translationArea can be reused
    function processMachineTranslation(data, scope) {
        decreaseLoading(scope);
        if (data.responseStatus !== 200) {
            var msg = interpolate(
                gettext('The request for machine translation using %s has failed:'),
                [data.service]
            );
            addAlert(msg + ' ' + data.responseDetails);

            return;
        }

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
                (el.quality >= 70 ? 'progress-bar-success' : el.quality >= 50 ? 'progress-bar-warning' : 'progress-bar-danger') + '"' +
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
            if (!done) {
                $machineTranslations.append(newRow);
            }
        });
        $('a.copymt').click(function () {
            var text = $(this).parent().parent().find('.target').text();

            $('.translation-editor').val(text).change();
            autosize.update($('.translation-editor'));
            WLT.Utils.markFuzzy($('.translation-form'));
        });
        $('a.copymt-save').click(function () {
            var text = $(this).parent().parent().find('.target').text();

            $('.translation-editor').val(text).change();
            autosize.update($('.translation-editor'));
            WLT.Utils.markTranslated($('.translation-form'));
            submitForm({ target: $('.translation-editor') });
        });

        for (var i = 1; i < 10; i++) {
            Mousetrap.bindGlobal(
                'mod+m ' + i,
                function () {
                    return false;
                }
            );
        }

        var $machineTranslations = $('#' + scope + '-translations');
        $machineTranslations.children('tr').each(function (idx) {
            if (idx < 10) {
                var key = WLT.Utils.getNumericKey(idx);

                var title;
                if (WLT.Config.IS_MAC) {
                    title = interpolate(gettext('Cmd+M then %s'), [key]);
                } else {
                    title = interpolate(gettext('Ctrl+M then %s'), [key]);
                }
                $(this).find('.mt-number').html(
                    ' <kbd title="' + title + '">' + key + '</kbd>'
                );
                Mousetrap.bindGlobal(
                    'mod+m ' + key,
                    function () {
                        $($('#' + scope + '-translations').children('tr')[idx]).find('a.copymt').click();
                        return false;
                    }
                );
            } else {
                $(this).find('.mt-number').html('');
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        new FullEditor();
    });

})();
