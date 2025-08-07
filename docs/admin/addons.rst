..
   Partly generated using ./manage.py list_addons

.. _addons:

Add-ons
=======

Add-ons provide ways to customize and automate the translation workflow.
Admins can add and manage add-ons from the :guilabel:`Operations` ↓ :guilabel:`Add-ons` menu of each respective
translation project or component. Add-ons can be also installed site-wide in :ref:`management-interface`.

.. hint::

   You can also configure add-ons using :ref:`API <addons-api>`,
   :setting:`DEFAULT_ADDONS`, or :wladmin:`install_addon`.

.. image:: /screenshots/addons.webp

Events that trigger add-ons
+++++++++++++++++++++++++++

.. _addon-event-install:

Add-on installation
-------------------

Triggered when add-on is being installed.

.. _addon-event-component-update:

Component update
----------------

Triggered whenever a change happens in a component such as:

* Strings are changed in the repository.
* A string is added.
* A new translation is added.

.. _addon-event-daily:

Daily
-----

Triggered daily, but add-ons usually split the daily load between components depending on :setting:`BACKGROUND_TASKS`.

.. _addon-event-event-change:

Event change
------------

Triggered after a Change event is created.

.. _addon-event-repository-post-add:

Repository post-add
-------------------

Triggered just after the new translation is added and committed.

.. _addon-event-repository-post-commit:

Repository post-commit
----------------------

Triggered just after the changes are committed.


.. _addon-event-repository-post-push:

Repository post-push
--------------------

Triggered just after the repository is pushed upstream.

.. _addon-event-repository-post-update:

Repository post-update
----------------------

Triggered whenever new changes are pulled from the upstream repository.

.. _addon-event-repository-pre-commit:

Repository pre-commit
---------------------

Triggered just before the changes are committed.

.. _addon-event-repository-pre-push:

Repository pre-push
-------------------

Triggered just before the repository is pushed upstream.

.. _addon-event-repository-pre-update:

Repository pre-update
---------------------

Triggered just before the repository update is attempted.

.. _addon-event-storage-post-load:

Storage post-load
-----------------

Triggered when file is parsed by Weblate.

.. _addon-event-unit-post-save:

Unit post-save
--------------

Triggered just after the string is saved.

.. _addon-event-unit-pre-create:

Unit pre-create
---------------

Triggered just after the newly created string is saved.


Built-in add-ons
++++++++++++++++


.. _addon-weblate.autotranslate.autotranslate:

Automatic translation
---------------------

:Add-on ID: ``weblate.autotranslate.autotranslate``
:Configuration: +-----------------+----------------------------------+------------------------------------------------------------------------------------------------------+
                | ``mode``        | Automatic translation mode       | .. list-table:: Available choices:                                                                   |
                |                 |                                  |    :width: 100%                                                                                      |
                |                 |                                  |                                                                                                      |
                |                 |                                  |    * - ``suggest``                                                                                   |
                |                 |                                  |      - Add as suggestion                                                                             |
                |                 |                                  |    * - ``translate``                                                                                 |
                |                 |                                  |      - Add as translation                                                                            |
                |                 |                                  |    * - ``fuzzy``                                                                                     |
                |                 |                                  |      - Add as "Needing edit"                                                                         |
                +-----------------+----------------------------------+------------------------------------------------------------------------------------------------------+
                | ``filter_type`` | Search filter                    | Please note that translating all strings will discard all existing translations.                     |
                |                 |                                  |                                                                                                      |
                |                 |                                  | .. list-table:: Available choices:                                                                   |
                |                 |                                  |    :width: 100%                                                                                      |
                |                 |                                  |                                                                                                      |
                |                 |                                  |    * - ``all``                                                                                       |
                |                 |                                  |      - All strings                                                                                   |
                |                 |                                  |    * - ``nottranslated``                                                                             |
                |                 |                                  |      - Untranslated strings                                                                          |
                |                 |                                  |    * - ``todo``                                                                                      |
                |                 |                                  |      - Unfinished strings                                                                            |
                |                 |                                  |    * - ``fuzzy``                                                                                     |
                |                 |                                  |      - Strings marked for edit                                                                       |
                |                 |                                  |    * - ``check:inconsistent``                                                                        |
                |                 |                                  |      - Failing check: Inconsistent                                                                   |
                |                 |                                  |    * - ``check:translated``                                                                          |
                |                 |                                  |      - Failing check: Has been translated                                                            |
                +-----------------+----------------------------------+------------------------------------------------------------------------------------------------------+
                | ``auto_source`` | Source of automated translations | .. list-table:: Available choices:                                                                   |
                |                 |                                  |    :width: 100%                                                                                      |
                |                 |                                  |                                                                                                      |
                |                 |                                  |    * - ``others``                                                                                    |
                |                 |                                  |      - Other translation components                                                                  |
                |                 |                                  |    * - ``mt``                                                                                        |
                |                 |                                  |      - Machine translation                                                                           |
                +-----------------+----------------------------------+------------------------------------------------------------------------------------------------------+
                | ``component``   | Component                        | Enter slug of a component to use as source, keep blank to use all components in the current project. |
                +-----------------+----------------------------------+------------------------------------------------------------------------------------------------------+
                | ``engines``     | Machine translation engines      |                                                                                                      |
                +-----------------+----------------------------------+------------------------------------------------------------------------------------------------------+
                | ``threshold``   | Score threshold                  |                                                                                                      |
                +-----------------+----------------------------------+------------------------------------------------------------------------------------------------------+
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-component-update`, :ref:`addon-event-daily`

Automatically translates strings using machine translation or other components.

.. seealso::

   * :ref:`auto-translation`
   * :ref:`translation-consistency`
   * :ref:`mt-translation-services-priority`

.. _addon-weblate.cdn.cdnjs:

JavaScript localization CDN
---------------------------

.. versionadded:: 4.2

:Add-on ID: ``weblate.cdn.cdnjs``
:Configuration: +------------------+---------------------------------+-------------------------------------------------------------------------------------------+
                | ``threshold``    | Translation threshold           | The percentage of translated strings that must be present for translation to be included. |
                +------------------+---------------------------------+-------------------------------------------------------------------------------------------+
                | ``css_selector`` | CSS selector                    | CSS selector to detect localizable elements.                                              |
                +------------------+---------------------------------+-------------------------------------------------------------------------------------------+
                | ``cookie_name``  | Language cookie name            | Name of cookie which stores language preference.                                          |
                +------------------+---------------------------------+-------------------------------------------------------------------------------------------+
                | ``files``        | Extract strings from HTML files | List of filenames in current repository or remote URLs to parse for translatable strings. |
                +------------------+---------------------------------+-------------------------------------------------------------------------------------------+
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-daily`, :ref:`addon-event-repository-post-commit`, :ref:`addon-event-repository-post-update`

Publishes translations into content delivery network for use in JavaScript or
HTML localization.

Can be used to localize static HTML pages, or
to load localization in the JavaScript code.

