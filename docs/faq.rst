Frequently Asked Questions
==========================

Configuration
+++++++++++++

.. _auto-workflow:

How to create automatic workflow?
---------------------------------

Weblate can handle all the translation things semi-automatically for you. If
you will give it push access to your repository, the translations can live
without interaction unless some merge conflict occurs.

1. Set up your git repository to tell Weblate whenever there is any change, see
   :ref:`hooks` for information how to do it.
2. Set push URL at your :ref:`component` in Weblate, this will allow Weblate
   to push changes to your repository.
3. Enable push on commit on your :ref:`project` in Weblate, this will make
   Weblate push changes to your repository whenever they are committed at Weblate.
4. Optionally setup cron job for :djadmin:`commit_pending`.

.. seealso:: 
   
   :ref:`continuous-translation`

How to access repositories over SSH?
------------------------------------

Please see :ref:`vcs-repos` for information about setting up SSH keys.

.. _merge:

How to fix merge conflicts in translations?
-------------------------------------------

The merge conflicts happen time to time when the translation file is changed in
both Weblate and upstream repository. You can usually avoid this by merging
Weblate translations prior to doing some changes in the translation files (eg.
before executing msgmerge). Just tell Weblate to commit all pending
tranlslations (you can do it in the :guilabel:`Repository maintenance` in the
:guilabel:`Tools` menu) and merge the repository (if automatic push is not
enabled).

If you've already ran to the merge conflict, the easiest way is to solve all
conflicts locally at your workstation - simply add Weblate as remote
repository, merge it into upstream and fix conflicts.  Once you push changes
back, Weblate will be able to use merged version without any other special
actions.

.. code-block:: sh

    # Add remote
    git remote add weblate git://git.weblate.org/debian-handbook.git

    # Update remotes
    git remote update

    # Merge Weblate changes
    git merge weblate/master

    # Resolve conflicts
    edit ....
    git add ...
    ...
    git commit

    # Push changes to upstream respository, Weblate will fetch merge from there
    git push

.. seealso:: 
   
   :ref:`git-export`

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

How to export Git repository weblate uses?
------------------------------------------

There is nothing special about the repository, it lives under
:setting:`DATA_DIR` directory and is named as :file:`vcs/<project>/<component>/`. If you
have SSH access to this machine, you can use the repository directly.

For anonymous access you might want to run git server and let it serve the
repository to outside world.

What are options of pushing changes back upstream?
--------------------------------------------------

This heavily depends on your setup, Weblate is quite flexible in this area.
Here are examples of workflows used with Weblate:

- Weblate automatically pushes and merges changes (see :ref:`auto-workflow`)
- You tell manually Weblate to push (it needs push access to upstream repository)
- Somebody manually merges changes from Weblate git repository into upstream
  repository
- Somebody rewrites history produced by Weblate (eg. by eliminating merge
  commits), merges changes and tells Weblate to reset contet on upstream
  repository.

Of course your are free to mix all of these as you wish.

How can I check if my Weblate is configured properly?
-----------------------------------------------------

Weblate includes set of configuration checks, which you can see in admin
interface, just follow :guilabel:`Performace report` link in admin interface or
directly open ``/admin/performance/`` URL.

.. _faq-site:

Why does links contain example.com as domain?
---------------------------------------------

Weblate uses Django sites framework and it defines site name inside the
database. You need to set the domain name to match your installation.

.. seealso:: 
   
   :ref:`production-site`

Why are all commits committed by Weblate <noreply@weblate.org>?
---------------------------------------------------------------

This is default commiter name configured when you create translation component.
You can also change it in the administration at any time.

The author of every commit (when underlaying VCS supports it) is still recorded
correctly as an user who has made the translation.

.. seealso:: 
   
   :ref:`component`

Why do I get warning about not reflected changes on database migration?
-----------------------------------------------------------------------

When running :command:`./manage.py migrate`, you can get following warning::

    Your models have changes that are not yet reflected in a migration, and so won't be applied.

This is expected as Weblate generates choices for some fields and Django
migrations can not reflect this. You can safely ignore this warning.

Usage
+++++

How do I review others translations?
------------------------------------

- You can subscribe to any changes made in :ref:`subscriptions` and then check
  other contributions in email.
- There is review tool available at bottom of translation view, where you can
  choose to browse translations made by others since given date.

How do I provide feedback on source string?
-------------------------------------------

On context tabs below translation, you can use :guilabel:`Source` tab to
provide feedback on source string or discuss it with other translators.

How can I use existing translations while translating?
------------------------------------------------------

Weblate provides you several ways to utilize existing translations while
translating:

- You can use import functionality to load compendium as translations,
  suggestions or translations needing review. This is best approach for one time
  translation using compedium or similar translation database.
- You can setup :ref:`tmserver` with all databases you have and let Weblate use
  it. This is good for case when you want to use it for several times during
  translating.
- Another option is to translate all related projects in single Weblate
  instance, what will make it automatically pick up translation from other
  projects as well.

.. seealso:: 
   
   :ref:`machine-translation-setup`, :ref:`machine-translation`

Does Weblate update translation files besides translations?
-----------------------------------------------------------

