Integrating with Weblate
========================

.. include:: /snippets/basics.rst

Importing localization project into Weblate
+++++++++++++++++++++++++++++++++++++++++++

You can either use a version-control system to hold your translations,
by granting Weblate access to it, and letting it guide you through configuring your
components and translations.

Alternatively, you can use Weblate to set up a local repository containing all the
translations.

.. seealso::

   :ref:`adding-projects`,
   :ref:`faq-submodule`

Send string changes to Weblate
++++++++++++++++++++++++++++++

Your Weblate project should already be set up to pull changes from the upstream
repository. If not, it can be done in the user interface
(in the :guilabel:`Repository maintenance`) or from the command-line
using :ref:`wlc`.

This can be automated by installing a webhook on your repository to trigger
Weblate whenever there is a new commit, see :ref:`update-vcs` for more details.

Alternateively, you can use the UI or :doc:`/api` to update translations
to match the latest version of what it is you want to translate.

.. seealso::

    :ref:`continuous-translation`
    
Fetch changes made in Weblate
+++++++++++++++++++++++++++++

Weblate represents a branch from your version-control system upstream that
you can fetch changed strings from just like any other.

Either fetch the filesystem, or use :ref:`git-exporter`. Commit any pending
changes first (see :ref:`lazy-commit`) from the user interface
(in the :guilabel:`Repository maintenance`) or from the command-line
using :ref:`wlc`.

Automation is possible by granting the Weblate user (available for various
code-hosting websites) push access to your repository and configuring
:ref:`component-push` in the :ref:`component`.

.. seealso::

    :ref:`continuous-translation`

Adding new strings
++++++++++++++++++

In case your translation files are stored in a version-control system together with the code,
you most likely have an existing workflow for developers to introduce new strings.
Any way of adding strings will be picked up, but consider using
:ref:`source-quality-gateway` to avoid also introducing errors.

When the translation files are not in a upstream repository, there needs to be a way to introduce
new strings.

* Manually, using :guilabel:`Add new translation string` from :guilabel:`Tools`
  menu on the translation language used as the source for others.
  (Only works for monolingual translations :ref:`bimono`)
* Alternatively, you can use the API
  :http:post:`/api/translations/(string:project)/(string:component)/(string:language)/units/`.
  (Only works for monolingual translations :ref:`bimono`)
* It is also possible to just upload a new source file as
  :guilabel:`Replace existing translation file`
  (this overwrites existing strings, so make sure the file includes both old
  and new ones, see :ref:`upload-method`).
  