Generates a unique URL for your component you can include in
HTML pages to localize them. See :ref:`weblate-cdn` for more details.

.. note::

   This add-on requires additional configuration on the Weblate server.
   :setting:`LOCALIZE_CDN_PATH` configures where generated files will be
   written (on a filesystem), and :setting:`LOCALIZE_CDN_URL` defines where
   they will be served (URL). Serving of the files is not done by Weblate and
   has to be set up externally (typically using a CDN service).

   This add-on is configured on :guilabel:`Hosted Weblate` and serves the files
   via ``https://weblate-cdn.com/``.

.. seealso::

    * :ref:`cdn-addon-config`
    * :ref:`weblate-cdn`
    * :ref:`cdn-addon-extract`
    * :ref:`cdn-addon-html`

.. _addon-weblate.cleanup.blank:

Remove blank strings
--------------------

.. versionadded:: 4.4

:Add-on ID: ``weblate.cleanup.blank``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-repository-post-commit`, :ref:`addon-event-repository-post-update`

Removes strings without a translation from translation files.

Use this to not have any empty strings in translation files (for
example if your localization library displays them as missing instead
of falling back to the source string).

.. seealso::

   :ref:`faq-cleanup`

.. _addon-weblate.cleanup.generic:

Cleanup translation files
-------------------------

:Add-on ID: ``weblate.cleanup.generic``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-repository-post-update`, :ref:`addon-event-repository-pre-commit`

Update all translation files to match the monolingual base file. For most file
formats, this means removing stale translation keys no longer present in the
base file.

For formats containing additional content besides translation strings (such as
:ref:`html`, :ref:`winrc`, or :ref:`odf`) this also brings the translation file
in sync with the base file.

.. seealso::

   :ref:`faq-cleanup`

.. _addon-weblate.consistency.languages:

Add missing languages
---------------------

:Add-on ID: ``weblate.consistency.languages``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-daily`, :ref:`addon-event-repository-post-add`

Ensures a consistent set of languages is used for all components within a
project.

Missing languages are checked once every 24 hours, and when new languages
are added in Weblate.

Unlike most others, this add-on affects the whole project.

.. hint::

   Auto-translate the newly added strings with
   :ref:`addon-weblate.autotranslate.autotranslate`.

.. _addon-weblate.discovery.discovery:

Component discovery
-------------------

:Add-on ID: ``weblate.discovery.discovery``
:Configuration: +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``match``                 | Regular expression to match translation files against           |                                                                                                                                                             |
                +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``file_format``           | File format                                                     |                                                                                                                                                             |
                +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``name_template``         | Customize the component name                                    |                                                                                                                                                             |
                +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``base_file_template``    | Define the monolingual base filename                            | Leave empty for bilingual translation files.                                                                                                                |
                +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``new_base_template``     | Define the base file for new translations                       | Filename of file used for creating new translations. For gettext choose .pot file.                                                                          |
                +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``intermediate_template`` | Intermediate language file                                      | Filename of intermediate translation file. In most cases this is a translation file provided by developers and is used when creating actual source strings. |
                +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``language_regex``        | Language filter                                                 | Regular expression to filter translation files against when scanning for file mask.                                                                         |
                +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``copy_addons``           | Clone add-ons from the main component to the newly created ones |                                                                                                                                                             |
                +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``remove``                | Remove components for inexistent files                          |                                                                                                                                                             |
                +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``confirm``               | I confirm the above matches look correct                        |                                                                                                                                                             |
                +---------------------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------+
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-repository-post-update`

Automatically adds or removes project components based on file changes in the
version control system.

The matching is done using regular expressions
enabling complex configuration, but some knowledge is required to do so.
Some examples for common use cases can be found in
the add-on help section.

The regular expression to match translation files has to contain two named
groups to match component and language. All named groups in the regular
expression can be used as variables in the template fields.

You can use Django template markup in all filename fields, for example:

``{{ component }}``
   Component filename match
``{{ component|title }}``
   Component filename with upper case first letter
``{{ path }}: {{ component }}``
   Custom match group from the regular expression

Once you hit :guilabel:`Save`, a preview of matching components will be presented,
from where you can check whether the configuration actually matches your needs:

.. image:: /screenshots/addon-discovery.webp

Component discovery examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

One folder per language
#######################

One folder per language containing translation files for components.

Regular expression:
   ``(?P<language>[^/.]*)/(?P<component>[^/]*)\.po``
Matching files:
   - :file:`cs/application.po`
   - :file:`cs/website.po`
   - :file:`de/application.po`
   - :file:`de/website.po`

Gettext locales layout
######################

Usual structure for storing gettext PO files.

Regular expression:
   ``locale/(?P<language>[^/.]*)/LC_MESSAGES/(?P<component>[^/]*)\.po``
Matching files:
   - :file:`locale/cs/LC_MESSAGES/application.po`
   - :file:`locale/cs/LC_MESSAGES/website.po`
   - :file:`locale/de/LC_MESSAGES/application.po`
   - :file:`locale/de/LC_MESSAGES/website.po`

Complex filenames
#################

Using both component and language name within filename.

Regular expression:
   ``src/locale/(?P<component>[^/]*)\.(?P<language>[^/.]*)\.po``
Matching files:
   - :file:`src/locale/application.cs.po`
   - :file:`src/locale/website.cs.po`
   - :file:`src/locale/application.de.po`
   - :file:`src/locale/website.de.po`

Repeated language code
######################

Using language in both path and filename.

Regular expression:
   ``locale/(?P<language>[^/.]*)/(?P<component>[^/]*)/(?P=language)\.po``
Matching files:
   - :file:`locale/cs/application/cs.po`
   - :file:`locale/cs/website/cs.po`
   - :file:`locale/de/application/de.po`
   - :file:`locale/de/website/de.po`


Split Android strings
#####################

Android resource strings, split into several files.

Regular expression:
   ``res/values-(?P<language>[^/.]*)/strings-(?P<component>[^/]*)\.xml``
Matching files:
   - :file:`res/values-cs/strings-about.xml`
   - :file:`res/values-cs/strings-help.xml`
   - :file:`res/values-de/strings-about.xml`
   - :file:`res/values-de/strings-help.xml`

Matching multiple paths
#######################

Multi-module Maven project with Java properties translations.

Regular expression:
   ``(?P<originalHierarchy>.+/)(?P<component>[^/]*)/src/main/resources/ApplicationResources_(?P<language>[^/.]*)\.properties``
Component name:
   ``{{ originalHierarchy }}: {{ component }}``
Matching files:
   - :file:`parent/module1/submodule/src/main/resources/ApplicationResources_fr.properties`
   - :file:`parent/module1/submodule/src/main/resources/ApplicationResource_es.properties`
   - :file:`parent/module2/src/main/resources/ApplicationResource_de.properties`
   - :file:`parent/module2/src/main/resources/ApplicationResource_ro.properties`


