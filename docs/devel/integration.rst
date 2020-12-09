Integrating with Weblate
========================

.. include:: /snippets/basics.rst


Getting translations updates from Weblate
+++++++++++++++++++++++++++++++++++++++++

To fetch updated strings from Weblate you can simply fetch the underlying
repository (either from filesystem or it can be made available through
:ref:`git-exporter`). Prior to this, you might want to commit any pending
changes (see :ref:`lazy-commit`). This can be achieved in the user interface
(in the :guilabel:`Repository maintenance`) or from command line using :ref:`wlc`.

This can be automated if you grant Weblate push access to your repository and
configure :ref:`component-push` in the :ref:`component`.

.. seealso::

    :ref:`continuous-translation`

Pushing string changes to Weblate
+++++++++++++++++++++++++++++++++

To push newly updated strings to Weblate, just let it pull from the upstream
repository. This can be achieved in the user interface (in the :guilabel:`Repository
maintenance`) or from command line using :ref:`wlc`.

This can be automated by installing a webhook on your repository to trigger
Weblate whenever there is a new commit, see :ref:`update-vcs` for more details.

.. seealso::

    :ref:`continuous-translation`
