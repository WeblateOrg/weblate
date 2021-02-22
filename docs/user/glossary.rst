.. _glossary:

Glossary
========

Each project can have an assigned glossary as a shorthand for storing
terminology in all languages. Consistency is more easily maintained this way.
Terms from the glossary containing words from the currently translated string can be
displayed in the sidebar.

Managing glossaries
-------------------

.. versionchanged:: 4.5

   Glossaries are now regular translation components and you can use all
   Weblate features on them — commenting, storing in a Git repository, or
   adding explanations.

Use any component as a glossary by turning on :ref:`component-is_glossary`.

An empty glossary for a given project is automatically created with the project.
Glossaries are shared among all components of the same project, and optionally
with other projects using :ref:`component-links` from the respective glossary
component.

The glossary component looks like any other component in Weblate:

.. image:: /images/glossary-component.png

You can browse all glossary terms:

.. image:: /images/glossary-browse.png

Glossary terms
--------------

Glossary terms are translated the same way regular strings are. You can
toggle additional features using the :guilabel:`Tools` menu for each term.

.. image:: /images/glossary-tools.png

Untranslatable terms
++++++++++++++++++++

.. versionadded:: 4.5

Flagging certain glossary term translations ``read-only`` manually, or
using :guilabel:`Tools` ↓:guilabel:`Mark as read-only` means they can not
be translated. Use this for names or other terms that should not be changed in translation.
Such terms are visually highlighted in the glossary sidebar.

.. seealso::

   :ref:`custom-checks`

.. _glossary-forbidden:

Forbidden translations
++++++++++++++++++++++

.. versionadded:: 4.5

Flagging certain glossary term translations as ``forbidden``, manually or
using :guilabel:`Tools` ↓:guilabel:`Mark as forbidden translation` means they are
**not** to be used. Use this to clarify translation when some words are ambiguous
or could have unexpected meanings.

.. seealso::

   :ref:`custom-checks`

.. _glossary-terminology:

Terminology
+++++++++++

.. versionadded:: 4.5

Flagging certain glossary terms as ``terminology`` manually, or by
using :guilabel:`Tools` ↓:guilabel:`Mark as terminology` puts them in all
glossary languages. Use this for terms that should be translated consistently.

.. seealso::

   :ref:`custom-checks`

.. _glossary-variants:

Variants
++++++++

Variants are a generic way to group strings together. All term variants are
listed in the glossary sidebar when translating.

.. hint::

   You can use this to add abbreviations or shorter expressions for a term.

.. seealso::

   :ref:`variants`
