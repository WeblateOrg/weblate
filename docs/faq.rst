Frequently Asked Questions
==========================

Configuration
+++++++++++++

.. _auto-workflow:

How to create an automated workflow?
------------------------------------

Weblate can handle all the translation things semi-automatically for you. If
you give it push access to your repository, the translations can happen
without interaction, unless some merge conflict occurs.

1. Set up your Git repository to tell Weblate when there is any change, see
   :ref:`hooks` for info on how to do it.
2. Set a push URL at your :ref:`component` in Weblate, this allows Weblate
   to push changes to your repository.
3. Turn on :ref:`component-push_on_commit` on your :ref:`component` in Weblate,
   this will make Weblate push changes to your repository whenever they happen
   at Weblate.

.. seealso::

   :ref:`continuous-translation`, :ref:`avoid-merge-conflicts`

How to access repositories over SSH?
------------------------------------

Please see :ref:`vcs-repos` for info on setting up SSH keys.

.. _merge:

How to fix merge conflicts in translations?
-------------------------------------------

Merge conflicts happen from time to time when the translation file is changed in
both Weblate and the upstream repository concurrently. You can usually avoid this by merging
Weblate translations prior to making changes in the translation files (e.g.
before running msgmerge). Just tell Weblate to commit all pending
translations (you can do it in :guilabel:`Repository maintenance` in the
:guilabel:`Manage` menu) and merge the repository (if automatic push is not
on).

If you've already ran into a merge conflict, the easiest way is to solve all
conflicts locally at your workstation - is to simply add Weblate as a remote
repository, merge it into upstream and fix any conflicts. Once you push changes
back, Weblate will be able to use the merged version without any other special
actions.

.. note::

   Depending on your setup, access to the Weblate repository might require
   authentication. When using the built-in :ref:`git-exporter` in Weblate, you
   authenticate with your username and the API key.

.. code-block:: sh

    # Commit all pending changes in Weblate, you can do this in the UI as well:
    wlc commit
    # Lock the translation in Weblate, again this can be done in the UI as well:
    wlc lock
    # Add Weblate as remote:
    git remote add weblate https://hosted.weblate.org/git/project/component/
    # You might need to include credentials in some cases:
    git remote add weblate https://username:APIKEY@hosted.weblate.org/git/project/component/

    # Update weblate remote:
    git remote update weblate

    # Merge Weblate changes:
    git merge weblate/main

    # Resolve conflicts:
    edit …
    git add …
    …
    git commit

    # Push changes to upstream repository, Weblate will fetch merge from there:
    git push

    # Open Weblate for translation:
    wlc unlock

If you're using multiple branches in Weblate, you can do the same to all of them:

.. code-block:: sh

    # Add and update Weblate remotes
    git remote add weblate-one https://hosted.weblate.org/git/project/one/
    git remote add weblate-second https://hosted.weblate.org/git/project/second/
    git remote update weblate-one weblate-second

    # Merge QA_4_7 branch:
    git checkout QA_4_7
    git merge weblate-one/QA_4_7
    ... # Resolve conflicts
    git commit

    # Merge main branch:
    git checkout main
    git merge weblates-second/main
    ... # Resolve conflicts
    git commit

    # Push changes to the upstream repository, Weblate will fetch the merge from there:
    git push

In case of gettext PO files, there is a way to merge conflicts in a semi-automatic way:

Fetch and keep a local clone of the Weblate Git repository. Also get a second fresh
local clone of the upstream Git repository (i. e. you need two copies of the
upstream Git repository: An intact and a working copy):


.. code-block:: sh

    # Add remote:
    git remote add weblate /path/to/weblate/snapshot/

    # Update Weblate remote:
    git remote update weblate

    # Merge Weblate changes:
    git merge weblate/main

    # Resolve conflicts in the PO files:
    for PO in `find . -name '*.po'` ; do
        msgcat --use-first /path/to/weblate/snapshot/$PO\
                   /path/to/upstream/snapshot/$PO -o $PO.merge
        msgmerge --previous --lang=${PO%.po} $PO.merge domain.pot -o $PO
        rm $PO.merge
        git add $PO
    done
    git commit

    # Push changes to the upstream repository, Weblate will fetch merge from there:
    git push

.. seealso::

   :ref:`git-export`,
   :ref:`continuous-translation`,
   :ref:`avoid-merge-conflicts`,
   :ref:`wlc`

How do I translate several branches at once?
--------------------------------------------

Weblate supports pushing translation changes within one :ref:`project`. For
every :ref:`component` which has it turned on (the default behavior), the change
made is automatically propagated to others. This way translations are kept
synchronized even if the branches themselves have already diverged quite a lot,
and it is not possible to simply merge translation changes between them.

Once you merge changes from Weblate, you might have to merge these branches
(depending on your development workflow) discarding differences:

.. code-block:: sh

    git merge -s ours origin/maintenance

