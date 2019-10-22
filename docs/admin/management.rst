.. _manage:

Management commands
===================

.. note::

    Running management commands under a different user than is running your
    webserver can cause wrong permissions on some files, please check
    :ref:`file-permissions` for more details.

Django comes with a management script (available as :file:`./manage.py` in
sources or installed as :command:`weblate` when Weblate is installed). It
provides various management commands and Weblate extends it with several
additional commands.

.. _invoke-manage:

Invoking management commands
----------------------------

As mentioned before, invocation depends on how you have installed Weblate.

If you are using virtualenv for Weblate, you can either specify full path to
:command:`weblate` or activate the virtualenv prior invoking it:

.. code-block:: sh
   
   # Direct invocation
   ~/weblate-env/bin/weblate

   # Activating virtualenv adds it to search path
   . ~/weblate-env/bin/activate
   weblate

If you are using source code directly (either tarball or Git checkout), the
management script is :file:`./manage.py` in Weblate sources. Execution can be
done as:

.. code-block:: sh

    python ./manage.py list_versions

If you've installed Weblate using PIP installer or by :file:`./setup.py`
script, the :command:`weblate` is installed to your path (or virtualenv path)
and you can use it to control Weblate:

.. code-block:: sh

    weblate list_versions

For Docker image, the script is installed same as above, you can execute it
using :command:`docker exec`:

.. code-block:: sh

    docker exec --user weblate <container> weblate list_versions

With :program:`docker-compose` this is quite similar, you just have to use
:command:`docker-compose exec`:

.. code-block:: sh

    docker-compose exec --user weblate weblate weblate list_versions

In case you need to pass some file, you can temporary add a volume:

.. code-block:: sh

    docker-compose exec --user weblate /tmp:/tmp weblate weblate importusers /tmp/users.json

.. seealso::

    :ref:`quick-docker`,
    :doc:`install/venv-debian`,
    :doc:`install/venv-suse`,
    :doc:`install/venv-redhat`

* :ref:`quick-source`, recommended for development.


add_suggestions
---------------

.. django-admin:: add_suggestions <project> <component> <language> <file>

.. versionadded:: 2.5

Imports translation from the file as a suggestion to given translation. It
skips translations which are the same as existing ones, only different ones are
added.

.. django-admin-option:: --author USER@EXAMPLE.COM

    Email of author for the suggestions. This user has to exist prior importing
    (you can create one in the admin interface if needed).

Example:

.. code-block:: sh

    ./manage.py --author michal@cihar.com add_suggestions weblate master cs /tmp/suggestions-cs.po


auto_translate
--------------

.. django-admin:: auto_translate <project> <component> <language>

.. versionadded:: 2.5

Performs automatic translation based on other component translations.

.. django-admin-option:: --source PROJECT/COMPONENT

    Specifies component to use as source for translation. If not specified
    all components in the project are used.

.. django-admin-option:: --user USERNAME

    Specify username who will be author of the translations. Anonymous user
    is used if not specified.

.. django-admin-option:: --overwrite

    Whether to overwrite existing translations.

.. django-admin-option:: --inconsistent

    Whether to overwrite existing translations which are inconsistent (see
    :ref:`check-inconsistent`).

.. django-admin-option:: --add

    Automatically add language if given translation does not exist.

.. django-admin-option:: --mt MT

    Use machine translation instead of other components.

.. django-admin-option:: --threshold THRESHOLD

    Similarity threshold for machine translation, defaults to 80.

Example:

.. code-block:: sh

    ./manage.py --user nijel --inconsistent --source phpmyadmin/master phpmyadmin 4-5 cs

.. seealso::

   :ref:`auto-translation`

celery_queues
-------------

.. django-admin:: celery_queues

.. versionadded:: 3.7

Displays length of Celery task queues.

changesite
----------

.. django-admin:: changesite

.. versionadded:: 2.4

You can use this to change or display site name from command line without using
admin interface.

.. django-admin-option:: --set-name NAME

    Sets name for the site.

.. django-admin-option:: --get-name

    Prints currently configured site name.

.. seealso::

   :ref:`production-site`

checkgit
--------

.. django-admin:: checkgit <project|project/component>

Prints current state of the backend git repository.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

commitgit
---------

.. django-admin:: commitgit <project|project/component>

Commits any possible pending changes to backend git repository.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

commit_pending
--------------

.. django-admin:: commit_pending <project|project/component>

Commits pending changes older than given age.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

.. django-admin-option:: --age HOURS

    Age in hours for committing. If not specified value configured in
    :ref:`component` is used.

