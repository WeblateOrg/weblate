.. index::
    single: wlc
    single: API

.. _wlc:

Weblate Client
==============

.. program:: wlc

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

.. _files:

Files
+++++

:file:`~/.config/wlc`
    User configuration file
:file:`/etc/xdg/wlc`
    Global configration file

The program follows XDG specification, so you can adjust placement of config files
by environment variables ``XDG_CONFIG_HOME`` or ``XDG_CONFIG_DIRS``.

Following settings can be configured in the ``[wlc]`` section (you can
customize this by :option:`--config-section`):

.. describe:: key 

    API KEY to access Weblate.

.. describe:: url

    API server URL, defaults to ``http://127.0.0.1:8000/api/``.

The configuration file is INI file, for example:

.. code-block:: ini

    [wlc]
    url = https://hosted.weblate.org/api/
    key = APIKEY

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
