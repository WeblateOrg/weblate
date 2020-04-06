## Vendasta Weblate

**Weblate is a copylefted libre software web-based continuous localization system,
used by over 1150 libre projects and companies in more than 115 countries.**

This repository has been forked from https://github.com/WeblateOrg/Weblate.
It is a **public** repository, so take special care not to commit keys.

### Documentation

To be found in the [docs](./docs) directory the source code, or
viewed online on [https://docs.weblate.org/]

### Branching

This project uses a unique branching structure since not all changes
are appropriate to push upstream.

`vendasta`: This branch is our "working master". It should be branched
off when starting new work and used as a base for pull requests. If code
committed to this branch can potentially be contributed to the Weblate
project, please cherry-pick the relevant commits into a pull request
against **master**.

`master`: This branch is reserved for code that can potentially be
contributed back to the Weblate project. This should **not** be treated as
the base branch for new work.

### Local Development

**weblate** runs on Python 3.7 and Django. In order to develop locally,
install Python with brew:
 ```
 brew install python
 ```

Since you're most likely using Python 2 for your other projects, it's
best to use a virtual environment for developing weblate:
 ```
 python3 -m venv venv; source venv/bin/activate
 ```

Install additional requirements:
 ```
 ./install.sh
 ```

Build local dockerfile "weblate-dev" and run it on `localhost:8080`:
 ```
 inv serve
 ```

#### Before Committing

Run `inv lint` to ensure all linting rules are being observed.
If you are missing pip modules you can install them using:
 ```
 pip install -r requirements-lint.txt`
 ```

License
-------

Copyright © 2012–2020 Michal Čihař michal@cihar.com

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details
https://www.gnu.org/licenses/.

.. _weblate.org: https://weblate.org/
