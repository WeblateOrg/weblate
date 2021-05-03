.. index::
    single: wlc
    single: API

.. _wlc:

Weblate Client
==============

.. program:: wlc

.. versionadded:: 2.7

    There has been full wlc utility support ever since Weblate 2.7. If you are using an older version
    some incompatibilities with the API might occur.

Installation
++++++++++++

The Weblate Client is shipped separately and includes the Python module.
To use the commands below, you need to install :mod:`wlc`:

.. code-block:: sh

    pip3 install wlc

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

You might want to pass your :ref:`wlc-config` to the Docker container, the
easiest approach is to add your current directory as :file:`/home/weblate`
volume:

.. code-block:: sh

   docker run --volume $PWD:/home/weblate --rm weblate/wlc show


Getting started
+++++++++++++++

The wlc configuration is stored in ``~/.config/weblate`` (see :ref:`wlc-config`
for other locations), please create it to match your environment:

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

    Overrides the configuration file path, see :ref:`wlc-config`.

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

    .. versionadded:: 0.7

        Supported since wlc 0.7.

    Resets changes in Weblate object to match remote repository (translation, component or project).

.. option:: cleanup

    .. versionadded:: 0.9

        Supported since wlc 0.9.

    Removes any untracked changes in a Weblate object to match the remote repository (translation, component or project).

.. option:: repo

    Displays repository status for a given Weblate object (translation, component or project).

.. option:: statistics

    Displays detailed statistics for a given Weblate object (translation, component or project).

.. option:: lock-status

    .. versionadded:: 0.5

        Supported since wlc 0.5.

    Displays lock status.

.. option:: lock

    .. versionadded:: 0.5

        Supported since wlc 0.5.

    Locks component from further translation in Weblate.

.. option:: unlock

    .. versionadded:: 0.5

        Supported since wlc 0.5.

    Unlocks translation of Weblate component.

.. option:: changes

    .. versionadded:: 0.7

        Supported since wlc 0.7 and Weblate 2.10.

    Displays changes for a given object.

.. option:: download

    .. versionadded:: 0.7

        Supported since wlc 0.7.

    Downloads a translation file.

    .. option:: --convert

        Converts file format, if unspecified no conversion happens on the server
        and the file is downloaded as is to the repository.

    .. option:: --output

        Specifies file to save output in, if left unspecified it is printed to stdout.

.. option:: upload

    .. versionadded:: 0.9

        Supported since wlc 0.9.

    Uploads a translation file.

    .. option:: --overwrite

        Overwrite existing translations upon uploading.

    .. option:: --input

        File from which content is read, if left unspecified it is read from stdin.

.. hint::

   You can get more detailed information on invoking individual commands by
   passing ``--help``, for example: ``wlc ls --help``.

.. _wlc-config:

Configuration files
+++++++++++++++++++

:file:`.weblate`, :file:`.weblate.ini`, :file:`weblate.ini`
    .. versionchanged:: 1.6

        The files with `.ini` extension are accepted as well.

    Per project configuration file
:file:`C:\\Users\\NAME\\AppData\\weblate.ini`
    .. versionadded:: 1.6

    User configuration file on Windows.
:file:`~/.config/weblate`
    User configuration file
:file:`/etc/xdg/weblate`
    System wide configuration file

The program follows the XDG specification, so you can adjust placement of config files
by environment variables ``XDG_CONFIG_HOME`` or ``XDG_CONFIG_DIRS``. On Windows
``APPDATA`` directory is preferred location for the configuration file.

Following settings can be configured in the ``[weblate]`` section (you can
customize this by :option:`--config-section`):

.. describe:: key

    API KEY to access Weblate.

.. describe:: url

    API server URL, defaults to ``http://127.0.0.1:8000/api/``.

.. describe:: translation

    Path to the default translation - component or project.

The configuration file is an INI file, for example:

.. code-block:: ini

    [weblate]
    url = https://hosted.weblate.org/api/
    key = APIKEY
    translation = weblate/application

Additionally API keys can be stored in the ``[keys]`` section:

.. code-block:: ini

    [keys]
    https://hosted.weblate.org/api/ = APIKEY

This allows you to store keys in your personal settings, while using the
:file:`.weblate` configuration in the VCS repository so that wlc knows which
server it should talk to.

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

You can also designate what project wlc should work on:

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
