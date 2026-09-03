.. index::
    single: wlc
    single: API

.. _wlc:

Weblate Client
==============

.. program:: wlc

Installation
++++++++++++

The :pypi:`Weblate Client <wlc>` is shipped separately and includes the Python
module.
The source code is maintained in the `WeblateOrg/wlc repository
<https://github.com/WeblateOrg/wlc>`_.
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

Images are published on `Docker Hub <https://hub.docker.com/r/weblate/wlc>`_
and the `GitHub Container Registry
<https://github.com/WeblateOrg/wlc/pkgs/container/wlc>`_. The examples below
use the Docker Hub image name.

Installing:

.. code-block:: sh

    docker pull weblate/wlc

The following tags are available:

``latest``
    Latest stable release.
Full version, for example ``2.2.0``
    A specific stable release.
Major version, for example ``2``
    Latest stable release in that major series.
``edge``
    Current development version from the main branch.
``edge-YYYY-MM-DD-COMMIT``
    A specific development snapshot.

To build an image from the source checkout:

.. code-block:: sh

    docker build -t weblate/wlc .

The Docker container uses Weblate Client defaults and connects to the API
deployed on localhost. Configure the API URL and API key using the normal
:program:`wlc` arguments or environment variables, for example :option:`--url`,
:option:`--key`, :envvar:`WLC_URL`, and :envvar:`WLC_KEY`.
API keys are rejected over non-local ``http://`` URLs by default; use HTTPS,
loopback HTTP for local development, or explicitly opt in to insecure HTTP.

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

When the mounted repository provides the API URL in project configuration and
you pass an unscoped API key to the container, also pin the URL explicitly:
:envvar:`WLC_KEY` requires :envvar:`WLC_URL`, and :option:`--key` requires
:option:`--url`. The same pairing is required for the
:option:`--allow-insecure-http` and :option:`--allow-insecure-ssl` overrides.

If the configured API URL uses non-local ``http://`` and an API key is
provided, the container refuses to send the key unless insecure HTTP is
explicitly enabled. Prefer HTTPS; for legacy deployments, pass
:option:`--allow-insecure-http` or set :envvar:`WLC_ALLOW_INSECURE_HTTP`.
TLS certificates are always verified by default, including for loopback URLs.
Use :option:`--allow-insecure-ssl` or :envvar:`WLC_ALLOW_INSECURE_SSL` only
when certificate verification can not be enabled.


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

.. versionchanged:: 2.2.0

   Global ``allow_insecure_http`` configuration is no longer supported.
   Configure an origin in the ``[insecure_http]`` section instead.

Migrate legacy configuration:

.. code-block:: ini

   [weblate]
   url = https://hosted.weblate.org/api/
   key = YOUR_KEY_HERE

To a configuration with key scoped to an API URL:

.. code-block:: ini

   [weblate]
   url = https://hosted.weblate.org/api/

   [keys]
   https://hosted.weblate.org/api/ = YOUR_KEY_HERE

Synopsis
++++++++

.. code-block:: text

    wlc [arguments] <command> [options]

Commands actually indicate which operation should be performed.

Description
+++++++++++

Weblate Client is a Python library and command-line utility to manage Weblate
remotely using :ref:`api`. Invoke the command-line utility as
:command:`wlc`; see :mod:`wlc` for the Python API.

Arguments
---------

The program accepts the following arguments which define output format or which
Weblate instance to use. These must be entered before any command.

.. option:: --format {csv,json,text,html}

    Specify the output format. The default is ``text``.

.. option:: --version

    Print the program version and exit. The :option:`version` command supports
    output formatting and can print only the version number.

.. option:: --debug

    Print verbose HTTP communication. Authorization header values are redacted
    and request bodies are not logged, but query parameters are; do not put
    secrets in query parameters.

.. option:: --url URL

    Specify the API URL. Overrides any value found in the configuration file, see :ref:`wlc-config`.
    The URL should end with ``/api/``, for example ``https://hosted.weblate.org/api/``.

