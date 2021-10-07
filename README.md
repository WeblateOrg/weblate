# Vendasta Weblate

**Weblate is a copylefted libre software web-based continuous localization system,
used by over 1150 libre projects and companies in more than 115 countries.**

This repository has been forked from https://github.com/WeblateOrg/Weblate.
It is a **public** repository, so take special care not to commit keys.

- [Administration](#administration)
    - [Emails](#emails)
- [Development](#development)
    - [Branching](#branching)
    - [Local development](#local-development)
    - [Lint](#lint)
    - [Deploying changes](#deploying-changes)
- [Using Weblate](#using-weblate)
    - [Documentation](#documentation)
    - [Project structure](#project-structure)
    - [Lexicon](#lexicon)
    - [Creating a new component](#creating-a-new-component)
 - [License](#license)

## Administration

The Google Group `weblate@vendasta.com` is configured as the administrator account for Weblate. The password for this group is stored in a kubernetes secret.

### Emails

To receive admin notifications (for requests, error logs, and repository alerts), add yourself to the `weblate@vendasta.com` Google Group.

Outgoing emails from Weblate use `vmail@vendasta.com` as the sender. This account is configured as an SMTP relay for Weblate using kubernetes environment variables `WEBLATE_EMAIL_HOST_USER` and `WEBLATE_EMAIL_HOST_PASSWORD`. The password is generated as an [App Password](https://support.google.com/accounts/answer/185833?hl=en).

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

### Deploying Changes

Weblate is deployed using kubernetes configurations located in the [Gitops](https://github.com/vendasta/gitops) repo. These configurations are monitored by ArgoCD, which should be used to synchronize pods whenever the k8s files are updated.
1. Push changes to `vendasta` branch, as described in [Branching](#branching) above.
2. Go to [Mission Control](https://mission-control-prod.vendasta-internal.com/applications/weblate) and wait for your changes to build successfully.
3. Go to the Build Log and copy the destination image from Execution Details: ![Destination Image](https://user-images.githubusercontent.com/12201403/129250174-083f6d5e-89e2-4dac-847a-d28a02487dd9.png)
4. Go to [Gitops](https://github.com/vendasta/gitops). Find `weblate/demo/deployment.yaml` or `weblate/prod/deployment.yaml`, and update the `image` key to the value copied in step 4. Commit this to master.
5. Go to [ArgoCD](https://argocd.vendasta-internal.com). Find weblate-demo or weblate-prod, then click Sync > Synchronize.

## Using Weblate

### Documentation

To be found in the [docs](./docs) directory the source code, or viewed online on [https://docs.weblate.org/]

### Project structure

The topology of Weblate is divided into *Projects* and *Components*. A Project is simply an administrative collection of Components, and each Component represents a single collection of translation units. 

### Lexicon

Weblate does not have the stability necessary for serving translations to apps. Lexicon is a microservice for mirroring and serving translations as they are committed to Weblate component repos.
The `NotifyLexicon` is responsible for triggering Lexicon mirroring workflows, and it should be enabled for any Component that serves its translations from Lexicon. 

[Lexicon typescript SDK README](https://github.com/vendasta/lexicon/tree/master/sdks/typescript/src/lexicon_sdk/src)

### Creating a new component

Before starting, your project needs a source translation file. This should typically be named `en_devel.json` and should be saved to a Vendasta github repository.

1. Navigate to [Weblate](https://weblate.vendasta-internal.com) and login using Vendasta SSO.
2. Navigate to the [Common](https://weblate.vendasta-internal.com/projects/common/) Weblate Project. Create a new component for your project by clicking `Add new translation component`.
    - If this project is not a common library, you might choose another Weblate Project, or create a new Weblate Project using the `+` in the navbar.
3. Click the `Translate document` tab.  
4. Complete the form and click `Continue`.
    - Document to translate: Choose the `en_devel.json` source file.
    - Project: The Weblate project this component lives under. You probably don't need to change this.
    - Component name: The name for the component. Usually the repo name or project directory name.
    - URL slug: The url and unique ID for the component. You probably don't need to change the generated value.
5. Find and select the wildcard filepath for your translation files from the list, and click `Continue`.
6. Choose an option for `File format` that matches your file. It will probably be `JSON file`, `JSON nested structure file`, or `XLIFF translation file`.
6. Copy the value from `Monolingual base language file` to `Template for new translations`.
7. Accept other default values and click `Continue`.
8. After the component is created, click `Manage` > `Addons`.
9. Add the `Notify Lexicon` Addon. This step ensures that any change to the base translation file within VCS will propagate to Lexicon.

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
