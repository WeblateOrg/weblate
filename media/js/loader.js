$(document).ready(function(){
    $('.button').button();
    $('ul.menu li').button();
    $('ul.breadcums').buttonset();
    $('.sug-accept').button({text: false, icons: { primary: "ui-icon-check" }});
    $('.sug-delete').button({text: false, icons: { primary: "ui-icon-close" }});
    $('#id_target').change(function f() {$('#id_fuzzy').attr('checked', false);}).focus();
});
