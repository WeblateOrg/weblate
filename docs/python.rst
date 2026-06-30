.. index::
    single: Python
    single: API

.. _python:

Weblate's Python API
~~~~~~~~~~~~~~~~~~~~

Installation
============

The Python API is shipped separately as the :pypi:`Weblate Client <wlc>`
package:

.. code-block:: sh

    pip install wlc

:mod:`wlc`
==========

.. module:: wlc
    :synopsis: Weblate API

:exc:`WeblateException`
-----------------------

.. exception:: WeblateException

    Base class for all exceptions.

:class:`Weblate`
----------------

.. class:: Weblate(key='', url='http://127.0.0.1:8000/api/', config=None, retries=0, status_forcelist=None, allowed_methods=None, backoff_factor=0, timeout=300, allow_insecure_http=False)

    :param key: User key
    :type key: str
    :param url: API server URL.
    :type url: str
    :param config: Configuration object, overrides any other parameters.
    :type config: wlc.config.WeblateConfig
    :param retries: Total number of HTTP retries.
    :type retries: int
    :param status_forcelist: HTTP status codes that should trigger retries.
    :type status_forcelist: list
    :param allowed_methods: HTTP methods that may be retried.
    :type allowed_methods: list
    :param backoff_factor: Retry backoff factor passed to urllib3.
    :type backoff_factor: float
    :param timeout: HTTP request timeout in seconds.
    :type timeout: int
    :param allow_insecure_http: Allow API keys over non-local ``http://`` URLs.
    :type allow_insecure_http: bool

    Access class to the API, define API key and optionally API URL. When an API
    key is configured, non-local ``http://`` URLs are rejected by default. Use
    HTTPS, loopback HTTP for local development, or set ``allow_insecure_http``
    only for legacy deployments where HTTPS is not available.

    .. method:: get(path)

        :param path: Request path
        :type path: str
        :rtype: object

        Performs a single API GET call.

    .. method:: post(path, **kwargs)

        :param path: Request path
        :type path: str
        :rtype: object

        Performs a single API POST call.


:mod:`wlc.config`
=================

.. module:: wlc.config
    :synopsis: Configuration parsing

.. exception:: WLCConfigurationError

    Raised when configuration can not be loaded or combines an unscoped API key
    with an automatically discovered project API URL.

:class:`WeblateConfig`
----------------------

.. class:: WeblateConfig(section='weblate')

    :param section: Configuration section to use
    :type section: str

    Configuration file parser following XDG specification.


    .. method:: load(path=None)

        :param path: Path from which to load configuration.
        :type path: str

        Loads configuration from ``path`` when it is specified. Otherwise it
        loads the discovered global configuration file and then the nearest
        project configuration file (:file:`.weblate`,
        :file:`.weblate.ini`, or :file:`weblate.ini`) from the current
        directory or its parents.

    .. method:: validate_url_key()

        Validates the resolved API URL and key sources.

        When the API URL comes from an automatically discovered project
        configuration file, unscoped keys must pin the destination explicitly:
        :envvar:`WLC_KEY` requires :envvar:`WLC_URL`, and a key set through the
        command-line configuration path requires an explicit URL from the same
        path. URL-scoped ``[keys]`` entries continue to work with project
        configuration.

    .. method:: get_url_key()

        :returns: tuple with the resolved API URL and API key

        Returns the resolved API URL and key and performs the same validation as
        :meth:`validate_url_key`.

    .. method:: get_allow_insecure_http()

        :returns: whether API keys may be sent over non-local ``http://`` URLs

        Resolves the insecure HTTP opt-in from command-line configuration,
        :envvar:`WLC_ALLOW_INSECURE_HTTP`, or the ``allow_insecure_http``
        configuration option. Automatically discovered project configuration
        cannot enable this option. The opt-in is enable-only: false or unset
        command-line and environment sources do not disable an enabled
        configuration option.


:mod:`wlc.main`
===============

.. module:: wlc.main
    :synopsis: Command-line interface

.. function:: main(settings=None, stdout=None, args=None)

    :param settings: Settings to override as list of tuples
    :type settings: list
    :param stdout: stdout file object for printing output, uses ``sys.stdout`` as default
    :type stdout: object
    :param args: Command-line arguments to process, uses ``sys.args`` as default
    :type args: list

    Main entry point for command-line interface.

.. decorator:: register_command(command)

    Decorator to register :class:`Command` class in main parser used by
    :func:`main`.

:class:`Command`
----------------

.. class:: Command(args, config, stdout=None)

    Main class for invoking commands.
