.. _continuous-translation:

Continuous localization
=======================

There is infrastructure in place so that your translation closely follows
development. This way translators can work on translations the entire time,
instead of working through huge amount of new text just prior to release.

.. seealso::

   :doc:`/devel/integration` describes basic ways to integrate your development
   with Weblate.
   :doc:`/admin/code-hosting` lists provider-specific setup steps for common
   code hosting sites.

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

* Use :ref:`hooks` to integrate with most of common code hosting services, see
  :doc:`/admin/code-hosting`. You must also :ref:`project-enable_hooks` for
  this to work.

* Manually trigger update either in the repository management or using :ref:`api` or :ref:`wlc`

* Enable :setting:`AUTO_UPDATE` to automatically update all components on your Weblate instance

* Execute :wladmin:`updategit` (with selection of project or ``--all`` to update all)

Whenever Weblate updates the repository, the post-update addons will be
triggered, see :ref:`addons`.

.. _avoid-merge-conflicts:

Avoiding merge conflicts
++++++++++++++++++++++++

The merge conflicts from Weblate arise when same file was changed both in
Weblate and outside it. Depending on the situation, there are several approaches that might help here:

* :ref:`merge-weblate-only`
* :ref:`merge-weblate-locking`
* :ref:`merge-weblate-git`

.. _merge-weblate-only:

Avoiding merge conflicts by changing translation files in Weblate only
``````````````````````````````````````````````````````````````````````

Avoiding edits outside Weblate is easy with monolingual files — you can add new strings
within Weblate and leave whole editing of the files there. For bilingual files,
there is usually some kind of message extraction process to generate
translatable files from the source code. In some cases, this can be split into
two parts:

1. The extraction generates template (for example gettext POT is generated using :program:`xgettext`).
2. Further process merges it into actual translations (the gettext PO files are updated using :program:`msgmerge`).

You can perform the second step within Weblate and it
will ensure that all pending changes are included before this operation.

.. _merge-weblate-locking:

Avoiding merge conflicts by locking Weblate while doing outside changes
```````````````````````````````````````````````````````````````````````

Integrating Weblate into your updating process so that it flushes changes before updating the files outside Weblate can be achieved by using :ref:`api` to force Weblate to
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

If you have multiple components sharing the same repository, you need to lock them
all separately:

.. code-block:: sh

    wlc lock foo/bar
    wlc lock foo/baz
    wlc lock foo/baj

.. note::

    The example uses :ref:`wlc`, which needs configuration (API keys) to be
    able to control Weblate remotely. You can also achieve this using any HTTP
    client instead of :ref:`wlc`, for example curl, see :ref:`api`.

.. _repository-maintenance:

Repository maintenance
++++++++++++++++++++++

The :guilabel:`Repository maintenance` view shows repository status for a
project, component, or translation and lets privileged users run maintenance
operations from the user interface.

The same actions can also be triggered using :ref:`api` or, for the supported
subset, :ref:`wlc`.

Availability of individual actions depends on permissions, the configured
version control system, whether pushing is configured, and whether the selected
object can be locked.

.. list-table::
   :header-rows: 1

   * - Action
     - What it does
     - Typical use

   * - :guilabel:`Commit`
     - Commits pending changes stored in Weblate to the local repository.
     - Flush pending Weblate changes before doing repository work elsewhere.

   * - :guilabel:`Push`
     - Pushes committed local repository changes to the configured upstream.
     - Send committed translations upstream when automatic push is disabled or delayed.

   * - :guilabel:`Update`
     - Fetches upstream changes and integrates them using the component's configured :ref:`component-merge_style`.
     - Bring Weblate in sync with upstream using the default integration strategy.

   * - :guilabel:`Update with merge`
     - Fetches upstream changes and integrates them with an explicit merge.
     - Override the default merge style for a single update.

   * - :guilabel:`Update with rebase`
     - Fetches upstream changes and rebases local Weblate commits on top of upstream.
     - Keep history linear when that matches your workflow.

   * - :guilabel:`Update with merge without fast-forward`
     - Fetches upstream changes and creates an explicit merge commit even when a fast-forward would be possible.
     - Preserve merge commits for auditing or branch-management reasons.

   * - :guilabel:`Lock` / :guilabel:`Unlock`
     - Prevents or allows translators to make further changes in Weblate.
     - Freeze translation changes while doing repository maintenance outside Weblate.

   * - :guilabel:`Reset and discard`
     - Resets Weblate's local repository to upstream and discards pending Weblate changes.
     - Use when upstream should overwrite the local Weblate repository state.

   * - :guilabel:`Reset and reapply`
     - Resets Weblate's local repository to upstream while preserving pending translations. See :ref:`manage-vcs-reset-reapply`.
     - Recover from diverged history while keeping pending Weblate translations.

   * - :guilabel:`Cleanup`
     - Removes untracked files and stale branches from the local repository checkout.
     - Clean up leftover files or stale repository state in Weblate's checkout.

   * - :guilabel:`Synchronize`
     - Forces Weblate to write all known translations back to the repository files.
     - Repair cases where repository files became out of sync with the database state.

   * - :guilabel:`Rescan`
     - Re-reads translation files from the local repository into Weblate.
     - Import file changes after manual repository work or file creation.

.. _manage-vcs-reset-reapply:

Reset and reapply recovery behavior
````````````````````````````````````

The :guilabel:`Reset and reapply` operation keeps pending translations from
Weblate while resetting the local repository state to match upstream.

The operation can restore pending translations only when the target language
files still exist after the reset or when Weblate can create them for the
component, for example using a valid :ref:`component-new_base`.

If neither of these conditions is met, Weblate keeps the pending changes in its
database and reports a recovery error instead of failing later with a generic
parse error.

.. _merge-weblate-git:

Avoiding merge conflicts by focusing on Git operations
``````````````````````````````````````````````````````

Even when Weblate is the single source of the changes in the translation files,
conflicts can appear when using :ref:`addon-weblate.git.squash` add-on,
:ref:`component-merge_style` is configured to :guilabel:`Rebase`, or you are
squashing commits outside of Weblate (for example, when merging a pull request).

The reason for merge conflicts is different in this case - there are changes in
Weblate which happened after you merged Weblate commits. This typically happens
if merging is not automated and waits for days or weeks for a human to review
them. Git is then sometimes no longer able to identify upstream changes as
matching the Weblate ones and refuses to perform a rebase.

To approach this, you either need to minimize the amount of pending changes in
Weblate when you merge a pull request, or avoid the conflicts completely by not
squashing changes.

Here are few options how to avoid that:

* Do not use neither :ref:`addon-weblate.git.squash` nor squashing at merge time. This is the root cause why git doesn't recognize changes after merging.
* Let Weblate commit pending changes before merging. This will update the pull request with all its changes, and both repositories will be in sync.
* Use the review features in Weblate (see :doc:`/workflows`) so that you can automatically merge GitHub pull requests after CI passes.
* Use locking in Weblate to avoid changes while GitHub pull request is in review.

.. seealso::

   :ref:`wlc`

Code hosting notifications
++++++++++++++++++++++++++

Provider-specific app and webhook instructions for GitHub, GitLab, Bitbucket,
Pagure, Azure Repos, Gitea, Forgejo, and Gitee are covered in
:doc:`/admin/code-hosting`.

.. _github-setup:
.. _gitlab-setup:
.. _bitbucket-setup:
.. _pagure-setup:
.. _azure-setup:
.. _gitea-setup:
.. _forgejo-setup:
.. _gitee-setup:

Provider-specific notifications
```````````````````````````````

