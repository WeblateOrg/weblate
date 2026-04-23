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

   * For Hosted Weblate, add the hosted :guilabel:`weblate` user where it is
     available, see :ref:`hosted-push`.
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

.. _code-hosting-github:

GitHub
------

.. _code-hosting-github-repositories:

GitHub repository access
~~~~~~~~~~~~~~~~~~~~~~~~

There are two main approaches to accessing GitHub repositories with Weblate:

**Option 1: HTTPS with personal access token**

Use HTTPS authentication with a personal access token and your GitHub account.
This works for both read-only access and read-write access.

To use this approach:

1. Create a personal access token as described in `Creating an access token for command-line use`_.
2. Include the token in your repository URL:
   ``https://username:token@github.com/owner/repo.git``.

This is suitable when you are starting with Weblate or working with a single repository.

.. _Creating an access token for command-line use: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token

**Option 2: SSH with a dedicated user**

For setups with multiple repositories, create a dedicated user for Weblate.
This avoids GitHub's limitation that each SSH key can only be used once per
platform.

To use this approach:

1. Create a dedicated GitHub user account, for example ``weblate-bot``.
2. Add Weblate's public SSH key to this user, see :ref:`weblate-ssh-key`.
3. Grant this user access to all repositories you want to translate.
4. Use SSH URLs for your repositories: ``git@github.com:owner/repo.git``.

This approach is also used for Hosted Weblate, which has a dedicated
:guilabel:`weblate` user for that purpose.

.. note::

   When using :guilabel:`GitHub` for pull requests, the
   :ref:`component-push_branch` configuration affects the behavior: if not set,
   the project is forked and changes are pushed through a fork. If set, changes
   are pushed to the upstream repository and the chosen branch.

.. _code-hosting-github-notifications:

GitHub notifications
~~~~~~~~~~~~~~~~~~~~

Weblate comes with native support for GitHub.

If you are using Hosted Weblate, the recommended approach is to install the
`Weblate app <https://github.com/apps/weblate>`_. The app delivers GitHub
notifications to Hosted Weblate, so you do not need to configure a separate
:guilabel:`Webhook` in GitHub. It does not by itself grant Hosted Weblate write
access to the repository, though. To push changes back, you still need to add
the Hosted Weblate :guilabel:`weblate` GitHub user as a collaborator with write
access, see :ref:`hosted-push`.

If you are not using the app, add the Weblate webhook in the repository
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

Access via SSH is possible, see :ref:`ssh-repos`, but if you need to access
more than one repository, you will hit a GitLab limitation on allowed SSH key
usage because each key can be used only once.

In case the :ref:`component-push_branch` is not set, the project is forked and
changes pushed through a fork. In case it is set, changes are pushed to the
upstream repository and chosen branch.

Using personal or project access tokens is possible as well. The token needs
:guilabel:`write_repository` scope to be able to push changes to the
repository. The project access token requires :guilabel:`Developer` role for
pushing.

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

.. _GitLab API: https://docs.gitlab.com/api/

.. _code-hosting-gitea:

Gitea, Forgejo, and Codeberg
----------------------------

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

.. _code-hosting-gitee-notifications:

Gitee notifications
~~~~~~~~~~~~~~~~~~~

Weblate has support for Gitee webhooks. Add a :guilabel:`WebHook` for
:guilabel:`Push` event with destination to ``/hooks/gitee/`` URL on your
Weblate installation, for example ``https://hosted.weblate.org/hooks/gitee/``.
This can be done in :guilabel:`WebHooks` under repository
:guilabel:`Management`.

.. seealso::

   * `Webhooks in Gitee manual <https://gitee.com/help/categories/40>`_
   * :http:post:`/hooks/gitee/`
   * :ref:`hosted-push`

.. _code-hosting-gerrit:

Gerrit review requests
~~~~~~~~~~~~~~~~~~~~~~

Gerrit support adds a thin layer atop :ref:`vcs-git` using the `git-review`_
tool to allow pushing translation changes as Gerrit review requests, instead
of pushing them directly to the repository.

The Gerrit documentation has the details on the configuration necessary to set
up such repositories. There is no separate code hosting credential setting for
this backend.

.. _git-review: https://pypi.org/project/git-review/

Docker credentials
~~~~~~~~~~~~~~~~~~

For Docker installations, code hosting API credentials can also be provided
through environment variables, see :ref:`docker-vcs-config`.