.. option:: --key KEY

    Specify the API user key to use. Overrides any value found in the configuration file, see :ref:`wlc-config`.
    You can find your key in your profile on Weblate.
    When the API URL is loaded from automatically discovered project
    configuration, :option:`--key` must be used together with :option:`--url`.
    API keys are rejected over non-local ``http://`` URLs by default.

.. option:: --allow-insecure-http

    Allow sending API keys over non-local ``http://`` URLs. Prefer HTTPS or
    loopback HTTP instead; this option is intended only for legacy deployments
    where HTTPS is not available. This option only enables insecure HTTP for
    the current run. When the API URL comes from automatically discovered
    project configuration, this option requires :option:`--url`.

.. option:: --allow-insecure-ssl

    Disable TLS certificate verification for the current run. Certificates are
    verified by default for every HTTPS URL, including loopback URLs. When the
    API URL comes from automatically discovered project configuration, this
    option requires :option:`--url`.

.. option:: --config PATH

    Load configuration only from ``PATH`` instead of the discovered global and
    project configuration files, see :ref:`wlc-config`.

.. option:: --config-section SECTION

    Selects the configuration file section to use instead of ``[weblate]``, see
    :ref:`wlc-config`.

Object paths
------------

Commands that operate on an object accept one of these paths:

``PROJECT``
    Project slug.
``PROJECT/COMPONENT``
    Component slug, including its project.
``PROJECT/COMPONENT/LANGUAGE``
    Translation language, including its project and component.
``UNIT_ID``
    Numeric translation unit ID. Only commands that explicitly support units
    accept this form.

Commands that require an object use the ``translation`` setting from
:ref:`wlc-config` when the path is omitted. The :option:`ls` and
:option:`download` commands also use this setting before falling back to their
no-object behavior. For :option:`list-components` and
:option:`list-translations`, an omitted object always requests an instance-wide
list.

Commands
--------

The following commands are available:

.. option:: version

    Prints the current version.

    .. option:: --bare

        Prints only the version number.

.. option:: list-languages

    Lists all languages in Weblate.

.. option:: list-projects

    Lists all projects in Weblate.

.. option:: list-components

    Lists all components in Weblate, or components in the specified project.

.. option:: list-translations

    Lists all translations in Weblate, or translations in the specified
    component.

.. option:: list-units

    Lists units in the specified translation.

    .. option:: --query QUERY

        Filters units using the :doc:`search query syntax </user/search>`.

.. option:: show

    Shows a project, component, translation, or unit.

.. option:: delete

    Deletes a project, component, translation, or unit without a confirmation
    prompt.

.. option:: ls

    Lists all projects when no object is specified, components in a project, or
    translations in a component.

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

    Displays the lock status of a component.

.. option:: lock

    Locks component from further translation in Weblate.

.. option:: unlock

    Unlocks translation of Weblate component.

.. option:: changes

    Displays changes for a project, component, or translation.

.. option:: download

    Downloads translation files. For a translation, :program:`wlc` writes the
    file to :option:`--output` or to redirected standard output. It refuses to
    write raw file content to an interactive terminal.

    For a component or project, :option:`--output` is required and is treated
    as a directory. :program:`wlc` writes one ZIP archive per component. With
    no object, it downloads every component in the Weblate instance in the same
    way.

    .. option:: --convert FORMAT

        Requests conversion to ``FORMAT`` on the server. If unspecified, no
        conversion happens.

    .. option:: --output PATH

        Specifies the output file for a translation or output directory for a
        component, project, or instance-wide download. Use ``-`` to write a
        translation to standard output.

    .. option:: --no-glossary

        Excludes glossary components from component, project, and instance-wide
        downloads.

