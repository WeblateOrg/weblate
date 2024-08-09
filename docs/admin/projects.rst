Translation projects
====================

Translation organization
------------------------

Weblate organizes translatable VCS content of project/components into a
tree-like structure. You can additionally organize components within a project
using categories.

* The bottom level object is :ref:`project`, which should hold all translations belonging
  together (for example translation of an application in several versions
  and/or accompanying documentation).

* The middle level is optionally created by :ref:`category`. The categories can
  be nested to achieve more complex structure.

* On the level above, :ref:`component`, which is
  actually the component to translate, you define the VCS repository to use, and
  the mask of files to translate.

* Above :ref:`component` there are individual translations, handled automatically by Weblate as translation
  files (which match :ref:`component-filemask` defined in :ref:`component`) appear in the VCS repository.

Weblate supports a wide range of translation formats (both bilingual and
monolingual ones) supported by Translate Toolkit, see :ref:`formats`.

.. note::

    You can share cloned VCS repositories using :ref:`internal-urls`.
    Using this feature is highly recommended when you have many
    components sharing the same VCS. It improves performance and decreases
    required disk space.

.. _adding-projects:

Adding translation projects and components
------------------------------------------

Based on your permissions, new translation projects and components can be
created. It is always permitted for users with the :guilabel:`Add new projects`
permission, and if your instance uses billing (e.g. like
https://hosted.weblate.org/ see :ref:`billing`), you can also create those
based on your plans allowance from the user account that manages billing.

.. hint::

   To grant every user permission to create new projects create new
   :ref:`autoteam` for the :guilabel:`Project creators` team.

You can view your current billing plan on a separate page:

.. image:: /screenshots/user-billing.webp

The project creation can be initiated from there, or using the menu in the navigation
bar, filling in basic info about the translation project to complete addition of it:

.. image:: /screenshots/user-add-project.webp

After creating the project, you are taken directly to the project page:

.. image:: /screenshots/user-add-project-done.webp

Creating a new translation component can be initiated via a single click there.
The process of creating a component is multi-staged and automatically detects most
translation parameters. There are several approaches to creating component:

From version control
    Creates component from remote version control repository.
From existing component
    Creates additional component to existing one by choosing different files.
Additional branch
    Creates additional component to existing one, just for different branch.
Upload translations files
    Upload translation files to Weblate in case you do not have version control
    or do not want to integrate it with Weblate. You can later update the
    content using the web interface or :ref:`api`.
Translate document
    Upload single document or translation file and translate that.
Start from scratch
    Create blank translation project and add strings manually.

Once you have existing translation components, you can also easily add new ones
for additional files or branches using same repository.

First you need to fill in name and repository location:

.. image:: /screenshots/user-add-component-init.webp

On the next page, you are presented with a list of discovered translatable resources:

.. image:: /screenshots/user-add-component-discovery.webp

As a last step, you review the translation component info and fill in optional details:

.. image:: /screenshots/user-add-component.webp

.. seealso::

      :ref:`admin-interface`,
      :ref:`project`,
      :ref:`component`

.. _project:

Project configuration
---------------------

Create a translation project and then add a new component for translation in it.
The project is like a shelf, in which real translations are stacked. All
components in the same project share suggestions and their dictionary; the
translations are also automatically propagated through all components in a single
project (unless turned off in the component configuration), see :ref:`memory`.

.. seealso::

   :doc:`/devel/integration`

These basic attributes set up and inform translators of a project:

.. _project-name:

Project name
++++++++++++

Verbose project name, used to display the project name.

.. seealso::

   :setting:`PROJECT_NAME_RESTRICT_RE`

.. _project-slug:

URL slug
++++++++

Project name suitable for URLs.

.. _project-web:

Project website
+++++++++++++++

URL where translators can find more info about the project.

This is a required parameter unless turned off by :setting:`WEBSITE_REQUIRED`.

.. seealso::

   :setting:`PROJECT_WEB_RESTRICT_HOST`,
   :setting:`PROJECT_WEB_RESTRICT_NUMERIC`,
   :setting:`PROJECT_WEB_RESTRICT_RE`

.. _project-instructions:

Translation instructions
++++++++++++++++++++++++

Text describing localization process in the project, and any other information
useful for translators. Markdown can be used for text formatting or inserting links.

.. _project-set_language_team:

Set "Language-Team" header
++++++++++++++++++++++++++

Whether Weblate should manage the ``Language-Team`` header (this is a
:ref:`gettext` only feature right now).

.. _project-use_shared_tm:

Use shared translation memory
+++++++++++++++++++++++++++++

Whether to use shared translation memory, see :ref:`shared-tm` for more details.

The default value can be changed by :setting:`DEFAULT_SHARED_TM`.

.. _project-contribute_shared_tm:

Contribute to shared translation memory
+++++++++++++++++++++++++++++++++++++++

Whether to contribute to shared translation memory, see :ref:`shared-tm` for more details.

This also affects whether the project can be used as source for :ref:`automatic-translation`.

The default value can be changed by :setting:`DEFAULT_SHARED_TM`.

.. note::

    This option is unavailable on Hosted Weblate, it is toggled together with :ref:`project-use_shared_tm`.

.. _project-access_control:

Access control
++++++++++++++

Configure per project access control, see :ref:`acl` for more details.

The default value can be changed by :setting:`DEFAULT_ACCESS_CONTROL`.

.. _project-enforced_2fa:

Enforced two-factor authentication
++++++++++++++++++++++++++++++++++

.. versionadded:: 5.7

Enforce :ref:`2fa` for all contributors. Users won’t be allowed
to perform any operations within the project without having it configured.

.. _project-translation_review:

Enable reviews
++++++++++++++

Enable review workflow for translations, see :ref:`reviews`.

.. seealso::

   :ref:`workflow-customization`

.. _project-source_review:

Enable source reviews
+++++++++++++++++++++

Enable review workflow for source strings, see :ref:`source-reviews`.

.. seealso::

   :ref:`report-source`,
   :ref:`user-comments`

.. _project-enable_hooks:

Enable hooks
++++++++++++

Whether unauthenticated :ref:`hooks` are to be used for this repository.

.. seealso::

   :ref:`component-intermediate`,
   :ref:`source-quality-gateway`,
   :ref:`bimono`,
   :ref:`languages`

.. _project-language_aliases:

Language aliases
++++++++++++++++

Define language codes mapping when importing translations into Weblate. Use
this when language codes are inconsistent in your repositories and you want to
get a consistent view in Weblate or in case you want to use non-standard naming
of your translation files.

The typical use case might be mapping American English to English: ``en_US:en``

Multiple mappings to be separated by comma: ``en_GB:en,en_US:en``

Using non standard code: ``ia_FOO:ia``

.. hint::

   The language codes are mapped when matching the translation files and the
   matches are case sensitive, so ensure you use the source language codes
   in same form as used in the filenames.

.. seealso::

    :ref:`adding-translation`,
    :ref:`language-code`,
    :ref:`language-parsing-codes`

.. _component:

Component configuration
-----------------------

A component is a grouping of something for translation. You enter a VCS repository location
and file mask for which files you want translated, and Weblate automatically fetches from this VCS,
and finds all matching translatable files.

.. seealso::

   :doc:`/devel/integration`

You can find some examples of typical configurations in the :ref:`formats`.

.. note::

    It is recommended to keep translation components to a reasonable size - split
    the translation by anything that makes sense in your case (individual
    apps or add-ons, book chapters or websites).

    Weblate easily handles translations with 10000s of strings, but it is harder
    to split work and coordinate among translators with such large translation components.

Should the language definition for a translation be missing, an empty definition is
created and named as "cs_CZ (generated)". You should adjust the definition and
report this back to the Weblate authors, so that the missing languages can be included in
next release.

The component contains all important parameters for working with the VCS, and
for getting translations out of it:

.. _component-name:

Component name
++++++++++++++

Verbose component name, used to display the component name.

.. _component-slug:

Component slug
++++++++++++++

Component name suitable for URLs.

.. _component-project:

Component project
+++++++++++++++++

:ref:`project` where the component belongs.

.. _component-vcs:

Version control system
++++++++++++++++++++++

VCS to use, see :ref:`vcs` for details.

.. seealso::

   :ref:`push-changes`

.. _component-repo:

Source code repository
++++++++++++++++++++++

VCS repository used to pull changes.

.. seealso::

    See :ref:`vcs-repos` for more details on specifying URLs.

.. hint::

    This can either be a real VCS URL or ``weblate://project/component``
    indicating that the repository should be shared with another component.
    See :ref:`internal-urls` for more details.

.. _component-push:

Repository push URL
+++++++++++++++++++

Repository URL used for pushing. The behavior of this depends on
:ref:`component-vcs`, and this is in more detail covered in
:ref:`push-changes`.

For linked repositories, this is not used and setting from linked component applies.

.. seealso::

   See :ref:`vcs-repos` for more details on how to specify a repository URL and
   :ref:`push-changes` for more details on pushing changes from Weblate.

.. _component-repoweb:

Repository browser
++++++++++++++++++

URL of repository browser used to display source files (location of used messages).
When empty, no such links will be generated. You can use :ref:`markup`.

For example on GitHub, use something like:
``https://github.com/WeblateOrg/hello/blob/{{branch}}/{{filename}}#L{{line}}``

In case your paths are relative to different folder (path contains ``..``), you
might want to strip leading directory by ``parentdir`` filter (see
:ref:`markup`):
``https://github.com/WeblateOrg/hello/blob/{{branch}}/{{filename|parentdir}}#L{{line}}``

.. _component-git_export:

Exported repository URL
+++++++++++++++++++++++

URL where changes made by Weblate are exported. This is important when
:ref:`continuous-translation` is not used, or when there is a need to manually
merge changes. You can use :ref:`git-exporter` to automate this for Git
repositories.

.. _component-branch:

Repository branch
+++++++++++++++++

Which branch to checkout from the VCS, and where to look for translations.

For linked repositories, this is not used and setting from linked component applies.

.. _component-push_branch:

Push branch
+++++++++++

Branch for pushing changes, leave empty to use :ref:`component-branch`.

For linked repositories, this is not used and setting from linked component applies.

.. note::

   This is currently only supported for Git, GitLab and GitHub, it is ignored
   for other VCS integrations.

.. seealso::

   :ref:`push-changes`

.. _component-filemask:

File mask
+++++++++

Mask of files to translate, including path. It should include one "*"
replacing language code (see :ref:`languages` for info on how this is
processed). In case your repository contains more than one translation
file (e.g. more gettext domains), you need to create a component for
each of them.

For example ``po/*.po`` or ``locale/*/LC_MESSAGES/django.po``.

In case your filename contains special characters such as ``[``, ``]``, these need
to be escaped as ``[[]`` or ``[]]``.

.. seealso::

   :ref:`bimono`,
   :ref:`faq-duplicate-files`

.. _component-screenshot_filemask:

Screenshot file mask
++++++++++++++++++++

This feature allows the discovery and updating of screenshots through screenshot file masks, using paths from the VCS repository.
This operates at the component level and necessitates the use of an asterisk "*" to replace the screenshot file name.

Allowed formats are WebP, JPEG, PNG, APNG and GIF.

Note:

1. The file mask and screenshot file mask are not related. Configure them separately.
2. It is a manual job to link a discovered screenshot in a component to a specific translation key.

For example:

Let's assume your VCS repository has a structure like this:

.. code-block:: text

    component_A
    └── docs
        ├── image1.png
        └── image2.jpg

For component_A, you want to allow discovery and updates of PNG screenshots.
You'd set the screenshot file mask for component_A as ``component_A/docs/*.png``.
This means any PNG images under docs in component_A can be discovered and updated.
So, if you want to update ``image1.png``, the new screenshot you provide should be named ``image1.png``,
matching the existing ``filename``, and stored under ``component_A/docs/``.

.. _component-template:

Monolingual base language file
++++++++++++++++++++++++++++++

Base file containing string definitions for :ref:`monolingual`.

.. seealso::

   :ref:`bimono`,
   :ref:`faq-duplicate-files`

.. _component-edit_template:

Edit base file
++++++++++++++

Whether to allow editing strings in the :ref:`component-template`.

.. seealso::

   :ref:`bimono`,
   :ref:`monolingual`,
   :ref:`faq-duplicate-files`,
   :ref:`component-manage_units`

.. _component-intermediate:

Intermediate language file
++++++++++++++++++++++++++

Intermediate language file for :ref:`monolingual`. In most cases this is a
translation file provided by developers and is used when creating actual source
strings.

When set, the source strings are based on this file, but all other languages
are based on :ref:`component-template`. In case the string is not translated
into the source language, translating to other languages is prohibited. This
provides :ref:`source-quality-gateway`.

.. seealso::

   :ref:`source-quality-gateway`,
   :ref:`bimono`,
   :ref:`faq-duplicate-files`

.. _component-new_base:

Template for new translations
+++++++++++++++++++++++++++++

Base file used to generate new translations.

* Keep this field empty for most of the monoligual formats. Those are typically able to start from an empty file.
* Choose ``.pot`` file with GNU gettext PO files.
* Choose blank file without translations, if you have one.
* Choose :ref:`component-template` for monolingual formats that need a full set of keys present.
* Choose :ref:`component-template` for document translations.
* Choose any translation file for others.
* Template file can be the same as the base file in most cases.

.. hint::

   In many monolingual formats Weblate starts with empty file by default. Use
   this in case you want to have all strings present with empty value when
   creating new translation.

.. seealso::

   :ref:`adding-translation`,
   :ref:`component-new_lang`,
   :ref:`bimono`,
   :ref:`faq-duplicate-files`

.. _component-file_format:

File format
+++++++++++

Translation file format, see also :ref:`formats`.

.. _component-report_source_bugs:

Source string bug reporting address
+++++++++++++++++++++++++++++++++++

Email address used for reporting upstream bugs. This address will also receive
notification about any source string comments made in Weblate.

With the :ref:`gettext` format, this address is also saved by Weblate in the
:mailheader:`Report-Msgid-Bugs-To` header of the file.

.. _component-allow_translation_propagation:

Allow translation propagation
+++++++++++++++++++++++++++++

You can turn off propagation of translations to this component from other
components within same project. This really depends on what you are
translating, sometimes it's desirable to have make use of a translation more than once.

It's usually a good idea to turn this off for monolingual translations, unless
you are using the same IDs across the whole project.

Default value can be changed by :setting:`DEFAULT_TRANSLATION_PROPAGATION`.

.. seealso::

   :ref:`translation-consistency`

.. _component-enable_suggestions:

Enable suggestions
++++++++++++++++++

Whether translation suggestions are accepted for this component.

.. seealso::

   :ref:`workflow-customization`

.. _component-suggestion_voting:

Suggestion voting
+++++++++++++++++

Turns on vote casting for suggestions, see :ref:`voting`.

.. seealso::

   :ref:`workflow-customization`

.. _component-suggestion_autoaccept:

Automatically accept suggestions
++++++++++++++++++++++++++++++++

Automatically accept voted suggestions, see :ref:`voting`.

.. seealso::

   :ref:`workflow-customization`

.. _component-check_flags:

Translation flags
+++++++++++++++++

Customization of quality checks and other Weblate behavior, see :ref:`custom-checks`.

.. _component-enforced_checks:

Enforced checks
+++++++++++++++

List of checks which can not be ignored, see :ref:`enforcing-checks`.

.. note::

   Enforcing the check does not automatically enable it, you still should
   enabled it using :ref:`custom-checks` in :ref:`component-check_flags` or
   :ref:`additional`.

.. _component-license:

Translation license
+++++++++++++++++++

License of the translation (does not need to be the same as the source code license).

.. _component-agreement:

Contributor agreement
+++++++++++++++++++++

User agreement which needs to be approved before a user can translate this
component.

.. _component-new_lang:

Adding new translation
++++++++++++++++++++++

How to handle requests for creation of new languages. Available options:

Contact maintainers
    User can select desired language and the project maintainers will receive a
    notification about this. It is up to them to add (or not) the language to the
    repository.
Point to translation instructions URL
    User is presented a link to page which describes process of starting new
    translations. Use this in case more formal process is desired (for example
    forming a team of people before starting actual translation).
Create new language file
    User can select language and Weblate automatically creates the file for it
    and translation can begin.
Disable adding new translations
    There will be no option for user to start new translation.

.. hint::

   The project admins can add new translations even if it is disabled here when
   it is possible (either :ref:`component-new_base` or the file format supports
   starting from an empty file).

.. seealso::

   :ref:`adding-translation`,
   :ref:`component-new_base`

.. _component-manage_units:

Manage strings
++++++++++++++

.. versionadded:: 4.5

Configures whether users in Weblate will be allowed to add new strings and
remove existing ones. Adjust this to match your localization workflow - how the
new strings are supposed to be introduced.

For bilingual formats, the strings are typically extracted from the source code
(for example by using :program:`xgettext`) and adding new strings in Weblate
should be disabled (they would be discarded next time you update the
translation files). In Weblate you can manage strings for every translation and
it does not enforce the strings in all translations to be consistent.

For monolingual formats, the strings are managed only on source language and
are automatically added or removed in the translations. The strings appear in
the translation files once they are translated.

.. hint::

   You might want to turn on :ref:`component-edit_template` together with
   :guilabel:`Manage strings` for monolingual formats.

.. seealso::

   :ref:`bimono`,
   :ref:`adding-new-strings`,
   :http:post:`/api/translations/(string:project)/(string:component)/(string:language)/units/`

.. _component-language_code_style:

Language code style
+++++++++++++++++++

Customize language code used to generate the filename for translations
created by Weblate.

.. note::

   Weblate recognizes any of the language codes when parsing translation files,
   following settings only influences how new files are created.

Default based on the file format
   Dependent on file format, for most of them POSIX is used.
POSIX style using underscore as a separator
   Typically used by gettext and related tools, produces language codes like
   ``pt_BR``.
POSIX style using underscore as a separator, lower cased
   Typically used by gettext and related tools, produces language codes like
   ``pt_BR``.
POSIX style using underscore as a separator, including country code
   POSIX style language code including the country code even when not necessary
   (for example ``cs_CZ``).
POSIX style using underscore as a separator, including country code, lower cased
   POSIX style language code including the country code even when not necessary (lowercase)
   (for example ``cs_cz``).
BCP style using hyphen as a separator
   Typically used on web platforms, produces language codes like
   ``pt-BR``.
BCP style using hyphen as a separator, including country code
   BCP style language code including the country code even when not necessary
   (for example ``cs-CZ``).
BCP style using hyphen as a separator, legacy language codes
   Uses legacy codes for Chinese and BCP style notation.
BCP style using hyphen as a separator, lower cased
   BCP style notation, all in lower case (for example ``cs-cz``).
Apple App Store metadata style
   Style suitable for uploading metadata to Apple App Store.
Google Play metadata style
   Style suitable for uploading metadata to Google Play Store.
Android style
   Only used in Android apps, produces language codes like
   ``pt-rBR``.
Linux style
   Locales as used by Linux, uses legacy codes for Chinese and POSIX style notation.
Linux style, lower cased
   Locales as used by Linux, uses legacy codes for Chinese and POSIX style notation. Lower cased.

.. seealso::

    :ref:`adding-translation`,
    :ref:`language-code`,
    :ref:`language-parsing-codes`,
    :ref:`project-language_aliases`

.. _component-merge_style:

Merge style
+++++++++++

You can configure how updates from the upstream repository are handled.
The actual implementation depends on VCS, see :doc:`/vcs`.

Rebase
   Rebases Weblate commits on top of upstream repository on update. This
   provides clean history without extra merge commits.

   Rebasing can cause you trouble in case of complicated merges, so carefully
   consider whether or not you want to enable them.

   You might need to enable force pushing by choosing :ref:`vcs-git-force-push`
   as :ref:`component-vcs`, especially when pushing to a different branch.

Merge
   Upstream repository changes are merged into Weblate one. This setting utilizes
   fast-forward when possible. This is the safest way, but might produce a lot
   of merge commits.

Merge without fast-forward
   Upstream repository changes are merged into Weblate one with doing a merge
   commit every time (even when fast-forward would be possible). Every Weblate
   change will appear as a merge commit in Weblate repository.

Default value can be changed by :setting:`DEFAULT_MERGE_STYLE`.

.. _component-commit_message:
.. _component-add_message:
.. _component-delete_message:
.. _component-merge_message:
.. _component-addon_message:
.. _component-pull_message:

Commit, add, delete, merge, add-on, and merge request messages
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

Message used when committing a translation, see :ref:`markup`.

Default value can be changed by :setting:`DEFAULT_ADD_MESSAGE`,
:setting:`DEFAULT_ADDON_MESSAGE`, :setting:`DEFAULT_COMMIT_MESSAGE`,
:setting:`DEFAULT_DELETE_MESSAGE`, :setting:`DEFAULT_MERGE_MESSAGE`,
:setting:`DEFAULT_PULL_MESSAGE`.

.. _component-push_on_commit:

Push on commit
++++++++++++++

Whether committed changes should be automatically pushed to the upstream
repository. When enabled, the push is initiated once Weblate commits
changes to its underlying repository (see :ref:`lazy-commit`). To actually
enable pushing :guilabel:`Repository push URL` has to be configured as
well.

.. _component-commit_pending_age:

Age of changes to commit
++++++++++++++++++++++++

Sets how old (in hours) changes have to be before they are committed by
background task or the :wladmin:`commit_pending` management command. All
changes in a component are committed once there is at least one change
older than this period.

Default value can be changed by :setting:`COMMIT_PENDING_HOURS`.

.. hint::

   There are other situations where pending changes might be committed, see
   :ref:`lazy-commit`.

.. _component-auto_lock_error:

Lock on error
+++++++++++++

Locks the component (and linked components, see :ref:`internal-urls`)
upon the first failed push or merge into its upstream repository, or pull from it.
This avoids adding another conflicts, which would have to be resolved manually.

The component will be automatically unlocked once there are no repository
errors left.

.. _component-source_language:

Source language
+++++++++++++++

Language used for source strings. Change this if you are translating from
something else than English.

.. hint::

   In case you are translating bilingual files from English, but want to be
   able to do fixes in the English translation as well, choose
   :guilabel:`English (Developer)` as a source language to avoid conflict
   between the name of the source language and the existing translation.

   For monolingual translations, you can use intermediate translation in this
   case, see :ref:`component-intermediate`.


.. _component-language_regex:

Language filter
+++++++++++++++

Regular expression used to filter the translation when scanning for file mask.
It can be used to limit the list of languages managed by Weblate.

.. note::

    You need to list language codes as they appear in the filename.

Some examples of filtering:

+-------------------------------+-----------------------+
| Filter description            | Regular expression    |
+===============================+=======================+
| Selected languages only       | ``^(cs|de|es)$``      |
+-------------------------------+-----------------------+
| Exclude languages             | ``^(?!(it|fr)$).+$``  |
+-------------------------------+-----------------------+
| Filter two letter codes only  | ``^..$``              |
+-------------------------------+-----------------------+
| Exclude non language files    | ``^(?!(blank)$).+$``  |
+-------------------------------+-----------------------+
| Include all files (default)   | ``^[^.]+$``           |
+-------------------------------+-----------------------+

.. _component-variant_regex:

Variants regular expression
+++++++++++++++++++++++++++

Regular expression used to determine the variants of a string, see
:ref:`variants`.

.. note::

    Most of the fields can be edited by project owners or administrators, in the
    Weblate interface.

.. seealso::

   :ref:`faq-vcs`, :ref:`alerts`

.. _component-priority:

Priority
+++++++++

Components with higher priority are offered first to translators.

.. versionchanged:: 4.15

   This now also affects ordering of matched glossary terms.

.. _component-restricted:

Restricted access
+++++++++++++++++

.. include:: /snippets/not-hosted.rst

By default the component is visible to anybody who has access to the project,
even if the person can not perform any changes in the component. This makes it
easier to keep translation consistency within the project.

Restricting access at a component, or component-list level takes over
access permission to a component, regardless of project-level permissions.
You will have to grant access to it explicitly. This can be done through
granting access to a new user group and putting users in it,
or using the default `custom` or `private` access control groups.

The default value can be changed in :setting:`DEFAULT_RESTRICTED_COMPONENT`.

.. hint::

   This applies to project admins as well — please ensure you will not
   loose access to the component after toggling the status.

.. _component-links:

Share in projects
+++++++++++++++++

You can choose additional projects where the component will be visible.
Useful for shared libraries which you use in several projects.

.. note::

   Sharing a component doesn't change its access control. It only makes it
   visible when browsing other projects. Users still need access to the
   actual component to browse or translate it.


.. _component-is_glossary:

Use as a glossary
+++++++++++++++++

.. versionadded:: 4.5

Allows using this component as a glossary. You can configure how it will be
listed using :ref:`component-glossary_color`.

The glossary will be accessible in all projects defined by :ref:`component-links`.

It is recommended to enable :ref:`component-manage_units` on glossaries in
order to allow adding new words to them.

.. seealso::

   :ref:`glossary`

.. _component-glossary_color:

Glossary color
++++++++++++++

Display color for a glossary used when showing word matches.

.. _category:

Category
--------

Categories are there to give structure to components within a project. You can
nest them to achieve a more complex structure.

.. _markup:

Template markup
---------------

Weblate uses simple markup language in several places where text rendering is
needed. It is based on :doc:`django:ref/templates/language`, so it can be quite
powerful.

Currently it is used in:

* Commit message formatting, see :ref:`component`
* Several add-ons
    * :ref:`addon-weblate.discovery.discovery`
    * :ref:`addon-weblate.generate.generate`
    * :ref:`addon-script`

There following variables are available in the component templates:

``{{ language_code }}``
    Language code
``{{ language_name }}``
    Language name
``{{ component_name }}``
    Component name
``{{ component_slug }}``
    Component slug
``{{ project_name }}``
    Project name
``{{ project_slug }}``
    Project slug
``{{ url }}``
    Translation URL
``{{ filename }}``
    Translation filename
``{{ stats }}``
    Translation stats, this has further attributes, examples below.
``{{ stats.all }}``
    Total strings count
``{{ stats.fuzzy }}``
    Count of strings needing review
``{{ stats.fuzzy_percent }}``
    Percent of strings needing review
``{{ stats.translated }}``
    Translated strings count
``{{ stats.translated_percent }}``
    Translated strings percent
``{{ stats.allchecks }}``
    Number of strings with failing checks
``{{ stats.allchecks_percent }}``
    Percent of strings with failing checks
``{{ author }}``
    Author of current commit, available only in the commit scope.
``{{ addon_name }}``
    Name of currently executed add-on, available only in the add-on commit message.

The following variables are available in the repository browser or editor templates:

``{{branch}}``
   current branch
``{{line}}``
   line in file
``{{filename}}``
   filename, you can also strip leading parts using the ``parentdir`` filter, for example ``{{filename|parentdir}}``

.. hint::

   In some places additional variables can be available, see :ref:`addon-weblate.discovery.discovery`.

You can combine them with filters:

.. code-block:: django

    {{ component|title }}

You can use conditions:

.. code-block:: django

    {% if stats.translated_percent > 80 %}Well translated!{% endif %}

There is additional tag available for replacing characters:

.. code-block:: django

    {% replace component "-" " " %}

You can combine it with filters:

.. code-block:: django

    {% replace component|capfirst "-" " " %}

There are also additional filter to manipulate with filenames:

.. code-block:: django

    Directory of a file: {{ filename|dirname }}
    File without extension: {{ filename|stripext }}
    File in parent dir: {{ filename|parentdir }}
    It can be used multiple times:  {{ filename|parentdir|parentdir }}

...and other Django template features.

.. _import-speed:

Importing speed
---------------

Fetching VCS repository and importing translations to Weblate can be a lengthy
process, depending on size of your translations. Here are some tips:

Optimize configuration
++++++++++++++++++++++

The default configuration is useful for testing and debugging Weblate, while
for a production setup, you should do some adjustments. Many of them have quite
a big impact on performance. Please check :ref:`production` for more details,
especially:

* Configure Celery for executing background tasks (see :ref:`celery`)
* :ref:`production-cache`
* :ref:`production-database`
* :ref:`production-debug`

Check resource limits
+++++++++++++++++++++

If you are importing huge translations or repositories, you might be hit by
resource limitations of your server.

* Check the amount of free memory, having translation files cached by the operating system will greatly improve performance.
* Disk operations might be bottleneck if there is a lot of strings to process—the disk is pushed by both Weblate and the database.
* Additional CPU cores might help improve performance of background tasks (see :ref:`celery`).

Disable unneeded checks
+++++++++++++++++++++++++

Some quality checks can be quite expensive, and if not needed,
can save you some time during import if omitted. See :setting:`CHECK_LIST` for
info on configuration.

.. _autocreate:

Automatic creation of components
--------------------------------

In case your project has dozen of translation files (e.g. for different
gettext domains, or parts of Android apps), you might want to import them
automatically. This can either be achieved from the command-line by using
:wladmin:`import_project` or :wladmin:`import_json`, or by installing the
:ref:`addon-weblate.discovery.discovery` add-on.

To use the add-on, you first need to create a component for one translation
file (choose the one that is the least likely to be renamed or removed in future),
and install the add-on on this component.

For the management commands, you need to create a project which will contain all
components and then run :wladmin:`import_project` or
:wladmin:`import_json`.

.. seealso::

   :ref:`manage`,
   :ref:`addon-weblate.discovery.discovery`