Weblate tries to limit changes in translation files to minimum. For some file
formats it might unfortunately lead to reformatting the file. If you want to
keep the file formattted in your way, please use pre commit hook for that.

For monolingual files (see :ref:`formats`) Weblate might add new translation
units which are present in the :guilabel:`template` and not in actual
translations. It does not however perform any automatic cleanup of stale
strings as it might have unexpected outcome. If you want to do this, please
install pre commit hook which will handle the cleanup according to your needs.

Weblate also will not try to update bilingual files in any way, so if you need
:file:`po` files being updated from :file:`pot`, you need to do it on
your own.

.. seealso:: 
   
   :ref:`processing`


Where do language definition come from and how can I add own?
-------------------------------------------------------------

Basic set of language definitions is included within Weblate and
Translate-toolkit. This covers more than 150 languages and includes information
about used plural forms or text direction.

You are free to define own language in administrative interface, you just need
to provide information about it.

Can Weblate highlight change in a fuzzy string?
-----------------------------------------------

Weblate supports this, however it needs the data to show the difference.

For Gettext PO files, you have to pass parameter ``--previous`` to
:command:`msgmerge` when updating PO files, for example:

.. code-block:: sh

    msgmerge --previous -U po/cs.po po/phpmyadmin.pot

For monolingual translations, Weblate can find the previous string by ID, so it
shows the differences automatically.

.. _translations-update:

Why does Weblate still shows old translation strings when I've updated the template?
------------------------------------------------------------------------------------

Weblate does not try to manipulate with the translation files in any other way
than allowing translators to translate. So it also does not update the
translatable files when the template or source code has been changed. You
simply have to do this manually and push changes to the repository, Weblate
will then pick up the changes automatically.

.. note::

    It is usually good idea to merge changed done in Weblate before updating
    translation files as otherwise you will usually end up with some conflicts
    to merge.

For example with Gettext PO files, you can update the translation files using
the :command:`msgmerge` tool:

.. code-block:: sh

    msgmerge -U locale/cs/LC_MESSAGES/django.mo locale/django.pot

In case you can want to do the update automatically, you can add custom script
to handle this to :setting:`POST_UPDATE_SCRIPTS` and enable it in the
:ref:`component`.

Troubleshooting
+++++++++++++++

Requests sometimes fail with too many open files error
------------------------------------------------------

This happens sometimes when your Git repository grows too much and you have
more of them. Compressing the Git repositories will improve this situation.

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
other), fulltext index might get too fragmented over time. It is recommended to
optimize it time to time:

.. code-block:: sh

    ./manage.py rebuild_index --optimize

In case it does not help (or if you have removed lot of strings) it might be
better to rebuild it from scratch:

.. code-block:: sh

    ./manage.py rebuild_index --clean

.. seealso:: 
   
   :djadmin:`rebuild_index`

.. _faq-ft-lock:

I get "Lock Error" quite often while translating
------------------------------------------------

This is usually caused by concurrent updates to fulltext index. In case you are
running multi threaded server (eg. mod_wsgi), this happens quite often. For such
setup it is recommended to enable :setting:`OFFLOAD_INDEXING`.

.. seealso:: 
   
   :ref:`fulltext`

.. _faq-ft-space:

Rebuilding index has failed with "No space left on device"
----------------------------------------------------------

Whoosh uses temporary directory to build indices. In case you have small /tmp
(eg. using ramdisk), this might fail. Change used temporary directory by passing
as ``TEMP`` variable:

.. code-block:: sh

    TEMP=/path/to/big/temp ./manage.py rebuild_index --clean

.. seealso:: 
   
   :djadmin:`rebuild_index`


Database operations fail with "too many SQL variables"
------------------------------------------------------

This can happen with SQLite database as it is not powerful enough for some
relations used within Weblate. The only way to fix this is to use some more
capable database, see :ref:`production-database` for more information.

.. seealso:: 
   
   :ref:`production-database`, `Django's databases <https://docs.djangoproject.com/en/stable/ref/databases/>`_

Features
++++++++

.. _faq-vcs:

Does Weblate support other VCS than Git and Mercurial?
------------------------------------------------------

Weblate currently does not have native support for anything else than
:ref:`vcs-git` (with extended support for :ref:`vcs-github`) and
:ref:`vcs-mercurial`, but it is possible to write backends for other VCSes.

You can also use :ref:`vcs-git-helpers` in Git to access other VCSes.


.. note::

    For native support of other VCS, Weblate requires distributed VCS and could
    be probably adjusted to work with anything else than Git and Mercurial, but
    somebody has to implement this support.

.. seealso:: :ref:`vcs`

How does Weblate credit translators?
------------------------------------

Every change made in Weblate is committed into VCS under translators name. This
way every single change has proper authorship and you can track it down using
standard VCS tools you use for code.

Additionally, when translation file format supports it, the file headers are
updated to include translator name.

Why does Weblate force to have show all po files in single tree?
----------------------------------------------------------------

Weblate was designed in a way that every po file is represented as single
component. This is beneficial for translators, that they know what they are
actually translating. If you feel your project should be translated as one,
consider merging these po files. It will make life easier even for translators
not using Weblate.

.. note::

    In case there will be big demand for this feature, it might be implemented
    in future versions, but it's definitely not a priority for now.
