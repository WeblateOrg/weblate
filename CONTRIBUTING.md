# Contributing to Weblate

As an open source project, Weblate welcomes contributions of many forms.

## Bug reporting

Please use the [issue tracker on GitHub][1]. Useful error report contain a
backtrace if possible. In production setup, admins receive it on the configured
email address, in debug mode, it is shown on screen and for management
commands, you can obtain the full backtrace using ``--traceback`` parameter.

Many bugs might be also caused by third party libraries, so please include
their versions as well. You can collect them all using
``./manage.py list_versions``.

[1]: https://github.com/WeblateOrg/weblate/issues

## Patches submission

Patches are welcome either as [pull requests on GitHub][2] or using email on
[our mailing list][3]. Please include a Signed-off-by tag in the commit message
(you can do this by passing `--signoff` parameter to Git).  Note that by
submitting patches with the Signed-off-by tag, you are giving permission to
license the patch as GPLv3-or-later.  See [the DCO file][4] for details.

[2]: https://github.com/WeblateOrg/weblate/pulls
[3]: https://lists.cihar.com/cgi-bin/mailman/listinfo/weblate
[4]: https://github.com/WeblateOrg/weblate/blob/master/DCO

## Running development version locally

If you have Docker and docker-compose installed you can spin up the development
environment simply by running:
```
   ./rundev.sh
```

## More information

You can find more information on our website:

https://weblate.org/contribute/
