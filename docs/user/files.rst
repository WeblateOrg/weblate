Downloading and uploading translations
======================================

You can export files from a translation, make changes, and import them again. This allows
working offline, and then merging changes back into the existing translation.
This works even if it has been changed in the meantime.

.. note::

    The available options might be limited by :ref:`privileges`.

Downloading translations
------------------------

From the project or component dashboard, translatable files can be downloaded using the :guilabel:`Download source file`
in the :guilabel:`Files` menu, producing a copy of the file as it is stored
in the upstream Version Control System.

You can either download the original file as is or converted into one of widely
used localization formats. The converted files will be enriched with data
provided in Weblate such as additional context, comments or flags.

Several file formats are available, including a compiled file
to use in your choice of application (for example ``.mo`` files for GNU Gettext) using
the :guilabel:`Files` menu.

Uploading translations
----------------------

When you have made your changes, use :guilabel:`Upload translation`
in the :guilabel:`Files` menu.

Any file in a supported file format can be uploaded, but it is still
recommended to use the same file format as the one used for translation, otherwise some
features might not be translated properly.

.. seealso:: 
   
   :ref:`formats`

The uploaded file is merged to update the translation, overwriting existing
entries by default (this can be turned off or on in the upload dialog).

Import methods
++++++++++++++

These are the choices presented when uploading translation files:

Add as translation
    Imported translations are added as translations. This is the most common usecase, and
    the default behavior.
Add as suggestion
    Imported translations are added as suggestions, do this when you want to have your
    uploaded strings reviewed.
Add as translation needing edit
    Imported translations are added as translations needing edit. This can be useful
    when you want translations to be used, but also reviewed.
Replace existing translation file
    Existing file is replaced with new content. This can lead to loss of existing
    translations, use with caution.

There is also an option for how to handle strings needing edit in the imported
file. Such strings can be handle in one of the three following ways: "Do not import", "Import as string needing edit", or "Import as translated".

.. image:: /images/export-import.png
