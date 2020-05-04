---
name: Bug report
about: Create a report to help us improve
labels: bug

---

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Screenshots**
If applicable, add screenshots to help explain your problem.

**Server configuration and status**
Please paste the output of `list_versions` and `check --deploy` commands over
here. Depending on installation these can be executed in different way, please
consult https://docs.weblate.org/en/latest/admin/management.html for more
details.

On pip installed Weblate:

```
weblate list_versions
weblate check --deploy
```

On Git checkout:

```
./manage.py list_versions
./manage.py check --deploy
```

Using docker-compose:

```
docker-compose exec weblate weblate list_versions
docker-compose exec --user weblate weblate weblate check --deploy
```

**Additional context**
Add any other context about the problem here.
