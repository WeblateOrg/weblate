.. index::
    single: wlc
    single: API

.. _wlc:

Weblate Client
==============

.. program:: wlc

Installation
++++++++++++

The Weblate Client is shipped separately and includes the Python module.
To use the commands below, you need to install :program:`wlc` using pip:

.. code-block:: sh

    pip install wlc

You can also execute it directly using :program:`uvx`:

.. code-block:: sh

   uvx wlc --help

.. hint::

   You can also use this :program:`wlc` as a Python module, see :mod:`wlc`.

.. _docker-wlc:

Docker usage
++++++++++++

The Weblate Client is also available as a Docker image.

The image is published on Docker Hub: https://hub.docker.com/r/weblate/wlc

Installing:

.. code-block:: sh

    docker pull weblate/wlc

The Docker container uses Weblate's default settings and connects to the API
deployed in localhost. The API URL and API_KEY can be configured through the
arguments accepted by Weblate.

The command to launch the container uses the following syntax:

.. code-block:: sh

    docker run --rm weblate/wlc [WLC_ARGS]

Example:

.. code-block:: sh

    docker run --rm weblate/wlc --url https://hosted.weblate.org/api/ list-projects

You might want to pass your :ref:`wlc-config` to the Docker container. When
your repository contains a project configuration such as :file:`.weblate`, the
easiest approach is to add your current directory as the
:file:`/home/weblate` volume:

.. code-block:: sh

   docker run --volume $PWD:/home/weblate --rm weblate/wlc show


Getting started
+++++++++++++++

The easiest way to get started is to create a personal
:program:`wlc` configuration in :file:`~/.config/weblate` (see
:ref:`wlc-config` for the full discovery rules and other locations):

.. code-block:: ini

    [weblate]
    url = https://hosted.weblate.org/api/

    [keys]
    https://hosted.weblate.org/api/ = APIKEY


You can then invoke commands on the default server:

.. code-block:: console

    wlc ls
    wlc commit sandbox/hello-world

.. seealso::

    :ref:`wlc-config`

.. _wlc_legacy:

Legacy configuration
++++++++++++++++++++

.. versionchanged:: 1.17

   The legacy configuration using unscoped ``key`` is no longer supported.

Migrate legacy configuration:

.. code-block:: ini

   [weblate]
   url = https://hosted.weblate.org/api
   key = YOUR_KEY_HERE

To a configuration with key scoped to an API URL:

.. code-block:: ini

   [weblate]
   url = https://hosted.weblate.org/api

   [keys]
   https://hosted.weblate.org/api = YOUR_KEY_HERE

Synopsis
++++++++

.. code-block:: text

    wlc [arguments] <command> [options]

Commands actually indicate which operation should be performed.

Description
+++++++++++

Weblate Client is a Python library and command-line utility to manage Weblate remotely
using :ref:`api`. The command-line utility can be invoked as :command:`wlc` and is
built-in on :mod:`wlc`.

Arguments
---------

The program accepts the following arguments which define output format or which
Weblate instance to use. These must be entered before any command.

.. option:: --format {csv,json,text,html}

    Specify the output format.

.. option:: --url URL

    Specify the API URL. Overrides any value found in the configuration file, see :ref:`wlc-config`.
    The URL should end with ``/api/``, for example ``https://hosted.weblate.org/api/``.

.. option:: --key KEY

    Specify the API user key to use. Overrides any value found in the configuration file, see :ref:`wlc-config`.
    You can find your key in your profile on Weblate.

.. option:: --config PATH

    Load configuration only from ``PATH`` instead of the discovered global and
    project configuration files, see :ref:`wlc-config`.

.. option:: --config-section SECTION

    Overrides configuration file section in use, see :ref:`wlc-config`.

Commands
--------

The following commands are available:

.. option:: version

    Prints the current version.

.. option:: list-languages

    Lists used languages in Weblate.

.. option:: list-projects

    Lists projects in Weblate.

.. option:: list-components

    Lists components in Weblate.

.. option:: list-translations

    Lists translations in Weblate.

.. option:: show

    Shows Weblate object (translation, component or project).

.. option:: ls

    Lists Weblate object (translation, component or project).

.. option:: commit

    Commits changes made in a Weblate object (translation, component or project).

.. option:: pull

    Pulls remote repository changes into Weblate object (translation, component or project).

.. option:: push

    Pushes Weblate object changes into remote repository (translation, component or project).

.. option:: reset

    Resets changes in Weblate object to match remote repository (translation, component or project).

.. option:: cleanup

    Removes any untracked changes in a Weblate object to match the remote repository (translation, component or project).

.. option:: repo

    Displays repository status for a given Weblate object (translation, component or project).

.. option:: stats

    Displays detailed statistics for a given Weblate object (translation, component or project).

.. option:: lock-status

    Displays lock status.

.. option:: lock

    Locks component from further translation in Weblate.

.. option:: unlock

    Unlocks translation of Weblate component.

.. option:: changes

    Displays changes for a given object.

.. option:: download

    Downloads a translation file.

    .. option:: --convert

        Converts file format, if unspecified no conversion happens on the server
        and the file is downloaded as is to the repository.

    .. option:: --output

        Specifies file to save output in, if left unspecified it is printed to stdout.

