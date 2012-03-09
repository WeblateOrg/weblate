function text_change(e) {
    $('#id_fuzzy').attr('checked', false);
}


$(function() {
    $('.button').button();
    $('ul.menu li a').button();
    $('ul.breadcums').buttonset();
    $('div.progress').each(function f(i, e) {e = $(e); e.progressbar({ value: parseInt(e.attr('id')) })});
    $('.accordion').accordion();
    $('.errorlist').addClass('ui-state-error ui-corner-all');
    $('.sug-accept').button({text: false, icons: { primary: "ui-icon-check" }});
    $('.sug-delete').button({text: false, icons: { primary: "ui-icon-close" }});
    $('.navi').buttonset();
    $('.button-first').button({text: false, icons: { primary: "ui-icon-seek-first" }});
    $('.button-next').button({text: false, icons: { primary: "ui-icon-seek-next" }});
    $('.button-prev').button({text: false, icons: { primary: "ui-icon-seek-prev" }});
    $('.button-end').button({text: false, icons: { primary: "ui-icon-seek-end" }});
    $('textarea.translation').change(text_change).keypress(text_change).autogrow().focus();
    $('#copy-text').button({text: true, icons: { primary: "ui-icon-arrow-1-s" }}).click(function f() {
        $.get("/js/get/" + $('#id_checksum').attr('value') + '/', function(data) {
            $('#id_target').text(data);
        });
        return false;
    });
    if (typeof(apertium) != 'undefined' && typeof(target_language) != 'undefined' && apertium.isTranslatablePair('en', target_language)) {
        $('#copy-text').after('<a href="#" id="translate-apertium">' + gettext('Translate using Apertium') + '</a>');
        $('#translate-apertium').button({text: true, icons: { primary: "ui-icon-shuffle" }}).click(function f() {
            $.get("/js/get/" + $('#id_checksum').attr('value') + '/', function(data) {
                apertium.translate(data, 'en', target_language, function (ret) {
                    if (!ret.error) {
                        $('#id_target').text(ret.translation);
                    }
                });
            });
            return false;
        });
    }
    if (typeof(Microsoft) != 'undefined' && typeof(target_language) != 'undefined') {
        var langs = Microsoft.Translator.getLanguages();
        if (langs.indexOf(target_language) != -1) {
            $('#copy-text').after('<a href="#" id="translate-microsoft">' + gettext('Translate using Microsoft Translator') + '</a>');
            $('#translate-microsoft').button({text: true, icons: { primary: "ui-icon-shuffle" }}).click(function f() {
                $.get("/js/get/" + $('#id_checksum').attr('value') + '/', function(data) {
                    Microsoft.Translator.translate(data, 'en', target_language, function (ret) {
                        $('#id_target').text(ret);
                    });
                });
                return false;
            });
        }
    }
});
