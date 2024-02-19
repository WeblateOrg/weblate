.. _continuous-translation:

Continuous localization
=======================

There is infrastructure in place so that your translation closely follows
development. This way translators can work on translations the entire time,
instead of working through huge amount of new text just prior to release.

.. seealso::

   :doc:`/devel/integration` describes basic ways to integrate your development
   with Weblate.

This is the process:

1. Developers make changes and push them to the VCS repository.
2. Optionally the translation files are updated, see :ref:`translations-update`.
3. Weblate pulls changes from the VCS repository, parses translation files and updates its database, see :ref:`update-vcs`.
4. Translators submit translations using the Weblate web interface, or upload offline changes.
5. Once the translators are finished, Weblate commits the changes to the local repository (see :ref:`lazy-commit`).
6. Changes are pushed back to the upstream repository (see :ref:`push-changes`).

.. graphviz::

    digraph translations {
        graph [fontname = "sans-serif", fontsize=10, ranksep=0.6, newrank=true];
        node [fontname = "sans-serif", fontsize=10, margin=0.15];
        edge [fontname = "sans-serif", fontsize=10];

         subgraph cluster_codehosting {
            rank=same;
            graph [color=lightgrey,
               label="Upstream code hosting",
               style=filled
            ];

            "VCS repository" [shape=cylinder];
         }

         subgraph cluster_weblate {
            rank=same;
            graph [color=lightgrey,
               label="Weblate",
               style=filled
            ];

            repo [label="Weblate repository",
               shape=cylinder];
            database [label=Database,
               shape=cylinder];
         }

        "Developers" [shape=box, fillcolor="#144d3f", fontcolor=white, style=filled];
        "Translators" [shape=box, fillcolor="#144d3f", fontcolor=white, style=filled];

        "Developers" -> "VCS repository" [label=" 1. Push "];

        "VCS repository" -> "VCS repository" [label=" 2. Updating translations ", style=dotted];

        "VCS repository" -> repo [label=" 3. Pull "];
        repo -> database [label=" 3. Parse translations "];

        "database" -> repo [label=" 5. Commit changes "];

        "Translators" -> "database" [label=" 4. Translate "];

        "repo" -> "VCS repository" [label=" 6. Push repository "];
    }

.. hint::

   Upstream code hosting is not necessary, you can use Weblate with
   :ref:`vcs-local` where there is only the repository inside Weblate.

.. _update-vcs:

Updating repositories
---------------------

You should set up some way of updating backend repositories from their
source.

* Use :ref:`hooks` to integrate with most of common code hosting services:

  * :ref:`github-setup`
  * :ref:`gitlab-setup`
  * :ref:`bitbucket-setup`
  * :ref:`pagure-setup`
  * :ref:`azure-setup`
  * :ref:`gitea-setup`

* Manually trigger update either in the repository management or using :ref:`api` or :ref:`wlc`

* Enable :setting:`AUTO_UPDATE` to automatically update all components on your Weblate instance

* Execute :wladmin:`updategit` (with selection of project or ``--all`` to update all)

Whenever Weblate updates the repository, the post-update addons will be
triggered, see :ref:`addons`.

.. _avoid-merge-conflicts:

Avoiding merge conflicts
++++++++++++++++++++++++

The merge conflicts from Weblate arise when same file was changed both in
Weblate and outside it. There are two approaches to deal with that - avoid
edits outside Weblate or integrate Weblate into your updating process, so that
it flushes changes prior to updating the files outside Weblate.

The first approach is easy with monolingual files — you can add new strings
within Weblate and leave whole editing of the files there. For bilingual files,
there is usually some kind of message extraction process to generate
translatable files from the source code. In some cases this can be split into
two parts - one for the extraction generates template (for example gettext POT
is generated using :program:`xgettext`) and then further process merges it into
actual translations (the gettext PO files are updated using
:program:`msgmerge`). You can perform the second step within Weblate and it
will ensure that all pending changes are included prior to this operation.

The second approach can be achieved by using :ref:`api` to force Weblate to
push all pending changes and lock the translation while you are doing changes
on your side.

The script for doing updates can look like this:

.. code-block:: sh

    # Lock Weblate translation
    wlc lock
    # Push changes from Weblate to upstream repository
    wlc push
    # Pull changes from upstream repository to your local copy
    git pull
    # Update translation files, this example is for Django
    ./manage.py makemessages --keep-pot -a
    git commit -m 'Locale updates' -- locale
    # Push changes to upstream repository
    git push
    # Tell Weblate to pull changes (not needed if Weblate follows your repo
    # automatically)
    wlc pull
    # Unlock translations
    wlc unlock

