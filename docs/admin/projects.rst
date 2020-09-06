Translation projects
====================

Translation organization
------------------------

Weblate organizes translatable VCS content of project/components into a tree-like structure.

* The bottom level object is :ref:`project`, which should hold all translations belonging
  together (for example translation of an application in several versions
  and/or accompanying documentation).

* On the level above, :ref:`component`, which is
  actually the component to translate, you define the VCS repository to use, and
  the mask of files to translate.

* Above :ref:`component` there are individual translations, handled automatically by Weblate as translation
  files (which match the mask defined in :ref:`component`) appear in the VCS repository.

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

.. versionchanged:: 3.2

   An interface for adding projects and components is included,
   and you no longer have to use :ref:`admin-interface`.

.. versionchanged:: 3.4

   The process of adding components is now multi staged,
   with automated discovery of most parameters.

Based on your permissions, new translation projects and components can be
created. It is always permitted for users with the :guilabel:`Add new projects`
permission, and if your instance uses billing (e.g. like
https://hosted.weblate.org/ see :ref:`billing`), you can also create those
based on your plans allowance from the user account that manages billing.

You can view your current billing plan on a separate page:

.. image:: /images/user-billing.png

The project creation can be initiated from there, or using the menu in the navigation
bar, filling in basic info about the translation project to complete addition of it:

.. image:: /images/user-add-project.png

After creating the project, you are taken directly to the project page:

.. image:: /images/user-add-project-done.png

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
    Upload single document and translate that.
Start from scratch
    Create blank translation project and add strings manually.

Once you have existing translation components, you can also easily add new ones
for additional files or branches using same repository.

First you need to fill in name and repository location:

.. image:: /images/user-add-component-init.png

On the next page, you are presented with a list of discovered translatable resources:

.. image:: /images/user-add-component-discovery.png

As a last step, you review the translation component info and fill in optional details:

.. image:: /images/user-add-component.png

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

These basic attributes set up and inform translators of a project:

.. _project-name:

Project name
++++++++++++

Verbose project name, used to display the project name.

.. _project-slug:

Project slug
++++++++++++

Project name suitable for URLs.

.. _project-web:

Project website
+++++++++++++++

URL where translators can find more info about the project.

.. _project-mail:

Mailing list
++++++++++++

Mailing list where translators can discuss or comment translations.

.. _project-instructions:

Translation instructions
++++++++++++++++++++++++

URL to more site with more detailed instructions for translators.

.. _project-set_language_team:

Set Language-Team header
++++++++++++++++++++++++

Whether Weblate should manage the ``Language-Team`` header (this is a
:ref:`gettext` only feature right now).

.. _project-use_shared_tm:

Use shared translation memory
+++++++++++++++++++++++++++++

Whether to use shared translation memory, see :ref:`shared-tm` for more details.

.. _project-contribute_shared_tm:

Contribute to shared translation memory
+++++++++++++++++++++++++++++++++++++++

Whether to contribute to shared translation memory, see :ref:`shared-tm` for more details.

.. _project-access_control:

Access control
++++++++++++++

Configure per project access control, see :ref:`acl` for more details.

Default value can be changed by :setting:`DEFAULT_ACCESS_CONTROL`.

.. _project-translation_review:

Enable reviews
++++++++++++++

Enable review workflow for translations, see :ref:`reviews`.

.. _project-source_review:

Enable source reviews
+++++++++++++++++++++

Enable review workflow for source strings, see :ref:`source-reviews`.

.. _project-enable_hooks:

Enable hooks
++++++++++++

Whether unauthenticated :ref:`hooks` are to be used for this repository.

.. _project-source_language:

Source language
+++++++++++++++

Language used for source strings in all components. Change this if you are
translating from something else than English.

.. hint::

   In case you are translating bilingual files from English, but want to be
   able to do fixes in the English translation as well, you might want to
   choose :guilabel:`English (Developer)` as a source language. To avoid
   conflict between name of the source language and existing translation.

   For monolingual translations, you can use intermediate translation in this
   case, see :ref:`component-intermediate`.

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
get a consistent view in Weblate.

The typical use case might be mapping American English to English: ``en_US:en``

Multiple mappings to be separated by comma: ``en_GB:en,en_US:en``

.. hint::

   The language codes are mapped when matching the translation files and the
   matches are case sensitive, so make sure you use the source language codes
   in same form as used in the filenames.

.. seealso::

    :ref:`language-parsing-codes`

.. _component:

Component configuration
-----------------------

A component is a grouping of something for translation. You enter a VCS repository location
and file mask for which files you want translated, and Weblate automatically fetches from this VCS,
and finds all matching translatable files.

You can find some examples of typical configurations in the :ref:`formats`.

.. note::

    It is recommended to keep translation components to a reasonable size - split
    the translation by anything that makes sense in your case (individual
    apps or addons, book chapters or websites).

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

Repository URL used for pushing. This setting is used only for :ref:`vcs-git`
and :ref:`vcs-mercurial` and push support is turned off for these when this is
empty.

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

In case your paths are relative to different folder, you might want to strip leading
directory by ``parentdir`` filter (see :ref:`markup`):
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

.. _component-push_branch:

Push branch
+++++++++++

Branch for pushing changes, leave empty to use :ref:`component-branch`.

.. note::

   This is currently only supported for Git and GitHub, it is ignored for other
   VCS integrations.

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

Whether to allow editing the base file for :ref:`monolingual`.

.. _component-intermediate:

Intermediate language file
++++++++++++++++++++++++++

Intermediate language file for :ref:`monolingual`. In most cases this is a
translation file provided by developers and is used when creating actual source
strings.

When set, the source translation is based on this file, but all others are
based on :ref:`component-template`. In case the string is not translated in
source translation, translating to other languages is prohibited. This provides
:ref:`source-quality-gateway`.

.. seealso::

   :ref:`source-quality-gateway`,
   :ref:`bimono`,
   :ref:`faq-duplicate-files`

.. _component-new_base:

Template for new translations
+++++++++++++++++++++++++++++

Base file used to generate new translations, e.g. ``.pot`` file with gettext.

.. hint::

   In many monolingual formats Weblate starts with blank file by default. Use
   this in case you want to have all strings present with empty value when
   creating new translation.

.. seealso::

   :ref:`new-translations`,
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

.. _component-allow_translation_propagation:

Allow translation propagation
+++++++++++++++++++++++++++++

You can turn off propagation of translations to this component from other
components within same project. This really depends on what you are
translating, sometimes it's desirable to have make use of a translation more than once.

It's usually a good idea to turn this off for monolingual translations, unless
you are using the same IDs across the whole project.

Default value can be changed by :setting:`DEFAULT_TRANSLATION_PROPAGATION`.

.. _component-enable_suggestions:

Enable suggestions
++++++++++++++++++

Whether translation suggestions are accepted for this component.

.. _component-suggestion_voting:

Suggestion voting
+++++++++++++++++

Turns on votecasting for suggestions, see :ref:`voting`.

.. _component-suggestion_autoaccept:

Autoaccept suggestions
++++++++++++++++++++++

Automatically accept voted suggestions, see :ref:`voting`.

.. _component-check_flags:

Translation flags
+++++++++++++++++

Customization of quality checks and other Weblate behavior, see :ref:`custom-checks`.

.. _component-enforced_checks:

Enforced checks
+++++++++++++++

List of checks which can not be ignored, see :ref:`enforcing-checks`.

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

.. seealso::

   :ref:`adding-translation`.

.. _component-language_code_style:

Language code style
+++++++++++++++++++

Customize language code used to generate the filename for translations
created by Weblate, see :ref:`new-translations` for more details.

.. _component-merge_style:

Merge style
+++++++++++

You can configure how updates from the upstream repository are handled.
This might not be supported for some VCSs. See :ref:`merge-rebase` for
more details.

Default value can be changed by :setting:`DEFAULT_MERGE_STYLE`.

.. _component-commit_message:
.. _component-add_message:
.. _component-delete_message:
.. _component-merge_message:
.. _component-addon_message:

Commit, add, delete, merge and addon messages
+++++++++++++++++++++++++++++++++++++++++++++

Message used when committing a translation, see :ref:`markup`.

Default value can be changed by :setting:`DEFAULT_ADD_MESSAGE`,
:setting:`DEFAULT_ADDON_MESSAGE`, :setting:`DEFAULT_COMMIT_MESSAGE`,
:setting:`DEFAULT_DELETE_MESSAGE`, :setting:`DEFAULT_MERGE_MESSAGE`.

.. _component-committer_name:

Committer name
++++++++++++++

Name of the committer used for Weblate commits, the author will always be the
real translator. On some VCSs this might be not supported.

Default value can be changed by :setting:`DEFAULT_COMMITER_NAME`.

.. _component-committer_email:

Committer e-mail
++++++++++++++++

Email of committer used for Weblate commits, the author will always be the
real translator. On some VCSs this might be not supported. The default value
can be changed in :setting:`DEFAULT_COMMITER_EMAIL`.

.. _component-push_on_commit:

Push on commit
++++++++++++++

Whether committed changes should be automatically pushed to the upstream
repository. When enabled, the push is initiated once Weblate commits
changes to its internal repository (see :ref:`lazy-commit`). To actually
enable pushing :guilabel:`Repository push URL` has to be configured as
well.

.. _component-commit_pending_age:

Age of changes to commit
++++++++++++++++++++++++

Sets how old changes (in hours) are to get before they are committed by
background task or :djadmin:`commit_pending` management command.  All
changes in a component are committed once there is at least one older than
this period.

Default value can be changed by :setting:`COMMIT_PENDING_HOURS`.

.. _component-auto_lock_error:

Lock on error
+++++++++++++

Enables locking the component on repository error (failed pull, push or merge).
Locking in this situation avoids adding another conflict which would have to be
resolved manually.

The component will be automatically unlocked once there are no repository
errors left.

.. _component-language_regex:

Language filter
+++++++++++++++

Regular expression used to filter the translation when scanning for filemask.
This can be used to limit the list of languages managed by Weblate.

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

    Most of the fields can be edited by project owners or managers, in the
    Weblate interface.

.. seealso::

   :ref:`faq-vcs`, :ref:`alerts`

.. _component-priority:

Priority
+++++++++

Components with higher priority are offered first to translators.

.. _component-restricted:

Restricted access
+++++++++++++++++

By default the component is visible to anybody who has access to the project,
even if the person can not perform any changes in the component. This makes it
easier to keep translation consistency within the project.

Enable this in case you want to grant access to this component explicitly -
the project level permissions will not apply and you will have to specify
component or component list level permission in order to grant access.

Default value can be changed by :setting:`DEFAULT_RESTRICTED_COMPONENT`.

.. hint::

   This applies to project managers as well - please make sure you will not
   loose access to the component after toggling the status.

.. _markup:

Template markup
---------------

Weblate uses simple markup language in several places where text rendering is
needed. It is based on :doc:`django:ref/templates/language`, so it can be quite
powerful.

Currently it is used in:

* Commit message formatting, see :ref:`component`
* Several addons
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
    Name of currently executed addon, available only in the addon commit message.

The following variables are available in the repository browser or editor templates:

``{{branch}}``
   current branch
``{{line}}``
   line in file
``{{filename}}``
   filename, you can also strip leading parts using the ``parentdir`` filter, for example ``{{filename|parentdir}}``

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
automatically. This can either be achieved from the command line by using
:djadmin:`import_project` or :djadmin:`import_json`, or by installing the
:ref:`addon-weblate.discovery.discovery` addon.

To use the addon, you first need to create a component for one translation
file (choose the one that is the least likely to be renamed or removed in future),
and install the addon on this component.

For the management commands, you need to create a project which will contain all
components and then run :djadmin:`import_project` or
:djadmin:`import_json`.

.. seealso::

   :ref:`manage`,
   :ref:`addon-weblate.discovery.discovery`
