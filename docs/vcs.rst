.. _vcs:

Version control integration
===========================

Weblate currently supports :ref:`vcs-git` (with extended support for
:ref:`vcs-github`) and :ref:`vcs-mercurial` as version control backends.

.. _vcs-repos:

Accessing repositories
----------------------

The VCS repository you want to use has to be accessible to Weblate. With
publicly available repository you just need to enter correct URL (for example
``git://github.com/nijel/weblate.git`` or
``https://github.com/nijel/weblate.git``), but for private repositories the
setup might be more complex.

Weblate internal URLs
+++++++++++++++++++++

To share one repository between different components you can use special URL
like ``weblate://project/component``. This way the component will share the VCS
repository configuration with referenced component and the VCS repository will
be stored just once on the disk.

SSH repositories
++++++++++++++++

Most frequently used method to access private repositories is based on SSH. To
have access to such repository, you generate SSH key for Weblate and authorize
it to access the repository.

You can generate or display key currently used by Weblate in the admin
interface (follow :guilabel:`SSH keys` link on main admin page). Once you've
done this, Weblate should be able to access your repository.

.. note::

    The keys need to be without password to make it work, so be sure they are
    well protected against malicious usage.

Before connecting to the repository, you also need to verify SSH host keys of
servers you are going to access in the same section of the admin interface.

.. note:: 
   
    On GitHub, you can add the key to only one repository. See following
    sections for other solutions for GitHub.
   
HTTPS repositories
++++++++++++++++++

To access protected HTTPS repositories, you need to include user and password
in the URL. Don't worry, Weblate will strip this information when showing URL
to the users (if they are allowed to see the repository URL at all).

For example the GitHub URL with authentication might look like 
``https://user:your_access_token@github.com/nijel/weblate.git``.

Using proxy
+++++++++++

If you need to access http/https VCS repositories using a proxy server, you
need to configure VCS to use it.

This can be configured using the ``http_proxy``, ``https_proxy``, and
``all_proxy`` environment variables (check cURL documentation for more details)
or by enforcing it in VCS configuration, for example:

.. code-block:: sh

    git config --global http.proxy http://user:password@proxy.example.com:80

.. note::

    The proxy setting needs to be done in context which is used to execute
    Weblate. For the environment it should be set for both server and cron
    jobs. The VCS configuration has to be set for the user which is running
    Weblate.

.. seealso:: 
   
    `curl manpage <http://curl.haxx.se/docs/manpage.html>`_,
    `git config documentation <http://git-scm.com/docs/git-config>`_


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
need to access more repositories, you will hit GitHub limitation on the SSH key
usage (one key can be used only for one repository). There are several ways to
workaround this limitation. 

For smaller deployments, you can use HTTPS authentication using personal access
token and your account, see `Creating an access token for command-line use`_.

.. _Creating an access token for command-line use: https://help.github.com/articles/creating-an-access-token-for-command-line-use/

For bigger setup, it is usually better to create dedicated user for Weblate,
assign him the SSH key generated in Weblate and grant him access to all
repositories you want.

.. _vcs-git-helpers:

Git remote helpers
++++++++++++++++++

You can also use Git `remote helpers`_ for supporting other VCS as well, but
this usually leads to smaller or bigger problems, so be prepared to debug them.

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

.. _remote helpers: http://git-scm.com/docs/git-remote-helpers
.. _git-remote-hg: https://github.com/felipec/git-remote-hg
.. _git-remote-bzr: https://github.com/felipec/git-remote-bzr

.. warning::

    Please be prepared to some incovenience when using Git remote helpers,
    for example with Mercurial, the remote helper sometimes tends to create new
    tip when pushing changes back.

.. _vcs-github:

GitHub
------

.. versionadded:: 2.3

This just adds thin layer on top of :ref:`vcs-git` to allow push translation
changes as pull requests instead of pushing directory to the repository.
It currently uses the `hub`_ tool to do the integration.

There is no need to use this to access Git repositories, ordinary
:ref:`vcs-git` works same, the only difference is how pushing to repository is
handled. With :ref:`vcs-git` changes are pushed directly to the repository, while 
:ref:`vcs-github` creates pull requests.

.. note::

    This feature is currently not available on Hosted Weblate due to technical
    limitations. See :ref:`hosted-push` for available options.

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

    hub clone octocat/Spoon-Knife

The `hub`_ will ask you for your GitHub credentials, retrieve a token and
store it into :file:`~/.config/hub`.

.. note::

    Use the username you configured :guilabel:`hub` with as :setting:`GITHUB_USERNAME`.

.. _hub: https://hub.github.com/

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
