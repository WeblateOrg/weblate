.. _glossary:

Glossary
========

Each project can include one or more glossaries as a shorthand for storing
terminology. Glossaries help to maintain consistency of the translation.

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

.. seealso::

   :ref:`adding-strings`

.. _glossary-untranslatable:

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

Flagging certain glossary term translations as ``forbidden`` by bulk-editing,
typing in the flag, or by using :guilabel:`Tools` ↓ :guilabel:`Mark as forbidden translation`
means they are **not** to be used. Use this to clarify translation when some words are
ambiguous or could have unexpected meanings.

.. seealso::

   :ref:`custom-checks`

.. _glossary-terminology:

Terminology
+++++++++++

.. versionadded:: 4.5

Flagging certain glossary terms as ``terminology`` by bulk-editing, typing in the flag,
or by using :guilabel:`Tools` ↓ :guilabel:`Mark as terminology` declares the term as
managed project terminology and performs a one-time population:

* Weblate creates an entry for that term in every language of the glossary that does not
   yet have it, with an empty translation target. This ensures the term exists across all
   languages so it can be translated (or left empty for later).

What it indicates
-----------------

The presence of the ``terminology`` flag indicates that this term is intended to exist in
all glossary languages. While the flag is present on the source term:

* Weblate will keep adding the missing language entries if new languages are added to the
   project or glossary later.
* Non‑source terminology entries can not be removed individually — trying to delete one will
   be refused with an explanation. Remove the source term to remove the whole set, or unmark
   the source term first (see below).

What it does not do
-------------------

* Removing the flag later does not delete any entries that were created earlier. It simply
   stops further automatic creation for newly added languages.
* The flag does not change how the term is used by translation suggestions or checks by itself;
   all glossary terms are available to those features. The flag only affects creation/management
   and deletion protection as described here.

Unmarking a terminology term
----------------------------

You can remove the ``terminology`` flag from the source term at any time. After unmarking:

* Existing per‑language entries remain as they are.
* Weblate no longer ensures the term exists in newly added languages.
* Deleting individual per‑language entries becomes possible again (subject to component settings
   and file format support). If you want to remove the term everywhere, delete the source term.

How this differs from regular glossary entries
----------------------------------------------

* Regular glossary entries only exist in languages where they were imported or manually created.
* Marking a term as ``terminology`` instructs Weblate to create and maintain empty placeholders
   for all other languages, so translators can fill them. This is especially helpful for key terms
   that should be present across the project.

.. note::

    Creating terminology entries might require specific permissions (for example
    :guilabel:`Add glossary terminology`) depending on your Weblate setup.

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

Glossary import
---------------

Similar to regular translation components, you can upload existing glossaries
to Weblate. Formats like :doc:`/formats/csv` or :doc:`/formats/tbx` are
supported and can be uploaded, see :ref:`upload`.

.. _glossary-mt:

Glossaries in automatic suggestion
----------------------------------

.. versionadded:: 5.3

Following automatic suggestion services utilize glossaries during the translation:

* :ref:`mt-openai`
* :ref:`mt-deepl`
* :ref:`mt-microsoft-translator`
* :ref:`mt-modernmt`
* :ref:`mt-aws`
* :ref:`mt-google-translate-api-v3`

The glossary is processed before exposed to the service:

* Duplicate source entries are not allowed, any additional entries with the same source are skipped.
* Any control characters and leading and trailing whitespace are stripped.
* :ref:`glossary-forbidden` are skipped.

.. note::

   Many services store glossaries server-side and enforce limit on the number
   of saved glossaries. Weblate always deletes the oldest glossary if it runs out of
   space.
