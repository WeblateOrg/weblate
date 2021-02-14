Integrating with Weblate
========================

.. include:: /snippets/basics.rst

Importing localization project into Weblate
+++++++++++++++++++++++++++++++++++++++++++

Weblate has been developed with VCS integration in mind as it’s core feature, so the easiest way is
to grant Weblate the access to your repository.
The import process will guide you through configuring your translations into components.

Alternatively, you can use Weblate to set up a local repository containing
all the translations without integration.

.. seealso::

   :ref:`adding-projects`,
   :ref:`faq-submodule`

Fetching updated translations from Weblate
++++++++++++++++++++++++++++++++++++++++++

To fetch updated strings from Weblate, you can simply fetch the underlying Git
repository (either from filesystem, or it can be made available through
:ref:`git-exporter`). Prior to this, you might want to commit any pending
changes (see :ref:`lazy-commit`). You can do so in the user interface
(in the :guilabel:`Repository maintenance`) or from the command line using :ref:`wlc`.

This can be automated if you grant Weblate push access to your repository and
configure :ref:`component-push` in the :ref:`component`, see :ref:`push-changes`.

Alternatively, you can use :doc:`/api` to update translations
to match their latest version.

.. seealso::

    :ref:`continuous-translation`,
    :ref:`push-changes`,
    :ref:`vcs-repos`

Fetching remote changes into Weblate
++++++++++++++++++++++++++++++++++++

To fetch the strings newly updated in your repository into Weblate, just let it pull from the upstream
repository. This can be achieved in the user interface (in the :guilabel:`Repository
maintenance`), or from the command line using :ref:`wlc`.

This can be automated by setting a webhook in your repository to trigger
Weblate whenever there is a new commit, see :ref:`update-vcs` for more details.

If you’re not using a VCS integration, you can use UI or :doc:`/api` to update
translations to match your code base.

.. seealso::

    :ref:`continuous-translation`,
    :ref:`vcs-repos`

.. _adding-new-strings:

Adding new strings
++++++++++++++++++

In case your translation files are stored in a VCS together with the code,
you most likely have an existing workflow for developers to introduce new strings.
Any way of adding strings will be picked up, but consider using
:ref:`source-quality-gateway` to avoid introducing errors.

When the translation files are separate from the code, there are following ways to introduce
new strings into Weblate.

* Manually, using :guilabel:`Add new translation string` from :guilabel:`Tools`
  menu in the language used as the source for translations.
* Programatically, using API :http:post:`/api/translations/(string:project)/(string:component)/(string:language)/units/`.
* By uploading source file as :guilabel:`Replace existing translation file`
  (this overwrites existing strings, so please make sure the file includes both
  old and new strings) or :guilabel:`Add new strings`, see :ref:`upload-method`.

.. note::

   Availability of adding strings in Weblate depends on :ref:`component-manage_units`.

.. _updating-target-files:

Updating target language files
++++++++++++++++++++++++++++++

For monolingual files (see :ref:`formats`) Weblate might add new translation
strings not present in the :ref:`component-template`, and not in actual
translations. It does not however perform any automatic cleanup of stale
strings as that might have unexpected outcomes. If you want to do this, please
install :ref:`addon-weblate.cleanup.generic` addon which will handle the
cleanup according to your requirements.

Weblate also will not try to update bilingual files in any way, so if you need
:file:`po` files being updated from :file:`pot`, you need to do it yourself
using :guilabel:`Update source strings` :ref:`upload-method` or using
:ref:`addon-weblate.gettext.msgmerge` addon.

.. seealso::

   :ref:`processing`,
   :ref:`addon-weblate.cleanup.generic`,
   :ref:`addon-weblate.cleanup.blank`,
   :ref:`addon-weblate.resx.update`,
   :ref:`addon-weblate.gettext.msgmerge`