.. note::

   This is automatically perfomed in the background by Weblate, so there is not
   much reason to invoke this manually besides forcing earlier commit than
   specified by :ref:`component`.

.. seealso::

    :ref:`production-cron`,
    :setting:`COMMIT_PENDING_HOURS`

cleanup_avatar_cache
--------------------

.. versionadded:: 3.1

.. django-admin:: cleanup_avatar_cache

Removes invalid items in avatar cache. This can be useful when switching
between Python 2 and 3 as the cache files might be not compatible.

cleanuptrans
------------

.. django-admin:: cleanuptrans

Cleanups orphaned checks and translation suggestions. This is normally not
needed to execute manually, the cleanups happen automatically in the
background.

.. seealso::

   :ref:`production-cron`

createadmin
-----------

.. django-admin:: createadmin

Creates ``admin`` account with random password unless it is specified.

.. django-admin-option:: --password PASSWORD

    Provide password on the command line and skip generating random one.

.. django-admin-option:: --no-password

    Do not set password, this can be useful with --update.

.. django-admin-option:: --username USERNAME

    Use given name instead of ``admin``.

.. django-admin-option:: --email USER@EXAMPLE.COM

    Specify admin e-mail.

.. django-admin-option:: --name

    Specify admin name (visible).

.. django-admin-option:: --update

    Update existing user (you can use this to change password).

.. versionchanged:: 2.9

    Added parameters ``--username``, ``--email``, ``--name`` and ``--update``.

delete_memory
-------------

.. django-admin:: delete_memory

.. versionadded:: 2.20

Deletes entries in the Weblate Translation Memory.

.. django-admin-option:: --origin ORIGIN

    Origin to delete, for imported files the origin is filename without path.

.. django-admin-option:: --all

    Delete complete memory content and recreate the database.

.. seealso::

    :ref:`translation-memory`

dump_memory
-----------

.. django-admin:: dump_memory

.. versionadded:: 2.20

Export a JSON file with the Weblate Translation Memory content.

.. seealso::

    :ref:`translation-memory`

dumpuserdata
------------

.. django-admin:: dumpuserdata <file.json>

Dumps userdata to file for later use by :djadmin:`importuserdata`

This is useful when migrating or merging Weblate instances.

import_json
-----------

.. django-admin:: import_json <json-file>

.. versionadded:: 2.7

Batch import of components based on JSON data.

The imported JSON file structure pretty much corresponds to the component
object (see :http:get:`/api/components/(string:project)/(string:component)/`).
You always have to include fields ``name`` and ``filemask``.

.. django-admin-option:: --project PROJECT

    Specifies where the components will be imported.

.. django-admin-option:: --main-component COMPONENT

    Use VCS repository from this component for all.

.. django-admin-option:: --ignore

    Skip already imported components.

.. django-admin-option:: --update

    Update already imported components.

.. versionchanged:: 2.9

    Added parameters ``--ignore`` and ``--update`` to deal with already
    imported components.

Example of JSON file:

.. literalinclude:: ../../weblate/trans/tests/data/components.json
   :language: json
   :encoding: utf-8

.. seealso::

    :djadmin:`import_memory`

import_memory
-------------

.. django-admin:: import_memory <file>

.. versionadded:: 2.20

Imports a TMX or JSON file into the Weblate Translation Memory.

.. django-admin-option:: --language-map LANGMAP

    Allows to map languages in the TMX to Weblate one. The language codes are
    mapped after normalization usually done by Weblate.

    For example ``--language-map en_US:en`` will import all ``en_US`` strings
    as ``en`` ones.

    This can be useful in case your TMX file locales does not match what you
    use in Weblate.

.. seealso::

    :ref:`translation-memory`

import_project
--------------

.. django-admin:: import_project <project> <gitrepo> <branch> <filemask>

.. versionchanged:: 3.0

    The import_project command is now based on the
    :ref:`addon-weblate.discovery.discovery` addon and that has lead to some
    changes in behavior and accepted parameters.

Batch imports components into project based on file mask.

`<project>` names an existing project, into which the components should
be imported.

The `<gitrepo>` defines URL of Git repository to use, and `<branch>` the
git branch.
To import additional translation components, from an existing Weblate component,
use a `weblate://<project>/<component>` URL for the `<gitrepo>`.

The `<filemask>` defines files discovery in the repository. It can be either
simple using wildcards or it can use full power of regular expressions.