.. option:: upload

    Uploads a translation file.

    .. option:: --overwrite

        Overwrites existing translated strings. This is equivalent to
        ``--conflicts replace-translated``.

    .. option:: --conflicts {ignore,replace-translated,replace-approved}

        Selects how conflicts with existing translations are handled.

    .. option:: --input PATH

        Reads content from ``PATH``. If unspecified or ``-``, content is read
        from standard input.

    .. option:: --method {translate,approve,suggest,fuzzy,replace,source,add}

        Upload method to use, see :ref:`upload-method`. The default is
        ``translate``.

    .. option:: --fuzzy {process,approve}

        Selects processing of fuzzy strings (marked for edit).

    .. option:: --author-name NAME

        Author name, to override currently authenticated user

    .. option:: --author-email EMAIL

        Author e-mail, to override currently authenticated user

.. option:: edit-unit

    Updates a translation unit. At least one update option is required.

    .. option:: --target TARGET [TARGET ...]

        Sets one or more translated strings.

    .. option:: --state STATE

        Sets the unit state: ``0`` for empty, ``10`` for fuzzy, ``20`` for
        translated, or ``30`` for approved.

    .. option:: --explanation EXPLANATION

        Sets the string explanation.

    .. option:: --extra-flags FLAGS

        Sets additional string flags.


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
:file:`~/.config/weblate.ini`
    Alternative global configuration filename on Unix-like systems.
:file:`/etc/xdg/weblate`
    System-wide fallback configuration file.
:file:`/etc/xdg/weblate.ini`
    Alternative system-wide fallback filename.

The program follows the XDG specification, so you can adjust the placement of
config files by environment variables ``XDG_CONFIG_HOME`` or
``XDG_CONFIG_DIRS``.

On Windows ``APPDATA`` and ``LOCALAPPDATA`` directories are the preferred
locations for the configuration file.

After loading the global configuration, :program:`wlc` loads the nearest
project configuration file from the current directory or its parents:

:file:`.weblate`, :file:`.weblate.ini`, :file:`weblate.ini`
    Project configuration file placed in the repository.

Project configuration is loaded after global configuration and overrides
matching settings. It can select the API URL, default object, request settings,
and a matching URL-scoped API key, allowing a cloned repository to
automatically select its Weblate server and translation.

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

    Default object path for commands that accept one: a project, component,
    translation, or numeric unit ID.

.. describe:: retries, timeout, allowed_methods, backoff_factor, status_forcelist

    HTTP request retry and timeout settings. ``retries`` defaults to ``0`` and
    ``backoff_factor`` to ``0``. ``status_forcelist`` is a comma-separated list
    of HTTP status codes that trigger retries and is empty by default.

    ``allowed_methods`` lists methods that may be retried, separated by commas
    or whitespace. It defaults to ``HEAD``, ``DELETE``, ``OPTIONS``, ``PUT``,
    and ``GET``. These retry settings are passed to ``urllib3.util.Retry``.

    ``timeout`` is the request timeout in seconds and defaults to ``300``.
    Current :program:`wlc` releases use ``allowed_methods`` in place of the
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
:file:`.weblate` configuration in the VCS repository so that :program:`wlc`
knows which server it should talk to. The ``[keys]`` lookup is scoped to the
complete configured API URL, not merely its network origin.

Project configuration can also supply or replace a matching entry in
``[keys]``. Do not commit valuable API keys to version control; normally keep
keys in personal configuration and only the API URL and default object in
project configuration.

Insecure transport exceptions are stored in origin-scoped sections in trusted
user configuration:

.. code-block:: ini

    [insecure_http]
    http://legacy.example.com:80 = true

    [insecure_ssl]
    https://legacy.example.com:443 = true

An origin consists of the scheme, normalized hostname, and effective port. The
API path is ignored, while different schemes and ports remain isolated. The
``[insecure_http]`` section allows API keys over non-local HTTP for matching
origins. The ``[insecure_ssl]`` section disables TLS certificate verification
for matching origins.

.. versionchanged:: 2.2.0

   TLS certificates are verified for all hosts by default. Insecure HTTP and
   TLS configuration is scoped to origins. Automatically discovered project
   configuration can neither add entries to these sections nor enable the
   removed global settings. User configuration and explicitly selected
   :option:`--config` files are trusted.

