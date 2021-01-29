# Vendasta Weblate

**Weblate is a copylefted libre software web-based continuous localization system,
used by over 1150 libre projects and companies in more than 115 countries.**

This repository has been forked from https://github.com/WeblateOrg/Weblate.
It is a **public** repository, so take special care not to commit keys.

- [Development](#development)
    - [Branching](#branching)
    - [Local development](#local-development)
    - [Lint](#lint)
- [Using Weblate](#using-weblate)
    - [Documentation](#documentation)
    - [Project structure](#project-structure)
    - [Version control](#version-control)
    - [Lexicon](#lexicon)
    - [Creating a new component with automation](#creating-a-new-component-with-automation)
 - [License](#license)

## Development

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

### Lint

Run `inv lint` to ensure all linting rules are being observed.
If you are missing pip modules you can install them using:
 ```
 pip install -r requirements-lint.txt`
 ```

## Using Weblate

### Documentation

To be found in the [docs](./docs) directory the source code, or viewed online on [https://docs.weblate.org/]

### Project structure

The topology of Weblate is divided into *Projects* and *Components*. A Project is simply an administrative collection of Components, and each Component represents a single collection of translation units. 

### Version control

Weblate is configured to read translation files from VCS sources. If you move a project from one repository to another, be sure to update VCS integration settings for linked components.

### Lexicon

[Lexicon typescript SDK README](https://github.com/vendasta/lexicon/tree/master/sdks/typescript/src/lexicon_sdk/src)

### Creating a new component with automation

Weblate works best with automation. Before starting, your github repository should have an assets directory containing a base (English) translation file.

1. Navigate to [Weblate](https://weblate.vendasta-internal.com) and login using Vendasta SSO.
2. Navigate to the [Common](https://weblate.vendasta-internal.com/projects/common/) Weblate Project. Create a new component for your project by clicking `Add new translation component`.
    - If this project is not a common library, you might choose another Weblate Project, or create a new Weblate Project using the `+` in the navbar.
3. Complete the `Create component` form and click `Continue`.
    - Component name: The name for the component. Usually the repo name or project directory name.
    - URL slug: The url and unique ID for the component. You probably don't need to change the generated value.
    - Project: The Weblate project this component lives under. You probably don't need to change this.
    - Version control system: `Git` is fine.
    - Source code repository: The path to the VCS repository. The full repo will checked out and saved to Weblate's persistent storage. If one repository is being used for multiple components in Weblate (Galaxy, for example), any component after the first can link to the same checked out repo using the pattern `weblate://<project-slug>/<component-slug>` in this field.
    - Repository branch: The name of the main branch for the VCS repo. If linking this component to another using `weblate://...`, leave  this blank.
4. Find and select the wildcard filepath for your translation files from the list, and click `Continue`.
5. Accept default values and click `Continue`.
6. After the component is created, click `Manage` > `Addons`.
7. Add the `Notify Lexicon` Addon. This step ensures that any change to the base translation file within VCS will propagate to Lexicon.
8. Navigate to the VCS repository and go to `Settings > Webhooks`.
9. If there is already a `weblate.vendasta-internal.com` webhook, you're done. Otherwise, click `Add webhook`.
10. Complete the `Add webhook` form and click `Add webhook`.
    - Payload URL: `https://weblate.vendasta-internal.com/hooks/github/`
    - Content type: `application/json`
    - Secret: Navigate to `https://github.com/vendasta/social-marketing-client/settings/hooks/217964978` and copy the value.
    - SSL verification: `Enable SSL Verification`
    - Which events would you like to trigger this webhook?: `Just the push event`

# License

Copyright © 2012–2020 Michal Čihař michal@cihar.com

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details
https://www.gnu.org/licenses/.

weblate.org: https://weblate.org/
