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

The :mod:`wlc` module exposes the Weblate API client, API objects returned by
the client, and exceptions raised for common API failures.


:class:`Weblate`
----------------

The :class:`Weblate` class is the main API entry point. It accepts an API key,
an API URL, an optional :class:`wlc.config.WeblateConfig` instance, retry
configuration, request timeout, and the ``allow_insecure_http`` opt-in.

When an API key is configured, non-local ``http://`` URLs are rejected by
default. Use HTTPS, loopback HTTP for local development, or set
``allow_insecure_http`` only for legacy deployments where HTTPS is not
available.

.. autoclass:: Weblate
   :members: get, post, get_object, get_project, get_component, get_translation, get_unit, list_projects, list_components, list_changes, list_units, list_translations, list_languages, list_categories, add_source_string, create_project, create_component, create_language


Exceptions
----------

.. autoexception:: WeblateException

.. autoexception:: WeblatePermissionError

.. autoexception:: WeblateDeniedError

.. autoexception:: WeblateThrottlingError


API objects
-----------

API objects behave as mappings and support deferred loading. Attribute access
loads missing data from the API when needed.

.. autoclass:: Project
   :members: list, statistics, languages, changes, categories, delete, create_component, full_slug

.. autoclass:: Component
   :members: full_slug, list, add_translation, statistics, lock, unlock, lock_status, changes, delete, add_source_string, download, patch

.. autoclass:: Translation
   :members: list, statistics, changes, download, upload, delete, units

.. autoclass:: Unit
   :members: list, patch, put, delete

.. autoclass:: Category
   :members: full_slug

.. autoclass:: Language

.. autoclass:: Change

.. autoclass:: Statistics
   :members: refresh, keys

.. autoclass:: LanguageStats

.. autoclass:: TranslationStatistics

.. autoclass:: ProjectRepository

.. autoclass:: Repository


:mod:`wlc.config`
=================

.. module:: wlc.config
    :synopsis: Configuration parsing

.. autoexception:: WLCConfigurationError

.. autoclass:: WeblateConfig
   :members: find_config, find_project_config, load, validate_url_key, get_url_key, get_request_options
