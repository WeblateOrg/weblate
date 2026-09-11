.. include:: /snippets/basics.rst

.. _translator-start:

Make your first translation
---------------------------

You can contribute to a project using your web browser. You do not need to
install Weblate or work with its source code repository.

Find your project and language
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Follow the translation link from the project you want to help. Projects
   can use Hosted Weblate or their own Weblate installation; use an account on
   that installation. If you arrive at its dashboard, choose
   :guilabel:`Projects` > :guilabel:`Browse all projects` to find the project.
2. Sign in, or follow the site's registration instructions. Access depends on
   the project: you might need to request permission from its maintainers.
   Some projects also accept suggestions without signing in.
3. If you are signed in, open your user menu and choose :guilabel:`Settings`. Under
   :guilabel:`Languages`, select your :guilabel:`Translated languages` and,
   optionally, :guilabel:`Secondary languages` you understand. Secondary
   languages appear above the source as additional help. Save your settings.
   If you are contributing anonymously, skip this step and choose your language
   directly in the project as described below.

.. image:: /screenshots/onboarding-languages.webp
   :alt: Language settings with Czech selected for translation and German as a secondary language.

Read the project's translation instructions before starting. These can explain
terminology, style, priorities, and how to contact the language team. If you
cannot find them, ask the maintainers which component to start with.

Choose your language and a component. A component groups related strings, such
as an application's interface or its documentation. Open
:guilabel:`Untranslated strings` to start with empty translations, or
:guilabel:`Unfinished strings` to include translations that still need work.
Use :guilabel:`All strings` or :doc:`/user/search` to find existing translations.
If your language is missing, use the option to start or request a translation
when available, or contact the maintainers.

.. seealso::

   * :doc:`/user/profile`
   * :ref:`strings-to-check`
   * :ref:`workflow-language-restrictions`

Translate a string
~~~~~~~~~~~~~~~~~~

The editor shows the source text and a field for your translation. Read any
explanation, screenshot, nearby strings, and glossary entries before writing.
Short strings can have several meanings: ask in :ref:`user-comments` if the
context is unclear. Other languages can help, but their translations can also
contain mistakes.

Write a natural expression of the intended meaning in your language. Follow
your language's typography and the project's terminology and style. Preserve
technical markers such as placeholders and markup; see
:ref:`translating-special-text`. When Weblate displays several plural fields,
complete each one according to its label; see :ref:`plurals`.

.. image:: /screenshots/onboarding-translation.webp
   :alt: Translation editor showing a source string, a Czech translation, and the save, suggest, and skip actions.

Choose the action that fits your contribution:

* :guilabel:`Save and continue` saves your translation and opens the next
  string. Use :guilabel:`Save and stay` to remain on the current string.
* Mark :guilabel:`Needs editing` when saving a translation that still needs
  work. Clear it after you have resolved the outstanding issues.
* :guilabel:`Suggest` proposes a translation for someone to accept. Use this
  when you want another translator to consider your wording, or when the
  project only allows you to suggest changes. A suggestion does not replace
  the current translation until it is accepted.
* :guilabel:`Skip` moves on without saving your edits. You can return later.

The available actions depend on your permissions and the project's workflow.
For example, an approved translation might only allow you to suggest a change.
Saving in Weblate does not mean the translation is immediately published in the
application: review, repository synchronization, and releases depend on the
project. See :ref:`states` and :ref:`workflows`.

Check your work and ask for help
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Read your translation again after saving. If Weblate reports failing
:doc:`quality checks </user/checks>`, open their explanations and correct the
problem. Ignore a check only when you have confirmed it is a false positive and
your permissions allow it. Passing all checks does not guarantee that the
meaning or tone is correct. Review suggestions from translation memory or
machine translation just as carefully as text you write yourself.

Use a translation comment for questions about your language, or a source
string comment for an unclear or incorrect original. Explain the problem and
include the context you have found. If source editing or source review is
available, follow the project's instructions for proposing a correction;
otherwise use its advertised contact or repository link. See
:ref:`user-comments` and :ref:`report-source`.

Keep contributing
~~~~~~~~~~~~~~~~~

Watch projects you want to return to and choose your :ref:`notifications`.
Your :ref:`dashboard` helps you find watched translations in your selected
languages. You can also help by reviewing existing translations and suggestions
when your permissions allow it.

As you become familiar with the editor, explore :ref:`keyboard`,
:ref:`source-context`, :doc:`/user/glossary`, and :doc:`/user/search`.
The editor's :guilabel:`History` tab shows earlier changes to a string.
See :ref:`profile-preferences` for editor preferences and :doc:`/user/files`
for downloading and uploading translations to work offline.