.. hint::

   Component discovery add-on uses :ref:`internal-urls`. It’s a convenient way to share
   VCS setup between multiple components. Linked components use the local repository of
   the main component set up by filling ``weblate://project/main-component``
   into the :ref:`component-repo` field (in :guilabel:`Operations` ↓ :guilabel:`Settings` ↓
   :guilabel:`Version control system`) of each respective component.
   This saves time with configuration and system resources too.

.. hint::

   Ensure the new component contains the full set of translatable languages with
   :ref:`addon-weblate.consistency.languages`.

.. warning::

   To be discovered, a new component must contain a file that matches ``base_file_template``
   **and** at least one file with a name that matches ``match`` -- i.e., the component must
   contain a base language file and at least one existing translation. Otherwise, it will be
   ignored.

.. seealso::

   * :ref:`markup`
   * :wladmin:`import_project`

.. _addon-weblate.flags.bulk:

Bulk edit
---------

:Add-on ID: ``weblate.flags.bulk``
:Configuration: +-------------------+-----------------------------+------------------------------------+
                | ``q``             | Query                       |                                    |
                +-------------------+-----------------------------+------------------------------------+
                | ``state``         | State to set                | .. list-table:: Available choices: |
                |                   |                             |    :width: 100%                    |
                |                   |                             |                                    |
                |                   |                             |    * - ``-1``                      |
                |                   |                             |      - Do not change               |
                |                   |                             |    * - ``10``                      |
                |                   |                             |      - Needs editing               |
                |                   |                             |    * - ``20``                      |
                |                   |                             |      - Translated                  |
                |                   |                             |    * - ``30``                      |
                |                   |                             |      - Approved                    |
                +-------------------+-----------------------------+------------------------------------+
                | ``add_flags``     | Translation flags to add    |                                    |
                +-------------------+-----------------------------+------------------------------------+
                | ``remove_flags``  | Translation flags to remove |                                    |
                +-------------------+-----------------------------+------------------------------------+
                | ``add_labels``    | Labels to add               |                                    |
                +-------------------+-----------------------------+------------------------------------+
                | ``remove_labels`` | Labels to remove            |                                    |
                +-------------------+-----------------------------+------------------------------------+
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-component-update`

Bulk edit flags, labels, or states of strings.

**Examples:**

.. list-table:: Label new strings automatically
    :stub-columns: 1

    * - Search query
      - ``NOT has:label``
    * - Labels to add
      - *recent*

.. list-table:: Marking all :ref:`appstore` changelog strings read-only
    :stub-columns: 1

    * - Search query
      - ``language:en AND key:changelogs/``
    * - Translation flags to add
      - ``read-only``


.. list-table:: Marking certain strings read-only
    :stub-columns: 1

    * - Search query
      - ``source:r"^\`\`[.a-zA-Z0-9_-]*\`\`$" AND language:en``
    * - Translation flags to add
      - ``read-only``

.. seealso::

   * :ref:`bulk-edit`
   * :ref:`custom-checks`
   * :ref:`labels`


.. _addon-weblate.flags.same_edit:

Flag unchanged translations as "Needs editing"
----------------------------------------------

:Add-on ID: ``weblate.flags.same_edit``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-unit-pre-create`

Whenever a new translatable string is imported from the VCS and it matches a
source string, it is flagged as needing editing in Weblate. Especially useful
for file formats that include source strings for untranslated strings.

.. hint::

   You might also want to tighthen the :ref:`check-same` check by adding
   ``strict-same`` flag to :ref:`component-check_flags`.

.. seealso::

   :ref:`states`

.. _addon-weblate.flags.source_edit:

Flag new source strings as "Needs editing"
------------------------------------------

:Add-on ID: ``weblate.flags.source_edit``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-unit-pre-create`

Whenever a new source string is imported from the VCS, it is flagged as needing
editing in Weblate. This way you can easily filter and edit source strings
written by the developers.

.. seealso::

   :ref:`states`

.. _addon-weblate.flags.target_edit:

Flag new translations as "Needs editing"
----------------------------------------

:Add-on ID: ``weblate.flags.target_edit``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-unit-pre-create`

Whenever a new translatable string is imported from the VCS, it is flagged as
needing editing in Weblate. This way you can easily filter and edit
translations created by the developers.

.. seealso::

   :ref:`states`

.. _addon-weblate.generate.fill_read_only:

Fill read-only strings with source
----------------------------------

.. versionadded:: 4.18

:Add-on ID: ``weblate.generate.fill_read_only``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-component-update`, :ref:`addon-event-daily`

Fills in translation of read-only strings with source string.

.. _addon-weblate.generate.generate:

Statistics generator
--------------------

:Add-on ID: ``weblate.generate.generate``
:Configuration: +--------------+---------------------------+--+
                | ``filename`` | Name of generated file    |  |
                +--------------+---------------------------+--+
                | ``template`` | Content of generated file |  |
                +--------------+---------------------------+--+
:Triggers: :ref:`addon-event-repository-pre-commit`

Generates a file containing detailed info about the translation status.

You can use a Django template in both filename and content, see :ref:`markup`
for a detailed markup description.

For example generating a summary file for each translation:

Name of generated file
   ``locale/{{ language_code }}.json``
Content
   .. code-block:: json

      {
         "language": "{{ language_code }}",
         "strings": "{{ stats.all }}",
         "translated": "{{ stats.translated }}",
         "last_changed": "{{ stats.last_changed }}",
         "last_author": "{{ stats.last_author }}",
      }


.. seealso::

    :ref:`markup`

.. _addon-weblate.generate.prefill:

Prefill translation with source
-------------------------------

.. versionadded:: 4.11

:Add-on ID: ``weblate.generate.prefill``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-component-update`, :ref:`addon-event-daily`

Fills in translation strings with source string.

All untranslated strings in the component will be filled with the source
string, and marked as needing edit. Use this when you can not have empty
strings in the translation files.

.. _addon-weblate.generate.pseudolocale:

Pseudolocale generation
-----------------------

.. versionadded:: 4.5

