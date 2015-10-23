Managing translations
=====================

.. _adding-translation:

Adding new translations
-----------------------

Weblate can add new language files to your project automatically for most of
the :ref:`formats`. This feature needs to be enabled in the :ref:`component`.
In case this is not enabled (or available for your file format) the files have
to be added manually to the VCS.

Weblate will automatically detect new languages which are added to the VCS
repository and makes them available for translation. This makes adding new
translations incredibly easy:

1. Add the translation file to VCS.
2. Let Weblate update the repository (usually set up automatically, see
   :ref:`update-vcs`).
