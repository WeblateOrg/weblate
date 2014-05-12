$(function () {
    /* AJAX loading of tabs/pills */
    $(document).on('show.bs.tab', '[data-toggle="tab"][data-href], [data-toggle="pill"][data-href]', function (e) {
        var $target = $(e.target);
        var $content = $($target.attr('href'));
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
            }
        );
    });

    /* Git commit tooltip */
    $(document).tooltip({
        selector: '.git-commit',
        html: true
    });

    /* Hiding spam protection field */
    $('#s_content').hide();
    $('#id_content').parent('td').parent('tr').hide();
});
