.. _manage:

Management commands
===================

.. note::

    Running management commands under a different user than the one running your
    webserver can result in files getting wrong permissions, please check
    :ref:`file-permissions` for more details.

You will find basic management commands (available as :file:`./manage.py` in the Django sources,
or as an extended set in a script called :command:`weblate` installable atop Weblate).

.. _invoke-manage:

Invoking management commands
----------------------------

As mentioned before, invocation depends on how you installed Weblate.

If using virtualenv for Weblate, you can either specify the full path to
:command:`weblate`, or activate the virtualenv prior to invoking it:

.. code-block:: sh

   # Direct invocation
   ~/weblate-env/bin/weblate

   # Activating virtualenv adds it to search path
   . ~/weblate-env/bin/activate
   weblate

If you are using source code directly (either from a tarball or Git checkout), the
management script is :file:`./manage.py` available in the Weblate sources.
To run it:

.. code-block:: sh

    python ./manage.py list_versions

If you've installed Weblate using the pip or pip3 installer, or by using the :file:`./setup.py`
script, the :command:`weblate` is installed to your path (or virtualenv path),
from where you can use it to control Weblate:

.. code-block:: sh

    weblate list_versions

For the Docker image, the script is installed like above, and you can run it
using :command:`docker exec`:

.. code-block:: sh

    docker exec --user weblate <container> weblate list_versions

For :program:`docker-compose` the process is similar, you just have to use
:command:`docker-compose exec`:

.. code-block:: sh

    docker-compose exec --user weblate weblate weblate list_versions

In case you need to pass it a file, you can temporary add a volume:

.. code-block:: sh

    docker-compose exec --user weblate /tmp:/tmp weblate weblate importusers /tmp/users.json

.. seealso::

    :doc:`install/docker`,
    :doc:`install/venv-debian`,
    :doc:`install/venv-suse`,
    :doc:`install/venv-redhat`,
    :doc:`install/source`


add_suggestions
---------------

.. django-admin:: add_suggestions <project> <component> <language> <file>

.. versionadded:: 2.5

Imports a translation from the file to use as a suggestion for the given translation.
It skips duplicated translations; only different ones are added.

.. django-admin-option:: --author USER@EXAMPLE.COM

    E-mail of author for the suggestions. This user has to exist prior to importing
    (you can create one in the admin interface if needed).

Example:

.. code-block:: sh

    weblate --author michal@cihar.com add_suggestions weblate application cs /tmp/suggestions-cs.po


auto_translate
--------------

.. django-admin:: auto_translate <project> <component> <language>

.. versionadded:: 2.5

.. versionchanged:: 4.6

    Added parameter for translation mode.

Performs automatic translation based on other component translations.

.. django-admin-option:: --source PROJECT/COMPONENT

    Specifies the component to use as source available for translation.
    If not specified all components in the project are used.

.. django-admin-option:: --user USERNAME

    Specify username listed as author of the translations.
    "Anonymous user" is used if not specified.

.. django-admin-option:: --overwrite

    Whether to overwrite existing translations.

.. django-admin-option:: --inconsistent

    Whether to overwrite existing translations that are inconsistent (see
    :ref:`check-inconsistent`).

.. django-admin-option:: --add

    Automatically add language if a given translation does not exist.

.. django-admin-option:: --mt MT

    Use machine translation instead of other components as machine translations.

.. django-admin-option:: --threshold THRESHOLD

    Similarity threshold for machine translation, defaults to 80.

.. django-admin-option:: --mode MODE

    Specify translation mode, default is "translate" but "fuzzy" or "suggest"
    can be used.

Example:

.. code-block:: sh

    weblate auto_translate --user nijel --inconsistent --source weblate/application weblate website cs

.. seealso::

   :ref:`auto-translation`

celery_queues
-------------

.. django-admin:: celery_queues

.. versionadded:: 3.7

Displays length of Celery task queues.

checkgit
--------

.. django-admin:: checkgit <project|project/component>

Prints current state of the back-end Git repository.

You can either define which project or component to update (for example
``weblate/application``), or use ``--all`` to update all existing components.

commitgit
---------

.. django-admin:: commitgit <project|project/component>

Commits any possible pending changes to the back-end Git repository.

You can either define which project or component to update (for example
``weblate/application``), or use ``--all`` to update all existing components.

commit_pending
--------------

.. django-admin:: commit_pending <project|project/component>

Commits pending changes older than a given age.

You can either define which project or component to update (for example
``weblate/application``), or use ``--all`` to update all existing components.