:Add-on ID: ``weblate.generate.pseudolocale``
:Configuration: +----------------------+---------------------------+------------------------------------------------------------------------------------------+
                | ``source``           | Source strings            |                                                                                          |
                +----------------------+---------------------------+------------------------------------------------------------------------------------------+
                | ``target``           | Target translation        | All strings in this translation will be overwritten                                      |
                +----------------------+---------------------------+------------------------------------------------------------------------------------------+
                | ``prefix``           | Prepended static text     |                                                                                          |
                +----------------------+---------------------------+------------------------------------------------------------------------------------------+
                | ``var_prefix``       | Prepended variable text   |                                                                                          |
                +----------------------+---------------------------+------------------------------------------------------------------------------------------+
                | ``suffix``           | Appended static text      |                                                                                          |
                +----------------------+---------------------------+------------------------------------------------------------------------------------------+
                | ``var_suffix``       | Appended variable text    |                                                                                          |
                +----------------------+---------------------------+------------------------------------------------------------------------------------------+
                | ``var_multiplier``   | Variable text multiplier  | How many times to repeat the variable text depending on the length of the source string. |
                +----------------------+---------------------------+------------------------------------------------------------------------------------------+
                | ``include_readonly`` | Include read-only strings |                                                                                          |
                +----------------------+---------------------------+------------------------------------------------------------------------------------------+
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-component-update`, :ref:`addon-event-daily`

Generates a translation by adding prefix and suffix to source strings
automatically.

Pseudolocales are useful to find strings that are not prepared for
localization. This is done by altering all translatable source strings
to make it easy to spot unaltered strings when running the application
in the pseudolocale language.

Finding strings whose localized counterparts might not fit the layout
is also possible.

Using the variable parts makes it possible to look for strings which might not
fit into the user interface after the localization - it extends the text based
on the source string length. The variable texts are repeated by length of the
text multiplied by the multiplier. For example ``Hello world`` with variable
text ``_`` and variable multiplier of 1 becomes ``Hello world___________`` -
the text is repeated once for each character in the source string.

The strings will be generated using following pattern:

:guilabel:`Prepended static text`
:guilabel:`Prepended variable text`
:guilabel:`Source string`
:guilabel:`Appended variable text`
:guilabel:`Appended static text`

.. hint::

   You can use real languages for testing, but there are dedicated
   pseudolocales available in Weblate - `en_XA` and `ar_XB`.

.. hint::

   You can use this add-on to start translation to a new locale of an
   existing language or similar language.
   Once you add the translation to the component, follow to the add-on.
   *Example:* If you have `fr` and want to start `fr_CA` translation, simply set
   `fr` as the source, `fr_CA` as the target, and leave the prefix and suffix blank.

   Uninstall the add-on once you have the new translation filled to prevent Weblate
   from changing the translations made after the copying.


.. _addon-weblate.gettext.authors:

Contributors in comment
-----------------------

:Add-on ID: ``weblate.gettext.authors``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-repository-pre-commit`

Updates the comment part of the PO file header to include contributor names and
years of contributions.

The PO file header will look like this:

.. code-block:: po

    # Michal Čihař <michal@weblate.org>, 2012, 2018, 2019, 2020.
    # Pavel Borecki <pavel@example.com>, 2018, 2019.
    # Filip Hron <filip@example.com>, 2018, 2019.
    # anonymous <noreply@weblate.org>, 2019.

.. _addon-weblate.gettext.configure:

Update ALL_LINGUAS variable in the "configure" file
---------------------------------------------------

:Add-on ID: ``weblate.gettext.configure``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-daily`, :ref:`addon-event-repository-post-add`

Updates the ALL_LINGUAS variable in :file:`configure`, :file:`configure.in` or any
:file:`configure.ac` files, when a new translation is added.

.. _addon-weblate.gettext.customize:

Customize gettext output
------------------------

:Add-on ID: ``weblate.gettext.customize``
:Configuration: +-----------+---------------------+-----------------------------------------------------------------------------------------------------------------------------------+
                | ``width`` | Long lines wrapping | By default gettext wraps lines at 77 characters and at newlines. With the --no-wrap parameter, wrapping is only done at newlines. |
                |           |                     |                                                                                                                                   |
                |           |                     | .. list-table:: Available choices:                                                                                                |
                |           |                     |    :width: 100%                                                                                                                   |
                |           |                     |                                                                                                                                   |
                |           |                     |    * - ``77``                                                                                                                     |
                |           |                     |      - Wrap lines at 77 characters and at newlines (xgettext default)                                                             |
                |           |                     |    * - ``65535``                                                                                                                  |
                |           |                     |      - Only wrap lines at newlines (like 'xgettext --no-wrap')                                                                    |
                |           |                     |    * - ``-1``                                                                                                                     |
                |           |                     |      - No line wrapping                                                                                                           |
                +-----------+---------------------+-----------------------------------------------------------------------------------------------------------------------------------+
:Triggers: :ref:`addon-event-storage-post-load`

Allows customization of gettext output behavior, for example line wrapping.

It offers the following options:

* Wrap lines at 77 characters and at newlines
* Only wrap lines at newlines
* No line wrapping

.. note::

   By default gettext wraps lines at 77 characters and at newlines.
   With the ``--no-wrap`` parameter, wrapping is only done at newlines.


.. _addon-weblate.gettext.linguas:

Update LINGUAS file
-------------------

:Add-on ID: ``weblate.gettext.linguas``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-daily`, :ref:`addon-event-repository-post-add`

Updates the LINGUAS file when a new translation is added.

.. _addon-weblate.gettext.mo:

Generate MO files
-----------------

:Add-on ID: ``weblate.gettext.mo``
:Configuration: +-----------+---------------------------------+----------------------------------------------------------------------------------+
                | ``path``  | Path of generated MO file       | If not specified, the location of the PO file will be used.                      |
                +-----------+---------------------------------+----------------------------------------------------------------------------------+
                | ``fuzzy`` | Include strings needing editing | Strings needing editing (fuzzy) are typically not ready for use as translations. |
                +-----------+---------------------------------+----------------------------------------------------------------------------------+
:Triggers: :ref:`addon-event-repository-pre-commit`

Automatically generates a MO file for every changed PO file.

The location of the generated MO file can be customized and the field for it uses :ref:`markup`.

.. note::

   If a translation is removed, its PO file will be deleted from the
   repository, but the MO file generated by this add-on will not. The MO file
   must be removed from the upstream manually.


.. _addon-weblate.gettext.msgmerge:

Update PO files to match POT (msgmerge)
---------------------------------------

:Add-on ID: ``weblate.gettext.msgmerge``
:Configuration: +-----------------+--------------------------------------------+--+
                | ``previous``    | Keep previous msgids of translated strings |  |
                +-----------------+--------------------------------------------+--+
                | ``no_location`` | Remove locations of translated strings     |  |
                +-----------------+--------------------------------------------+--+
                | ``fuzzy``       | Use fuzzy matching                         |  |
                +-----------------+--------------------------------------------+--+
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-repository-post-update`

Updates all PO files (as configured by :ref:`component-filemask`) to match the
POT file (as configured by :ref:`component-new_base`) using :program:`msgmerge`.

Most msgmerge command-line options can be set up through the add-on
configuration.

.. seealso::

   :ref:`faq-cleanup`

.. _addon-weblate.git.squash:

Squash Git commits
------------------

:Add-on ID: ``weblate.git.squash``
:Configuration: +---------------------+--------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``squash``          | Commit squashing                           | .. list-table:: Available choices:                                                                                                                                |
                |                     |                                            |    :width: 100%                                                                                                                                                   |
                |                     |                                            |                                                                                                                                                                   |
                |                     |                                            |    * - ``all``                                                                                                                                                    |
                |                     |                                            |      - All commits into one                                                                                                                                       |
                |                     |                                            |    * - ``language``                                                                                                                                               |
                |                     |                                            |      - Per language                                                                                                                                               |
                |                     |                                            |    * - ``file``                                                                                                                                                   |
                |                     |                                            |      - Per file                                                                                                                                                   |
                |                     |                                            |    * - ``author``                                                                                                                                                 |
                |                     |                                            |      - Per author                                                                                                                                                 |
                +---------------------+--------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``append_trailers`` | Append trailers to squashed commit message | Trailer lines are lines that look similar to RFC 822 e-mail headers, at the end of the otherwise free-form part of a commit message, such as 'Co-authored-by: …'. |
                +---------------------+--------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``commit_message``  | Commit message                             | This commit message will be used instead of the combined commit messages from the squashed commits.                                                               |
                +---------------------+--------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------+
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-repository-post-commit`

