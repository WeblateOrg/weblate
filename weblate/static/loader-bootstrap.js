var loading = 0;
var activityDataLoaded = false;

// Remove some weird things from location hash
if (window.location.hash && (window.location.hash.indexOf('"') > -1 || window.location.hash.indexOf('=') > -1)) {
    window.location.hash = '';
}

// Loading indicator handler
function increaseLoading(sel) {
    if (loading === 0) {
        $('#loading-' + sel).show();
    }
    loading += 1;
}

function decreaseLoading(sel) {
    loading -= 1;
    if (loading === 0) {
        $('#loading-' + sel).hide();
    }
}

function addAlert(message, kind="danger") {
    var alerts = $('#popup-alerts');
    var e = $('<div class="alert alert-' + kind + ' alert-dismissible" role="alert"><button type="button" class="close" data-dismiss="alert" aria-label="Close"><span aria-hidden="true">&times;</span></button></div>');
    e.append(new Text(message));
    alerts.show().append(e);
    e.on('closed.bs.alert', function () {
        if (alerts.find('.alert').length == 0) {
            alerts.hide();
        }
    });
    setTimeout(function () {
        e.alert('close');
    }, 5000);
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
    var $form = $target.closest('form');

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
Mousetrap.bindGlobal(
    ['alt+enter', 'mod+enter'],
    submitForm
);

function loadActivityChart(element) {
    if (activityDataLoaded) {
        return;
    }
    activityDataLoaded = true;

    increaseLoading('activity');
    $.ajax({
        url: element.data('monthly'),
        success: function(data) {
            Chartist.Bar('#activity-month', data);
            decreaseLoading('activity');
        },
        error: function (jqXHR, textStatus, errorThrown) {
            addAlert(errorThrown);
        },
        dataType: 'json'
    });

    increaseLoading('activity');
    $.ajax({
        url: element.data('yearly'),
        success: function(data) {
            Chartist.Bar('#activity-year', data);
            decreaseLoading('activity');
        },
        error: function (jqXHR, textStatus, errorThrown) {
            addAlert(errorThrown);
        },
        dataType: 'json'
    });
}

function screenshotStart() {
    $('#search-results').empty();
    increaseLoading('screenshots');
}

function screenshotFailure() {
    screenshotLoaded({responseCode: 500});
}

function screenshotAddString() {
    var pk = $(this).data('pk');
    var form = $('#screenshot-add-form');

    $('#add-source').val(pk);
    $.ajax({
        type: 'POST',
        url: form.attr('action'),
        data: form.serialize(),
        dataType: 'json',
        success: function () {
            var list = $('#sources-listing');

            $.get(list.data('href'), function (data) {
                list.html(data);
            });
        },
        error: function (jqXHR, textStatus, errorThrown) {
            addAlert(errorThrown);
        }
    });
}

function screnshotResultError(severity, message) {
    $('#search-results').html(
        '<tr class="' + severity + '"><td colspan="4">' + message + '</td></tr>'
    );
}

function screenshotResultSet(results) {
    $('#search-results').empty();
    $.each(results, function (idx, value) {
        var row = $(
            '<tr><td class="text"></td>' +
            '<td class="context"></td>' +
            '<td class="location"></td>' +
            '<td><a class="add-string btn btn-primary"> ' +
            gettext('Add to screenshot') + '</tr>'
        );

        row.find('.text').text(value.text);
        row.find('.context').text(value.context);
        row.find('.location').text(value.location);
        row.find('.add-string').data('pk', value.pk);
        $('#search-results').append(row);
    });
    $('#search-results').find('.add-string').click(screenshotAddString);
}

function screenshotLoaded(data) {
    decreaseLoading('screenshots');
    if (data.responseCode !== 200) {
        screnshotResultError('danger', gettext('Error loading search results!'));
    } else if (data.results.length === 0) {
        screnshotResultError('warning', gettext('No new matching source strings found.'));
    } else {
        screenshotResultSet(data.results);
    }
}

function isNumber(n) {
    return !isNaN(parseFloat(n)) && isFinite(n);
}

function extractText(cell) {
    var value = $(cell).data('value');
    if (typeof value !== 'undefined') {
        return value;
    }
    return $.text(cell);
}

function compareCells(a, b) {
    if (typeof a === 'number' && typeof b === 'number') {
    } else if (a.indexOf('%') !== -1 && b.indexOf('%') !== -1) {
        a = parseFloat(a.replace(',', '.'));
        b = parseFloat(b.replace(',', '.'));
    } else if (isNumber(a) && isNumber(b)) {
        a = parseFloat(a.replace(',', '.'));
        b = parseFloat(b.replace(',', '.'));
    } else if (typeof a === 'string' && typeof b === 'string') {
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
                th.attr('title', gettext('Sort this column')).addClass('sort-cell').append('<span class="sort-icon" />');

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
                            extractText($a.find('td,th')[myIndex]),
                            extractText($b.find('td,th')[myIndex])
                        );
                    }).appendTo(tbody);
                    thead.find('.sort-icon').removeClass('sort-down sort-up');
                    if (inverse === 1) {
                        $(this).find('.sort-icon').addClass('sort-down');
                    } else {
                        $(this).find('.sort-icon').addClass('sort-up');
                    }

                    inverse = inverse * -1;

                });
            }
            // Increase index
            thIndex += 1;
        });

    });
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

