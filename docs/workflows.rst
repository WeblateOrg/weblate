.. _workflows:

Translation workflows
=====================

Using Weblate raises quality, reduces manual work, and brings everyone
involved in the localization process closer to each other.
It is up to you to decide how many of Weblate features you want to make use of.

The following is not a complete list of ways to configure Weblate.
You can base other workflows on the examples listed here.

.. _workflow-customization:

Workflow customization
----------------------

In addition to configuration at :ref:`project` and :ref:`component` (as
:ref:`project-translation_review`, :ref:`component-enable_suggestions`,
:ref:`component-suggestion_voting`, and
:ref:`component-suggestion_autoaccept`), the translation workflow can be
customized per language.

Site-wide workflow customization can be done while :ref:`changing-languages`.

Per-project customization can be done on each language page of the project.

All workflow settings can be overridden, the only limitation is that
:ref:`project-translation_review` needs to be turned on and can only be
disabled in customization.

The first existing setting applies:

1. Project-language customization
2. Language customization
3. The project/component settings

.. note::

   Please be careful when using site-wide override as that applies to all
   projects (unless they have own overrides for a given language).


Translation access
------------------

The :ref:`access control <access-control>` is not discussed in detail as a whole in
the workflows, as most of its options can be applied to any workflow.
Please consult the respective documentation on how to manage access to
translations.

In the following chapters, *any user* means a user who has access to the
translation. It can be any authenticated user if the project is public, or a user
with :guilabel:`Translate` permission to the project.

.. _states:

Translation states
------------------

Each translated string can be in one of the following states:

Untranslated
    Translation is empty, it might or not be stored in the file, depending
    on the file format.
Needs editing
    Translation needs editing, this is usually the result of a source string change, fuzzy matching or translator action.
    The translation is stored in the file, depending on the file format it might
    be marked as needing edit (for example as it gets a ``fuzzy`` flag in the gettext file).
Waiting for review
    Translation is made, but not reviewed. It is stored in the file as a valid
    translation.
Approved
    Translation has been approved in the review. It can no longer be changed by
    translators, but only by reviewers. Translators can only add suggestions to
    it.

    This state is only available when reviews are enabled.
Read-only
    String is read-only as a result of having ``read-only`` :ref:`flag
    <custom-checks>`, being a non-editable source string, or marked such in the
    translation file.
Suggestions
    Suggestions are stored in Weblate only and not in the translation file.

The states are represented in the translation files when possible.

.. hint::

   If the file format you use does not support storing states, you might want
   to use the :ref:`addon-weblate.flags.same_edit` add-on to flag unchanged strings
   as needing editing.

.. seealso::

   :ref:`fmt_capabs`,
   :ref:`workflows`


Direct translation
------------------
The most common setup for smaller teams, where anybody can translate directly.
This is also the default setup in Weblate.

* *Any user* can edit translations.
* Suggestions are optional ways to suggest changes, when translators are not
  sure about the change.

+----------------------------------+-------------+------------------------------------+
| Setting                          |   Value     |   Note                             |
+==================================+=============+====================================+
| Enable reviews                   | off         | Configured at project level.       |
+----------------------------------+-------------+------------------------------------+
| Enable suggestions               | on          | Useful for users to be able        |
|                                  |             | to suggest when they are not sure. |
+----------------------------------+-------------+------------------------------------+
| Suggestion voting                | off         |                                    |
+----------------------------------+-------------+------------------------------------+
| Automatically accept suggestions | 0           |                                    |
+----------------------------------+-------------+------------------------------------+
| Translators group                | `Users`     | Or `Translate` with                |
|                                  |             | :ref:`per-project access control   |
|                                  |             | <manage-acl>`.                     |
+----------------------------------+-------------+------------------------------------+
| Reviewers group                  | N/A         | Not used.                          |
+----------------------------------+-------------+------------------------------------+


.. _peer-review:

Peer review
-----------

With this workflow, anybody can add a suggestion, which needs approval
from additional member(s) before it is accepted as a translation.

* *Any user* can add suggestions.
* *Any user* can vote for suggestions.
* Suggestions become translations when given a predetermined number of votes.