.. django-admin-option:: --age HOURS

    Age in hours for committing. If not specified the value configured in
    :ref:`component` is used.

.. note::

   This is automatically performed in the background by Weblate, so there no
   real need to invoke this manually, besides forcing an earlier commit than
   specified by :ref:`component`.

.. seealso::

    :ref:`production-cron`,
    :setting:`COMMIT_PENDING_HOURS`

cleanuptrans
------------

.. django-admin:: cleanuptrans

Cleans up orphaned checks and translation suggestions. There is normally no need to run this
manually, as the cleanups happen automatically in the background.

.. seealso::

   :ref:`production-cron`

createadmin
-----------

.. django-admin:: createadmin

Creates an ``admin`` account with a random password, unless it is specified.

.. django-admin-option:: --password PASSWORD

    Provides a password on the command-line, to not generate a random one.

.. django-admin-option:: --no-password

    Do not set password, this can be useful with `--update`.

.. django-admin-option:: --username USERNAME

    Use the given name instead of ``admin``.

.. django-admin-option:: --email USER@EXAMPLE.COM

    Specify the admin e-mail address.

.. django-admin-option:: --name

    Specify the admin name (visible).

.. django-admin-option:: --update

    Update the existing user (you can use this to change passwords).

.. versionchanged:: 2.9

    Added parameters ``--username``, ``--email``, ``--name`` and ``--update``.

dump_memory
-----------

.. django-admin:: dump_memory

.. versionadded:: 2.20

Export a JSON file containing Weblate Translation Memory content.

.. seealso::

    :ref:`translation-memory`,
    :ref:`schema-memory`

dumpuserdata
------------

.. django-admin:: dumpuserdata <file.json>

Dumps userdata to a file for later use by :djadmin:`importuserdata`

.. hint::

   This comes in handy when migrating or merging Weblate instances.

import_demo
-----------

.. django-admin:: import_demo

.. versionadded:: 4.1

Creates a demo project with components based on <https://github.com/WeblateOrg/demo>.

This can be useful when developing Weblate.


import_json
-----------

.. django-admin:: import_json <json-file>

.. versionadded:: 2.7

Batch import of components based on JSON data.

The imported JSON file structure pretty much corresponds to the component
object (see :http:get:`/api/components/(string:project)/(string:component)/`).
You have to include the ``name`` and ``filemask`` fields.

.. django-admin-option:: --project PROJECT

    Specifies where the components will be imported from.

.. django-admin-option:: --main-component COMPONENT

    Use the given VCS repository from this component for all of them.

.. django-admin-option:: --ignore

    Skip (already) imported components.

.. django-admin-option:: --update

    Update (already) imported components.

.. versionchanged:: 2.9

    The parameters ``--ignore`` and ``--update`` are there to deal with already
    imported components.

Example of JSON file:

.. literalinclude:: ../../weblate/trans/tests/data/components.json
   :language: json

.. seealso::

    :djadmin:`import_memory`

import_memory
-------------

.. django-admin:: import_memory <file>

.. versionadded:: 2.20

Imports a TMX or JSON file into the Weblate translation memory.

.. django-admin-option:: --language-map LANGMAP

    Allows mapping languages in the TMX to the Weblate translation memory.
    The language codes are mapped after normalization usually done by Weblate.

    ``--language-map en_US:en`` will for example import all ``en_US`` strings
    as ``en`` ones.

    This can be useful in case your TMX file locales happen not to match what you
    use in Weblate.

.. seealso::

    :ref:`translation-memory`,
    :ref:`schema-memory`

import_project
--------------

.. django-admin:: import_project <project> <gitrepo> <branch> <filemask>

.. versionchanged:: 3.0

    The import_project command is now based on the
    :ref:`addon-weblate.discovery.discovery` addon, leading to some
    changes in behavior and what parameters are accepted.

Batch imports components into project based on filemask.

`<project>` names an existing project, into which the components are to
be imported.

The `<gitrepo>` defines the Git repository URL to use, and `<branch>` signifies the
Git branch.
To import additional translation components from an existing Weblate component,
use a `weblate://<project>/<component>` URL for the `<gitrepo>`.

The `<filemask>` defines file discovery for the repository. It can be either
be made simple using wildcards, or it can use the full power of regular expressions.

