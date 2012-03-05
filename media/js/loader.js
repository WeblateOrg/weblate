$(document).ready(function(){
    $('.button').button();
    $('ul.menu li a').button();
    $('ul.breadcums').buttonset();
    $('.sug-accept').button({text: false, icons: { primary: "ui-icon-check" }});
    $('.sug-delete').button({text: false, icons: { primary: "ui-icon-close" }});
    $('.navi').buttonset();
    $('.button-first').button({text: false, icons: { primary: "ui-icon-seek-first" }});
    $('.button-next').button({text: false, icons: { primary: "ui-icon-seek-next" }});
    $('.button-prev').button({text: false, icons: { primary: "ui-icon-seek-prev" }});
    $('.button-end').button({text: false, icons: { primary: "ui-icon-seek-end" }});
    $('#id_target').change(function f() {$('#id_fuzzy').attr('checked', false);}).focus();
    $('#copy-text').button({text: false, icons: { primary: "ui-icon-arrowthick-1-s" }}).click(function f() {
        $.get("/js/get/" + $('#id_checksum').attr('value') + '/', function(data) {
            $('#id_target').text(data);
        });
        return false;
    });
    $('.accordion').accordion();
    $('.errorlist').addClass('ui-state-error ui-corner-all');
    $('div.progress').each(function f(i, e) {e = $(e); e.progressbar({ value: parseInt(e.attr('id')) })});
});
