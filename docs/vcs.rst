.. _vcs:

Version control integration
===========================

Weblate currently supports :ref:`vcs-git` (with extended support for
:ref:`vcs-github`, :ref:`vcs-gerrit` and :ref:`vcs-git-svn`) and
:ref:`vcs-mercurial` as version control backends.

.. _vcs-repos:

Accessing repositories
----------------------

The VCS repository you want to use has to be accessible to Weblate. With a
publicly available repository you just need to enter correct URL (for example
``git://github.com/WeblateOrg/weblate.git`` or
``https://github.com/WeblateOrg/weblate.git``), but for private repositories the
setup might be more complex.

.. _internal-urls:

Weblate internal URLs
+++++++++++++++++++++

To share one repository between different components you can use a special URL
like ``weblate://project/component``. This way, the component will share the VCS
repository configuration with referenced component and the VCS repository will
be stored just once on the disk.

.. _ssh-repos:

SSH repositories
++++++++++++++++

The most frequently used method to access private repositories is based on SSH. To
have access to such a repository, you generate SSH key for Weblate and authorize
it to access the repository. Weblate also needs to know the host key to avoid
man in the middle attacks. This all can be done in the Weblate administration
interface:

.. image:: images/ssh-keys.png

Generating SSH keys
~~~~~~~~~~~~~~~~~~~

You can generate or display the key currently used by Weblate in the admin
interface (follow :guilabel:`SSH keys` link on main admin page). Once you've
done this, Weblate should be able to access your repository.

.. note::

    The keys need to be without password to make it work, so be sure they are
    well protected against malicious usage.

.. hint::

   You can backup the Weblate generated private key as well.

.. warning::

    On GitHub, you can add the key to only one repository. See the following
    sections for other solutions for GitHub.

.. _verify-ssh:

Verifying SSH host keys
~~~~~~~~~~~~~~~~~~~~~~~

Before connecting to the repository, you also need to verify SSH host keys of
servers you are going to access in the same section of the admin interface.
You can do this in the :guilabel:`Add host key` section. Just enter hostname
you are going to access (eg. ``gitlab.com``) and press :guilabel:`Submit`.
After adding it please verify that the fingerprint matches the server you're
adding, the fingerprints will be displayed in the confirmation message:

.. image:: images/ssh-keys-added.png


HTTPS repositories
++++++++++++++++++

To access protected HTTPS repositories, you need to include the username and password
in the URL. Don't worry, Weblate will strip this information when showing the URL
to the users (if they are allowed to see the repository URL at all).

For example the GitHub URL with authentication might look like
``https://user:your_access_token@github.com/WeblateOrg/weblate.git``.

.. note::

    In case your username or password contains special characters, those have to be
    URL encoded, for example
    ``https://user%40example.com:%24password%23@bitbucket.org/...```.

Using proxy
+++++++++++

If you need to access http/https VCS repositories using a proxy server, you
need to configure the VCS to use it.

This can be configured using the ``http_proxy``, ``https_proxy``, and
``all_proxy`` environment variables (check cURL documentation for more details)
or by enforcing it in VCS configuration, for example:

.. code-block:: sh

    git config --global http.proxy http://user:password@proxy.example.com:80

.. note::

    The proxy setting needs to be done in the same context which is used to
    execute Weblate. For the environment it should be set for both wsgi and
    Celery servers. The VCS configuration has to be set for the user which is
    running Weblate.

.. seealso::

    `curl manpage <https://curl.haxx.se/docs/manpage.html>`_,
    `git config documentation <https://git-scm.com/docs/git-config>`_


.. _vcs-git:

Git
---

Git is first VCS backend that was available in Weblate and is still the most
stable and tested one.

.. seealso::

    See :ref:`vcs-repos` for information how to access different kind of
    repositories.

.. _vcs-repos-github:

GitHub repositories
+++++++++++++++++++

You can access GitHub repositories by SSH as mentioned above, but in case you
need to access more repositories, you will hit a GitHub limitation on the SSH key
usage (one key can be used only for one repository). There are several ways to
work around this limitation.

For smaller deployments, you can use HTTPS authentication using a personal access
token and your account, see `Creating an access token for command-line use`_.

.. _Creating an access token for command-line use: https://help.github.com/articles/creating-an-access-token-for-command-line-use/

For a bigger setup, it is usually better to create dedicated user for Weblate,
assign him the SSH key generated in Weblate and grant him access to all
repositories you want.

Customizing Git configuration
+++++++++++++++++++++++++++++

Weblate invokes all VCS commands with HOME pointed to ``home`` directory in
:setting:`DATA_DIR`, therefore if you want to edit user configuration, you need
to do this in ``DATA_DIR/home/.git``.

.. _vcs-git-helpers:

Git remote helpers
++++++++++++++++++

You can also use Git `remote helpers`_ for supporting other VCS as well, but
this usually leads to other problems, so be prepared to debug them.

At this time, helpers for Bazaar and Mercurial are available within separate
repositories on GitHub: `git-remote-hg`_ and `git-remote-bzr`_. You can
download them manually and put somewhere in your search path (for example
:file:`~/bin`). You also need to have installed appropriate version control
programs as well.

Once you have these installed, you can use such remotes to specify repository
in Weblate.

To clone ``gnuhello`` project from Launchpad with Bazaar use::

    bzr::lp:gnuhello

For ``hello`` repository from selenic.com with Mercurial use::

    hg::http://selenic.com/repo/hello

.. _remote helpers: https://git-scm.com/docs/git-remote-helpers
.. _git-remote-hg: https://github.com/felipec/git-remote-hg
.. _git-remote-bzr: https://github.com/felipec/git-remote-bzr

.. warning::

    Please be prepared to some inconvenience when using Git remote helpers,
    for example with Mercurial, the remote helper sometimes tends to create new
    tip when pushing changes back.

.. _vcs-github:

GitHub
------

.. versionadded:: 2.3

This just adds a thin layer on top of :ref:`vcs-git` to allow push translation
changes as pull requests instead of pushing directory to the repository.
It currently uses the `hub`_ tool to do the integration.

There is no need to use this to access Git repositories, ordinary
:ref:`vcs-git` works the same, the only difference is how pushing to a repository is
handled. With :ref:`vcs-git` changes are pushed directly to the repository, while
:ref:`vcs-github` creates pull requests.

.. _github-push:

Pushing changes to GitHub as pull request
+++++++++++++++++++++++++++++++++++++++++

If you are translating a project that's hosted on GitHub and don't want to
push translations to the repository, you can have them sent as a pull request instead.

You need to configure the `hub`_ command line tool and set
:setting:`GITHUB_USERNAME` for this to work.

.. seealso::

   :setting:`GITHUB_USERNAME`, :ref:`hub-setup` for configuration instructions

.. _hub-setup:

Setting up hub
++++++++++++++

:ref:`github-push` requires a configured `hub`_ installation on your server.
Follow the installation instructions at https://hub.github.com/ and perform an
action with `hub`_ to finish the configuration, for example:

.. code-block:: sh

    # DATA_DIR is set in Weblate settings.py, set it accordingy.
    # Is is /app/data in Docker
    HOME=${DATA_DIR}/home hub clone octocat/Spoon-Knife

The `hub`_ will ask you for your GitHub credentials, retrieve a token and store
it into :file:`~/.config/hub`. This file has to be readable by user running
Weblate.

.. note::

    Use the username you configured :guilabel:`hub` with as
    :setting:`GITHUB_USERNAME` (:envvar:`WEBLATE_GITHUB_USERNAME` for the
    Docker image).

.. _hub: https://hub.github.com/

.. _vcs-gerrit:

Gerrit
------

.. versionadded:: 2.2

Adds a thin layer atop :ref:`vcs-git` to allow pushing translation
changes as Gerrit review requests, instead of pushing a directory to the repository.
Currently uses the `git-review`_ tool to do the integration.

Please refer to the Gerrit documentation for setting up the repository with
necessary configuration.

.. _git-review: https://pypi.org/project/git-review/

.. _vcs-mercurial:

Mercurial
---------

.. versionadded:: 2.1

Mercurial is another VCS you can use directly in Weblate.

.. note::

    It should work with any Mercurial version, but there are sometimes
    incompatible changes to the command line interface which break Weblate.

.. seealso::

    See :ref:`vcs-repos` for information how to access different kind of
    repositories.

.. _vcs-git-svn:

Subversion
----------

.. versionadded:: 2.8

Thanks to `git-svn`_, Weblate can work with `subversion`_ repositories. Git-svn
is a Perl script that enables the usage of subversion with a git client, enabling
users to have a full clone of the internal repository and commit locally.

.. note::

    Weblate tries to detect Subversion repository layout automatically - it
    supports both direct URLs for branch or repositories with standard layout
    (branches/, tags/ and trunk/). See `git-svn documentation
    <https://git-scm.com/docs/git-svn#Documentation/git-svn.txt---stdlayout>`_
    for more information.

.. versionchanged:: 2.19

    In older versions only repositories with standard layout were supported.

.. _git-svn: https://git-scm.com/docs/git-svn

.. _subversion: https://subversion.apache.org/

Subversion Credentials
++++++++++++++++++++++

Weblate expects you to have accepted the certificate upfront and inserted your
credential, if needed. It will look into the DATA_DIR directory. To insert your
credential and accept the certificate, you can run svn once with the `$HOME`
environment variable set to the DATA_DIR::

    HOME=${DATA_DIR}/home svn co https://svn.example.com/example

.. seealso::

    :setting:`DATA_DIR`


.. _vcs-local:

Local files
-----------

.. versionadded:: 3.8

Weblate can operate without remote VCS as well. The initial translations are
imported by ZIP upload. Later you can replace individual files by file upload
or add translation strings directly in Weblate (currently available only for
monolingual translations).

In the background Weblate creates Git repository for you and all changes are
tracked in in. In case you decide later to use VCS to store the translations,
it's already within Weblate and you can base on that.

.. _vcs-gitlab:

GitLab
------

.. versionadded:: 3.9

This just adds a thin layer on top of :ref:`vcs-git` to allow pushing
translation changes as merge requests instead of pushing directly to the
repository. It currently uses the `lab`_ tool to do the push.

There is no need to use this access Git repositories, ordinary :ref:`vcs-git`
works the same, the only difference is how pushing to a repository is
handled. With :ref:`vcs-git` changes are pushed directly to the repository,
while :ref:`vcs-gitlab` creates merge request.

.. _gitlab-push:

Pushing changes to GitLab as merge request
++++++++++++++++++++++++++++++++++++++++++

If you are translating a project that is hosted on GitLab and don't want to
push translations to the repository, you can have them sent as a merge request.

You need to configure the `lab`_ command line tool and set
:setting:`GITLAB_USERNAME` for this to work.

.. seealso::

   :setting:`GITLAB_USERNAME`, :ref:`lab-setup` for configuration instructions

.. _lab-setup:

Setting up lab
++++++++++++++

:ref:`gitlab-push` requires a configured `lab`_ installation on your
server. Follow the installation instructions at
https://github.com/zaquestion/lab#installation and perform and run it without
any arguments to finish configuration, for example:

.. code-block:: sh

    # DATA_DIR is set in Weblate settings.py, set it accordingy.
    # Is is /app/data in Docker
    $ HOME=${DATA_DIR}/home lab
    Enter GitLab host (default: https://gitlab.com):
    Create a token here: https://gitlab.com/profile/personal_access_tokens
    Enter default GitLab token (scope: api):
    Config saved to ~/.config/lab.hcl


The `lab`_ will ask you for your GitLab access token, retrieve a token and
store it into :file:`~/.config/lab.hcl`. The file has to be readable by user
running Weblate.


.. note::

    Use the username you configured :guilabel:`lab` with as
    :setting:`GITLAB_USERNAME` (:envvar:`WEBLATE_GITLAB_USERNAME` for the
    Docker image).

.. _lab: https://github.com/zaquestion/lab