In CI, unscoped keys must pin the API URL explicitly: set both
:envvar:`WLC_URL` and :envvar:`WLC_KEY`, or use :option:`--url` together with
:option:`--key`.


Environment variables
+++++++++++++++++++++

.. versionadded:: 1.18.0

.. versionchanged:: 2.0.1

   Unscoped API keys require an explicit API URL when project configuration is
   discovered automatically. API keys are rejected over non-local ``http://``
   URLs unless insecure HTTP is explicitly enabled.

.. versionchanged:: 2.2.0

   Insecure HTTP and TLS environment overrides require :envvar:`WLC_URL` when
   the API URL would otherwise come from automatically discovered project
   configuration.

The API URL and key can also be configured using environment variables. This is
especially useful for CI workflows where :envvar:`WLC_URL` pins the destination
and :envvar:`WLC_KEY` is injected as a secret:

.. envvar:: WLC_URL

   API URL

.. envvar:: WLC_KEY

   API key. When the API URL would otherwise come from automatically discovered
   project configuration, :envvar:`WLC_KEY` is accepted only together with
   :envvar:`WLC_URL`. API keys are rejected over non-local ``http://`` URLs by
   default.

.. envvar:: WLC_ALLOW_INSECURE_HTTP

   Set to ``1``, ``true``, ``yes``, or ``on`` to allow API keys over non-local
   ``http://`` URLs. Prefer HTTPS or loopback HTTP instead. Other values, such
   as ``0`` or ``false``, are treated as unset. When the API URL would otherwise
   come from automatically discovered project configuration, this variable is
   accepted only together with :envvar:`WLC_URL`.

.. envvar:: WLC_ALLOW_INSECURE_SSL

   Set to ``1``, ``true``, ``yes``, or ``on`` to disable TLS certificate
   verification. Other values, such as ``0`` or ``false``, are treated as
   unset. When the API URL would otherwise come from automatically discovered
   project configuration, this variable is accepted only together with
   :envvar:`WLC_URL`.

The same protection applies to command-line arguments: :option:`--key`,
:option:`--allow-insecure-http`, and :option:`--allow-insecure-ssl` are accepted
with automatically discovered project configuration only when :option:`--url`
is provided.

The API URL and key configuration precedence (highest to lowest) is:

1. Command-line arguments (:option:`--url`, :option:`--key`).
2. Environment variables (:envvar:`WLC_URL`, :envvar:`WLC_KEY`).
3. Configuration loaded from :option:`--config`, or from the discovered global
   configuration plus the nearest project configuration when
   :option:`--config` is not used.

The insecure transport opt-ins are enable-only rather than normal precedence
settings. They are enabled by a command-line or environment override, or by a
matching origin in the trusted ``[insecure_http]`` or ``[insecure_ssl]``
section. Automatically discovered project configuration cannot add trusted
origins.

.. _wlc-security:

Security model
++++++++++++++

Project configuration is part of the repository workflow and is intentionally
trusted to select the API endpoint, default object, request settings, and a
matching URL-scoped API key. Running :program:`wlc` inside a repository
authorizes its nearest project configuration to select the server that receives
commands and uploads and supplies displayed or downloaded content. Use an
explicit trusted :option:`--config` file when this is not desired.

The command-line client accepts API keys from :option:`--key`,
:envvar:`WLC_KEY`, or the ``[keys]`` section. It does not load HTTP
authentication from :file:`.netrc` or the file named by ``NETRC``. Credentials
embedded in API URLs are rejected; use an API key instead. Other Requests
environment integration, including proxy and CA-bundle variables, remains
enabled.

The `wlc threat model
<https://github.com/WeblateOrg/wlc/blob/main/THREAT_MODEL.md>`_ documents the
complete trust boundaries, security properties, non-goals, and downstream
responsibilities. A version-matched copy is included in source and wheel
distributions. Report security issues using the :ref:`Weblate vulnerability
reporting process <security>`.

Examples
++++++++

Print current program version:

.. code-block:: sh

    $ wlc version

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