+---------------------------------+-------------+------------------------------------+
| Setting                         |   Value     |   Note                             |
+=================================+=============+====================================+
| Enable reviews                  | off         | Configured at project level.       |
+---------------------------------+-------------+------------------------------------+
| Enable suggestions              | on          |                                    |
+---------------------------------+-------------+------------------------------------+
| Suggestion voting               | off         |                                    |
+---------------------------------+-------------+------------------------------------+
| Automatically accept suggestions| 1           | You can set higher value to        |
|                                 |             | require more peer reviews.         |
+---------------------------------+-------------+------------------------------------+
| Translators group               | `Users`     | Or `Translate` with                |
|                                 |             | :ref:`per-project access control   |
|                                 |             | <manage-acl>`.                     |
+---------------------------------+-------------+------------------------------------+
| Reviewers group                 | N/A         | Not used, all translators review.  |
+---------------------------------+-------------+------------------------------------+

.. _reviews:

Dedicated reviewers
-------------------

With dedicated reviewers you have two groups of users, one able to submit
translations, and one able to review them to ensure translations are
consistent and that the quality is good.

* *Any user* can edit unapproved translations.
* *Reviewer* can approve / unapprove strings.
* *Reviewer* can edit all translations (including approved ones).
* Suggestions can also be used to suggest changes for approved strings.

+---------------------------------+-------------+------------------------------------+
| Setting                         |   Value     |   Note                             |
+=================================+=============+====================================+
| Enable reviews                  | on          | Configured at project level.       |
+---------------------------------+-------------+------------------------------------+
| Enable suggestions              | off         | Useful for users to be able        |
|                                 |             | to suggest when they are not sure. |
+---------------------------------+-------------+------------------------------------+
| Suggestion voting               | off         |                                    |
+---------------------------------+-------------+------------------------------------+
| Automatically accept suggestions| 0           |                                    |
+---------------------------------+-------------+------------------------------------+
| Translators group               | `Users`     | Or `Translate` with                |
|                                 |             | :ref:`per-project access control   |
|                                 |             | <manage-acl>`.                     |
+---------------------------------+-------------+------------------------------------+
| Reviewers group                 | `Reviewers` | Or `Review` with                   |
|                                 |             | :ref:`per-project access control   |
|                                 |             | <manage-acl>`.                     |
+---------------------------------+-------------+------------------------------------+

Turning on reviews
------------------

Reviews can be turned on in the project configuration, from the
:guilabel:`Workflow` subpage of project settings (to be found in the
:guilabel:`Manage` → :guilabel:`Settings` menu):

.. image:: /screenshots/project-workflow.webp

.. _source-quality-gateway:

Quality gateway for the source strings
--------------------------------------

In many cases the original source language strings are coming from developers,
because they write the code and provide initial strings. However developers are
often not native speakers in the source language and do not provide desired
quality of the source strings. The intermediate translation can help you address this - there is an additional quality gateway for the strings between
developers and translators.

By setting :ref:`component-intermediate`, this file is used for translating strings
to the source language by translators/editors. Once this stage is done,
strings are available for translations to target languages,
based on what is now a polished source language.

.. graphviz::

    digraph translations {
        graph [fontname = "sans-serif", fontsize=10];
        node [fontname = "sans-serif", fontsize=10, margin=0.1, height=0, style=filled, fillcolor=white, shape=note];
        edge [fontname = "sans-serif", fontsize=10];

        subgraph cluster_dev {
            style=filled;
            color=lightgrey;

            label = "Development process";

            "Developers" [shape=box, fillcolor="#144d3f", fontcolor=white];
            "Developers" -> "Intermediate file";
        }

        subgraph cluster_l10n {
            style=filled;
            color=lightgrey;

            label = "Localization process";

            "Translators" [shape=box, fillcolor="#144d3f", fontcolor=white];
            "Editors" [shape=box, fillcolor="#144d3f", fontcolor=white];

            "Editors" -> "Monolingual base language file";
            "Translators" -> "Translation language file";
        }



        "Intermediate file" -> "Monolingual base language file" [constraint=false];
        "Monolingual base language file" -> "Translation language file" [constraint=false];

    }

.. seealso::

   :ref:`component-intermediate`,
   :ref:`component-template`,
   :ref:`bimono`

.. _source-reviews:

Source strings reviews
----------------------

With :ref:`project-source_review` enabled, the review process can be applied for
source strings. Once enabled, users can report issues with source strings.
The actual process depends on whether bilingual or monolingual formats are in use.

For monolingual formats, source string review functions similarly to
:ref:`reviews` — once an issue with a source string is reported, it is marked as
:guilabel:`Needs editing`.

Bilingual formats do not allow direct editing of source strings (these
are typically extracted directly from the source code). In this case, a
:guilabel:`Source needs review` label is attached to strings reported by
translators. You should review such strings and either edit them in the source
code, or remove the label.

.. seealso::

   :ref:`bimono`,
   :ref:`reviews`,
   :ref:`labels`,
   :ref:`user-comments`
