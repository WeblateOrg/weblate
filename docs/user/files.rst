Downloading and uploading translations
======================================

You can export files from a translation, make changes, and import them again. This allows
working offline, and then merging changes back into the existing translation.
This works even if it has been changed in the meantime.

.. note::

    Available options might be limited by
    :ref:`access control <access-control>` settings.

.. _download:

Downloading translations
------------------------

From the project or component dashboard, translatable files can be downloaded
in the :guilabel:`Files` menu.

The first option is to download the file in the original format as it is stored in the
repository. In this case, any pending changes in the translation are getting committed
and the up-to-date file is yield without any conversions.

You can also download the translation converted into one of the widely used
localization formats. The converted files will be enriched with data provided
in Weblate; such as additional context, comments or flags. Several file formats
are available via the :guilabel:`Files` ↓ :guilabel:`Customize download` menu:

* gettext PO (``po``)
* XLIFF 1.1 with gettext extensions (``xliff``)
* XLIFF 1.1 (``xliff11``)
* TermBase eXchange (``tbx``)
* Translation Memory eXchange (``tmx``)
* gettext MO (only available when translation is using gettext PO) (``mo``)
* CSV (``csv``)
* Excel Open XML (``xlsx``)
* JSON (only available for monolingual translations) (``json``)
* JSON nested structure file (only available for monolingual translations) (``json-nested``)
* Android String Resource (only available for monolingual translations) (``aresource``)
* iOS strings (only available for monolingual translations) (``strings``)

.. hint::

   The content available in the converted files differs based on file format
   features, you can find overview in :ref:`fmt_capabs`.

.. image:: /screenshots/file-download.webp

.. seealso::

   :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/file/`,
   :setting:`WEBLATE_EXPORTERS`

.. _download-multi:

Downloading components, categories or projects
----------------------------------------------

Translation files for a component, category or project can be downloaded at
once via the :guilabel:`Files` menu. The download is always served as a ZIP
file, and you can choose original or converted formats similarly as in
:ref:`download`.

.. seealso::

   :http:get:`/api/components/(string:project)/(string:component)/file/`

.. _upload:

Uploading translations
----------------------

When you have made your changes, use :guilabel:`Upload translation`
in the :guilabel:`Files` menu.

.. image:: /screenshots/file-upload.webp

.. _upload-file:

Supported file formats
++++++++++++++++++++++

Any file in a supported file format can be uploaded, but it is still
recommended to use the same file format as the one used for translation, otherwise some
features might not be translated properly.

.. seealso::

   :ref:`formats`,
   :doc:`/user/files`

.. _upload-method:

Import methods
++++++++++++++

These are the choices presented when uploading translation files:

Add as translation (``translate``)
    Imported strings are added as translations to existing strings. This is the most common usecase, and
    the default behavior.

    Only translations are used from the uploaded file and no additional content.

    This option is available only if the user has the :ref:`"Edit strings" permission <privileges>`.
Add as suggestion (``suggest``)
    Imported strings are added as suggestions. Do this when you want to have your
    uploaded strings reviewed.

    Only translations are used from the uploaded file and no additional content.

    This option is available only if the user has the :ref:`"Add suggestion" permission <privileges>`.
Add as approved translation (``approve``)
    Imported strings are added as approved translations. Do this when you already
    reviewed your translations before uploading them.

    Only translations are used from the uploaded file and no additional content.

    This option is available only if the user has the :ref:`"Review strings" permission <privileges>`.
Add as translation needing edit (``fuzzy``)
    Imported strings are added as translations needing edit. This can be useful
    when you want translations to be used, but also reviewed.

    Only translations are used from the uploaded file and no additional content.

    This option is available only if the user has the :ref:`"Edit strings" permission <privileges>`.
Replace existing translation file (``replace``)
    Existing file is replaced with new content. This can lead to loss of existing
    translations, use with caution.

    This option is available only if the user has the
    :ref:`"Edit component settings" permission or "Add new string", "Remove a string" and "Edit strings" permissions <privileges>`.
Update source strings (``source``)
    Updates source strings in bilingual translation file. This is similar to
    what :ref:`addon-weblate.gettext.msgmerge` does.

    This option is available only for some file formats and only if the user has the
    :ref:`"Upload translations" permission <privileges>`.
Add new strings (``add``)
    Adds new strings to the translation. It skips the one which already exist.

    In case you want to both add new strings and update existing translations,
    upload the file second time with :guilabel:`Add as translation`.

    Only source, translation and key (context) are used from the uploaded file.

    This option is available only with :ref:`component-manage_units` turned on
    and only if the user has the :ref:`"Add new string" permission <privileges>`.

.. seealso::

   :http:post:`/api/translations/(string:project)/(string:component)/(string:language)/file/`

.. _upload-conflicts:

Conflicts handling
++++++++++++++++++

Defines how to deal with uploaded strings which are already translated:

Change only untranslated strings (``ignore``)
   Ignore uploaded translations which are already translated.
Change translated strings (``replace-translated``)
   Replace existing translations with uploaded ones, but keep approved ones.
Change translated and approved strings (``replace-approved``)
   Replace existing translations with uploaded ones, including approved ones.

.. _upload-fuzzy:

Strings needing edit
++++++++++++++++++++

There is also an option for how to handle strings needing edit in the imported
file. Such strings can be handle in one of the three following ways: "Do not
import", "Import as string needing edit", or "Import as translated".

.. _upload-author-name:
.. _upload-author-email:

Overriding authorship
+++++++++++++++++++++

With admin permissions, you can also specify authorship of uploaded file. This
can be useful in case you've received the file in another way and want to merge
it into existing translations while properly crediting the actual author.
