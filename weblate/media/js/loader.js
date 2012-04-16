function text_change(e) {
    $('#id_fuzzy').attr('checked', false);
}

function mt_set(txt) {
    $('#id_target').text(txt);
    $('#id_fuzzy').attr('checked', true);
}

var loading = 0;

function inc_loading() {
    if (loading == 0) {
        $('#loading').show();
    }
    loading++;
}

function dec_loading() {
    loading--;
    if (loading == 0) {
        $('#loading').hide();
    }
}

function get_source_string(callback) {
    inc_loading();
    $.get("/js/get/" + $('#id_checksum').attr('value') + '/', function(data) {
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
    } else if (data.responseData != '') {
        mt_set(data.responseData.translatedText);
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
                    url: "http://api.apertium.org/json/translate?q=" + data + "&langpair=en|" + target_language + "&key=" + APERTIUM_API_KEY,
                    success: process_mt,
                    error: failed_mt,
                    timeout: 10000,
                    dataType: 'json',
                });
            });
            return false;
        });
    }
    if (typeof(MICROSOFT_LANGS) != 'undefined' && MICROSOFT_LANGS.indexOf(target_language) != -1) {
        add_translate_button('apertium', gettext('Translate using Microsoft Translator'), function () {
            get_source_string(function(data) {
                inc_loading();
                $.ajax({
                    url: "http://api.microsofttranslator.com/V2/Ajax.svc/Translate?appID=" + MICROSOFT_API_KEY + "&text=" + data + "&from=en&to=" + target_language,
                    success: process_mt,
                    error: failed_mt,
                    dataType: 'jsonp',
                    jsonp: "oncomplete",
                });
            });
            return false;
        });
    }
    add_translate_button('mymemory', gettext('Translate using MyMemory'), function () {
        get_source_string(function(data) {
            inc_loading();
            $.ajax({
                url: "http://mymemory.translated.net/api/get?q=" + data + "&langpair=en|" + target_language,
                success: process_mt,
                error: failed_mt,
                dataType: 'json',
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

$(function() {
    $('.button').button();
    $('ul.menu li a').button();
    $('ul.breadcums').buttonset();
    $('div.progress').each(function f(i, e) {e = $(e); e.progressbar({ value: parseInt(e.attr('id')) })});
    $('.errorlist').addClass('ui-state-error ui-corner-all');
    $('.sug-accept').button({text: false, icons: { primary: "ui-icon-check" }});
    $('.sug-delete').button({text: false, icons: { primary: "ui-icon-close" }});
    $('.navi').buttonset();
    $('.button-first').button({text: false, icons: { primary: "ui-icon-seek-first" }});
    $('.button-next').button({text: false, icons: { primary: "ui-icon-seek-next" }});
    $('.button-pos').button({text: true});
    $('.button-prev').button({text: false, icons: { primary: "ui-icon-seek-prev" }});
    $('.button-end').button({text: false, icons: { primary: "ui-icon-seek-end" }});
    $('textarea.translation').change(text_change).keypress(text_change).autogrow().focus();
    $('#copy-text').button({text: true, icons: { primary: "ui-icon-arrow-1-s" }}).click(function f() {
        get_source_string(function(data) {
            mt_set(data);
        });
        return false;
    });
    if (typeof(target_language) != 'undefined') {
        load_translate_apis();
    }
    $('.ignorecheck').button({text: false, icons: { primary: "ui-icon-close" }}).click(function () {
        var parent_id = $(this).parent()[0].id;
        var check_id = parent_id.substring(6);
        $.get('/js/ignore-check/' + check_id + '/', function() {
            $('#' + parent_id).remove();
        });
    });
    $('table.sort').each(function() {
        var table = $(this);
        $(this).find('thead th')
            .each(function(){

            var th = $(this),
                thIndex = th.index(),
                inverse = 1,
                tbody = th.parents('table').find('tbody'),
                thead = th.parents('table').find('thead');
            if (th.text() == '') {
                return;
            }
            // Second column contains percent with colspan
            if (thIndex >= 1 && !table.hasClass('simple')) {
                thIndex += 1;
            }
            th.attr('title', gettext("Sort this column")).addClass('sort').append('<span class="sort ui-icon ui-icon-carat-2-n-s" />');

            th.click(function(){

                tbody.find('td,th').filter(function(){
                    return $(this).index() === thIndex;
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
        });

    });
    $("div.translate-tabs").tabs({
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
        load: function (e, ui) {
            $(ui.panel).find(".tab-loading").remove();
        },
        show: function (e, ui) {
            var $panel = $(ui.panel);

            if ($panel.is(":empty")) {
                $panel.append("<div class='tab-loading'>" + gettext("Loading...") + "</div>");
            }
        },
        load: function (e, ui) {
            $('a.mergebutton').button({text: true, icons: { primary: "ui-icon-check" }});
        }
    });
    $("div.tabs").tabs({
        ajaxOptions: {
            error: function(xhr, status, index, anchor) {
                $(anchor.hash).html(gettext("AJAX request to load this content has failed!"));
            }
        },
        cookie: {
            expires: 31,
            name: $(this).id,
            path: '/'
        },
        cache: true,
        load: function (e, ui) {
            $(ui.panel).find(".tab-loading").remove();
            $('.buttons').buttonset();
            $('.buttons .disabled').button('disable');
            $('.details-accordion').accordion({collapsible: true, active: -1});
        },
        show: function (e, ui) {
            var $panel = $(ui.panel);

            if ($panel.is(":empty")) {
                $panel.append("<div class='tab-loading'>" + gettext("Loading...") + "</div>");
            }
        },
    });
    $("#id_date").datepicker();
});
