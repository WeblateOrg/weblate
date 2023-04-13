.. _fluent:

Fluent format
-------------

.. versionadded:: 4.8

.. note::

   Support for this format is currently in beta, feedback from testing is welcome.

Fluent is a monolingual text format that focuses on asymmetric localization: a
simple string in one language can map to a complex multi-variant translation in
another language.

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


.. seealso::


   `Project Fluent website <https://projectfluent.org/>`_