These legacy anchors are kept for compatibility. Current provider-specific app
and webhook setup is documented in :doc:`/admin/code-hosting`.

.. seealso::

   * :ref:`GitHub notifications <code-hosting-github-notifications>`
   * :ref:`GitLab notifications <code-hosting-gitlab-notifications>`
   * :ref:`Bitbucket notifications <code-hosting-bitbucket-notifications>`
   * :ref:`Pagure notifications <code-hosting-pagure-notifications>`
   * :ref:`Azure Repos notifications <code-hosting-azure-repos-notifications>`
   * :ref:`Gitea notifications <code-hosting-gitea-notifications>`
   * :ref:`Forgejo notifications <code-hosting-forgejo-notifications>`
   * :ref:`Gitee notifications <code-hosting-gitee-notifications>`

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
the remote repository. Weblate can be also be configured to automatically push
changes on every commit (this is default, see :ref:`component-push_on_commit`).
If you do not want changes to be pushed automatically, you can do that manually
under :guilabel:`Repository maintenance` or using the API via :option:`wlc push`.

The push options differ based on the :ref:`vcs` used, more details are found in that chapter.
For provider-specific push setup, see :doc:`/admin/code-hosting`.

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
Gitea, Pagure, Azure DevOps, Bitbucket Data Center and Bitbucket Cloud:

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

   * - Push to separate branch
     - :ref:`vcs-mercurial`
     - SSH URL
     - Branch name

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

.. _translation-propagation:

Translation propagation
+++++++++++++++++++++++

With :ref:`component-allow_translation_propagation` enabled (what is the default, see
:ref:`component`), all new translations are automatically done in all
components with matching strings. Such translations are properly credited to
currently translating user in all components.

Propagation preconditions:

- All components have to reside in a single project (linking component is not enough).
- Enable :ref:`component-allow_translation_propagation` to automatically reuse translations for matching strings.
- The translation propagation requires the key to be match for monolingual
  translation formats, so keep that in mind when creating translation keys.
- The strings are propagated while translating, strings loaded from the
  repository are not propagated.

.. tip::

   This feature currently has limitations, and we want to make it more
   universal. Please share your feedback at
   https://github.com/WeblateOrg/weblate/issues/3166.

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
