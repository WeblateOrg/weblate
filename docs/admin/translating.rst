Translation process
===================

.. _voting:

Suggestion voting
-----------------

.. versionadded:: 1.6

    This feature is available since Weblate 1.6.

By default, everyone can add suggestions, which logged in users can
accept. Requiring more then one person for acceptance can be achieved by suggestion voting.
You can enable this on :ref:`component` configuration by
:guilabel:`Suggestion voting` and :guilabel:`Autoaccept suggestions`. The first
one enables the voting feature, while the latter sets the threshold a suggestion 
is automatically is accepted (this includes a vote from
the user making the suggestion).

.. note::

    Once automatic acceptance is set up, normal users lose the privilege to
    directly save translations or accept suggestions. This can be overridden
    by :guilabel:`Can override suggestion state` privilege
    (see :ref:`privileges`).

You can combine these with :ref:`privileges` into one of the following setups:

* Users suggest and vote for suggestions, a limited group controls what is
  accepted - turn on voting, but automatic acceptance off, and 
  don't let users save translations.
* Users suggest and vote for suggestions with automatical acceptance
  once the defined number of them agree - turn on voting and set the desired
  number of votes for automatic acceptance.
* Optional voting for suggestions - you can also turn on voting only, and in
  this case it can optionally be used by users when they are unsure about
  a translation by making multiple suggestions.

.. _additional:

Additional info on source strings
----------------------------------------

Enhance the translation process with info available in the translation files.
This includes string prioritization, check flags, or providing visual context.
All these features can be set on the
:ref:`source-review`:

.. image:: /images/source-review-edit.png

Access this directly from the translating interface by clicking the
"Edit" icon next to :guilabel:`Screenshot context` or :guilabel:`Flags`.

.. image:: /images/source-information.png

Strings prioritization
++++++++++++++++++++++

.. versionadded:: 2.0

You can change string priority, strings with higher priority are offered first
for translation. This can be useful for prioritizing translation of strings
which are seen first by users or are otherwise important. This can be achieved
using ``priority`` flag.

.. seealso:: :ref:`checks`

Translation flags
+++++++++++++++++

.. versionadded:: 2.4

.. versionchanged:: 3.3

      Previously this was called :guilabel:`Quality checks flags`, but as it no
      longer configures only checks, the name was changed to be more generic.

The default set of translation flags is determined by the translation
:ref:`component` and the translation file. However, you might want to use it 
to customize this per source string.

.. seealso:: :ref:`checks`

.. _screenshots:

Visual context for strings
++++++++++++++++++++++++++

.. versionadded:: 2.9

You can upload a screenshot showing a given source string in use within your
program. This helps translators understand where it is used, and how
it should be translated.

The uploaded screenshot is shown in the translation context sidebar:

.. image:: /images/screenshot-context.png

In addition to :ref:`source-review`, screenshots have a separate management
interface under :guilabel:`Tools` menu.
Upload screenshots, assign them to source strings manually or with the use of OCR.

Once a screenshot is uploaded, this interface handles
management and assigning it to source strings:

.. image:: /images/screenshot-ocr.png