function adjustColspan() {
    $('table.autocolspan').each(function () {
        var $this = $(this);
        var numOfVisibleCols = $this.find('thead th:visible').length;
        $this.find('td.autocolspan').attr('colspan', numOfVisibleCols - 1);
    });

}

function quoteSearch(value) {
    if (value.indexOf(' ') === -1) {
        return value;
    }
    if (value.indexOf('"') === -1) {
        return '"' + value + '"';
    }
    if (value.indexOf("'") === -1) {
        return "'" + value + "'";
    }
    /* We should do some escaping here */
    return value;
}

$(function () {
    var $window = $(window), $document = $(document);

    adjustColspan();
    $window.resize(adjustColspan);
    $document.on('shown.bs.tab', adjustColspan);

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

    /* Hiding spam protection field */
    $('#s_content').hide();
    $('#id_content').parent('div').hide();
    $('#div_id_content').hide();

    /* Form automatic submission */
    $('form.autosubmit select').change(function () {
        $('form.autosubmit').submit();
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

    /* Announcement discard */
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
                error: function (jqXHR, textStatus, errorThrown) {
                    addAlert(errorThrown);
                },
            });
        }
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
    loadTableSorting();

    /* Matrix mode handling */
    if ($('.matrix').length > 0) {
        load_matrix();
        $window.scroll(function() {
            if ($window.scrollTop() >= $document.height() - (2 * $window.height())) {
                load_matrix();
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
            pgettext('Short (for example three letter) name of day in week', 'Sun'),
            pgettext('Short (for example three letter) name of day in week', 'Mon'),
            pgettext('Short (for example three letter) name of day in week', 'Tue'),
            pgettext('Short (for example three letter) name of day in week', 'Wed'),
            pgettext('Short (for example three letter) name of day in week', 'Thu'),
            pgettext('Short (for example three letter) name of day in week', 'Fri'),
            pgettext('Short (for example three letter) name of day in week', 'Sat'),
            pgettext('Short (for example three letter) name of day in week', 'Sun')
        ],
        daysMin: [
            pgettext('Minimal (for example two letter) name of day in week', 'Su'),
            pgettext('Minimal (for example two letter) name of day in week', 'Mo'),
            pgettext('Minimal (for example two letter) name of day in week', 'Tu'),
            pgettext('Minimal (for example two letter) name of day in week', 'We'),
            pgettext('Minimal (for example two letter) name of day in week', 'Th'),
            pgettext('Minimal (for example two letter) name of day in week', 'Fr'),
            pgettext('Minimal (for example two letter) name of day in week', 'Sa'),
            pgettext('Minimal (for example two letter) name of day in week', 'Su')
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

    $('.dropdown-menu').find('form').click(function (e) {
        e.stopPropagation();
    });

    $('.link-post').click(function () {
        var $form = $('#link-post');
        var $this = $(this);

        $form.attr('action', $this.attr('href'));
        $.each($this.data("params"), function (name, value) {
            var elm = $("<input>").attr("name", name).attr("value", value);
            $form.append(elm)
        });
        $form.submit();
        return false;
    });
    $('.link-auto').click();
    $document.on('click', '.thumbnail', function() {
        var $this = $(this);
        $('#imagepreview').attr('src', $this.attr('href'));
        $('#screenshotModal').text($this.attr('title'));
        $('#modalEditLink').attr('href', $this.data('edit'));
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
    $('.set-group').click(function () {
        var $this = $(this);
        var $form = $('#set_groups_form');

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
                    addAlert(data.message);
                }
                $this.prop('checked', data.state);
                $this.prop('disabled', false);
            },
            error: function (xhr, textStatus, errorThrown) {
                addAlert(errorThrown);
                $this.prop('disabled', false);
            },
        });
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
    /* Reset submitted flag when leaving the page, so that it is not set when going back in history */
    $window.on('pagehide', function() {
        $('form:not(.double-submission)').data('submitted', false);
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

    /*
     * Disable modal enforce focus to fix compatibility
     * issues with ClipboardJS, see https://stackoverflow.com/a/40862005/225718
     */
    $.fn.modal.Constructor.prototype.enforceFocus = function() {};

    /* Focus first input in modal */
    $(document).on('shown.bs.modal', function(event) {
        var button = $(event.relatedTarget) // Button that triggered the modal
        var target = button.data('focus');
        if (target) {
            /* Modal context focusing */
            $(target).focus();
        } else {
            $('input:visible:enabled:first', event.target).focus();
        }
    });

    /* Copy to clipboard */
    var clipboard = new ClipboardJS('[data-clipboard-text]');

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

    /* Slugify name */
    slugify.extend({'.': '-'})
    $('input[name="slug"]').each(function () {
        var $slug = $(this);
        var $form = $slug.closest('form');
        $form.find('input[name="name"]').on('change keypress keydown paste', function () {
            $slug.val(slugify($(this).val(), {remove: /[^\w\s-]+/g}).toLowerCase());
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

    // Show the correct toggle button
    if ($('.sort-field').length) {
        var sort_name = $('#query-sort-dropdown span.search-label').text();
        var sort_dropdown_value = $(".sort-field li a").filter(function() {
            return $(this).text() == sort_name;
        }).data('sort');
        var sort_value = $('#id_sort_by').val();
        if (sort_dropdown_value) {
            if (
                sort_value.replace("-", "") === sort_dropdown_value.replace("-", "")
                && sort_value !== sort_dropdown_value
            ) {
                $('#query-sort-toggle .asc').hide();
                $('#query-sort-toggle .desc').show();
            } else {
                $('#query-sort-toggle .desc').hide();
                $('#query-sort-toggle .asc').show();
            }
        }
    }

    /* Branch loading */
    $('.branch-loader select[name=component]').change(function () {
        var $this = $(this);
        var $form = $this.closest('form');
        var branches = $form.data('branches');
        var $select = $form.find('select[name=branch]');
        $select.empty();
        $.each(branches[$this.val()], function(key, value) {
            $select.append($("<option></option>").attr("value", value).text(value));
        });
    });

    /* Click to edit position inline. Disable when clicked outside or pressed ESC */
    $('#position-input').on('click', function() {
        $('#position-input').hide();
        $('#position-input-editable').show();
        $('#position-input-editable input').focus();
        document.addEventListener('click', clickedOutsideEditableInput);
        document.addEventListener('keyup', pressedEscape);
    });
    var clickedOutsideEditableInput = function(event) {
        if (!$.contains($('#position-input-editable')[0], event.target) &&
            event.target != $('#position-input')[0]
        ) {
            $('#position-input').show();
            $('#position-input-editable').hide();
            document.removeEventListener('click', clickedOutsideEditableInput);
            document.removeEventListener('keyup', pressedEscape);
        }
    }
    var pressedEscape = function(event) {
        if (event.key == 'Escape' && event.target != $('#position-input')[0]) {
            $('#position-input').show();
            $('#position-input-editable').hide();
            document.removeEventListener('click', clickedOutsideEditableInput);
            document.removeEventListener('keyup', pressedEscape);
        }
    }

    /* Advanced search */
    $('.search-group li a').click(function () {
        var $this = $(this);
        var $button = $this.closest('.input-group-btn').find('button');
        $button.attr('data-field', $this.data('field'));
        $button.find('span.search-label').not('#query-sort-toggle span').text($this.text());
        if ($this.data('sort')) {
            $('#id_sort_by').val($this.data('sort'));
            if ($this.closest('.result-page-form').length) {
                $this.closest('form').submit();
            }
        }
        if ($this.closest('.query-field').length) {
            $('#id_q').val($this.data('field'));
            if ($this.closest('.result-page-form').length) {
                $this.closest('form').submit();
            }
        }
    });
    $('#query-sort-toggle').click(function () {
        var $this = $(this);
        var $label = $this.find('span.search-label');
        $label.toggle();
        var sort_params = $('#id_sort_by').val().split(",")
        sort_params.forEach(function(param, index) {
            if (param.indexOf("-") !== -1) {
                sort_params[index] = param.replace("-", "");
            } else {
                sort_params[index] = `-${param}`;
            }
        });
        $('#id_sort_by').val(sort_params.join(","));
        if ($this.closest('.result-page-form').length) {
            $this.closest('form').submit();
        }
    });
    $('.search-group input').not('#id_q,#id_position').on('keydown', function (event) {
        if (event.key === "Enter") {
            $(this).closest('.input-group').find('.search-add').click();
            event.preventDefault();
            return false;
        }
    });
    $('#id_q,#id_position').on('keydown', function (event) {
        if (event.key === "Enter") {
            $(this).closest('form').submit();
        }
    });
    $('.search-add').click(function () {
        var group = $(this).closest('.input-group');
        var button = group.find('button');
        var input = group.find('input');

        if (input.length === 0) {
            $('#id_q').insertAtCaret(' ' + button.data('field') + ' ');
        } else if (input.val() !== '') {
            var prefix = '';
            if ($('#is-exact input[type=checkbox]').is(':checked')) {
                prefix = '=';
            }
            $('#id_q').insertAtCaret(' ' + button.data('field') + prefix + quoteSearch(input.val()) + ' ');
        }
    });
    $('.search-insert').click(function () {
        $('#id_q').insertAtCaret(' ' + $(this).closest('tr').find('code').text() + ' ');
    });

    /* Clickable rows */
    $('tr[data-href]').click(function () {
        window.location = $(this).data('href');
    });

    /* ZIP import - autofill name and slug */
    $('#id_zipcreate_zipfile,#id_doccreate_docfile').change(function () {
        var $form = $(this).closest('form');
        var target = $form.find('input[name=name]');
        if (this.files.length > 0 && target.val() === '') {
            var name = this.files[0].name;
            target.val(name.substring(0, name.lastIndexOf('.')));
            target.change();
        }
    });

    /* Warn users that they do not want to use developer console in most cases */
    console.log("%cStop!", "color: red; font-weight: bold; font-size: 50px;");
    console.log( "%cThis is a console for developers. If someone has asked you to open this "
               + "window, they are likely trying to compromise your Weblate account."
               , "color: red;"
                );
    console.log("%cPlease close this window now.", "color: blue;");
});
