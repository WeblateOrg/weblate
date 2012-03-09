Configuration
-------------

All settings are stored in :file:`settings.py` (as usual for Django).

.. envvar:: COMMIT_MESSAGE

    Message used on each commit Weblate does.

.. envvar:: ENABLE_HOOKS

    Whether to enable anonymous remote hooks.

    .. seealso:: :ref:`hooks`

.. envvar:: GIT_ROOT

    Path where Weblate will store cloned Git repositories. Defaults to
    :file:`repos` subdirectory.

.. envvar:: MT_APERTIUM_KEY

    API key for Apertium Web Service, you can register at http://api.apertium.org/register.jsp

.. envvar:: SITE_TITLE

    Site title to be used in website and emails as well.


.. seealso:: https://docs.djangoproject.com/en/1.3/ref/settings/
