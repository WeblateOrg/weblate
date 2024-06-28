.. _gettext:

GNU gettext PO (Portable Object)
--------------------------------

.. index::
    pair: gettext; file format
    pair: PO; file format

Most widely used format for translating libre software.

Contextual info stored in the file is supported by adjusting its
headers or linking to corresponding source files.

.. seealso::

    :doc:`../devel/gettext`,
    :doc:`../devel/sphinx`,
    `Gettext on Wikipedia <https://en.wikipedia.org/wiki/Gettext>`_,
    :doc:`tt:formats/po`,
    :ref:`addon-weblate.gettext.authors`,
    :ref:`addon-weblate.gettext.configure`,
    :ref:`addon-weblate.gettext.customize`,
    :ref:`addon-weblate.gettext.linguas`,
    :ref:`addon-weblate.gettext.mo`,
    :ref:`addon-weblate.gettext.msgmerge`

Showing source string change
++++++++++++++++++++++++++++

Weblate can extract previous source strings from the PO files if present and
show the string difference for strings needing editing based on that. To
include these, :program:`msgmerge` has to be executed with ``--previous`` and
the resulting PO file then contains lines such as:

.. code-block:: po

   #, fuzzy
   #| msgid "previous-untranslated-string"
   msgid "untranslated-string"
   msgstr "translated-string"

PO file header
++++++++++++++

The header of the PO file is automatically maintained by Weblate. Optionally it
can include :ref:`component-report_source_bugs` and
:ref:`project-set_language_team`.

.. _mono_gettext:

Monolingual gettext
+++++++++++++++++++

Some projects decide to use gettext as monolingual formats—they code just the IDs
in their source code and the string then needs to be translated to all languages,
including English. This is supported, though you have to choose
this file format explicitly when importing components into Weblate.

Example files
+++++++++++++

The bilingual gettext PO file typically looks like this:

.. code-block:: po

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "Monday"
    msgstr "Pondělí"

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "Tuesday"
    msgstr "Úterý"

    #: weblate/accounts/avatar.py:163
    msgctxt "No known user"
    msgid "None"
    msgstr "Žádný"

The monolingual gettext PO file typically looks like this:

.. code-block:: po

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "day-monday"
    msgstr "Pondělí"

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "day-tuesday"
    msgstr "Úterý"

    #: weblate/accounts/avatar.py:163
    msgid "none-user"
    msgstr "Žádný"

While the base language file will be:

.. code-block:: po

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "day-monday"
    msgstr "Monday"

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "day-tuesday"
    msgstr "Tuesday"

    #: weblate/accounts/avatar.py:163
    msgid "none-user"
    msgstr "None"


Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` for bilingual gettext            |
+================================+==================================+
| File mask                      | ``po/*.po``                      |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Template for new translations  | ``po/messages.pot``              |
+--------------------------------+----------------------------------+
| File format                    | `Gettext PO file`                |
+--------------------------------+----------------------------------+

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` for monolingual gettext          |
+================================+==================================+
| File mask                      | ``po/*.po``                      |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``po/en.po``                     |
+--------------------------------+----------------------------------+
| Template for new translations  | ``po/messages.pot``              |
+--------------------------------+----------------------------------+
| File format                    | `Gettext PO file (monolingual)`  |
+--------------------------------+----------------------------------+