The simple matching uses ``**`` for component name and ``*`` for language, for
example: ``**/*.po``

The regular expression has to contain groups named `component` and `language`.
For example: ``(?P<language>[^/]*)/(?P<component>[^-/]*)\.po``

The import matches existing components based on files and adds the ones that
do not exist. It does not change already existing ones.

.. django-admin-option:: --name-template TEMPLATE

    Customize the name of a component using Django template syntax.

    For example: ``Documentation: {{ component }}``

.. django-admin-option:: --base-file-template TEMPLATE

    Customize the base file for monolingual translations.

    For example: ``{{ component }}/res/values/string.xml``

.. django-admin-option:: --new-base-template TEMPLATE

    Customize the base file for addition of new translations.

    For example: ``{{ component }}/ts/en.ts``

.. django-admin-option:: --file-format FORMAT

    You can also specify the file format to use (see :ref:`formats`), the default
    is auto-detection.

.. django-admin-option:: --language-regex REGEX

    You can specify language filtering (see :ref:`component`) with this
    parameter. It has to be a valid regular expression.

.. django-admin-option:: --main-component

    You can specify which component will be chosen as the main one—the one actually
    containing the VCS repository.

.. django-admin-option:: --license NAME

    Specify the overall, project or component translation license.

.. django-admin-option:: --license-url URL

    Specify the URL where the translation license is to be found.

.. django-admin-option:: --vcs NAME

    In case you need to specify which version control system to use, you can do it
    here. The default version control is Git.

To give you some examples, let's try importing two projects.

First The Debian Handbook translations, where each language has
separate a folder with the translations of each chapter:

.. code-block:: sh

    weblate import_project \
        debian-handbook \
        git://anonscm.debian.org/debian-handbook/debian-handbook.git \
        squeeze/master \
        '*/**.po'

Then the Tanaguru tool, where the file format needs be specified,
along with the base file template, and how all components and translations
are located in single folder:

