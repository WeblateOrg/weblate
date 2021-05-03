---
# This file is maintained in https://github.com/WeblateOrg/meta/
name: Bug report
about: Create a report to help us improve
---

<!--
Thank you for reporting an issue on Weblate! Here are a few things to note:

* This template will guide you to create a useful issue report, so please do NOT delete it.
* The description blocks like this one are comments and won't be shown in the issue once it’s created.
* Please write your text outside them or replace them.
* In case you are pasting logs, please place them inside tripple backticks:

```
log content
```
-->

**Describe the issue**

<!--
A clear and concise description of the problem you are facing.
-->

**I already tried**

Describe the steps you tried to solve the problem yourself.

- [ ] I've read and searched [the docs](https://docs.weblate.org/) and did not find the answer there.
      If you didn’t try already, try to search there what you wrote above.

**To Reproduce the issue**

Steps to reproduce the behavior:

1. Go to '...'
2. Scroll down to '...'
3. Click on '...'
4. See error

**Expected behavior**

<!--
A clear and concise description of what you expected to happen.
-->

**Screenshots**

<!--
If applicable, add screenshots to better explain your problem.
-->

**Exception traceback**

<!--
In case you observed server error or crash, please see
<https://docs.weblate.org/en/latest/contributing/debugging.html>
for information how to obtain that.
-->

**Server configuration and status**

Weblate installation: weblate.org service / Docker / PyPI / other

<!--
Please paste the output of `list_versions` command over here. Depending on
the installation these can be executed in a different way. Please consult
https://docs.weblate.org/en/latest/admin/management.html for more details.

On pip installed Weblate:

weblate list_versions

On Git checkout:

./manage.py list_versions

Using docker-compose:

docker-compose exec --user weblate weblate weblate list_versions
-->

**Weblate deploy checks**

<!--
Please paste the output of check --deploy command over here. Depending on
the installation, these can be executed in a different way. Please consult
https://docs.weblate.org/en/latest/admin/management.html for more details.

On pip installed Weblate:

weblate check --deploy

On Git checkout:

./manage.py check --deploy

Using docker-compose:

docker-compose exec --user weblate weblate weblate check --deploy
-->

**Additional context**

<!--
Add any other context about the problem here.
-->