If you have multiple components sharing same repository, you need to lock them
all separately:

.. code-block:: sh

    wlc lock foo/bar
    wlc lock foo/baz
    wlc lock foo/baj

.. note::

    The example uses :ref:`wlc`, which needs configuration (API keys) to be
    able to control Weblate remotely. You can also achieve this using any HTTP
    client instead of wlc, e.g. curl, see :ref:`api`.

Avoiding merge conflicts on Weblate originated changes
``````````````````````````````````````````````````````

Even when Weblate is the single source of the changes in the translation files,
conflicts can appear when using :ref:`addon-weblate.git.squash` add-on,
:ref:`component-merge_style` is configured to :guilabel:`Rebase`, or you are
squashing commits outside of Weblate (for example when merging a pull request).

The reason for merge conflicts is different in this case - there are changes in
Weblate which happened after you merged Weblate commits. This typically happens
if merging is not automated and waits for days or weeks for a human to review
them. Git is then sometimes no longer able to identify upstream changes as
matching the Weblate ones and refuses to perform a rebase.

To approach this, you either need to minimize amount of pending changes in
Weblate when you merge a pull request, or avoid the conflicts completely by not
squashing changes.

Here are few options how to avoid that:

* Do not use neither :ref:`addon-weblate.git.squash` nor squashing at merge time. This is the root cause why git doesn't recognize changes after merging.
* Let Weblate commit pending changes before merging. This will update the pull request with all its changes and both repositories will be in sync.
* Use the review features in Weblate (see :doc:`/workflows`), so that you can automatically merge GitHub pull requests after CI passes.
* Use locking in Weblate to avoid changes while GitHub pull request is in review.

.. seealso::

   :ref:`wlc`

.. _github-setup:

Automatically receiving changes from GitHub
+++++++++++++++++++++++++++++++++++++++++++

Weblate comes with native support for GitHub.

If you are using Hosted Weblate, the recommended approach is to install the
`Weblate app <https://github.com/apps/weblate>`_, that way you will get the
correct setup without having to set much up. It can also be used for pushing
changes back.

To receive notifications on every push to a GitHub repository,
add the Weblate Webhook in the repository settings (:guilabel:`Webhooks`)
as shown on the image below:

.. image:: /images/github-settings.png

For the payload URL, append ``/hooks/github/`` to your Weblate URL, for example
for the Hosted Weblate service, this is ``https://hosted.weblate.org/hooks/github/``.

You can leave other values at default settings (Weblate can handle both
content types and consumes just the `push` event).

.. seealso::

   :http:post:`/hooks/github/`, :ref:`hosted-push`

.. _bitbucket-setup:

Automatically receiving changes from Bitbucket
++++++++++++++++++++++++++++++++++++++++++++++

