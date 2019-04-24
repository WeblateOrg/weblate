Frequently Asked Questions
==========================

Configuration
+++++++++++++

.. _auto-workflow:

How to create an automated workflow?
------------------------------------

Weblate can handle all the translation things semi-automatically for you. If
you give it push access to your repository, the translations can happen
without interaction unless some merge conflict occurs.

1. Set up your git repository to tell Weblate whenever there is any change, see
   :ref:`hooks` for information how to do it.
2. Set push URL at your :ref:`component` in Weblate, this will allow Weblate
   to push changes to your repository.
3. Enable push on commit on your :ref:`project` in Weblate, this will make
   Weblate push changes to your repository whenever they are committed at Weblate.

.. seealso::

   :ref:`continuous-translation`, :ref:`avoid-merge-conflicts`

How to access repositories over SSH?
------------------------------------

Please see :ref:`vcs-repos` for information about setting up SSH keys.

.. _merge:

How to fix merge conflicts in translations?
-------------------------------------------

The merge conflicts happen from time to time when the translation file is changed in
both Weblate and the upstream repository. You can usually avoid this by merging
Weblate translations prior to doing some changes in the translation files (e.g.
before executing msgmerge). Just tell Weblate to commit all pending
translations (you can do it in the :guilabel:`Repository maintenance` in the
:guilabel:`Tools` menu) and merge the repository (if automatic push is not
enabled).

If you've already ran into the merge conflict, the easiest way is to solve all
conflicts locally at your workstation - simply add Weblate as a remote
repository, merge it into upstream and fix any conflicts.  Once you push changes
back, Weblate will be able to use the merged version without any other special
actions.

.. note::

   Depending on your setup, access to the Weblte repository might require
   authentication. When using Weblate built in :ref:`git-exporter`, you
   authenticate with your username and the API key.

.. code-block:: sh

    # Commit all pending changes in Weblate, you can do this in the UI as well
    wlc commit
    # Lock translation in Weblate, again this can be done in the UI as well
    wlc lock
    # Add Weblate as remote
    git remote add weblate https://hosted.weblate.org/git/project/component/
    # You might need to include credentials in some cases:
    git remote add weblate https://username:APIKEY@hosted.weblate.org/git/project/component/

    # Update weblate remote
    git remote update weblate

    # Merge Weblate changes
    git merge weblate/master

    # Resolve conflicts
    edit ....
    git add ...
    ...
    git commit

    # Push changes to upstream repository, Weblate will fetch merge from there
    git push

    # Open Weblate for translation
    wlc unlock

If you're using multiple branches in Weblate, you can work similarly on all
branches:

.. code-block:: sh

    # Add and update Weblate remotes
    git remote add weblate-one https://hosted.weblate.org/git/project/one/
    git remote add weblate-second https://hosted.weblate.org/git/project/second/
    git remote update weblate-one weblate-second

    # Merge QA_4_7 branch
    git checkout QA_4_7
    git merge weblate-one/QA_4_7
    ... # Resolve conflicts
    git commit

    # Merge master branch
    git checkout master
    git merge weblates-second/master
    ... # Resolve conflicts
    git commit

    # Push changes to upstream repository, Weblate will fetch merge from there
    git push

In case of Gettext po files, there is a way to merge conflict in a semi-automatic way:

Get and keep local clone of the Weblate git repository. Also get a second fresh
local clone of the upstream git repository (i. e. you need two copies of the
upstream git repository: intact and working copy):


.. code-block:: sh

    # Add remote
    git remote add weblate /path/to/weblate/snapshot/

    # Update weblate remote
    git remote update weblate

    # Merge Weblate changes
    git merge weblate/master

    # Resolve conflicts in the po files
    for PO in `find . -name '*.po'` ; do
        msgcat --use-first /path/to/weblate/snapshot/$PO\
                   /path/to/upstream/snapshot/$PO -o $PO.merge
        msgmerge --previous --lang=${PO%.po} $PO.merge domain.pot -o $PO
        rm $PO.merge
        git add $PO
    done
    git commit

    # Push changes to upstream repository, Weblate will fetch merge from there
    git push

.. seealso::

   :ref:`git-export`, :ref:`continuous-translation`, :ref:`avoid-merge-conflicts`

How do I translate several branches at once?
--------------------------------------------

Weblate supports pushing translation changes within one :ref:`project`. For
every :ref:`component` which has it enabled (the default behavior), the change
made is automatically propagated to others. This way the translations are kept
synchronized even if the branches themselves have already diverged quite a lot
and it is not possible to simply merge translation changes between them.