Squash Git commits prior to pushing changes.

.. hint::

   To avoid unnecessary conflicts, it is recommended to configure automatic
   receiving of upstream changes by webhooks or API, see :ref:`update-vcs`.

Git commits can be squashed prior to pushing changes
in one of the following modes:

* All commits into one
* Per language
* Per file
* Per author

Original commit messages are kept, but authorship is lost unless :guilabel:`Per author` is selected, or
the commit message is customized to include it.

The original commit messages can optionally be overridden with a custom commit message.

Trailers (commit lines like ``Co-authored-by: …``) can optionally be removed
from the original commit messages and appended to the end of the squashed
commit message. This also generates proper ``Co-authored-by:`` credit for every
translator.

.. _addon-weblate.json.customize:

Customize JSON output
---------------------

.. versionchanged:: 5.12

   :guilabel:`Avoid spaces after separators` option added.

:Add-on ID: ``weblate.json.customize``
:Configuration: +----------------------------+-------------------------------+------------------------------------+
                | ``sort_keys``              | Sort JSON keys                |                                    |
                +----------------------------+-------------------------------+------------------------------------+
                | ``use_compact_separators`` | Avoid spaces after separators |                                    |
                +----------------------------+-------------------------------+------------------------------------+
                | ``indent``                 | JSON indentation              |                                    |
                +----------------------------+-------------------------------+------------------------------------+
                | ``style``                  | JSON indentation style        | .. list-table:: Available choices: |
                |                            |                               |    :width: 100%                    |
                |                            |                               |                                    |
                |                            |                               |    * - ``spaces``                  |
                |                            |                               |      - Spaces                      |
                |                            |                               |    * - ``tabs``                    |
                |                            |                               |      - Tabs                        |
                +----------------------------+-------------------------------+------------------------------------+
:Triggers: :ref:`addon-event-storage-post-load`

Allows adjusting JSON output behavior, for example indentation, sorting or
compact formatting using minimal whitespace.

.. _addon-weblate.properties.sort:

Format the Java properties file
-------------------------------

:Add-on ID: ``weblate.properties.sort``
:Configuration: +--------------------+-----------------------------------+--+
                | ``case_sensitive`` | Enable case-sensitive key sorting |  |
                +--------------------+-----------------------------------+--+
:Triggers: :ref:`addon-event-repository-pre-commit`

Formats and sorts the Java properties file.

* Consolidates newlines to Unix ones.
* Uppercase formatting of Unicode escape sequences (in case they are present).
* Strips blank lines and comments.
* Sorts the strings by the keys.
* Drops duplicate strings.

.. _addon-weblate.removal.comments:

Stale comment removal
---------------------

:Add-on ID: ``weblate.removal.comments``
:Configuration: +---------+--------------+--+
                | ``age`` | Days to keep |  |
                +---------+--------------+--+
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-daily`

Set a timeframe for removal of comments.

This can be useful to remove old
comments which might have become outdated. Use with care as comments
getting old does not mean they have lost their importance.

.. _addon-weblate.removal.suggestions:

Stale suggestion removal
------------------------

:Add-on ID: ``weblate.removal.suggestions``
:Configuration: +-----------+------------------+-------------------------------------------------------------------------+
                | ``age``   | Days to keep     |                                                                         |
                +-----------+------------------+-------------------------------------------------------------------------+
                | ``votes`` | Voting threshold | Threshold for removal. This field has no effect with voting turned off. |
                +-----------+------------------+-------------------------------------------------------------------------+
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-daily`

Set a timeframe for removal of suggestions.

Can be very useful in connection with suggestion voting
(see :ref:`peer-review`) to remove suggestions which
don't receive enough positive votes in a given timeframe.

.. _addon-weblate.resx.update:

Update RESX files
-----------------

:Add-on ID: ``weblate.resx.update``
:Configuration: `This add-on has no configuration.`
:Triggers: :ref:`addon-event-install`, :ref:`addon-event-repository-post-update`

Update all translation files to match the monolingual upstream base file.
Unused strings are removed, and new ones added as copies of the source string.

.. hint::

   Use :ref:`addon-weblate.cleanup.generic` if you only want to remove stale
   translation keys.

.. seealso::

   :ref:`faq-cleanup`

.. _addon-weblate.webhook.slack:

Slack Webhooks
--------------

.. versionadded:: 5.12