Weblate has support for Bitbucket webhooks, add a webhook
which triggers upon repository push, with destination to ``/hooks/bitbucket/`` URL
on your Weblate installation (for example
``https://hosted.weblate.org/hooks/bitbucket/``).

.. image:: /images/bitbucket-settings.png

.. seealso::

   :http:post:`/hooks/bitbucket/`, :ref:`hosted-push`

.. _gitlab-setup:

Automatically receiving changes from GitLab
+++++++++++++++++++++++++++++++++++++++++++

Weblate has support for GitLab hooks, add a project webhook
with destination to ``/hooks/gitlab/`` URL on your Weblate installation
(for example ``https://hosted.weblate.org/hooks/gitlab/``).

.. seealso::

   :http:post:`/hooks/gitlab/`, :ref:`hosted-push`

.. _pagure-setup:

Automatically receiving changes from Pagure
+++++++++++++++++++++++++++++++++++++++++++

Weblate has support for Pagure hooks, add a webhook
with destination to ``/hooks/pagure/`` URL on your Weblate installation (for
example ``https://hosted.weblate.org/hooks/pagure/``). This can be done in
:guilabel:`Activate Web-hooks` under :guilabel:`Project options`:

.. image:: /images/pagure-webhook.png

.. seealso::

   :http:post:`/hooks/pagure/`, :ref:`hosted-push`

.. _azure-setup:

Automatically receiving changes from Azure Repos
++++++++++++++++++++++++++++++++++++++++++++++++

Weblate has support for Azure Repos webhooks, add a webhook for
:guilabel:`Code pushed` event with destination to ``/hooks/azure/`` URL on your
Weblate installation (for example ``https://hosted.weblate.org/hooks/azure/``).
This can be done in :guilabel:`Service hooks` under :guilabel:`Project
settings`.


.. seealso::

   `Web hooks in Azure DevOps manual <https://learn.microsoft.com/en-us/azure/devops/service-hooks/services/webhooks?view=azure-devops>`_,
   :http:post:`/hooks/azure/`, :ref:`hosted-push`

.. _gitea-setup:

Automatically receiving changes from Gitea Repos
++++++++++++++++++++++++++++++++++++++++++++++++

Weblate has support for Gitea webhooks, add a :guilabel:`Gitea Webhook` for
:guilabel:`Push events` event with destination to ``/hooks/gitea/`` URL on your
Weblate installation (for example ``https://hosted.weblate.org/hooks/gitea/``).
This can be done in :guilabel:`Webhooks` under repository :guilabel:`Settings`.

.. seealso::

   `Webhooks in Gitea manual <https://docs.gitea.io/en-us/webhooks/>`_,
   :http:post:`/hooks/gitea/`, :ref:`hosted-push`

.. _gitee-setup:

Automatically receiving changes from Gitee Repos
++++++++++++++++++++++++++++++++++++++++++++++++

Weblate has support for Gitee webhooks, add a :guilabel:`WebHook` for
:guilabel:`Push` event with destination to ``/hooks/gitee/`` URL on your
Weblate installation (for example ``https://hosted.weblate.org/hooks/gitee/``).
This can be done in :guilabel:`WebHooks` under repository :guilabel:`Management`.

.. seealso::

   `Webhooks in Gitee manual <https://gitee.com/help/categories/40>`_,
   :http:post:`/hooks/gitee/`, :ref:`hosted-push`

Automatically updating repositories nightly
+++++++++++++++++++++++++++++++++++++++++++

Weblate automatically fetches remote repositories nightly to improve
performance when merging changes later. You can optionally turn this into doing
nightly merges as well, by enabling :setting:`AUTO_UPDATE`.

.. _push-changes:

Pushing changes from Weblate
----------------------------

Each translation component can have a push URL set up (see
:ref:`component-push`), and in that case Weblate will be able to push change to
the remote repository.  Weblate can be also be configured to automatically push
changes on every commit (this is default, see :ref:`component-push_on_commit`).
If you do not want changes to be pushed automatically, you can do that manually
under :guilabel:`Repository maintenance` or using the API via :option:`wlc push`.

The push options differ based on the :ref:`vcs` used, more details are found in that chapter.

In case you do not want direct pushes by Weblate, there is support for
:ref:`vcs-github`, :ref:`vcs-gitlab`, :ref:`vcs-gitea`, :ref:`vcs-pagure`,
:ref:`vcs-azure-devops` pull requests or :ref:`vcs-gerrit` reviews, you can activate these by
choosing :guilabel:`GitHub`, :guilabel:`GitLab`, :guilabel:`Gitea`, :guilabel:`Gerrit`,
:guilabel:`Azure DevOps`, or :guilabel:`Pagure` as :ref:`component-vcs` in :ref:`component`.

Overall, following options are available with Git, Mercurial, GitHub, GitLab,
Gitea, Pagure, and Azure DevOps:

+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Desired setup                           | :ref:`component-vcs`          | :ref:`component-push`         | :ref:`component-push_branch`  |
+=========================================+===============================+===============================+===============================+
| No push                                 | :ref:`vcs-git`                | `empty`                       | `empty`                       |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Push directly                           | :ref:`vcs-git`                | SSH URL                       | `empty`                       |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Push to separate branch                 | :ref:`vcs-git`                | SSH URL                       | Branch name                   |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| No push                                 | :ref:`vcs-mercurial`          | `empty`                       | `empty`                       |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Push directly                           | :ref:`vcs-mercurial`          | SSH URL                       | `empty`                       |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Push to separate branch                 | :ref:`vcs-mercurial`          | SSH URL                       | Branch name                   |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| GitHub pull request from fork           | :ref:`vcs-github`             | `empty`                       | `empty`                       |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| GitHub pull request from branch         | :ref:`vcs-github`             | SSH URL [#empty]_             | Branch name                   |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| GitLab merge request from fork          | :ref:`vcs-gitlab`             | `empty`                       | `empty`                       |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| GitLab merge request from branch        | :ref:`vcs-gitlab`             | SSH URL [#empty]_             | Branch name                   |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Gitea merge request from fork           | :ref:`vcs-gitea`              | `empty`                       | `empty`                       |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Gitea merge request from branch         | :ref:`vcs-gitea`              | SSH URL [#empty]_             | Branch name                   |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Pagure merge request from fork          | :ref:`vcs-pagure`             | `empty`                       | `empty`                       |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Pagure merge request from branch        | :ref:`vcs-pagure`             | SSH URL [#empty]_             | Branch name                   |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Azure DevOps pull request from fork     | :ref:`vcs-azure-devops`       | `empty`                       | `empty`                       |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+
| Azure DevOps pull request from branch   | :ref:`vcs-azure-devops`       | SSH URL [#empty]_             | Branch name                   |
+-----------------------------------------+-------------------------------+-------------------------------+-------------------------------+

.. [#empty] Can be empty in case :ref:`component-repo` supports pushing.


.. note::

   You can also enable automatic pushing of changes after Weblate commits, this can be done in
   :ref:`component-push_on_commit`.

.. seealso::

    See :ref:`vcs-repos` for setting up SSH keys, and :ref:`lazy-commit` for
    info about when Weblate decides to commit changes.

Protected branches
++++++++++++++++++

If you are using Weblate on protected branch, you can configure it to use pull
requests and perform actual review on the translations (what might be
problematic for languages you do not know). An alternative approach is to waive
this limitation for the Weblate push user.

For example on GitHub this can be done in the repository configuration:

.. image:: /images/github-protected.png

Interacting with others
-----------------------

Weblate makes it easy to interact with others using its API.

.. seealso::

   :ref:`api`

.. _lazy-commit:

Lazy commits
------------

The behaviour of Weblate is to group commits from the same author into one
commit if possible. This greatly reduces the number of commits, however you
might need to explicitly tell it to do the commits in case you want to get the
VCS repository in sync, e.g. for merge (this is by default allowed for the :guilabel:`Managers`
group, see :ref:`privileges`).

The changes in this mode are committed once any of the following conditions are
fulfilled:

* Somebody else changes an already changed string.
* A merge from upstream occurs.
* An explicit commit is requested.
* A file download is requested.
* Change is older than period defined as :ref:`component-commit_pending_age` on :ref:`component`.

.. hint::

   Commits are created for every component. So in case you have many components
   you will still see lot of commits. You might utilize
   :ref:`addon-weblate.git.squash` add-on in that case.

If you want to commit changes more frequently and without checking of age, you
can schedule a regular task to perform a commit. This can be done using
:guilabel:`Periodic Tasks` in :ref:`admin-interface`. First create desired
:guilabel:`Interval` (for example 120 seconds). Then add new periodic task and
choose ``weblate.trans.tasks.commit_pending`` as :guilabel:`Task` with
``{"hours": 0}`` as :guilabel:`Keyword Arguments` and desired interval.

.. _processing:

Processing repository with scripts
----------------------------------

The way to customize how Weblate interacts with the repository is
:ref:`addons`. Consult :ref:`addon-script` for info on how to execute
external scripts through add-ons.

.. _translation-consistency:

Keeping translations same across components
-------------------------------------------

Once you have multiple translation components, you might want to ensure that
the same strings have same translation. This can be achieved at several levels.

Translation propagation
+++++++++++++++++++++++

With :ref:`component-allow_translation_propagation` enabled (what is the default, see
:ref:`component`), all new translations are automatically done in all
components with matching strings. Such translations are properly credited to
currently translating user in all components.

.. note::

   The translation propagation requires the key to be match for monolingual
   translation formats, so keep that in mind when creating translation keys.

Consistency check
+++++++++++++++++

The :ref:`check-inconsistent` check fires whenever the strings are different.
You can utilize this to review such differences manually and choose the right
translation.

.. _automatic-translation:

Automatic translation
+++++++++++++++++++++

Automatic translation based on different components can be way to synchronize
the translations across components. You can either trigger it manually (see
:ref:`auto-translation`) or make it run automatically on repository update
using add-on (see :ref:`addon-weblate.autotranslate.autotranslate`).
