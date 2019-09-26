Translation projects
====================

Translation organization
------------------------

Weblate organizes translatable content into a tree-like structure. The bottom level
object is :ref:`project`, which should hold all translations belonging
together (for example translation of an application in several versions
and/or accompanying documentation). On the level above, :ref:`component`, which is
actually the component to translate. Here you define the VCS repository to use, and
the mask of files to translate. Above :ref:`component` there are individual
translations, handled automatically by Weblate as translation
files (which match the mask defined in :ref:`component`) appear in the VCS repository.

All translation components need to be available as VCS repositories, and are
organized in a project/component structure.

Weblate supports a wide range of translation formats (both bilingual and
monolingual ones) supported by Translate Toolkit, see :ref:`formats` for more
info.

.. note::

    You can share cloned VCS repositories using :ref:`internal-urls`. Using
    this feature is highly recommended when you have many
    components sharing the same VCS. It improves performance and decreases
    the required disk space.

.. _adding-projects:

Adding translation projects and components
------------------------------------------

.. versionchanged:: 3.2

   Since the 3.2 release the interface for adding projects and components is
   included in Weblate, and no longer requires you to use
   :ref:`admin-interface`.

.. versionchanged:: 3.4

   As of 3.4, the process of adding components is multi staged, with
   automated discovery of most parameters.

Based on your permissions, you can create new translation projects
and components in Weblate. It is always permitted for superusers, and if your
instance uses billing (e.g. like https://hosted.weblate.org/ see
:ref:`billing`), you can also create those based on your plans allowance.

You can view your current billing plan on a separate page:

.. image:: /images/user-billing.png

The project creation can be initiated from there, or using the menu in the navigation
bar, filling in basic info about the translation project to complete addition of it:

.. image:: /images/user-add-project.png

After creating the project, you are taken directly to the project page:

.. image:: /images/user-add-project-done.png

Creating a new translation component can be initiated via a single click there.
The process of creating a component is multi-staged and automatically detects most
translation parameters.

Once you have existing translation components, you can also easily add new ones
for additional files or branches using same repository.

First you need to fill in name and repository location:

.. image:: /images/user-add-component-init.png

On the next page, you are presented with a list of discovered translatable resources:

.. image:: /images/user-add-component-discovery.png

As a last step, you review the translation component info and fill
in optional details:

.. image:: /images/user-add-component.png

.. seealso::

      :ref:`admin-interface`,
      :ref:`project`,
      :ref:`component`

.. _project:

Project configuration
---------------------

To add a new component for translation, you need to create a translation project first.
The project is like a shelf, in which real translations are stacked. All
components in the same project share suggestions and their dictionary; the
translations are also automatically propagated through all components in a single
project (unless turned off in the component configuration).

The project has only a few attributes that informs translators of it:

Project website
    URL where translators can find more info about the project.
Mailing list
    Mailing list where translators can discuss or comment translations.
Translation instructions
    URL to more site with more detailed instructions for translators.
Set Language-Team header
    Whether Weblate should manage the ``Language-Team`` header (this is a
    :ref:`gettext` only feature right now).
Use shared translation memory
    Whether to use shared translation memory, see :ref:`shared-tm` for more details.
Access control
    Configure per project access control, see :ref:`acl` for more details.
Enable reviews
    Enable review workflow, see :ref:`reviews`.
Enable hooks
    Whether unauthenticated :ref:`hooks` are to be used for this repository.
Source language
    Language used for source strings in all components. Change this if you are
    translating from something else than English.

.. note::

    Most of the fields can be edited by project owners or managers, in the
    Weblate interface.

Adjusting interaction
+++++++++++++++++++++

There are also additional features which you can control, like automatic
pushing of changes (see also :ref:`push-changes`) or maintainership of the
``Language-Team`` header.

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

Version control system
    VCS to use, see :ref:`vcs` for details.
Source code repository
    VCS repository used to pull changes, see :ref:`vcs-repos` for more details.

    This can either be a real VCS URL or ``weblate://project/component``
    indicating that the repository should be shared with another component.
    See :ref:`internal-urls` for more details.
Repository push URL
    Repository URL used for pushing. This is completely optional and push
    support is turned off when this is empty. See :ref:`vcs-repos` for more
    details on how to specify a repository URL.
Repository browser
    URL of repository browser used to display source files (location of used messages).
    When empty, no such links will be generated. You can use :ref:`markup`.

    For example on GitHub, use something like
    ``https://github.com/WeblateOrg/hello/blob/{{branch}}/{{filename}}#L{{line}}``.
Exported repository URL
    URL where changes made by Weblate are exported. This is important when
    :ref:`continuous-translation` is not used, or when there is a need to manually
    merge changes. You can use :ref:`git-exporter` to automate this for Git
    repositories.
