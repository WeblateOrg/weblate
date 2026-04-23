.. _vcs:

Version control integration
===========================

Weblate currently supports :ref:`vcs-git` (with extended support for
:ref:`code-hosting-github-pull-requests`,
:ref:`code-hosting-gitlab-merge-requests`,
:ref:`code-hosting-gitea-pull-requests`, :ref:`code-hosting-gerrit`,
:ref:`vcs-git-svn`, :ref:`code-hosting-bitbucket-cloud-pull-requests`,
:ref:`code-hosting-bitbucket-data-center-pull-requests`, and
:ref:`code-hosting-azure-devops-pull-requests`) and :ref:`vcs-mercurial` as
version control back-ends.

For provider-specific setup steps that combine repository access, incoming
notifications, and pushing translations back, see :doc:`/admin/code-hosting`.

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

.. note::

   This section applies **only** to Hosted Weblate (hosted.weblate.org). If you are
   running your own self-hosted Weblate instance, please see
   :ref:`the next section <vcs-repos-code-hosting>` instead.

For Hosted Weblate, there is a dedicated push user registered on GitHub,
Bitbucket, Codeberg, and GitLab (with the username :guilabel:`weblate`, e-mail
``hosted@weblate.org``, and a name or profile description :guilabel:`Weblate push user`).

.. hint::

   There can be more Weblate users on the platforms, designated for other Weblate instances.
   Searching by e-mail ``hosted@weblate.org`` is recommended to find the correct
   user for Hosted Weblate.

You need to add this user as a collaborator and give it appropriate permissions to your
repository (read-only is okay for cloning, write is required for pushing).
Depending on the service and your organization’s settings, this happens immediately,
or requires confirmation on the Weblate side.

On GitHub, you need to add or invite the Hosted Weblate :guilabel:`weblate`
user with write access even when you use the Hosted Weblate GitHub app. The
app handles incoming notifications from GitHub, but pushing changes back
still uses the Hosted Weblate :guilabel:`weblate` user.

The :guilabel:`weblate` user on GitHub accepts invitations automatically within five minutes.
Manual processing might be needed on the other services, so please be patient.

Once the :guilabel:`weblate` user is added to your repository, you can configure
:ref:`component-repo` and :ref:`component-push` using the SSH protocol (for example
``git@github.com:WeblateOrg/weblate.git``).

.. _vcs-repos-code-hosting:

Accessing repositories on code hosting sites (GitHub, GitLab, Bitbucket, Azure DevOps, ...)
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

.. note::

   This section applies to **self-hosted** Weblate instances. If you are using
   Hosted Weblate (hosted.weblate.org), see :ref:`hosted-push` instead.

For self-hosted Weblate, accessing repositories on code hosting sites is typically done by creating a
dedicated user who is associated with a Weblate SSH key (see
:ref:`weblate-ssh-key`). This way you associate Weblate SSH key with a single
user (platforms frequently enforce single use of a SSH key) and grant this user access
to the repository. You can then use SSH URL to access the repository (see
:ref:`ssh-repos`).

.. _ssh-repos:

SSH repositories
++++++++++++++++

The most frequently used method to access private repositories is based on SSH.
Authorize the public Weblate SSH key (see :ref:`weblate-ssh-key`) to access the upstream
repository this way.

.. warning::

    On GitHub, each key can only be used once, see
    :ref:`code-hosting-github-repositories` and :ref:`hosted-push`.

Weblate also stores the host key fingerprint upon first connection, and fails to
connect to the host should it be changed later (see :ref:`verify-ssh`).

In case adjustment is needed, do so from the Weblate admin interface:

.. image:: /screenshots/ssh-keys.webp


.. _weblate-ssh-key:

Weblate SSH key
~~~~~~~~~~~~~~~

.. versionchanged:: 4.17

   Weblate now generates both RSA and Ed25519 SSH keys. Using Ed25519 is recommended for new setups.

The Weblate public key is visible to all users browsing the :guilabel:`About` page.

Admins can generate or display the public key currently used by Weblate in the connection
(from :guilabel:`SSH keys`) on the admin interface landing page.

.. note::

    The corresponding private SSH key can not currently have a password, so ensure it is
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

.. image:: /screenshots/ssh-keys-added.webp

Connecting to legacy SSH servers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Recent OpenSSH releases (for example the one used in Weblate Docker container)
disable RSA signatures using the SHA-1 hash algorithm by default. This change
has been made as the SHA-1 hash algorithm is cryptographically broken, and it
is possible to create chosen-prefix hash collisions for <USD$50K.

For most users, this change should be invisible and there is no need to replace
ssh-rsa keys. OpenSSH has supported RFC8332 RSA/SHA-256/512 signatures since
release 7.2 and existing ssh-rsa keys will automatically use the stronger
algorithm where possible.

Incompatibility is more likely when connecting to older SSH implementations
that have not been upgraded or have not closely tracked improvements in the SSH
protocol. The SSH connection to such server will fail with:

.. code-block:: text

   no matching host key type found. Their offer: ssh-rsa

