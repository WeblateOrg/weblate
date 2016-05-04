.. index::
    single: Python
    single: API

.. _python:

Weblate's Python API
~~~~~~~~~~~~~~~~~~~~

Instalation
===========

The Python API is shipped separately, you need to install wlc to have it,
it also include :ref:`wlc`:

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

.. class:: Weblate(key='', url=None, config=None):

    :param key: User key
    :type key: string
    :param url: API server URL, if not specified default is used
    :type url: string
    :param config: Configuration object, overrides any other parameters.
    :type config: WeblateConfig

    Access class to the API, define API key and optionally API URL.

    .. method:: get(path)

        :param path: Request path
        :type path: string
        :rtype: object

        Performs single API GET call.

    .. method:: post(path, **kwargs)

        :param path: Request path
        :type path: string
        :rtype: object

        Performs single API GET call.


:mod:`wlc.config`
====================

.. module:: wlc.config
    :synopsis: Configuration parsing

:class:`WeblateConfig`
----------------------

.. class:: WeblateConfig(section='wlc')
    
    :param section: Configuration section to use
    :type section: string

    Configuration file parser following XDG specification.


    .. method:: load(path=None)

        :param path: Path where to load configuration.
        :type path: string

        Loads configuration from a file, if none is specified it loads from
        `wlc` configuration file placed in XDG configuration path
        (:file:`~/.config/wlc` and :file:`/etc/xdg/wlc`).


:mod:`wlc.main`
===============

.. module:: wlc.main
    :synopsis: Command line interface

.. function:: main(settings=None, stdout=None, args=None)

    :param settings: settings to override
    :type settings: list of tuples
    :param stdout: stdout for printing output, uses ``sys.stdout`` as default
    :type stdout: file
    :param args: command line argumets to process, uses ``sys.args`` as default
    :type args: list

    Main entry point for command line interface.

.. decorator:: register_command(command)

    Decorator to register :class:`Command` class in main parser used by
    :func:`main`.

:class:`Command`
----------------

.. class:: Command(args, config, stdout=None)

    Main class for invoking commands.