Once you merge changes from Weblate, you might have to merge these branches
(depending on your development workflow) discarding differences:

.. code-block:: sh

    git merge -s ours origin/maintenance

.. _git-export:

How to export the Git repository that Weblate uses?
---------------------------------------------------

There is nothing special about the repository, it lives under the
:setting:`DATA_DIR` directory and is named :file:`vcs/<project>/<component>/`. If you
have SSH access to this machine, you can use the repository directly.

For anonymous access you might want to run a git server and let it serve the
repository to the outside world.

Alternatively you can use :ref:`git-exporter` inside Weblate to automate this.

What are the options for pushing changes back upstream?
-------------------------------------------------------

This heavily depends on your setup, Weblate is quite flexible in this area.
Here are examples of workflows used with Weblate:

- Weblate automatically pushes and merges changes (see :ref:`auto-workflow`)
- You manually tell Weblate to push (it needs push access to the upstream repository)
- Somebody manually merges changes from the Weblate git repository into the upstream
  repository
- Somebody rewrites history produced by Weblate (eg. by eliminating merge
  commits), merges changes and tells Weblate to reset the content on the upstream
  repository.

Of course you are free to mix all of these as you wish.

How can I limit Weblate access to translations only without exposing source code to it?
----------------------------------------------------------------------------------------

You can use `git submodule`_ for separating translations from source code
while still having them under version control.

1. Create a repository with your translation files.
2. Add this as a submodule to your code:

   .. code-block:: sh

        git submodule add git@example.com:project-translations.git path/to/translations

3. Link Weblate to this repository, it no longer needs access to the repository
   with your source code.
4. You can update the main repository with translations from Weblate by:

   .. code-block:: sh

        git submodule update --remote path/to/translations

Please consult `git submodule`_ documentation for more details.

.. _`git submodule`: https://git-scm.com/docs/git-submodule

How can I check if my Weblate is configured properly?
-----------------------------------------------------

Weblate includes a set of configuration checks which you can see in the admin
interface, just follow the :guilabel:`Performance report` link in the admin interface or
open the ``/admin/performance/`` URL directly.

.. _faq-site:

Why do links contain example.com as the domain?
-----------------------------------------------

Weblate uses Django's sites framework and it defines the site name inside the
database. You need to set the domain name to match your installation.

.. seealso::

   :ref:`production-site`

Why are all commits committed by Weblate <noreply@weblate.org>?
---------------------------------------------------------------

This is the default committer name, configured when you create a translation component.
You can also change it in the administration at any time.

The author of every commit (if the underlying VCS supports it) is still recorded
correctly as the user who has made the translation.

.. seealso::

   :ref:`component`

Usage
+++++

How do I review others translations?
------------------------------------

- You can subscribe to any changes made in :ref:`subscriptions` and then check
  others contributions in email.
- There is a review tool available at the bottom of the translation view, where you can
  choose to browse translations made by others since a given date.

How do I provide feedback on a source string?
---------------------------------------------

On context tabs below translation, you can use the :guilabel:`Source` tab to
provide feedback on a source string or discuss it with other translators.

How can I use existing translations while translating?
------------------------------------------------------

Weblate provides you with several ways to utilize existing translations while
translating:

- You can use the import functionality to load compendium as translations,
  suggestions or translations needing review. This is the best approach for a one time
  translation using compendium or similar translation database.
- You can setup :ref:`tmserver` with all databases you have and let Weblate use
  it. This is good for cases when you want to use it for several times during
  translating.
- Another option is to translate all related projects in a single Weblate
  instance, which will make it automatically pick up translations from other
  projects as well.

.. seealso::

   :ref:`machine-translation-setup`, :ref:`machine-translation`

Does Weblate update translation files besides translations?
-----------------------------------------------------------

Weblate tries to limit changes in translation files to a minimum. For some file
formats it might unfortunately lead to reformatting the file. If you want to
keep the file formatted in your way, please use a pre-commit hook for that.

For monolingual files (see :ref:`formats`) Weblate might add new translation
strings which are present in the :guilabel:`template` and not in actual
translations. It does not however perform any automatic cleanup of stale
strings as that might have unexpected outcomes. If you want to do this, please
install a pre-commit hook which will handle the cleanup according to your requirements.

Weblate also will not try to update bilingual files in any way, so if you need
:file:`po` files being updated from :file:`pot`, you need to do it yourself.

.. seealso::

   :ref:`processing`


Where do language definitions come from and how can I add my own?
-----------------------------------------------------------------

