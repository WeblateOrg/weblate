.. _glossary:

Glossary
--------

Each project can have an assigned glossary for any language as a shorthand for storing
terminology. Consistency is more easily maintained this way.
Terms from the glossary containing words from the currently translated string can be
displayed in the sidebar.

Managing glossaries
+++++++++++++++++++

.. versionchanged:: 4.5

   Glossaries are now regular translation components and you can use all
   Weblate features on them - commenting, storing in a Git repository, or
   adding explanations.

You can use any component a glossary by turning on :ref:`component-is_glossary`.

An empty glossary for a given project is automatically created with the project.
Glossaries are shared among all components of the same project, and optionally
with other projects using :ref:`component-links`.

Not translatable terms
++++++++++++++++++++++

.. versionadded:: 4.5

Glossary terms which are read-only are not meant to be translated. You can use
this for names or other terms which should not change while translating. Such
term is visually highlighted in the glossary sidebar.

The terms can be flagged on the source language using :guilabel:`Tools` ↓
:guilabel:`Prohibit translations`. In background this toggles the ``read-only``
flag on the string.

.. seealso::

   :ref:`custom-checks`
