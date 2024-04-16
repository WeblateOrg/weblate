.. _fluent:

Fluent format
-------------

.. versionadded:: 4.8

.. include:: /snippets/format-in-development.rst

Fluent is a monolingual text format that focuses on asymmetric localization: a
simple string in one language can map to a complex multi-variant translation in
another language.


.. seealso::


   `Project Fluent website <https://projectfluent.org/>`_

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.ftl

Weblate configuration
+++++++++++++++++++++

+-----------------------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                                  |
+================================+==================================================+
| File mask                      |``locales/*/messages.ftl``                        |
+--------------------------------+--------------------------------------------------+
| Monolingual base language file |``locales/en/messages.ftl``                       |
+--------------------------------+--------------------------------------------------+
| Template for new translations  | `Empty`                                          |
+--------------------------------+--------------------------------------------------+
| File format                    | `Fluent file`                                    |
+--------------------------------+--------------------------------------------------+