The basic set of language definitions is included within Weblate and
Translate-toolkit. This covers more than 150 languages and includes information
about used plural forms or text direction.

You are free to define own languages in the administrative interface, you just need
to provide information about it.

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

For example with Gettext PO files, you can update the translation files using
the :command:`msgmerge` tool:

.. code-block:: sh

    msgmerge -U locale/cs/LC_MESSAGES/django.mo locale/django.pot

In case you want to do the update automatically, you can install
addon :ref:`addon-weblate.gettext.msgmerge`.

Troubleshooting
+++++++++++++++

Requests sometimes fail with too many open files error
------------------------------------------------------

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

.. _faq-ft-slow:

Fulltext search is too slow
---------------------------

Depending on various conditions (frequency of updates, server restarts and
other), the fulltext index might become too fragmented over time. It is recommended to
optimize it from time to time:

.. code-block:: sh

    ./manage.py rebuild_index --optimize

In case it does not help (or if you have removed a lot of strings) it might be
better to rebuild it from scratch:

.. code-block:: sh

    ./manage.py rebuild_index --clean

.. seealso::

   :djadmin:`rebuild_index`

.. _faq-ft-lock:

I get "Lock Error" quite often while translating
------------------------------------------------

This is usually caused by concurrent updates to the fulltext index. In case you are
running a multi-threaded server (e.g. mod_wsgi), this happens quite often. For such
a setup it is recommended to use Celery to perform updates in the background.

.. seealso::

   :ref:`fulltext`, :ref:`celery`

.. _faq-ft-space:

Rebuilding index has failed with "No space left on device"
----------------------------------------------------------

Whoosh uses a temporary directory to build indices. In case you have a small /tmp
(eg. using ramdisk), this might fail. Change the temporary directory by passing it
as ``TEMP`` variable:

.. code-block:: sh

    TEMP=/path/to/big/temp ./manage.py rebuild_index --clean

.. seealso::

   :djadmin:`rebuild_index`


Database operations fail with "too many SQL variables"
------------------------------------------------------

This can happen when using theSQLite database as it is not powerful enough for some
relations used within Weblate. The only way to fix this is to use some more
capable database, see :ref:`production-database` for more information.

.. seealso::

   :ref:`production-database`,
   :doc:`django:ref/databases`


When accessing the site I get Bad Request (400) error
-----------------------------------------------------

This is most likely caused by an improperly configured :setting:`ALLOWED_HOSTS`.
It needs to contain all hostnames you want to access your Weblate. For example:

.. code-block:: python

    ALLOWED_HOSTS = ['weblate.example.com', 'weblate', 'localhost']

.. seealso::

    :ref:`production-hosts`

Features
++++++++

.. _faq-vcs:

Does Weblate support other VCS than Git and Mercurial?
------------------------------------------------------

Weblate currently does not have native support for anything other than
:ref:`vcs-git` (with extended support for :ref:`vcs-github`, :ref:`vcs-gerrit`
and :ref:`vcs-git-svn`) and ref:`vcs-mercurial`, but it is possible to write
backends for other VCSes.

You can also use :ref:`vcs-git-helpers` in Git to access other VCSes.


.. note::

    For native support of other VCS, Weblate requires distributed VCS and could
    be probably adjusted to work with anything other than Git and Mercurial, but
    somebody has to implement this support.

.. seealso:: :ref:`vcs`

How does Weblate credit translators?
------------------------------------

Every change made in Weblate is committed into VCS under the translators name. This
way every single change has proper authorship and you can track it down using
standard VCS tools you use for code.

Additionally, when the translation file format supports it, the file headers are
updated to include the translator name.

.. seealso:: :djadmin:`list_translators`

Why does Weblate force to show all po files in a single tree?
-------------------------------------------------------------

Weblate was designed in a way that every po file is represented as a single
component. This is beneficial for translators, so they know what they are
actually translating. If you feel your project should be translated as one,
consider merging these po files. It will make life easier even for translators
not using Weblate.

.. note::

    In case there will be big demand for this feature, it might be implemented
    in future versions, but it's definitely not a priority for now.

.. _faq-codes:

Why does Weblate use language codes such sr_Latn or zh_Hant?
------------------------------------------------------------

These are language codes defined by :rfc:`4646` to better indicate that they
are really different languages instead previously wrongly used modifiers (for
``@latin`` variants) or country codes (for Chinese).

Weblate will still understand legacy language codes and will map them to
current one - for example ``sr@latin`` will be handled as ``sr_Latn`` or
``zh@CN`` as ``sr_Hans``.
