.. _glossary:

Glossary
========

Each project can include one or more glossaries as a shorthand for storing
terminology. Glossary easify maintaining consistency of the translation.

A glossary for each language can be managed on its own, but they are
stored together as a single component which helps project admins
and multilingual translators to maintain some cross-language consistency as well.
Terms from the glossary containing words from the currently translated string are
displayed in the sidebar of the translation editor.

.. hint::

   The glossary terms are not used in quality checks unless you enable that,
   see :ref:`check-check-glossary` for more information.

Managing glossaries
-------------------

.. versionchanged:: 4.5

   Glossaries are now regular translation components and you can use all
   Weblate features on them — commenting, storing in a remote repository, or
   adding explanations.

Use any component as a glossary by turning on :ref:`component-is_glossary`.
You can create multiple glossaries for one project.

An empty glossary for a given project is automatically created with the project.
Glossaries are shared among all components of the same project, and optionally
with other projects using :ref:`component-links` from the respective glossary
component.

The glossary component looks like any other component in Weblate with added
colored label:

.. image:: /screenshots/glossary-component.webp

You can browse all glossary terms:

.. image:: /screenshots/glossary-browse.webp

or edit them as any translations.

Glossary terms
--------------

Glossary terms are translated the same way regular strings are. You can
toggle additional features using the :guilabel:`Tools` menu for each term.

.. image:: /screenshots/glossary-tools.webp

Untranslatable terms
++++++++++++++++++++

.. versionadded:: 4.5

Flagging certain glossary term translations ``read-only`` by bulk-editing, typing in the flag, or
by using :guilabel:`Tools` ↓ :guilabel:`Mark as untranslatable` means they can not
be translated. Use this for brand names or other terms that should not be changed in other languages.
Such terms are visually highlighted in the glossary sidebar.

.. seealso::

   :ref:`custom-checks`

.. _glossary-forbidden:

Forbidden translations
++++++++++++++++++++++

.. versionadded:: 4.5

Flagging certain glossary term translations as ``forbidden``,  by bulk-editing,
typing in the flag, or by using :guilabel:`Tools` ↓ :guilabel:`Mark as forbidden translation`
means they are **not** to be used. Use this to clarify translation when some words are
ambiguous or could have unexpected meanings.

.. seealso::

   :ref:`custom-checks`

.. _glossary-terminology:

Terminology
+++++++++++

.. versionadded:: 4.5

Flagging certain glossary terms as ``terminology``  by bulk-editing, typing in the flag,
or by using :guilabel:`Tools` ↓ :guilabel:`Mark as terminology` adds entries for them
to all languages in the glossary. Use this for important terms that should
be well thought out, and retain a consistent meaning across all languages.

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

.. _glossary-mt:

Glossaries in automatic suggestion
----------------------------------

.. versionadded:: 5.3

Following automatic suggestion services utilize glossaries during the translation:

* :ref:`mt-openai`
* :ref:`mt-deepl`
* :ref:`mt-microsoft-translator`

The glossary is processed before exposed to the service:

* Duplicate source entries are not allowed, any additional entries with the same source are skipped.
* Any control characters and leading and trailing whitespace are stripped.
* :ref:`glossary-forbidden` are skipped.

.. note::

   Many services store glossaries server-side and enforce limit on the number
   of saved glossaries. Weblate always deletes the oldest glossary if it runs out of
   space.
