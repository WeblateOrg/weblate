Translation process
===================

.. _voting:

Suggestion voting
-----------------

Everyone can add suggestions by default, to be accepted by signed in users.
Suggestion voting can be used to make use of a string when more than one signed-in
user agrees, by setting up the :ref:`component` configuration with
:guilabel:`Suggestion voting` to turn on voting, and :guilabel:`Autoaccept suggestions`
to set a threshold for accepted suggestions (this includes a vote from the user
making the suggestion if it is cast).

.. note::

    Once automatic acceptance is set up, normal users lose the privilege to
    directly save translations or accept suggestions. This can be overridden
    with the :guilabel:`Edit string when suggestions are enforced`
    :ref:`permission <privileges>`.

You can combine these with :ref:`access control <access-control>` into one of
the following setups:

* Users suggest and vote for suggestions and a limited group controls what is
  accepted.
  - Turn on voting.
  - Turn off automatic acceptance.
  - Don't let users save translations.
* Users suggest and vote for suggestions with automatic acceptance
  once the defined number of them agree.
  - Turn on voting.
  - Set the desired number of votes for automatic acceptance.
* Optional voting for suggestions. (Can optionally be used by users when they are unsure about
  a translation by making multiple suggestions.)
  - Only turn on voting.

.. _additional:

Additional info on source strings
---------------------------------

Enhance the translation process by adding additional info to the strings
including explanations, string priorities, check flags and visual context. Some
of that info may be extracted from the translation files and some may be added
by editing the additional string info:

.. image:: /images/source-review-edit.png

Access this directly from the translation interface by clicking the
"Edit" icon next to :guilabel:`Screenshot context` or :guilabel:`Flags`.

.. image:: /images/source-information.png

Strings prioritization
++++++++++++++++++++++

.. versionadded:: 2.0

String priority can be changed to offer higher priority strings for translation earlier by
using the ``priority`` flag.

.. hint::

    This can be used to order the flow of translation in a logical manner.

.. seealso:: :ref:`checks`

Translation flags
+++++++++++++++++

.. versionadded:: 2.4

.. versionchanged:: 3.3

      Previously called :guilabel:`Quality checks flags`, it no
      longer configures only checks.

The default set of translation flags is determined by the translation
:ref:`component` and the translation file. However, you might want to use it
to customize this per source string.

.. seealso:: :ref:`checks`

Explanation
+++++++++++

.. versionchanged:: 4.1

    In previous versions this has been called :guilabel:`Extra context`.

Use the explanation to clarify scope or usage of the translation. You can use
Markdown to include links and other markup.

.. _screenshots:

Visual context for strings
++++++++++++++++++++++++++

.. versionadded:: 2.9

You can upload a screenshot showing a given source string in use within your
program. This helps translators understand where it is used, and how it should
be translated.

The uploaded screenshot is shown in the translation context sidebar:

.. image:: /images/screenshot-context.png

In addition to :ref:`additional`, screenshots have a separate management
interface under the :guilabel:`Tools` menu.
Upload screenshots, assign them to source strings manually, or use
optical character recognition to do so.

Once a screenshot is uploaded, this interface handles
management and source string association:

.. image:: /images/screenshot-ocr.png
