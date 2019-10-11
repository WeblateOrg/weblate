var loading = 0;
var machineTranslationLoaded = false;
var translationMemoryLoaded = false;
var activityDataLoaded = false;
var lastEditor = null;

// Remove some weird things from location hash
if (window.location.hash && (window.location.hash.indexOf('"') > -1 || window.location.hash.indexOf('=') > -1)) {
    window.location.hash = '';
}

// Loading indicator handler
function increaseLoading(sel) {
    if (loading === 0) {
        $(sel).show();
    }
    loading += 1;
}

function decreaseLoading(sel) {
    loading -= 1;
    if (loading === 0) {
        $(sel).hide();
    }
}

function getNumericKey(idx) {
    var ret = idx + 1;

    if (ret === 10) {
        return '0';
    }
    return ret;
}

jQuery.fn.extend({
    insertAtCaret: function (myValue) {
        return this.each(function () {
            if (document.selection) {
                // For browsers like Internet Explorer
                this.focus();
                let sel = document.selection.createRange();

                sel.text = myValue;
                this.focus();
            } else if (this.selectionStart || this.selectionStart === 0) {
                //For browsers like Firefox and Webkit based
                let startPos = this.selectionStart;
                let endPos = this.selectionEnd;
                let scrollTop = this.scrollTop;

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


function submitForm(evt) {
    var $target = $(evt.target);
    var $form = $target.parents('form');

    if ($form.length === 0) {
        $form = $('.translation-form');
    }
    if ($form.length > 0) {
        let submits = $form.find('input[type="submit"]');

        if (submits.length === 0) {
            submits = $form.find('button[type="submit"]');
        }
        if (submits.length > 0) {
            submits[0].click();
        }
    }
    return false;
}

function configureChart($chart) {
    var $toolTip = $chart
        .append('<div class="tooltip top" role="tooltip"><div class="tooltip-arrow"></div><div class="tooltip-inner"></div></div>')
        .find('.tooltip');

    $chart.on('mouseenter', '.ct-bar', function() {
        var $bar = $(this),
            value = $bar.attr('ct:value'),
            pos = $bar.offset();

        $toolTip.find('.tooltip-inner').html(value);
        pos.top -= $toolTip.outerHeight();
        pos.left -= $toolTip.outerWidth() / 2 + 7.5 /* stroke-width / 2 */;
        $toolTip.offset(pos);
        $toolTip.css('opacity', 1);
    });

    $chart.on('mouseleave', '.ct-bar', function() {
        $toolTip.css('opacity', 0);
    });
}


function loadActivityChart(element) {
    if (activityDataLoaded) {
        return;
    }
    activityDataLoaded = true;

    increaseLoading('#activity-loading');
    $.ajax({
        url: element.data('monthly'),
        success: function(data) {
            Chartist.Bar('#activity-month', data);
            configureChart($('#activity-month'));
            decreaseLoading('#activity-loading');
        },
        dataType: 'json'
    });

    increaseLoading('#activity-loading');
    $.ajax({
        url: element.data('yearly'),
        success: function(data) {
            Chartist.Bar('#activity-year', data);
            configureChart($('#activity-year'));
            decreaseLoading('#activity-loading');
        },
        dataType: 'json'
    });
}

function screenshotStart() {
    $('#search-results').empty();
    increaseLoading('#screenshots-loading');
}

function screenshotFailure() {
    screenshotLoaded({responseCode: 500});
}

function screenshotAddString() {
    var pk = $(this).data('pk');
    var addLoadId = '#adding-' + pk;
    var form = $('#screenshot-add-form');

    $('#add-source').val(pk);
    increaseLoading(addLoadId);
    $.ajax({
        type: 'POST',
        url: form.attr('action'),
        data: form.serialize(),
        dataType: 'json',
        success: function () {
            var list = $('#sources-listing');

            decreaseLoading(addLoadId);
            $(addLoadId).parents('tr').fadeOut();
            $.get(list.data('href'), function (data) {
                list.html(data);
            });
        },
        error: function () {
            decreaseLoading(addLoadId);
        }
    });
}

function screnshotResultError(severity, message) {
    $('#search-results').html(
        '<tr class="' + severity + '"><td colspan="2">' + message + '</td></tr>'
    );
}

function screenshotResultSet(results) {
    $('#search-results').empty();
    $.each(results, function (idx, value) {
        var row = $(
            '<tr><td class="text"></td>' +
            '<td class="context"></td>' +
            '<td class="location"></td>' +
            '<td><a class="add-string btn btn-primary"><i class="fa fa-plus"></i> ' +
            gettext('Add to screenshot') +
            '</a><i class="fa fa-spinner fa-spin"></i></tr>'
        );

        row.find('.text').text(value.text);
        row.find('.context').text(value.context);
        row.find('.location').text(value.location);
        row.find('.add-string').data('pk', value.pk);
        row.find('.fa-spin').hide().attr('id', 'adding-' + value.pk);
        $('#search-results').append(row);
    });
    $('#search-results').find('.add-string').click(screenshotAddString);
}

function screenshotLoaded(data) {
    decreaseLoading('#screenshots-loading');
    if (data.responseCode !== 200) {
        screnshotResultError('danger', gettext('Error loading search results!'));
    } else if (data.results.length === 0) {
        screnshotResultError('warning', gettext('No new matching source strings found.'));
    } else {
        screenshotResultSet(data.results);
    }
}

function initEditor() {
    /* Autosizing */
    autosize($('.translation-editor'));

    /* Count characters */
    $(".translation-editor").keyup(function() {
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
    $('.copy-text').click(function (e) {
        var $this = $(this);

        $this.button('loading');
        $this.parents('.translation-item').find('.translation-editor').val(
            $.parseJSON($this.data('content'))
        ).change();
        autosize.update($('.translation-editor'));
        $('#id_' + $this.data('checksum') + '_fuzzy').prop('checked', true);
        $this.button('reset');
        e.preventDefault();
    });

    /* Direction toggling */
    $('.direction-toggle').change(function () {
        var $this = $(this);

        $this.parents('.translation-item').find('.translation-editor').attr(
            'dir',
            $this.find('input').val()
        );
    });

    /* Special characters */
    $('.specialchar').click(function (e) {
        var $this = $(this);
        var text = $this.data('value');

        $this.parents('.translation-item').find('.translation-editor').insertAtCaret(text).change();
        autosize.update($('.translation-editor'));
        e.preventDefault();
    });

}

function testChangeHandler(e) {
    if (e.key && e.key === 'Tab') {
        return;
    }
    $(this).parents('form').find('[name=fuzzy]').prop('checked', false);
}

function processMachineTranslation(data, scope) {
    decreaseLoading('#' + scope + '-loading');
    if (data.responseStatus === 200) {
        data.translations.forEach(function (el, idx) {
            var newRow = $('<tr/>').data('quality', el.quality);
            var done = false;
            var $machineTranslations = $('#' + scope + '-translations');

            newRow.append($('<td/>').attr('class', 'target').attr('lang', data.lang).attr('dir', data.dir).text(el.text));
            newRow.append($('<td/>').text(el.source));
            if (scope === "mt") {
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
                    // newRow.append($('<td/>').text(interpolate('%s (%s)', [el.service, ])));
                }
                newRow.append(service);
            } else {
                newRow.append($('<td/>').text(el.origin));
            }
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
                '<a class="copymt btn btn-xs btn-default">' +
                '<i class="fa fa-clipboard"></i> ' +
                gettext('Copy') +
                '<span class="mt-number text-info"></span>' +
                '</a>' +
                '</td>' +
                '<td>' +
                '<a class="copymt-save btn btn-xs btn-primary">' +
                '<i class="fa fa-save"></i> ' +
                gettext('Copy and save') +
                '</a>' +
                '</td>'
            ));
            $machineTranslations.children('tr').each(function (idx) {
                if ($(this).data('quality') < el.quality && !done) {
                    $(this).before(newRow);
                    done = true;
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
            /* Standard worflow */
            $('.translation-form input[name="fuzzy"]').prop('checked', true);
            /* Review workflow */
            $('.translation-form input[name="review"][value="10"]').prop('checked', true);
        });
        $('a.copymt-save').click(function () {
            var text = $(this).parent().parent().find('.target').text();

            $('.translation-editor').val(text).change();
            autosize.update($('.translation-editor'));
            /* Standard worflow */
            $('.translation-form input[name="fuzzy"]').prop('checked', false);
            /* Review workflow */
            $('.translation-form input[name="review"][value="20"]').prop('checked', true);
            submitForm({target:$('.translation-editor')});
        });

        for (var i = 1; i < 10; i++) {
            Mousetrap.bindGlobal(
                ['ctrl+m ' + i, 'command+m ' + i],
                function() {
                    return false;
                }
            );
        }

        var $machineTranslations = $('#' + scope + '-translations');

        $machineTranslations.children('tr').each(function (idx) {
            if (idx < 10) {
                var key = getNumericKey(idx);

                $(this).find('.mt-number').html(
                    ' <kbd title="' +
                    interpolate(gettext('Ctrl+M then %s'), [key]) +
                    '">' +
                    key +
                    '</kbd>'
                );
                Mousetrap.bindGlobal(
                    ['ctrl+m ' + key, 'command+m ' + key],
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

        $('#' + scope + '-errors').append(
            $('<li>' + msg + ' ' + data.responseDetails + '</li>')
        );
    }
}

function failedMachineTranslation(jqXHR, textStatus, errorThrown, scope) {
    decreaseLoading('#' + scope + '-loading');
    $('#' + scope + '-errors').append(
        $('<li>' + gettext('The request for machine translation has failed:') + ' ' + textStatus + ': ' + errorThrown + '</li>')
    );
}

function loadMachineTranslations(data, textStatus) {
    var $form = $('#link-post');
    decreaseLoading('#mt-loading');
    data.forEach(function (el, idx) {
        increaseLoading('#mt-loading');
        $.ajax({
            type: 'POST',
            url: $('#js-translate').attr('href').replace('__service__', el),
            success: function (data) {processMachineTranslation(data, 'mt');},
            error: function (jqXHR, textStatus, errorThrown) {failedMachineTranslation(jqXHR, textStatus, errorThrown, 'mt');},
            dataType: 'json',
            data: {
                csrfmiddlewaretoken: $form.find('input').val(),
            },
        });
    });
}

function isNumber(n) {
    return !isNaN(parseFloat(n)) && isFinite(n);
}

function compareCells(a, b) {
    if (a.indexOf('%') !== -1 && b.indexOf('%') !== -1) {
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

function loadTableSorting() {
    $('table.sort').each(function () {
        var table = $(this),
            tbody = table.find('tbody'),
            thead = table.find('thead'),
            thIndex = 0;

        $(this).find('thead th').each(function () {
            var th = $(this),
                inverse = 1;

            // handle colspan
            if (th.attr('colspan')) {
                thIndex += parseInt(th.attr('colspan'), 10) - 1;
            }
            // skip empty cells and cells with icon (probably already processed)
            if (th.text() !== '' && ! th.hasClass('sort-cell') && ! th.hasClass('sort-skip')) {
                // Store index copy
                let myIndex = thIndex;
                // Add icon, title and class
                th.attr('title', gettext('Sort this column')).addClass('sort-cell').append('<i class="sort-button fa fa-chevron-down sort-none" />');

                // Click handler
                th.click(function () {

                    tbody.find('tr').sort(function(a, b) {
                        var $a = $(a), $b = $(b);
                        var a_parent = $a.data('parent'), b_parent = $b.data('parent');
                        if (a_parent) {
                            $a = tbody.find('#' + a_parent);
                        }
                        if (b_parent) {
                            $b = tbody.find('#' + b_parent);
                        }
                        return inverse * compareCells(
                            $.text($a.find('td,th')[myIndex]),
                            $.text($b.find('td,th')[myIndex])
                        );
                    }).appendTo(tbody);
                    thead.find('i.sort-button').removeClass('fa-chevron-down fa-chevron-up').addClass('fa-chevron-down sort-none');
                    if (inverse === 1) {
                        $(this).find('i.sort-button').addClass('fa-chevron-down').removeClass('fa-chevron-up sort-none');
                    } else {
                        $(this).find('i.sort-button').addClass('fa-chevron-up').removeClass('fa-chevron-down sort-none');
                    }

                    inverse = inverse * -1;

                });
            }
            // Increase index
            thIndex += 1;
        });

    });
}

function zenEditor() {
    var $this = $(this);
    var $row = $this.parents('tr');
    var checksum = $row.find('[name=checksum]').val();

    $row.addClass('translation-modified');

    var form = $row.find('form');
    var statusdiv = $('#status-' + checksum).hide();
    var loadingdiv = $('#loading-' + checksum).show();
    $.ajax({
        type: 'POST',
        url: form.attr('action'),
        data: form.serialize(),
        dataType: 'json',
        error: screenshotFailure,
        success: function (data) {
            loadingdiv.hide();
            statusdiv.show();
            if (data.state == 'danger') {
                statusdiv.attr('class', 'fa-times-circle text-danger');
            } else if (data.state == 'warning') {
                statusdiv.attr('class', 'fa-exclamation-circle text-warning');
            } else if (data.state == 'info') {
                statusdiv.attr('class', 'fa-check-circle text-warning');
            } else {
                statusdiv.attr('class', 'fa-check-circle text-success');
            }
            statusdiv.addClass('fa').tooltip('destroy');
            if (data.messages !== '') {
                statusdiv.tooltip({
                    'html': true,
                    'title': data.messages
                });
            };
            $row.removeClass('translation-modified').addClass('translation-saved');
            if (data.translationsum !== '') {
                $row.find('input[name=translationsum]').val(data.translationsum);
            }
        }
    });
}


function insertEditor(text, element)
{
    var root;

    /* Find withing root element */
    if (typeof element !== 'undefined') {
        root = element.parents('.zen-unit');
        if (root.length === 0) {
            root = element.parents('.translation-form');
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

/* Thin wrappers for django to avoid problems when i18n js can not be loaded */
function gettext(msgid) {
    if (typeof django !== 'undefined') {
        return django.gettext(msgid);
    }
    return msgid;
}
function pgettext(context, msgid) {
    if (typeof django !== 'undefined') {
        return django.pgettext(context, msgid);
    }
    return msgid;
}
function interpolate(fmt, obj, named) {
    if (typeof django !== 'undefined') {
        return django.interpolate(fmt, obj, named);
    }
    return fmt.replace(/%s/g, function() {return String(obj.shift())});
}

function load_matrix() {
    var $loadingNext = $('#loading-next');
    var $loader = $('#matrix-load');
    var offset = parseInt($loader.data('offset'));

    if ($('#last-section').length > 0 || $loadingNext.css('display') !== 'none') {
        return;
    }
    $loadingNext.show();

    $loader.data('offset', 20 + offset);

    $.get(
        $loader.attr('href') + '&offset=' + offset,
        function (data) {
            $loadingNext.hide();
            $('.matrix tfoot').before(data);
        }
    );
}

$(function () {
    var $window = $(window), $document = $(document);
    /* AJAX loading of tabs/pills */
    $document.on('show.bs.tab', '[data-toggle="tab"][data-href], [data-toggle="pill"][data-href]', function (e) {
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
            function (responseText, status, xhr) {
                if ( status !== 'success' ) {
                    var msg = gettext('Error while loading page:');
                    $content.text(msg + ' ' + xhr.statusText + ' (' + xhr.status + '): ' + responseText);
                }
                $target.data('loaded', 1);
                loadTableSorting();
            }
        );
    });

    if ($('#form-activetab').length > 0) {
        $document.on('show.bs.tab', '[data-toggle="tab"]', function (e) {
            var $target = $(e.target);
            $('#form-activetab').attr('value', $target.attr('href'));
        });
    }

    /* Activity charts on tabs */
    $document.on('show.bs.tab', '[data-load="activity"]', function (e) {
        loadActivityChart($(this));
    });

    /* Automatic loading of activity charts on page load */
    var autoLoadActivity = $('#load-activity');
    if (autoLoadActivity.length > 0) {
        loadActivityChart(autoLoadActivity);
    }

    /* Machine translation */
    $document.on('show.bs.tab', '[data-load="mt"]', function (e) {
        if (machineTranslationLoaded) {
            return;
        }
        machineTranslationLoaded = true;
        increaseLoading('#mt-loading');
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
        increaseLoading('#memory-loading');
        var $form = $('#link-post');
        $.ajax({
            type: 'POST',
            url: $('#js-translate').attr('href').replace('__service__', 'weblate-translation-memory'),
            success: function (data) {processMachineTranslation(data, 'memory');},
            error: function (jqXHR, textStatus, errorThrown) {failedMachineTranslation(jqXHR, textStatus, errorThrown, 'memory');},
            dataType: 'json',
            data: {
                csrfmiddlewaretoken: $form.find('input').val(),
            },
        });
    });

    $('#memory-search').submit(function () {
        var form = $(this);

        increaseLoading('#memory-loading');
        $('#memory-translations').empty();
        $.ajax({
            type: 'POST',
            url: form.attr('action'),
            data: form.serialize(),
            dataType: 'json',
            success: function (data) {processMachineTranslation(data, 'memory');},
            error: function (jqXHR, textStatus, errorThrown) {failedMachineTranslation(jqXHR, textStatus, errorThrown, 'memory');},
        });
        return false;
    });

    /* Git commit tooltip */
    $('.html-tooltip').each(function () {
        var $this = $(this);
        $this.tooltip({
            html: true,
            title: $this.find('.tooltip-content').html()
        });
    });
    $('.text-tooltip').tooltip();

    /* Hiding spam protection field */
    $('#s_content').hide();
    $('#id_content').parent('div').hide();
    $('#div_id_content').hide();

    /* Form automatic submission */
    $('form.autosubmit select').change(function () {
        $('form.autosubmit').submit();
    });

    /* Row expander */
    $('.expander').click(function () {
        var $this = $(this);
        var $tableRow = $this.closest('tr');
        var $nextRow = $tableRow.next();
        $nextRow.toggle();
        $tableRow.find('.expand-icon').toggleClass('fa-chevron-right').toggleClass('fa-chevron-down');
        var $loader = $nextRow.find('.load-details');
        if ($loader.length > 0) {
            var url = $loader.attr('href');
            $loader.remove();
            $.get(
                url,
                function (data) {
                    var $cell = $nextRow.find('.details-content');
                    $cell.find('.fa-spin').remove();
                    $cell.append(data);
                    $cell.find('[data-flag]').click(function (e) {
                        var $this = $(this);
                        var $textarea = $this.closest('td').find('input[type="text"]');
                        if ($textarea.val().length > 0) {
                            $textarea.val($textarea.val() + ',' + $this.data('flag'));
                        } else {
                            $textarea.val($this.data('flag'));
                        }
                        e.preventDefault();
                    });
                }
            );
        }
    });

    /* Auto expand expander */
    $('.auto-expand').each(function () {
        $(this).click();
    });

    var activeTab;

    /* Load correct tab */
    if (location.hash !== '') {
        /* From URL hash */
        var separator = location.hash.indexOf('__');
        if (separator != -1) {
            activeTab = $('[data-toggle=tab][href="' + location.hash.substr(0, separator) + '"]');
            if (activeTab.length) {
                activeTab.tab('show');
            }
        }
        activeTab = $('[data-toggle=tab][href="' + location.hash + '"]');
        if (activeTab.length) {
            activeTab.tab('show');
            window.scrollTo(0, 0);
        }
    } else if ($('.translation-tabs').length > 0 && Cookies.get('translate-tab')) {
        /* From cookie */
        activeTab = $('[data-toggle=tab][href="' + Cookies.get('translate-tab') + '"]');
        if (activeTab.length) {
            activeTab.tab('show');
        }
    }

    /* Add a hash to the URL when the user clicks on a tab */
    $('a[data-toggle="tab"]').on('shown.bs.tab', function(e) {
        history.pushState(null, null, $(this).attr('href'));
        /* Remove focus on rows */
        $('.selectable-row').removeClass('active');
    });

    /* Store active translation tab in cookie */
    $('.translation-tabs a[data-toggle="tab"]').on('shown.bs.tab', function(e) {
        Cookies.remove('translate-tab', { path: '' });
        Cookies.set('translate-tab', $(this).attr('href'), { path: '/', expires: 365 });
    });

    /* Navigate to a tab when the history changes */
    window.addEventListener('popstate', function(e) {
        if (location.hash !== '') {
            activeTab = $('[data-toggle=tab][href="' + location.hash + '"]');
        } else {
            activeTab = Array();
        }
        if (activeTab.length) {
            activeTab.tab('show');
        } else {
            $('.nav-tabs a:first').tab('show');
        }
    });

    /* Activate tab with error */
    var formErrors = $('div.has-error');
    if (formErrors.length > 0) {
        var tab = formErrors.closest('div.tab-pane');
        if (tab.length > 0) {
            $('[data-toggle=tab][href="#' + tab.attr('id')+ '"]').tab('show');
        }
    }

    /* Translation editor */
    Mousetrap.bindGlobal(
        ['alt+enter', 'ctrl+enter', 'command+enter'],
        submitForm
    );
    var translationEditor = $('.translation-editor');
    if (translationEditor.length > 0) {
        $document.on('change', '.translation-editor', testChangeHandler);
        $document.on('keypress', '.translation-editor', testChangeHandler);
        $document.on('keydown', '.translation-editor', testChangeHandler);
        $document.on('paste', '.translation-editor', testChangeHandler);
        $document.on('focusin', '.translation-editor', function () { lastEditor = $(this); });
        initEditor();
        translationEditor.get(0).focus();
        if ($('#button-first').length > 0) {
            Mousetrap.bindGlobal('alt+end', function(e) {window.location = $('#button-end').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+pagedown', function(e) {window.location = $('#button-next').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+pageup', function(e) {window.location = $('#button-prev').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+home', function(e) {window.location = $('#button-first').attr('href'); return false;});
            Mousetrap.bindGlobal(['ctrl+o', 'command+o'], function(e) {$('.translation-item .copy-text').click(); return false;});
            Mousetrap.bindGlobal(['ctrl+y', 'command+y'], function(e) {$('input[name="fuzzy"]').click(); return false;});
            Mousetrap.bindGlobal(
                ['ctrl+shift+enter', 'command+shift+enter'],
                function(e) {$('input[name="fuzzy"]').prop('checked', false); return submitForm(e);}
            );
            Mousetrap.bindGlobal(
                ['ctrl+e', 'command+e'],
                function(e) {
                    $('.translation-editor').get(0).focus();
                    return false;
                }
            );
            Mousetrap.bindGlobal(
                ['ctrl+s', 'command+s'],
                function(e) {
                    $('#search-dropdown').click();
                    $('input[name="q"]').focus();
                    return false;
                }
            );
            Mousetrap.bindGlobal(
                ['ctrl+u', 'command+u'],
                function(e) {
                    $('.nav [href="#comments"]').click();
                    $('textarea[name="comment"]').focus();
                    return false;
                }
            );
            Mousetrap.bindGlobal(
                ['ctrl+j', 'command+j'],
                function(e) {
                    $('.nav [href="#nearby"]').click();
                    return false;
                }
            );
            Mousetrap.bindGlobal(
                ['ctrl+m', 'command+m'],
                function(e) {
                    $('.nav [href="#machine"]').click();
                    return false;
                }
            );
        }
    }

    /* Generic tooltips */
    $('.tooltip-control').tooltip();

    /* Whiteboard message discard */
    $('.alert').on('close.bs.alert', function () {
        var $this = $(this);
        var $form = $('#link-post');

        if ($this.data('action')) {
            $.ajax({
                type: 'POST',
                url: $this.data('action'),
                data: {
                    csrfmiddlewaretoken: $form.find('input').val(),
                    id: $this.data('id'),
                },
            });
        }
        $this.tooltip('destroy');
    });

    /* Check ignoring */
    $('.dismiss-single,.dismiss-all').click(function () {
        var $this = $(this);
        var $form = $('#link-post');

        $.ajax({
            type: 'POST',
            url: $this.attr('href'),
            data: {
                csrfmiddlewaretoken: $form.find('input').val(),
            },
        });
        $this.parents('.check').remove();
        return false;
    });

    /* Check fix */
    $('[data-check-fixup]').click(function (e) {
        var fixups = $(this).data('check-fixup');
        $('.translation-editor').each(function () {
            var $this = $(this);
            $.each(fixups, function (key, value) {
                var re = new RegExp(value[0], "gu");
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
            ['ctrl+' + i, 'command+' + i],
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

                $(this).attr('title', interpolate(gettext('Ctrl/Command+%s'), [key]));
                $(this).find('.highlight-number').html('<kbd>' + key + '</kbd>');

                Mousetrap.bindGlobal(
                    ['ctrl+' + key, 'command+' + key],
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
    Mousetrap.bindGlobal(['ctrl', 'command'], function (e) {
        $('.highlight-number').show();
    }, 'keydown');
    Mousetrap.bindGlobal(['ctrl', 'command'], function (e) {
        $('.highlight-number').hide();
    }, 'keyup');

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
    loadTableSorting();

    /* Table column changing */
    $('.columns-menu').each(function () {
        var columnsMenu = $(this);
        var columnsPanel = columnsMenu.closest('div.tab-pane');
        if (columnsPanel.length === 0) {
            columnsPanel = columnsMenu.closest('div.content');
        }
        var width = columnsPanel.width();

        columnsMenu.on('click', function(e) {
            e.stopPropagation();
        });
        columnsMenu.find('input').on('click', function(e) {
            var $this = $(this);

            columnsPanel.find('.' + $this.attr('id').replace('toggle-', 'col-')).toggle($this.attr('checked'));
            e.stopPropagation();
        });
        columnsMenu.find('a').on('click', function(e) {
            $(this).find('input').click();
            e.stopPropagation();
            e.preventDefault();
        });
        if (width < 800) {
            columnsMenu.find('#toggle-comments').click();
        }
        if (width < 700) {
            columnsMenu.find('#toggle-suggestions').click();
        }
        if (width < 600) {
            columnsMenu.find('#toggle-checks').click();
        }
        if (width < 500) {
            columnsMenu.find('#toggle-fuzzy').click();
        }
        if (width < 500) {
            columnsMenu.find('#toggle-words-total').click();
            columnsMenu.find('#toggle-strings-total').click();
        }
        if (width < 300) {
            columnsMenu.find('#toggle-words').click();
        }
    });

    /* Matrix mode handling */
    if ($('.matrix').length > 0) {
        load_matrix();
        $window.scroll(function() {
            if ($window.scrollTop() >= $document.height() - (2 * $window.height())) {
                load_matrix();
            }
        });
    };


    /* Zen mode handling */
    if ($('.zen').length > 0) {
        $window.scroll(function() {
            var $loadingNext = $('#loading-next');
            var loader = $('#zen-load');

            if ($window.scrollTop() >= $document.height() - (2 * $window.height())) {
                if ($('#last-section').length > 0 || $loadingNext.css('display') !== 'none') {
                    return;
                }
                $loadingNext.show();

                loader.data('offset', 20 + parseInt(loader.data('offset'), 10));

                $.get(
                    loader.attr('href') + '&offset=' + loader.data('offset'),
                    function (data) {
                        $loadingNext.hide();

                        $('.zen tfoot').before(data);

                        initEditor();
                    }
                );
            }
        });

        /*
         * Ensure current editor is reasonably located in the window
         * - show whole element if moving back
         * - scroll down if in bottom half of the window
         */
        $document.on('focus', '.zen .translation-editor', function() {
            var current = $window.scrollTop();
            var row_offset = $(this).parents('tbody').offset().top;
            if (row_offset < current || row_offset - current > $window.height() / 2) {
                $([document.documentElement, document.body]).animate({
                    scrollTop: row_offset
                }, 100);
            }
        });

        $document.on('change', '.translation-editor', zenEditor);
        $document.on('change', '.fuzzy_checkbox', zenEditor);
        $document.on('change', '.review_radio', zenEditor);

        Mousetrap.bindGlobal(['ctrl+end', 'command+end'], function(e) {
            $('.zen-unit:last').find('.translation-editor:first').focus();
            return false;
        });
        Mousetrap.bindGlobal(['ctrl+home', 'command+home'], function(e) {
            $('.zen-unit:first').find('.translation-editor:first').focus();
            return false;
        });
        Mousetrap.bindGlobal(['ctrl+pagedown', 'command+pagedown'], function(e) {
            var focus = $(':focus');

            if (focus.length === 0) {
                $('.zen-unit:first').find('.translation-editor:first').focus();
            } else {
                focus.parents('.zen-unit').next().find('.translation-editor:first').focus();
            }
            return false;
        });
        Mousetrap.bindGlobal(['ctrl+pageup', 'command+pageup'], function(e) {
            var focus = $(':focus');

            if (focus.length === 0) {
                $('.zen-unit:last').find('.translation-editor:first').focus();
            } else {
                focus.parents('.zen-unit').prev().find('.translation-editor:first').focus();
            }
            return false;
        });

        $window.on('beforeunload', function() {
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

    /* Check if browser provides native datepicker */
    if (Modernizr.inputtypes.date) {
        $(document).off('.datepicker.data-api');
    }

    /* Datepicker localization */
    var week_start = '1';

    if (typeof django !== 'undefined') {
        week_start = django.formats.FIRST_DAY_OF_WEEK;
    }
    $.fn.datepicker.dates.en = {
        days: [
            gettext('Sunday'), gettext('Monday'), gettext('Tuesday'),
            gettext('Wednesday'), gettext('Thursday'), gettext('Friday'),
            gettext('Saturday'), gettext('Sunday')
        ],
        daysShort: [
            pgettext('Short (eg. three letter) name of day in week', 'Sun'),
            pgettext('Short (eg. three letter) name of day in week', 'Mon'),
            pgettext('Short (eg. three letter) name of day in week', 'Tue'),
            pgettext('Short (eg. three letter) name of day in week', 'Wed'),
            pgettext('Short (eg. three letter) name of day in week', 'Thu'),
            pgettext('Short (eg. three letter) name of day in week', 'Fri'),
            pgettext('Short (eg. three letter) name of day in week', 'Sat'),
            pgettext('Short (eg. three letter) name of day in week', 'Sun')
        ],
        daysMin: [
            pgettext('Minimal (eg. two letter) name of day in week', 'Su'),
            pgettext('Minimal (eg. two letter) name of day in week', 'Mo'),
            pgettext('Minimal (eg. two letter) name of day in week', 'Tu'),
            pgettext('Minimal (eg. two letter) name of day in week', 'We'),
            pgettext('Minimal (eg. two letter) name of day in week', 'Th'),
            pgettext('Minimal (eg. two letter) name of day in week', 'Fr'),
            pgettext('Minimal (eg. two letter) name of day in week', 'Sa'),
            pgettext('Minimal (eg. two letter) name of day in week', 'Su')
        ],
        months: [
            gettext('January'), gettext('February'), gettext('March'),
            gettext('April'), gettext('May'), gettext('June'), gettext('July'),
            gettext('August'), gettext('September'), gettext('October'),
            gettext('November'), gettext('December')
        ],
        monthsShort: [
            pgettext('Short name of month', 'Jan'),
            pgettext('Short name of month', 'Feb'),
            pgettext('Short name of month', 'Mar'),
            pgettext('Short name of month', 'Apr'),
            pgettext('Short name of month', 'May'),
            pgettext('Short name of month', 'Jun'),
            pgettext('Short name of month', 'Jul'),
            pgettext('Short name of month', 'Aug'),
            pgettext('Short name of month', 'Sep'),
            pgettext('Short name of month', 'Oct'),
            pgettext('Short name of month', 'Nov'),
            pgettext('Short name of month', 'Dec')
        ],
        today: gettext('Today'),
        clear: gettext('Clear'),
        weekStart: week_start,
        titleFormat: 'MM yyyy'
    };

    /* Check dismiss shortcuts */
    Mousetrap.bindGlobal(['ctrl+i', 'command+i'], function(e) {});
    for (var i = 1; i < 10; i++) {
        Mousetrap.bindGlobal(
            ['ctrl+i ' + i, 'command+i ' + i],
            function(e) {
                return false;
            }
        );
    }

    if ($('.check').length > 0) {
        $($('.check')[0].parentNode).children('.check').each(function(idx) {
            var $this = $(this);

            if (idx < 10) {
                let key = getNumericKey(idx);

                $(this).find('.check-number').html(
                    ' <kbd title="' +
                    interpolate(gettext('Ctrl+I then %s'), [key]) +
                    '">' +
                    key +
                    '</kbd>'
                );

                Mousetrap.bindGlobal(
                    ['ctrl+i ' + key, 'command+i ' + key],
                    function(e) {
                        $this.find('.dismiss-single').click();
                        return false;
                    }
                );
            } else {
                $(this).find('.check-number').html('');
            }
        });
    }

    /* Labels in dropdown menu in Dashboard */
    $('#views-menu li a').click(function() {
      $('#views-title').html($(this).text()+' <span class="caret"></span>');
    });

    $('.dropdown-menu').find('form').click(function (e) {
        e.stopPropagation();
    });

    $('.link-post').click(function () {
        var $form = $('#link-post');

        $form.attr('action', $(this).attr('href'));
        $form.submit();
        return false;
    });
    $('.link-auto').click();
    $document.on('click', '.thumbnail', function() {
        $('#imagepreview').attr('src', $(this).attr('href'));
        $('#myModalLabel').text($(this).attr('title'));
        $('#imagemodal').modal('show');
        return false;
    });
    /* Screenshot management */
    $('#screenshots-search,#screenshots-auto').click(function () {
        var $this = $(this);

        screenshotStart();
        $.ajax({
            type: 'POST',
            url: $this.data('href'),
            data: $this.parent().serialize(),
            dataType: 'json',
            success: screenshotLoaded,
            error: screenshotFailure,
        });
        return false;
    });

    /* Access management */
    $('.set-group').tooltip({
        title: function() {
            var $this = $(this);

            if ($this.data('error')) {
                return $this.data('error');
            }
            return $this.data('name');
        },
        animation: false
    });
    $('.set-group').click(function () {
        var $this = $(this);
        var $form = $('#set_groups_form');

        $this.tooltip('hide');
        $this.prop('disabled', true);
        $this.data('error', '');
        $this.parent().removeClass('load-error');

        $.ajax({
            type: 'POST',
            url: $form.attr('action'),
            data: {
                csrfmiddlewaretoken: $form.find('input').val(),
                action: ($this.prop('checked') ? 'add' : 'remove'),
                user: $this.data('username'),
                group: $this.data('group'),
            },
            dataType: 'json',
            success: function (data) {
                if (data.responseCode !== 200) {
                    $this.parent().addClass('load-error');
                    $this.data('error', data.message);
                    $this.tooltip('show');
                }
                $this.prop('checked', data.state);
                $this.prop('disabled', false);
            },
            error: function (xhr, textStatus, errorThrown) {
                $this.parent().addClass('load-error');
                $this.data('error', errorThrown);
                $this.tooltip('show');
                $this.prop('disabled', false);
            },
        });
    });

    /* Inline dictionary adding */
    $('.add-dict-inline').submit(function () {
        var form = $(this);

        increaseLoading('#glossary-add-loading');
        $.ajax({
            type: 'POST',
            url: form.attr('action'),
            data: form.serialize(),
            dataType: 'json',
            success: function (data) {
                decreaseLoading('#glossary-add-loading');
                if (data.responseCode === 200) {
                    form.find('tbody').html(data.results);
                    form.find('[name=words]').attr('value', data.words);
                }
                $('.translation-editor:first').focus();
                form.trigger('reset');
            },
            error: function (xhr, textStatus, errorThrown) {
                decreaseLoading('#glossary-add-loading');
            }
        });
        return false;
    });

    /* Avoid double submission of non AJAX forms */
    $('form:not(.double-submission)').on('submit', function(e) {
        var $form = $(this);

        if ($form.data('submitted') === true) {
            // Previously submitted - don't submit again
            e.preventDefault();
        } else {
            // Mark it so that the next submit can be ignored
            $form.data('submitted', true);
        }
    });

    /* Client side form persistence */
    var $forms = $('[data-persist]');
    if ($forms.length > 0 && window.localStorage) {
        /* Load from local storage */
        $forms.each(function () {
            var $this = $(this);
            var storedValue = window.localStorage[$this.data('persist')];
            if (storedValue) {
                storedValue = JSON.parse(storedValue);
                $.each(storedValue, function (key, value) {
                    var target = $this.find('[name=' + key + ']');
                    if (target.is(":checkbox")) {
                        target.prop('checked', value);
                    } else {
                        target.val(value);
                    }
                });
            }
        });
        /* Save on submit */
        $forms.submit(function (e) {
            var data = {};
            var $this = $(this);

            $this.find(':checkbox').each(function () {
                var $this = $(this);

                data[$this.attr('name')] = $this.prop('checked');
            });
            $this.find('select').each(function () {
                var $this = $(this);

                data[$this.attr('name')] = $this.val();
            });
            window.localStorage[$this.data('persist')] = JSON.stringify(data);
        });
    }

    /* Translate forms persistence */
    $forms = $('.translation-form');
    if ($forms.length > 0 && window.localStorage && window.localStorage.translation_autosave) {
        var translation_restore = JSON.parse(window.localStorage.translation_autosave);

        $.each(translation_restore, function () {
            var target = $('#' + this.id);

            if (target.length > 0) {
                target.val(this.value);
                autosize.update(target);
            }
        });
        localStorage.removeItem('translation_autosave');
    }

    /*
     * Disable modal enforce focus to fix compatibility
     * issues with ClipboardJS, see https://stackoverflow.com/a/40862005/225718
     */
    $.fn.modal.Constructor.prototype.enforceFocus = function() {};

    /* Copy to clipboard */
    var clipboard = new ClipboardJS('[data-clipboard-text]');
    clipboard.on('success', function(e) {
        var $trigger = $(e.trigger);
        // Backup current text
        var backup = $trigger.attr('data-original-title');

        // Change text to copied
        $trigger.attr('data-original-title', gettext('Copied')).tooltip('show');
        // Restore original
        $trigger.attr('data-original-title', backup);
    });

    /* Auto translate source select */
    var select_auto_source = $('input[name="auto_source"]');
    if (select_auto_source.length > 0) {
        select_auto_source.on('change', function() {
            if ($('input[name="auto_source"]:checked').val() == 'others') {
                $('#auto_source_others').show();
                $('#auto_source_mt').hide();
            } else {
                $('#auto_source_others').hide();
                $('#auto_source_mt').show();
            }
        });
        select_auto_source.trigger('change');
    }

    /* Override all multiple selects */
    $('select[multiple]').multi({
        'enable_search': true,
        'search_placeholder': gettext('Search…'),
        'non_selected_header': gettext('Available:'),
        'selected_header': gettext('Chosen:')
    });

    $('.auto-save-translation').on('submit', function () {
        if (window.localStorage) {
            let data = $('.translation-editor').map(function () {
                var $this = $(this);

                return {id: $this.attr('id'), value: $this.val()};
            });

            window.localStorage.translation_autosave = JSON.stringify(data.get());
        }
    });

    /* Slugify name */
    $('input[name="slug"]').each(function () {
        var $slug = $(this);
        var $form = $slug.parents('form');
        $form.find('input[name="name"]').on('change keypress keydown paste', function () {
            $slug.val(slugify($(this).val()).toLowerCase());
        });

    });

    /* Component update progress */
    $('[data-progress-url]').each(function () {
        var $progress = $(this);
        var $pre = $progress.find('pre'), $bar = $progress.find('.progress-bar');

        $pre.animate({scrollTop: $pre.get(0).scrollHeight});

        var progress_interval = setInterval(function() {
            $.get($progress.data('progress-url'), function (data) {
                $bar.width(data.progress + '%');
                $pre.text(data.log);
                $pre.animate({scrollTop: $pre.get(0).scrollHeight});
                if (! data.in_progress) {
                    clearInterval(progress_interval);
                    if ($('#progress-redirect').prop('checked')) {
                        window.location = $('#progress-return').attr('href');
                    }
                }
            });
        }, 1000);
    });

    /* Generic messages progress */
    $('[data-task]').each(function () {
        var $message = $(this);
        var $bar = $message.find('.progress-bar');

        var task_interval = setInterval(function() {
            $.get($message.data('task'), function (data) {
                $bar.width(data.progress + '%');
                console.log(data);
                if (data.completed) {
                    clearInterval(task_interval);
                    $message.text(data.result);
                }
            });
        }, 1000);
    });

    /* Disable invalid file format choices */
    $('.invalid-format').each(function () {
        $(this).parent().find('input').attr('disabled', '1');
    });

    /* Branch loading */
    $('.branch-loader select[name=component]').change(function () {
        var $this = $(this);
        var $form = $this.parents('form');
        var branches = $form.data('branches');
        var $select = $form.find('select[name=branch]');
        $select.empty();
        $.each(branches[$this.val()], function(key, value) {
            $select.append($("<option></option>").attr("value", value).text(value));
        });
    });

    /* Advanced search */
    $('.search-group li a').click(function () {
        var $this = $(this);
        var $button = $this.parents('.input-group-btn').find('button');
        $button.data('field', $this.data('field'));
        $button.find('span.search-label').text($this.text());
    });
    $('.search-add').click(function () {
        var group = $(this).parents('.input-group');
        var button = group.find('button');
        var input = group.find('input');

        if (input.val() !== '') {
            $('#id_q').insertAtCaret(' ' + button.data('field') + input.val() + ' ');
        }
    });
    $('.search-insert').click(function () {
        $('#id_q').insertAtCaret(' ' + $(this).parents('tr').find('code').text() + ' ');
    });

    /* Warn users that they do not want to use developer console in most cases */
    console.log("%cStop!", "color: red; font-weight: bold; font-size: 50px;");
    console.log( "%cThis is a console for developers. If someone has asked you to open this "
               + "window, they are likely trying to compromise your Weblate account."
               , "color: red;"
                );
    console.log("%cPlease close this window now.", "color: blue;");
});
