Managing translations
=====================

.. _adding-translation:

Adding new translations
-----------------------

Weblate can add new translations to your translation components when configured
:guilabel:`Template for new translations` (see :ref:`component`) or your file
format doesn't require it (for most of monolingual files it is okay to start
with blank files).

Weblate can be configured to automatically add translation when requested by
user or to send notification to project admins for approval and manual
processing. This can be done using :guilabel:`New translation` in
:ref:`component`. The project admins can still start translation within Weblate
even if contact form is shown for regular users.

Alternatively you can add the files manually to the VCS. Weblate will
automatically detect new languages which are added to the VCS repository and
makes them available for translation. This makes adding new translations
incredibly easy:

1. Add the translation file to VCS.
2. Let Weblate update the repository (usually set up automatically, see
   :ref:`update-vcs`).

