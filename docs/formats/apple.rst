.. _apple:

Apple iOS strings
-----------------

.. index::
    pair: Apple strings; file format

File format typically used for translating Apple :index:`iOS <pair: iOS;
translation>` applications, but also standardized by PWG 5100.13 and used on
NeXTSTEP/OpenSTEP.

Apple iOS strings are usually used as monolingual.

.. seealso::

    :ref:`stringsdict`,
    `Apple "strings files" documentation <https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPInternational/MaintaingYourOwnStringsFiles/MaintaingYourOwnStringsFiles.html>`_,
    `Message Catalog File Format in PWG 5100.13 <http://ftp.pwg.org/pub/pwg/candidates/cs-ippjobprinterext3v10-20120727-5100.13.pdf#page=66>`_,
    :doc:`tt:formats/strings`

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                              |
+================================+==============================================+
| File mask                      |``Resources/*.lproj/Localizable.strings``     |
+--------------------------------+----------------------------------------------+
| Monolingual base language file |``Resources/en.lproj/Localizable.strings`` or |
|                                |``Resources/Base.lproj/Localizable.strings``  |
+--------------------------------+----------------------------------------------+
| Template for new translations  | `Empty`                                      |
+--------------------------------+----------------------------------------------+
| File format                    | `iOS Strings (UTF-8)`                        |
+--------------------------------+----------------------------------------------+
