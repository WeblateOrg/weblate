.. _formats:

Supported formats
=================

Weblate supports any format understood by Translate-toolkit, however each
format being slightly different, there might be some issues with not well
tested formats.

.. seealso:: `Supported formats in translate-toolkit`_

GNU Gettext
-----------

Most widely used format in translating free software. This was first format
supported by Weblate and still has best support.

Weblate supports contextual information stored in the file, adjusting it's
headers or linking to corresponding source files.

.. seealso:: https://en.wikipedia.org/wiki/Gettext

Monolingual Gettext
+++++++++++++++++++

Some projects decide to use Gettext as monolingual formats - they code just IDs
in their source code and the string needs to be translated to all languages,
including English. Weblate does support this, though you have to choose explicitely
this file format when importing resources into Weblate.

XLIFF
-----

XML based format created to standardize translation files, but in the end it
is one of many standards in this area.

.. seealso:: https://en.wikipedia.org/wiki/XLIFF

Java properties
---------------

Native Java format for translations.

.. seealso:: https://en.wikipedia.org/wiki/.properties

Qt Linguist .ts
---------------

Translation format used in Qt based applications.

.. seealso:: http://qt-project.org/doc/qt-4.8/linguist-manual.html

Android string resources
------------------------

Android specific file format for translating applications.

.. seealso:: https://developer.android.com/guide/topics/resources/string-resource.html

.. note::

    This format is not yet supported by Translate-toolkit (merge request is
    pending), but Weblate includes own support for it.

Apple OS X strings
------------------

Apple specific file format for translating applications, used for both OS X
and iPhone/iPad application translations.

.. seealso:: https://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPInternational/Articles/StringsFiles.html

.. note::

    Apple OS X strings are half broken in translate-toolkit 1.9.0 (it will
    generate corrupted files while saving), please use Git snapshot for
    handling these.

PHP files
---------

PHP files can be processed directly, though currently Translate-toolkit has
some problems writing them properly, so please double check that your files
won't get corrupted.

Sample file which should work:

.. code-block:: php

    <?php

    $string['foo'] = 'This is foo string';


Others
------

As already mentioned, all Translate-toolkit formats are supported, but they
did not (yet) receive deeper testing.

.. seealso:: `Supported formats in translate-toolkit`_
   
.. _Supported formats in translate-toolkit: http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/index.html