.. seealso::

   :ref:`translation-consistency`

How to translate multi-platform projects?
-----------------------------------------

Weblate supports a wide range of file formats (see :doc:`formats`) and the
easiest approach is to use the native format for each platform.

Once you have added all platform translation files as components in one project
(see :ref:`adding-projects`), you can utilize the translation propagation
feature (turned on by default, and can be turned off in the :ref:`component`) to
translate strings for all platforms at once.

.. seealso::

   :ref:`translation-consistency`

.. _git-export:

How to export the Git repository that Weblate uses?
---------------------------------------------------

There is nothing special about the repository, it lives under the
:setting:`DATA_DIR` directory and is named :file:`vcs/<project>/<component>/`. If you
have SSH access to this machine, you can use the repository directly.

For anonymous access, you might want to run a Git server and let it serve the
repository to the outside world.

Alternatively, you can use :ref:`git-exporter` inside Weblate to automate this.

What are the options for pushing changes back upstream?
-------------------------------------------------------

This heavily depends on your setup, Weblate is quite flexible in this area.
Here are examples of some workflows used with Weblate:

- Weblate automatically pushes and merges changes (see :ref:`auto-workflow`).
- You manually tell Weblate to push (it needs push access to the upstream repository).
- Somebody manually merges changes from the Weblate git repository into the upstream
  repository.
- Somebody rewrites history produced by Weblate (e.g. by eliminating merge
  commits), merges changes, and tells Weblate to reset the content in the upstream
  repository.

Of course you are free to mix all of these as you wish.

.. _faq-submodule:

How can I limit Weblate access to only translations, without exposing source code to it?
----------------------------------------------------------------------------------------

You can use `git submodule`_ for separating translations from source code
while still having them under version control.

1. Create a repository with your translation files.
2. Add this as a submodule to your code:

   .. code-block:: sh

        git submodule add git@example.com:project-translations.git path/to/translations

3. Link Weblate to this repository, it no longer needs access to the repository
   containing your source code.
4. You can update the main repository with translations from Weblate by:

   .. code-block:: sh

        git submodule update --remote path/to/translations

Please consult the `git submodule`_ documentation for more details.

.. _`git submodule`: https://git-scm.com/docs/git-submodule

How can I check whether my Weblate is set up properly?
------------------------------------------------------

Weblate includes a set of configuration checks which you can see in the admin
interface, just follow the :guilabel:`Performance report` link in the admin interface, or
open the ``/manage/performance/`` URL directly.


Why are all commits committed by Weblate <noreply@weblate.org>?
---------------------------------------------------------------

This is the default committer name, configured when you create a translation component.
You can change it in the administration at any time.

The author of every commit (if the underlying VCS supports it) is still recorded
correctly as the user that made the translation.

.. seealso::

   :ref:`component`

Usage
+++++

How do I review the translations of others?
---------------------------------------------

- There are several review based workflows available in Weblate, see :ref:`workflows`.
- You can subscribe to any changes made in :ref:`subscriptions` and then check
  others contributions as they come in by e-mail.
- There is a review tool available at the bottom of the translation view, where you can
  choose to browse translations made by others since a given date.

.. seealso::

   :ref:`workflows`

How do I provide feedback on a source string?
---------------------------------------------

On context tabs below translation, you can use the :guilabel:`Comments` tab to
provide feedback on a source string, or discuss it with other translators.

.. seealso::

    :ref:`report-source`,
    :ref:`user-comments`

How can I use existing translations while translating?
------------------------------------------------------

- All translations within Weblate can be used thanks to shared translation memory.
- You can import existing translation memory files into Weblate.
- Use the import functionality to load compendium as translations,
  suggestions or translations needing review. This is the best approach for a one-time
  translation using a compendium or a similar translation database.
- You can set up :ref:`tmserver` with all databases you have and let Weblate use
  it. This is good when you want to use it several times during
  translation.
- Another option is to translate all related projects in a single Weblate
  instance, which will make it automatically pick up translations from other
  projects as well.

.. seealso::

   :ref:`machine-translation-setup`,
   :ref:`machine-translation`,
   :ref:`memory`

.. _faq-cleanup:

Does Weblate update translation files besides translations?
-----------------------------------------------------------

Weblate tries to limit changes in translation files to a minimum. For some file
formats it might unfortunately lead to reformatting the file. If you want to
keep the file formatted your way, please use a pre-commit hook for that.

.. seealso::

   :ref:`updating-target-files`


Where do language definitions come from and how can I add my own?
-----------------------------------------------------------------

The basic set of language definitions is included within Weblate and
Translate-toolkit. This covers more than 150 languages and includes info
about plural forms or text direction.

You are free to define your own languages in the administrative interface, you just need
to provide info about it.

.. seealso::

   :ref:`languages`

Can Weblate highlight changes in a fuzzy string?
------------------------------------------------

Weblate supports this, however it needs the data to show the difference.

