.. _addons:

Addons
======

.. versionadded:: 2.19

Addons provide ways to customize translation workflow. You can install addons
to your translation component and they will work behind the scenes.

.. image:: ../images/addons.png

Built in addons
+++++++++++++++

Cleanup translation files
-------------------------

Update all translation files to match the monolingual base file. In most file
formats this means removing stale translation keys which are no longer present
in the base file.

Flag new source strings to need edit
------------------------------------

Whenever a new source string is imported from the VCS, it is flagged as needing
editing in Weblate. This way you can easily filter and edit source strings
written by the developers.

Flag new translations to need edit
----------------------------------

Whenever a new translation unit is imported from the VCS, it is flagged as
needing editing in Weblate. This way you can easily filter and edit
translations created by the developers.

Statistics generator
--------------------

This addon generates file with detailed information about the translation.

Update ALL_LINGUAS variable in the configure file
-------------------------------------------------

Updates the ALL_LINGUAS variable in configure, configure.in or configure.ac
files when adding new translation.

Update LINGUAS file
-------------------

Updates the LINGUAS file when adding new translation.

Generate mo files
-----------------

Automatically generates mo file for every changed po file.

Update po files to match pot (msgmerge)
---------------------------------------

Update all po files to match the pot file using msgmerge. This is triggered
whenever new changes are pulled from upstream repository.

Formats the Java properties translation
---------------------------------------

This addon sorts the Java properties file.

Writing addon
+++++++++++++

You can write own addons as well, all you need to do is subclass ``BaseAddon``,
define addon metadata and implement callback which will do the processing.

You can look at example addon for more information:

.. literalinclude:: ../../weblate/addons/example.py
    :language: python
