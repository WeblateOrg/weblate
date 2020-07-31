Downloading and uploading translations
======================================

You can export files from a translation, make changes, and import them again. This allows
working offline, and then merging changes back into the existing translation.
This works even if it has been changed in the meantime.

.. note::

    The available options might be limited by :ref:`privileges`.

Downloading translations
------------------------

From the project or component dashboard, translatable files can be downloaded
using the :guilabel:`Download original translation file` in the :guilabel:`Files`
menu, producing a copy of the original file as it is stored in the upstream
Version Control System.

You can also download the translation converted into one of widely used
localization formats. The converted files will be enriched with data
provided in Weblate such as additional context, comments or flags.

Several file formats are available, including a compiled file
to use in your choice of application (for example ``.mo`` files for GNU Gettext) using
the :guilabel:`Files` menu.

Uploading translations
----------------------

When you have made your changes, use :guilabel:`Upload translation`
in the :guilabel:`Files` menu.

.. image:: /images/export-import.png

.. _upload-file:

Supported file formats
++++++++++++++++++++++

Any file in a supported file format can be uploaded, but it is still
recommended to use the same file format as the one used for translation, otherwise some
features might not be translated properly.

.. seealso::

   :ref:`formats`

The uploaded file is merged to update the translation, overwriting existing
entries by default (this can be turned off or on in the upload dialog).

.. _upload-method:

Import methods
++++++++++++++

These are the choices presented when uploading translation files:

Add as translation (``translate``)
    Imported translations are added as translations. This is the most common usecase, and
    the default behavior.
Add as suggestion (``suggest``)
    Imported translations are added as suggestions, do this when you want to have your
    uploaded strings reviewed.
Add as translation needing edit (``fuzzy``)
    Imported translations are added as translations needing edit. This can be useful
    when you want translations to be used, but also reviewed.
Replace existing translation file (``replace``)
    Existing file is replaced with new content. This can lead to loss of existing
    translations, use with caution.
Update source strings (``source``)
    Updates source strings in bilingual translation file. This is similar to
    what :ref:`addon-weblate.gettext.msgmerge` does.

.. seealso::

   :http:post:`/api/translations/(string:project)/(string:component)/(string:language)/file/`

.. _upload-conflicts:

Conflicts handling
++++++++++++++++++

Defines how to deal with uploaded strings which are already translated.

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
