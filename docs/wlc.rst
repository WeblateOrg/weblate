.. index::
    single: wlc
    single: API

.. _wlc:

Weblate Client
==============

.. program:: wlc

.. versionadded:: 2.7

    The wlc utility is fully supported since Weblate 2.7. If you are using older version
    some incompatibilities with API might occur.

Instalation
+++++++++++

The Weblate Client is shipped separately, you need to install wlc to have it,
it also includes Python module :mod:`wlc`:

.. code-block:: sh

    pip install wlc

Synopsis
++++++++

.. code-block:: text

    wlc [parameter] <command> [options]

Commands actually indicate which operation should be performed.

Description
+++++++++++

Weblate Client is Python library and command line utility to manage Weblate remotely
using :ref:`api`. The command line utility can be invoked as :command:`wlc` and is
build on :mod:`wlc`.

Global options
--------------

The program accepts following global options, which must be entered before subcommand.

.. option:: --format {csv,json,text,html}

    Specify output format.

.. option:: --url URL

    Specify API URL. Overrides value from configuration file, see :ref:`files`.
    The URL should end with ``/api/``, for example ``https://hosted.weblate.org/api/``.

.. option:: --key KEY

    Specify API user key to use. Overrides value from configuration file, see :ref:`files`.
    You can figure out your key in your profile in Weblate.

.. option:: --config PATH

    Override path to configuration file, see :ref:`files`.

.. option:: --config-section SECTION

    Override section to use in configuration file, see :ref:`files`.

Subcommands
-----------

Currently following subcommands are available:

.. option:: version

    Prints current version.

.. option:: list-languages

    List used languages in Weblate.

.. option:: list-projects

    List projects in Weblate.

.. option:: list-components

    List components in Weblate.

.. option:: list-translations

    List translations in Weblate.

.. option:: show

    Shows Weblate object (translation, component or project).

.. option:: ls

    Lists Weblate object (translation, component or project).

.. option:: commit

    Commits changes in Weblate object (translation, component or project).

.. option:: pull

    Pulls remote repository changes into Weblate object (translation, component or project).

.. option:: push

    Pusches changes in Weblate object into remote repository (translation, component or project).

.. option:: repo

    Displays repository status for given Weblate object (translation, component or project).

.. option:: statistics

    Displays detailed statistics for given Weblate object (translation or component).

.. _files:

Files
+++++

:file:`.weblate`
    Per project configuration file
:file:`~/.config/weblate`
    User configuration file
:file:`/etc/xdg/weblate`
    Global configration file

The program follows XDG specification, so you can adjust placement of config files
by environment variables ``XDG_CONFIG_HOME`` or ``XDG_CONFIG_DIRS``.

Following settings can be configured in the ``[weblate]`` section (you can
customize this by :option:`--config-section`):

.. describe:: key 

    API KEY to access Weblate.

.. describe:: url

    API server URL, defaults to ``http://127.0.0.1:8000/api/``.

.. describe:: translation

    Path of default translation, component or project.

The configuration file is INI file, for example:

.. code-block:: ini

    [weblate]
    url = https://hosted.weblate.org/api/
    key = APIKEY
    translation = weblate/master

Additionally API keys can be stored in the ``[keys]`` section:

.. code-block:: ini

    [keys]
    https://hosted.weblate.org/api/ = APIKEY

This allows you to store keys in your personal settings, while having
:file:`.weblate` configuration in the VCS repository so that wlc knows to which
server it should talk.

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
    source_language: en
    url: http://example.com/api/projects/hello/
    web: http://weblate.org/
    web_url: http://example.com/projects/hello/

You can also let wlc know current project and it will then operate on it:

.. code-block:: sh

    $ cat .weblate 
    [weblate]
    url = https://hosted.weblate.org/api/
    translation = weblate/master
    
    $ wlc show
    branch: master
    file_format: po
    filemask: weblate/locale/*/LC_MESSAGES/django.po
    git_export: git://git.weblate.org/weblate.git
    license: GPL-3.0+
    license_url: https://spdx.org/licenses/GPL-3.0+
    name: master
    new_base: weblate/locale/django.pot
    project: weblate
    repo: git://github.com/nijel/weblate.git
    slug: master
    template: 
    url: https://hosted.weblate.org/api/components/weblate/master/
    vcs: git
    web_url: https://hosted.weblate.org/projects/weblate/master/


With such setup it is easy to commit pending changes in current project:

.. code-block:: sh

    $ wlc commit
