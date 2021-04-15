.. _addons:

Addons
======

.. versionadded:: 2.19

Addons provide ways to customize and automate the translation workflow.
Admins can add and mangage addons from the :guilabel:`Manage` ↓ :guilabel:`Addons` menu of each respective
translation component.

.. image:: /images/addons.png

Built-in addons
+++++++++++++++

.. _addon-weblate.autotranslate.autotranslate:

Automatic translation
---------------------

.. versionadded:: 3.9

Automatically translates strings using machine translation or other components.

It is triggered:

* When new strings appear in a component.
* Once in a month for every component, this can be configured using :setting:`BACKGROUND_TASKS`.

.. seealso::

   :ref:`auto-translation`,
   :ref:`translation-consistency`

.. _addon-weblate.cdn.cdnjs:

JavaScript localization CDN
---------------------------

.. versionadded:: 4.2

Publishes translations into content delivery network for use in JavaScript or
HTML localization.

Can be used to localize static HTML pages, or
to load localization in the JavaScript code.

Generates a unique URL for your component you can include in
HTML pages to localize them. See :ref:`weblate-cdn` for more details.

.. seealso::

    :ref:`cdn-addon-config`,
    :ref:`weblate-cdn`,
    :ref:`cdn-addon-extract`,
    :ref:`cdn-addon-html`

.. _addon-weblate.cleanup.blank:

Remove blank strings
--------------------

.. versionadded:: 4.4

Removes strings without a translation from translation files.

Use this to not have any empty strings in translation files (for
example if your localization library displays them as missing instead
of falling back to the source string).

.. seealso::

   :ref:`faq-cleanup`

.. _addon-weblate.cleanup.generic:

Cleanup translation files
-------------------------

Update all translation files to match the monolingual base file. For most file
formats, this means removing stale translation keys no longer present in the
base file.

.. seealso::

   :ref:`faq-cleanup`

.. _addon-weblate.consistency.languages:

Add missing languages
---------------------

Ensures a consistent set of languages is used for all components within a
project.

Missing languages are checked once every 24 hours, and when new languages
are added in Weblate.

Unlike most others, this addon affects the whole project.

.. hint::

   Auto-translate the newly added strings with
   :ref:`addon-weblate.autotranslate.autotranslate`.

.. _addon-weblate.discovery.discovery:

Component discovery
-------------------

Automatically adds or removes project components based on file changes in the
version control system.

Triggered each time the VCS is updated, and otherwise similar to
the :djadmin:`import_project` management command. This way you can track
multiple translation components within one VCS.

The matching is done using regular expressions
enabling complex configuration, but some knowledge is required to do so.
Some examples for common use cases can be found in
the addon help section.

Once you hit :guilabel:`Save`, a preview of matching components will be presented,
from where you can check whether the configuration actually matches your needs:

.. image:: /images/addon-discovery.png

.. hint::

   Component discovery addon uses :ref:`internal-urls`. It’s a convenient way to share
   VCS setup between multiple components. Linked components use the local repository of
   the main component set up by filling ``weblate://project/main-component``
   into the :ref:`component-repo` field (in :guilabel:`Manage` ↓ :guilabel:`Settings` ↓
   :guilabel:`Version control system`) of each respective component.
   This saves time with configuration and system resources too.

.. seealso::

    :ref:`markup`

.. _addon-weblate.flags.bulk:

Bulk edit
---------

.. versionadded:: 3.11

Bulk edit flags, labels, or states of strings.

Automate labeling by starting out with the search query ``NOT has:label``
and add labels till all strings have all required labels.
Other automated operations for Weblate metadata can also be done.

**Examples:**

.. list-table:: Label new strings automatically
    :stub-columns: 1

    * - Search query
      - ``NOT has:label``
    * - Labels to add
      - *recent*

.. list-table:: Marking all :ref:`appstore` changelog entries read-only
    :stub-columns: 1

    * - Search query
      - ``language:en AND key:changelogs/``
    * - Translation flags to add
      - ``read-only``


.. seealso::

   :ref:`bulk-edit`,
   :ref:`custom-checks`,
   :ref:`labels`


.. _addon-weblate.flags.same_edit:

Flag unchanged translations as "Needs editing"
----------------------------------------------

.. versionadded:: 3.1

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

Whenever a new source string is imported from the VCS, it is flagged as needing
editing in Weblate. This way you can easily filter and edit source strings
written by the developers.

.. seealso::

   :ref:`states`

.. _addon-weblate.flags.target_edit:

Flag new translations as "Needs editing"
----------------------------------------

Whenever a new translatable string is imported from the VCS, it is flagged as
needing editing in Weblate. This way you can easily filter and edit
translations created by the developers.

.. seealso::

   :ref:`states`

.. _addon-weblate.generate.generate:

Statistics generator
--------------------

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

.. _addon-weblate.generate.pseudolocale:

Pseudolocale generation
-----------------------

Generates a translation by adding prefix and suffix to source strings
automatically.

Pseudolocales are useful to find strings that are not prepared for
localization. This is done by altering all translatable source strings
to make it easy to spot unaltered strings when running the application
in the pseudolocale language.

Finding strings whose localized counterparts might not fit the layout
is also possible.