The simple matching uses ``**`` for component name and ``*`` for language, for
example: ``**/*.po``

The regular expression has to contain named groups `component` and `language`.
For example: ``(?P<language>[^/]*)/(?P<component>[^-/]*)\.po``

The import matches existing components based on files and adds the ones which
do not exist. It does no changes to the already existing ones.

.. django-admin-option:: --name-template TEMPLATE

    Customize the component's name, using Django template syntax.

    For example: ``Documentation: {{ component }}``

.. django-admin-option:: --base-file-template TEMPLATE

    Customize base file for monolingual translations.

    For example: ``{{ component }}/res/values/string.xml``

.. django-admin-option:: --new-base-template TEMPLATE

    Customize base file for adding new translations.

    For example: ``{{ component }}/ts/en.ts``

.. django-admin-option:: --file-format FORMAT

    You can also specify file format to use (see :ref:`formats`), the default
    is autodetection.

.. django-admin-option:: --language-regex REGEX

    You can specify language filtering (see :ref:`component`) by this
    parameter. It has to be valid regular expression.

.. django-admin-option:: --main-component

    You can specify which component will be chosen as main - the one actually
    containing VCS repository.

.. django-admin-option:: --license NAME

    Specify translation license.

.. django-admin-option:: --license-url URL

    Specify translation license URL.

.. django-admin-option:: --vcs NAME

    In case you need to specify version control system to use, you can do it
    here. The default version control is Git.

To give you some examples, let's try importing two projects.

As first we import The Debian Handbook translations, where each language has
separate folder with translations of each chapter:

.. code-block:: sh

    ./manage.py import_project \
        debian-handbook \
        git://anonscm.debian.org/debian-handbook/debian-handbook.git \
        squeeze/master \
        '*/**.po'

Another example can be Tanaguru tool, where we need to specify file format,
base file template and has all components and translations located in single
folder:

