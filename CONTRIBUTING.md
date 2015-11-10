# Contributing to Weblate

As an open source project, Weblate welcomes contributions of many forms.

## Bug reporting

Please use the [issue tracker on GitHub][1]. Useful error report contains
backtrace if possible. In production setup, admins receive it on configured
email address, in debug mode, it is shown on screen and for management
commands, you can obtain full backtrace using ``--traceback`` parameter.

Many bugs might be also caused by third party libraries, so please include
their versions as well. You can collect all using
``./manage.py list_versions``.

[1]: https://github.com/nijel/weblate/issues

## Patches submission

Patches are welcome either as [pull requests on GitHub][2] or using email on
[our mailing list][3].

[2]: https://github.com/nijel/weblate/pulls
[3]: https://lists.cihar.com/cgi-bin/mailman/listinfo/weblate

## More information

You can find more information on our website:

https://weblate.org/en/contribute/