Repository branch
    Which branch to checkout from the VCS, and where to look for translations.
File mask
    Mask of files to translate, including path. It should include one "*"
    replacing language code (see :ref:`languages` for info on how this is
    processed). In case your repository contains more than one translation
    file (e.g. more Gettext domains), you need to create a component for
    each of them.

    For example ``po/*.po`` or ``locale/*/LC_MESSAGES/django.po``.

    In case your filename contains special characters such as ``[``, ``]``, these need
    to be escaped as ``[[]`` or ``[]]``.
Monolingual base language file
    Base file containing string definitions for :ref:`monolingual`.
Edit base file
    Whether to allow editing the base file for :ref:`monolingual`.
Template for new translations
    Base file used to generate new translations, e.g. ``.pot`` file with Gettext,
    see :ref:`new-translations` for more info.
File format
    Translation file format, see also :ref:`formats`.
Source string bug report address
    Email address used for reporting upstream bugs. This address will also receive
    notification about any source string comments made in Weblate.
Locked
    You can lock the translation to prevent updates by users.
Allow translation propagation
    You can turn off propagation of translations to this component from other
    components within same project. This really depends on what you are
    translating, sometimes it's desirable to have make use of a translation more than once.

    It's usually a good idea to turn this off for monolingual translations, unless
    you are using the same IDs across the whole project.
Save translation history
    Whether to store a history of translation changes in the database.
Enable suggestions
    Whether translation suggestions are accepted for this component.
Suggestion voting
    Turns on votecasting for suggestions, see :ref:`voting`.
Autoaccept suggestions
    Automatically accept voted suggestions, see :ref:`voting`.
Translation flags
    Customization of quality checks and other Weblate behavior, see :ref:`custom-checks`.
Translation license
    License of the translation, (does not need to be the same as the source code license).
License URL
    URL where users can find the actual text of a license in full.
New translation
    How to handle requests for creation of new languages. See :ref:`adding-translation`.
Language code style
   Customize language code used to generate the filename for translations
   created by Weblate, see :ref:`new-translations` for more details.
Merge style
    You can configure how updates from the upstream repository are handled.
    This might not be supported for some VCSs. See :ref:`merge-rebase` for
    more details.
Commit message
    Message used when committing a translation, see :ref:`markup`, default can be 
    changed by :setting:`DEFAULT_COMMIT_MESSAGE`.
Committer name
    Name of the committer used for Weblate commits, the author will always be the
    real translator. On some VCSs this might be not supported. Default value
    can be changed by :setting:`DEFAULT_COMMITER_NAME`.
Committer e-mail
    Email of committer used for Weblate commits, the author will always be the
    real translator. On some VCSs this might be not supported. Default value
    can be changed by :setting:`DEFAULT_COMMITER_EMAIL`.
Push on commit
    Whether committed changes should be automatically pushed to the upstream
    repository. When enabled, the push is initiated once Weblate commits
    changes to its internal repository (see :ref:`lazy-commit`). To actually
    enable pushing :guilabel:`Repository push URL` has to be configured as
    well.
Age of changes to commit
    Sets how old changes (in hours) are to get before they are committed by
    background task or :djadmin:`commit_pending` management command.  All
    changes in a component are committed once there is at least one older than
    this period.  The Default value can be changed by
    :setting:`COMMIT_PENDING_HOURS`.
Language filter
    Regular expression used to filter the translation when scanning for
    file mask. This can be used to limit the list of languages managed by Weblate
    (e.g. ``^(cs|de|es)$`` will include only these languages. Please note
    that you need to list language codes as they appear in the filename.

.. note::

    Most of the fields can be edited by project owners or managers, in the
    Weblate interface.

.. seealso::

   :ref:`faq-vcs`, :ref:`alerts`

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
    Transaltion filename
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
   filename, you can also strip leading parts using the parentdir filter, for example ``{{filename|parentdir}}``

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
* Disk operations might be bottleneck if there is a lot of strings to process - the disk is pushed by both Weblate and the database.
* Additional CPU cores might help improve performance of background tasks (see :ref:`celery`).

Disable unneeded checks
+++++++++++++++++++++++++

Some quality checks can be quite expensive, and if not needed,
can save you some time during import if omitted. See :setting:`CHECK_LIST` for more
info on how to configure this.

.. _autocreate:

Automatic creation of components
--------------------------------

In case your project has dozen of translation files (e.g. for different
Gettext domains, or parts of Android apps), you might want to import them
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

.. _fulltext:

Fulltext search
---------------

Fulltext search is based on Whoosh. It is processed in the background if Celery is
set up. This leads to faster site response, and a less fragmented
index with the added cost that it might be slightly outdated.

.. seealso::

   :ref:`faq-ft-slow`, :ref:`faq-ft-lock`, :ref:`faq-ft-space`