For Gettext PO files, you have to pass the parameter ``--previous`` to
:command:`msgmerge` when updating PO files, for example:

.. code-block:: sh

    msgmerge --previous -U po/cs.po po/phpmyadmin.pot

For monolingual translations, Weblate can find the previous string by ID, so it
shows the differences automatically.

.. _translations-update:

Why does Weblate still show old translation strings when I've updated the template?
-----------------------------------------------------------------------------------

Weblate does not try to manipulate the translation files in any way other
than allowing translators to translate. So it also does not update the
translatable files when the template or source code have been changed. You
simply have to do this manually and push changes to the repository, Weblate
will then pick up the changes automatically.

.. note::

    It is usually a good idea to merge changes done in Weblate before updating
    translation files, as otherwise you will usually end up with some conflicts
    to merge.

For example with gettext PO files, you can update the translation files using
the :command:`msgmerge` tool:

.. code-block:: sh

    msgmerge -U locale/cs/LC_MESSAGES/django.mo locale/django.pot

In case you want to do the update automatically, you can install
addon :ref:`addon-weblate.gettext.msgmerge`.

.. seealso::

   :ref:`updating-target-files`


Troubleshooting
+++++++++++++++

Requests sometimes fail with "too many open files" error
--------------------------------------------------------

This happens sometimes when your Git repository grows too much and you have
many of them. Compressing the Git repositories will improve this situation.

The easiest way to do this is to run:

.. code-block:: sh

    # Go to DATA_DIR directory
    cd data/vcs
    # Compress all Git repositories
    for d in */* ; do
        pushd $d
        git gc
        popd
    done

.. seealso::

    :setting:`DATA_DIR`


When accessing the site I get a "Bad Request (400)" error
---------------------------------------------------------

This is most likely caused by an improperly configured :setting:`ALLOWED_HOSTS`.
It needs to contain all hostnames you want to access on your Weblate. For example:

.. code-block:: python

    ALLOWED_HOSTS = ["weblate.example.com", "weblate", "localhost"]

.. seealso::

    :ref:`production-hosts`

.. _faq-duplicate-files:

What does mean "There are more files for the single language (en)"?
-------------------------------------------------------------------

This typically happens when you have translation file for source language.
Weblate keeps track of source strings and reserves source language for this.
The additional file for same language is not processed.

* In case the translation to the source language is desired, please change the :ref:`component-source_language` in the component settings.
* In case the translation file for the source language is not needed, please remove it from the repository.
* In case the translation file for the source language is needed, but should be ignored by Weblate, please adjust the :ref:`component-language_regex` to exclude it.

.. hint::

   You might get similar error message for other languages as well. In that
   case the most likely reason is that several files map to single language in
   Weblate.

   This can be caused by using obsolete language codes together with new one
   (``ja`` and ``jp`` for Japanese) or including both country specific and
   generic codes (``fr`` and ``fr_FR``). See :ref:`language-parsing-codes` for
   more details.

Features
++++++++

.. _faq-vcs:

Does Weblate support other VCSes than Git and Mercurial?
--------------------------------------------------------

Weblate currently does not have native support for anything other than
:ref:`vcs-git` (with extended support for :ref:`vcs-github`, :ref:`vcs-gerrit`
and :ref:`vcs-git-svn`) and :ref:`vcs-mercurial`, but it is possible to write
backends for other VCSes.

You can also use :ref:`vcs-git-helpers` in Git to access other VCSes.

Weblate also supports VCS-less operation, see :ref:`vcs-local`.

.. note::

    For native support of other VCSes, Weblate requires using distributed VCS, and could
    probably be adjusted to work with anything other than Git and Mercurial, but
    somebody has to implement this support.

.. seealso:: :ref:`vcs`

How does Weblate credit translators?
------------------------------------

Every change made in Weblate is committed into VCS under the translators name. This
way every single change has proper authorship, and you can track it down using
the standard VCS tools you use for code.

Additionally, when the translation file format supports it, the file headers are
updated to include the translator's name.

.. seealso::

   :djadmin:`list_translators`,
   :doc:`../devel/reporting`

Why does Weblate force showing all PO files in a single tree?
-------------------------------------------------------------

Weblate was designed in a way that every PO file is represented as a single
component. This is beneficial for translators, so they know what they are
actually translating.

.. versionchanged:: 4.2

   Translators can translate all the components of a project into a specific
   language as a whole.

.. _faq-codes:

Why does Weblate use language codes such sr_Latn or zh_Hant?
------------------------------------------------------------

These are language codes defined by :rfc:`4646` to better indicate that they
are really different languages instead previously wrongly used modifiers (for
``@latin`` variants) or country codes (for Chinese).

Weblate still understands legacy language codes and will map them to
current one - for example ``sr@latin`` will be handled as ``sr_Latn`` or
``zh@CN`` as ``zh_Hans``.

.. seealso::

   :ref:`languages`
