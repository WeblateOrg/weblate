(function () {
    var EditorBase = WLT.Editor.Base;

    var TM_SERVICE_NAME = 'weblate-translation-memory';

    var $window = $(window);

    function FullEditor() {
        EditorBase.call(this);

        this.csrfToken = $('#link-post').find('input').val();

        this.initTranslationForm();
        this.initTabs();
        this.initChecks();
        this.initGlossary();

        /* Copy machinery results */
        this.$editor.on('click', '.js-copy-machinery', (e) => {
            var $el = $(e.currentTarget);
            var text = $el.parent().parent().find('.target').text();

            this.$translationArea.val(text).change();
            autosize.update(this.$translationArea);
            WLT.Utils.markFuzzy(this.$translationForm);
        });

        /* Copy and save machinery results */
        this.$editor.on('click', '.js-copy-save-machinery', (e) => {
            var $el = $(e.currentTarget);
            var text = $el.parent().parent().find('.target').text();

            this.$translationArea.val(text).change();
            autosize.update(this.$translationArea);
            WLT.Utils.markTranslated(this.$translationForm);
            submitForm({ target: this.$translationArea });
        });

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
            () => {
                this.$translationArea.get(0).focus();
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
        var restoreKey = 'translation_autosave';
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

        this.$editor.on('submit', '.auto-save-translation', function () {
            var data = self.$translationArea.map(function () {
                var $this = $(this);

                return {
                    id: $this.attr('id'),
                    value: $this.val(),
                };
            });

            window.localStorage.setItem(restoreKey, JSON.stringify(data.get()));
        });
    };

    FullEditor.prototype.initTabs = function () {
        /* Store active tab in a cookie */
        $('.translation-tabs a[data-toggle="tab"]').on('shown.bs.tab', function () {
            Cookies.remove('translate-tab', { path: '' });
            Cookies.set('translate-tab', $(this).attr('href'), { path: '/', expires: 365 });
        });

        /* Machinery */
        this.isMachineryLoaded = false;
        this.$editor.on('show.bs.tab', '[data-load="machinery"]', () => {
            if (this.isMachineryLoaded) {
                return;
            }
            this.initMachinery();
        });
    };

    FullEditor.prototype.initMachinery = function () {
        this.machinery = new Machinery();

        increaseLoading('machinery');
        // TODO: inline list of services and skip this request
        $.ajax({
            url: $('#js-mt-services').attr('href'),
            success: (servicesList) => {
                decreaseLoading('machinery');
                servicesList.forEach((serviceName) => {
                    increaseLoading('machinery');
                    this.fetchMachinery(serviceName);
                });
                this.isMachineryLoaded = true;
            },
            error: this.processMachineryError,
            dataType: 'json'
        });

        this.$editor.on('submit', '#memory-search', (e) => {
            var $form = $(e.currentTarget);

            increaseLoading('machinery');
            this.machinery.setState({translations: []});
            $('#machinery-translations').empty();
            $.ajax({
                type: 'POST',
                url: $form.attr('action'),
                data: $form.serialize(),
                dataType: 'json',
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
            type: 'POST',
            url: $('#js-translate').attr('href').replace('__service__', serviceName),
            success: (data) => {
                this.processMachineryResults(data);
            },
            error: (jqXHR, textStatus, errorThrown) => {
                this.processMachineryError(jqXHR, textStatus, errorThrown);
            },
            dataType: 'json',
            data: {
                csrfmiddlewaretoken: this.csrfToken,
            },
        });
    };

    FullEditor.prototype.processMachineryError = function (jqXHR, textStatus, errorThrown) {
        decreaseLoading('machinery');
        if (jqXHR.state() !== 'rejected') {
            addAlert(gettext('The request for machine translation has failed:') + ' ' + textStatus + ': ' + errorThrown);
        }
    };

    FullEditor.prototype.processMachineryResults = function (data) {
        decreaseLoading('machinery');
        if (data.responseStatus !== 200) {
            var msg = interpolate(
                gettext('The request for machine translation using %s has failed:'),
                [data.service]
            );
            addAlert(msg + ' ' + data.responseDetails);

            return;
        }

        this.machinery.setState({
            translations: [...this.machinery.state.translations, ...data.translations],
            lang: data.lang,
            dir: data.dir,
        })

        // Cancel out browser's `meta+m` and let Mousetrap handle the rest
        document.addEventListener('keydown', function (e) {
            var isMod = WLT.Config.IS_MAC ? e.metaKey : e.ctrlKey;
            if (isMod && e.key.toLowerCase() === 'm') {
                e.preventDefault();
                e.stopPropagation();
            }
        });

        var $translationRows = $('#machinery-translations').children('tr');
        $translationRows.each(function (idx) {
            if (idx < 10) {
                var key = WLT.Utils.getNumericKey(idx);

                var title;
                if (WLT.Config.IS_MAC) {
                    title = interpolate(gettext('Cmd+M then %s'), [key]);
                } else {
                    title = interpolate(gettext('Ctrl+M then %s'), [key]);
                }
                $(this).find('.machinery-number').html(
                    ' <kbd title="' + title + '">' + key + '</kbd>'
                );
                Mousetrap.bindGlobal(
                    'mod+m ' + key,
                    function () {
                        $translationRows.eq(idx).find('.js-copy-machinery').click();
                        return false;
                    }
                );
            } else {
                $(this).find('.machinery-number').html('');
            }
        });
    };

    FullEditor.prototype.initChecks = function () {
        /* Clicking links (e.g. comments, suggestions)
         * This is inside things to checks, but not a check-item */
        this.$editor.on('click', '.check [data-toggle="tab"]', function (e) {
            var href = $(this).attr('href');

            e.preventDefault();
            $('.nav [href="' + href + '"]').click();
            $window.scrollTop($(".translation-tabs").offset().top);
        });

        var $checks = $('.check-item');
        if (!$checks.length) {
            return;
        }

        /* Check ignoring */
        this.$editor.on('click', '.check-dismiss', (e) => {
            var $el = $(e.currentTarget);
            $.ajax({
                type: 'POST',
                url: $el.attr('href'),
                data: {
                    csrfmiddlewaretoken: this.csrfToken,
                },
                error: function (jqXHR, textStatus, errorThrown) {
                    addAlert(errorThrown);
                },
            });
            if ($el.hasClass("check-dismiss-all")) {
                $el.closest('.check').remove();
            } else {
                $el.closest('.check').toggleClass("check-dismissed");
            }
            return false;
        });

        /* Check fix */
        this.$editor.on('click', '[data-check-fixup]', (e) => {
            var $el = $(e.currentTarget);
            var fixups = $el.data('check-fixup');
            this.$translationArea.each(function () {
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
    };

    FullEditor.prototype.initGlossary = function () {
        /* Copy from glossary */
        this.$editor.on('click', '.glossary-embed', (e) => {
            var text = $(e.currentTarget).find('.target').text();

            this.insertIntoTranslation(text);
            e.preventDefault();
        });

        /* Glossary dialog */
        var $glossaryDialog = null;
        this.$editor.on('show.bs.modal', '#add-glossary-form', (e) => {
            $glossaryDialog = $(e.currentTarget);
        })
        this.$editor.on('hidden.bs.modal', '#add-glossary-form', () => {
            this.$translationArea.first().focus();
        });

        /* Inline glossary adding */
        this.$editor.on('submit', '.add-dict-inline', (e) => {
            var $form = $(e.currentTarget);

            increaseLoading('glossary-add');
            $.ajax({
                type: 'POST',
                url: $form.attr('action'),
                data: $form.serialize(),
                dataType: 'json',
                success: (data) => {
                    decreaseLoading('glossary-add');
                    if (data.responseCode === 200) {
                        $('#glossary-terms').html(data.results);
                        $form.find('[name=terms]').attr('value', data.terms);
                    }
                    $form.trigger('reset');
                },
                error: function (xhr, textStatus, errorThrown) {
                    addAlert(errorThrown);
                    decreaseLoading('glossary-add');
                },
                complete: function () {
                    $glossaryDialog.modal('hide');
                },
            });
            return false;
        });

    };

    FullEditor.prototype.insertIntoTranslation = function (text) {
        this.$translationArea.insertAtCaret($.trim(text)).change();
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
            this.state = {...this.state, ...newState};
            this.render();
        }

        renderTranslation(el, service) {
            var row = $('<tr/>').attr('class', 'js-copy-machinery').data('raw', el);
            row.append($('<td/>').attr('class', 'target machinery-text').attr('lang', this.state.lang).attr('dir', this.state.dir).text(el.text));
            row.append($('<td/>').attr('class', 'machinery-text').text(el.source));
            row.append(service);

            /* Quality score as bar with the text */
            row.append($(
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
            row.append($(
                '<td>' +
                '<a class="js-copy-machinery btn btn-warning">' +
                gettext('Copy') +
                '<span class="mt-number text-info"></span>' +
                '</a>' +
                '</td>' +
                '<td>' +
                '<a class="js-copy-save-machinery btn btn-primary">' +
                gettext('Copy and save') +
                '</a>' +
                '</td>'
            ));

            return row;
        }

        renderService(el) {
            var service = $('<td/>').text(el.service);
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
            return service;
        }

        render() {
            var $translations = $('#machinery-translations');
            this.state.translations.forEach((translation) => {
                if (translation.done) {
                    return;
                }
                var service = this.renderService(translation);
                var newRow = this.renderTranslation(translation, service);
                translation.done = false;

                /* This is the merging and insert sort logic */
                $translations.children('tr').each(function (idx) {
                    var $this = $(this);
                    var base = $this.data('raw');
                    if (base.text == translation.text && base.source == translation.source) {
                        // Add origin to current ones
                        var current = $this.children('td:nth-child(3)');
                        current.append($("<br/>"));
                        current.append(service.html());
                        translation.done = true;
                        return false;
                    } else if (base.quality <= translation.quality) {
                        // Insert match before lower quality one
                        $this.before(newRow);
                        translation.done = true;
                        return false;
                    }
                });

                if (! translation.done) {
                    translation.done = true;
                    $translations.append(newRow);
                }
          });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        new FullEditor();
    });

})();
