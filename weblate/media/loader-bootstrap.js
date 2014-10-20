var loading = 0;
var mt_loaded = false;

function inc_loading() {
    if (loading === 0) {
        $('#mt-loading').show();
    }
    loading++;
}

function dec_loading() {
    loading--;
    if (loading === 0) {
        $('#mt-loading').hide();
    }
}

jQuery.fn.extend({
    insertAtCaret: function (myValue) {
        return this.each(function (i) {
            if (document.selection) {
                // For browsers like Internet Explorer
                this.focus();
                sel = document.selection.createRange();
                sel.text = myValue;
                this.focus();
            } else if (this.selectionStart || this.selectionStart == '0') {
                //For browsers like Firefox and Webkit based
                var startPos = this.selectionStart;
                var endPos = this.selectionEnd;
                var scrollTop = this.scrollTop;
                this.value = this.value.substring(0, startPos) + myValue + this.value.substring(endPos, this.value.length);
                this.focus();
                this.selectionStart = startPos + myValue.length;
                this.selectionEnd = startPos + myValue.length;
                this.scrollTop = scrollTop;
            } else {
                this.value += myValue;
                this.focus();
            }
        });
    }
});

function init_editor(editors) {
    editors.autosize();
}

function text_change(e) {
    if (e.key && e.key == 'Tab') {
        return;
    }
    $(this).parents('form').find('[name=fuzzy]').prop('checked', false);
}

function process_machine_translation(data, textStatus, jqXHR) {
    dec_loading();
    if (data.responseStatus == 200) {
        data.translations.forEach(function (el, idx, ar) {
            var new_row = $('<tr/>').data('quality', el.quality);
            var done = false;
            new_row.append($('<td/>').attr('class', 'target').attr('lang', data.lang).attr('dir', data.dir).text(el.text));
            new_row.append($('<td/>').text(el.source));
            new_row.append($('<td/>').text(el.service));
            /* Translators: Verb for copy operation */
            new_row.append($('<td><a class="copymt btn btn-xs btn-default">' + gettext('Copy') + '</a></td>'));
            $('#machine-translations').children('tr').each(function (idx) {
                if ($(this).data('quality') < el.quality && !done) {
                    $(this).before(new_row);
                    done = true;
                }
            });
            if (! done) {
                $('#machine-translations').append(new_row);
            }
        });
        $('a.copymt').button({text: true, icons: { primary: "ui-icon-copy" }}).click(function () {
            var text = $(this).parent().parent().find('.target').text();
            $('.translation-editor').val(text).trigger('autosize.resize');
            $('#id_fuzzy').prop('checked', true);
        });
    } else {
        var msg = interpolate(
            gettext('The request for machine translation using %s has failed:'),
            [data.service]
        );
        $('#mt-errors').append(
            $('<li>' + msg + ' ' + data.responseDetails + '</li>')
        );
    }
}

function failed_machine_translation(jqXHR, textStatus, errorThrown) {
    dec_loading();
    $('#mt-errors').append(
        $('<li>' + gettext('The request for machine translation has failed:') + ' ' + textStatus + '</li>')
    );
}

function isNumber(n) {
    return !isNaN(parseFloat(n)) && isFinite(n);
}

function cell_cmp(a, b) {
    if (a.indexOf('%') != -1 && b.indexOf('%') != -1) {
        a = parseFloat(a.replace(',', '.'));
        b = parseFloat(b.replace(',', '.'));
    } else if (isNumber(a) && isNumber(b)) {
        a  = parseFloat(a);
        b  = parseFloat(b);
    } else {
        a = a.toLowerCase();
        b = b.toLowerCase();
    }
    if (a == b) {
        return 0;
    }
    if (a > b) {
        return 1;
    }
    return -1;
}

function load_table_sorting() {
    $('table.sort').each(function () {
        var table = $(this),
            tbody = table.find('tbody'),
            thead = table.find('thead'),
            thIndex = 0;
        $(this).find('thead th')
            .each(function () {

            var th = $(this),
                inverse = 1;
            // handle colspan
            if (th.attr('colspan')) {
                thIndex += parseInt(th.attr('colspan'), 10) - 1;
            }
            // skip empty cells and cells with icon (probably already processed)
            if (th.text() !== '' && ! th.hasClass('sort-cell')) {
                // Store index copy
                var myIndex = thIndex;
                // Add icon, title and class
                th.attr('title', gettext("Sort this column")).addClass('sort-cell').append('<span class="sort-button glyphicon glyphicon-chevron-down sort-none" />');

                // Click handler
                th.click(function () {

                    tbody.find('td,th').filter(function () {
                        return $(this).index() === myIndex;
                    }).sortElements(function (a, b) {
                        return inverse * cell_cmp($.text([a]), $.text([b]));
                    }, function () {

                        // parentNode is the element we want to move
                        return this.parentNode;

                    });
                    thead.find('span.sort-button').removeClass('glyphicon-chevron-down glyphicon-chevron-up').addClass('glyphicon-chevron-down sort-none');
                    if (inverse == 1) {
                        $(this).find('span.sort-button').addClass('glyphicon-chevron-down').removeClass('glyphicon-chevron-up sort-none');
                    } else {
                        $(this).find('span.sort-button').addClass('glyphicon-chevron-up').removeClass('glyphicon-chevron-down sort-none');
                    }

                    inverse = inverse * -1;

                });
            }
            // Increase index
            thIndex += 1;
        });

    });
}