.. code-block:: sh

    ./manage.py import_project \
        --file-format=properties \
        --base-file-template=web-app/tgol-web-app/src/main/resources/i18n/%s-I18N.properties \
        tanaguru \
        https://github.com/Tanaguru/Tanaguru \
        master \
        web-app/tgol-web-app/src/main/resources/i18n/**-I18N_*.properties

Example of more complex parsing of filenames to get correct component and
language out of filename like
``src/security/Numerous_security_holes_in_0.10.1.de.po``:

.. code-block:: sh

    ./manage.py import_project \
        tails \
        git://git.tails.boum.org/tails master \
        'wiki/src/security/(?P<component>.*)\.(?P<language>[^.]*)\.po$'

Filtering only translations in chosen language:

.. code-block:: sh

    ./manage import_project \
        --language-regex '^(cs|sk)$' \
        weblate \
        https://github.com/WeblateOrg/weblate.git \
        'weblate/locale/*/LC_MESSAGES/**.po'

.. seealso::

    More detailed examples can be found in the :ref:`starting` chapter,
    alternatively you might want to use :djadmin:`import_json`.

importuserdata
--------------

.. django-admin:: importuserdata <file.json>

Imports userdata from file created by :djadmin:`dumpuserdata`

importusers
-----------

.. django-admin:: importusers --check <file.json>

Imports users from JSON dump of Django auth_users database.


.. django-admin-option:: --check

    With this option it will just check whether given file can be imported and
    report possible conflicts on usernames or e-mails.

You can dump users from existing Django installation using:

.. code-block:: sh

    ./manage.py dumpdata auth.User > users.json

install_addon
-------------

.. versionadded:: 3.2

.. django-admin:: install_addon --addon ADDON <project|project/component>

Installs addon to set of components.

.. django-admin-option:: --addon ADDON

   Name of addon to install. For example ``weblate.gettext.customize``.

.. django-admin-option:: --configuration CONFIG

   JSON encoded configuration of an addon.

.. django-admin-option:: --update

   Update existing addon configuration.

You can either define on which project or component to install addon (eg.
``weblate/master``) or use ``--all`` to include all existing components.

For example installing :ref:`addon-weblate.gettext.customize` to all components:

.. code-block:: shell

   ./manage.py install_addon --addon weblate.gettext.customize --config '{"width": -1}' --update --all

.. seealso::

   :ref:`addons`

list_ignored_checks
-------------------

.. django-admin:: list_ignored_checks

Lists most frequently ignored checks. This can be useful for tuning your setup,
if users have to ignore too many of consistency checks.

list_languages
--------------

.. django-admin:: list_languages <locale>

Lists supported language in MediaWiki markup - language codes, English names
and localized names.

This is used to generate <https://wiki.l10n.cz/Jazyky>.

list_memory
-----------

.. django-admin:: list_memory

.. versionadded:: 2.20

Lists contents of the Weblate Translation Memory.

.. django-admin-option:: --type {origin}

    Type of information to list, defaults to listing used origins.

.. seealso::

    :ref:`translation-memory`

list_translators
----------------

.. django-admin:: list_translators <project|project/component>

Renders the list of translators by language for the given project::

    [French]
    Jean Dupont <jean.dupont@example.com>
    [English]
    John Doe <jd@exemple.com>

.. django-admin-option:: --language-code

    Use language code instead of language name in output.

You can either define which project or component to use (eg.
``weblate/master``) or use ``--all`` to list translators from all existing
components.

list_versions
-------------

.. django-admin:: list_versions

Lists versions of Weblate dependencies.

loadpo
------

.. django-admin:: loadpo <project|project/component>

Reloads translations from disk (eg. in case you did some updates in VCS
repository).

.. django-admin-option:: --force

    Force update even if the files should be up to date.

.. django-admin-option:: --lang LANGUAGE

    Limit processing to single language.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

.. note::

    You seldom need to invoke this, Weblate will automatically load changed
    files on VCS update. This is needed in case you manually change underlying
    Weblate VCS repository or in some special cases after upgrade.

lock_translation
----------------

.. django-admin:: lock_translation <project|project/component>

Locks given component for translating. This is useful in case you want to do
some maintenance on underlying repository.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

.. seealso::

   :djadmin:`unlock_translation`

move_language
-------------

.. django-admin:: move_language source target

.. versionadded:: 3.0

Allows you to merge language content. This is useful when updating to new
version which contains aliases for previously unknown languages which were
created with the `(generated)` suffix. It moves all content from the `source`
language to `target` one.

Example:

.. code-block:: sh

   ./manage.py move_language cze cs

After moving the content, you should review if there is nothing left (this is
subject to race conditions when somebody updates the repository meanwhile) and
remove the `(generated)` language.

optimize_memory
---------------

.. django-admin:: optimize_memory

.. versionadded:: 3.2

Optimizes translation memory storage.

.. django-admin-option:: --rebuild

    The index will be completely rebuilt by dumping all content and creating it again.
    It is recommended to backup it prior to this operation.

.. seealso::

    :ref:`translation-memory`,
    :doc:`backup`,
    :djadmin:`dump_memory`

pushgit
-------

.. django-admin:: pushgit <project|project/component>

Pushes committed changes to upstream VCS repository.

.. django-admin-option:: --force-commit

    Force committing any pending changes prior to push.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

.. note::

    Weblate does push changes automatically if :guilabel:`Push on commit` in
    :ref:`component` is enabled, what is default.

rebuild_index
-------------

.. django-admin:: rebuild_index <project|project/component>

Rebuilds index for fulltext search. This might be lengthy operation if you
have a huge set of translation strings.

.. django-admin-option:: --clean

    Removes all words from database prior updating, this is implicit when
    called with ``--all``.

.. django-admin-option:: --optimize

    The index will not be processed again, only its content will be optimized
    (removing stale entries and merging possibly split index files).

.. seealso::

   :ref:`fulltext`

unlock_translation
------------------

.. django-admin:: unlock_translation <project|project/component>

Unlocks a given component for translating. This is useful in case you want to do
some maintenance on the underlying repository.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

.. seealso::

   :djadmin:`lock_translation`

setupgroups
-----------

.. django-admin:: setupgroups

Configures default groups and optionally assigns all users to default group.

.. django-admin-option:: --no-privs-update

    Disables update of existing groups (only adds new ones).

.. django-admin-option:: --no-projects-update

    Prevents updates of groups for existing projects. This allows to add newly
    added groups to existing projects, see :ref:`acl`.

.. seealso::

   :ref:`privileges`

setuplang
---------

.. django-admin:: setuplang

Updates list of defined languages in Weblate.

.. django-admin-option:: --no-update

    Disables update of existing languages (only adds new ones).

updatechecks
------------

.. django-admin:: updatechecks <project|project/component>

Updates all check for all strings. This could be useful only on upgrades
which do major changes to checks.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

updategit
---------

.. django-admin:: updategit <project|project/component>

Fetches remote VCS repositories and updates internal cache.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

.. note::

    Usually it is better to configure hooks in the repository to trigger
    :ref:`hooks` instead of regular polling by :djadmin:`updategit`.