.. option:: upload

    Uploads a translation file.

    .. option:: --overwrite

        Overwrite existing translations upon uploading.

    .. option:: --input

        File from which content is read, if left unspecified it is read from stdin.

    .. option:: --method

        Upload method to use, see :ref:`upload-method`.

    .. option:: --fuzzy

        Fuzzy (marked for edit) strings processing (*empty*, ``process``, ``approve``)

    .. option:: --author-name

        Author name, to override currently authenticated user

    .. option:: --author-email

        Author e-mail, to override currently authenticated user


.. hint::

   You can get more detailed information on invoking individual commands by
   passing ``--help``, for example: ``wlc ls --help``.

.. _wlc-config:

Configuration files
+++++++++++++++++++

When :option:`--config` is provided, :program:`wlc` loads only that file.

Without :option:`--config`, :program:`wlc` first loads the discovered global
configuration file from the standard platform-specific locations:

:file:`C:\\Users\\NAME\\AppData\\Roaming\\weblate.ini`
    Global configuration file on Windows in the roamed profile.
:file:`C:\\Users\\NAME\\AppData\\Local\\weblate.ini`
    Global configuration file on Windows in the local profile.
:file:`~/.config/weblate`
    Global configuration file on Unix-like systems.
:file:`/etc/xdg/weblate`
    System-wide fallback configuration file.

The program follows the XDG specification, so you can adjust the placement of
config files by environment variables ``XDG_CONFIG_HOME`` or
``XDG_CONFIG_DIRS``.

On Windows ``APPDATA`` and ``LOCALAPPDATA`` directories are the preferred
locations for the configuration file.

After loading the global configuration, :program:`wlc` loads the nearest
project configuration file from the current directory or its parents:

:file:`.weblate`, :file:`.weblate.ini`, :file:`weblate.ini`
    Project configuration file placed in the repository.

Only the closest project configuration file is loaded. Configuration files in
farther parent directories are ignored.

Following settings can be configured in the ``[weblate]`` section (you can
customize this by :option:`--config-section`):

.. describe:: key

   .. versionremoved:: 1.17

      Use the ``[keys]`` section to specify keys scoped for individual API URLs, see :ref:`wlc_legacy`.

.. describe:: url

    API server URL, defaults to ``http://127.0.0.1:8000/api/``.

.. describe:: translation

    Path to the default translation - component or project.

.. describe:: retries, timeout, allowed_methods, backoff_factor, status_forcelist

    Optional HTTP retry and timeout settings passed to ``urllib3``.
    Use ``allowed_methods`` to list the request methods that may be retried.
    Current :program:`wlc` releases use this setting name in place of the
    older ``method_whitelist`` option.

The configuration file is an INI file, for example:

.. code-block:: ini

    [weblate]
    url = https://hosted.weblate.org/api/
    translation = weblate/application
    retries = 3
    allowed_methods = PUT,POST,GET
    backoff_factor = 0.2
    status_forcelist = 429,500,502,503,504
    timeout = 30

The API keys are stored in the ``[keys]`` section:

.. code-block:: ini

    [keys]
    https://hosted.weblate.org/api/ = APIKEY

This allows you to store keys in your personal settings, while using the
:file:`.weblate` configuration in the VCS repository so that :program:`wlc` knows which
server it should talk to. In CI, keep only the repository configuration in
version control and inject the API key using :envvar:`WLC_KEY`.


Environment variables
+++++++++++++++++++++

.. versionadded:: 1.18.0

The API URL and key can also be configured using environment variables. This is
especially useful for CI workflows where the repository provides the project
configuration and :envvar:`WLC_KEY` is injected as a secret:

.. envvar:: WLC_URL

   API URL

.. envvar:: WLC_KEY

   API key

The configuration precedence (highest to lowest) is:

1. Command-line arguments (:option:`--url`, :option:`--key`).
2. Environment variables (:envvar:`WLC_URL`, :envvar:`WLC_KEY`).
3. Configuration loaded from :option:`--config`, or from the discovered global
   configuration plus the nearest project configuration when
   :option:`--config` is not used.

Examples
++++++++

Print current program version:

.. code-block:: sh

    $ wlc version
    version: 0.1

List all projects:

.. code-block:: sh

    $ wlc list-projects
    name: Hello
    slug: hello
    url: http://example.com/api/projects/hello/
    web: https://weblate.org/
    web_url: http://example.com/projects/hello/

Upload translation file:

.. code-block:: sh

   $ wlc upload project/component/language --input /tmp/hello.po

You can also designate what project :program:`wlc` should work on:

.. code-block:: sh

    $ cat .weblate
    [weblate]
    url = https://hosted.weblate.org/api/
    translation = weblate/application

    $ wlc show
    branch: main
    file_format: po
    source_language: en
    filemask: weblate/locale/*/LC_MESSAGES/django.po
    git_export: https://hosted.weblate.org/git/weblate/application/
    license: GPL-3.0+
    license_url: https://spdx.org/licenses/GPL-3.0+
    name: Application
    new_base: weblate/locale/django.pot
    project: weblate
    repo: git://github.com/WeblateOrg/weblate.git
    slug: application
    template:
    url: https://hosted.weblate.org/api/components/weblate/application/
    vcs: git
    web_url: https://hosted.weblate.org/projects/weblate/application/


With this setup it is easy to commit pending changes in the current project:

.. code-block:: sh

    $ wlc commit