:Add-on ID: ``weblate.webhook.slack``
:Configuration: +-----------------+---------------+----------------------------------------------+
                | ``webhook_url`` | Webhook URL   |                                              |
                +-----------------+---------------+----------------------------------------------+
                | ``events``      | Change events | .. list-table:: Available choices:           |
                |                 |               |    :width: 100%                              |
                |                 |               |                                              |
                |                 |               |    * - ``0``                                 |
                |                 |               |      - Resource updated                      |
                |                 |               |    * - ``1``                                 |
                |                 |               |      - Translation completed                 |
                |                 |               |    * - ``2``                                 |
                |                 |               |      - Translation changed                   |
                |                 |               |    * - ``3``                                 |
                |                 |               |      - Comment added                         |
                |                 |               |    * - ``4``                                 |
                |                 |               |      - Suggestion added                      |
                |                 |               |    * - ``5``                                 |
                |                 |               |      - Translation added                     |
                |                 |               |    * - ``6``                                 |
                |                 |               |      - Automatically translated              |
                |                 |               |    * - ``7``                                 |
                |                 |               |      - Suggestion accepted                   |
                |                 |               |    * - ``8``                                 |
                |                 |               |      - Translation reverted                  |
                |                 |               |    * - ``9``                                 |
                |                 |               |      - Translation uploaded                  |
                |                 |               |    * - ``13``                                |
                |                 |               |      - Source string added                   |
                |                 |               |    * - ``14``                                |
                |                 |               |      - Component locked                      |
                |                 |               |    * - ``15``                                |
                |                 |               |      - Component unlocked                    |
                |                 |               |    * - ``17``                                |
                |                 |               |      - Changes committed                     |
                |                 |               |    * - ``18``                                |
                |                 |               |      - Changes pushed                        |
                |                 |               |    * - ``19``                                |
                |                 |               |      - Repository reset                      |
                |                 |               |    * - ``20``                                |
                |                 |               |      - Repository merged                     |
                |                 |               |    * - ``21``                                |
                |                 |               |      - Repository rebased                    |
                |                 |               |    * - ``22``                                |
                |                 |               |      - Repository merge failed               |
                |                 |               |    * - ``23``                                |
                |                 |               |      - Repository rebase failed              |
                |                 |               |    * - ``24``                                |
                |                 |               |      - Parsing failed                        |
                |                 |               |    * - ``25``                                |
                |                 |               |      - Translation removed                   |
                |                 |               |    * - ``26``                                |
                |                 |               |      - Suggestion removed                    |
                |                 |               |    * - ``27``                                |
                |                 |               |      - Translation replaced                  |
                |                 |               |    * - ``28``                                |
                |                 |               |      - Repository push failed                |
                |                 |               |    * - ``29``                                |
                |                 |               |      - Suggestion removed during cleanup     |
                |                 |               |    * - ``30``                                |
                |                 |               |      - Source string changed                 |
                |                 |               |    * - ``31``                                |
                |                 |               |      - String added                          |
                |                 |               |    * - ``32``                                |
                |                 |               |      - Bulk status changed                   |
                |                 |               |    * - ``33``                                |
                |                 |               |      - Visibility changed                    |
                |                 |               |    * - ``34``                                |
                |                 |               |      - User added                            |
                |                 |               |    * - ``35``                                |
                |                 |               |      - User removed                          |
                |                 |               |    * - ``36``                                |
                |                 |               |      - Translation approved                  |
                |                 |               |    * - ``37``                                |
                |                 |               |      - Marked for edit                       |
                |                 |               |    * - ``38``                                |
                |                 |               |      - Component removed                     |
                |                 |               |    * - ``39``                                |
                |                 |               |      - Project removed                       |
                |                 |               |    * - ``41``                                |
                |                 |               |      - Project renamed                       |
                |                 |               |    * - ``42``                                |
                |                 |               |      - Component renamed                     |
                |                 |               |    * - ``43``                                |
                |                 |               |      - Moved component                       |
                |                 |               |    * - ``45``                                |
                |                 |               |      - Contributor joined                    |
                |                 |               |    * - ``46``                                |
                |                 |               |      - Announcement posted                   |
                |                 |               |    * - ``47``                                |
                |                 |               |      - Alert triggered                       |
                |                 |               |    * - ``48``                                |
                |                 |               |      - Language added                        |
                |                 |               |    * - ``49``                                |
                |                 |               |      - Language requested                    |
                |                 |               |    * - ``50``                                |
                |                 |               |      - Project created                       |
                |                 |               |    * - ``51``                                |
                |                 |               |      - Component created                     |
                |                 |               |    * - ``52``                                |
                |                 |               |      - User invited                          |
                |                 |               |    * - ``53``                                |
                |                 |               |      - Repository notification received      |
                |                 |               |    * - ``54``                                |
                |                 |               |      - Translation replaced file by upload   |
                |                 |               |    * - ``55``                                |
                |                 |               |      - License changed                       |
                |                 |               |    * - ``56``                                |
                |                 |               |      - Contributor license agreement changed |
                |                 |               |    * - ``57``                                |
                |                 |               |      - Screenshot added                      |
                |                 |               |    * - ``58``                                |
                |                 |               |      - Screenshot uploaded                   |
                |                 |               |    * - ``59``                                |
                |                 |               |      - String updated in the repository      |
                |                 |               |    * - ``60``                                |
                |                 |               |      - Add-on installed                      |
                |                 |               |    * - ``61``                                |
                |                 |               |      - Add-on configuration changed          |
                |                 |               |    * - ``62``                                |
                |                 |               |      - Add-on uninstalled                    |
                |                 |               |    * - ``63``                                |
                |                 |               |      - String removed                        |
                |                 |               |    * - ``64``                                |
                |                 |               |      - Comment removed                       |
                |                 |               |    * - ``65``                                |
                |                 |               |      - Comment resolved                      |
                |                 |               |    * - ``66``                                |
                |                 |               |      - Explanation updated                   |
                |                 |               |    * - ``67``                                |
                |                 |               |      - Category removed                      |
                |                 |               |    * - ``68``                                |
                |                 |               |      - Category renamed                      |
                |                 |               |    * - ``69``                                |
                |                 |               |      - Category moved                        |
                |                 |               |    * - ``70``                                |
                |                 |               |      - Saving string failed                  |
                |                 |               |    * - ``71``                                |
                |                 |               |      - String added in the repository        |
                |                 |               |    * - ``72``                                |
                |                 |               |      - String updated in the upload          |
                |                 |               |    * - ``73``                                |
                |                 |               |      - String added in the upload            |
                |                 |               |    * - ``74``                                |
                |                 |               |      - Translation updated by source upload  |
                |                 |               |    * - ``75``                                |
                |                 |               |      - Component translation completed       |
                |                 |               |    * - ``76``                                |
                |                 |               |      - Applied enforced check                |
                |                 |               |    * - ``77``                                |
                |                 |               |      - Propagated change                     |
                |                 |               |    * - ``78``                                |
                |                 |               |      - File uploaded                         |
                |                 |               |    * - ``79``                                |
                |                 |               |      - Extra flags updated                   |
                |                 |               |    * - ``80``                                |
                |                 |               |      - Font uploaded                         |
                |                 |               |    * - ``81``                                |
                |                 |               |      - Font changed                          |
                |                 |               |    * - ``82``                                |
                |                 |               |      - Font removed                          |
                +-----------------+---------------+----------------------------------------------+
:Triggers: :ref:`addon-event-event-change`

Sends notification to a Slack channel based on selected events.

.. warning::

   The notification content might show HTML tags. This is a known issue that will be soon addressed; see https://github.com/WeblateOrg/weblate/issues/15056.

.. hint::

   To obtain a webhook URL, follow the steps outlined in the `Slack Incoming Webhooks documentation <https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks>`_

.. _addon-weblate.webhook.webhook:

Webhook
-------

.. versionadded:: 5.11

