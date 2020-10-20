---
name: Bug report
about: Create a report to help us improve
---

**Describe the bug**

A clear and concise description of what the bug is.

**To Reproduce the bug**

Description should look similar to this:

Steps to reproduce the behavior:

1. Go to '...'
2. Scroll down to '....'
3. Click on '....'
4. See error

**Expected behavior**

A clear and concise description of what you expected to happen.

**Screenshots**

If applicable, add screenshots to better explain your problem.

**Server configuration and status**

<!--
Please paste the output of `list_versions` command over here. Depending on
installation these can be executed in different way, please consult
https://docs.weblate.org/en/latest/admin/management.html for more details.

On pip installed Weblate:

weblate list_versions

On Git checkout:

./manage.py list_versions

Using docker-compose:

docker-compose exec weblate weblate list_versions
-->

**Weblate deploy checks**

<!--
Please paste the output of check --deploy command over here. Depending on
installation these can be executed in different way, please consult
https://docs.weblate.org/en/latest/admin/management.html for more details.

On pip installed Weblate:

weblate check --deploy

On Git checkout:

./manage.py check --deploy

Using docker-compose:

docker-compose exec --user weblate weblate weblate check --deploy
-->

**Exception traceback**

<!--
In case you observed server error or crash, please see
<https://docs.weblate.org/en/latest/contributing/debugging.html>
for information how to obtain that.
-->

**Additional context**

Add any other context about the problem here.
