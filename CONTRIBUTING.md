# Contributing to Weblate

As a libre copylefted project, Weblate welcomes contributions in many forms.

## Bug reporting

Please use the [issue tracker on GitHub][1]. Useful error reports contain a
backtrace if possible.

In production setup, admins receive it on the configured e-mail address,

in debug mode, it is shown on screen and for management commands,

you can obtain the full backtrace using `--traceback` parameter.

Bugs might also be caused by third party libraries, so please include
their versions as well. You can collect them all using:
`weblate list_versions`.

## Patch submission

Patches are welcome, either as [pull requests on GitHub][2] or using e-mail on
[the mailing list][3]

## Running the development version locally

If you have Docker and docker-compose-plugin installed, you can spin up the development
environment by running:

```
   ./rundev.sh
```

For more, see: https://docs.weblate.org/en/latest/contributing/start.html#dev-docker

## More info

To be found on the website:

https://weblate.org/contribute/

[1]: https://github.com/WeblateOrg/weblate/issues
[2]: https://github.com/WeblateOrg/weblate/pulls
[3]: https://lists.cihar.com/postorius/lists/weblate.lists.cihar.com/
