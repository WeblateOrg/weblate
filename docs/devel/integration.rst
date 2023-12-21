Integrating with Weblate
========================

.. include:: /snippets/basics.rst

Importing localization projects into Weblate
++++++++++++++++++++++++++++++++++++++++++++

The most automated of maintaining integration with a remote
version-control repository is to grant Weblate access to it.
The import process guides you through configuring and splitting up your
translation effort into Weblate components.

Alternatively, you can use Weblate without any integration, where
a local repository contains all translations.

.. seealso::

   :ref:`adding-projects`,
   :ref:`faq-submodule`

Fetching updated translations from Weblate
++++++++++++++++++++++++++++++++++++++++++

Weblate stores updated strings in a database and commits them to a local
version-control repository. You can add a Weblate repository (when
:ref:`git-exporter` is turned on) as an additional remote repository
and fetch translation updates from it.

Prior to this, you might want to commit any pending local
changes made in Weblate (see :ref:`lazy-commit`). This can be done from the user interface
(in the :guilabel:`Repository maintenance`), or from the command-line using :ref:`wlc`.

Pushing changes can be automated if you grant Weblate push access to your repository and
configure :ref:`component-push` in the :ref:`component`, see :ref:`push-changes`.

Alternatively, use :doc:`/api` to update translations
so that they match the latest version from upstream in your remote VCS repository.

.. seealso::

    :ref:`continuous-translation`,
    :ref:`push-changes`,
    :ref:`vcs-repos`

Fetching remote changes into Weblate
++++++++++++++++++++++++++++++++++++

To fetch any strings recently updated in your remote VCS repository into Weblate,
allow Weblate pull from the upstream repository.
This can be achieved in the user interface (in the :guilabel:`Repository maintenance`),
or from the command-line using :ref:`wlc`.

This can be automated by setting a webhook in your repository to trigger
Weblate whenever there is a new commit. See :ref:`update-vcs` for more details.

If not using VCS integration, you can use the UI or :doc:`/api` to update
the translations so that they match your codebase.

.. seealso::

    :ref:`continuous-translation`,
    :ref:`vcs-repos`

.. _adding-new-strings:

Adding new strings
++++++++++++++++++

If your translation files are stored in a remote VCS together with the code,
you most likely have an existing workflow for developers to introduce new strings.
Any way of adding strings will be picked up, but consider using
:ref:`source-quality-gateway` to avoid introducing errors.

When translation files are separated from the code, the following ways can
introduce new strings into Weblate.

* Manually, using :guilabel:`Add new translation string` from :guilabel:`Tools`
  menu in the source language.
* Programmatically, using the API :http:post:`/api/translations/(string:project)/(string:component)/(string:language)/units/`.
* By uploading source file as :guilabel:`Replace existing translation file`
  (this overwrites existing strings, so please ensure the file includes both
  old and new strings) or :guilabel:`Add new strings`, see :ref:`upload-method`.

.. note::

   The ability to add strings in Weblate requires :ref:`component-manage_units`.

.. _updating-target-files:

Updating target-language files
++++++++++++++++++++++++++++++

For monolingual files (see :ref:`formats`) Weblate might add new translation
strings not present in the :ref:`component-template`, or other translations.
It does not however perform any automatic cleanup of stale strings, as that
might have unexpected results. If you still want to do this, please install
the :ref:`addon-weblate.cleanup.generic` add-on, which handles
cleanup according to your requirements.

Weblate will also not try to update bilingual files in any way, so if you need
:file:`po` files to be updated from :file:`pot`, do it yourself by
using :guilabel:`Update source strings` :ref:`upload-method`, or by using
the :ref:`addon-weblate.gettext.msgmerge` add-on.

.. seealso::

   :ref:`processing`,
   :ref:`addon-weblate.cleanup.generic`,
   :ref:`addon-weblate.cleanup.blank`,
   :ref:`addon-weblate.resx.update`,
   :ref:`addon-weblate.gettext.msgmerge`


.. _translations-update:

Introducing new strings
+++++++++++++++++++++++

You can add new strings in Weblate with :ref:`component-manage_units` turned
on, but it is usually better to introduce new strings together with the code
changes that introduced them.

Monolingual formats need to be configured so that new strings are added to
:ref:`component-template`. This is typically done by developers as they
develop the code. You might want to introduce review of those strings using
:ref:`source-quality-gateway`.

Bilingual formats typically extract strings from the source code using some
tooling (like :program:`xgettext` or :program:`intltool-update`). Follow your
localization framework documentation for instructions how to do that. Once the
strings are extracted, there might be an additional step needed to update
existing translations, see :ref:`updating-target-files`.

.. hint::

   Automating string extraction is presently out of scope for Weblate. It
   typically involves executing untrusted code what makes it more suitable for
   a generic continuous integration than localization-specific platform.

   You might want to integrate this into your continuous integration pipelines
   to make new strings automatically appear for translation. Such pipeline
   should also cover :ref:`avoid-merge-conflicts`.

.. seealso::

   :ref:`updating-target-files`,
   :doc:`/devel/gettext`,
   :doc:`/devel/sphinx`

.. _manage-vcs:

Managing the local VCS repository
+++++++++++++++++++++++++++++++++

Weblate stores all translations a version control repository of its own.
It can either be connected to a remote one, or it can remain internal only.
The :guilabel:`Repository maintenance` allows manipulating the repository.

.. hint::

   With :doc:`/admin/continuous` any changes are auto-pushed from the
   repository, and there is usually no need to manually manipulate it.

.. image:: /screenshots/component-repository.webp

.. seealso::

   :doc:`/admin/continuous`,
   :doc:`/vcs`
