jQuery.fn.extend({
    insertAtCaret: function(myValue){
        return this.each(function(i) {
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
                this.value = this.value.substring(0, startPos)+myValue+this.value.substring(endPos,this.value.length);
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


function text_change(e) {
    $('#id_fuzzy').attr('checked', false);
}

function mt_set(txt) {
    $('#id_target').val(txt).change();
    $('#id_fuzzy').attr('checked', true);
}

var loading = 0;

function inc_loading() {
    if (loading === 0) {
        $('#loading').show();
    }
    loading++;
}

function dec_loading() {
    loading--;
    if (loading === 0) {
        $('#loading').hide();
    }
}

function get_source_string(callback) {
    inc_loading();
    $.get($('#js-get').attr('href'), function(data) {
        callback(data);
        dec_loading();
    });
}

function failed_mt(jqXHR, textStatus, errorThrown) {
    dec_loading();
    $('<div title="' + gettext('Failed translation') + '"><p>' + gettext('The request for machine translation has failed.') + '</p><p>' + gettext('Error details:') + ' ' + textStatus + '</p></div>').dialog();
}

function process_mt(data, textStatus, jqXHR) {
    if (typeof(data.responseData) == 'undefined') {
        mt_set(data);
    } else if (data.responseData !== '') {
        if (data.responseStatus == 200) {
            mt_set(data.responseData.translatedText);
        } else {
            failed_mt(null, data.responseDetails, null);
        }
    }
    dec_loading();
}

function add_translate_button(id, text, callback) {
    $('#copy-text').after('<a href="#" id="translate-' + id + '">' + text + '</a>');
    $('#translate-' + id).button({text: true, icons: { primary: "ui-icon-shuffle" }}).click(callback);
}

function load_translate_apis() {
    if (typeof(APERTIUM_LANGS) != 'undefined' && APERTIUM_LANGS.indexOf(target_language) != -1) {
        add_translate_button('apertium', gettext('Translate using Apertium'), function () {
            get_source_string(function(data) {
                inc_loading();
                $.ajax({
                    url: "http://api.apertium.org/json/translate?q=" + encodeURIComponent(data) + "&langpair=en|" + target_language + "&key=" + APERTIUM_API_KEY,
                    success: process_mt,
                    error: failed_mt,
                    timeout: 10000,
                    dataType: 'json'
                });
            });
            return false;
        });
    }

    var microsoft_language = target_language;
    if (microsoft_language == 'zh-tw') {
        microsoft_language = 'zh-CHT';
    } else if (microsoft_language == 'zh-cn') {
        microsoft_language = 'zh-CHS';
    }
    if (typeof(MICROSOFT_LANGS) != 'undefined' && MICROSOFT_LANGS.indexOf(microsoft_language) != -1) {
        add_translate_button('apertium', gettext('Translate using Microsoft Translator'), function () {
            get_source_string(function(data) {
                inc_loading();
                $.ajax({
                    url: "http://api.microsofttranslator.com/V2/Ajax.svc/Translate?appID=" + MICROSOFT_API_KEY + "&text=" + encodeURIComponent(data) + "&from=en&to=" + microsoft_language,
                    success: process_mt,
                    error: failed_mt,
                    dataType: 'jsonp',
                    jsonp: "oncomplete"
                });
            });
            return false;
        });
    }
    add_translate_button('mymemory', gettext('Translate using MyMemory'), function () {
        get_source_string(function(data) {
            inc_loading();
            $.ajax({
                url: "http://mymemory.translated.net/api/get?q=" + encodeURIComponent(data) + "&langpair=en|" + target_language,
                success: process_mt,
                error: failed_mt,
                dataType: 'json'
            });
        });
        return false;
    });
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
    if (a == b) return 0;
    if (a > b) return 1;
    return -1;
}

function load_table_sorting() {
    $('table.sort').each(function() {
        var table = $(this),
            tbody = table.find('tbody'),
            thead = table.find('thead'),
            thIndex = 0;
        $(this).find('thead th')
            .each(function(){

            var th = $(this),
                inverse = 1;
            // handle colspan
            if (th.attr('colspan')) {
                thIndex += parseInt(th.attr('colspan'), 10) - 1;
            }
            // skip empty cells and cells with icon (probably already processed)
            if (th.text() !== '' && th.find('span.ui-icon').length === 0) {
                // Store index copy
                var myIndex = thIndex;
                // Add icon, title and class
                th.attr('title', gettext("Sort this column")).addClass('sort').append('<span class="sort ui-icon ui-icon-carat-2-n-s" />');

                // Click handler
                th.click(function(){

                    tbody.find('td,th').filter(function(){
                        return $(this).index() === myIndex;
                    }).sortElements(function(a, b){
                        return inverse * cell_cmp($.text([a]), $.text([b]));
                    }, function(){

                        // parentNode is the element we want to move
                        return this.parentNode;

                    });
                    thead.find('span.sort').removeClass('ui-icon-carat-1-n ui-icon-carat-1-s').addClass('ui-icon-carat-2-n-s');
                    if (inverse == 1) {
                        $(this).find('span.sort').addClass('ui-icon-carat-1-n').removeClass('ui-icon-carat-2-n-s');
                    } else {
                        $(this).find('span.sort').addClass('ui-icon-carat-1-s').removeClass('ui-icon-carat-2-n-s');
                    }

                    inverse = inverse * -1;

                });
            }
            // Increase index
            thIndex += 1;
        });

    });
}
function load_progress() {
    $('div.progress').each(function f(i, e) {
        var $e = $(e);
        var good = parseFloat($e.data('value'));
        var checks = -1;
        if ($e.data('checks')) {
            checks = parseFloat($e.data('checks'));
            good = good - checks;
        }
        var parts = [{
            value: good,
            barClass: 'good'
        }];
        if (checks !== -1) {
            parts.push({
                value: checks,
                barClass: 'checks'
            });
        }
        if ($e.data('fuzzy')) {
            parts.push({
                value: parseFloat($e.data('fuzzy')),
                barClass: 'fuzzy'
            });
        }
        $e.multiprogressbar({
            parts: parts
        });
    });
    $('div.progress .checks').attr('title', gettext('Strings with any failing checks'));
    $('div.progress .fuzzy').attr('title', gettext('Fuzzy strings'));
    $('div.progress .good').attr('title', gettext('Translated strings'));
}

$(function() {
    $('.button').button();
    $('#breadcrumbs').buttonset();
    load_progress();
    $('.errorlist').addClass('ui-state-error ui-corner-all');
    $('.sug-accept').button({text: false, icons: { primary: "ui-icon-check" }});
    $('.sug-delete').button({text: false, icons: { primary: "ui-icon-close" }});
    $('#navi').buttonset();
    $('#button-first').button({text: false, icons: { primary: "ui-icon-seek-first" }});
    $('#button-next').button({text: false, icons: { primary: "ui-icon-seek-next" }});
    $('#button-pos').button({text: true});
    $('#button-prev').button({text: false, icons: { primary: "ui-icon-seek-prev" }});
    $('#button-end').button({text: false, icons: { primary: "ui-icon-seek-end" }});
    $('#navi .button-disabled').button('disable');
    $('.translation-editor').change(text_change).keypress(text_change).autogrow();
    $('.translation-editor').focus();
    $('#toggle-direction').buttonset().change(function(e) {
        $('.translation-editor').attr('dir', $("#toggle-direction :radio:checked").attr('value')).focus();
    });
    $('#copy-text').button({text: true, icons: { primary: "ui-icon-arrow-1-s" }}).click(function f() {
        get_source_string(function(data) {
            mt_set(data);
        });
        return false;
    });
    $('.specialchar').button().click(function() {
        var text = $(this).text();
        if (text == '\\t') {
            text = '\t';
        } else if (text == '→') {
            text = '\t';
        } else if (text == '↵') {
            text = '\r';
        }
        $('#id_target').insertAtCaret(text);
    });
    if (typeof(target_language) != 'undefined') {
        load_translate_apis();
    }
    $('.ignorecheck').button({text: false, icons: { primary: "ui-icon-close" }}).click(function () {
        var parent_id = $(this).parent()[0].id;
        var check_id = parent_id.substring(6);
        $.get($(this).attr('href'), function() {
            $('#' + parent_id).remove();
        });
        return false;
    });
    load_table_sorting();
    $("#translate-tabs").tabs({
        ajaxOptions: {
            error: function(xhr, status, index, anchor) {
                $(anchor.hash).html(gettext("AJAX request to load this content has failed!"));
            }
        },
        cookie: {
            expires: 31,
            name: 'translate-tab',
            path: '/'
        },
        cache: true,
        beforeLoad: function (e, ui) {
            var $panel = $(ui.panel);

            if ($panel.is(":empty")) {
                $panel.append("<div class='tab-loading'>" + gettext("Loading…") + "</div>");
            }
            ui.jqXHR.error(function() {
                $panel.find('.tab-loading').html(gettext("AJAX request to load this content has failed!"));
            });
        },
        load: function (e, ui) {
            $(ui.panel).find(".tab-loading").remove();
            $('a.mergebutton').button({text: true, icons: { primary: "ui-icon-check" }});
            $('a.copydict').button({text: true, icons: { primary: "ui-icon-copy" }}).click(function () {
                var text = $(this).parent().parent().find('.target').text();
                $('#id_target').insertAtCaret(text);
            });
        }
    });
    $("div.tabs").tabs({
        ajaxOptions: {
            error: function(xhr, status, index, anchor) {
                $(anchor.hash).html(gettext("AJAX request to load this content has failed!"));
            }
        },
        cache: true,
        load: function (e, ui) {
            $(ui.panel).find(".tab-loading").remove();
            load_table_sorting();
            load_progress();
            $('.buttons').buttonset();
            $('.buttons .disabled').button('disable');
            $('.details-accordion').accordion({collapsible: true, active: false});
            $('.confirm-reset').click(function() {

                $('<div title="' + gettext('Confirm resetting repository') + '"><p>' + gettext('Resetting the repository will throw away all local changes!') + '</p></div>').dialog({
                    modal: true,
                    autoOpen: true,
                    buttons: [
                        {
                            text: gettext("Ok"),
                            click: function() {
                                window.location = $('.confirm-reset').attr('href');
                                $(this).dialog("close");
                            }
                        },
                        {
                            text: gettext("Cancel"),
                            click: function() {
                                $(this).dialog("close");
                            }
                        }
                    ]
                });
                return false;
            });
        },
        beforeLoad: function (e, ui) {
            var $panel = $(ui.panel);

            if ($panel.is(":empty")) {
                $panel.append("<div class='tab-loading'>" + gettext("Loading…") + "</div>");
            }
            ui.jqXHR.error(function() {
                $panel.find('.tab-loading').html(gettext("AJAX request to load this content has failed!"));
            });

        }
    });
    $("#id_date").datepicker();
    $("form.autosubmit select").change(function() {
        $("form.autosubmit").submit();
    });
    $('#s_content').hide();
    $('#id_content').parent('td').parent('tr').hide();
    $('.expander').click(function() {
        $(this).parent().find('.expander-icon').toggleClass('ui-icon-triangle-1-s').toggleClass('ui-icon-triangle-1-e');
        $(this).parent().next().toggle();
    });
    $('.code-example').focus(function() {
        $(this).select();
    });
    $(document).tooltip({
        content: function() {
            var element = $(this);
            if (element.is('span.git-commit')) {
                element = $(this).find('.git-details');
            }
            return element.html();
        },
        items: "span.tooltip, span.git-commit"
    });
    if (update_lock) {
        window.setInterval(function() {
            $.get($('#js-lock').attr('href'));
        }, 19000);
    }
});