.. code-block:: sh

    weblate import_project \
        --file-format=properties \
        --base-file-template=web-app/tgol-web-app/src/main/resources/i18n/%s-I18N.properties \
        tanaguru \
        https://github.com/Tanaguru/Tanaguru \
        master \
        web-app/tgol-web-app/src/main/resources/i18n/**-I18N_*.properties

More complex example of parsing of filenames to get the correct component and
language out of a filename like
``src/security/Numerous_security_holes_in_0.10.1.de.po``:

.. code-block:: sh

    weblate import_project \
        tails \
        git://git.tails.boum.org/tails master \
        'wiki/src/security/(?P<component>.*)\.(?P<language>[^.]*)\.po$'

Filtering only translations in a chosen language:

.. code-block:: sh

    ./manage import_project \
        --language-regex '^(cs|sk)$' \
        weblate \
        https://github.com/WeblateOrg/weblate.git \
        'weblate/locale/*/LC_MESSAGES/**.po'

Importing Sphinx documentation split to multiple files:

.. code-block:: console

    $ weblate import_project --name-template 'Documentation: %s' \
        --file-format po \
        project https://github.com/project/docs.git master \
        'docs/locale/*/LC_MESSAGES/**.po'

Importing Sphinx documentation split to multiple files and directories:

.. code-block:: console

    $ weblate import_project --name-template 'Directory 1: %s' \
        --file-format po \
        project https://github.com/project/docs.git master \
        'docs/locale/*/LC_MESSAGES/dir1/**.po'
    $ weblate import_project --name-template 'Directory 2: %s' \
        --file-format po \
        project https://github.com/project/docs.git master \
        'docs/locale/*/LC_MESSAGES/dir2/**.po'

.. seealso::

    More detailed examples can be found in the :ref:`starting` chapter,
    alternatively you might want to use :djadmin:`import_json`.

importuserdata
--------------

.. django-admin:: importuserdata <file.json>

Imports user data from a file created by :djadmin:`dumpuserdata`

importusers
-----------

.. django-admin:: importusers --check <file.json>

Imports users from JSON dump of the Django auth_users database.


.. django-admin-option:: --check

    With this option it will just check whether a given file can be imported and
    report possible conflicts arising from usernames or e-mails.

You can dump users from the existing Django installation using:

.. code-block:: sh

    weblate dumpdata auth.User > users.json

install_addon
-------------

.. versionadded:: 3.2

.. django-admin:: install_addon --addon ADDON <project|project/component>

Installs an addon to a set of components.

.. django-admin-option:: --addon ADDON

   Name of the addon to install. For example ``weblate.gettext.customize``.

.. django-admin-option:: --configuration CONFIG

   JSON encoded configuration of an addon.

.. django-admin-option:: --update

   Update the existing addon configuration.

You can either define which project or component to install the addon in (for example
``weblate/application``), or use ``--all`` to include all existing components.

To install :ref:`addon-weblate.gettext.customize` for all components:

.. code-block:: shell

   weblate install_addon --addon weblate.gettext.customize --config '{"width": -1}' --update --all

.. seealso::

   :ref:`addons`

list_languages
--------------

.. django-admin:: list_languages <locale>

Lists supported languages in MediaWiki markup - language codes, English names
and localized names.

This is used to generate <https://wiki.l10n.cz/Slovn%C3%ADk_s_n%C3%A1zvy_jazyk%C5%AF>.

list_translators
----------------

.. django-admin:: list_translators <project|project/component>

Lists translators by contributed language for the given project::

    [French]
    Jean Dupont <jean.dupont@example.com>
    [English]
    John Doe <jd@example.com>

.. django-admin-option:: --language-code

    List names by language code instead of language name.

You can either define which project or component to use (for example
``weblate/application``), or use ``--all`` to list translators from all existing
components.

list_versions
-------------

.. django-admin:: list_versions

Lists all Weblate dependencies and their versions.

loadpo
------

.. django-admin:: loadpo <project|project/component>

Reloads translations from disk (for example in case you have done some updates in the VCS
repository).

.. django-admin-option:: --force

    Force update, even if the files should be up-to-date.

.. django-admin-option:: --lang LANGUAGE

    Limit processing to a single language.

You can either define which project or component to update (for example
``weblate/application``), or use ``--all`` to update all existing components.

.. note::

    You seldom need to invoke this, Weblate will automatically load changed
    files for every VCS update. This is needed in case you manually changed an
    underlying Weblate VCS repository or in some special cases following an upgrade.

lock_translation
----------------

.. django-admin:: lock_translation <project|project/component>

Prevents further translation of a component.

.. hint::

    Useful in case you want to do some maintenance on the underlying repository.

You can either define which project or component to update (for example
``weblate/application``), or use ``--all`` to update all existing components.

.. seealso::

   :djadmin:`unlock_translation`

move_language
-------------

.. django-admin:: move_language source target

.. versionadded:: 3.0

Allows you to merge language content. This is useful when updating to a new
version which contains aliases for previously unknown languages that have been
created with the `(generated)` suffix. It moves all content from the `source`
language to the `target` one.

Example:

.. code-block:: sh

   weblate move_language cze cs

After moving the content, you should check whether there is anything left (this is
subject to race conditions when somebody updates the repository meanwhile) and
remove the `(generated)` language.

pushgit
-------

.. django-admin:: pushgit <project|project/component>

Pushes committed changes to the upstream VCS repository.

.. django-admin-option:: --force-commit

    Force commits any pending changes, prior to pushing.

You can either define which project or component to update (for example
``weblate/application``), or use ``--all`` to update all existing components.

.. note::

    Weblate pushes changes automatically if :ref:`component-push_on_commit` in
    :ref:`component` is turned on, which is the default.

unlock_translation
------------------

.. django-admin:: unlock_translation <project|project/component>

Unlocks a given component, making it available for translation.

.. hint::

    Useful in case you want to do some maintenance on the underlying repository.

You can either define which project or component to update (for example
``weblate/application``), or use ``--all`` to update all existing components.

.. seealso::

   :djadmin:`lock_translation`

setupgroups
-----------

.. django-admin:: setupgroups

Configures default groups and optionally assigns all users to that default group.

.. django-admin-option:: --no-privs-update

    Turns off automatic updating of existing groups (only adds new ones).

.. django-admin-option:: --no-projects-update

    Prevents automatic updates of groups for existing projects. This allows adding newly
    added groups to existing projects, see :ref:`acl`.

.. seealso::

   :ref:`privileges`

setuplang
---------

.. django-admin:: setuplang

Updates list of defined languages in Weblate.

.. django-admin-option:: --no-update

    Turns off automatic updates of existing languages (only adds new ones).

updatechecks
------------

.. django-admin:: updatechecks <project|project/component>

Updates all checks for all strings.

.. hint::

    Useful for upgrades which do major changes to checks.

You can either define which project or component to update (for example
``weblate/application``), or use ``--all`` to update all existing components.

updategit
---------

.. django-admin:: updategit <project|project/component>

Fetches remote VCS repositories and updates the internal cache.

You can either define which project or component to update (for example
``weblate/application``), or use ``--all`` to update all existing components.

.. note::

    Usually it is better to configure hooks in the repository to trigger
    :ref:`hooks`, instead of regular polling by :djadmin:`updategit`.
