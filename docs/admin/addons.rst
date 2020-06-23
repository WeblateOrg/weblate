.. _addons:

Addons
======

.. versionadded:: 2.19

Addons provide ways to customize translation workflow. They can be installed in the
translation component view, and work behind the scenes. Addon management
is available from the :guilabel:`Manage` ↓ `Addons` menu of each respective translation
component for admins.

.. image:: /images/addons.png

Built-in addons
+++++++++++++++

.. _addon-weblate.autotranslate.autotranslate:

Automatic translation
---------------------

.. versionadded:: 3.9

Automatically translates strings using machine translation or other components.

This addon is triggered automatically when new strings appear in a component.

.. seealso::

   :ref:`auto-translation`,
   :ref:`translation-consistency`

.. _addon-weblate.cleanup.generic:

Cleanup translation files
-------------------------

Update all translation files to match the monolingual base file. For most file
formats, this means removing stale translation keys no longer present in the
base file.

.. _addon-weblate.consistency.languages:

Language consistency
--------------------

Ensures all components within one project have translations for every added
language for translation.

It creates empty translations in languages that have
unadded components.

Missing languages are checked once every 24 hours and when a new language is
added in Weblate.

Unlike most others, this addon affects the whole project.

.. hint::

   Auto-translate the newly added strings with
   :ref:`addon-weblate.autotranslate.autotranslate`.

.. _addon-weblate.discovery.discovery:

Component discovery
-------------------

Automatically adds or removes project components based on file changes in the
version control system.

It is triggered on every VCS update, and otherwise similar to the :djadmin:`import_project`
management command. This way you can track multiple translation
components within one VCS.

Create one master component least likely to disappear in the future, and others
will employ :ref:`internal-urls` to it as a VCS configuration, and configure it
to find all compoents in it.

The matching is done using regular expressions, where power is a tradeoff for
complexity in configuration. Some examples for common use cases can be found in
the addon help sectoin.

Once you hit :guilabel:`Save`, a preview of matching components will be presented,
from where you can check whether the configuration actually matches your needs:

.. image:: /images/addon-discovery.png

.. seealso::

    :ref:`markup`

.. _addon-weblate.flags.bulk:

Bulk edit
---------

.. versionadded:: 3.11

Bulk edit flags, labels or state for strings.

Automating the labeling of new strings can be useful (start out with search query ``NOT
has:label`` and add desired labels till all strings are properly labeled).
You can also carry out any other automated operations for Weblate metadata.


.. _addon-weblate.flags.same_edit:

Flag unchanged translations as "Needs editing"
----------------------------------------------

.. versionadded:: 3.1

Whenever a new translatable string is imported from the VCS and it matches a
source string, it is flagged as needing editing in Weblate. This is especially
useful for file formats that include all strings even if not translated.

.. _addon-weblate.flags.source_edit:

Flag new source strings as "Needs editing"
------------------------------------------

Whenever a new source string is imported from the VCS, it is flagged as needing
editing in Weblate. This way you can easily filter and edit source strings
written by the developers.

.. _addon-weblate.flags.target_edit:

Flag new translations as "Needs editing"
----------------------------------------

Whenever a new translatable string is imported from the VCS, it is flagged as
needing editing in Weblate. This way you can easily filter and edit
translations created by the developers.

.. _addon-weblate.generate.generate:

Statistics generator
--------------------

Generates a file containing detailed info about the translation.

You can use Django template in both filename and content, see :ref:`markup`
for a detailed markup description.

For example generating summary file for each translation:

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

.. _addon-weblate.gettext.authors:

Contributors in comment
-----------------------

Update the comment in the PO file header to include contributor names and years
of contributions.

The PO file header will contain a list of contributors and years contributed:

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

   By default gettext wraps lines at 77 characters and for newlines.
   With the ``--no-wrap`` parameter, it wraps only at newlines.


.. _addon-weblate.gettext.linguas:

Update LINGUAS file
-------------------

Updates the LINGUAS file when a new translation is added.

.. _addon-weblate.gettext.mo:

Generate MO files
-----------------

Automatically generates a MO file for every changed PO file.

.. _addon-weblate.gettext.msgmerge:

Update PO files to match POT (msgmerge)
---------------------------------------

Updates all PO files to match the POT file using msgmerge. Triggered whenever
new changes are pulled from the upstream repository.

.. _addon-weblate.git.squash:

Squash Git commits
------------------

Squash Git commits prior to pushing changes.

You can choose one of following modes:

.. versionadded:: 3.4

* All commits into one
* Per language
* Per file

.. versionadded:: 3.5

* Per author

Original commit messages are kept, but authorship is lost unless "Per author" is selected, or
the commit message is customized to include it.

.. versionadded:: 4.1

The original commit messages can optionally be overridden with a custom commit message.

Trailers (commit lines like ``Co-authored-by: ...``) can optionally be removed
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
comments which might have become outdated. Use with care as comment being old
does not mean they have lost their importance.

.. _addon-weblate.removal.suggestions:

Stale suggestion removal
------------------------

.. versionadded:: 3.7

Set a timeframe for removal of suggestions.

This can be very useful in connection
with suggestion voting (see :ref:`peer-review`) to remove suggestions which
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

.. _addon-weblate.yaml.customize:

Customize YAML output
---------------------

.. versionadded:: 3.10.2

Allows adjusting YAML output behavior, for example line-length or newlines.


Customizing list of addons
++++++++++++++++++++++++++

The list of addons is configured by :setting:`WEBLATE_ADDONS`.
To add another addon, simply include class absolute name in this setting.


.. _own-addon:

Writing addon
+++++++++++++

You can write your own addons too, all you need to do is subclass ``BaseAddon``,
define the addon metadata and implement a callback which will do the processing.

Here is an example addon:

.. literalinclude:: ../../weblate/addons/example.py
    :language: python

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

    Fileformat used in current component.

.. envvar:: WL_LANGUAGE

    Language of currently processed translation (not available for component
    level hooks).

.. envvar:: WL_PREVIOUS_HEAD

    Previous HEAD on update (available only available when running post update hook).

.. envvar:: WL_COMPONENT_SLUG

   .. versionadded:: 3.9

   Component slug used to contruct URL.

.. envvar:: WL_PROJECT_SLUG

   .. versionadded:: 3.9

   Project slug used to contruct URL.

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

Post update repository processing
---------------------------------

Post update repository processing can be used to update translation files when
the VCS upstream source changes. To achieve this, please remember that Weblate only sees
files committed to the VCS, so you need to commit changes as a part
of the script.

For example with Gulp you can do it using following code:

.. code-block:: sh

    #! /bin/sh
    gulp --gulpfile gulp-i18n-extract.js
    git commit -m 'Update source strings' src/languages/en.lang.json


Pre commit processing of translations
-------------------------------------

Use the commit script to automatically make changes to the translation before it is committed
to the repository.

It is passed as a single parameter consisting of the filename of a current translation.