For these cases, it may be necessary to selectively re-enable RSA/SHA1 to allow
connection and/or user authentication via the HostkeyAlgorithms and
PubkeyAcceptedAlgorithms options. For example, the following stanza in
:file:`DATA_DIR/ssh/config` will enable RSA/SHA1 for host and user
authentication for a single destination host:

.. code-block:: text

   Host legacy-host
      HostkeyAlgorithms +ssh-rsa
      PubkeyAcceptedAlgorithms +ssh-rsa

We recommend enabling RSA/SHA1 only as a stopgap measure until legacy
implementations can be upgraded or reconfigured with another key type (such as
ECDSA or Ed25519).

.. _vcs-repos-github:

GitHub repositories
+++++++++++++++++++

Detailed GitHub repository access is covered in
:ref:`code-hosting-github-repositories`.

.. _vcs-repos-gitlab:

GitLab repositories
+++++++++++++++++++

Detailed GitLab repository access is covered in
:ref:`code-hosting-gitlab-repositories`.

.. _internal-urls:

Weblate internal URLs
+++++++++++++++++++++

Share one repository setup between different components by referring to its
placement as ``weblate://project/component`` in other (linked) components. This
way linked components use the VCS repository configuration of the
main (referenced) component.

.. warning::

   Removing main component also removes linked components.

Weblate automatically adjusts the repository URL when creating a component if it
finds a component with a matching repository setup. You can override this in
the last step of the component configuration.

Reasons to use this:

* Saves disk space on the server, the repository is stored just once.
* Makes the updates faster, only one repository is updated.
* There is just single exported repository with Weblate translations (see :ref:`git-exporter`).
* Some add-ons can operate on multiple components sharing one repository, for example :ref:`addon-weblate.git.squash`.


HTTPS repositories
++++++++++++++++++

.. seealso::

   * :ref:`code-hosting-github-repositories`
   * :ref:`code-hosting-gitlab-repositories`

To access protected HTTPS repositories, include the username and password
in the URL. Don't worry, Weblate will strip this info when the URL is shown
to users (if even allowed to see the repository URL at all).

For example the GitHub URL with authentication added might look like:
``https://user:your_access_token@github.com/WeblateOrg/weblate.git``.

In case you don't provide credentials in the URL and the repository requires it, Git will fail with an error:

.. code-block:: text

   fatal: could not read Username for 'https://github.com': terminal prompts disabled

.. versionchanged:: 5.10.2

   Weblate uses proactive authentication with Git 2.46.0 and newer when HTTP
   credentials are supplied.

   This makes it possible to access Azure DevOps repositories and makes access
   to authenticated repositories faster.

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

    * `The cURL manpage <https://curl.se/docs/manpage.html>`_
    * `Git config documentation <https://git-scm.com/docs/git-config>`_


.. _vcs-git:

Git
---

.. hint::

   Weblate needs Git 2.28 or newer.

.. seealso::

    See :ref:`vcs-repos` for info on how to access different kinds of repositories.

.. _vcs-git-force-push:

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

.. _vcs-github:
.. _github-push:

GitHub pull requests
--------------------

Detailed GitHub pull request setup is covered in
:ref:`code-hosting-github-pull-requests`.

.. _vcs-gitlab:
.. _gitlab-push:

GitLab merge requests
---------------------

Detailed GitLab merge request setup is covered in
:ref:`code-hosting-gitlab-merge-requests`.

.. _vcs-gitea:
.. _gitea-push:

Gitea pull requests
-------------------

Detailed Gitea pull request setup is covered in
:ref:`code-hosting-gitea-pull-requests`.

.. _vcs-bitbucket-server:
.. _vcs-bitbucket-data-center:
.. _bitbucket-server-push:

Bitbucket Data Center pull requests
-----------------------------------

Detailed Bitbucket Data Center pull request setup is covered in
:ref:`code-hosting-bitbucket-data-center-pull-requests`.

.. _vcs-bitbucket-cloud:
.. _bitbucket-cloud-push:

Bitbucket Cloud pull requests
------------------------------

Detailed Bitbucket Cloud pull request setup is covered in
:ref:`code-hosting-bitbucket-cloud-pull-requests`.

.. _vcs-pagure:
.. _pagure-push:

Pagure merge requests
---------------------

Detailed Pagure merge request setup is covered in
:ref:`code-hosting-pagure-merge-requests`.

.. _vcs-gerrit:

Gerrit
------

Detailed Gerrit review request setup is covered in
:ref:`code-hosting-gerrit`.

.. _vcs-azure-devops:
.. _azure-devops-push:

Azure DevOps pull requests
--------------------------

Detailed Azure DevOps pull request setup is covered in
:ref:`code-hosting-azure-devops-pull-requests`.

.. _vcs-mercurial:

Mercurial
---------

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

.. hint::

   Underneath, this uses :ref:`vcs-git`. It requires Git installed and allows
   you to switch to using Git natively with full history of your translations.

Weblate can also operate without a remote VCS. The initial translations are
imported by uploading them. Later you can replace individual files by file upload,
or add translation strings directly from Weblate (currently available only for
monolingual translations).

In the background Weblate creates a Git repository for you and all changes are
tracked in. In case you later decide to use a VCS to store the translations,
you already have a repository within Weblate can base your integration on.