function zen_editor(e) {
    var $this = $(this);
    var $row = $this.parents('tr');
    var checksum = $row.find('[name=checksum]').val();

    $row.addClass('translation-modified');

    var form = $row.find('form');
    $('#loading-' + checksum).show();
    $.post(
        form.attr('action'),
        form.serialize(),
        function (data) {
            var messages = $('<div>' + data + '</div>');
            var statusdiv = $('#status-' + checksum);
            $('#loading-' + checksum).hide();
            if (messages.find('.alert-danger').length > 0) {
                statusdiv.attr('class', 'glyphicon-remove-sign text-danger');
            } else if (messages.find('.alert-warning').length > 0) {
                statusdiv.attr('class', 'glyphicon-exclamation-sign text-warning');
            } else if (messages.find('.alert-info').length > 0) {
                statusdiv.attr('class', 'glyphicon-ok-sign text-warning');
            } else {
                statusdiv.attr('class', 'glyphicon-ok-sign text-success');
            }
            statusdiv.addClass('glyphicon').tooltip({
                'html': true,
                'title': data
            });
            $row.removeClass('translation-modified').addClass('translation-saved');
        }
    );
}

$(function () {
    /* AJAX loading of tabs/pills */
    $(document).on('show.bs.tab', '[data-toggle="tab"][data-href], [data-toggle="pill"][data-href]', function (e) {
        var $target = $(e.target);
        var $content = $($target.attr('href'));
        if ($target.data('loaded')) {
            return;
        }
        if ($content.find('.panel-body').length > 0) {
            $content = $content.find('.panel-body');
        };
        $content.load(
            $target.data('href'),
            function (response, status, xhr) {
                if ( status == "error" ) {
                    var msg = gettext('Error while loading page:');
                    $content.html( msg + " "  + xhr.status + " " + xhr.statusText );
                }
                $target.data('loaded', 1);
                load_table_sorting();
            }
        );
    });

    /* Machine translation */
    $(document).on('show.bs.tab', '[data-load="mt"]', function (e) {
        if (mt_loaded) {
            return;
        }
        mt_loaded = true;
        MACHINE_TRANSLATION_SERVICES.forEach(function (el, idx, ar) {
            inc_loading();
            $.ajax({
                url: $('#js-translate').attr('href') + '?service=' + el,
                success: process_machine_translation,
                error: failed_machine_translation,
                dataType: 'json'
            });
        });
    });

    /* Git commit tooltip */
    $(document).tooltip({
        selector: '.html-tooltip',
        html: true
    });

    /* Hiding spam protection field */
    $('#s_content').hide();
    $('#id_content').parent('div').hide();

    /* Form automatic submission */
    $("form.autosubmit select").change(function () {
        $("form.autosubmit").submit();
    });

    /* Row expander */
    $('.expander').click(function () {
        var $this = $(this);
        console.log($this);
        var $table_row = $this.closest('tr');
        var $next_row = $table_row.next();
        $next_row.toggle();
        $table_row.find('.expand-icon').toggleClass('glyphicon-chevron-right').toggleClass('glyphicon-chevron-down');
        var $loader = $next_row.find('.load-details');
        if ($loader.length > 0) {
            var url = $loader.attr('href');
            $loader.remove();
            $.get(
                url,
                function (data) {
                    var $cell = $next_row.find('.details-content');
                    $cell.find('.glyphicon-spin').remove();
                    $cell.append(data);
                    $cell.find('.button').button();
                }
            );
        }
    });

    /* Priority editor */
    $('.edit-priority').click(function (e) {
        e.preventDefault();
        $(this).closest('tr').find('.expander').first().click();
    });

    /* Load correct tab */
    if (location.hash !== '') {
        var activeTab = $('[data-toggle=tab][href=' + location.hash + ']');
        if (activeTab.length) {
            activeTab.tab('show');
            window.scrollTo(0, 0);
        }
    }

    /* Add a hash to the URL when the user clicks on a tab */
    $('a[data-toggle="tab"]').on('shown.bs.tab', function(e) {
        history.pushState(null, null, $(this).attr('href'));
        /* Remove focus on rows */
        $('.selectable-row').removeClass('active');
    });

    /* Navigate to a tab when the history changes */
    window.addEventListener("popstate", function(e) {
        var activeTab = $('[data-toggle=tab][href=' + location.hash + ']');
        if (activeTab.length) {
            activeTab.tab('show');
        } else {
            $('.nav-tabs a:first').tab('show');
        }
    });

    /* Activate tab with error */
    var form_errors = $('div.has-error');
    if (form_errors.length > 0) {
        var tab = form_errors.closest('div.tab-pane');
        if (tab.length > 0) {
            $('[data-toggle=tab][href=#' + tab.attr('id')+ ']').tab('show');
        }
    }

    /* Translation editor */
    var translation_editor = $('.translation-editor');
    if (translation_editor.length > 0) {
        $(document).on('change', '.translation-editor', text_change);
        $(document).on('keypress', '.translation-editor', text_change);
        init_editor(translation_editor);
        translation_editor.get(0).focus();
        if ($('#button-first').length > 0) {
            Mousetrap.bindGlobal('alt+end', function(e) {window.location = $('#button-end').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+pagedown', function(e) {window.location = $('#button-next').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+pageup', function(e) {window.location = $('#button-prev').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+home', function(e) {window.location = $('#button-first').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+enter', function(e) {$('.translation-form').submit(); return false;});
            Mousetrap.bindGlobal('ctrl+enter', function(e) {$('.translation-form').submit(); return false;});
        }
    }

    /* Generic tooltips */
    $('.tooltip-control').tooltip();

    /* Check ignoring */
    $('.check').bind('close.bs.alert', function () {
        var $this = $(this);
        $.get($this.data('href'));
        $this.tooltip('destroy');
    });

    /* Check link clicking */
    $(document).on('click', '.check [data-toggle="tab"]', function (e) {
        var href = $(this).attr('href');
        e.preventDefault();
        $('.nav [href="' + href + '"]').click();
        $(window).scrollTop($(href).offset().top);
    })

    /* Copy source text */
    $('.copy-text').click(function (e) {
        var $this = $(this);
        $this.button('loading');
        $.get($this.data('href'), function (data) {
            $this.parents('.translation-item').find('.translation-editor').val(data).trigger('autosize.resize');
            $('#id_fuzzy').prop('checked', true);
            $this.button('reset');
        });
        e.preventDefault();
    });

    /* Direction toggling */
    $('.direction-toggle').change(function (e) {
        var $this = $(this);
        $this.parents('.translation-item').find('.translation-editor').attr(
            'dir',
            $this.find('input').val()
        );
    });

    /* Special characters */
    $('.specialchar').click(function (e) {
        var $this = $(this);
        var text = $this.text();
        if (text == '\\t') {
            text = '\t';
        } else if (text == '→') {
            text = '\t';
        } else if (text == '↵') {
            text = '\r';
        }
        $this.parents('.translation-item').find('.translation-editor').insertAtCaret(text).trigger('autosize.resize');
        e.preventDefault();
    });

    /* Copy from dictionary */
    $('.copydict').click(function (e) {
        var text = $(this).parents('tr').find('.target').text();
        $('.translation-editor').insertAtCaret($.trim(text)).trigger('autosize.resize');;
        e.preventDefault();
    });

    /* Widgets selector */
    $('.select-tab').on('change', function (e) {
         $(this).parent().find('.tab-pane').removeClass('active');
        $('#' + $(this).val()).addClass('active');
    });

    /* Code samples (on widgets page) */
    $('.code-example').focus(function () {
        $(this).select();
    });

    /* Table sorting */
    load_table_sorting();

    /* Lock updates */
    if ($('#js-lock').length > 0) {
        window.setInterval(function () {
            $.get($('#js-lock').attr('href'));
        }, 19000);
    };

    /* Zen mode handling */
    if ($('.zen').length > 0) {
        $(window).scroll(function(){
            if ($(window).scrollTop() >= $(document).height() - (2 * $(window).height())) {
                if ($('#last-section').length > 0 || $('#loading-next').css('display') != 'none') {
                    return;
                }
                $('#loading-next').show();

                var loader = $('#zen-load');
                loader.data('offset', 20 + parseInt(loader.data('offset')));

                $.get(
                    loader.attr('href') + '&offset=' + loader.data('offset'),
                    function (data) {
                        $('#loading-next').hide();

                        $('.zen tbody').append(data).find('.button').button();

                        var $editors = $('.translation-editor');

                        init_editor($editors);
                    }
                );
            }
        });

        $(document).on('change', '.translation-editor', zen_editor);
        $(document).on('change', '.fuzzy_checkbox', zen_editor);

        $(window).on('beforeunload', function(){
            if ($('.translation-modified').length > 0) {
                return gettext('There are some unsaved changes, are you sure you want to leave?');
            }
        });
    };

    /* Social auth disconnect */
    $('a.disconnect').click(function (e) {
        e.preventDefault();
        $('form#disconnect-form')
            .attr('action', $(this).attr('href'))
            .submit();
    });
});
