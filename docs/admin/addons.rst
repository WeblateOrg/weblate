.. _addons:

Addons
======

.. versionadded:: 2.19

Addons provide ways to customize translation workflow. You can install addons
to your translation component and they will work behind the scenes. The addon
management can be found under :guilabel:`Manage` menu of a translation
component.

.. image:: /images/addons.png

Built in addons
+++++++++++++++

.. _addon-weblate.autotranslate.autotranslate:

Automatic translation
---------------------

.. versionadded:: 3.9

This addon automatically translates strings using machine translation or other
components.

.. seealso:: 
   
   :ref:`auto-translation`

.. _addon-weblate.cleanup.generic:

Cleanup translation files
-------------------------

Update all translation files to match the monolingual base file. For most file
formats, this means removing stale translation keys no longer present in the
base file.

.. _addon-weblate.consistency.languages:

Language consistency
--------------------

Ensure that all components within one project have translation to same
languages. It will create empty translations for languages which are not
present.

Missing languages are checked once in a 24 hours and when new language is being
added in Weblate.

Unlike most others, this addon operates on whole project.

.. hint::

   If you want to translate the strings as well, please look into
   :ref:`addon-weblate.autotranslate.autotranslate`.

.. _addon-weblate.discovery.discovery:

Component discovery
-------------------

This addon automatically adds or removes components to the project based on
file changes in the version control system.

It is similar to the :djadmin:`import_project` management command, but the
major difference is that it is triggered on every VCS update. This way you can
easily track multiple translation components within one VCS.

To use component discovery, you first need to create one component which will
act as master and others will use :ref:`internal-urls` to it as a VCS
configuration. You should choose the one which is less likely to disappear in
the future here.

Once you have one component from the target VCS, you can configure the
discovery addon to find all translation components in the VCS. The matching is
done using regular expression so it can be quite powerful, but it can be complex
to configure. You can use examples in the addon help for some common use cases.

Once you hit save, you will be presented with a preview of matched components,
so you can check whether the configuration actually matches your needs:

.. image:: /images/addon-discovery.png

.. seealso::

    :ref:`markup`

.. _addon-weblate.flags.same_edit:

Flag unchanged translations as "Needs editing"
----------------------------------------------

.. versionadded:: 3.1

Whenever a new translatable string is imported from the VCS and it matches
source strings, it is flagged as needing editing in Weblate. This is especially
useful for file formats that include all strings even if they are not
translated.

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

This addon generates a file containing detailed information about the
translation. You can use Django template in both filename and content, see
:ref:`markup` for detailed markup description.

For example generating summary file for each translations:

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

Update comment in the PO file header to include contributor name and years of
contributions.

.. _addon-weblate.gettext.configure:

Update ALL_LINGUAS variable in the "configure" file
---------------------------------------------------

Updates the ALL_LINGUAS variable in :file:`configure`, :file:`configure.in` or
:file:`configure.ac` files, when a new translation is added.

.. _addon-weblate.gettext.customize:

Customize gettext output
------------------------

Allows customization of gettext output behavior, for example line wrapping.

It offers following options:


* Wrap lines at 77 characters and at newlines
* Only wrap lines at newlines
* No line wrapping

.. note::

   By default gettext wraps lines at 77 characters and newlines. With
   ``--no-wrap`` parameter, it wraps only at newlines.


.. _addon-weblate.gettext.linguas:

Update LINGUAS file
-------------------

Updates the LINGUAS file when a new translation is added.

.. _addon-weblate.gettext.mo:

Generate MO files
-----------------

Automatically generates MO file for every changed PO file.

.. _addon-weblate.gettext.msgmerge:

Update PO files to match POT (msgmerge)
---------------------------------------

Update all PO files to match the POT file using msgmerge. This is triggered
whenever new changes are pulled from the upstream repository.

.. _addon-weblate.git.squash:

Squash Git commits
------------------

Squash Git commits prior to pushing changes. You can choose one of following modes:

* All commits into one
* Per language
* Per file
* Per author

Original commit messages are kept, but authorship is lost unless "Per author" is selected or the commit message is customized to include it.

.. _addon-weblate.json.customize:

Customize JSON output
---------------------

Allows to customize JSON output behavior, for example indentation or sorting.

.. _addon-weblate.properties.sort:

Formats the Java properties file
--------------------------------

This addon sorts the Java properties file.

.. _addon-weblate.removal.comments:

Stale comment removal
---------------------

.. versionadded:: 3.7

Set timeframe for removal of comments. This can be useful to remove old
comments which might have become outdated. Use with care as comment being old
does not mean it has lost it's importation.

.. _addon-weblate.removal.suggestions:

Stale suggestion removal
------------------------

.. versionadded:: 3.7

Set timeframe for removal of suggestions. This can be very useful in connection
with suggestion voting (see :ref:`peer-review`) to remove suggestions which
don't receive enough positive votes until certain deadline.

.. _addon-weblate.resx.update:

Update RESX files
-----------------

.. versionadded:: 3.9

Update all translation files to match the monolingual upstream base file.
Unused strings are removed, and new ones are added as copies of the source
string.

.. hint::

   Use :ref:`addon-weblate.cleanup.generic` if you only want to remove stale
   translation keys.


Customizing list of addons
++++++++++++++++++++++++++

List of addons is configured by :setting:`WEBLATE_ADDONS`, to add another addon
simply include class absolute name in this setting.


.. _own-addon:

Writing addon
+++++++++++++

You can write own addons as well, all you need to do is subclass ``BaseAddon``,
define addon metadata and implement callback which will do the processing.

You can look at example addon for more information:

.. literalinclude:: ../../weblate/addons/example.py
    :language: python

.. _addon-script:

Executing scripts from addon
++++++++++++++++++++++++++++

You can also use addons to execute external scripts. This used to be
integrated in Weblate, but now you have to write little code to wrap your
script with an addon.

.. literalinclude:: ../../weblate/addons/example_pre.py
    :language: python

For installing instructions see :ref:`custom-addon-modules`.

The script is executed with the current directory set to the root of the VCS repository
for given component.

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

    File mask for current component.

.. envvar:: WL_TEMPLATE

    File name of template for monolingual translations (can be empty).

.. envvar:: WL_NEW_BASE

    .. versionadded:: 2.14

    File name of the file which is used for creating new translations (can be
    empty).

.. envvar:: WL_FILE_FORMAT

    File format used in current component.

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

   Component URL

.. envvar:: WL_ENGAGE_URL

   .. versionadded:: 3.9

   Project engage URL

.. seealso::

    :ref:`component`

Post update repository processing
---------------------------------

Post update repository processing can be used to update translation files on
the source change. To achieve this, please remember that Weblate only sees
files which are committed to the VCS, so you need to commit changes as a part
of the script.

For example with gulp you can do it using following code:

.. code-block:: sh

    #! /bin/sh
    gulp --gulpfile gulp-i18n-extract.js
    git commit -m 'Update source strings' src/languages/en.lang.json


Pre commit processing of translations
-------------------------------------

In many cases you might want to automatically do some changes to the translation
before it is committed to the repository. The pre commit script is exactly the
place to achieve this.

It is passed a single parameter consisting of filename of current translation.
