.. _vcs:

Version control integration
===========================

Weblate currently supports :ref:`vcs-git` (with extended support for
:ref:`vcs-github`, :ref:`vcs-gerrit` and :ref:`vcs-git-svn`) and
:ref:`vcs-mercurial` as version control back-ends.

.. _vcs-repos:

Accessing repositories
----------------------

The VCS repository you want to use has to be accessible to Weblate. With a
publicly available repository you just need to enter the correct URL (for
example ``https://github.com/WeblateOrg/weblate.git``), but for private
repositories or for push URLs the setup is more complex and requires
authentication.

.. _hosted-push:

Accessing repositories from Hosted Weblate
++++++++++++++++++++++++++++++++++++++++++

For Hosted Weblate there is a dedicated push user registered on GitHub,
Bitbucket, Codeberg and GitLab (with the username :guilabel:`weblate`, e-mail
``hosted@weblate.org`` and, named :guilabel:`Weblate push user`). You need to
add this user as a collaborator and give it appropriate permission to your
repository (read-only is okay for cloning, write is required for pushing).
Depending on service and your organization settings, this happens immediately,
or requires confirmation on the Weblate side.

The :guilabel:`weblate` user on GitHub accepts invitations automatically within five minutes.
Manual processing might be needed on the other services, so please be patient.

Once the :guilabel:`weblate` user is added, you can configure
:ref:`component-repo` and :ref:`component-push` using the SSH protocol (for example
``git@github.com:WeblateOrg/weblate.git``).

.. _ssh-repos:

SSH repositories
++++++++++++++++

The most frequently used method to access private repositories is based on SSH.
Authorize the public Weblate SSH key (see :ref:`weblate-ssh-key`) to access the upstream
repository this way.

.. warning::

    On GitHub, each key can only be used once, see :ref:`vcs-repos-github` and
    :ref:`hosted-push`.

Weblate also stores the host key fingerprint upon first connection, and fails to
connect to the host should it be changed later (see :ref:`verify-ssh`).

In case adjustment is needed, do so from the Weblate admin interface:

.. image:: images/ssh-keys.png


.. _weblate-ssh-key:

Weblate SSH key
~~~~~~~~~~~~~~~

The Weblate public key is visible to all users browsing the :guilabel:`About` page.

Admins can generate or display the public key currently used by Weblate in the connection
(from :guilabel:`SSH keys`) on the admin interface landing page.

.. note::

    The corresponding private SSH key can not currently have a password, so make sure it is
    well protected.

.. hint::

   Make a backup of the generated private Weblate SSH key.

.. _verify-ssh:

Verifying SSH host keys
~~~~~~~~~~~~~~~~~~~~~~~

Weblate automatically stores the SSH host keys on first access and remembers
them for further use.

In case you want to verify the key fingerprint before connecting to the
repository, add the SSH host keys of the servers you are going to access in
:guilabel:`Add host key`, from the same section of the admin interface. Enter
the hostname you are going to access (e.g. ``gitlab.com``), and press
:guilabel:`Submit`. Verify its fingerprint matches the server you added.

The added keys with fingerprints are shown in the confirmation message:

.. image:: images/ssh-keys-added.png

.. _vcs-repos-github:

GitHub repositories
+++++++++++++++++++

Access via SSH is possible (see :ref:`ssh-repos`), but in case you need to
access more than one repository, you will hit a GitHub limitation on allowed
SSH key usage (since each key can be used only once).

In case the :ref:`component-push_branch` is not set, the project is forked and
changes pushed through a fork. In case it is set, changes are pushed to the
upstream repository and chosen branch.

For smaller deployments, use HTTPS authentication with a personal access
token and your GitHub account, see `Creating an access token for command-line use`_.

.. _Creating an access token for command-line use: https://docs.github.com/en/github/authenticating-to-github/creating-a-personal-access-token

For bigger setups, it is usually better to create a dedicated user for Weblate,
assign it the public SSH key generated in Weblate (see :ref:`weblate-ssh-key`)
and grant it access to all the repositories you want to translate. This
approach is also used for Hosted Weblate, there is dedicated
:guilabel:`weblate` user for that.

.. seealso::

    :ref:`hosted-push`

.. _internal-urls:

Weblate internal URLs
+++++++++++++++++++++

Share one repository setup between different components by referring to
its placement as ``weblate://project/component`` in other(linked) components. This way linked components
use the VCS repository configuration of the main(referenced) component.

.. warning::

   Removing main component also removes linked components.

Weblate automatically adjusts the repository URL when creating a component if it
finds a component with a matching repository setup. You can override this in
the last step of the component configuration.

Reasons to use this:

* Saves disk space on the server, the repository is stored just once.
* Makes the updates faster, only one repository is updated.
* There is just single exported repository with Weblate translations (see :ref:`git-exporter`).
* Some addons can operate on multiple components sharing one repository, for example :ref:`addon-weblate.git.squash`.


HTTPS repositories
++++++++++++++++++

To access protected HTTPS repositories, include the username and password
in the URL. Don't worry, Weblate will strip this info when the URL is shown
to users (if even allowed to see the repository URL at all).

For example the GitHub URL with authentication added might look like:
``https://user:your_access_token@github.com/WeblateOrg/weblate.git``.

.. note::

    If your username or password contains special characters, those have to be
    URL encoded, for example
    ``https://user%40example.com:%24password%23@bitbucket.org/…``.

Using proxy
+++++++++++

If you need to access HTTP/HTTPS VCS repositories using a proxy server,
configure the VCS to use it.

This can be done using the ``http_proxy``, ``https_proxy``, and ``all_proxy``
environment variables, (as described in the `cURL documentation <https://curl.se/docs/>`_)
or by enforcing it in the VCS configuration, for example:

.. code-block:: sh

    git config --global http.proxy http://user:password@proxy.example.com:80

.. note::

    The proxy configuration needs to be done under user running Weblate (see
    also :ref:`file-permissions`) and with ``HOME=$DATA_DIR/home`` (see
    :setting:`DATA_DIR`), otherwise Git executed by Weblate will not use it.

.. seealso::

    `The cURL manpage <https://curl.se/docs/manpage.html>`_,
    `Git config documentation <https://git-scm.com/docs/git-config>`_


.. _vcs-git:

Git
---

.. seealso::

    See :ref:`vcs-repos` for info on how to access different kinds of repositories.

Git with force push
+++++++++++++++++++

This behaves exactly like Git itself, the only difference being that it always
force pushes. This is intended only in the case of using a separate repository
for translations.

.. warning::

    Use with caution, as this easily leads to lost commits in your
    upstream repository.

Customizing Git configuration
+++++++++++++++++++++++++++++

Weblate invokes all VCS commands with ``HOME=$DATA_DIR/home`` (see
:setting:`DATA_DIR`), therefore editing the user configuration needs to be done
in ``DATA_DIR/home/.git``.

.. _vcs-git-helpers:

Git remote helpers
++++++++++++++++++

You can also use Git `remote helpers`_ for additionally supporting other version
control systems, but be prepared to debug problems this may lead to.

At this time, helpers for Bazaar and Mercurial are available within separate
repositories on GitHub: `git-remote-hg`_ and `git-remote-bzr`_.
Download them manually and put somewhere in your search path
(for example :file:`~/bin`). Make sure you have the corresponding version control
systems installed.

Once you have these installed, such remotes can be used to specify a repository
in Weblate.

To clone the ``gnuhello`` project from Launchpad using Bazaar::

    bzr::lp:gnuhello

For the ``hello`` repository from selenic.com using Mercurial::

    hg::http://selenic.com/repo/hello

.. _remote helpers: https://git-scm.com/docs/gitremote-helpers
.. _git-remote-hg: https://github.com/felipec/git-remote-hg
.. _git-remote-bzr: https://github.com/felipec/git-remote-bzr

.. warning::

    The inconvenience of using Git remote helpers is for example with Mercurial,
    the remote helper sometimes creates a new tip when pushing changes back.

.. _vcs-github:

GitHub
------

.. versionadded:: 2.3

This adds a thin layer atop :ref:`vcs-git` using the `GitHub API`_ to allow pushing
translation changes as pull requests, instead of pushing directly to the repository.

:ref:`vcs-git` pushes changes directly to a repository, while
:ref:`vcs-github` creates pull requests.
The latter is not needed for merely accessing Git repositories.

.. seealso::

   :ref:`push-changes`


.. _github-push:

Pushing changes to GitHub as pull requests
++++++++++++++++++++++++++++++++++++++++++

If not wanting to push translations to a GitHub repository, they can be sent as
either one or many pull requests instead.

You need to configure API credentials to make this work.

.. seealso::

   :setting:`GITHUB_USERNAME`,
   :setting:`GITHUB_TOKEN`,
   :setting:`GITHUB_CREDENTIALS`

.. _GitHub API: https://docs.github.com/en/rest

.. _vcs-gitlab:

GitLab
------

.. versionadded:: 3.9

This just adds a thin layer atop :ref:`vcs-git` using the `GitLab API`_ to allow
pushing translation changes as merge requests instead of
pushing directly to the repository.

There is no need to use this to access Git repositories, ordinary :ref:`vcs-git`
works the same, the only difference is how pushing to a repository is
handled. With :ref:`vcs-git` changes are pushed directly to the repository,
while :ref:`vcs-gitlab` creates merge request.

.. seealso::

   :ref:`push-changes`

.. _gitlab-push:

Pushing changes to GitLab as merge requests
+++++++++++++++++++++++++++++++++++++++++++

If not wanting to push translations to a GitLab repository, they can be sent as either
one or many merge requests instead.

You need to configure API credentials to make this work.

.. seealso::

   :setting:`GITLAB_USERNAME`,
   :setting:`GITLAB_TOKEN`,
   :setting:`GITLAB_CREDENTIALS`

.. _GitLab API: https://docs.gitlab.com/ee/api/

.. _vcs-pagure:

Pagure
------

.. versionadded:: 4.3.2

This just adds a thin layer atop :ref:`vcs-git` using the `Pagure API`_ to allow
pushing translation changes as merge requests instead of
pushing directly to the repository.

There is no need to use this to access Git repositories, ordinary :ref:`vcs-git`
works the same, the only difference is how pushing to a repository is
handled. With :ref:`vcs-git` changes are pushed directly to the repository,
while :ref:`vcs-pagure` creates merge request.

.. seealso::

   :ref:`push-changes`

.. _pagure-push:

Pushing changes to Pagure as merge requests
+++++++++++++++++++++++++++++++++++++++++++

If not wanting to push translations to a Pagure repository, they can be sent as either
one or many merge requests instead.

You need to configure API credentials to make this work.

.. seealso::

   :setting:`PAGURE_USERNAME`,
   :setting:`PAGURE_TOKEN`,
   :setting:`PAGURE_CREDENTIALS`

.. _Pagure API: https://pagure.io/api/0/

.. _vcs-gerrit:

Gerrit
------

.. versionadded:: 2.2

Adds a thin layer atop :ref:`vcs-git` using the `git-review`_ tool to allow
pushing translation changes as Gerrit review requests, instead of
pushing them directly to the repository.

The Gerrit documentation has the details on the configuration necessary to set up
such repositories.

.. _git-review: https://pypi.org/project/git-review/

.. _vcs-mercurial:

Mercurial
---------

.. versionadded:: 2.1

Mercurial is another VCS you can use directly in Weblate.

.. note::

    It should work with any Mercurial version, but there are sometimes
    incompatible changes to the command-line interface which breaks Weblate
    integration.

.. seealso::

    See :ref:`vcs-repos` for info on how to access different kinds of
    repositories.

.. _vcs-git-svn:

Subversion
----------

.. versionadded:: 2.8

Weblate uses `git-svn`_ to interact with `subversion`_ repositories. It is
a Perl script that lets subversion be used by a Git client, enabling
users to maintain a full clone of the internal repository and commit locally.

.. note::

    Weblate tries to detect Subversion repository layout automatically - it
    supports both direct URLs for branch or repositories with standard layout
    (branches/, tags/ and trunk/). More info about this is to be found in the
    `git-svn documentation <https://git-scm.com/docs/git-svn#Documentation/git-svn.txt---stdlayout>`_.
    If your repository does not have a standard layout and you encounter errors,
    try including the branch name in the repository URL and leaving branch empty.

.. versionchanged:: 2.19

    Before this, only repositories using the standard layout were supported.

.. _git-svn: https://git-scm.com/docs/git-svn

.. _subversion: https://subversion.apache.org/

Subversion credentials
++++++++++++++++++++++

Weblate expects you to have accepted the certificate up-front (and your
credentials if needed). It will look to insert them into the :setting:`DATA_DIR`
directory. Accept the certificate by using `svn` once with the `$HOME`
environment variable set to the :setting:`DATA_DIR`:

.. code-block:: sh

    # Use DATA_DIR as configured in Weblate settings.py, it is /app/data in the Docker
    HOME=${DATA_DIR}/home svn co https://svn.example.com/example

.. seealso::

    :setting:`DATA_DIR`


.. _vcs-local:

Local files
-----------

.. versionadded:: 3.8

Weblate can also operate without a remote VCS. The initial translations are
imported by uploading them. Later you can replace individual files by file upload,
or add translation strings directly from Weblate (currently available only for
monolingual translations).

In the background Weblate creates a Git repository for you and all changes are
tracked in. In case you later decide to use a VCS to store the translations,
you already have a repository within Weblate can base your integration on.
