Administration
==============

Administration of Weblate is done through standard Django admin interface,
which is available under :file:`/admin/` URL.

.. _voting:

Suggestion voting
-----------------

.. versionadded:: 1.6
    This feature is available since Weblate 1.6.

In default Weblate setup, everybody can add suggestions and logged in users can
accept them. You might however want to have more eyes on the translation and
require more people to accept them. This can be achieved by suggestion voting.
You can enable this on :ref:`subproject` configuration by 
:guilabel:`Suggestion voting` and :guilabel:`Autoaccept suggestions`. The first
one enables voting feature, while the latter allows you to configure threshold
at which suggestion will gets automatically accepted (this includes own vote from
suggesting user).

.. note::

    Once you enable automatic accepting, normal users lose privilege to
    directly save translations or accept suggestions. This can be overriden
    by :guilabel:`Can override suggestion state` privilege
    (see :ref:`privileges`).

You can combine these with :ref:`privileges` into one of following setups:

* Users can suggest and vote for suggestions, limited group controls what is
  accepted - enable voting but not automatic accepting and remove privilege
  from users to save translations.
* Users can suggest and vote for suggestions, which get automatically accepted
  once defined number of users agree on this - enable voting and set desired 
  number of votes for automatic accepting.
* Optional voting for suggestions - you can also only enable voting and in 
  this case it can be optionally used by users when they are not sure about 
  translation (they can suggest more of them).

.. _lazy-commit:

Lazy commits
------------

Default behaviour (configured by :setting:`LAZY_COMMITS`) of Weblate is to group
commits from same author into one if possible. This heavily reduces number of
commits, however you might need to explicitly tell to do the commits in case
you want to get Git repository in sync, eg. for merge (this is by default
allowed for Managers group, see :ref:`privileges`).

The changes are in this mode committed once any of following conditions is
fulfilled:

* somebody else works on the translation
* merge from upstream occurs
* import of translation happens
* translation for a language is completed
* explicit commit is requested

You can also additionally set a cron job to commit pending changes after some
delay, see :djadmin:`commit_pending`.

.. _fulltext:

Fulltext search
---------------

Fulltext search is based on Whoosh. You can either allow Weblate to directly
update index on every change to content or offload this to separate process by 
:setting:`OFFLOAD_INDEXING`.

The first approach (immediate updates) allows more up to date index, but
suffers locking issues in some setup (eg. Apache's mod_wsgi) and produces more
fragmented index.

Offloaded indexing is always better choice for production setup - it only marks
which items need to be reindexed and you need to schedule background process 
(:djadmin:`update_index`) to update index. This leads to faster response of the
site and less fragmented index with cost that it might be slightly outdated.

.. seealso:: :djadmin:`update_index`, :setting:`OFFLOAD_INDEXING`, :ref:`faq-ft-slow`, :ref:`faq-ft-lock`, :ref:`faq-ft-space`

.. _locking:

Translation locking
-------------------

To improve collaboration, it is good to prevent duplicate effort on
translation. To achieve this, translation can be locked for single translator.
This can be either done manually on translation page or is done automatically
when somebody starts to work on translation. The automatic locking needs to be
enabled using :setting:`AUTO_LOCK`.

The automatic lock is valid for :setting:`AUTO_LOCK_TIME` seconds and is
automatically extended on every translation made and while user has opened
translation page.

User can also explicitly lock translation for :setting:`LOCK_TIME` seconds.