.. hint::

   You can use real languages for testing, but there are dedicated
   pseudolocales available in Weblate - `en_XA` and `ar_XB`.

.. _addon-weblate.gettext.authors:

Contributors in comment
-----------------------

Updates the comment part of the PO file header to include contributor names
and years of contributions.

The PO file header will look like this:

.. code-block:: po

    # Michal Čihař <michal@cihar.com>, 2012, 2018, 2019, 2020.
    # Pavel Borecki <pavel@example.com>, 2018, 2019.
    # Filip Hron <filip@example.com>, 2018, 2019.
    # anonymous <noreply@weblate.org>, 2019.

.. _addon-weblate.gettext.configure:

Update ALL_LINGUAS variable in the "configure" file
---------------------------------------------------

Updates the ALL_LINGUAS variable in :file:`configure`, :file:`configure.in` or any
:file:`configure.ac` files, when a new translation is added.

.. _addon-weblate.gettext.customize:

Customize gettext output
------------------------

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

Updates the LINGUAS file when a new translation is added.

.. _addon-weblate.gettext.mo:

Generate MO files
-----------------

Automatically generates a MO file for every changed PO file.

The location of the generated MO file can be customized and the field for it uses :ref:`markup`.

.. _addon-weblate.gettext.msgmerge:

Update PO files to match POT (msgmerge)
---------------------------------------

Updates all PO files (as configured by :ref:`component-filemask`) to match the
POT file (as configured by :ref:`component-new_base`) using :program:`msgmerge`.

Triggered whenever new changes are pulled from the upstream repository.
Most msgmerge command-line options can be set up through the addon
configuration.

.. seealso::

   :ref:`faq-cleanup`

.. _addon-weblate.git.squash:

Squash Git commits
------------------

Squash Git commits prior to pushing changes.

Git commits can be squashed prior to pushing changes
in one of the following modes:

.. versionadded:: 3.4

* All commits into one
* Per language
* Per file

.. versionadded:: 3.5

* Per author

Original commit messages are kept, but authorship is lost unless :guilabel:`Per author` is selected, or
the commit message is customized to include it.

.. versionadded:: 4.1

The original commit messages can optionally be overridden with a custom commit message.

Trailers (commit lines like ``Co-authored-by: …``) can optionally be removed
from the original commit messages and appended to the end of the squashed
commit message. This also generates proper ``Co-authored-by:`` credit for every
translator.

.. _addon-weblate.json.customize:

Customize JSON output
---------------------

Allows adjusting JSON output behavior, for example indentation or sorting.

.. _addon-weblate.properties.sort:

Formats the Java properties file
--------------------------------

Sorts the Java properties file.

.. _addon-weblate.removal.comments:

Stale comment removal
---------------------

.. versionadded:: 3.7

Set a timeframe for removal of comments.

This can be useful to remove old
comments which might have become outdated. Use with care as comments
getting old does not mean they have lost their importance.

.. _addon-weblate.removal.suggestions:

Stale suggestion removal
------------------------

.. versionadded:: 3.7

Set a timeframe for removal of suggestions.

Can be very useful in connection with suggestion voting
(see :ref:`peer-review`) to remove suggestions which
don't receive enough positive votes in a given timeframe.

.. _addon-weblate.resx.update:

Update RESX files
-----------------

.. versionadded:: 3.9

Update all translation files to match the monolingual upstream base file.
Unused strings are removed, and new ones added as copies of the source string.

.. hint::

   Use :ref:`addon-weblate.cleanup.generic` if you only want to remove stale
   translation keys.

.. seealso::

   :ref:`faq-cleanup`

.. _addon-weblate.yaml.customize:

Customize YAML output
---------------------

.. versionadded:: 3.10.2

Allows adjusting YAML output behavior, for example line-length or newlines.


Customizing list of addons
++++++++++++++++++++++++++

The list of addons is configured by :setting:`WEBLATE_ADDONS`.
To add another addon, simply include the absolute class name in this setting.


.. _own-addon:

Writing addon
+++++++++++++

You can write your own addons too, create a subclass of
:class:`weblate.addons.base.BaseAddon` to define the addon metadata, and
then implement a callback to do the processing.

.. seealso::

   :doc:`../contributing/addons`

.. _addon-script:

Executing scripts from addon
++++++++++++++++++++++++++++

Addons can also be used to execute external scripts. This used to be
integrated in Weblate, but now you have to write some code to wrap your
script with an addon.

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

    .. versionadded:: 2.11

    Repository branch configured in the current component.

.. envvar:: WL_FILEMASK

    Filemask for current component.

.. envvar:: WL_TEMPLATE

    Filename of template for monolingual translations (can be empty).

.. envvar:: WL_NEW_BASE

    .. versionadded:: 2.14

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

   .. versionadded:: 3.9

   Component slug used to construct URL.

.. envvar:: WL_PROJECT_SLUG

   .. versionadded:: 3.9

   Project slug used to construct URL.

.. envvar:: WL_COMPONENT_NAME

   .. versionadded:: 3.9

   Component name.

.. envvar:: WL_PROJECT_NAME

   .. versionadded:: 3.9

   Project name.

.. envvar:: WL_COMPONENT_URL

   .. versionadded:: 3.9

   Component URL.

.. envvar:: WL_ENGAGE_URL

   .. versionadded:: 3.9

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
