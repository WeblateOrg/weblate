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
    $('#id_content').parent('div').hide();

    /* Form automatic submission */
    $("form.autosubmit select").change(function () {
        $("form.autosubmit").submit();
    });

    /* Row expander */
    $('.expander').click(function () {
        var $table_row = $(this).parent();
        var $next_row = $table_row.next();
        $next_row.toggle();
        var $loader = $next_row.find('tr.details .load-details');
        if ($loader.length > 0) {
            var url = $loader.attr('href');
            $loader.remove();
            $.get(
                url,
                function (data) {
                    var $cell = $next_row.find('tr.details td');
                    $cell.find('img').remove();
                    $cell.append(data);
                    $cell.find('.button').button();
                }
            );
        }
    });

    /* Priority editor */
    $('.edit-priority').click(function (e) {
        e.preventDefault();
    });
});
