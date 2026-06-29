.. _code-hosting:

Code hosting integrations
=========================

Weblate integrates with code hosting sites in several separate places:
repository access, incoming notifications, and pushing translations back. The
exact setup depends on whether you use Hosted Weblate or run your own Weblate
instance, and on whether Weblate should push directly or create pull requests.

Use this page as a provider-oriented checklist. The individual setting pages
remain the canonical reference for setting syntax.

Setup overview
--------------

1. Grant Weblate access to the repository.

   * For GitHub repositories on Hosted Weblate, use the
     `Hosted Weblate app <https://github.com/apps/hosted-weblate>`_ from
     Weblate's :guilabel:`Connect GitHub account` flow. The App gives Hosted
     Weblate repository access without inviting the hosted :guilabel:`weblate`
     user.
   * For other Hosted Weblate repositories, and for direct SSH pushes outside
     the GitHub App workflow, add the hosted :guilabel:`weblate` user where it
     is available, see :ref:`hosted-push`.
   * For self-hosted Weblate, create a dedicated code hosting user and grant
     access using Weblate's SSH key or an HTTPS token, see
     :ref:`vcs-repos-code-hosting`.

2. Configure :ref:`component-repo` so Weblate can clone the repository.

3. Configure incoming notifications so Weblate pulls changes soon after a push.
   The repository webhook or app must point to the matching Weblate hook URL,
   and the project must have :ref:`project-enable_hooks` enabled.

4. Decide how Weblate should push translations back:

   * Use :ref:`vcs-git` or :ref:`vcs-mercurial` and :ref:`component-push` to
     push directly.
   * Use a provider-specific VCS backend, such as :guilabel:`GitHub` or
     :guilabel:`GitLab`, to create pull or merge requests. These backends need
     API credentials in the Weblate settings.

5. Optionally set :ref:`component-push_branch` when Weblate should push to a
   branch in the upstream repository instead of using a fork where supported.

.. _code-hosting-push-options:

Pushing changes from Weblate
----------------------------

Each translation component can have a push URL set up (see
:ref:`component-push`), and in that case Weblate will be able to push changes
to the remote repository. Weblate can also be configured to automatically push
changes on every commit; this is enabled by default, see
:ref:`component-push_on_commit`.

If you do not want changes to be pushed automatically, you can push manually
under :guilabel:`Repository maintenance` or using the API via
:option:`wlc push`.

In case you do not want direct pushes by Weblate, there is support for
:ref:`code-hosting-github-pull-requests`,
:ref:`code-hosting-gitlab-merge-requests`,
:ref:`code-hosting-gitea-pull-requests`,
:ref:`code-hosting-pagure-merge-requests`,
:ref:`code-hosting-azure-devops-pull-requests`, or
:ref:`code-hosting-gerrit` reviews. You can activate these by choosing
:guilabel:`GitHub`, :guilabel:`GitLab`, :guilabel:`Gitea`,
:guilabel:`Gerrit`, :guilabel:`Azure DevOps`, or :guilabel:`Pagure` as
:ref:`component-vcs` in :ref:`component`.

Overall, following options are available with Git, Mercurial, GitHub, GitLab,
Gitea, Pagure, Azure DevOps, Gerrit, Bitbucket Data Center and Bitbucket Cloud:

.. list-table::
   :header-rows: 1

   * - Desired setup
     - :ref:`component-vcs`
     - :ref:`component-push`
     - :ref:`component-push_branch`

   * - No push
     - :ref:`vcs-git`
     - `empty`
     - `empty`

   * - Push directly
     - :ref:`vcs-git`
     - SSH URL
     - `empty`

   * - Push to separate branch
     - :ref:`vcs-git`
     - SSH URL
     - Branch name

   * - No push
     - :ref:`vcs-mercurial`
     - `empty`
     - `empty`

   * - Push directly
     - :ref:`vcs-mercurial`
     - SSH URL
     - `empty`

   * - GitHub pull request from fork
     - :ref:`code-hosting-github-pull-requests`
     - `empty`
     - `empty`

   * - GitHub pull request from branch
     - :ref:`code-hosting-github-pull-requests`
     - SSH URL [#empty]_
     - Branch name

   * - GitLab merge request from fork
     - :ref:`code-hosting-gitlab-merge-requests`
     - `empty`
     - `empty`

   * - GitLab merge request from branch
     - :ref:`code-hosting-gitlab-merge-requests`
     - SSH URL [#empty]_
     - Branch name

   * - Gitea merge request from fork
     - :ref:`code-hosting-gitea-pull-requests`
     - `empty`
     - `empty`

   * - Gitea merge request from branch
     - :ref:`code-hosting-gitea-pull-requests`
     - SSH URL [#empty]_
     - Branch name

   * - Pagure merge request from fork
     - :ref:`code-hosting-pagure-merge-requests`
     - `empty`
     - `empty`

   * - Pagure merge request from branch
     - :ref:`code-hosting-pagure-merge-requests`
     - SSH URL [#empty]_
     - Branch name

   * - Azure DevOps pull request from fork
     - :ref:`code-hosting-azure-devops-pull-requests`
     - `empty`
     - `empty`

   * - Azure DevOps pull request from branch
     - :ref:`code-hosting-azure-devops-pull-requests`
     - SSH URL [#empty]_
     - Branch name

   * - Gerrit review
     - :ref:`code-hosting-gerrit`
     - SSH URL
     - Target branch name (optional)

   * - Bitbucket Data Center pull request from fork
     - :ref:`code-hosting-bitbucket-data-center-pull-requests`
     - `empty`
     - `empty`

   * - Bitbucket Data Center pull request from branch
     - :ref:`code-hosting-bitbucket-data-center-pull-requests`
     - SSH URL [#empty]_
     - Branch name

   * - Bitbucket Cloud pull request from fork
     - :ref:`code-hosting-bitbucket-cloud-pull-requests`
     - `empty`
     - `empty`

   * - Bitbucket Cloud pull request from branch
     - :ref:`code-hosting-bitbucket-cloud-pull-requests`
     - SSH URL [#empty]_
     - Branch name

.. [#empty] Can be empty in case :ref:`component-repo` supports pushing.

.. _code-hosting-github:

GitHub
------

.. _code-hosting-github-repositories:

GitHub repository access
~~~~~~~~~~~~~~~~~~~~~~~~

Hosted Weblate GitHub App
^^^^^^^^^^^^^^^^^^^^^^^^^

On Hosted Weblate, the recommended setup is to connect the
`Hosted Weblate app <https://github.com/apps/hosted-weblate>`_ from the
Weblate workspace where your project lives. Use the :guilabel:`Connect GitHub
account` flow, install the App on the GitHub user or organization that owns
your repositories, grant it access to the repositories you want to translate,
and import components from the connected GitHub account.

The App-backed workflow uses GitHub installation access tokens for cloning,
pushing translation branches, creating pull requests, and receiving incoming
notifications. You do not need to invite the Hosted Weblate
:guilabel:`weblate` GitHub user or configure a separate repository webhook for
components imported this way.

Use the Hosted Weblate :guilabel:`weblate` GitHub user only when you
intentionally configure direct SSH pushes outside the GitHub App workflow, see
:ref:`hosted-push`.

HTTPS with personal access token
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-https-repository-access.rst

To use this approach:

1. Create a personal access token as described in `Creating an access token for command-line use`_.
2. Include the token in your repository URL:
   ``https://username:token@github.com/owner/repo.git``.

This is suitable when you are starting with Weblate or working with a single repository.

.. _Creating an access token for command-line use: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token

SSH with a dedicated user
^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-ssh-repository-access.rst

For GitHub, create a dedicated user, for example ``weblate-bot``, and use
GitHub SSH URLs for your repositories, for example
``git@github.com:owner/repo.git``.

On Hosted Weblate, use this SSH-user workflow only for direct SSH pushes outside
the recommended `Hosted Weblate app <https://github.com/apps/hosted-weblate>`_
workflow.

.. note::

   When using :guilabel:`GitHub` for pull requests, the
   :ref:`component-push_branch` configuration affects the behavior: if not set,
   the project is forked and changes are pushed through a fork. If set, changes
   are pushed to the upstream repository and the chosen branch.

.. _code-hosting-github-notifications:

GitHub notifications
~~~~~~~~~~~~~~~~~~~~

Weblate comes with native support for GitHub.

If you are using Hosted Weblate, use the
`Hosted Weblate app <https://github.com/apps/hosted-weblate>`_ from
Weblate's :guilabel:`Connect GitHub account` flow. It uses GitHub App
webhooks, so you do not need to configure a separate :guilabel:`Webhook` in
GitHub. Components imported from the connected GitHub account also use the App
for repository access and pull requests, without inviting the Hosted Weblate
:guilabel:`weblate` GitHub user.

The `Hosted Weblate legacy app`_ is kept for existing webhook-only setups. Use
it only when you need the legacy app to deliver GitHub notifications to Hosted
Weblate.

.. _Hosted Weblate legacy app: https://github.com/apps/hosted-weblate-legacy

For self-hosted Weblate, register the GitHub App using the in-app registration
flow described below. Weblate generates the App manifest, GitHub returns the
credentials, and they are stored in the database - there is no settings-based
configuration.

.. _code-hosting-github-app-register:

Registering the GitHub App from Weblate
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The fastest way to add the GitHub App is to let Weblate generate a GitHub App
manifest with the correct permissions, events, and webhook URL pre-filled:

1. Sign in to Weblate with an account that has management access.
2. Open :guilabel:`Manage → VCS Installations → Register Weblate GitHub
   App`.
3. Fill in the form. The :guilabel:`GitHub host` defaults to ``github.com``;
   change it to your GitHub Enterprise hostname if needed. Leave
   :guilabel:`Organization` blank to register the App under your personal
   account, or enter an organization slug to register it under that org.
4. Click :guilabel:`Continue to GitHub` and confirm on GitHub's
   :guilabel:`Create GitHub App` page (you can still rename the App there).
5. GitHub redirects back to Weblate, which exchanges the temporary code for
   the App ID, private key, webhook secret, and slug and stores them in the
   database. The :guilabel:`Connect GitHub account` button is available
   immediately afterwards.

The manifest requests the permissions and event subscriptions Weblate needs
(``Contents`` and ``Pull requests`` read/write, ``Metadata`` read-only,
``Organization administration`` read-only, ``Workflows`` read/write, and the
``Installation``, ``Meta`` and ``Push`` events), and sets the callback, setup
and per-integration webhook URLs automatically, so no manual GitHub App
configuration is required. GitHub delivers the ``Installation`` and
``Installation repositories`` events to all GitHub Apps by default.

GitHub only offers accounts where the signed-in GitHub user can install or
request the app. If an organization is not shown during the install flow, check
the user's organization role and the organization's GitHub App installation
restrictions. On GitHub.com, public apps can be installed on other accounts;
private apps can only be installed on the account that owns the app.

Connecting a workspace
^^^^^^^^^^^^^^^^^^^^^^

Connected GitHub accounts are bound to a Weblate :ref:`workspace <workspaces>`.
A user with project administration rights for any project in a workspace can
connect a GitHub account on that workspace. After connecting, every project in
the workspace can import components from repositories the app installation has
access to. For organization installations, Weblate verifies that the install-time
GitHub user can administer the organization installation.

Projects that are not in a workspace cannot connect a GitHub App installation.

Components imported through the GitHub App flow use the dedicated
:guilabel:`GitHub (via Weblate GitHub app)` VCS backend. The component
settings UI keeps the repository URL read-only to prevent the App-issued
credentials from being redirected to an unrelated repository.

.. _code-hosting-github-app-webhook:

App webhook URL
^^^^^^^^^^^^^^^

Each registered GitHub App integration has its own webhook URL containing an
opaque token that uniquely identifies a single integration:

.. code-block:: text

   https://weblate.example.com/hooks/integrations/<webhook_token>/

If you are not using a GitHub App, add the Weblate webhook in the repository
settings (:guilabel:`Webhooks`) to receive notifications on every push to a
GitHub repository, as shown on the image below:

.. image:: /images/github-settings.png

The :guilabel:`Payload URL` consists of your Weblate URL appended by
``/hooks/github/``, for example for the Hosted Weblate service, this is
``https://hosted.weblate.org/hooks/github/``.

You can leave other values at default settings. Weblate can handle both content
types and consumes just the :guilabel:`push` event.

.. seealso::

   * :http:post:`/hooks/github/`
   * :ref:`hosted-push`

.. _code-hosting-github-pull-requests:

GitHub pull requests
~~~~~~~~~~~~~~~~~~~~

This adds a thin layer atop :ref:`vcs-git` using the `GitHub API`_ to allow
pushing translation changes as pull requests, instead of pushing directly to
the repository.

:ref:`vcs-git` pushes changes directly to a repository, while the
:guilabel:`GitHub` backend creates pull requests. The latter is not needed for
merely accessing Git repositories.

To create pull requests, select :guilabel:`GitHub` as
:ref:`component-vcs` and configure :setting:`GITHUB_CREDENTIALS`. For
GitHub.com, use
``api.github.com`` as the API host. The token must allow Weblate to read and
write repository contents and create pull requests. If Weblate should fork
private repositories, the token might also need administration access.

.. _GitHub API: https://docs.github.com/en/rest

.. _code-hosting-gitlab:

GitLab
------

.. _code-hosting-gitlab-repositories:

GitLab repository access
~~~~~~~~~~~~~~~~~~~~~~~~

HTTPS with personal or project access token
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-https-repository-access.rst

For GitLab, the token needs :guilabel:`write_repository` scope to be able to
push changes to the repository. The project access token requires
:guilabel:`Developer` role for pushing.

The URL needs to contain a username. For a personal access token, it is the
actual username:
``https://user:personal_access_token@gitlab.com/example/example.git``.
For project access tokens it can be a non-blank value:
``https://example:project_access_token@gitlab.com/example/example.git``.

.. note::

   The rules for using project access tokens have changed between GitLab
   releases, the non-blank value is the current requirement, but older versions
   had different expectations (project name, bot user name). Check GitLab
   documentation matching your version if unsure.

SSH with a dedicated user
^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-ssh-repository-access.rst

For GitLab, create a dedicated user and use GitLab SSH URLs, for example
``git@gitlab.com:group/project.git``.

.. _code-hosting-gitlab-notifications:

GitLab notifications
~~~~~~~~~~~~~~~~~~~~

Weblate has support for GitLab hooks. Add a project webhook with destination
to ``/hooks/gitlab/`` URL on your Weblate installation, for example
``https://hosted.weblate.org/hooks/gitlab/``.

.. admonition:: Troubleshooting

   * Check `GitLab webhook request history`_ if webhooks are delivered.
   * The response payload contains information about matched components.

.. _GitLab webhook request history: https://docs.gitlab.com/user/project/integrations/webhooks/#view-webhook-request-history

.. seealso::

   * :http:post:`/hooks/gitlab/`
   * :ref:`hosted-push`

.. _code-hosting-gitlab-merge-requests:

GitLab merge requests
~~~~~~~~~~~~~~~~~~~~~

This adds a thin layer atop :ref:`vcs-git` using the `GitLab API`_ to allow
pushing translation changes as merge requests instead of pushing directly to
the repository.

There is no need to use this to access Git repositories, ordinary
:ref:`vcs-git` works the same, the only difference is how pushing to a
repository is handled. With :ref:`vcs-git` changes are pushed directly to the
repository, while the :guilabel:`GitLab` backend creates a merge request.

To create merge requests, select :guilabel:`GitLab` as
:ref:`component-vcs` and configure :setting:`GITLAB_CREDENTIALS`.

The :ref:`component-push_branch` configuration affects where Weblate pushes
changes before opening the merge request. If it is not set, the project is
forked and changes are pushed through a fork. If it is set, changes are pushed
to the upstream repository and chosen branch.

.. _GitLab API: https://docs.gitlab.com/api/

.. _code-hosting-gitea:

Gitea, Forgejo, and Codeberg
----------------------------

.. _code-hosting-gitea-repositories:

Gitea, Forgejo, and Codeberg repository access
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HTTPS with an access token
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-https-repository-access.rst

SSH with a dedicated user
^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-ssh-repository-access.rst

For Hosted Weblate repositories on Codeberg, add the hosted
:guilabel:`weblate` user where write access is needed, see :ref:`hosted-push`.

.. _code-hosting-gitea-notifications:

Gitea notifications
~~~~~~~~~~~~~~~~~~~

Weblate has support for Gitea webhooks. Add a :guilabel:`Gitea Webhook` for
:guilabel:`Push events` event with destination to ``/hooks/gitea/`` URL on your
Weblate installation, for example ``https://hosted.weblate.org/hooks/gitea/``.
This can be done in :guilabel:`Webhooks` under repository :guilabel:`Settings`.

.. seealso::

   * `Webhooks in Gitea manual <https://docs.gitea.io/en-us/webhooks/>`_
   * :http:post:`/hooks/gitea/`
   * :ref:`hosted-push`

.. _code-hosting-forgejo-notifications:

Forgejo notifications
~~~~~~~~~~~~~~~~~~~~~

Weblate has support for Forgejo webhooks. Add a :guilabel:`Forgejo Webhook`
for :guilabel:`Push events` event with destination to ``/hooks/forgejo/`` URL
on your Weblate installation, for example
``https://hosted.weblate.org/hooks/forgejo/``. This can be done in
:guilabel:`Webhooks` under repository :guilabel:`Settings`.

.. seealso::

   * `Webhooks in Forgejo documentation <https://forgejo.org/docs/latest/user/webhooks/>`_
   * :http:post:`/hooks/forgejo/`
   * :ref:`hosted-push`

.. _code-hosting-gitea-pull-requests:

Gitea pull requests
~~~~~~~~~~~~~~~~~~~

.. versionadded:: 4.12

This adds a thin layer atop :ref:`vcs-git` using the `Gitea API`_ to allow
pushing translation changes as pull requests instead of pushing directly to the
repository.

There is no need to use this to access Git repositories, ordinary
:ref:`vcs-git` works the same, the only difference is how pushing to a
repository is handled. With :ref:`vcs-git` changes are pushed directly to the
repository, while the :guilabel:`Gitea` backend creates pull requests.

To create pull requests, select :guilabel:`Gitea` as
:ref:`component-vcs` and configure :setting:`GITEA_CREDENTIALS`.

.. _Gitea API: https://docs.gitea.io/en-us/api-usage/

.. _code-hosting-bitbucket:

Bitbucket
---------

.. _code-hosting-bitbucket-repositories:

Bitbucket repository access
~~~~~~~~~~~~~~~~~~~~~~~~~~~

HTTPS with an access token
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-https-repository-access.rst

SSH with a dedicated user
^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-ssh-repository-access.rst

Hosted Weblate has a dedicated :guilabel:`weblate` user for Bitbucket access,
see :ref:`hosted-push`.

To push directly, use :ref:`vcs-git` or :ref:`vcs-mercurial` with
:ref:`component-push`.

.. _code-hosting-bitbucket-notifications:

Bitbucket notifications
~~~~~~~~~~~~~~~~~~~~~~~

Weblate has support for Bitbucket webhooks. Add a webhook which triggers upon
repository push, with destination to ``/hooks/bitbucket/`` URL on your Weblate
installation, for example ``https://hosted.weblate.org/hooks/bitbucket/``.

.. image:: /images/bitbucket-settings.png

.. seealso::

   * :http:post:`/hooks/bitbucket/`
   * :ref:`hosted-push`

.. _code-hosting-bitbucket-data-center-pull-requests:

Bitbucket Data Center pull requests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 4.16

This adds a thin layer atop :ref:`vcs-git` using the
`Bitbucket Data Center API`_ to allow pushing translation changes as pull
requests instead of pushing directly to the repository.

.. warning::

   This does not support Bitbucket Cloud API.

There is no need to use this to access Git repositories, ordinary
:ref:`vcs-git` works the same, the only difference is how pushing to a
repository is handled. With :ref:`vcs-git` changes are pushed directly to the
repository, while the :guilabel:`Bitbucket Data Center` backend creates a pull
request.

To create pull requests, select :guilabel:`Bitbucket Data Center` as
:ref:`component-vcs` and configure :setting:`BITBUCKETSERVER_CREDENTIALS`.

.. _Bitbucket Data Center API: https://developer.atlassian.com/server/bitbucket/

.. _code-hosting-bitbucket-cloud-pull-requests:

Bitbucket Cloud pull requests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 5.8

This adds a thin layer atop :ref:`vcs-git` using the `Bitbucket Cloud API`_ to
allow pushing translation changes as pull requests instead of pushing directly
to the repository.

.. warning::

   This is different from Bitbucket Data Center API.

There is no need to use this to access Git repositories, ordinary
:ref:`vcs-git` works the same, the only difference is how pushing to a
repository is handled. With :ref:`vcs-git` changes are pushed directly to the
repository, while the :guilabel:`Bitbucket Cloud` backend creates a pull
request.

To create pull requests, select :guilabel:`Bitbucket Cloud` as
:ref:`component-vcs` and configure :setting:`BITBUCKETCLOUD_CREDENTIALS`.

.. _Bitbucket Cloud API: https://developer.atlassian.com/cloud/bitbucket/

.. _code-hosting-azure-devops:

Azure DevOps
------------

.. _code-hosting-azure-repos-repositories:

Azure Repos repository access
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HTTPS with an access token
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-https-repository-access.rst

Use the HTTPS clone URL shown by Azure Repos for the repository.

SSH with a dedicated user
^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-ssh-repository-access.rst

Use the SSH URL shown by Azure Repos for the repository.

.. _code-hosting-azure-repos-notifications:

Azure Repos notifications
~~~~~~~~~~~~~~~~~~~~~~~~~

Weblate has support for Azure Repos webhooks. Add a webhook for
:guilabel:`Code pushed` event with destination to ``/hooks/azure/`` URL on your
Weblate installation, for example ``https://hosted.weblate.org/hooks/azure/``.
This can be done in :guilabel:`Service hooks` under :guilabel:`Project
settings`.

.. seealso::

   * `Web hooks in Azure DevOps manual <https://learn.microsoft.com/en-us/azure/devops/service-hooks/services/webhooks?view=azure-devops>`_
   * :http:post:`/hooks/azure/`
   * :ref:`hosted-push`

.. _code-hosting-azure-devops-pull-requests:

Azure DevOps pull requests
~~~~~~~~~~~~~~~~~~~~~~~~~~

This adds a thin layer atop :ref:`vcs-git` using the `Azure DevOps API`_ to
allow pushing translation changes as pull requests, instead of pushing directly
to the repository.

:ref:`vcs-git` pushes changes directly to a repository, while the
:guilabel:`Azure DevOps` backend creates pull requests. The latter is not
needed for merely accessing Git repositories.

To create pull requests, select :guilabel:`Azure DevOps` as
:ref:`component-vcs` and configure :setting:`AZURE_DEVOPS_CREDENTIALS`.

.. _Azure DevOps API: https://learn.microsoft.com/en-us/rest/api/azure/devops/?view=azure-devops-rest-7.2

.. _code-hosting-pagure:

Pagure
------

.. _code-hosting-pagure-repositories:

Pagure repository access
~~~~~~~~~~~~~~~~~~~~~~~~

HTTPS with an access token
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-https-repository-access.rst

SSH with a dedicated user
^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-ssh-repository-access.rst

.. _code-hosting-pagure-notifications:

Pagure notifications
~~~~~~~~~~~~~~~~~~~~

Weblate has support for Pagure hooks. Add a webhook with destination to
``/hooks/pagure/`` URL on your Weblate installation, for example
``https://hosted.weblate.org/hooks/pagure/``. This can be done in
:guilabel:`Activate Web-hooks` under :guilabel:`Project options`:

.. image:: /images/pagure-webhook.png

.. seealso::

   * :http:post:`/hooks/pagure/`
   * :ref:`hosted-push`

.. _code-hosting-pagure-merge-requests:

Pagure merge requests
~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 4.3.2

This adds a thin layer atop :ref:`vcs-git` using the `Pagure API`_ to allow
pushing translation changes as merge requests instead of pushing directly to
the repository.

There is no need to use this to access Git repositories, ordinary
:ref:`vcs-git` works the same, the only difference is how pushing to a
repository is handled. With :ref:`vcs-git` changes are pushed directly to the
repository, while the :guilabel:`Pagure` backend creates a merge request.

To create merge requests, select :guilabel:`Pagure` as
:ref:`component-vcs` and configure :setting:`PAGURE_CREDENTIALS`.

.. _Pagure API: https://pagure.io/api/0/

Other workflows
---------------

.. _code-hosting-gitee-repositories:

Gitee repository access
~~~~~~~~~~~~~~~~~~~~~~~

HTTPS with an access token
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-https-repository-access.rst

SSH with a dedicated user
^^^^^^^^^^^^^^^^^^^^^^^^^

.. include:: /snippets/code-hosting-ssh-repository-access.rst

.. _code-hosting-gitee-notifications:

Gitee notifications
~~~~~~~~~~~~~~~~~~~

Weblate has support for Gitee webhooks. Add a :guilabel:`WebHook` for
:guilabel:`Push` event with destination to ``/hooks/gitee/`` URL on your
Weblate installation, for example ``https://hosted.weblate.org/hooks/gitee/``.
This can be done in :guilabel:`WebHooks` under repository
:guilabel:`Management`.

.. seealso::

   * `Webhooks in Gitee manual <https://help.gitee.com/webhook>`_
   * :http:post:`/hooks/gitee/`
   * :ref:`hosted-push`

.. _code-hosting-gerrit:

Gerrit review requests
~~~~~~~~~~~~~~~~~~~~~~

Gerrit support adds a thin layer atop :ref:`vcs-git` using the
:pypi:`git-review` tool to allow pushing translation changes as Gerrit review
requests, instead of pushing them directly to the repository.

The optional :ref:`component-push_branch` setting selects the target branch for
the Gerrit review. Leave it empty to use :ref:`component-branch`. Use the short
branch name, such as ``main``; Weblate and ``git-review`` push the review to
``refs/for/<branch>`` automatically. Gerrit push options can be appended after
``%`` in either setting, for example ``main%topic=l10n``. Gerrit interprets
these options as the configured Weblate Gerrit account and applies its own
permissions.

The Gerrit documentation has the details on the configuration necessary to set
up such repositories. There is no separate code hosting credential setting for
this backend.

Docker credentials
~~~~~~~~~~~~~~~~~~

For Docker installations, code hosting API credentials can also be provided
through environment variables, see :ref:`docker-vcs-config`.
