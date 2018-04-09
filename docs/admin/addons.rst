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

Update all translation files to match the monolingual base file. For most file
formats, this means removing stale translation keys no longer present in the
base file.

Component discovery
-------------------

This addon automatically adds or removes components to the project based on
file changes in the version control system.

Flag new source strings to need edit
------------------------------------

Whenever a new source string is imported from the VCS, it is flagged as needing
editing in Weblate. This way you can easily filter and edit source strings
written by the developers.

Flag new translations to need edit
----------------------------------

Whenever a new translation string is imported from the VCS, it is flagged as
needing editing in Weblate. This way you can easily filter and edit
translations created by the developers.

Statistics generator
--------------------

This addon generates a file containing detailed information about the
translation.

Update ALL_LINGUAS variable in the configure file
-------------------------------------------------

Updates the ALL_LINGUAS variable in configure, configure.in or configure.ac
files when adding new translation.

Customize gettext output
------------------------

Allows customization of gettext output behavior, for example line wrapping.

Update LINGUAS file
-------------------

Updates the LINGUAS file when adding new translation.

Generate MO files
-----------------

Automatically generates MO file for every changed PO file.

Update po files to match pot (msgmerge)
---------------------------------------

Update all PO files to match the POT file using msgmerge. This is triggered
whenever new changes are pulled from the upstream repository.

Customize JSON output
---------------------

Allows to customize JSON output behavior, for example indentation or sorting.

Formats the Java properties file
--------------------------------

This addon sorts the Java properties file.


Writing addon
+++++++++++++

You can write own addons as well, all you need to do is subclass ``BaseAddon``,
define addon metadata and implement callback which will do the processing.

You can look at example addon for more information:

.. literalinclude:: ../../weblate/addons/example.py
    :language: python
