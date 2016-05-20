var loading = 0;
var machineTranslationLoaded = false;
var activityDataLoaded = false;

if (window.location.hash && window.location.hash.indexOf("=") > -1) {
    window.location.hash = '';
}

// Loading indicator handler
function increaseLoading(sel) {
    if (loading === 0) {
        $(sel).show();
    }
    loading = loading + 1;
}

function decreaseLoading(sel) {
    loading = loading - 1;
    if (loading === 0) {
        $(sel).hide();
    }
}

function getNumericKey(idx) {
    var ret = idx + 1;
    if (ret == 10) {
        return '0';
    }
    return ret;
}

jQuery.fn.extend({
    insertAtCaret: function (myValue) {
        return this.each(function (i) {
            if (document.selection) {
                // For browsers like Internet Explorer
                this.focus();
                var sel = document.selection.createRange();
                sel.text = myValue;
                this.focus();
            } else if (this.selectionStart || this.selectionStart === 0) {
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


function submitForm(evt) {
    var $target = $(evt.target);
    var $form = $target.parents('form');
    if ($form.length == 0) {
        $form = $('.translation-form');
    }
    if ($form.length > 0) {
        var submits = $form.find('input[type="submit"]');
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
        pos.top = pos.top - $toolTip.outerHeight();
        pos.left = pos.left - ($toolTip.outerWidth() / 2) + 7.5 /* stroke-width / 2 */;
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

function initEditor(editors) {
    /* Autosizing */
    autosize($('.translation-editor'));

    /* Copy source text */
    $('.copy-text').click(function (e) {
        var $this = $(this);
        $this.button('loading');
        $this.parents('.translation-item').find('.translation-editor').val(
            $.parseJSON($this.data('content'))
        );
        autosize.update($('.translation-editor'));
        $('#id_' + $this.data('checksum') + '_fuzzy').prop('checked', true);
        $this.button('reset');
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
        if (text === '\\t') {
            text = '\t';
        } else if (text === '→') {
            text = '\t';
        } else if (text === '↵') {
            text = '\r';
        }
        $this.parents('.translation-item').find('.translation-editor').insertAtCaret(text);
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

function processMachineTranslation(data, textStatus, jqXHR) {
    decreaseLoading('#mt-loading');
    if (data.responseStatus === 200) {
        data.translations.forEach(function (el, idx, ar) {
            var newRow = $('<tr/>').data('quality', el.quality);
            var done = false;
            newRow.append($('<td/>').attr('class', 'target').attr('lang', data.lang).attr('dir', data.dir).text(el.text));
            newRow.append($('<td/>').text(el.source));
            newRow.append($('<td/>').text(el.service));
            /* Translators: Verb for copy operation */
            newRow.append($(
                '<td>' +
                '<a class="copymt btn btn-xs btn-default">' +
                '<i class="fa fa-clipboard"></i> ' +
                gettext('Copy') +
                '<span class="mt-number text-info"></span>' +
                '</a>' +
                '<a class="copymt-save btn btn-xs btn-success">' +
                '<i class="fa fa-save"></i> ' +
                gettext('Copy and save') +
                '</a>' +
                '</td>'
            ));
            var $machineTranslations = $('#machine-translations');
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
            $('.translation-editor').val(text).trigger('autosize.resize');
            $('#id_fuzzy').prop('checked', true);
        });
        $('a.copymt-save').click(function () {
            var text = $(this).parent().parent().find('.target').text();
            $('.translation-editor').val(text).trigger('autosize.resize');
            $('#id_fuzzy').prop('checked', false);
            submitForm({target:$('.translation-editor')});
        });

        for (var i = 1; i < 10; i++){
            Mousetrap.bindGlobal(
                'alt+m ' + i,
                function() {
                    return false;
                }
            );
        }

        var $machineTranslations = $('#machine-translations');
        $machineTranslations.children('tr').each(function (idx) {
            if (idx < 10) {
                var key = getNumericKey(idx);
                $(this).find('.mt-number').html(
                    " <span class='badge kbd-badge' title='" +
                    interpolate(gettext('Alt+M then %s'), [key]) +
                    "'>" +
                    key +
                    "</span>"
                );
                Mousetrap.bindGlobal(
                    'alt+m ' + key,
                    function(e) {
                        $($('#machine-translations').children('tr')[idx]).find('a.copymt').click();
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
        $('#mt-errors').append(
            $('<li>' + msg + ' ' + data.responseDetails + '</li>')
        );
    }
}

function failedMachineTranslation(jqXHR, textStatus, errorThrown) {
    decreaseLoading('#mt-loading');
    $('#mt-errors').append(
        $('<li>' + gettext('The request for machine translation has failed:') + ' ' + textStatus + '</li>')
    );
}

function loadMachineTranslations(data, textStatus, jqXHR) {
    decreaseLoading('#mt-loading');
    data.forEach(function (el, idx, ar) {
        increaseLoading('#mt-loading');
        $.ajax({
            url: $('#js-translate').attr('href') + '?service=' + el,
            success: processMachineTranslation,
            error: failedMachineTranslation,
            dataType: 'json'
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
        $(this).find('thead th')
            .each(function () {

            var th = $(this),
                inverse = 1;
            // handle colspan
            if (th.attr('colspan')) {
                thIndex += parseInt(th.attr('colspan'), 10) - 1;
            }
            // skip empty cells and cells with icon (probably already processed)
            if (th.text() !== '' && ! th.hasClass('sort-cell') && ! th.hasClass('sort-skip')) {
                // Store index copy
                var myIndex = thIndex;
                // Add icon, title and class
                th.attr('title', gettext('Sort this column')).addClass('sort-cell').append('<i class="sort-button fa fa-chevron-down sort-none" />');

                // Click handler
                th.click(function () {

                    tbody.find('td,th').filter(function () {
                        return $(this).index() === myIndex;
                    }).sortElements(function (a, b) {
                        return inverse * compareCells($.text([a]), $.text([b]));
                    }, function () {

                        // parentNode is the element we want to move
                        return this.parentNode;

                    });
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

function zenEditor(e) {
    var $this = $(this);
    var $row = $this.parents('tr');
    var checksum = $row.find('[name=checksum]').val();

    $row.addClass('translation-modified');

    var form = $row.find('form');
    var statusdiv = $('#status-' + checksum).hide();
    var loadingdiv = $('#loading-' + checksum).show();
    $.post(
        form.attr('action'),
        form.serialize(),
        function (data) {
            var messages = $('<div>' + data + '</div>');
            loadingdiv.hide();
            statusdiv.show();
            if (messages.find('.alert-danger').length > 0) {
                statusdiv.attr('class', 'fa-times-circle text-danger');
            } else if (messages.find('.alert-warning').length > 0) {
                statusdiv.attr('class', 'fa-exclamation-circle text-warning');
            } else if (messages.find('.alert-info').length > 0) {
                statusdiv.attr('class', 'fa-check-circle text-warning');
            } else {
                statusdiv.attr('class', 'fa-check-circle text-success');
            }
            statusdiv.addClass('fa').tooltip('destroy');
            if (data.trim() !== '') {
                statusdiv.tooltip({
                    'html': true,
                    'title': data
                });
            };
            $row.removeClass('translation-modified').addClass('translation-saved');
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
            function (response, status, xhr) {
                if ( status === 'error' ) {
                    var msg = gettext('Error while loading page:');
                    $content.html( msg + ' '  + xhr.status + ' ' + xhr.statusText );
                }
                $target.data('loaded', 1);
                loadTableSorting();
            }
        );
    });

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

    /* Git commit tooltip */
    $document.tooltip({
        selector: '.html-tooltip',
        html: true
    });

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

    /* Priority editor */
    $('.edit-priority').click(function (e) {
        e.preventDefault();
        $(this).closest('tr').find('.expander').first().click();
    });

    /* Auto expand expander */
    $('.auto-expand').each(function () {
        $(this).click();
    });

    var activeTab;

    /* Load correct tab */
    if (location.hash !== '') {
        /* From URL hash */
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
        initEditor();
        translationEditor.get(0).focus();
        if ($('#button-first').length > 0) {
            Mousetrap.bindGlobal('alt+end', function(e) {window.location = $('#button-end').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+pagedown', function(e) {window.location = $('#button-next').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+pageup', function(e) {window.location = $('#button-prev').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+home', function(e) {window.location = $('#button-first').attr('href'); return false;});
            Mousetrap.bindGlobal('alt+v', function(e) {$('.translation-item .copy-text').click(); return false;});
            Mousetrap.bindGlobal('alt+f', function(e) {$('input[name="fuzzy"]').click(); return false;});
            Mousetrap.bindGlobal(
                ['ctrl+shift+enter', 'command+shift+enter'],
                function(e) {$('input[name="fuzzy"]').prop('checked', false); return submitForm(e);}
            );
            Mousetrap.bindGlobal(
                'alt+e',
                function(e) {
                    $('.translation-editor').get(0).focus();
                    return false;
                }
            );
            Mousetrap.bindGlobal(
                'alt+s',
                function(e) {
                    $('.nav [href="#search"]').click();
                    $('input[name="q"]').focus();
                    return false;
                }
            );
            Mousetrap.bindGlobal(
                'alt+c',
                function(e) {
                    $('.nav [href="#comments"]').click();
                    $('textarea[name="comment"]').focus();
                    return false;
                }
            );
            Mousetrap.bindGlobal(
                'alt+n',
                function(e) {
                    $('.nav [href="#nearby"]').click();
                    return false;
                }
            );
            Mousetrap.bindGlobal(
                'alt+m',
                function(e) {
                    $('.nav [href="#machine"]').click();
                    return false;
                }
            );
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
    $document.on('click', '.check [data-toggle="tab"]', function (e) {
        var href = $(this).attr('href');
        e.preventDefault();
        $('.nav [href="' + href + '"]').click();
        $window.scrollTop($(href).offset().top);
    });

    /* Copy from dictionary */
    $('.copydict').click(function (e) {
        var text = $(this).parents('tr').find('.target').text();
        $('.translation-editor').insertAtCaret($.trim(text)).trigger('autosize.resize');;
        e.preventDefault();
    });


    /* Copy from source text highlight check */
    $('.hlcheck').click(function (e) {
        var text = $(this).clone();
        text.find(".highlight-number").remove();
        text=text.text();
        $('.translation-editor').insertAtCaret($.trim(text)).trigger('autosize.resize');;
        e.preventDefault();
    });
    /* and shortcuts */
    for (var i = 1; i < 10; i++) {
        Mousetrap.bindGlobal(
            "alt+" + i,
            function(e) {
                return false;
            }
        );
    }
    if ($(".hlcheck").length>0) {
        $('.hlcheck').each(function(idx){
            var $this = $(this);
            if (idx < 10) {
                var key = getNumericKey(idx);
                $(this).find('.highlight-number').html(
                    " <span class='badge kbd-badge' title='" +
                    interpolate(gettext('Alt+%s'), [key]) +
                    "'>" +
                    key +
                    "</span>"
                );

                Mousetrap.bindGlobal(
                    "alt+" + key,
                    function(e) {
                        $this.click();
                        return false;
                    }
                );
            } else {
                $this.find(".highlight-number").html("");
            }
        });
    }

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
    var columnsMenu = $('#columns-menu');
    if (columnsMenu.length > 0) {
        var columnsPanel = columnsMenu.closest('div.panel');
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
            columnsMenu.find('#toggle-words').click();
        }
    }

    /* Lock updates */
    if ($('#js-lock').length > 0) {
        var jsLockUpdate = window.setInterval(function () {
            /* No locking for idle users */
            if (idleTime >= 5) {
                return;
            }
            $.ajax({
                url: $('#js-lock').attr('href'),
                success: function(data) {
                    if (! data.status) {
                        $('.lock-error').remove();
                        var message = $('<div class="alert lock-error alert-danger"></div>');
                        message.text(data.message);
                        $('.content').prepend(message);
                    }
                },
                dataType: 'json'
            });
        }, 19000);

        var idleTime = 0;

        var idleInterval = setInterval(
            function () {
                idleTime = idleTime + 1;
            },
            60000 // 1 minute
        );

        // Zero the idle timer on mouse movement.
        $(document).click(function (e) {
            idleTime = 0;
        });
        $(document).mousemove(function (e) {
            idleTime = 0;
        });
        $(document).keypress(function (e) {
            idleTime = 0;
        });

        window.setInterval(function () {
            window.clearInterval(jsLockUpdate);
        }, 3600000);
    };

    /* Zen mode handling */
    if ($('.zen').length > 0) {
        $window.scroll(function(){
            var $loadingNext = $('#loading-next');
            if ($window.scrollTop() >= $document.height() - (2 * $window.height())) {
                if ($('#last-section').length > 0 || $loadingNext.css('display') !== 'none') {
                    return;
                }
                $loadingNext.show();

                var loader = $('#zen-load');
                loader.data('offset', 20 + parseInt(loader.data('offset'), 10));

                $.get(
                    loader.attr('href') + '&offset=' + loader.data('offset'),
                    function (data) {
                        $loadingNext.hide();

                        $('.zen tbody').append(data);

                        initEditor();
                    }
                );
            }
        });

        $document.on('change', '.translation-editor', zenEditor);
        $document.on('change', '.fuzzy_checkbox', zenEditor);

        $window.on('beforeunload', function(){
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

    /* Datepicker localization */
    $.fn.datepicker.dates.en = {
        days: [
            gettext("Sunday"), gettext("Monday"), gettext("Tuesday"),
            gettext("Wednesday"), gettext("Thursday"), gettext("Friday"),
            gettext("Saturday"), gettext("Sunday")
        ],
        daysShort: [
            pgettext("Short (eg. three letter) name of day in week", "Sun"),
            pgettext("Short (eg. three letter) name of day in week", "Mon"),
            pgettext("Short (eg. three letter) name of day in week", "Tue"),
            pgettext("Short (eg. three letter) name of day in week", "Wed"),
            pgettext("Short (eg. three letter) name of day in week", "Thu"),
            pgettext("Short (eg. three letter) name of day in week", "Fri"),
            pgettext("Short (eg. three letter) name of day in week", "Sat"),
            pgettext("Short (eg. three letter) name of day in week", "Sun")
        ],
        daysMin: [
            pgettext("Minimal (eg. two letter) name of day in week", "Su"),
            pgettext("Minimal (eg. two letter) name of day in week", "Mo"),
            pgettext("Minimal (eg. two letter) name of day in week", "Tu"),
            pgettext("Minimal (eg. two letter) name of day in week", "We"),
            pgettext("Minimal (eg. two letter) name of day in week", "Th"),
            pgettext("Minimal (eg. two letter) name of day in week", "Fr"),
            pgettext("Minimal (eg. two letter) name of day in week", "Sa"),
            pgettext("Minimal (eg. two letter) name of day in week", "Su")
        ],
        months: [
            gettext("January"), gettext("February"), gettext("March"),
            gettext("April"), gettext("May"), gettext("June"), gettext("July"),
            gettext("August"), gettext("September"), gettext("October"),
            gettext("November"), gettext("December")
        ],
        monthsShort: [
            pgettext("Short name of month", "Jan"),
            pgettext("Short name of month", "Feb"),
            pgettext("Short name of month", "Mar"),
            pgettext("Short name of month", "Apr"),
            pgettext("Short name of month", "May"),
            pgettext("Short name of month", "Jun"),
            pgettext("Short name of month", "Jul"),
            pgettext("Short name of month", "Aug"),
            pgettext("Short name of month", "Sep"),
            pgettext("Short name of month", "Oct"),
            pgettext("Short name of month", "Nov"),
            pgettext("Short name of month", "Dec")
        ],
        today: gettext("Today"),
        clear: gettext("Clear"),
        weekStart: django.formats.FIRST_DAY_OF_WEEK,
        titleFormat: "MM yyyy"
    };

    /* Override all multiple selects, use font awesome for exchange icon */
    $('select[multiple]').each(function () {
        $(this).multiSelect({
            afterInit: function (target) {
                $(target.children()[0]).after(
                    '<div class="fa-multiselect"><i class="fa fa-exchange"></i></div>'
                );
            }
        });
    });

    /* Check dismiss shortcuts */
    Mousetrap.bindGlobal("alt+i", function(e) {});
    for (var i = 1; i < 10; i++) {
        Mousetrap.bindGlobal(
            "alt+i " + i,
            function(e) {
                return false;
            }
        );
    }

    if ($(".check").length > 0) {
        $($('.check')[0].parentNode).children(".check").each(function(idx){
            var $this = $(this);
            if (idx < 10) {
                var key = getNumericKey(idx);
                $(this).find('.check-number').html(
                    " <span class='badge kbd-badge' title='" +
                    interpolate(gettext('Alt+I then %s'), [key]) +
                    "'>" +
                    key +
                    "</span>"
                );

                Mousetrap.bindGlobal(
                    "alt+i " + key,
                    function(e) {
                        $this.find('.close').click();
                        return false;
                    }
                );
            } else {
                $(this).find('.check-number').html('');
            }
        });
    }

    /* Labels in dropdown menu in Dashboard */
    $("#views-menu li a").click(function(){
      $("#views-title").html($(this).text()+' <span class="caret"></span>');
    });


});
