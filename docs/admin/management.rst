.. _manage:

Management commands
===================

.. note::

    Running management commands under different user than is running your
    webserver can cause wrong permissions on some files, please check
    :ref:`file-permissions` for more details.

Django comes with management script (available as :file:`./manage.py` in
sources or installed as :command:`weblate` when Weblate is installed). It
provides various management commands and Weblate extends it with several
additional commands.

.. _invoke-manage:

Invoking management commands
----------------------------

As mentioned before, invocation depends on how you have installed Weblate.

If you are using source code directly (either tarball or Git checkout), the
management script is :file:`./manage.py` in Weblate sources. Execution can be
done as:

.. code-block:: sh

    python ./manage.py list_versions

If you've istalled Weblate using PIP installer or by :file:`./setup.py` script,
the :command:`weblate` is installed to your path and you can use it to control
Weblate:

.. code-block:: sh

    weblate list_versions

For Docker image, the script is installed same as above, you can execute it
using :command:`docker exec`:

.. code-block:: sh

    docker exec <container> weblate list_versions

With :program:`docker-compose` this is quite similar, you just have to use
:command:`docker-compose run`:

.. code-block:: sh

    docker-compose run <container> weblate list_versions


.. seealso::

    :ref:`docker`,
    :ref:`install-pip`


add_suggestions
---------------

.. django-admin:: add_suggesstions <project> <component> <language> <file>

.. versionadded:: 2.5

Imports translation from the file as a suggestions to given translation. It
skips translations which are same as existing ones, only different ones are
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

Example:

.. code-block:: sh

    ./manage.py --user nijel --inconsistent --source phpmyadmin/master phpmyadmin 4-5 cs

.. seealso:: 
   
   :ref:`auto-translation`

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

Prints current state of backend git repository.

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

    Age in hours for committing, default value can be set by :setting:`COMMIT_PENDING_HOURS`.

This is most useful if executed periodically from cron or similar tool:

.. code-block:: sh

    ./manage.py commit_pending --all --age=48

.. seealso::

    :ref:`production-cron`,
    :setting:`COMMIT_PENDING_HOURS`

cleanuptrans
------------

.. django-admin:: cleanuptrans

Cleanups orphaned checks and translation suggestions.

.. seealso::
   
   :ref:`production-cron`

createadmin
-----------

.. django-admin:: createadmin

Creates ``admin`` account with random password unless it is specified.

.. django-admin-option:: --password PASSWORD
   
    Provide password on the command line and skip generating random one.
    
.. django-admin-option:: --username USERNAME
   
    Use given name instead of ``admin``.

.. django-admin-option:: --email USER@EXAMPLE.COM
   
    Specify admin email.
    
.. django-admin-option:: --name

    Specify admin name (visible).

.. django-admin-option:: --update
   
    Update existing user (you can use this to change password).

.. versionchanged:: 2.9

    Added parameters ``--username``, ``--email``, ``--name`` and ``--update``.

dumpuserdata
------------

.. django-admin:: dumpuserdata <file.json>

Dumps userdata to file for later use by :djadmin:`importuserdata`

This is useful when migrating of merging Weblate instances.

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

    :djadmin:`import_project`


import_project
--------------

.. django-admin:: import_project <project> <gitrepo> <branch> <filemask>

Batch imports components into project based on file mask.

`<project>` names an existing project, into which the components should
be imported.

The `<gitrepo>` defines URL of Git repository to use, and `<branch>` the
git branch.
To import additional translation components, from an existing Weblate component,
use a `weblate://<project>/<component>` URL for the `<gitrepo>`.

The repository is searched for directories matching a double wildcard
(`**`) in the `<filemask>`.
Each of these is then added as a component, named after the matched
directory.
Existing components will be skipped.


.. django-admin-option:: --name-template TEMPLATE

    Customise the component's name, its parameter is a python formatting
    string, which will expect the match from `<filemask>`.

.. django-admin-option:: --base-file-template TEMPLATE

    Customize base file for monolingual translations.

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

.. django-admin-option:: --component-regexp REGEX

    You can override parsing of component name from matched files here. This is
    a regular expression which will be matched against file name (as matched by
    `<filemask>`) and has to contain named groups `name` and `language`. This
    can be also used for excluding files in case they do not match this
    expression. For example: ``(?P<language>.*)/(?P<name>[^-]*)\.po``

.. django-admin-option:: --no-skip-duplicates

    By default the import does skip already existing projects. This is to allow
    repeated importing of same repository. However if you want to force
    importing additional components even if name or slug matches existing one,
    you can do it by passing ``--no-skip-duplicates``. This is generally useful
    for components with long names, which will get truncated on import and many
    of them will get same name or slug.

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
language out of file name like
``src/security/Numerous_security_holes_in_0.10.1.de.po``:

.. code-block:: sh

    ./manage.py import_project \
        --component-regexp 'wiki/src/security/(?P<name>.*)\.([^.]*)\.po$' \
        tails \
        git://git.tails.boum.org/tails master \
        'wiki/src/security/**.*.po'

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
    report possible conflicts on usernames or emails.

You can dump users from existing Django installation using:

.. code-block:: sh

    ./manage.py dumpdata auth.User > users.json

list_ignored_checks
-------------------

.. django-admin:: list_ignored_checks

Lists most frequently ignored checks. This can be useful for tuning your setup,
if users have to ignore too many of consistency checks.

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

    Limit processing to single languaguage.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

lock_translation
----------------

.. django-admin:: lock_translation <project|project/component>

Locks given component for translating. This is useful in case you want to do
some maintenance on underlaying repository.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

.. seealso:: 
   
   :djadmin:`unlock_translation`

pushgit
-------

.. django-admin:: pushgit <project|project/component>

Pushes committed changes to upstream VCS repository. 

.. django-admin-option:: --force-commit

    Force committing any pending changes prior to push.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

rebuild_index
-------------

.. django-admin:: rebuild_index <project|project/component>

Rebuilds index for fulltext search. This might be lengthy operation if you
have huge set of translation units.

.. django-admin-option:: --clean

    Removes all words from database prior updating.

.. django-admin-option:: --optimize

    The index will not be processed again, only it's content will be optimized
    (removing stale entries and merging possibly split index files).

.. seealso:: 
   
   :ref:`fulltext`

update_index
------------

.. django-admin:: update_index

Updates index for fulltext search when :setting:`OFFLOAD_INDEXING` is enabled.

It is recommended to run this frequently (eg. every 5 minutes) to have index
uptodate.

.. seealso:: 
   
   :ref:`fulltext`, :ref:`production-cron`, :ref:`production-indexing`

unlock_translation
------------------

.. django-admin:: unlock_translation <project|project/component>

Unnocks given component for translating. This is useful in case you want to do
some maintenance on underlaying repository.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

.. seealso:: 
   
   :djadmin:`lock_translation`

setupgroups
-----------

.. django-admin:: setupgroups

Configures default groups and optionally assigns all users to default group.

.. django-admin-option:: --move

    Assigns all users to the default group.

.. django-admin-option:: --no-privs-update

    Disables update of existing groups (only adds new ones).

.. seealso:: 
   
   :ref:`privileges`

setuplang
---------

.. django-admin:: setuplang

Setups list of languages (it has own list and all defined in
translate-toolkit).

.. django-admin-option:: --no-update
    
    Disables update of existing languages (only adds new ones).

updatechecks
------------

.. django-admin:: updatechecks <project|project/component>

Updates all check for all units. This could be useful only on upgrades
which do major changes to checks.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

updategit
---------

.. django-admin:: updategit <project|project/component>

Fetches remote VCS repositories and updates internal cache.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.
