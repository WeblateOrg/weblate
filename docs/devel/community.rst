Building a translators community
================================

Make it easy for people to start translating, ask questions, and see their work
reach users. Link contributors to :ref:`translator-start` and provide
project-specific instructions alongside it.

Welcoming translators
---------------------

Set :ref:`project-instructions` to explain where to begin, which components
have priority, and how to contact the language team. Include a short style
guide with examples of the tone and terminology you expect. Explain any
contribution agreement and how to request access or a missing language.

Describe your :ref:`workflows`: whether contributors save translations or
submit suggestions, who reviews their work, and when translations reach users.
Keep the requirements realistic for small language teams. Welcome useful
partial contributions rather than requiring a complete language translation.

Tell translators about release dates and translation deadlines early. Use
:doc:`/admin/announcements` for timely notices, and keep the translation instructions
up to date. Let contributors know when their work has shipped and acknowledge
their contributions. See :ref:`continuous-translation` for repository
integration and automation.

Component diagnostics
---------------------

Guidance is shown in the :guilabel:`Diagnostics` tab on each
component. These alerts are dismissible and point to the configuration or
documentation needed to make your localization process easier for community
translators.

.. image:: /screenshots/component-diagnostics.webp

Diagnostics cannot tell whether your instructions are clear or questions get
answered. Regularly try the contribution process with a translator account
and ask newcomers where they got stuck.

Terminology management
----------------------

Provide a :doc:`/user/glossary` for recurring terms, with explanations where a
word has a project-specific meaning. Agree on terminology with each language
team and keep it consistent across components. Record decisions so new
contributors do not need to repeat earlier discussions.

Existing :doc:`/admin/memory` can help reuse past translations. Review matches
in their new context: identical source wording does not always have the same
meaning.

Machine translation
-------------------

Explain whether machine translation is allowed and how contributors should
review its output. Choose services suited to the languages and subject matter
of your project, and evaluate their output with the language teams. Do not
assume that fluent wording preserves the source meaning or your terminology.

Weblate supports both service suggestions and automatic translation with
human review. Choose a :ref:`machine-translation-workflows` configuration that
matches your quality expectations and available reviewers.

Review translations
-------------------

When possible, have another speaker review translations for meaning, tone,
and consistency. Explain how to become a reviewer and who handles pending
suggestions. Respond constructively and explain corrections so contributors
can learn from them.

Provide :ref:`screenshots`, :ref:`additional-explanation`, and access to a
preview or test release so people can check translations in context. A
translation that reads well in isolation can still be wrong for a button or
too long for its layout. See :doc:`/devel/starting` for writing source strings
that work across languages.

Structured feedback
-------------------

Weblate's :doc:`/user/checks` help identify technical mistakes while translating.
Explain how to resolve recurring failures, and investigate false positives
instead of encouraging translators to ignore checks indiscriminately.

Translators also find problems in source strings. Monitor :ref:`user-comments`
and your advertised contact channel, answer questions, and report back when a
problem is fixed. Configure :ref:`component-repoweb` so contributors can find
the source code, and :ref:`component-report_source_bugs` for reporting source
problems. See :ref:`source-reviews` for reviewing source strings in Weblate.

Avoid unnecessary source-string changes that create repeated translation
work. Communicate changes to the workflow and let teams know when a component
is no longer maintained. For broader developer practices, see
:doc:`/devel/starting`.