:Add-on ID: ``weblate.webhook.webhook``
:Configuration: +-----------------+---------------+----------------------------------------------+
                | ``webhook_url`` | Webhook URL   |                                              |
                +-----------------+---------------+----------------------------------------------+
                | ``secret``      | Secret        | A Base64 encoded string                      |
                +-----------------+---------------+----------------------------------------------+
                | ``events``      | Change events | .. list-table:: Available choices:           |
                |                 |               |    :width: 100%                              |
                |                 |               |                                              |
                |                 |               |    * - ``0``                                 |
                |                 |               |      - Resource updated                      |
                |                 |               |    * - ``1``                                 |
                |                 |               |      - Translation completed                 |
                |                 |               |    * - ``2``                                 |
                |                 |               |      - Translation changed                   |
                |                 |               |    * - ``3``                                 |
                |                 |               |      - Comment added                         |
                |                 |               |    * - ``4``                                 |
                |                 |               |      - Suggestion added                      |
                |                 |               |    * - ``5``                                 |
                |                 |               |      - Translation added                     |
                |                 |               |    * - ``6``                                 |
                |                 |               |      - Automatically translated              |
                |                 |               |    * - ``7``                                 |
                |                 |               |      - Suggestion accepted                   |
                |                 |               |    * - ``8``                                 |
                |                 |               |      - Translation reverted                  |
                |                 |               |    * - ``9``                                 |
                |                 |               |      - Translation uploaded                  |
                |                 |               |    * - ``13``                                |
                |                 |               |      - Source string added                   |
                |                 |               |    * - ``14``                                |
                |                 |               |      - Component locked                      |
                |                 |               |    * - ``15``                                |
                |                 |               |      - Component unlocked                    |
                |                 |               |    * - ``17``                                |
                |                 |               |      - Changes committed                     |
                |                 |               |    * - ``18``                                |
                |                 |               |      - Changes pushed                        |
                |                 |               |    * - ``19``                                |
                |                 |               |      - Repository reset                      |
                |                 |               |    * - ``20``                                |
                |                 |               |      - Repository merged                     |
                |                 |               |    * - ``21``                                |
                |                 |               |      - Repository rebased                    |
                |                 |               |    * - ``22``                                |
                |                 |               |      - Repository merge failed               |
                |                 |               |    * - ``23``                                |
                |                 |               |      - Repository rebase failed              |
                |                 |               |    * - ``24``                                |
                |                 |               |      - Parsing failed                        |
                |                 |               |    * - ``25``                                |
                |                 |               |      - Translation removed                   |
                |                 |               |    * - ``26``                                |
                |                 |               |      - Suggestion removed                    |
                |                 |               |    * - ``27``                                |
                |                 |               |      - Translation replaced                  |
                |                 |               |    * - ``28``                                |
                |                 |               |      - Repository push failed                |
                |                 |               |    * - ``29``                                |
                |                 |               |      - Suggestion removed during cleanup     |
                |                 |               |    * - ``30``                                |
                |                 |               |      - Source string changed                 |
                |                 |               |    * - ``31``                                |
                |                 |               |      - String added                          |
                |                 |               |    * - ``32``                                |
                |                 |               |      - Bulk status changed                   |
                |                 |               |    * - ``33``                                |
                |                 |               |      - Visibility changed                    |
                |                 |               |    * - ``34``                                |
                |                 |               |      - User added                            |
                |                 |               |    * - ``35``                                |
                |                 |               |      - User removed                          |
                |                 |               |    * - ``36``                                |
                |                 |               |      - Translation approved                  |
                |                 |               |    * - ``37``                                |
                |                 |               |      - Marked for edit                       |
                |                 |               |    * - ``38``                                |
                |                 |               |      - Component removed                     |
                |                 |               |    * - ``39``                                |
                |                 |               |      - Project removed                       |
                |                 |               |    * - ``41``                                |
                |                 |               |      - Project renamed                       |
                |                 |               |    * - ``42``                                |
                |                 |               |      - Component renamed                     |
                |                 |               |    * - ``43``                                |
                |                 |               |      - Moved component                       |
                |                 |               |    * - ``45``                                |
                |                 |               |      - Contributor joined                    |
                |                 |               |    * - ``46``                                |
                |                 |               |      - Announcement posted                   |
                |                 |               |    * - ``47``                                |
                |                 |               |      - Alert triggered                       |
                |                 |               |    * - ``48``                                |
                |                 |               |      - Language added                        |
                |                 |               |    * - ``49``                                |
                |                 |               |      - Language requested                    |
                |                 |               |    * - ``50``                                |
                |                 |               |      - Project created                       |
                |                 |               |    * - ``51``                                |
                |                 |               |      - Component created                     |
                |                 |               |    * - ``52``                                |
                |                 |               |      - User invited                          |
                |                 |               |    * - ``53``                                |
                |                 |               |      - Repository notification received      |
                |                 |               |    * - ``54``                                |
                |                 |               |      - Translation replaced file by upload   |
                |                 |               |    * - ``55``                                |
                |                 |               |      - License changed                       |
                |                 |               |    * - ``56``                                |
                |                 |               |      - Contributor license agreement changed |
                |                 |               |    * - ``57``                                |
                |                 |               |      - Screenshot added                      |
                |                 |               |    * - ``58``                                |
                |                 |               |      - Screenshot uploaded                   |
                |                 |               |    * - ``59``                                |
                |                 |               |      - String updated in the repository      |
                |                 |               |    * - ``60``                                |
                |                 |               |      - Add-on installed                      |
                |                 |               |    * - ``61``                                |
                |                 |               |      - Add-on configuration changed          |
                |                 |               |    * - ``62``                                |
                |                 |               |      - Add-on uninstalled                    |
                |                 |               |    * - ``63``                                |
                |                 |               |      - String removed                        |
                |                 |               |    * - ``64``                                |
                |                 |               |      - Comment removed                       |
                |                 |               |    * - ``65``                                |
                |                 |               |      - Comment resolved                      |
                |                 |               |    * - ``66``                                |
                |                 |               |      - Explanation updated                   |
                |                 |               |    * - ``67``                                |
                |                 |               |      - Category removed                      |
                |                 |               |    * - ``68``                                |
                |                 |               |      - Category renamed                      |
                |                 |               |    * - ``69``                                |
                |                 |               |      - Category moved                        |
                |                 |               |    * - ``70``                                |
                |                 |               |      - Saving string failed                  |
                |                 |               |    * - ``71``                                |
                |                 |               |      - String added in the repository        |
                |                 |               |    * - ``72``                                |
                |                 |               |      - String updated in the upload          |
                |                 |               |    * - ``73``                                |
                |                 |               |      - String added in the upload            |
                |                 |               |    * - ``74``                                |
                |                 |               |      - Translation updated by source upload  |
                |                 |               |    * - ``75``                                |
                |                 |               |      - Component translation completed       |
                |                 |               |    * - ``76``                                |
                |                 |               |      - Applied enforced check                |
                |                 |               |    * - ``77``                                |
                |                 |               |      - Propagated change                     |
                |                 |               |    * - ``78``                                |
                |                 |               |      - File uploaded                         |
                |                 |               |    * - ``79``                                |
                |                 |               |      - Extra flags updated                   |
                |                 |               |    * - ``80``                                |
                |                 |               |      - Font uploaded                         |
                |                 |               |    * - ``81``                                |
                |                 |               |      - Font changed                          |
                |                 |               |    * - ``82``                                |
                |                 |               |      - Font removed                          |
                +-----------------+---------------+----------------------------------------------+
:Triggers: :ref:`addon-event-event-change`

Sends notifications to external services based on selected events, following
the Standard Webhooks specification.

The request payload complies with the :ref:`schema-messaging` schema.
The OpenAPI description can also be found at ``/api/docs/``.
Sample request body:

