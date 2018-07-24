### Steps to reproduce

1.
2.
3.

### Actual behaviour

Tell us what happens instead

### Expected behaviour

Tell us what should happen

### Server configuration and status

Please paste the output of `list_versions` and `check --deploy` commands over
here. Depending on installation these can be executed in different way, please
consult https://docs.weblate.org/en/latest/admin/management.html for more
details.

On Git checkout:

```
./manage.py list_versions
./manage.py check --deploy
```

Using docker-compose:

```
docker-compose run --rm weblate list_versions
docker-compose run --rm weblate check --deploy
```
