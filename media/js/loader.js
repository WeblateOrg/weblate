$(document).ready(function(){
    $('.button').button();
    $('ul.menu li').button();
    $('ul.breadcums').buttonset();
    $('.sug-accept').button({text: false, icons: { primary: "ui-icon-check" }});
    $('.sug-delete').button({text: false, icons: { primary: "ui-icon-close" }});
});