.. code-block:: json

   {
      "change_id": 99,
      "action": "Translation changed",
      "timestamp": "2019-08-24T14:15:22Z",
      "target": "Nazdar svete!",
      "old": "Nazdar!",
      "source": "Hello, world",
      "url": "/translate/project-slug/component-slug/cs/?checksum=46add148a53cab6f",
      "author": "author-username",
      "user": "user-username",
      "project": "project-slug",
      "component": "component-slug",
      "translation": "cs"
   }

Sample request body with categories:

.. code-block:: json

   {
      "change_id": 8910,
      "action": "Component renamed",
      "timestamp": "2025-06-11T07:15:09Z",
      "target": ["new-name"],
      "old": ["component-slug"],
      "url": "/projects/project-slug/parent-category/child-category/sub-category/component-slug/",
      "user": "testuser",
      "project": "project-slug",
      "component": "component-slug",
      "category": [
         "sub-category",
         "child-category",
         "parent-category"
      ]
   }

Sample request headers:

.. code-block:: json

   {
      "webhook-id": "7f1c5477f6275a69af7b83236c20cb1a",
      "webhook-timestamp": "1748505623.044281",
      "webhook-signature": "v1,Ceo5qEr07ixe2NLpvHk3FH9bwy/WavXrAFQ/9tdO6mc="
   }

The ``webhook-signature`` is a space separated list of HMAC signatures generated using the ``secret`` string,
the request payload, the ``webhook-timestamp``, and the ``webhook-id``. This ensures the authenticity
and integrity of the webhook request.

To verify a request, you can use the ``Webhook.verify`` method from the ``standardwebhooks`` library
or an implementation of the "Standard Webhooks Specification".


.. seealso::

   * `Standard Webhooks Specification <https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md>`_
   * :ref:`schema-messaging`
   * `Python library for Standard Webhooks <https://pypi.org/project/standardwebhooks/>`_



.. _addon-weblate.xml.customize:

Customize XML output
--------------------

.. versionadded:: 4.15

:Add-on ID: ``weblate.xml.customize``
:Configuration: +------------------+----------------------------------------+--+
                | ``closing_tags`` | Include closing tag for blank XML tags |  |
                +------------------+----------------------------------------+--+
:Triggers: :ref:`addon-event-storage-post-load`

Allows adjusting XML output behavior, for example closing tags.

.. _addon-weblate.yaml.customize:

Customize YAML output
---------------------

:Add-on ID: ``weblate.yaml.customize``
:Configuration: +----------------+---------------------+------------------------------------+
                | ``indent``     | YAML indentation    |                                    |
                +----------------+---------------------+------------------------------------+
                | ``width``      | Long lines wrapping | .. list-table:: Available choices: |
                |                |                     |    :width: 100%                    |
                |                |                     |                                    |
                |                |                     |    * - ``80``                      |
                |                |                     |      - Wrap lines at 80 chars      |
                |                |                     |    * - ``100``                     |
                |                |                     |      - Wrap lines at 100 chars     |
                |                |                     |    * - ``120``                     |
                |                |                     |      - Wrap lines at 120 chars     |
                |                |                     |    * - ``180``                     |
                |                |                     |      - Wrap lines at 180 chars     |
                |                |                     |    * - ``65535``                   |
                |                |                     |      - No line wrapping            |
                +----------------+---------------------+------------------------------------+
                | ``line_break`` | Line breaks         | .. list-table:: Available choices: |
                |                |                     |    :width: 100%                    |
                |                |                     |                                    |
                |                |                     |    * - ``dos``                     |
                |                |                     |      - DOS (\\r\\n)                |
                |                |                     |    * - ``unix``                    |
                |                |                     |      - UNIX (\\n)                  |
                |                |                     |    * - ``mac``                     |
                |                |                     |      - MAC (\\r)                   |
                +----------------+---------------------+------------------------------------+
:Triggers: :ref:`addon-event-storage-post-load`

Allows adjusting YAML output behavior, for example line-length or newlines.


Customizing list of add-ons
+++++++++++++++++++++++++++

The list of add-ons is configured by :setting:`WEBLATE_ADDONS`.
To add another add-on, simply include the absolute class name in this setting.


.. _own-addon:

Writing add-on
++++++++++++++

You can write your own add-ons too, create a subclass of
:class:`weblate.addons.base.BaseAddon` to define the add-on metadata, and
then implement a callback to do the processing.

.. seealso::

   :doc:`../contributing/addons`

.. _addon-script:

Executing scripts from add-on
+++++++++++++++++++++++++++++

Add-ons can also be used to execute external scripts. This used to be
integrated in Weblate, but now you have to write some code to wrap your
script with an add-on.

.. literalinclude:: ../../weblate/addons/example_pre.py
    :language: python

For installation instructions see :ref:`custom-addon-modules`.

The script is executed with the current directory set to the root of the VCS repository
for any given component.

Additionally, the following environment variables are available:

.. envvar:: WL_VCS

    Version control system used.

.. envvar:: WL_REPO

    Upstream repository URL.

.. envvar:: WL_PATH

    Absolute path to VCS repository.

.. envvar:: WL_BRANCH

    Repository branch configured in the current component.

.. envvar:: WL_FILEMASK

    File mask for current component.

.. envvar:: WL_TEMPLATE

    Filename of template for monolingual translations (can be empty).

.. envvar:: WL_NEW_BASE

    Filename of the file used for creating new translations (can be
    empty).

.. envvar:: WL_FILE_FORMAT

    File format used in current component.

.. envvar:: WL_LANGUAGE

    Language of currently processed translation (not available for
    component-level hooks).

.. envvar:: WL_PREVIOUS_HEAD

    Previous HEAD after update (only available after running the post-update hook).

.. envvar:: WL_COMPONENT_SLUG

   Component slug used to construct URL.

.. envvar:: WL_PROJECT_SLUG

   Project slug used to construct URL.

.. envvar:: WL_COMPONENT_NAME

   Component name.

.. envvar:: WL_PROJECT_NAME

   Project name.

.. envvar:: WL_COMPONENT_URL

   Component URL.

.. envvar:: WL_ENGAGE_URL

   Project engage URL.

.. seealso::

    :ref:`component`

Post-update repository processing
---------------------------------

Can be used to update translation files when the VCS upstream source changes.
To achieve this, please remember Weblate only sees files committed to the VCS,
so you need to commit changes as a part of the script.

For example with Gulp you can do it using following code:

.. code-block:: sh

    #! /bin/sh
    gulp --gulpfile gulp-i18n-extract.js
    git commit -m 'Update source strings' src/languages/en.lang.json


Pre-commit processing of translations
-------------------------------------

Use the commit script to automatically change a translation before it is committed
to the repository.

It is passed as a single parameter consisting of the filename of a current translation.


Add-on activity logging
-----------------------

Add-on activity log keeps track of the add-on execution and can be used to
keep track of add-on activity.

The logs can be pruned after a certain time interval by configuring the :setting:`ADDON_ACTIVITY_LOG_EXPIRY`.
